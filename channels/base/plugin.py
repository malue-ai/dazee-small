"""
渠道插件基类

定义 ChannelPlugin 协议和基类
"""

from typing import (
    Protocol,
    TypeVar,
    Generic,
    Optional,
    runtime_checkable,
)
from channels.base.capabilities import ChannelMeta, ChannelCapabilities
from channels.base.adapters import (
    ChannelConfigAdapter,
    ChannelGatewayAdapter,
    ChannelOutboundAdapter,
    ChannelSecurityAdapter,
    ChannelActionsAdapter,
    ChannelStreamingAdapter,
)


TAccount = TypeVar("TAccount")


@runtime_checkable
class ChannelPlugin(Protocol[TAccount]):
    """
    渠道插件协议
    
    定义一个渠道插件必须实现的接口
    
    使用示例：
    ```python
    class FeishuPlugin:
        id = "feishu"
        meta = ChannelMeta(...)
        capabilities = ChannelCapabilities(...)
        
        config = FeishuConfigAdapter()
        gateway = FeishuGatewayAdapter()
        outbound = FeishuOutboundAdapter()
        security = FeishuSecurityAdapter()
    ```
    """
    
    # 渠道 ID（唯一标识）
    id: str
    
    # 元数据
    meta: ChannelMeta
    
    # 功能声明
    capabilities: ChannelCapabilities
    
    # 必需适配器
    config: ChannelConfigAdapter[TAccount]
    
    # 可选适配器
    gateway: Optional[ChannelGatewayAdapter]
    outbound: Optional[ChannelOutboundAdapter]
    security: Optional[ChannelSecurityAdapter]
    actions: Optional[ChannelActionsAdapter]
    streaming: Optional[ChannelStreamingAdapter]


class BaseChannelPlugin(Generic[TAccount]):
    """
    渠道插件基类
    
    提供默认实现，子类可以覆盖
    """
    
    id: str = "base"
    meta: ChannelMeta = ChannelMeta(id="base", label="Base Channel")
    capabilities: ChannelCapabilities = ChannelCapabilities()
    
    # 适配器（子类覆盖）
    config: Optional[ChannelConfigAdapter[TAccount]] = None
    gateway: Optional[ChannelGatewayAdapter] = None
    outbound: Optional[ChannelOutboundAdapter] = None
    security: Optional[ChannelSecurityAdapter] = None
    actions: Optional[ChannelActionsAdapter] = None
    streaming: Optional[ChannelStreamingAdapter] = None
    
    def __init__(self):
        """初始化插件"""
        pass
    
    def supports(self, feature: str) -> bool:
        """检查是否支持某功能"""
        return self.capabilities.supports(feature)
    
    def has_gateway(self) -> bool:
        """是否有 Gateway 适配器"""
        return self.gateway is not None
    
    def has_outbound(self) -> bool:
        """是否有 Outbound 适配器"""
        return self.outbound is not None
    
    def has_security(self) -> bool:
        """是否有 Security 适配器"""
        return self.security is not None
    
    def has_streaming(self) -> bool:
        """是否有 Streaming 适配器"""
        return self.streaming is not None
