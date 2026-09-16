from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from .models import (Bill, Case, CaseLawyer, CaseParty, CaseRate, Deadline,
                     Expense, FeeAgreement, Hearing, Lawyer, Material, Party,
                     Payment, StageLog, TimeEntry)
from .serializers import (BillCreateSerializer, BillSerializer,
                          CaseDetailSerializer, CaseLawyerSerializer,
                          CaseListSerializer, CasePartySerializer,
                          CaseRateSerializer, CaseWriteSerializer,
                          DeadlineSerializer, ExpenseSerializer,
                          FeeAgreementSerializer, HearingSerializer,
                          LawyerSerializer, MaterialSerializer, PartySerializer,
                          PaymentSerializer, StageLogSerializer,
                          TimeEntrySerializer)


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

    @action(detail=True, methods=['get'])
    def finance(self, request, pk=None):
        """案件财务全景：收费约定、费率、工时、费用、账单及应收/已收/未收汇总"""
        case = self.get_object()
        bills = case.bills.prefetch_related('lines', 'payments')
        active = [b for b in bills if b.status != 'void']
        entries = case.time_entries.select_related('lawyer', 'bill_line__bill')
        expenses = case.expenses.select_related('lawyer', 'bill_line__bill')

        zero = Decimal('0')

        def money(value):
            return str(value.quantize(Decimal('0.01')))

        summary = {
            'billed_total': money(sum((b.total_amount for b in active), zero)),
            'reduction_total': money(sum((b.reduction_amount for b in active), zero)),
            'received_total': money(sum((b.received_amount for b in active), zero)),
            'outstanding_total': money(sum((b.outstanding for b in active), zero)),
            'unbilled_time_amount': money(sum(
                (e.amount for e in entries
                 if e.status == 'approved' and e.amount is not None), zero)),
            'unbilled_expense_amount': money(sum(
                (e.amount for e in expenses if e.status == 'approved'), zero)),
            'pending_time_count': entries.filter(status='pending').count(),
            'pending_expense_count': expenses.filter(status='pending').count(),
        }
        agreement = getattr(case, 'fee_agreement', None)
        return Response({
            'agreement': FeeAgreementSerializer(agreement).data if agreement else None,
            'rates': CaseRateSerializer(case.case_rates.all(), many=True).data,
            'time_entries': TimeEntrySerializer(entries, many=True).data,
            'expenses': ExpenseSerializer(expenses, many=True).data,
            'bills': BillSerializer(bills, many=True).data,
            'summary': summary,
        })


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


# ---------------------------------------------------------------- 费用与账单

class FeeAgreementViewSet(viewsets.ModelViewSet):
    """案件收费约定（固定收费/按工时收费，一案一份）"""
    serializer_class = FeeAgreementSerializer

    def get_queryset(self):
        qs = FeeAgreement.objects.select_related('case')
        case_id = self.request.query_params.get('case')
        if case_id:
            qs = qs.filter(case_id=case_id)
        return qs


class CaseRateViewSet(viewsets.ModelViewSet):
    """计时费率：按生效日期记录，变更仅影响生效日之后提交的工时"""
    serializer_class = CaseRateSerializer

    def get_queryset(self):
        qs = CaseRate.objects.select_related('case', 'lawyer')
        case_id = self.request.query_params.get('case')
        if case_id:
            qs = qs.filter(case_id=case_id)
        return qs


def _approve_or_reject(instance, approve):
    if approve and instance.status != 'pending':
        return Response({'detail': '仅待核准记录可以核准'},
                        status=status.HTTP_400_BAD_REQUEST)
    if not approve and instance.status != 'approved':
        return Response({'detail': '仅已核准记录可以退回'},
                        status=status.HTTP_400_BAD_REQUEST)
    instance.status = 'approved' if approve else 'pending'
    instance.approved_at = timezone.now() if approve else None
    instance.save(update_fields=['status', 'approved_at'])
    return None


