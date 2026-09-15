"""当事人重复档案识别与合并服务。"""
from collections import defaultdict

from django.db import connection, transaction
from django.utils import timezone
from rest_framework import serializers

from .models import CaseParty, Party, PartyAlias, PartyMergeRecord
from .serializers import PartySerializer

MERGE_FIELDS = [
    ('name', '姓名/名称'),
    ('party_type', '类型'),
    ('id_number', '证件号'),
    ('phone', '联系电话'),
    ('address', '地址'),
    ('source_system', '原档来源'),
    ('notes', '备注'),
]
VALID_PARTY_TYPES = {key for key, _ in Party.TYPE_CHOICES}


def clean_text(value):
    return (value or '').strip()


def norm_name(value):
    return clean_text(value).casefold()


def norm_id(value):
    return clean_text(value).replace(' ', '').upper()


def norm_phone(value):
    return ''.join(ch for ch in clean_text(value) if ch.isdigit())


def _union(parent, a, b):
    roots = []
    for x in (a, b):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        roots.append(x)
    if roots[0] != roots[1]:
        parent[roots[1]] = roots[0]


def _find(parent, x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def _party_conflicts(parties):
    """返回字段冲突项；空值与非空值也作为待补全冲突展示。"""
    conflicts = []
    for field, label in MERGE_FIELDS:
        raw_values = [getattr(p, field) or '' for p in parties]
        values = []
        for value in raw_values:
            value = value.strip()
            if value not in values:
                values.append(value)
        if len(values) > 1:
            nonempty = [v for v in values if v]
            conflicts.append({
                'field': field,
                'label': label,
                'values': values,
                'options': nonempty or values,
                'has_blank': any(not v for v in values),
                'conflict_type': 'incomplete' if len(nonempty) <= 1 else 'different',
            })
    return conflicts


def _relation_analysis(parties):
    """分析同案诉讼地位及重复涉案关系。"""
    party_ids = [p.id for p in parties]
    rows_qs = (CaseParty.objects.filter(party_id__in=party_ids)
               .select_related('case', 'party').order_by('case_id', 'role', 'id'))
    rows = []
    by_case = defaultdict(list)
    by_case_role = defaultdict(list)
    for cp in rows_qs:
        item = {
            'case_party_id': cp.id,
            'case_id': cp.case_id,
            'case_number': cp.case.case_number,
            'case_title': cp.case.title,
            'role': cp.role,
            'role_display': cp.get_role_display(),
            'is_client': cp.is_client,
            'party_id': cp.party_id,
            'party_name': cp.party.name,
        }
        rows.append(item)
        by_case[cp.case_id].append(item)
        by_case_role[(cp.case_id, cp.role)].append(item)

    role_warnings = []
    confirm_case_ids = []
    for case_id, items in by_case.items():
        roles = {i['role'] for i in items}
        if len(roles) > 1:
            first = items[0]
            confirm_case_ids.append(case_id)
            role_warnings.append({
                'code': f'different_roles:{case_id}',
                'case_id': case_id,
                'case_number': first['case_number'],
                'case_title': first['case_title'],
                'roles': sorted(roles),
                'role_displays': sorted({i['role_display'] for i in items}),
                'message': f"案件「{first['case_title']}」中存在不同诉讼地位"
                           f"（{'、'.join(sorted({i['role_display'] for i in items}))}），"
                           '合并后将全部保留，请逐项核实。',
            })

    duplicate_roles = []
    for (case_id, role), items in sorted(by_case_role.items(), key=lambda x: (x[0][0], x[0][1])):
        if len(items) == 1:
            continue
        client_values = sorted({bool(i['is_client']) for i in items})
        duplicate_roles.append({
            'key': f'{case_id}:{role}',
            'case_id': case_id,
            'case_number': items[0]['case_number'],
            'case_title': items[0]['case_title'],
            'role': role,
            'role_display': items[0]['role_display'],
            'rows': items,
            'is_client_options': client_values,
            'requires_client_choice': len(client_values) > 1,
        })

    return {
        'rows': rows,
        'role_warnings': role_warnings,
        'confirm_case_ids': sorted(confirm_case_ids),
        'duplicate_roles': duplicate_roles,
    }


def _candidate_payload(group_id, parties, match_basis, confidence):
    distinct_ids = sorted({norm_id(p.id_number) for p in parties if norm_id(p.id_number)})
    blocked = len(distinct_ids) > 1
    relations = _relation_analysis(parties)
    reasons = []
    if 'id_number' in match_basis:
        reasons.append('证件号一致')
    if 'contact' in match_basis:
        reasons.append('名称与联系方式一致')
    if 'name' in match_basis:
        reasons.append('名称相同（证件不同或缺失，需人工核实）')

    return {
        'id': group_id,
        'confidence': 'blocked' if blocked else confidence,
        'match_reasons': reasons,
        'blocked': blocked,
        'block_reason': '同名档案存在不同证件号，不能自动合并；请核实后分别保留或更正证件号。'
                        if blocked else '',
        'parties': PartySerializer(parties, many=True).data,
        'conflicts': _party_conflicts(parties),
        'relations': relations,
    }


def duplicate_candidates():
    """列出待核实重复档案：同证件号 / 同名称同联系方式 / 同名。"""
    parties = list(Party.objects.filter(merged_into__isnull=True).prefetch_related('aliases'))
    parent = {p.id: p.id for p in parties}
    edge_basis = defaultdict(set)

    def link(a, b, basis):
        # 记录原始候选边；构建组时再汇总到对应连通组。
        edge_basis[(min(a, b), max(a, b))].add(basis)
        _union(parent, a, b)

    buckets = {'id_number': defaultdict(list), 'contact': defaultdict(list),
               'name': defaultdict(list)}
    for p in parties:
        ident = norm_id(p.id_number)
        phone = norm_phone(p.phone)
        name = norm_name(p.name)
        if ident:
            buckets['id_number'][ident].append(p.id)
        if name and phone:
            buckets['contact'][(name, phone)].append(p.id)
        if name:
            buckets['name'][name].append(p.id)

    # DSU 合并同证件号、同名同联系方式、同名的候选。
    for basis, groups in buckets.items():
        for ids in groups.values():
            if len(ids) > 1:
                first = ids[0]
                for other in ids[1:]:
                    link(first, other, basis)

    groups = defaultdict(list)
    for p in parties:
        groups[_find(parent, p.id)].append(p)

    candidates = []
    serial = 1
    for root, members in groups.items():
        if len(members) <= 1:
            continue
        member_ids = {p.id for p in members}
        basis = set()
        for (a, b), bases in edge_basis.items():
            # 收集所有端点均在该连通组内的边，避免 DSU root 变化遗漏标签
            if a in member_ids and b in member_ids:
                basis.update(bases)
        confidence = 'low'
        if 'id_number' in basis:
            confidence = 'high'
        elif 'contact' in basis:
            confidence = 'medium'
        members.sort(key=lambda p: (p.created_at, p.id))
        candidates.append(_candidate_payload(serial, members, basis, confidence))
        serial += 1

    rank = {'high': 0, 'medium': 1, 'low': 2, 'blocked': 3}
    candidates.sort(key=lambda c: (rank[c['confidence']], c['id']))
    for index, candidate in enumerate(candidates, 1):
        candidate['id'] = index
    return candidates


def _require(condition, detail):
    if not condition:
        raise serializers.ValidationError(detail)


def merge_parties(data):
    """原子合并当事人档案。任何校验或写入失败均整体回滚。"""
    master_id = data.get('master_party')
    source_ids = data.get('source_parties') or []
    operator = clean_text(data.get('operator'))

    _require(master_id, {'master_party': '请选择主档'})
    _require(isinstance(source_ids, list) and source_ids,
             {'source_parties': '请选择至少一个被合并档案'})
    try:
        master_id = int(master_id)
        source_ids = [int(i) for i in source_ids if i]
    except (TypeError, ValueError):
        raise serializers.ValidationError({'source_parties': '当事人标识格式不正确'})
    _require(master_id not in source_ids, {'master_party': '主档不能同时作为被合并旧档'})
    _require(len(source_ids) == len(set(source_ids)),
             {'source_parties': '被合并档案不能重复'})

    with transaction.atomic():
        cursor = connection.cursor()
        # 锁定关联写入：合并期间新增的涉案关系必须等待重指完成，不能丢失。
        cursor.execute('LOCK TABLE cases_caseparty, cases_party, cases_partyalias, '
                       'cases_partymergerecord IN ACCESS EXCLUSIVE MODE')
        all_ids = sorted(set([int(master_id)] + source_ids))
        parties = list(Party.objects.select_for_update().filter(id__in=all_ids).order_by('id'))
        by_id = {p.id: p for p in parties}

        _require(len(parties) == len(all_ids), {'source_parties': '存在无效的当事人档案'})
        master = by_id.get(int(master_id))
        sources = [by_id[i] for i in source_ids]
        _require(master is not None, {'master_party': '主档不存在'})
        _require(all(not p.merged_into_id for p in parties),
                 {'source_parties': '已合并旧档不能再次作为合并对象，请选择当前有效主档'})

        distinct_ids = sorted({norm_id(p.id_number) for p in parties if norm_id(p.id_number)})
        _require(len(distinct_ids) <= 1,
                 {'id_number': '同名但证件号不同，不能自动合并；请核实后保留独立档案'})

        field_resolutions = data.get('field_resolutions') or {}
        _require(isinstance(field_resolutions, dict), {'field_resolutions': '冲突信息格式不正确'})
        conflicts = _party_conflicts(parties)
        allowed_values = {
            c['field']: set(c['options']) for c in conflicts
        }
        resolved = {}
        for conflict in conflicts:
            field = conflict['field']
            _require(field in field_resolutions,
                     {'field_resolutions': f'请逐项确认冲突信息：{conflict["label"]}'})
            value = field_resolutions[field]
            if field == 'party_type':
                _require(value in VALID_PARTY_TYPES,
                         {'field_resolutions': '请选择有效的当事人类型'})
            else:
                value = clean_text(value) if isinstance(value, str) else ''
                _require(value in allowed_values[field],
                         {'field_resolutions': f'请从候选值中确认「{conflict["label"]}」'})
            resolved[field] = value

        relations = _relation_analysis(parties)
        try:
            confirmed_role_cases = {int(i) for i in (data.get('confirmed_role_cases') or [])}
        except (TypeError, ValueError):
            raise serializers.ValidationError({'confirmed_role_cases': '涉案关系核实标识格式不正确'})
        required_role_cases = set(relations['confirm_case_ids'])
        _require(required_role_cases.issubset(confirmed_role_cases),
                 {'confirmed_role_cases': '同一案件中的不同诉讼地位必须逐项核实并确认保留'})

        decisions = data.get('relation_decisions') or {}
        _require(isinstance(decisions, dict), {'relation_decisions': '涉案关系确认格式不正确'})
        duplicate_plan = {}
        for dup in relations['duplicate_roles']:
            key = dup['key']
            _require(key in decisions and isinstance(decisions[key], dict),
                     {'relation_decisions': f'请确认案件「{dup["case_title"]}」的{dup["role_display"]}关系'})
            is_client = decisions[key].get('is_client')
            _require(isinstance(is_client, bool),
                     {'relation_decisions': f'请确认案件「{dup["case_title"]}」的客户状态'})
            duplicate_plan[key] = {'is_client': is_client, 'rows': dup['rows']}

        # 主档字段冲突解决。若主档名称被替换，先保留主档旧名称。
        old_master_name = clean_text(master.name)
        new_name = resolved.get('name', old_master_name)
        if old_master_name and new_name and old_master_name != new_name:
            PartyAlias.objects.get_or_create(
                party=master, name=old_master_name,
                defaults={'source_system': master.source_system or '案件登记'})
        for field, value in resolved.items():
            setattr(master, field, value)
        master.save(update_fields=list(resolved.keys()))
        master.refresh_from_db()

        relation_result = {'retained_roles': [], 'merged_duplicates': [],
                           'moved_relations': [], 'warnings': relations['role_warnings']}
        source_relation_count = CaseParty.objects.filter(party_id__in=source_ids).count()
        # 1. 同一案件、同一诉讼地位的重复关联归并为一条。
        for key, plan in duplicate_plan.items():
            rows = plan['rows']
            target = next((r for r in rows if r['party_id'] == master.id), None)
            if target is None:
                target = sorted(rows, key=lambda r: r['case_party_id'])[0]
            target_cp = CaseParty.objects.select_for_update().get(id=target['case_party_id'])
            target_cp.party = master
            target_cp.is_client = plan['is_client']
            target_cp.save(update_fields=['party', 'is_client'])
            removed = []
            for row in rows:
                if row['case_party_id'] == target_cp.id:
                    continue
                removed.append(row)
                CaseParty.objects.filter(id=row['case_party_id']).delete()
            relation_result['merged_duplicates'].append({
                'key': key,
                'case_id': target_cp.case_id,
                'role': target_cp.role,
                'retained_case_party_id': target_cp.id,
                'removed_case_party_ids': [r['case_party_id'] for r in removed],
                'is_client': target_cp.is_client,
            })

        # 2. 其余涉案关系重指到主档；不同诉讼地位因 role 不同自然保留。
        remaining = (CaseParty.objects.filter(party_id__in=source_ids)
                     .select_for_update().select_related('case'))
        moved_count = 0
        for cp in remaining:
            moved_count += 1
            relation_result['moved_relations'].append({
                'case_party_id': cp.id,
                'case_id': cp.case_id,
                'case_number': cp.case.case_number,
                'role': cp.role,
                'role_display': cp.get_role_display(),
                'is_client': cp.is_client,
            })
            cp.party = master
            cp.save(update_fields=['party'])

        for warning in relations['role_warnings']:
            relation_result['retained_roles'].append({
                'case_id': warning['case_id'],
                'case_number': warning['case_number'],
                'roles': warning['roles'],
            })

        now = timezone.now()
        warnings_confirmed = [f'different_roles:{i}' for i in sorted(required_role_cases)]
        records = []
        for source in sources:
            snapshot = PartySerializer(source).data
            source_name = clean_text(source.name)
            if source_name and source_name != clean_text(master.name):
                PartyAlias.objects.get_or_create(
                    party=master, name=source_name,
                    defaults={'source_party': source,
                              'source_system': source.source_system or '案件登记'})
            # 旧档此前沉淀的曾用名继续归到主档；原别名行保留在旧档以保留历史。
            for alias in source.aliases.all():
                PartyAlias.objects.get_or_create(
                    party=master, name=alias.name,
                    defaults={'source_party': alias.source_party,
                              'source_system': alias.source_system})

            record = PartyMergeRecord.objects.create(
                master_party=master,
                source_party=source,
                source_name=source_name,
                source_system=source.source_system or '案件登记',
                source_snapshot=snapshot,
                field_resolutions=resolved,
                relation_resolutions=relation_result,
                warnings_confirmed=warnings_confirmed,
                operator=operator,
            )
            records.append(record)

            # 若被选旧档本身已是一个主档，其下级旧档和历史记录同步归并。
            source.merged_parties.update(merged_into=master, merged_at=now)
            source.merge_records_as_master.update(master_party=master)

            source.merged_into = master
            source.merged_at = now
            source.save(update_fields=['merged_into', 'merged_at'])

        # 合并后再次校验：旧档不得残留涉案关系；所有待移动关联均已有归属。
        leftover = CaseParty.objects.filter(party_id__in=source_ids).count()
        _require(leftover == 0, {'non_field_errors': '涉案关系归并未完成，已回滚本次合并'})
        removed_count = sum(
            len(item.get('removed_case_party_ids', []))
            for item in relation_result['merged_duplicates'])
        accounted_count = moved_count + removed_count
        _require(accounted_count == source_relation_count,
                 {'non_field_errors': '涉案关系数量核对不一致，已回滚本次合并'})

        return {
            'master': PartySerializer(master).data,
            'records': [
                {'id': r.id, 'source_party': r.source_party_id,
                 'source_name': r.source_name, 'created_at': r.created_at}
                for r in records
            ],
        }
