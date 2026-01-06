"""
聊天服务层 - Chat Service

职责：
1. 提供统一的对话入口 chat()
2. 协调 Agent 执行
3. 管理 Session 生命周期

设计原则：
- chat() 是唯一入口，根据 stream 参数选择模式
- 内容累积和持久化由 EventBroadcaster 自动处理
- 数据库操作委托给 ConversationService
"""

import asyncio
import json
import time
from typing import Dict, Any, Optional, AsyncGenerator, List
from datetime import datetime
from uuid import uuid4

from logger import get_logger
from core.agent import SimpleAgent
from core.context import Context
from services.session_service import SessionService, get_session_service, SessionNotFoundError
from services.conversation_service import get_conversation_service, ConversationNotFoundError
from infra.database import AsyncSessionLocal, crud
from utils.background_tasks import get_background_task_service
from utils.message_utils import (
    normalize_message_format,
    extract_text_from_message,
)
from utils.file_processor import get_file_processor, FileCategory

logger = get_logger("chat_service")


class ChatServiceError(Exception):
    """聊天服务异常基类"""
    pass


class AgentExecutionError(ChatServiceError):
    """Agent 执行失败异常"""
    pass


class ChatService:
    """
    聊天服务
    
    使用方法：
        service = get_chat_service()
        
        # 流式模式（推荐用于 Web）
        async for event in service.chat(message, user_id, stream=True):
            yield event
        
        # 同步模式（推荐用于 API 集成）
        result = await service.chat(message, user_id, stream=False)
    """
    
    def __init__(
        self,
        session_service: Optional[SessionService] = None,
        default_model: str = "claude-sonnet-4-5-20250929"
    ):
        self.session_service = session_service or get_session_service()
        self.default_model = default_model
        
        # 其他服务
        self.conversation_service = get_conversation_service()  # 用于 Context 加载消息
        self.background_tasks = get_background_task_service()
    
    # ==================== 统一入口 ====================
    
    async def chat(
        self,
        message: Any,
        user_id: str,
        conversation_id: Optional[str] = None,
        message_id: Optional[str] = None,
        stream: bool = True,
        background_tasks: Optional[List[str]] = None,
        files: Optional[List[Dict[str, Any]]] = None
    ):
        """
        统一的对话入口 ⭐
        
        根据 stream 参数自动选择模式：
        - stream=True  → 返回 AsyncGenerator，用于 SSE
        - stream=False → 返回 Dict，用于 API 集成
        
        Args:
            message: 用户消息（任意格式，会自动标准化）
            user_id: 用户 ID
            conversation_id: 对话 ID（可选，不提供则自动创建）
            message_id: 消息 ID（可选）
            stream: 是否流式返回
            background_tasks: 需要启用的后台任务列表，如 ["title_generation"]
            files: 文件引用列表（可选），每个元素包含 file_id 或 file_url
            
        Returns:
            stream=True  → AsyncGenerator[Dict, None]
            stream=False → Dict
        """
        if stream:
            return self._chat_stream(message, user_id, conversation_id, message_id, background_tasks, files)
        else:
            return await self._chat_sync(message, user_id, conversation_id, message_id, background_tasks, files)
    
    # ==================== 内部实现 ====================
    
    async def _chat_sync(
        self,
        message: Any,
        user_id: str,
        conversation_id: Optional[str] = None,
        message_id: Optional[str] = None,
        background_tasks: Optional[List[str]] = None,
        files: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        同步模式：立即返回 task_id，Agent 在后台运行
        
        适用场景：API 集成、不需要实时反馈
        """
        try:
            # 处理文件（如果有）
            processed_message = await self._process_message_with_files(message, files)
            normalized_message = normalize_message_format(processed_message)
            logger.info(f"📨 同步对话请求: user_id={user_id}")
            
            # 确保 Conversation 存在
            is_new_conversation = False
            if not conversation_id:
                async with AsyncSessionLocal() as session:
                    conv = await crud.create_conversation(
                        session=session,
                    user_id=user_id,
                        title="新对话"
                )
                conversation_id = conv.id
                is_new_conversation = True
                logger.info(f"✅ 新对话已创建: id={conversation_id}")
            
            # 创建 Session（传入 conversation_service 用于消息持久化）
            session_id, agent = await self.session_service.create_session(
                user_id=user_id,
                message=normalized_message,
                conversation_id=conversation_id,
                message_id=message_id,
                conversation_service=self.conversation_service
            )
            
            # 启动后台任务
            asyncio.create_task(
                self._run_agent(
                    session_id=session_id,
                    agent=agent,
                    message=normalized_message,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    is_new_conversation=is_new_conversation,
                    background_tasks=background_tasks
                )
            )
            
            logger.info(f"✅ 后台任务已启动: task_id={session_id}")
            
            return {
                "task_id": session_id,
                "conversation_id": conversation_id,
                "message": "任务已启动，请轮询 /api/v1/session/{task_id} 查看结果",
                "status": "running"
            }
        
        except Exception as e:
            logger.error(f"❌ 同步对话失败: {str(e)}", exc_info=True)
            raise AgentExecutionError(f"对话启动失败: {str(e)}") from e
    
    async def _chat_stream(
        self,
        message: Any,
        user_id: str,
        conversation_id: Optional[str] = None,
        message_id: Optional[str] = None,
        background_tasks: Optional[List[str]] = None,
        files: Optional[List[Dict[str, Any]]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式模式：实时返回事件流
        
        适用场景：Web 界面、需要实时反馈
        """
        session_id = None
        try:
            # 处理文件（如果有）
            processed_message = await self._process_message_with_files(message, files)
            normalized_message = normalize_message_format(processed_message)
            message_preview = str(message)[:50] if message else ""
            logger.info(f"📨 流式对话请求: user_id={user_id}, message={message_preview}...")
            
            # 确保 Conversation 存在
            is_new_conversation = False
            if not conversation_id:
                async with AsyncSessionLocal() as session:
                    conv = await crud.create_conversation(
                        session=session,
                    user_id=user_id,
                        title="新对话"
                )
                conversation_id = conv.id
                is_new_conversation = True
                logger.info(f"✅ 新对话已创建: id={conversation_id}")
            
            # 创建 Session（传入 conversation_service 用于消息持久化）
            session_id, agent = await self.session_service.create_session(
                user_id=user_id,
                message=normalized_message,
                conversation_id=conversation_id,
                message_id=message_id,
                conversation_service=self.conversation_service
            )
            
            logger.info(f"🤖 Session 已创建: session_id={session_id}")
            
            # 发送初始事件
            redis = self.session_service.redis
            events = self.session_service.events
            
            await events.session.emit_session_start(
                session_id=session_id,
                user_id=user_id,
                conversation_id=conversation_id
            )
            
            if is_new_conversation:
                await events.conversation.emit_conversation_start(
                    session_id=session_id,
                    conversation={
                        "id": conversation_id,
                        "title": "新对话",
                        "created_at": datetime.now().isoformat(),
                        "metadata": {}
                    }
                )
            
            # 启动后台 Agent 任务
            agent_task = asyncio.create_task(
                self._run_agent(
                    session_id=session_id,
                    agent=agent,
                    message=normalized_message,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    is_new_conversation=is_new_conversation,
                    background_tasks=background_tasks
                )
            )
            
            # 🎯 使用 Pub/Sub 订阅实时事件流（更低延迟）
            try:
                async for event in redis.subscribe_events(
                    session_id=session_id,
                    after_id=0,
                    timeout=300  # 5分钟超时
                ):
                    yield event
                    
                    # 检查 Agent 任务是否异常退出
                    if agent_task.done():
                        # 注意：不需要 raise，因为 _run_agent 已经处理了错误
                        # 错误事件已经通过 Pub/Sub 发送给前端了
                        break
                
                # 确保 agent_task 完成（或已取消）
                if not agent_task.done():
                    await agent_task
            
            except asyncio.CancelledError:
                # SSE 连接被取消（用户刷新页面、切换会话等）
                # 这是正常行为，Agent 应该继续在后台运行
                logger.info(f"⚠️ SSE 连接取消，Agent 继续在后台运行: session_id={session_id}")
                
                # 🛡️ 不要取消 agent_task，让它继续运行
                # 使用 asyncio.shield 防止任务被取消
                if not agent_task.done():
                    # 创建一个后台任务来等待 agent 完成
                    async def wait_for_agent():
                        try:
                            await asyncio.shield(agent_task)
                            logger.info(f"✅ 后台 Agent 已完成: session_id={session_id}")
                        except asyncio.CancelledError:
                            logger.warning(f"⚠️ 后台 Agent 被强制取消: session_id={session_id}")
                        except Exception as e:
                            logger.error(f"❌ 后台 Agent 执行失败: {e}")
                    
                    # 启动后台等待任务（不阻塞当前函数退出）
                    asyncio.create_task(wait_for_agent())
                
                # 正常返回，不抛出异常（SSE 断开是预期行为）
                return
            
            logger.info(f"✅ 流式对话完成: session_id={session_id}")
        
        except Exception as e:
            logger.error(f"❌ 流式对话失败: {str(e)}", exc_info=True)
            if session_id:
                try:
                    await self.session_service.end_session(session_id, status="failed")
                except Exception as ex:
                    logger.warning(f"⚠️ 结束 Session 失败: {str(ex)}")
            raise AgentExecutionError(f"流式对话失败: {str(e)}") from e
    
    async def _run_agent(
        self,
        session_id: str,
        agent: SimpleAgent,
        message: List[Dict[str, str]],
        user_id: str,
        conversation_id: str,
        is_new_conversation: bool = False,
        background_tasks: Optional[List[str]] = None
    ):
        """
        执行 Agent（核心逻辑，同步和流式共用）
        
        流程：
        1. 保存用户消息
        2. 创建 Assistant 消息占位
        3. 调用 Agent.chat()
           - 内容累积由 EventBroadcaster 自动处理
           - Checkpoint 在每个 content_stop 后自动保存
           - 最终保存在 message_stop 时自动完成
        4. 完成后发送 session_end 事件
        
        Args:
            background_tasks: 需要启用的后台任务列表，如 ["title_generation"]
        """
        start_time = time.time()
        background_tasks = background_tasks or []
        
        try:
            logger.info(f"🚀 Agent 开始执行: session_id={session_id}, background_tasks={background_tasks}")
            
            redis = self.session_service.redis
            events = self.session_service.events
            
            # 生成 Assistant 消息 ID
            assistant_message_id = f"msg_{uuid4().hex[:24]}"
            
            # 1️⃣ 先保存到数据库（确保数据持久化）
            content_json = json.dumps(message, ensure_ascii=False)
            
            async with AsyncSessionLocal() as session:
                # 保存用户消息
                await crud.create_message(
                    session=session,
                    conversation_id=conversation_id,
                    role="user",
                    content=content_json,
                    metadata={"session_id": session_id, "model": self.default_model}
                )
                logger.debug(f"💾 用户消息已保存")
                
                # 创建 Assistant 消息占位（status 使用简单字符串）
                await crud.create_message(
                    session=session,
                    conversation_id=conversation_id,
                    role="assistant",
                    content="[]",
                    message_id=assistant_message_id,
                    status="processing",  # processing/completed/stopped/failed
                    metadata={
                        "session_id": session_id,
                        "model": self.default_model,
                    }
                )
                logger.info(f"✅ Assistant 占位记录已创建: id={assistant_message_id}")
            
            # 2️⃣ 数据库成功后，再发送 SSE 事件通知前端
            await events.message.emit_message_start(
                session_id=session_id,
                message_id=assistant_message_id,
                model=self.default_model
            )
            
            # 🎯 使用 Context 加载历史消息（核心上下文管理模块）
            context = Context(
                conversation_id=conversation_id,
                conversation_service=self.conversation_service
            )
            history_messages = await context.load_messages()
            logger.info(f"📚 历史消息已加载: {len(history_messages)} 条")
            
            # 🆕 初始化 broadcaster 的消息累积（内容累积和持久化由 broadcaster 自动处理）
            agent.broadcaster.start_message(session_id, assistant_message_id)
            
            # 🎯 调用 Agent.chat()
            # - 内容累积：broadcaster 自动处理 content_start/delta/stop
            # - Checkpoint：broadcaster 在每个 content_stop 后自动保存
            # - 最终保存：broadcaster 在 message_stop 时自动完成
            async for event in agent.chat(
                messages=history_messages,
                session_id=session_id,
                message_id=assistant_message_id,
                enable_stream=True
            ):
                # 检查停止标志（异步）
                if await redis.is_stopped(session_id):
                    logger.warning(f"🛑 检测到停止标志: session_id={session_id}")
                    # 强制保存当前内容
                    await agent.broadcaster._finalize_message(session_id)
                    await self.session_service.end_session(session_id, status="stopped")
                    break
                
                # 🎯 只处理需要额外逻辑的事件
                event_type = event.get("type", "")
                
                if event_type == "conversation_delta":
                    # conversation 更新同步到数据库
                    await self._handle_conversation_delta(event, conversation_id)
            
            # 计算执行时间
            duration_ms = int((time.time() - start_time) * 1000)
            
            # 检查最终状态（异步）
            final_status = await redis.get_session_status(session_id)
            status = final_status.get("status") if final_status else "completed"
            
            if status != "stopped":
                await events.session.emit_session_end(
                    session_id=session_id,
                    status="completed",
                    duration_ms=duration_ms
                )
                await self.session_service.end_session(session_id, status="completed")
                
                # 🎯 后台任务：根据 background_tasks 参数决定是否启动
                if is_new_conversation and "title_generation" in background_tasks:
                    first_message_text = extract_text_from_message(message)
                    if first_message_text:
                        asyncio.create_task(
                            self.background_tasks.generate_conversation_title(
                                conversation_id=conversation_id,
                                first_message=first_message_text,
                                session_id=session_id,
                                event_manager=events,
                                conversation_service=self.conversation_service
                            )
                        )
                        logger.info(f"🏷️ 标题生成任务已启动: conversation_id={conversation_id}")
                
                # 🆕 推荐问题生成
                if "recommended_questions" in background_tasks:
                    user_text = extract_text_from_message(message)
                    # 从 broadcaster 的 accumulator 获取 assistant 文本
                    accumulator = agent.broadcaster.get_accumulator(session_id)
                    assistant_text = ""
                    if accumulator:
                        assistant_text = extract_text_from_message(
                        accumulator.build_for_db()
                    )
                    if user_text and assistant_text:
                        asyncio.create_task(
                            self.background_tasks.generate_recommended_questions(
                                session_id=session_id,
                                message_id=assistant_message_id,
                                user_message=user_text,
                                assistant_response=assistant_text,
                                event_manager=events
                            )
                        )
                        logger.info(f"💡 推荐问题生成任务已启动: session_id={session_id}")
            
            logger.info(f"✅ Agent 执行完成: session_id={session_id}, duration={duration_ms}ms")
        
        except Exception as e:
            logger.error(f"❌ Agent 执行失败: {str(e)}", exc_info=True)
            duration_ms = int((time.time() - start_time) * 1000)
            
            # 分类错误类型，提供更友好的错误信息
            error_type = "unknown_error"
            user_message = "执行失败，请稍后重试"
            
            # 🎯 识别常见错误类型
            error_str = str(e)
            if "PermissionDeniedError" in str(type(e)) or "403" in error_str:
                error_type = "permission_denied"
                user_message = "API 权限错误，请检查 API Key 配置"
            elif "RateLimitError" in str(type(e)) or "429" in error_str:
                error_type = "rate_limit"
                user_message = "请求频率过高，请稍后重试"
            elif "AuthenticationError" in str(type(e)) or "401" in error_str:
                error_type = "authentication_error"
                user_message = "API 认证失败，请检查 API Key"
            elif "TimeoutError" in str(type(e)) or "timeout" in error_str.lower():
                error_type = "timeout"
                user_message = "请求超时，请稍后重试"
            elif "ConnectionError" in str(type(e)):
                error_type = "connection_error"
                user_message = "网络连接失败，请检查网络"
            
            # 🎯 发送详细的错误事件到前端
            try:
                await self.session_service.events.system.emit_error(
                    session_id=session_id,
                    error_type=error_type,
                    error_message=user_message,
                    details={
                        "error_class": type(e).__name__,
                        "duration_ms": duration_ms
                    }
                )
            except Exception as ex:
                logger.warning(f"⚠️ 发送错误事件失败: {str(ex)}")
            
            # 🎯 发送 session_end 事件
            try:
                await self.session_service.events.session.emit_session_end(
                    session_id=session_id,
                    status="failed",
                    duration_ms=duration_ms
                )
            except Exception as ex:
                logger.warning(f"⚠️ 发送 session_end 失败: {str(ex)}")
            
            # 🎯 更新 Session 状态
            try:
                await self.session_service.end_session(session_id, status="failed")
            except Exception as ex:
                logger.warning(f"⚠️ 结束 Session 失败: {str(ex)}")
            
            # ⚠️ 不要 raise，避免 "Task exception was never retrieved"
            # 异常已经通过事件和日志记录，不需要传播
    
    async def _handle_conversation_delta(
        self,
        event: Dict[str, Any],
        conversation_id: str
    ) -> None:
        """
        处理 conversation_delta 事件，同步到数据库
        
        Args:
            event: conversation_delta 事件
            conversation_id: 对话 ID
            
        支持的字段：
            {"title": "新标题"}
            {"metadata": {...}}
        """
        try:
            data = event.get("data", {})
            
            # 直接检查字段名
            if "title" in data:
                await self.conversation_service.update_conversation(
                    conversation_id=conversation_id,
                    title=data["title"]
                )
                logger.info(f"📝 Conversation 标题已更新: {data['title']}")
                
            if "metadata" in data:
                await self.conversation_service.update_conversation(
                    conversation_id=conversation_id,
                    metadata=data["metadata"]
                )
                logger.info(f"📝 Conversation metadata 已更新")
                
        except Exception as e:
            logger.warning(f"⚠️ 处理 conversation_delta 失败: {str(e)}")
    
    def _extract_text_from_content_blocks(
        self,
        content_blocks: List[Dict[str, Any]]
    ) -> str:
        """
        从 content_blocks 中提取纯文本
        
        Args:
            content_blocks: content blocks 列表
            
        Returns:
            合并后的纯文本
        """
        texts = []
        for block in content_blocks:
            block_type = block.get("type")
            if block_type == "text":
                text = block.get("text", "")
                if text:
                    texts.append(text)
        return "\n".join(texts)
    
    async def _process_message_with_files(
        self,
        message: Any,
        files: Optional[List[Dict[str, Any]]]
    ) -> Any:
        """
        处理文件并合并到消息中
        
        文件处理策略：
        - 图片 (image/*) → 作为 ImageBlock 传给 LLM
        - 纯文本 (text/*) → 读取内容拼进消息
        - 复杂文档 (PDF等) → 生成 URL，让 Agent 决定如何处理
        
        Args:
            message: 原始用户消息
            files: 文件引用列表
            
        Returns:
            处理后的消息（可能是字符串或 content blocks 列表）
        """
        if not files:
            return message
        
        try:
            processor = get_file_processor()
            processed_files = await processor.process_files(files)
            
            if not processed_files:
                return message
            
            logger.info(f"📎 处理了 {len(processed_files)} 个文件")
            
            # 获取原始消息文本
            if isinstance(message, str):
                original_text = message
            elif isinstance(message, list):
                # 已经是 content blocks 格式
                original_text = ""
                for block in message:
                    if isinstance(block, dict) and block.get("type") == "text":
                        original_text += block.get("text", "")
            else:
                original_text = str(message)
            
            # 使用 FileProcessor 构建 content blocks
            content_blocks = processor.build_message_content(processed_files, original_text)
            
            return content_blocks
            
        except Exception as e:
            logger.error(f"❌ 处理文件失败: {str(e)}", exc_info=True)
            # 文件处理失败，返回原始消息，不影响对话
            return message


# ==================== 便捷函数 ====================

_default_service: Optional[ChatService] = None


def get_chat_service(
    session_service: Optional[SessionService] = None,
    default_model: str = "claude-sonnet-4-5-20250929"
) -> ChatService:
    """获取默认聊天服务单例"""
    global _default_service
    if _default_service is None:
        _default_service = ChatService(
            session_service=session_service,
            default_model=default_model
        )
    return _default_service
