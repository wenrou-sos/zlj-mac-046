from datetime import date, timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from .models import (Case, CaseLawyer, CaseParty, Deadline, Hearing, Lawyer,
                     Material, MaterialReview, MaterialSubmission,
                     MaterialVersion, Party, StageLog, SubmissionItem,
                     SubmissionReceipt)
from .serializers import (CaseDetailSerializer, CaseLawyerSerializer,
                          CaseListSerializer, CasePartySerializer,
                          CaseWriteSerializer, DeadlineSerializer,
                          HearingSerializer, LawyerSerializer,
                          MaterialReviewSerializer, MaterialSerializer,
                          MaterialSubmissionSerializer, MaterialVersionSerializer,
                          PartySerializer, StageLogSerializer,
                          SubmissionCreateSerializer, SubmissionReceiptSerializer)


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
            'material_submissions__items', 'materials__versions__reviews')
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


# ---------- 材料：主档 / 版本 / 审阅意见 ----------

class MaterialViewSet(viewsets.ModelViewSet):
    serializer_class = MaterialSerializer

    def get_queryset(self):
        qs = (Material.objects
              .select_related('case')
              .prefetch_related('versions__reviews'))
        case_id = self.request.query_params.get('case')
        if case_id:
            qs = qs.filter(case_id=case_id)
        return qs

    def perform_destroy(self, instance):
        # 已提交批次引用过的材料一律不得删除（版本同样受 PROTECT 保护）
        if SubmissionItem.objects.filter(version__material=instance).exists():
            raise PermissionDenied('该材料已有提交记录，历史材料不可删除，可继续查看')
        super().perform_destroy(instance)


class MaterialVersionViewSet(viewsets.ModelViewSet):
    """材料版本：仅允许新增与查看；不允许修改、不允许删除"""
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ['get', 'post', 'head', 'options']
    serializer_class = MaterialVersionSerializer

    def get_queryset(self):
        qs = MaterialVersion.objects.select_related('material', 'material__case')
        params = self.request.query_params
        if params.get('material'):
            qs = qs.filter(material_id=params['material'])
        if params.get('case'):
            qs = qs.filter(material__case_id=params['case'])
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            version = serializer.save()
        except PermissionDenied:
            raise
        except Exception:
            # 并发等任何失败都不得留下附件记录（序列化器内已清理孤儿文件）
            return Response(
                {'detail': '版本保存失败（可能与他人同时上传冲突），请重试'},
                status=status.HTTP_409_CONFLICT)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED,
                        headers=headers)

    @action(detail=True, methods=['post'])
    def finalize(self, request, pk=None):
        """定稿确认：固定版本；他人若已定稿另一版本则互斥拒绝"""
        operator = (request.data.get('operator') or '').strip()
        if not operator:
            return Response({'detail': '请填写定稿确认人'},
                            status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            version = (MaterialVersion.objects
                       .select_for_update()
                       .select_related('material')
                       .get(pk=pk))
            material = (Material.objects
                        .select_for_update()
                        .get(pk=version.material_id))
            if version.is_final:
                return Response({'detail': '该版本已是定稿版本'},
                                status=status.HTTP_400_BAD_REQUEST)
            if not version.file:
                return Response(
                    {'detail': '该版本缺少附件（历史补录件），请先补传文件版本再定稿'},
                    status=status.HTTP_400_BAD_REQUEST)
            if version.submission_items.exists():
                return Response(
                    {'detail': '该版本已随批次提交，已提交版本不得再改定稿状态'},
                    status=status.HTTP_400_BAD_REQUEST)
            others = (MaterialVersion.objects
                      .filter(material=material, is_final=True)
                      .order_by('-version_no'))
            blocking = None
            for other in others:
                # 已随「未退回」批次提交的定稿受保护；
                # 仅存在于已退回批次中的定稿可被补正版取代（用于重新提交）
                active = other.submission_items.exclude(
                    submission__status='returned').exists()
                if active:
                    blocking = other
                    break
            if blocking is not None:
                return Response(
                    {'detail': f'定稿 v{blocking.version_no} 已提交，'
                               f'已提交版本不得被替换；如需修改请先经退回补正流程'},
                    status=status.HTTP_409_CONFLICT)
            # 其余旧定稿（含已退回批次中的定稿）标记取消，定稿前移到本版本
            others.update(is_final=False, finalized_by='', finalized_at=None)
            version.is_final = True
            version.finalized_by = operator
            version.finalized_at = timezone.now()
            version.save(update_fields=['is_final', 'finalized_by', 'finalized_at'])
            if material.status in ('draft', 'finalized', 'returned'):
                material.status = 'finalized'
                material.save(update_fields=['status'])

        return Response(MaterialVersionSerializer(version, context={'request': request}).data)


class MaterialReviewViewSet(viewsets.ModelViewSet):
    """审阅意见：只追加，不允许修改、不允许删除"""
    http_method_names = ['get', 'post', 'head', 'options']
    serializer_class = MaterialReviewSerializer

    def get_queryset(self):
        qs = MaterialReview.objects.select_related('version', 'version__material')
        params = self.request.query_params
        if params.get('version'):
            qs = qs.filter(version_id=params['version'])
        if params.get('material'):
            qs = qs.filter(version__material_id=params['material'])
        return qs

    def perform_create(self, serializer):
        # 已提交版本的审阅意见只可作为留痕补充，不影响其固定性
        serializer.save()


# ---------- 提交批次 / 回执 ----------

class MaterialSubmissionViewSet(viewsets.ModelViewSet):
    """提交批次：新建时固定清单与版本快照；批次本身不允许编辑/删除"""
    http_method_names = ['get', 'post', 'head', 'options']
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        qs = (MaterialSubmission.objects
              .prefetch_related('items', 'receipts'))
        case_id = self.request.query_params.get('case')
        if case_id:
            qs = qs.filter(case_id=case_id)
        return qs

    def get_serializer_class(self):
        if self.action == 'create':
            return SubmissionCreateSerializer
        return MaterialSubmissionSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        submission = serializer.save()
        out = MaterialSubmissionSerializer(submission, context={'request': request})
        return Response(out.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def resubmissions(self, request, pk=None):
        submission = self.get_object()
        qs = submission.resubmissions.all()
        data = MaterialSubmissionSerializer(qs, many=True, context={'request': request}).data
        return Response(data)


class SubmissionReceiptViewSet(viewsets.ModelViewSet):
    """签收 / 退回补正回执：只追加；不允许修改/删除"""
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ['get', 'post', 'head', 'options']
    serializer_class = SubmissionReceiptSerializer

    def get_queryset(self):
        qs = SubmissionReceipt.objects.select_related('submission')
        params = self.request.query_params
        if params.get('submission'):
            qs = qs.filter(submission_id=params['submission'])
        if params.get('case'):
            qs = qs.filter(submission__case_id=params['case'])
        return qs

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except Exception as exc:
            if getattr(exc, 'status_code', None):
                raise
            return Response({'detail': '回执保存失败，请重试'},
                            status=status.HTTP_409_CONFLICT)


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
    """工作台统计：案件概览、期限提醒、近期开庭"""
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
        is_done=False, due_date__lte=soon).select_related('case').order_by('due_date')[:20]

    return Response({
        'case_total': cases.count(),
        'case_active': cases.exclude(stage='closed').count(),
        'party_total': Party.objects.count(),
        'lawyer_total': Lawyer.objects.count(),
        'deadline_overdue': Deadline.objects.filter(is_done=False, due_date__lt=today).count(),
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
