from datetime import date, timedelta

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from . import archives
from .models import (ArchiveVersion, Case, CaseLawyer, CaseParty, Deadline,
                     Hearing, Lawyer, Material, Party, ReopenRequest, StageLog)
from .serializers import (ArchiveVersionSerializer, CaseDetailSerializer,
                          CaseLawyerSerializer, CaseListSerializer,
                          CasePartySerializer, CaseWriteSerializer,
                          DeadlineSerializer, HearingSerializer,
                          LawyerSerializer, MaterialSerializer,
                          PartySerializer, ReopenRequestSerializer,
                          StageLogSerializer)

ARCHIVE_LOCKED_DETAIL = '案件卷宗已封存，日常编辑和删除不能改写归档版本；如需再审或补充材料，请申请重开'


def _archive_error_response(exc):
    payload = {'detail': exc.message if hasattr(exc, 'message') else str(exc)}
    if isinstance(exc, archives.ArchiveConflict):
        payload['changed_sections'] = exc.changed_sections
        payload['stale_items'] = exc.stale_items
    return Response(payload, status=exc.status_code)


class SealedWriteGuardMixin:
    """子记录（当事人/律师/庭期/阶段/材料/期限）写保护：
    案件存在已封存卷宗时，禁止增删改。"""

    def _case_for_write(self, request):
        case_id = request.data.get('case')
        if case_id is not None:
            return Case.objects.filter(pk=case_id).first()
        if self.action in ('update', 'partial_update', 'destroy'):
            return getattr(self.get_object(), 'case', None)
        return None

    def _guard_sealed(self, request):
        case = self._case_for_write(request)
        if case is not None and case.is_sealed:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(ARCHIVE_LOCKED_DETAIL)

    def create(self, request, *args, **kwargs):
        self._guard_sealed(request)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self._guard_sealed(request)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._guard_sealed(request)
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._guard_sealed(request)
        return super().destroy(request, *args, **kwargs)


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
            'caselawyer_set__lawyer', 'caseparty_set__party', 'deadlines',
            'archive_versions', 'reopen_requests')
        p = self.request.query_params
        if p.get('stage'):
            qs = qs.filter(stage=p['stage'])
        if p.get('case_type'):
            qs = qs.filter(case_type=p['case_type'])
        archive_filter = p.get('archive_status')
        if archive_filter == 'sealed':
            qs = qs.filter(archive_versions__status='sealed').distinct()
        elif archive_filter == 'pending_review':
            qs = qs.filter(archive_versions__status='submitted').distinct()
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

    def _deny_if_sealed(self, case):
        if case.is_sealed:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(ARCHIVE_LOCKED_DETAIL)

    def perform_update(self, serializer):
        self._deny_if_sealed(self.get_object())
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        self._deny_if_sealed(instance)
        super().perform_destroy(instance)

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

    # ---------------- 结案归档 / 卷宗封存 ----------------
    @action(detail=True, methods=['get'], url_path='archive/prepare')
    def archive_prepare(self, request, pk=None):
        """整理卷宗：汇总当事人/律师/阶段/庭期/材料/期限，扫描未结事项，返回并发指纹"""
        case = self.get_object()
        return Response(archives.prepare_archive(case))

    @action(detail=True, methods=['post'], url_path='archive/submit')
    def archive_submit(self, request, pk=None):
        """整理完成后提交复核：逐项附处置说明，冻结提交时清单指纹"""
        case = self.get_object()
        try:
            version, stale = archives.submit_archive(case, request.data)
        except (archives.ArchiveError, archives.ArchiveConflict) as exc:
            return _archive_error_response(exc)
        return Response(ArchiveVersionSerializer(version).data
                        | {'stale_warnings': stale}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='archive/cancel')
    def archive_cancel(self, request, pk=None):
        """复核前撤回归档"""
        case = self.get_object()
        try:
            version = archives.cancel_submitted_archive(
                case, int(request.data.get('version_no') or 0))
        except archives.ArchiveError as exc:
            return _archive_error_response(exc)
        return Response(ArchiveVersionSerializer(version).data)

    @action(detail=True, methods=['post'], url_path='archive/confirm')
    def archive_confirm(self, request, pk=None):
        """复核人确认并封存：行锁内复核清单指纹，过期则 409 要求重新核对"""
        case = self.get_object()
        try:
            version = archives.confirm_archive(
                case, int(request.data.get('version_no') or 0),
                request.data.get('reviewer', ''),
                request.data.get('review_comment', ''))
        except (archives.ArchiveError, archives.ArchiveConflict) as exc:
            return _archive_error_response(exc)
        return Response(ArchiveVersionSerializer(version).data)

    @action(detail=True, methods=['post'], url_path='archive/reject')
    def archive_reject(self, request, pk=None):
        """复核退回：说明原因，整理人修改后重新提交（版本号不变）"""
        case = self.get_object()
        try:
            version = archives.reject_archive(
                case, int(request.data.get('version_no') or 0),
                request.data.get('reviewer', ''),
                request.data.get('reject_reason', ''))
        except archives.ArchiveError as exc:
            return _archive_error_response(exc)
        return Response(ArchiveVersionSerializer(version).data)

    @action(detail=True, methods=['post'], url_path='reopen')
    def reopen_apply(self, request, pk=None):
        """封存后再审/补充材料：申请重开，需审批并保留批准记录"""
        case = self.get_object()
        try:
            req = archives.apply_reopen(case, request.data)
        except archives.ArchiveError as exc:
            return _archive_error_response(exc)
        return Response(ReopenRequestSerializer(req).data,
                        status=status.HTTP_201_CREATED)


