#!/bin/bash
#
# xiaodazi 一键安装/升级脚本
#
# 面向终端用户：在本机编译并安装 xiaodazi.app 到 /Applications
# 全自动处理依赖安装、源码下载、编译、安装、升级覆盖
#
# Quick Start (直接在 Terminal 中粘贴):
#   bash <(curl -fsSL https://raw.githubusercontent.com/malue-ai/dazee-small/main/scripts/auto_build_app.sh)
#
# 高级用法:
#   bash scripts/auto_build_app.sh                      # 编译 + 安装到 /Applications
#   bash scripts/auto_build_app.sh --no-install          # 仅编译，不安装（开发者模式）
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

REPO_URL="${REPO_URL:-https://github.com/malue-ai/dazee-small.git}"
REPO_BRANCH="${REPO_BRANCH:-main}"
DEFAULT_CLONE_DIR="$HOME/dazee-small"

# When run via process substitution (bash <(curl ...)), $0 becomes /dev/fd/N.
# In that case, fall back to the current working directory as the project root.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd 2>/dev/null || echo "")"
IS_CURL_MODE=false
if [[ -z "$SCRIPT_DIR" || "$SCRIPT_DIR" == /dev/fd* || "$SCRIPT_DIR" == /dev ]]; then
  IS_CURL_MODE=true
  PROJECT_ROOT="$(pwd)"
  SCRIPT_DIR="$PROJECT_ROOT/scripts"
else
  PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

is_valid_project() {
  [ -d "$1/frontend" ] && [ -f "$1/VERSION" ]
}

if ! is_valid_project "$PROJECT_ROOT"; then
  if [ "$IS_CURL_MODE" = true ]; then
    echo ""
    echo "===> 当前目录 ($(pwd)) 不是项目根目录，正在自动查找..."
    echo ""

    # 在常见位置搜索已有项目
    FOUND=false
    for candidate in \
      "$HOME/dazee-small" \
      "$HOME/xiaodazi" \
      "$HOME/zenflux_agent" \
      "$HOME/Desktop/dazee-small" \
      "$HOME/Documents/dazee-small"; do
      if is_valid_project "$candidate"; then
        PROJECT_ROOT="$candidate"
        FOUND=true
        echo "  ✓  在 $candidate 找到项目"
        break
      fi
    done

    # 未找到 → 自动 clone
    if [ "$FOUND" = false ]; then
      CLONE_DIR="${CLONE_DIR:-$DEFAULT_CLONE_DIR}"
      echo "  未找到已有项目，正在自动下载源码..."
      echo ""
      echo "  仓库: $REPO_URL"
      echo "  分支: $REPO_BRANCH"
      echo "  位置: $CLONE_DIR"
      echo ""

      if ! command -v git &>/dev/null; then
        echo ""
        echo "ERROR: 需要 git 来下载源码"
        echo ""
        echo "  请先安装 git："
        echo "    macOS:  xcode-select --install"
        echo "    Ubuntu: sudo apt install git"
        echo ""
        exit 1
      fi

      if [ -d "$CLONE_DIR" ]; then
        echo "  目录 $CLONE_DIR 已存在但不是有效项目，正在删除后重新下载..."
        rm -rf "$CLONE_DIR"
      fi

      git clone --depth 1 --branch "$REPO_BRANCH" "$REPO_URL" "$CLONE_DIR"
      if [ $? -ne 0 ]; then
        echo ""
        echo "ERROR: 源码下载失败"
        echo ""
        echo "  请检查："
        echo "    1. 网络连接是否正常"
        echo "    2. 仓库地址是否正确: $REPO_URL"
        echo "    3. 或手动 clone 后重试："
        echo "       git clone $REPO_URL $CLONE_DIR"
        echo "       cd $CLONE_DIR && bash scripts/auto_build_app.sh"
        echo ""
        exit 1
      fi

      PROJECT_ROOT="$CLONE_DIR"

      if ! is_valid_project "$PROJECT_ROOT"; then
        echo ""
        echo "ERROR: 下载的源码结构不正确（找不到 frontend/ 或 VERSION 文件）"
        echo ""
        exit 1
      fi

      echo ""
      echo "  ✓  源码下载完成: $PROJECT_ROOT"
    fi
  else
    echo ""
    echo "ERROR: 项目根目录无效: $PROJECT_ROOT"
    echo "  找不到 frontend/ 或 VERSION 文件，请确认脚本位于正确的项目中"
    echo ""
    exit 1
  fi
