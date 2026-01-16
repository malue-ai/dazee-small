#!/usr/bin/env bash
# ============================================================
# Zenflux Agent - Staging 环境统一管理脚本
# ============================================================
# 功能：
#   - deploy: 完整部署（环境 + 服务）
#   - start: 启动已停止的环境（恢复 ECS 任务）
#   - stop: 停止环境（缩容或完全删除）
#   - status: 查看环境状态
#   - logs: 查看服务日志
#   - cert: 申请/查看 SSL 证书
#
# 用法：
#   ./deploy/aws/staging/staging.sh deploy [--env-only|--svc-only|--force]
#   ./deploy/aws/staging/staging.sh start
#   ./deploy/aws/staging/staging.sh stop [--keep-service|--force]
#   ./deploy/aws/staging/staging.sh status
#   ./deploy/aws/staging/staging.sh logs [--follow]
#   ./deploy/aws/staging/staging.sh cert [request|status]
#   ./deploy/aws/staging/staging.sh --help
# ============================================================

set -euo pipefail

# ============================================================
# 配置变量
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
cd "$PROJECT_ROOT"

# AWS 配置
REGION="${AWS_REGION:-ap-southeast-1}"
APP_NAME="zen0-backend"          # 复用现有应用
ENV_NAME="staging"               # 复用现有环境
SERVICE_NAME="agent"             # 新服务名（区别于 backend）

# AWS Copilot CLI 路径（自动检测，支持 Mac/Linux/Windows）
# 优先使用 PATH 中的 copilot，否则尝试常见安装路径
detect_copilot() {
    # 1. 优先使用 PATH 中的 copilot
    if command -v copilot &> /dev/null; then
        command -v copilot
        return 0
    fi
    
    # 2. Mac: Homebrew (Apple Silicon)
    if [ -x "/opt/homebrew/bin/copilot" ]; then
        echo "/opt/homebrew/bin/copilot"
        return 0
    fi
    
    # 3. Mac: Homebrew (Intel) / Linux
    if [ -x "/usr/local/bin/copilot" ]; then
        echo "/usr/local/bin/copilot"
        return 0
    fi
    
    # 4. Windows: 常见安装路径 (Git Bash / WSL)
    if [ -x "$HOME/bin/copilot" ]; then
        echo "$HOME/bin/copilot"
        return 0
    fi
    
    # 5. Windows: AppData 路径
    if [ -n "${LOCALAPPDATA:-}" ] && [ -x "${LOCALAPPDATA}/Programs/copilot/copilot.exe" ]; then
        echo "${LOCALAPPDATA}/Programs/copilot/copilot.exe"
        return 0
    fi
    
    # 未找到
    echo ""
    return 1
}

COPILOT="$(detect_copilot)"

# 域名配置（可选，留空则使用 ALB 默认域名）
# 如需 HTTPS，请填写域名并申请证书
DOMAIN_NAME="${CUSTOM_DOMAIN:-}"  # 留空 = HTTP only, 填写 = HTTPS

# VPC 配置（复用现有）
VPC_ID="vpc-0c7d3d0bd0b1dcdce"
PUBLIC_SUBNET_1="subnet-0f76e3152f949cd27"
PUBLIC_SUBNET_2="subnet-0b9e593b3287cbe9e"
PRIVATE_SUBNET_1="subnet-065f4089cc1d85311"
PRIVATE_SUBNET_2="subnet-015b9392db9a65d2a"

# ALB 配置（复用现有）
EXISTING_ALB_ARN="arn:aws:elasticloadbalancing:ap-southeast-1:308470327605:loadbalancer/app/zen0-b-Publi-NMnJaDU9XzTR/ddb12f2de16cdb64"

# Redis 配置（复用现有）
REDIS_HOST="zen0-backend-staging-redis.w9tdej.0001.apse1.cache.amazonaws.com"
REDIS_PORT="6379"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 日志配置
LOG_DIR="logs"
LOG_FILE="$LOG_DIR/staging-$(date +%Y%m%d-%H%M%S).log"
STATE_FILE=".staging-state"

# 健康检查配置
HEALTH_CHECK_TIMEOUT=120
HEALTH_CHECK_INTERVAL=10

