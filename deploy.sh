#!/usr/bin/env bash
# ============================================================
# Zenflux Agent - 统一部署管理脚本
# ============================================================
# 功能：
#   - 交互式选择环境和操作
#   - 支持直接执行模式（CI/CD）
#   - 可选的企微 Webhook 部署通知
#
# 用法：
#   ./deploy.sh                           # 交互模式
#   ./deploy.sh <env> <action> [options]  # 直接执行模式
#   ./deploy.sh config                    # 配置管理
#   ./deploy.sh --help                    # 显示帮助
#
# 示例：
#   ./deploy.sh staging deploy --notify
#   ./deploy.sh staging status
#   ./deploy.sh config --show
# ============================================================

set -euo pipefail

# ============================================================
# 配置变量
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"

# 配置文件路径
CONFIG_FILE="${HOME}/.zenflux-deploy-config"

# AWS 配置
REGION="${AWS_REGION:-ap-southeast-1}"
APP_NAME="zen0-backend"
SERVICE_NAME="agent"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m'

# 全局变量
WECHAT_WEBHOOK_URL=""
DEPLOY_USER_NAME=""  # 可配置的操作者名称
SELECTED_ENV=""
SELECTED_ACTION=""
FORCE_NOTIFY=""  # "yes" | "no" | ""
START_TIME=0
END_TIME=0

# ============================================================
# 辅助函数
# ============================================================

log_info() { printf "${BLUE}ℹ️  %s${NC}\n" "$1"; }
log_success() { printf "${GREEN}✅ %s${NC}\n" "$1"; }
log_warning() { printf "${YELLOW}⚠️  %s${NC}\n" "$1"; }
log_error() { printf "${RED}❌ %s${NC}\n" "$1"; }

