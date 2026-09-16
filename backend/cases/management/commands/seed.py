"""内置样例案件数据：python manage.py seed"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from cases.models import (Bill, BillLine, Case, CaseLawyer, CaseParty,
                          CaseRate, Deadline, Expense, FeeAgreement, Hearing,
                          Lawyer, Material, Party, Payment, StageLog, TimeEntry)

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
        for model in (BillLine, Payment, Bill, TimeEntry, Expense, CaseRate,
                      FeeAgreement, Hearing, StageLog, Material, Deadline,
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

        # ---------- 材料提交 ----------
        for case, name, to, days, status_, notes in [
            (c1, '民事起诉状', '朝阳区人民法院', -90, 'accepted', ''),
            (c1, '证据清单及证据材料(共12组)', '朝阳区人民法院', -20, 'submitted', '含送货单、对账单、催款函'),
            (c1, '代理词', '朝阳区人民法院', None, 'pending', '开庭前提交'),
            (c2, '民事上诉状', '上海二中院', -55, 'accepted', ''),
            (c2, '二审新证据(货损鉴定报告)', '上海二中院', None, 'pending', '等待鉴定机构出具'),
            (c3, '取保候审申请书', '福田区人民检察院', -40, 'accepted', '已取保'),
            (c3, '辩护意见', '福田区人民法院', -22, 'submitted', ''),
            (c4, '管辖权异议申请书', '杭州市中级人民法院', -28, 'accepted', '法院已裁定移送'),
            (c4, '民事答辩状', '杭州市中级人民法院', -12, 'submitted', ''),
            (c5, '恢复执行申请书', '成都市中级人民法院', -120, 'accepted', ''),
            (c5, '被执行人财产线索清单', '成都市中级人民法院执行局', -30, 'submitted', '新增两处房产线索'),
            (c6, '行政起诉状', '北京市第三中级人民法院', -25, 'accepted', ''),
            (c6, '证据材料(处罚决定书等)', '北京市第三中级人民法院', None, 'pending', ''),
            (c7, '仲裁申请书', '深圳国际仲裁院', -15, 'accepted', ''),
        ]:
            Material.objects.create(
                case=case, name=name, submitted_to=to,
                submit_date=d(days) if days is not None else None,
                status=status_, notes=notes)

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

        # ---------- 收费约定与费率 ----------
        FeeAgreement.objects.create(case=c1, fee_type='hourly',
                                    notes='按承办律师实际工时结算，按月出账')
        FeeAgreement.objects.create(case=c2, fee_type='hourly',
                                    notes='二审阶段按工时收费')
        FeeAgreement.objects.create(case=c3, fee_type='fixed',
                                    fixed_amount=Decimal('150000'),
                                    notes='固定收费15万元，签约/开庭/结案三期各5万')
        FeeAgreement.objects.create(case=c5, fee_type='fixed',
                                    fixed_amount=Decimal('200000'),
                                    notes='固定收费20万元，恢复执行立案后先收50%')
        FeeAgreement.objects.create(case=c7, fee_type='hourly',
                                    notes='仲裁程序按工时收费')

        # 费率按生效日期记录：张伟民自 d(-20) 起费率由 2500 调整为 2800，
        # 此前提交的工时仍按 2500 计价
        for case, lname, rate, days in [
            (c1, '张伟民', '2500', -95), (c1, '张伟民', '2800', -20),
            (c1, '陈晓东', '1200', -95),
            (c2, '李静怡', '2000', -60),
            (c7, '李静怡', '2000', -15), (c7, '王志强', '1500', -15),
        ]:
            CaseRate.objects.create(case=case, lawyer=lawyers[lname],
                                    hourly_rate=Decimal(rate),
                                    effective_date=d(days))

        # ---------- 工时记录 ----------
        def time_entry(case, lname, days, hours, desc, rate, status_):
            return TimeEntry.objects.create(
                case=case, lawyer=lawyers[lname], work_date=d(days),
                hours=Decimal(hours), description=desc,
                hourly_rate=Decimal(rate) if rate else None, status=status_,
                approved_at=dt(days) if status_ != 'pending' else None)

        te1 = time_entry(c1, '张伟民', -90, '3', '案情分析、起诉状起草', '2500', 'billed')
        te2 = time_entry(c1, '张伟民', -80, '2', '证据梳理与补充取证指引', '2500', 'billed')
        te3 = time_entry(c1, '陈晓东', -75, '4', '证据清单整理(12组)', '1200', 'billed')
        time_entry(c1, '张伟民', -10, '2.5', '庭前会议及庭审方案讨论', '2800', 'approved')
        time_entry(c1, '陈晓东', -5, '3', '代理词起草', '1200', 'pending')
        time_entry(c1, '张伟民', -2, '1.5', '与当事人沟通庭审安排', '2800', 'pending')
        time_entry(c2, '李静怡', -50, '4', '二审答辩意见起草', '2000', 'approved')
        time_entry(c2, '李静怡', -30, '2', '一审卷宗阅卷', '2000', 'approved')
        time_entry(c7, '李静怡', -12, '2', '仲裁申请书起草', '2000', 'approved')
        time_entry(c7, '王志强', -8, '3', '证据交换材料准备', '1500', 'pending')

        # ---------- 代垫费用 ----------
        def expense(case, lname, days, cat, amount, desc, status_):
            return Expense.objects.create(
                case=case, lawyer=lawyers[lname], expense_date=d(days),
                category=cat, amount=Decimal(amount), description=desc,
                status=status_,
                approved_at=dt(days) if status_ != 'pending' else None)

        ex1 = expense(c1, '张伟民', -88, 'court_fee', '16300',
                      '一审案件受理费', 'billed')
        expense(c1, '陈晓东', -30, 'travel', '2360',
                '赴天津调取证据差旅费', 'approved')
        expense(c1, '陈晓东', -6, 'courier', '86', '证据材料快递费', 'pending')
        expense(c3, '王志强', -35, 'travel', '1800',
                '赴看守所会见差旅费', 'approved')
        ex2 = expense(c5, '陈晓东', -110, 'other', '3200',
                      '被执行人财产线索调查费', 'billed')

        # ---------- 分期账单与收款 ----------
        def make_bill(case, seq, title, issue_days, due_days, lines, payments,
                      reduction=None, reduction_reason=''):
            bill = Bill.objects.create(
                case=case, bill_number=f'B{case.id:04d}-{seq:03d}', title=title,
                issue_date=d(issue_days),
                due_date=d(due_days) if due_days is not None else None,
                reduction_amount=Decimal(reduction) if reduction else Decimal('0'),
                reduction_reason=reduction_reason)
            for line in lines:
                BillLine.objects.create(bill=bill, **line)
            for amount, days, method in payments:
                Payment.objects.create(bill=bill, amount=Decimal(amount),
                                       received_date=d(days), method=method)
            bill.refresh_status()
            return bill

        def time_line(entry):
            return dict(line_type='time',
                        description=f'{entry.lawyer.name} {entry.work_date} '
                                    f'{entry.description}',
                        quantity=entry.hours, unit_price=entry.hourly_rate,
                        amount=entry.amount, time_entry=entry)

        def expense_line(exp):
            return dict(line_type='expense',
                        description=f'{exp.get_category_display()}：{exp.description}',
                        amount=exp.amount, expense=exp)

        # c1 第一期：3条工时 + 代垫诉讼费，已减免3600并部分收款2万
        make_bill(c1, 1, '第一期（立案至8月工时及代垫费用）', -45, -30,
                  [time_line(te1), time_line(te2), time_line(te3),
                   expense_line(ex1)],
                  [('20000', -40, 'bank')],
                  reduction='3600', reduction_reason='长期合作客户优惠')
        # c3 第一期签约款已结清，第二期开庭前已出账待收
        make_bill(c3, 1, '第一期·委托签约款', -44, -34,
                  [dict(line_type='fixed', description='固定收费第一期（签约）',
                        amount=Decimal('50000'))],
                  [('30000', -40, 'bank'), ('20000', -20, 'bank')])
        make_bill(c3, 2, '第二期·一审开庭前', -14, 6,
                  [dict(line_type='fixed', description='固定收费第二期（一审开庭）',
                        amount=Decimal('50000'))],
                  [])
        # c5 第一期：固定收费50% + 财产调查费，已收5万
        make_bill(c5, 1, '第一期·恢复执行立案', -100, -70,
                  [dict(line_type='fixed', description='固定收费第一期（50%）',
                        amount=Decimal('100000')),
                   expense_line(ex2)],
                  [('50000', -60, 'bank')])

        self.stdout.write(self.style.SUCCESS(
            f'样例数据已生成：{Lawyer.objects.count()}名律师、'
            f'{Party.objects.count()}个当事人、{Case.objects.count()}个案件、'
            f'{Hearing.objects.count()}次开庭、{Material.objects.count()}份材料、'
            f'{Deadline.objects.count()}项期限、'
            f'{TimeEntry.objects.count()}条工时、{Expense.objects.count()}笔费用、'
            f'{Bill.objects.count()}张账单'))