class ApproveFlowMixin:
    """核准/退回/删除保护（工时与代垫费用共用）"""

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        obj = self.get_object()
        resp = _approve_or_reject(obj, approve=True)
        return resp or Response(self.get_serializer(obj).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        obj = self.get_object()
        resp = _approve_or_reject(obj, approve=False)
        return resp or Response(self.get_serializer(obj).data)

    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.status != 'pending':
            return Response({'detail': '仅待核准记录可以删除'},
                            status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)


class TimeEntryViewSet(ApproveFlowMixin, viewsets.ModelViewSet):
    serializer_class = TimeEntrySerializer

    def get_queryset(self):
        qs = TimeEntry.objects.select_related('case', 'lawyer', 'bill_line__bill')
        p = self.request.query_params
        if p.get('case'):
            qs = qs.filter(case_id=p['case'])
        if p.get('status'):
            qs = qs.filter(status=p['status'])
        return qs


class ExpenseViewSet(ApproveFlowMixin, viewsets.ModelViewSet):
    serializer_class = ExpenseSerializer

    def get_queryset(self):
        qs = Expense.objects.select_related('case', 'lawyer', 'bill_line__bill')
        p = self.request.query_params
        if p.get('case'):
            qs = qs.filter(case_id=p['case'])
        if p.get('status'):
            qs = qs.filter(status=p['status'])
        return qs


class BillViewSet(viewsets.ModelViewSet):
    """分期账单：生成、收款、减免、冲正；已收款账单不能直接删除"""
    http_method_names = ['get', 'post', 'delete', 'head', 'options']

    def get_queryset(self):
        qs = (Bill.objects.select_related('case')
              .prefetch_related('lines', 'payments'))
        case_id = self.request.query_params.get('case')
        if case_id:
            qs = qs.filter(case_id=case_id)
        return qs

    def get_serializer_class(self):
        if self.action == 'create':
            return BillCreateSerializer
        return BillSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        bill = serializer.save()
        return Response(BillSerializer(bill).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        bill = self.get_object()
        if bill.status == 'void':
            return Response({'detail': '已冲正账单不能删除'},
                            status=status.HTTP_400_BAD_REQUEST)
        if bill.payments.exists():
            return Response({'detail': '已收款账单不能直接删除，如需作废请使用冲正'},
                            status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            self._release_lines(bill)
            bill.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @staticmethod
    def _release_lines(bill):
        """释放账单占用的工时/费用（明细行保留当时计价快照，仅断开关联）"""
        for line in bill.lines.all():
            if line.time_entry:
                entry = line.time_entry
                line.time_entry = None
                entry.status = 'approved'
                entry.save(update_fields=['status'])
                line.save(update_fields=['time_entry'])
            if line.expense:
                expense = line.expense
                line.expense = None
                expense.status = 'approved'
                expense.save(update_fields=['status'])
                line.save(update_fields=['expense'])

    @action(detail=True, methods=['post'])
    def reduction(self, request, pk=None):
        """费用减免：设置减免金额（绝对值），需说明原因"""
        bill = self.get_object()
        if bill.status == 'void':
            return Response({'detail': '账单已冲正'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            amount = Decimal(str(request.data.get('amount', '0')))
        except InvalidOperation:
            return Response({'detail': '减免金额格式不正确'},
                            status=status.HTTP_400_BAD_REQUEST)
        reason = request.data.get('reason', '').strip()
        if amount < 0:
            return Response({'detail': '减免金额不能为负'},
                            status=status.HTTP_400_BAD_REQUEST)
        if amount > 0 and not reason:
            return Response({'detail': '请填写减免原因'},
                            status=status.HTTP_400_BAD_REQUEST)
        if bill.received_amount + amount > bill.total_amount:
            return Response(
                {'detail': f'减免后应收不能低于已收款 ¥{bill.received_amount}'},
                status=status.HTTP_400_BAD_REQUEST)
        bill.reduction_amount = amount
        bill.reduction_reason = reason
        bill.save(update_fields=['reduction_amount', 'reduction_reason'])
        bill.refresh_status()
        return Response(BillSerializer(bill).data)

    @action(detail=True, methods=['post'])
    def void(self, request, pk=None):
        """冲正：账单作废，已收款自动生成负数退款记录，工时/费用释放回已核准"""
        bill = self.get_object()
        if bill.status == 'void':
            return Response({'detail': '账单已冲正'}, status=status.HTTP_400_BAD_REQUEST)
        reason = request.data.get('reason', '').strip()
        if not reason:
            return Response({'detail': '请填写冲正原因'},
                            status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            received = bill.received_amount
            if received > 0:
                Payment.objects.create(
                    bill=bill, amount=-received, received_date=date.today(),
                    method='other', is_reversal=True,
                    notes='账单冲正，退回已收款项')
            self._release_lines(bill)
            bill.status = 'void'
            bill.void_reason = reason
            bill.voided_at = timezone.now()
            bill.save(update_fields=['status', 'void_reason', 'voided_at'])
        bill.refresh_from_db()  # 清除预取缓存，确保响应含新生成的退款记录
        return Response(BillSerializer(bill).data)


class PaymentViewSet(viewsets.ModelViewSet):
    """收款记录：支持部分收款；删除收款会回写账单状态"""
    serializer_class = PaymentSerializer
    http_method_names = ['get', 'post', 'delete', 'head', 'options']

    def get_queryset(self):
        qs = Payment.objects.select_related('bill')
        bill_id = self.request.query_params.get('bill')
        if bill_id:
            qs = qs.filter(bill_id=bill_id)
        return qs

    def destroy(self, request, *args, **kwargs):
        payment = self.get_object()
        if payment.bill.status == 'void':
            return Response({'detail': '账单已冲正，收款记录不能删除'},
                            status=status.HTTP_400_BAD_REQUEST)
        if payment.is_reversal:
            return Response({'detail': '冲正退款记录不能删除'},
                            status=status.HTTP_400_BAD_REQUEST)
        bill = payment.bill
        response = super().destroy(request, *args, **kwargs)
        bill.refresh_status()
        return response


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