# 检查依赖
check_dependencies() {
    local missing=()
    for cmd in curl jq aws docker copilot; do
        if ! command -v "$cmd" &>/dev/null; then
            missing+=("$cmd")
        fi
    done
    if [ ${#missing[@]} -gt 0 ]; then
        log_error "缺少依赖工具: ${missing[*]}"
        log_info "安装建议："
        log_info "  brew install curl jq awscli docker"
        log_info "  brew install aws/tap/copilot-cli"
        exit 1
    fi
}

# 显示横幅
show_banner() {
    clear
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║                                                          ║"
    echo "║           Zenflux Agent 部署管理工具                     ║"
    echo "║                                                          ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# 显示帮助
show_help() {
    cat << 'EOF'
用法: ./deploy.sh [命令] [选项]

交互模式:
  ./deploy.sh                     启动交互式菜单

直接执行模式:
  ./deploy.sh <环境> <操作> [选项]

环境:
  staging                         测试环境

操作:
  deploy                          部署服务
  status                          查看状态
  logs                            查看日志
  start                           启动环境
  stop                            停止环境
  clean                           清理资源
  exec                            进入容器

通知选项:
  --notify                        操作完成后发送企微通知
  --no-notify                     不发送通知

部署选项:
  --svc-only                      仅部署服务（跳过环境检查）

配置管理:
  ./deploy.sh config              配置企微 Webhook URL
  ./deploy.sh config --show       显示当前配置
  ./deploy.sh config --clear      清除配置

帮助:
  --help, -h                      显示帮助信息

示例:
  ./deploy.sh                              # 交互模式
  ./deploy.sh staging deploy               # 部署 staging
  ./deploy.sh staging deploy --notify      # 部署并发送通知
  ./deploy.sh staging status               # 查看 staging 状态
  ./deploy.sh staging logs                 # 查看日志
  ./deploy.sh config                       # 配置 Webhook

EOF
    exit 0
}

# ============================================================
# 配置管理
# ============================================================

# 加载配置
load_config() {
    if [ -f "$CONFIG_FILE" ]; then
        # shellcheck source=/dev/null
        source "$CONFIG_FILE"
    fi
}

# 保存配置
save_config() {
    # 保存所有配置项
    cat > "$CONFIG_FILE" << EOF
WECHAT_WEBHOOK_URL="${WECHAT_WEBHOOK_URL}"
DEPLOY_USER_NAME="${DEPLOY_USER_NAME}"
EOF
    chmod 600 "$CONFIG_FILE"
    log_success "配置已保存到 $CONFIG_FILE"
}

# 显示配置
show_config() {
    echo ""
    echo "当前配置:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    if [ -f "$CONFIG_FILE" ]; then
        echo "配置文件: $CONFIG_FILE"
        if [ -n "$WECHAT_WEBHOOK_URL" ]; then
            # 隐藏部分 key
            local masked_url
            masked_url=$(echo "$WECHAT_WEBHOOK_URL" | sed 's/\(key=.\{8\}\).\{20\}/\1********************/')
            echo "Webhook URL: $masked_url"
        else
            echo "Webhook URL: 未配置"
        fi
        echo "操作者名称: ${DEPLOY_USER_NAME:-未配置 (将使用系统用户名: $USER)}"
    else
        echo "配置文件: 不存在"
        echo "Webhook URL: 未配置"
        echo "操作者名称: 未配置 (将使用系统用户名: $USER)"
    fi
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
}

# 清除配置
clear_config() {
    if [ -f "$CONFIG_FILE" ]; then
        rm -f "$CONFIG_FILE"
        WECHAT_WEBHOOK_URL=""
        DEPLOY_USER_NAME=""
        log_success "配置已清除"
    else
        log_info "配置文件不存在"
    fi
}

# 交互式配置
prompt_webhook_config() {
    echo ""
    echo "部署通知配置"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    # 配置操作者名称
    echo "1. 操作者名称配置"
    echo "   当前: ${DEPLOY_USER_NAME:-未配置 (使用系统用户名: $USER)}"
    read -p "   输入操作者名称 (留空保持不变): " new_name
    if [ -n "$new_name" ]; then
        DEPLOY_USER_NAME="$new_name"
        log_success "操作者名称已设置为: $DEPLOY_USER_NAME"
    fi
    
    echo ""
    echo "2. 企微 Webhook 配置"
    echo "   配置步骤:"
    echo "     a. 打开企业微信群 → 群设置 → 群机器人"
    echo "     b. 添加机器人，复制 Webhook 地址"
    echo "     c. 粘贴到下方"
    echo ""
    
    if [ -n "$WECHAT_WEBHOOK_URL" ]; then
        echo "   当前已配置 Webhook URL"
        read -p "   是否重新配置? [y/N]: " reconfigure
        if [[ ! $reconfigure =~ ^[Yy]$ ]]; then
            # 保存配置（可能只更新了操作者名称）
            save_config
            return 0
        fi
    fi
    
    read -p "   Webhook URL (留空跳过): " url
    
    if [ -n "$url" ]; then
        # 简单验证 URL 格式
        if [[ $url =~ ^https://qyapi\.weixin\.qq\.com/cgi-bin/webhook/send\?key= ]]; then
            WECHAT_WEBHOOK_URL="$url"
            save_config
            
            # 测试通知
            read -p "   发送测试通知? [y/N]: " test_notify
            if [[ $test_notify =~ ^[Yy]$ ]]; then
                send_test_notify
            fi
        else
            log_error "URL 格式不正确，应以 https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key= 开头"
            return 1
        fi
    else
        # 保存配置（可能只更新了操作者名称）
        save_config
        log_info "Webhook URL 保持不变"
    fi
}

# 配置管理入口
manage_config() {
    local action="${1:-}"
    
    case "$action" in
        --show)
            show_config
            ;;
        --clear)
            clear_config
            ;;
        *)
            prompt_webhook_config
            ;;
    esac
}

# ============================================================
# 企微通知
# ============================================================

# 获取服务信息
get_service_info() {
    local env=$1
    local service_url=""
    local image_tag=""
    local task_count="N/A"
    local git_branch=""
    local git_commit=""
    
    # 根据环境设置服务 URL
    case "$env" in
        staging) service_url="https://agent.malue.ai" ;;
        production) service_url="https://agent.dazee.ai" ;;
    esac
    
    # 获取 Git 信息
    if command -v git &> /dev/null && [ -d "${PROJECT_ROOT}/.git" ]; then
        git_branch=$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
        git_commit=$(git -C "$PROJECT_ROOT" log -1 --format='%h %s' 2>/dev/null | head -c 50 || echo "")
    fi
    
    # 尝试获取任务数
    if command -v copilot &> /dev/null; then
        task_count=$(copilot svc status --name "$SERVICE_NAME" --env "$env" --json 2>/dev/null | \
            jq -r '.tasks | length' 2>/dev/null || echo "0")
    fi
    
    # 尝试获取镜像标签
    local cluster
    cluster=$(aws ecs list-clusters --region "$REGION" \
        --query "clusterArns[?contains(@, '${APP_NAME}-${env}')]" \
        --output text 2>/dev/null | head -1 || echo "")
    
    if [ -n "$cluster" ]; then
        local service
        # 精确匹配 agent-Service
        service=$(aws ecs list-services --cluster "$cluster" --region "$REGION" \
            --output text 2>/dev/null | tr '\t' '\n' | grep 'agent-Service' | head -1 || echo "")
        
        if [ -n "$service" ]; then
            local task_def
            task_def=$(aws ecs describe-services \
                --cluster "$cluster" \
                --services "$service" \
                --region "$REGION" \
                --query 'services[0].taskDefinition' \
                --output text 2>/dev/null || echo "")
            
            if [ -n "$task_def" ]; then
                image_tag=$(aws ecs describe-task-definition \
                    --task-definition "$task_def" \
                    --region "$REGION" \
                    --query 'taskDefinition.containerDefinitions[0].image' \
                    --output text 2>/dev/null | grep -oE '[0-9]{8}-[0-9]{6}$' || echo "unknown")
            fi
        fi
    fi
    
    echo "${service_url}|${image_tag}|${task_count}|${git_branch}|${git_commit}"
}

