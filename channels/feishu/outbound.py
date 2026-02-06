"""
飞书 Outbound 适配器

负责消息发送
"""

from typing import Dict, Any, List, Optional, Literal
from channels.base.types import OutboundContext, DeliveryResult
from channels.feishu.types import FeishuAccount
from channels.feishu.client import FeishuClient
from channels.feishu.cards import FeishuCardBuilder
from logger import get_logger

logger = get_logger("feishu_outbound")


class FeishuOutboundAdapter:
    """
    飞书 Outbound 适配器
    
    负责发送各类消息到飞书
    """
    
    delivery_mode: Literal["direct", "gateway", "hybrid"] = "gateway"
    text_chunk_limit: int = 4000
    
    def __init__(self):
        """初始化 Outbound"""
        self._clients: Dict[str, FeishuClient] = {}
    
    def set_client(self, account_id: str, client: FeishuClient) -> None:
        """设置客户端"""
        self._clients[account_id] = client
    
    def get_client(self, ctx: OutboundContext) -> Optional[FeishuClient]:
        """获取客户端"""
        return self._clients.get(ctx.account_id)
    
    async def send_text(self, ctx: OutboundContext) -> DeliveryResult:
        """
        发送文本消息
        
        Args:
            ctx: 发送上下文
            
        Returns:
            发送结果
        """
        client = self.get_client(ctx)
        if not client:
            return DeliveryResult.fail("Client not found")
        
        try:
            # 文本分片
            chunks = self.chunker(ctx.text)
            
            message_id = None
            for i, chunk in enumerate(chunks):
                if ctx.reply_to and i == 0:
                    # 第一条回复原消息
                    response = await client.reply_text(ctx.reply_to, chunk)
                else:
                    response = await client.send_text(ctx.chat_id, chunk)
                
                if response.get("code") != 0:
                    return DeliveryResult.fail(
                        response.get("msg", "Unknown error"),
                        raw_response=response
                    )
                
                if i == 0:
                    message_id = response.get("data", {}).get("message_id")
            
            return DeliveryResult.ok(message_id, raw_response=response)
            
        except Exception as e:
            logger.error(f"发送文本失败: {e}", exc_info=True)
            return DeliveryResult.fail(str(e))
    
    async def send_card(self, ctx: OutboundContext) -> DeliveryResult:
        """
        发送卡片消息
        
        Args:
            ctx: 发送上下文
            
        Returns:
            发送结果
        """
        client = self.get_client(ctx)
        if not client:
            return DeliveryResult.fail("Client not found")
        
        try:
            card = ctx.card_data or FeishuCardBuilder.text_card("消息", ctx.text)
            
            if ctx.reply_to:
                response = await client.reply_card(ctx.reply_to, card)
            else:
                response = await client.send_card(ctx.chat_id, card)
            
            if response.get("code") != 0:
                return DeliveryResult.fail(
                    response.get("msg", "Unknown error"),
                    raw_response=response
                )
            
            message_id = response.get("data", {}).get("message_id")
            return DeliveryResult.ok(message_id, raw_response=response)
            
        except Exception as e:
            logger.error(f"发送卡片失败: {e}", exc_info=True)
            return DeliveryResult.fail(str(e))
    
    async def send_media(self, ctx: OutboundContext) -> DeliveryResult:
        """
        发送媒体消息
        
        Args:
            ctx: 发送上下文
            
        Returns:
            发送结果
        """
        client = self.get_client(ctx)
        if not client:
            return DeliveryResult.fail("Client not found")
        
        try:
            media_type = ctx.media_type or "image"
            
            # TODO: 先上传媒体获取 key，再发送
            # 暂时返回不支持
            return DeliveryResult.fail("Media upload not implemented")
            
        except Exception as e:
            logger.error(f"发送媒体失败: {e}", exc_info=True)
            return DeliveryResult.fail(str(e))
    
    async def edit_message(
        self,
        message_id: str,
        ctx: OutboundContext
    ) -> DeliveryResult:
        """
        编辑消息（流式输出用）
        
        Args:
            message_id: 消息 ID
            ctx: 发送上下文
            
        Returns:
            编辑结果
        """
        client = self.get_client(ctx)
        if not client:
            return DeliveryResult.fail("Client not found")
        
        try:
            if ctx.card_data:
                response = await client.update_card(message_id, ctx.card_data)
            else:
                response = await client.update_message(message_id, ctx.text)
            
            if response.get("code") != 0:
                return DeliveryResult.fail(
                    response.get("msg", "Unknown error"),
                    raw_response=response
                )
            
            return DeliveryResult.ok(message_id, raw_response=response)
            
        except Exception as e:
            logger.error(f"编辑消息失败: {e}", exc_info=True)
            return DeliveryResult.fail(str(e))
    
    def chunker(self, text: str, limit: int = None) -> List[str]:
        """
        文本分片
        
        Args:
            text: 原始文本
            limit: 分片限制
            
        Returns:
            分片列表
        """
        limit = limit or self.text_chunk_limit
        
        if len(text) <= limit:
            return [text]
        
        chunks = []
        current = ""
        
        # 按段落分割
        paragraphs = text.split("\n\n")
        
        for para in paragraphs:
            if len(current) + len(para) + 2 > limit:
                if current:
                    chunks.append(current.strip())
                    current = ""
                
                # 单段落超长，强制分割
                if len(para) > limit:
                    for i in range(0, len(para), limit):
                        chunks.append(para[i:i+limit])
                else:
                    current = para
            else:
                if current:
                    current += "\n\n"
                current += para
        
        if current:
            chunks.append(current.strip())
        
        return chunks
