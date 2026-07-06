#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "${PROJECT_ROOT}/.." && pwd)"

resolve_agent_path() {
  case "${UNION_AGENT_TARGET:-dev}" in
    dev|development|test)
      echo "${WORKSPACE_ROOT}/union-lab-union-agent-git-https"
      ;;
    runtime|prod|production|formal)
      echo "${WORKSPACE_ROOT}/union-lab-union-agent-davinci-runtime"
      ;;
    *)
      echo "未知 UNION_AGENT_TARGET=${UNION_AGENT_TARGET}，请使用 dev 或 runtime" >&2
      exit 2
      ;;
  esac
}

resolve_database_name() {
  case "${UNION_AGENT_TARGET:-dev}" in
    dev|development|test)
      echo "union_dev"
      ;;
    runtime|prod|production|formal)
      echo "union_prod"
      ;;
    *)
      echo "未知 UNION_AGENT_TARGET=${UNION_AGENT_TARGET}，请使用 dev 或 runtime" >&2
      exit 2
      ;;
  esac
}

export UNION_AGENT_PATH="${UNION_AGENT_PATH:-$(resolve_agent_path)}"
export UNION_KNOWLEDGEBASE_PATH="${UNION_KNOWLEDGEBASE_PATH:-${PROJECT_ROOT}/../union-lab-union-knowledgebase-git-https}"
export DAVINCI_TASK_DATABASE_NAME="${DAVINCI_TASK_DATABASE_NAME:-$(resolve_database_name)}"
export DAVINCI_DATABASE_NAME="${DAVINCI_DATABASE_NAME:-${DAVINCI_TASK_DATABASE_NAME}}"
export DAVINCI_DB_SEARCH_PATH="${DAVINCI_DB_SEARCH_PATH:-davinci,public,app}"
export DAVINCI_CN_IMAGE_ENABLED="${DAVINCI_CN_IMAGE_ENABLED:-false}"
export PYTHONPATH="${PROJECT_ROOT}/src:${PYTHONPATH:-}"

PYTHON_BIN="${UNION_AGENT_PYTHON:-${UNION_AGENT_PATH}/.venv/bin/python}"
exec "${PYTHON_BIN}" -m union_davinci_task "$@"
