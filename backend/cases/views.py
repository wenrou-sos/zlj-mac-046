from datetime import date, timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from .models import (Case, CaseLawyer, CaseParty, Deadline, DeadlineEvent,
                     DeadlineRule, Hearing, Holiday, Lawyer, Material, Party,
                     Reminder, StageLog)
from .reminder_tasks import retry_failed_reminders, send_due_reminders
from .serializers import (CaseDetailSerializer, CaseLawyerSerializer,
                          CaseListSerializer, CasePartySerializer,
                          CaseWriteSerializer, DeadlineEventSerializer,
                          DeadlineRuleSerializer, DeadlineSerializer,
                          DeadlineVersionListSerializer, HearingSerializer,
                          HolidaySerializer, LawyerSerializer,
                          MaterialSerializer, PartySerializer,
                          ReminderSerializer, StageLogSerializer)
from .services import (apply_event_update, apply_rule_to_existing,
                       preview_event, preview_event_revocation, process_event,
                       revoke_event)


class LawyerViewSet(viewsets.ModelViewSet):
    serializer_class = LawyerSerializer

    def get_queryset(self):
        qs = Lawyer.objects.all()
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(bar_number__icontains=search))
        return qs


class PartyViewSet(viewsets.ModelViewSet):
    serializer_class = PartySerializer

    def get_queryset(self):
        qs = Party.objects.all()
        search = self.request.query_params.get('search', '').strip()
        ptype = self.request.query_params.get('party_type', '').strip()
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(id_number__icontains=search))
        if ptype:
            qs = qs.filter(party_type=ptype)
        return qs


class CaseViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        qs = Case.objects.prefetch_related(
            'caselawyer_set__lawyer', 'caseparty_set__party',
            'deadlines__owner', 'deadlines__reviewer',
            'deadline_events', 'deadlines__versions')
        p = self.request.query_params
        if p.get('stage'):
            qs = qs.filter(stage=p['stage'])
        if p.get('case_type'):
            qs = qs.filter(case_type=p['case_type'])
        search = p.get('search', '').strip()
        if search:
            qs = qs.filter(Q(case_number__icontains=search) | Q(title__icontains=search))
        return qs

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return CaseDetailSerializer
        if self.action in ('create', 'update', 'partial_update'):
            return CaseWriteSerializer
        return CaseListSerializer

    @action(detail=True, methods=['post'], url_path='conflict-check')
    def conflict_check(self, request, pk=None):
        """向本案添加当事人前的利益冲突预检"""
        case = self.get_object()
        party = get_object_or_404(Party, pk=request.data.get('party_id'))
        is_client = bool(request.data.get('is_client'))

        conflicts = []
        existing = CaseParty.objects.filter(case=case, party=party).first()
        if existing:
            conflicts.append({
                'level': 'high',
                'message': f'该当事人已是本案{existing.get_role_display()}，请勿重复添加',
            })

        for cp in (CaseParty.objects.filter(party=party).exclude(case=case)
                   .select_related('case')):
            title = cp.case.title
            if cp.is_client and cp.case.stage != 'closed' and not is_client:
                conflicts.append({
                    'level': 'high',
                    'message': f'该当事人是本所在办案件「{title}」的委托客户，'
                               f'本案拟列为对方当事人，构成直接利益冲突',
                })
            elif cp.is_client and is_client:
                conflicts.append({
                    'level': 'low',
                    'message': f'该当事人已是本所客户（案件「{title}」），请注意信息隔离',
                })
            elif not cp.is_client and is_client and cp.case.stage != 'closed':
                conflicts.append({
                    'level': 'medium',
                    'message': f'该当事人是本所在办案件「{title}」的对方当事人，'
                               f'接受其委托前须进行冲突审查并取得相关方同意',
                })

        has_high = any(c['level'] == 'high' for c in conflicts)
        return Response({'has_conflict': has_high, 'conflicts': conflicts})


class CasePartyViewSet(viewsets.ModelViewSet):
    serializer_class = CasePartySerializer

    def get_queryset(self):
        qs = CaseParty.objects.select_related('party', 'case')
        case_id = self.request.query_params.get('case')
        if case_id:
            qs = qs.filter(case_id=case_id)
        return qs


