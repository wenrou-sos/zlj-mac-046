# 律所案件管理系统

基于 **Vue 3 + Django + PostgreSQL** 的律所案件管理系统，支持案件登记、当事人与承办律师管理、诉讼阶段跟踪、开庭安排、材料提交、期限提醒与利益冲突检查。

## 功能

| 模块 | 说明 |
|------|------|
| 工作台 | 案件统计、未来 30 天期限提醒（含逾期标红）、近期开庭时间线、案件阶段分布 |
| 案件管理 | 案件登记（案号/类型/案由/法院/标的额）、筛选搜索、编辑删除 |
| 案件详情 | 当事人（诉讼地位/是否本所客户）、承办律师（主办/协办）、诉讼阶段流转时间线、开庭安排、材料提交记录、期限管理 |
| 当事人管理 | 自然人/法人档案，证件号、联系方式 |
| 律师管理 | 执业证号、职称、联系方式 |
| 利益冲突检查 | ① 全局检索：按姓名/名称/证件号检查当事人在本所的全部涉诉记录，输出高/中/低风险结论；② 添加当事人到案件时自动预检，发现直接冲突（如系本所在办案件客户）将阻止保存 |
| 律师费与账单 | 按案件约定固定收费或按工时收费；律师提交工时与代垫费用，负责人核准后生成分期账单；费率按生效日管理、变更只影响后续工作，已出账项目保留当时计价依据；同一工时/费用不可重复出账；支持部分收款、费用减免与冲正，有收款记录的账单不可删除；案件详情可追溯工作记录→应收→已收→未收，标的额与律师费分开核算 |
| 登录与权限 | 会话登录（管理员 admin/admin123，律师 用户名/lawyer123，如 zhangwm）；匿名只读；律师只能以本人名义提交工时/费用；核准、出账、收款、减免、冲正仅限本案主办律师或管理员；收款记录不可删除，错误以红冲（负数记录）更正；固定收费期款累计不得超过约定总额 |

## 快速启动

```bash
./start.sh
```

启动后访问：

- 系统入口：http://127.0.0.1:8000/
- API 浏览：http://127.0.0.1:8000/api/
- 管理后台：http://127.0.0.1:8000/admin/

> 数据库为空时会自动导入样例数据（6 名律师、15 个当事人、8 个案件及配套开庭/材料/期限）。
> 手动重置样例数据：`venv/bin/python backend/manage.py seed`

## 技术栈与结构

```
├── backend/            Django 5 + DRF
│   ├── config/         设置(PostgreSQL 连接、CORS、静态托管)
│   └── cases/          核心应用
│       ├── models.py       Lawyer / Party / Case / CaseParty / CaseLawyer
│       │                   Hearing / StageLog / Material / Deadline
│       │                   FeeAgreement / CaseRate / TimeEntry / Expense
│       │                   Bill / BillLine / Payment
│       ├── views.py        REST ViewSet + 工作台统计 + 冲突检查
│       └── management/commands/seed.py   样例数据
├── frontend/           Vue 3 + Vite + Element Plus + vue-router + axios
│   └── src/views/      工作台 / 案件列表 / 案件详情 / 当事人 / 律师 / 冲突检查
├── pgsql/              PostgreSQL 17(用户态运行,无需 root)
├── pgdata/             数据库数据目录
└── venv/               Python 虚拟环境
```

前端构建产物由 Django 直接托管（`frontend/dist` → `/static/`），单端口 8000 即可运行；
开发调试也可前后端分离：`cd frontend && npm run dev`（Vite 已配置 `/api` 代理到 8000）。

## 主要 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/dashboard/` | 工作台统计 |
| GET/POST | `/api/cases/` | 案件列表/新建（支持 stage、case_type、search 过滤） |
| GET | `/api/cases/{id}/` | 案件详情（含当事人/律师/阶段/开庭/材料/期限） |
| POST | `/api/cases/{id}/conflict-check/` | 添加当事人前的冲突预检 |
| GET | `/api/conflict-check/?name=&id_number=` | 全局利益冲突检索 |
| GET/POST | `/api/parties/` `/api/lawyers/` | 当事人 / 律师 |
| GET/POST | `/api/case-parties/` `/api/case-lawyers/` | 案件-当事人 / 案件-律师关联 |
| GET/POST | `/api/hearings/` `/api/stage-logs/` `/api/materials/` `/api/deadlines/` | 开庭 / 阶段 / 材料 / 期限（支持 `?case={id}` 过滤） |
| GET | `/api/deadlines/?upcoming=1&days=30` | 未来 N 天待办期限 |
| GET | `/api/cases/{id}/finance/` | 案件财务全景：约定/费率/工时/费用/账单 + 应收/已收/未收汇总 |
| GET/POST/PATCH | `/api/fee-agreements/` | 收费约定（固定收费/按工时收费，一案一份） |
| GET/POST | `/api/case-rates/` | 计时费率（按生效日期，变更不影响既往） |
| GET/POST/PATCH | `/api/time-entries/` `/api/expenses/` | 工时 / 代垫费用（提交时快照费率） |
| POST | `/api/time-entries/{id}/approve/` `/reject/` | 核准 / 退回（费用同） |
| GET/POST/DELETE | `/api/bills/` | 账单：POST 勾选已核准工时/费用或固定期款生成；已收款账单禁止删除 |
| POST | `/api/bills/{id}/reduction/` `/void/` | 费用减免 / 冲正（自动生成负数退款、释放工时费用） |
| GET/POST/DELETE | `/api/payments/` | 收款记录（部分收款，不可超额；记录不可删除） |
| POST | `/api/payments/{id}/reverse/` | 红冲某笔收款（生成等额负数记录） |
| POST | `/api/auth/login/` `/api/auth/logout/` | 登录 / 退出 |
| GET | `/api/auth/me/` | 当前登录用户（匿名返回 null） |
