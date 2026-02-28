#!/bin/bash
#
# xiaodazi 全自动构建脚本（零依赖启动）
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
#   bash scripts/auto_build_app.sh                      # 当前架构构建
#   bash scripts/auto_build_app.sh --arch arm64          # 仅 ARM64 (Apple Silicon)
#   bash scripts/auto_build_app.sh --arch x86_64         # 仅 Intel（ARM Mac 通过 Rosetta）
#   bash scripts/auto_build_app.sh --arch both           # 同时构建两个架构
#   bash scripts/auto_build_app.sh --skip-backend        # 跳过后端打包
#   bash scripts/auto_build_app.sh --clean               # 清理后重新构建
#   bash scripts/auto_build_app.sh --dry-run             # 仅检查环境，不执行构建
#

set -e

# 全局禁用 Homebrew 自动更新（避免网络问题阻塞 brew install）
export HOMEBREW_NO_AUTO_UPDATE=1
export HOMEBREW_NO_INSTALL_CLEANUP=1

# ==================== 配置 ====================

# When run via process substitution (bash <(curl ...)), $0 becomes /dev/fd/N.
# In that case, fall back to the current working directory as the project root.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd 2>/dev/null || echo "")"
if [[ -z "$SCRIPT_DIR" || "$SCRIPT_DIR" == /dev/fd* || "$SCRIPT_DIR" == /dev ]]; then
  PROJECT_ROOT="$(pwd)"
  SCRIPT_DIR="$PROJECT_ROOT/scripts"
else
  PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi
FRONTEND_DIR="$PROJECT_ROOT/frontend"
VENV_DIR="$PROJECT_ROOT/.venv"
VENV_X86_DIR="$PROJECT_ROOT/.venv-x86_64"
PYTHON_VERSION="3.12"
NODE_MAJOR_VERSION="20"
NATIVE_ARCH=$(uname -m)  # arm64 or x86_64

SKIP_BACKEND=false
CLEAN=false
DRY_RUN=false
TARGET_ARCH="native"

# ==================== 参数解析 ====================

while [ $# -gt 0 ]; do
  case "$1" in
    --skip-backend) SKIP_BACKEND=true ;;
    --clean)        CLEAN=true ;;
    --dry-run)      DRY_RUN=true ;;
    --arch)         shift; TARGET_ARCH="$1" ;;
    --arch=*)       TARGET_ARCH="${1#*=}" ;;
  esac
  shift
done

# 验证 --arch 参数
case "$TARGET_ARCH" in
  native|arm64|x86_64|both) ;;
  *) echo "ERROR: 无效的 --arch 参数: $TARGET_ARCH (可选: native, arm64, x86_64, both)"; exit 1 ;;
esac

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

# 自动安装 Homebrew（原生架构）
install_homebrew() {
  if has_cmd brew; then
    return 0
  fi
  info "安装 Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || true
  ensure_brew_path
  if ! has_cmd brew; then
    fail "Homebrew 安装失败，请手动安装: https://brew.sh"
  fi
  export HOMEBREW_NO_AUTO_UPDATE=1
  ok "Homebrew 安装完成"
}

# 确保 Homebrew 可用（需要时自动安装）
ensure_brew() {
  ensure_brew_path
  if ! has_cmd brew; then
    if [ "$(uname)" != "Darwin" ]; then
      return 1
    fi
    install_homebrew
  fi
  return 0
}

# 将架构名转换为 DMG/Tauri 使用的名称
arch_to_tauri_name() {
  case "$1" in
    arm64)  echo "aarch64" ;;
    x86_64) echo "x86_64" ;;
    *)      echo "$1" ;;
  esac
}

# 将架构名转换为 Rust target triple
arch_to_rust_target() {
  case "$1" in
    arm64)  echo "aarch64-apple-darwin" ;;
    x86_64) echo "x86_64-apple-darwin" ;;
  esac
}

# ==================== Step 0: 环境检测与自动安装 ====================

info "Step 0/4: 检测构建环境..."
echo ""
info "目标架构: $TARGET_ARCH (本机: $NATIVE_ARCH)"
echo ""

INSTALLED_SOMETHING=false

