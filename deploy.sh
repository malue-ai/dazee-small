#!/bin/bash
# ============================================================
# Zenflux Agent 一键部署脚本
# 兼容 Docker Compose V1 和 V2
# ============================================================

set -e

echo "🚀 Zenflux Agent 部署"
echo "================================"
echo ""

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 检测 Docker Compose 命令
detect_compose() {
    if docker compose version &> /dev/null; then
        echo "docker compose"
    elif command -v docker-compose &> /dev/null; then
        echo "docker-compose"
    else
        echo ""
    fi
}

COMPOSE_CMD=$(detect_compose)

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker 未安装${NC}"
    exit 1
fi

# 检查 Docker Compose
if [ -z "$COMPOSE_CMD" ]; then
    echo -e "${RED}❌ Docker Compose 未安装${NC}"
    echo "请安装 docker-compose: sudo apt install docker-compose"
    exit 1
fi

echo -e "${GREEN}✓ 使用: $COMPOSE_CMD${NC}"

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
$COMPOSE_CMD down 2>/dev/null || true

# 构建
echo ""
echo "🏗️  构建镜像..."
# 旧版 docker-compose 可能不支持 --no-cache，单独处理
if [ "$COMPOSE_CMD" = "docker-compose" ]; then
    # 旧版：先用 docker build，再 compose up
    docker build -t zenflux-backend:latest .
else
    # 新版：直接使用 compose build
    $COMPOSE_CMD build --no-cache 2>/dev/null || $COMPOSE_CMD build
fi

# 启动
echo ""
echo "🚀 启动服务..."
$COMPOSE_CMD up -d

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
if $COMPOSE_CMD ps | grep -q "Up\|running"; then
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
    echo "  - 查看日志: $COMPOSE_CMD logs -f backend"
    echo "  - 查看状态: $COMPOSE_CMD ps"
    echo "  - 停止服务: $COMPOSE_CMD down"
    echo "  - 重启服务: $COMPOSE_CMD restart backend"
    echo "  - 进入容器: $COMPOSE_CMD exec backend bash"
    echo ""
else
    echo -e "${RED}❌ 启动失败${NC}"
    echo "查看日志: $COMPOSE_CMD logs backend"
    exit 1
fi
