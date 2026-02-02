"""
后台健康探测服务 - Health Probe Service

🆕 V7.10: 实现后台异步健康检测，与用户请求完全解耦

职责：
1. 定期探测所有配置的 LLM 模型健康状态
2. 更新 HealthMonitor 中的健康状态
3. 发现问题时提前标记模型不可用
4. 支持高优先级恢复探测

设计原则：
- 后台运行，不阻塞用户请求
- 探测失败不影响用户请求（优雅降级）
- 支持动态配置探测间隔
"""

import asyncio
import os
import time
from typing import Dict, Any, Optional, List, Set
from datetime import datetime

from logger import get_logger

logger = get_logger("health_probe_service")


class HealthProbeService:
    """
    后台健康探测服务（与用户请求解耦）
    
    使用方法：
        # 启动服务
        probe_service = get_health_probe_service()
        await probe_service.start()
        
        # 停止服务
        await probe_service.stop()
        
        # 手动触发探测（调试用）
        await probe_service.probe_all()
        
        # 查询健康状态
        status = probe_service.get_health_status()
    
    配置来源（优先级从高到低）：
        1. 环境变量
        2. config/llm_config/profiles.yaml 中的 health_probe 配置
        3. 默认值
    
    环境变量：
        LLM_HEALTH_PROBE_ENABLED=true     启用后台探测（默认 true）
        LLM_HEALTH_PROBE_INTERVAL=120     探测间隔（秒，默认 120）
        LLM_HEALTH_PROBE_TIMEOUT=10       单次探测超时（秒，默认 10）
        LLM_HEALTH_PROBE_PROFILES=main_agent,intent_analyzer  要探测的 Profile 列表
    """
    
    def __init__(
        self,
        interval_seconds: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
        profiles: Optional[List[str]] = None
    ):
        """
        初始化健康探测服务
        
        Args:
            interval_seconds: 探测间隔（秒），None 则从配置读取
            timeout_seconds: 单次探测超时（秒），None 则从配置读取
            profiles: 要探测的 Profile 列表，None 则从配置读取
        """
        # 🆕 V7.10: 从统一配置加载器读取配置
        try:
            from config.llm_config import get_health_probe_config
            config = get_health_probe_config()
            bg_config = config.get("background_probe", {})
        except Exception as e:
            logger.warning(f"⚠️ 加载健康探测配置失败，使用默认值: {e}")
            bg_config = {}
        
        # 合并配置（参数 > 配置文件）
        self.enabled = bg_config.get("enabled", True)
        self.interval = interval_seconds if interval_seconds is not None else bg_config.get("interval_seconds", 120)
        self.timeout = timeout_seconds if timeout_seconds is not None else bg_config.get("timeout_seconds", 10.0)
        self.profiles = profiles if profiles is not None else bg_config.get(
            "profiles", 
            ["main_agent", "intent_analyzer", "lead_agent", "worker_agent", "critic_agent"]
        )
        
        # 运行状态
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_probe_time: Dict[str, float] = {}
        self._probe_results: Dict[str, Dict[str, Any]] = {}
        self._probe_errors: Dict[str, str] = {}
        
        # 缓存的 LLM 服务
        self._llm_services: Dict[str, Any] = {}
    
    async def start(self) -> None:
        """
        启动后台探测任务
        """
        if not self.enabled:
            logger.info("⏭️ 后台健康探测已禁用 (LLM_HEALTH_PROBE_ENABLED=false)")
            return
        
        if self._running:
            logger.warning("⚠️ 后台健康探测已在运行")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._probe_loop())
        logger.info(
            f"✅ 后台健康探测已启动: interval={self.interval}s, "
            f"timeout={self.timeout}s, profiles={self.profiles}"
        )
    
    async def stop(self) -> None:
        """
        停止后台探测任务
        """
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("🛑 后台健康探测已停止")
    
    async def _probe_loop(self) -> None:
        """
        探测循环（后台运行）
        """
        # 启动后立即执行一次探测
        await self.probe_all()
        
        while self._running:
            try:
                await asyncio.sleep(self.interval)
                if self._running:
                    await self.probe_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 后台探测循环异常: {e}", exc_info=True)
                await asyncio.sleep(5)  # 异常后短暂等待再重试
    
    async def probe_all(self) -> Dict[str, Dict[str, Any]]:
        """
        探测所有配置的模型
        
        Returns:
            探测结果字典 {profile_name: result}
        """
        results = {}
        
        logger.info("=" * 60)
        logger.info("🩺 开始健康探测...")
        
        for profile_name in self.profiles:
            try:
                result = await self._probe_profile(profile_name)
                results[profile_name] = result
                self._probe_results[profile_name] = result
                self._last_probe_time[profile_name] = time.time()
                self._probe_errors.pop(profile_name, None)
                
                # 显示每个 Profile 的探测结果
                status = result.get("status", "unknown")
                selected = result.get("selected", {})
                switched = result.get("switched", False)
                errors = result.get("errors", [])
                
                if status == "healthy":
                    if switched:
                        logger.info(f"   [{profile_name}] ✅ 健康 (已切换到备用: {selected.get('name', '未知')})")
                    else:
                        logger.info(f"   [{profile_name}] ✅ 健康 (主密钥: {selected.get('name', '未知')})")
                elif status == "degraded":
                    logger.info(f"   [{profile_name}] ⚠️ 降级 (备用密钥: {selected.get('name', '未知')})")
                else:
                    logger.info(f"   [{profile_name}] ❌ 不健康")
                
                # 显示失败的密钥
                if errors:
                    for err in errors:
                        target_name = err.get("target", "未知")
                        api_key = err.get("api_key_env", "未知")
                        # 解析 fallback 级别（如 "primary:claude:..." -> "Primary"）
                        if target_name.startswith("primary:"):
                            level = "Primary"
                        elif target_name.startswith("fallback_"):
                            # 提取数字：fallback_0 -> Fallback 0
                            parts = target_name.split(":")
                            if parts[0].startswith("fallback_"):
                                fb_num = parts[0].replace("fallback_", "")
                                level = f"Fallback {fb_num}"
                            else:
                                level = parts[0].title()
                        else:
                            level = "未知"
                        
                        logger.info(f"      - [{level}] 密钥 {api_key}: ❌ 不可用")
                        
            except Exception as e:
                error_msg = str(e)
                self._probe_errors[profile_name] = error_msg
                results[profile_name] = {"status": "error", "error": error_msg}
                logger.info(f"   [{profile_name}] ❌ 探测异常: {error_msg}")
        
        # 汇总日志
        healthy_count = sum(1 for r in results.values() if r.get("status") in ("healthy", "degraded"))
        total_count = len(results)
        logger.info(f"🩺 探测完成: {healthy_count}/{total_count} 可用")
        logger.info("=" * 60)
        
        return results
    
    async def _probe_profile(self, profile_name: str) -> Dict[str, Any]:
        """
        探测单个 Profile
        
        Args:
            profile_name: Profile 名称
            
        Returns:
            探测结果
        """
        start_time = time.time()
        
        # 获取或创建 LLM 服务
        llm = await self._get_or_create_llm_service(profile_name)
        if not llm:
            return {
                "status": "error",
                "error": f"无法创建 LLM 服务: {profile_name}",
                "latency_ms": 0
            }
        
        # 执行探测（带超时）
        # 🆕 V7.11: 使用轻量级探针（max_tokens=1, enable_thinking=False）
        try:
            if hasattr(llm, "probe"):
                result = await asyncio.wait_for(
                    llm.probe(
                        max_retries=0,           # 探针不重试，快速失败
                        message="health_check",  # 简短消息
                        include_unhealthy=True   # 包含不健康目标
                    ),
                    timeout=self.timeout
                )
            else:
                # 无 probe 方法，直接标记为健康
                result = {"status": "healthy", "message": "no_probe_method"}
        except asyncio.TimeoutError:
            latency_ms = (time.time() - start_time) * 1000
            return {
                "status": "timeout",
                "error": f"探测超时 ({self.timeout}s)",
                "latency_ms": latency_ms
            }
        
        latency_ms = (time.time() - start_time) * 1000
        
        # 解析结果
        if result:
            selected = result.get("selected", {})
            primary = result.get("primary", {})
            switched = result.get("switched", False)
            errors = result.get("errors", [])
            
            # 🐛 修复：根据是否有可用 target 判断健康状态
            # 之前错误地将单个 Profile 的 errors 数量与全局 profiles 列表长度比较
            if not selected or not selected.get("name"):
                status = "unhealthy"  # 没有任何可用的 target
            elif switched:
                status = "degraded"   # 已切换到 fallback（降级）
            else:
                status = "healthy"    # 使用 primary（健康）
            
            return {
                "status": status,
                "selected": selected,
                "primary": primary,
                "switched": switched,
                "errors": errors,
                "latency_ms": latency_ms,
                "timestamp": datetime.now().isoformat()
            }
        
        return {
            "status": "healthy",
            "latency_ms": latency_ms,
            "timestamp": datetime.now().isoformat()
        }
    
    async def _get_or_create_llm_service(self, profile_name: str) -> Optional[Any]:
        """
        获取或创建 LLM 服务（缓存）
        
        Args:
            profile_name: Profile 名称
            
        Returns:
            LLM 服务实例
        """
        if profile_name in self._llm_services:
            return self._llm_services[profile_name]
        
        try:
            from config.llm_config import get_llm_profile
            from core.llm import create_llm_service
            
            profile = get_llm_profile(profile_name)
            llm = create_llm_service(**profile)
            self._llm_services[profile_name] = llm
            return llm
        except Exception as e:
            logger.warning(f"⚠️ 创建 LLM 服务失败: profile={profile_name}, error={e}")
            return None
    
    def get_health_status(self) -> Dict[str, Any]:
        """
        获取当前健康状态汇总
        
        Returns:
            健康状态字典
        """
        now = time.time()
        
        status_summary = {}
        for profile_name in self.profiles:
            result = self._probe_results.get(profile_name, {})
            last_probe = self._last_probe_time.get(profile_name)
            error = self._probe_errors.get(profile_name)
            
            status_summary[profile_name] = {
                "status": result.get("status", "unknown"),
                "selected": result.get("selected", {}),
                "switched": result.get("switched", False),
                "latency_ms": result.get("latency_ms", 0),
                "last_probe_seconds_ago": int(now - last_probe) if last_probe else None,
                "error": error
            }
        
        # 整体健康状态
        statuses = [s["status"] for s in status_summary.values()]
        if all(s == "healthy" for s in statuses):
            overall = "healthy"
        elif any(s in ("error", "unhealthy", "timeout") for s in statuses):
            overall = "degraded"
        else:
            overall = "unknown"
        
        return {
            "overall": overall,
            "profiles": status_summary,
            "enabled": self.enabled,
            "interval_seconds": self.interval,
            "running": self._running
        }
    
    def is_healthy(self, profile_name: str) -> bool:
        """
        判断指定 Profile 是否健康
        
        Args:
            profile_name: Profile 名称
            
        Returns:
            是否健康
        """
        result = self._probe_results.get(profile_name, {})
        status = result.get("status", "unknown")
        return status in ("healthy", "degraded")
    
    def get_selected_target(self, profile_name: str) -> Optional[Dict[str, Any]]:
        """
        获取指定 Profile 当前选中的目标
        
        Args:
            profile_name: Profile 名称
            
        Returns:
            选中的目标信息
        """
        result = self._probe_results.get(profile_name, {})
        return result.get("selected")


# ============================================================
# 单例管理
# ============================================================

_health_probe_service: Optional[HealthProbeService] = None


def get_health_probe_service() -> HealthProbeService:
    """
    获取健康探测服务单例
    """
    global _health_probe_service
    if _health_probe_service is None:
        _health_probe_service = HealthProbeService()
    return _health_probe_service


async def start_health_probe_service() -> HealthProbeService:
    """
    启动健康探测服务（便捷方法）
    
    使用方法：
        # 在应用启动时调用
        from services.health_probe_service import start_health_probe_service
        await start_health_probe_service()
    """
    service = get_health_probe_service()
    await service.start()
    return service


async def stop_health_probe_service() -> None:
    """
    停止健康探测服务（便捷方法）
    
    使用方法：
        # 在应用关闭时调用
        from services.health_probe_service import stop_health_probe_service
        await stop_health_probe_service()
    """
    global _health_probe_service
    if _health_probe_service:
        await _health_probe_service.stop()
        _health_probe_service = None