# 构建通知消息
build_notify_message() {
    local env=$1
    local action=$2
    local status=$3  # success | error
    local duration=$4
    local error_msg="${5:-}"

    local timestamp
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    # 优先使用配置的操作者名称，否则使用系统用户名
    local user="${DEPLOY_USER_NAME:-${USER:-unknown}}"
    
    # 获取服务信息
    local service_info
    service_info=$(get_service_info "$env")
    local service_url
    service_url=$(echo "$service_info" | cut -d'|' -f1)
    local image_tag
    image_tag=$(echo "$service_info" | cut -d'|' -f2)
    local task_count
    task_count=$(echo "$service_info" | cut -d'|' -f3)
    local git_branch
    git_branch=$(echo "$service_info" | cut -d'|' -f4)
    local git_commit
    git_commit=$(echo "$service_info" | cut -d'|' -f5)
    
    # 格式化耗时
    local duration_str=""
    if [ "$duration" -gt 0 ]; then
        local minutes=$((duration / 60))
        local seconds=$((duration % 60))
        if [ "$minutes" -gt 0 ]; then
            duration_str="${minutes}分${seconds}秒"
        else
            duration_str="${seconds}秒"
        fi
    fi
    
    # 环境显示名称
    local env_display
    case "$env" in
        staging) env_display="Staging 环境" ;;
        production) env_display="Production 环境" ;;
        *) env_display="$env" ;;
    esac
    
    # 操作显示名称
    local action_display
    case "$action" in
        deploy) action_display="部署" ;;
        start) action_display="启动" ;;
        stop) action_display="停止" ;;
        *) action_display="$action" ;;
    esac
    
    # 状态图标和文字
    local status_icon status_text
    if [ "$status" = "success" ]; then
        status_icon="✅"
        status_text="成功"
    else
        status_icon="❌"
        status_text="失败"
    fi
    
    # 构建标题
    local title
    if [ "$status" = "success" ]; then
        title="🚀 Zenflux Agent ${env_display} ${action_display}${status_text}"
    else
        title="🔴 Zenflux Agent ${env_display} ${action_display}${status_text}"
    fi
    
    # 构建消息内容（使用实际换行符）
    local content_lines=()
    content_lines+=("## ${title}")
    content_lines+=("")
    content_lines+=("**环境**: ${env_display}")
    content_lines+=("**操作**: ${action_display}")
    content_lines+=("**状态**: ${status_icon} ${status_text}")
    
    if [ -n "$service_url" ]; then
        content_lines+=("**服务URL**: [${service_url}](${service_url})")
    fi
    
    if [ -n "$image_tag" ] && [ "$image_tag" != "unknown" ]; then
        content_lines+=("**镜像版本**: ${image_tag}")
    fi
    
    if [ -n "$git_branch" ]; then
        content_lines+=("**Git分支**: ${git_branch}")
    fi
    
    if [ -n "$git_commit" ]; then
        content_lines+=("**最新提交**: ${git_commit}")
    fi
    
    if [ "$task_count" != "N/A" ] && [ "$task_count" != "0" ]; then
        content_lines+=("**运行任务数**: ${task_count}")
    fi
    
    if [ -n "$duration_str" ]; then
        content_lines+=("**耗时**: ${duration_str}")
    fi
    
    if [ "$status" = "error" ] && [ -n "$error_msg" ]; then
        content_lines+=("**错误信息**: ${error_msg}")
    fi
    
    content_lines+=("**操作者**: ${user}")
    content_lines+=("**时间**: ${timestamp}")
    content_lines+=("")
    content_lines+=("---")
    content_lines+=("*Zenflux Agent*")
    
    # 将数组用换行符连接
    local IFS=$'\n'
    local full_content="${content_lines[*]}"
    
    # 使用 jq 构建 JSON，确保特殊字符正确转义
    jq -n --arg content "$full_content" '{msgtype: "markdown", markdown: {content: $content}}'
}

