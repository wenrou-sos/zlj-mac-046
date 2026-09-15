"""利益冲突评估引擎。

以"拟承接关系"（当事人 + 目标案件 + 诉讼地位 + 是否作为本所客户）为输入，
输出结构化风险依据，供冲突复核单快照与审批时复评共用。

结论分两类：
- ``prohibited=True``：本所明确禁止的冲突（如《律师法》第三十九条规定的
  在办客户对抗代理），任何情况下都不得批准，也不存在例外；
- 其余中等风险（needs_exception）：属于可有条件豁免的冲突，批准时必须
  登记授权依据与适用期限。
"""
import hashlib
import json

from django.utils import timezone

from .models import CaseParty

HIGH = 'high'
MEDIUM = 'medium'
LOW = 'low'


def party_involvements(party):
    """当事人在全部案件中的涉案关系（风险依据的事实部分）。"""
    items = []
    for cp in (CaseParty.objects.filter(party=party)
               .select_related('case').order_by('-case__filed_date', '-case_id')):
        items.append({
            'case_id': cp.case.id,
            'case_number': cp.case.case_number,
            'case_title': cp.case.title,
            'stage': cp.case.stage,
            'stage_display': cp.case.get_stage_display(),
            'role': cp.role,
            'role_display': cp.get_role_display(),
            'is_client': cp.is_client,
        })
    return items


def evaluate_conflict(party, case, proposed_role, proposed_is_client):
    """评估拟承接关系的冲突情形。

    返回 {findings, risk_level, has_prohibited, needs_exception}。
    """
    findings = []

    existing = CaseParty.objects.filter(case=case, party=party).first()
    if existing:
        findings.append({
            'code': 'duplicate_in_case',
            'level': HIGH,
            'prohibited': True,
            'message': f'该当事人已在本案中登记为{existing.get_role_display()}，'
                       f'不得就同一案件重复发起承接',
            'related_case_id': case.id,
            'related_case_number': case.case_number,
            'related_case_title': case.title,
        })

    for cp in (CaseParty.objects.filter(party=party)
               .exclude(case=case).select_related('case')):
        c = cp.case
        active = c.stage != 'closed'
        ref = {
            'related_case_id': c.id,
            'related_case_number': c.case_number,
            'related_case_title': c.title,
        }
        if cp.is_client and active and not proposed_is_client:
            findings.append({
                'code': 'active_client_adverse',
                'level': HIGH,
                'prohibited': True,
                'message': f'该当事人是本所在办案件「{c.title}」（{c.case_number}）的委托客户，'
                           f'本案拟将其列为利益相对方，构成《中华人民共和国律师法》第三十九条'
                           f'明令禁止的利益冲突，本所规定不得批准、亦不适用例外授权',
                **ref,
            })
        elif not cp.is_client and active and proposed_is_client:
            findings.append({
                'code': 'active_adverse_new_client',
                'level': MEDIUM,
                'prohibited': False,
                'message': f'该当事人是本所在办案件「{c.title}」（{c.case_number}）的对方当事人，'
                           f'接受其委托前须经冲突审查、取得利害关系方知情同意并落实信息隔离措施，'
                           f'属可有条件豁免的冲突，批准时须登记授权依据及适用期限',
                **ref,
            })
        elif cp.is_client and proposed_is_client:
            findings.append({
                'code': 'existing_client_new_matter',
                'level': LOW,
                'prohibited': False,
                'message': f'该当事人已系本所客户（案件「{c.title}」，'
                           f'{"在办" if active else "已结案"}），建立新委托时应注意信息隔离与利益边界',
                **ref,
            })
        elif not cp.is_client and not active and proposed_is_client:
            findings.append({
                'code': 'former_adverse_closed',
                'level': LOW,
                'prohibited': False,
                'message': f'该当事人曾在本所已结案件「{c.title}」中作为对方当事人，'
                           f'接受委托前请复核既往案卷并留档',
                **ref,
            })

    has_prohibited = any(f['prohibited'] for f in findings)
    has_medium = any(f['level'] == MEDIUM for f in findings)
    risk_level = HIGH if has_prohibited else (MEDIUM if has_medium else LOW)
    return {
        'findings': findings,
        'risk_level': risk_level,
        'has_prohibited': has_prohibited,
        'needs_exception': (not has_prohibited and has_medium),
    }


def relationship_fingerprint(party, case, proposed_role, proposed_is_client):
    """风险依据指纹：纳入"拟承接关系落地后"的全部涉案关系。

    承接动作本身产生的关联在发起复核时已被预先计入，因此承接保存不会
    导致指纹变化；此后任何案件-当事人关系、客户标记或案件阶段的实质
    变更都会使指纹不一致，从而触发重新复核。
    """
    rows = {}
    for cp in (CaseParty.objects.filter(party=party)
               .select_related('case')):
        rows[cp.case_id] = [cp.role, bool(cp.is_client), cp.case.stage]
    if case is not None:
        rows[case.id] = [proposed_role or '', bool(proposed_is_client), case.stage]
    payload = sorted((cid, *vals) for cid, vals in rows.items())
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def build_snapshot(party, case, proposed_role, proposed_is_client):
    """生成风险依据快照（申请时 / 审批复评时各留存一份）。"""
    evaluation = evaluate_conflict(party, case, proposed_role, proposed_is_client)
    return {
        'evaluated_at': timezone.localtime().strftime('%Y-%m-%d %H:%M'),
        'party': {
            'id': party.id,
            'name': party.name,
            'party_type': party.party_type,
            'party_type_display': party.get_party_type_display(),
            'id_number': party.id_number or '',
            'phone': party.phone or '',
            'address': party.address or '',
        },
        'case': {
            'id': case.id,
            'case_number': case.case_number,
            'title': case.title,
            'stage': case.stage,
            'stage_display': case.get_stage_display(),
            'court': case.court or '',
        },
        'proposed': {
            'role': proposed_role,
            'role_display': dict(CaseParty.ROLE_CHOICES).get(proposed_role, proposed_role),
            'is_client': bool(proposed_is_client),
        },
        'involvements': party_involvements(party),
        **evaluation,
    }
