"""
飞书消息处理器

负责：
- 接收飞书消息
- 调用 ChatService 处理
- 发送回复
- 流式输出
"""

import asyncio
from typing import Dict, Any, Optional, TYPE_CHECKING
from channels.base.types import (
    InboundMessage,
    ProcessedMessage,
    OutboundContext,
    GatewayContext,
    SecurityContext,
)
from channels.gateway.preprocessor import MessagePreprocessor
from channels.gateway.security import SecurityChecker
from channels.feishu.types import FeishuAccount
from channels.feishu.client import FeishuClient
from channels.feishu.cards import FeishuCardBuilder
from channels.feishu.outbound import FeishuOutboundAdapter
from logger import get_logger

if TYPE_CHECKING:
    from services.chat_service import ChatService

logger = get_logger("feishu_handler")


class FeishuMessageHandler:
    """
    飞书消息处理器
    
    整合 Gateway、Security、ChatService 的完整处理流程
    
    使用示例：
    ```python
    handler = FeishuMessageHandler(chat_service)
    
    # 处理消息
    await handler.handle_message(inbound_message, gateway_context)
    ```
    """
    
    def __init__(
        self,
        chat_service: "ChatService",
        default_agent_id: str = None,
        enable_streaming: bool = True,
        stream_update_interval_ms: int = 500
    ):
        """
        初始化处理器
        
        Args:
            chat_service: ChatService 实例
            default_agent_id: 默认 Agent ID
            enable_streaming: 是否启用流式输出
            stream_update_interval_ms: 流式更新间隔（毫秒）
        """
        self.chat_service = chat_service
        self.default_agent_id = default_agent_id
        self.enable_streaming = enable_streaming
        self.stream_update_interval_ms = stream_update_interval_ms
        
        # 组件
        self.preprocessor = MessagePreprocessor()
        self.security_checker = SecurityChecker()
        self.outbound = FeishuOutboundAdapter()
        
        # 客户端缓存
        self._clients: Dict[str, FeishuClient] = {}
        
        # 会话映射（chat_id -> conversation_id）
        self._conversations: Dict[str, str] = {}

        # 机器人 ID 缓存（account_id -> set[id]）
        self._bot_ids: Dict[str, set[str]] = {}
    
    def get_client(self, account: FeishuAccount, account_id: str) -> FeishuClient:
        """获取或创建客户端"""
        if account_id not in self._clients:
            self._clients[account_id] = FeishuClient(account)
            self.outbound.set_client(account_id, self._clients[account_id])
        return self._clients[account_id]
    
    async def handle_message(
        self,
        message: InboundMessage,
        ctx: GatewayContext
    ) -> Optional[str]:
        """
        处理入站消息
        
        完整流程：
        1. 权限检查
        2. 消息预处理
        3. 调用 ChatService
        4. 发送回复
        
        Args:
            message: 入站消息
            ctx: Gateway 上下文
            
        Returns:
            回复内容（如果有）
        """
        account: FeishuAccount = ctx.account
        client = self.get_client(account, ctx.account_id)
        
        # 1. 权限检查
        security_ctx = SecurityContext(
            channel_id=message.channel_id,
            account_id=ctx.account_id,
            account=account,
            chat_id=message.chat_id,
            chat_type=message.chat_type,
            sender_id=message.sender_id,
            sender_name=message.sender_name,
            message=message
        )
        
        # 这里需要传入插件来检查权限
        # 暂时跳过权限检查，直接处理
        
        # 2. 检查是否需要 @机器人（群聊）
        if message.chat_type == "group" and account.require_mention:
            bot_ids = await self._get_bot_ids(ctx.account_id, client)

            # 无法确定机器人身份时，保守策略：不回复群消息（确保“只在 @ 时回复”）
            if not bot_ids:
                logger.warning(
                    f"群聊 require_mention=true 但无法获取机器人ID，已忽略消息: "
                    f"account_id={ctx.account_id}, chat_id={message.chat_id}"
                )
                return None

            # 防止自回复循环
            if message.sender_id in bot_ids:
                return None

            # 只有在 mentions 中包含机器人 id 时才处理
            if not set(message.mentions).intersection(bot_ids):
                logger.debug(
                    f"群聊未@机器人，忽略: account_id={ctx.account_id}, chat_id={message.chat_id}"
                )
                return None
        
        # 3. 获取或创建 conversation_id
        conversation_id = self._get_conversation_id(message.chat_id)
        
        # 4. 调用 ChatService
        try:
            if self.enable_streaming and account.stream_mode == "edit":
                return await self._handle_streaming(
                    message, ctx, client, conversation_id
                )
            else:
                return await self._handle_sync(
                    message, ctx, client, conversation_id
                )
        except Exception as e:
            logger.error(f"处理消息失败: {e}", exc_info=True)
            
            # 发送错误提示
            error_card = FeishuCardBuilder.error_card(
                error_type="处理失败",
                error_message=str(e)
            )
            await client.send_card(message.chat_id, error_card)
            
            return None

    async def _get_bot_ids(self, account_id: str, client: FeishuClient) -> set[str]:
        """
        获取并缓存机器人 ID 集合

        Args:
            account_id: 账户 ID
            client: 飞书客户端

        Returns:
            可用于匹配 mentions 的 ID 集合（可能为空）
        """
        if account_id in self._bot_ids:
            return self._bot_ids[account_id]

        ids = await client.get_bot_ids()
        self._bot_ids[account_id] = ids
        return ids
    
    async def _handle_sync(
        self,
        message: InboundMessage,
        ctx: GatewayContext,
        client: FeishuClient,
        conversation_id: str
    ) -> Optional[str]:
        """
        同步处理（等待完成后回复）
        
        Args:
            message: 入站消息
            ctx: Gateway 上下文
            client: 飞书客户端
            conversation_id: 对话 ID
            
        Returns:
            回复内容
        """
        # 调用 ChatService
        response_text = ""
        
        async for event in await self.chat_service.chat(
            message=message.content,
            user_id=message.sender_id,
            conversation_id=conversation_id,
            agent_id=self.default_agent_id,
            stream=True
        ):
            # 收集文本内容
            event_type = event.get("type", "")
            
            if event_type == "content_delta":
                delta = event.get("data", {}).get("delta", "")
                response_text += delta
            
            elif event_type in ("message_stop", "done"):
                break
        
        # 发送回复
        if response_text:
            await client.reply_text(message.message_id, response_text)
        
        return response_text
    
    async def _handle_streaming(
        self,
        message: InboundMessage,
        ctx: GatewayContext,
        client: FeishuClient,
        conversation_id: str
    ) -> Optional[str]:
        """
        流式处理（边生成边更新消息）
        
        Args:
            message: 入站消息
            ctx: Gateway 上下文
            client: 飞书客户端
            conversation_id: 对话 ID
            
        Returns:
            回复内容
        """
        # 先发送一个占位卡片
        initial_card = FeishuCardBuilder.streaming_card("", is_typing=True)
        response = await client.reply_card(message.message_id, initial_card)
        
        if response.get("code") != 0:
            logger.error(f"发送占位消息失败: {response}")
            return await self._handle_sync(message, ctx, client, conversation_id)
        
        reply_message_id = response.get("data", {}).get("message_id")
        
        # 流式处理
        response_text = ""
        last_update_time = 0
        update_interval = self.stream_update_interval_ms / 1000
        
        try:
            async for event in await self.chat_service.chat(
                message=message.content,
                user_id=message.sender_id,
                conversation_id=conversation_id,
                agent_id=self.default_agent_id,
                stream=True
            ):
                event_type = event.get("type", "")
                
                if event_type == "content_delta":
                    delta = event.get("data", {}).get("delta", "")
                    response_text += delta
                    
                    # 节流更新
                    now = asyncio.get_event_loop().time()
                    if now - last_update_time >= update_interval:
                        card = FeishuCardBuilder.streaming_card(
                            response_text,
                            is_typing=True
                        )
                        await client.update_card(reply_message_id, card)
                        last_update_time = now
                
                elif event_type in ("message_stop", "done"):
                    break
            
            # 最终更新
            final_card = FeishuCardBuilder.final_card(
                title="回复",
                content=response_text
            )
            await client.update_card(reply_message_id, final_card)
            
        except Exception as e:
            logger.error(f"流式处理失败: {e}", exc_info=True)
            
            # 更新为错误卡片
            error_card = FeishuCardBuilder.error_card(
                error_type="处理中断",
                error_message=str(e)
            )
            await client.update_card(reply_message_id, error_card)
        
        return response_text
    
    def _get_conversation_id(self, chat_id: str) -> str:
        """
        获取或生成 conversation_id
        
        Args:
            chat_id: 聊天 ID
            
        Returns:
            conversation_id
        """
        if chat_id not in self._conversations:
            # 使用 chat_id 作为 conversation_id 的一部分
            self._conversations[chat_id] = f"feishu_{chat_id}"
        return self._conversations[chat_id]
    
    def set_conversation_id(self, chat_id: str, conversation_id: str) -> None:
        """设置 conversation_id 映射"""
        self._conversations[chat_id] = conversation_id
