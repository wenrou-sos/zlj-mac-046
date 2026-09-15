"""承办团队 <-> 案件授权 的自动联动

- 新建账号自动生成资料(UserProfile)
- 律师被加入/移出案件(CaseLawyer)时，同步其绑定账号的 team 类授权
- 账号重新绑定律师档案时，按新的承办关系回填团队授权
"""
from django.contrib.auth.models import User
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import CaseAccess, CaseLawyer, UserProfile


@receiver(post_save, sender=User)
def ensure_profile(sender, instance, created, **kwargs):
    if created and not hasattr(instance, 'profile'):
        UserProfile.objects.create(user=instance)


def sync_team_access_for_lawyer(lawyer):
    """按律师当前全部承办关系，同步其绑定账号的团队授权"""
    profile = (UserProfile.objects.filter(lawyer=lawyer)
               .select_related('user').first())
    if not profile:
        return
    user = profile.user
    for cl in lawyer.caselawyer_set.select_related('case'):
        acc, created = CaseAccess.objects.get_or_create(
            case=cl.case, user=user,
            defaults={'role': cl.role, 'source': 'team'})
        if created:
            continue
        changed = False
        # 已撤权（手动移除过）但承办关系仍在 -> 恢复
        if acc.revoked:
            acc.revoked = False
            acc.revoked_at = None
            changed = True
        if acc.source != 'team':
            acc.source = 'team'
            acc.expires_at = None
            changed = True
        if acc.role != cl.role:
            acc.role = cl.role
            changed = True
        if changed:
            acc.save()

def revoke_team_access(user, case, *, keep_if_other_lawyer=None):
    qs = CaseAccess.objects.filter(case=case, user=user, source='team')
    if keep_if_other_lawyer_id := (keep_if_other_lawyer or 0):
        # 账号改绑到另一位仍在本案团队的律师时，不应撤权
        if CaseLawyer.objects.filter(
                case=case, lawyer_id=keep_if_other_lawyer_id).exists():
            return
    acc = qs.first()
    if acc and not acc.revoked:
        acc.revoked = True
        acc.revoked_at = timezone.now()
        acc.save(update_fields=['revoked', 'revoked_at'])


@receiver(post_save, sender=CaseLawyer)
def case_lawyer_synced(sender, instance, created, **kwargs):
    sync_team_access_for_lawyer(instance.lawyer)


@receiver(post_delete, sender=CaseLawyer)
def case_lawyer_removed(sender, instance, **kwargs):
    profile = (UserProfile.objects.filter(lawyer=instance.lawyer)
               .select_related('user').first())
    if profile:
        revoke_team_access(profile.user, instance.case)


@receiver(pre_save, sender=UserProfile)
def remember_old_lawyer(sender, instance, **kwargs):
    if instance.pk:
        instance._old_lawyer_id = (
            UserProfile.objects.filter(pk=instance.pk)
            .values_list('lawyer_id', flat=True).first())
    else:
        instance._old_lawyer_id = None


@receiver(post_save, sender=UserProfile)
def profile_lawyer_rebound(sender, instance, created, **kwargs):
    old_id = getattr(instance, '_old_lawyer_id', None)
    new_id = instance.lawyer_id
    if (created or old_id != new_id) and new_id:
        if old_id:
            for cl in CaseLawyer.objects.filter(lawyer_id=old_id):
                revoke_team_access(
                    instance.user, cl.case, keep_if_other_lawyer=new_id)
        sync_team_access_for_lawyer(instance.lawyer)
