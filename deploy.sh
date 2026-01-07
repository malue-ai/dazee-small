#!/bin/bash
# ============================================================
# Zenflux Agent 快速部署脚本
# ============================================================

set -e  # 遇到错误立即退出

echo "🚀 Zenflux Agent Docker 部署脚本"
echo "================================"
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 检查 Docker
echo "📦 检查 Docker..."
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker 未安装！${NC}"
    echo "请先安装 Docker: https://docs.docker.com/get-docker/"
    exit 1
fi
echo -e "${GREEN}✅ Docker 已安装: $(docker --version)${NC}"

# 检查 Docker Compose
echo "📦 检查 Docker Compose..."
if ! command -v docker compose &> /dev/null; then
    echo -e "${RED}❌ Docker Compose 未安装！${NC}"
    echo "请先安装 Docker Compose"
    exit 1
fi
echo -e "${GREEN}✅ Docker Compose 已安装: $(docker compose version)${NC}"

# 检查 .env 文件
echo ""
echo "🔐 检查环境变量配置..."
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠️  未找到 .env 文件${NC}"
    
    if [ -f env.template ]; then
        echo "📋 复制 env.template 为 .env..."
        cp env.template .env
        echo -e "${GREEN}✅ .env 文件已创建${NC}"
        echo ""
        echo -e "${RED}⚠️  重要：请编辑 .env 文件，填入你的 API Keys！${NC}"
        echo ""
        echo "必须配置的变量："
        echo "  - ANTHROPIC_API_KEY=sk-ant-xxxxx"
        echo "  - E2B_API_KEY=e2b_xxxxx"
        echo ""
        read -p "是否现在编辑 .env 文件？(y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            ${EDITOR:-vi} .env
        else
            echo -e "${YELLOW}请手动编辑 .env 文件后再运行此脚本${NC}"
            exit 1
        fi
    else
        echo -e "${RED}❌ 未找到 env.template 文件${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✅ .env 文件已存在${NC}"
fi

# 检查必需的环境变量
echo ""
echo "🔍 验证环境变量..."
source .env

if [ -z "$ANTHROPIC_API_KEY" ] || [ "$ANTHROPIC_API_KEY" = "sk-ant-xxxxx" ]; then
    echo -e "${RED}❌ ANTHROPIC_API_KEY 未配置或使用默认值${NC}"
    echo "请在 .env 文件中设置有效的 Claude API Key"
    exit 1
fi

if [ -z "$E2B_API_KEY" ] || [ "$E2B_API_KEY" = "e2b_xxxxx" ]; then
    echo -e "${RED}❌ E2B_API_KEY 未配置或使用默认值${NC}"
    echo "请在 .env 文件中设置有效的 E2B API Key"
    exit 1
fi

echo -e "${GREEN}✅ 环境变量配置有效${NC}"

# 创建必要的目录
echo ""
echo "📁 创建工作目录..."
mkdir -p workspace/database
mkdir -p workspace/knowledge
mkdir -p workspace/memory
mkdir -p workspace/outputs
mkdir -p workspace/inputs
mkdir -p logs
echo -e "${GREEN}✅ 工作目录创建完成${NC}"

# 询问是否构建
echo ""
echo "🏗️  准备构建 Docker 镜像..."
read -p "是否重新构建镜像？(y/n) [默认: y] " -n 1 -r
echo
BUILD_FLAG=""
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    BUILD_FLAG="--build"
    echo "将重新构建镜像..."
else
    echo "跳过构建，使用已有镜像..."
fi

# 停止旧容器
echo ""
echo "🛑 停止旧容器..."
docker compose down

# 启动服务
echo ""
echo "🚀 启动服务..."
docker compose up -d $BUILD_FLAG

# 等待服务启动
echo ""
echo "⏳ 等待服务启动..."
sleep 10

# 检查服务状态
echo ""
echo "📊 检查服务状态..."
docker compose ps

# 健康检查
echo ""
echo "🏥 健康检查..."

echo -n "检查后端... "
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ 后端运行正常${NC}"
else
    echo -e "${RED}❌ 后端未响应${NC}"
    echo "查看日志: docker compose logs backend"
fi

echo -n "检查前端... "
if curl -s http://localhost:3000 > /dev/null 2>&1; then
    echo -e "${GREEN}✅ 前端运行正常${NC}"
else
    echo -e "${YELLOW}⚠️  前端未响应（可能还在构建中）${NC}"
fi

# 显示日志
echo ""
read -p "是否查看实时日志？(y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    docker compose logs -f
fi

# 完成信息
echo ""
echo "================================"
echo -e "${GREEN}🎉 部署完成！${NC}"
echo "================================"
echo ""
echo "📍 访问地址："
echo "  - 前端: http://localhost:3000"
echo "  - 后端: http://localhost:8000"
echo "  - API 文档: http://localhost:8000/docs"
echo ""
echo "📝 常用命令："
echo "  - 查看日志: docker compose logs -f"
echo "  - 查看状态: docker compose ps"
echo "  - 停止服务: docker compose down"
echo "  - 重启服务: docker compose restart"
echo ""
echo "📖 详细文档: DOCKER_DEPLOYMENT.md"
echo ""