fi

echo ""
echo "===> 项目根目录: $PROJECT_ROOT"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
VENV_DIR="$PROJECT_ROOT/.venv"
VENV_X86_DIR="$PROJECT_ROOT/.venv-x86_64"
PYTHON_VERSION="3.12"
NODE_MAJOR_VERSION="20"
NATIVE_ARCH=$(uname -m)  # arm64 or x86_64

SKIP_BACKEND=false
CLEAN=false
DRY_RUN=false
NO_INSTALL=false
TARGET_ARCH="native"

# ==================== 参数解析 ====================

while [ $# -gt 0 ]; do
  case "$1" in
    --skip-backend) SKIP_BACKEND=true ;;
    --clean)        CLEAN=true ;;
    --dry-run)      DRY_RUN=true ;;
    --no-install)   NO_INSTALL=true ;;
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

cd "$FRONTEND_DIR" || fail "前端目录不存在: $FRONTEND_DIR"
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
[ -f "$PROJECT_ROOT/scripts/sync_version.py" ] || fail "找不到版本同步脚本: $PROJECT_ROOT/scripts/sync_version.py"
$PYTHON_CMD "$PROJECT_ROOT/scripts/sync_version.py" || fail "版本同步失败"

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
    cd "$PROJECT_ROOT" || fail "项目根目录不存在: $PROJECT_ROOT"

    [ -f "$PROJECT_ROOT/scripts/build_backend.py" ] || fail "找不到构建脚本: $PROJECT_ROOT/scripts/build_backend.py"
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
  cd "$FRONTEND_DIR" || fail "前端目录不存在: $FRONTEND_DIR"

  if [ ! -d "node_modules" ]; then
    info "安装前端依赖..."
    npm install
  fi

  unset CI

  # 设置 Tauri updater 签名密钥
  if [ -z "$TAURI_SIGNING_PRIVATE_KEY" ]; then
    local sign_key_file="$PROJECT_ROOT/keys/xiaodazi.key"
    local sign_key_pwd_file="$PROJECT_ROOT/keys/xiaodazi.key.password"
    if [ -f "$sign_key_file" ]; then
      export TAURI_SIGNING_PRIVATE_KEY="$(cat "$sign_key_file")"
      if [ -f "$sign_key_pwd_file" ]; then
        export TAURI_SIGNING_PRIVATE_KEY_PASSWORD="$(cat "$sign_key_pwd_file")"
      elif [ -z "$TAURI_SIGNING_PRIVATE_KEY_PASSWORD" ]; then
        export TAURI_SIGNING_PRIVATE_KEY_PASSWORD=""
      fi
      info "已加载 updater 签名密钥"
    else
      warn "未找到 updater 签名密钥（开发构建）"
      info "生成临时签名密钥..."
      local temp_key_dir=$(mktemp -d)
      local dev_key_pwd="dev-build-temp"
      local tauri_cli="$FRONTEND_DIR/node_modules/.bin/tauri"
      if [ -x "$tauri_cli" ]; then
        "$tauri_cli" signer generate -p "$dev_key_pwd" -w "$temp_key_dir/temp.key"
      else
        npx --yes @tauri-apps/cli signer generate -p "$dev_key_pwd" -w "$temp_key_dir/temp.key"
      fi
      if [ -f "$temp_key_dir/temp.key" ]; then
        export TAURI_SIGNING_PRIVATE_KEY="$(cat "$temp_key_dir/temp.key")"
        export TAURI_SIGNING_PRIVATE_KEY_PASSWORD="$dev_key_pwd"
        info "已生成临时密钥（更新包签名仅用于本次构建，不可用于正式发布）"
      else
        warn "临时密钥生成失败，构建可能会报错"
      fi
      rm -rf "$temp_key_dir"
    fi
  else
    info "使用环境变量中的 updater 签名密钥"
  fi

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

    # PyInstaller 6.x bootloader 根据构建时的 Python 安装类型查找共享库：
    #   - Framework Python (python.org): 查找 "Python"
    #   - Homebrew Python: 查找 "libpython3.XX.dylib"
    # 确保两种名字都能找到，无论构建机器用的是哪种 Python
    if [ ! -e "$frameworks_dir/Python" ] && [ ! -L "$frameworks_dir/Python" ]; then
      local py_lib=$(find "$resources_dir/_internal" -maxdepth 1 -name "libpython3*.dylib" -type f 2>/dev/null | head -1)
      if [ -n "$py_lib" ]; then
        ln -s "../Resources/_internal/$(basename "$py_lib")" "$frameworks_dir/Python"
        info "已创建 Python 库兼容 symlink: Frameworks/Python → $(basename "$py_lib")"
      fi
    fi
    for py_lib in "$resources_dir/_internal"/libpython3*.dylib; do
      [ -e "$py_lib" ] || continue
      local py_name=$(basename "$py_lib")
      if [ ! -e "$frameworks_dir/$py_name" ] && [ ! -L "$frameworks_dir/$py_name" ]; then
        ln -s "../Resources/_internal/$py_name" "$frameworks_dir/$py_name"
      fi
    done
  else
    warn "Resources/_internal/ 不存在，无法创建 Frameworks symlink"
  fi

  # 3c. 签名动态库
  info "签名动态库..."
  local sign_count=0

  if [ -d "$resources_dir/_internal" ]; then
    while IFS= read -r -d '' lib; do
      codesign --force --sign - "$lib" 2>/dev/null && sign_count=$((sign_count + 1))
    done < <(find "$resources_dir/_internal" '(' -name "*.so" -o -name "*.dylib" ')' -print0)
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

