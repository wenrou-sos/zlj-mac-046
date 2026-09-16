from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from .models import (Bill, BillLine, Case, CaseLawyer, CaseParty, CaseRate,
                     Deadline, Expense, FeeAgreement, Hearing, Lawyer,
                     Material, Party, Payment, StageLog, TimeEntry)


class LawyerSerializer(serializers.ModelSerializer):
    title_display = serializers.CharField(source='get_title_display', read_only=True)
    case_count = serializers.SerializerMethodField()

    class Meta:
        model = Lawyer
        fields = '__all__'

    def get_case_count(self, obj):
        return obj.cases.exclude(stage='closed').count()


class PartySerializer(serializers.ModelSerializer):
    party_type_display = serializers.CharField(source='get_party_type_display', read_only=True)
    case_count = serializers.SerializerMethodField()

    class Meta:
        model = Party
        fields = '__all__'

    def get_case_count(self, obj):
        return obj.cases.count()


class CasePartySerializer(serializers.ModelSerializer):
    party = PartySerializer(read_only=True)
    party_id = serializers.PrimaryKeyRelatedField(
        queryset=Party.objects.all(), source='party', write_only=True)
    case = serializers.PrimaryKeyRelatedField(queryset=Case.objects.all())
    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = CaseParty
        fields = ['id', 'case', 'party', 'party_id', 'role', 'role_display', 'is_client']



    def validate(self, attrs):
        qs = CaseParty.objects.filter(
            case=attrs['case'], party=attrs['party'], role=attrs['role'])
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {'party_id': '该当事人已以此诉讼地位存在于本案中'})
        return attrs


class CaseLawyerSerializer(serializers.ModelSerializer):
    lawyer = LawyerSerializer(read_only=True)
    lawyer_id = serializers.PrimaryKeyRelatedField(
        queryset=Lawyer.objects.all(), source='lawyer', write_only=True)
    case = serializers.PrimaryKeyRelatedField(queryset=Case.objects.all())
    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = CaseLawyer
        fields = ['id', 'case', 'lawyer', 'lawyer_id', 'role', 'role_display']

    def validate(self, attrs):
        qs = CaseLawyer.objects.filter(case=attrs['case'], lawyer=attrs['lawyer'])
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError({'lawyer_id': '该律师已承办本案'})
        return attrs


class HearingSerializer(serializers.ModelSerializer):
    case_title = serializers.CharField(source='case.title', read_only=True)
    case_number = serializers.CharField(source='case.case_number', read_only=True)

    class Meta:
        model = Hearing
        fields = '__all__'


class StageLogSerializer(serializers.ModelSerializer):
    stage_display = serializers.CharField(source='get_stage_display', read_only=True)

    class Meta:
        model = StageLog
        fields = '__all__'


class MaterialSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Material
        fields = '__all__'


class DeadlineSerializer(serializers.ModelSerializer):
    deadline_type_display = serializers.CharField(source='get_deadline_type_display', read_only=True)
    case_title = serializers.CharField(source='case.title', read_only=True)
    case_number = serializers.CharField(source='case.case_number', read_only=True)
    days_left = serializers.SerializerMethodField()

    class Meta:
        model = Deadline
        fields = '__all__'

    def get_days_left(self, obj):
        return (obj.due_date - date.today()).days


class CaseListSerializer(serializers.ModelSerializer):
    stage_display = serializers.CharField(source='get_stage_display', read_only=True)
    case_type_display = serializers.CharField(source='get_case_type_display', read_only=True)
    case_lawyers = CaseLawyerSerializer(source='caselawyer_set', many=True, read_only=True)
    case_parties = CasePartySerializer(source='caseparty_set', many=True, read_only=True)
    pending_deadline_count = serializers.SerializerMethodField()

    class Meta:
        model = Case
        fields = ['id', 'case_number', 'title', 'case_type', 'case_type_display',
                  'stage', 'stage_display', 'cause', 'court', 'filed_date',
                  'amount', 'case_lawyers', 'case_parties',
                  'pending_deadline_count', 'created_at']

    def get_pending_deadline_count(self, obj):
        return obj.deadlines.filter(is_done=False).count()


class CaseDetailSerializer(CaseListSerializer):
    hearings = HearingSerializer(many=True, read_only=True)
    stage_logs = StageLogSerializer(many=True, read_only=True)
    materials = MaterialSerializer(many=True, read_only=True)
    deadlines = DeadlineSerializer(many=True, read_only=True)

    class Meta(CaseListSerializer.Meta):
        fields = CaseListSerializer.Meta.fields + [
            'description', 'hearings', 'stage_logs', 'materials', 'deadlines']


class CaseWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Case
        fields = ['id', 'case_number', 'title', 'case_type', 'stage', 'cause',
                  'court', 'filed_date', 'amount', 'description']


# ---------------------------------------------------------------- 费用与账单

class FeeAgreementSerializer(serializers.ModelSerializer):
    fee_type_display = serializers.CharField(source='get_fee_type_display',
                                             read_only=True)

    class Meta:
        model = FeeAgreement
        fields = ['id', 'case', 'fee_type', 'fee_type_display', 'fixed_amount',
                  'notes', 'created_at']

    def validate(self, attrs):
        fee_type = attrs.get('fee_type', getattr(self.instance, 'fee_type', None))
        fixed_amount = attrs.get('fixed_amount',
                                 getattr(self.instance, 'fixed_amount', None))
        if fee_type == 'fixed' and not fixed_amount:
            raise serializers.ValidationError({'fixed_amount': '固定收费须填写收费总额'})
        if fee_type == 'hourly':
            attrs['fixed_amount'] = None
        # 约定总额不得调低到低于已出账的固定期款
        if fee_type == 'fixed' and self.instance:
            billed = sum(
                (line.amount for line in BillLine.objects.filter(
                    bill__case=self.instance.case, line_type='fixed')
                 .exclude(bill__status='void')), Decimal('0'))
            if fixed_amount < billed:
                raise serializers.ValidationError(
                    {'fixed_amount': f'已出账固定期款 ¥{billed}，约定总额不能低于该金额'})
        return attrs


class CaseRateSerializer(serializers.ModelSerializer):
    lawyer_name = serializers.CharField(source='lawyer.name', read_only=True)

    class Meta:
        model = CaseRate
        fields = ['id', 'case', 'lawyer', 'lawyer_name', 'hourly_rate',
                  'effective_date', 'created_at']

    def validate_hourly_rate(self, value):
        if value <= 0:
            raise serializers.ValidationError('费率必须大于0')
        return value

    def validate(self, attrs):
        case = attrs.get('case', getattr(self.instance, 'case', None))
        lawyer = attrs.get('lawyer', getattr(self.instance, 'lawyer', None))
        effective_date = attrs.get('effective_date',
                                   getattr(self.instance, 'effective_date', None))
        if not CaseLawyer.objects.filter(case=case, lawyer=lawyer).exists():
            raise serializers.ValidationError({'lawyer': '该律师不是本案承办律师'})
        qs = CaseRate.objects.filter(case=case, lawyer=lawyer,
                                     effective_date=effective_date)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {'effective_date': '该律师在此生效日期已有费率记录，请直接修改该条'})
        return attrs


def resolve_hourly_rate(case, lawyer, work_date):
    """按工作日期取当时生效的费率（费率变更只影响其生效日之后的工作）"""
    return (CaseRate.objects.filter(case=case, lawyer=lawyer,
                                    effective_date__lte=work_date)
            .order_by('-effective_date', '-id').first())


class TimeEntrySerializer(serializers.ModelSerializer):
    lawyer_name = serializers.CharField(source='lawyer.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2,
                                      read_only=True)
    bill_id = serializers.IntegerField(source='bill_line.bill_id', read_only=True,
                                       default=None)
    bill_number = serializers.CharField(source='bill_line.bill.bill_number',
                                        read_only=True, default=None)

    class Meta:
        model = TimeEntry
        fields = ['id', 'case', 'lawyer', 'lawyer_name', 'work_date', 'hours',
                  'description', 'hourly_rate', 'amount', 'status',
                  'status_display', 'bill_id', 'bill_number', 'approved_at',
                  'created_at']
        read_only_fields = ['status', 'approved_at']

    def validate_hours(self, value):
        if value <= 0:
            raise serializers.ValidationError('工时必须大于0')
        return value

    def validate(self, attrs):
        instance = self.instance
        if instance and instance.status != 'pending':
            raise serializers.ValidationError('仅待核准的工时可以修改')
        case = attrs.get('case', getattr(instance, 'case', None))
        lawyer = attrs.get('lawyer', getattr(instance, 'lawyer', None))
        if not CaseLawyer.objects.filter(case=case, lawyer=lawyer).exists():
            raise serializers.ValidationError({'lawyer': '该律师不是本案承办律师'})
        # 计时收费案件：提交工时即按工作日期快照当时费率
        work_date = attrs.get('work_date', getattr(instance, 'work_date', None))
        agreement = getattr(case, 'fee_agreement', None)
        if agreement and agreement.fee_type == 'hourly':
            rate = resolve_hourly_rate(case, lawyer, work_date)
            if rate is None:
                raise serializers.ValidationError(
                    f'未找到{lawyer.name}在{work_date}前生效的费率，请先在收费约定中设置费率')
            attrs['hourly_rate'] = rate.hourly_rate
        else:
            attrs['hourly_rate'] = None
        return attrs