# 发送企微通知
send_wechat_notify() {
    local env=$1
    local action=$2
    local status=$3
    local duration=${4:-0}
    local error_msg="${5:-}"
    
    if [ -z "$WECHAT_WEBHOOK_URL" ]; then
        log_warning "未配置企微 Webhook，跳过通知"
        return 0
    fi
    
    log_info "发送企微通知..."
    
    local payload
    payload=$(build_notify_message "$env" "$action" "$status" "$duration" "$error_msg")
    
    # 使用 mktemp 创建临时文件，避免多实例冲突
    local tmp_file
    tmp_file=$(mktemp)
    
    local http_code
    http_code=$(curl -s -w "%{http_code}" -o "$tmp_file" -X POST \
        -H 'Content-Type: application/json; charset=utf-8' \
        -d "$payload" \
        "$WECHAT_WEBHOOK_URL")
    
    local body
    body=$(cat "$tmp_file" 2>/dev/null || echo "")
    local errcode
    errcode=$(echo "$body" | jq -r '.errcode // -1' 2>/dev/null || echo "-1")
    
    # 清理临时文件
    rm -f "$tmp_file"
    
    if [ "$http_code" = "200" ] && [ "$errcode" = "0" ]; then
        log_success "通知发送成功"
        return 0
    else
        log_error "通知发送失败 (HTTP: $http_code, errcode: $errcode)"
        return 1
    fi
}

# 发送测试通知
send_test_notify() {
    log_info "发送测试通知..."

    local timestamp
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    # 优先使用配置的操作者名称，否则使用系统用户名
    local user="${DEPLOY_USER_NAME:-${USER:-unknown}}"
    
    # 使用 jq 构建 JSON，确保特殊字符正确转义
    local content="## 🔔 测试通知\n\n**消息**: 企微 Webhook 配置成功\n**操作者**: ${user}\n**时间**: ${timestamp}\n\n---\n*Zenflux Agent*"
    local payload
    payload=$(jq -n --arg content "$content" '{msgtype: "markdown", markdown: {content: $content}}')
    
    # 使用 mktemp 创建临时文件
    local tmp_file
    tmp_file=$(mktemp)
    
    local http_code
    http_code=$(curl -s -w "%{http_code}" -o "$tmp_file" -X POST \
        -H 'Content-Type: application/json; charset=utf-8' \
        -d "$payload" \
        "$WECHAT_WEBHOOK_URL")
    
    local body
    body=$(cat "$tmp_file" 2>/dev/null || echo "")
    local errcode
    errcode=$(echo "$body" | jq -r '.errcode // -1' 2>/dev/null || echo "-1")
    
    # 清理临时文件
    rm -f "$tmp_file"
    
    if [ "$http_code" = "200" ] && [ "$errcode" = "0" ]; then
        log_success "测试通知发送成功，请检查企微群"
        return 0
    else
        log_error "测试通知发送失败"
        return 1
    fi
}

# 询问是否发送通知
ask_send_notify() {
    local env=$1
    local action=$2
    local status=$3
    local duration=$4
    
    # 如果强制指定了通知选项
    if [ "$FORCE_NOTIFY" = "yes" ]; then
        send_wechat_notify "$env" "$action" "$status" "$duration"
        return
    elif [ "$FORCE_NOTIFY" = "no" ]; then
        return 0
    fi
    
    # 如果未配置 Webhook，跳过
    if [ -z "$WECHAT_WEBHOOK_URL" ]; then
        return 0
    fi
    
    echo ""
    read -p "发送企微通知? [y/N]: " notify
    if [[ $notify =~ ^[Yy]$ ]]; then
        send_wechat_notify "$env" "$action" "$status" "$duration"
    fi
}

# ============================================================
# 交互式菜单
# ============================================================

# 环境选择菜单
show_env_menu() {
    echo ""
    echo -e "${BOLD}请选择环境:${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  1) Staging     (测试环境)"
    echo ""
    echo "  c) 配置管理"
    echo "  0) 退出"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    read -p "请选择 [0-1/c]: " choice
    
    case $choice in
        1) SELECTED_ENV="staging" ;;
        c|C) manage_config; return 1 ;;
        0) echo ""; log_info "再见！"; exit 0 ;;
        *) log_error "无效选择"; return 1 ;;
    esac
    
    return 0
}

