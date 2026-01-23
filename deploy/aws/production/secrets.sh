#!/usr/bin/env bash
# ============================================================
# Zenflux Agent - Production Secrets 统一管理脚本
# ============================================================
# 功能：
#   - init: 初始化所有 secrets
#   - create: 创建单个 secret
#   - delete: 删除 secrets
#   - list: 列出所有 secrets
#   - verify: 验证 secrets
#   - update: 更新单个 secret
#   - show: 显示单个 secret 的值
#
# 用法：
#   ./deploy/aws/production/secrets.sh init [--interactive|--from-env <文件>]
#   ./deploy/aws/production/secrets.sh create <name> <value>
#   ./deploy/aws/production/secrets.sh update <name> <value>
#   ./deploy/aws/production/secrets.sh delete [--force]
#   ./deploy/aws/production/secrets.sh list
#   ./deploy/aws/production/secrets.sh verify
#   ./deploy/aws/production/secrets.sh show <name>
#   ./deploy/aws/production/secrets.sh --help
# ============================================================

set -euo pipefail

# ============================================================
# 项目根目录检测
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
cd "${PROJECT_ROOT}"

# ============================================================
# 配置变量
# ============================================================

APP_NAME="${APP_NAME:-zen0-backend}"
ENV_NAME="production"  # 固定为 production
REGION="${AWS_REGION:-ap-southeast-1}"
SECRET_PREFIX="/copilot/${APP_NAME}/${ENV_NAME}/secrets"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

# ============================================================
# 辅助函数
# ============================================================

log_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
log_success() { echo -e "${GREEN}✅ $1${NC}"; }
log_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error() { echo -e "${RED}❌ $1${NC}"; }
log_step() {
    echo ""
    echo -e "${MAGENTA}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${MAGENTA}📋 $1${NC}"
    echo -e "${MAGENTA}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# Production 环境操作确认
confirm_production_action() {
    local action=$1
    echo ""
    echo -e "${RED}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║                    ⚠️  PRODUCTION 环境警告                  ║${NC}"
    echo -e "${RED}╠════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${RED}║  您即将在 PRODUCTION 环境执行: ${action}${NC}"
    echo -e "${RED}║  此操作可能影响线上服务！                                   ║${NC}"
    echo -e "${RED}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    read -p "请输入 'PRODUCTION' 确认继续: " confirm
    if [ "$confirm" != "PRODUCTION" ]; then
        log_info "操作已取消"
        exit 0
    fi
}

# ============================================================
# 显示帮助
# ============================================================

show_help() {
    cat << 'EOF'
用法: ./deploy/aws/production/secrets.sh <命令> [选项]

命令:
  init                初始化所有 secrets（使用占位符值）
  init --interactive  交互式初始化（逐个输入实际值）
  init --from-env     从环境变量文件初始化
  create <名称> <值>  创建单个 secret
  update <名称> <值>  更新单个 secret
  delete              删除所有 secrets
  list                列出所有 secrets
  verify              验证 secrets
  show <名称>         显示单个 secret 的值
  export-template     导出 secrets 模板文件

init 选项:
  --interactive       交互式输入每个 secret 的值
  --from-env <文件>   从 .env 文件读取值

delete 选项:
  --force             跳过确认，强制删除

示例:
  # 使用占位符初始化（后续手动更新）
  ./deploy/aws/production/secrets.sh init

  # 交互式初始化（推荐首次部署）
  ./deploy/aws/production/secrets.sh init --interactive

  # 从 .env 文件初始化
  ./deploy/aws/production/secrets.sh init --from-env ./secrets.production.env

  # 导出模板文件
  ./deploy/aws/production/secrets.sh export-template > secrets.production.env
  # 编辑 secrets.production.env 后导入
  ./deploy/aws/production/secrets.sh init --from-env secrets.production.env

  # 创建单个 secret
  ./deploy/aws/production/secrets.sh create ANTHROPIC_API_KEY "sk-ant-xxxxx"

  # 更新 secret
  ./deploy/aws/production/secrets.sh update ANTHROPIC_API_KEY "sk-ant-new-key"

  # 列出所有 secrets
  ./deploy/aws/production/secrets.sh list

  # 验证 secrets
  ./deploy/aws/production/secrets.sh verify

  # 删除所有 secrets（交互式）
  ./deploy/aws/production/secrets.sh delete

  # 显示 secret 值
  ./deploy/aws/production/secrets.sh show ANTHROPIC_API_KEY

环境变量:
  APP_NAME      应用名称（默认: zen0-backend）
  AWS_REGION    AWS 区域（默认: ap-southeast-1）

EOF
    exit 0
}

# ============================================================
# 前置检查
# ============================================================

check_prerequisites() {
    if ! command -v aws &> /dev/null; then
        log_error "未找到 AWS CLI"
        exit 1
    fi
    
    # 验证 AWS 凭证
    if ! aws sts get-caller-identity --region "$REGION" &> /dev/null; then
        log_error "AWS 凭证验证失败"
        exit 1
    fi
}

# ============================================================
# Secrets 定义（集中管理）
# ============================================================

# 定义所有 secrets 及其默认值
# 格式: "NAME|DEFAULT_VALUE|DESCRIPTION|REQUIRED"
declare -a SECRETS_DEFINITION=(
    # 数据库
    "DATABASE_URL||PostgreSQL 连接字符串|required"
    
    # MemoryDB for Redis
    "MEMORYDB_HOST||MemoryDB 主机地址|required"
    "MEMORYDB_PORT|6379|MemoryDB 端口|required"
    "MEMORYDB_USER||MemoryDB 用户名|optional"
    "MEMORYDB_PASSWORD||MemoryDB 密码|optional"
    
    # AI 服务 - Anthropic
    "ANTHROPIC_API_KEY||Anthropic API 密钥|required"
    
    # AI 服务 - E2B
    "E2B_API_KEY||E2B 代码执行 API 密钥|optional"
    
    # AI 服务 - Ragie
    "RAGIE_API_KEY||Ragie RAG API 密钥|optional"
    
    # AI 服务 - Tavily
    "TAVILY_API_KEY||Tavily 搜索 API 密钥|optional"
    
    # AI 服务 - Exa
    "EXA_API_KEY||Exa 搜索 API 密钥|optional"
    
    # AI 服务 - SlideSpeak
    "SLIDESPEAK_API_KEY||SlideSpeak PPT 生成 API 密钥|optional"
    
    # AWS 凭证
    "AWS_ACCESS_KEY_ID||AWS Access Key ID（S3 访问）|optional"
    "AWS_SECRET_ACCESS_KEY||AWS Secret Access Key（S3 访问）|optional"
)

# 生成随机值
generate_random_value() {
    local type=$1
    case $type in
        AUTO_GENERATE)
            openssl rand -hex 32
            ;;
        AUTO_GENERATE_32)
            openssl rand -hex 16  # 16 bytes hex = 32 chars
            ;;
        *)
            echo "$type"
            ;;
    esac
}