# ==================== 构建完成 · 安装 ====================

info ""
info "============================================"
info "  编译完成!"
info "============================================"
info ""

# ---------- 查找构建产物 ----------

BUILT_APP=""
for build_arch in $BUILD_ARCHES; do
  local_rust_target=$(arch_to_rust_target "$build_arch")
  if [ "$build_arch" != "$NATIVE_ARCH" ]; then
    BUILT_APP=$(find "$FRONTEND_DIR/src-tauri/target/$local_rust_target/release/bundle/macos" -name "*.app" -maxdepth 1 2>/dev/null | head -1)
  else
    BUILT_APP=$(find "$FRONTEND_DIR/src-tauri/target/release/bundle/macos" -name "*.app" -maxdepth 1 2>/dev/null | head -1)
  fi
  [ -n "$BUILT_APP" ] && break
done

if [ -z "$BUILT_APP" ]; then
  fail "编译完成但未找到 .app 文件，请检查构建日志"
fi

APP_SIZE=$(du -sh "$BUILT_APP" | cut -f1)
APP_BASENAME=$(basename "$BUILT_APP" .app)
info "产物: $(basename "$BUILT_APP") ($APP_SIZE)"

# ---------- 复制 DMG 到 dist/ ----------

OUTPUT_DIR="$PROJECT_ROOT/dist"
mkdir -p "$OUTPUT_DIR"

if [ "$(uname)" = "Darwin" ]; then
  while IFS= read -r -d '' dmg; do
    cp -f "$dmg" "$OUTPUT_DIR/"
  done < <(find "$FRONTEND_DIR/src-tauri/target" -path "*/bundle/dmg/*.dmg" -print0 2>/dev/null)
elif [ "$(uname -o 2>/dev/null)" = "Msys" ] || [ "$(uname -o 2>/dev/null)" = "Cygwin" ]; then
  EXE_PATH=$(find "$FRONTEND_DIR/src-tauri/target/release/bundle/nsis" -name "*.exe" 2>/dev/null | head -1)
  [ -n "$EXE_PATH" ] && cp -f "$EXE_PATH" "$OUTPUT_DIR/"
