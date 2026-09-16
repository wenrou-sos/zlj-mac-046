from decimal import Decimal

from django.db import models


class Lawyer(models.Model):
    """承办律师"""
    TITLE_CHOICES = [
        ('partner', '合伙人'),
        ('senior', '资深律师'),
        ('lawyer', '律师'),
        ('assistant', '律师助理'),
    ]
    name = models.CharField('姓名', max_length=50)
    bar_number = models.CharField('执业证号', max_length=50, unique=True)
    title = models.CharField('职称', max_length=20, choices=TITLE_CHOICES, default='lawyer')
    phone = models.CharField('电话', max_length=20, blank=True)
    email = models.EmailField('邮箱', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.name


class Party(models.Model):
    """当事人（自然人或法人/组织）"""
    TYPE_CHOICES = [
        ('person', '自然人'),
        ('org', '法人/组织'),
    ]
    name = models.CharField('姓名/名称', max_length=100, db_index=True)
    party_type = models.CharField('类型', max_length=10, choices=TYPE_CHOICES, default='person')
    id_number = models.CharField('身份证号/统一社会信用代码', max_length=50, blank=True, db_index=True)
    phone = models.CharField('联系电话', max_length=20, blank=True)
    address = models.CharField('地址', max_length=200, blank=True)
    notes = models.TextField('备注', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.name


class Case(models.Model):
    """案件"""
    TYPE_CHOICES = [
        ('civil', '民事'),
        ('criminal', '刑事'),
        ('administrative', '行政'),
        ('arbitration', '仲裁'),
        ('nonlit', '非诉讼'),
    ]
    STAGE_CHOICES = [
        ('filing', '立案'),
        ('first', '一审'),
        ('second', '二审'),
        ('retrial', '再审'),
        ('enforcement', '执行'),
        ('closed', '结案'),
    ]
    case_number = models.CharField('案号', max_length=50, unique=True)
    title = models.CharField('案件名称', max_length=200)
    case_type = models.CharField('案件类型', max_length=20, choices=TYPE_CHOICES, default='civil')
    stage = models.CharField('诉讼阶段', max_length=20, choices=STAGE_CHOICES, default='filing')
    cause = models.CharField('案由', max_length=100, blank=True)
    court = models.CharField('受理法院/仲裁机构', max_length=100, blank=True)
    filed_date = models.DateField('立案日期', null=True, blank=True)
    amount = models.DecimalField('标的额(元)', max_digits=14, decimal_places=2, null=True, blank=True)
    description = models.TextField('案情简介', blank=True)
    lawyers = models.ManyToManyField(Lawyer, through='CaseLawyer', related_name='cases')
    parties = models.ManyToManyField(Party, through='CaseParty', related_name='cases')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return f'{self.case_number} {self.title}'


class CaseParty(models.Model):
    """案件-当事人关联（含诉讼地位）"""
    ROLE_CHOICES = [
        ('plaintiff', '原告'),
        ('defendant', '被告'),
        ('third', '第三人'),
        ('appellant', '上诉人'),
        ('appellee', '被上诉人'),
        ('applicant', '申请执行人'),
        ('respondent', '被执行人'),
        ('suspect', '犯罪嫌疑人'),
        ('victim', '被害人'),
    ]
    case = models.ForeignKey(Case, on_delete=models.CASCADE)
    party = models.ForeignKey(Party, on_delete=models.CASCADE)
    role = models.CharField('诉讼地位', max_length=20, choices=ROLE_CHOICES)
    is_client = models.BooleanField('是否本所客户', default=False)

    class Meta:
        unique_together = ('case', 'party', 'role')

    def __str__(self):
        return f'{self.party.name}({self.get_role_display()})'


class CaseLawyer(models.Model):
    """案件-律师关联"""
    ROLE_CHOICES = [
        ('lead', '主办律师'),
        ('assist', '协办律师'),
    ]
    case = models.ForeignKey(Case, on_delete=models.CASCADE)
    lawyer = models.ForeignKey(Lawyer, on_delete=models.CASCADE)
    role = models.CharField('承办角色', max_length=10, choices=ROLE_CHOICES, default='lead')

    class Meta:
        unique_together = ('case', 'lawyer')

    def __str__(self):
        return f'{self.lawyer.name}({self.get_role_display()})'


class Hearing(models.Model):
    """开庭安排"""
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='hearings')
    hearing_time = models.DateTimeField('开庭时间')
    location = models.CharField('开庭地点', max_length=100)
    judge = models.CharField('承办法官/仲裁员', max_length=50, blank=True)
    notes = models.TextField('备注', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['hearing_time']

    def __str__(self):
        return f'{self.case.title} {self.hearing_time}'


class StageLog(models.Model):
    """诉讼阶段流转记录"""
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='stage_logs')
    stage = models.CharField('阶段', max_length=20, choices=Case.STAGE_CHOICES)
    log_date = models.DateField('日期')
    notes = models.TextField('备注', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['log_date', 'id']

    def __str__(self):
        return f'{self.case.title} -> {self.get_stage_display()}'


class Material(models.Model):
    """案件材料提交记录"""
    STATUS_CHOICES = [
        ('pending', '待提交'),
        ('submitted', '已提交'),
        ('accepted', '已签收'),
    ]
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='materials')
    name = models.CharField('材料名称', max_length=100)
    submitted_to = models.CharField('提交对象', max_length=100, blank=True)
    submit_date = models.DateField('提交日期', null=True, blank=True)
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='pending')
    notes = models.TextField('备注', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return self.name


class FeeAgreement(models.Model):
    """案件收费约定（一案一份，与标的额无关）"""
    FEE_TYPE_CHOICES = [
        ('fixed', '固定收费'),
        ('hourly', '按工时收费'),
    ]
    case = models.OneToOneField(Case, on_delete=models.CASCADE,
                                related_name='fee_agreement')
    fee_type = models.CharField('收费方式', max_length=10,
                                choices=FEE_TYPE_CHOICES, default='hourly')
    fixed_amount = models.DecimalField('固定收费总额(元)', max_digits=14,
                                       decimal_places=2, null=True, blank=True)
    notes = models.TextField('约定说明', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.case.title} - {self.get_fee_type_display()}'


class CaseRate(models.Model):
    """案件内律师计时费率（按生效日期记录，变更不影响既往工作）"""
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='case_rates')
    lawyer = models.ForeignKey(Lawyer, on_delete=models.CASCADE)
    hourly_rate = models.DecimalField('小时费率(元)', max_digits=10, decimal_places=2)
    effective_date = models.DateField('生效日期')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('case', 'lawyer', 'effective_date')
        ordering = ['-effective_date', '-id']

    def __str__(self):
        return f'{self.lawyer.name} ¥{self.hourly_rate}/h 自{self.effective_date}'


