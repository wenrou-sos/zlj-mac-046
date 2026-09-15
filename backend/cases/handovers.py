"""案件交接业务逻辑：待办快照、清单比对（防过期）、状态流转、确认接管"""
import hashlib
from datetime import datetime

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .models import CaseLawyer, HandoverItem, HandoverLog, Lawyer

DESTINATION_TAKEOVER = 'takeover'
DESTINATION_KEEP = 'keep'
DESTINATION_VOID = 'void'

# 状态
DRAFT, PENDING, RETURNED, COMPLETED, CANCELED = (
    'draft', 'pending', 'returned', 'completed', 'canceled')


# ---------------- 待办快照 ----------------

def collect_pending_items(case):
    """汇总案件当前的全部待办：未办期限 / 后续开庭 / 待提交材料。

    返回 [dict(item_type, ref_id, title, detail, due_date,
               hearing_time, is_overdue)]
    """
    today = timezone.localdate()
    items = []

    for d in case.deadlines.filter(is_done=False):
        items.append({
            'item_type': 'deadline',
            'ref_id': d.id,
            'title': d.title,
            'detail': f'{d.get_deadline_type_display()}'
                      + (f'｜{d.notes}' if d.notes else ''),
            'due_date': d.due_date,
            'hearing_time': None,
            'is_overdue': d.due_date < today,
        })

    for h in case.hearings.filter(hearing_time__date__gte=today):
        items.append({
            'item_type': 'hearing',
            'ref_id': h.id,
            'title': f'开庭：{case.title}',
            'detail': h.location
                      + (f'｜{h.judge}' if h.judge else '')
                      + (f'｜{h.notes}' if h.notes else ''),
            'due_date': h.hearing_time.date(),
            'hearing_time': h.hearing_time,
            'is_overdue': False,
        })

    for m in case.materials.exclude(status='accepted'):
        items.append({
            'item_type': 'material',
            'ref_id': m.id,
            'title': m.name,
            'detail': f"{m.get_status_display()}"
                      + (f'｜提交对象：{m.submitted_to}' if m.submitted_to else '')
                      + (f'｜{m.notes}' if m.notes else ''),
            'due_date': None,
            'hearing_time': None,
            'is_overdue': False,
        })

    items.sort(key=lambda x: (
        x['item_type'] != 'deadline',
        x['due_date'] or datetime.max.date(),
        x['ref_id'] or 0,
    ))
    return items


def compute_items_hash(items):
    """待办指纹：标题/时间/状态等关键字段变化即失效"""
    lines = [
        '|'.join([
            i['item_type'], str(i['ref_id']), i['title'],
            str(i['detail']),
            str(i['due_date'] or ''),
            i['hearing_time'].strftime('%Y-%m-%dT%H:%M:%S') if i['hearing_time'] else '',
            '1' if i['is_overdue'] else '0',
        ])
        for i in items
    ]
    return hashlib.sha256('\n'.join(lines).encode()).hexdigest()


def _match_snapshot(items, item_type, ref_id):
    for i in items:
        if i['item_type'] == item_type and i['ref_id'] == ref_id:
            return i
    return None