# ---------- 0a. Python ----------

PYTHON_MIN_MINOR=12
PYTHON_MAX_MINOR=13

is_python_compatible() {
  local cmd="$1"
  local ver major minor
  ver=$($cmd --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
  major=$(echo "$ver" | cut -d. -f1)
  minor=$(echo "$ver" | cut -d. -f2)
  [ "$major" = "3" ] && [ "$minor" -ge "$PYTHON_MIN_MINOR" ] && [ "$minor" -le "$PYTHON_MAX_MINOR" ]
}

find_python() {
  if [ -x "$VENV_DIR/bin/python3" ]; then
    if is_python_compatible "$VENV_DIR/bin/python3"; then
      echo "$VENV_DIR/bin/python3"
      return 0
    fi
  fi
  for cmd in python3.12 python3.13 python3 python; do
    if has_cmd "$cmd"; then
      if is_python_compatible "$cmd"; then
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
  if has_cmd python3; then
    CURRENT_VER=$(python3 --version 2>&1)
    need "Python 3.12 ~ 3.13（当前 $CURRENT_VER 不兼容）"
  else
    need "Python 3.12 ~ 3.13"
  fi

  if [ "$DRY_RUN" = true ]; then
    fail "Python 版本不兼容（--dry-run 模式不自动安装）"
  fi

  if [ "$(uname)" = "Darwin" ]; then
    ensure_brew
    info "通过 Homebrew 安装 Python ${PYTHON_VERSION}..."
    # brew install 可能因 keg-only 警告、已安装未链接等返回非零，
    # 不能让 set -e 直接杀掉脚本，需手动检查安装结果。
    brew install "python@${PYTHON_VERSION}" 2>&1 || true
    ensure_brew_path
    # brew 安装的 keg-only Python 可能不在 PATH 中，显式添加
    BREW_PYTHON_PREFIX=$(brew --prefix "python@${PYTHON_VERSION}" 2>/dev/null || true)
    if [ -n "$BREW_PYTHON_PREFIX" ] && [ -d "$BREW_PYTHON_PREFIX/bin" ]; then
      export PATH="$BREW_PYTHON_PREFIX/bin:$PATH"
    fi
    # 尝试链接（已链接时会返回非零，忽略）
    brew link --overwrite "python@${PYTHON_VERSION}" 2>/dev/null || true
  else
    fail "请手动安装 Python 3.12: https://www.python.org/downloads/"
  fi
  PYTHON_CMD=$(find_python || true)
  [ -z "$PYTHON_CMD" ] && fail "Python 安装后仍未找到，请检查 PATH 或手动安装: https://www.python.org/downloads/"
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
      brew install "node@${NODE_MAJOR_VERSION}" 2>&1 || true
      brew link --overwrite "node@${NODE_MAJOR_VERSION}" 2>/dev/null || true
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
    brew install "node@${NODE_MAJOR_VERSION}" 2>&1 || true
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
  source "$HOME/.cargo/env"
  INSTALLED_SOMETHING=true
  ok "Rust 安装完成 ($(rustc --version | head -1))"
fi

if [ -f "$HOME/.cargo/env" ]; then
  source "$HOME/.cargo/env"
fi

# ---------- 0d. Python 虚拟环境 + 依赖（原生架构）----------

info "检查 Python 虚拟环境..."

if [ ! -d "$VENV_DIR" ]; then
  info "创建虚拟环境: $VENV_DIR"
  $PYTHON_CMD -m venv "$VENV_DIR"
  INSTALLED_SOMETHING=true
  ok "虚拟环境已创建"
else
  ok "虚拟环境已存在: $VENV_DIR"
fi

# 激活 venv（后续所有 pip install / PyInstaller / build_backend.py 都在此环境中执行）
# 注意：activate 脚本内部的 hash -r 可能返回非零，加 || true 防止 set -e 退出
info "激活虚拟环境: $VENV_DIR"
source "$VENV_DIR/bin/activate" 2>/dev/null || true
PYTHON_CMD="$VENV_DIR/bin/python3"

# 验证 venv 激活成功
if [ ! -x "$PYTHON_CMD" ]; then
  fail "虚拟环境激活失败: $PYTHON_CMD 不存在"
fi
VENV_PYTHON_VER=$($PYTHON_CMD --version 2>&1)
ok "venv 已激活: $PYTHON_CMD ($VENV_PYTHON_VER)"

info "检查 Python 依赖..."

if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
  NEEDS_INSTALL=false
  for pkg in aiofiles fastapi pydantic uvicorn httpx sqlalchemy tiktoken mem0 sqlite_vec; do
    if ! $PYTHON_CMD -c "import $pkg" 2>/dev/null; then
      NEEDS_INSTALL=true
      break
    fi
  done

  if [ "$NEEDS_INSTALL" = true ]; then
    info "安装 Python 依赖 (requirements.txt)..."
    if ! $PYTHON_CMD -m pip install -r "$PROJECT_ROOT/requirements.txt" --quiet; then
      fail "Python 依赖安装失败！请检查 Python 版本（当前: $($PYTHON_CMD --version 2>&1)，需要 3.12 ~ 3.13）"
    fi
    INSTALLED_SOMETHING=true
    ok "Python 依赖安装完成"
  else
    ok "Python 依赖已是最新"
  fi
else
  warn "requirements.txt 不存在，跳过 Python 依赖安装"
fi

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

# ---------- 0e. 前端 npm 依赖 ----------

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

# ---------- 0f. 跨架构构建环境（仅当需要时）----------
#
# 在 ARM Mac 上构建 x86_64 版本：
#   - 通过 Rosetta 2 运行 x86_64 二进制
#   - 使用 x86_64 Homebrew（/usr/local/bin/brew）安装 x86_64 Python
#   - 创建独立的 x86_64 虚拟环境（.venv-x86_64）
#
# 在 Intel Mac 上无法构建 arm64 版本（需要 ARM 硬件）

NEED_CROSS_BUILD=false

if [ "$TARGET_ARCH" = "both" ] && [ "$NATIVE_ARCH" = "x86_64" ]; then
  warn "Intel Mac 无法构建 ARM 版本，将仅构建 x86_64"
  TARGET_ARCH="x86_64"
elif [ "$TARGET_ARCH" = "both" ]; then
  NEED_CROSS_BUILD=true
elif [ "$TARGET_ARCH" = "x86_64" ] && [ "$NATIVE_ARCH" = "arm64" ]; then
  NEED_CROSS_BUILD=true
elif [ "$TARGET_ARCH" = "arm64" ] && [ "$NATIVE_ARCH" = "x86_64" ]; then
  fail "无法在 Intel Mac 上构建 ARM 版本（需要 Apple Silicon 硬件）"
fi

X86_PYTHON_CMD=""

if [ "$NEED_CROSS_BUILD" = true ] && [ "$NATIVE_ARCH" = "arm64" ]; then
  info "配置 x86_64 跨架构构建环境..."

  # 检查 Rosetta 2
  if arch -x86_64 /usr/bin/true 2>/dev/null; then
    ok "Rosetta 2 已安装"
  else
    if [ "$DRY_RUN" = true ]; then
      fail "Rosetta 2 未安装（--dry-run 模式不自动安装）"
    fi
    info "安装 Rosetta 2..."
    softwareupdate --install-rosetta --agree-to-license || fail "Rosetta 2 安装失败"
    ok "Rosetta 2 安装完成"
  fi

  # 检查 x86_64 Homebrew（安装在 /usr/local/）
  if [ -x "/usr/local/bin/brew" ]; then
    ok "x86_64 Homebrew 已安装"
  else
    if [ "$DRY_RUN" = true ]; then
      fail "x86_64 Homebrew 未安装（--dry-run 模式不自动安装）"
    fi
    info "安装 x86_64 Homebrew（/usr/local/）..."
    arch -x86_64 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || true
    if [ ! -x "/usr/local/bin/brew" ]; then
      fail "x86_64 Homebrew 安装失败"
    fi
    ok "x86_64 Homebrew 安装完成"
  fi

  # 检查 x86_64 Python
  X86_BREW="/usr/local/bin/brew"
  X86_PYTHON_FOUND=""
  for cmd in /usr/local/bin/python3.12 /usr/local/bin/python3.13; do
    if [ -x "$cmd" ]; then
      X86_PYTHON_FOUND="$cmd"
      break
    fi
  done

  if [ -z "$X86_PYTHON_FOUND" ]; then
    if [ "$DRY_RUN" = true ]; then
      fail "x86_64 Python 未安装（--dry-run 模式不自动安装）"
    fi
    info "安装 x86_64 Python ${PYTHON_VERSION}..."
    arch -x86_64 "$X86_BREW" install "python@${PYTHON_VERSION}" 2>&1 || true
    arch -x86_64 "$X86_BREW" link --overwrite "python@${PYTHON_VERSION}" 2>/dev/null || true
    # 显式添加 keg-only Python 路径
    X86_BREW_PREFIX=$(arch -x86_64 "$X86_BREW" --prefix "python@${PYTHON_VERSION}" 2>/dev/null || true)
    if [ -n "$X86_BREW_PREFIX" ] && [ -d "$X86_BREW_PREFIX/bin" ]; then
      export PATH="$X86_BREW_PREFIX/bin:$PATH"
    fi
    X86_PYTHON_FOUND="/usr/local/bin/python3.12"
    # 如果标准路径找不到，尝试 keg 路径
    if [ ! -x "$X86_PYTHON_FOUND" ] && [ -n "$X86_BREW_PREFIX" ]; then
      X86_PYTHON_FOUND="$X86_BREW_PREFIX/bin/python3.12"
    fi
  fi
  ok "x86_64 Python: $(arch -x86_64 "$X86_PYTHON_FOUND" --version 2>&1)"

  # 创建 x86_64 虚拟环境
  if [ ! -d "$VENV_X86_DIR" ]; then
    info "创建 x86_64 虚拟环境: $VENV_X86_DIR"
    arch -x86_64 "$X86_PYTHON_FOUND" -m venv "$VENV_X86_DIR"
    ok "x86_64 虚拟环境已创建"
  else
    ok "x86_64 虚拟环境已存在: $VENV_X86_DIR"
  fi

  X86_PYTHON_CMD="$VENV_X86_DIR/bin/python3"

  # 安装 x86_64 依赖
  NEEDS_INSTALL=false
  for pkg in aiofiles fastapi pydantic uvicorn httpx sqlalchemy tiktoken mem0 sqlite_vec; do
    if ! arch -x86_64 "$X86_PYTHON_CMD" -c "import $pkg" 2>/dev/null; then
      NEEDS_INSTALL=true
      break
    fi
  done

  if [ "$NEEDS_INSTALL" = true ]; then
    info "安装 x86_64 Python 依赖..."
    if ! arch -x86_64 "$VENV_X86_DIR/bin/pip" install -r "$PROJECT_ROOT/requirements.txt" --quiet; then
      fail "x86_64 Python 依赖安装失败"
    fi
    ok "x86_64 Python 依赖安装完成"
  else
    ok "x86_64 Python 依赖已是最新"
  fi

  # 确保 x86_64 PyInstaller
  if [ "$SKIP_BACKEND" = false ]; then
    if ! arch -x86_64 "$X86_PYTHON_CMD" -c "import PyInstaller" 2>/dev/null; then
      info "安装 x86_64 PyInstaller..."
      arch -x86_64 "$VENV_X86_DIR/bin/pip" install pyinstaller --quiet
      ok "x86_64 PyInstaller 安装完成"
    else
      ok "x86_64 PyInstaller 已安装"
    fi
  fi

  # 添加 Rust x86_64 target（用于 Tauri 跨架构编译）
  rustup target add x86_64-apple-darwin 2>/dev/null || true
  ok "Rust x86_64-apple-darwin target 已就绪"

  info "x86_64 跨架构构建环境配置完成"
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

# ==================== 清理 instances 测试残留 ====================

info "清理 instances/ 测试残留..."
INSTANCE_CLEANED=0
for item in "$PROJECT_ROOT/instances/"*; do
  name=$(basename "$item")
  case "$name" in
    _template|xiaodazi|.gitignore) ;; # 白名单：保留
    *)
      rm -rf "$item"
      INSTANCE_CLEANED=$((INSTANCE_CLEANED + 1))
      ;;
  esac
