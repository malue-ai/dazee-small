#!/bin/bash
# ============================================================
# Zenflux Agent 一键部署脚本
# ============================================================

set -e

echo "🚀 Zenflux Agent 部署"
echo "================================"
echo ""

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker 未安装${NC}"
    exit 1
fi

# 检查 .env
if [ ! -f .env ]; then
    echo -e "${YELLOW}创建 .env 文件...${NC}"
    cp env.template .env
    echo -e "${RED}请编辑 .env 填入 API Keys:${NC}"
    echo "  - ANTHROPIC_API_KEY"
    echo "  - E2B_API_KEY"
    echo ""
    echo "然后重新运行: ./deploy.sh"
    exit 1
fi

# 验证配置
source .env
if [ -z "$ANTHROPIC_API_KEY" ] || [ "$ANTHROPIC_API_KEY" = "sk-ant-xxxxx" ]; then
    echo -e "${RED}❌ ANTHROPIC_API_KEY 未配置${NC}"
    exit 1
fi

if [ -z "$E2B_API_KEY" ] || [ "$E2B_API_KEY" = "e2b_xxxxx" ]; then
    echo -e "${RED}❌ E2B_API_KEY 未配置${NC}"
    exit 1
fi

# 创建目录
mkdir -p workspace/database logs

# 停止旧容器
echo "🛑 停止旧容器..."
docker compose down 2>/dev/null || true

# 构建
echo ""
echo "🏗️  构建镜像..."
docker compose build --no-cache

# 启动
echo ""
echo "🚀 启动服务..."
docker compose up -d

# 等待
echo ""
echo "⏳ 等待启动..."
sleep 15

# 获取本机 IP
get_local_ip() {
    # macOS
    if command -v ipconfig &> /dev/null; then
        ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "127.0.0.1"
    # Linux
    elif command -v hostname &> /dev/null; then
        hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1"
    else
        echo "127.0.0.1"
    fi
}

LOCAL_IP=$(get_local_ip)

# 检查
echo ""
if docker compose ps | grep -q "Up"; then
    echo -e "${GREEN}✅ 部署成功！${NC}"
    echo ""
    echo "📍 访问地址："
    echo "  🖥️  本机访问:"
    echo "     - API: http://localhost:8010"
    echo "     - 文档: http://localhost:8010/docs"
    echo ""
    echo "  🌐 局域网访问:"
    echo "     - API: http://${LOCAL_IP}:8010"
    echo "     - 文档: http://${LOCAL_IP}:8010/docs"
    echo ""
    echo "  💡 提示: 局域网内其他设备可以通过 ${LOCAL_IP} 访问"
    echo ""
    echo "📝 常用命令："
    echo "  - 查看日志: docker compose logs -f backend"
    echo "  - 查看状态: docker compose ps"
    echo "  - 停止服务: docker compose down"
    echo "  - 重启服务: docker compose restart backend"
    echo "  - 进入容器: docker compose exec backend bash"
    echo ""
else
    echo -e "${RED}❌ 启动失败${NC}"
    echo "查看日志: docker compose logs backend"
    exit 1
fi