fi

# ---------- macOS 自动安装到 /Applications ----------

if [ "$(uname)" = "Darwin" ] && [ "$NO_INSTALL" = false ]; then

  INSTALL_DIR="/Applications"
  INSTALL_PATH="$INSTALL_DIR/$(basename "$BUILT_APP")"

  # 检测旧版本是否正在运行
  if pgrep -xq "$APP_BASENAME" 2>/dev/null; then
    info "检测到 $APP_BASENAME 正在运行，正在关闭..."
    osascript -e "tell application \"$APP_BASENAME\" to quit" 2>/dev/null || true
    sleep 2
    # 仍在运行则强制关闭
    if pgrep -xq "$APP_BASENAME" 2>/dev/null; then
      pkill -x "$APP_BASENAME" 2>/dev/null || true
      sleep 1
    fi
  fi

  # 处理已有安装（升级覆盖）
  if [ -d "$INSTALL_PATH" ]; then
    info "检测到已安装版本，正在升级覆盖..."
    rm -rf "$INSTALL_PATH" 2>/dev/null || {
      warn "无法直接覆盖 $INSTALL_PATH，尝试使用 sudo..."
      sudo rm -rf "$INSTALL_PATH" || {
        warn "无法覆盖 /Applications 中的旧版本，安装到 ~/Applications/"
        INSTALL_DIR="$HOME/Applications"
        INSTALL_PATH="$INSTALL_DIR/$(basename "$BUILT_APP")"
        mkdir -p "$INSTALL_DIR"
        rm -rf "$INSTALL_PATH" 2>/dev/null || true
      }
    }
  fi

  # 复制 .app 到安装目录
  info "安装到 $INSTALL_PATH ..."
  cp -R "$BUILT_APP" "$INSTALL_PATH" 2>/dev/null || {
    warn "无法安装到 /Applications，尝试 ~/Applications/"
    INSTALL_DIR="$HOME/Applications"
    INSTALL_PATH="$INSTALL_DIR/$(basename "$BUILT_APP")"
    mkdir -p "$INSTALL_DIR"
    cp -R "$BUILT_APP" "$INSTALL_PATH" || fail "安装失败：无法复制到 $INSTALL_PATH"
  }

  # 去除 quarantine 属性（本机编译的 app 无需 Gatekeeper 验证）
  xattr -cr "$INSTALL_PATH" 2>/dev/null || true

  echo ""
  echo "  ╔══════════════════════════════════════════════════╗"
  echo "  ║                                                  ║"
  echo "  ║   ✅  安装成功!                                  ║"
  echo "  ║                                                  ║"
  echo "  ║   应用位置: $INSTALL_PATH"
  echo "  ║                                                  ║"
  echo "  ║   启动方式:                                      ║"
  echo "  ║     • Launchpad 中搜索 \"$APP_BASENAME\"             ║"
  echo "  ║     • 或 Finder → 应用程序 → $APP_BASENAME          ║"
  echo "  ║                                                  ║"
  echo "  ╚══════════════════════════════════════════════════╝"
  echo ""

  # 询问是否立即启动（10 秒超时自动启动）
  printf "  是否现在启动 %s？[Y/n] " "$APP_BASENAME"
  read -r -t 10 LAUNCH_ANSWER < /dev/tty 2>/dev/null || LAUNCH_ANSWER="y"
  echo ""

  if [[ ! "$LAUNCH_ANSWER" =~ ^[Nn]$ ]]; then
    open "$INSTALL_PATH"
    info "$APP_BASENAME 已启动 🚀"
  fi

elif [ "$NO_INSTALL" = true ]; then
  info ""
  info "已跳过安装（--no-install 模式）"
  info "构建产物位置:"
  info "  APP: $BUILT_APP"
  info "  DMG: $OUTPUT_DIR/"
fi
