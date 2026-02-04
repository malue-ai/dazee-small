"""
聊天服务层 - Chat Service

职责：
1. 提供统一的对话入口 chat()
2. 协调 Agent 执行
3. 管理 Session 生命周期

设计原则：
- chat() 是唯一入口，根据 stream 参数选择模式
- Session 管理由 SessionService 负责
- Agent 获取由 AgentPool 负责
- SessionPool 提供统计视图和协调
- 内容累积和持久化由 EventBroadcaster 自动处理
"""

# 标准库
import asyncio
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import uuid4

from logger import get_logger, log_execution_time
from core.agent import SimpleAgent
from core.billing.tracker import EnhancedUsageTracker
from core.events.broadcaster import EventBroadcaster
from core.schemas.validator import AgentSchema
from core.agent.multi.models import MultiAgentConfig
from core.agent.multi.orchestrator import MultiAgentOrchestrator
from core.context import Context
from core.context.compaction import (
    QoSLevel,
    TrimStats,
    get_compaction_threshold,
    get_context_awareness_prompt,
    get_context_strategy,
    trim_by_token_budget,
    trim_history_messages_with_stats,
)
from core.output import OutputFormatter, create_output_formatter
from core.llm import create_llm_service, Message
from config.llm_config.loader import get_llm_profile
from core.routing import AgentRouter, RoutingDecision, IntentResult
from core.monitoring import TokenAuditor, get_token_auditor
from infra.database import AsyncSessionLocal, crud
from infra.pools import get_agent_pool, get_session_pool
from infra.resilience import get_circuit_breaker, with_retry, with_timeout
from services.agent_registry import AgentNotFoundError, get_agent_registry
from services.conversation_service import (
    ConversationNotFoundError,
    get_conversation_service,
)
from services.session_service import (
    SessionNotFoundError,
    SessionService,
    get_session_service,
)
from evaluation.models import TokenUsage
from models.usage import UsageResponse
from utils.background_tasks import TaskContext, get_background_task_service
from utils.message_utils import (
    append_text_to_last_block,
    dict_list_to_messages,
    extract_text_from_message,
    normalize_message_format,
)
from utils.file_processor import get_file_processor
from utils.query_utils import apply_conversation_delta, format_variables

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
    
    # 默认 Agent 标识
    DEFAULT_AGENT_KEY = "__default__"
    
    def __init__(
        self,
        session_service: Optional[SessionService] = None,
        default_model: str = "claude-sonnet-4-5-20250929",
        qos_level: QoSLevel = QoSLevel.PRO,
        enable_routing: bool = True,
        multi_agent_config: Optional["MultiAgentConfig"] = None,
    ):
        self.session_service = session_service or get_session_service()
        self.default_model = default_model
        
        # 资源池
        self.session_pool = get_session_pool()
        self.agent_pool = get_agent_pool()
        
        # 多智能体配置（延迟加载）
        self.multi_agent_config = multi_agent_config
        
        # 依赖服务
        self.conversation_service = get_conversation_service()
        self.background_tasks = get_background_task_service()
        
        # OutputFormatter 缓存
        self._formatters: Dict[str, OutputFormatter] = {}
        
        # 熔断器
        self.agent_breaker = get_circuit_breaker("agent_execution")
        
        # 上下文压缩配置
        self.qos_level = qos_level
        self.compaction_threshold = get_compaction_threshold(qos_level)
        
        # 路由层配置
        self.enable_routing = enable_routing
        # 使用字典缓存不同实例的 Router，避免频繁重新创建
        self._routers: Dict[str, AgentRouter] = {}
        self._default_router: Optional[AgentRouter] = None
        
        # Token 审计器
        self.token_auditor: TokenAuditor = get_token_auditor()
        
        logger.info(
            "ChatService 初始化完成",
            extra={
                "qos_level": qos_level.value,
                "compaction_threshold": self.compaction_threshold,
                "enable_routing": enable_routing
            }
        )
        
    
    def _get_router(self, prompt_cache=None) -> AgentRouter:
        """
        延迟初始化路由器（支持按实例缓存）
        
        Args:
            prompt_cache: InstancePromptCache，用于加载实例自定义的意图识别提示词
        
        Returns:
            AgentRouter 实例
        """
        # 获取缓存键：使用 instance_name 作为标识，无 prompt_cache 时用 "__default__"
        cache_key = getattr(prompt_cache, 'instance_name', None) or "__default__"
        
        # 优先使用缓存的 Router
        if cache_key in self._routers:
            return self._routers[cache_key]
        
        # 创建新的 Router 并缓存
        intent_profile = get_llm_profile("intent_analyzer")
        routing_llm = create_llm_service(**intent_profile)
        
        router = AgentRouter(
            llm_service=routing_llm,
            enable_llm=True,
            prompt_cache=prompt_cache
        )
        
        self._routers[cache_key] = router
        
        logger.info(
            "AgentRouter 已初始化",
            extra={
                "cache_key": cache_key,
                "use_custom_prompt": prompt_cache is not None
            }
        )
        return router
    
    def get_output_formatter(self, agent: SimpleAgent) -> Optional[OutputFormatter]:
        """
        从 Agent Schema 获取 OutputFormatter（按需创建）
        
        Args:
            agent: Agent 实例
            
        Returns:
            OutputFormatter 实例，如果未启用则返回 None
        """
        if not agent.schema or not agent.schema.output_formatter.enabled:
            return None
        
        agent_id = getattr(agent, 'agent_id', id(agent))
        cache_key = str(agent_id)
        
        if cache_key not in self._formatters:
            formatter_config = agent.schema.output_formatter
            self._formatters[cache_key] = create_output_formatter(config=formatter_config)
            logger.info(
                "OutputFormatter 已创建",
                extra={"agent_id": agent_id, "format": formatter_config.default_format}
            )
        
        return self._formatters[cache_key]
    
    # ==================== 前置处理层 ====================
    
    async def _emit_intent_event(
        self,
        intent: "IntentResult",
        session_id: str,
        message_id: str,
        broadcaster: EventBroadcaster
    ) -> None:
        """
        发送意图识别结果到前端
        
        Args:
            intent: 意图识别结果
            session_id: Session ID
            message_id: 消息 ID
            broadcaster: EventBroadcaster 实例
        """
        intent_content = {
            "intent_id": intent.intent_id,
            "intent_name": intent.intent_name,
            "complexity": intent.complexity.value,
            "needs_plan": intent.needs_plan,
            "confidence": intent.confidence,
        }
        if intent.platform:
            intent_content["platform"] = intent.platform
        
        await broadcaster.emit_message_delta(
            session_id=session_id,
            delta={"type": "intent", "content": intent_content},
            message_id=message_id
        )
        
        logger.info(
            "Intent 事件已发送",
            extra={"intent_id": intent.intent_id, "intent_name": intent.intent_name}
        )
    
    async def _generate_preface_stream(
        self,
        intent: "IntentResult",
        user_message: str,
        session_id: str,
        message_id: str,
        broadcaster: EventBroadcaster,
        schema: Optional[AgentSchema] = None,
        tracker: Optional[EnhancedUsageTracker] = None
    ) -> Optional[str]:
        """
        流式生成 Preface 开场白
        
        Args:
            intent: 意图识别结果
            user_message: 用户原始消息
            session_id: Session ID
            message_id: 消息 ID
            broadcaster: EventBroadcaster 实例
            schema: Agent Schema（包含 prompts.preface 配置）
            tracker: UsageTracker，用于计费追踪
            
        Returns:
            完整的开场白文本，失败返回 None
        """
        try:
            if not schema or not schema.preface_template:
                logger.warning("Preface 配置缺失")
                return None
            
            intent_profile = get_llm_profile("intent_analyzer")
            preface_llm = create_llm_service(**intent_profile)
            
            # 将 preface_template 作为系统提示词，用户消息作为 user 角色传入
            llm_messages = [
                Message(role="system", content=schema.preface_template),
                Message(role="user", content=user_message)
            ]
            
            accumulated_text = ""
            final_response = None
            
            max_tokens = schema.preface_max_tokens
            async for chunk in preface_llm.create_message_stream(
                messages=llm_messages,
                max_tokens=max_tokens
            ):
                if chunk.content and chunk.is_stream:
                    accumulated_text += chunk.content
                    await broadcaster.emit_message_delta(
                        session_id=session_id,
                        delta={"type": "preface", "content": chunk.content},
                        message_id=message_id,
                        persist=False
                    )
                
                if not chunk.is_stream:
                    final_response = chunk
            
            if tracker and final_response:
                tracker.record_call(
                    llm_response=final_response,
                    model=final_response.model,
                    purpose="preface"
                )
            
            preface_text = accumulated_text.strip()
            if preface_text:
                logger.info(
                    "Preface 生成完成",
                    extra={"length": len(preface_text), "preview": preface_text[:50]}
                )
                return preface_text
            
            return None
            
        except Exception as e:
            logger.warning("Preface 生成失败", extra={"error": str(e)})
            return None
    
    # ==================== 资源管理 ====================
    
    async def _cleanup_session_resources(
        self,
        session_id: str,
        user_id: str,
        agent_id: str,
        status: str = "failed"
    ) -> None:
        """
        清理 Session 相关资源
        
        Args:
            session_id: Session ID
            user_id: 用户 ID
            agent_id: Agent ID
            status: Session 最终状态
        """
        try:
            await self.agent_pool.release(agent_id)
        except Exception as e:
            logger.warning("释放 Agent 失败", extra={"agent_id": agent_id, "error": str(e)})
        
        try:
            await self.session_pool.on_session_end(session_id, user_id, agent_id)
        except Exception as e:
            logger.warning("更新 SessionPool 失败", extra={"session_id": session_id, "error": str(e)})
        
        try:
            await self.session_service.end_session(session_id, status=status)
        except Exception as e:
            logger.warning("结束 Session 失败", extra={"session_id": session_id, "error": str(e)})
    
    @asynccontextmanager
    async def acquire_agent_context(
        self,
        agent_id: str,
        session_id: str,
        user_id: str
    ):
        """
        Agent 资源上下文管理器，自动管理获取和释放
        
        Args:
            agent_id: Agent ID（pool key）
            session_id: Session ID
            user_id: 用户 ID
            
        Yields:
            SimpleAgent 实例
            
        Raises:
            AgentExecutionError: 资源获取失败
        """
        agent = None
        session_pool_updated = False
        
        try:
            agent = await self.agent_pool.acquire(
                agent_id=agent_id,
                event_manager=self.session_service.events,
                conversation_service=self.conversation_service
            )
            logger.debug("Agent 已获取", extra={"agent_id": agent_id})
            
            from core.billing.tracker import EnhancedUsageTracker
            shared_tracker = EnhancedUsageTracker()
            agent.usage_tracker = shared_tracker
            
            await self.session_pool.on_session_start(session_id, user_id, agent_id)
            session_pool_updated = True
            
            yield agent
            
        except Exception as e:
            logger.error("Agent 上下文错误", extra={"error": str(e)})
            raise AgentExecutionError(f"资源获取失败: {e}") from e
            
        finally:
            if agent is not None:
                try:
                    await self.agent_pool.release(agent_id)
                    logger.debug("Agent 已释放", extra={"agent_id": agent_id})
                except Exception as e:
                    logger.warning("释放 Agent 失败", extra={"error": str(e)})
            
            if session_pool_updated:
                try:
                    await self.session_pool.on_session_end(session_id, user_id, agent_id)
                except Exception as e:
                    logger.warning("更新 SessionPool 失败", extra={"error": str(e)})
    
    # ==================== 统一入口 ====================
    
    async def chat(
        self,
        message: Any,
        user_id: str,
        conversation_id: Optional[str] = None,
        message_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        stream: bool = True,
        background_tasks: Optional[List[str]] = None,
        files: Optional[List[Any]] = None,
        variables: Optional[Dict[str, Any]] = None,
        output_format: str = "zenflux"
    ):
        """
        统一的对话入口
        
        根据 stream 参数自动选择模式：
        - stream=True  → 返回 AsyncGenerator，用于 SSE
        - stream=False → 返回 Dict，用于 API 集成
        
        流程（入口层负责准备，执行层负责执行）：
        1. 验证 agent_id
        2. 创建/校验 Conversation
        3. 生成 assistant_message_id
        4. 处理文件
        5. 标准化消息
        6. 检查并发 + 创建 Session
        7. 保存用户消息（含正确的 session_id）
        8. 创建 Assistant 占位
        9. 获取 Agent
        10. 调度执行
        
        Args:
            message: 用户消息（原始格式）
            user_id: 用户 ID
            conversation_id: 对话 ID（可选，不提供则自动创建）
            message_id: 消息 ID（可选）
            stream: 是否流式返回
            background_tasks: 需要启用的后台任务列表，如 ["title_generation"]
            files: 文件引用列表（FileReference 对象或字典）
            variables: 前端上下文变量（可选），如位置、时区等
            agent_id: Agent 实例 ID（可选，不提供则使用默认 Agent）
            output_format: 输出事件格式（zeno/zenflux），默认 zenflux
            
        Returns:
            stream=True  → AsyncGenerator
            stream=False → Dict
        """
        # 🆕 从 variables 中提取 hitlFlag
        hitlFlag = variables.get("hitlFlag", False) if variables else False
        
        logger.info(
            "对话请求",
            extra={
                "user_id": user_id,
                "agent_id": agent_id or "default",
                "conversation_id": conversation_id,
                "message_preview": str(message)[:50] if message else "",
                "hitlFlag": hitlFlag
            }
        )
        
        # 🆕 HITL 响应模式：特殊处理流程
        if hitlFlag:
            logger.info(f"[HITL Response] 检测到 HITL 响应模式")
            return await self._handle_hitl_response(
                message=message,
                user_id=user_id,
                conversation_id=conversation_id,
                agent_id=agent_id,
                stream=stream,
                output_format=output_format
            )
        
        # 1. 验证 agent_id
        if agent_id:
            registry = get_agent_registry()
            if not registry.has_agent(agent_id):
                available = [a["agent_id"] for a in registry.list_agents()]
                raise AgentNotFoundError(f"Agent '{agent_id}' 不存在，可用: {available}")
        
        # 2. 创建/校验 Conversation
        try:
            conv, is_new_conversation = await self.conversation_service.get_or_create_conversation(
                user_id=user_id,
                conversation_id=conversation_id,
                title="新对话"
            )
            conversation_id = conv.id
        except Exception as e:
            raise ValueError(f"对话创建/校验失败: {e}") from e
        
        # 3. 生成 assistant_message_id
        assistant_message_id = str(uuid4())
        
        # 4. 处理文件
        files_metadata = None
        raw_message = message
        if files:
            with log_execution_time("文件处理", logger):
                processor = get_file_processor()
                files_data = [
                    f.model_dump() if hasattr(f, "model_dump") else f
                    for f in files if isinstance(f, (dict,)) or hasattr(f, "model_dump")
                ]
                if files_data:
                    processed_files = await processor.process_files(files_data)
                    if processed_files:
                        files_metadata = [
                            {"file_url": pf.file_url, "file_name": pf.filename, 
                             "file_type": pf.mime_type, "file_size": pf.file_size}
                            for pf in processed_files
                        ]
                        original_text = raw_message if isinstance(raw_message, str) else str(raw_message)
                        if isinstance(raw_message, list):
                            original_text = "".join(
                                b.get("text", "") for b in raw_message 
                                if isinstance(b, dict) and b.get("type") == "text"
                            )
                        raw_message = processor.build_message_content(processed_files, original_text)
                        logger.info("文件处理完成", extra={"file_count": len(files_metadata)})
        
        # 5. 标准化消息
        normalized_message = normalize_message_format(raw_message)
        
        # 6. 检查并发 + 创建 Session（移到消息保存之前，避免额外的 UPDATE 操作）
        await self.session_pool.check_can_create_session(user_id)
        
        session_id = await self.session_service.create_session(
            user_id=user_id,
            message=message,
            conversation_id=conversation_id,
            message_id=message_id,
        )
        logger.info("Session 已创建", extra={"session_id": session_id})
        
        # 7. 保存用户消息 + 8. 创建 Assistant 占位
        content_json = json.dumps(normalized_message, ensure_ascii=False)
        user_message_id = None
        
        try:
            with log_execution_time("保存消息", logger):
                async with AsyncSessionLocal() as session:
                    user_metadata = {
                        "session_id": session_id,  # 现在可以使用正确的 session_id
                        "model": self.default_model
                    }
                    if files_metadata:
                        user_metadata["files"] = files_metadata
                    
                    user_msg = await crud.create_message(
                        session=session,
                        conversation_id=conversation_id,
                        role="user",
                        content=content_json,
                        metadata=user_metadata
                    )
                    user_message_id = user_msg.id
                    logger.info(
                        "用户消息已保存",
                        extra={
                            "conversation_id": conversation_id,
                            "message_id": user_message_id,
                            "session_id": session_id,
                            "file_count": len(files_metadata) if files_metadata else 0
                        }
                    )
                    
                    await crud.create_message(
                        session=session,
                        conversation_id=conversation_id,
                        role="assistant",
                        content="[]",
                        message_id=assistant_message_id,
                        status="processing",
                        metadata={"session_id": session_id, "model": self.default_model}
                    )
                    logger.debug("Assistant 占位已创建", extra={"message_id": assistant_message_id})
        except Exception as e:
            logger.error("消息保存失败", extra={"error": str(e)}, exc_info=True)
            # 消息保存失败时需要清理已创建的 Session
            try:
                await self.session_service.end_session(session_id, status="failed")
            except Exception as cleanup_err:
                logger.warning("清理 Session 失败", extra={"error": str(cleanup_err)})
            raise ValueError(f"消息保存失败: {e}") from e
        
        # 9. 获取 Agent
        pool_key = agent_id or self.DEFAULT_AGENT_KEY
        agent = None
        agent_acquired = False
        session_pool_updated = False
        
        try:
            agent = await self.agent_pool.acquire(
                agent_id=pool_key,
                event_manager=self.session_service.events,
                conversation_service=self.conversation_service
            )
            agent_acquired = True
            logger.debug("Agent 就绪", extra={"agent_id": pool_key})
            
            from core.billing.tracker import EnhancedUsageTracker
            shared_tracker = EnhancedUsageTracker()
            agent.usage_tracker = shared_tracker
            
            await self.session_pool.on_session_start(session_id, user_id, pool_key)
            session_pool_updated = True
            
        except Exception as e:
            logger.error("资源获取失败", extra={"error": str(e)}, exc_info=True)
            try:
                await self.conversation_service.update_message(
                    message_id=assistant_message_id,
                    status="failed"
                )
            except Exception as update_err:
                logger.warning("更新 Assistant 状态失败", extra={"error": str(update_err)})
            try:
                # 按获取顺序的逆序释放资源
                if session_pool_updated:
                    await self.session_pool.on_session_end(session_id, user_id, pool_key)
                if agent_acquired:
                    await self.agent_pool.release(pool_key)
                await self.session_service.end_session(session_id, status="failed")
            except Exception as cleanup_error:
                logger.warning("清理失败", extra={"error": str(cleanup_error)})
            raise AgentExecutionError(f"资源获取失败: {e}") from e
        
        # 10. 调度执行
        if not stream:
            # 同步模式：后台运行，立即返回
            asyncio.create_task(self._run_agent(
                session_id=session_id,
                agent=agent,
                agent_id=pool_key,
                message=normalized_message,
                user_id=user_id,
                conversation_id=conversation_id,
                assistant_message_id=assistant_message_id,
                is_new_conversation=is_new_conversation,
                background_tasks=background_tasks,
                variables=variables,
                output_format=output_format
            ))
            return {
                "task_id": session_id,
                "conversation_id": conversation_id,
                "message": "任务已启动，请轮询 /api/v1/session/{task_id} 查看结果",
                "status": "running"
            }
        
        # 流式模式：返回事件流
        return self._create_stream_generator(
            session_id=session_id,
            agent=agent,
            agent_id=pool_key,
            message=normalized_message,
            user_id=user_id,
            conversation_id=conversation_id,
            assistant_message_id=assistant_message_id,
            is_new_conversation=is_new_conversation,
            background_tasks=background_tasks,
            variables=variables,
            output_format=output_format
        )
    
    async def _create_stream_generator(
        self,
        session_id: str,
        agent: SimpleAgent,
        agent_id: str,
        message: List[Dict[str, Any]],
        user_id: str,
        conversation_id: str,
        assistant_message_id: str,
        is_new_conversation: bool,
        background_tasks: Optional[List[str]],
        variables: Optional[Dict[str, Any]],
        output_format: str = "zenflux"
    ):
        """
        创建流式事件生成器
        
        Args:
            session_id: Session ID
            agent: Agent 实例
            agent_id: Agent ID
            message: 已标准化的消息（content blocks 格式）
            user_id: 用户 ID
            conversation_id: 对话 ID
            assistant_message_id: Assistant 消息 ID（在 chat() 中生成）
            is_new_conversation: 是否新对话
            background_tasks: 后台任务列表
            variables: 前端上下文变量
            output_format: 输出事件格式
        """
        agent_task = None  # 提前声明，避免 except 块中 NameError
        
        try:
            redis = self.session_service.redis
            
            # 设置输出格式（EventManager 和 EventBroadcaster 都会使用）
            events = self.session_service.events
            events.set_output_format(output_format, conversation_id)
            if hasattr(agent, 'broadcaster') and agent.broadcaster:
                agent.broadcaster.set_output_format(output_format, conversation_id)
            
            # 发送初始事件
            await events.session.emit_session_start(
                session_id=session_id,
                user_id=user_id,
                conversation_id=conversation_id,
                message_id=assistant_message_id,
                output_format=events.output_format,
                adapter=events.adapter
            )
            
            if is_new_conversation:
                await events.conversation.emit_conversation_start(
                    session_id=session_id,
                    conversation_id=conversation_id,
                    conversation={
                        "id": conversation_id,
                        "title": "新对话",
                        "created_at": datetime.now().isoformat(),
                        "metadata": {}
                    },
                    output_format=events.output_format,
                    adapter=events.adapter
                )
            
            # 启动 Agent 任务
            agent_task = asyncio.create_task(self._run_agent(
                session_id=session_id,
                agent=agent,
                agent_id=agent_id,
                message=message,
                user_id=user_id,
                conversation_id=conversation_id,
                assistant_message_id=assistant_message_id,
                is_new_conversation=is_new_conversation,
                background_tasks=background_tasks,
                variables=variables,
                output_format=output_format
            ))
                     
            # 订阅事件流
            async for event in redis.subscribe_events(session_id=session_id, after_id=0, timeout=1800):
                yield event
                if agent_task.done():
                    break
            
            if not agent_task.done():
                await agent_task
            
            logger.info("流式对话完成", extra={"session_id": session_id})
                
        except asyncio.CancelledError:
            logger.info("SSE 断开，Agent 后台继续", extra={"session_id": session_id})
        
        except Exception as e:
            logger.error("流式对话失败", extra={"session_id": session_id, "error": str(e)}, exc_info=True)
            # 资源清理策略：
            # - 如果 agent_task 已启动，由其 finally 块统一处理，避免双重清理
            # - 如果 agent_task 未启动（异常发生在 create_task 之前），需要手动清理
            if agent_task is None:
                await self._cleanup_session_resources(
                    session_id=session_id,
                    user_id=user_id,
                    agent_id=agent_id,
                    status="failed"
                )
            raise AgentExecutionError(f"流式对话失败: {e}") from e
    
    async def _handle_hitl_response(
        self,
        message: Any,
        user_id: str,
        conversation_id: Optional[str],
        agent_id: Optional[str],
        stream: bool,
        output_format: str
    ):
        """
        处理 HITL 响应（前端提交表单后触发）
        
        流程：
        1. 解析 message 中的 hitl_response 数据
        2. 加载历史消息
        3. 动态替换 pending tool_result
        4. 添加触发消息（"请继续"）
        5. 调用 Agent 继续执行
        
        Args:
            message: 包含 hitl_response 的消息数据
            user_id: 用户 ID
            conversation_id: 对话 ID
            agent_id: Agent ID
            stream: 是否流式返回
            output_format: 输出格式
        
        Returns:
            AsyncGenerator (stream=True) 或 Dict (stream=False)
        """
        logger.info(f"[HITL Response] 开始处理 HITL 响应")
        
        # 1. 解析 HITL 响应数据（支持分号分隔的字符串格式）
        try:
            hitl_response = {}
            
            if isinstance(message, str):
                # 🆕 新格式：分号分隔的字符串 "写实风格；1024x1024" 或 "写实风格;1024x1024"
                # 将其解析为字典格式传递给 LLM
                # 兼容中英文分号
                if "；" in message:
                    parts = message.split("；")  # 中文分号
                    logger.info(f"[HITL Response] 解析到中文分号分隔格式: {parts}")
                elif ";" in message:
                    parts = message.split(";")  # 英文分号
                    logger.info(f"[HITL Response] 解析到英文分号分隔格式: {parts}")
                else:
                    parts = [message]
                
                # 简单将所有值合并为一个响应文本
                hitl_response = {"response": message}
            else:
                # 兼容旧格式：JSON 对象
                message_data = message
                if isinstance(message_data, dict):
                    hitl_response = message_data.get("hitl_response", {})
                else:
                    hitl_response = {"response": str(message_data)}
            
            logger.info(f"[HITL Response] 解析到响应数据: {hitl_response}")
        except Exception as e:
            logger.error(f"[HITL Response] 解析响应数据失败: {e}", exc_info=True)
            raise ValueError(f"HITL 响应数据格式错误: {e}") from e
        
        # 2. 验证 conversation_id
        if not conversation_id:
            raise ValueError("HITL 响应必须提供 conversation_id")
        
        # 3. 验证 agent_id
        if agent_id:
            registry = get_agent_registry()
            if not registry.has_agent(agent_id):
                available = [a["agent_id"] for a in registry.list_agents()]
                raise AgentNotFoundError(f"Agent '{agent_id}' 不存在，可用: {available}")
        
        # 4. 生成 assistant_message_id
        assistant_message_id = str(uuid4())
        
        # 5. 创建/校验 Conversation
        try:
            conv, is_new_conversation = await self.conversation_service.get_or_create_conversation(
                user_id=user_id,
                conversation_id=conversation_id,
                title="继续对话"
            )
            conversation_id = conv.id
        except Exception as e:
            raise ValueError(f"对话校验失败: {e}") from e
        
        # 6. 创建 Session
        session_id = await self.session_service.create_session(
            user_id=user_id,
            message="[HITL_CONTINUE]",
            conversation_id=conversation_id,
            message_id=None
        )
        logger.info(f"[HITL Response] Session 已创建: {session_id}")
        
        # 7. 加载历史消息
        history_messages = []
        with log_execution_time("加载历史消息", logger):
            async with AsyncSessionLocal() as session:
                db_messages = await crud.list_messages(
                    session=session,
                    conversation_id=conversation_id,
                    limit=1000,
                    order="asc"
                )
                
                from core.llm.adaptor import ClaudeAdaptor
                
                raw_messages = []
                for db_msg in db_messages:
                    if db_msg.role == "assistant" and db_msg.status == "processing":
                        continue
                    
                    content = db_msg.content
                    try:
                        if isinstance(content, str):
                            content = json.loads(content) if content else []
                        elif content is None:
                            content = []
                    except json.JSONDecodeError:
                        logger.warning("JSON 解析失败", extra={"message_id": db_msg.id})
                    
                    raw_messages.append({
                        "role": db_msg.role,
                        "content": content
                    })
                
                history_messages = ClaudeAdaptor.prepare_messages_from_db(raw_messages)
                
                logger.info(
                    f"[HITL Response] 历史消息已加载",
                    extra={"conversation_id": conversation_id, "count": len(history_messages)}
                )
        
        # 8. 🆕 从历史消息中提取原始 questions，并重新解析用户响应
        original_questions = self._extract_questions_from_history(history_messages)
        if original_questions:
            hitl_response = self._parse_hitl_response_with_questions(
                message, 
                original_questions, 
                hitl_response
            )
            logger.info(f"[HITL Response] 重新解析后的响应: {hitl_response}")
        
        # 9. 动态替换 pending tool_result
        history_messages = await self._replace_pending_hitl_with_response(
            messages=history_messages,
            hitl_response=hitl_response
        )
        
        # 10. 添加触发消息
        trigger_message = {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "用户已完成表单填写并提交了响应数据。请根据上述工具返回的信息继续执行原任务。"
                }
            ]
        }
        history_messages.append(trigger_message)
        
        logger.info(f"[HITL Response] 已添加触发消息，准备继续执行")
        
        # 10. 创建 Assistant 占位
        try:
            async with AsyncSessionLocal() as session:
                await crud.create_message(
                    session=session,
                    conversation_id=conversation_id,
                    role="assistant",
                    content="[]",
                    message_id=assistant_message_id,
                    status="processing",
                    metadata={"session_id": session_id, "model": self.default_model}
                )
                logger.debug(f"[HITL Response] Assistant 占位已创建: {assistant_message_id}")
        except Exception as e:
            logger.error(f"[HITL Response] 创建 Assistant 占位失败: {e}", exc_info=True)
            try:
                await self.session_service.end_session(session_id, status="failed")
            except Exception as cleanup_err:
                logger.warning(f"清理 Session 失败: {cleanup_err}")
            raise ValueError(f"消息保存失败: {e}") from e
        
        # 11. 获取 Agent
        pool_key = agent_id or self.DEFAULT_AGENT_KEY
        agent = None
        agent_acquired = False
        session_pool_updated = False
        
        try:
            agent = await self.agent_pool.acquire(
                agent_id=pool_key,
                event_manager=self.session_service.events,
                conversation_service=self.conversation_service
            )
            agent_acquired = True
            logger.debug(f"[HITL Response] Agent 就绪: {pool_key}")
            
            from core.billing.tracker import EnhancedUsageTracker
            shared_tracker = EnhancedUsageTracker()
            agent.usage_tracker = shared_tracker
            
            await self.session_pool.on_session_start(session_id, user_id, pool_key)
            session_pool_updated = True
            
        except Exception as e:
            logger.error(f"[HITL Response] 资源获取失败: {e}", exc_info=True)
            try:
                await self.conversation_service.update_message(
                    message_id=assistant_message_id,
                    status="failed"
                )
            except Exception as update_err:
                logger.warning(f"更新 Assistant 状态失败: {update_err}")
            try:
                if session_pool_updated:
                    await self.session_pool.on_session_end(session_id, user_id, pool_key)
                if agent_acquired:
                    await self.agent_pool.release(pool_key)
                await self.session_service.end_session(session_id, status="failed")
            except Exception as cleanup_error:
                logger.warning(f"清理失败: {cleanup_error}")
            raise AgentExecutionError(f"资源获取失败: {e}") from e
        
        # 12. 调度执行
        if not stream:
            # 同步模式：后台运行，立即返回
            asyncio.create_task(self._run_agent_with_history(
                session_id=session_id,
                agent=agent,
                agent_id=pool_key,
                history_messages=history_messages,
                user_id=user_id,
                conversation_id=conversation_id,
                assistant_message_id=assistant_message_id,
                output_format=output_format
            ))
            return {
                "task_id": session_id,
                "conversation_id": conversation_id,
                "message": "HITL 响应已处理，任务继续执行中",
                "status": "running"
            }
        
        # 流式模式：返回事件流
        return self._create_hitl_stream_generator(
            session_id=session_id,
            agent=agent,
            agent_id=pool_key,
            history_messages=history_messages,
            user_id=user_id,
            conversation_id=conversation_id,
            assistant_message_id=assistant_message_id,
            output_format=output_format
        )
    
    def _extract_questions_from_history(self, messages: List[Dict]) -> Optional[List[Dict]]:
        """
        从历史消息中提取原始的 HITL questions
        
        Args:
            messages: 历史消息列表
            
        Returns:
            questions 列表，如果未找到则返回 None
        """
        for msg in messages:
            if msg.get("role") != "user":
                continue
            
            content = msg.get("content", [])
            if isinstance(content, str):
                continue
            
            for block in content:
                if block.get("type") != "tool_result":
                    continue
                
                block_content = block.get("content", "")
                try:
                    if isinstance(block_content, str):
                        block_data = json.loads(block_content)
                    else:
                        block_data = block_content
                    
                    if block_data.get("status") == "pending_user_input":
                        questions = block_data.get("questions", [])
                        if questions:
                            logger.info(f"[HITL Response] 提取到原始 questions: {len(questions)} 个")
                            return questions
                except Exception as e:
                    logger.warning(f"解析 tool_result 失败: {e}")
                    continue
        
        return None
    
    def _parse_hitl_response_with_questions(
        self, 
        message: Any, 
        questions: List[Dict],
        fallback_response: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        根据原始 questions 解析用户响应
        
        Args:
            message: 用户响应消息（分号分隔的字符串）
            questions: 原始的 HITL questions
            fallback_response: 如果解析失败，使用的兜底响应
            
        Returns:
            解析后的响应字典
        """
        if not isinstance(message, str):
            logger.warning("[HITL Response] 消息不是字符串，使用兜底响应")
            return fallback_response
        
        # 分割响应（兼容中英文分号）
        if "；" in message:
            parts = message.split("；")
        elif ";" in message:
            parts = message.split(";")
        else:
            parts = [message]
        
        # 清理空白
        parts = [p.strip() for p in parts if p.strip()]
        
        logger.info(f"[HITL Response] 分割后的响应parts: {parts}")
        logger.info(f"[HITL Response] questions数量: {len(questions)}")
        
        # 按照 questions 的 id 顺序映射
        parsed_response = {}
        for i, question in enumerate(questions):
            question_id = question.get("id", f"field_{i}")
            if i < len(parts):
                parsed_response[question_id] = parts[i]
            else:
                # 如果用户没有提供足够的值，使用空字符串
                parsed_response[question_id] = ""
        
        logger.info(f"[HITL Response] 按 question id 映射后: {parsed_response}")
        return parsed_response
    
    async def _replace_pending_hitl_with_response(
        self,
        messages: List[Dict],
        hitl_response: Dict[str, Any]
    ) -> List[Dict]:
        """
        动态替换 pending 状态的 tool_result
        
        Args:
            messages: 历史消息列表
            hitl_response: 用户提交的 HITL 响应数据
            
        Returns:
            替换后的消息列表（仅在内存中替换，不修改数据库）
        """
        logger.info(f"[HITL Response] 开始替换 pending tool_result")
        
        replaced = False
        
        # 遍历消息，找到 pending 的 tool_result
        for msg in messages:
            if msg.get("role") != "user":
                continue
            
            content = msg.get("content", [])
            if isinstance(content, str):
                continue
            
            for block in content:
                if block.get("type") != "tool_result":
                    continue
                
                # 检查是否是 pending 状态
                block_content = block.get("content", "")
                
                # 尝试解析 JSON
                try:
                    if isinstance(block_content, str):
                        block_data = json.loads(block_content)
                    else:
                        block_data = block_content
                    
                    # 检查状态
                    if block_data.get("status") == "pending_user_input":
                        # 🔧 动态替换
                        new_content = {
                            "success": True,
                            "response": hitl_response
                        }
                        
                        block["content"] = json.dumps(new_content, ensure_ascii=False)
                        
                        replaced = True
                        
                        logger.info(
                            f"[HITL Response] ✅ 已替换 tool_result: "
                            f"tool_use_id={block.get('tool_use_id')}"
                        )
                        
                        # 只替换第一个 pending（假设同时只有一个 HITL）
                        return messages
                except (json.JSONDecodeError, TypeError):
                    # 如果不是 JSON，尝试字符串匹配
                    if isinstance(block_content, str) and "pending_user_input" in block_content:
                        new_content = {
                            "success": True,
                            "response": hitl_response
                        }
                        
                        block["content"] = json.dumps(new_content, ensure_ascii=False)
                        
                        replaced = True
                        
                        logger.info(
                            f"[HITL Response] ✅ 已替换 tool_result (字符串匹配): "
                            f"tool_use_id={block.get('tool_use_id')}"
                        )
                        
                        return messages
        
        if not replaced:
            logger.warning(f"[HITL Response] ⚠️ 未找到 pending 状态的 tool_result")
        
        return messages
    
    async def _create_hitl_stream_generator(
        self,
        session_id: str,
        agent: SimpleAgent,
        agent_id: str,
        history_messages: List[Dict[str, Any]],
        user_id: str,
        conversation_id: str,
        assistant_message_id: str,
        output_format: str
    ):
        """
        创建 HITL 响应的流式事件生成器
        
        Args:
            session_id: Session ID
            agent: Agent 实例
            agent_id: Agent ID
            history_messages: 已处理的历史消息（含替换后的 tool_result）
            user_id: 用户 ID
            conversation_id: 对话 ID
            assistant_message_id: Assistant 消息 ID
            output_format: 输出事件格式
        """
        agent_task = None
        
        try:
            redis = self.session_service.redis
            
            # 设置输出格式
            events = self.session_service.events
            events.set_output_format(output_format, conversation_id)
            if hasattr(agent, 'broadcaster') and agent.broadcaster:
                agent.broadcaster.set_output_format(output_format, conversation_id)
            
            # 发送初始事件
            await events.session.emit_session_start(
                session_id=session_id,
                user_id=user_id,
                conversation_id=conversation_id,
                message_id=assistant_message_id,
                output_format=events.output_format,
                adapter=events.adapter
            )
            
            # 启动 Agent 任务
            agent_task = asyncio.create_task(self._run_agent_with_history(
                session_id=session_id,
                agent=agent,
                agent_id=agent_id,
                history_messages=history_messages,
                user_id=user_id,
                conversation_id=conversation_id,
                assistant_message_id=assistant_message_id,
                output_format=output_format
            ))
            
            # 订阅事件流
            async for event in redis.subscribe_events(session_id=session_id, after_id=0, timeout=1800):
                yield event
                if agent_task.done():
                    break
            
            if not agent_task.done():
                await agent_task
            
            logger.info(f"[HITL Response] 流式对话完成: {session_id}")
        
        except asyncio.CancelledError:
            logger.info(f"[HITL Response] SSE 断开，Agent 后台继续: {session_id}")
        
        except Exception as e:
            logger.error(f"[HITL Response] 流式对话失败: {session_id}, {e}", exc_info=True)
            if agent_task is None:
                await self._cleanup_session_resources(
                    session_id=session_id,
                    user_id=user_id,
                    agent_id=agent_id,
                    status="failed"
                )
            raise AgentExecutionError(f"流式对话失败: {e}") from e
    
    async def _run_agent_with_history(
        self,
        session_id: str,
        agent: SimpleAgent,
        agent_id: str,
        history_messages: List[Dict[str, Any]],
        user_id: str,
        conversation_id: str,
        assistant_message_id: str,
        output_format: str = "zenflux"
    ):
        """
        使用已提供的历史消息执行 Agent（用于 HITL 继续模式）
        
        Args:
            session_id: 会话 ID
            agent: Agent 实例
            agent_id: Agent ID
            history_messages: 历史消息（已动态替换）
            user_id: 用户 ID
            conversation_id: 对话 ID
            assistant_message_id: Assistant 消息 ID
            output_format: 输出事件格式
        """
        start_time = time.time()
        execution_status = "completed"
        
        redis = self.session_service.redis
        events = self.session_service.events
        events.set_output_format(output_format, conversation_id)
        
        try:
            logger.info(f"[HITL Response] Agent 开始执行: {session_id}")
            
            # 发送 message_start 事件
            await events.message.emit_message_start(
                session_id=session_id,
                conversation_id=conversation_id,
                message_id=assistant_message_id,
                model=self.default_model,
                output_format=events.output_format,
                adapter=events.adapter
            )
            
            # 初始化 broadcaster 的消息累积
            agent.broadcaster.start_message(session_id, assistant_message_id)
            
            # 设置输出格式
            if hasattr(agent, 'broadcaster') and agent.broadcaster:
                agent.broadcaster.set_output_format(output_format, conversation_id)
            
            # 更新 Session context
            await redis.set_session_context(
                session_id=session_id,
                conversation_id=conversation_id,
                user_id=user_id,
                message_id=assistant_message_id
            )
            
            # 执行 Agent
            async for event in agent.chat(
                messages=history_messages,
                session_id=session_id,
                conversation_id=conversation_id,
                message_id=assistant_message_id,
                enable_stream=True,
                variables=None
            ):
                if event is None:
                    continue
                
                event_type = event.get("type", "")
                
                # 检查停止标志
                if await redis.is_stopped(session_id):
                    logger.warning(f"[HITL Response] 检测到停止标志: {session_id}")
                    await agent.broadcaster.emit_message_stop(
                        session_id=session_id,
                        message_id=assistant_message_id
                    )
                    await events.session.emit_session_stopped(
                        session_id=session_id,
                        conversation_id=conversation_id,
                        reason="user_requested",
                        output_format=events.output_format,
                        adapter=events.adapter
                    )
                    await self.session_service.end_session(session_id, status="stopped")
                    break
            
            # 完成处理
            duration_ms = int((time.time() - start_time) * 1000)
            
            final_status = await redis.get_session_status(session_id)
            status = final_status.get("status") if final_status else "completed"
            
            if status != "stopped":
                await events.session.emit_session_end(
                    session_id=session_id,
                    conversation_id=conversation_id,
                    status="completed",
                    duration_ms=duration_ms,
                    output_format=events.output_format,
                    adapter=events.adapter
                )
                await self.session_service.end_session(session_id, status="completed")
            
            logger.info(f"[HITL Response] Agent 执行完成: {session_id}, 耗时: {duration_ms}ms")
        
        except Exception as e:
            execution_status = "failed"
            logger.error(f"[HITL Response] Agent 执行失败: {e}", exc_info=True)
            duration_ms = int((time.time() - start_time) * 1000)
            
            if assistant_message_id:
                try:
                    await self.conversation_service.update_message(
                        message_id=assistant_message_id,
                        status="failed"
                    )
                except Exception as update_err:
                    logger.warning(f"更新消息状态失败: {update_err}")
            
            try:
                await events.session.emit_session_end(
                    session_id=session_id,
                    conversation_id=conversation_id,
                    status="failed",
                    duration_ms=duration_ms,
                    output_format=events.output_format,
                    adapter=events.adapter
                )
            except Exception as ex:
                logger.warning(f"发送 session_end 失败: {ex}")
        
        finally:
            try:
                await self._cleanup_session_resources(
                    session_id=session_id,
                    user_id=user_id,
                    agent_id=agent_id,
                    status=execution_status
                )
                logger.debug(f"[HITL Response] 资源已释放: {session_id}")
            except Exception as cleanup_err:
                logger.error(f"资源清理失败: {cleanup_err}", exc_info=True)
    
    async def _dispatch_background_tasks(
        self,
        background_tasks: List[str],
        session_id: str,
        conversation_id: str,
        user_id: str,
        message_id: str,
        message: Any,
        is_new_conversation: bool,
        events: Any,
        broadcaster: EventBroadcaster,
        routing_intent: Optional[IntentResult] = None
    ) -> str:
        """
        执行后台任务（如标题生成）
        
        Args:
            background_tasks: 待执行的后台任务列表
            session_id: 会话 ID
            conversation_id: 对话 ID
            user_id: 用户 ID
            message_id: Assistant 消息 ID
            message: 用户消息
            is_new_conversation: 是否新对话
            events: EventManager 实例
            broadcaster: EventBroadcaster 实例
            routing_intent: 路由意图结果
        
        Returns:
            assistant_text: 从 accumulator 获取的 AI 回复文本
        """
        if not background_tasks:
            return ""
        
        # 从 accumulator 获取 assistant 回复
        assistant_text = ""
        accumulator = broadcaster.get_accumulator(session_id)
        if accumulator:
            assistant_text = extract_text_from_message(accumulator.build_for_db())
        
        user_text = extract_text_from_message(message)
        task_context = TaskContext(
            session_id=session_id,
            conversation_id=conversation_id,
            user_id=user_id,
            message_id=message_id,
            user_message=user_text,
            assistant_response=assistant_text,
            is_new_conversation=is_new_conversation,
            event_manager=events,
            conversation_service=self.conversation_service,
            metadata={"intent_id": routing_intent.intent_id if routing_intent else None}
        )
        
        await self.background_tasks.dispatch_tasks(
            task_names=background_tasks,
            context=task_context
        )
        
        return assistant_text
    
    async def _run_agent(
        self,
        session_id: str,
        agent: SimpleAgent,
        agent_id: str,
        message: List[Dict[str, Any]],
        user_id: str,
        conversation_id: str,
        assistant_message_id: str,
        is_new_conversation: bool = False,
        background_tasks: Optional[List[str]] = None,
        variables: Optional[Dict[str, Any]] = None,
        output_format: str = "zenflux"
    ):
        """
        执行 Agent（核心逻辑，同步和流式共用）
        
        流程分为 3 个阶段：
        
        阶段 1: 数据准备
          1.1 加载历史消息
          1.2 注入前端变量（位置、时区等）
        
        阶段 2: 执行 Agent
          2.1 发送 message_start 事件
          2.2 上下文管理（裁剪历史消息）
          2.3 调用 Agent.chat
        
        阶段 3: 完成处理
          3.1 检查最终状态
          3.2 发送完成事件
          3.3 执行后台任务（如标题生成）
          3.4 释放资源（Agent、更新池状态）
        
        Args:
            session_id: 会话 ID
            agent: Agent 实例
            agent_id: Agent ID（用于释放）
            message: 已标准化的用户消息（content blocks 格式）
            user_id: 用户 ID
            conversation_id: 对话 ID
            assistant_message_id: Assistant 消息 ID（在 chat() 中已创建）
            is_new_conversation: 是否新对话
            background_tasks: 后台任务列表
            variables: 前端上下文变量（如位置、时区）
            output_format: 输出事件格式
        """
        start_time = time.time()
        background_tasks = background_tasks or []
        
        # 跟踪执行状态，用于 finally 块的资源清理
        execution_status = "completed"
        
        # 将 events 和 redis 提前初始化，确保 except 块可以访问
        redis = self.session_service.redis
        events = self.session_service.events
        
        # 提前设置 output_format，确保 error 事件也使用正确的格式
        events.set_output_format(output_format, conversation_id)
        
        try:
            logger.info("Agent 开始执行", extra={"session_id": session_id})
            
            # 阶段 1: 数据准备
            
            # 1.1 加载历史消息
            history_messages = []
            with log_execution_time("加载历史消息", logger):
                async with AsyncSessionLocal() as session:
                    db_messages = await crud.list_messages(
                        session=session,
                        conversation_id=conversation_id,
                        limit=1000,
                        order="asc"
                    )
                    
                    from core.llm.adaptor import ClaudeAdaptor
                    
                    raw_messages = []
                    for db_msg in db_messages:
                        if db_msg.role == "assistant" and db_msg.status == "processing":
                            continue
                        
                        content = db_msg.content
                        try:
                            if isinstance(content, str):
                                content = json.loads(content) if content else []
                            elif content is None:
                                content = []
                        except json.JSONDecodeError:
                            logger.warning("JSON 解析失败", extra={"message_id": db_msg.id})
                        
                        raw_messages.append({
                            "role": db_msg.role,
                            "content": content
                        })
                    
                    history_messages = ClaudeAdaptor.prepare_messages_from_db(raw_messages)
                    
                    logger.info(
                        "历史消息已加载",
                        extra={"conversation_id": conversation_id, "count": len(history_messages)}
                    )
            
            # 1.2 注入前端变量到最新用户消息（传给 LLM，不保存到数据库）
            if variables and history_messages:
                last_message = history_messages[-1]
                if last_message.get("role") == "user":
                    context_text = format_variables(variables)
                    if append_text_to_last_block(last_message["content"], context_text):
                        logger.debug("前端变量已注入", extra={"keys": list(variables.keys())})
            
            # 阶段 2: 执行 Agent
            
            # 2.1 发送 message_start 事件
            await events.message.emit_message_start(
                session_id=session_id,
                conversation_id=conversation_id,
                message_id=assistant_message_id,
                model=self.default_model,
                output_format=events.output_format,
                adapter=events.adapter
            )
            
            # 2.2 上下文管理（基于 token 预算裁剪历史消息）
            with log_execution_time("上下文裁剪", logger):
                context_strategy = get_context_strategy(self.qos_level)
                token_budget = int(context_strategy.token_budget * context_strategy.trim_threshold)
                
                history_messages, trim_stats = trim_by_token_budget(
                    messages=history_messages,
                    token_budget=token_budget,
                    preserve_first_messages=context_strategy.preserve_first_messages,
                    preserve_last_messages=context_strategy.preserve_last_messages,
                    preserve_tool_results=context_strategy.preserve_tool_results
                )
            
            if trim_stats.trimmed_count < trim_stats.original_count:
                logger.info(
                    "历史裁剪",
                    extra={
                        "original": trim_stats.original_count,
                        "trimmed": trim_stats.trimmed_count
                    }
                )
            
            if trim_stats.should_warn:
                logger.warning(
                    "Token 预警",
                    extra={
                        "estimated": trim_stats.estimated_tokens,
                        "budget": context_strategy.token_budget
                    }
                )
            
            # 使用 Agent 已注入的共享 Tracker
            shared_tracker = agent.usage_tracker
            
            # 初始化 broadcaster 的消息累积
            agent.broadcaster.start_message(session_id, assistant_message_id)
            
            # 路由决策
            use_multi_agent = False
            routing_intent = None
            enable_intent = agent.schema.is_intent_analysis_enabled if agent.schema else False
            enable_preface = agent.schema.is_preface_enabled if agent.schema else False
            
            if self.enable_routing and enable_intent:
                with log_execution_time("路由决策", logger):
                    agent_prompt_cache = getattr(agent, 'prompt_cache', None)
                    router = self._get_router(prompt_cache=agent_prompt_cache)
                    routing_decision = await router.route(
                        user_query=message,
                        conversation_history=history_messages,
                        tracker=shared_tracker
                    )
                    use_multi_agent = routing_decision.agent_type == "multi"
                    routing_intent = routing_decision.intent
                
                complexity_score = routing_decision.complexity.score if routing_decision.complexity else 0.0
                
                logger.info(
                    "路由决策",
                    extra={
                        "complexity": complexity_score,
                        "use_multi_agent": use_multi_agent,
                        "intent": routing_intent.task_type.value if routing_intent else None
                    }
                )
                
                if routing_intent:
                    logger.debug(
                        "Intent 详情",
                        extra={
                            "intent_id": routing_intent.intent_id,
                            "intent_name": routing_intent.intent_name,
                            "task_type": routing_intent.task_type.value,
                            "complexity": routing_intent.complexity.value,
                            "needs_plan": routing_intent.needs_plan,
                            "confidence": routing_intent.confidence
                        }
                    )
            elif self.enable_routing and not enable_intent:
                # 意图识别已关闭，使用默认 IntentResult
                from core.agent.types import IntentResult, TaskType, Complexity
                routing_intent = IntentResult(
                    task_type=TaskType.OTHER,
                    complexity=Complexity.MEDIUM,
                    needs_plan=False,
                    intent_id=3,
                    intent_name="综合咨询",
                    confidence=1.0
                )
                logger.debug("意图识别已跳过，使用默认 IntentResult")
                
            # 生成 Preface 开场白
            if enable_preface and routing_intent:
                with log_execution_time("Preface 生成", logger):
                    user_text = extract_text_from_message(message)
                    preface_text = await self._generate_preface_stream(
                        intent=routing_intent,
                        user_message=user_text,
                        session_id=session_id,
                        message_id=assistant_message_id,
                        broadcaster=agent.broadcaster,
                        schema=agent.schema,
                        tracker=shared_tracker
                    )
                
                if preface_text:
                    history_messages.append({
                        "role": "assistant",
                        "content": [{"type": "text", "text": preface_text}]
                    })
                    logger.debug("Preface 已添加到上下文", extra={"length": len(preface_text)})
            
            # 设置输出格式
            if hasattr(agent, 'broadcaster') and agent.broadcaster:
                agent.broadcaster.set_output_format(output_format, conversation_id)
            
            # 更新 Session context
            await redis.set_session_context(
                session_id=session_id,
                conversation_id=conversation_id,
                user_id=user_id,
                message_id=assistant_message_id
            )
            
            _assistant_text_for_tasks = ""
            
            # 根据路由决策选择执行路径
            if use_multi_agent:
                # 多智能体执行
                multi_agent_start = time.time()
                logger.info("启用多智能体模式", extra={"session_id": session_id})
                
                if self.multi_agent_config is None:
                    from core.agent.multi.models import load_multi_agent_config
                    self.multi_agent_config = await load_multi_agent_config()
                
                orchestrator = MultiAgentOrchestrator(
                    config=self.multi_agent_config,
                    enable_checkpoints=True,
                    enable_lead_agent=True,
                )
                
                async for event in orchestrator.execute(
                    intent=routing_intent,
                    messages=[{"role": "user", "content": extract_text_from_message(message)}],
                    session_id=session_id,
                    message_id=assistant_message_id,
                ):
                    await agent.broadcaster.emit_raw_event(session_id, event)
                
                multi_agent_duration = (time.time() - multi_agent_start) * 1000
                logger.info(
                    "多智能体执行 完成",
                    extra={"operation": "多智能体执行", "duration_ms": round(multi_agent_duration, 2)}
                )
                
                # 在 message_stop 前执行后台任务
                if background_tasks:
                    _assistant_text_for_tasks = await self._dispatch_background_tasks(
                        background_tasks=background_tasks,
                        session_id=session_id,
                        conversation_id=conversation_id,
                        user_id=user_id,
                        message_id=assistant_message_id,
                        message=message,
                        is_new_conversation=is_new_conversation,
                        events=events,
                        broadcaster=agent.broadcaster,
                        routing_intent=routing_intent
                    )
                    background_tasks = []
                
                await agent.broadcaster.emit_message_stop(
                    session_id=session_id,
                    message_id=assistant_message_id
                )
            else:
                # 单智能体执行
                single_agent_start = time.time()
                # 优化：使用计数器减少 Redis 查询频率（每 10 个事件检查一次）
                stop_check_interval = 10
                event_counter = 0
                
                async for event in agent.chat(
                    messages=history_messages,
                    session_id=session_id,
                    conversation_id=conversation_id,
                    message_id=assistant_message_id,
                    enable_stream=True,
                    variables=variables
                ):
                    if event is None:
                        continue
                    
                    event_counter += 1
                    
                    # 优化：每 N 个事件检查一次停止标志，减少 Redis 查询
                    if event_counter % stop_check_interval == 0 and await redis.is_stopped(session_id):
                        logger.warning("检测到停止标志", extra={"session_id": session_id})
                        
                        # 发送 billing 事件
                        try:
                            usage_response = UsageResponse.from_usage_tracker(
                                tracker=agent.usage_tracker,
                                model=agent.model,
                                latency=int((time.time() - start_time) * 1000)
                            )
                            
                            await agent.broadcaster.emit_message_delta(
                                session_id=session_id,
                                delta={
                                    "type": "billing",
                                    "content": usage_response.model_dump(mode='json')
                                },
                                message_id=assistant_message_id,
                                persist=False
                            )
                            logger.info(
                                "中止时已发送 billing 事件",
                                extra={"total_price": usage_response.total_price}
                            )
                            
                            await agent.broadcaster.accumulate_usage(
                                session_id=session_id,
                                usage=usage_response.model_dump(mode='json')
                            )
                        except Exception as e:
                            logger.error("中止时发送 billing 事件失败", extra={"error": str(e)}, exc_info=True)
                        
                        await agent.broadcaster.emit_message_stop(
                            session_id=session_id,
                            message_id=assistant_message_id
                        )
                        logger.debug("中止时已发送 message_stop 事件")
                        
                        await events.session.emit_session_stopped(
                            session_id=session_id,
                            conversation_id=conversation_id,
                            reason="user_requested",
                            output_format=events.output_format,
                            adapter=events.adapter
                        )
                        
                        await self.session_service.end_session(session_id, status="stopped")
                        break
                    
                    event_type = event.get("type", "")
                    
                    # 在收到 billing 事件时执行后台任务
                    if event_type in ("message_delta", "message.assistant.delta") and background_tasks:
                        delta = event.get("data", {}).get("delta", {})
                        if not delta:
                            delta = event.get("delta", {})
                        if delta.get("type") == "billing":
                            _assistant_text_for_tasks = await self._dispatch_background_tasks(
                                background_tasks=background_tasks,
                                session_id=session_id,
                                conversation_id=conversation_id,
                                user_id=user_id,
                                message_id=assistant_message_id,
                                message=message,
                                is_new_conversation=is_new_conversation,
                                events=events,
                                broadcaster=agent.broadcaster,
                                routing_intent=routing_intent
                            )
                            background_tasks = []
                    
                    if event_type == "conversation_delta":
                        await apply_conversation_delta(self.conversation_service, event, conversation_id)
                
                single_agent_duration = (time.time() - single_agent_start) * 1000
                logger.info(
                    "单智能体执行 完成",
                    extra={"operation": "单智能体执行", "duration_ms": round(single_agent_duration, 2)}
                )
            
            # 阶段 3: 完成处理
            duration_ms = int((time.time() - start_time) * 1000)
            
            # 统一从 accumulator 获取 assistant_text，避免为空的问题
            if not _assistant_text_for_tasks:
                accumulator = agent.broadcaster.get_accumulator(session_id)
                if accumulator:
                    _assistant_text_for_tasks = extract_text_from_message(accumulator.build_for_db())
            assistant_text = _assistant_text_for_tasks
            
            final_status = await redis.get_session_status(session_id)
            status = final_status.get("status") if final_status else "completed"
            
            if status != "stopped":
                # 后台任务回退机制
                if background_tasks:
                    await self._dispatch_background_tasks(
                        background_tasks=background_tasks,
                        session_id=session_id,
                        conversation_id=conversation_id,
                        user_id=user_id,
                        message_id=assistant_message_id,
                        message=message,
                        is_new_conversation=is_new_conversation,
                        events=events,
                        broadcaster=agent.broadcaster,
                        routing_intent=routing_intent
                    )
                
                await events.session.emit_session_end(
                    session_id=session_id,
                    conversation_id=conversation_id,
                    status="completed",
                    duration_ms=duration_ms,
                    output_format=events.output_format,
                    adapter=events.adapter
                )
                await self.session_service.end_session(session_id, status="completed")
            
            # 生成 UsageResponse 并记录审计
            usage_response = None
            try:
                with log_execution_time("Token 审计", logger):
                    usage_stats = agent.usage_tracker.get_stats()
                    
                    usage_response = UsageResponse.from_usage_tracker(
                        tracker=agent.usage_tracker,
                        model=self.default_model,
                        latency=duration_ms / 1000.0
                    )
                    
                    token_usage = TokenUsage(
                        input_tokens=usage_stats.get("total_input_tokens", 0),
                        output_tokens=usage_stats.get("total_output_tokens", 0),
                        thinking_tokens=usage_stats.get("total_thinking_tokens", 0),
                        cache_read_tokens=usage_stats.get("total_cache_read_tokens", 0),
                        cache_write_tokens=usage_stats.get("total_cache_creation_tokens", 0)
                    )
                    
                    await self.token_auditor.record(
                        session_id=session_id,
                        usage=token_usage,
                        conversation_id=conversation_id,
                        user_id=user_id,
                        agent_id=getattr(agent, 'agent_id', None),
                        model=self.default_model,
                        duration_ms=duration_ms,
                        query_length=len(str(message))
                    )
                
                logger.info(
                    "Token 审计",
                    extra={
                        "input_tokens": token_usage.input_tokens,
                        "output_tokens": token_usage.output_tokens,
                        "thinking_tokens": token_usage.thinking_tokens,
                        "cache_read_tokens": token_usage.cache_read_tokens,
                        "total_price": usage_response.total_price
                    }
                )
                
                try:
                    await self.conversation_service.update_message(
                        message_id=assistant_message_id,
                        metadata={"usage": usage_response.model_dump(mode='json')}
                    )
                except Exception as update_err:
                    logger.warning("更新 Usage 数据失败", extra={"error": str(update_err)})
                
            except Exception as audit_err:
                logger.warning("Token 审计失败", extra={"error": str(audit_err)})
            
            logger.info(
                "Agent 执行完成",
                extra={"session_id": session_id, "duration_ms": duration_ms}
            )
        
        except asyncio.CancelledError:
            execution_status = "stopped"
            logger.warning("Agent 任务被取消", extra={"session_id": session_id})
        
        except Exception as e:
            execution_status = "failed"
            logger.error("Agent 执行失败", extra={"error": str(e)}, exc_info=True)
            duration_ms = int((time.time() - start_time) * 1000)
            
            if assistant_message_id:
                try:
                    await self.conversation_service.update_message(
                        message_id=assistant_message_id,
                        status="failed"
                    )
                except Exception as update_err:
                    logger.warning("更新消息状态失败", extra={"error": str(update_err)})
            
            # 分类错误类型
            error_type = "unknown_error"
            user_message = "执行失败，请稍后重试"
            
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
            
            try:
                await events.system.emit_error(
                    session_id=session_id,
                    conversation_id=conversation_id,
                    error_type=error_type,
                    error_message=user_message,
                    details={
                        "error_class": type(e).__name__,
                        "duration_ms": duration_ms
                    },
                    output_format=events.output_format,
                    adapter=events.adapter
                )
            except Exception as ex:
                logger.warning("发送错误事件失败", extra={"error": str(ex)})
            
            try:
                await events.session.emit_session_end(
                    session_id=session_id,
                    conversation_id=conversation_id,
                    status="failed",
                    duration_ms=duration_ms,
                    output_format=events.output_format,
                    adapter=events.adapter
                )
            except Exception as ex:
                logger.warning("发送 session_end 失败", extra={"error": str(ex)})
            
            # 不要 raise，避免 "Task exception was never retrieved"
        
        finally:
            # 确保资源始终释放，使用跟踪的执行状态
            try:
                await self._cleanup_session_resources(
                    session_id=session_id,
                    user_id=user_id,
                    agent_id=agent_id,
                    status=execution_status
                )
                logger.debug(
                    "资源已释放",
                    extra={"session_id": session_id, "agent_id": agent_id, "status": execution_status}
                )
            except Exception as cleanup_err:
                logger.error("资源清理失败", extra={"error": str(cleanup_err)}, exc_info=True)
    
    # ==================== LLM 探测 ====================
    
    async def _emit_llm_switch_event(
        self,
        session_id: str,
        probe_result: dict,
        role: str
    ) -> None:
        """
        发送 LLM 切换事件
        
        Args:
            session_id: 会话 ID
            probe_result: 探测结果，包含 primary、selected、errors 等信息
            role: Agent 角色（如 simple_agent、lead_agent 等）
        """
        try:
            event_data = {
                "role": role,
                "from": probe_result.get("primary", {}),
                "to": probe_result.get("selected", {}),
                "reason": "health_check_failed" if probe_result.get("switched") else "manual",
                "errors": probe_result.get("errors", [])
            }
            
            await self.session_service.events.emit_custom(
                session_id=session_id,
                event_type="llm_switch",
                event_data=event_data
            )
            
            logger.info(
                "LLM 切换事件已发送",
                extra={
                    "session_id": session_id,
                    "role": role,
                    "from_provider": event_data["from"].get("provider"),
                    "to_provider": event_data["to"].get("provider")
                }
            )
        except Exception as e:
            logger.warning(
                "发送 LLM 切换事件失败",
                extra={"session_id": session_id, "error": str(e)},
                exc_info=True
            )
    
    async def _probe_llm_service(
        self,
        llm_service: Any,
        session_id: str,
        role: str = "simple_agent"
    ) -> Optional[dict]:
        """
        请求级 LLM 探针，仅在后台健康探测不健康时执行
        
        Args:
            llm_service: LLM 服务实例
            session_id: 会话 ID
            role: Agent 角色
        
        Returns:
            探测结果字典，如果跳过探测则返回 None
        """
        from core.llm.router import ModelRouter
        if not isinstance(llm_service, ModelRouter):
            return None
        
        from services.health_probe_service import get_health_probe_service
        health_service = get_health_probe_service()
        
        if health_service and health_service.is_healthy(role):
            logger.debug(
                "后台健康探测正常，跳过请求级探测",
                extra={"session_id": session_id, "role": role}
            )
            return None
        
        try:
            import os
            timeout = float(os.getenv("LLM_PROBE_TIMEOUT", "5.0"))
            
            logger.info(
                "执行请求级探测",
                extra={"session_id": session_id, "role": role, "timeout": timeout}
            )
            
            probe_start = time.time()
            probe_result = await asyncio.wait_for(
                llm_service.probe(max_retries=0),
                timeout=timeout
            )
            probe_duration = (time.time() - probe_start) * 1000
            logger.info(
                "LLM 探测 完成",
                extra={"operation": "LLM 探测", "duration_ms": round(probe_duration, 2), "role": role}
            )
            
            if probe_result.get("switched"):
                await self._emit_llm_switch_event(
                    session_id=session_id,
                    probe_result=probe_result,
                    role=role
                )
            
            return probe_result
            
        except asyncio.TimeoutError:
            logger.warning(
                "请求级探测超时",
                extra={"session_id": session_id, "role": role, "timeout": timeout}
            )
            return None
        except Exception as e:
            logger.error(
                "请求级探测失败",
                extra={"session_id": session_id, "role": role, "error": str(e)},
                exc_info=True
            )
            return None


_default_service: Optional[ChatService] = None


def get_chat_service(
    session_service: Optional[SessionService] = None,
    default_model: str = "claude-sonnet-4-5-20250929"
) -> ChatService:
    """
    获取默认聊天服务单例
    """
    global _default_service
    if _default_service is None:
        _default_service = ChatService(
            session_service=session_service,
            default_model=default_model
        )
    return _default_service


def reset_chat_service() -> None:
    """
    重置聊天服务单例（仅用于测试）
    """
    global _default_service
    _default_service = None