# ============================================================
# 辅助函数
# ============================================================

log_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
log_success() { echo -e "${GREEN}✅ $1${NC}"; }
log_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error() { echo -e "${RED}❌ $1${NC}"; }
log_step() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}📋 $1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# 记录日志到文件
log_to_file() {
    mkdir -p "$LOG_DIR"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# 保存环境状态
save_state() {
    echo "$1|$(date '+%Y-%m-%d %H:%M:%S')" > "$STATE_FILE"
}

# 读取环境状态
read_state() {
    if [ -f "$STATE_FILE" ]; then
        cat "$STATE_FILE"
    else
        echo "unknown|never"
    fi
}

# ============================================================
# 显示帮助
# ============================================================

show_help() {
    cat << 'EOF'
用法: ./deploy/aws/staging/staging.sh <命令> [选项]

命令:
  deploy              部署环境和服务
  start               启动已停止的环境（恢复 ECS 任务）
  stop                停止环境
  status              查看环境状态
  logs                查看服务日志
  cert                SSL 证书管理
  clean               清理失败的部署资源

deploy 选项:
  --env-only          仅创建环境，不部署服务
  --svc-only          仅部署服务（假设环境已存在）
  --force             强制清理并重新创建
  --skip-checks       跳过前置检查
  --skip-health       跳过健康检查

stop 选项:
  --keep-service      仅缩容到 0，保留服务配置
  --force             跳过确认，强制停止

logs 选项:
  --follow            实时跟踪日志
  --since <时间>      显示指定时间以来的日志（如: 10m, 1h）

cert 选项:
  request             申请 SSL 证书
  status              查看证书状态

示例:
  # 完整部署
  ./deploy/aws/staging/staging.sh deploy

  # 仅部署服务（环境已存在）
  ./deploy/aws/staging/staging.sh deploy --svc-only

  # 启动环境
  ./deploy/aws/staging/staging.sh start

  # 停止环境（保留配置，可快速恢复）
  ./deploy/aws/staging/staging.sh stop --keep-service

  # 查看状态
  ./deploy/aws/staging/staging.sh status

  # 查看实时日志
  ./deploy/aws/staging/staging.sh logs --follow

  # 申请 SSL 证书
  ./deploy/aws/staging/staging.sh cert request

EOF
    exit 0
}

# ============================================================
# 前置检查
# ============================================================

check_dependencies() {
    log_step "检查依赖工具"
    
    local missing_deps=()
    
    for cmd in aws docker jq; do
        if ! command -v $cmd &> /dev/null; then
            missing_deps+=("$cmd")
        fi
    done
    
    if [ ${#missing_deps[@]} -gt 0 ]; then
        log_error "缺少必需工具: ${missing_deps[*]}"
        echo ""
        echo "安装说明:"
        echo "  brew install awscli jq docker"
        exit 1
    fi
    
    # 检查 AWS Copilot CLI
    if [ -z "$COPILOT" ] || [ ! -x "$COPILOT" ]; then
        log_error "AWS Copilot CLI 未安装"
        echo ""
        echo "安装说明:"
        echo ""
        # 检测操作系统
        case "$(uname -s)" in
            Darwin)
                echo "  macOS (Homebrew):"
                echo "    brew install aws/tap/copilot-cli"
                echo ""
                echo "  macOS (手动安装 - Apple Silicon):"
                echo "    sudo curl -Lo /usr/local/bin/copilot https://github.com/aws/copilot-cli/releases/latest/download/copilot-darwin-arm64"
                echo "    sudo chmod +x /usr/local/bin/copilot"
                echo ""
                echo "  macOS (手动安装 - Intel):"
                echo "    sudo curl -Lo /usr/local/bin/copilot https://github.com/aws/copilot-cli/releases/latest/download/copilot-darwin"
                echo "    sudo chmod +x /usr/local/bin/copilot"
                ;;
            Linux)
                echo "  Linux:"
                echo "    sudo curl -Lo /usr/local/bin/copilot https://github.com/aws/copilot-cli/releases/latest/download/copilot-linux"
                echo "    sudo chmod +x /usr/local/bin/copilot"
                ;;
            MINGW*|MSYS*|CYGWIN*)
                echo "  Windows (PowerShell 管理员模式):"
                echo "    Invoke-WebRequest -OutFile copilot.exe https://github.com/aws/copilot-cli/releases/latest/download/copilot-windows.exe"
                echo "    Move-Item copilot.exe \$env:LOCALAPPDATA\\Programs\\copilot\\"
                echo "    # 添加到 PATH 环境变量"
                echo ""
                echo "  Windows (Scoop):"
                echo "    scoop install aws-copilot"
                echo ""
                echo "  Windows (Chocolatey):"
                echo "    choco install copilot"
                ;;
            *)
                echo "  请访问: https://aws.github.io/copilot-cli/docs/getting-started/install/"
                ;;
        esac
        exit 1
    fi
    log_success "AWS Copilot CLI: $($COPILOT --version)"
    
    # 检查 AWS 凭证
    if ! aws sts get-caller-identity --region "$REGION" &> /dev/null; then
        log_error "AWS 凭证验证失败"
        log_info "请先配置 AWS 凭证: aws configure"
        exit 1
    fi
    
    # 检查 Docker
    if ! docker info &> /dev/null; then
        log_error "Docker 守护进程未运行"
        exit 1
    fi
    
    # 检查 .env 文件
    if [ ! -f ".env" ]; then
        log_error ".env 文件不存在"
        log_info "请先创建 .env 文件（参考 env.template）"
        exit 1
    fi
    
    log_success "依赖检查通过"
}

