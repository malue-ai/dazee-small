#!/usr/bin/env bash
# ============================================================
# SSL 证书申请和验证脚本
# ============================================================

set -euo pipefail

REGION="${AWS_REGION:-ap-southeast-1}"
DOMAIN_NAME="${CUSTOM_DOMAIN:-}"  # 可选，通过环境变量设置

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
log_success() { echo -e "${GREEN}✅ $1${NC}"; }
log_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error() { echo -e "${RED}❌ $1${NC}"; }

# ============================================================
# 申请证书
# ============================================================

request_certificate() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📋 申请 SSL 证书"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    if [ -z "$DOMAIN_NAME" ]; then
        log_error "未配置域名"
        log_info "请使用环境变量设置域名:"
        log_info "  export CUSTOM_DOMAIN=your-domain.com"
        log_info "  $0 request"
        exit 1
    fi
    
    log_info "域名: $DOMAIN_NAME"
    log_info "区域: $REGION"
    echo ""
    
    # 检查证书是否已存在
    local existing_cert=$(aws acm list-certificates \
        --region "$REGION" \
        --query "CertificateSummaryList[?DomainName=='${DOMAIN_NAME}'].CertificateArn" \
        --output text 2>/dev/null || echo "")
    
    if [ -n "$existing_cert" ]; then
        log_warning "证书已存在: $existing_cert"
        log_info "查看状态: $0 status"
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
    
    # 等待 DNS 验证记录生成
    log_info "等待 DNS 验证记录生成（约 10 秒）..."
    sleep 10
    
    # 获取 DNS 验证记录
    log_warning "⚠️  重要：需要完成 DNS 验证"
    echo ""
    echo "请在您的 DNS 提供商添加以下 CNAME 记录:"
    echo ""
    
    aws acm describe-certificate \
        --certificate-arn "$cert_arn" \
        --region "$REGION" \
        --query 'Certificate.DomainValidationOptions[0].ResourceRecord' \
        --output table
    
    echo ""
    log_info "添加 DNS 记录后，等待验证完成（通常 5-30 分钟）"
    log_info "查看状态: $0 status"
    echo ""
}

# ============================================================
# 检查证书状态
# ============================================================

check_status() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📋 检查 SSL 证书状态"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    if [ -z "$DOMAIN_NAME" ]; then
        log_warning "未配置域名，当前使用 HTTP 模式"
        log_info "如需 HTTPS，请设置域名: export CUSTOM_DOMAIN=your-domain.com"
        exit 0
    fi
    
    local cert_arn=$(aws acm list-certificates \
        --region "$REGION" \
        --query "CertificateSummaryList[?DomainName=='${DOMAIN_NAME}'].CertificateArn" \
        --output text 2>/dev/null || echo "")
    
    if [ -z "$cert_arn" ]; then
        log_warning "未找到证书"
        log_info "申请证书: $0 request"
        exit 1
    fi
    
    log_info "证书 ARN: $cert_arn"
    echo ""
    
    # 获取证书详情
    local cert_info=$(aws acm describe-certificate \
        --certificate-arn "$cert_arn" \
        --region "$REGION" \
        --output json)
    
    local status=$(echo "$cert_info" | jq -r '.Certificate.Status')
    local domain=$(echo "$cert_info" | jq -r '.Certificate.DomainName')
    
    echo "证书信息:"
    echo "  域名: $domain"
    echo "  状态: $status"
    echo ""
    
    if [ "$status" = "ISSUED" ]; then
        log_success "✅ 证书已签发，可以部署"
        echo ""
        echo "下一步:"
        echo "  ./deploy/aws/staging/staging.sh deploy"
        echo ""
        return 0
    elif [ "$status" = "PENDING_VALIDATION" ]; then
        log_warning "⏳ 等待 DNS 验证"
        echo ""
        echo "DNS 验证记录:"
        echo "$cert_info" | jq -r '.Certificate.DomainValidationOptions[0].ResourceRecord | 
            "  类型: \(.Type)\n  名称: \(.Name)\n  值: \(.Value)"'
        echo ""
        log_info "请确保已在 DNS 提供商添加上述 CNAME 记录"
        log_info "验证通常需要 5-30 分钟"
        echo ""
        return 1
    else
        log_error "证书状态异常: $status"
        return 1
    fi
}

# ============================================================
# 主函数
# ============================================================

main() {
    case "${1:-}" in
        request)
            request_certificate
            ;;
        status)
            check_status
            ;;
        *)
            echo "用法: $0 {request|status}"
            echo ""
            echo "命令:"
            echo "  request  - 申请 SSL 证书"
            echo "  status   - 查看证书状态"
            echo ""
            echo "示例:"
            echo "  $0 request"
            echo "  $0 status"
            exit 1
            ;;
    esac
}

main "$@"