done
if [ "$INSTANCE_CLEANED" -gt 0 ]; then
  info "已清理 $INSTANCE_CLEANED 个测试残留实例"
else
  ok "instances/ 目录干净，无需清理"
fi

# ==================== Tauri Updater 签名密钥 ====================

SIGN_KEY_FILE="$PROJECT_ROOT/keys/xiaodazi.key"
SIGN_KEY_PUB_FILE="$PROJECT_ROOT/keys/xiaodazi.key.pub"
SIGN_KEY_PWD_FILE="$PROJECT_ROOT/keys/xiaodazi.key.password"
TAURI_CONF="$FRONTEND_DIR/src-tauri/tauri.conf.json"

if [ -n "$TAURI_SIGNING_PRIVATE_KEY" ]; then
  ok "使用环境变量中的 updater 签名密钥"
elif [ -f "$SIGN_KEY_FILE" ] && [ -f "$SIGN_KEY_PWD_FILE" ]; then
  export TAURI_SIGNING_PRIVATE_KEY="$(cat "$SIGN_KEY_FILE")"
  export TAURI_SIGNING_PRIVATE_KEY_PASSWORD="$(cat "$SIGN_KEY_PWD_FILE")"
  ok "已加载 updater 签名密钥（含密码文件）"
else
  LOCAL_BUILD_PWD="xiaodazi-local-build"
  info "生成本地构建签名密钥..."
  mkdir -p "$PROJECT_ROOT/keys"
  rm -f "$SIGN_KEY_FILE" "$SIGN_KEY_PUB_FILE"
  cd "$FRONTEND_DIR"
  npx @tauri-apps/cli signer generate -w "$SIGN_KEY_FILE" -p "$LOCAL_BUILD_PWD" --ci --force 2>/dev/null || true

  if [ -f "$SIGN_KEY_FILE" ] && [ -f "$SIGN_KEY_PUB_FILE" ]; then
    export TAURI_SIGNING_PRIVATE_KEY="$(cat "$SIGN_KEY_FILE")"
    export TAURI_SIGNING_PRIVATE_KEY_PASSWORD="$LOCAL_BUILD_PWD"
    printf '%s' "$LOCAL_BUILD_PWD" > "$SIGN_KEY_PWD_FILE"

    NEW_PUBKEY=$(cat "$SIGN_KEY_PUB_FILE")
    $PYTHON_CMD -c "
