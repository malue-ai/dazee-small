"""
飞书 Gateway 适配器

处理飞书事件回调
"""

from typing import Dict, Any, Optional, Callable, Awaitable
from channels.base.types import (
    InboundMessage,
    GatewayContext,
    GatewayResponse,
)
from channels.feishu.types import FeishuAccount, FeishuMessage
from channels.feishu.client import FeishuClient
from logger import get_logger

logger = get_logger("feishu_gateway")


# 消息处理回调类型
MessageCallback = Callable[[InboundMessage, GatewayContext], Awaitable[Optional[str]]]


class FeishuGatewayAdapter:
    """
    飞书 Gateway 适配器
    
    处理飞书推送的事件：
    - URL 验证
    - 消息事件
    - 卡片交互事件
    """
    
    def __init__(self):
        """初始化 Gateway"""
        self._clients: Dict[str, FeishuClient] = {}
        self._message_callback: Optional[MessageCallback] = None
        self._card_action_callback: Optional[Callable] = None
    
    def on_message(self, callback: MessageCallback) -> None:
        """注册消息处理回调"""
        self._message_callback = callback
    
    def on_card_action(self, callback: Callable) -> None:
        """注册卡片交互回调"""
        self._card_action_callback = callback
    
    async def start(self, ctx: GatewayContext) -> None:
        """
        启动 Gateway（初始化客户端）
        
        Args:
            ctx: Gateway 上下文
        """
        key = f"{ctx.channel_id}/{ctx.account_id}"
        if key not in self._clients:
            self._clients[key] = FeishuClient(ctx.account)
        logger.info(f"✅ 飞书 Gateway 已启动: {key}")
    
    async def stop(self, ctx: GatewayContext) -> None:
        """
        停止 Gateway
        
        Args:
            ctx: Gateway 上下文
        """
        key = f"{ctx.channel_id}/{ctx.account_id}"
        if key in self._clients:
            await self._clients[key].close()
            del self._clients[key]
        logger.info(f"飞书 Gateway 已停止: {key}")
    
    def get_client(self, ctx: GatewayContext) -> Optional[FeishuClient]:
        """获取客户端"""
        key = f"{ctx.channel_id}/{ctx.account_id}"
        return self._clients.get(key)
    
    async def handle_event(
        self,
        event: Dict[str, Any],
        ctx: GatewayContext
    ) -> GatewayResponse:
        """
        处理飞书事件
        
        Args:
            event: 原始事件数据
            ctx: Gateway 上下文
            
        Returns:
            Gateway 响应
        """
        # 1. URL 验证
        if event.get("type") == "url_verification":
            return self._handle_url_verification(event, ctx)
        
        # 2. 解析事件类型
        schema = event.get("schema")
        
        if schema == "2.0":
            return await self._handle_event_v2(event, ctx)
        else:
            return await self._handle_event_v1(event, ctx)
    
    def _handle_url_verification(
        self,
        event: Dict[str, Any],
        ctx: GatewayContext
    ) -> GatewayResponse:
        """处理 URL 验证请求"""
        challenge = event.get("challenge", "")
        logger.info(f"📌 飞书 URL 验证: challenge={challenge[:20]}...")
        return GatewayResponse(challenge=challenge)
    
    async def _handle_event_v2(
        self,
        event: Dict[str, Any],
        ctx: GatewayContext
    ) -> GatewayResponse:
        """
        处理 v2.0 格式事件
        
        v2.0 结构：
        {
            "schema": "2.0",
            "header": {"event_type": "im.message.receive_v1", ...},
            "event": {...}
        }
        """
        header = event.get("header", {})
        event_type = header.get("event_type", "")
        event_data = event.get("event", {})
        
        logger.info(f"📨 收到飞书事件: type={event_type}")
        
        # 消息事件
        if event_type == "im.message.receive_v1":
            return await self._handle_message_event(event_data, ctx)
        
        # 卡片交互事件
        if event_type == "card.action.trigger":
            return await self._handle_card_action(event_data, ctx)
        
        # 其他事件
        logger.debug(f"未处理的事件类型: {event_type}")
        return GatewayResponse(code=0)
    
    async def _handle_event_v1(
        self,
        event: Dict[str, Any],
        ctx: GatewayContext
    ) -> GatewayResponse:
        """处理 v1.0 格式事件"""
        event_data = event.get("event", {})
        event_type = event_data.get("type", "")
        
        if event_type == "message":
            return await self._handle_message_event(event_data, ctx)
        
        return GatewayResponse(code=0)
    
    async def _handle_message_event(
        self,
        event: Dict[str, Any],
        ctx: GatewayContext
    ) -> GatewayResponse:
        """
        处理消息事件
        
        Args:
            event: 消息事件数据
            ctx: Gateway 上下文
            
        Returns:
            Gateway 响应
        """
        try:
            # 解析消息
            feishu_msg = FeishuMessage.from_event(event)
            
            logger.info(
                f"📩 收到飞书消息: chat_type={feishu_msg.chat_type}, "
                f"msg_type={feishu_msg.msg_type}, "
                f"content={feishu_msg.content[:50] if feishu_msg.content else ''}..."
            )
            
            # 转换为通用消息格式
            inbound_message = InboundMessage(
                message_id=feishu_msg.message_id,
                channel_id="feishu",
                account_id=ctx.account_id,
                chat_id=feishu_msg.chat_id,
                chat_type="direct" if feishu_msg.chat_type == "p2p" else "group",
                sender_id=feishu_msg.sender_id,
                sender_name=feishu_msg.sender_name,
                content=feishu_msg.content,
                msg_type=feishu_msg.msg_type,
                # 飞书 mentions 为对象数组，包含被 @ 的用户 id 信息
                # 这里转换为字符串列表（open_id/user_id/union_id），供上层做严格 @ 判断
                mentions=self._extract_mention_ids(feishu_msg.mentions),
                thread_id=feishu_msg.thread_id,
                raw_event=event,
            )
            
            # 调用回调处理消息
            if self._message_callback:
                try:
                    reply = await self._message_callback(inbound_message, ctx)
                    if reply:
                        logger.debug(f"消息处理完成，将回复: {reply[:50]}...")
                except Exception as e:
                    logger.error(f"消息处理回调失败: {e}", exc_info=True)
            
            return GatewayResponse(code=0)
            
        except Exception as e:
            logger.error(f"处理消息事件失败: {e}", exc_info=True)
            return GatewayResponse(code=500, message=str(e))

    @staticmethod
    def _extract_mention_ids(mentions: Any) -> list[str]:
        """
        从飞书 mentions 提取可用于匹配的 ID 列表

        备注：
        - 飞书回调的 mentions 结构通常包含 {"id": {"open_id": "...", "user_id": "..."}, ...}
        - 为了提高匹配成功率，会尽量收集 open_id/user_id/union_id
        """
        if not isinstance(mentions, list):
            return []

        ids: list[str] = []
        seen: set[str] = set()

        for m in mentions:
            if not isinstance(m, dict):
                continue

            id_obj = m.get("id") if isinstance(m.get("id"), dict) else {}

            candidates = [
                id_obj.get("open_id"),
                id_obj.get("user_id"),
                id_obj.get("union_id"),
                m.get("open_id"),
                m.get("user_id"),
                m.get("union_id"),
            ]

            for c in candidates:
                if isinstance(c, str) and c and c not in seen:
                    seen.add(c)
                    ids.append(c)

        return ids
    
    async def _handle_card_action(
        self,
        event: Dict[str, Any],
        ctx: GatewayContext
    ) -> GatewayResponse:
        """
        处理卡片交互事件
        
        Args:
            event: 卡片交互数据
            ctx: Gateway 上下文
            
        Returns:
            Gateway 响应
        """
        action = event.get("action", {})
        value = action.get("value", {})
        
        logger.info(f"🔘 飞书卡片交互: action={action.get('tag')}, value={value}")
        
        if self._card_action_callback:
            try:
                result = await self._card_action_callback(event, ctx)
                if result:
                    return result
            except Exception as e:
                logger.error(f"卡片交互处理失败: {e}", exc_info=True)
        
        return GatewayResponse(code=0)
