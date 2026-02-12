"""
容错配置加载模块

从 YAML 文件加载容错配置
"""

import yaml
import aiofiles
from pathlib import Path
from typing import Optional

from logger import get_logger
from infra.resilience.timeout import TimeoutConfig, set_timeout_config
from infra.resilience.retry import RetryConfig, set_retry_config
from infra.resilience.circuit_breaker import CircuitBreakerConfig, get_circuit_breaker

logger = get_logger(__name__)


async def load_resilience_config(config_path: Optional[Path] = None) -> dict:
    """
    异步加载容错配置
    
    Args:
        config_path: 配置文件路径，默认为 config/resilience.yaml
        
    Returns:
        配置字典
    """
    if config_path is None:
        # 默认路径（兼容打包环境）
        from utils.app_paths import get_bundle_dir
        config_path = get_bundle_dir() / "config" / "resilience.yaml"
    
    if not config_path.exists():
        logger.warning(f"⚠️ 容错配置文件不存在: {config_path}，使用默认配置")
        return {}
    
    try:
        async with aiofiles.open(config_path, 'r', encoding='utf-8') as f:
            content = await f.read()
            config = yaml.safe_load(content)
        
        logger.info(f"✅ 容错配置已加载: {config_path}")
        return config or {}
    
    except Exception as e:
        logger.error(f"❌ 加载容错配置失败: {e}")
        return {}


async def apply_resilience_config(config: Optional[dict] = None):
    """
    异步应用容错配置到全局实例
    
    Args:
        config: 配置字典，如果为 None 则从文件加载
    """
    if config is None:
        config = await load_resilience_config()
    
    # 1. 应用超时配置
    if "timeout" in config:
        timeout_cfg = config["timeout"]
        timeout_config = TimeoutConfig(
            llm_timeout=timeout_cfg.get("llm_timeout", 60.0),
            tool_timeout=timeout_cfg.get("tool_timeout", 30.0),
            database_timeout=timeout_cfg.get("database_timeout", 5.0),
            cache_timeout=timeout_cfg.get("cache_timeout", 2.0),
            default_timeout=timeout_cfg.get("default_timeout", 30.0),
        )
        set_timeout_config(timeout_config)
    
    # 2. 应用重试配置
    if "retry" in config:
        retry_cfg = config["retry"]
        retry_config = RetryConfig(
            max_retries=retry_cfg.get("max_retries", 3),
            base_delay=retry_cfg.get("base_delay", 0.5),
            max_delay=retry_cfg.get("max_delay", 60.0),
            exponential_base=retry_cfg.get("exponential_base", 2.0),
        )
        set_retry_config(retry_config)
    
    # 3. 创建熔断器实例
    if "circuit_breakers" in config:
        for service_name, breaker_cfg in config["circuit_breakers"].items():
            breaker_config = CircuitBreakerConfig(
                failure_threshold=breaker_cfg.get("failure_threshold", 5),
                success_threshold=breaker_cfg.get("success_threshold", 2),
                timeout=breaker_cfg.get("timeout", 30.0),
                window_size=breaker_cfg.get("window_size", 10),
                half_open_max_calls=breaker_cfg.get("half_open_max_calls", 1),
            )
            # 预创建熔断器（会注册到全局注册表）
            get_circuit_breaker(service_name, breaker_config)
            logger.info(f"✅ 熔断器已创建: {service_name}")
    
    # 4. 注册降级策略
    if "fallback" in config:
        from infra.resilience.fallback import (
            register_fallback,
            FallbackType,
            default_llm_fallback,
            default_tool_fallback,
            default_database_fallback,
        )
        
        fallback_funcs = {
            "llm_service": default_llm_fallback,
            "tool_service": default_tool_fallback,
            "database_service": default_database_fallback,
        }
        
        for service_name, fb_cfg in config["fallback"].items():
            if fb_cfg.get("enabled", False):
                fallback_func = fallback_funcs.get(service_name, lambda: {"error": "服务不可用"})
                fb_type = FallbackType(fb_cfg.get("type", "default_response"))
                
                register_fallback(service_name, fallback_func, fb_type)
                logger.info(f"✅ 降级策略已注册: {service_name} (type={fb_type.value})")
    
    logger.info("✅ 容错配置应用完成")