import json, sys
with open('$TAURI_CONF', 'r') as f:
    conf = json.load(f)
conf.setdefault('plugins', {}).setdefault('updater', {})['pubkey'] = '''$NEW_PUBKEY'''
with open('$TAURI_CONF', 'w') as f:
    json.dump(conf, f, indent=2, ensure_ascii=False)
    f.write('\n')
"
    ok "已生成签名密钥并更新 tauri.conf.json pubkey"
  else
    warn "签名密钥生成失败，禁用 updater 签名..."
    $PYTHON_CMD -c "
import json
with open('$TAURI_CONF', 'r') as f:
    conf = json.load(f)
conf['bundle']['createUpdaterArtifacts'] = False
if 'plugins' in conf and 'updater' in conf['plugins']:
    del conf['plugins']['updater']
with open('$TAURI_CONF', 'w') as f:
    json.dump(conf, f, indent=2, ensure_ascii=False)
    f.write('\n')
"
    warn "已禁用 createUpdaterArtifacts，应用将不支持自动更新"
  fi
fi

# ==================== 确定构建目标 ====================

BUILD_ARCHES=""
case "$TARGET_ARCH" in
  native) BUILD_ARCHES="$NATIVE_ARCH" ;;
  arm64)  BUILD_ARCHES="arm64" ;;
  x86_64) BUILD_ARCHES="x86_64" ;;
  both)   BUILD_ARCHES="arm64 x86_64" ;;
