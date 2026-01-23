#!/usr/bin/env bash
# ============================================================
# Zenflux Agent - Production 环境统一管理脚本
# ============================================================
# 功能：
#   - deploy: 完整部署（环境 + 服务）
#   - rollback: 回滚到指定版本
#   - status: 查看环境状态
#   - logs: 查看服务日志
#   - clean: 清理失败的部署资源
#
# 用法：
#   ./deploy/aws/production/production.sh deploy [--env-only|--svc-only|--force]
#   ./deploy/aws/production/production.sh rollback [--to-version <tag>]
#   ./deploy/aws/production/production.sh status
#   ./deploy/aws/production/production.sh logs [--follow]
#   ./deploy/aws/production/production.sh --help
#
# 注意：
#   - Production 环境为 7×24 持续运行，不提供 start/stop 命令
#   - Production 使用 Load Balanced Web Service，仅内网 gRPC 暴露（不配置公网域名）
#   - 其他服务通过 NLB 或 Service Connect 访问：agent.production.zen0-backend.local:50051
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
ENV_NAME="production"            # 生产环境
SERVICE_NAME="agent"             # 服务名（与 staging 统一）

# AWS Copilot CLI 路径（自动检测，支持 Mac/Linux/Windows）
detect_copilot() {
    if command -v copilot &> /dev/null; then
        command -v copilot
        return 0
    fi
    if [ -x "/opt/homebrew/bin/copilot" ]; then
        echo "/opt/homebrew/bin/copilot"
        return 0
    fi
    if [ -x "/usr/local/bin/copilot" ]; then
        echo "/usr/local/bin/copilot"
        return 0
    fi
    if [ -x "$HOME/bin/copilot" ]; then
        echo "$HOME/bin/copilot"
        return 0
    fi
    echo ""
    return 1
}

COPILOT="$(detect_copilot)"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
NC='\033[0m'

# 日志配置
LOG_DIR="logs"
LOG_FILE="$LOG_DIR/production-$(date +%Y%m%d-%H%M%S).log"
STATE_FILE=".production-state"

# 健康检查配置
HEALTH_CHECK_TIMEOUT=180
HEALTH_CHECK_INTERVAL=15

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
用法: ./deploy/aws/production/production.sh <命令> [选项]

命令:
  deploy              部署环境和服务
  rollback            回滚到指定版本
  status              查看环境状态
  logs                查看服务日志
  clean               清理失败的部署资源

deploy 选项:
  --env-only          仅创建环境，不部署服务
  --svc-only          仅部署服务（假设环境已存在）
  --force             强制清理并重新创建
  --skip-checks       跳过前置检查
  --skip-health       跳过健康检查
  --skip-confirm      跳过确认（危险！仅用于 CI/CD）

rollback 选项:
  --to-version <tag>  回滚到指定镜像标签

logs 选项:
  --follow            实时跟踪日志
  --since <时间>      显示指定时间以来的日志（如: 10m, 1h）

示例:
  # 完整部署（首次）
  ./deploy/aws/production/production.sh deploy

  # 仅部署服务（环境已存在）
  ./deploy/aws/production/production.sh deploy --svc-only

  # 回滚到指定版本
  ./deploy/aws/production/production.sh rollback --to-version 20260101-120000

  # 查看状态
  ./deploy/aws/production/production.sh status

  # 查看实时日志
  ./deploy/aws/production/production.sh logs --follow

注意：
  - Production 环境为 7×24 持续运行，不提供 start/stop 命令
  - Production 使用 Load Balanced Web Service，仅内网 gRPC 暴露（不配置公网域名）
  - 其他服务通过 NLB 或 Service Connect 访问：agent.production.zen0-backend.local:50051

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
        case "$(uname -s)" in
            Darwin)
                echo "  brew install aws/tap/copilot-cli"
                ;;
            Linux)
                echo "  sudo curl -Lo /usr/local/bin/copilot https://github.com/aws/copilot-cli/releases/latest/download/copilot-linux"
                echo "  sudo chmod +x /usr/local/bin/copilot"
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
    
    cleanup_review_stacks
    
    log_success "清理完成"
}

# ============================================================
# 环境变量管理
# ============================================================

