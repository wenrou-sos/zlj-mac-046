#!/bin/bash
# 律所案件管理系统 - 一键启动脚本
# 用法: ./start.sh
set -e
cd "$(dirname "$0")"
ROOT=$(pwd)

# 确保用户态 PostgreSQL 运行目录完整且权限安全
chmod 700 "$ROOT/pgdata"
mkdir -p "$ROOT/pgdata"/{pg_notify,pg_stat,pg_stat_tmp,pg_serial,pg_snapshots,pg_tblspc,pg_replslot,pg_twophase,pg_dynshmem,pg_commit_timestamp,pg_wal/archive_status,pg_wal/summaries,pg_logical/snapshots,pg_logical/mappings}
chmod 700 "$ROOT/pgdata"/{pg_notify,pg_stat,pg_stat_tmp,pg_serial,pg_snapshots,pg_tblspc,pg_replslot,pg_twophase,pg_dynshmem,pg_commit_timestamp,pg_wal/archive_status,pg_wal/summaries,pg_logical/snapshots,pg_logical/mappings}

# 1. 启动 PostgreSQL(用户态,端口 5432)
if ! ./pgsql/bin/pg_ctl -D pgdata status > /dev/null 2>&1; then
  echo ">> 启动 PostgreSQL..."
  ./pgsql/bin/pg_ctl -D pgdata -l pg.log -o "-p 5432 -k $ROOT" start
  sleep 2
else
  echo ">> PostgreSQL 已在运行"
fi

# 2. 数据库迁移
echo ">> 执行数据库迁移..."
./venv/bin/python backend/manage.py migrate --run-syncdb > /dev/null

# 3. 如数据库为空则导入样例数据
CASE_COUNT=$(./venv/bin/python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import sys; sys.path.insert(0, 'backend')
django.setup()
from cases.models import Case
print(Case.objects.count())
")
if [ "$CASE_COUNT" = "0" ]; then
  echo ">> 导入样例数据..."
  ./venv/bin/python backend/manage.py seed
fi

# 4. 启动 Django(同时托管 API 与前端静态文件)
echo ""
echo "==============================================="
echo "  系统已启动:  http://127.0.0.1:8000/"
echo "  API 文档:    http://127.0.0.1:8000/api/"
echo "  管理后台:    http://127.0.0.1:8000/admin/"
echo "==============================================="
exec ./venv/bin/python backend/manage.py runserver 0.0.0.0:8000
