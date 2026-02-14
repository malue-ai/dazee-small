# ============================================================
# xiaodazi - Multi-stage Docker Build
# ============================================================
#
# Stage 1: Build frontend (Vue 3 + Vite)
# Stage 2: Run backend (FastAPI + uvicorn) + serve frontend via Nginx
#
# Usage:
#   docker build -t xiaodazi .
#   docker run -p 8000:8000 --env-file .env xiaodazi
#
# ============================================================

# ==================== Stage 1: Frontend Build ====================
FROM node:20-alpine AS frontend-builder

WORKDIR /build/frontend

# Install dependencies first (layer cache)
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund

# Copy frontend source and build
COPY frontend/ ./
RUN npm run build


# ==================== Stage 2: Backend Runtime ====================
FROM python:3.11-slim AS runtime

# System dependencies for:
# - build-essential: compile native Python packages (llama-cpp-python, etc.)
# - curl: health check
# - libsqlite3-dev: SQLite extensions (FTS5, sqlite-vec)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (layer cache)
COPY requirements.txt ./

# Install dependencies; skip macOS-only packages
RUN pip install --no-cache-dir -r requirements.txt \
    --ignore-installed \
    2>&1 | grep -v "pyobjc" || true

# Copy backend source
COPY . .

# Copy frontend build output
COPY --from=frontend-builder /build/frontend/dist /app/frontend/dist

# Create data directory for SQLite, memory, uploads, etc.
RUN mkdir -p /app/data

# ==================== Environment ====================
# Data persistence
ENV XIAODAZI_DATA_DIR=/app/data

# Default instance
ENV AGENT_INSTANCE=xiaodazi

# Server config
ENV HOST=0.0.0.0
ENV PORT=8000

# Disable schedulers by default in container (enable via docker-compose)
ENV ENABLE_SCHEDULER=true
ENV ENABLE_USER_TASK_SCHEDULER=true

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start FastAPI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