class WorkStatus(models.TextChoices):
    PENDING = 'pending', '待核准'
    APPROVED = 'approved', '已核准'
    BILLED = 'billed', '已出账'


class TimeEntry(models.Model):
    """办案工时记录（提交时按工作日期快照当时费率）"""
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='time_entries')
    lawyer = models.ForeignKey(Lawyer, on_delete=models.CASCADE)
    work_date = models.DateField('工作日期')
    hours = models.DecimalField('工时(小时)', max_digits=5, decimal_places=2)
    description = models.CharField('工作内容', max_length=200)
    hourly_rate = models.DecimalField('适用费率快照(元/小时)', max_digits=10,
                                      decimal_places=2, null=True, blank=True)
    status = models.CharField('状态', max_length=10, choices=WorkStatus.choices,
                              default=WorkStatus.PENDING)
    approved_at = models.DateTimeField('核准时间', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-work_date', '-id']

    @property
    def amount(self):
        if self.hourly_rate is None:
            return None
        return (self.hours * self.hourly_rate).quantize(Decimal('0.01'))

    def __str__(self):
        return f'{self.lawyer.name} {self.work_date} {self.hours}h'


class Expense(models.Model):
    """代垫费用"""
    CATEGORY_CHOICES = [
        ('court_fee', '诉讼费/仲裁费'),
        ('travel', '差旅费'),
        ('notary', '公证费'),
        ('appraisal', '鉴定费'),
        ('courier', '快递/文印'),
        ('other', '其他'),
    ]
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='expenses')
    lawyer = models.ForeignKey(Lawyer, on_delete=models.CASCADE, verbose_name='代垫人')
    expense_date = models.DateField('费用日期')
    category = models.CharField('费用类别', max_length=20,
                                choices=CATEGORY_CHOICES, default='other')
    amount = models.DecimalField('金额(元)', max_digits=12, decimal_places=2)
    description = models.CharField('费用说明', max_length=200)
    status = models.CharField('状态', max_length=10, choices=WorkStatus.choices,
                              default=WorkStatus.PENDING)
    approved_at = models.DateTimeField('核准时间', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-expense_date', '-id']

    def __str__(self):
        return f'{self.get_category_display()} ¥{self.amount}'


class Bill(models.Model):
    """分期账单"""
    STATUS_CHOICES = [
        ('open', '待收款'),
        ('partial', '部分收款'),
        ('paid', '已结清'),
        ('void', '已冲正'),
    ]
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='bills')
    bill_number = models.CharField('账单编号', max_length=30, unique=True)
    title = models.CharField('期次/说明', max_length=100)
    issue_date = models.DateField('出账日期')
    due_date = models.DateField('付款期限', null=True, blank=True)
    reduction_amount = models.DecimalField('减免金额(元)', max_digits=12,
                                           decimal_places=2, default=0)
    reduction_reason = models.CharField('减免原因', max_length=200, blank=True)
    status = models.CharField('状态', max_length=10, choices=STATUS_CHOICES,
                              default='open')
    void_reason = models.CharField('冲正原因', max_length=200, blank=True)
    voided_at = models.DateTimeField('冲正时间', null=True, blank=True)
    notes = models.TextField('备注', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-id']

    @property
    def total_amount(self):
        return sum((line.amount for line in self.lines.all()), Decimal('0'))

    @property
    def received_amount(self):
        return sum((p.amount for p in self.payments.all()), Decimal('0'))

    @property
    def outstanding(self):
        return self.total_amount - self.reduction_amount - self.received_amount

    def refresh_status(self):
        """根据收款/减免情况刷新账单状态"""
        if self.status == 'void':
            return
        if self.outstanding <= 0:
            self.status = 'paid'
        elif self.received_amount > 0 or self.reduction_amount > 0:
            self.status = 'partial'
        else:
            self.status = 'open'
        self.save(update_fields=['status'])

    def __str__(self):
        return f'{self.bill_number} {self.title}'


class BillLine(models.Model):
    """账单明细（工时/费用一对一关联，杜绝重复出账；金额费率为出账时快照）"""
    TYPE_CHOICES = [
        ('time', '工时费'),
        ('expense', '代垫费用'),
        ('fixed', '固定收费'),
    ]
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name='lines')
    line_type = models.CharField('明细类型', max_length=10, choices=TYPE_CHOICES)
    description = models.CharField('摘要', max_length=200)
    quantity = models.DecimalField('数量(工时)', max_digits=6, decimal_places=2,
                                   null=True, blank=True)
    unit_price = models.DecimalField('单价/费率(元)', max_digits=10, decimal_places=2,
                                     null=True, blank=True)
    amount = models.DecimalField('金额(元)', max_digits=12, decimal_places=2)
    time_entry = models.OneToOneField(TimeEntry, on_delete=models.SET_NULL,
                                      null=True, blank=True,
                                      related_name='bill_line')
    expense = models.OneToOneField(Expense, on_delete=models.SET_NULL,
                                   null=True, blank=True,
                                   related_name='bill_line')

    def __str__(self):
        return f'{self.bill.bill_number} - {self.description}'


