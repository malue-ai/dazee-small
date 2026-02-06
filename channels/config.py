"""
渠道配置加载

从 YAML 文件加载渠道配置
"""

import os
from typing import Dict, Any, Optional
from pathlib import Path
import yaml
import aiofiles
from logger import get_logger

logger = get_logger("channel_config")


# 默认配置路径
DEFAULT_CONFIG_PATH = "config/channels.yaml"


async def load_config(config_path: str = None) -> Dict[str, Any]:
    """
    异步加载配置
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        配置字典
    """
    config_path = config_path or DEFAULT_CONFIG_PATH
    path = Path(config_path)
    
    if not path.exists():
        logger.warning(f"配置文件不存在: {config_path}，使用空配置")
        return {}
    
    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            content = await f.read()
            config = yaml.safe_load(content)
        
        # 替换环境变量
        config = _resolve_env_vars(config)
        
        logger.info(f"✅ 加载渠道配置: {config_path}")
        return config or {}
        
    except Exception as e:
        logger.error(f"加载配置失败: {e}", exc_info=True)
        return {}


def _resolve_env_vars(obj: Any) -> Any:
    """
    递归替换环境变量
    
    支持格式：${VAR_NAME} 或 ${VAR_NAME:default_value}
    
    Args:
        obj: 配置对象
        
    Returns:
        替换后的对象
    """
    if isinstance(obj, dict):
        return {k: _resolve_env_vars(v) for k, v in obj.items()}
    
    elif isinstance(obj, list):
        return [_resolve_env_vars(item) for item in obj]
    
    elif isinstance(obj, str):
        # 替换 ${VAR} 或 ${VAR:default}
        if obj.startswith("${") and obj.endswith("}"):
            var_expr = obj[2:-1]
            
            if ":" in var_expr:
                var_name, default = var_expr.split(":", 1)
                return os.environ.get(var_name, default)
            else:
                return os.environ.get(var_expr, "")
        
        return obj
    
    else:
        return obj


def get_channel_config(
    config: Dict[str, Any],
    channel_id: str
) -> Dict[str, Any]:
    """
    获取指定渠道的配置
    
    Args:
        config: 完整配置
        channel_id: 渠道 ID
        
    Returns:
        渠道配置
    """
    return config.get("channels", {}).get(channel_id, {})


def is_channel_enabled(
    config: Dict[str, Any],
    channel_id: str
) -> bool:
    """
    检查渠道是否启用
    
    Args:
        config: 完整配置
        channel_id: 渠道 ID
        
    Returns:
        是否启用
    """
    channel_config = get_channel_config(config, channel_id)
    return channel_config.get("enabled", False)
