#!/bin/bash
#
# ZenFlux Agent 全自动构建脚本（零依赖启动）
#
# 与 build_app.sh 的区别：
#   build_app.sh     — 假设环境已就绪，缺依赖直接报错退出
#   auto_build_app.sh — 自动检测并安装所有缺失的依赖，适合全新机器
#
# 自动安装的依赖：
#   - Python 3.12（通过 Homebrew，或提示手动安装）
#   - Node.js 18+（通过 Homebrew，或提示手动安装）
#   - Rust toolchain（通过 rustup）
#   - Python 虚拟环境 + pip 依赖（requirements.txt）
#   - PyInstaller（后端打包工具）
#   - 前端 npm 依赖（package.json）
#
# 用法:
#   bash scripts/auto_build_app.sh                # 完整构建
#   bash scripts/auto_build_app.sh --skip-backend # 跳过后端打包
#   bash scripts/auto_build_app.sh --clean        # 清理后重新构建
#   bash scripts/auto_build_app.sh --dry-run      # 仅检查环境，不执行构建
#

set -e

# ==================== 配置 ====================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
VENV_DIR="$PROJECT_ROOT/.venv"
PYTHON_VERSION="3.12"
NODE_MAJOR_VERSION="20"

SKIP_BACKEND=false
CLEAN=false
DRY_RUN=false

for arg in "$@"; do
  case $arg in
    --skip-backend) SKIP_BACKEND=true ;;
    --clean)        CLEAN=true ;;
    --dry-run)      DRY_RUN=true ;;
  esac
done

# ==================== 辅助函数 ====================

info()  { echo "===> $1"; }
warn()  { echo "WARN: $1"; }
fail()  { echo "ERROR: $1"; exit 1; }
ok()    { echo "  ✓  $1"; }
need()  { echo "  ✗  $1 — 需要安装"; }

# 检查命令是否存在
has_cmd() { command -v "$1" &> /dev/null; }

