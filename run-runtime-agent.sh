#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export UNION_AGENT_TARGET=runtime
exec "${SCRIPT_DIR}/run.sh" "$@"
