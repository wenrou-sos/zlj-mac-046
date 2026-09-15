from django.db import models


def material_file_path(instance, filename):
    return f'materials/case_{instance.material.case_id}/material_{instance.material_id}/v{instance.version_no}_{filename}'


def receipt_file_path(instance, filename):
    return f'receipts/submission_{instance.submission_id}/{filename}'


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
    """案件材料（主档）：一份材料对应多个不可变版本"""
    STATUS_CHOICES = [
        ('draft', '未定稿'),
        ('finalized', '已定稿'),
        ('submitted', '已提交'),
        ('signed', '已签收'),
        ('returned', '退回补正'),
    ]
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='materials')
    name = models.CharField('材料名称', max_length=100)
    category = models.CharField('材料类别', max_length=50, blank=True,
                                help_text='如 起诉状/证据材料/代理词/申请书')
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='draft')
    notes = models.TextField('备注', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return self.name

    @property
    def final_version(self):
        return self.versions.filter(is_final=True).order_by('-version_no').first()

    def has_submission(self):
        return SubmissionItem.objects.filter(version__material=self).exists()


class MaterialVersion(models.Model):
    """材料版本：只增不改，同一材料多人同时上传各自生成新版本，绝不互相覆盖"""
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name='versions')
    version_no = models.PositiveIntegerField('版本号')
    file = models.FileField('附件', upload_to=material_file_path, null=True, blank=True,
                            help_text='历史补录时可暂缺，之后再上传新版本补件')
    file_name = models.CharField('文件名', max_length=255, blank=True)
    file_size = models.PositiveBigIntegerField('文件大小(字节)', null=True, blank=True)
    file_hash = models.CharField('SHA-256', max_length=64, blank=True, db_index=True)
    change_note = models.CharField('版本说明', max_length=255, blank=True,
                                   help_text='如 根据法官意见修改诉讼请求第二项')
    uploaded_by = models.CharField('上传人', max_length=50)
    is_backfilled = models.BooleanField('历史补录', default=False,
                                        help_text='补建历史材料时产生的无附件版本')
    is_final = models.BooleanField('定稿版本', default=False)
    finalized_by = models.CharField('定稿确认人', max_length=50, blank=True)
    finalized_at = models.DateTimeField('定稿时间', null=True, blank=True)
    created_at = models.DateTimeField('上传时间', auto_now_add=True)

    class Meta:
        ordering = ['material_id', '-version_no']
        constraints = [
            models.UniqueConstraint(fields=['material', 'version_no'],
                                    name='uniq_material_version_no'),
        ]

    def __str__(self):
        return f'{self.material.name} v{self.version_no}'

    def is_submitted(self):
        return self.submission_items.exists()


class MaterialReview(models.Model):
    """版本审阅意见：只追加，不修改"""
    RESULT_CHOICES = [
        ('comment', '意见'),
        ('revise', '需修改'),
        ('approve', '同意定稿'),
    ]
    version = models.ForeignKey(MaterialVersion, on_delete=models.CASCADE, related_name='reviews')
    author = models.CharField('审阅人', max_length=50)
    result = models.CharField('审阅结论', max_length=20, choices=RESULT_CHOICES, default='comment')
    comment = models.TextField('审阅意见')
    created_at = models.DateTimeField('审阅时间', auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.version} 审阅意见'


class MaterialSubmission(models.Model):
    """提交批次：每次向法院或对方提交固定接收对象、清单与所用版本"""
    STATUS_CHOICES = [
        ('submitted', '已提交'),
        ('signed', '已签收'),
        ('returned', '退回补正'),
    ]
    METHOD_CHOICES = [
        ('window', '立案/诉讼窗口'),
        ('online', '网上立案/诉讼平台'),
        ('post', '邮寄'),
        ('hand', '当面递交'),
        ('other', '其他'),
    ]
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='material_submissions')
    submitted_to = models.CharField('接收对象', max_length=100,
                                    help_text='如 朝阳区人民法院立案庭 / 对方代理律师')
    receiver_name = models.CharField('接收人', max_length=50, blank=True)
    method = models.CharField('提交方式', max_length=20, choices=METHOD_CHOICES, default='window')
    submit_date = models.DateField('提交日期')
    note = models.TextField('备注', blank=True)
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='submitted')
    created_by = models.CharField('提交经办人', max_length=50)
    resubmitted_from = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='resubmissions',
        verbose_name='补正后重新提交自')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-submit_date', '-id']

    def __str__(self):
        return f'{self.case_id} -> {self.submitted_to} ({self.submit_date})'


class SubmissionItem(models.Model):
    """提交清单项：提交时把所用版本快照固定，后续定稿/新版本不影响本批次"""
    submission = models.ForeignKey(MaterialSubmission, on_delete=models.CASCADE,
                                   related_name='items')
    version = models.ForeignKey(MaterialVersion, on_delete=models.PROTECT,
                                related_name='submission_items')
    material_name = models.CharField('材料名称(快照)', max_length=100)
    version_no = models.PositiveIntegerField('版本号(快照)')
    file_name = models.CharField('文件名(快照)', max_length=255, blank=True)
    copies = models.PositiveIntegerField('份数', default=1)
    pages = models.PositiveIntegerField('页数', null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['submission', 'version'],
                                    name='uniq_submission_version'),
        ]

    def __str__(self):
        return f'{self.material_name} v{self.version_no}'


class SubmissionReceipt(models.Model):
    """提交回执：签收回执 / 退回补正通知（含重新提交的关联）"""
    TYPE_CHOICES = [
        ('signed', '签收回执'),
        ('returned', '退回补正'),
    ]
    submission = models.ForeignKey(MaterialSubmission, on_delete=models.CASCADE,
                                   related_name='receipts')
    receipt_type = models.CharField('回执类型', max_length=20, choices=TYPE_CHOICES)
    receipt_no = models.CharField('回执/签收编号', max_length=100, blank=True)
    receiver_name = models.CharField('经办人/签收人', max_length=50, blank=True)
    receipt_date = models.DateField('回执日期')
    file = models.FileField('回执附件', upload_to=receipt_file_path, null=True, blank=True)
    file_name = models.CharField('回执文件名', max_length=255, blank=True)
    note = models.TextField('说明', blank=True,
                            help_text='退回补正须注明补正事项；重新提交可在备注中关联')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['receipt_date', 'id']

    def __str__(self):
        return f'{self.get_receipt_type_display()}({self.receipt_date})'


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
