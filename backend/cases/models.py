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


class Holiday(models.Model):
    """律所维护的节假日（周末自动识别，此表用于法定节假日/调休特殊安排）"""
    holiday_date = models.DateField('放假日期', unique=True)
    name = models.CharField('节假日名称', max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['holiday_date']
        verbose_name = '节假日'
        verbose_name_plural = '节假日'

    def __str__(self):
        return f'{self.holiday_date} {self.name}'


class DeadlineRule(models.Model):
    """按律所规则从案件事件自动生成期限"""
    EVENT_CHOICES = [
        ('service', '送达'),
        ('filing', '立案'),
        ('judgment', '裁判文书送达'),
        ('hearing', '开庭通知'),
        ('other', '其他事件'),
    ]
    DAY_TYPE_CHOICES = [
        ('natural', '自然日'),
        ('workday', '工作日'),
    ]
    START_CHOICES = [
        ('event_day', '事件发生当日'),
        ('next_day', '事件次日'),
    ]
    LAWYER_ROLE_CHOICES = [
        ('lead', '主办律师'),
        ('assist', '协办律师'),
    ]
    name = models.CharField('规则名称/期限事项', max_length=100)
    deadline_type = models.CharField('期限类型', max_length=20, choices=[
        ('appeal', '上诉期限'),
        ('evidence', '举证期限'),
        ('defense', '答辩期限'),
        ('hearing', '开庭'),
        ('payment', '缴费期限'),
        ('retrial', '再审申请期限'),
        ('enforcement', '申请执行期限'),
        ('other', '其他'),
    ], default='other')
    event_type = models.CharField('触发事件', max_length=20, choices=EVENT_CHOICES)
    duration_days = models.PositiveIntegerField('期限天数')
    day_type = models.CharField('日期口径', max_length=20, choices=DAY_TYPE_CHOICES, default='natural')
    start_timing = models.CharField('起算点', max_length=20, choices=START_CHOICES, default='next_day')
    holiday_postpone = models.BooleanField('届满日遇节假日顺延', default=True)
    remind_days = models.PositiveIntegerField('提前提醒天数', default=7)
    escalate_days = models.PositiveIntegerField('逾期升级天数', default=3)
    owner_role = models.CharField('默认负责人角色', max_length=20, choices=LAWYER_ROLE_CHOICES, default='lead')
    reviewer_role = models.CharField('默认复核人角色', max_length=20, choices=LAWYER_ROLE_CHOICES, default='assist')
    active = models.BooleanField('启用', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['event_type', 'id']
        verbose_name = '期限规则'
        verbose_name_plural = '期限规则'

    def __str__(self):
        return self.name


class DeadlineEvent(models.Model):
    """作为期限起算依据的案件事件，如送达、立案、裁判文书送达"""
    EVENT_CHOICES = DeadlineRule.EVENT_CHOICES
    STATUS_CHOICES = [
        ('active', '有效'),
        ('revoked', '已撤销'),
    ]
    case = models.ForeignKey(Case, on_delete=models.PROTECT, related_name='deadline_events')
    event_type = models.CharField('事件类型', max_length=20, choices=EVENT_CHOICES)
    title = models.CharField('事件名称', max_length=100)
    event_date = models.DateField('事件日期')
    external_id = models.CharField('外部事件流水号', max_length=100, blank=True, null=True, unique=True)
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='active')
    revoked_reason = models.CharField('撤销原因', max_length=200, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField('备注', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-event_date', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['case', 'event_type', 'event_date', 'title'],
                name='uniq_deadline_event_identity'),
        ]

    def __str__(self):
        return f'{self.case.title} {self.title} {self.event_date}'


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
    SOURCE_CHOICES = [
        ('manual', '人工登记'),
        ('generated', '规则生成'),
    ]
    LIFECYCLE_CHOICES = [
        ('active', '有效'),
        ('revoked', '因事件撤销'),
        ('superseded', '已被替代'),
    ]
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='deadlines')
    rule = models.ForeignKey(DeadlineRule, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='deadlines', verbose_name='生成规则')
    event = models.ForeignKey(DeadlineEvent, on_delete=models.PROTECT, null=True, blank=True,
                              related_name='deadlines', verbose_name='起算事件')
    title = models.CharField('事项', max_length=100)
    deadline_type = models.CharField('期限类型', max_length=20, choices=TYPE_CHOICES, default='other')
    due_date = models.DateField('截止日期')
    remind_days = models.IntegerField('提前提醒天数', default=7)
    escalate_days = models.PositiveIntegerField('逾期升级天数', default=3)
    owner = models.ForeignKey(Lawyer, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='owned_deadlines', verbose_name='负责人')
    reviewer = models.ForeignKey(Lawyer, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='reviewed_deadlines', verbose_name='复核人')
    basis_text = models.TextField('起算依据', blank=True)
    source = models.CharField('来源', max_length=20, choices=SOURCE_CHOICES, default='manual')
    lifecycle = models.CharField('生命周期', max_length=20, choices=LIFECYCLE_CHOICES, default='active')
    is_done = models.BooleanField('已办结', default=False)
    done_at = models.DateTimeField('办结时间', null=True, blank=True)
    revoked_reason = models.CharField('失效原因', max_length=200, blank=True)
    notes = models.TextField('备注', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['due_date']
        constraints = [
            models.UniqueConstraint(
                fields=['event', 'rule'],
                condition=models.Q(lifecycle='active', event__isnull=False, rule__isnull=False),
                name='uniq_active_generated_deadline'),
        ]

    def __str__(self):
        return f'{self.title}({self.due_date})'


class DeadlineVersion(models.Model):
    """期限快照版本，事件更正/撤销或人工修改时保留旧版本"""
    CHANGE_CHOICES = [
        ('created', '创建'),
        ('manual_update', '人工修改'),
        ('event_recalculate', '事件更正重算'),
        ('rule_recalculate', '规则调整重算'),
        ('event_revoked', '事件撤销'),
    ]
    deadline = models.ForeignKey(Deadline, on_delete=models.CASCADE, related_name='versions')
    version = models.PositiveIntegerField('版本号')
    change_type = models.CharField('变更类型', max_length=30, choices=CHANGE_CHOICES)
    reason = models.CharField('变更原因', max_length=200, blank=True)
    snapshot = models.JSONField('期限快照', default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-version', '-id']
        unique_together = ('deadline', 'version')


class Reminder(models.Model):
    """站内提醒及其确认、逾期升级、失败补发记录"""
    KIND_CHOICES = [
        ('advance', '到期提醒'),
        ('overdue', '逾期提醒'),
        ('escalation', '逾期升级'),
    ]
    ROLE_CHOICES = [
        ('owner', '负责人'),
        ('reviewer', '复核人'),
    ]
    STATUS_CHOICES = [
        ('pending', '待发送'),
        ('sent', '已发送'),
        ('failed', '发送失败'),
        ('confirmed', '已确认'),
        ('cancelled', '已取消'),
    ]
    deadline = models.ForeignKey(Deadline, on_delete=models.CASCADE, related_name='reminders')
    recipient = models.ForeignKey(Lawyer, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='reminders', verbose_name='接收人')
    recipient_role = models.CharField('接收角色', max_length=20, choices=ROLE_CHOICES)
    kind = models.CharField('提醒类型', max_length=20, choices=KIND_CHOICES)
    scheduled_at = models.DateTimeField('计划发送时间')
    sent_at = models.DateTimeField('发送时间', null=True, blank=True)
    confirmed_at = models.DateTimeField('确认时间', null=True, blank=True)
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='pending')
    attempts = models.PositiveIntegerField('发送次数', default=0)
    next_retry_at = models.DateTimeField('下次补发时间', null=True, blank=True)
    last_error = models.CharField('最近失败原因', max_length=200, blank=True)
    dedupe_key = models.CharField('幂等键', max_length=120, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-scheduled_at', '-id']

    def __str__(self):
        return f'{self.get_kind_display()} - {self.deadline.title}'
