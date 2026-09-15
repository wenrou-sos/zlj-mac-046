from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import Reminder


@transaction.atomic
def deliver_reminder(reminder):
    """当前演示系统把“站内提醒”视为落库即可见；失败时记录原因并等待补发。"""
    reminder.attempts += 1
    if reminder.recipient_id is None:
        reminder.status = 'failed'
        reminder.last_error = '未配置接收人，无法发送站内提醒'
        reminder.next_retry_at = timezone.now() + timedelta(minutes=30)
    elif reminder.deadline.lifecycle != 'active' or reminder.deadline.is_done:
        reminder.status = 'cancelled'
        reminder.last_error = '期限已办结或失效，提醒取消'
    else:
        reminder.status = 'sent'
        reminder.sent_at = timezone.now()
        reminder.last_error = ''
        reminder.next_retry_at = None
    reminder.save()
    return reminder


@transaction.atomic
def send_due_reminders(now=None):
    now = now or timezone.now()
    pending_ids = list(Reminder.objects.filter(
        status='pending', scheduled_at__lte=now
    ).select_for_update(skip_locked=True).values_list('id', flat=True))
    for reminder_id in pending_ids:
        deliver_reminder(Reminder.objects.select_related('deadline', 'recipient').get(id=reminder_id))
    return len(pending_ids)


@transaction.atomic
def retry_failed_reminders(now=None, max_attempts=5):
    now = now or timezone.now()
    failed_ids = list(Reminder.objects.filter(
        status='failed', attempts__lt=max_attempts
    ).filter(Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now)
    ).select_for_update(skip_locked=True).values_list('id', flat=True))
    for reminder_id in failed_ids:
        deliver_reminder(Reminder.objects.select_related('deadline', 'recipient').get(id=reminder_id))
    return len(failed_ids)