class CaseLawyerViewSet(viewsets.ModelViewSet):
    serializer_class = CaseLawyerSerializer

    def get_queryset(self):
        qs = CaseLawyer.objects.select_related('lawyer', 'case')
        case_id = self.request.query_params.get('case')
        if case_id:
            qs = qs.filter(case_id=case_id)
        return qs


class HearingViewSet(viewsets.ModelViewSet):
    serializer_class = HearingSerializer

    def get_queryset(self):
        qs = Hearing.objects.select_related('case')
        case_id = self.request.query_params.get('case')
        if case_id:
            qs = qs.filter(case_id=case_id)
        return qs


class StageLogViewSet(viewsets.ModelViewSet):
    serializer_class = StageLogSerializer

    def get_queryset(self):
        qs = StageLog.objects.select_related('case')
        case_id = self.request.query_params.get('case')
        if case_id:
            qs = qs.filter(case_id=case_id)
        return qs


class MaterialViewSet(viewsets.ModelViewSet):
    serializer_class = MaterialSerializer

    def get_queryset(self):
        qs = Material.objects.select_related('case')
        case_id = self.request.query_params.get('case')
        if case_id:
            qs = qs.filter(case_id=case_id)
        return qs


class HolidayViewSet(viewsets.ModelViewSet):
    serializer_class = HolidaySerializer
    queryset = Holiday.objects.all()


class DeadlineRuleViewSet(viewsets.ModelViewSet):
    serializer_class = DeadlineRuleSerializer
    queryset = DeadlineRule.objects.all()

    def _current_rule(self):
        return self.get_object()

    @action(detail=True, methods=['get'], url_path='apply-preview')
    def apply_preview(self, request, pk=None):
        """规则变更后，先预览对全部相关有效事件的影响，不保存。"""
        rule = self._current_rule()
        # 允许通过 query 参数模拟未保存的规则调整。
        serializer = DeadlineRuleSerializer(rule, data=request.query_params.dict(),
                                            partial=True)
        preview_rule = rule
        if request.query_params:
            serializer.is_valid(raise_exception=True)
            for key, value in serializer.validated_data.items():
                setattr(preview_rule, key, value)
        result = _preview_rule(preview_rule)
        return Response(result)

    @action(detail=True, methods=['post'], url_path='apply-existing')
    def apply_existing(self, request, pk=None):
        rule = self._current_rule()
        result = apply_rule_to_existing(rule)
        return Response(result)


def _preview_rule(rule):
    """与 apply_rule_to_existing 相同的计算口径，但不写库。"""
    from .services import (calculate_due_date, holiday_id_set, render_basis,
                           assign_owner_and_reviewer, _deadline_change_info)
    holidays = holiday_id_set()
    creates, updates, blocked = [], [], []
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
                    and current.title == rule.name):
                continue
            updates.append(_deadline_change_info(
                current, rule=rule, event=event, start_date=start_date,
                due_date=due_date, basis=basis, owner=current.owner or owner,
                reviewer=current.reviewer or reviewer, action='update',
                reason='规则调整将替代旧版本'))
        else:
            creates.append(_deadline_change_info(
                rule=rule, event=event, start_date=start_date, due_date=due_date,
                basis=basis, owner=owner, reviewer=reviewer, action='create'))
    return {'rule_id': rule.id, 'creates': creates, 'updates': updates,
            'blocked': blocked, 'requires_confirmation': bool(creates or updates or blocked)}


