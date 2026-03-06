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
#   - Python 虚拟环境 + pip 依赖（requirements-dev.txt = 运行时依赖 + 构建工具）
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
# 镜像源（中国大陆 / 海外）：
# - 默认自动检测：同时探测 GitHub 与清华 TUNA 的延迟，大陆环境自动用国内镜像，海外用官方源
# - 强制国内镜像：USE_CHINA_MIRROR=1 bash scripts/auto_build_app.sh
# - 强制官方源：  USE_CHINA_MIRROR=0 bash scripts/auto_build_app.sh
# 国内镜像包括：Homebrew 清华 TUNA、pip 清华、npm npmmirror、Rust 中科大
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

# 面向小白：长时间步骤开始提示（预计时间可选）
# 用法: long_step_begin "正在安装 Python" "约 3–5 分钟"
long_step_begin() {
  local desc="$1"
  local estimate="${2:-}"
  if [ -n "$estimate" ]; then
    echo ""
    info "⏳ $desc（预计 $estimate，请耐心等待）"
  else
    echo ""
    info "⏳ $desc..."
  fi
}

# 长时间步骤结束
long_step_end() {
  local desc="$1"
  ok "${desc}完成"
}

# 面向小白：结构化错误与下一步建议
# 用法: fail_with_help "简短错误描述" "可能原因（多行）" "建议操作（多行，每行一条）"
fail_with_help() {
  local err_title="$1"
  local reasons="$2"
  local actions="$3"
  echo ""
  echo "============================================"
  echo "  ❌ 错误：$err_title"
  echo "============================================"
  echo "可能原因："
  echo "$reasons"
  echo ""
  echo "建议操作："
  echo "$actions"
  echo ""
  echo "若仍无法解决，请将上述错误信息与终端完整输出保存后反馈给开发者。"
  echo "============================================"
  echo ""
  exit 1
}

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

# ==================== 镜像源配置 ====================
#
# 当官方源因网络问题安装失败时，自动切换到国内镜像源重试。
# 镜像源列表：
#   Homebrew — 清华 TUNA
#   pip      — 清华 TUNA
#   npm      — npmmirror（原淘宝源）
#   Rust     — 中科大 USTC
#

USING_MIRROR=false
PIP_MIRROR_ARGS=""
RUST_INSTALL_URL="https://sh.rustup.rs"
HOMEBREW_MIRROR_INSTALL_URL="https://mirrors.tuna.tsinghua.edu.cn/git/homebrew/install/raw/HEAD/install.sh"
CURL_TIMEOUT="--connect-timeout 10 --max-time 30"

