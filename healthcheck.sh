#!/bin/sh
# 健康检查脚本 - 检查 Nginx 和 FastAPI 是否正常运行

set -e

# 检查 Nginx
if ! pgrep -x nginx > /dev/null; then
    echo "Nginx is not running"
    exit 1
fi

# 检查 FastAPI
if ! curl -f -s --max-time 5 http://localhost:8000/health > /dev/null 2>&1; then
    echo "FastAPI health check failed"
    exit 1
fi

# 检查前端（通过 Nginx）
if ! curl -f -s --max-time 5 http://localhost/health > /dev/null 2>&1; then
    echo "Frontend health check failed"
    exit 1
fi

echo "Health check passed"
exit 0
