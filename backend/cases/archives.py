"""卷宗归档领域服务：清单指纹、未结事项汇总、封存快照、重开流程。

封存的不可变性依赖两层保障：
1. 封存时把全量内容写入 ArchiveVersion.snapshot（JSON 快照），此后日常编辑只改原表，
   快照不再变化 —— “旧卷宗随时可查”；
2. 案件存在 sealed 版本期间，views 层拒绝一切对案件及其子记录的增删改。

并发保障：把案件信息拆成若干分区（当事人/律师/阶段/庭期/材料/期限/基本信息），
每个分区按记录内容与 updated_at 生成哈希。提交封存时携带当时的分区指纹，
封存瞬间在行锁内重新计算并比对，任何分区变化即抛 ArchiveConflict（HTTP 409），
要求重新核对清单，绝不封存过时清单。
"""
import hashlib
import json

from django.db import models, transaction
from django.utils import timezone
from rest_framework import status

from .models import (ArchiveVersion, CaseLawyer, CaseParty, Deadline, Hearing,
                     Material, PendingItem, ReopenRequest, StageLog)

SECTIONS = [
    ('case', '案件基本信息'),
    ('parties', '当事人'),
    ('lawyers', '承办律师'),
    ('stages', '诉讼阶段'),
    ('hearings', '庭期'),
    ('materials', '材料'),
    ('deadlines', '期限'),
]
SECTION_LABELS = dict(SECTIONS)


class ArchiveConflict(Exception):
    """清单在提交后发生过变更，需重新核对"""

    def __init__(self, message, changed_sections=None, stale_items=None):
        super().__init__(message)
        self.message = message
        self.changed_sections = changed_sections or []
        self.stale_items = stale_items or []
        self.status_code = status.HTTP_409_CONFLICT


class ArchiveError(Exception):
    """归档流程的业务校验错误（400）"""
    status_code = status.HTTP_400_BAD_REQUEST


def _norm(value):
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)