class CasePartyViewSet(SealedWriteGuardMixin, viewsets.ModelViewSet):
    serializer_class = CasePartySerializer

    def get_queryset(self):
        qs = CaseParty.objects.select_related('party', 'case')
        case_id = self.request.query_params.get('case')
        if case_id:
            qs = qs.filter(case_id=case_id)
        return qs


class CaseLawyerViewSet(SealedWriteGuardMixin, viewsets.ModelViewSet):
    serializer_class = CaseLawyerSerializer

    def get_queryset(self):
        qs = CaseLawyer.objects.select_related('lawyer', 'case')
        case_id = self.request.query_params.get('case')
        if case_id:
            qs = qs.filter(case_id=case_id)
        return qs


class HearingViewSet(SealedWriteGuardMixin, viewsets.ModelViewSet):
    serializer_class = HearingSerializer

    def get_queryset(self):
        qs = Hearing.objects.select_related('case')
        case_id = self.request.query_params.get('case')
        if case_id:
            qs = qs.filter(case_id=case_id)
        return qs


class StageLogViewSet(SealedWriteGuardMixin, viewsets.ModelViewSet):
    serializer_class = StageLogSerializer

    def get_queryset(self):
        qs = StageLog.objects.select_related('case')
        case_id = self.request.query_params.get('case')
        if case_id:
            qs = qs.filter(case_id=case_id)
        return qs


class MaterialViewSet(SealedWriteGuardMixin, viewsets.ModelViewSet):
    serializer_class = MaterialSerializer

    def get_queryset(self):
        qs = Material.objects.select_related('case')
        case_id = self.request.query_params.get('case')
        if case_id:
            qs = qs.filter(case_id=case_id)
        return qs


class DeadlineViewSet(SealedWriteGuardMixin, viewsets.ModelViewSet):
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


class ArchiveVersionViewSet(viewsets.ReadOnlyModelViewSet):
    """卷宗版本只读接口；封存快照不可经任何接口改写"""
    serializer_class = ArchiveVersionSerializer

    def get_queryset(self):
        qs = ArchiveVersion.objects.prefetch_related(
            'pending_items').select_related('case')
        case_id = self.request.query_params.get('case')
        if case_id:
            qs = qs.filter(case_id=case_id)
        return qs


class ReopenRequestViewSet(viewsets.ModelViewSet):
    """重开申请：可发起、可审批；申请记录本身不允许编辑或删除"""
    serializer_class = ReopenRequestSerializer
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        qs = ReopenRequest.objects.select_related('case', 'archive_version')
        params = self.request.query_params
        if params.get('case'):
            qs = qs.filter(case_id=params['case'])
        if params.get('status'):
            qs = qs.filter(status=params['status'])
        return qs

    def create(self, request, *args, **kwargs):
        case = get_object_or_404(Case, pk=request.data.get('case'))
        try:
            req = archives.apply_reopen(case, request.data)
        except archives.ArchiveError as exc:
            return _archive_error_response(exc)
        return Response(ReopenRequestSerializer(req).data,
                        status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        try:
            req = archives.decide_reopen(
                pk, request.data.get('approver', ''),
                request.data.get('approval_comment', ''), True,
                request.data.get('next_stage'))
        except archives.ArchiveError as exc:
            return _archive_error_response(exc)
        return Response(ReopenRequestSerializer(req).data)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        try:
            req = archives.decide_reopen(
                pk, request.data.get('approver', ''),
                request.data.get('approval_comment', ''), False)
        except archives.ArchiveError as exc:
            return _archive_error_response(exc)
        return Response(ReopenRequestSerializer(req).data)


@api_view(['GET'])
def dashboard(request):
    """工作台统计：案件概览、期限提醒、近期开庭、待复核卷宗"""
    today = date.today()
    soon = today + timedelta(days=30)
    cases = Case.objects.all()

    stage_stats = []
    counts = {row['stage']: row['n'] for row in cases.values('stage').annotate(n=Count('id'))}
    for key, label in Case.STAGE_CHOICES:
        stage_stats.append({'stage': key, 'stage_display': label,
                            'count': counts.get(key, 0)})

    sealed_ids = set(ArchiveVersion.objects.filter(
        status='sealed').values_list('case_id', flat=True))
    active_cases = cases.exclude(id__in=sealed_ids)

    hearings = Hearing.objects.filter(
        hearing_time__date__gte=today).exclude(case_id__in=sealed_ids)\
        .select_related('case').order_by('hearing_time')[:10]
    deadlines = Deadline.objects.filter(
        is_done=False, due_date__lte=soon).exclude(case_id__in=sealed_ids)\
        .select_related('case').order_by('due_date')[:20]

    pending_review = ArchiveVersion.objects.filter(
        status='submitted').select_related('case').order_by('submitted_at')
    pending_review_data = [{
        'id': v.id,
        'case_id': v.case_id,
        'case_number': v.case.case_number,
        'case_title': v.case.title,
        'version_no': v.version_no,
        'submitted_by': v.submitted_by,
        'submitted_at': v.submitted_at.strftime('%Y-%m-%d %H:%M') if v.submitted_at else '',
        'pending_count': v.pending_items.count(),
    } for v in pending_review]

    return Response({
        'case_total': cases.count(),
        'case_active': active_cases.count(),
        'party_total': Party.objects.count(),
        'lawyer_total': Lawyer.objects.count(),
        'deadline_overdue': Deadline.objects.filter(
            is_done=False, due_date__lt=today).exclude(case_id__in=sealed_ids).count(),
        'sealed_total': len(sealed_ids),
        'pending_review_total': len(pending_review_data),
        'pending_review': pending_review_data,
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
