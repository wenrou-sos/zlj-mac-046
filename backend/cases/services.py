from datetime import datetime, time, timedelta

from django.db import transaction
from django.utils import timezone

from .models import (Case, Deadline, DeadlineEvent, DeadlineRule, DeadlineVersion,
                     Holiday, Lawyer, Reminder)


def _lawyer_links(case):
    return list(case.caselawyer_set.select_related('lawyer'))


def assign_owner_and_reviewer(case, rule=None):
    """按规则上的角色选择负责人/复核人；人员不足时复核人可临时与负责人相同。"""
    links = _lawyer_links(case)
    if not links:
        return None, None

    def pick(role):
        exact = [link.lawyer for link in links if link.role == role]
        if exact:
            return exact[0]
        lead = [link.lawyer for link in links if link.role == 'lead']
        return (lead or [links[0].lawyer])[0]

    owner_role = rule.owner_role if rule else 'lead'
    reviewer_role = rule.reviewer_role if rule else 'assist'
    owner = pick(owner_role)
    reviewer = pick(reviewer_role)
    if reviewer == owner:
        others = [link.lawyer for link in links if link.lawyer_id != owner.id]
        if others:
            reviewer = others[0]
        else:
            reviewer = (Lawyer.objects.exclude(id=owner.id).order_by('id').first()
                        or owner)
    return owner, reviewer


def holiday_id_set():
    return set(Holiday.objects.values_list('holiday_date', flat=True))


def is_workday(day, holidays=None):
    holidays = holiday_id_set() if holidays is None else holidays
    return day.weekday() < 5 and day not in holidays


def calculate_due_date(rule, event_date, holidays=None):
    """按自然日/工作日计算，start_timing 控制事件当日或次日起算。"""
    holidays = holiday_id_set() if holidays is None else holidays
    start_date = event_date + timedelta(days=1 if rule.start_timing == 'next_day' else 0)

    if rule.day_type == 'workday':
        due_date = start_date
        counted = 0
        while counted < rule.duration_days:
            if is_workday(due_date, holidays):
                counted += 1
            if counted < rule.duration_days:
                due_date += timedelta(1)
    else:
        due_date = start_date + timedelta(days=rule.duration_days - 1)

    if rule.holiday_postpone:
        while not is_workday(due_date, holidays):
            due_date += timedelta(1)
    return start_date, due_date


def render_basis(rule, event, start_date, due_date):
    day_label = '工作日' if rule.day_type == 'workday' else '自然日'
    postpone_label = '届满日遇法定节假日/休息日顺延' if rule.holiday_postpone else '届满日不顺延'
    start_label = '次日' if rule.start_timing == 'next_day' else '当日'
    return (
        f'依据{event.get_event_type_display()}事件「{event.title}」（事件日期：{event.event_date}）；'
        f'适用律所规则「{rule.name}」，自事件{start_label}{start_date}起按{day_label}'
        f'计算{rule.duration_days}日，{postpone_label}，最终截止日期：{due_date}。'
    )


def deadline_snapshot(deadline):
    def lawyer_ref(lawyer):
        if not lawyer:
            return None
        return {'id': lawyer.id, 'name': lawyer.name}

    return {
        'title': deadline.title,
        'deadline_type': deadline.deadline_type,
        'due_date': deadline.due_date.isoformat(),
        'remind_days': deadline.remind_days,
        'escalate_days': deadline.escalate_days,
        'owner': lawyer_ref(deadline.owner),
        'reviewer': lawyer_ref(deadline.reviewer),
        'basis_text': deadline.basis_text,
        'source': deadline.source,
        'lifecycle': deadline.lifecycle,
        'is_done': deadline.is_done,
        'notes': deadline.notes,
        'event_id': deadline.event_id,
        'rule_id': deadline.rule_id,
        'revoked_reason': deadline.revoked_reason,
    }


def create_version(deadline, change_type, reason=''):
    version = (deadline.versions.order_by('-version').first().version + 1
               if deadline.versions.exists() else 1)
    return DeadlineVersion.objects.create(
        deadline=deadline, version=version, change_type=change_type,
        reason=reason, snapshot=deadline_snapshot(deadline))


def _at_nine(day):
    return timezone.make_aware(datetime.combine(day, time(hour=9)))


def cancel_future_reminders(deadline, reason='期限已失效或重新计算'):
    deadline.reminders.filter(status__in=['pending', 'failed']).update(
        status='cancelled', last_error=reason[:200])


