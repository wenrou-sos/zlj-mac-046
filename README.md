# 律所案件管理系统

基于 **Vue 3 + Django + PostgreSQL** 的律所案件管理系统，支持案件登记、当事人与承办律师管理、诉讼阶段跟踪、开庭安排、材料提交、期限提醒与利益冲突检查。

## 功能

| 模块 | 说明 |
|------|------|
| 工作台 | 案件统计、未来 30 天期限提醒（含逾期标红）、近期开庭时间线、案件阶段分布 |
| 案件管理 | 案件登记（案号/类型/案由/法院/标的额）、筛选搜索、编辑删除 |
| 案件详情 | 当事人（诉讼地位/是否本所客户）、承办律师（主办/协办）、诉讼阶段流转时间线、开庭安排、**材料版本/审阅/定稿/提交回执**、期限管理 |
| 当事人管理 | 自然人/法人档案，证件号、联系方式 |
| 律师管理 | 执业证号、职称、联系方式 |
| 利益冲突检查 | ① 全局检索：按姓名/名称/证件号检查当事人在本所的全部涉诉记录，输出高/中/低风险结论；② 添加当事人到案件时自动预检，发现直接冲突（如系本所在办案件客户）将阻止保存 |

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
│       │                   Hearing / StageLog
│       │                   Material(材料主档) / MaterialVersion(不可变版本)
│       │                   MaterialReview(审阅意见)
│       │                   MaterialSubmission / SubmissionItem(提交批次与清单)
│       │                   SubmissionReceipt(签收/退回补正回执) / Deadline
│       ├── views.py        REST ViewSet + 定稿动作 + 工作台统计 + 冲突检查
│       └── management/commands/seed.py   样例数据（含多版本/退回补正/重新提交样例）
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
| GET/POST | `/api/material-versions/` | 材料版本（multipart 上传；支持 `?material=`/`?case=`），版本不可改、不可删 |
| POST | `/api/material-versions/{id}/finalize/` | 定稿确认 `{operator}`；已随未退回批次提交的版本拒绝替换 |
| GET/POST | `/api/material-reviews/` | 版本审阅意见（只追加；支持 `?version=`/`?material=`） |
| GET/POST | `/api/submissions/` | 提交批次：创建时传 `{case, submitted_to, method, submit_date, created_by, items:[{version_id,copies,pages}], resubmitted_from?}`，清单与版本快照固定 |
| GET/POST | `/api/submission-receipts/` | 签收回执 / 退回补正回执（可带扫描件）；登记后自动联动批次与材料状态 |
| GET | `/media/materials/...` `/media/receipts/...` | 版本附件 / 回执附件下载 |
| GET | `/api/deadlines/?upcoming=1&days=30` | 未来 N 天待办期限 |

## 材料版本与提交管理规则

- **版本不可变**：`MaterialVersion` 只增不改；版本号在数据库行锁内分配并有 `(材料,版本号)` 唯一约束，多人同时上传各自生成 v2/v3，互不覆盖。
- **失败不留痕**：空文件（0 字节）/超 100MB/缺附件的上传直接 400；入库异常时事务回滚并清理已写文件，不会出现没有有效附件的版本记录。
- **定稿确认**：仅定稿版本可进入提交清单；已随「未退回」批次提交的定稿不得被替换（409），退回补正后定稿允许前移到补正版。
- **提交固定快照**：`SubmissionItem` 冗余材料名/版本号/文件名快照，后续新版本不影响历史批次；清单版本必须属于本案、已定稿且有附件。
- **回执与状态联动**：签收回执 → 批次/材料「已签收」；退回回执 → 「退回补正」；重新提交通过 `resubmitted_from` 关联原批次，完整保留退回与重提链路。
- **历史可查可补录**：历史纸质材料可先建无附件的「历史补录」版本（不可定稿/提交），拿到扫描件后补传新版本即可；有提交记录的材料禁止删除，版本与回执端点不提供修改/删除。
