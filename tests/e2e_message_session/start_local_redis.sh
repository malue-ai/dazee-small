#!/bin/bash
# 启动本地 Redis 服务（用于测试）
#
# 使用方法：
#   bash tests/e2e_message_session/start_local_redis.sh
#
# 或者使用 Docker：
#   docker run -d --name redis-test -p 6379:6379 redis:7-alpine

echo "🚀 启动本地 Redis 服务..."

# 检查是否已安装 Redis
if command -v redis-server &> /dev/null; then
    echo "✅ 发现 Redis 已安装"
    # 检查是否已在运行
    if redis-cli ping &> /dev/null 2>&1; then
        echo "✅ Redis 已在运行"
        exit 0
    fi
    # 启动 Redis
    echo "📦 启动 Redis 服务器..."
    redis-server --daemonize yes --port 6379
    sleep 2
    if redis-cli ping &> /dev/null 2>&1; then
        echo "✅ Redis 启动成功"
        exit 0
    else
        echo "❌ Redis 启动失败"
        exit 1
    fi
fi

# 检查 Docker
if command -v docker &> /dev/null; then
    echo "🐳 使用 Docker 启动 Redis..."
    
    # 检查容器是否已存在
    if docker ps -a | grep -q redis-test; then
        echo "📦 发现已有 Redis 容器，启动中..."
        docker start redis-test
    else
        echo "📦 创建新的 Redis 容器..."
        docker run -d \
            --name redis-test \
            -p 6379:6379 \
            redis:7-alpine \
            redis-server --appendonly yes
    fi
    
    sleep 2
    
    # 测试连接
    if docker exec redis-test redis-cli ping &> /dev/null 2>&1; then
        echo "✅ Redis 容器启动成功"
        echo "📍 Redis 运行在: localhost:6379"
        exit 0
    else
        echo "❌ Redis 容器启动失败"
        exit 1
    fi
fi

echo "❌ 未找到 Redis 或 Docker，请手动安装："
echo "   1. macOS: brew install redis && brew services start redis"
echo "   2. 或使用 Docker: docker run -d -p 6379:6379 redis:7-alpine"
exit 1