# 获取 secret 的实际值
get_secret_value() {
    local name=$1
    local default=$2
    local env_file=$3
    
    # 如果提供了环境文件，从文件读取
    if [ -n "$env_file" ] && [ -f "$env_file" ]; then
        local file_value=$(grep "^${name}=" "$env_file" 2>/dev/null | cut -d'=' -f2- | sed 's/^"//' | sed 's/"$//')
        if [ -n "$file_value" ]; then
            echo "$file_value"
            return
        fi
    fi
    
    # 处理特殊默认值
    case $default in
        AUTO_GENERATE|AUTO_GENERATE_32)
            generate_random_value "$default"
            ;;
        *)
            echo "$default"
            ;;
    esac
}

# ============================================================
# 获取 Secrets 列表
# ============================================================

list_secrets() {
    local ssm_params=$(aws ssm describe-parameters \
        --region "${REGION}" \
        --parameter-filters "Key=Name,Option=BeginsWith,Values=${SECRET_PREFIX}" \
        --query "Parameters[].Name" \
        --output text 2>/dev/null | tr '\t' '\n' || echo "")
    
    if [ -z "${ssm_params}" ]; then
        return 1
    fi
    
    echo "${ssm_params}"
    return 0
}

show_secrets_list() {
    log_step "Production Secrets 列表"
    
    local secrets=$(list_secrets)
    if [ $? -ne 0 ]; then
        log_info "未找到任何 secrets"
        return 1
    fi
    
    local count=0
    echo ""
    echo "应用: ${APP_NAME}"
    echo "环境: ${ENV_NAME}"
    echo "区域: ${REGION}"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    while IFS= read -r secret_name; do
        if [ -n "${secret_name}" ]; then
            ((count++))
            local short_name=$(echo "${secret_name}" | sed "s|${SECRET_PREFIX}/||")
            echo "${count}. ${short_name}"
        fi
    done <<< "${secrets}"
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "总计: ${count} 个 secrets"
    echo ""
}

