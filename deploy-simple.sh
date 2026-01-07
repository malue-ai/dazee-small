#!/bin/bash
# ============================================================
# Zenflux Agent 精简版部署脚本
# 只部署后端 + Redis，使用 SQLite
# ============================================================

set -e

echo "🚀 Zenflux Agent 精简版部署"
echo "================================"
echo "✅ 使用 SQLite（无需 PostgreSQL）"
echo "✅ 包含 Redis（支持 SSE）"
echo "✅ 监听 0.0.0.0（外网可访问）"
echo ""

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# 检查 Docker
echo "📦 检查 Docker..."
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker 未安装！${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Docker: $(docker --version)${NC}"

# 检查 .env 文件
echo ""
echo "🔐 检查配置..."
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠️  未找到 .env 文件，创建中...${NC}"
    cp env.template .env
    echo -e "${RED}请编辑 .env 文件，填入 API Keys！${NC}"
    exit 1
fi

# 验证必需的环境变量
source .env
if [ -z "$ANTHROPIC_API_KEY" ] || [ "$ANTHROPIC_API_KEY" = "sk-ant-xxxxx" ]; then
    echo -e "${RED}❌ ANTHROPIC_API_KEY 未配置${NC}"
    exit 1
fi

if [ -z "$E2B_API_KEY" ] || [ "$E2B_API_KEY" = "e2b_xxxxx" ]; then
    echo -e "${RED}❌ E2B_API_KEY 未配置${NC}"
    exit 1
fi

echo -e "${GREEN}✅ 配置有效${NC}"

# 创建目录
echo ""
echo "📁 创建工作目录..."
mkdir -p workspace/database workspace/knowledge workspace/memory workspace/outputs workspace/inputs logs
echo -e "${GREEN}✅ 完成${NC}"

# 停止旧容器
echo ""
echo "🛑 停止旧容器..."
docker compose -f docker-compose.simple.yml down 2>/dev/null || true

# 启动服务
echo ""
echo "🚀 启动服务..."
read -p "是否重新构建镜像？(y/n) [默认: n] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "正在构建镜像..."
    docker compose -f docker-compose.simple.yml build
fi

echo "正在启动容器..."
docker compose -f docker-compose.simple.yml up -d

# 等待启动
echo ""
echo "⏳ 等待服务启动..."
sleep 10

# 检查状态
echo ""
echo "📊 服务状态："
docker compose -f docker-compose.simple.yml ps

# 健康检查
echo ""
echo "🏥 健康检查..."
sleep 5

if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ 后端运行正常${NC}"
    echo ""
    echo "================================"
    echo -e "${GREEN}🎉 部署成功！${NC}"
    echo "================================"
    echo ""
    echo "📍 访问地址："
    echo "  - 本地: http://localhost:8000"
    echo "  - 外网: http://your-ip:8000"
    echo "  - API 文档: http://localhost:8000/docs"
    echo ""
    echo "📝 常用命令："
    echo "  - 查看日志: docker compose -f docker-compose.simple.yml logs -f"
    echo "  - 停止服务: docker compose -f docker-compose.simple.yml down"
    echo "  - 重启服务: docker compose -f docker-compose.simple.yml restart"
    echo ""
else
    echo -e "${RED}❌ 后端未响应${NC}"
    echo "查看日志："
    docker compose -f docker-compose.simple.yml logs backend
    exit 1
fi

# 询问是否查看日志
read -p "是否查看实时日志？(y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    docker compose -f docker-compose.simple.yml logs -f
fi

