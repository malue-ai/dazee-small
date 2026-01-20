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
from core.agent import SimpleAgent, create_simple_agent
from core.context import Context
from core.output import OutputFormatter, create_output_formatter  # 🆕 V6.3
# 🆕 容错机制（基础设施层）
from infra.resilience import with_timeout, with_retry, get_circuit_breaker
# 🆕 上下文压缩（简化版，使用 Claude SDK 原生 compaction）
from core.context.compaction import QoSLevel, get_compaction_threshold, get_context_awareness_prompt
# 🆕 V7: 路由模块（单智能体/多智能体路由决策）
from core.routing import AgentRouter, RoutingDecision
# 🆕 V7: Token 审计（消耗记录、统计分析、异常检测）
from core.monitoring import get_token_auditor, TokenAuditor
from evaluation.models import TokenUsage
# 🆕 V7.4: Usage 响应模型（计费信息）
from models.usage import UsageResponse
# ✅ V7.2: 多智能体模块
from core.agent.multi.orchestrator import MultiAgentOrchestrator
from core.agent.multi.models import MultiAgentConfig
from services.session_service import SessionService, get_session_service, SessionNotFoundError
from services.conversation_service import get_conversation_service, ConversationNotFoundError
from services.agent_registry import get_agent_registry, AgentNotFoundError
from infra.database import AsyncSessionLocal, crud
from utils.background_tasks import TaskContext, get_background_task_service
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
        default_model: str = "claude-sonnet-4-5-20250929",
        qos_level: QoSLevel = QoSLevel.PRO,  # 🆕 P0: QoS 等级，默认 Pro
        enable_routing: bool = True,  # ✅ V7.2: 启用路由层（单/多智能体路由决策）
        multi_agent_config: Optional["MultiAgentConfig"] = None  # ✅ V7.2: 多智能体配置
    ):
        self.session_service = session_service or get_session_service()
        self.default_model = default_model
        
        # ✅ V7.2: 多智能体配置
        from core.agent.multi.models import MultiAgentConfig
        self.multi_agent_config = multi_agent_config  # 如果为 None，在需要时加载默认配置
        
        # 其他服务
        self.conversation_service = get_conversation_service()  # 用于 Context 加载消息
        self.background_tasks = get_background_task_service()
        
        # 🆕 V6.3: OutputFormatter 缓存（按需创建）
        self._formatters: Dict[str, OutputFormatter] = {}
        
        # 🆕 容错机制：熔断器
        self.agent_breaker = get_circuit_breaker("agent_execution")
        
        # 🆕 上下文压缩（简化版）
        # 核心原则：使用 Claude SDK 原生 compaction，用户无感知
        # QoS 仅用于后端成本统计，不影响用户体验
        self.qos_level = qos_level
        self.compaction_threshold = get_compaction_threshold(qos_level)
        logger.info(
            f"✅ Context Compaction 配置: qos_level={qos_level.value}, "
            f"threshold={self.compaction_threshold:,} tokens (Claude SDK 原生处理)"
        )
        
        # 🆕 V7: 路由器（单智能体/多智能体路由决策）
        # enable_routing=False: 意图分析在 SimpleAgent 内部完成（向后兼容）
        # enable_routing=True: 意图分析在路由层完成，支持多智能体路由
        self.enable_routing = enable_routing
        self._router: Optional[AgentRouter] = None
        
        if enable_routing:
            logger.info("🔀 路由层已启用：意图分析将在路由层完成")
        
        # 🆕 V7: Token 审计器
        self.token_auditor: TokenAuditor = get_token_auditor()
    
    def _get_router(self) -> AgentRouter:
        """
        延迟初始化路由器
        
        Returns:
            AgentRouter 实例
        """
        if self._router is None:
            self._router = AgentRouter()
            logger.debug("🔀 AgentRouter 已初始化")
        return self._router
    
    # ==================== 辅助方法 ====================
    
    def get_output_formatter(self, agent: SimpleAgent) -> Optional[OutputFormatter]:
        """
        从 Agent Schema 获取 OutputFormatter（按需创建）
        
        这个方法展示了如何使用 Agent Schema 中的 output_formatter 配置。
        
        Args:
            agent: Agent 实例
            
        Returns:
            OutputFormatter 实例（如果配置启用），否则返回 None
            
        使用示例：
            formatter = service.get_output_formatter(agent)
            if formatter:
                formatted = formatter.format(content, format="json")
        """
        if not agent.schema or not agent.schema.output_formatter.enabled:
            return None
        
        # 使用 agent_id 作为缓存 key（避免重复创建）
        agent_id = getattr(agent, 'agent_id', id(agent))
        cache_key = str(agent_id)
        
        if cache_key not in self._formatters:
            # 从 Agent Schema 读取配置并创建 OutputFormatter
            formatter_config = agent.schema.output_formatter
            self._formatters[cache_key] = create_output_formatter(config=formatter_config)
            logger.info(f"✅ 从 Agent Schema 创建 OutputFormatter: format={formatter_config.default_format}")
        
        return self._formatters[cache_key]
    
    # ==================== 统一入口 ====================
    
    async def chat(
        self,
        message: Any,
        user_id: str,
        conversation_id: Optional[str] = None,
        message_id: Optional[str] = None,
        stream: bool = True,
        background_tasks: Optional[List[str]] = None,
        files: Optional[List[Any]] = None,
        variables: Optional[Dict[str, Any]] = None,
        agent_id: Optional[str] = None
    ):
        """
        统一的对话入口 ⭐
        
        根据 stream 参数自动选择模式：
        - stream=True  → 返回 AsyncGenerator，用于 SSE
        - stream=False → 返回 Dict，用于 API 集成
        
        Args:
            message: 用户消息
            user_id: 用户 ID
            conversation_id: 对话 ID（可选，不提供则自动创建）
            message_id: 消息 ID（可选）
            stream: 是否流式返回
            background_tasks: 需要启用的后台任务列表，如 ["title_generation"]
            files: 文件引用列表（FileReference 对象或字典）
            variables: 前端上下文变量（可选），如位置、时区等
            agent_id: Agent 实例 ID（可选，不提供则使用默认 Agent）
            
        Returns:
            stream=True  → AsyncGenerator
            stream=False → Dict
        """
        # ========== 1. 验证 ==========
        if agent_id:
            registry = get_agent_registry()
            if not registry.has_agent(agent_id):
                available = [a["agent_id"] for a in registry.list_agents()]
                raise AgentNotFoundError(f"Agent '{agent_id}' 不存在，可用: {available}")
        
        # ========== 2. 处理文件 ==========
        processed_message, files_metadata = await self._process_message_with_files(message, files)
        normalized_message = normalize_message_format(processed_message)
        
        msg_preview = str(message)[:50] if message else ""
        logger.info(f"📨 对话请求: user={user_id}, agent={agent_id or '默认'}, msg={msg_preview}..., files={len(files_metadata) if files_metadata else 0}")
        
        # ========== 3. 创建 Conversation ==========
        is_new_conversation = False
        if not conversation_id:
            async with AsyncSessionLocal() as session:
                conv = await crud.create_conversation(session=session, user_id=user_id, title="新对话")
                conversation_id = conv.id
                is_new_conversation = True
                logger.info(f"✅ 新对话: {conversation_id}")
        
        # ========== 4. 创建 Session ==========
        session_id = await self.session_service.create_session(
            user_id=user_id,
            message=normalized_message,
            conversation_id=conversation_id,
            message_id=message_id,
        )
        logger.info(f"✅ Session: {session_id}")
        
        # ========== 5. 获取 Agent ==========
        workspace_dir = str(self.session_service.workspace_manager.get_workspace_root(conversation_id))
        if agent_id:
            agent = await get_agent_registry().get_agent(
                agent_id=agent_id,
                event_manager=self.session_service.events,
                workspace_dir=workspace_dir,
                conversation_service=self.conversation_service
            )
        else:
            agent = create_simple_agent(
                model=self.default_model,
                workspace_dir=workspace_dir,
                event_manager=self.session_service.events,
                conversation_service=self.conversation_service
            )
        
        # ========== 6. 执行 ==========
        if not stream:
            # 同步模式：后台运行，立即返回
            asyncio.create_task(self._run_agent(
                session_id=session_id,
                agent=agent,
                message=normalized_message,
                user_id=user_id,
                conversation_id=conversation_id,
                is_new_conversation=is_new_conversation,
                background_tasks=background_tasks,
                files_metadata=files_metadata,
                variables=variables
            ))
            return {
                "task_id": session_id,
                "conversation_id": conversation_id,
                "message": "任务已启动，请轮询 /api/v1/session/{task_id} 查看结果",
                "status": "running"
            }
        
        # 流式模式：返回事件流
        async def stream_events():
            try:
                redis = self.session_service.redis
                events = self.session_service.events
                
                # 发送初始事件
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
                
                # 启动 Agent 任务
                agent_task = asyncio.create_task(self._run_agent(
                    session_id=session_id,
                    agent=agent,
                    message=normalized_message,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    is_new_conversation=is_new_conversation,
                    background_tasks=background_tasks,
                    files_metadata=files_metadata,
                    variables=variables
                ))
                
                # 订阅事件流
                async for event in redis.subscribe_events(session_id=session_id, after_id=0, timeout=300):
                    yield event
                    if agent_task.done():
                        break
                
                if not agent_task.done():
                    await agent_task
                
                logger.info(f"✅ 流式对话完成: {session_id}")
                    
            except asyncio.CancelledError:
                # SSE 断开，Agent 继续后台运行（agent_task 是独立任务，会自动继续）
                logger.info(f"⚠️ SSE 断开，Agent 后台继续: {session_id}")
            
            except Exception as e:
                logger.error(f"❌ 流式对话失败: {e}", exc_info=True)
                try:
                    await self.session_service.end_session(session_id, status="failed")
                except:
                    pass
                raise AgentExecutionError(f"流式对话失败: {e}") from e
        
        return stream_events()
    
    async def _run_agent(
        self,
        session_id: str,
        agent: SimpleAgent,
        message: List[Dict[str, str]],
        user_id: str,
        conversation_id: str,
        is_new_conversation: bool = False,
        background_tasks: Optional[List[str]] = None,
        files_metadata: Optional[List[Dict[str, Any]]] = None,
        variables: Optional[Dict[str, Any]] = None
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
            files_metadata: 文件元数据列表，用于保存到用户消息的 metadata 中
            variables: 前端上下文变量（如位置、时区），直接注入到 System Prompt
        """
        start_time = time.time()
        background_tasks = background_tasks or []
        
        try:
            logger.info(f"🚀 Agent 开始执行: session_id={session_id}, background_tasks={background_tasks}")
            
            redis = self.session_service.redis
            events = self.session_service.events
            
            # 生成 Assistant 消息 ID
            assistant_message_id = f"msg_{uuid4().hex[:24]}"
            
            # 1️⃣ 异步持久化：推送到 Redis Streams（两阶段持久化）
            content_json = json.dumps(message, ensure_ascii=False)
            
            # 准备用户消息元数据
            user_metadata = {
                "schema_version": "message_meta_v1",
                "session_id": session_id,
                "model": self.default_model
            }
            # 如果有文件，将文件信息添加到 metadata
            if files_metadata:
                user_metadata["files"] = files_metadata
            
            # 生成用户消息 ID
            user_message_id = f"msg_{uuid4().hex[:24]}"
            
            # 推送到 Redis Streams（异步持久化 - 用户消息）
            from infra.message_queue import get_message_queue_client
            from services.session_cache_service import get_session_cache_service, MessageContext
            from datetime import datetime
            
            mq_client = await get_message_queue_client()
            
            # 推送用户消息到 Redis Streams
            await mq_client.push_create_event(
                message_id=user_message_id,
                conversation_id=conversation_id,
                role="user",
                content=content_json,
                status="completed",
                metadata=user_metadata
            )
            logger.info(f"✅ 用户消息已推送到 Redis Streams: {user_message_id}, files={len(files_metadata) if files_metadata else 0}")
            
            # 更新内存缓存（SessionCacheService）
            try:
                session_cache = get_session_cache_service()
                user_message_ctx = MessageContext(
                    id=user_message_id,
                    role="user",
                    content=content_json,
                    created_at=datetime.now(),
                    metadata=user_metadata
                )
                await session_cache.append_message(conversation_id, user_message_ctx)
            except Exception as cache_err:
                logger.warning(f"⚠️ 更新内存缓存失败（不影响主流程）: {cache_err}")
            
            # 创建 Assistant 消息占位（两阶段持久化 - 阶段一）
            placeholder_metadata = {
                "schema_version": "message_meta_v1",
                "session_id": session_id,
                "model": self.default_model,
                "stream": {
                    "phase": "placeholder",
                    "chunk_count": 0
                }
            }
            
            # 推送占位消息到 Redis Streams（异步持久化）
            await mq_client.push_create_event(
                message_id=assistant_message_id,
                conversation_id=conversation_id,
                role="assistant",
                content="[]",  # 空数组
                status="streaming",  # 关键：标记为流式状态（对齐文档规范）
                metadata=placeholder_metadata
            )
            logger.info(f"✅ Assistant 占位消息已推送到 Redis Streams: {assistant_message_id}")
            
            # 更新内存缓存（SessionCacheService）
            try:
                assistant_message_ctx = MessageContext(
                    id=assistant_message_id,
                    role="assistant",
                    content="[]",
                    created_at=datetime.now(),
                    metadata=placeholder_metadata
                )
                await session_cache.append_message(conversation_id, assistant_message_ctx)
            except Exception as cache_err:
                logger.warning(f"⚠️ 更新内存缓存失败（不影响主流程）: {cache_err}")
            
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
            original_count = len(history_messages)
            logger.info(f"📚 历史消息已加载: {original_count} 条")
            
            # =====================================================================
            # 🎯 上下文管理策略（三层防护，用户无感知）
            # =====================================================================
            # 
            # L1. Memory Tool 状态保存（在 System Prompt 中指导 Claude）
            # L2. 历史消息智能裁剪（服务层自动执行）
            # L3. QoS 成本控制（后端日志警告，用户无感知）
            # 
            # 核心原则：
            # 1. 静默处理，用户完全无感知
            # 2. 不警告用户，不建议开启新会话
            # 3. 优先保证问答效果，其次控制成本
            # =====================================================================
            
            # L2 策略：智能裁剪历史消息
            from core.context.compaction import (
                get_context_strategy, 
                trim_history_messages,
                estimate_tokens,
                should_warn_backend
            )
            
            context_strategy = get_context_strategy(self.qos_level)
            
            # 裁剪历史消息（保留首轮 + 最近 N 轮 + 关键 tool_result）
            history_messages = trim_history_messages(history_messages, context_strategy)
            
            if len(history_messages) < original_count:
                logger.info(
                    f"✂️ L2 历史消息裁剪: {original_count} → {len(history_messages)} 条 "
                    f"(保留前{context_strategy.preserve_first_n}轮 + "
                    f"最近{context_strategy.preserve_last_n}轮 + tool_results)"
                )
            
            # L3 策略：后端 token 预警（用户无感知）
            estimated_tokens = estimate_tokens(history_messages)
            if should_warn_backend(estimated_tokens, context_strategy):
                logger.warning(
                    f"⚠️ L3 Token 预警（后端）: {estimated_tokens:,} / "
                    f"{context_strategy.token_budget:,} tokens "
                    f"(QoS={self.qos_level.value})"
                )
            
            # =====================================================================
            # 🎯 V7 路由层：决定使用 SimpleAgent 还是 MultiAgentOrchestrator
            # =====================================================================
            # 
            # enable_routing=False（默认）:
            #   - 向后兼容模式
            #   - 意图分析在 SimpleAgent 内部完成
            #   - 直接调用 SimpleAgent.chat()
            # 
            # enable_routing=True:
            #   - 路由层模式
            #   - 意图分析在路由层完成（AgentRouter）
            #   - 根据复杂度决定使用 SimpleAgent 或 MultiAgentOrchestrator
            # =====================================================================
            
            # 初始化 broadcaster 的消息累积
            agent.broadcaster.start_message(session_id, assistant_message_id, conversation_id)
            
            # 路由决策（仅当启用路由时）
            use_multi_agent = False
            routing_intent = None
            
            if self.enable_routing:
                router = self._get_router()
                routing_decision = await router.route(
                    user_query=message,
                    conversation_history=history_messages
                )
                use_multi_agent = (routing_decision.agent_type == "multi")
                routing_intent = routing_decision.intent
                
                # 获取复杂度评分
                complexity_score = 0.0
                if routing_intent and hasattr(routing_intent, 'complexity_score'):
                    complexity_score = routing_intent.complexity_score
                elif routing_decision.complexity:
                    complexity_score = routing_decision.complexity.score
                
                logger.info(
                    f"🔀 路由决策: complexity={complexity_score:.2f}, "
                    f"use_multi_agent={use_multi_agent}, "
                    f"intent={routing_intent.task_type.value if routing_intent else 'N/A'}"
                )
            
            # 根据路由决策选择执行路径
            if use_multi_agent:
                # ✅ V7.2: 多智能体执行
                logger.info(f"🚀 启用多智能体模式: session_id={session_id}")
                
                # 加载多智能体配置
                if self.multi_agent_config is None:
                    from core.agent.multi.models import load_multi_agent_config
                    self.multi_agent_config = load_multi_agent_config()
                
                # 创建 MultiAgentOrchestrator
                orchestrator = MultiAgentOrchestrator(
                    config=self.multi_agent_config,
                    enable_checkpoints=True,
                    enable_lead_agent=True,
                )
                
                # 设置工作目录（与 SimpleAgent 一致）
                orchestrator.workspace_dir = workspace_dir
                
                # 执行多智能体协作
                async for event in orchestrator.execute(
                    intent=routing_intent,
                    messages=[{"role": "user", "content": extract_text_from_message(message)}],
                    session_id=session_id,
                    message_id=assistant_message_id,
                ):
                    # 转发事件到 EventBroadcaster
                    # 多智能体事件类型：orchestrator_start, task_decomposition, 
                    # agent_start, agent_end, orchestrator_summary, orchestrator_end
                    await agent.broadcaster.emit_raw_event(session_id, event)
            else:
                # 🎯 单智能体执行
                # - 意图分析：由路由层提供（enable_routing=True）或内部完成（默认）
                # - 内容累积：broadcaster 自动处理 content_start/delta/stop
                # - Checkpoint：broadcaster 在每个 content_stop 后自动保存
                # - 最终保存：broadcaster 在 message_stop 时自动完成
                # - variables：直接注入到 System Prompt（前端上下文）
                async for event in agent.chat(
                    messages=history_messages,
                    session_id=session_id,
                    message_id=assistant_message_id,
                    enable_stream=True,
                    variables=variables,
                    intent=routing_intent  # 🆕 V7: 路由层意图结果（None 则内部分析）
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
            
            # =====================================================================
            # 【待扩展】Multi-Agent 路由逻辑（已注释）
            # =====================================================================
            # 
            # from core.agent.multi.models import ExecutionMode
            # 
            # # 1. 提取用户 query
            # user_text = extract_text_from_message(message)
            # 
            # # 2. 意图分析（获取 needs_multi_agent）
            # intent_result = None
            # if hasattr(agent, 'intent_analyzer') and agent.intent_analyzer:
            #     intent_result = await agent.intent_analyzer.analyze(user_text)
            # 
            # # 3. 判断是否使用 Multi-Agent
            # if self.multi_agent_config.mode == MultiAgentMode.DISABLED:
            #     should_use_ma = False
            # elif self.multi_agent_config.mode == MultiAgentMode.ENABLED:
            #     should_use_ma = True
            # else:  # AUTO
            #     should_use_ma = intent_result.needs_multi_agent if intent_result else False
            # 
            # # 4. 根据决策选择执行路径
            # if should_use_ma:
            #     await self._execute_multi_agent(...)
            # else:
            #     # SimpleAgent 逻辑（当前使用）
            #     pass
            # =====================================================================
            
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
                
                # 🎯 统一后台任务调度（新增任务只需在 BackgroundTaskService 中注册）
                if background_tasks:
                    # 提取用户消息文本
                    user_text = extract_text_from_message(message)
                    
                    # 从 broadcaster 的 accumulator 获取 assistant 文本
                    assistant_text = ""
                    accumulator = agent.broadcaster.get_accumulator(session_id)
                    if accumulator:
                        assistant_text = extract_text_from_message(
                            accumulator.build_for_db()
                        )
                    
                    # 构建任务上下文
                    task_context = TaskContext(
                        session_id=session_id,
                        conversation_id=conversation_id,
                        user_id=user_id,
                        message_id=assistant_message_id,
                        user_message=user_text,
                        assistant_response=assistant_text,
                        is_new_conversation=is_new_conversation,
                        event_manager=events,
                        conversation_service=self.conversation_service
                    )
                    
                    # 统一调度后台任务
                    await self.background_tasks.dispatch_tasks(
                        task_names=background_tasks,
                        context=task_context
                    )
            
            # 🆕 V7.4: 生成 UsageResponse（计费信息）
            usage_response = None
            try:
                usage_stats = agent.usage_tracker.get_stats()
                
                # 🆕 使用 UsageResponse 统一模型
                usage_response = UsageResponse.from_usage_tracker(
                    tracker=agent.usage_tracker,
                    model=self.default_model,
                    latency=duration_ms / 1000.0  # 毫秒转秒
                )
                
                # Token 审计记录（兼容旧逻辑）
                token_usage = TokenUsage(
                    input_tokens=usage_stats.get("total_input_tokens", 0),
                    output_tokens=usage_stats.get("total_output_tokens", 0),
                    thinking_tokens=usage_stats.get("total_thinking_tokens", 0),  # 🆕 使用实际值
                    cache_read_tokens=usage_stats.get("total_cache_read_tokens", 0),
                    cache_write_tokens=usage_stats.get("total_cache_creation_tokens", 0)
                )
                
                self.token_auditor.record(
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
                    f"📊 Token 审计: input={token_usage.input_tokens:,}, "
                    f"output={token_usage.output_tokens:,}, "
                    f"thinking={token_usage.thinking_tokens:,}, "
                    f"cache_read={token_usage.cache_read_tokens:,}, "
                    f"total_price=${usage_response.total_price}"
                )
                
                # ✅ 累积 usage 到内存（等待 _finalize_message 时合并写入）
                # 注意：不立即推送，避免多次数据库写入
                await agent.broadcaster.accumulate_usage(
                    session_id=session_id,
                    usage=usage_response.model_dump()  # 传递完整的 UsageResponse
                )
                
                # 注意：billing 事件已在 Agent 内部发送（message_stop 之前）
                # 这里不再重复发送，避免重复计费信息
                logger.debug(f"✅ Usage 数据已累积到内存，等待最终保存")
                
            except Exception as audit_err:
                logger.warning(f"⚠️ Token 审计失败: {audit_err}")
            
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
    
    # =========================================================================
    # 【待扩展】Multi-Agent 执行方法（已注释）
    # 
    # 如需启用 Multi-Agent 功能，取消注释以下方法，并：
    # 1. 取消注释顶部的 from core.agent.multi import ... 
    # 2. 取消注释 __init__ 中的 multi_agent_config 参数
    # 3. 取消注释 _run_agent 中的 Multi-Agent 路由逻辑
    # =========================================================================
    #
    # async def _execute_multi_agent(
    #     self,
    #     user_query: str,
    #     session_id: str,
    #     assistant_message_id: str,
    #     agent: SimpleAgent,
    #     context: Dict[str, Any] = None
    # ):
    #     """
    #     使用 MultiAgentOrchestrator 执行任务
    #     
    #     流程：
    #     1. 创建 MultiAgentOrchestrator
    #     2. 调用 orchestrator.execute()
    #     3. 转换事件并通过 EventBroadcaster 发送
    #     4. 将最终结果保存到数据库
    #     """
    #     orchestrator = MultiAgentOrchestrator(
    #         event_manager=agent.event_manager,
    #         memory_manager=agent.memory,
    #         llm_service=agent.llm,
    #         config=None,
    #         prompt_cache=agent.prompt_cache,
    #         workers_config=getattr(agent, 'workers_config', [])
    #     )
    #     
    #     async for ma_event in orchestrator.execute(
    #         user_query=user_query,
    #         session_id=session_id,
    #         context=context
    #     ):
    #         # 转换 Multi-Agent 事件为标准事件格式
    #         pass
    # =========================================================================
    
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
        files: Optional[List[Any]]
    ) -> tuple[Any, Optional[List[Dict[str, Any]]]]:
        """
        处理文件并合并到消息中
        
        文件处理策略：
        - 图片 (image/*) → 作为 ImageBlock 传给 LLM
        - 纯文本 (text/*) → 读取内容拼进消息
        - 复杂文档 (PDF等) → 生成 URL，让 Agent 决定如何处理
        
        Args:
            message: 原始用户消息
            files: 文件引用列表（FileReference 对象或字典）
            
        Returns:
            tuple: (处理后的消息, 文件元数据列表)
            - 处理后的消息（可能是字符串或 content blocks 列表）
            - 文件元数据列表（用于保存到数据库，供历史记录展示）
        """
        if not files:
            return message, None
        
        try:
            # 统一转换为字典列表
            files_data = []
            for f in files:
                if hasattr(f, "model_dump"):
                    files_data.append(f.model_dump())
                elif isinstance(f, dict):
                    files_data.append(f)
                else:
                    logger.warning(f"⚠️ 未知的文件引用格式: {type(f)}")
            
            if not files_data:
                return message, None
            
            processor = get_file_processor()
            processed_files = await processor.process_files(files_data)
            
            if not processed_files:
                return message, None
            
            logger.info(f"📎 处理了 {len(processed_files)} 个文件")
            
            # 提取文件元数据（用于保存到数据库，字段名统一为 API 格式）
            files_metadata = []
            for pf in processed_files:
                files_metadata.append({
                    "file_id": pf.file_id,
                    "file_name": pf.filename,
                    "file_type": pf.mime_type,
                    "file_size": pf.file_size,
                    "category": pf.category.value if pf.category else None
                })
            
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
            
            return content_blocks, files_metadata
            
        except Exception as e:
            logger.error(f"❌ 处理文件失败: {str(e)}", exc_info=True)
            # 文件处理失败，返回原始消息，不影响对话
            return message, None


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