esac

info "构建目标架构: $BUILD_ARCHES"

# ==================== 构建函数 ====================
#
# build_for_arch <arch>
#   执行 Steps 1-3 针对指定架构的完整构建。
#   参数: arm64 或 x86_64
#
# 构建流程：
#   Step 1: PyInstaller 打包后端（使用对应架构的 Python venv）
#   Step 2: Tauri 构建前端（使用 --target 指定 Rust 目标）
#   Step 3: macOS 后处理（复制 _internal、创建 symlink、签名、生成 DMG）
#
build_for_arch() {
  local arch="$1"
  local tauri_arch=$(arch_to_tauri_name "$arch")    # aarch64 or x86_64
  local rust_target=$(arch_to_rust_target "$arch")   # aarch64-apple-darwin or x86_64-apple-darwin

  local is_cross=false
  local build_python=""
  local arch_prefix=""

  # 确定是否为跨架构构建
  if [ "$arch" != "$NATIVE_ARCH" ]; then
    is_cross=true
  fi

  # 设置架构相关的构建参数
  if [ "$is_cross" = true ] && [ "$arch" = "x86_64" ] && [ "$NATIVE_ARCH" = "arm64" ]; then
    # ARM Mac 上构建 x86_64：通过 Rosetta 运行
    build_python="$X86_PYTHON_CMD"
    arch_prefix="arch -x86_64"
  else
    # 原生构建
    build_python="$PYTHON_CMD"
    arch_prefix=""
  fi

  info ""
  info "╔══════════════════════════════════════════════╗"
  info "║  构建目标: $arch ($rust_target)"
  if [ "$is_cross" = true ]; then
  info "║  模式: 跨架构 (通过 Rosetta)"
  else
  info "║  模式: 原生"
  fi
  info "║  Python: $build_python"
  info "╚══════════════════════════════════════════════╝"
  info ""

  # ==================== Step 1: 构建 Python 后端 ====================

  if [ "$SKIP_BACKEND" = false ]; then
    info "Step 1/3: 构建 Python 后端 [$arch] (PyInstaller onedir)..."
    info "使用 Python: $build_python ($($arch_prefix $build_python --version 2>&1))"
    cd "$PROJECT_ROOT"

    # 确保在 venv 环境中执行打包（PyInstaller 通过 sys.executable 获取 Python 路径）
    $arch_prefix $build_python scripts/build_backend.py
    info "Python 后端构建完成 [$arch]"
  else
    info "Step 1/3: 跳过 Python 后端构建 [$arch]"

    BINARY_COUNT=$(ls "$FRONTEND_DIR/src-tauri/binaries/xiaodazi-backend-"* 2>/dev/null | wc -l)
    if [ "$BINARY_COUNT" -eq 0 ]; then
      warn "binaries/ 目录中没有 sidecar 二进制文件"
      warn "如果要构建完整应用，请去掉 --skip-backend 参数"
    fi
  fi

  # ==================== Step 2: 构建 Tauri 应用 ====================

  info "Step 2/3: 构建 Tauri 应用 [$arch]..."
  cd "$FRONTEND_DIR"

  if [ ! -d "node_modules" ]; then
    info "安装前端依赖..."
    npm install
  fi

  unset CI

  if [ "$(uname)" = "Darwin" ]; then
    if [ "$is_cross" = true ]; then
      # 跨架构：指定 Rust target
      info "Tauri 跨架构编译: --target $rust_target"
      npm run tauri:build -- --target "$rust_target" --bundles app
    else
      npm run tauri:build -- --bundles app
    fi
  else
    npm run tauri:build
  fi

  # ==================== Step 3: macOS 后处理 ====================

  if [ "$(uname)" != "Darwin" ]; then
    return 0
  fi

  # 根据是否跨架构确定 .app 路径
  # - 原生构建: target/release/bundle/macos/
  # - 跨架构:   target/{rust_target}/release/bundle/macos/
  local bundle_base
  if [ "$is_cross" = true ]; then
    bundle_base="$FRONTEND_DIR/src-tauri/target/$rust_target/release/bundle/macos"
  else
    bundle_base="$FRONTEND_DIR/src-tauri/target/release/bundle/macos"
  fi

  local app_path=$(find "$bundle_base" -name "*.app" 2>/dev/null | head -1)
  local internal_src="$FRONTEND_DIR/src-tauri/binaries/_internal"
  local entitlements="$FRONTEND_DIR/src-tauri/entitlements.plist"

  if [ -z "$app_path" ]; then
    fail "找不到 .app bundle (搜索路径: $bundle_base)"
  fi

  local macos_dir="$app_path/Contents/MacOS"
  local resources_dir="$app_path/Contents/Resources"

  info "Step 3/3: macOS 后处理 [$arch]..."

  # 3a. 复制 _internal/ 到 Contents/Resources/
  if [ -d "$internal_src" ]; then
    info "复制 _internal/ 到 Contents/Resources/..."
    rm -rf "$resources_dir/_internal"
    cp -R "$internal_src" "$resources_dir/_internal"

    local file_count=$(find "$resources_dir/_internal" -type f | wc -l | tr -d ' ')
    local internal_size=$(du -sh "$resources_dir/_internal" | cut -f1)
    info "已复制 $file_count 个文件 ($internal_size)"
  else
    warn "_internal/ 目录不存在: $internal_src"
    warn "sidecar 可能无法启动，请确保已运行 Step 1"
  fi

  # 3b. 创建 symlink: Contents/MacOS/_internal -> ../Resources/_internal
  rm -rf "$macos_dir/_internal"
  ln -s "../Resources/_internal" "$macos_dir/_internal"
  info "已创建 symlink: MacOS/_internal -> ../Resources/_internal"

  # 3b2. 在 Contents/Frameworks/ 为 _internal/ 中所有内容创建 symlink
  local frameworks_dir="$app_path/Contents/Frameworks"
  mkdir -p "$frameworks_dir"
  local link_count=0
  if [ -d "$resources_dir/_internal" ]; then
    for item in "$resources_dir/_internal/"*; do
      local name=$(basename "$item")
      local target="$frameworks_dir/$name"
      if [ ! -e "$target" ] && [ ! -L "$target" ]; then
        ln -s "../Resources/_internal/$name" "$target"
        link_count=$((link_count + 1))
      fi
    done
    info "已在 Frameworks/ 创建 $link_count 个 symlink → Resources/_internal/"
  else
    warn "Resources/_internal/ 不存在，无法创建 Frameworks symlink"
  fi

  # 3c. 签名动态库
  info "签名动态库..."
  local sign_count=0

  if [ -d "$resources_dir/_internal" ]; then
    while IFS= read -r -d '' lib; do
      codesign --force --sign - "$lib" 2>/dev/null && sign_count=$((sign_count + 1))
    done < <(find "$resources_dir/_internal" \( -name "*.so" -o -name "*.dylib" \) -print0)
  fi
  info "已签名 $sign_count 个动态库"

  # 3d. 签名 sidecar
  local sidecar_path=$(find "$macos_dir" -maxdepth 1 -name "xiaodazi-backend*" -type f | head -1)
  if [ -n "$sidecar_path" ]; then
    info "签名 sidecar: $(basename "$sidecar_path")"
    if [ -f "$entitlements" ]; then
      codesign --force --sign - --entitlements "$entitlements" "$sidecar_path"
    else
      codesign --force --sign - "$sidecar_path"
    fi
  fi

  # 3e. 签名 app bundle
  info "签名 app bundle: $(basename "$app_path")"
  if [ -f "$entitlements" ]; then
    codesign --force --sign - --entitlements "$entitlements" "$app_path"
  else
    codesign --force --sign - "$app_path"
  fi

  # 3f. 验证签名
  if codesign --verify --deep "$app_path" 2>/dev/null; then
    info "签名验证通过 [$arch]"
  else
    warn "签名验证失败 [$arch]（可能不影响本地使用）"
  fi

  # 3g. 生成 DMG
  info "生成 DMG 安装包 [$arch]..."

  local version=$(cat "$PROJECT_ROOT/VERSION" 2>/dev/null || echo "0.0.0")
  local dmg_dir="$FRONTEND_DIR/src-tauri/target/release/bundle/dmg"
  local dmg_filename="$(basename "$app_path" .app)_${version}_${tauri_arch}.dmg"
  local dmg_path="$dmg_dir/$dmg_filename"
  local vol_name=$(basename "$app_path" .app)
  local tmp_dmg="/tmp/xiaodazi_dmg_tmp_${arch}.dmg"
  local tmp_mount="/tmp/xiaodazi_dmg_mount_${arch}"

  mkdir -p "$dmg_dir"

  rm -f "$tmp_dmg" "$dmg_path"
  [ -d "$tmp_mount" ] && hdiutil detach "$tmp_mount" 2>/dev/null || true

  # 动态计算 DMG 大小
  local app_size_mb=$(du -sm "$app_path" | cut -f1)
  local dmg_size_mb=$(( app_size_mb + 50 ))
  info ".app 大小: ${app_size_mb}MB, DMG 预留: ${dmg_size_mb}MB"

  hdiutil create -size "${dmg_size_mb}m" -fs HFS+ -volname "$vol_name" "$tmp_dmg" -quiet
  mkdir -p "$tmp_mount"
  hdiutil attach "$tmp_dmg" -mountpoint "$tmp_mount" -quiet
  cp -R "$app_path" "$tmp_mount/"
  ln -s /Applications "$tmp_mount/Applications"
  hdiutil detach "$tmp_mount" -quiet

  hdiutil convert "$tmp_dmg" -format UDZO -o "$dmg_path" -quiet

  rm -f "$tmp_dmg"
  rmdir "$tmp_mount" 2>/dev/null || true

  local dmg_size=$(du -h "$dmg_path" | cut -f1)
  info "DMG 生成完成: $dmg_filename ($dmg_size)"
  info "macOS 后处理完成 [$arch]"
}

