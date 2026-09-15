from datetime import date, timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from . import conflicts as conflict_engine
from .access import (ValidationCodeError, current_lawyer,
                     require_reviewer)
from .models import (Case, CaseLawyer, CaseParty, ConflictReview,
                     ConflictReviewLog, ConflictReviewMaterial, Deadline,
                     Hearing, Lawyer, Material, Party, StageLog)
from .serializers import (CaseDetailSerializer, CaseLawyerSerializer,
                          CaseListSerializer, CasePartySerializer,
                          CaseWriteSerializer, ConflictDecisionSerializer,
                          ConflictReviewCreateSerializer,
                          ConflictReviewMaterialSerializer,
                          ConflictReviewSerializer, DeadlineSerializer,
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
        """向本案添加当事人前的利益冲突预检（即时只读，不留痕）。

        POST /api/cases/{id}/conflict-check/  {party_id, is_client, role?}
        """
        case = self.get_object()
        party = get_object_or_404(Party, pk=request.data.get('party_id'))
        is_client = bool(request.data.get('is_client'))
        proposed_role = request.data.get('role') or 'plaintiff'

        result = conflict_engine.evaluate_conflict(party, case, proposed_role, is_client)
        conflicts = [{
            'level': f['level'],
            'code': f['code'],
            'prohibited': f['prohibited'],
            'message': f['message'],
        } for f in result['findings']]
        return Response({
            'has_conflict': result['has_prohibited'],
            'risk_level': result['risk_level'],
            'needs_exception': result['needs_exception'],
            'conflicts': conflicts,
        })


class CasePartyViewSet(viewsets.ModelViewSet):
    serializer_class = CasePartySerializer

    def get_queryset(self):
        qs = CaseParty.objects.select_related('party', 'case')
        case_id = self.request.query_params.get('case')
        if case_id:
            qs = qs.filter(case_id=case_id)
        return qs

    def create(self, request, *args, **kwargs):
        """承接闸门：添加当事人到案件，必须持有当前仍有效的批准复核单。

        凭复核单编号 ``review_number``（或 review_id）承接；承接时核对
        批准结论是否仍有效（未被使用、例外未到期、风险指纹未变化）。
        """
        case = get_object_or_404(Case, pk=request.data.get('case'))
        party = get_object_or_404(Party, pk=request.data.get('party_id'))
        role = request.data.get('role')
        is_client = str(request.data.get('is_client', False)).lower() in ('true', '1', 'yes')
        lawyer = current_lawyer(request)

        review = self._resolve_review(request.data, case, party)
        self._ensure_review_valid(review, party, case, role, is_client)

        response = super().create(request, *args, **kwargs)

        review.used_at = timezone.now()
        review.used_by = lawyer
        review.save(update_fields=['used_at', 'used_by', 'updated_at'])
        ConflictReviewLog.objects.create(
            review=review, action='use', actor=lawyer,
            actor_name=lawyer.name,
            detail=f'凭批准结论承接：{party.name} 列为案件「{case.title}」'
                   f'{review.get_proposed_role_display()}，承接人 {lawyer.name}')
        return response

    @staticmethod
    def _resolve_review(data, case, party):
        review = None
        number = (data.get('review_number') or '').strip()
        review_id = data.get('review_id')
        if number:
            review = ConflictReview.objects.filter(review_number=number).first()
        elif review_id:
            review = ConflictReview.objects.filter(pk=review_id).first()
        if not review:
            raise ValidationCodeError(
                '承接前须先完成利益冲突复核并取得批准结论，请在复核单列表中发起申请')
        if review.case_id != case.id or review.party_id != party.id:
            raise ValidationCodeError('复核单与当前承接的案件或当事人不一致')
        return review

    @staticmethod
    def _ensure_review_valid(review, party, case, role, is_client):
        if review.status != 'approved':
            raise ValidationCodeError(
                f'复核单 {review.review_number} 当前状态为「{review.get_status_display()}」，'
                f'未获批准，不得承接')
        if review.used_at is not None:
            raise ValidationCodeError(
                f'复核单 {review.review_number} 的批准结论已用于承接，不能重复使用，'
                f'如关系变更请重新发起复核')
        if (review.exception_expire_date
                and review.exception_expire_date < timezone.localdate()):
            raise ValidationCodeError(
                f'复核单 {review.review_number} 的例外授权适用期限已于 '
                f'{review.exception_expire_date} 届满，须重新复核')
        fresh_fp = conflict_engine.relationship_fingerprint(
            party, case, review.proposed_role, review.proposed_is_client)
        if fresh_fp != review.relationship_fingerprint:
            raise ValidationCodeError(
                f'复核单 {review.review_number} 作出后相关涉案关系已变更，'
                f'原批准结论失效，请重新发起冲突复核')
        if role and role != review.proposed_role:
            raise ValidationCodeError('拟列诉讼地位与批准复核单不一致，须重新复核')
        if is_client != review.proposed_is_client:
            raise ValidationCodeError('客户身份认定与批准复核单不一致，须重新复核')


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
    return conflict_engine.party_involvements(party)


@api_view(['GET'])
def conflict_check(request):
    """利益冲突检查：按姓名/名称或证件号检索当事人的全部涉诉记录（只读检索）"""
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
                                f"代理与其利益相对方构成《律师法》第三十九条禁止的直接利益冲突")
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


