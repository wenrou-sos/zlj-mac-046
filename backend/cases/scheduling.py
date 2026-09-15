"""开庭排程：冲突检测与可用时段推荐

冲突规则：
- 同一律师的其他在排庭期：同一直接比较起止时间；不同地点时，
  双方各自按“往返缓冲”向外扩展后再比较（保证跨地点往返时间）。
- 律师请假/不可用时段：与开庭起止时间有交集即冲突。
"""
from datetime import datetime, time, timedelta

from django.utils import timezone

from .models import Hearing, HearingLawyer, Lawyer, LawyerAbsence

# 推荐替代时段时的工作时间窗
WORK_START = time(9, 0)
WORK_END = time(18, 0)
SLOT_STEP_MINUTES = 30  # 推荐时段按 30 分钟取整


def _norm_loc(location):
    return (location or '').strip()


def _overlap(s1, e1, s2, e2):
    return s1 < e2 and s2 < e1


def _fmt(dt):
    return timezone.localtime(dt).strftime('%Y-%m-%d %H:%M')


def find_conflicts(lawyer_ids, start, end, location, buffer_minutes,
                   exclude_hearing_id=None):
    """检查一组律师在指定时段的排程冲突，返回冲突列表"""
    conflicts = []
    lawyers = {l.id: l for l in Lawyer.objects.filter(id__in=lawyer_ids)}
    loc = _norm_loc(location)

    for lawyer_id in lawyer_ids:
        lawyer = lawyers.get(lawyer_id)
        if not lawyer:
            continue

        # 1) 其他案件庭期
        qs = (Hearing.objects.filter(
                  status='scheduled',
                  assignments__lawyer_id=lawyer_id,
                  assignments__status='active')
              .exclude(id=exclude_hearing_id)
              .select_related('case').distinct())
        for h in qs:
            s1, e1 = start, end
            s2, e2 = h.hearing_time, h.end_time
            same_loc = _norm_loc(h.location) == loc
            if not same_loc:
                # 跨地点：双方各加往返缓冲
                s1 -= timedelta(minutes=buffer_minutes)
                e1 += timedelta(minutes=buffer_minutes)
                s2 -= timedelta(minutes=h.buffer_minutes)
                e2 += timedelta(minutes=h.buffer_minutes)
            if _overlap(s1, e1, s2, e2):
                if same_loc:
                    detail = f'与「{h.case.title}」庭期重叠（{_fmt(h.hearing_time)}，{h.location}）'
                else:
                    detail = (f'与「{h.case.title}」庭期冲突（{_fmt(h.hearing_time)}，{h.location}；'
                              f'跨地点含往返缓冲）')
                conflicts.append({
                    'lawyer_id': lawyer_id, 'lawyer_name': lawyer.name,
                    'type': 'hearing', 'type_display': '其他庭期',
                    'hearing_id': h.id, 'detail': detail,
                })

        # 2) 请假 / 不可用时段
        for a in LawyerAbsence.objects.filter(
                lawyer_id=lawyer_id, start_time__lt=end, end_time__gt=start):
            conflicts.append({
                'lawyer_id': lawyer_id, 'lawyer_name': lawyer.name,
                'type': a.category, 'type_display': a.get_category_display(),
                'absence_id': a.id,
                'detail': (f'{a.get_category_display()}：{_fmt(a.start_time)} ~ {_fmt(a.end_time)}'
                           + (f'（{a.reason}）' if a.reason else '')),
            })

    return conflicts


def _busy_intervals(lawyer_id, location, buffer_minutes, day_start, day_end):
    """律师在指定日期窗口内的占用区间（庭期含跨地点缓冲 + 请假/不可用）"""
    loc = _norm_loc(location)
    intervals = []

    qs = (Hearing.objects.filter(
              status='scheduled',
              assignments__lawyer_id=lawyer_id,
              assignments__status='active',
              hearing_time__lt=day_end, end_time__gt=day_start)
          .distinct())
    for h in qs:
        s, e = h.hearing_time, h.end_time
        if _norm_loc(h.location) != loc:
            s -= timedelta(minutes=h.buffer_minutes)
            e += timedelta(minutes=h.buffer_minutes)
        intervals.append((s, e))

    for a in LawyerAbsence.objects.filter(
            lawyer_id=lawyer_id, start_time__lt=day_end, end_time__gt=day_start):
        intervals.append((a.start_time, a.end_time))

    return intervals


def suggest_slots(lawyer_ids, duration_minutes, location, buffer_minutes,
                  not_before=None, days=14, max_results=5):
    """为给定律师组合推荐可用开庭时段（工作时间窗内、全员无冲突）"""
    if not_before is None:
        not_before = timezone.localtime()
    duration = timedelta(minutes=duration_minutes)
    step = timedelta(minutes=SLOT_STEP_MINUTES)
    suggestions = []

    for offset in range(days):
        day = (not_before + timedelta(days=offset)).date()
        day_start = timezone.make_aware(datetime.combine(day, WORK_START))
        day_end = timezone.make_aware(datetime.combine(day, WORK_END))
        if day_end <= not_before:
            continue

        # 合并全部律师的占用区间
        busy = []
        for lawyer_id in lawyer_ids:
            busy.extend(_busy_intervals(lawyer_id, location, buffer_minutes,
                                        day_start, day_end))
        busy.sort()
        merged = []
        for s, e in busy:
            if merged and s <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], e))
            else:
                merged.append((s, e))

        # 在空档中按 30 分钟步长找可用时段；起始时间向上对齐到 30 分钟边界
        cursor = max(day_start, not_before).replace(second=0, microsecond=0)
        if cursor.minute % SLOT_STEP_MINUTES:
            cursor += timedelta(
                minutes=SLOT_STEP_MINUTES - cursor.minute % SLOT_STEP_MINUTES)

        for s, e in merged:
            while cursor + duration <= min(s, day_end):
                suggestions.append({'start': cursor, 'end': cursor + duration})
                if len(suggestions) >= max_results:
                    return suggestions
                cursor += step
            cursor = max(cursor, e)
        while cursor + duration <= day_end:
            suggestions.append({'start': cursor, 'end': cursor + duration})
            if len(suggestions) >= max_results:
                return suggestions
            cursor += step

    return suggestions


def hearing_snapshot(hearing):
    """生成开庭安排的快照（用于变更记录保留原安排）"""
    return {
        'hearing_time': _fmt(hearing.hearing_time),
        'end_time': _fmt(hearing.end_time),
        'location': hearing.location,
        'buffer_minutes': hearing.buffer_minutes,
        'judge': hearing.judge,
        'lawyers': [
            {'id': a.lawyer_id, 'name': a.lawyer.name}
            for a in hearing.assignments.filter(status='active').select_related('lawyer')
        ],
    }


def active_lawyer_ids(hearing):
    return list(hearing.assignments.filter(status='active')
                .values_list('lawyer_id', flat=True))