class ExpenseSerializer(serializers.ModelSerializer):
    lawyer_name = serializers.CharField(source='lawyer.name', read_only=True)
    category_display = serializers.CharField(source='get_category_display',
                                             read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    bill_id = serializers.IntegerField(source='bill_line.bill_id', read_only=True,
                                       default=None)
    bill_number = serializers.CharField(source='bill_line.bill.bill_number',
                                        read_only=True, default=None)

    class Meta:
        model = Expense
        fields = ['id', 'case', 'lawyer', 'lawyer_name', 'expense_date',
                  'category', 'category_display', 'amount', 'description',
                  'status', 'status_display', 'bill_id', 'bill_number',
                  'approved_at', 'created_at']
        read_only_fields = ['status', 'approved_at']

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError('金额必须大于0')
        return value

    def validate(self, attrs):
        instance = self.instance
        if instance and instance.status != 'pending':
            raise serializers.ValidationError('仅待核准的费用可以修改')
        case = attrs.get('case', getattr(instance, 'case', None))
        lawyer = attrs.get('lawyer', getattr(instance, 'lawyer', None))
        if not CaseLawyer.objects.filter(case=case, lawyer=lawyer).exists():
            raise serializers.ValidationError({'lawyer': '该律师不是本案承办律师'})
        return attrs


class PaymentSerializer(serializers.ModelSerializer):
    method_display = serializers.CharField(source='get_method_display', read_only=True)
    is_reversed = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = ['id', 'bill', 'amount', 'received_date', 'method',
                  'method_display', 'is_reversal', 'is_reversed', 'reverses',
                  'notes', 'created_at']
        read_only_fields = ['is_reversal', 'reverses']

    def get_is_reversed(self, obj):
        """该笔收款是否已被红冲"""
        return obj.reversed_by.exists()

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError('收款金额必须大于0')
        return value

    def validate(self, attrs):
        bill = attrs['bill']
        if bill.status == 'void':
            raise serializers.ValidationError('账单已冲正，不能收款')
        if bill.status == 'paid':
            raise serializers.ValidationError('账单已结清')
        remaining = bill.outstanding
        if attrs['amount'] > remaining:
            raise serializers.ValidationError(
                {'amount': f'收款金额超出未收余额 ¥{remaining}'})
        return attrs

    def create(self, validated_data):
        payment = super().create(validated_data)
        payment.bill.refresh_status()
        return payment


class BillLineSerializer(serializers.ModelSerializer):
    line_type_display = serializers.CharField(source='get_line_type_display',
                                              read_only=True)

    class Meta:
        model = BillLine
        fields = ['id', 'line_type', 'line_type_display', 'description',
                  'quantity', 'unit_price', 'amount', 'time_entry', 'expense']


class BillSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    lines = BillLineSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    total_amount = serializers.DecimalField(max_digits=14, decimal_places=2,
                                            read_only=True)
    received_amount = serializers.DecimalField(max_digits=14, decimal_places=2,
                                               read_only=True)
    outstanding = serializers.DecimalField(max_digits=14, decimal_places=2,
                                           read_only=True)

    class Meta:
        model = Bill
        fields = ['id', 'case', 'bill_number', 'title', 'issue_date', 'due_date',
                  'status', 'status_display', 'total_amount', 'reduction_amount',
                  'reduction_reason', 'received_amount', 'outstanding',
                  'void_reason', 'voided_at', 'notes', 'lines', 'payments',
                  'created_at']


class FixedLineInput(serializers.Serializer):
    description = serializers.CharField(max_length=200)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))


