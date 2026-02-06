"""
健康检查路由

提供服务健康状态探针
"""

import asyncio
import time
from typing import Any, Dict

import psutil
from fastapi import APIRouter, Response, status
from sqlalchemy import text

from infra.cache import get_redis_client
from infra.database import AsyncSessionLocal
from infra.pools import get_mcp_pool, get_session_pool
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
        redis_client = await get_redis_client()  # get_redis_client 是异步函数
        ping_result = await asyncio.wait_for(redis_client.ping(), timeout=2.0)
        checks["redis"] = {"status": "healthy" if ping_result else "unhealthy"}
    except Exception as e:
        checks["redis"] = {"status": "unhealthy", "error": str(e)}
        all_ready = False

    # 2. 检查数据库连接
    try:
        async with AsyncSessionLocal() as session:
            await asyncio.wait_for(session.execute(text("SELECT 1")), timeout=2.0)
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
        "timestamp": time.time(),
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
        name: breaker.get_stats() for name, breaker in circuit_breakers.items()
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

    return {"status": "ok", "metrics": metrics, "timestamp": time.time()}


@router.get("/pools", summary="资源池状态")
async def pool_stats() -> Dict[str, Any]:
    """
    资源池状态

    返回：
    - SessionPool 统计
    - MCPPool 统计（连接状态、工具数量、调用统计）
    """
    pools = {}

    # 1. SessionPool 统计
    try:
        session_pool = get_session_pool()
        pools["session_pool"] = await session_pool.get_system_stats()
    except Exception as e:
        pools["session_pool"] = {"error": str(e)}

    # 2. MCPPool 统计
    try:
        mcp_pool = get_mcp_pool()
        pools["mcp_pool"] = await mcp_pool.get_stats()
    except Exception as e:
        pools["mcp_pool"] = {"error": str(e)}

    return {"status": "ok", "pools": pools, "timestamp": time.time()}


@router.get("/mcp", summary="MCP 池详细状态")
async def mcp_pool_stats() -> Dict[str, Any]:
    """
    MCP 客户端池详细状态

    返回：
    - 已连接的 MCP 服务器列表
    - 每个服务器的连接状态
    - 工具数量
    - 调用统计（缓存命中、重连次数等）
    """
    try:
        mcp_pool = get_mcp_pool()
        stats = await mcp_pool.get_stats()

        return {"status": "ok", "mcp": stats, "timestamp": time.time()}
    except Exception as e:
        logger.error(f"获取 MCP 池统计失败: {e}", exc_info=True)
        return {"status": "error", "error": str(e), "timestamp": time.time()}


# ==================== 管理员 API ====================


@router.post("/admin/calibrate", summary="校准 Session 数据")
async def calibrate_sessions(deep: bool = False) -> Dict[str, Any]:
    """
    校准 Session 数据（管理员接口）

    清理孤立的 Session 记录，解决因服务重启或异常退出导致的数据不一致问题。

    Args:
        deep: 是否进行深度校准（同时清理用户级别的孤立记录）

    Returns:
        校准结果（清理数量等）
    """
    try:
        session_pool = get_session_pool()
        result = await session_pool.calibrate(deep=deep)

        return {"status": "ok", "result": result, "timestamp": time.time()}
    except Exception as e:
        logger.error(f"校准失败: {e}", exc_info=True)
        return {"status": "error", "error": str(e), "timestamp": time.time()}


@router.delete("/admin/user/{user_id}/sessions", summary="清理用户 Session")
async def clear_user_sessions(user_id: str) -> Dict[str, Any]:
    """
    清理指定用户的所有活跃 Session（管理员接口）

    用于手动清理用户的僵尸 Session 记录。

    ⚠️ 警告：这会强制结束用户的所有活跃会话！

    Args:
        user_id: 用户 ID

    Returns:
        清理结果
    """
    try:
        session_pool = get_session_pool()
        cleaned_count = await session_pool.clear_user_sessions(user_id)

        return {
            "status": "ok",
            "user_id": user_id,
            "sessions_cleared": cleaned_count,
            "timestamp": time.time(),
        }
    except Exception as e:
        logger.error(f"清理用户 Session 失败: {e}", exc_info=True)
        return {"status": "error", "error": str(e), "timestamp": time.time()}


@router.get("/admin/user/{user_id}/sessions", summary="查看用户活跃 Session")
async def get_user_sessions(user_id: str) -> Dict[str, Any]:
    """
    查看指定用户的活跃 Session 列表（管理员接口）

    用于诊断用户的 Session 状态。

    Args:
        user_id: 用户 ID

    Returns:
        用户的活跃 Session 列表
    """
    try:
        session_pool = get_session_pool()
        sessions = await session_pool.get_user_active_sessions(user_id)
        stats = await session_pool.get_user_stats(user_id)

        return {
            "status": "ok",
            "user_id": user_id,
            "active_sessions": sessions,
            "session_count": len(sessions),
            "stats": stats,
            "timestamp": time.time(),
        }
    except Exception as e:
        logger.error(f"获取用户 Session 失败: {e}", exc_info=True)
        return {"status": "error", "error": str(e), "timestamp": time.time()}
