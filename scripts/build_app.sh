#!/bin/bash
#
# ZenFlux Agent 桌面应用一键构建脚本
#
# 构建流程:
#   1. 检查依赖
#   2. PyInstaller 打包 Python 后端（onedir 模式）
#   3. Tauri 打包（前端 + Rust 壳 + sidecar）
#   4. macOS 后处理：复制 _internal/ 到 app bundle + 签名所有动态库
#
# 用法:
#   bash scripts/build_app.sh                    # 完整构建
#   bash scripts/build_app.sh --skip-backend     # 仅构建前端+Tauri（跳过 PyInstaller）
#   bash scripts/build_app.sh --clean            # 清理后重新构建
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

# ==================== 版本同步 ====================

info "同步版本号..."
python3 "$SCRIPT_DIR/sync_version.py" || fail "版本同步失败"

# ==================== 清理（可选）====================

if [ "$CLEAN" = true ]; then
  info "清理构建产物..."
  rm -rf "$PROJECT_ROOT/build" "$PROJECT_ROOT/dist"
  rm -rf "$FRONTEND_DIR/dist"
  rm -rf "$FRONTEND_DIR/src-tauri/target"
  rm -rf "$FRONTEND_DIR/src-tauri/binaries/zenflux-backend-*"
  rm -rf "$FRONTEND_DIR/src-tauri/binaries/_internal"
  info "清理完成"
fi

# ==================== Step 1: 构建 Python 后端 ====================

if [ "$SKIP_BACKEND" = false ]; then
  info "Step 1/3: 构建 Python 后端 (PyInstaller onedir)..."
  cd "$PROJECT_ROOT"
  python3 scripts/build_backend.py
  info "Python 后端构建完成"
else
  info "Step 1/3: 跳过 Python 后端构建"
  
  # 检查 sidecar 二进制是否存在
  BINARY_COUNT=$(ls "$FRONTEND_DIR/src-tauri/binaries/zenflux-backend-"* 2>/dev/null | wc -l)
  if [ "$BINARY_COUNT" -eq 0 ]; then
    warn "binaries/ 目录中没有 sidecar 二进制文件"
    warn "如果要构建完整应用，请去掉 --skip-backend 参数"
  fi
fi

# ==================== Step 2: 构建 Tauri 应用 ====================

info "Step 2/3: 构建 Tauri 应用..."
cd "$FRONTEND_DIR"

# 安装前端依赖
if [ ! -d "node_modules" ]; then
  info "安装前端依赖..."
  npm install
fi

# 构建 Tauri
npm run tauri:build

# ==================== Step 3: macOS 后处理（Resources + symlink + 签名）====================
#
# macOS bundle 规范：
#   Contents/MacOS/    — 仅放可执行文件
#   Contents/Resources/ — 放数据文件、配置、资源
#
# PyInstaller _internal/ 包含 .so/.dylib（代码）和 .yaml/.json（数据）的混合内容。
# 放在 MacOS/ 下会导致 codesign 把数据文件当 code object 报错。
#
# 解决方案：
#   1. 把 _internal/ 放在 Contents/Resources/_internal/
#   2. 在 Contents/MacOS/ 创建 symlink 指向它
#   3. PyInstaller bootloader 通过 symlink 找到依赖
#   4. codesign 不递归验证 symlink 目标，签名顺利通过

if [ "$(uname)" = "Darwin" ]; then
  APP_PATH=$(find "$FRONTEND_DIR/src-tauri/target/release/bundle/macos" -name "*.app" 2>/dev/null | head -1)
  INTERNAL_SRC="$FRONTEND_DIR/src-tauri/binaries/_internal"
  ENTITLEMENTS="$FRONTEND_DIR/src-tauri/entitlements.plist"

  if [ -z "$APP_PATH" ]; then
    fail "找不到 .app bundle"
  fi

  MACOS_DIR="$APP_PATH/Contents/MacOS"
  RESOURCES_DIR="$APP_PATH/Contents/Resources"

  info "Step 3/3: macOS 后处理..."

  # 3a. 复制 _internal/ 到 Contents/Resources/（数据文件的正确位置）
  if [ -d "$INTERNAL_SRC" ]; then
    info "复制 _internal/ 到 Contents/Resources/..."
    rm -rf "$RESOURCES_DIR/_internal"
    cp -R "$INTERNAL_SRC" "$RESOURCES_DIR/_internal"

    FILE_COUNT=$(find "$RESOURCES_DIR/_internal" -type f | wc -l | tr -d ' ')
    INTERNAL_SIZE=$(du -sh "$RESOURCES_DIR/_internal" | cut -f1)
    info "已复制 $FILE_COUNT 个文件 ($INTERNAL_SIZE)"
  else
    warn "_internal/ 目录不存在: $INTERNAL_SRC"
    warn "sidecar 可能无法启动，请确保已运行 Step 1"
  fi

  # 3b. 创建 symlink: Contents/MacOS/_internal -> ../Resources/_internal
  #     PyInstaller bootloader 通过 symlink 找到依赖文件
  #     codesign 不会递归验证 symlink 目标内容
  rm -rf "$MACOS_DIR/_internal"
  ln -s "../Resources/_internal" "$MACOS_DIR/_internal"
  info "已创建 symlink: MacOS/_internal -> ../Resources/_internal"

  # 3c. 签名 Resources/_internal/ 中的所有 .so 和 .dylib（AMFI 要求）
  info "签名动态库..."
  SIGN_COUNT=0

  if [ -d "$RESOURCES_DIR/_internal" ]; then
    while IFS= read -r -d '' lib; do
      codesign --force --sign - "$lib" 2>/dev/null && SIGN_COUNT=$((SIGN_COUNT + 1))
    done < <(find "$RESOURCES_DIR/_internal" \( -name "*.so" -o -name "*.dylib" \) -print0)
  fi
  info "已签名 $SIGN_COUNT 个动态库"

  # 3d. 签名 sidecar 主程序（zenflux-backend）
  SIDECAR_PATH=$(find "$MACOS_DIR" -maxdepth 1 -name "zenflux-backend*" -type f | head -1)
  if [ -n "$SIDECAR_PATH" ]; then
    info "签名 sidecar: $(basename "$SIDECAR_PATH")"
    if [ -f "$ENTITLEMENTS" ]; then
      codesign --force --sign - --entitlements "$ENTITLEMENTS" "$SIDECAR_PATH"
    else
      codesign --force --sign - "$SIDECAR_PATH"
    fi
  fi

  # 3e. 重新签名整个 app bundle
  info "签名 app bundle: $(basename "$APP_PATH")"
  if [ -f "$ENTITLEMENTS" ]; then
    codesign --force --sign - --entitlements "$ENTITLEMENTS" "$APP_PATH"
  else
    codesign --force --sign - "$APP_PATH"
  fi

  # 3f. 验证签名
  if codesign --verify --deep "$APP_PATH" 2>/dev/null; then
    info "签名验证通过"
  else
    warn "签名验证失败（可能不影响本地使用）"
  fi

  info "macOS 后处理完成"
fi

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