setup_env_variables() {
    log_step "配置环境变量"
    
    # 使用临时文件存储 .env
    local merged_env=$(mktemp)
    
    # 只读取 .env.production（Production 环境专用配置）
    if [ -f ".env.production" ]; then
        log_info "📄 Production 专用 .env.production"
        _load_env_file ".env.production" "$merged_env"
    else
        log_warning "⚠️ .env.production 不存在，跳过环境变量上传"
        rm -f "$merged_env"
        return 0
    fi
    
    # 去重（保留最后出现的值）
    local unique_env=$(mktemp)
    if command -v tac &>/dev/null; then
        tac "$merged_env" | awk -F= '!seen[$1]++' | tac > "$unique_env"
    elif command -v tail &>/dev/null && tail -r /dev/null &>/dev/null 2>&1; then
        tail -r "$merged_env" | awk -F= '!seen[$1]++' | tail -r > "$unique_env"
    else
        awk -F= '{key=$1; val=$0; if(key!="") lines[key]=val} END {for(k in lines) print lines[k]}' "$merged_env" > "$unique_env"
    fi
    local var_count=$(wc -l < "$unique_env" | tr -d ' ')
    
    log_info "📤 上传 ${var_count} 个环境变量到 SSM Parameter Store..."
    
    # 上传所有合并后的环境变量
    local success_count=0
    while IFS='=' read -r key value || [ -n "$key" ]; do
        [ -z "$key" ] && continue
        
        local param_name="/copilot/${APP_NAME}/${ENV_NAME}/secrets/${key}"
        
        if aws ssm put-parameter \
            --name "$param_name" \
            --value "$value" \
            --type "SecureString" \
            --overwrite \
            --region "$REGION" &> /dev/null; then
            log_info "  ✓ $key"
            ((success_count++))
        else
            log_warning "  ✗ $key (可能已存在或权限不足)"
        fi
    done < "$unique_env"
    
    # 清理临时文件
    rm -f "$merged_env" "$unique_env"
    
    log_success "环境变量上传完成（${success_count}/${var_count} 个成功）"
}

