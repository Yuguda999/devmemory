#!/bin/sh
# DevMemory REST container entrypoint.
#
# 1. Managed platforms (Render, Cloud Run) inject $PORT — honour it, else fall
#    back to the configured DEVMEMORY_PORT (default 8765 for docker-compose).
# 2. Bring the database schema up to date before serving. Idempotent: safe to
#    run on every boot/restart.
# 3. Hand off (exec) to the REST server so it becomes PID 1 and receives signals.
set -e

export DEVMEMORY_PORT="${PORT:-${DEVMEMORY_PORT:-8765}}"

echo "[devmemory] alembic upgrade head"
alembic upgrade head

echo "[devmemory] starting REST API on 0.0.0.0:${DEVMEMORY_PORT}"
exec devmemory --rest --port "${DEVMEMORY_PORT}"
