"""
LLM 健康监控器

用于聚合模型调用的成功率与延迟指标，提供健康状态判断。
"""

import os
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional

from logger import get_logger

logger = get_logger("llm.health_monitor")


@dataclass
class HealthPolicy:
    """
    健康检测策略

    Attributes:
        window_seconds: 统计窗口（秒）
        min_samples: 最小样本数
        error_rate_threshold: 错误率阈值
        avg_latency_ms_threshold: 平均延迟阈值（毫秒）
    """

    window_seconds: int = 300
    min_samples: int = 5
    error_rate_threshold: float = 0.3
    avg_latency_ms_threshold: float = 15000.0


class LLMHealthMonitor:
    """
    LLM 健康监控器（按模型目标统计）

    记录调用成功/失败与延迟，按滑动窗口计算健康状态。
    """

    def __init__(self, policy: Optional[HealthPolicy] = None):
        """
        初始化健康监控器

        Args:
            policy: 健康检测策略
        """
        self.policy = policy or HealthPolicy()
        self._records: Dict[str, Deque[tuple[float, bool, float]]] = {}
        self._last_error: Dict[str, str] = {}
        self._status_cache: Dict[str, str] = {}

    def record_success(self, target_key: str, latency_ms: float) -> None:
        """
        记录成功调用

        Args:
            target_key: 目标唯一标识
            latency_ms: 延迟（毫秒）
        """
        self._append_record(target_key, True, latency_ms)

    def record_failure(self, target_key: str, latency_ms: float, error: Exception) -> None:
        """
        记录失败调用

        Args:
            target_key: 目标唯一标识
            latency_ms: 延迟（毫秒）
            error: 异常
        """
        self._last_error[target_key] = str(error)
        self._append_record(target_key, False, latency_ms)

    def is_healthy(self, target_key: str) -> bool:
        """
        判断目标是否健康

        Args:
            target_key: 目标唯一标识

        Returns:
            是否健康
        """
        status = self.get_status(target_key)
        return status != "unhealthy"

    def get_status(self, target_key: str) -> str:
        """
        获取健康状态

        Returns:
            "healthy" | "degraded" | "unhealthy"
        """
        stats = self.get_stats(target_key)

        # ⚠️ 样本不足时的特殊处理
        if stats["sample_count"] < self.policy.min_samples:
            # 如果样本不足但有失败，直接返回 unhealthy
            if stats["error_rate"] > 0:
                return "unhealthy"
            # 如果样本不足且全部成功，暂时认为健康（观察期）
            return "healthy"

        if stats["error_rate"] > self.policy.error_rate_threshold:
            return "unhealthy"
        if stats["avg_latency_ms"] > self.policy.avg_latency_ms_threshold:
            return "degraded"
        return "healthy"

    def get_stats(self, target_key: str) -> Dict[str, float]:
        """
        获取统计指标

        Args:
            target_key: 目标唯一标识

        Returns:
            统计指标
        """
        self._prune_old_records(target_key)
        records = self._records.get(target_key, deque())

        if not records:
            return {
                "sample_count": 0,
                "error_rate": 0.0,
                "avg_latency_ms": 0.0,
                "last_error": self._last_error.get(target_key, ""),
            }

        total = len(records)
        errors = sum(1 for _, success, _ in records if not success)
        total_latency = sum(latency for _, _, latency in records)

        return {
            "sample_count": float(total),
            "error_rate": errors / total if total > 0 else 0.0,
            "avg_latency_ms": total_latency / total if total > 0 else 0.0,
            "last_error": self._last_error.get(target_key, ""),
        }

    def _append_record(self, target_key: str, success: bool, latency_ms: float) -> None:
        """
        追加记录
        """
        if target_key not in self._records:
            self._records[target_key] = deque()
        self._records[target_key].append((time.time(), success, latency_ms))
        self._prune_old_records(target_key)

        new_status = self.get_status(target_key)
        old_status = self._status_cache.get(target_key)
        if new_status != old_status:
            self._status_cache[target_key] = new_status
            logger.info(f"🩺 LLM 健康状态变化: {target_key} -> {new_status}")

    def _prune_old_records(self, target_key: str) -> None:
        """
        清理过期记录
        """
        records = self._records.get(target_key)
        if not records:
            return

        cutoff = time.time() - self.policy.window_seconds
        while records and records[0][0] < cutoff:
            records.popleft()


def _load_health_policy_from_env() -> HealthPolicy:
    """
    从环境变量加载健康检测策略
    """
    window_seconds = os.getenv("LLM_HEALTH_WINDOW_SECONDS")
    min_samples = os.getenv("LLM_HEALTH_MIN_SAMPLES")
    error_rate_threshold = os.getenv("LLM_HEALTH_ERROR_RATE_THRESHOLD")
    avg_latency_ms_threshold = os.getenv("LLM_HEALTH_AVG_LATENCY_MS_THRESHOLD")

    return HealthPolicy(
        window_seconds=int(window_seconds) if window_seconds else HealthPolicy.window_seconds,
        min_samples=int(min_samples) if min_samples else HealthPolicy.min_samples,
        error_rate_threshold=(
            float(error_rate_threshold)
            if error_rate_threshold
            else HealthPolicy.error_rate_threshold
        ),
        avg_latency_ms_threshold=(
            float(avg_latency_ms_threshold)
            if avg_latency_ms_threshold
            else HealthPolicy.avg_latency_ms_threshold
        ),
    )


_health_monitor: Optional[LLMHealthMonitor] = None


def get_llm_health_monitor() -> LLMHealthMonitor:
    """
    获取健康监控器单例
    """
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = LLMHealthMonitor(policy=_load_health_policy_from_env())
    return _health_monitor