# ============================================================
# 创建 Secret
# ============================================================

create_secret() {
    local name=$1
    local value=$2
    local description=${3:-"Managed by zenflux-agent deployment script"}
    
    local param_name="${SECRET_PREFIX}/${name}"
    
    # 检查参数是否已存在
    local exists=false
    if aws ssm get-parameter --name "$param_name" --region "$REGION" &> /dev/null; then
        exists=true
    fi
    
    if [ "$exists" = "true" ]; then
        # 参数已存在，使用 overwrite 更新
        if aws ssm put-parameter \
            --region "$REGION" \
            --name "$param_name" \
            --type "SecureString" \
            --value "$value" \
            --overwrite \
            --description "$description" \
            --no-cli-pager &> /dev/null; then
            log_success "Secret ${name} 已更新"
            return 0
        else
            log_error "Secret ${name} 更新失败"
            return 1
        fi
    else
        # 参数不存在，创建新参数
        if aws ssm put-parameter \
            --region "$REGION" \
            --name "$param_name" \
            --type "SecureString" \
            --value "$value" \
            --description "$description" \
            --tags "Key=copilot-application,Value=${APP_NAME}" "Key=copilot-environment,Value=${ENV_NAME}" \
            --no-cli-pager &> /dev/null; then
            log_success "Secret ${name} 创建成功"
            return 0
        else
            log_error "Secret ${name} 创建失败"
            return 1
        fi
    fi
}

# ============================================================
# 导出模板文件
# ============================================================

export_template() {
    echo "# ============================================================"
    echo "# Zenflux Agent - Production Secrets 配置模板"
    echo "# ============================================================"
    echo "# 使用方法："
    echo "#   1. 复制此文件: cp secrets.production.env.template secrets.production.env"
    echo "#   2. 编辑 secrets.production.env，填入实际值"
    echo "#   3. 导入: ./deploy/aws/production/secrets.sh init --from-env secrets.production.env"
    echo "#"
    echo "# 注意："
    echo "#   - 以 # 开头的行为注释"
    echo "#   - 空值表示使用默认值或需要手动填写"
    echo "# ============================================================"
    echo ""
    
    local current_section=""
    
    for secret_def in "${SECRETS_DEFINITION[@]}"; do
        IFS='|' read -r name default desc required <<< "$secret_def"
        
        # 根据名称判断分类
        local section=""
        case $name in
            DATABASE_*) section="数据库" ;;
            MEMORYDB_*) section="MemoryDB Redis" ;;
            ANTHROPIC_*) section="AI 服务 - Anthropic" ;;
            E2B_*) section="AI 服务 - E2B" ;;
            RAGIE_*) section="AI 服务 - Ragie" ;;
            TAVILY_*) section="AI 服务 - Tavily" ;;
            EXA_*) section="AI 服务 - Exa" ;;
            SLIDESPEAK_*) section="AI 服务 - SlideSpeak" ;;
            AWS_*) section="AWS 凭证" ;;
        esac
        
        if [ "$section" != "$current_section" ]; then
            echo ""
            echo "# ============ ${section} ============"
            current_section="$section"
        fi
        
        # 输出注释和变量
        echo "# ${desc} [${required}]"
        if [ -n "$default" ]; then
            echo "# 默认: ${default}"
        fi
        echo "${name}="
    done
}

# ============================================================
# 交互式初始化
# ============================================================