# 确保 Homebrew 的 PATH 在当前 shell 中生效
ensure_brew_path() {
  if [ -x "/opt/homebrew/bin/brew" ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [ -x "/usr/local/bin/brew" ]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
}

# 自动安装 Homebrew
install_homebrew() {
  if has_cmd brew; then
    return 0
  fi
  info "安装 Homebrew..."
  # 允许安装脚本返回非零（brew update 可能因网络问题失败，但 brew 本体已装好）
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || true
  ensure_brew_path
  if ! has_cmd brew; then
    fail "Homebrew 安装失败，请手动安装: https://brew.sh"
  fi
  # 跳过后续自动更新（避免 GitHub 连接问题阻塞 brew install）
  export HOMEBREW_NO_AUTO_UPDATE=1
  ok "Homebrew 安装完成"
}

# 确保 Homebrew 可用（需要时自动安装）
ensure_brew() {
  ensure_brew_path
  if ! has_cmd brew; then
    if [ "$(uname)" != "Darwin" ]; then
      return 1  # 非 macOS 不安装 Homebrew
    fi
    install_homebrew
  fi
  return 0
}

# ==================== Step 0: 环境检测与自动安装 ====================

info "Step 0/4: 检测构建环境..."
echo ""

INSTALLED_SOMETHING=false

# ---------- 0a. Python ----------

# 查找可用的 Python 3.12+
find_python() {
  # 优先使用项目 venv 中的 python
  if [ -x "$VENV_DIR/bin/python3" ]; then
    local ver
    ver=$("$VENV_DIR/bin/python3" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
    local major minor
    major=$(echo "$ver" | cut -d. -f1)
    minor=$(echo "$ver" | cut -d. -f2)
    if [ "$major" = "3" ] && [ "$minor" -ge 12 ]; then
      echo "$VENV_DIR/bin/python3"
      return 0
    fi
  fi
  # 查找系统 python
  for cmd in python3.12 python3 python; do
    if has_cmd "$cmd"; then
      local ver
      ver=$($cmd --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
      local major minor
      major=$(echo "$ver" | cut -d. -f1)
      minor=$(echo "$ver" | cut -d. -f2)
      if [ "$major" = "3" ] && [ "$minor" -ge 12 ]; then
        echo "$cmd"
        return 0
      fi
    fi
  done
  return 1
}

PYTHON_CMD=$(find_python || true)

if [ -n "$PYTHON_CMD" ]; then
  ok "Python 已安装 ($($PYTHON_CMD --version 2>&1))"
else
  need "Python >= 3.12"
  if [ "$DRY_RUN" = true ]; then
    fail "Python 未安装（--dry-run 模式不自动安装）"
  fi
  # 自动安装：确保 Homebrew 可用，然后用 brew 装 Python
  if [ "$(uname)" = "Darwin" ]; then
    ensure_brew
    info "通过 Homebrew 安装 Python ${PYTHON_VERSION}..."
    brew install "python@${PYTHON_VERSION}"
    ensure_brew_path
  else
    fail "请手动安装 Python >= 3.12: https://www.python.org/downloads/"
  fi
  PYTHON_CMD=$(find_python || true)
  [ -z "$PYTHON_CMD" ] && fail "Python 安装后仍未找到，请检查 PATH"
  INSTALLED_SOMETHING=true
  ok "Python 安装完成 ($($PYTHON_CMD --version 2>&1))"
fi

# ---------- 0b. Node.js ----------

if has_cmd node; then
  NODE_VER=$(node --version | grep -oE '[0-9]+' | head -1)
  if [ "$NODE_VER" -ge 18 ]; then
    ok "Node.js 已安装 ($(node --version))"
  else
    need "Node.js >= 18（当前 $(node --version) 过旧）"
    if [ "$DRY_RUN" = true ]; then
      fail "Node.js 版本过旧（--dry-run 模式不自动升级）"
    fi
    if [ "$(uname)" = "Darwin" ]; then
      ensure_brew
      info "通过 Homebrew 升级 Node.js..."
      brew install "node@${NODE_MAJOR_VERSION}"
      brew link --overwrite "node@${NODE_MAJOR_VERSION}"
      ensure_brew_path
    else
      fail "请手动升级 Node.js >= 18: https://nodejs.org"
    fi
    INSTALLED_SOMETHING=true
  fi
else
  need "Node.js"
  if [ "$DRY_RUN" = true ]; then
    fail "Node.js 未安装（--dry-run 模式不自动安装）"
  fi
  if [ "$(uname)" = "Darwin" ]; then
    ensure_brew
    info "通过 Homebrew 安装 Node.js ${NODE_MAJOR_VERSION}..."
    brew install "node@${NODE_MAJOR_VERSION}"
    brew link --overwrite "node@${NODE_MAJOR_VERSION}" 2>/dev/null || true
    ensure_brew_path
  else
    fail "请手动安装 Node.js: https://nodejs.org"
  fi
  INSTALLED_SOMETHING=true
  ok "Node.js 安装完成 ($(node --version))"
fi

# ---------- 0c. Rust ----------

if has_cmd rustc && has_cmd cargo; then
  ok "Rust 已安装 ($(rustc --version | head -1))"
else
  need "Rust toolchain"
  if [ "$DRY_RUN" = true ]; then
    fail "Rust 未安装（--dry-run 模式不自动安装）"
  fi
  info "通过 rustup 安装 Rust..."
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
  # 加载 cargo 环境
  source "$HOME/.cargo/env"
  INSTALLED_SOMETHING=true
  ok "Rust 安装完成 ($(rustc --version | head -1))"
fi

# 确保 cargo 在 PATH 中
if [ -f "$HOME/.cargo/env" ]; then
  source "$HOME/.cargo/env"
fi

# ---------- 0e. Python 虚拟环境 + 依赖 ----------

info "检查 Python 虚拟环境..."

if [ ! -d "$VENV_DIR" ]; then
  info "创建虚拟环境: $VENV_DIR"
  $PYTHON_CMD -m venv "$VENV_DIR"
  INSTALLED_SOMETHING=true
  ok "虚拟环境已创建"
else
  ok "虚拟环境已存在: $VENV_DIR"
fi

# 激活虚拟环境
source "$VENV_DIR/bin/activate"
PYTHON_CMD="$VENV_DIR/bin/python3"

info "检查 Python 依赖..."

# 安装/更新 pip 依赖
if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
  # 检查是否需要安装（用 freeze 对比，有差异就安装）
  MISSING=$($PYTHON_CMD -m pip install --dry-run -r "$PROJECT_ROOT/requirements.txt" 2>&1 | grep -c "Would install" || true)
  if [ "$MISSING" -gt 0 ]; then
    info "安装 Python 依赖 (requirements.txt)..."
    $PYTHON_CMD -m pip install -r "$PROJECT_ROOT/requirements.txt" --quiet
    INSTALLED_SOMETHING=true
    ok "Python 依赖安装完成"
  else
    ok "Python 依赖已是最新"
  fi
else
  warn "requirements.txt 不存在，跳过 Python 依赖安装"
fi

# 确保 PyInstaller 已安装
if [ "$SKIP_BACKEND" = false ]; then
  if ! $PYTHON_CMD -c "import PyInstaller" 2>/dev/null; then
    info "安装 PyInstaller..."
    $PYTHON_CMD -m pip install pyinstaller --quiet
    INSTALLED_SOMETHING=true
    ok "PyInstaller 安装完成"
  else
    ok "PyInstaller 已安装"
  fi
fi

# ---------- 0f. 前端 npm 依赖 ----------

info "检查前端依赖..."

cd "$FRONTEND_DIR"
if [ ! -d "node_modules" ]; then
  info "安装前端 npm 依赖..."
  npm install
  INSTALLED_SOMETHING=true
  ok "前端依赖安装完成"
else
  ok "前端依赖已存在 (node_modules/)"
fi

# ---------- 环境检测完成 ----------

echo ""
if [ "$INSTALLED_SOMETHING" = true ]; then
  info "环境准备完成（已安装缺失的依赖）"
else
  info "环境检测通过（所有依赖已就绪）"
fi
echo ""

if [ "$DRY_RUN" = true ]; then
  info "============================================"
  info "  --dry-run 模式，环境检测完成，跳过构建"
  info "============================================"
  exit 0
fi

# ==================== Step 1: 版本同步 ====================

info "同步版本号..."
$PYTHON_CMD "$SCRIPT_DIR/sync_version.py" || fail "版本同步失败"

# ==================== Step 2: 清理（可选）====================

if [ "$CLEAN" = true ]; then
  info "清理构建产物..."
  rm -rf "$PROJECT_ROOT/build" "$PROJECT_ROOT/dist"
  rm -rf "$FRONTEND_DIR/dist"
  rm -rf "$FRONTEND_DIR/src-tauri/target"
  rm -rf "$FRONTEND_DIR/src-tauri/binaries/zenflux-backend-"*
  rm -rf "$FRONTEND_DIR/src-tauri/binaries/_internal"
  info "清理完成"
fi

# ==================== Step 3: 构建 Python 后端 ====================

if [ "$SKIP_BACKEND" = false ]; then
  info "Step 1/3: 构建 Python 后端 (PyInstaller onedir)..."
  cd "$PROJECT_ROOT"
  $PYTHON_CMD scripts/build_backend.py
  info "Python 后端构建完成"
else
  info "Step 1/3: 跳过 Python 后端构建"
  BINARY_COUNT=$(ls "$FRONTEND_DIR/src-tauri/binaries/zenflux-backend-"* 2>/dev/null | wc -l)
  if [ "$BINARY_COUNT" -eq 0 ]; then
    warn "binaries/ 目录中没有 sidecar 二进制文件"
    warn "如果要构建完整应用，请去掉 --skip-backend 参数"
  fi
fi

# ==================== Step 4: 构建 Tauri 应用 ====================

info "Step 2/3: 构建 Tauri 应用..."
cd "$FRONTEND_DIR"

# Tauri 2.x: 取消 CI 标志，避免 IDE 环境干扰
unset CI

# 构建 Tauri（macOS 只打包 .app，Step 5 会自己生成 DMG）
if [ "$(uname)" = "Darwin" ]; then
  npm run tauri:build -- --bundles app
else
  npm run tauri:build
fi

# ==================== Step 5: macOS 后处理 ====================

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

  # 5a. 复制 _internal/ 到 Contents/Resources/
  if [ -d "$INTERNAL_SRC" ]; then
    info "复制 _internal/ 到 Contents/Resources/..."
    rm -rf "$RESOURCES_DIR/_internal"
    cp -R "$INTERNAL_SRC" "$RESOURCES_DIR/_internal"
    FILE_COUNT=$(find "$RESOURCES_DIR/_internal" -type f | wc -l | tr -d ' ')
    INTERNAL_SIZE=$(du -sh "$RESOURCES_DIR/_internal" | cut -f1)
    info "已复制 $FILE_COUNT 个文件 ($INTERNAL_SIZE)"
  else
    warn "_internal/ 目录不存在: $INTERNAL_SRC"
    warn "sidecar 可能无法启动，请确保已运行后端构建"
  fi

  # 5b. 创建 symlink: Contents/MacOS/_internal -> ../Resources/_internal
  rm -rf "$MACOS_DIR/_internal"
  ln -s "../Resources/_internal" "$MACOS_DIR/_internal"
  info "已创建 symlink: MacOS/_internal -> ../Resources/_internal"

  # 5b2. 在 Contents/Frameworks/ 为 _internal/ 中所有内容创建 symlink
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
  fi

  # 5c. 签名动态库
  info "签名动态库..."
  SIGN_COUNT=0
  if [ -d "$RESOURCES_DIR/_internal" ]; then
    while IFS= read -r -d '' lib; do
      codesign --force --sign - "$lib" 2>/dev/null && SIGN_COUNT=$((SIGN_COUNT + 1))
    done < <(find "$RESOURCES_DIR/_internal" \( -name "*.so" -o -name "*.dylib" \) -print0)
  fi
  info "已签名 $SIGN_COUNT 个动态库"

  # 5d. 签名 sidecar 主程序
  SIDECAR_PATH=$(find "$MACOS_DIR" -maxdepth 1 -name "zenflux-backend*" -type f | head -1)
  if [ -n "$SIDECAR_PATH" ]; then
    info "签名 sidecar: $(basename "$SIDECAR_PATH")"
    if [ -f "$ENTITLEMENTS" ]; then
      codesign --force --sign - --entitlements "$ENTITLEMENTS" "$SIDECAR_PATH"
    else
      codesign --force --sign - "$SIDECAR_PATH"
    fi
  fi

  # 5e. 签名 app bundle
  info "签名 app bundle: $(basename "$APP_PATH")"
  if [ -f "$ENTITLEMENTS" ]; then
    codesign --force --sign - --entitlements "$ENTITLEMENTS" "$APP_PATH"
  else
    codesign --force --sign - "$APP_PATH"
  fi

  # 5f. 验证签名
  if codesign --verify --deep "$APP_PATH" 2>/dev/null; then
    info "签名验证通过"
  else
    warn "签名验证失败（可能不影响本地使用）"
  fi

  # 5g. 生成 DMG
  info "生成 DMG 安装包..."
  VERSION=$(cat "$PROJECT_ROOT/VERSION" 2>/dev/null || echo "0.0.0")
  ARCH=$(uname -m)
  [ "$ARCH" = "arm64" ] && ARCH="aarch64"
  DMG_DIR="$FRONTEND_DIR/src-tauri/target/release/bundle/dmg"
  DMG_FILENAME="$(basename "$APP_PATH" .app)_${VERSION}_${ARCH}.dmg"
  DMG_PATH="$DMG_DIR/$DMG_FILENAME"
  VOL_NAME=$(basename "$APP_PATH" .app)
  TMP_DMG="/tmp/zenflux_dmg_tmp.dmg"
  TMP_MOUNT="/tmp/zenflux_dmg_mount"

  mkdir -p "$DMG_DIR"
  rm -f "$TMP_DMG" "$DMG_PATH"
  [ -d "$TMP_MOUNT" ] && hdiutil detach "$TMP_MOUNT" 2>/dev/null || true

  hdiutil create -size 300m -fs HFS+ -volname "$VOL_NAME" "$TMP_DMG" -quiet
  mkdir -p "$TMP_MOUNT"
  hdiutil attach "$TMP_DMG" -mountpoint "$TMP_MOUNT" -quiet
  cp -R "$APP_PATH" "$TMP_MOUNT/"
  ln -s /Applications "$TMP_MOUNT/Applications"
  hdiutil detach "$TMP_MOUNT" -quiet

  hdiutil convert "$TMP_DMG" -format UDZO -o "$DMG_PATH" -quiet

  rm -f "$TMP_DMG"
  rmdir "$TMP_MOUNT" 2>/dev/null || true

  DMG_SIZE=$(du -h "$DMG_PATH" | cut -f1)
  info "DMG 生成完成: $DMG_FILENAME ($DMG_SIZE)"

  info "macOS 后处理完成"
fi

# ==================== 构建完成 ====================

echo ""
info "============================================"
info "  构建完成!"
info "============================================"
echo ""

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
fi