class Payment(models.Model):
    """收款记录（支持部分收款；冲正退款以负数记录）"""
    METHOD_CHOICES = [
        ('bank', '银行转账'),
        ('cash', '现金'),
        ('check', '支票'),
        ('other', '其他'),
    ]
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField('金额(元)', max_digits=12, decimal_places=2)
    received_date = models.DateField('收款日期')
    method = models.CharField('收款方式', max_length=10,
                              choices=METHOD_CHOICES, default='bank')
    is_reversal = models.BooleanField('冲正退款', default=False)
    notes = models.CharField('备注', max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['received_date', 'id']

    def __str__(self):
        return f'{self.bill.bill_number} 收款 ¥{self.amount}'


class Deadline(models.Model):
    """期限提醒"""
    TYPE_CHOICES = [
        ('appeal', '上诉期限'),
        ('evidence', '举证期限'),
        ('defense', '答辩期限'),
        ('hearing', '开庭'),
        ('payment', '缴费期限'),
        ('retrial', '再审申请期限'),
        ('enforcement', '申请执行期限'),
        ('other', '其他'),
    ]
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='deadlines')
    title = models.CharField('事项', max_length=100)
    deadline_type = models.CharField('期限类型', max_length=20, choices=TYPE_CHOICES, default='other')
    due_date = models.DateField('截止日期')
    remind_days = models.IntegerField('提前提醒天数', default=7)
    is_done = models.BooleanField('已办结', default=False)
    notes = models.TextField('备注', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['due_date']

    def __str__(self):
        return f'{self.title}({self.due_date})'
