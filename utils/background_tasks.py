"""
后台任务服务 - Background Task Service

职责：
- 管理所有后台异步任务
- 对话标题生成
- 对话摘要生成（未来扩展）
- 标签自动提取（未来扩展）

设计原则：
- 使用 core/llm 抽象层（不直接使用 anthropic）
- 集成 EventManager（SSE 推送给前端）
- 错误不影响主流程（静默失败 + 日志记录）
"""

from typing import Optional, Dict, Any
from logger import get_logger
from core.llm import create_llm_service
from core.llm.base import Message
from core.events.manager import EventManager

logger = get_logger("background_tasks")


class BackgroundTaskService:
    """
    后台任务服务
    
    统一管理所有后台任务，提供可扩展的任务接口
    """
    
    def __init__(self):
        """初始化后台任务服务"""
        # 使用 Haiku（快速、便宜，适合简单任务）
        self.llm = None  # 延迟初始化，避免启动时加载
        self.title_generation_prompt = """请为以下对话内容生成一个简短的中文标题。

要求：
- 不超过15个字
- 不要加引号、书名号等标点符号
- 简洁明了，概括对话主题
- 只返回标题文本，不要任何其他内容

对话内容：
{message}

标题："""
    
    def _get_llm(self):
        """懒加载 LLM 服务"""
        if self.llm is None:
            self.llm = create_llm_service(model="claude-3-5-haiku-latest")
        return self.llm
    
    async def generate_conversation_title(
        self,
        conversation_id: str,
        first_message: str,
        session_id: Optional[str] = None,
        event_manager: Optional[EventManager] = None,
        conversation_service = None
    ) -> Optional[str]:
        """
        生成对话标题（后台任务）
        
        流程：
        1. 使用 LLM 生成标题
        2. 更新数据库（ConversationService）
        3. 通过 SSE 推送给前端（EventManager）
        
        Args:
            conversation_id: 对话 ID
            first_message: 第一条用户消息
            session_id: Session ID（用于 SSE 推送）
            event_manager: 事件管理器（用于 SSE 推送）
            conversation_service: 对话服务（用于数据库更新）
            
        Returns:
            生成的标题（成功），或 None（失败）
            
        注意：
            - 此方法静默失败，不会抛出异常
            - 失败只记录日志，不影响主流程
        """
        try:
            logger.info(f"🏷️ 开始生成对话标题: conversation_id={conversation_id}")
            
            # 1. 截取消息前 200 字符
            message_preview = first_message[:200] if len(first_message) > 200 else first_message
            
            # 2. 使用 core/llm 生成标题
            title = await self._generate_title_with_llm(message_preview)
            
            if not title:
                logger.warning(f"⚠️ LLM 返回空标题")
                return None
            
            # 3. 清理标题（去除引号、标点等）
            title = self._clean_title(title)
            
            logger.info(f"✅ 标题已生成: {title}")
            
            # 4. 更新数据库
            if conversation_service:
                await conversation_service.update_conversation(
                    conversation_id=conversation_id,
                    title=title
                )
                logger.info(f"💾 数据库已更新")
            
            # 5. 通过 SSE 推送给前端（使用专用事件类型）
            if session_id and event_manager:
                await event_manager.conversation.emit_conversation_title_update(
                    session_id=session_id,
                    conversation_id=conversation_id,
                    title=title
                )
                logger.info(f"📤 标题更新事件已推送到前端: {title}")
            
            return title
        
        except Exception as e:
            # 静默失败，只记录日志
            logger.warning(f"⚠️ 生成对话标题失败: {str(e)}")
            return None
    
    async def _generate_title_with_llm(self, message: str) -> Optional[str]:
        """
        使用 LLM 生成标题
        
        Args:
            message: 消息内容
            
        Returns:
            生成的标题，或 None（失败时）
        """
        try:
            llm = self._get_llm()
            
            # 构建提示词
            prompt = self.title_generation_prompt.format(message=message)
            
            # 调用 LLM（使用 create_message_async 方法）
            # 注意：create_message_async 需要 Message 对象列表，不是字典
            response = await llm.create_message_async(
                messages=[Message(role="user", content=prompt)],
                max_tokens=50,
                temperature=0.7
            )
            
            # 提取标题
            if response and hasattr(response, 'content') and response.content:
                # response.content 是 list[ContentBlock]
                for block in response.content:
                    if hasattr(block, 'text'):
                        return block.text.strip()
            
            return None
        
        except Exception as e:
            logger.error(f"❌ LLM 生成标题失败: {str(e)}", exc_info=True)
            return None
    
    def _clean_title(self, title: str) -> str:
        """
        清理标题（去除引号、标点等）
        
        Args:
            title: 原始标题
            
        Returns:
            清理后的标题
        """
        # 去除常见的引号和标点
        title = title.strip('"\'「」『』【】《》""''')
        
        # 限制长度
        if len(title) > 20:
            title = title[:17] + "..."
        
        return title


# ==================== 便捷函数 ====================

_default_service: Optional[BackgroundTaskService] = None


def get_background_task_service() -> BackgroundTaskService:
    """获取默认后台任务服务单例"""
    global _default_service
    if _default_service is None:
        _default_service = BackgroundTaskService()
    return _default_service