def _stable_json(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _h(rows):
    return hashlib.sha256(_stable_json(rows).encode('utf-8')).hexdigest()


# ---------- 分区指纹 ----------
def fingerprint_state(case):
    """返回 {section: hash}，内容或 updated_at 任一变化都会改变哈希。"""
    state = {
        'case': _h([{
            'case_number': case.case_number,
            'title': case.title,
            'case_type': case.case_type,
            'stage': case.stage,
            'cause': case.cause,
            'court': case.court,
            'filed_date': _norm(case.filed_date),
            'amount': _norm(case.amount),
            'description': case.description,
            'updated_at': _norm(case.updated_at),
        }]),
        'parties': _h([{
            'id': cp.id, 'party_id': cp.party_id, 'role': cp.role,
            'is_client': cp.is_client, 'updated_at': _norm(cp.updated_at),
        } for cp in CaseParty.objects.filter(case=case).order_by('id')]),
        'lawyers': _h([{
            'id': cl.id, 'lawyer_id': cl.lawyer_id, 'role': cl.role,
            'updated_at': _norm(cl.updated_at),
        } for cl in CaseLawyer.objects.filter(case=case).order_by('id')]),
        'stages': _h([{
            'id': s.id, 'stage': s.stage, 'log_date': _norm(s.log_date),
            'notes': s.notes, 'updated_at': _norm(s.updated_at),
        } for s in StageLog.objects.filter(case=case).order_by('id')]),
        'hearings': _h([{
            'id': h.id, 'hearing_time': _norm(h.hearing_time),
            'location': h.location, 'judge': h.judge, 'notes': h.notes,
            'updated_at': _norm(h.updated_at),
        } for h in Hearing.objects.filter(case=case).order_by('id')]),
        'materials': _h([{
            'id': m.id, 'name': m.name, 'submitted_to': m.submitted_to,
            'submit_date': _norm(m.submit_date), 'status': m.status,
            'notes': m.notes, 'updated_at': _norm(m.updated_at),
        } for m in Material.objects.filter(case=case).order_by('id')]),
        'deadlines': _h([{
            'id': d.id, 'title': d.title, 'deadline_type': d.deadline_type,
            'due_date': _norm(d.due_date), 'remind_days': d.remind_days,
            'is_done': d.is_done, 'notes': d.notes,
            'updated_at': _norm(d.updated_at),
        } for d in Deadline.objects.filter(case=case).order_by('id')]),
    }
    state['overall'] = _h([state[k] for k, _ in SECTIONS])
    return state


def changed_sections(before, after):
    return [k for k, _ in SECTIONS if before.get(k) != after.get(k)]


# ---------- 封存快照 ----------
def build_snapshot(case, version, pending_items=None):
    """封存瞬间冻结的完整卷宗内容"""
    parties = [
        {'name': cp.party.name, 'role': cp.get_role_display(),
         'is_client': cp.is_client,
         'party_type': cp.party.get_party_type_display(),
         'id_number': cp.party.id_number, 'phone': cp.party.phone,
         'address': cp.party.address}
        for cp in CaseParty.objects.filter(case=case).select_related('party').order_by('id')
    ]
    lawyers = [
        {'name': cl.lawyer.name, 'role': cl.get_role_display(),
         'title': cl.lawyer.get_title_display(),
         'bar_number': cl.lawyer.bar_number, 'phone': cl.lawyer.phone}
        for cl in CaseLawyer.objects.filter(case=case).select_related('lawyer').order_by('id')
    ]
    stages = [
        {'stage': s.get_stage_display(), 'log_date': str(s.log_date), 'notes': s.notes}
        for s in StageLog.objects.filter(case=case).order_by('log_date', 'id')
    ]
    hearings = [
        {'hearing_time': h.hearing_time.strftime('%Y-%m-%d %H:%M'),
         'location': h.location, 'judge': h.judge, 'notes': h.notes}
        for h in Hearing.objects.filter(case=case).order_by('hearing_time')
    ]
    materials = [
        {'name': m.name, 'submitted_to': m.submitted_to,
         'submit_date': str(m.submit_date) if m.submit_date else '',
         'status': m.get_status_display(), 'notes': m.notes}
        for m in Material.objects.filter(case=case).order_by('id')
    ]
    deadlines = [
        {'title': d.title, 'deadline_type': d.get_deadline_type_display(),
         'due_date': str(d.due_date), 'is_done': d.is_done, 'notes': d.notes}
        for d in Deadline.objects.filter(case=case).order_by('due_date', 'id')
    ]
    if pending_items is None:
        pending_items = version.pending_items.all()
    pending = [
        {'kind': p.get_kind_display(), 'title': p.title, 'detail': p.detail,
         'disposition': p.get_disposition_display() if p.disposition else '',
         'disposition_note': p.disposition_note}
        for p in pending_items
    ]
    return {
        'generated_at': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
        'case': {
            'case_number': case.case_number,
            'title': case.title,
            'case_type': case.get_case_type_display(),
            'stage': case.get_stage_display(),
            'cause': case.cause,
            'court': case.court,
            'filed_date': str(case.filed_date) if case.filed_date else '',
            'amount': str(case.amount) if case.amount is not None else '',
            'description': case.description,
            'closed_date': str(version.closed_date) if version.closed_date else '',
            'summary': version.summary,
        },
        'parties': parties,
        'lawyers': lawyers,
        'stages': stages,
        'hearings': hearings,
        'materials': materials,
        'deadlines': deadlines,
        'pending_items': pending,
        'prepared_by': version.prepared_by,
        'reviewer': version.reviewer,
    }


# ---------- 未结事项自动汇总 ----------
def suggest_pending_items(case):
    """扫描案件，汇总必须逐项说明处置方式的未结事项。"""
    items = []
    for d in Deadline.objects.filter(case=case, is_done=False).order_by('due_date'):
        items.append({
            'kind': 'deadline',
            'ref_id': d.id,
            'item_key': f'deadline-{d.id}',
            'title': d.title,
            'detail': f'{d.get_deadline_type_display()}，截止 {d.due_date}'
                      + (f'；{d.notes}' if d.notes else ''),
        })
    for m in Material.objects.filter(case=case).exclude(status='accepted').order_by('id'):
        items.append({
            'kind': 'material',
            'ref_id': m.id,
            'item_key': f'material-{m.id}',
            'title': m.name,
            'detail': f'当前状态：{m.get_status_display()}'
                      + (f'；{m.notes}' if m.notes else ''),
        })
    for h in Hearing.objects.filter(case=case,
                                    hearing_time__gt=timezone.now()).order_by('hearing_time'):
        items.append({
            'kind': 'hearing',
            'ref_id': h.id,
            'item_key': f'hearing-{h.id}',
            'title': f'庭期：{h.hearing_time.strftime("%Y-%m-%d %H:%M")} {h.location}',
            'detail': (f'承办法官/仲裁员：{h.judge}' if h.judge else '')
                      + (f'；{h.notes}' if h.notes else ''),
        })
    return items


def prepare_archive(case):
    """GET 归档整理页所需数据：当前草稿（含已填处置）+ 最新扫描清单 + 指纹。"""
    state = fingerprint_state(case)
    current = case.get_current_archive()
    # 草稿/退回可继续整理；重开后的历史版本视为新一轮，重新扫描、生成新版本
    editable = current is None or current.status in ('draft', 'rejected', 'reopened')
    if current and current.status == 'reopened':
        current = None
    suggestions = suggest_pending_items(case)
    suggestion_keys = {s['item_key'] for s in suggestions}

    # 已保存的处置（自定义事项不在最新扫描结果中也要带出来）
    saved = []
    if current and current.status in ('draft', 'rejected'):
        for p in current.pending_items.all():
            saved.append({
                'id': p.id, 'kind': p.kind, 'ref_id': p.ref_id,
                'item_key': p.item_key, 'title': p.title, 'detail': p.detail,
                'disposition': p.disposition, 'disposition_note': p.disposition_note,
            })
    saved_map = {p['item_key']: p for p in saved}

    items = []
    for s in suggestions:
        row = {**s, 'disposition': '', 'disposition_note': '', 'id': None}
        if s['item_key'] in saved_map:
            old = saved_map[s['item_key']]
            row.update(disposition=old['disposition'],
                       disposition_note=old['disposition_note'], id=old['id'])
        items.append(row)
    for p in saved:
        if p['item_key'] not in suggestion_keys:
            items.append(p)  # 自定义事项，或原关联记录已删除的遗留事项

    return {
        'editable': editable,
        'fingerprint': state['overall'],
        'fingerprint_state': state,
        'sections': [{'key': k, 'label': v} for k, v in SECTIONS],
        'suggested_pending_items': items,
        'current_version': current.version_no if current else None,
        'current_status': current.status if current else None,
    }


def _validate_items(case, submitted_items, stored_items=None):
    """校验逐项处置是否完整，并识别已被并发改动/删除的陈旧事项。

    返回 (resolved, stale)。resolved 为按 item_key 归一化后的提交内容。
    """
    fresh = {s['item_key']: s for s in suggest_pending_items(case)}
    resolved = {}
    stale = []
    for item in submitted_items:
        key = (item.get('item_key') or '').strip()
        kind = item.get('kind', 'custom')
        if not key:
            if kind != 'custom' or not item.get('title'):
                raise ArchiveError('存在缺少标识的未结事项')
            key = f'custom-{item["title"]}'
        disposition = item.get('disposition', '')
        note = (item.get('disposition_note') or '').strip()
        if not disposition:
            raise ArchiveError(f'未结事项「{item.get("title", key)}」请选择处置方式')
        if not note:
            raise ArchiveError(f'未结事项「{item.get("title", key)}」请填写处置说明')
        # 引用了案件原始记录（期限/材料/庭期）的，确认记录仍然存在且仍未结
        if key in fresh:
            resolved[key] = {
                **fresh[key],
                'disposition': disposition, 'disposition_note': note}
        elif kind == 'custom':
            resolved[key] = {
                'kind': 'custom', 'ref_id': None, 'item_key': key,
                'title': item.get('title', key),
                'detail': item.get('detail', ''),
                'disposition': disposition, 'disposition_note': note}
        else:
            stale.append({'item_key': key, 'title': item.get('title', key),
                          'reason': '关联记录已删除或状态已变化'})
    # 提交清单漏掉了当前仍未结的事项
    known = set(resolved) | {s['item_key'] for s in stale}
    for key, s in fresh.items():
        if key not in known:
            stale.append({'item_key': key, 'title': s['title'],
                          'reason': '提交清单遗漏了该未结事项'})
    return resolved, stale


@transaction.atomic
def submit_archive(case, data):
    """整理完成，提交复核（生成/更新 draft 版本并置为 submitted）。"""
    if case.is_sealed:
        raise ArchiveError('卷宗已封存，如需再审或补充材料请申请重开')

    case = case.__class__.objects.select_for_update().get(pk=case.pk)
    current = case.archive_versions.order_by('-version_no').first()
    if current and current.status == 'submitted':
        raise ArchiveError('该卷宗已提交，正在等待复核确认')

    closed_date = data.get('closed_date') or timezone.localdate()
    summary = (data.get('summary') or '').strip()
    items = data.get('pending_items') or []
    if not items and suggest_pending_items(case):
        raise ArchiveError('存在未结事项，请逐项核对并填写处置方式后再提交')

    resolved, stale = _validate_items(case, items)
    state = fingerprint_state(case)

    # 复用退回版本以保持版本号连续；否则新建版本
    if current and current.status in ('draft', 'rejected'):
        version = current
        version.status = 'submitted'
        version.reject_reason = ''
        version.review_comment = ''
        version.reviewer = ''
    else:
        next_no = (case.archive_versions.aggregate(
            max_no=models.Max('version_no'))['max_no'] or 0) + 1
        version = ArchiveVersion(case=case, version_no=next_no,
                                 status='submitted')

    version.closed_date = closed_date
    version.summary = summary
    version.prepared_by = (data.get('prepared_by') or version.prepared_by or '').strip()
    version.submitted_by = (data.get('submitted_by') or version.prepared_by or '').strip()
    version.submitted_at = timezone.now()
    version.fingerprint = state['overall']
    version.fingerprint_state = state
    version.save()

    version.pending_items.all().delete()
    for key, row in resolved.items():
        PendingItem.objects.create(
            archive_version=version, kind=row['kind'], ref_id=row.get('ref_id'),
            item_key=key, title=row['title'], detail=row.get('detail', '')[:300],
            disposition=row['disposition'], disposition_note=row['disposition_note'])

    return version, stale


@transaction.atomic
def confirm_archive(case, version_no, reviewer, comment):
    """复核确认并封存：行锁内复核指纹，过期则拒绝。"""
    case = case.__class__.objects.select_for_update().get(pk=case.pk)
    version = case.archive_versions.select_for_update().filter(
        version_no=version_no).first()
    if not version:
        raise ArchiveError('卷宗版本不存在')
    if version.status != 'submitted':
        raise ArchiveError(f'该版本当前状态为「{version.get_status_display()}」，无法封存')

    reviewer = (reviewer or '').strip()
    if not reviewer:
        raise ArchiveError('请填写复核人')

    # 1) 分区指纹复核：提交后案件内容是否被改过
    fresh_state = fingerprint_state(case)
    changed = changed_sections(version.fingerprint_state or {}, fresh_state)

    # 2) 未结事项复核：记录是否被删除/状态变化/有遗漏
    fresh_suggestions = suggest_pending_items(case)
    fresh_keys = {s['item_key'] for s in fresh_suggestions}
    stored_keys = set(version.pending_items.exclude(kind='custom')
                      .values_list('item_key', flat=True))
    stale_items = []
    for key in stored_keys - fresh_keys:
        item = version.pending_items.filter(item_key=key).first()
        stale_items.append({'item_key': key,
                            'title': item.title if item else key,
                            'reason': '关联记录已删除或状态已变化'})
    for key in fresh_keys - stored_keys:
        s = next(x for x in fresh_suggestions if x['item_key'] == key)
        stale_items.append({'item_key': key, 'title': s['title'],
                            'reason': '存在未登记处置的新增未结事项'})
    if changed or stale_items:
        raise ArchiveConflict(
            '归档清单提交后案件信息发生变化，请重新核对后再次提交封存',
            changed_sections=[{'key': k, 'label': SECTION_LABELS[k]} for k in changed],
            stale_items=stale_items)

    # 3) 封存：冻结快照，案件进入结案
    version.status = 'sealed'
    version.reviewer = reviewer
    version.review_comment = (comment or '').strip()
    version.sealed_at = timezone.now()
    version.fingerprint = fresh_state['overall']
    version.fingerprint_state = fresh_state
    version.snapshot = build_snapshot(case, version)
    version.save()

    if case.stage != 'closed':
        StageLog.objects.create(case=case, stage='closed',
                                log_date=version.closed_date or timezone.localdate(),
                                notes=f'复核人{reviewer}确认封存卷宗 v{version.version_no}')
        case.stage = 'closed'
        case.save(update_fields=['stage', 'updated_at'])
    return version


@transaction.atomic
def reject_archive(case, version_no, reviewer, reason):
    """复核退回，整理人修改后可重新提交（版本号不变）。"""
    version = case.archive_versions.filter(version_no=version_no).first()
    if not version:
        raise ArchiveError('卷宗版本不存在')
    if version.status != 'submitted':
        raise ArchiveError('仅待复核的卷宗可以退回')
    reason = (reason or '').strip()
    if not reason:
        raise ArchiveError('请填写退回原因')
    version.status = 'rejected'
    version.reviewer = (reviewer or '').strip()
    version.reject_reason = reason
    version.save(update_fields=['status', 'reviewer', 'reject_reason', 'updated_at'])
    return version


@transaction.atomic
def cancel_submitted_archive(case, version_no):
    """提交人在复核前撤回归档整理。"""
    version = case.archive_versions.filter(version_no=version_no).first()
    if not version or version.status != 'submitted':
        raise ArchiveError('仅待复核的卷宗可以撤回')
    version.status = 'draft'
    version.submitted_at = None
    version.save(update_fields=['status', 'submitted_at', 'updated_at'])
    return version


@transaction.atomic
def apply_reopen(case, data):
    """申请重开已封存卷宗（再审/补充材料），需审批后才能恢复编辑。"""
    sealed = case.get_sealed_archive()
    if not sealed:
        raise ArchiveError('卷宗尚未封存，无需申请重开；可直接办理')
    pending = case.reopen_requests.filter(status='pending').exists()
    if pending:
        raise ArchiveError('该案件已有待审批的重开申请，请勿重复提交')
    reason = (data.get('reason') or '').strip()
    if not reason:
        raise ArchiveError('请填写重开原因说明')
    return ReopenRequest.objects.create(
        case=case, archive_version=sealed,
        reason_type=data.get('reason_type', 'other'),
        reason=reason,
        applicant=(data.get('applicant') or '').strip(),
        next_stage=data.get('next_stage') or 'retrial')


@transaction.atomic
def decide_reopen(request_id, approver, comment, approve, next_stage=None):
    """审批重开申请：批准后封存版本转为历史版本（reopened），案件解锁。"""
    req = ReopenRequest.objects.select_for_update().get(pk=request_id)
    if req.status != 'pending':
        raise ArchiveError('该申请已审批')
    approver = (approver or '').strip()
    if not approver:
        raise ArchiveError('请填写审批人')
    req.approver = approver
    req.approval_comment = (comment or '').strip()
    req.decided_at = timezone.now()
    if approve:
        req.status = 'approved'
        if next_stage:
            req.next_stage = next_stage
        req.save()
        if req.archive_version and req.archive_version.status == 'sealed':
            req.archive_version.status = 'reopened'
            req.archive_version.save(update_fields=['status', 'updated_at'])
        case = req.case
        case.stage = req.next_stage
        stage_label = dict(ReopenRequest.REASON_CHOICES).get(req.reason_type, '重开')
        StageLog.objects.create(
            case=case, stage=req.next_stage, log_date=timezone.localdate(),
            notes=f'{stage_label}重开：{req.reason}；批准人 {approver}')
        case.save(update_fields=['stage', 'updated_at'])
    else:
        req.status = 'rejected'
        req.save()
    return req
