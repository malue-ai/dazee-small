"""
渠道管理器

统一管理所有渠道的生命周期和消息处理
"""

from typing import Dict, Any, Optional, List, Callable, Awaitable
from channels.base.plugin import ChannelPlugin
from channels.base.types import (
    InboundMessage,
    ProcessedMessage,
    OutboundContext,
    DeliveryResult,
    GatewayContext,
    GatewayResponse,
    SecurityContext,
    SecurityResult,
)
from channels.registry import ChannelRegistry, get_channel_registry
from logger import get_logger

logger = get_logger("channel_manager")


# 消息处理回调类型
MessageHandler = Callable[[ProcessedMessage], Awaitable[Optional[str]]]


class ChannelManager:
    """
    渠道管理器
    
    职责：
    - 管理渠道生命周期（启动/停止）
    - 统一消息处理入口
    - 消息路由和分发
    
    使用示例：
    ```python
    manager = ChannelManager(config)
    
    # 注册消息处理回调
    manager.on_message(async_message_handler)
    
    # 启动所有渠道
    await manager.start_all()
    
    # 处理入站事件
    response = await manager.handle_event("feishu", event_data)
    
    # 发送消息
    result = await manager.send_message("feishu", "default", "chat_id", "Hello!")
    ```
    """
    
    def __init__(
        self,
        config: Dict[str, Any] = None,
        registry: ChannelRegistry = None
    ):
        """
        初始化渠道管理器
        
        Args:
            config: 渠道配置（从 channels.yaml 加载）
            registry: 渠道注册表（默认使用全局注册表）
        """
        self.config = config or {}
        self.registry = registry or get_channel_registry()
        
        # 消息处理回调
        self._message_handler: Optional[MessageHandler] = None
        
        # 活跃的 Gateway 上下文
        self._gateway_contexts: Dict[str, GatewayContext] = {}
        
        # 是否已启动
        self._started = False
    
    def on_message(self, handler: MessageHandler) -> None:
        """
        注册消息处理回调
        
        Args:
            handler: 异步消息处理函数
        """
        self._message_handler = handler
        logger.debug("已注册消息处理回调")
    
    # ===========================================================================
    # 生命周期管理
    # ===========================================================================
    
    async def start_all(self) -> None:
        """启动所有已启用的渠道"""
        if self._started:
            logger.warning("渠道管理器已启动")
            return
        
        channels_config = self.config.get("channels", {})
        
        for channel_id, channel_config in channels_config.items():
            if channel_config.get("enabled", False):
                await self.start_channel(channel_id)
        
        self._started = True
        logger.info(f"✅ 渠道管理器已启动，活跃渠道: {list(self._gateway_contexts.keys())}")
    
    async def stop_all(self) -> None:
        """停止所有渠道"""
        for channel_id in list(self._gateway_contexts.keys()):
            await self.stop_channel(channel_id)
        
        self._started = False
        logger.info("渠道管理器已停止")
    
    async def start_channel(self, channel_id: str, account_id: str = None) -> bool:
        """
        启动指定渠道
        
        Args:
            channel_id: 渠道 ID
            account_id: 账户 ID（可选）
            
        Returns:
            是否成功启动
        """
        plugin = self.registry.get(channel_id)
        if not plugin:
            logger.warning(f"渠道插件不存在: {channel_id}")
            return False
        
        if not plugin.gateway:
            logger.debug(f"渠道 {channel_id} 没有 Gateway 适配器")
            return False
        
        # 获取渠道配置
        channel_config = self.config.get("channels", {}).get(channel_id, {})
        
        # 解析账户
        if account_id is None:
            account_id = plugin.config.default_account_id(channel_config) or "default"
        
        account = plugin.config.resolve_account(channel_config, account_id)
        
        if not plugin.config.is_enabled(account):
            logger.info(f"渠道 {channel_id}/{account_id} 未启用")
            return False
        
        if not plugin.config.is_configured(account):
            logger.warning(f"渠道 {channel_id}/{account_id} 未配置")
            return False
        
        # 创建 Gateway 上下文
        ctx = GatewayContext(
            channel_id=channel_id,
            account_id=account_id,
            account=account,
            config=channel_config
        )
        
        # 启动 Gateway
        try:
            await plugin.gateway.start(ctx)
            self._gateway_contexts[f"{channel_id}/{account_id}"] = ctx
            logger.info(f"✅ 启动渠道: {channel_id}/{account_id}")
            return True
        except Exception as e:
            logger.error(f"❌ 启动渠道失败: {channel_id}/{account_id}, error={e}", exc_info=True)
            return False
    
    async def stop_channel(self, channel_id: str, account_id: str = None) -> bool:
        """
        停止指定渠道
        
        Args:
            channel_id: 渠道 ID
            account_id: 账户 ID（可选）
            
        Returns:
            是否成功停止
        """
        plugin = self.registry.get(channel_id)
        if not plugin or not plugin.gateway:
            return False
        
        # 查找匹配的上下文
        key = f"{channel_id}/{account_id}" if account_id else None
        
        contexts_to_stop = []
        if key and key in self._gateway_contexts:
            contexts_to_stop.append((key, self._gateway_contexts[key]))
        elif key is None:
            # 停止该渠道的所有账户
            for k, ctx in self._gateway_contexts.items():
                if k.startswith(f"{channel_id}/"):
                    contexts_to_stop.append((k, ctx))
        
        for key, ctx in contexts_to_stop:
            try:
                await plugin.gateway.stop(ctx)
                del self._gateway_contexts[key]
                logger.info(f"停止渠道: {key}")
            except Exception as e:
                logger.error(f"停止渠道失败: {key}, error={e}", exc_info=True)
        
        return len(contexts_to_stop) > 0
    
    # ===========================================================================
    # 事件处理
    # ===========================================================================
    
    async def handle_event(
        self,
        channel_id: str,
        event: Dict[str, Any],
        account_id: str = None
    ) -> GatewayResponse:
        """
        处理入站事件
        
        Args:
            channel_id: 渠道 ID
            event: 原始事件数据
            account_id: 账户 ID（可选）
            
        Returns:
            Gateway 响应
        """
        plugin = self.registry.get(channel_id)
        if not plugin:
            logger.warning(f"渠道插件不存在: {channel_id}")
            return GatewayResponse(code=404, message=f"Channel {channel_id} not found")
        
        if not plugin.gateway:
            logger.warning(f"渠道 {channel_id} 没有 Gateway 适配器")
            return GatewayResponse(code=501, message="Gateway not supported")
        
        # 获取或创建上下文
        channel_config = self.config.get("channels", {}).get(channel_id, {})
        
        if account_id is None:
            account_id = plugin.config.default_account_id(channel_config) or "default"
        
        account = plugin.config.resolve_account(channel_config, account_id)
        
        ctx = GatewayContext(
            channel_id=channel_id,
            account_id=account_id,
            account=account,
            config=channel_config
        )
        
        # 调用 Gateway 处理事件
        try:
            return await plugin.gateway.handle_event(event, ctx)
        except Exception as e:
            logger.error(f"处理事件失败: {channel_id}, error={e}", exc_info=True)
            return GatewayResponse(code=500, message=str(e))
    
    # ===========================================================================
    # 消息发送
    # ===========================================================================
    
    async def send_message(
        self,
        channel_id: str,
        account_id: str,
        chat_id: str,
        text: str = None,
        card_data: Dict[str, Any] = None,
        media_url: str = None,
        **kwargs
    ) -> DeliveryResult:
        """
        发送消息
        
        Args:
            channel_id: 渠道 ID
            account_id: 账户 ID
            chat_id: 聊天 ID
            text: 文本内容
            card_data: 卡片数据
            media_url: 媒体 URL
            **kwargs: 其他参数
            
        Returns:
            发送结果
        """
        plugin = self.registry.get(channel_id)
        if not plugin:
            return DeliveryResult.fail(f"Channel {channel_id} not found")
        
        if not plugin.outbound:
            return DeliveryResult.fail("Outbound not supported")
        
        # 构建发送上下文
        ctx = OutboundContext(
            channel_id=channel_id,
            account_id=account_id,
            chat_id=chat_id,
            text=text or "",
            card_data=card_data,
            media_url=media_url,
            **kwargs
        )
        
        # 选择发送方式
        try:
            if card_data:
                return await plugin.outbound.send_card(ctx)
            elif media_url:
                return await plugin.outbound.send_media(ctx)
            else:
                return await plugin.outbound.send_text(ctx)
        except Exception as e:
            logger.error(f"发送消息失败: {channel_id}/{chat_id}, error={e}", exc_info=True)
            return DeliveryResult.fail(str(e))
    
    # ===========================================================================
    # 查询接口
    # ===========================================================================
    
    def get_plugin(self, channel_id: str) -> Optional[ChannelPlugin]:
        """获取渠道插件"""
        return self.registry.get(channel_id)
    
    def list_channels(self) -> List[str]:
        """列出所有注册的渠道"""
        return self.registry.list_ids()
    
    def list_active_channels(self) -> List[str]:
        """列出所有活跃的渠道"""
        return list(self._gateway_contexts.keys())
    
    def get_channel_status(self, channel_id: str) -> Dict[str, Any]:
        """获取渠道状态"""
        plugin = self.registry.get(channel_id)
        if not plugin:
            return {"error": "Channel not found"}
        
        active_accounts = [
            k.split("/")[1] for k in self._gateway_contexts.keys()
            if k.startswith(f"{channel_id}/")
        ]
        
        return {
            "id": plugin.id,
            "label": plugin.meta.label,
            "active_accounts": active_accounts,
            "capabilities": {
                "chat_types": plugin.capabilities.chat_types,
                "media": plugin.capabilities.media,
                "cards": plugin.capabilities.cards,
                "streaming": plugin.capabilities.streaming,
            }
        }


# ===========================================================================
# 全局管理器（单例）
# ===========================================================================

_global_manager: Optional[ChannelManager] = None


def get_channel_manager() -> ChannelManager:
    """
    获取全局渠道管理器
    
    Returns:
        全局 ChannelManager 实例
    """
    global _global_manager
    if _global_manager is None:
        _global_manager = ChannelManager()
    return _global_manager


def set_channel_manager(manager: ChannelManager) -> None:
    """
    设置全局渠道管理器
    
    Args:
        manager: ChannelManager 实例
    """
    global _global_manager
    _global_manager = manager
