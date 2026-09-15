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
| 冲突复核单 | 把检查结果固化为**可追溯复核单**：冻结当事人身份、拟承接涉案关系与风险依据快照；指定独立复核人**批准 / 拒绝 / 退回补充材料**（申请人不能自审）。**本所明确禁止的冲突（《律师法》第39条在办客户对抗代理）一律不得批准**；可有条件豁免的冲突，批准时必须登记**例外授权依据与适用期限**。承接时复核结论是否仍有效（未使用/未到期/关系指纹未变），相关关系变更后自动作废旧结论并进入**重新复核**，旧结论与退回全过程继续可查 |

> 复核与承接需要身份：请在系统右上角选择"当前律师"（写入 `X-Lawyer-Id` 请求头并持久化）。
> 承接（向案件添加当事人）必须凭**当前仍有效的批准复核单**，在案件详情页"添加当事人"时选择。

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
│       │                   ConflictReview / ConflictReviewMaterial / ConflictReviewLog
│       ├── conflicts.py    冲突评估引擎（禁止性冲突 / 需例外授权 / 关系指纹）
│       ├── signals.py      涉案关系变更后自动使旧复核结论失效
│       ├── views.py        REST ViewSet + 工作台统计 + 冲突检查 + 冲突复核审批
│       └── management/commands/seed.py   样例数据
├── frontend/           Vue 3 + Vite + Element Plus + vue-router + axios
│   └── src/views/      工作台 / 案件列表 / 案件详情 / 当事人 / 律师
│                       冲突检查 / 冲突复核单列表 / 复核单详情
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
| POST | `/api/cases/{id}/conflict-check/` | 添加当事人前的冲突预检（只读即时） |
| GET | `/api/conflict-check/?name=&id_number=` | 全局利益冲突检索 |
| GET | `/api/conflict-reviews/` | 复核单列表（支持 status、risk_level、case、party、scope=mine_apply/mine_review） |
| POST | `/api/conflict-reviews/apply/` | 发起复核申请（冻结身份/关系/风险快照、指定复核人、随附材料） |
| POST | `/api/conflict-reviews/{id}/decide/` | 指定复核人 批准/拒绝/退回（approve/reject/return；批准可豁免冲突须带 exception_basis+exception_expire_date） |
| POST | `/api/conflict-reviews/{id}/supplement/` | 退回后申请人补充材料，重新进入待复核 |
| POST | `/api/conflict-reviews/{id}/recheck/` | 关系变更后基于旧单发起重新复核（旧单作废旧并指向新单） |
| POST | `/api/case-parties/` | 承接闸门：必须携带 `review_id` 或 `review_number`，校验批准结论当前有效 |
| GET/POST | `/api/parties/` `/api/lawyers/` | 当事人 / 律师 |
| GET/POST | `/api/case-parties/` `/api/case-lawyers/` | 案件-当事人 / 案件-律师关联 |
| GET/POST | `/api/hearings/` `/api/stage-logs/` `/api/materials/` `/api/deadlines/` | 开庭 / 阶段 / 材料 / 期限（支持 `?case={id}` 过滤） |
| GET | `/api/deadlines/?upcoming=1&days=30` | 未来 N 天待办期限 |
