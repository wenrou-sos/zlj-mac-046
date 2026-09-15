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
| 案件交接 | 律师离岗/更换主办时发起交接，自动汇总未办期限、后续开庭、待提交材料形成清单，明确交出人、接收人及每项待办去向；接收人逐项核对后确认接管，支持退回补充与取消。交接期间新增/变更的待办须补入清单并重新核对（过期清单不能完成交接）；完成前原责任人保留可追溯，完成后工作台按新负责人归集，历史办案记录保留原承办人 |

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
│       │                   CaseHandover / HandoverItem / HandoverLog
│       ├── handovers.py    交接清单快照、防过期比对、提交/退回/确认/取消状态机
│       ├── views.py        REST ViewSet + 工作台统计 + 冲突检查 + 案件交接
│       └── management/commands/seed.py   样例数据
├── frontend/           Vue 3 + Vite + Element Plus + vue-router + axios
│   └── src/views/      工作台 / 案件列表 / 案件详情 / 当事人 / 律师 / 冲突检查
│                       案件交接列表 / 交接处理
├── pgsql/              PostgreSQL 17(用户态运行,无需 root)
├── pgdata/             数据库数据目录
└── venv/               Python 虚拟环境
```

前端构建产物由 Django 直接托管（`frontend/dist` → `/static/`），单端口 8000 即可运行；
开发调试也可前后端分离：`cd frontend && npm run dev`（Vite 已配置 `/api` 代理到 8000）。

## 主要 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/dashboard/` | 工作台统计（可带 `?lawyer={id}` 按律师个人视角归集，含待我核对的交接） |
| GET/POST | `/api/cases/` | 案件列表/新建（支持 stage、case_type、search 过滤） |
| GET | `/api/cases/{id}/` | 案件详情（含当事人/律师/阶段/开庭/材料/期限、进行中交接与交接历史） |
| POST | `/api/cases/{id}/conflict-check/` | 添加当事人前的冲突预检 |
| POST | `/api/cases/{id}/handovers/initiate/` | 发起交接（自动汇总待办生成清单，`submit=true` 直接提交核对） |
| GET | `/api/handovers/` | 交接列表（支持 `?case=&lawyer=&status=&active=1`） |
| POST | `/api/handovers/{id}/submit/ return/ confirm/ cancel/ refresh/` | 提交核对 / 退回补充 / 确认接管 / 取消 / 补入最新待办 |
| POST | `/api/handovers/{id}/items/{itemId}/check/` | 接收人逐项核对（含备注） |
| POST | `/api/handovers/{id}/items/{itemId}/destination/` | 明确去向：接管 / 原责任人继续 / 无需办理 |
| GET | `/api/conflict-check/?name=&id_number=` | 全局利益冲突检索 |
| GET/POST | `/api/parties/` `/api/lawyers/` | 当事人 / 律师 |
| GET/POST | `/api/case-parties/` `/api/case-lawyers/` | 案件-当事人 / 案件-律师关联 |
| GET/POST | `/api/hearings/` `/api/stage-logs/` `/api/materials/` `/api/deadlines/` | 开庭 / 阶段 / 材料 / 期限（支持 `?case={id}` 过滤） |
| GET | `/api/deadlines/?upcoming=1&days=30` | 未来 N 天待办期限 |
