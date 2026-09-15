from django.db import models
from django.utils import timezone


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


class ConflictReview(models.Model):
    """利益冲突复核单：把一次冲突检查固化为可追溯的审批记录。

    申请时即冻结当事人身份、拟承接涉案关系与风险依据快照（JSON），
    审批结论、例外授权依据、适用期限以及承接使用情况均留痕；
    关系变更导致风险指纹变化后，旧单作废并可经 superseded_by 接续。
    """
    STATUS_CHOICES = [
        ('pending', '待复核'),
        ('approved', '已批准'),
        ('rejected', '已拒绝'),
        ('returned', '退回补充材料'),
        ('superseded', '已重新复核'),
        ('invalid', '已失效(关系变更)'),
    ]

    review_number = models.CharField('复核单号', max_length=30, unique=True, blank=True)
    case = models.ForeignKey(Case, on_delete=models.PROTECT, related_name='conflict_reviews',
                             verbose_name='目标案件')
    party = models.ForeignKey(Party, on_delete=models.PROTECT, related_name='conflict_reviews',
                              verbose_name='拟承接当事人')
    proposed_role = models.CharField('拟列诉讼地位', max_length=20, choices=CaseParty.ROLE_CHOICES)
    proposed_is_client = models.BooleanField('是否拟作为本所客户', default=False)

    applicant = models.ForeignKey(Lawyer, on_delete=models.PROTECT, related_name='applied_reviews',
                                  verbose_name='申请人')
    reviewer = models.ForeignKey(Lawyer, on_delete=models.PROTECT, related_name='assigned_reviews',
                                 verbose_name='指定复核人')
    apply_remark = models.TextField('申请说明', blank=True)

    # 申请时冻结的当事人身份 / 涉案关系 / 风险依据快照
    snapshot = models.JSONField('风险依据快照', default=dict)
    risk_level = models.CharField('风险等级', max_length=10, default='low')
    has_prohibited = models.BooleanField('含本所禁止性冲突', default=False)
    needs_exception = models.BooleanField('须例外授权', default=False)
    relationship_fingerprint = models.CharField('关系指纹', max_length=64, blank=True, db_index=True)

    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='pending',
                              db_index=True)
    # 复核结论
    decision_remark = models.TextField('复核意见', blank=True)
    exception_basis = models.TextField('例外授权依据', blank=True)
    exception_expire_date = models.DateField('例外适用期限', null=True, blank=True)
    decided_at = models.DateTimeField('决定时间', null=True, blank=True)

    # 承接闸门：批准结论被实际承接使用的记录
    used_at = models.DateTimeField('承接使用时间', null=True, blank=True)
    used_by = models.ForeignKey(Lawyer, on_delete=models.PROTECT, null=True, blank=True,
                                related_name='used_reviews', verbose_name='承接经办人')

    # 关系变更后进入重新复核的接续链
    superseded_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='superseded_reviews', verbose_name='重新复核单')
    created_at = models.DateTimeField('申请时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return self.review_number or f'复核单#{self.pk}'

    def save(self, *args, **kwargs):
        if not self.review_number:
            seq = ConflictReview.objects.filter(
                created_at__date=timezone.localdate()).count() + 1
            self.review_number = f'CR{timezone.localdate():%Y%m%d}{seq:03d}'
            # 同日并发兜底，保证唯一
            while ConflictReview.objects.filter(review_number=self.review_number)\
                    .exclude(pk=self.pk).exists():
                seq += 1
                self.review_number = f'CR{timezone.localdate():%Y%m%d}{seq:03d}'
        super().save(*args, **kwargs)

    @property
    def is_active_approval(self):
        """批准结论当前是否仍然有效（未使用 / 未到期 / 未被重新复核）。"""
        return (self.status == 'approved'
                and self.used_at is None
                and (self.exception_expire_date is None
                     or self.exception_expire_date >= timezone.localdate()))


class ConflictReviewMaterial(models.Model):
    """复核依据材料：申请时提交、退回后补充，全程保留。"""
    review = models.ForeignKey(ConflictReview, on_delete=models.CASCADE,
                               related_name='materials', verbose_name='复核单')
    name = models.CharField('材料名称', max_length=200)
    material_type = models.CharField('材料类型', max_length=50, blank=True)
    source = models.CharField('来源/出具方', max_length=200, blank=True)
    remark = models.TextField('说明', blank=True)
    uploaded_by = models.ForeignKey(Lawyer, on_delete=models.PROTECT,
                                    related_name='review_materials', verbose_name='提交人')
    uploaded_at = models.DateTimeField('提交时间', auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.name


class ConflictReviewLog(models.Model):
    """复核单全过程流水：申请、补材料、批准、拒绝、退回、作废、承接使用。"""
    ACTION_CHOICES = [
        ('apply', '提交申请'),
        ('supplement', '补充材料'),
        ('approve', '批准'),
        ('reject', '拒绝'),
        ('return', '退回补充材料'),
        ('supersede', '重新复核'),
        ('invalidate', '关系变更失效'),
        ('use', '承接使用'),
    ]
    review = models.ForeignKey(ConflictReview, on_delete=models.CASCADE,
                               related_name='logs', verbose_name='复核单')
    action = models.CharField('动作', max_length=20, choices=ACTION_CHOICES)
    actor = models.ForeignKey(Lawyer, on_delete=models.PROTECT, null=True, blank=True,
                              related_name='review_logs', verbose_name='操作人')
    actor_name = models.CharField('操作人姓名(留痕)', max_length=50, blank=True)
    detail = models.TextField('详情', blank=True)
    created_at = models.DateTimeField('时间', auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.review} {self.get_action_display()}'
