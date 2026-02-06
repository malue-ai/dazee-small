#!/bin/bash
#
# ZenFlux Agent 桌面应用一键构建脚本
#
# 构建流程:
#   1. 检查依赖
#   2. PyInstaller 打包 Python 后端
#   3. Tauri 打包（前端 + Rust 壳 + sidecar）
#
# 用法:
#   bash scripts/build_app.sh           # 完整构建
#   bash scripts/build_app.sh --skip-backend  # 仅构建前端+Tauri（跳过 PyInstaller）
#   bash scripts/build_app.sh --clean   # 清理后重新构建
#

set -e

# ==================== 配置 ====================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

SKIP_BACKEND=false
CLEAN=false

for arg in "$@"; do
  case $arg in
    --skip-backend) SKIP_BACKEND=true ;;
    --clean) CLEAN=true ;;
  esac
done

# ==================== 辅助函数 ====================

info() { echo "===> $1"; }
warn() { echo "WARN: $1"; }
fail() { echo "ERROR: $1"; exit 1; }

check_cmd() {
  if ! command -v "$1" &> /dev/null; then
    fail "$1 未安装，请先安装: $2"
  fi
}

# ==================== 依赖检查 ====================

info "检查构建依赖..."

check_cmd "python3" "brew install python3 / https://python.org"
check_cmd "node" "brew install node / https://nodejs.org"
check_cmd "npm" "brew install node / https://nodejs.org"
check_cmd "cargo" "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"

if [ "$SKIP_BACKEND" = false ]; then
  python3 -c "import PyInstaller" 2>/dev/null || fail "PyInstaller 未安装: pip install pyinstaller"
fi

info "依赖检查通过"

# ==================== 清理（可选）====================

if [ "$CLEAN" = true ]; then
  info "清理构建产物..."
  rm -rf "$PROJECT_ROOT/build" "$PROJECT_ROOT/dist"
  rm -rf "$FRONTEND_DIR/dist"
  rm -rf "$FRONTEND_DIR/src-tauri/target"
  rm -rf "$FRONTEND_DIR/src-tauri/binaries/zenflux-backend-*"
  info "清理完成"
fi

# ==================== Step 1: 构建 Python 后端 ====================

if [ "$SKIP_BACKEND" = false ]; then
  info "Step 1/2: 构建 Python 后端 (PyInstaller)..."
  cd "$PROJECT_ROOT"
  python3 scripts/build_backend.py
  info "Python 后端构建完成"
else
  info "Step 1/2: 跳过 Python 后端构建"
  
  # 检查 sidecar 二进制是否存在
  BINARY_COUNT=$(ls "$FRONTEND_DIR/src-tauri/binaries/zenflux-backend-"* 2>/dev/null | wc -l)
  if [ "$BINARY_COUNT" -eq 0 ]; then
    warn "binaries/ 目录中没有 sidecar 二进制文件"
    warn "如果要构建完整应用，请去掉 --skip-backend 参数"
  fi
fi

# ==================== Step 2: 构建 Tauri 应用 ====================

info "Step 2/2: 构建 Tauri 应用..."
cd "$FRONTEND_DIR"

# 安装前端依赖
if [ ! -d "node_modules" ]; then
  info "安装前端依赖..."
  npm install
fi

# 构建 Tauri
npm run tauri:build

info ""
info "============================================"
info "  构建完成!"
info "============================================"
info ""

# 显示产物路径
if [ "$(uname)" = "Darwin" ]; then
  DMG_PATH=$(find "$FRONTEND_DIR/src-tauri/target/release/bundle/dmg" -name "*.dmg" 2>/dev/null | head -1)
  APP_PATH=$(find "$FRONTEND_DIR/src-tauri/target/release/bundle/macos" -name "*.app" 2>/dev/null | head -1)
  
  if [ -n "$DMG_PATH" ]; then
    SIZE=$(du -h "$DMG_PATH" | cut -f1)
    info "DMG: $DMG_PATH ($SIZE)"
  fi
  if [ -n "$APP_PATH" ]; then
    SIZE=$(du -sh "$APP_PATH" | cut -f1)
    info "APP: $APP_PATH ($SIZE)"
  fi
elif [ "$(uname -o 2>/dev/null)" = "Msys" ] || [ "$(uname -o 2>/dev/null)" = "Cygwin" ]; then
  EXE_PATH=$(find "$FRONTEND_DIR/src-tauri/target/release/bundle/nsis" -name "*.exe" 2>/dev/null | head -1)
  
  if [ -n "$EXE_PATH" ]; then
    info "Installer: $EXE_PATH"
  fi
fi
