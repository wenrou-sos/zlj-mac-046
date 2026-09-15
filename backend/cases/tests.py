"""归档封存流程冒烟测试：python manage.py test cases"""
from datetime import date, timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from cases import archives
from cases.models import (ArchiveVersion, Case, CaseLawyer, CaseParty, Deadline,
                          Hearing, Lawyer, Material, Party, ReopenRequest)


class ArchiveFlowTests(APITestCase):
    def setUp(self):
        self.lawyer = Lawyer.objects.create(name='律师甲', bar_number='B001')
        self.lawyer2 = Lawyer.objects.create(name='律师乙', bar_number='B002')
        self.party = Party.objects.create(name='当事人A')
        self.case = Case.objects.create(case_number='(2026)测1号', title='测试案件')
        CaseParty.objects.create(case=self.case, party=self.party, role='plaintiff',
                                 is_client=True)
        CaseLawyer.objects.create(case=self.case, lawyer=self.lawyer, role='lead')
        self.deadline = Deadline.objects.create(
            case=self.case, title='举证期限', deadline_type='evidence',
            due_date=date.today() + timedelta(days=5))
        self.material = Material.objects.create(
            case=self.case, name='代理词', status='pending')
        self.hearing = Hearing.objects.create(
            case=self.case, hearing_time=timezone.now() + timedelta(days=3),
            location='第1法庭')

    # ---------- 服务层状态机 ----------
    def test_full_seal_flow(self):
        prep = archives.prepare_archive(self.case)
        self.assertFalse(prep['editable'] is False)
        keys = {i['item_key'] for i in prep['suggested_pending_items']}
        self.assertEqual(keys, {f'deadline-{self.deadline.id}',
                                f'material-{self.material.id}',
                                f'hearing-{self.hearing.id}'})

        # 漏填处置 -> 400
        with self.assertRaises(archives.ArchiveError):
            archives.submit_archive(self.case, {'pending_items': []})

        items = [
            {'item_key': f'deadline-{self.deadline.id}', 'kind': 'deadline',
             'title': '举证期限', 'disposition': 'completed',
             'disposition_note': '已按期提交证据'},
            {'item_key': f'material-{self.material.id}', 'kind': 'material',
             'title': '代理词', 'disposition': 'handover',
             'disposition_note': '已移交法院'},
            {'item_key': f'hearing-{self.hearing.id}', 'kind': 'hearing',
             'title': '庭期', 'disposition': 'waived',
             'disposition_note': '调解结案，庭期取消'},
            {'item_key': 'custom-案卷装订', 'kind': 'custom', 'title': '案卷装订',
             'disposition': 'other', 'disposition_note': '已装订两卷'},
        ]
        version, stale = archives.submit_archive(
            self.case, {'summary': '调解结案', 'prepared_by': '律师甲',
                        'submitted_by': '律师甲', 'pending_items': items})
        self.assertEqual(version.status, 'submitted')
        self.assertEqual(version.version_no, 1)
        self.assertEqual(version.pending_items.count(), 4)

        # 缺复核人 -> 400
        with self.assertRaises(archives.ArchiveError):
            archives.confirm_archive(self.case, 1, '', '')

        sealed = archives.confirm_archive(self.case, 1, '律师乙', '齐全')
        self.assertEqual(sealed.status, 'sealed')
        self.assertTrue(sealed.snapshot)
        self.assertEqual(len(sealed.snapshot['pending_items']), 4)
        self.assertEqual(self.case.__class__.objects.get(pk=self.case.pk).stage,
                         'closed')

    def test_concurrent_change_blocks_seal(self):
        archives.submit_archive(self.case, {
            'prepared_by': '律师甲',
            'pending_items': [{
                'item_key': f'deadline-{self.deadline.id}', 'kind': 'deadline',
                'title': '举证期限', 'disposition': 'completed',
                'disposition_note': '已完成'},
                {'item_key': f'material-{self.material.id}', 'kind': 'material',
                 'title': '代理词', 'disposition': 'handover',
                 'disposition_note': '已移交'},
                {'item_key': f'hearing-{self.hearing.id}', 'kind': 'hearing',
                 'title': '庭期', 'disposition': 'waived',
                 'disposition_note': '取消'}]})
        # 提交后有人补登材料 —— 分区指纹变化（旧清单过时）
        Material.objects.create(case=self.case, name='补充代理意见', status='pending')
        with self.assertRaises(archives.ArchiveConflict) as ctx:
            archives.confirm_archive(self.case, 1, '律师乙', '')
        changed_keys = [s['key'] for s in ctx.exception.changed_sections]
        self.assertIn('materials', changed_keys)

        # 指纹一致但登记过的未结事项被办结删除/新增遗漏 -> stale_items
        self.material.status = 'accepted'
        self.material.save()
        with self.assertRaises(archives.ArchiveConflict) as ctx:
            archives.confirm_archive(self.case, 1, '律师乙', '')
        changed_keys = [s['key'] for s in ctx.exception.changed_sections]
        self.assertIn('materials', changed_keys)
        self.assertTrue(ctx.exception.stale_items)

    def test_sealed_write_protection_via_api(self):
        archives.submit_archive(self.case, {
            'prepared_by': '律师甲',
            'pending_items': [{
                'item_key': f'deadline-{self.deadline.id}', 'kind': 'deadline',
                'title': '举证期限', 'disposition': 'completed',
                'disposition_note': '已完成'},
                {'item_key': f'material-{self.material.id}', 'kind': 'material',
                 'title': '代理词', 'disposition': 'handover',
                 'disposition_note': '已移交'},
                {'item_key': f'hearing-{self.hearing.id}', 'kind': 'hearing',
                 'title': '庭期', 'disposition': 'waived',
                 'disposition_note': '取消'}]})
        archives.confirm_archive(self.case, 1, '律师乙', '')

        # 案件本身不能改、不能删
        r = self.client.patch(f'/api/cases/{self.case.id}/', {'description': 'x'},
                              format='json')
        self.assertEqual(r.status_code, 403)
        r = self.client.delete(f'/api/cases/{self.case.id}/')
        self.assertEqual(r.status_code, 403)
        # 子记录不能增/改/删
        r = self.client.post('/api/deadlines/',
                             {'case': self.case.id, 'title': '新期限',
                              'deadline_type': 'other',
                              'due_date': str(date.today())}, format='json')
        self.assertEqual(r.status_code, 403)
        r = self.client.patch(f'/api/materials/{self.material.id}/',
                              {'status': 'accepted'}, format='json')
        self.assertEqual(r.status_code, 403)
        r = self.client.delete(f'/api/hearings/{self.hearing.id}/')
        self.assertEqual(r.status_code, 403)
        # 不能直接把普通案件阶段改成结案
        new_case = Case.objects.create(case_number='(2026)测2号', title='另案')
        r = self.client.patch(f'/api/cases/{new_case.id}/', {'stage': 'closed'},
                              format='json')
        self.assertEqual(r.status_code, 400)

    def test_reopen_creates_new_version_old_snapshot_kept(self):
        archives.submit_archive(self.case, {
            'prepared_by': '律师甲',
            'pending_items': [{
                'item_key': f'deadline-{self.deadline.id}', 'kind': 'deadline',
                'title': '举证期限', 'disposition': 'completed',
                'disposition_note': '已完成'},
                {'item_key': f'material-{self.material.id}', 'kind': 'material',
                 'title': '代理词', 'disposition': 'handover',
                 'disposition_note': '已移交'},
                {'item_key': f'hearing-{self.hearing.id}', 'kind': 'hearing',
                 'title': '庭期', 'disposition': 'waived',
                 'disposition_note': '取消'}]})
        v1 = archives.confirm_archive(self.case, 1, '律师乙', '')
        snapshot_v1 = v1.snapshot

        # 未批准前仍封存
        req = archives.apply_reopen(self.case, {
            'reason_type': 'retrial', 'reason': '高院裁定再审',
            'applicant': '律师甲'})
        self.assertEqual(req.status, 'pending')
        self.assertTrue(
            Case.objects.get(pk=self.case.pk).is_sealed)
        # 重复申请被拒绝
        with self.assertRaises(archives.ArchiveError):
            archives.apply_reopen(self.case, {'reason_type': 'retrial',
                                              'reason': 'again'})

        req = archives.decide_reopen(req.id, '律师乙', '同意', True, 'retrial')
        self.assertEqual(req.status, 'approved')
        self.assertFalse(Case.objects.get(pk=self.case.pk).is_sealed)
        v1.refresh_from_db()
        self.assertEqual(v1.status, 'reopened')
        self.assertEqual(v1.snapshot, snapshot_v1)  # 旧卷宗原样可查

        # 新一轮办理：旧事项全部办结，新增再审材料后再次封存，生成 v2
        self.deadline.is_done = True
        self.deadline.save()
        self.material.status = 'accepted'
        self.material.save()
        self.hearing.hearing_time = timezone.now() - timedelta(days=1)
        self.hearing.save()
        new_material = Material.objects.create(
            case=self.case, name='再审新证据', status='pending')
        v2_submit, _ = archives.submit_archive(self.case, {
            'prepared_by': '律师甲', 'summary': '再审结案',
            'pending_items': [{
                'item_key': f'material-{new_material.id}', 'kind': 'material',
                'title': '再审新证据', 'disposition': 'handover',
                'disposition_note': '已提交再审法院'}]})
        self.assertEqual(v2_submit.version_no, 2)
        v2 = archives.confirm_archive(self.case, 2, '律师乙', '')
        self.assertEqual(v2.status, 'sealed')
        self.assertEqual(v2.version_no, 2)
        self.assertEqual(
            ArchiveVersion.objects.get(pk=v1.pk).snapshot, snapshot_v1)

    def test_reject_and_resubmit_keeps_version_no(self):
        archives.submit_archive(self.case, {
            'prepared_by': '律师甲',
            'pending_items': [{
                'item_key': f'deadline-{self.deadline.id}', 'kind': 'deadline',
                'title': '举证期限', 'disposition': 'completed',
                'disposition_note': '已完成'},
                {'item_key': f'material-{self.material.id}', 'kind': 'material',
                 'title': '代理词', 'disposition': 'handover',
                 'disposition_note': '已移交'},
                {'item_key': f'hearing-{self.hearing.id}', 'kind': 'hearing',
                 'title': '庭期', 'disposition': 'waived',
                 'disposition_note': '取消'}]})
        archives.reject_archive(self.case, 1, '律师乙', '处置说明不完整')
        v, _stale = archives.submit_archive(self.case, {
            'prepared_by': '律师甲',
            'pending_items': [{
                'item_key': f'deadline-{self.deadline.id}', 'kind': 'deadline',
                'title': '举证期限', 'disposition': 'completed',
                'disposition_note': '已完成x'},
                {'item_key': f'material-{self.material.id}', 'kind': 'material',
                 'title': '代理词', 'disposition': 'handover',
                 'disposition_note': '已移交x'},
                {'item_key': f'hearing-{self.hearing.id}', 'kind': 'hearing',
                 'title': '庭期', 'disposition': 'waived',
                 'disposition_note': '取消x'}]})
        self.assertEqual(v.version_no, 1)
        sealed = archives.confirm_archive(self.case, 1, '律师乙', '')
        self.assertEqual(sealed.status, 'sealed')
