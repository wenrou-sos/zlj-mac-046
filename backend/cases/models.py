from django.conf import settings
from django.db import models
from django.utils import timezone


class UserProfile(models.Model):
    """系统账号扩展资料：账号 -> 角色(及可选的律师档案绑定)"""
    ROLE_CHOICES = [
        ('admin', '管理员'),
        ('lead', '主办律师'),
        ('assist', '协办律师'),
        ('reader', '只读助理'),
    ]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='profile')
    role = models.CharField('账号角色', max_length=10, choices=ROLE_CHOICES, default='reader')
    lawyer = models.OneToOneField('Lawyer', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='profile', verbose_name='绑定律师档案')

    class Meta:
        verbose_name = '账号资料'
        verbose_name_plural = '账号资料'

    def __str__(self):
        return f'{self.user.username}({self.get_role_display()})'


class CaseAccess(models.Model):
    """案件级访问授权（按办案团队区分可见范围的唯一依据）

    来源：
    - team  : 随承办关系(CaseLawyer)自动生成的团队授权，主办->lead、协办->assist
    - grant : 管理员/主办律师对只读助理等账号的手动授权（可限时借阅）
    撤权即 revoked；限时借阅到期由 valid 自动判定为失效，无需定时任务。
    """
    ROLE_CHOICES = [
        ('lead', '主办律师'),
        ('assist', '协办律师'),
        ('reader', '只读'),
    ]
    SOURCE_CHOICES = [
        ('team', '承办团队'),
        ('grant', '手动授权'),
    ]
    case = models.ForeignKey('Case', on_delete=models.CASCADE, related_name='accesses')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='case_accesses')
    role = models.CharField('案件内角色', max_length=10, choices=ROLE_CHOICES, default='reader')
    source = models.CharField('授权来源', max_length=10, choices=SOURCE_CHOICES, default='grant')
    granted_at = models.DateTimeField('授权时间', auto_now_add=True)
    expires_at = models.DateTimeField('借阅到期时间', null=True, blank=True)
    revoked = models.BooleanField('已撤权', default=False)
    revoked_at = models.DateTimeField('撤权时间', null=True, blank=True)

    class Meta:
        verbose_name = '案件授权'
        verbose_name_plural = '案件授权'
        unique_together = ('case', 'user')
        ordering = ['case_id', 'role', 'user__username']

    @property
    def is_valid(self):
        if self.revoked:
            return False
        if self.expires_at and self.expires_at <= timezone.now():
            return False
        return True

    def __str__(self):
        return f'{self.user.username} -> {self.case_id}({self.role})'


class AuditLog(models.Model):
    """审计日志：权限变更与敏感访问留痕"""
    ACTION_CHOICES = [
        ('login', '登录'),
        ('login_failed', '登录失败'),
        ('logout', '退出登录'),
        ('grant', '授权'),
        ('revoke', '撤权'),
        ('expire', '借阅到期'),
        ('case_view', '查看案件详情'),
        ('conflict_check', '利益冲突检索'),
        ('case_delete', '删除案件'),
    ]
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                              null=True, blank=True, related_name='audit_actions',
                              verbose_name='操作人')
    action = models.CharField('动作', max_length=20, choices=ACTION_CHOICES)
    target_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='audit_targets',
                                    verbose_name='被授权对象')
    case = models.ForeignKey('Case', on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='audit_logs', verbose_name='相关案件')
    access = models.ForeignKey('CaseAccess', on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='audit_logs', verbose_name='相关授权')
    detail = models.CharField('详情', max_length=500, blank=True)
    ip = models.GenericIPAddressField('IP地址', null=True, blank=True)
    created_at = models.DateTimeField('时间', auto_now_add=True)

    class Meta:
        verbose_name = '审计日志'
        verbose_name_plural = '审计日志'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.created_at:%Y-%m-%d %H:%M} {self.action}'


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
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='created_parties',
                                   verbose_name='建档人')
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
