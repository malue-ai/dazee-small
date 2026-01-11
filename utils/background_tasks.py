"""
后台任务服务 - Background Task Service

职责：
- 管理所有后台异步任务
- 对话标题生成
- 推荐问题生成
- 🆕 Mem0 用户记忆增量更新（V4.6）
- 对话摘要生成（未来扩展）
- 标签自动提取（未来扩展）

设计原则：
- 使用 core/llm 抽象层（不直接使用 anthropic）
- 集成 EventManager（SSE 推送给前端）
- 错误不影响主流程（静默失败 + 日志记录）
"""

import asyncio
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from logger import get_logger
from core.llm import create_llm_service
from core.llm.base import Message
from core.events.manager import EventManager
from utils.json_utils import extract_json_list

logger = get_logger("background_tasks")


# ==================== Mem0 更新结果数据类 ====================

@dataclass
class Mem0UpdateResult:
    """单用户 Mem0 更新结果"""
    user_id: str
    success: bool
    memories_added: int = 0
    conversations_processed: int = 0
    error: Optional[str] = None
    duration_ms: int = 0


@dataclass
class Mem0BatchUpdateResult:
    """批量 Mem0 更新结果"""
    total_users: int
    successful: int
    failed: int
    total_memories_added: int = 0
    results: List[Mem0UpdateResult] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    @property
    def duration_seconds(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0


class BackgroundTaskService:
    """
    后台任务服务
    
    统一管理所有后台任务，提供可扩展的任务接口
    
    支持任务类型：
    - 对话标题生成
    - 推荐问题生成
    - 🆕 Mem0 用户记忆增量更新（V4.6）
    """
    
    def __init__(self):
        """初始化后台任务服务"""
        # 使用 Haiku（快速、便宜，适合简单任务）
        self.llm = None  # 延迟初始化，避免启动时加载
        self._mem0_pool = None  # 🆕 Mem0 Pool 延迟初始化
        
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
            # 🆕 使用配置化的 LLM Profile
            from config.llm_config import get_llm_profile
            profile = get_llm_profile("background_task")
            self.llm = create_llm_service(**profile)
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
    
    # ==================== 🆕 Mem0 记忆增量更新（V4.6）====================
    
    def _get_mem0_pool(self):
        """懒加载 Mem0 Pool"""
        if self._mem0_pool is None:
            try:
                from core.memory.mem0 import get_mem0_pool
                self._mem0_pool = get_mem0_pool()
            except ImportError:
                logger.warning("⚠️ mem0 模块未安装，Mem0 功能不可用")
                return None
        return self._mem0_pool
    
    async def update_user_memories(
        self,
        user_id: str,
        since_hours: int = 24,
        session_id: Optional[str] = None,
        event_manager: Optional[EventManager] = None
    ) -> Mem0UpdateResult:
        """
        更新单个用户的 Mem0 记忆（后台任务）
        
        从数据库获取用户在指定时间范围内的会话，提取记忆并更新
        
        Args:
            user_id: 用户 ID
            since_hours: 处理过去多少小时的会话（默认 24）
            session_id: Session ID（用于 SSE 推送进度）
            event_manager: 事件管理器（用于 SSE 推送）
            
        Returns:
            Mem0UpdateResult 更新结果
            
        注意：
            - 此方法静默失败，不会抛出异常
            - 失败只记录日志，不影响主流程
        """
        start_time = datetime.now()
        
        try:
            logger.info(f"🧠 开始更新用户记忆: user_id={user_id}, since={since_hours}h")
            
            pool = self._get_mem0_pool()
            if not pool:
                return Mem0UpdateResult(
                    user_id=user_id,
                    success=False,
                    error="mem0 模块未安装",
                    duration_ms=self._calc_duration_ms(start_time)
                )
            
            # 获取用户会话
            since = datetime.now() - timedelta(hours=since_hours)
            conversations = await self._fetch_user_conversations(user_id, since)
            
            if not conversations:
                logger.info(f"○ 用户 {user_id} 无需更新（无符合条件的会话）")
                return Mem0UpdateResult(
                    user_id=user_id,
                    success=True,
                    memories_added=0,
                    conversations_processed=0,
                    duration_ms=self._calc_duration_ms(start_time)
                )
            
            # 提取所有消息
            all_messages = []
            for conv in conversations:
                all_messages.extend(conv.get("messages", []))
            
            if not all_messages:
                return Mem0UpdateResult(
                    user_id=user_id,
                    success=True,
                    memories_added=0,
                    conversations_processed=len(conversations),
                    duration_ms=self._calc_duration_ms(start_time)
                )
            
            # 调用 Mem0 添加记忆（在线程池中执行）
            result = await asyncio.to_thread(
                pool.add,
                user_id=user_id,
                messages=all_messages
            )
            
            memories_added = len(result.get("results", []))
            
            logger.info(
                f"✅ 用户 {user_id} 记忆更新完成: "
                f"会话数={len(conversations)}, 消息数={len(all_messages)}, "
                f"新增记忆={memories_added}"
            )
            
            # 通过 SSE 推送进度（可选）
            if session_id and event_manager:
                import json
                await event_manager.message.emit_message_delta(
                    session_id=session_id,
                    message_id=f"mem0_update_{user_id}",
                    delta={
                        "type": "mem0_update",
                        "content": json.dumps({
                            "user_id": user_id,
                            "memories_added": memories_added,
                            "conversations_processed": len(conversations)
                        }, ensure_ascii=False)
                    }
                )
            
            return Mem0UpdateResult(
                user_id=user_id,
                success=True,
                memories_added=memories_added,
                conversations_processed=len(conversations),
                duration_ms=self._calc_duration_ms(start_time)
            )
            
        except Exception as e:
            logger.warning(f"⚠️ 更新用户记忆失败: user_id={user_id}, error={str(e)}")
            return Mem0UpdateResult(
                user_id=user_id,
                success=False,
                error=str(e),
                duration_ms=self._calc_duration_ms(start_time)
            )
    
    async def batch_update_all_memories(
        self,
        since_hours: int = 24,
        max_concurrent: int = 5
    ) -> Mem0BatchUpdateResult:
        """
        批量更新所有用户的 Mem0 记忆（后台任务）
        
        典型用途：定时任务（如凌晨批量处理当天会话）
        
        Args:
            since_hours: 处理过去多少小时的会话（默认 24）
            max_concurrent: 最大并发数（默认 5）
            
        Returns:
            Mem0BatchUpdateResult 批量更新结果
            
        注意：
            - 此方法静默失败，不会抛出异常
            - 失败只记录日志，不影响主流程
        """
        batch_result = Mem0BatchUpdateResult(
            total_users=0,
            successful=0,
            failed=0,
            start_time=datetime.now()
        )
        
        try:
            logger.info(f"🚀 开始批量更新用户记忆: since={since_hours}h, max_concurrent={max_concurrent}")
            
            pool = self._get_mem0_pool()
            if not pool:
                batch_result.failed = 1
                batch_result.end_time = datetime.now()
                batch_result.results.append(Mem0UpdateResult(
                    user_id="batch",
                    success=False,
                    error="mem0 模块未安装"
                ))
                return batch_result
            
            # 获取所有用户的会话
            since = datetime.now() - timedelta(hours=since_hours)
            user_conversations = await self._fetch_all_user_conversations(since)
            
            if not user_conversations:
                logger.info(f"○ 无需更新（无符合条件的会话）")
                batch_result.end_time = datetime.now()
                return batch_result
            
            batch_result.total_users = len(user_conversations)
            
            # 使用信号量控制并发
            semaphore = asyncio.Semaphore(max_concurrent)
            
            async def update_with_limit(user_id: str, convs: List[Dict]):
                async with semaphore:
                    return await self._update_user_memories_internal(user_id, convs)
            
            # 并发执行
            tasks = [
                update_with_limit(user_id, convs)
                for user_id, convs in user_conversations.items()
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, Exception):
                    batch_result.failed += 1
                    batch_result.results.append(Mem0UpdateResult(
                        user_id="unknown",
                        success=False,
                        error=str(result)
                    ))
                elif isinstance(result, Mem0UpdateResult):
                    batch_result.results.append(result)
                    if result.success:
                        batch_result.successful += 1
                        batch_result.total_memories_added += result.memories_added
                    else:
                        batch_result.failed += 1
            
            batch_result.end_time = datetime.now()
            
            logger.info(
                f"✅ 批量更新完成: "
                f"总数={batch_result.total_users}, "
                f"成功={batch_result.successful}, "
                f"失败={batch_result.failed}, "
                f"新增记忆={batch_result.total_memories_added}, "
                f"耗时={batch_result.duration_seconds:.2f}s"
            )
            
            # 🆕 情绪聚合：为成功更新的用户生成周汇总
            await self._aggregate_weekly_summaries(
                user_ids=[r.user_id for r in batch_result.results if r.success],
                pool=pool
            )
            
            return batch_result
            
        except Exception as e:
            logger.warning(f"⚠️ 批量更新失败: {str(e)}")
            batch_result.failed = 1
            batch_result.end_time = datetime.now()
            batch_result.results.append(Mem0UpdateResult(
                user_id="batch",
                success=False,
                error=str(e)
            ))
            return batch_result
    
    async def _update_user_memories_internal(
        self,
        user_id: str,
        conversations: List[Dict[str, Any]]
    ) -> Mem0UpdateResult:
        """内部方法：更新单用户记忆（已有会话数据）"""
        start_time = datetime.now()
        
        try:
            pool = self._get_mem0_pool()
            if not pool:
                return Mem0UpdateResult(
                    user_id=user_id,
                    success=False,
                    error="mem0 模块未安装",
                    duration_ms=self._calc_duration_ms(start_time)
                )
            
            # 提取所有消息
            all_messages = []
            for conv in conversations:
                all_messages.extend(conv.get("messages", []))
            
            if not all_messages:
                return Mem0UpdateResult(
                    user_id=user_id,
                    success=True,
                    memories_added=0,
                    conversations_processed=len(conversations),
                    duration_ms=self._calc_duration_ms(start_time)
                )
            
            # 调用 Mem0 添加记忆
            result = await asyncio.to_thread(
                pool.add,
                user_id=user_id,
                messages=all_messages
            )
            
            memories_added = len(result.get("results", []))
            
            return Mem0UpdateResult(
                user_id=user_id,
                success=True,
                memories_added=memories_added,
                conversations_processed=len(conversations),
                duration_ms=self._calc_duration_ms(start_time)
            )
            
        except Exception as e:
            return Mem0UpdateResult(
                user_id=user_id,
                success=False,
                error=str(e),
                duration_ms=self._calc_duration_ms(start_time)
            )
    
    async def _fetch_user_conversations(
        self,
        user_id: str,
        since: datetime
    ) -> List[Dict[str, Any]]:
        """从数据库获取单个用户的会话"""
        try:
            from infra.database import AsyncSessionLocal, crud
            
            async with AsyncSessionLocal() as session:
                conversations = await crud.get_conversations_since(
                    session,
                    since=since,
                    user_id=user_id
                )
                
                result = []
                for conv in conversations:
                    messages = await crud.get_messages_by_conversation(
                        session,
                        conversation_id=conv.id
                    )
                    result.append({
                        "id": conv.id,
                        "created_at": conv.created_at.isoformat() if conv.created_at else None,
                        "messages": [
                            {"role": msg.role, "content": msg.content}
                            for msg in messages
                        ]
                    })
                
                return result
                
        except ImportError:
            logger.warning("⚠️ 数据库模块不可用")
            return []
        except Exception as e:
            logger.warning(f"⚠️ 获取用户会话失败: {e}")
            return []
    
    async def _fetch_all_user_conversations(
        self,
        since: datetime
    ) -> Dict[str, List[Dict[str, Any]]]:
        """从数据库获取所有用户的会话（按用户分组）"""
        try:
            from infra.database import AsyncSessionLocal, crud
            
            async with AsyncSessionLocal() as session:
                conversations = await crud.get_conversations_since(
                    session,
                    since=since
                )
                
                user_conversations: Dict[str, List[Dict[str, Any]]] = {}
                
                for conv in conversations:
                    user_id = conv.user_id
                    if not user_id:
                        continue
                    
                    messages = await crud.get_messages_by_conversation(
                        session,
                        conversation_id=conv.id
                    )
                    
                    conv_data = {
                        "id": conv.id,
                        "created_at": conv.created_at.isoformat() if conv.created_at else None,
                        "messages": [
                            {"role": msg.role, "content": msg.content}
                            for msg in messages
                        ]
                    }
                    
                    if user_id not in user_conversations:
                        user_conversations[user_id] = []
                    user_conversations[user_id].append(conv_data)
                
                return user_conversations
                
        except ImportError:
            logger.warning("⚠️ 数据库模块不可用")
            return {}
        except Exception as e:
            logger.warning(f"⚠️ 获取所有用户会话失败: {e}")
            return {}
    
    def _calc_duration_ms(self, start_time: datetime) -> int:
        """计算耗时（毫秒）"""
        return int((datetime.now() - start_time).total_seconds() * 1000)
    
    async def _aggregate_weekly_summaries(
        self,
        user_ids: List[str],
        pool
    ) -> None:
        """
        为用户生成周汇总（情绪 + 工作重点）
        
        在批量更新后调用，将聚合结果存入 Mem0
        
        Args:
            user_ids: 需要聚合的用户 ID 列表
            pool: Mem0 Pool 实例
        """
        if not user_ids:
            return
        
        try:
            from core.memory.mem0.aggregator import (
                aggregate_user_emotion,
                aggregate_work_summary,
                format_time_window
            )
            
            # 计算本周时间窗口
            today = datetime.now()
            start_of_week = today - timedelta(days=today.weekday())
            start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
            
            logger.info(f"📊 开始情绪聚合: {len(user_ids)} 个用户")
            
            for user_id in user_ids:
                try:
                    # 检索用户记忆
                    memories = pool.get_all(user_id=user_id, limit=100)
                    
                    if not memories:
                        continue
                    
                    # 聚合情绪
                    emotion_result = await aggregate_user_emotion(
                        user_id=user_id,
                        start_date=start_of_week,
                        end_date=today,
                        memories=memories
                    )
                    
                    # 聚合工作重点
                    work_result = await aggregate_work_summary(
                        user_id=user_id,
                        start_date=start_of_week,
                        end_date=today,
                        memories=memories
                    )
                    
                    # 存储情绪摘要
                    if emotion_result.get("summary") and emotion_result.get("dominant") != "neutral":
                        pool.add(
                            user_id=user_id,
                            messages=[{
                                "role": "user",
                                "content": f"[情绪摘要] {emotion_result['summary']}"
                            }],
                            metadata={
                                "type": "emotion_weekly",
                                "time_window": emotion_result.get("time_window"),
                                "dominant": emotion_result.get("dominant")
                            }
                        )
                    
                    # 存储工作摘要
                    if work_result.get("summary") and work_result.get("highlights"):
                        pool.add(
                            user_id=user_id,
                            messages=[{
                                "role": "user",
                                "content": f"[工作摘要] {work_result['summary']}"
                            }],
                            metadata={
                                "type": "work_weekly",
                                "time_window": work_result.get("time_window"),
                                "next_steps": work_result.get("next_steps", [])
                            }
                        )
                    
                    logger.debug(f"  ✓ 用户 {user_id} 聚合完成")
                    
                except Exception as e:
                    logger.warning(f"  ⚠️ 用户 {user_id} 聚合失败: {e}")
                    continue
            
            logger.info(f"✅ 情绪聚合完成")
            
        except ImportError:
            logger.debug("情绪聚合模块未加载，跳过")
        except Exception as e:
            logger.warning(f"⚠️ 情绪聚合失败: {e}")


# ==================== 便捷函数 ====================

_default_service: Optional[BackgroundTaskService] = None


def get_background_task_service() -> BackgroundTaskService:
    """获取默认后台任务服务单例"""
    global _default_service
    if _default_service is None:
        _default_service = BackgroundTaskService()
    return _default_service