class BillCreateSerializer(serializers.Serializer):
    """生成账单：勾选已核准工时/代垫费用，或录入固定收费期款"""
    case = serializers.PrimaryKeyRelatedField(queryset=Case.objects.all())
    title = serializers.CharField(max_length=100)
    issue_date = serializers.DateField()
    due_date = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    time_entry_ids = serializers.ListField(child=serializers.IntegerField(),
                                           required=False, default=list)
    expense_ids = serializers.ListField(child=serializers.IntegerField(),
                                        required=False, default=list)
    fixed_lines = FixedLineInput(many=True, required=False, default=list)

    @staticmethod
    def next_bill_number(case):
        seqs = []
        for bn in Bill.objects.filter(case=case).values_list('bill_number', flat=True):
            try:
                seqs.append(int(bn.rsplit('-', 1)[1]))
            except (IndexError, ValueError):
                continue
        return f'B{case.id:04d}-{(max(seqs) if seqs else 0) + 1:03d}'

    def validate(self, attrs):
        case = attrs['case']
        agreement = getattr(case, 'fee_agreement', None)
        fixed_lines = attrs['fixed_lines']

        # 固定收费期款仅适用于固定收费约定，且累计不得超过约定总额
        if fixed_lines:
            if not agreement or agreement.fee_type != 'fixed':
                raise serializers.ValidationError(
                    {'fixed_lines': '仅固定收费约定的案件可以录入固定收费期款'})
            new_total = sum((fl['amount'] for fl in fixed_lines), Decimal('0'))
            billed = sum(
                (line.amount for line in BillLine.objects.filter(
                    bill__case=case, line_type='fixed')
                 .exclude(bill__status='void')), Decimal('0'))
            remaining = agreement.fixed_amount - billed
            if new_total > remaining:
                raise serializers.ValidationError(
                    f'固定收费期款超出约定总额：约定 ¥{agreement.fixed_amount}，'
                    f'已出账 ¥{billed}，剩余可出 ¥{remaining}')

        entries = list(TimeEntry.objects.filter(pk__in=attrs['time_entry_ids'],
                                                case=case).select_related('lawyer'))
        if len(entries) != len(set(attrs['time_entry_ids'])):
            raise serializers.ValidationError({'time_entry_ids': '存在不属于本案的工时记录'})
        for e in entries:
            if e.status == 'billed':
                raise serializers.ValidationError(
                    f'工时「{e}」已出账，不能重复出账')
            if e.status != 'approved':
                raise serializers.ValidationError(f'工时「{e}」尚未核准')
            if e.hourly_rate is None:
                raise serializers.ValidationError(
                    f'工时「{e}」无费率依据（固定收费案件的工时不出账）')
        expenses = list(Expense.objects.filter(pk__in=attrs['expense_ids'], case=case))
        if len(expenses) != len(set(attrs['expense_ids'])):
            raise serializers.ValidationError({'expense_ids': '存在不属于本案的代垫费用'})
        for e in expenses:
            if e.status == 'billed':
                raise serializers.ValidationError(f'费用「{e}」已出账，不能重复出账')
            if e.status != 'approved':
                raise serializers.ValidationError(f'费用「{e}」尚未核准')
        if not entries and not expenses and not attrs['fixed_lines']:
            raise serializers.ValidationError('账单至少需要一条明细')
        attrs['_entries'] = entries
        attrs['_expenses'] = expenses
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        case = validated_data['case']
        bill = Bill.objects.create(
            case=case,
            bill_number=self.next_bill_number(case),
            title=validated_data['title'],
            issue_date=validated_data['issue_date'],
            due_date=validated_data.get('due_date'),
            notes=validated_data.get('notes', ''),
        )
        for entry in validated_data['_entries']:
            BillLine.objects.create(
                bill=bill, line_type='time',
                description=f"{entry.lawyer.name} {entry.work_date} {entry.description}",
                quantity=entry.hours, unit_price=entry.hourly_rate,
                amount=entry.amount, time_entry=entry)
            entry.status = 'billed'
            entry.save(update_fields=['status'])
        for expense in validated_data['_expenses']:
            BillLine.objects.create(
                bill=bill, line_type='expense',
                description=f"{expense.get_category_display()}：{expense.description}",
                amount=expense.amount, expense=expense)
            expense.status = 'billed'
            expense.save(update_fields=['status'])
        for fl in validated_data['fixed_lines']:
            BillLine.objects.create(
                bill=bill, line_type='fixed',
                description=fl['description'], amount=fl['amount'])
        bill.refresh_status()
        return bill
