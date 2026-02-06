"""
健康检查路由

提供服务健康状态探针
"""

import time
from typing import Any, Dict

import psutil
from fastapi import APIRouter

from infra.resilience.circuit_breaker import get_all_circuit_breakers, get_circuit_breaker
from logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", summary="健康检查")
async def health_root() -> Dict[str, Any]:
    """
    健康检查入口

    Returns:
        简单存活状态
    """
    return {"status": "ok", "timestamp": time.time()}


@router.get("/live", summary="存活探针")
async def liveness_probe():
    """
    存活探针（Liveness Probe）

    用于：Kubernetes/Docker 健康检查
    返回：服务进程是否存活
    """
    return {"status": "alive", "timestamp": time.time()}


@router.get("/metrics", summary="健康指标")
async def health_metrics() -> Dict[str, Any]:
    """
    健康指标

    返回：
    - 熔断器状态
    - 系统资源使用
    """
    metrics = {}

    # 1. 熔断器状态
    circuit_breakers = get_all_circuit_breakers()
    metrics["circuit_breakers"] = {
        name: breaker.get_stats() for name, breaker in circuit_breakers.items()
    }

    # 2. 系统资源
    try:
        process = psutil.Process()
        metrics["system"] = {
            "cpu_percent": process.cpu_percent(),
            "memory_mb": process.memory_info().rss / 1024 / 1024,
            "threads": process.num_threads(),
        }
    except ImportError:
        metrics["system"] = {"available": False}

    return {"status": "ok", "metrics": metrics, "timestamp": time.time()}
