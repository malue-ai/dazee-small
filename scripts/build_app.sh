#!/bin/bash
#
# xiaodazi 桌面应用一键构建脚本
#
# 构建流程:
#   1. 检查依赖
#   2. PyInstaller 打包 Python 后端（onedir 模式）
#   3. Tauri 打包（前端 + Rust 壳 + sidecar）
#   4. macOS 后处理：复制 _internal/ 到 app bundle + 签名所有动态库 + 重建 DMG
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

# Python 环境：使用当前已激活的环境（conda/venv 均可）
PYTHON_CMD="python3"

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

# ==================== 检查 Python 环境 ====================

PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 || true)
if [ -n "$VIRTUAL_ENV" ]; then
  info "当前 venv 环境: $VIRTUAL_ENV ($PYTHON_VERSION)"
elif [ -n "$CONDA_PREFIX" ]; then
  info "当前 conda 环境: $(basename "$CONDA_PREFIX") ($PYTHON_VERSION)"
else
  warn "未检测到激活的虚拟环境，将使用系统 python3 ($PYTHON_VERSION)"
  warn "建议先激活环境: source .venv/bin/activate 或 conda activate <env>"
fi

# ==================== 依赖检查 ====================

info "检查构建依赖..."

$PYTHON_CMD --version &> /dev/null || fail "python3 未找到: brew install python3 / conda create -n $CONDA_ENV_NAME python=3.12"
check_cmd "node" "brew install node / https://nodejs.org"
check_cmd "npm" "brew install node / https://nodejs.org"
check_cmd "cargo" "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"

if [ "$SKIP_BACKEND" = false ]; then
  $PYTHON_CMD -c "import PyInstaller" 2>/dev/null || fail "PyInstaller 未安装: pip install pyinstaller"
fi

info "依赖检查通过"

# ==================== 版本同步 ====================

info "同步版本号..."
$PYTHON_CMD "$SCRIPT_DIR/sync_version.py" || fail "版本同步失败"

# ==================== 清理（可选）====================

if [ "$CLEAN" = true ]; then
  info "清理构建产物..."
  rm -rf "$PROJECT_ROOT/build" "$PROJECT_ROOT/dist"
  rm -rf "$FRONTEND_DIR/dist"
  rm -rf "$FRONTEND_DIR/src-tauri/target"
  rm -rf "$FRONTEND_DIR/src-tauri/binaries/xiaodazi-backend-*"
  rm -rf "$FRONTEND_DIR/src-tauri/binaries/_internal"
  info "清理完成"
fi

# ==================== Step 1: 构建 Python 后端 ====================

if [ "$SKIP_BACKEND" = false ]; then
  info "Step 1/3: 构建 Python 后端 (PyInstaller onedir)..."
  cd "$PROJECT_ROOT"
  $PYTHON_CMD scripts/build_backend.py
  info "Python 后端构建完成"
else
  info "Step 1/3: 跳过 Python 后端构建"
  
  # 检查 sidecar 二进制是否存在
  BINARY_COUNT=$(ls "$FRONTEND_DIR/src-tauri/binaries/xiaodazi-backend-"* 2>/dev/null | wc -l)
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

# Tauri 2.x 的 --ci 参数只接受 true/false，
# 但某些 IDE（如 Cursor）会设置 CI=1 导致构建失败。
# 本地构建时统一取消 CI 标志。
unset CI

# 构建 Tauri（只打包 .app，跳过 Tauri 自带的 DMG 打包，Step 3 会自己生成完整 DMG）
if [ "$(uname)" = "Darwin" ]; then
  npm run tauri:build -- --bundles app
else
  npm run tauri:build
