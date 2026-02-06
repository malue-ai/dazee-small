#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 默认与常用本地开发一致；如需自定义参数，直接在命令后追加即可：
# bash .cursor/skills/run-tests/scripts/uvicorn.sh --port 9000

"${SCRIPT_DIR}/py.sh" -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload "$@"