# 操作选择菜单
show_action_menu() {
    local env=$1
    
    echo ""
    echo -e "${BOLD}环境: ${CYAN}${env}${NC}"
    echo -e "${BOLD}请选择操作:${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  1) deploy    - 部署服务"
    echo "  2) status    - 查看状态"
    echo "  3) logs      - 查看日志"
    echo "  4) start     - 启动环境"
    echo "  5) stop      - 停止环境"
    echo "  6) exec      - 进入容器"
    echo "  7) clean     - 清理资源"
    echo ""
    echo "  0) 返回上级"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    read -p "请选择 [0-7]: " choice
    
    case $choice in
        1) SELECTED_ACTION="deploy" ;;
        2) SELECTED_ACTION="status" ;;
        3) SELECTED_ACTION="logs" ;;
        4) SELECTED_ACTION="start" ;;
        5) SELECTED_ACTION="stop" ;;
        6) SELECTED_ACTION="exec" ;;
        7) SELECTED_ACTION="clean" ;;
        0) return 1 ;;
        *) log_error "无效选择"; return 1 ;;
    esac
    
    return 0
}

# ============================================================
# 执行操作
# ============================================================

# 执行操作
execute_action() {
    local env=$1
    local action=$2
    shift 2
    local extra_args=("$@")
    
    local script="${PROJECT_ROOT}/deploy/aws/${env}/${env}.sh"
    
    if [ ! -f "$script" ]; then
        log_error "脚本不存在: $script"
        return 1
    fi
    
    echo ""
    echo -e "${MAGENTA}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${MAGENTA}执行: ${env} ${action}${NC}"
    echo -e "${MAGENTA}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    
    # 记录开始时间
    START_TIME=$(date +%s)
    
    # 切换到项目根目录执行（确保相对路径正确）
    cd "$PROJECT_ROOT"
    
    # 执行脚本（处理空数组情况，避免 set -u 报错）
    local exit_code=0
    if [ ${#extra_args[@]} -gt 0 ]; then
        if "$script" "$action" "${extra_args[@]}"; then
            exit_code=0
        else
            exit_code=$?
        fi
    else
        if "$script" "$action"; then
            exit_code=0
        else
            exit_code=$?
        fi
    fi
    
    # 记录结束时间
    END_TIME=$(date +%s)
    local duration=$((END_TIME - START_TIME))
    
    echo ""
    
    # 根据结果处理通知
    if [ $exit_code -eq 0 ]; then
        log_success "操作完成 (耗时: ${duration}秒)"
        
        # 对于 deploy/start/stop 操作，询问是否发送通知
        case "$action" in
            deploy|start|stop)
                ask_send_notify "$env" "$action" "success" "$duration"
                ;;
        esac
    else
        log_error "操作失败 (退出码: $exit_code)"
        
        # 失败时自动发送通知（如果配置了 Webhook）
        if [ -n "$WECHAT_WEBHOOK_URL" ] && [ "$FORCE_NOTIFY" != "no" ]; then
            send_wechat_notify "$env" "$action" "error" "$duration" "操作失败，退出码: $exit_code"
        fi
    fi
    
    return $exit_code
}

# ============================================================
# 主函数
# ============================================================

main() {
    # 检查依赖
    check_dependencies
    
    # 加载配置
    load_config
    
    # 无参数时进入交互模式
    if [ $# -eq 0 ]; then
        while true; do
            show_banner
            
            if ! show_env_menu; then
                continue
            fi
            
            while true; do
                if ! show_action_menu "$SELECTED_ENV"; then
                    break
                fi
                
                execute_action "$SELECTED_ENV" "$SELECTED_ACTION"
                
                echo ""
                read -p "按回车键继续..."
            done
        done
        exit 0
    fi
    
    # 解析命令行参数
    local env=""
    local action=""
    local extra_args=()
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --help|-h)
                show_help
                ;;
            --notify)
                FORCE_NOTIFY="yes"
                shift
                ;;
            --no-notify)
                FORCE_NOTIFY="no"
                shift
                ;;
            config)
                shift
                manage_config "$@"
                exit 0
                ;;
            staging)
                env=$1
                shift
                ;;
            deploy|status|logs|start|stop|clean|exec)
                action=$1
                shift
                ;;
            *)
                extra_args+=("$1")
                shift
                ;;
        esac
    done
    
    # 验证参数
    if [ -z "$env" ]; then
        log_error "未指定环境"
        echo "用法: ./deploy.sh <staging> <操作>"
        exit 1
    fi
    
    if [ -z "$action" ]; then
        log_error "未指定操作"
        echo "用法: ./deploy.sh $env <deploy|status|logs|start|stop|clean|exec>"
        exit 1
    fi
    
    # 执行操作
    execute_action "$env" "$action" "${extra_args[@]}"
}

main "$@"
