#!/usr/bin/env bash
# ============================================================
# Production 环境 IAM 权限设置脚本
# ============================================================
# 功能：为 Production 环境的 ECS 任务执行角色配置 SSM Parameter Store 访问权限
# 
# 用法：
#   ./scripts/setup_production_iam.sh
#
# 说明：
#   此脚本会自动查找 zen0-backend-production-agent-ExecutionRole
#   并为其添加访问 SSM Parameter Store 的权限
#   这是部署 Production 服务的前置条件
# ============================================================

set -euo pipefail

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 日志函数
log_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
log_success() { echo -e "${GREEN}✅ $1${NC}"; }
log_error() { echo -e "${RED}❌ $1${NC}"; }
log_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }

# 配置
REGION="${AWS_REGION:-ap-southeast-1}"
ACCOUNT_ID="308470327605"
APP_NAME="zen0-backend"
ENV_NAME="production"
SERVICE_NAME="agent"

log_info "Production IAM 权限设置脚本"
log_info "区域: $REGION"
log_info "应用: $APP_NAME"
log_info "环境: $ENV_NAME"
log_info "服务: $SERVICE_NAME"
echo ""

# ============================================================
# 步骤 1: 查找 TaskExecutionRole
# ============================================================
log_info "步骤 1/3: 查找 TaskExecutionRole..."

ROLE_NAME="${APP_NAME}-${ENV_NAME}-${SERVICE_NAME}-ExecutionRole"

# 尝试查找完整的角色名（含随机后缀）
FULL_ROLE_NAME=$(aws iam list-roles \
    --query "Roles[?starts_with(RoleName, '${ROLE_NAME}')].RoleName" \
    --output text \
    --region "$REGION" 2>/dev/null || echo "")

if [ -z "$FULL_ROLE_NAME" ]; then
    log_warning "未找到执行角色: $ROLE_NAME"
    log_info "可能原因："
    log_info "  1. 环境/服务还未创建 (需要先运行 copilot 部署)"
    log_info "  2. 权限不足，无法查看 IAM 角色"
    log_info ""
    log_info "快速解决方案："
    log_info "  - 继续部署，部署失败后会创建角色"
    log_info "  - 部署失败后再次运行此脚本添加权限"
    exit 0
fi

log_success "找到角色: $FULL_ROLE_NAME"
echo ""

# ============================================================
# 步骤 2: 检查现有权限
# ============================================================
log_info "步骤 2/3: 检查现有 IAM 策略..."

EXISTING_POLICIES=$(aws iam list-role-policies \
    --role-name "$FULL_ROLE_NAME" \
    --query "PolicyNames" \
    --output text \
    --region "$REGION")

if echo "$EXISTING_POLICIES" | grep -q "SSMParameterStoreAccess"; then
    log_success "SSMParameterStoreAccess 策略已存在"
    exit 0
fi

log_info "当前策略: ${EXISTING_POLICIES:-无}"
echo ""

# ============================================================
# 步骤 3: 添加权限
# ============================================================
log_info "步骤 3/3: 添加 SSM Parameter Store 访问权限..."

# 创建 IAM 策略文档
POLICY_DOCUMENT="{
  \"Version\": \"2012-10-17\",
  \"Statement\": [
    {
      \"Sid\": \"SSMParameterStoreAccess\",
      \"Effect\": \"Allow\",
      \"Action\": [
        \"ssm:GetParameters\",
        \"ssm:GetParameter\"
      ],
      \"Resource\": [
        \"arn:aws:ssm:${REGION}:${ACCOUNT_ID}:parameter/copilot/${APP_NAME}/staging/secrets/*\",
        \"arn:aws:ssm:${REGION}:${ACCOUNT_ID}:parameter/copilot/${APP_NAME}/${ENV_NAME}/secrets/*\"
      ]
    },
    {
      \"Sid\": \"KMSDecryptAccess\",
      \"Effect\": \"Allow\",
      \"Action\": [
        \"kms:Decrypt\"
      ],
      \"Resource\": \"arn:aws:kms:${REGION}:${ACCOUNT_ID}:key/*\"
    }
  ]
}"

if aws iam put-role-policy \
    --role-name "$FULL_ROLE_NAME" \
    --policy-name "SSMParameterStoreAccess" \
    --policy-document "$POLICY_DOCUMENT" \
    --region "$REGION"; then
    log_success "权限添加成功"
    echo ""
    log_success "TaskExecutionRole 现在拥有以下权限："
    log_info "  ✓ ssm:GetParameters"
    log_info "  ✓ ssm:GetParameter"
    log_info "  ✓ kms:Decrypt"
    echo ""
    log_success "可以继续部署 Production 服务"
else
    log_error "权限添加失败"
    exit 1
fi