# ============================================================
# 清理函数
# ============================================================

cleanup_review_stacks() {
    log_info "检查卡住的 CloudFormation Stack..."
    
    local stuck_stacks=$(aws cloudformation list-stacks \
        --region "$REGION" \
        --stack-status-filter REVIEW_IN_PROGRESS \
        --query "StackSummaries[?contains(StackName, '${APP_NAME}-${ENV_NAME}')].StackName" \
        --output text 2>/dev/null || echo "")
    
    if [ -z "$stuck_stacks" ]; then
        log_info "无卡住的 Stack"
        return 0
    fi
    
    log_warning "发现卡住的 Stack，正在清理..."
    for stack in $stuck_stacks; do
        echo "删除 $stack..."
        aws cloudformation delete-stack --stack-name "$stack" --region "$REGION" 2>/dev/null || true
    done
    
    sleep 5
    log_success "卡住的 Stack 已清理"
}

cleanup_failed_resources() {
    log_step "清理失败的部署资源"
    
    # 清理卡住的 Stack
    cleanup_review_stacks
    
    log_success "清理完成"
}

# ============================================================
# 环境变量管理
# ============================================================

setup_env_variables() {
    log_step "配置环境变量"
    
    if [ ! -f ".env" ]; then
        log_error ".env 文件不存在"
        exit 1
    fi
    
    log_info "从 .env 文件读取配置"
    
    # 添加 Redis 配置到 .env（如果不存在）
    if ! grep -q "REDIS_HOST" .env; then
        log_info "添加 Redis 配置到 .env"
        echo "" >> .env
        echo "# Redis 配置（复用 zen0-backend）" >> .env
        echo "REDIS_HOST=${REDIS_HOST}" >> .env
        echo "REDIS_PORT=${REDIS_PORT}" >> .env
    fi
    
    log_info "上传环境变量到 SSM Parameter Store..."
    
    # 读取 .env 文件并上传到 SSM
    while IFS='=' read -r key value || [ -n "$key" ]; do
        # 跳过注释和空行
        [[ "$key" =~ ^#.*$ ]] && continue
        [[ -z "$key" ]] && continue
        
        # 移除前后空格和引号
        key=$(echo "$key" | xargs)
        value=$(echo "$value" | xargs | sed 's/^["'\'']\(.*\)["'\'']$/\1/')
        
        # 跳过已在 manifest 中定义的变量
        if [[ "$key" =~ ^(LOG_LEVEL|MAX_TOKENS|TEMPERATURE|DATABASE_URL|REDIS_HOST|REDIS_PORT|AWS_DEFAULT_REGION|AWS_S3_BUCKET|ALLOWED_ORIGINS)$ ]]; then
            continue
        fi
        
        # 上传到 SSM（敏感信息）
        local param_name="/copilot/${APP_NAME}/${ENV_NAME}/secrets/${key}"
        
        if aws ssm put-parameter \
            --name "$param_name" \
            --value "$value" \
            --type "SecureString" \
            --overwrite \
            --region "$REGION" &> /dev/null; then
            log_info "  ✓ $key"
        else
            log_warning "  ✗ $key (可能已存在或权限不足)"
        fi
    done < .env
    
    log_success "环境变量上传完成"
}

# ============================================================
# SSL 证书管理
# ============================================================

request_certificate() {
    log_step "申请 SSL 证书"
    
    # 检查是否配置了域名
    if [ -z "$DOMAIN_NAME" ]; then
        log_error "未配置域名"
        log_info "请在脚本中设置 DOMAIN_NAME 变量或使用环境变量:"
        log_info "  export CUSTOM_DOMAIN=your-domain.com"
        log_info "  ./deploy/aws/staging/staging.sh cert request"
        exit 1
    fi
    
    log_info "域名: $DOMAIN_NAME"
    log_info "区域: $REGION"
    
    # 检查证书是否已存在
    local existing_cert=$(aws acm list-certificates \
        --region "$REGION" \
        --query "CertificateSummaryList[?DomainName=='${DOMAIN_NAME}'].CertificateArn" \
        --output text 2>/dev/null || echo "")
    
    if [ -n "$existing_cert" ]; then
        log_warning "证书已存在: $existing_cert"
        log_info "查看状态: ./deploy/aws/staging/staging.sh cert status"
        return 0
    fi
    
    log_info "申请新证书..."
    
    local cert_arn=$(aws acm request-certificate \
        --domain-name "$DOMAIN_NAME" \
        --validation-method DNS \
        --region "$REGION" \
        --query 'CertificateArn' \
        --output text 2>/dev/null || echo "")
    
    if [ -z "$cert_arn" ]; then
        log_error "证书申请失败"
        exit 1
    fi
    
    log_success "证书申请成功: $cert_arn"
    echo ""
    log_warning "⚠️  重要：需要完成 DNS 验证"
    echo ""
    echo "1. 获取 DNS 验证记录:"
    echo "   aws acm describe-certificate --certificate-arn $cert_arn --region $REGION"
    echo ""
    echo "2. 在您的 DNS 提供商添加 CNAME 记录"
    echo ""
    echo "3. 等待验证完成（通常 5-30 分钟）"
    echo "   ./deploy/aws/staging/staging.sh cert status"
    echo ""
}

check_certificate_status() {
    log_step "检查 SSL 证书状态"
    
    # 检查是否配置了域名
    if [ -z "$DOMAIN_NAME" ]; then
        log_warning "未配置域名，当前使用 HTTP 模式"
        log_info "如需启用 HTTPS，请设置域名并申请证书"
        return 1
    fi
    
    local cert_arn=$(aws acm list-certificates \
        --region "$REGION" \
        --query "CertificateSummaryList[?DomainName=='${DOMAIN_NAME}'].CertificateArn" \
        --output text 2>/dev/null || echo "")
    
    if [ -z "$cert_arn" ]; then
        log_warning "未找到证书"
        log_info "申请证书: export CUSTOM_DOMAIN=$DOMAIN_NAME && ./deploy/aws/staging/staging.sh cert request"
        return 1
    fi
    
    log_info "证书 ARN: $cert_arn"
    echo ""
    
    aws acm describe-certificate \
        --certificate-arn "$cert_arn" \
        --region "$REGION" \
        --query 'Certificate.{Status:Status,Domain:DomainName,Validation:DomainValidationOptions[0]}' \
        --output table
    
    local status=$(aws acm describe-certificate \
        --certificate-arn "$cert_arn" \
        --region "$REGION" \
        --query 'Certificate.Status' \
        --output text)
    
    if [ "$status" = "ISSUED" ]; then
        log_success "证书已签发，可以部署"
        return 0
    elif [ "$status" = "PENDING_VALIDATION" ]; then
        log_warning "等待 DNS 验证"
        echo ""
        echo "DNS 验证记录:"
        aws acm describe-certificate \
            --certificate-arn "$cert_arn" \
            --region "$REGION" \
            --query 'Certificate.DomainValidationOptions[0].ResourceRecord' \
            --output table
        return 1
    else
        log_error "证书状态异常: $status"
        return 1
    fi
}

# ============================================================
# 部署函数
# ============================================================

init_copilot_app() {
    log_step "检查/创建 Copilot 应用"
    
    # 检查应用是否已存在
    if $COPILOT app show --name "$APP_NAME" &> /dev/null; then
        log_success "应用 $APP_NAME 已存在"
        return 0
    fi
    
    # 应用不存在，创建新应用
    log_info "应用 $APP_NAME 不存在，正在创建..."
    
    if $COPILOT app init "$APP_NAME"; then
        log_success "应用 $APP_NAME 创建成功"
    else
        log_error "应用创建失败"
    exit 1
    fi
}

deploy_environment() {
    log_step "检查/创建 Staging 环境"
    
    log_info "环境配置: ${ENV_NAME} (${REGION})"
    log_info "应用: ${APP_NAME}"
    echo ""
    
    # 检查环境是否存在
    if $COPILOT env show --name "$ENV_NAME" &> /dev/null; then
        log_success "环境 $ENV_NAME 已存在"
        return 0
    fi
    
    # 环境不存在，创建新环境
    log_info "环境 $ENV_NAME 不存在，正在创建..."
    log_warning "预计时间: 10-15 分钟"
    echo ""
    
    if $COPILOT env init \
        --name "$ENV_NAME" \
        --profile default \
        --region "$REGION" \
        --default-config; then
        log_success "环境初始化成功"
    else
        log_error "环境初始化失败"
    exit 1
    fi
    
    log_info "部署环境..."
    if $COPILOT env deploy --name "$ENV_NAME"; then
        log_success "环境 $ENV_NAME 部署成功"
    else
        log_error "环境部署失败"
        exit 1
    fi
}

deploy_service() {
    log_step "部署应用服务"
    
    cleanup_review_stacks
    
    # ECR 仓库配置
    local ECR_REGISTRY="308470327605.dkr.ecr.${REGION}.amazonaws.com"
    local ECR_REPO="${ECR_REGISTRY}/${APP_NAME}/${SERVICE_NAME}"
    local IMAGE_TAG=$(date +%Y%m%d-%H%M%S)
    local FULL_IMAGE="${ECR_REPO}:${IMAGE_TAG}"
    
    log_info "应用: $APP_NAME"
    log_info "环境: $ENV_NAME"
    log_info "服务: $SERVICE_NAME"
    log_info "镜像: $FULL_IMAGE"
    log_warning "预计时间: 10-15 分钟"
    echo ""
    
    # 配置环境变量
    setup_env_variables
    
    # 检查服务是否已存在
    if $COPILOT svc show --name "$SERVICE_NAME" &> /dev/null; then
        log_info "服务已存在，执行更新部署..."
    else
        log_info "服务不存在，执行初始化..."
        # 初始化服务（使用现有的 manifest）
        if ! $COPILOT svc init \
            --name "$SERVICE_NAME" \
            --svc-type "Load Balanced Web Service" \
            --dockerfile "Dockerfile.production"; then
            log_error "服务初始化失败"
            exit 1
        fi
        log_success "服务初始化成功"
    fi
    
    # 手动构建并推送镜像（解决 Copilot 跨项目目录部署时的 bug）
    log_step "构建并推送 Docker 镜像"
    
    log_info "登录 ECR..."
    aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"
    
    log_info "构建镜像: $FULL_IMAGE (平台: linux/amd64)"
    # 指定 linux/amd64 平台，确保与 ECS Fargate 兼容
    if ! docker build --platform linux/amd64 -f Dockerfile.production -t "$FULL_IMAGE" -t "${ECR_REPO}:latest" .; then
        log_error "镜像构建失败"
        exit 1
    fi
    
    log_info "推送镜像..."
    if ! docker push "$FULL_IMAGE"; then
        log_error "镜像推送失败"
        exit 1
    fi
    docker push "${ECR_REPO}:latest"
    
    log_success "镜像推送完成: $FULL_IMAGE"
    
    # 更新 manifest 中的镜像位置
    log_info "更新 manifest 镜像位置..."
    sed -i.bak "s|location:.*|location: ${FULL_IMAGE}|" copilot/${SERVICE_NAME}/manifest.yml
    rm -f copilot/${SERVICE_NAME}/manifest.yml.bak
    
    START_TIME=$(date +%s)
    
    # 使用 --no-rollback 避免自动回滚，便于调试
    if $COPILOT svc deploy --name "$SERVICE_NAME" --env "$ENV_NAME"; then
        END_TIME=$(date +%s)
        DURATION=$((END_TIME - START_TIME))
        log_success "服务部署成功（用时: $((DURATION/60))分$((DURATION%60))秒）"
        
        save_state "deployed"
        log_to_file "Service deployed successfully"
    else
        log_error "服务部署失败"
        log_info "查看日志: copilot svc logs --name $SERVICE_NAME --env $ENV_NAME --since 30m"
        exit 1
    fi
}

run_database_migration() {
    log_step "运行数据库迁移"
    
    log_info "通过 ECS Exec 执行迁移脚本"
    
    # 检查是否有迁移文件
    if [ ! -d "migrations" ]; then
        log_warning "未找到 migrations 目录，跳过迁移"
        return 0
    fi
    
    # 执行迁移（通过 copilot svc exec）
    log_info "执行迁移命令..."
    
    if $COPILOT svc exec \
        --name "$SERVICE_NAME" \
        --env "$ENV_NAME" \
        --command "python -c 'from infra.database import init_database; import asyncio; asyncio.run(init_database())'"; then
        log_success "数据库迁移完成"
    else
        log_warning "数据库迁移失败（可能已初始化）"
    fi
}

perform_health_check() {
    log_step "执行健康检查"
    
    local service_url=$($COPILOT svc show --name "$SERVICE_NAME" --env "$ENV_NAME" --json 2>/dev/null | \
        jq -r '.routes[0].url // empty')
    
    if [ -z "$service_url" ] || [ "$service_url" = "null" ]; then
        log_warning "无法获取服务 URL，跳过健康检查"
        return 0
    fi
    
    service_url="${service_url%/}"
    local health_url="${service_url}/health"
    
    log_info "健康检查地址: $health_url"
    log_info "超时时间: ${HEALTH_CHECK_TIMEOUT} 秒"
    
    local elapsed=0
    while [ $elapsed -lt $HEALTH_CHECK_TIMEOUT ]; do
        if curl -f -s --connect-timeout 2 --max-time 5 -o /dev/null "$health_url" 2>/dev/null; then
            log_success "健康检查通过"
            echo ""
            log_success "🎉 部署完成！"
            echo ""
            echo "访问地址:"
            echo "  - API: $service_url"
            echo "  - 健康检查: $health_url"
            echo "  - 文档: ${service_url}/docs"
            echo ""
            return 0
        fi
        
        sleep $HEALTH_CHECK_INTERVAL
        elapsed=$((elapsed + HEALTH_CHECK_INTERVAL))
        echo -n "."
    done
    
    echo ""
    log_warning "健康检查超时，但服务可能仍在启动中"
    return 1
}

# ============================================================
# 启动/停止函数
# ============================================================

start_environment() {
    log_step "启动 Staging 环境"
    
    # 获取 ECS 集群和服务
    local cluster=$(aws ecs list-clusters --region "$REGION" \
        --query "clusterArns[?contains(@, '${APP_NAME}-${ENV_NAME}')]" \
        --output text 2>/dev/null | head -1)
    
    if [ -z "$cluster" ]; then
        log_error "未找到 ECS 集群"
        log_info "环境可能未部署，请先运行: ./deploy/aws/staging/staging.sh deploy"
        exit 1
    fi
    
    local cluster_name=$(echo "$cluster" | cut -d'/' -f2)
    
    local service=$(aws ecs list-services --cluster "$cluster" --region "$REGION" \
        --query "serviceArns[?contains(@, '$SERVICE_NAME')]" \
        --output text 2>/dev/null | head -1)
    
    if [ -z "$service" ]; then
        log_error "未找到 ECS 服务"
        exit 1
    fi
    
    log_info "集群: $cluster_name"
    log_info "启动 ECS 任务，目标副本数: 1"
    
    if aws ecs update-service \
        --cluster "$cluster" \
        --service "$service" \
        --desired-count 1 \
        --region "$REGION" &> /dev/null; then
        
        log_success "启动命令已发送"
        log_info "等待服务稳定（约 2-3 分钟）..."
        
        if aws ecs wait services-stable \
            --cluster "$cluster" \
            --services "$service" \
            --region "$REGION" 2>/dev/null; then
            log_success "服务已稳定运行"
        else
            log_warning "等待超时，但服务可能仍在启动中"
        fi
        
        save_state "started"
        log_to_file "Environment started"
        
        echo ""
        log_success "环境启动成功"
    else
        log_error "启动失败"
        exit 1
    fi
}

stop_environment() {
    local keep_service=${1:-false}
    local force=${2:-false}
    
    log_step "停止 Staging 环境"
    
    if [ "$force" != "true" ]; then
        if [ "$keep_service" = "true" ]; then
            echo "将缩容 ECS 任务到 0（保留配置）"
        else
            echo "将完全停止并删除环境"
        fi
        echo ""
        read -p "确认继续？[y/N] " confirm
        if [[ ! $confirm =~ ^[Yy]$ ]]; then
            log_info "操作已取消"
            exit 0
        fi
    fi
    
    if [ "$keep_service" = "true" ]; then
        # 仅缩容
        local cluster=$(aws ecs list-clusters --region "$REGION" \
            --query "clusterArns[?contains(@, '${APP_NAME}-${ENV_NAME}')]" \
            --output text 2>/dev/null | head -1)
        
        if [ -n "$cluster" ]; then
            local service=$(aws ecs list-services --cluster "$cluster" --region "$REGION" \
                --query "serviceArns[?contains(@, '$SERVICE_NAME')]" \
                --output text 2>/dev/null | head -1)
            
            if [ -n "$service" ]; then
                log_info "缩容 ECS 任务到 0..."
                if aws ecs update-service \
                    --cluster "$cluster" \
                    --service "$service" \
                    --desired-count 0 \
                    --region "$REGION" &> /dev/null; then
                    log_success "服务已缩容"
                    save_state "stopped"
                    log_to_file "Environment stopped (scale to 0)"
                fi
            fi
        fi
    else
        # 完全停止
        log_info "删除服务..."
        $COPILOT svc delete --name "$SERVICE_NAME" --env "$ENV_NAME" --yes 2>/dev/null || true
        
        sleep 10
        
        log_info "删除环境..."
        $COPILOT env delete --name "$ENV_NAME" --yes 2>/dev/null || true
        
        save_state "deleted"
        log_to_file "Environment deleted"
        
        log_success "环境已完全删除"
    fi
}

# ============================================================
# 状态查看
# ============================================================

show_status() {
    log_step "Staging 环境状态"
    
    # 本地状态
    local state_info=$(read_state)
    local state=$(echo "$state_info" | cut -d'|' -f1)
    local state_time=$(echo "$state_info" | cut -d'|' -f2)
    
    echo "本地记录:"
    echo "  状态: $state"
    echo "  时间: $state_time"
    echo ""
    
    # 检查环境
    echo "环境状态:"
    if $COPILOT env show --name "$ENV_NAME" &> /dev/null; then
        log_success "环境已创建"
    else
        log_warning "环境未创建"
    fi
    
    # 检查服务
    echo ""
    echo "服务状态:"
    $COPILOT svc status --name "$SERVICE_NAME" --env "$ENV_NAME" 2>/dev/null || \
        log_warning "服务未部署"
    
    # 检查 ECS
    echo ""
    echo "ECS 状态:"
    local cluster=$(aws ecs list-clusters --region "$REGION" \
        --query "clusterArns[?contains(@, '${APP_NAME}-${ENV_NAME}')]" \
        --output text 2>/dev/null | head -1)
    
    if [ -n "$cluster" ]; then
        local service=$(aws ecs list-services --cluster "$cluster" --region "$REGION" \
            --query "serviceArns[?contains(@, '$SERVICE_NAME')]" \
            --output text 2>/dev/null | head -1)
        
        if [ -n "$service" ]; then
            local running=$(aws ecs describe-services \
                --cluster "$cluster" \
                --services "$service" \
                --region "$REGION" \
                --query 'services[0].runningCount' \
                --output text 2>/dev/null)
            
            local desired=$(aws ecs describe-services \
                --cluster "$cluster" \
                --services "$service" \
                --region "$REGION" \
                --query 'services[0].desiredCount' \
                --output text 2>/dev/null)
            
            echo "  运行任务: $running/$desired"
        fi
    fi
    
    # 检查证书
    echo ""
    echo "SSL 证书:"
    check_certificate_status &> /dev/null && log_success "证书已签发" || log_warning "证书未就绪"
}

show_logs() {
    local follow=${1:-false}
    local since=${2:-10m}
    
    if [ "$follow" = "true" ]; then
        $COPILOT svc logs --name "$SERVICE_NAME" --env "$ENV_NAME" --follow
    else
        $COPILOT svc logs --name "$SERVICE_NAME" --env "$ENV_NAME" --since "$since"
    fi
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
    local env_only=false
    local svc_only=false
    local force=false
    local skip_checks=false
    local skip_health=false
    local keep_service=false
    local follow=false
    local since="10m"
    local cert_action=""
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --env-only) env_only=true; shift ;;
            --svc-only) svc_only=true; shift ;;
            --force) force=true; shift ;;
            --skip-checks) skip_checks=true; shift ;;
            --skip-health) skip_health=true; shift ;;
            --keep-service) keep_service=true; shift ;;
            --follow) follow=true; shift ;;
            --since) since=$2; shift 2 ;;
            --help) show_help ;;
            request|status) cert_action=$1; shift ;;
            *) shift ;;
        esac
    done
    
    # 执行命令
    case $command in
        deploy)
            echo ""
            echo -e "${CYAN}==========================================${NC}"
            echo -e "${CYAN}🚀 部署 Staging 环境${NC}"
            echo -e "${CYAN}==========================================${NC}"
            
            [ "$skip_checks" != "true" ] && check_dependencies
            
            # 显示部署模式
            if [ -z "$DOMAIN_NAME" ]; then
                log_warning "⚠️  HTTP 模式部署（无 SSL 证书）"
                log_info "访问地址将使用 ALB 默认域名"
                echo ""
            else
                log_info "🔒 HTTPS 模式部署"
                log_info "域名: $DOMAIN_NAME"
                
                # 检查证书状态（仅警告，不阻止部署）
                if ! check_certificate_status &> /dev/null; then
                    log_warning "⚠️  证书未就绪，将使用 HTTP"
                    log_info "部署后可通过 ALB 默认域名访问"
                    log_info "证书就绪后，重新部署即可启用 HTTPS"
                fi
                echo ""
            fi
            
            init_copilot_app
            
            if [ "$svc_only" != "true" ]; then
                deploy_environment
            fi
            
            if [ "$env_only" != "true" ]; then
                deploy_service
                [ "$skip_health" != "true" ] && perform_health_check
                run_database_migration
            fi
            
            log_success "部署完成"
            log_info "查看状态: ./deploy/aws/staging/staging.sh status"
            ;;
            
        start)
            check_dependencies
            start_environment
            ;;
            
        stop)
            check_dependencies
            stop_environment "$keep_service" "$force"
            ;;
            
        status)
            check_dependencies
            show_status
            ;;
            
        logs)
            check_dependencies
            show_logs "$follow" "$since"
            ;;
            
        cert)
            check_dependencies
            case $cert_action in
                request) request_certificate ;;
                status) check_certificate_status ;;
                *) 
                    log_error "未知证书操作: $cert_action"
                    echo "用法: ./deploy/aws/staging/staging.sh cert [request|status]"
                    exit 1
                    ;;
            esac
            ;;
            
        clean)
            check_dependencies
            cleanup_failed_resources
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