# 自动检测是否为中国大陆网络（用于默认选国内镜像）
# 同时探测 GitHub 与清华 TUNA 的响应时间；若 GitHub 不可达或明显慢于 TUNA，判定为大陆环境
# 输出 "cn" 或 "overseas"，无外部 API 依赖、不传 IP
detect_region_for_mirror() {
  local gh_time tuna_time
  gh_time=$(curl -s -o /dev/null -w '%{time_total}' --connect-timeout 3 --max-time 5 https://api.github.com 2>/dev/null) || true
  tuna_time=$(curl -s -o /dev/null -w '%{time_total}' --connect-timeout 3 --max-time 5 https://mirrors.tuna.tsinghua.edu.cn 2>/dev/null) || true
  [ -z "$gh_time" ] && gh_time=999
  [ -z "$tuna_time" ] && tuna_time=999
  # 中国大陆：GitHub 不可达/很慢，或国内镜像明显更快
  if echo "$gh_time $tuna_time" | awk 'BEGIN {r="overseas"} $1+0 >= 3.5 || $1+0 == 0 {r="cn"} $2+0 > 0 && $2+0 < 2.5 && $1+0 > 2 {r="cn"} END {print r}' | grep -q cn; then
    echo "cn"
  else
    echo "overseas"
  fi
}

# 区分中国大陆 / 海外源：
# - 若已设置 USE_CHINA_MIRROR=1：直接使用国内镜像
# - 若已设置 USE_CHINA_MIRROR=0：强制使用官方源，不自动检测
# - 未设置：自动检测（GitHub vs 清华 TUNA 可达性/延迟），大陆默认国内镜像，海外默认官方源
check_network_and_setup_mirrors() {
  info "检测网络与镜像源（中国大陆 / 海外）..."

  if [ -n "${USE_CHINA_MIRROR:-}" ] && [ "$USE_CHINA_MIRROR" != "0" ]; then
    info "已设置 USE_CHINA_MIRROR，使用国内镜像源（Homebrew 清华 / pip 清华 / npm npmmirror / Rust 中科大）"
    MIRROR_EXPLICIT_CN=1 setup_brew_mirror
    MIRROR_EXPLICIT_CN=1 setup_pip_mirror
    MIRROR_EXPLICIT_CN=1 setup_npm_mirror
    MIRROR_EXPLICIT_CN=1 setup_rust_mirror
    ok "国内镜像已启用，后续 brew/pip/npm/rust 将走国内源"
    echo ""
    return 0
  fi

  if [ -n "${USE_CHINA_MIRROR:-}" ] && [ "$USE_CHINA_MIRROR" = "0" ]; then
    ok "已设置 USE_CHINA_MIRROR=0，使用官方源（海外）"
    echo ""
    return 0
  fi

  # 自动检测：大陆默认国内镜像，海外默认官方源
  local region
  region=$(detect_region_for_mirror)
  if [ "$region" = "cn" ]; then
    info "检测到中国大陆网络环境（GitHub 较慢或不可达），自动使用国内镜像源"
    setup_brew_mirror
    setup_pip_mirror
    setup_npm_mirror
    setup_rust_mirror
    ok "国内镜像已启用，后续 brew/pip/npm/rust 将走国内源"
    echo ""
    return 0
  fi

  ok "检测到海外网络环境，使用官方源"
  echo "  💡 若实际在中国大陆且下载很慢，可强制国内镜像：USE_CHINA_MIRROR=1 bash scripts/auto_build_app.sh"
  echo ""
}

setup_brew_mirror() {
  if [ "$USING_MIRROR" = true ] && [ -n "${HOMEBREW_BOTTLE_DOMAIN:-}" ]; then
    return 0
  fi
  if [ -n "${MIRROR_EXPLICIT_CN:-}" ]; then
    info "Homebrew 使用国内镜像（清华 TUNA）"
  else
    warn "切换 Homebrew 到国内镜像源（清华 TUNA）..."
  fi
  export HOMEBREW_BREW_GIT_REMOTE="https://mirrors.tuna.tsinghua.edu.cn/git/homebrew/brew.git"
  export HOMEBREW_CORE_GIT_REMOTE="https://mirrors.tuna.tsinghua.edu.cn/git/homebrew/homebrew-core.git"
  export HOMEBREW_API_DOMAIN="https://mirrors.tuna.tsinghua.edu.cn/homebrew-bottles/api"
  export HOMEBREW_BOTTLE_DOMAIN="https://mirrors.tuna.tsinghua.edu.cn/homebrew-bottles"
  USING_MIRROR=true
}

setup_pip_mirror() {
  if [ -n "$PIP_MIRROR_ARGS" ]; then
    return 0
  fi
  if [ -n "${MIRROR_EXPLICIT_CN:-}" ]; then
    info "pip 使用国内镜像（清华 TUNA）"
  else
    warn "切换 pip 到国内镜像源（清华 TUNA）..."
  fi
  PIP_MIRROR_ARGS="-i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn"
  USING_MIRROR=true
}

setup_npm_mirror() {
  if [ -n "${npm_config_registry:-}" ]; then
    return 0
  fi
  if [ -n "${MIRROR_EXPLICIT_CN:-}" ]; then
    info "npm 使用国内镜像（npmmirror）"
  else
    warn "切换 npm 到国内镜像源（npmmirror）..."
  fi
  export npm_config_registry="https://registry.npmmirror.com"
  USING_MIRROR=true
}

setup_rust_mirror() {
  if [ "$RUST_INSTALL_URL" != "https://sh.rustup.rs" ]; then
    return 0
  fi
  if [ -n "${MIRROR_EXPLICIT_CN:-}" ]; then
    info "Rust 使用国内镜像（中科大 USTC）"
  else
    warn "切换 Rust 到国内镜像源（中科大 USTC）..."
  fi
  export RUSTUP_DIST_SERVER="https://mirrors.ustc.edu.cn/rust-static"
  export RUSTUP_UPDATE_ROOT="https://mirrors.ustc.edu.cn/rust-static/rustup"
  RUST_INSTALL_URL="https://mirrors.ustc.edu.cn/misc/rustup-install.sh"
  USING_MIRROR=true
}

brew_install_or_mirror() {
  local pkg="$1"
  local arch_prefix="${2:-}"

  if [ -n "${HOMEBREW_BOTTLE_DOMAIN:-}" ]; then
    $arch_prefix brew install "$pkg" 2>&1
    return $?
  fi

  if $arch_prefix brew install "$pkg" 2>&1; then
    return 0
  fi

  warn "brew install $pkg 失败，切换到镜像源重试..."
  setup_brew_mirror
  $arch_prefix brew install "$pkg" 2>&1
}

pip_install_or_mirror() {
  local pip_cmd="$1"
  shift
  local arch_prefix=""
  if [ "$1" = "--arch-prefix" ]; then
    shift
    arch_prefix="$1"
    shift
  fi

  if [ -n "$PIP_MIRROR_ARGS" ]; then
    $arch_prefix $pip_cmd install $PIP_MIRROR_ARGS "$@" 2>&1
    return $?
  fi

  if $arch_prefix $pip_cmd install "$@" 2>&1; then
    return 0
  fi

  warn "pip install 失败，切换到镜像源重试..."
  setup_pip_mirror
  $arch_prefix $pip_cmd install $PIP_MIRROR_ARGS "$@" 2>&1
}

npm_install_or_mirror() {
  if [ -n "${npm_config_registry:-}" ]; then
    npm install 2>&1
    return $?
  fi

  if npm install 2>&1; then
    return 0
  fi

  warn "npm install 失败，切换到镜像源重试..."
  setup_npm_mirror
  npm install 2>&1
}

# 自动安装 Homebrew（原生架构）
install_homebrew() {
  if has_cmd brew; then
    return 0
  fi

  if [ -n "${HOMEBREW_BOTTLE_DOMAIN:-}" ]; then
    long_step_begin "安装 Homebrew（镜像源）" "约 2–5 分钟"
    /bin/bash -c "$(curl $CURL_TIMEOUT -fsSL "$HOMEBREW_MIRROR_INSTALL_URL")" 2>&1 || true
    ensure_brew_path
    if ! has_cmd brew; then
      fail_with_help "Homebrew 安装失败（镜像源）" \
        "• 网络不稳定或镜像源暂时不可用\n• 安装脚本需要交互时被非交互环境跳过" \
        "1. 手动安装：打开 https://brew.sh 按页面说明安装
2. 安装完成后在终端执行：eval \"\$(/opt/homebrew/bin/brew shellenv)\" 或 eval \"\$(/usr/local/bin/brew shellenv)\"
3. 重新运行本脚本：bash scripts/auto_build_app.sh"
    fi
    long_step_end "Homebrew（镜像源）"
    export HOMEBREW_NO_AUTO_UPDATE=1
    ok "Homebrew 安装完成（镜像源）"
    return 0
  fi

  long_step_begin "安装 Homebrew" "约 2–5 分钟"
  if /bin/bash -c "$(curl $CURL_TIMEOUT -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" 2>&1; then
    ensure_brew_path
    if has_cmd brew; then
      export HOMEBREW_NO_AUTO_UPDATE=1
      long_step_end "Homebrew"
      return 0
    fi
  fi

  warn "官方源安装失败，尝试使用国内镜像源..."
  setup_brew_mirror
  /bin/bash -c "$(curl $CURL_TIMEOUT -fsSL "$HOMEBREW_MIRROR_INSTALL_URL")" 2>&1 || true
  ensure_brew_path
  if ! has_cmd brew; then
    fail_with_help "Homebrew 安装失败（官方源和镜像源均失败）" \
      "• 无法连接 GitHub（可尝试开启 VPN 或使用镜像）\n• 安装脚本需要输入密码或确认时未完成\n• 磁盘空间不足或权限不足" \
      "1. 手动安装：打开 https://brew.sh 按页面说明执行安装命令
2. 若在国内网络，可改用国内安装脚本：https://mirrors.tuna.tsinghua.edu.cn/help/homebrew/
3. 安装完成后根据提示执行 PATH 配置（如 eval \"\$(/opt/homebrew/bin/brew shellenv)\"）
4. 再运行本脚本：bash scripts/auto_build_app.sh"
  fi
  export HOMEBREW_NO_AUTO_UPDATE=1
  long_step_end "Homebrew（镜像源）"
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

check_network_and_setup_mirrors

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
      # macOS ships a /usr/bin/python3 stub that triggers an Xcode CLT install
      # dialog when executed. Skip it to avoid the unwanted popup — Homebrew
      # will install a real Python later if needed.
      if [ "$(uname)" = "Darwin" ]; then
        local cmd_path
        cmd_path=$(command -v "$cmd" 2>/dev/null)
        if [ "$cmd_path" = "/usr/bin/$cmd" ] && ! xcode-select -p &>/dev/null; then
          continue
        fi
      fi
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
  # On macOS without Xcode CLT, /usr/bin/python3 is a stub that triggers
  # an install dialog — avoid calling it, just report "not installed".
  _has_real_python=false
  if has_cmd python3; then
    _py_path=$(command -v python3 2>/dev/null)
    if [ "$(uname)" != "Darwin" ] || [ "$_py_path" != "/usr/bin/python3" ] || xcode-select -p &>/dev/null; then
      _has_real_python=true
    fi
  fi
  if [ "$_has_real_python" = true ]; then
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
    long_step_begin "通过 Homebrew 安装 Python ${PYTHON_VERSION}" "约 2–5 分钟"
    brew_install_or_mirror "python@${PYTHON_VERSION}" || true
    ensure_brew_path
    BREW_PYTHON_PREFIX=$(brew --prefix "python@${PYTHON_VERSION}" 2>/dev/null || true)
    if [ -n "$BREW_PYTHON_PREFIX" ] && [ -d "$BREW_PYTHON_PREFIX/bin" ]; then
      export PATH="$BREW_PYTHON_PREFIX/bin:$PATH"
    fi
    # 尝试链接（已链接时会返回非零，忽略）
    brew link --overwrite "python@${PYTHON_VERSION}" 2>/dev/null || true
    long_step_end "Python ${PYTHON_VERSION}"
  else
    fail_with_help "当前系统不支持自动安装 Python" \
      "• 本脚本在 macOS 上可通过 Homebrew 自动安装 Python" \
      "1. 请手动安装 Python 3.12 或 3.13：https://www.python.org/downloads/
2. 安装后确保 python3 或 python3.12 在 PATH 中
3. 再运行本脚本：bash scripts/auto_build_app.sh"
  fi
  PYTHON_CMD=$(find_python || true)
  if [ -z "$PYTHON_CMD" ]; then
    fail_with_help "Python 安装后仍未找到" \
      "• Homebrew 已安装但 PATH 未包含 Python\n• 或 python@${PYTHON_VERSION} 未正确链接" \
      "1. 在终端执行：brew --prefix python@${PYTHON_VERSION}，记下输出路径
2. 将该路径下的 bin 加入 PATH，例如：export PATH=\"\$(brew --prefix python@${PYTHON_VERSION})/bin:\$PATH\"
3. 再运行本脚本：bash scripts/auto_build_app.sh
4. 或从 https://www.python.org/downloads/ 安装官方 Python 并确保在 PATH 中"
  fi
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
      long_step_begin "通过 Homebrew 升级 Node.js" "约 2–5 分钟"
      brew_install_or_mirror "node@${NODE_MAJOR_VERSION}" || true
      brew link --overwrite "node@${NODE_MAJOR_VERSION}" 2>/dev/null || true
      ensure_brew_path
      long_step_end "Node.js 升级"
    else
      fail_with_help "Node.js 版本过旧，且当前系统不支持自动升级" \
        "• 需要 Node.js >= 18（当前 $(node --version)）" \
        "1. 请手动安装或升级 Node.js：https://nodejs.org
2. 安装后确认 node --version >= 18
3. 再运行本脚本：bash scripts/auto_build_app.sh"
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
    long_step_begin "通过 Homebrew 安装 Node.js ${NODE_MAJOR_VERSION}" "约 2–5 分钟"
    brew_install_or_mirror "node@${NODE_MAJOR_VERSION}" || true
    brew link --overwrite "node@${NODE_MAJOR_VERSION}" 2>/dev/null || true
    ensure_brew_path
    long_step_end "Node.js ${NODE_MAJOR_VERSION}"
  else
    fail_with_help "Node.js 未安装，且当前系统不支持自动安装" \
      "• 本脚本在 macOS 上可通过 Homebrew 自动安装 Node.js" \
      "1. 请手动安装 Node.js 18 或更高：https://nodejs.org
2. 安装后确保 node 与 npm 在 PATH 中
3. 再运行本脚本：bash scripts/auto_build_app.sh"
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
  long_step_begin "通过 rustup 安装 Rust" "约 5–15 分钟（首次下载较大）"
  curl $CURL_TIMEOUT --proto '=https' --tlsv1.2 -sSf "$RUST_INSTALL_URL" | sh -s -- -y 2>&1 || true
  [ -f "$HOME/.cargo/env" ] && source "$HOME/.cargo/env"
  if ! has_cmd rustc; then
    if [ "$RUST_INSTALL_URL" = "https://sh.rustup.rs" ]; then
      warn "官方源安装失败，切换到镜像源重试..."
      setup_rust_mirror
    fi
    curl $CURL_TIMEOUT --proto '=https' --tlsv1.2 -sSf "$RUST_INSTALL_URL" | sh -s -- -y
    [ -f "$HOME/.cargo/env" ] && source "$HOME/.cargo/env"
    if ! has_cmd rustc; then
      fail_with_help "Rust 安装失败" \
        "• 网络超时或无法连接 rustup 服务器（可尝试 VPN 或使用镜像）\n• 磁盘空间不足\n• 安装脚本中途被中断" \
        "1. 手动安装：在终端执行 curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
2. 国内用户可设置镜像后重试：export RUSTUP_DIST_SERVER=https://mirrors.ustc.edu.cn/rust-static
3. 安装完成后执行 source \"\$HOME/.cargo/env\"，再运行本脚本：bash scripts/auto_build_app.sh"
    fi
  fi
  long_step_end "Rust"
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
  for pkg in aiofiles fastapi pydantic uvicorn httpx sqlalchemy tiktoken sqlite_vec openai; do
    if ! $PYTHON_CMD -c "import $pkg" 2>/dev/null; then
      NEEDS_INSTALL=true
      break
    fi
  done

  # 构建时使用 requirements-dev.txt（包含运行时依赖 + PyInstaller 等构建工具）
  DEV_REQ="$PROJECT_ROOT/requirements-dev.txt"
  [ ! -f "$DEV_REQ" ] && DEV_REQ="$PROJECT_ROOT/requirements.txt"

  if [ "$NEEDS_INSTALL" = true ]; then
    info "安装 Python 依赖 ($(basename "$DEV_REQ"))..."
    if ! pip_install_or_mirror "$PYTHON_CMD -m pip" -r "$DEV_REQ"; then
      fail "Python 依赖安装失败！请检查 Python 版本（当前: $($PYTHON_CMD --version 2>&1)，需要 3.12 ~ 3.13）"
    fi
    INSTALLED_SOMETHING=true
    ok "Python 依赖安装完成"
  else
    # 即使运行时依赖已安装，仍需确保 PyInstaller 存在
    if [ "$SKIP_BACKEND" = false ] && ! $PYTHON_CMD -c "import PyInstaller" 2>/dev/null; then
      info "安装构建工具 (PyInstaller)..."
      pip_install_or_mirror "$PYTHON_CMD -m pip" -r "$DEV_REQ"
      INSTALLED_SOMETHING=true
      ok "构建工具安装完成"
    else
      ok "Python 依赖已是最新"
    fi
  fi
else
  warn "requirements.txt 不存在，跳过 Python 依赖安装"
fi

# ---------- 0d-2. Pandoc（Markdown → Word 转换）----------

if has_cmd pandoc; then
  ok "Pandoc 已安装 ($(pandoc --version | head -1))"
else
  info "安装 Pandoc（Markdown → Word 文档转换）..."
  brew_install_or_mirror pandoc
  if has_cmd pandoc; then
    ok "Pandoc 安装完成"
    INSTALLED_SOMETHING=true
  else
    warn "Pandoc 安装失败（可选依赖，Word 文档生成将降级到 python-docx 方案）"
  fi
fi

# ---------- 0e. 前端 npm 依赖 ----------

info "检查前端依赖..."

cd "$FRONTEND_DIR"
if [ ! -d "node_modules" ]; then
  info "安装前端 npm 依赖..."
  npm_install_or_mirror
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
    if [ -n "${HOMEBREW_BOTTLE_DOMAIN:-}" ]; then
      arch -x86_64 /bin/bash -c "$(curl $CURL_TIMEOUT -fsSL "$HOMEBREW_MIRROR_INSTALL_URL")" 2>&1 || true
    elif ! arch -x86_64 /bin/bash -c "$(curl $CURL_TIMEOUT -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" 2>&1; then
      warn "官方源安装失败，尝试使用国内镜像源..."
      setup_brew_mirror
      arch -x86_64 /bin/bash -c "$(curl $CURL_TIMEOUT -fsSL "$HOMEBREW_MIRROR_INSTALL_URL")" 2>&1 || true
    fi
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
    brew_install_or_mirror "python@${PYTHON_VERSION}" "arch -x86_64" || true
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
  for pkg in aiofiles fastapi pydantic uvicorn httpx sqlalchemy tiktoken sqlite_vec; do
    if ! arch -x86_64 "$X86_PYTHON_CMD" -c "import $pkg" 2>/dev/null; then
      NEEDS_INSTALL=true
      break
    fi
  done

  X86_DEV_REQ="$PROJECT_ROOT/requirements-dev.txt"
  [ ! -f "$X86_DEV_REQ" ] && X86_DEV_REQ="$PROJECT_ROOT/requirements.txt"

  if [ "$NEEDS_INSTALL" = true ]; then
    info "安装 x86_64 Python 依赖..."
    if ! pip_install_or_mirror "$VENV_X86_DIR/bin/pip" --arch-prefix "arch -x86_64" -r "$X86_DEV_REQ"; then
      fail "x86_64 Python 依赖安装失败"
    fi
    ok "x86_64 Python 依赖安装完成"
  else
    if [ "$SKIP_BACKEND" = false ] && ! arch -x86_64 "$X86_PYTHON_CMD" -c "import PyInstaller" 2>/dev/null; then
      info "安装 x86_64 构建工具..."
      pip_install_or_mirror "$VENV_X86_DIR/bin/pip" --arch-prefix "arch -x86_64" -r "$X86_DEV_REQ"
      ok "x86_64 构建工具安装完成"
    else
      ok "x86_64 Python 依赖已是最新"
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
  if [ "$USING_MIRROR" = true ]; then
    info "环境准备完成（已安装缺失的依赖，部分通过国内镜像源）"
  else
    info "环境准备完成（已安装缺失的依赖）"
  fi
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
  # 清理 __pycache__，防止 PyInstaller 复用旧 .pyc
  find "$PROJECT_ROOT" -name "__pycache__" -not -path "*/.venv/*" -not -path "*/node_modules/*" -exec rm -rf {} + 2>/dev/null || true
  info "清理完成"
fi

# 注意：不清理 instances/ 目录。
# 打包范围由 xiaodazi-backend.spec 的 datas 列表精确控制，
# 本地实例（SAP_xiaodazi 等）不会被误打包，也不应被构建脚本删除。

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
  info "生成本地构建签名密钥..."
  DEV_KEY_PWD="dev-build"
  mkdir -p "$PROJECT_ROOT/keys"
  rm -f "$SIGN_KEY_FILE" "$SIGN_KEY_PUB_FILE" "$SIGN_KEY_PWD_FILE"
  cd "$FRONTEND_DIR"
  npx @tauri-apps/cli signer generate -w "$SIGN_KEY_FILE" -p "$DEV_KEY_PWD" --ci --force 2>&1 || true

  if [ -f "$SIGN_KEY_FILE" ] && [ -f "$SIGN_KEY_PUB_FILE" ]; then
    printf '%s' "$DEV_KEY_PWD" > "$SIGN_KEY_PWD_FILE"
    export TAURI_SIGNING_PRIVATE_KEY="$(cat "$SIGN_KEY_FILE")"
    export TAURI_SIGNING_PRIVATE_KEY_PASSWORD="$DEV_KEY_PWD"

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
    npm_install_or_mirror
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
