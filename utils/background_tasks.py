"""
后台任务服务 - Background Task Service

职责：
- 管理所有后台异步任务
- 对话标题生成
- 推荐问题生成
- 对话摘要生成（未来扩展）
- 标签自动提取（未来扩展）

设计原则：
- 使用 core/llm 抽象层（不直接使用 anthropic）
- 集成 EventManager（SSE 推送给前端）
- 错误不影响主流程（静默失败 + 日志记录）
"""

from typing import Optional, Dict, Any, List
from logger import get_logger
from core.llm import create_llm_service
from core.llm.base import Message
from core.events.manager import EventManager
from utils.json_utils import extract_json_list

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

        self.recommended_questions_prompt = """基于以下对话内容，生成3个用户可能想要继续问的相关问题。

要求：
- 生成3个问题
- 每个问题不超过25个字
- 问题要与对话主题相关且有价值
- 问题要能引导深入探讨
- 使用中文
- 返回 JSON 格式

对话内容：
用户：{user_message}
助手：{assistant_response}

请返回以下 JSON 格式：
```json
{{"questions": ["问题1", "问题2", "问题3"]}}
```"""
    
    def _get_llm(self):
        """懒加载 LLM 服务"""
        if self.llm is None:
            self.llm = create_llm_service(
                model="claude-haiku-4-5-20251001",
                enable_thinking=False,
            )
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
            
            # 5. 通过 SSE 推送给前端
            if session_id and event_manager:
                await event_manager.conversation.emit_conversation_delta(
                    session_id=session_id,
                    conversation_id=conversation_id,
                    delta={"title": title}
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
            
            # 调用 LLM
            response = await llm.create_message_async(
                messages=[Message(role="user", content=prompt)],
            )
            
            # 提取标题（LLMResponse.content 是字符串）
            if response and response.content:
                return response.content.strip()
            
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
    
    # ==================== 推荐问题生成 ====================
    
    async def generate_recommended_questions(
        self,
        session_id: str,
        message_id: str,
        user_message: str,
        assistant_response: str,
        event_manager: Optional[EventManager] = None
    ) -> Optional[List[str]]:
        """
        生成推荐问题（后台任务）
        
        根据对话内容生成用户可能感兴趣的后续问题，
        通过 SSE 推送到前端显示在消息底部
        
        Args:
            session_id: Session ID（用于 SSE 推送）
            message_id: 消息 ID
            user_message: 用户的消息
            assistant_response: 助手的回复
            event_manager: 事件管理器（用于 SSE 推送）
            
        Returns:
            推荐问题列表（成功），或 None（失败）
            
        注意：
            - 此方法静默失败，不会抛出异常
            - 失败只记录日志，不影响主流程
        """
        try:
            logger.info(f"💡 开始生成推荐问题: session_id={session_id}, message_id={message_id}")
            
            # 1. 截取内容（避免过长）
            user_preview = user_message[:300] if len(user_message) > 300 else user_message
            assistant_preview = assistant_response[:500] if len(assistant_response) > 500 else assistant_response
            
            # 2. 使用 LLM 生成推荐问题
            questions = await self._generate_questions_with_llm(user_preview, assistant_preview)
            
            if not questions:
                logger.warning("⚠️ LLM 返回空的推荐问题")
                return None
            
            logger.info(f"✅ 推荐问题已生成: {len(questions)} 个")
            
            # 3. 通过 SSE 推送给前端（使用通用 message_delta）
            if session_id and event_manager:
                import json
                await event_manager.message.emit_message_delta(
                    session_id=session_id,
                    message_id=message_id,
                    delta={
                        "type": "recommended",
                        "content": json.dumps({"questions": questions}, ensure_ascii=False)
                    }
                )
                logger.info(f"📤 推荐问题已推送到前端")
            
            return questions
        
        except Exception as e:
            # 静默失败，只记录日志
            logger.warning(f"⚠️ 生成推荐问题失败: {str(e)}")
            return None
    
    async def _generate_questions_with_llm(
        self,
        user_message: str,
        assistant_response: str
    ) -> Optional[List[str]]:
        """
        使用 LLM 生成推荐问题
        
        Args:
            user_message: 用户消息
            assistant_response: 助手回复
            
        Returns:
            问题列表，或 None（失败时）
        """
        try:
            llm = self._get_llm()
            
            # 构建提示词
            prompt = self.recommended_questions_prompt.format(
                user_message=user_message,
                assistant_response=assistant_response
            )
            
            # 调用 LLM
            response = await llm.create_message_async(
                messages=[Message(role="user", content=prompt)],
            )
            
            # 提取问题（使用 JSON 提取器）
            if response and hasattr(response, 'content') and response.content:
                for block in response.content:
                    if hasattr(block, 'text'):
                        raw_text = block.text.strip()
                        
                        # 使用 JSON 提取器
                        questions = extract_json_list(raw_text, key="questions")
                        
                        if questions:
                            # 清理和限制长度
                            cleaned = []
                            for q in questions[:3]:
                                q = q.strip().strip('"\'「」『』')
                                if len(q) > 30:
                                    q = q[:27] + "..."
                                if q:
                                    cleaned.append(q)
                            return cleaned
                        
                        # JSON 提取失败，回退到逐行解析
                        logger.debug("JSON 提取失败，回退到逐行解析")
                        return self._parse_questions_fallback(raw_text)
            
            return None
        
        except Exception as e:
            logger.error(f"❌ LLM 生成推荐问题失败: {str(e)}", exc_info=True)
            return None
    
    def _parse_questions_fallback(self, raw_text: str) -> List[str]:
        """
        回退方案：逐行解析 LLM 返回的问题文本
        
        Args:
            raw_text: LLM 返回的原始文本
            
        Returns:
            清理后的问题列表
        """
        import re
        questions = []
        
        for line in raw_text.split('\n'):
            line = line.strip()
            
            if not line:
                continue
            
            # 去除常见的编号格式
            line = re.sub(r'^[\d]+[.、)\]]\s*', '', line)
            line = re.sub(r'^[-•·]\s*', '', line)
            line = line.strip().strip('"\'「」『』')
            
            if len(line) > 30:
                line = line[:27] + "..."
            
            if line and not line.startswith('{') and not line.startswith('['):
                questions.append(line)
        
        return questions[:3]


# ==================== 便捷函数 ====================

_default_service: Optional[BackgroundTaskService] = None


def get_background_task_service() -> BackgroundTaskService:
    """获取默认后台任务服务单例"""
    global _default_service
    if _default_service is None:
        _default_service = BackgroundTaskService()
    return _default_service