class DeadlineEventViewSet(viewsets.ModelViewSet):
    serializer_class = DeadlineEventSerializer
    queryset = DeadlineEvent.objects.select_related('case').all()

    def get_queryset(self):
        qs = DeadlineEvent.objects.select_related('case')
        case_id = self.request.query_params.get('case')
        if case_id:
            qs = qs.filter(case_id=case_id)
        status_ = self.request.query_params.get('status')
        if status_:
            qs = qs.filter(status=status_)
        return qs

    def perform_create(self, serializer):
        with transaction.atomic():
            event = serializer.save()
            result = process_event(event)
        event._generation_result = result

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            self.perform_create(serializer)
        except Exception as exc:  # 并发重复提交时依赖数据库唯一约束兜底
            if 'duplicate key' not in str(exc).lower() and 'unique' not in str(exc).lower():
                raise
            return Response({'detail': '同一事件正在处理或已存在，未重复生成期限'},
                            status=status.HTTP_409_CONFLICT)
        event = serializer.instance
        return Response({
            'event': DeadlineEventSerializer(event).data,
            'impact': getattr(event, '_generation_result', {}),
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        event = self.get_object()
        allowed = {'notes'}
        blocked_fields = set(request.data.keys()) - allowed
        if blocked_fields:
            return Response({
                'detail': '事件日期、类型或名称更正必须先预览影响并确认，请使用 change-preview / confirm-change'
            }, status=status.HTTP_400_BAD_REQUEST)
        return super().update(request, *args, **kwargs)

    def _changes(self, request):
        allowed = {'title', 'event_type', 'event_date', 'notes'}
        return {key: value for key, value in request.data.items() if key in allowed and value not in (None, '')}

    @action(detail=True, methods=['post'], url_path='change-preview')
    def change_preview(self, request, pk=None):
        old_event = self.get_object()
        changes = self._changes(request)
        if not changes:
            return Response({'detail': '没有可更正字段'}, status=status.HTTP_400_BAD_REQUEST)

        # 构造临时对象但不保存。
        effective = DeadlineEvent(
            case=old_event.case, title=changes.get('title', old_event.title),
            event_type=changes.get('event_type', old_event.event_type),
            event_date=changes.get('event_date', old_event.event_date),
            status=old_event.status)
        return Response(preview_event(old_event, effective))

    @action(detail=True, methods=['post'], url_path='confirm-change')
    def confirm_change(self, request, pk=None):
        event = self.get_object()
        changes = self._changes(request)
        reason = request.data.get('reason') or '事件日期/类型/名称更正'
        if not changes:
            return Response({'detail': '没有可更正字段'}, status=status.HTTP_400_BAD_REQUEST)
        result = apply_event_update(event, changes, reason)
        return Response(result)

    @action(detail=True, methods=['post'], url_path='revocation-preview')
    def revocation_preview(self, request, pk=None):
        event = self.get_object()
        reason = request.data.get('reason') or '事件撤销'
        return Response(preview_event_revocation(event, reason))

    @action(detail=True, methods=['post'], url_path='confirm-revoke')
    def confirm_revoke(self, request, pk=None):
        event = self.get_object()
        reason = (request.data.get('reason') or '').strip()
        if not reason:
            return Response({'detail': '请填写撤销原因'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(revoke_event(event, reason))


class DeadlineViewSet(viewsets.ModelViewSet):
    serializer_class = DeadlineSerializer

    def get_queryset(self):
        qs = Deadline.objects.select_related('case', 'owner', 'reviewer', 'rule', 'event')
        p = self.request.query_params
        if p.get('case'):
            qs = qs.filter(case_id=p['case'])
        if p.get('lifecycle'):
            qs = qs.filter(lifecycle=p['lifecycle'])
        elif p.get('include_inactive') != 'true':
            qs = qs.filter(lifecycle='active')
        if p.get('done') in ('true', 'false'):
            qs = qs.filter(is_done=(p['done'] == 'true'))
        owner = p.get('owner')
        if owner:
            qs = qs.filter(owner_id=owner)
        reviewer = p.get('reviewer')
        if reviewer:
            qs = qs.filter(reviewer_id=reviewer)
        if p.get('upcoming'):
            days = int(p.get('days', 30))
            qs = qs.filter(is_done=False, lifecycle='active',
                           due_date__lte=date.today() + timedelta(days=days))
        return qs

    @action(detail=True, methods=['get'], url_path='versions')
    def versions(self, request, pk=None):
        deadline = self.get_object()
        return Response(DeadlineVersionListSerializer(deadline.versions.all(), many=True).data)


class ReminderViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ReminderSerializer

    def get_queryset(self):
        # 页面打开时先执行到期发送和失败补发；无定时任务时也能闭环。
        send_due_reminders()
        retry_failed_reminders()
        qs = Reminder.objects.select_related('deadline__case', 'recipient')
        p = self.request.query_params
        if p.get('lawyer'):
            qs = qs.filter(recipient_id=p['lawyer'])
        if p.get('status'):
            qs = qs.filter(status=p['status'])
        if p.get('kind'):
            qs = qs.filter(kind=p['kind'])
        if p.get('case'):
            qs = qs.filter(deadline__case_id=p['case'])
        return qs

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        reminder = self.get_object()
        if reminder.status in ('sent', 'failed', 'pending'):
            reminder.status = 'confirmed'
            reminder.confirmed_at = timezone.now()
            reminder.save(update_fields=['status', 'confirmed_at', 'updated_at'])
        return Response(ReminderSerializer(reminder).data)

    @action(detail=True, methods=['post'], url_path='retry')
    def retry(self, request, pk=None):
        reminder = self.get_object()
        if reminder.status != 'failed':
            return Response({'detail': '仅发送失败的提醒支持补发'},
                            status=status.HTTP_400_BAD_REQUEST)
        from .reminder_tasks import deliver_reminder
        deliver_reminder(reminder)
        return Response(ReminderSerializer(reminder).data)

    @action(detail=False, methods=['post'], url_path='send-due')
    def send_due(self, request):
        sent = send_due_reminders()
        retried = retry_failed_reminders()
        return Response({'sent': sent, 'retried': retried})


@api_view(['GET'])
def dashboard(request):
    """工作台统计：案件概览、期限提醒、近期开庭、站内提醒。"""
    send_due_reminders()
    retry_failed_reminders()
    today = date.today()
    soon = today + timedelta(days=30)
    cases = Case.objects.all()

    stage_stats = []
    counts = {row['stage']: row['n'] for row in cases.values('stage').annotate(n=Count('id'))}
    for key, label in Case.STAGE_CHOICES:
        stage_stats.append({'stage': key, 'stage_display': label,
                            'count': counts.get(key, 0)})

    hearings = Hearing.objects.filter(
        hearing_time__date__gte=today).select_related('case').order_by('hearing_time')[:10]
    deadlines = Deadline.objects.filter(
        is_done=False, lifecycle='active', due_date__lte=soon
    ).select_related('case', 'owner', 'reviewer').order_by('due_date')[:20]
    reminder_qs = Reminder.objects.filter(status__in=['sent', 'failed'])
    lawyer_id = request.query_params.get('lawyer')
    if lawyer_id:
        reminder_qs = reminder_qs.filter(recipient_id=lawyer_id)

    return Response({
        'case_total': cases.count(),
        'case_active': cases.exclude(stage='closed').count(),
        'party_total': Party.objects.count(),
        'lawyer_total': Lawyer.objects.count(),
        'deadline_overdue': Deadline.objects.filter(
            is_done=False, lifecycle='active', due_date__lt=today).count(),
        'reminder_pending': Reminder.objects.filter(status='pending').count(),
        'reminder_unconfirmed': reminder_qs.filter(status='sent').count(),
        'reminder_failed': Reminder.objects.filter(status='failed').count(),
        'stage_stats': stage_stats,
        'hearings_upcoming': HearingSerializer(hearings, many=True).data,
        'deadlines_upcoming': DeadlineSerializer(deadlines, many=True).data,
    })


def _party_involvements(party):
    """汇总当事人在全部案件中的涉诉情况"""
    items = []
    for cp in (CaseParty.objects.filter(party=party)
               .select_related('case').order_by('-case__filed_date')):
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


@api_view(['GET'])
def conflict_check(request):
    """利益冲突检查：按姓名/名称或证件号检索当事人的全部涉诉记录"""
    name = request.query_params.get('name', '').strip()
    id_number = request.query_params.get('id_number', '').strip()
    if not name and not id_number:
        return Response({'detail': '请提供姓名/名称或证件号'}, status=status.HTTP_400_BAD_REQUEST)

    q = Q()
    if name:
        q |= Q(name__icontains=name)
    if id_number:
        q |= Q(id_number=id_number)
    parties = Party.objects.filter(q).distinct()

    results = []
    for party in parties:
        involvements = _party_involvements(party)
        warnings = []
        for inv in involvements:
            if inv['is_client'] and inv['stage'] != 'closed':
                warnings.append(f"系本所在办案件「{inv['case_title']}」的委托客户，"
                                f"代理与其利益相对方构成直接利益冲突")
            elif not inv['is_client']:
                warnings.append(f"在案件「{inv['case_title']}」中为对方当事人"
                                f"（{inv['stage_display']}）")
        if any(w.startswith('系本所') for w in warnings):
            risk = 'high'
        elif warnings:
            risk = 'medium'
        else:
            risk = 'low'
        results.append({
            'party': PartySerializer(party).data,
            'involvements': involvements,
            'warnings': warnings,
            'risk': risk,
        })

    return Response({'count': len(results), 'results': results})