def sync_reminders(deadline):
    """根据当前截止日期重建未发送提醒；已发送/已确认记录保留。"""
    cancel_future_reminders(deadline)
    if deadline.lifecycle != 'active' or deadline.is_done:
        return

    now = timezone.now()
    slots = []
    advance_day = deadline.due_date - timedelta(days=deadline.remind_days)
    slots.append((_at_nine(advance_day), deadline.owner, 'owner', 'advance'))
    if deadline.reviewer_id and (not deadline.owner_id or deadline.reviewer_id != deadline.owner_id):
        slots.append((_at_nine(advance_day), deadline.reviewer, 'reviewer', 'advance'))
    slots.append((_at_nine(deadline.due_date + timedelta(days=1)), deadline.owner, 'owner', 'overdue'))
    escalation_day = deadline.due_date + timedelta(days=deadline.escalate_days + 1)
    slots.append((_at_nine(escalation_day), deadline.reviewer or deadline.owner,
                  'reviewer', 'escalation'))

    for scheduled_at, recipient, role, kind in slots:
        if recipient is None:
            continue
        # 已过去的提前提醒不再补发，避免登记旧期限时突然出现历史提醒。
        if kind == 'advance' and scheduled_at < now:
            continue
        dedupe_key = f'deadline-{deadline.id}-{kind}-{role}-{recipient.id}-{scheduled_at.date().isoformat()}'
        Reminder.objects.get_or_create(
            dedupe_key=dedupe_key,
            defaults={
                'deadline': deadline,
                'recipient': recipient,
                'recipient_role': role,
                'kind': kind,
                'scheduled_at': scheduled_at,
            })


def _deadline_change_info(deadline=None, rule=None, event=None, start_date=None,
                          due_date=None, basis=None, owner=None, reviewer=None,
                          action='unchanged', reason=''):
    return {
        'action': action,
        'reason': reason,
        'deadline_id': deadline.id if deadline else None,
        'title': deadline.title if deadline else rule.name,
        'deadline_type': deadline.deadline_type if deadline else rule.deadline_type,
        'old_due_date': deadline.due_date.isoformat() if deadline else None,
        'new_due_date': due_date.isoformat() if due_date else (
            deadline.due_date.isoformat() if deadline else None),
        'start_date': start_date.isoformat() if start_date else None,
        'basis': basis or (deadline.basis_text if deadline else ''),
        'owner': owner.name if owner else (deadline.owner.name if deadline and deadline.owner else None),
        'reviewer': reviewer.name if reviewer else (
            deadline.reviewer.name if deadline and deadline.reviewer else None),
        'case_id': event.case_id if event else (deadline.case_id if deadline else None),
        'case_title': event.case.title if event else (
            deadline.case.title if deadline else None),
    }


def preview_event(event, effective_event=None):
    """effective_event 用于更正事件时传入尚未保存的事件对象。"""
    effective_event = effective_event or event
    holidays = holiday_id_set()
    rules = DeadlineRule.objects.filter(active=True, event_type=effective_event.event_type)
    existing = list(Deadline.objects.filter(event=event, lifecycle='active').select_related(
        'rule', 'owner', 'reviewer', 'case')) if event.pk else []
    existing_by_rule = {item.rule_id: item for item in existing if item.rule_id}

    creates, updates, revokes, blocked, unchanged = [], [], [], [], []
    owner, reviewer = assign_owner_and_reviewer(effective_event.case)
    if not owner:
        blocked.append({
            'reason': '案件尚未配置承办律师，无法分配负责人和复核人，规则期限不会生成',
            'case_id': effective_event.case_id,
            'case_title': effective_event.case.title,
        })

    for rule in rules:
        old = existing_by_rule.pop(rule.id, None)
        if old and old.is_done:
            blocked.append(_deadline_change_info(
                old, action='blocked', reason='该期限已办结，系统不会自动重算；如需调整请先显式重开'))
            continue
        start_date, due_date = calculate_due_date(rule, effective_event.event_date, holidays)
        basis = render_basis(rule, effective_event, start_date, due_date)
        if not old:
            if owner:
                creates.append(_deadline_change_info(
                    rule=rule, event=effective_event, start_date=start_date,
                    due_date=due_date, basis=basis, owner=owner, reviewer=reviewer,
                    action='create'))
        elif old.due_date != due_date or old.basis_text != basis or old.title != rule.name:
            updates.append(_deadline_change_info(
                old, rule=rule, event=effective_event, start_date=start_date,
                due_date=due_date, basis=basis, owner=old.owner, reviewer=old.reviewer,
                action='update', reason='事件日期/类型或名称更正后重新计算'))
        else:
            unchanged.append(_deadline_change_info(
                old, rule=rule, event=effective_event, start_date=start_date,
                due_date=due_date, basis=basis, owner=old.owner, reviewer=old.reviewer))

    # 事件类型改变后，旧类型生成的有效期限需要失效；已办结项保留并列入阻断项。
    for old in existing_by_rule.values():
        if old.is_done:
            blocked.append(_deadline_change_info(
                old, action='blocked', reason='旧事件类型对应期限已办结，不会被撤销或改写'))
        else:
            revokes.append(_deadline_change_info(
                old, action='revoke', reason='事件类型更正，旧规则不再适用'))

    return {
        'event': {
            'id': event.pk,
            'case_id': effective_event.case_id,
            'title': effective_event.title,
            'event_type': effective_event.event_type,
            'event_date': effective_event.event_date.isoformat(),
            'status': effective_event.status,
        },

        'creates': creates,
        'updates': updates,
        'revokes': revokes,
        'blocked': blocked,
        'unchanged': unchanged,
        'requires_confirmation': bool(creates or updates or revokes),
    }


