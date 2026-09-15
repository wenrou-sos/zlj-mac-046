"""把旧材料表的 submitted_to/submit_date/status 迁移为版本+提交批次+回执"""
from django.db import migrations
from django.utils import timezone


def migrate_legacy_materials(apps, schema_editor):
    Material = apps.get_model('cases', 'Material')
    MaterialVersion = apps.get_model('cases', 'MaterialVersion')
    MaterialSubmission = apps.get_model('cases', 'MaterialSubmission')
    SubmissionItem = apps.get_model('cases', 'SubmissionItem')
    SubmissionReceipt = apps.get_model('cases', 'SubmissionReceipt')

    # 同一案件、相同提交对象与日期的旧材料合并为一个提交批次
    batch_cache = {}

    for m in Material.objects.all().iterator():
        old_status = m.status  # pending / submitted / accepted（旧 choices 值仍在列里）
        is_submitted = old_status in ('submitted', 'accepted') and bool(m.submitted_to)

        version = MaterialVersion(
            material=m,
            version_no=1,
            file=None,
            file_name='',
            change_note='历史登记数据，附件待补录',
            uploaded_by='历史数据',
            is_backfilled=True,
            is_final=is_submitted,
            finalized_by='历史数据' if is_submitted else '',
            finalized_at=timezone.now() if is_submitted else None,
        )
        version.save()

        if not is_submitted:
            # pending：旧记录中尚未提交的草稿
            Material.objects.filter(pk=m.pk).update(status='draft')
            continue

        key = (m.case_id, m.submitted_to, m.submit_date)
        submission = batch_cache.get(key)
        if submission is None:
            submission = MaterialSubmission(
                case_id=m.case_id,
                submitted_to=m.submitted_to,
                receiver_name='',
                method='window',
                submit_date=m.submit_date or timezone.now().date(),
                note='由历史材料记录迁移生成',
                status='signed' if old_status == 'accepted' else 'submitted',
                created_by='历史数据',
            )
            submission.save()
            batch_cache[key] = submission

        SubmissionItem(
            submission=submission,
            version=version,
            material_name=m.name,
            version_no=1,
            file_name='',
            copies=1,
            pages=None,
        ).save()

        if old_status == 'accepted' and submission.submit_date:
            SubmissionReceipt(
                submission=submission,
                receipt_type='signed',
                receipt_no='',
                receiver_name='',
                receipt_date=submission.submit_date,
                note='由历史「已签收」材料记录迁移生成',
            ).save()

        Material.objects.filter(pk=m.pk).update(
            status='signed' if old_status == 'accepted' else 'submitted')


def reverse_migrate(apps, schema_editor):
    """回滚：删除迁移生成的版本/批次（仅删除由历史数据迁移者）"""
    MaterialSubmission = apps.get_model('cases', 'MaterialSubmission')
    MaterialVersion = apps.get_model('cases', 'MaterialVersion')
    Material = apps.get_model('cases', 'Material')
    MaterialSubmission.objects.filter(created_by='历史数据').delete()
    MaterialVersion.objects.filter(uploaded_by='历史数据').delete()
    Material.objects.update(status='draft')


class Migration(migrations.Migration):

    dependencies = [
        ('cases', '0002_material_versions_submissions'),
    ]

    operations = [
        migrations.RunPython(migrate_legacy_materials, reverse_migrate),
    ]