class ConflictReviewViewSet(viewsets.ReadOnlyModelViewSet):
    """利益冲突复核单。

    读操作：列表 / 详情 / 筛选；写操作通过自定义动作完成，便于强制
    身份校验与业务规则（申请、补材料、审批、重新复核）。
    """

    def get_queryset(self):
        qs = ConflictReview.objects.select_related(
            'case', 'party', 'applicant', 'reviewer', 'superseded_by')
        p = self.request.query_params
        for key in ('status', 'risk_level'):
            if p.get(key):
                qs = qs.filter(**{key: p[key]})
        if p.get('case'):
            qs = qs.filter(case_id=p['case'])
        if p.get('party'):
            qs = qs.filter(party_id=p['party'])
        scope = p.get('scope')
        lawyer = current_lawyer(self.request, required=False)
        if scope == 'mine_apply' and lawyer:
            qs = qs.filter(applicant=lawyer)
        elif scope == 'mine_review' and lawyer:
            qs = qs.filter(reviewer=lawyer, status='pending')
        elif scope == 'todo' and lawyer:
            qs = qs.filter(reviewer=lawyer)
        return qs

    def get_serializer_class(self):
        return ConflictReviewSerializer

    @action(detail=False, methods=['post'], url_path='apply')
    def apply(self, request):
        """发起冲突复核申请：冻结身份/关系/风险快照并留痕。"""
        lawyer = current_lawyer(request)
        ser = ConflictReviewCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        case, party = data['case'], data['party']
        role, is_client = data['proposed_role'], data['proposed_is_client']
        reviewer = data.get('reviewer')
        prior = data.get('prior_review')

        if CaseParty.objects.filter(case=case, party=party).exists():
            raise ValidationCodeError('该当事人已在本案中，无需重复发起承接复核')
        if reviewer is None:
            raise ValidationCodeError('请指定复核人')
        if reviewer.id == lawyer.id:
            raise PermissionDenied('申请人不能同时担任本复核单的复核人')
        if ConflictReview.objects.filter(
                case=case, party=party, status='pending').exists():
            raise ValidationCodeError('该当事人在本案的复核申请已有待复核单，请勿重复提交')

        with transaction.atomic():
            review = ConflictReview.objects.create(
                case=case, party=party, proposed_role=role,
                proposed_is_client=is_client, applicant=lawyer, reviewer=reviewer,
                apply_remark=data.get('apply_remark', ''),
                snapshot=conflict_engine.build_snapshot(party, case, role, is_client),
                relationship_fingerprint=conflict_engine.relationship_fingerprint(
                    party, case, role, is_client))
            review.risk_level = review.snapshot['risk_level']
            review.has_prohibited = review.snapshot['has_prohibited']
            review.needs_exception = review.snapshot['needs_exception']
            review.save(update_fields=['risk_level', 'has_prohibited',
                                       'needs_exception'])
            for m in data.get('materials', []):
                ConflictReviewMaterial.objects.create(review=review, uploaded_by=lawyer, **m)
            detail = f'{lawyer.name} 提交复核申请，指定复核人 {reviewer.name}'
            if review.has_prohibited:
                detail += '；系统检出本所禁止性冲突，按规定不得批准'
            elif review.needs_exception:
                detail += '；检出需例外授权的冲突，批准时须登记授权依据与适用期限'
            if prior:
                detail += f'；基于原复核单 {prior.review_number}（{prior.get_status_display()}）发起'
            ConflictReviewLog.objects.create(
                review=review, action='apply', actor=lawyer,
                actor_name=lawyer.name, detail=detail)
        return Response(ConflictReviewSerializer(review).data,
                        status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='supplement')
    def supplement(self, request, pk=None):
        """退回后由申请人补充材料。"""
        review = self.get_object()
        lawyer = current_lawyer(request)
        if review.applicant_id != lawyer.id:
            raise PermissionDenied('只有申请人可以补充材料')
        if review.status != 'returned':
            raise ValidationCodeError('仅"退回补充材料"状态的复核单可以补充材料')
        materials = request.data.get('materials')
        if not materials or not any((m.get('name') for m in materials)):
            raise ValidationCodeError('请至少补充一份有效材料（填写材料名称）')
        names = []
        with transaction.atomic():
            for m in materials:
                if not m.get('name'):
                    continue
                ConflictReviewMaterial.objects.create(
                    review=review, uploaded_by=lawyer, name=m['name'],
                    material_type=m.get('material_type', ''),
                    source=m.get('source', ''), remark=m.get('remark', ''))
                names.append(m['name'])
            review.status = 'pending'
            review.save(update_fields=['status', 'updated_at'])
            ConflictReviewLog.objects.create(
                review=review, action='supplement', actor=lawyer,
                actor_name=lawyer.name,
                detail='补充材料：' + '、'.join(names) + '；复核单重新进入待复核')
        return Response(ConflictReviewSerializer(review).data)

    @action(detail=True, methods=['post'], url_path='decide')
    def decide(self, request, pk=None):
        """指定复核人作出 批准 / 拒绝 / 退回补充材料 决定。"""
        review = self.get_object()
        lawyer = current_lawyer(request)
        require_reviewer(review, lawyer)
        if review.status != 'pending':
            raise ValidationCodeError(f'复核单当前为「{review.get_status_display()}」，不能再审批')

        ser = ConflictDecisionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        decision, remark = d['decision'], d.get('decision_remark', '')

        with transaction.atomic():
            now = timezone.now()
            if decision == 'approve':
                # 以当前数据复评：本所明确禁止的冲突不得批准
                fresh = conflict_engine.evaluate_conflict(
                    review.party, review.case, review.proposed_role,
                    review.proposed_is_client)
                if fresh['has_prohibited']:
                    raise PermissionDenied(
                        '该承接关系含本所明确禁止的利益冲突，按规定不得批准，'
                        '也不适用例外授权；请作出拒绝决定')
                basis = d.get('exception_basis', '').strip()
                expire = d.get('exception_expire_date')
                if fresh['needs_exception']:
                    if not basis:
                        raise ValidationCodeError(
                            '该冲突属可有条件豁免情形，批准必须填写例外授权依据')
                    if not expire:
                        raise ValidationCodeError(
                            '允许例外的承接必须登记适用期限')
                    if expire < timezone.localdate():
                        raise ValidationCodeError('例外适用期限不能早于今天')
                review.exception_basis = basis
                review.exception_expire_date = expire if fresh['needs_exception'] else None
                review.status = 'approved'
                action_detail = '批准承接'
                if fresh['needs_exception']:
                    action_detail += (f'（例外授权，依据：{basis}；'
                                      f'适用期限至 {review.exception_expire_date}）')
            elif decision == 'reject':
                review.status = 'rejected'
                action_detail = '拒绝承接'
            else:
                review.status = 'returned'
                action_detail = '退回申请人补充材料'

            review.decision_remark = remark
            review.decided_at = now
            review.save()
            ConflictReviewLog.objects.create(
                review=review, action=decision, actor=lawyer,
                actor_name=lawyer.name,
                detail=(action_detail + (f'。复核意见：{remark}' if remark else '')))
        return Response(ConflictReviewSerializer(review).data)

    @action(detail=True, methods=['post'], url_path='recheck')
    def recheck(self, request, pk=None):
        """关系变更后基于旧单发起重新复核；旧单作废并保留全部历史。"""
        prior = self.get_object()
        lawyer = current_lawyer(request)
        if prior.applicant_id != lawyer.id:
            raise PermissionDenied('仅原申请人可以基于该复核单发起重新复核')
        if prior.status in ('rejected', 'returned'):
            raise ValidationCodeError(
                f'原单为「{prior.get_status_display()}」状态，请使用补充材料或重新申请，'
                f'而非重新复核')
        if prior.status == 'pending':
            raise ValidationCodeError('原单尚在待复核，无需重新复核')

        reviewer_id = request.data.get('reviewer')
        reviewer = get_object_or_404(Lawyer, pk=reviewer_id) if reviewer_id else prior.reviewer
        if reviewer.id == lawyer.id:
            raise PermissionDenied('申请人不能同时担任本复核单的复核人')
        apply_remark = request.data.get('apply_remark', '')
        materials = request.data.get('materials') or []

        case, party = prior.case, prior.party
        with transaction.atomic():
            review = ConflictReview.objects.create(
                case=case, party=party,
                proposed_role=prior.proposed_role,
                proposed_is_client=prior.proposed_is_client,
                applicant=lawyer, reviewer=reviewer,
                apply_remark=apply_remark or f'因相关涉案关系变更，基于 {prior.review_number} 重新复核',
                snapshot=conflict_engine.build_snapshot(
                    party, case, prior.proposed_role, prior.proposed_is_client),
                relationship_fingerprint=conflict_engine.relationship_fingerprint(
                    party, case, prior.proposed_role, prior.proposed_is_client))
            review.risk_level = review.snapshot['risk_level']
            review.has_prohibited = review.snapshot['has_prohibited']
            review.needs_exception = review.snapshot['needs_exception']
            review.save(update_fields=['risk_level', 'has_prohibited', 'needs_exception'])
            for m in materials:
                if m.get('name'):
                    ConflictReviewMaterial.objects.create(
                        review=review, uploaded_by=lawyer, name=m['name'],
                        material_type=m.get('material_type', ''),
                        source=m.get('source', ''), remark=m.get('remark', ''))
            prior.status = 'superseded'
            prior.superseded_by = review
            prior.save(update_fields=['status', 'superseded_by', 'updated_at'])
            ConflictReviewLog.objects.create(
                review=prior, action='supersede', actor=lawyer,
                actor_name=lawyer.name,
                detail=f'相关涉案关系变更，原结论失效，由复核单 {review.review_number} 接续重新复核')
            ConflictReviewLog.objects.create(
                review=review, action='apply', actor=lawyer,
                actor_name=lawyer.name,
                detail=f'{lawyer.name} 基于原复核单 {prior.review_number} 发起重新复核，'
                       f'原风险等级 {prior.risk_level}，现风险等级 {review.risk_level}'
                       + ('；系统检出禁止性冲突，不得批准' if review.has_prohibited else ''))
        return Response(ConflictReviewSerializer(review).data,
                        status=status.HTTP_201_CREATED)
