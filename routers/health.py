"""
健康检查路由

提供服务健康状态探针
"""

from fastapi import APIRouter, Response, status
from typing import Dict, Any
import time
import asyncio
import psutil

from logger import get_logger
from infra.resilience.circuit_breaker import get_all_circuit_breakers
from infra.cache import get_redis_client
from infra.resilience.circuit_breaker import get_circuit_breaker
from infra.database import AsyncSessionLocal

logger = get_logger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", summary="存活探针")
async def liveness_probe():
    """
    存活探针（Liveness Probe）
    
    用于：Kubernetes/Docker 健康检查
    返回：服务进程是否存活
    """
    return {
        "status": "alive",
        "timestamp": time.time()
    }


@router.get("/ready", summary="就绪探针")
async def readiness_probe(response: Response):
    """
    就绪探针（Readiness Probe）
    
    用于：负载均衡器判断是否接收流量
    检查：依赖服务（LLM/Redis/DB）是否就绪
    
    Returns:
        200: 服务就绪
        503: 服务未就绪
    """
    checks = {}
    all_ready = True
    
    # 1. 检查 Redis 连接
    try:
        redis_client = get_redis_client()
        await asyncio.wait_for(redis_client.ping(), timeout=2.0)
        checks["redis"] = {"status": "healthy"}
    except Exception as e:
        checks["redis"] = {"status": "unhealthy", "error": str(e)}
        all_ready = False
    
    # 2. 检查数据库连接
    try:
        async with AsyncSessionLocal() as session:
            await asyncio.wait_for(session.execute("SELECT 1"), timeout=2.0)
        checks["database"] = {"status": "healthy"}
    except Exception as e:
        checks["database"] = {"status": "unhealthy", "error": str(e)}
        all_ready = False
    
    # 3. 检查 LLM 服务（可选，避免每次探针都调用）
    # 改为检查熔断器状态
    try:
        llm_breaker = get_circuit_breaker("llm_service")
        if llm_breaker.is_open:
            checks["llm"] = {"status": "degraded", "reason": "circuit_breaker_open"}
            all_ready = False
        else:
            checks["llm"] = {"status": "healthy"}
    except Exception as e:
        checks["llm"] = {"status": "unknown", "error": str(e)}
    
    # 设置响应状态码
    if not all_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    
    return {
        "status": "ready" if all_ready else "not_ready",
        "checks": checks,
        "timestamp": time.time()
    }


@router.get("/metrics", summary="健康指标")
async def health_metrics() -> Dict[str, Any]:
    """
    健康指标
    
    返回：
    - 熔断器状态
    - 服务调用统计
    - 系统资源使用
    """
    metrics = {}
    
    # 1. 熔断器状态
    circuit_breakers = get_all_circuit_breakers()
    metrics["circuit_breakers"] = {
        name: breaker.get_stats()
        for name, breaker in circuit_breakers.items()
    }
    
    # 2. 系统资源（可选）
    try:
        process = psutil.Process()
        metrics["system"] = {
            "cpu_percent": process.cpu_percent(),
            "memory_mb": process.memory_info().rss / 1024 / 1024,
            "threads": process.num_threads(),
        }
    except ImportError:
        metrics["system"] = {"available": False}
    
    return {
        "status": "ok",
        "metrics": metrics,
        "timestamp": time.time()
    }