def _supersede(deadline, reason, change_type='event_recalculate'):
    create_version(deadline, change_type, reason)
    deadline.lifecycle = 'superseded'
    deadline.revoked_reason = reason[:200]
    deadline.save(update_fields=['lifecycle', 'revoked_reason', 'updated_at'])
    cancel_future_reminders(deadline, reason)


def _create_generated_deadline(rule, event, start_date, due_date, basis, owner, reviewer):
    deadline = Deadline.objects.create(
        case=event.case, rule=rule, event=event, title=rule.name,
        deadline_type=rule.deadline_type, due_date=due_date,
        remind_days=rule.remind_days, escalate_days=rule.escalate_days,
        owner=owner, reviewer=reviewer, basis_text=basis,
        source='generated', lifecycle='active')
    create_version(deadline, 'created', '规则事件触发生成')
    sync_reminders(deadline)
    return deadline


@transaction.atomic
def process_event(event):
    """新事件幂等处理：重复事件不会新增第二套期限或提醒。"""
    preview = preview_event(event)
    owner, reviewer = assign_owner_and_reviewer(event.case)
    if not owner:
        return preview

    holidays = holiday_id_set()
    rules = DeadlineRule.objects.filter(active=True, event_type=event.event_type)
    existing = {
        item.rule_id: item
        for item in Deadline.objects.filter(event=event, lifecycle='active').select_related('rule')
        if item.rule_id
    }
    for rule in rules:
        old = existing.get(rule.id)
        if old:
            # 并发或重复提交已生成时直接复用；办结项也不会被改写。
            continue
        start_date, due_date = calculate_due_date(rule, event.event_date, holidays)
        basis = render_basis(rule, event, start_date, due_date)
        _create_generated_deadline(rule, event, start_date, due_date, basis, owner, reviewer)
    return preview


@transaction.atomic
def apply_event_update(event, changes, reason='事件信息更正'):
    """保存事件更正并创建新期限、替代旧期限；已办结期限不会被改写。"""
    holidays = holiday_id_set()
    old_active = list(Deadline.objects.filter(event=event, lifecycle='active').select_related('rule'))
    old_by_rule = {item.rule_id: item for item in old_active if item.rule_id}
    owner, reviewer = assign_owner_and_reviewer(event.case)

    new_type = changes.get('event_type', event.event_type)
    new_date = changes.get('event_date', event.event_date)
    new_title = changes.get('title', event.title)
    event.event_type = new_type
    event.event_date = new_date
    event.title = new_title
    if 'notes' in changes:
        event.notes = changes['notes']
    event.save()

    if not owner:
        return preview_event(event)

    active_rules = list(DeadlineRule.objects.filter(active=True, event_type=new_type))
    for rule in active_rules:
        old = old_by_rule.pop(rule.id, None)
        if old and old.is_done:
            continue
        start_date, due_date = calculate_due_date(rule, new_date, holidays)
        basis = render_basis(rule, event, start_date, due_date)
        if old:
            if old.due_date == due_date and old.basis_text == basis and old.title == rule.name:
                continue
            _supersede(old, reason)
            _create_generated_deadline(rule, event, start_date, due_date, basis,
                                       old.owner or owner, old.reviewer or reviewer)
        else:
            _create_generated_deadline(rule, event, start_date, due_date, basis, owner, reviewer)

    for old in old_by_rule.values():
        if not old.is_done:
            _supersede(old, '事件类型更正，旧规则不再适用')
    return preview_event(event)


