from django.core.management.base import BaseCommand

from cases.reminder_tasks import retry_failed_reminders, send_due_reminders


class Command(BaseCommand):
    help = '发送到期站内提醒，并补发之前失败的提醒'

    def handle(self, *args, **options):
        sent = send_due_reminders()
        retried = retry_failed_reminders()
        self.stdout.write(self.style.SUCCESS(f'到期提醒发送 {sent} 条，失败补发处理 {retried} 条'))
