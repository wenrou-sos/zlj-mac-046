# 律所案件管理系统

基于 **Vue 3 + Django + PostgreSQL** 的律所案件管理系统，支持案件登记、当事人与承办律师管理、诉讼阶段跟踪、开庭安排、材料提交、期限提醒与利益冲突检查。

## 功能

| 模块 | 说明 |
|------|------|
| 工作台 | 案件统计、未来 30 天期限提醒（含逾期标红）、近期开庭时间线、案件阶段分布 |
| 案件管理 | 案件登记（案号/类型/案由/法院/标的额）、筛选搜索、编辑删除 |
| 案件详情 | 当事人（诉讼地位/是否本所客户）、承办律师（主办/协办）、诉讼阶段流转时间线、开庭安排、材料提交记录、期限管理 |
| 当事人管理 | 自然人/法人档案，证件号、联系方式、原档来源；重复档案核实、主档合并、旧名与合并记录追溯 |
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
│       ├── models.py       Lawyer / Party / PartyAlias / PartyMergeRecord
│       │                   Case / CaseParty / CaseLawyer
│       │                   Hearing / StageLog / Material / Deadline
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
| GET | `/api/parties/` `/api/lawyers/` | 当事人 / 律师（当事人默认仅列有效主档，`include_merged=true` 可含旧档） |
| GET | `/api/parties/duplicates/` | 按证件号、名称+联系方式、同名规则生成待核实重复档案分组 |
| POST | `/api/parties/merge/` | 选择主档并逐项确认字段与涉案关系后原子合并 |
| GET | `/api/parties/{id}/merge-history/` | 旧档定位主档、查看保留旧名、原档来源与合并记录 |
| GET/POST | `/api/case-parties/` `/api/case-lawyers/` | 案件-当事人 / 案件-律师关联 |
| GET/POST | `/api/hearings/` `/api/stage-logs/` `/api/materials/` `/api/deadlines/` | 开庭 / 阶段 / 材料 / 期限（支持 `?case={id}` 过滤） |
| GET | `/api/deadlines/?upcoming=1&days=30` | 未来 N 天待办期限 |
