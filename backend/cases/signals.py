"""涉案关系变更后自动使旧复核结论失效。

监听三类与冲突认定相关的关系变化：
1. 案件新增 / 移除当事人（CaseParty 增删）；
2. 当事人诉讼地位或"是否本所客户"认定变化；
3. 案件阶段变化（在办 ↔ 结案直接影响对抗冲突认定）。

凡涉及当事人的待复核 / 已批准（尚未承接使用）复核单，一律重新计算
风险关系指纹；指纹不一致即标记"已失效(关系变更)"并留痕，由申请人
基于旧单发起重新复核，旧单与退回过程继续可查。
"""
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from . import conflicts
from .models import Case, CaseParty, ConflictReview, ConflictReviewLog

# 仍可能因关系变更而失效的状态（已拒绝/已退回/已作废/已承接使用的不动）
LIVE_STATUSES = ('pending', 'approved')


def _invalidate_for_party(party, reason):
    qs = ConflictReview.objects.filter(
        party=party, status__in=LIVE_STATUSES, used_at__isnull=True)
    for review in qs:
        fresh_fp = conflicts.relationship_fingerprint(
            party, review.case, review.proposed_role, review.proposed_is_client)
        if fresh_fp == review.relationship_fingerprint:
            continue
        review.status = 'invalid'
        review.save(update_fields=['status', 'updated_at'])
        ConflictReviewLog.objects.create(
            review=review, action='invalidate', actor=None,
            actor_name='系统', detail=reason)


def _invalidate_case_parties(case, reason):
    party_ids = case.caseparty_set.values_list('party_id', flat=True)
    for pid in party_ids:
        from .models import Party
        _invalidate_for_party(Party.objects.get(pk=pid), reason)


@receiver(pre_save, sender=CaseParty)
def _caseparty_pre_save(sender, instance, **kwargs):
    if instance.pk:
        old = CaseParty.objects.filter(pk=instance.pk).values(
            'role', 'is_client').first()
        instance._old_role = old['role'] if old else None
        instance._old_is_client = old['is_client'] if old else None


@receiver(post_save, sender=CaseParty)
def _caseparty_post_save(sender, instance, created, **kwargs):
    cp = instance
    if created:
        reason = (f'涉案关系变更：{cp.party.name} 新增登记到案件'
                  f'「{cp.case.title}」（{cp.get_role_display()}，'
                  f'{"本所客户" if cp.is_client else "非本所客户"}），原复核结论失效')
    else:
        old_role = getattr(cp, '_old_role', None)
        old_client = getattr(cp, '_old_is_client', None)
        if old_role == cp.role and old_client == cp.is_client:
            return
        changes = []
        if old_role != cp.role:
            changes.append(f'诉讼地位变更为{cp.get_role_display()}')
        if old_client != cp.is_client:
            changes.append(f'本所客户认定变更为{"是" if cp.is_client else "否"}')
        reason = (f'涉案关系变更：{cp.party.name} 在案件「{cp.case.title}」中'
                  f'{"、".join(changes)}，原复核结论失效')
    _invalidate_for_party(cp.party, reason)


@receiver(post_delete, sender=CaseParty)
def _caseparty_post_delete(sender, instance, **kwargs):
    reason = (f'涉案关系变更：{instance.party.name} 已从案件'
              f'「{instance.case.title}」移除，原复核结论失效')
    _invalidate_for_party(instance.party, reason)


@receiver(pre_save, sender=Case)
def _case_pre_save(sender, instance, **kwargs):
    if instance.pk:
        old = Case.objects.filter(pk=instance.pk).values('stage').first()
        instance._old_stage = old['stage'] if old else None
    else:
        instance._old_stage = None


@receiver(post_save, sender=Case)
def _case_post_save(sender, instance, created, **kwargs):
    old_stage = getattr(instance, '_old_stage', None)
    if created or old_stage is None or old_stage == instance.stage:
        return
    reason = (f'涉案关系变更：案件「{instance.title}」阶段由'
              f'{dict(Case.STAGE_CHOICES).get(old_stage, old_stage)}'
              f'变更为{instance.get_stage_display()}，相关复核结论失效')
    _invalidate_case_parties(instance, reason)