@transaction.atomic
def revoke_event(event, reason):
    event.status = 'revoked'
    event.revoked_reason = reason[:200]
    event.revoked_at = timezone.now()
    event.save(update_fields=['status', 'revoked_reason', 'revoked_at', 'updated_at'])

    blocked, revoked = [], []
    for deadline in Deadline.objects.filter(event=event, lifecycle='active'):
        if deadline.is_done:
            blocked.append(_deadline_change_info(
                deadline, action='blocked', reason='期限已办结，事件撤销不会改写办结记录'))
            continue
        create_version(deadline, 'event_revoked', reason)
        deadline.lifecycle = 'revoked'
        deadline.revoked_reason = reason[:200]
        deadline.save(update_fields=['lifecycle', 'revoked_reason', 'updated_at'])
        cancel_future_reminders(deadline, f'起算事件已撤销：{reason}')
        revoked.append(_deadline_change_info(deadline, action='revoke', reason=reason))
    return {'event_id': event.id, 'revoked': revoked, 'blocked': blocked,
            'requires_confirmation': False}


def preview_event_revocation(event, reason):
    blocked, revoked = [], []
    for deadline in Deadline.objects.filter(event=event, lifecycle='active'):
        info = _deadline_change_info(
            deadline, action='blocked' if deadline.is_done else 'revoke',
            reason=reason if not deadline.is_done else '期限已办结，撤销事件不会改写办结记录')
        (blocked if deadline.is_done else revoked).append(info)
    return {'event_id': event.id, 'reason': reason, 'revoked': revoked,
            'blocked': blocked, 'requires_confirmation': bool(revoked or blocked)}


@transaction.atomic
def apply_rule_to_existing(rule):
    """规则维护后，仅对显式确认的案件期限重算；办结项跳过。"""
    holidays = holiday_id_set()
    updates, creates, blocked = [], [], []
    events = DeadlineEvent.objects.filter(
        status='active', event_type=rule.event_type).select_related('case')
    for event in events:
        current = Deadline.objects.filter(event=event, rule=rule, lifecycle='active').first()
        if current and current.is_done:
            blocked.append(_deadline_change_info(
                current, action='blocked', reason='已办结期限不会因规则调整自动改写'))
            continue
        owner, reviewer = assign_owner_and_reviewer(event.case)
        if not owner:
            blocked.append({
                'reason': f'案件「{event.case.title}」未配置承办律师，未生成期限',
                'case_id': event.case_id,
            })
            continue
        start_date, due_date = calculate_due_date(rule, event.event_date, holidays)
        basis = render_basis(rule, event, start_date, due_date)
        if current:
            if (current.due_date == due_date and current.basis_text == basis
                    and current.title == rule.name and current.remind_days == rule.remind_days
                    and current.escalate_days == rule.escalate_days):
                continue
            create_version(current, 'rule_recalculate', '律所规则调整后人工确认重算')
            current.lifecycle = 'superseded'
            current.revoked_reason = '律所规则调整，旧版本保留'
            current.save(update_fields=['lifecycle', 'revoked_reason', 'updated_at'])
            cancel_future_reminders(current, '规则调整后重新计算')
            new_deadline = _create_generated_deadline(
                rule, event, start_date, due_date, basis,
                current.owner or owner, current.reviewer or reviewer)
            updates.append(_deadline_change_info(
                current, rule=rule, event=event, start_date=start_date,
                due_date=due_date, basis=basis, owner=new_deadline.owner,
                reviewer=new_deadline.reviewer, action='update', reason='规则调整'))
        else:
            new_deadline = _create_generated_deadline(
                rule, event, start_date, due_date, basis, owner, reviewer)
            creates.append(_deadline_change_info(
                new_deadline, rule=rule, event=event, start_date=start_date,
                due_date=due_date, basis=basis, owner=owner, reviewer=reviewer,
                action='create', reason='规则补充适用于既有事件'))
    return {'rule_id': rule.id, 'creates': creates, 'updates': updates,
            'blocked': blocked, 'requires_confirmation': bool(creates or updates or blocked)}
