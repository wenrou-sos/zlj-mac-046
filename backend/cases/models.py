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


class CaseHandover(models.Model):
    """案件交接：律师离岗/更换主办时，交出人与接收人核对待办后确认接管"""
    STATUS_CHOICES = [
        ('draft', '草稿'),
        ('pending', '待接收人核对'),
        ('returned', '已退回补充'),
        ('completed', '已完成交接'),
        ('canceled', '已取消'),
    ]
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='handovers')
    from_lawyer = models.ForeignKey(
        Lawyer, on_delete=models.PROTECT, related_name='handovers_from',
        verbose_name='交出人')
    to_lawyer = models.ForeignKey(
        Lawyer, on_delete=models.PROTECT, related_name='handovers_to',
        verbose_name='接收人')
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='draft')
    reason = models.CharField('交接原因', max_length=200, blank=True)
    # 待办快照指纹：实际待办变化后指纹失效，需补入清单并重新核对
    items_hash = models.CharField('清单指纹', max_length=64, blank=True)
    last_refreshed_at = models.DateTimeField('清单刷新时间', null=True, blank=True)
    submitted_at = models.DateTimeField('提交核对时间', null=True, blank=True)
    returned_reason = models.TextField('退回原因', blank=True)
    cancel_reason = models.TextField('取消原因', blank=True)
    completed_at = models.DateTimeField('完成时间', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return f'{self.case.title} {self.from_lawyer.name}→{self.to_lawyer.name}'

    @property
    def is_active(self):
        return self.status in ('draft', 'pending', 'returned')


class HandoverItem(models.Model):
    """交接清单条目：未办期限 / 后续开庭 / 待提交材料 / 自定义事项"""
    ITEM_TYPE_CHOICES = [
        ('deadline', '未办期限'),
        ('hearing', '后续开庭'),
        ('material', '待提交材料'),
        ('custom', '其他事项'),
    ]
    DESTINATION_CHOICES = [
        ('takeover', '接收人接管'),
        ('keep', '原责任人继续办理'),
        ('void', '无需办理'),
    ]
    CHANGE_CHOICES = [
        ('new', '新增'),
        ('changed', '已变更'),
        ('removed', '已办结/删除'),
        ('', ''),
    ]
    handover = models.ForeignKey(CaseHandover, on_delete=models.CASCADE, related_name='items')
    item_type = models.CharField('事项类型', max_length=20, choices=ITEM_TYPE_CHOICES)
    # 关联源对象（自定义事项为空），源对象删除后保留快照、置为 removed
    ref_id = models.IntegerField('源对象ID', null=True, blank=True)
    title = models.CharField('事项', max_length=200)
    detail = models.CharField('详情', max_length=300, blank=True)
    due_date = models.DateField('截止日期', null=True, blank=True)
    hearing_time = models.DateTimeField('开庭时间', null=True, blank=True)
    is_overdue = models.BooleanField('是否逾期', default=False)
    destination = models.CharField(
        '去向', max_length=20, choices=DESTINATION_CHOICES, default='takeover')
    checked = models.BooleanField('接收人已核对', default=False)
    check_note = models.CharField('核对备注', max_length=200, blank=True)
    change_flag = models.CharField(
        '清单变更标记', max_length=10, choices=CHANGE_CHOICES, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']
        unique_together = ('handover', 'item_type', 'ref_id')

    def __str__(self):
        return f'[{self.get_item_type_display()}] {self.title}'


class HandoverLog(models.Model):
    """交接操作留痕（提交/退回/确认/取消/刷新等），完成后仍可追溯"""
    ACTION_CHOICES = [
        ('create', '发起交接'),
        ('submit', '提交核对'),
        ('return', '退回补充'),
        ('confirm', '确认接管'),
        ('cancel', '取消交接'),
        ('refresh', '补入变更待办'),
        ('edit', '调整清单'),
    ]
    handover = models.ForeignKey(CaseHandover, on_delete=models.CASCADE, related_name='logs')
    action = models.CharField('操作', max_length=20, choices=ACTION_CHOICES)
    actor_lawyer = models.ForeignKey(
        Lawyer, on_delete=models.SET_NULL, null=True, verbose_name='操作人')
    actor_name = models.CharField('操作人姓名', max_length=50)
    note = models.TextField('说明', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.handover_id} {self.get_action_display()}'


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
