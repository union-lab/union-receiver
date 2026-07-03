#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_AGENT_PATH="$(cd "${PROJECT_ROOT}/../union-lab-union-agent-git-https" && pwd)"

export UNION_AGENT_PATH="${UNION_AGENT_PATH:-${DEFAULT_AGENT_PATH}}"
export UNION_KNOWLEDGEBASE_PATH="${UNION_KNOWLEDGEBASE_PATH:-${PROJECT_ROOT}/../union-lab-union-knowledgebase-git-https}"
export DAVINCI_CN_IMAGE_ENABLED="${DAVINCI_CN_IMAGE_ENABLED:-false}"
export PYTHONPATH="${PROJECT_ROOT}/src:${PYTHONPATH:-}"

PYTHON_BIN="${UNION_AGENT_PYTHON:-${UNION_AGENT_PATH}/.venv/bin/python}"
exec "${PYTHON_BIN}" -m union_davinci_task "$@"
