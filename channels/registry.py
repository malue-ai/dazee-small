"""
渠道插件注册表

管理所有注册的渠道插件
"""

from typing import Dict, List, Optional, Type
from channels.base.plugin import ChannelPlugin, BaseChannelPlugin
from logger import get_logger

logger = get_logger("channel_registry")


class ChannelRegistry:
    """
    渠道插件注册表
    
    职责：
    - 注册和管理渠道插件
    - 根据 ID 获取插件
    - 列出所有可用插件
    
    使用示例：
    ```python
    registry = ChannelRegistry()
    
    # 注册插件
    registry.register(FeishuPlugin())
    registry.register(DingTalkPlugin())
    
    # 获取插件
    plugin = registry.get("feishu")
    
    # 列出所有插件
    for plugin in registry.list():
        print(plugin.id, plugin.meta.label)
    ```
    """
    
    def __init__(self):
        """初始化注册表"""
        self._plugins: Dict[str, ChannelPlugin] = {}
        self._aliases: Dict[str, str] = {}  # alias -> id
    
    def register(self, plugin: ChannelPlugin) -> None:
        """
        注册渠道插件
        
        Args:
            plugin: 渠道插件实例
        """
        if plugin.id in self._plugins:
            logger.warning(f"渠道插件 {plugin.id} 已存在，将被覆盖")
        
        self._plugins[plugin.id] = plugin
        
        # 注册别名
        if hasattr(plugin.meta, "aliases"):
            for alias in plugin.meta.aliases:
                self._aliases[alias] = plugin.id
        
        logger.info(f"✅ 注册渠道插件: {plugin.id} ({plugin.meta.label})")
    
    def unregister(self, channel_id: str) -> bool:
        """
        注销渠道插件
        
        Args:
            channel_id: 渠道 ID
            
        Returns:
            是否成功注销
        """
        if channel_id in self._plugins:
            plugin = self._plugins.pop(channel_id)
            
            # 移除别名
            if hasattr(plugin.meta, "aliases"):
                for alias in plugin.meta.aliases:
                    self._aliases.pop(alias, None)
            
            logger.info(f"注销渠道插件: {channel_id}")
            return True
        
        return False
    
    def get(self, channel_id: str) -> Optional[ChannelPlugin]:
        """
        获取渠道插件
        
        Args:
            channel_id: 渠道 ID 或别名
            
        Returns:
            渠道插件，不存在则返回 None
        """
        # 先查别名
        if channel_id in self._aliases:
            channel_id = self._aliases[channel_id]
        
        return self._plugins.get(channel_id)
    
    def has(self, channel_id: str) -> bool:
        """
        检查是否存在渠道插件
        
        Args:
            channel_id: 渠道 ID 或别名
            
        Returns:
            是否存在
        """
        if channel_id in self._aliases:
            channel_id = self._aliases[channel_id]
        
        return channel_id in self._plugins
    
    def list(self) -> List[ChannelPlugin]:
        """
        列出所有渠道插件
        
        Returns:
            插件列表
        """
        return list(self._plugins.values())
    
    def list_ids(self) -> List[str]:
        """
        列出所有渠道 ID
        
        Returns:
            ID 列表
        """
        return list(self._plugins.keys())
    
    def get_summary(self) -> List[Dict]:
        """
        获取所有插件摘要
        
        Returns:
            插件摘要列表
        """
        return [
            {
                "id": plugin.id,
                "label": plugin.meta.label,
                "description": plugin.meta.description,
                "capabilities": {
                    "chat_types": plugin.capabilities.chat_types,
                    "media": plugin.capabilities.media,
                    "cards": plugin.capabilities.cards,
                    "streaming": plugin.capabilities.streaming,
                }
            }
            for plugin in self._plugins.values()
        ]


# ===========================================================================
# 全局注册表（单例）
# ===========================================================================

_global_registry: Optional[ChannelRegistry] = None


def get_channel_registry() -> ChannelRegistry:
    """
    获取全局渠道注册表
    
    Returns:
        全局 ChannelRegistry 实例
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = ChannelRegistry()
    return _global_registry


def register_channel(plugin: ChannelPlugin) -> None:
    """
    注册渠道插件到全局注册表
    
    Args:
        plugin: 渠道插件实例
    """
    get_channel_registry().register(plugin)
