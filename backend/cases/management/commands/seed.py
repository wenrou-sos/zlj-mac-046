"""内置样例案件数据：python manage.py seed"""
from datetime import date, datetime, timedelta

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone

from cases.models import (Case, CaseLawyer, CaseParty, Deadline, Hearing,
                          Lawyer, Material, MaterialReview,
                          MaterialSubmission, MaterialVersion, Party, StageLog,
                          SubmissionItem, SubmissionReceipt)
TODAY = date.today()


def d(days):
    """相对今天的日期"""
    return TODAY + timedelta(days=days)


def dt(days, hour=9, minute=30):
    day = d(days)
    return timezone.make_aware(datetime(day.year, day.month, day.day, hour, minute))


class Command(BaseCommand):
    help = '清空并重建律所样例数据'

    def handle(self, *args, **options):
        # 清空旧数据（顺序：关联表 -> 主表）
        for model in (Hearing, StageLog, SubmissionReceipt, SubmissionItem,
                      MaterialSubmission, MaterialReview, MaterialVersion,
                      Material, Deadline,
                      CaseParty, CaseLawyer, Case, Party, Lawyer):
            model.objects.all().delete()

        # ---------- 律师 ----------
        lawyers = {}
        for name, bar, title, phone, email in [
            ('张伟民', '11101200810123456', 'partner', '13801012345', 'zhangwm@lawfirm.cn'),
            ('李静怡', '11101201210234567', 'senior', '13902023456', 'lijy@lawfirm.cn'),
            ('王志强', '11101201510345678', 'lawyer', '13703034567', 'wangzq@lawfirm.cn'),
            ('陈晓东', '11101201810456789', 'lawyer', '13604045678', 'chenxd@lawfirm.cn'),
            ('刘雅芳', '11101202010567890', 'lawyer', '13505056789', 'liuyf@lawfirm.cn'),
            ('赵国庆', '11101202210678901', 'assistant', '13406067890', 'zhaogq@lawfirm.cn'),
        ]:
            lawyers[name] = Lawyer.objects.create(
                name=name, bar_number=bar, title=title, phone=phone, email=email)

        # ---------- 当事人 ----------
        parties = {}
        for name, ptype, idno, phone, addr in [
            ('深圳市恒达建材有限公司', 'org', '91440300MA5D8X2K1A', '0755-26801234', '深圳市南山区科技园南路18号'),
            ('北京中科信息技术有限公司', 'org', '91110108MA01C3Y55B', '010-62550123', '北京市海淀区中关村大街27号'),
            ('上海宏宇贸易有限公司', 'org', '91310115MA1K4P8Q2C', '021-58890123', '上海市浦东新区世纪大道1168号'),
            ('广州市顺达物流有限公司', 'org', '91440101MA5CJ7R33D', '020-83550123', '广州市白云区物流大道88号'),
            ('孙建国', 'person', '440304197802153319', '13823456789', '深圳市福田区梅林一村'),
            ('郑晓梅', 'person', '440304198506204422', '13934567890', '深圳市罗湖区翠竹路'),
            ('杭州西湖房地产开发有限公司', 'org', '91330100MA27W9T44E', '0571-88012345', '杭州市西湖区文三路199号'),
            ('南京金陵餐饮管理有限公司', 'org', '91320100MA1XK2F66F', '025-84701234', '南京市秦淮区夫子庙大街32号'),
            ('成都天府建筑工程有限公司', 'org', '91510100MA6C8H177G', '028-85012345', '成都市高新区天府大道北段966号'),
            ('重庆山城火锅餐饮有限公司', 'org', '91500100MA5U3Q288H', '023-63012345', '重庆市渝中区解放碑步行街66号'),
            ('周文斌', 'person', '110105197511083316', '13612345678', '北京市朝阳区望京西园四区'),
            ('北京市朝阳区住房和城乡建设委员会', 'org', '11110105000012345X', '010-85996000', '北京市朝阳区呼家楼向军北里23号'),
            ('马晓东', 'person', '440301198203154455', '13723456789', '深圳市南山区华侨城'),
            ('林淑华', 'person', '440301198709126628', '13834567890', '深圳市宝安区新安街道'),
            ('吴丽娟', 'person', '110108198201253327', '13512345678', '北京市海淀区知春路'),
        ]:
            parties[name] = Party.objects.create(
                name=name, party_type=ptype, id_number=idno, phone=phone, address=addr)

        P = parties

        def make_case(number, title, ctype, stage, cause, court, filed, amount,
                      desc, party_roles, lawyer_roles):
            case = Case.objects.create(
                case_number=number, title=title, case_type=ctype, stage=stage,
                cause=cause, court=court, filed_date=filed, amount=amount,
                description=desc)
            for pname, role, is_client in party_roles:
                CaseParty.objects.create(case=case, party=P[pname],
                                         role=role, is_client=is_client)
            for lname, role in lawyer_roles:
                CaseLawyer.objects.create(case=case, lawyer=lawyers[lname], role=role)
            return case

        # ---------- 案件 ----------
        c1 = make_case(
            '(2026)京0105民初886号', '恒达建材诉中科信息买卖合同纠纷',
            'civil', 'first', '买卖合同纠纷', '北京市朝阳区人民法院',
            d(-95), 1280000,
            '恒达建材向中科信息供应建筑钢材，中科信息拖欠货款128万元及逾期利息，多次催告未果后提起诉讼。',
            [('深圳市恒达建材有限公司', 'plaintiff', True),
             ('北京中科信息技术有限公司', 'defendant', False)],
            [('张伟民', 'lead'), ('陈晓东', 'assist')])

        c2 = make_case(
            '(2026)沪02民终4521号', '宏宇贸易诉顺达物流运输合同纠纷(二审)',
            'civil', 'second', '运输合同纠纷', '上海市第二中级人民法院',
            d(-60), 860000,
            '顺达物流承运货物途中发生货损，一审判决其赔偿宏宇贸易86万元，顺达物流不服提起上诉，本所代理被上诉人宏宇贸易。',
            [('上海宏宇贸易有限公司', 'appellee', True),
             ('广州市顺达物流有限公司', 'appellant', False)],
            [('李静怡', 'lead')])

        c3 = make_case(
            '(2026)粤0304刑初567号', '孙建国涉嫌合同诈骗罪辩护案',
            'criminal', 'first', '合同诈骗罪', '深圳市福田区人民法院',
            d(-45), None,
            '孙建国被控以虚构工程项目骗取郑晓梅投资款，本所担任其辩护人，已会见当事人并提交取保候审申请。',
            [('孙建国', 'suspect', True),
             ('郑晓梅', 'victim', False)],
            [('王志强', 'lead'), ('刘雅芳', 'assist')])

        c4 = make_case(
            '(2026)浙01民初2345号', '西湖房产诉金陵餐饮房屋租赁合同纠纷',
            'civil', 'first', '房屋租赁合同纠纷', '杭州市中级人民法院',
            d(-38), 2400000,
            '西湖房产诉金陵餐饮拖欠租金及违约金240万元，本所代理被告金陵餐饮，已提出管辖权异议。',
            [('杭州西湖房地产开发有限公司', 'plaintiff', False),
             ('南京金陵餐饮管理有限公司', 'defendant', True)],
            [('张伟民', 'lead'), ('赵国庆', 'assist')])

        c5 = make_case(
            '(2026)川01执恢89号', '天府建筑申请执行山城火锅工程款案',
            'civil', 'enforcement', '建设工程施工合同纠纷', '成都市中级人民法院',
            d(-120), 3150000,
            '生效判决确认山城火锅支付工程款315万元，因被执行人转移财产申请恢复执行，正在追查财产线索。',
            [('成都天府建筑工程有限公司', 'applicant', True),
             ('重庆山城火锅餐饮有限公司', 'respondent', False)],
            [('陈晓东', 'lead')])

        c6 = make_case(
            '(2026)京03行初112号', '周文斌诉朝阳区住建委行政处罚案',
            'administrative', 'first', '行政处罚', '北京市第三中级人民法院',
            d(-25), None,
            '周文斌不服朝阳区住建委作出的行政处罚决定，请求依法撤销，本所代理原告。',
            [('周文斌', 'plaintiff', True),
             ('北京市朝阳区住房和城乡建设委员会', 'defendant', False)],
            [('刘雅芳', 'lead')])

        c7 = make_case(
            '(2026)深仲裁字第078号', '马晓东与林淑华股权转让纠纷仲裁案',
            'arbitration', 'first', '股权转让纠纷', '深圳国际仲裁院',
            d(-15), 980000,
            '马晓东主张林淑华未按股权转让协议支付转让款98万元，已向深圳国际仲裁院申请仲裁。',
            [('马晓东', 'plaintiff', True),
             ('林淑华', 'defendant', False)],
            [('李静怡', 'lead'), ('王志强', 'assist')])

        c8 = make_case(
            '(2025)京0105民初9876号', '吴丽娟诉周文斌民间借贷纠纷',
            'civil', 'closed', '民间借贷纠纷', '北京市朝阳区人民法院',
            d(-300), 350000,
            '吴丽娟诉周文斌归还借款35万元，双方达成调解，被告已按期履行完毕，本案结案。',
            [('吴丽娟', 'plaintiff', True),
             ('周文斌', 'defendant', False)],
            [('赵国庆', 'lead')])

        # ---------- 开庭安排 ----------
        for case, days, loc, judge, notes in [
            (c1, 10, '朝阳区人民法院第12法庭', '王建国', '携带证据原件，提前30分钟到庭'),
            (c2, 11, '上海市第二中级人民法院第3法庭', '李慧敏', '二审开庭，准备答辩意见'),
            (c4, 28, '杭州市中级人民法院第8法庭', '张立群', '管辖权异议裁定后首次开庭'),
            (c7, 18, '深圳国际仲裁院第2仲裁庭', '陈志远', '仲裁庭组成已确认'),
            (c3, -20, '深圳市福田区人民法院第5法庭', '刘明', '一审第一次开庭（已开庭）'),
        ]:
            Hearing.objects.create(case=case, hearing_time=dt(days),
                                   location=loc, judge=judge, notes=notes)

        # ---------- 阶段流转 ----------
        for case, entries in [
            (c1, [('filing', -95, '法院立案受理'), ('first', -80, '进入一审程序，送达起诉状副本')]),
            (c2, [('filing', -150, '一审立案'), ('first', -140, '一审审理'),
                  ('second', -60, '对方上诉，进入二审程序')]),
            (c3, [('filing', -45, '检察院提起公诉，法院立案'), ('first', -30, '一审审理中')]),
            (c4, [('filing', -38, '收到应诉通知书'), ('first', -30, '一审程序，已提管辖权异议')]),
            (c5, [('filing', -200, '诉讼立案'), ('first', -180, '一审判决我方胜诉'),
                  ('enforcement', -120, '申请强制执行，后恢复执行')]),
            (c6, [('filing', -25, '行政案件立案'), ('first', -10, '一审审理中')]),
            (c7, [('filing', -15, '仲裁申请已受理'), ('first', -5, '仲裁庭组成，等待开庭')]),
            (c8, [('filing', -300, '立案受理'), ('first', -280, '一审审理'),
                  ('closed', -90, '调解结案，履行完毕')]),
        ]:
            for stage, days, notes in entries:
                StageLog.objects.create(case=case, stage=stage,
                                        log_date=d(days), notes=notes)

        # ---------- 材料（版本 / 审阅 / 提交 / 回执） ----------
        def fake_file(material_name, version_no, body):
            """生成一个纯文本占位附件（真实 PDF/DOCX 由用户上传替换）"""
            safe = material_name.replace('/', '_').replace('(', '').replace(')', '')
            data = (f'{material_name} — 第 {version_no} 版（样例占位文件）\n\n{body}\n')
            return ContentFile(data.encode(), name=f'{safe}_v{version_no}.txt')

        def add_version(material, no, uploaded_by, note, body, *,
                        final=False, finalized_by='', backfilled=False,
                        reviews=None, attach=True):
            v = MaterialVersion(
                material=material, version_no=no,
                change_note=note, uploaded_by=uploaded_by,
                is_backfilled=backfilled,
                is_final=final, finalized_by=finalized_by,
                finalized_at=timezone.now() if final else None)
            if attach:
                v.file = fake_file(material.name, no, body)
                v.file_name = v.file.name
            v.save()
            if attach:
                v.file_size = v.file.size
                v.save(update_fields=['file_size'])
            for author, result, comment in (reviews or []):
                MaterialReview.objects.create(version=v, author=author,
                                              result=result, comment=comment)
            return v

        def make_submission(case, to, days, method, created_by, entries,
                            status_='submitted', receiver='', note='',
                            receipt=None):
            """entries: [(material, version, copies, pages)]"""
            sub = MaterialSubmission.objects.create(
                case=case, submitted_to=to, receiver_name=receiver,
                method=method, submit_date=d(days) if days is not None else TODAY,
                status=status_, created_by=created_by, note=note)
            material_ids = set()
            for material, ver, copies, pages in entries:
                SubmissionItem.objects.create(
                    submission=sub, version=ver,
                    material_name=material.name, version_no=ver.version_no,
                    file_name=ver.file_name, copies=copies, pages=pages)
                material_ids.add(material.pk)
            Material.objects.filter(pk__in=material_ids).update(status=status_)
            if receipt:
                rtype, rno, rname, rnote = receipt
                SubmissionReceipt.objects.create(
                    submission=sub, receipt_type=rtype, receipt_no=rno,
                    receiver_name=rname, receipt_date=d(days), note=rnote)
            return sub

        # c1 起诉状：v1 被要求修改 -> v2 定稿 -> 已签收
        m_c1_sue = Material.objects.create(case=c1, name='民事起诉状', category='起诉状',
                                           status='signed')
        add_version(m_c1_sue, 1, '赵国庆', '初稿，诉讼请求待核对',
                    '诉讼请求：判令被告支付货款128万元。',
                    reviews=[('张伟民', 'revise', '诉讼请求第二项金额需与对账单一致，'
                                               '并补充逾期利息计算方式')])
        v2 = add_version(m_c1_sue, 2, '赵国庆', '按主办意见修改利息计算',
                         '诉讼请求：1.支付货款128万元；2.按LPR支付逾期利息。',
                         final=True, finalized_by='张伟民',
                         reviews=[('张伟民', 'approve', '可提交立案')])
        make_submission(c1, '朝阳区人民法院立案庭', -90, 'window', '赵国庆',
                        [(m_c1_sue, v2, 2, 6)], status_='signed',
                        receiver='立案窗口 刘法官',
                        receipt=('signed', '(朝)立收字第20260566号', '刘敏',
                                 '立案窗口签收，出具材料收据'),
                        note='立案提交，一式两份')

        # c1 证据材料：多组证据，已提交待签收
        m_c1_evi = Material.objects.create(case=c1, name='证据清单及证据材料(共12组)',
                                           category='证据材料', status='submitted')
        add_version(m_c1_evi, 1, '陈晓东', '证据初编',
                    '证据1-8：送货单、入库单',
                    reviews=[('张伟民', 'revise', '补充对账单与催款函作为第9-12组')])
        ve2 = add_version(m_c1_evi, 2, '陈晓东', '补充对账单、催款函共12组',
                          '证据1-12：送货单、对账单、催款函等',
                          final=True, finalized_by='张伟民',
                          reviews=[('张伟民', 'approve', '证据链完整')])
        make_submission(c1, '朝阳区人民法院民二庭', -20, 'online', '陈晓东',
                        [(m_c1_evi, ve2, 1, 86)], status_='submitted',
                        note='通过北京法院诉讼服务平台提交，等待签收')

        # c1 代理词：未定稿（仅 v1 + 审阅意见）
        m_c1_agent = Material.objects.create(case=c1, name='代理词', category='代理词',
                                             status='draft', notes='开庭前提交')
        add_version(m_c1_agent, 1, '赵国庆', '代理词初稿',
                    '围绕买卖合同关系及欠款事实展开',
                    reviews=[('张伟民', 'comment', '庭后根据庭审焦点补充质证意见')])

        # c2 答辩状（对方上诉）—— 邮寄已签收
        m_c2_app = Material.objects.create(case=c2, name='民事答辩状', category='答辩状',
                                           status='signed')
        va = add_version(m_c2_app, 1, '李静怡', '针对上诉理由逐条答辩',
                         '一审认定事实清楚，适用法律正确，请求驳回上诉。',
                         final=True, finalized_by='李静怡')
        make_submission(c2, '上海市第二中级人民法院立案庭', -55, 'post', '李静怡',
                        [(m_c2_app, va, 3, 9)], status_='signed',
                        receiver='EMS 法院专递',
                        receipt=('signed', 'EY023356678CN', '收发室',
                                 'EMS 回执显示法院收发室签收'),
                        note='EMS 法院专递邮寄')

        # c2 新证据：等待鉴定，暂无附件（历史补录占位）
        m_c2_evi = Material.objects.create(case=c2, name='二审新证据(货损鉴定报告)',
                                           category='证据材料', status='draft',
                                           notes='等待鉴定机构出具后补传')
        add_version(m_c2_evi, 1, '李静怡', '鉴定报告出具后在此补传新版本',
                    '', attach=False, backfilled=True)

        # c3 取保候审申请：v1 修改后 v2 定稿，已签收
        m_c3_bail = Material.objects.create(case=c3, name='取保候审申请书',
                                            category='申请书', status='signed')
        add_version(m_c3_bail, 1, '刘雅芳', '初稿', '申请对孙建国取保候审。',
                    reviews=[('王志强', 'revise', '补充保证人信息与社会危险性论证')])
        vb2 = add_version(m_c3_bail, 2, '刘雅芳', '补充保证人及理由',
                          '保证人：孙某（嫌疑人之父），已退休，固定住所。',
                          final=True, finalized_by='王志强')
        make_submission(c3, '福田区人民检察院案件管理中心', -40, 'hand', '刘雅芳',
                        [(m_c3_bail, vb2, 1, 5)], status_='signed',
                        receiver='案管中心 陈检察官助理',
                        receipt=('signed', '深福检管收〔2026〕118号', '陈助理',
                                 '检察机关已采纳，作出取保候审决定'),
                        note='当面递交')

        # c3 辩护意见：已提交
        m_c3_def = Material.objects.create(case=c3, name='辩护意见',
                                           category='辩护意见', status='submitted')
        vd = add_version(m_c3_def, 1, '王志强', '罪轻辩护意见',
                         '主观恶性小、积极退赔，建议从轻处罚。',
                         final=True, finalized_by='王志强')
        make_submission(c3, '福田区人民法院刑庭', -22, 'window', '王志强',
                        [(m_c3_def, vd, 5, 8)], status_='submitted',
                        note='庭审时提交法庭及公诉人、被告人各一份')

        # c4 管辖权异议：v1 被退回补正（缺授权委托书、所函），补正后重新提交并签收
        m_c4_juris = Material.objects.create(case=c4, name='管辖权异议申请书',
                                             category='申请书', status='signed')
        vj1 = add_version(m_c4_juris, 1, '赵国庆', '初稿',
                          '请求将本案移送被告住所地法院管辖。',
                          final=True, finalized_by='张伟民')
        sub_juris_1 = make_submission(
            c4, '杭州市中级人民法院立案庭', -33, 'window', '赵国庆',
            [(m_c4_juris, vj1, 2, 4)], status_='returned',
            receiver='立案窗口',
            receipt=('returned', '', '立案窗口 张法官',
                     '材料不齐：缺少授权委托书原件及律师事务所函，'
                     '请于收到通知之日起7日内补正后重新提交'),
            note='首次提交，窗口形式审查')
        vj2 = add_version(m_c4_juris, 2, '赵国庆', '补附授权委托书、所函',
                          '在原申请基础上附授权委托书原件、律师事务所函。',
                          reviews=[('张伟民', 'approve', '按补正通知补齐，可重新提交')],
                          final=True, finalized_by='张伟民')
        sub_juris_2 = make_submission(
            c4, '杭州市中级人民法院立案庭', -28, 'window', '赵国庆',
            [(m_c4_juris, vj2, 2, 8)], status_='signed',
            receiver='立案窗口 张法官',
            receipt=('signed', '(浙01)立收字第20263302号', '张法官',
                     '补正材料齐全，予以签收，后裁定移送'),
            note='退回补正后重新提交')
        sub_juris_2.resubmitted_from = sub_juris_1
        sub_juris_2.save(update_fields=['resubmitted_from'])

        # c4 答辩状：已提交
        m_c4_ans = Material.objects.create(case=c4, name='民事答辩状',
                                           category='答辩状', status='submitted')
        vans = add_version(m_c4_ans, 1, '张伟民', '答辩状定稿',
                           '租金支付受疫情及房屋瑕疵影响，请求调减违约金。',
                           final=True, finalized_by='张伟民')
        make_submission(c4, '杭州市中级人民法院民庭', -12, 'online', '赵国庆',
                        [(m_c4_ans, vans, 1, 12)], status_='submitted',
                        note='浙江法院网平台提交')

        # c5 恢复执行申请：已签收
        m_c5_res = Material.objects.create(case=c5, name='恢复执行申请书',
                                           category='申请书', status='signed')
        vr = add_version(m_c5_res, 1, '陈晓东', '恢复执行申请',
                         '发现被执行人新财产线索，申请恢复执行。',
                         final=True, finalized_by='陈晓东')
        make_submission(c5, '成都市中级人民法院执行局', -120, 'window', '陈晓东',
                        [(m_c5_res, vr, 2, 6)], status_='signed',
                        receiver='执行立案窗口',
                        receipt=('signed', '成执恢收字第0089号', '窗口',
                                 '立案恢复执行，案号(2026)川01执恢89号'))

        # c5 财产线索：已提交待签收
        m_c5_clue = Material.objects.create(case=c5, name='被执行人财产线索清单',
                                            category='线索材料', status='submitted',
                                            notes='新增两处房产线索')
        vc = add_version(m_c5_clue, 1, '陈晓东', '两处房产+一个银行账户',
                         '线索1：锦江区某商铺；线索2：高新区某住宅。',
                         final=True, finalized_by='陈晓东')
        make_submission(c5, '成都市中级人民法院执行局承办法官', -30, 'hand', '陈晓东',
                        [(m_c5_clue, vc, 1, 3)], status_='submitted',
                        receiver='执行法官 周法官',
                        note='当面向承办法官提交，待出具回执')

        # c5 限高申请：被退回补正、尚未重新提交（演示挂起状态）
        m_c5_delay = Material.objects.create(case=c5, name='限制消费申请书',
                                             category='申请书', status='returned',
                                             notes='法院要求补充被执行人法定代表人身份材料')
        vdl = add_version(m_c5_delay, 1, '陈晓东', '申请对被执行人法定代表人限高',
                          '请求采取限制消费措施。',
                          final=True, finalized_by='陈晓东')
        make_submission(c5, '成都市中级人民法院执行局', -8, 'online', '陈晓东',
                        [(m_c5_delay, vdl, 1, 2)], status_='returned',
                        receipt=('returned', '', '执行局',
                                 '请补充被执行人法定代表人身份证复印件后重新提交'))

        # c6 行政起诉状：已签收
        m_c6_sue = Material.objects.create(case=c6, name='行政起诉状',
                                           category='起诉状', status='signed')
        vs = add_version(m_c6_sue, 1, '刘雅芳', '撤销处罚之诉',
                         '请求撤销被告作出的行政处罚决定。',
                         final=True, finalized_by='刘雅芳')
        make_submission(c6, '北京市第三中级人民法院立案庭', -25, 'window', '刘雅芳',
                        [(m_c6_sue, vs, 2, 7)], status_='signed',
                        receipt=('signed', '(京03)立收字第20260771号', '立案窗口',
                                 '当场立案受理'))

        # c6 处罚决定证据：尚未定稿（占位版本，等待补录原件扫描件）
        m_c6_evi = Material.objects.create(case=c6, name='证据材料(处罚决定书等)',
                                           category='证据材料', status='draft')
        add_version(m_c6_evi, 1, '刘雅芳', '先登记，原件扫描后补传',
                    '', attach=False, backfilled=True)

        # c7 仲裁申请：v1 修改 -> v2 定稿，邮寄已签收
        m_c7_arb = Material.objects.create(case=c7, name='仲裁申请书',
                                           category='仲裁申请', status='signed')
        add_version(m_c7_arb, 1, '王志强', '仲裁申请初稿',
                    '请求支付股权转让款98万元。',
                    reviews=[('李静怡', 'revise', '仲裁请求补充违约金条款依据')])
        varb2 = add_version(m_c7_arb, 2, '王志强', '补充违约金依据',
                            '依据协议第7条主张逾期付款违约金。',
                            final=True, finalized_by='李静怡')
        make_submission(c7, '深圳国际仲裁院立案部', -15, 'post', '王志强',
                        [(m_c7_arb, varb2, 3, 11)], status_='signed',
                        receiver='仲裁院立案部',
                        receipt=('signed', '深国仲收〔2026〕078号', '立案秘书',
                                 '仲裁申请已受理'),
                        note='邮寄提交')

        # ---------- 期限提醒 ----------
        for case, title, dtype, days, done, notes in [
            (c1, '举证期限届满', 'evidence', 6, False, '逾期举证可能被法院不予采纳'),
            (c1, '开庭', 'hearing', 10, False, '第12法庭'),
            (c1, '缴纳案件受理费', 'payment', -85, True, '已缴纳'),
            (c2, '二审新证据提交期限', 'evidence', 9, False, '鉴定报告出具后立即提交'),
            (c2, '缴纳上诉费', 'payment', -50, True, '对方已缴纳'),
            (c3, '上诉期限届满(一审判决)', 'appeal', 3, False, '收到判决次日起10日内'),
            (c4, '管辖权异议裁定的上诉期限', 'appeal', -2, False, '已逾期，需与当事人确认是否放弃'),
            (c4, '举证期限届满', 'evidence', 16, False, ''),
            (c5, '补充财产线索', 'other', 12, False, '执行法官要求限期补充'),
            (c6, '举证期限届满', 'evidence', 7, False, '行政案件举证期限15日'),
            (c7, '仲裁答辩期届满', 'defense', 10, False, '被申请人答辩期'),
            (c7, '缴纳仲裁费余额', 'payment', 20, False, ''),
            (c8, '上诉期限', 'appeal', -250, True, '双方均未上诉，调解书生效'),
        ]:
            Deadline.objects.create(case=case, title=title, deadline_type=dtype,
                                    due_date=d(days), is_done=done, notes=notes)

        self.stdout.write(self.style.SUCCESS(
            f'样例数据已生成：{Lawyer.objects.count()}名律师、'
            f'{Party.objects.count()}个当事人、{Case.objects.count()}个案件、'
            f'{Hearing.objects.count()}次开庭、{Material.objects.count()}份材料、'
            f'{MaterialVersion.objects.count()}个版本、'
            f'{MaterialSubmission.objects.count()}个提交批次、'
            f'{Deadline.objects.count()}项期限'))