@transaction.atomic
def refresh_items(handover, actor=None, note='', resubmit=False):
    """将案件新增/变更的待办补入清单；已办结或删除的条目标记 removed。

    已核对状态仅对发生变化（含新增/删除）的条目重置，未变化条目保留核对结果。
    resubmit=True 时，交出人在「已退回补充」状态补入后直接重新提交核对。
    返回 {'added': n, 'changed': n, 'removed': n, 'changed_titles': [...]}
    """
    live = collect_pending_items(handover.case)
    result = {'added': 0, 'changed': 0, 'removed': 0, 'changed_titles': []}

    # 1. 新增 / 变更
    for snap in live:
        existing = HandoverItem.objects.filter(
            handover=handover, item_type=snap['item_type'],
            ref_id=snap['ref_id']).first()
        if not existing:
            HandoverItem.objects.create(
                handover=handover, change_flag='new', checked=False, **snap)
            result['added'] += 1
            result['changed_titles'].append(f'新增待办：{snap["title"]}')
            continue

        sig_fields = ('title', 'detail', 'due_date', 'hearing_time', 'is_overdue')
        changed = any(getattr(existing, f) != snap[f] for f in sig_fields)
        if changed:
            for f in sig_fields:
                setattr(existing, f, snap[f])
            existing.change_flag = 'changed'
            existing.checked = False
            existing.save(update_fields=sig_fields + ('change_flag', 'checked', 'updated_at'))
            result['changed'] += 1
            result['changed_titles'].append(f"变更：{snap['title']}")
        elif existing.change_flag == 'removed':
            # 源对象恢复（如期限撤销办结）：重新纳入
            existing.change_flag = ''
            existing.save(update_fields=['change_flag', 'updated_at'])

    # 2. 已办结 / 删除
    tracked = HandoverItem.objects.filter(handover=handover).exclude(item_type='custom')
    live_keys = {(i['item_type'], i['ref_id']) for i in live}
    for item in tracked:
        if (item.item_type, item.ref_id) not in live_keys and item.change_flag != 'removed':
            item.change_flag = 'removed'
            item.checked = False
            item.save(update_fields=['change_flag', 'checked', 'updated_at'])
            result['removed'] += 1
            result['changed_titles'].append(f"已办结/删除：{item.title}")

    handover.items_hash = compute_items_hash(live)
    handover.last_refreshed_at = timezone.now()
    handover.save(update_fields=['items_hash', 'last_refreshed_at', 'updated_at'])

    if actor and (result['added'] or result['changed'] or result['removed']):
        HandoverLog.objects.create(
            handover=handover, action='refresh', actor_lawyer=actor,
            actor_name=getattr(actor, 'name', str(actor or '')),
            note=note or '；'.join(result['changed_titles']))
    return result


def diff_items(handover):
    """对照案件当前待办，判断清单是否过期，不写库。"""
    live = collect_pending_items(handover.case)
    result = {'stale': False, 'added': [], 'changed': [], 'removed': []}
    if handover.items_hash != compute_items_hash(live):
        result['stale'] = True

    for snap in live:
        ex = HandoverItem.objects.filter(
            handover=handover, item_type=snap['item_type'],
            ref_id=snap['ref_id']).first()
        if not ex:
            result['added'].append(snap['title'])
        elif any(getattr(ex, f) != snap[f] for f in
                 ('title', 'detail', 'due_date', 'hearing_time', 'is_overdue')):
            result['changed'].append(snap['title'])

    for item in handover.items.exclude(item_type='custom'):
        if not _match_snapshot(live, item.item_type, item.ref_id):
            result['removed'].append(item.title)

    if result['added'] or result['changed'] or result['removed']:
        result['stale'] = True
    return result


# ---------------- 状态流转 ----------------

def _log(handover, action, actor, note=''):
    is_lawyer = isinstance(actor, Lawyer)
    HandoverLog.objects.create(
        handover=handover, action=action,
        actor_lawyer=actor if is_lawyer else None,
        actor_name=getattr(actor, 'name', str(actor or '')), note=note)


def _require_lawyer(handover, lawyer, allowed):
    if lawyer not in allowed:
        raise PermissionDenied('当前操作人不是本交接的交出人或接收人')


def _require_status(handover, allowed):
    if handover.status not in allowed:
        raise ValidationError(
            {'status': f'当前状态「{handover.get_status_display()}」不允许该操作'})


@transaction.atomic
def submit(handover, actor):
    """交出人提交给接收人核对"""
    _require_lawyer(handover, actor, [handover.from_lawyer])
    _require_status(handover, [DRAFT, RETURNED])
    refresh_items(handover)  # 提交前强制与案件待办对齐，杜绝拿过期清单交接
    active_items = handover.items.exclude(change_flag='removed')
    if not active_items.exists():
        raise ValidationError({'items': '本案当前没有待办事项，无需交接'})
    handover.status = PENDING
    handover.submitted_at = timezone.now()
    handover.returned_reason = ''
    handover.save()
    _log(handover, 'submit', actor, '清单已提交接收人核对')
    return handover


@transaction.atomic
def return_back(handover, actor, reason):
    """接收人退回补充"""
    _require_lawyer(handover, actor, [handover.to_lawyer])
    _require_status(handover, [PENDING])
    if not reason or not reason.strip():
        from rest_framework.exceptions import ValidationError
        raise ValidationError({'reason': '退回时必须填写补充说明'})
    handover.status = RETURNED
    handover.returned_reason = reason.strip()
    handover.save()
    _log(handover, 'return', actor, reason.strip())
    return handover


