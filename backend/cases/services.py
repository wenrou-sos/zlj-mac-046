"""案件可见范围与操作权限的统一判定

所有入口（列表搜索、详情直访、工作台统计、冲突检索、关联记录）
都必须经由本模块判定，保证“同一可见范围”。
"""
from django.db.models import Q
from django.utils import timezone

from .models import AuditLog, CaseAccess


def profile_of(user):
    if not user or not user.is_authenticated:
        return None
    return getattr(user, 'profile', None)


def is_admin(user):
    return bool(user and user.is_authenticated
                and (user.is_superuser or (profile_of(user)
                     and profile_of(user).role == 'admin')))


def active_access_qs(user):
    """当前仍有效的案件授权（未撤权、借阅未到期）"""
    now = timezone.now()
    return CaseAccess.objects.filter(
        user=user, revoked=False
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))


def access_for(user, case):
    """用户在某案件上的有效授权，无则 None"""
    if not user.is_authenticated:
        return None
    if is_admin(user):
        return None
    return (active_access_qs(user).filter(case=case)
            .select_related('user').first())


def visible_cases(user, qs=None):
    """按可见范围过滤案件查询集；管理员/超管返回全集"""
    if qs is None:
        from .models import Case
        qs = Case.objects.all()
    if is_admin(user):
        return qs
    if not user.is_authenticated:
        return qs.none()
    return qs.filter(id__in=active_access_qs(user).values('case_id'))


def visible_case_ids(user):
    if is_admin(user):
        return None
    if not user.is_authenticated:
        return set()
    return set(active_access_qs(user).values_list('case_id', flat=True))


def can_view_case(user, case):
    if is_admin(user):
        return True
    return active_access_qs(user).filter(case=case).exists()


def can_edit_case(user, case):
    """管理员可编辑全部；主办/协办账号凭有效授权可编辑经办案件；只读助理不可写"""
    if not user.is_authenticated:
        return False
    if is_admin(user):
        return True
    profile = profile_of(user)
    if not profile or profile.role == 'reader':
        return False
    return active_access_qs(user).filter(case=case).exists()


def my_access_info(user, case):
    """供序列化器输出：当前用户在该案的授权信息"""
    if not user.is_authenticated:
        return None
    if is_admin(user):
        return {'role': 'admin', 'role_display': '管理员',
                'source': 'admin', 'source_display': '管理员',
                'expires_at': None, 'can_edit': True}
    acc = access_for(user, case)
    if not acc:
        return None
    return {
        'role': acc.role,
        'role_display': acc.get_role_display(),
        'source': acc.source,
        'source_display': acc.get_source_display(),
        'expires_at': acc.expires_at,
        'can_edit': can_edit_case(user, case),
    }


def log_audit(actor, action, *, target_user=None, case=None, access=None,
              detail='', request=None):
    ip = None
    if request is not None:
        xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
        ip = (xff.split(',')[0].strip() or request.META.get('REMOTE_ADDR'))
    return AuditLog.objects.create(
        actor=actor if (actor and actor.is_authenticated) else None,
        action=action, target_user=target_user, case=case, access=access,
        detail=detail[:500], ip=ip)


def record_lapsed_accesses():
    """把已到期但尚未登记的限时借阅补记“借阅到期”审计（惰性登记，无需定时任务）"""
    now = timezone.now()
    lapsed = CaseAccess.objects.filter(revoked=False, expires_at__lte=now)
    for acc in lapsed.select_related('user', 'case'):
        if AuditLog.objects.filter(access=acc, action='expire').exists():
            continue
        log_audit(acc.user, 'expire', target_user=acc.user,
                  case=acc.case, access=acc,
                  detail=f'对案件「{acc.case.title}」的限时借阅已到期')