# 辅助函数：加载单个 .env 文件到临时文件
_load_env_file() {
    local env_file=$1
    local output_file=$2
    local count=0
    
    while IFS='=' read -r key value || [ -n "$key" ]; do
        # 跳过注释和空行
        [[ "$key" =~ ^#.*$ ]] && continue
        [[ -z "$key" ]] && continue
        
        # 移除前后空格和引号
        key=$(echo "$key" | xargs)
        value=$(echo "$value" | xargs | sed 's/^["'\'']\(.*\)["'\'']$/\1/')
        
        # 跳过已在 manifest 中定义的变量
        if [[ "$key" =~ ^(LOG_LEVEL|MAX_TOKENS|TEMPERATURE|DATABASE_URL|AWS_DEFAULT_REGION|AWS_S3_BUCKET|ALLOWED_ORIGINS)$ ]]; then
            continue
        fi
        
        # 追加到临时文件
        echo "${key}=${value}" >> "$output_file"
        ((count++))
    done < "$env_file"
    
    log_info "   已加载 ${count} 个变量"
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
    log_step "检查/创建 Production 环境"
    
    log_info "环境配置: ${ENV_NAME} (${REGION})"
    log_info "应用: ${APP_NAME}"
    log_warning "预计时间: 15-20 分钟"
    echo ""
    
    # 检查环境是否存在
    if $COPILOT env show --name "$ENV_NAME" &> /dev/null; then
        log_success "环境 $ENV_NAME 已存在"
        return 0
    fi
    
    # 环境不存在，创建新环境
    log_info "环境 $ENV_NAME 不存在，正在创建..."
    
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
    
    # 在部署前检查和设置必要的 IAM 权限
    log_info "检查 IAM 权限..."
    
    # 尝试设置权限（如果角色存在）
    local EXECUTION_ROLE=$(aws iam list-roles \
        --query "Roles[?starts_with(RoleName, '${APP_NAME}-${ENV_NAME}-${SERVICE_NAME}-ExecutionRole')].RoleName" \
        --output text 2>/dev/null || echo "")
    
    if [ -n "$EXECUTION_ROLE" ]; then
        # 检查是否已有 SSMParameterStoreAccess 权限
        if ! aws iam get-role-policy \
            --role-name "$EXECUTION_ROLE" \
            --policy-name "SSMParameterStoreAccess" &> /dev/null; then
            
            log_warning "ExecutionRole 缺少 SSM 访问权限，正在添加..."
            
            ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
            POLICY_DOCUMENT="{
              \"Version\": \"2012-10-17\",
              \"Statement\": [
                {
                  \"Sid\": \"SSMParameterStoreAccess\",
                  \"Effect\": \"Allow\",
                  \"Action\": [\"ssm:GetParameters\", \"ssm:GetParameter\"],
                  \"Resource\": [
                    \"arn:aws:ssm:${REGION}:${ACCOUNT_ID}:parameter/copilot/${APP_NAME}/staging/secrets/*\",
                    \"arn:aws:ssm:${REGION}:${ACCOUNT_ID}:parameter/copilot/${APP_NAME}/${ENV_NAME}/secrets/*\"
                  ]
                },
                {
                  \"Sid\": \"KMSDecryptAccess\",
                  \"Effect\": \"Allow\",
                  \"Action\": [\"kms:Decrypt\"],
                  \"Resource\": \"arn:aws:kms:${REGION}:${ACCOUNT_ID}:key/*\"
                }
              ]
            }"
            
            if aws iam put-role-policy \
                --role-name "$EXECUTION_ROLE" \
                --policy-name "SSMParameterStoreAccess" \
                --policy-document "$POLICY_DOCUMENT" &> /dev/null; then
                log_success "IAM 权限已添加"
            else
                log_warning "添加 IAM 权限失败（可能是权限不足，继续部署...）"
            fi
        else
            log_success "SSM 访问权限已配置"
        fi
    fi
    
    # ECR 仓库配置（动态获取 Account ID）
    local ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    local ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
    local ECR_REPO="${ECR_REGISTRY}/${APP_NAME}/${SERVICE_NAME}"
    local IMAGE_TAG=$(date +%Y%m%d-%H%M%S)
    local FULL_IMAGE="${ECR_REPO}:${IMAGE_TAG}"
    
    log_info "应用: $APP_NAME"
    log_info "环境: $ENV_NAME"
    log_info "服务: $SERVICE_NAME"
    log_info "镜像: $FULL_IMAGE"
    log_warning "预计时间: 15-20 分钟"
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
    
    # 手动构建并推送镜像
    log_step "构建并推送 Docker 镜像"
    
    log_info "登录 ECR..."
    aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"
    
    log_info "构建镜像: $FULL_IMAGE (平台: linux/amd64)"
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

perform_health_check() {
    log_step "执行健康检查"
    
    # Production 不配置公网域名，通过 ECS 任务状态检查
    log_info "检查 ECS 任务状态..."
    
    local cluster=$(aws ecs list-clusters --region "$REGION" \
        --query "clusterArns[?contains(@, '${APP_NAME}-${ENV_NAME}')]" \
        --output text 2>/dev/null | head -1)
    
    if [ -z "$cluster" ]; then
        log_warning "无法获取 ECS 集群，跳过健康检查"
        return 0
    fi
    
    local service=$(aws ecs list-services --cluster "$cluster" --region "$REGION" \
        --query "serviceArns[?contains(@, '$SERVICE_NAME')]" \
        --output text 2>/dev/null | head -1)
    
    if [ -z "$service" ]; then
        log_warning "无法获取 ECS 服务，跳过健康检查"
        return 0
    fi
    
    log_info "等待服务稳定（约 2-3 分钟）..."
    
    local elapsed=0
    while [ $elapsed -lt $HEALTH_CHECK_TIMEOUT ]; do
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
        
        if [ "$running" = "$desired" ] && [ "$running" != "0" ]; then
            log_success "健康检查通过（运行任务: $running/$desired）"
            echo ""
            log_success "🎉 部署完成！"
            echo ""
            echo "内网访问地址:"
            echo "  - gRPC: ${SERVICE_NAME}.${ENV_NAME}.${APP_NAME}.local:50051"
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
# 回滚函数
# ============================================================

rollback_service() {
    local target_version=${1:-}
    
    log_step "回滚 Production 服务"
    
    if [ -z "$target_version" ]; then
        # 列出最近的镜像标签
        log_info "获取可用版本..."
        
        local ecr_repo="${APP_NAME}/${SERVICE_NAME}"
        local images=$(aws ecr describe-images \
            --repository-name "$ecr_repo" \
            --region "$REGION" \
            --query 'imageDetails[*].{Tag:imageTags[0],PushedAt:imagePushedAt}' \
            --output json 2>/dev/null | jq -r 'sort_by(.PushedAt) | reverse | .[0:10] | .[] | "\(.Tag) (\(.PushedAt))"')
        
        if [ -z "$images" ]; then
            log_error "无法获取镜像列表"
            exit 1
        fi
        
        echo ""
        echo "最近 10 个版本:"
        echo "$images" | nl
        echo ""
        read -p "请输入要回滚的版本标签: " target_version
    fi
    
    if [ -z "$target_version" ]; then
        log_error "未指定版本"
        exit 1
    fi
    
    log_info "回滚到版本: $target_version"
    
    # 获取当前任务定义
    local cluster=$(aws ecs list-clusters --region "$REGION" \
        --query "clusterArns[?contains(@, '${APP_NAME}-${ENV_NAME}')]" \
        --output text 2>/dev/null | head -1)
    
    if [ -z "$cluster" ]; then
        log_error "未找到 ECS 集群"
        exit 1
    fi
    
    local service=$(aws ecs list-services --cluster "$cluster" --region "$REGION" \
        --query "serviceArns[?contains(@, '$SERVICE_NAME')]" \
        --output text 2>/dev/null | head -1)
    
    if [ -z "$service" ]; then
        log_error "未找到 ECS 服务"
        exit 1
    fi
    
    # 获取当前任务定义
    local current_task_def=$(aws ecs describe-services \
        --cluster "$cluster" \
        --services "$service" \
        --region "$REGION" \
        --query 'services[0].taskDefinition' \
        --output text)
    
    log_info "当前任务定义: $current_task_def"
    
    # 获取 ECR 仓库 URI
    local account_id=$(aws sts get-caller-identity --query Account --output text)
    local ecr_uri="${account_id}.dkr.ecr.${REGION}.amazonaws.com/${APP_NAME}/${SERVICE_NAME}:${target_version}"
    
    log_info "目标镜像: $ecr_uri"
    
    # 创建新的任务定义
    local new_task_def=$(aws ecs describe-task-definition \
        --task-definition "$current_task_def" \
        --region "$REGION" \
        --query 'taskDefinition' | \
        jq --arg IMAGE "$ecr_uri" '.containerDefinitions[0].image = $IMAGE | del(.taskDefinitionArn, .revision, .status, .requiresAttributes, .compatibilities, .registeredAt, .registeredBy)')
    
    local new_task_def_arn=$(echo "$new_task_def" | aws ecs register-task-definition \
        --region "$REGION" \
        --cli-input-json file:///dev/stdin \
        --query 'taskDefinition.taskDefinitionArn' \
        --output text)
    
    log_info "新任务定义: $new_task_def_arn"
    
    # 更新服务
    log_info "更新服务..."
    if aws ecs update-service \
        --cluster "$cluster" \
        --service "$service" \
        --task-definition "$new_task_def_arn" \
        --region "$REGION" &> /dev/null; then
        
        log_success "回滚命令已发送"
        log_info "等待服务稳定（约 3-5 分钟）..."
        
        if aws ecs wait services-stable \
            --cluster "$cluster" \
            --services "$service" \
            --region "$REGION" 2>/dev/null; then
            log_success "服务已稳定运行"
        else
            log_warning "等待超时，请检查服务状态"
        fi
        
        save_state "rolled_back:$target_version"
        log_to_file "Service rolled back to $target_version"
    else
        log_error "回滚失败"
        exit 1
    fi
}

# ============================================================
# 状态查看
# ============================================================

show_status() {
    log_step "Production 环境状态"
    
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
    
    # 内网访问地址
    echo ""
    echo "内网访问地址:"
    echo "  gRPC: ${SERVICE_NAME}.${ENV_NAME}.${APP_NAME}.local:50051"
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
    local skip_confirm=false
    local follow=false
    local since="10m"
    local rollback_version=""
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --env-only) env_only=true; shift ;;
            --svc-only) svc_only=true; shift ;;
            --force) force=true; shift ;;
            --skip-checks) skip_checks=true; shift ;;
            --skip-health) skip_health=true; shift ;;
            --skip-confirm) skip_confirm=true; shift ;;
            --follow) follow=true; shift ;;
            --since) since=$2; shift 2 ;;
            --to-version) rollback_version=$2; shift 2 ;;
            --help) show_help ;;
            *) shift ;;
        esac
    done
    
    # 执行命令
    case $command in
        deploy)
            echo ""
            echo -e "${MAGENTA}==========================================${NC}"
            echo -e "${MAGENTA}🚀 部署 Production 环境${NC}"
            echo -e "${MAGENTA}==========================================${NC}"
            
            [ "$skip_confirm" != "true" ] && confirm_production_action "deploy"
            [ "$skip_checks" != "true" ] && check_dependencies
            
            init_copilot_app
            
            if [ "$svc_only" != "true" ]; then
                deploy_environment
            fi
            
            if [ "$env_only" != "true" ]; then
                deploy_service
                [ "$skip_health" != "true" ] && perform_health_check
            fi
            
            log_success "部署完成"
            log_info "查看状态: ./deploy/aws/production/production.sh status"
            log_info "内网地址: ${SERVICE_NAME}.${ENV_NAME}.${APP_NAME}.local:50051"
            ;;
            
        rollback)
            [ "$skip_confirm" != "true" ] && confirm_production_action "rollback"
            check_dependencies
            rollback_service "$rollback_version"
            ;;
            
        status)
            check_dependencies
            show_status
            ;;
            
        logs)
            check_dependencies
            show_logs "$follow" "$since"
            ;;
            
        clean)
            [ "$skip_confirm" != "true" ] && confirm_production_action "clean"
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
