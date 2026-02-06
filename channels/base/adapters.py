"""
渠道适配器协议

定义各类适配器的接口规范
"""

from typing import (
    Protocol,
    TypeVar,
    Generic,
    Dict,
    Any,
    List,
    Optional,
    Literal,
    Union,
    runtime_checkable,
)
from channels.base.types import (
    InboundMessage,
    ProcessedMessage,
    OutboundContext,
    DeliveryResult,
    GatewayContext,
    GatewayResponse,
    SecurityContext,
    SecurityResult,
    DmPolicy,
    GroupPolicy,
)


# 泛型账户类型
TAccount = TypeVar("TAccount")


# ===========================================================================
# 配置适配器
# ===========================================================================

@runtime_checkable
class ChannelConfigAdapter(Protocol[TAccount]):
    """
    配置管理适配器
    
    负责：
    - 列出所有账户
    - 解析账户配置
    - 检查账户状态
    """
    
    def list_account_ids(self, config: Dict[str, Any]) -> List[str]:
        """
        列出所有账户 ID
        
        Args:
            config: 渠道配置
            
        Returns:
            账户 ID 列表
        """
        ...
    
    def resolve_account(
        self,
        config: Dict[str, Any],
        account_id: Optional[str] = None
    ) -> TAccount:
        """
        解析账户配置
        
        Args:
            config: 渠道配置
            account_id: 账户 ID（None 则使用默认账户）
            
        Returns:
            解析后的账户对象
        """
        ...
    
    def default_account_id(self, config: Dict[str, Any]) -> Optional[str]:
        """
        获取默认账户 ID
        
        Args:
            config: 渠道配置
            
        Returns:
            默认账户 ID，没有则返回 None
        """
        ...
    
    def is_enabled(self, account: TAccount) -> bool:
        """
        检查账户是否启用
        
        Args:
            account: 账户对象
            
        Returns:
            是否启用
        """
        ...
    
    def is_configured(self, account: TAccount) -> bool:
        """
        检查账户是否已配置（有必需的凭证）
        
        Args:
            account: 账户对象
            
        Returns:
            是否已配置
        """
        ...


# ===========================================================================
# Gateway 适配器
# ===========================================================================

@runtime_checkable
class ChannelGatewayAdapter(Protocol):
    """
    消息接收网关适配器
    
    负责：
    - 启动/停止消息监听
    - 处理入站事件
    """
    
    async def start(self, ctx: GatewayContext) -> None:
        """
        启动消息监听
        
        Args:
            ctx: Gateway 上下文
        """
        ...
    
    async def stop(self, ctx: GatewayContext) -> None:
        """
        停止消息监听
        
        Args:
            ctx: Gateway 上下文
        """
        ...
    
    async def handle_event(
        self,
        event: Dict[str, Any],
        ctx: GatewayContext
    ) -> GatewayResponse:
        """
        处理入站事件
        
        Args:
            event: 原始事件数据
            ctx: Gateway 上下文
            
        Returns:
            Gateway 响应
        """
        ...


# ===========================================================================
# Outbound 适配器
# ===========================================================================

@runtime_checkable
class ChannelOutboundAdapter(Protocol):
    """
    消息发送适配器
    
    负责：
    - 发送各类消息
    - 消息分片
    """
    
    # 发送模式
    delivery_mode: Literal["direct", "gateway", "hybrid"]
    
    # 文本分片限制
    text_chunk_limit: int
    
    async def send_text(self, ctx: OutboundContext) -> DeliveryResult:
        """
        发送文本消息
        
        Args:
            ctx: 发送上下文
            
        Returns:
            发送结果
        """
        ...
    
    async def send_card(self, ctx: OutboundContext) -> DeliveryResult:
        """
        发送卡片消息
        
        Args:
            ctx: 发送上下文
            
        Returns:
            发送结果
        """
        ...
    
    async def send_media(self, ctx: OutboundContext) -> DeliveryResult:
        """
        发送媒体消息
        
        Args:
            ctx: 发送上下文
            
        Returns:
            发送结果
        """
        ...
    
    def chunker(self, text: str, limit: int = None) -> List[str]:
        """
        文本分片
        
        Args:
            text: 原始文本
            limit: 分片限制（默认使用 text_chunk_limit）
            
        Returns:
            分片后的文本列表
        """
        ...
    
    async def edit_message(
        self,
        message_id: str,
        ctx: OutboundContext
    ) -> DeliveryResult:
        """
        编辑消息（流式输出用）
        
        Args:
            message_id: 要编辑的消息 ID
            ctx: 发送上下文
            
        Returns:
            编辑结果
        """
        ...


# ===========================================================================
# Security 适配器
# ===========================================================================

@runtime_checkable
class ChannelSecurityAdapter(Protocol):
    """
    安全策略适配器
    
    负责：
    - 解析私聊/群聊策略
    - 检查发送者权限
    """
    
    def resolve_dm_policy(self, ctx: SecurityContext) -> DmPolicy:
        """
        解析私聊策略
        
        Args:
            ctx: 安全上下文
            
        Returns:
            私聊策略
        """
        ...
    
    def resolve_group_policy(self, ctx: SecurityContext) -> GroupPolicy:
        """
        解析群聊策略
        
        Args:
            ctx: 安全上下文
            
        Returns:
            群聊策略
        """
        ...
    
    def is_sender_allowed(
        self,
        ctx: SecurityContext,
        policy: Union[DmPolicy, GroupPolicy]
    ) -> bool:
        """
        检查发送者是否在白名单中
        
        Args:
            ctx: 安全上下文
            policy: 策略对象
            
        Returns:
            是否允许
        """
        ...


# ===========================================================================
# Actions 适配器（卡片交互）
# ===========================================================================

@runtime_checkable
class ChannelActionsAdapter(Protocol):
    """
    卡片交互适配器
    
    负责：
    - 处理按钮点击
    - 处理表单提交
    """
    
    async def handle_action(
        self,
        action: Dict[str, Any],
        ctx: GatewayContext
    ) -> GatewayResponse:
        """
        处理卡片交互
        
        Args:
            action: 交互数据
            ctx: Gateway 上下文
            
        Returns:
            响应（可以是更新后的卡片）
        """
        ...


# ===========================================================================
# Streaming 适配器
# ===========================================================================

@runtime_checkable
class ChannelStreamingAdapter(Protocol):
    """
    流式输出适配器
    
    负责：
    - 流式消息发送
    - 消息编辑（实现打字机效果）
    """
    
    # 流式模式：off/edit（通过编辑消息）
    stream_mode: Literal["off", "edit"]
    
    # 更新间隔（毫秒）
    update_interval_ms: int
    
    async def start_stream(self, ctx: OutboundContext) -> str:
        """
        开始流式输出（发送占位消息）
        
        Args:
            ctx: 发送上下文
            
        Returns:
            消息 ID
        """
        ...
    
    async def update_stream(
        self,
        message_id: str,
        text: str,
        ctx: OutboundContext
    ) -> DeliveryResult:
        """
        更新流式消息
        
        Args:
            message_id: 消息 ID
            text: 当前文本
            ctx: 发送上下文
            
        Returns:
            更新结果
        """
        ...
    
    async def end_stream(
        self,
        message_id: str,
        text: str,
        ctx: OutboundContext
    ) -> DeliveryResult:
        """
        结束流式输出
        
        Args:
            message_id: 消息 ID
            text: 最终文本
            ctx: 发送上下文
            
        Returns:
            最终结果
        """
        ...