fi

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

  # 3b2. 在 Contents/Frameworks/ 为 _internal/ 中所有内容创建 symlink
  #      PyInstaller 6.x bootloader 检测到 .app bundle 后，
  #      会将 PYTHONHOME 设为 Contents/Frameworks/，
  #      在那里查找 libpython3.12.dylib、base_library.zip、lib-dynload/ 等。
  #      真实文件保留在 Resources/_internal/（codesign 安全），
  #      通过 symlink 让 bootloader 能找到。
  FRAMEWORKS_DIR="$APP_PATH/Contents/Frameworks"
  mkdir -p "$FRAMEWORKS_DIR"
  LINK_COUNT=0
  if [ -d "$RESOURCES_DIR/_internal" ]; then
    for item in "$RESOURCES_DIR/_internal/"*; do
      name=$(basename "$item")
      target="$FRAMEWORKS_DIR/$name"
      if [ ! -e "$target" ] && [ ! -L "$target" ]; then
        ln -s "../Resources/_internal/$name" "$target"
        LINK_COUNT=$((LINK_COUNT + 1))
      fi
    done
    info "已在 Frameworks/ 创建 $LINK_COUNT 个 symlink → Resources/_internal/"
  else
    warn "Resources/_internal/ 不存在，无法创建 Frameworks symlink"
  fi

  # 3c. 签名 Resources/_internal/ 中的所有 .so 和 .dylib（AMFI 要求）
  info "签名动态库..."
  SIGN_COUNT=0

  if [ -d "$RESOURCES_DIR/_internal" ]; then
    while IFS= read -r -d '' lib; do
      codesign --force --sign - "$lib" 2>/dev/null && SIGN_COUNT=$((SIGN_COUNT + 1))
    done < <(find "$RESOURCES_DIR/_internal" \( -name "*.so" -o -name "*.dylib" \) -print0)
  fi
  info "已签名 $SIGN_COUNT 个动态库"

  # 3d. 签名 sidecar 主程序（xiaodazi-backend）
  SIDECAR_PATH=$(find "$MACOS_DIR" -maxdepth 1 -name "xiaodazi-backend*" -type f | head -1)
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

  # 3g. 生成完整 DMG（包含后处理过的 .app）
  #     Step 2 只打包 .app（跳过 Tauri 自带的 DMG），
  #     这里用 hdiutil 从完整的 .app 创建 DMG 安装包。
  info "生成 DMG 安装包..."

  # 读取版本号用于 DMG 文件名
  VERSION=$(cat "$PROJECT_ROOT/VERSION" 2>/dev/null || echo "0.0.0")
  ARCH=$(uname -m)
  [ "$ARCH" = "arm64" ] && ARCH="aarch64"
  DMG_DIR="$FRONTEND_DIR/src-tauri/target/release/bundle/dmg"
  DMG_FILENAME="$(basename "$APP_PATH" .app)_${VERSION}_${ARCH}.dmg"
  DMG_PATH="$DMG_DIR/$DMG_FILENAME"
  VOL_NAME=$(basename "$APP_PATH" .app)
  TMP_DMG="/tmp/xiaodazi_dmg_tmp.dmg"
  TMP_MOUNT="/tmp/xiaodazi_dmg_mount"

  # 确保输出目录存在
  mkdir -p "$DMG_DIR"

  # 清理残留
  rm -f "$TMP_DMG" "$DMG_PATH"
  [ -d "$TMP_MOUNT" ] && hdiutil detach "$TMP_MOUNT" 2>/dev/null || true

  # 动态计算 DMG 大小（.app 实际大小 + 50MB 余量）
  APP_SIZE_MB=$(du -sm "$APP_PATH" | cut -f1)
  DMG_SIZE_MB=$(( APP_SIZE_MB + 50 ))
  info ".app 大小: ${APP_SIZE_MB}MB, DMG 预留: ${DMG_SIZE_MB}MB"

  # 创建临时可写 DMG → 挂载 → 复制 .app + /Applications 快捷方式 → 卸载
  hdiutil create -size "${DMG_SIZE_MB}m" -fs HFS+ -volname "$VOL_NAME" "$TMP_DMG" -quiet
  mkdir -p "$TMP_MOUNT"
  hdiutil attach "$TMP_DMG" -mountpoint "$TMP_MOUNT" -quiet
  cp -R "$APP_PATH" "$TMP_MOUNT/"
  ln -s /Applications "$TMP_MOUNT/Applications"
  hdiutil detach "$TMP_MOUNT" -quiet

  # 压缩为只读 DMG
  hdiutil convert "$TMP_DMG" -format UDZO -o "$DMG_PATH" -quiet

  # 清理
  rm -f "$TMP_DMG"
  rmdir "$TMP_MOUNT" 2>/dev/null || true

  DMG_SIZE=$(du -h "$DMG_PATH" | cut -f1)
  info "DMG 生成完成: $DMG_FILENAME ($DMG_SIZE)"

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