init_interactive() {
    log_step "交互式初始化 Production Secrets"
    
    echo ""
    log_info "将逐个询问每个 secret 的值"
    log_info "按 Enter 使用默认值，输入 'skip' 跳过可选项"
    echo ""
    
    confirm_production_action "init secrets (interactive)"
    
    echo ""
    local success_count=0
    local fail_count=0
    local skip_count=0
    local current_section=""
    
    for secret_def in "${SECRETS_DEFINITION[@]}"; do
        IFS='|' read -r name default desc required <<< "$secret_def"
        
        # 根据名称判断分类并显示分隔
        local section=""
        case $name in
            DATABASE_*) section="数据库" ;;
            MEMORYDB_*) section="MemoryDB Redis" ;;
            ANTHROPIC_*) section="AI 服务 - Anthropic" ;;
            E2B_*) section="AI 服务 - E2B" ;;
            RAGIE_*) section="AI 服务 - Ragie" ;;
            TAVILY_*) section="AI 服务 - Tavily" ;;
            EXA_*) section="AI 服务 - Exa" ;;
            SLIDESPEAK_*) section="AI 服务 - SlideSpeak" ;;
            AWS_*) section="AWS 凭证" ;;
        esac
        
        if [ "$section" != "$current_section" ]; then
            echo ""
            echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            echo -e "${CYAN}📁 ${section}${NC}"
            echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            current_section="$section"
        fi
        
        # 显示提示
        echo ""
        echo -e "${BLUE}${name}${NC}"
        echo -e "  描述: ${desc}"
        
        local default_display=""
        local input_hint=""
        if [ -n "$default" ]; then
            default_display="[默认: ${default}，按 Enter 使用默认值]"
            input_hint="(直接按 Enter 使用默认值)"
        else
            default_display="[无默认值]"
            input_hint=""
        fi
        
        if [ "$required" = "required" ]; then
            echo -e "  ${default_display} ${RED}(必需)${NC}"
        else
            echo -e "  ${default_display} ${YELLOW}(可选，输入 'skip' 跳过)${NC}"
        fi
        
        # 读取用户输入
        if [ -n "$input_hint" ]; then
            read -p "  输入值 ${input_hint}: " user_input
        else
            read -p "  输入值: " user_input
        fi
        
        # 处理输入
        if [ "$user_input" = "skip" ] && [ "$required" != "required" ]; then
            log_info "跳过 ${name}"
            ((skip_count++))
            continue
        fi
        
        local final_value
        if [ -z "$user_input" ]; then
            # 使用默认值
            final_value=$(get_secret_value "$name" "$default" "")
        else
            final_value="$user_input"
        fi
        
        # 跳过空值的可选项
        if [ -z "$final_value" ] && [ "$required" != "required" ]; then
            log_info "跳过 ${name}（空值）"
            ((skip_count++))
            continue
        fi
        
        # 创建 secret
        if create_secret "$name" "$final_value"; then
            ((success_count++))
        else
            ((fail_count++))
        fi
    done
    
    echo ""
    log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_success "成功创建: ${success_count} 个"
    [ ${skip_count} -gt 0 ] && log_info "跳过: ${skip_count} 个"
    [ ${fail_count} -gt 0 ] && log_error "创建失败: ${fail_count} 个"
    log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    echo ""
    log_warning "下一步："
    echo "  1. 验证 secrets:"
    echo "     ./deploy/aws/production/secrets.sh verify"
    echo ""
    echo "  2. 部署服务:"
    echo "     ./deploy/aws/production/production.sh deploy"
    echo ""
}

# ============================================================
# 从环境文件初始化
# ============================================================

init_from_env_file() {
    local env_file=$1
    
    log_step "从环境文件初始化 Production Secrets"
    
    if [ ! -f "$env_file" ]; then
        log_error "文件不存在: $env_file"
        exit 1
    fi
    
    log_info "读取配置文件: $env_file"
    echo ""
    
    confirm_production_action "init secrets from file"
    
    echo ""
    local success_count=0
    local fail_count=0
    local skip_count=0
    
    for secret_def in "${SECRETS_DEFINITION[@]}"; do
        IFS='|' read -r name default desc required <<< "$secret_def"
        
        # 从文件获取值
        local file_value=$(grep "^${name}=" "$env_file" 2>/dev/null | cut -d'=' -f2- | sed 's/^"//' | sed 's/"$//')
        
        local final_value
        if [ -n "$file_value" ]; then
            final_value="$file_value"
        else
            # 使用默认值
            final_value=$(get_secret_value "$name" "$default" "")
        fi
        
        # 跳过空值的可选项
        if [ -z "$final_value" ] && [ "$required" != "required" ]; then
            log_info "跳过 ${name}（空值）"
            ((skip_count++))
            continue
        fi
        
        # 创建 secret
        if create_secret "$name" "$final_value"; then
            ((success_count++))
        else
            ((fail_count++))
        fi
    done
    
    echo ""
    log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_success "成功创建: ${success_count} 个"
    [ ${skip_count} -gt 0 ] && log_info "跳过: ${skip_count} 个"
    [ ${fail_count} -gt 0 ] && log_error "创建失败: ${fail_count} 个"
    log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    echo ""
    log_warning "下一步："
    echo "  1. 验证 secrets:"
    echo "     ./deploy/aws/production/secrets.sh verify"
    echo ""
    echo "  2. 部署服务:"
    echo "     ./deploy/aws/production/production.sh deploy"
    echo ""
}

