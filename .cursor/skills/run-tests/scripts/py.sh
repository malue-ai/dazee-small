#!/usr/bin/env bash
set -euo pipefail

# 说明：
# - 按优先级查找可用的 Python 解释器
# - conda zeno > 项目本地 .venv > 当前环境 python3

# 1. conda env "zeno"
for CONDA_BASE in "${HOME}/miniconda3" "${HOME}/anaconda3"; do
  CANDIDATE="${CONDA_BASE}/envs/zeno/bin/python3"
  if [[ -x "${CANDIDATE}" ]]; then
    exec "${CANDIDATE}" "$@"
  fi
done

# 2. Project-local .venv (relative to repo root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
LOCAL_VENV="${REPO_ROOT}/.venv/bin/python3"
if [[ -x "${LOCAL_VENV}" ]]; then
  exec "${LOCAL_VENV}" "$@"
fi

# 3. Fallback to PATH python3
exec python3 "$@"