# ==================== 执行构建 ====================

for build_arch in $BUILD_ARCHES; do
  build_for_arch "$build_arch"
done

# ==================== 构建完成 ====================

info ""
info "============================================"
info "  构建完成!"
info "  本机架构: $NATIVE_ARCH"
info "  构建目标: $BUILD_ARCHES"
info "============================================"
info ""

# 复制产物到项目根目录，方便查找
OUTPUT_DIR="$PROJECT_ROOT/dist"
mkdir -p "$OUTPUT_DIR"

if [ "$(uname)" = "Darwin" ]; then
  # 收集所有架构的 DMG
  DMG_COUNT=0
  while IFS= read -r -d '' dmg; do
    cp -f "$dmg" "$OUTPUT_DIR/"
    SIZE=$(du -h "$dmg" | cut -f1)
    info "DMG: $OUTPUT_DIR/$(basename "$dmg") ($SIZE)"
    DMG_COUNT=$((DMG_COUNT + 1))
  done < <(find "$FRONTEND_DIR/src-tauri/target" -path "*/bundle/dmg/*.dmg" -print0 2>/dev/null)

  if [ "$DMG_COUNT" -eq 0 ]; then
    warn "未找到 DMG 产物"
  fi

  # 显示 .app 路径
  for build_arch in $BUILD_ARCHES; do
    local_rust_target=$(arch_to_rust_target "$build_arch")
    if [ "$build_arch" != "$NATIVE_ARCH" ]; then
      app=$(find "$FRONTEND_DIR/src-tauri/target/$local_rust_target/release/bundle/macos" -name "*.app" 2>/dev/null | head -1)
    else
      app=$(find "$FRONTEND_DIR/src-tauri/target/release/bundle/macos" -name "*.app" 2>/dev/null | head -1)
    fi
    if [ -n "$app" ]; then
      SIZE=$(du -sh "$app" | cut -f1)
      info "APP [$build_arch]: $app ($SIZE)"
    fi
  done

elif [ "$(uname -o 2>/dev/null)" = "Msys" ] || [ "$(uname -o 2>/dev/null)" = "Cygwin" ]; then
  EXE_PATH=$(find "$FRONTEND_DIR/src-tauri/target/release/bundle/nsis" -name "*.exe" 2>/dev/null | head -1)
  if [ -n "$EXE_PATH" ]; then
    cp -f "$EXE_PATH" "$OUTPUT_DIR/"
    info "Installer: $OUTPUT_DIR/$(basename "$EXE_PATH")"
  fi
fi

info ""
info "产物目录: $OUTPUT_DIR/"