# ============================================================
# 初始化所有 Secrets（使用占位符）
# ============================================================

init_all_secrets() {
    log_step "初始化 Production Secrets"
    
    log_warning "将使用占位符/默认值创建 secrets"
    log_info "推荐使用: ./deploy/aws/production/secrets.sh init --interactive"
    echo ""
    
    confirm_production_action "init secrets"
    
    echo ""
    local success_count=0
    local fail_count=0
    local skip_count=0
    
    for secret_def in "${SECRETS_DEFINITION[@]}"; do
        IFS='|' read -r name default desc required <<< "$secret_def"
        
        # 获取默认值
        local final_value=$(get_secret_value "$name" "$default" "")
        
        # 跳过空值的可选项
        if [ -z "$final_value" ] && [ "$required" != "required" ]; then
            log_info "跳过 ${name}（空值）"
            ((skip_count++))
            continue
        fi
        
        # 如果是必需项但没有默认值，使用占位符
        if [ -z "$final_value" ] && [ "$required" = "required" ]; then
            final_value="CHANGE_ME_${name}"
        fi
        
        # 创建 secret
        if create_secret "$name" "$final_value"; then
            ((success_count++))
        else
            ((fail_count++))
        fi
    done
    
    echo ""
    log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_success "成功创建: ${success_count} 个"
    [ ${skip_count} -gt 0 ] && log_info "跳过: ${skip_count} 个"
    [ ${fail_count} -gt 0 ] && log_error "创建失败: ${fail_count} 个"
    log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    echo ""
    log_warning "下一步："
    echo "  1. 更新必需的配置值:"
    echo "     ./deploy/aws/production/secrets.sh update ANTHROPIC_API_KEY 'sk-ant-xxxxx'"
    echo "     ./deploy/aws/production/secrets.sh update DATABASE_URL 'postgresql://...'"
    echo ""
    echo "  2. 或使用交互式模式重新初始化:"
    echo "     ./deploy/aws/production/secrets.sh init --interactive"
    echo ""
    echo "  3. 验证 secrets:"
    echo "     ./deploy/aws/production/secrets.sh verify"
    echo ""
}

# ============================================================
# 删除 Secrets
# ============================================================

delete_all_secrets() {
    local force=${1:-false}
    
    log_step "删除 Production Secrets"
    
    local secrets=$(list_secrets)
    if [ $? -ne 0 ]; then
        log_info "未找到任何 secrets"
        return 0
    fi
    
    # 显示列表
    local count=0
    echo ""
    echo "将要删除以下 secrets:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    while IFS= read -r secret_name; do
        if [ -n "${secret_name}" ]; then
            ((count++))
            echo "${count}. ${secret_name}"
        fi
    done <<< "${secrets}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "总计: ${count} 个"
    echo ""
    
    # 确认
    if [ "${force}" != "true" ]; then
        confirm_production_action "delete secrets"
    fi
    
    echo ""
    log_info "开始删除..."
    echo ""
    
    local success_count=0
    local fail_count=0
    
    while IFS= read -r secret_name; do
        if [ -z "${secret_name}" ]; then
            continue
        fi
        
        log_info "删除: ${secret_name}"
        
        if aws ssm delete-parameter \
            --name "${secret_name}" \
            --region "${REGION}" > /dev/null 2>&1; then
            log_success "已删除"
            ((success_count++))
        else
            log_error "删除失败"
            ((fail_count++))
        fi
        
    done <<< "${secrets}"
    
    echo ""
    log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_success "成功删除: ${success_count} 个"
    [ ${fail_count} -gt 0 ] && log_error "删除失败: ${fail_count} 个"
    log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
}

# ============================================================
# 验证 Secrets
# ============================================================

