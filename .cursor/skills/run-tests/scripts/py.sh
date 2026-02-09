#!/usr/bin/env bash
set -euo pipefail

# 说明：
# - 优先使用仓库规则指定的虚拟环境 python（如果存在）
# - 否则回退到当前环境的 python3

VENV_PY="${VENV_PYTHON:-.venv/bin/python3}"

if [[ -x "${VENV_PY}" ]]; then
  exec "${VENV_PY}" "$@"
fi

exec python3 "$@"

