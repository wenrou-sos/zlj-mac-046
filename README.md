# 律所案件管理系统

基于 **Vue 3 + Django + PostgreSQL** 的律所案件管理系统，支持案件登记、当事人与承办律师管理、诉讼阶段跟踪、开庭安排、材料提交、期限提醒、利益冲突检查，并内置**多团队协作的按案件访问控制**（账号角色、按案授权、限时借阅、立即撤权、统一可见范围与审计留痕）。

## 功能

| 模块 | 说明 |
|------|------|
| 账号与权限 | 管理员 / 主办律师 / 协办律师 / 只读助理四类账号；律师账号绑定律师档案后随承办关系自动获得团队授权 |
| 按案授权 | 案件详情「访问授权」页可对任意账号授予主办/协办/只读权限，支持 7/30 天及自定义**限时借阅**，到期自动失效，也可**立即撤权** |
| 统一可见范围 | 案件列表搜索、详情直访（越权返回 404）、工作台统计、开庭/期限/材料、当事人档案、利益冲突检索全部按同一套授权过滤 |
| 当事人隔离 | 同一当事人参与多个案件时，只展示当前账号有权查看案件中的涉案信息，不泄露其在其他团队案件中的存在 |
| 审计日志 | 登录/登录失败、授权、撤权、借阅到期、管理员与借阅账号查看案件详情、冲突检索、删除案件均留痕（管理员页面可筛选/分页） |
| 工作台 | 案件统计、未来 30 天期限提醒（含逾期标红）、近期开庭时间线、案件阶段分布（均按可见范围） |
| 案件管理 | 案件登记（案号/类型/案由/法院/标的额）、筛选搜索、编辑删除（仅管理员可删除） |
| 案件详情 | 当事人（诉讼地位/是否本所客户）、承办律师（主办/协办）、诉讼阶段流转时间线、开庭安排、材料提交记录、期限管理、访问授权 |
| 当事人管理 | 自然人/法人档案，证件号、联系方式；仅展示可见案件涉及的当事人，档案维护仅管理员 |
| 律师管理 | 执业证号、职称、联系方式（仅管理员可维护） |
| 利益冲突检查 | ① 全局检索：按姓名/名称/证件号检查当事人在**可见案件**中的涉诉记录；② 添加当事人到案件时自动预检 |

## 快速启动

```bash
./start.sh
```

启动后访问：

- 系统入口：http://127.0.0.1:8000/
- API 浏览：http://127.0.0.1:8000/api/
- 管理后台：http://127.0.0.1:8000/admin/

> 数据库为空时会自动导入样例数据（6 名律师、15 个当事人、8 个案件及配套开庭/材料/期限，以及 10 个演示账号）。
> 手动重置样例数据：`venv/bin/python backend/manage.py seed`

### 演示账号（密码均为 `123456`）

| 账号 | 角色 | 可见范围 |
|------|------|----------|
| `admin` | 管理员 | 全部案件、账号权限与审计日志 |
| `zhangwm` `lijy` `wangzq` | 主办律师 | 本人承办案件（如张伟民可见 c1/c4） |
| `chenxd` `liuyf` `zhaogq` | 协办律师 | 本人协办案件（可编辑、不可删案/管档） |
| `assistant1` | 只读助理 | c2 限时借阅 14 天 |
| `assistant2` | 只读助理 | c7 借阅已到期（自动失效，可见 0 案） |
| `assistant3` | 只读助理 | c1 授权后被立即撤权（可见 0 案） |

## 技术栈与结构

```
├── backend/            Django 5 + DRF
│   ├── config/         设置(PostgreSQL 连接、CORS/CSRF、会话认证、静态托管)
│   └── cases/          核心应用
│       ├── models.py       UserProfile / CaseAccess / AuditLog
│       │                   Lawyer / Party / Case / CaseParty / CaseLawyer
│       │                   Hearing / StageLog / Material / Deadline
│       ├── services.py     可见范围与编辑权限的唯一判定入口、审计写入
│       ├── signals.py      承办关系 <-> 团队授权自动联动
│       ├── permissions.py  DRF 权限类
│       ├── views.py        认证/账号/授权/审计 ViewSet + 工作台 + 冲突检查
│       └── management/commands/seed.py   样例数据（含演示账号）
├── frontend/           Vue 3 + Vite + Element Plus + vue-router + axios
│   └── src/views/      登录 / 工作台 / 案件列表 / 案件详情(含访问授权)
│                       / 当事人 / 律师 / 冲突检查 / 账号权限 / 审计日志
├── pgsql/              PostgreSQL 17(用户态运行,无需 root)
├── pgdata/             数据库数据目录
└── venv/               Python 虚拟环境
```

前端构建产物由 Django 直接托管（`frontend/dist` → `/static/`），单端口 8000 即可运行；
开发调试也可前后端分离：`cd frontend && npm run dev`（Vite 已配置 `/api` 代理到 8000）。

## 主要 API（除登录外均需登录会话 + CSRF 令牌）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/auth/me/` `/api/auth/login/` `/api/auth/logout/` | 当前登录态 / 登录 / 退出 |
| GET/POST/PUT/PATCH | `/api/accounts/` `/api/accounts/{id}/reset-password/` | 账号管理（管理员） |
| GET | `/api/access/?case={id}` | 案件授权列表；非管理员仅见本人授权与自己主办案件的授权 |
| GET | `/api/access/grantable-users/?case={id}` | 可授权账号精简列表（管理员/本案主办） |
| POST | `/api/access/grant/` | 按案授权/限时借阅 `{case,user_id,role,expires_at?}` |
| POST | `/api/access/{id}/revoke/` `/restore/` | 立即撤权 / 恢复 |
| GET | `/api/audit-logs/` | 审计日志（管理员，支持 action/actor/日期过滤与分页） |
| GET | `/api/dashboard/` | 工作台统计（按可见范围） |
| GET/POST | `/api/cases/` | 案件列表/新建（列表/搜索按可见范围） |
| GET | `/api/cases/{id}/` | 案件详情（越权返回 404，不泄露存在性） |
| POST | `/api/cases/{id}/conflict-check/` | 添加当事人前的冲突预检（仅可见案件） |
| GET | `/api/conflict-check/?name=&id_number=` | 全局利益冲突检索（仅可见案件） |
| GET/POST | `/api/parties/` `/api/lawyers/` | 当事人（仅可见案件涉及）/ 律师 |
| GET/POST | `/api/case-parties/` `/api/case-lawyers/` | 案件-当事人 / 案件-律师关联（写操作需案件编辑权限） |
| GET/POST | `/api/hearings/` `/api/stage-logs/` `/api/materials/` `/api/deadlines/` | 开庭/阶段/材料/期限（统一按可见案件过滤，支持 `?case={id}`） |
| GET | `/api/deadlines/?upcoming=1&days=30` | 未来 N 天待办期限（按可见范围） |