@transaction.atomic
def confirm_takeover(handover, actor):
    """接收人核对无误后确认接管（完成交接）"""
    _require_lawyer(handover, actor, [handover.to_lawyer])
    _require_status(handover, [PENDING])

    # —— 防过期（三层，全部在同一事务内重新取库）——
    # 1) 重新取案件实时待办，与清单逐项比对（新增/变更/办结删除）
    diff = diff_items(handover)
    if diff['stale']:
        raise ValidationError({
            'stale': '交接期间待办有新增或变更，不能使用过期清单完成交接，请先「补入最新待办」并重新核对',
            **{k: v for k, v in diff.items() if k != 'stale'},
        })

    # 2) 硬性数量不变量：案件实时待办数必须等于清单内有效条目数
    live_items = collect_pending_items(handover.case)
    active = HandoverItem.objects.select_for_update().filter(
        handover=handover).exclude(change_flag='removed')
    live_keys = {(i['item_type'], i['ref_id']) for i in live_items
                 if i['item_type'] != 'custom'}
    list_keys = {(i.item_type, i.ref_id) for i in active if i.item_type != 'custom'}
    if live_keys != list_keys:
        raise ValidationError({
            'stale': '案件待办与交接清单不一致（清单可能已过期），请先「补入最新待办」并重新核对',
            'added': [t for t in diff['added']],
            'removed': [t for t in diff['removed']],
        })

    # 3) 全部条目逐项核对
    unchecked = active.filter(checked=False)
    if unchecked.exists():
        names = '、'.join(unchecked.values_list('title', flat=True)[:5])
        raise ValidationError({'items': f'尚有 {unchecked.count()} 项待办未核对（如：{names}）'})
    if not active.filter(destination=DESTINATION_TAKEOVER).exists():
        raise ValidationError(
            {'items': '没有任何待办去向为「接收人接管」，无法完成交接；'
                      '如全部由原责任人继续办理，请取消本次交接'})

    case = handover.case
    from_link = CaseLawyer.objects.filter(case=case, lawyer=handover.from_lawyer).first()
    to_link = CaseLawyer.objects.filter(case=case, lawyer=handover.to_lawyer).first()

    # 明确每项去向：
    #  takeover -> 接收人须在承办团队中；keep -> 交出人保留（降为协办）；void -> 无人
    takeover = active.filter(destination=DESTINATION_TAKEOVER).exists()
    keep = active.filter(destination=DESTINATION_KEEP).exists()

    if from_link:
        from_role = from_link.role
        if not keep:
            # 交出人无保留事项：离开本案，角色（通常是主办）转移给接收人
            from_link.delete()
            if to_link:
                if from_role == 'lead' and to_link.role != 'lead':
                    to_link.role = 'lead'
                    to_link.save(update_fields=['role'])
            else:
                CaseLawyer.objects.create(case=case, lawyer=handover.to_lawyer, role=from_role)
        else:
            # 有“原责任人继续办理”的事项：交出人留在团队，接管主办时降为协办
            if takeover:
                if to_link:
                    if from_role == 'lead' and to_link.role != 'lead':
                        to_link.role = 'lead'
                        to_link.save(update_fields=['role'])
                        from_link.role = 'assist'
                        from_link.save(update_fields=['role'])
                else:
                    CaseLawyer.objects.create(case=case, lawyer=handover.to_lawyer,
                                              role='lead' if from_role == 'lead' else 'assist')
                    if from_role == 'lead':
                        from_link.role = 'assist'
                        from_link.save(update_fields=['role'])

    handover.status = COMPLETED
    handover.completed_at = timezone.now()
    handover.save()
    _log(handover, 'confirm', actor, '接收人已核对全部待办并确认接管')
    return handover


@transaction.atomic
def cancel(handover, actor, reason):
    """取消交接（完成前交出人/接收人均可）"""
    _require_lawyer(handover, actor, [handover.from_lawyer, handover.to_lawyer])
    _require_status(handover, [DRAFT, PENDING, RETURNED])
    handover.status = CANCELED
    handover.cancel_reason = (reason or '').strip()
    handover.save()
    _log(handover, 'cancel', actor, reason or '')
    return handover