verify_secrets() {
    log_step "验证 Production Secrets"
    
    echo ""
    echo "应用: ${APP_NAME}"
    echo "环境: ${ENV_NAME}"
    echo ""
    
    local required_missing=0
    local optional_missing=0
    local failed=0
    
    # 验证所有 secrets
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Secrets 验证:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    for secret_def in "${SECRETS_DEFINITION[@]}"; do
        IFS='|' read -r name default desc required <<< "$secret_def"
        
        local param_name="${SECRET_PREFIX}/${name}"
        
        if aws ssm get-parameter --name "$param_name" --region "$REGION" &>/dev/null; then
            # 检查值是否为占位符
            local value=$(aws ssm get-parameter \
                --name "$param_name" \
                --region "$REGION" \
                --with-decryption \
                --query 'Parameter.Value' \
                --output text 2>/dev/null)
            
            if [[ "$value" == *"CHANGE_ME"* ]]; then
                log_warning "${name} - 存在但需要更新（占位符值）"
                ((failed++))
            else
                log_success "${name} - 已配置"
            fi
        else
            if [ "$required" = "required" ]; then
                log_error "${name} - 缺失（必需）"
                ((required_missing++))
            else
                log_info "${name} - 未配置（可选）"
                ((optional_missing++))
            fi
        fi
    done
    
    echo ""
    log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_info "验证结果:"
    log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    if [[ $required_missing -eq 0 ]] && [[ $failed -eq 0 ]]; then
        log_success "所有必需的 secrets 验证通过！"
        [ ${optional_missing} -gt 0 ] && log_info "可选 secrets 未配置: ${optional_missing} 个"
        return 0
    else
        [ ${required_missing} -gt 0 ] && log_error "必需 secrets 缺失: ${required_missing} 个"
        [ ${failed} -gt 0 ] && log_warning "需要更新: ${failed} 个"
        [ ${optional_missing} -gt 0 ] && log_info "可选 secrets 未配置: ${optional_missing} 个"
        log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        return 1
    fi
}

# ============================================================
# 显示单个 Secret
# ============================================================

show_secret() {
    local name=$1
    local param_name="${SECRET_PREFIX}/${name}"
    
    log_info "获取 secret: ${name}"
    
    local value=$(aws ssm get-parameter \
        --name "$param_name" \
        --region "$REGION" \
        --with-decryption \
        --query 'Parameter.Value' \
        --output text 2>/dev/null)
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "Secret: ${name}"
        echo "Value: ${value}"
        echo ""
    else
        log_error "Secret 不存在: ${name}"
        return 1
    fi
}

# ============================================================
# 更新 Secret
# ============================================================

update_secret() {
    local name=$1
    local value=$2
    
    create_secret "$name" "$value"
}

# ============================================================
# 主函数
# ============================================================

main() {
    if [ $# -eq 0 ]; then
        show_help
    fi
    
    local command=$1
    shift
    
    # 解析选项
    local force=false
    local interactive=false
    local env_file=""
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --force) force=true; shift ;;
            --interactive) interactive=true; shift ;;
            --from-env)
                if [ -n "$2" ]; then
                    env_file="$2"
                    shift 2
                else
                    log_error "--from-env 需要指定文件路径"
                    exit 1
                fi
                ;;
            --help|-h) show_help ;;
            *) break ;;
        esac
    done
    
    # 大部分命令需要检查前置条件
    case $command in
        init|create|update|delete|verify|show|list)
            check_prerequisites
            ;;
    esac
    
    # 执行命令
    case $command in
        init)
            if [ "$interactive" = "true" ]; then
                init_interactive
            elif [ -n "$env_file" ]; then
                init_from_env_file "$env_file"
            else
                init_all_secrets
            fi
            ;;
            
        create)
            if [ $# -lt 2 ]; then
                log_error "用法: $0 create <名称> <值>"
                exit 1
            fi
            create_secret "$1" "$2"
            ;;
            
        update)
            if [ $# -lt 2 ]; then
                log_error "用法: $0 update <名称> <值>"
                exit 1
            fi
            update_secret "$1" "$2"
            ;;
            
        delete)
            delete_all_secrets "$force"
            ;;
            
        list)
            show_secrets_list
            ;;
            
        verify)
            verify_secrets
            ;;
            
        show)
            if [ $# -lt 1 ]; then
                log_error "用法: $0 show <名称>"
                exit 1
            fi
            show_secret "$1"
            ;;
            
        export-template)
            export_template
            ;;
            
        --help|-h|help)
            show_help
            ;;
            
        *)
            log_error "未知命令: $command"
            show_help
            ;;
    esac
}

main "$@"
