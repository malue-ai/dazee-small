"""
聊天服务层 - Chat Service

职责：
1. 对话执行（同步和流式）
2. 消息数据库持久化
3. 事件流管理
4. 结果改进（HITL）

设计原则：
- 专注于聊天对话业务逻辑
- 依赖 SessionService 管理 Session
- 封装 Agent 交互逻辑
- 支持 SSE 断线重连
"""

import asyncio
from typing import Dict, Any, Optional, AsyncGenerator, List
from datetime import datetime
from uuid import uuid4

from logger import get_logger
from core.agent import SimpleAgent
from services.session_service import SessionService, get_session_service, SessionNotFoundError
from utils.db_service import MessageService, ConversationService

logger = get_logger("chat_service")


class ChatServiceError(Exception):
    """聊天服务异常基类"""
    pass


class ConversationNotFoundError(ChatServiceError):
    """对话不存在异常"""
    pass


class AgentExecutionError(ChatServiceError):
    """Agent 执行失败异常"""
    pass


class ChatService:
    """
    聊天服务
    
    提供对话执行、消息持久化等业务逻辑
    """
    
    def __init__(
        self,
        session_service: Optional[SessionService] = None,
        default_model: str = "claude-sonnet-4-5-20250929"
    ):
        """
        初始化聊天服务
        
        Args:
            session_service: Session 服务（可选，默认使用单例）
            default_model: 默认 LLM 模型
        """
        self.session_service = session_service or get_session_service()
        self.default_model = default_model
    
    # ==================== 对话执行 ====================
    
    async def chat_sync(
        self,
        message: str,
        user_id: str,
        conversation_id: Optional[str] = None,
        message_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        同步对话执行（立即返回 session_id）
        
        **新设计**：
        - 创建 Session 后立即返回 session_id
        - Agent 在后台运行
        - 客户端通过轮询 /session/{id}/status 查询进度
        - 客户端通过 /session/{id}/events 获取最终结果
        
        Args:
            message: 用户消息
            user_id: 用户 ID（必填）
            conversation_id: 对话 ID（可选）
            message_id: 消息 ID（可选）
            verbose: 是否输出详细日志
            
        Returns:
            {
                "session_id": str,
                "conversation_id": str,
                "message": str,  # 提示信息
                "status": "running"
            }
            
        Raises:
            AgentExecutionError: Agent 启动失败
        """
        try:
            logger.info(f"📨 同步对话请求: user_id={user_id}, message={message[:50]}...")
            
            # 🎯 确保 Conversation 存在
            if not conversation_id:
                conversation_id = f"conv_{uuid4().hex[:24]}"
                logger.info(f"📝 未提供 conversation_id，自动创建: {conversation_id}")
            
            # 创建 Session
            session_id, agent = await self.session_service.create_session(
                user_id=user_id,
                message=message,
                conversation_id=conversation_id,
                message_id=message_id
            )
            
            logger.info(f"🤖 Session 已创建: session_id={session_id}")
            
            # 🎯 启动后台任务（与流式模式相同，只是前端接收方式不同）
            # Agent 仍然会写入 Redis 事件和数据库
            # 区别：前端不使用 SSE，而是轮询数据库 API
            asyncio.create_task(
                self._run_agent_background(
                    session_id=session_id,
                    agent=agent,
                    message=message,
                    user_id=user_id,
                    conversation_id=conversation_id
                )
            )
            
            logger.info(f"✅ 后台任务已启动，立即返回 task_id (session_id)")
            
            # 立即返回 task_id（就是 session_id）
            return {
                "task_id": session_id,  # task_id 就是 session_id
                "conversation_id": conversation_id,
                "message": "任务已启动，请轮询 /api/v1/session/{task_id} 查看结果",
                "status": "running"
            }
        
        except Exception as e:
            logger.error(f"❌ 启动同步对话失败: {str(e)}", exc_info=True)
            raise AgentExecutionError(f"对话启动失败: {str(e)}") from e
    
    async def chat_stream(
        self,
        message: str,
        user_id: str,
        conversation_id: Optional[str] = None,
        message_id: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式对话执行（支持 SSE 断线重连）
        
        **设计原则**：
        - Session 创建后立即发送 session_start 和 conversation_start 事件
        - Agent 在后台任务中执行，独立于 SSE 连接
        - 所有事件写入 Redis 缓冲区
        - SSE 从 Redis 读取事件流
        - SSE 断开不影响 Agent 执行
        
        Args:
            message: 用户消息
            user_id: 用户 ID（必填）
            conversation_id: 对话 ID（可选，如果不提供则自动创建）
            message_id: 消息 ID（可选）
            verbose: 是否输出详细日志
            
        Yields:
            事件流 {
                "id": int,          # 事件 ID
                "type": str,
                "data": dict,
                "timestamp": str
            }
            
        Raises:
            AgentExecutionError: Agent 执行失败
        """
        session_id = None
        try:
            logger.info(f"📨 流式对话请求: user_id={user_id}, message={message[:50]}...")
            
            # 🎯 第1步：确保 Conversation 存在（如果没有提供则创建）
            if not conversation_id:
                # 自动生成 conversation_id
                conversation_id = f"conv_{uuid4().hex[:24]}"
                logger.info(f"📝 未提供 conversation_id，自动创建: {conversation_id}")
            
            # 获取或创建 Conversation
            conversation_data = await self._get_or_create_conversation(
                conversation_id=conversation_id,
                user_id=user_id
            )
            logger.info(f"✅ Conversation 已就绪: id={conversation_data['id']}")
            
            # 🎯 第2步：创建 Session
            session_id, agent = await self.session_service.create_session(
                user_id=user_id,
                message=message,
                conversation_id=conversation_id,
                message_id=message_id
            )
            
            # 输出会话状态
            self.session_service.log_session_status(session_id, conversation_id)
            
            logger.info(f"🤖 Session 已创建: session_id={session_id}")
            
            # 🎯 第3步：立即发送 session_start 和 conversation_start 事件（在启动 Agent 之前）
            redis = self.session_service.redis
            events = self.session_service.events
            
            # 发送 session_start 事件
            await events.session.emit_session_start(
                session_id=session_id,
                user_id=user_id,
                conversation_id=conversation_id
            )
            logger.info(f"📤 已发送 session_start 事件")
            
            # 发送 conversation_start 事件
            await events.conversation.emit_conversation_start(
                session_id=session_id,
                conversation=conversation_data
            )
            logger.info(f"📤 已发送 conversation_start 事件")
            
            # 🎯 第4步：启动后台任务执行 Agent（现在才开始）
            agent_task = asyncio.create_task(
                self._run_agent_background(
                    session_id=session_id,
                    agent=agent,
                    message=message,
                    user_id=user_id,
                    conversation_id=conversation_id
                )
            )
            
            # 🎯 第5步：从 Redis 读取事件流并推送给前端
            # 即使 SSE 断开，Agent 仍在后台运行
            last_event_id = 0
            
            while True:
                # 从 Redis 获取新事件（after_id > last_event_id）
                events_list = redis.get_events(
                    session_id=session_id,
                    after_id=last_event_id,
                    limit=100
                )
                
                # 推送事件
                for event in events_list:
                    yield event
                    last_event_id = event["id"]
                
                # 检查 Agent 是否完成
                session_status = redis.get_session_status(session_id)
                if session_status and session_status.get("status") in ["completed", "failed"]:
                    logger.info(f"✅ Agent 执行完成: session_id={session_id}, status={session_status.get('status')}")
                    break
                
                # 检查 Agent 任务是否异常
                if agent_task.done():
                    try:
                        agent_task.result()  # 检查是否有异常
                    except Exception as e:
                        logger.error(f"❌ Agent 后台任务异常: {str(e)}")
                        raise
                    break
                
                # 等待一小段时间再查询（避免过度轮询）
                await asyncio.sleep(0.1)
            
            # 输出完成状态
            logger.info(f"✅ 流式对话完成: session_id={session_id}")
        
        except asyncio.CancelledError:
            # SSE 连接被客户端取消（正常情况：用户刷新页面）
            logger.warning(f"⚠️ SSE 连接已取消: session_id={session_id}，Agent 继续在后台运行")
            # 不抛出异常，让 Agent 继续执行
            raise
        
        except Exception as e:
            logger.error(f"❌ 流式对话执行失败: {str(e)}", exc_info=True)
            
            # 结束 Session（失败）
            if session_id:
                try:
                    self.session_service.end_session(session_id, status="failed")
                except:
                    pass
            
            raise AgentExecutionError(f"流式对话执行失败: {str(e)}") from e
    
    async def _run_agent_background(
        self,
        session_id: str,
        agent: SimpleAgent,
        message: str,
        user_id: str,
        conversation_id: str
    ):
        """
        统一的后台 Agent 执行逻辑（两种模式共用）
        
        架构说明：
        1. 流式模式 (stream=true)：
           - 前端通过 SSE 实时接收事件（从 Redis 读取）
           - chat_stream() 启动此方法后，从 Redis 推送事件到前端
        
        2. 同步模式 (stream=false)：
           - 前端轮询 /session/{id}/status 查询进度
           - 事件仍写入 Redis（但前端不消费）
           - 前端从数据库读取最终结果
        
        核心原则：
        - Agent 执行逻辑完全相同
        - 事件写入 Redis（EventManager）
        - 结果写入数据库（Message 表）
        - 区别只在前端如何获取信息
        
        Args:
            session_id: Session ID
            agent: Agent 实例
            message: 用户消息
            user_id: 用户ID
            conversation_id: 对话ID（必填）
        """
        try:
            logger.info(f"🚀 Agent 后台任务启动: session_id={session_id}")
            
            redis = self.session_service.redis
            events = self.session_service.events
            
            # 🎯 获取或创建 Conversation
            conversation_data = await self._get_or_create_conversation(
                conversation_id=conversation_id,
                user_id=user_id
            )
            logger.info(f"✅ Conversation 已就绪: id={conversation_data['id']}")
            
            # 🎯 第1个事件（后台）：message_start（符合 Claude API 标准）
            await events.message.emit_message_start(
                session_id=session_id,
                message_id=f"msg_{session_id}",
                model=self.default_model
            )
            logger.debug(f"📤 已发送 message_start 事件")
            
            # 🎯 保存用户消息到数据库
            await self._save_user_message(
                        conversation_id=conversation_id,
                message=message,
                session_id=session_id,
                user_id=user_id
            )
            
            # 🆕 加载历史消息（Service 层负责数据库操作）
            history_messages = await self._load_history_messages(conversation_id)
            logger.info(f"📚 历史消息已加载: {len(history_messages)} 条")
            
            # 🎯 第2+个事件：来自 Agent 的事件（已写入 Redis）
            assistant_content = ""  # 累积 Assistant 的回复内容
            
            # 🔑 关键：调用 agent.chat()（统一入口）
            # enable_stream=True 表示 Agent 内部使用流式LLM调用
            # 所有事件都会通过 EventManager 写入 Redis
            async for event in agent.chat(
                user_input=message,
                history_messages=history_messages,
                session_id=session_id,
                enable_stream=True  # Agent 内部使用流式 LLM 调用
            ):
                # ✅ 事件已经由 EventManager 写入 Redis
                # 不需要 yield，因为 SSE 会从 Redis 读取
                
                # 累积 Assistant 的回复内容（用于保存到数据库）
                if event["type"] == "content_delta":
                    # 处理新的 content_delta 格式
                    delta_data = event["data"].get("delta", {})
                    if delta_data.get("type") == "text":
                        assistant_content += delta_data.get("text", "")
                
                # 更新 Session 状态（进度）
                if event["type"] == "turn_complete" or event["type"] == "complete":
                    turn_count = event["data"].get("turn", event["data"].get("turns", 0))
                    redis.update_session_status(
                        session_id=session_id,
                        updates={"total_turns": turn_count}
                    )
            
            # 🎯 保存 Assistant 消息到数据库
            await self._save_assistant_message_content(
                        conversation_id=conversation_id,
                        content=assistant_content,
                session_id=session_id,
                agent=agent
            )
            
            # 执行完成，结束 Session
            self.session_service.end_session(session_id, status="completed")
            
            logger.info(f"✅ Agent 后台任务完成: session_id={session_id}, conversation_id={conversation_id}")
        
        except Exception as e:
            logger.error(f"❌ Agent 后台任务失败: session_id={session_id}, error={str(e)}", exc_info=True)
            
            # 结束 Session（失败）
            try:
                self.session_service.end_session(session_id, status="failed")
            except:
                pass
            
            raise
    
    async def refine_result(
        self,
        session_id: str,
        original_query: str,
        previous_result: str,
        user_feedback: str
    ) -> Dict[str, Any]:
        """
        改进结果（HITL - Human-in-the-Loop）
        
        Args:
            session_id: 会话ID
            original_query: 原始查询
            previous_result: 之前的结果
            user_feedback: 用户反馈
            
        Returns:
            改进后的结果
            
        Raises:
            SessionNotFoundError: 会话不存在
            AgentExecutionError: 改进失败
        """
        try:
            logger.info(f"🔧 改进结果请求: session_id={session_id}")
            
            # 获取 Agent
            agent = self.session_service.get_agent(session_id)
            
            # 执行改进
            result = await agent.refine(
                original_query=original_query,
                previous_result=previous_result,
                user_feedback=user_feedback
            )
            
            # 提取执行信息
            session_log = result.get("session_log", {})
            tool_calls_detail = self._extract_tool_calls(session_log)
            intent_analysis = session_log.get("intent_recognition")
            
            logger.info(f"✅ 改进完成: status={result.get('status')}")
            
            return {
                "session_id": session_id,
                "final_result": result.get("final_result", ""),
                "status": result.get("status", "unknown"),
                "turns": result.get("turns", 0),
                "plan": agent.get_plan(),
                "progress": agent.get_progress(),
                "invocation_stats": result.get("invocation_stats"),
                "routing_decisions": result.get("routing_decisions", []),
                "tool_calls": tool_calls_detail,
                "intent_analysis": intent_analysis
            }
        
        except SessionNotFoundError:
            raise
        except Exception as e:
            logger.error(f"❌ 改进失败: {str(e)}", exc_info=True)
            raise AgentExecutionError(f"改进失败: {str(e)}") from e
    
    # ==================== 辅助方法 ====================
    
    async def _load_history_messages(
        self,
        conversation_id: str
    ) -> List[Dict[str, str]]:
        """
        从数据库加载历史消息（用于传递给 Agent）
        
        Args:
            conversation_id: 对话 ID
            
        Returns:
            消息列表，格式: [{"role": "user", "content": "..."}, ...]
        """
        try:
            # 1. 检查是否有压缩信息
            conversation = await ConversationService.get_conversation(conversation_id)
            compression_info = None
            
            if conversation and conversation.metadata:
                import json
                metadata = json.loads(conversation.metadata) if isinstance(conversation.metadata, str) else conversation.metadata
                compression_info = metadata.get("compression")
            
            # 2. 加载所有消息
            db_messages = await MessageService.get_conversation_messages(conversation_id)
            
            if not db_messages:
                logger.debug(f"没有找到历史消息: conversation_id={conversation_id}")
                return []
            
            # 3. 如果有压缩信息，应用压缩替换
            if compression_info:
                from_message_id = compression_info.get("from_message_id")
                summary = compression_info.get("summary")
                
                if from_message_id and summary:
                    # 找到压缩点
                    compress_index = -1
                    for i, msg in enumerate(db_messages):
                        if msg.id == from_message_id:
                            compress_index = i
                            break
                    
                    if compress_index != -1:
                        # 返回：摘要 + 压缩点之后的消息
                        history = [
                            {"role": "system", "content": f"[历史对话摘要]\n{summary}"}
                        ]
                        
                        # 添加压缩点之后的消息
                        for msg in db_messages[compress_index + 1:]:
                            content = msg.content
                            # 处理 JSON 格式的 content
                            if isinstance(content, str):
                                try:
                                    import json
                                    content_array = json.loads(content)
                                    if isinstance(content_array, list):
                                        text_parts = [
                                            block.get("text", "")
                                            for block in content_array
                                            if block.get("type") == "text"
                                        ]
                                        content = "\n".join(text_parts)
                                except json.JSONDecodeError:
                                    pass
                            
                            history.append({"role": msg.role, "content": content})
                        
                        logger.info(
                            f"📦 应用压缩: {len(db_messages)} 条消息 → "
                            f"1 条摘要 + {len(history)-1} 条完整消息"
                        )
                        return history
            
            # 4. 无压缩：返回所有消息
            history = []
            for msg in db_messages:
                content = msg.content
                # 处理 JSON 格式的 content
                if isinstance(content, str):
                    try:
                        import json
                        content_array = json.loads(content)
                        if isinstance(content_array, list):
                            text_parts = [
                                block.get("text", "")
                                for block in content_array
                                if block.get("type") == "text"
                            ]
                            content = "\n".join(text_parts)
                    except json.JSONDecodeError:
                        pass
                
                history.append({"role": msg.role, "content": content})
            
            logger.info(f"📚 加载历史消息: {len(history)} 条")
            return history
        
        except Exception as e:
            logger.error(f"❌ 加载历史消息失败: {str(e)}", exc_info=True)
            return []
    
    async def _get_or_create_conversation(
        self,
        conversation_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        获取或创建 Conversation
        
        Args:
            conversation_id: Conversation ID
            user_id: 用户ID
            
        Returns:
            Conversation 数据
        """
        conversation_data = {"id": conversation_id}
        
        try:
            # 查询数据库中的 Conversation
            conv = await ConversationService.get_conversation(conversation_id)
            
            if not conv:
                # 如果不存在，自动创建（使用前端提供的 conversation_id）
                logger.info(f"📝 Conversation 不存在，自动创建: {conversation_id}")
                
                conv = await ConversationService.create_conversation(
                    user_id=user_id,
                    id=conversation_id,  # 使用前端提供的 ID
                    title="新对话",
                    metadata={}
                )
                logger.info(f"✅ Conversation 创建成功: id={conv.id}")
            
            # 构建完整的 conversation 数据
            conversation_data = {
                "id": conv.id,
                "user_id": conv.user_id,
                "title": conv.title,
                "created_at": conv.created_at.isoformat() if conv.created_at else None,
                "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
                "metadata": conv.metadata or {}
            }
        except Exception as e:
            logger.warning(f"⚠️ 处理 Conversation 失败: {str(e)}", exc_info=True)
            # 失败时只返回基本信息
            conversation_data = {"id": conversation_id}
        
        return conversation_data
    
    async def _save_user_message(
        self,
        conversation_id: str,
        message: str,
        session_id: str,
        user_id: str
    ) -> None:
        """
        保存用户消息到数据库
        
        Args:
            conversation_id: Conversation ID（必填）
            message: 用户消息
            session_id: Session ID
            user_id: 用户ID
        """
        try:
            await MessageService.create_message(
                conversation_id=conversation_id,
                role="user",
                content=message,
                metadata={
                    "session_id": session_id,
                    "message_type": "message",
                    "model": self.default_model
                }
            )
            logger.debug(f"💾 用户消息已保存到数据库: conversation_id={conversation_id}")
        except Exception as e:
            logger.warning(f"⚠️ 保存用户消息失败: {str(e)}")
    
    async def _save_assistant_message(
        self,
        conversation_id: Optional[str],
        result: Dict[str, Any],
        session_id: str
    ) -> None:
        """
        保存 Assistant 消息到数据库（从 result 提取）
        
        Args:
            conversation_id: Conversation ID（可选）
            result: Agent 执行结果
            session_id: Session ID
        """
        if not conversation_id or not result.get("final_result"):
            return
        
        try:
            # 提取 token 使用统计
            usage_stats = {}
            if result.get("invocation_stats"):
                stats = result["invocation_stats"]
                usage_stats = {
                    "input_tokens": stats.get("total_input_tokens", 0),
                    "output_tokens": stats.get("total_output_tokens", 0)
                }
            
            await MessageService.create_message(
                conversation_id=conversation_id,
                role="assistant",
                content=result["final_result"],
                metadata={
                    "session_id": session_id,
                    "message_type": "message",
                    "model": self.default_model,
                    "usage": usage_stats
                }
            )
            logger.debug(f"💾 Assistant 消息已保存到数据库: conversation_id={conversation_id}")
        except Exception as e:
            logger.warning(f"⚠️ 保存 Assistant 消息失败: {str(e)}")
    
    async def _save_assistant_message_content(
        self,
        conversation_id: str,
        content: str,
        session_id: str,
        agent: SimpleAgent
    ) -> None:
        """
        保存 Assistant 消息到数据库（从累积内容）
        
        Args:
            conversation_id: Conversation ID（必填）
            content: Assistant 回复内容
            session_id: Session ID
            agent: Agent 实例
        """
        if not content:
            logger.warning(f"⚠️ Assistant 回复内容为空，跳过保存")
            return
        
        try:
            # 统计 token 使用（如果 Agent 提供）
            usage_stats = {}
            if hasattr(agent.memory.working, 'invocation_stats'):
                stats = agent.memory.working.invocation_stats
                if stats:
                    usage_stats = {
                        "input_tokens": stats.get("total_input_tokens", 0),
                        "output_tokens": stats.get("total_output_tokens", 0)
                    }
            
            await MessageService.create_message(
                conversation_id=conversation_id,
                role="assistant",
                content=content,
                metadata={
                    "session_id": session_id,
                    "message_type": "message",
                    "model": self.default_model,
                    "usage": usage_stats
                }
            )
            logger.debug(f"💾 Assistant 消息已保存到数据库: conversation_id={conversation_id}")
        except Exception as e:
            logger.warning(f"⚠️ 保存 Assistant 消息失败: {str(e)}")
    
    def _extract_tool_calls(self, session_log: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从会话日志中提取工具调用详情"""
        tool_calls_detail = []
        
        for interaction in session_log.get("interactions", []):
            if interaction.get("event_type") == "llm_response":
                tool_count = interaction.get("data", {}).get("tool_calls_count", 0)
                if tool_count > 0:
                    tool_calls_detail.append({
                        "turn": interaction.get("turn"),
                        "tool_calls_count": tool_count
                    })
        
        return tool_calls_detail if tool_calls_detail else None


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

