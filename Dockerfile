# ============================================================
# Zenflux Agent 后端 Dockerfile
# Python 3.12 + FastAPI
# ============================================================

# 使用官方 Docker Hub 镜像
FROM python:3.12-slim

# 设置环境变量，避免 Python 缓冲问题
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 设置工作目录
WORKDIR /app

# 先只复制依赖文件（利用 Docker 缓存）
COPY requirements.txt .

# 安装 Python 依赖（不需要编译器的纯 Python 包）
RUN pip install --no-cache-dir -r requirements.txt

# 注意：我们使用 filetype（纯 Python），不需要安装系统依赖

# 复制项目代码
COPY . .

# 创建必要的目录
RUN mkdir -p workspace/database workspace/knowledge workspace/memory workspace/outputs workspace/inputs logs

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5)"

# 启动命令
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
