#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-runtime}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${PROJECT_ROOT}/logs/union-davinci-task-${TARGET}.log"

case "${TARGET}" in
  dev)
    DATABASE_NAME="union_dev"
    ;;
  runtime)
    DATABASE_NAME="union_prod"
    ;;
  *)
    echo "用法：$0 dev|runtime" >&2
    exit 2
    ;;
esac

mkdir -p "${PROJECT_ROOT}/logs"
screen -S union-davinci-task -X quit >/dev/null 2>&1 || true
pkill -f "python.*-m union_davinci_task" >/dev/null 2>&1 || true
sleep 1
pkill -9 -f "python.*-m union_davinci_task" >/dev/null 2>&1 || true

screen -dmS union-davinci-task bash -lc "
  cd '${PROJECT_ROOT}'
  UNION_AGENT_TARGET='${TARGET}' \
  UNION_AGENT_ENV_FILE='.env.union-dev' \
  DAVINCI_TASK_DATABASE_NAME='${DATABASE_NAME}' \
  DAVINCI_DATABASE_NAME='${DATABASE_NAME}' \
  DAVINCI_DB_SEARCH_PATH='davinci,public,app' \
  DAVINCI_TASK_INTERVAL_SECONDS='300' \
  DAVINCI_CN_IMAGE_ENABLED='false' \
  bash run.sh >> '${LOG_FILE}' 2>&1
"

echo "达芬奇工单 worker 已切换到 ${TARGET}，日志：${LOG_FILE}"
