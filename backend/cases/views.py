from datetime import date, timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from . import handovers as ho
from .handovers import collect_pending_items, compute_items_hash, diff_items, refresh_items
from .models import (Case, CaseHandover, CaseLawyer, CaseParty, Deadline,
                     HandoverItem, HandoverLog, Hearing, Lawyer, Material,
                     Party, StageLog)
from .serializers import (CaseDetailSerializer, CaseLawyerSerializer,
                          CaseListSerializer, CasePartySerializer,
                          CaseWriteSerializer, DeadlineSerializer,
                          HandoverCreateSerializer, HandoverDetailSerializer,
                          HandoverItemSerializer, HandoverListSerializer,
                          HearingSerializer, LawyerSerializer,
                          MaterialSerializer, PartySerializer,
                          StageLogSerializer)


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
            'caselawyer_set__lawyer', 'caseparty_set__party', 'deadlines')
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
        """向本案添加当事人前的利益冲突预检

        POST /api/cases/{id}/conflict-check/  {party_id, is_client}
        """
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

    @action(detail=True, methods=['post'], url_path='handovers/initiate')
    def initiate_handover(self, request, pk=None):
        """发起案件交接：汇总未办期限/后续开庭/待提交材料，生成待核对清单。

        POST /api/cases/{id}/handovers/initiate/
        {to_lawyer | to_lawyer_id, from_lawyer?, reason?, submit?}
        """
        case = self.get_object()
        ser = HandoverCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        to_lawyer = ser.validated_data['to_lawyer']
        reason = ser.validated_data.get('reason', '')

        # 交出人：默认取本案主办律师；协办发起须显式传入 from_lawyer
        from_lawyer = None
        from_id = request.data.get('from_lawyer')
        if from_id:
            from_lawyer = get_object_or_404(Lawyer, pk=from_id)
            if not CaseLawyer.objects.filter(case=case, lawyer=from_lawyer).exists():
                raise ValidationError({'from_lawyer': '交出人当前不在本案承办律师中'})
        else:
            from_lawyer = CaseLawyer.objects.filter(case=case, role='lead').first()
            from_lawyer = from_lawyer.lawyer if from_lawyer else None
        if not from_lawyer:
            raise ValidationError({'from_lawyer': '本案无主办律师，请显式指定交出人'})
        if from_lawyer == to_lawyer:
            raise ValidationError({'to_lawyer': '接收人不能与交出人为同一人'})

        active = case.handovers.filter(
            status__in=['draft', 'pending', 'returned']).first()
        if active:
            raise ValidationError(
                {'detail': f'本案已有进行中的交接（{active.from_lawyer.name}→'
                           f'{active.to_lawyer.name}），请先完成或取消'})

        with transaction.atomic():
            handover = CaseHandover.objects.create(
                case=case, from_lawyer=from_lawyer, to_lawyer=to_lawyer,
                status='draft', reason=reason)
            pending = collect_pending_items(case)
            for snap in pending:
                HandoverItem.objects.create(handover=handover, **snap)
            handover.items_hash = compute_items_hash(pending)
            handover.last_refreshed_at = timezone.now()
            handover.save(update_fields=['items_hash', 'last_refreshed_at'])
            HandoverLog.objects.create(
                handover=handover, action='create', actor_lawyer=from_lawyer,
                actor_name=from_lawyer.name,
                note=f'发起交接：{from_lawyer.name} → {to_lawyer.name}'
                     + (f'（{reason}）' if reason else ''))
            if ser.validated_data.get('submit'):
                ho.submit(handover, from_lawyer)
        return Response(HandoverDetailSerializer(handover).data,
                        status=status.HTTP_201_CREATED)


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

    def destroy(self, request, *args, **kwargs):
        # 交接完成前，不得绕过交接流程直接删掉交出人（原责任人须保留可追溯）
        link = self.get_object()
        active = CaseHandover.objects.filter(
            case=link.case, status__in=['draft', 'pending', 'returned'],
            from_lawyer=link.lawyer).first()
        if active:
            raise PermissionDenied(
                f'该律师与本案存在进行中的交接（{active.get_status_display()}），'
                '请先完成或取消交接，不能直接移除')
        return super().destroy(request, *args, **kwargs)


