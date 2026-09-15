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
    updated_at = models.DateTimeField('更新时间', auto_now=True)

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
    updated_at = models.DateTimeField('更新时间', auto_now=True)

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
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return f'{self.case_number} {self.title}'

    def _archive_versions_cached(self):
        """命中 prefetch 时返回缓存列表，否则返回 None"""
        cache = getattr(self, '_prefetched_objects_cache', None)
        if cache and 'archive_versions' in cache:
            return list(cache['archive_versions'])
        return None

    def get_archive_versions(self):
        cached = self._archive_versions_cached()
        if cached is not None:
            return sorted(cached, key=lambda v: v.version_no, reverse=True)
        return list(self.archive_versions.order_by('-version_no'))

    def get_current_archive(self):
        """当前卷宗版本（最新版本，无论处于何种状态）"""
        versions = self._archive_versions_cached()
        if versions is not None:
            return max(versions, key=lambda v: v.version_no) if versions else None
        return self.archive_versions.order_by('-version_no').first()

    def get_sealed_archive(self):
        """已封存卷宗（同一时刻至多一个）"""
        versions = self._archive_versions_cached()
        if versions is not None:
            sealed = [v for v in versions if v.status == 'sealed']
            return max(sealed, key=lambda v: v.version_no) if sealed else None
        return self.archive_versions.filter(status='sealed').order_by('-version_no').first()

    @property
    def is_sealed(self):
        return self.get_sealed_archive() is not None

    def archive_info(self):
        """供序列化器使用的归档状态摘要"""
        current = self.get_current_archive()
        sealed = self.get_sealed_archive()
        return {
            'is_sealed': self.is_sealed,
            'has_archive': current is not None,
            'current_version': current.version_no if current else None,
            'current_status': current.status if current else None,
            'current_status_display': current.get_status_display() if current else None,
            'sealed_version': sealed.version_no if sealed else None,
        }


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
    updated_at = models.DateTimeField('更新时间', auto_now=True)

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
    updated_at = models.DateTimeField('更新时间', auto_now=True)

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
    updated_at = models.DateTimeField('更新时间', auto_now=True)

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
    updated_at = models.DateTimeField('更新时间', auto_now=True)

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
    updated_at = models.DateTimeField('更新时间', auto_now=True)

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
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['due_date']

    def __str__(self):
        return f'{self.title}({self.due_date})'


class ArchiveVersion(models.Model):
    """卷宗归档版本：整理提交 -> 复核封存；封存后快照不可变"""
    STATUS_CHOICES = [
        ('draft', '整理中'),
        ('submitted', '待复核'),
        ('sealed', '已封存'),
        ('rejected', '复核退回'),
        ('reopened', '已重开(历史版本)'),
    ]
    REOPEN_REASON_CHOICES = [
        ('retrial', '再审'),
        ('supplement', '补充材料'),
        ('other', '其他'),
    ]
    case = models.ForeignKey(Case, on_delete=models.CASCADE,
                             related_name='archive_versions')
    version_no = models.PositiveIntegerField('版本号', default=1)
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='draft')

    # 提交/封存时的案件信息
    closed_date = models.DateField('结案日期', null=True, blank=True)
    summary = models.TextField('结案摘要', blank=True)
    fingerprint = models.CharField('清单指纹', max_length=64, blank=True)
    fingerprint_state = models.JSONField('分区指纹明细', default=dict, blank=True)

    # 人员记录（无用户体系，留姓名）
    prepared_by = models.CharField('整理人', max_length=50, blank=True)
    submitted_by = models.CharField('提交人', max_length=50, blank=True)
    submitted_at = models.DateTimeField('提交时间', null=True, blank=True)
    reviewer = models.CharField('复核人', max_length=50, blank=True)
    review_comment = models.TextField('复核意见', blank=True)
    sealed_at = models.DateTimeField('封存时间', null=True, blank=True)
    reject_reason = models.TextField('退回原因', blank=True)

    # 封存时冻结的完整卷宗快照
    snapshot = models.JSONField('归档快照', default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-version_no']
        unique_together = ('case', 'version_no')

    def __str__(self):
        return f'{self.case.case_number} 卷宗v{self.version_no}（{self.get_status_display()}）'


class PendingItem(models.Model):
    """卷宗整理时逐项登记的未结事项及处置说明"""
    KIND_CHOICES = [
        ('deadline', '未办结期限'),
        ('material', '未结材料'),
        ('hearing', '未来庭期'),
        ('custom', '其他事项'),
    ]
    DISPOSITION_CHOICES = [
        ('completed', '已完成'),
        ('handover', '已移交处理'),
        ('followup', '继续跟进'),
        ('waived', '当事人放弃/终结'),
        ('other', '其他处置'),
    ]
    archive_version = models.ForeignKey(ArchiveVersion, on_delete=models.CASCADE,
                                        related_name='pending_items')
    kind = models.CharField('事项类别', max_length=20, choices=KIND_CHOICES)
    ref_id = models.PositiveIntegerField('关联记录ID', null=True, blank=True)
    item_key = models.CharField('事项键', max_length=60)
    title = models.CharField('事项', max_length=200)
    detail = models.CharField('详情', max_length=300, blank=True)
    disposition = models.CharField('处置方式', max_length=20,
                                   choices=DISPOSITION_CHOICES, blank=True)
    disposition_note = models.TextField('处置说明', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['kind', 'id']
        unique_together = ('archive_version', 'item_key')

    def __str__(self):
        return f'v{self.archive_version.version_no}-{self.title}'


class ReopenRequest(models.Model):
    """卷宗重开申请（再审/补充材料），批准后产生新一轮办理"""
    REASON_CHOICES = [
        ('retrial', '再审'),
        ('supplement', '补充材料'),
        ('other', '其他'),
    ]
    STATUS_CHOICES = [
        ('pending', '待审批'),
        ('approved', '已批准'),
        ('rejected', '未批准'),
    ]
    case = models.ForeignKey(Case, on_delete=models.CASCADE,
                             related_name='reopen_requests')
    archive_version = models.ForeignKey(ArchiveVersion, on_delete=models.SET_NULL,
                                        null=True, blank=True, related_name='reopen_requests',
                                        verbose_name='申请时卷宗版本')
    reason_type = models.CharField('重开原因', max_length=20, choices=REASON_CHOICES)
    reason = models.TextField('原因说明')
    applicant = models.CharField('申请人', max_length=50, blank=True)
    status = models.CharField('审批状态', max_length=20, choices=STATUS_CHOICES, default='pending')
    approver = models.CharField('批准人', max_length=50, blank=True)
    approval_comment = models.TextField('审批意见', blank=True)
    next_stage = models.CharField('重开后阶段', max_length=20,
                                  choices=Case.STAGE_CHOICES, default='retrial')
    decided_at = models.DateTimeField('审批时间', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return f'{self.case.case_number} 重开申请-{self.get_status_display()}'