class HandoverViewSet(viewsets.ReadOnlyModelViewSet):
    """案件交接

    - POST /api/cases/{id}/handovers/initiate/   发起交接（自动汇总待办）
    - POST /api/handovers/{id}/submit/           交出人提交核对
    - POST /api/handovers/{id}/return/           接收人退回补充
    - POST /api/handovers/{id}/confirm/          接收人确认接管
    - POST /api/handovers/{id}/cancel/           取消
    - POST /api/handovers/{id}/refresh/          补入交接期间新增/变更的待办
    """

    def get_queryset(self):
        qs = CaseHandover.objects.select_related(
            'case', 'from_lawyer', 'to_lawyer').prefetch_related('items', 'logs')
        p = self.request.query_params
        if p.get('case'):
            qs = qs.filter(case_id=p['case'])
        if p.get('lawyer'):
            lid = p['lawyer']
            qs = qs.filter(Q(from_lawyer_id=lid) | Q(to_lawyer_id=lid))
        if p.get('status'):
            qs = qs.filter(status=p['status'])
        if p.get('active') in ('1', 'true'):
            qs = qs.filter(status__in=['draft', 'pending', 'returned'])
        return qs

    def get_serializer_class(self):
        return HandoverDetailSerializer if self.action == 'retrieve' else HandoverListSerializer

    def _lawyer(self, key='actor_lawyer'):
        """无鉴权系统：以请求体/查询参数中的律师ID代表当前操作人"""
        lid = self.request.data.get(key) or self.request.query_params.get(key)
        if not lid:
            raise ValidationError({key: '请指定操作律师'})
        return get_object_or_404(Lawyer, pk=lid)

    def _fresh(self, pk):
        """操作完成后重新取库，避免 prefetch 缓存中的旧 items/logs"""
        return (CaseHandover.objects.prefetch_related('items', 'logs')
                .select_related('case', 'from_lawyer', 'to_lawyer').get(pk=pk))

    @action(detail=True, methods=['post'], url_path='refresh')
    def do_refresh(self, request, pk=None):
        handover = self.get_object()
        actor = self._lawyer()
        ho._require_lawyer(handover, actor, [handover.from_lawyer, handover.to_lawyer])
        if handover.status not in ('draft', 'pending', 'returned'):
            raise ValidationError({'status': '已结束的交接不能再刷新清单'})
        result = refresh_items(
            handover, actor=actor, note=request.data.get('note', ''),
            resubmit=bool(request.data.get('resubmit')))
        # 补入变更后若处于待核对，退回交出人重新提交，接收人须基于新清单重新核对
        changed_any = any([result['added'], result['changed'], result['removed']])
        if changed_any and handover.status == 'pending':
            handover.status = 'returned'
            handover.returned_reason = '交接期间有待办新增/变更，已自动补入清单，请交出人确认后重新提交'
            handover.save()
        # 交出人在退回状态补入且勾选 resubmit：直接重新提交核对
        if (request.data.get('resubmit') and actor == handover.from_lawyer
                and handover.status == 'returned'
                and handover.items.exclude(change_flag='removed').exists()):
            handover.status = 'pending'
            handover.submitted_at = timezone.now()
            handover.returned_reason = ''
            handover.save()
            from .handovers import _log
            _log(handover, 'submit', actor, '补入最新待办后重新提交核对')
        # prefetch 缓存是刷新前的对象，需重新取库
        return Response({
            'detail': ('清单已是最新' if not changed_any
                       else '；'.join(result['changed_titles']) or '清单已更新'),
            **result,
            'handover': HandoverDetailSerializer(self._fresh(handover.pk)).data,
        })

    @action(detail=True, methods=['post'], url_path='submit')
    def do_submit(self, request, pk=None):
        handover = self.get_object()
        ho.submit(handover, self._lawyer())
        return Response(HandoverDetailSerializer(self._fresh(pk)).data)

    @action(detail=True, methods=['post'], url_path='return')
    def do_return(self, request, pk=None):
        handover = self.get_object()
        ho.return_back(handover, self._lawyer(), request.data.get('reason', ''))
        return Response(HandoverDetailSerializer(self._fresh(pk)).data)

    @action(detail=True, methods=['post'], url_path='confirm')
    def do_confirm(self, request, pk=None):
        handover = self.get_object()
        ho.confirm_takeover(handover, self._lawyer())
        return Response(HandoverDetailSerializer(self._fresh(pk)).data)

    @action(detail=True, methods=['post'], url_path='cancel')
    def do_cancel(self, request, pk=None):
        handover = self.get_object()
        ho.cancel(handover, self._lawyer(), request.data.get('reason', ''))
        return Response(HandoverDetailSerializer(self._fresh(pk)).data)

    @action(detail=True, methods=['post'], url_path='items/(?P<item_id>[0-9]+)/check')
    def check_item(self, request, pk=None, item_id=None):
        """接收人逐项核对"""
        handover = self.get_object()
        actor = self._lawyer()
        ho._require_lawyer(handover, actor, [handover.to_lawyer])
        if handover.status not in ('pending', 'returned'):
            raise ValidationError({'status': '仅核对中的清单可以标记核对'})
        item = get_object_or_404(HandoverItem, pk=item_id, handover=handover)
        item.checked = bool(request.data.get('checked', True))
        item.check_note = request.data.get('check_note', '') or ''
        item.save()
        return Response(HandoverItemSerializer(item).data)

    @action(detail=True, methods=['post'], url_path='items/(?P<item_id>[0-9]+)/destination')
    def set_destination(self, request, pk=None, item_id=None):
        """交出人/接收人明确每项待办去向"""
        handover = self.get_object()
        actor = self._lawyer()
        ho._require_lawyer(handover, actor, [handover.from_lawyer, handover.to_lawyer])
        if handover.status not in ('draft', 'pending', 'returned'):
            raise ValidationError({'status': '当前状态不能调整去向'})
        dest = request.data.get('destination')
        if dest not in dict(HandoverItem.DESTINATION_CHOICES):
            raise ValidationError({'destination': '去向无效'})
        item = get_object_or_404(HandoverItem, pk=item_id, handover=handover)
        item.destination = dest
        # 调整过清单后需要接收人重新核对该项
        item.checked = False
        item.save()
        return Response(HandoverItemSerializer(item).data)

    @action(detail=True, methods=['post'], url_path='custom-items')
    def add_custom_item(self, request, pk=None):
        """交出人补充清单外事项（口头交接、卷宗原件等）"""
        handover = self.get_object()
        actor = self._lawyer()
        ho._require_lawyer(handover, actor, [handover.from_lawyer])
        if handover.status not in ('draft', 'pending', 'returned'):
            raise ValidationError({'status': '当前状态不能补充事项'})
        title = (request.data.get('title') or '').strip()
        if not title:
            raise ValidationError({'title': '请填写事项内容'})
        item = HandoverItem.objects.create(
            handover=handover, item_type='custom', ref_id=None,
            title=title[:200], detail=(request.data.get('detail') or '')[:300],
            due_date=request.data.get('due_date') or None,
            destination=request.data.get('destination', 'takeover'))
        HandoverLog.objects.create(
            handover=handover, action='edit', actor_lawyer=actor,
            actor_name=actor.name, note=f'补充事项：{title}')
        return Response(HandoverItemSerializer(item).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'], url_path='custom-items/(?P<item_id>[0-9]+)')
    def delete_custom_item(self, request, pk=None, item_id=None):
        handover = self.get_object()
        actor = self._lawyer()
        ho._require_lawyer(handover, actor, [handover.from_lawyer])
        item = get_object_or_404(
            HandoverItem, pk=item_id, handover=handover, item_type='custom')
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


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


class DeadlineViewSet(viewsets.ModelViewSet):
    serializer_class = DeadlineSerializer

    def get_queryset(self):
        qs = Deadline.objects.select_related('case')
        p = self.request.query_params
        if p.get('case'):
            qs = qs.filter(case_id=p['case'])
        if p.get('done') in ('true', 'false'):
            qs = qs.filter(is_done=(p['done'] == 'true'))
        if p.get('upcoming'):
            days = int(p.get('days', 30))
            qs = qs.filter(is_done=False,
                           due_date__lte=date.today() + timedelta(days=days))
        return qs


@api_view(['GET'])
def dashboard(request):
    """工作台统计：案件概览、期限提醒、近期开庭。

    可传 ?lawyer={id} 按律师个人视角归集——交接完成后案件承办关系已变更，
    新负责人在自己的工作台看到案件，原责任人不再看到（历史办案记录仍保留原承办人）。
    """
    today = date.today()
    soon = today + timedelta(days=30)
    cases = Case.objects.all()
    lawyer_id = request.query_params.get('lawyer')
    lawyer = None
    if lawyer_id:
        lawyer = get_object_or_404(Lawyer, pk=lawyer_id)
        cases = cases.filter(caselawyer__lawyer=lawyer).distinct()

    stage_stats = []
    counts = {row['stage']: row['n'] for row in cases.values('stage').annotate(n=Count('id'))}
    for key, label in Case.STAGE_CHOICES:
        stage_stats.append({'stage': key, 'stage_display': label,
                            'count': counts.get(key, 0)})

    hearings = Hearing.objects.filter(
        case__in=cases, hearing_time__date__gte=today).select_related('case').order_by('hearing_time')[:10]
    deadlines = Deadline.objects.filter(
        case__in=cases, is_done=False, due_date__lte=soon).select_related('case').order_by('due_date')[:20]

    data = {
        'case_total': cases.count(),
        'case_active': cases.exclude(stage='closed').count(),
        'party_total': Party.objects.count(),
        'lawyer_total': Lawyer.objects.count(),
        'deadline_overdue': Deadline.objects.filter(
            case__in=cases, is_done=False, due_date__lt=today).count(),
        'stage_stats': stage_stats,
        'hearings_upcoming': HearingSerializer(hearings, many=True).data,
        'deadlines_upcoming': DeadlineSerializer(deadlines, many=True).data,
    }

    if lawyer:
        active_qs = CaseHandover.objects.filter(
            status__in=['draft', 'pending', 'returned']).select_related('case')
        # 只有「待接收人核对」才出现在接收人工作台；已退回补充的控制权在交出人
        to_review = active_qs.filter(to_lawyer=lawyer, status='pending')
        # 交出人视角：草稿、被退回需处理，以及已提交待对方核对（可查看进度）
        outgoing = active_qs.filter(from_lawyer=lawyer)
        data['handovers_to_review'] = HandoverListSerializer(to_review, many=True).data
        data['handovers_outgoing'] = HandoverListSerializer(outgoing, many=True).data
        data['scope_lawyer_id'] = lawyer.id
        data['scope_lawyer_name'] = lawyer.name

    return Response(data)


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
