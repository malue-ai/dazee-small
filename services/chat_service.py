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

import asyncio
import json
import time
from typing import Dict, Any, Optional, AsyncGenerator, List
from datetime import datetime
from uuid import uuid4

from logger import get_logger
from core.agent import SimpleAgent
from core.context import Context
from core.output import OutputFormatter, create_output_formatter
# 容错机制
from infra.resilience import with_timeout, with_retry, get_circuit_breaker
# 上下文压缩
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
# 资源池架构
from infra.pools import get_session_pool, get_agent_pool
from infra.database import AsyncSessionLocal, crud
from utils.background_tasks import TaskContext, get_background_task_service
from utils.message_utils import (
    normalize_message_format,
    extract_text_from_message,
    append_text_to_last_block,
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
    
    # 默认 Agent 标识
    DEFAULT_AGENT_KEY = "__default__"
    
    def __init__(
        self,
        session_service: Optional[SessionService] = None,
        default_model: str = "claude-sonnet-4-5-20250929",
        qos_level: QoSLevel = QoSLevel.PRO,  # 🆕 P0: QoS 等级，默认 Pro
        enable_routing: bool = True,  # ✅ V7.2: 启用路由层（单/多智能体路由决策）
        multi_agent_config: Optional["MultiAgentConfig"] = None  # ✅ V7.2: 多智能体配置
    ):
        # Session 管理
        self.session_service = session_service or get_session_service()
        self.default_model = default_model
        
        # 资源池架构
        self.session_pool = get_session_pool()  # 活跃 Session 追踪
        self.agent_pool = get_agent_pool()  # Agent 获取
        
        # ✅ V7.2: 多智能体配置
        from core.agent.multi.models import MultiAgentConfig
        self.multi_agent_config = multi_agent_config  # 如果为 None，在需要时加载默认配置
        
        # 其他服务
        self.conversation_service = get_conversation_service()
        self.background_tasks = get_background_task_service()
        
        # OutputFormatter 缓存
        self._formatters: Dict[str, OutputFormatter] = {}
        
        # 容错机制：熔断器
        self.agent_breaker = get_circuit_breaker("agent_execution")
        
        # 上下文压缩配置
        self.qos_level = qos_level
        self.compaction_threshold = get_compaction_threshold(qos_level)
        logger.info(
            f"✅ ChatService 初始化完成: qos_level={qos_level.value}, "
            f"compaction_threshold={self.compaction_threshold:,} tokens"
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
    
    def _build_user_context(self, variables: Dict[str, Any]) -> str:
        """
        构建用户上下文文本（注入到用户消息中）
        
        Args:
            variables: 前端变量 {"location": {"value": "北京", "description": "用户位置"}, ...}
            
        Returns:
            用户上下文文本
        """
        if not variables:
            return ""
        
        lines = ["[用户上下文]"]
        
        for var_name, var_data in variables.items():
            if isinstance(var_data, dict):
                value = var_data.get("value", "")
                description = var_data.get("description", "")
                if value:
                    if description:
                        lines.append(f"- {var_name}: {value}（{description}）")
                    else:
                        lines.append(f"- {var_name}: {value}")
            else:
                lines.append(f"- {var_name}: {var_data}")
        
        return "\n".join(lines)
    
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
    
    # ==================== 资源管理 ====================
    
    async def _cleanup_session_resources(
        self,
        session_id: str,
        user_id: str,
        agent_id: str,
        status: str = "failed"
    ) -> None:
        """
        清理 Session 相关资源（统一的清理入口）
        
        Args:
            session_id: Session ID
            user_id: 用户 ID
            agent_id: Agent ID
            status: Session 最终状态
        """
        try:
            await self.agent_pool.release(agent_id)
        except Exception as e:
            logger.warning(f"⚠️ 释放 Agent 失败: {e}")
        
        try:
            await self.session_pool.on_session_end(session_id, user_id, agent_id)
        except Exception as e:
            logger.warning(f"⚠️ 更新 SessionPool 失败: {e}")
        
        try:
            await self.session_service.end_session(session_id, status=status)
        except Exception as e:
            logger.warning(f"⚠️ 结束 Session 失败: {e}")
    
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
        agent_id: Optional[str] = None,
        output_format: str = "zenflux"
    ):
        """
        统一的对话入口 ⭐
        
        根据 stream 参数自动选择模式：
        - stream=True  → 返回 AsyncGenerator，用于 SSE
        - stream=False → 返回 Dict，用于 API 集成
        
        流程（入口层只做调度，数据准备在执行层）：
        1. 验证 agent_id
        2. 创建 Conversation（如果需要）
        3. 创建 Session
        4. 获取 Agent（池化优化）
        5. 调度执行（_run_agent 处理所有数据准备）
        
        Args:
            message: 用户消息（原始格式，由执行层处理）
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
        msg_preview = str(message)[:50] if message else ""
        logger.info(f"📨 对话请求: user={user_id}, agent={agent_id or '默认'}, msg={msg_preview}...")
        
        # ========== 1. 验证 agent_id ==========
        if agent_id:
            registry = get_agent_registry()
            if not registry.has_agent(agent_id):
                available = [a["agent_id"] for a in registry.list_agents()]
                raise AgentNotFoundError(f"Agent '{agent_id}' 不存在，可用: {available}")
        
        # ========== 2. 创建 Conversation ==========
        is_new_conversation = False
        if not conversation_id:
            async with AsyncSessionLocal() as session:
                conv = await crud.create_conversation(session=session, user_id=user_id, title="新对话")
                conversation_id = conv.id
                is_new_conversation = True
                logger.info(f"✅ 新对话: {conversation_id}")
        
        # ========== 3. 检查用户并发限制 ==========
        await self.session_pool.check_can_create_session(user_id)
        
        # ========== 4. 创建 Session ==========
        session_id = await self.session_service.create_session(
            user_id=user_id,
            message=message,
            conversation_id=conversation_id,
            message_id=message_id,
        )
        logger.info(f"✅ Session: {session_id}")
        
        # ========== 5. 获取 Agent（从 AgentPool）==========
        # 注：使用 try-finally 确保资源获取失败时正确清理
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
            logger.debug(f"✅ Agent 就绪: {pool_key}")
            
            # ========== 6. 更新 SessionPool 状态 ==========
            await self.session_pool.on_session_start(session_id, user_id, pool_key)
            session_pool_updated = True
            
        except Exception as e:
            # 资源获取失败，清理已创建的 Session
            logger.error(f"❌ 资源获取失败: {e}")
            try:
                if agent_acquired:
                    await self.agent_pool.release(pool_key)
                await self.session_service.end_session(session_id, status="failed")
            except Exception as cleanup_error:
                logger.warning(f"⚠️ 清理失败: {cleanup_error}")
            raise AgentExecutionError(f"资源获取失败: {e}") from e
        
        # ========== 7. 调度执行 ==========
        if not stream:
            # 同步模式：后台运行，立即返回
            asyncio.create_task(self._run_agent(
                session_id=session_id,
                agent=agent,
                agent_id=pool_key,  # 传递 agent_id 用于释放
                raw_message=message,
                user_id=user_id,
                conversation_id=conversation_id,
                is_new_conversation=is_new_conversation,
                background_tasks=background_tasks,
                files=files,
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
            agent_id=pool_key,  # 传递 agent_id 用于释放
            raw_message=message,
            user_id=user_id,
            conversation_id=conversation_id,
            is_new_conversation=is_new_conversation,
            background_tasks=background_tasks,
            files=files,
            variables=variables,
            output_format=output_format
        )
    
    async def _create_stream_generator(
        self,
        session_id: str,
        agent: SimpleAgent,
        agent_id: str,
        raw_message: Any,
        user_id: str,
        conversation_id: str,
        is_new_conversation: bool,
        background_tasks: Optional[List[str]],
        files: Optional[List[Any]],
        variables: Optional[Dict[str, Any]],
        output_format: str = "zenflux"
    ):
        """
        创建流式事件生成器
        
        将流式逻辑抽离，保持 chat() 简洁
        
        Args:
            output_format: 输出事件格式（zeno/zenflux），默认 zenflux
        """
        try:
            redis = self.session_service.redis
            
            # 设置输出格式（EventManager 和 EventBroadcaster 都会使用）
            events = self.session_service.events
            events.set_output_format(output_format, conversation_id)
            if hasattr(agent, 'broadcaster') and agent.broadcaster:
                agent.broadcaster.set_output_format(output_format, conversation_id)
            
            # 发送初始事件（使用配置的格式）
            await events.session.emit_session_start(
                session_id=session_id,
                user_id=user_id,
                conversation_id=conversation_id,
                output_format=events.output_format,
                adapter=events.adapter
            )
            
            if is_new_conversation:
                await events.conversation.emit_conversation_start(
                    session_id=session_id,
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
                raw_message=raw_message,
                user_id=user_id,
                conversation_id=conversation_id,
                is_new_conversation=is_new_conversation,
                background_tasks=background_tasks,
                files=files,
                variables=variables,
                output_format=output_format
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
            # SSE 断开，Agent 继续后台运行
            # 注：资源释放由 _run_agent 的 finally 块负责
            logger.info(f"⚠️ SSE 断开，Agent 后台继续: {session_id}")
            # 不要 raise，让 agent_task 继续执行
        
        except Exception as e:
            logger.error(f"❌ 流式对话失败: {e}", exc_info=True)
            # 释放资源
            await self._cleanup_session_resources(
                session_id=session_id,
                user_id=user_id,
                agent_id=agent_id,
                status="failed"
            )
            raise AgentExecutionError(f"流式对话失败: {e}") from e
    
    async def _run_agent(
        self,
        session_id: str,
        agent: SimpleAgent,
        agent_id: str,
        raw_message: Any,
        user_id: str,
        conversation_id: str,
        is_new_conversation: bool = False,
        background_tasks: Optional[List[str]] = None,
        files: Optional[List[Any]] = None,
        variables: Optional[Dict[str, Any]] = None,
        output_format: str = "zenflux"
    ):
        """
        执行 Agent（核心逻辑，同步和流式共用）
        
        流程分为 4 个阶段：
        
        阶段 1: 输入处理
          1.1 处理文件（图片、文档 → Claude 格式内容块）
          1.2 标准化消息格式
          1.3 注入前端变量（位置、时区等注入到用户消息）
        
        阶段 2: 数据库操作
          2.1 保存用户消息（含文件元数据）
          2.2 创建 Assistant 消息占位
          2.3 加载历史消息
        
        阶段 3: 执行 Agent
          3.1 发送 message_start 事件
          3.2 上下文管理（裁剪历史消息）
          3.3 调用 Agent.chat（传入 variables）
        
        阶段 4: 完成处理
          4.1 检查最终状态
          4.2 发送完成事件
          4.3 执行后台任务（如标题生成）
          4.4 释放资源（Agent、更新池状态）
        
        Args:
            session_id: 会话 ID
            agent: Agent 实例
            agent_id: Agent ID（用于释放）
            raw_message: 原始用户消息（未处理）
            user_id: 用户 ID
            conversation_id: 对话 ID
            is_new_conversation: 是否新对话
            background_tasks: 后台任务列表，如 ["title_generation"]
            files: 文件引用列表（FileReference 对象或字典）
            variables: 前端上下文变量（如位置、时区）
        """
        start_time = time.time()
        background_tasks = background_tasks or []
        
        try:
            logger.info(f"🚀 Agent 开始执行: session_id={session_id}")
            
            redis = self.session_service.redis
            events = self.session_service.events
            
            # =================================================================
            # 阶段 1: 输入处理（处理所有用户输入）
            # =================================================================
            
            # 1.1 处理文件（图片、文档 → Claude 格式内容块）
            processed_message, files_metadata = await self._process_message_with_files(raw_message, files)
            if files_metadata:
                logger.info(f"📎 文件处理完成: {len(files_metadata)} 个文件")
            
            # 1.2 标准化消息格式
            message = normalize_message_format(processed_message)
            
            # 1.3 注入前端变量（位置、时区等）到用户消息
            # 注：不能放 System Prompt（会被 cache），必须放在用户消息中
            # 格式：用户 query 在前，系统注入上下文在后（合并到同一个 text block）
            if variables:
                context_text = self._build_user_context(variables)
                if append_text_to_last_block(message, context_text):
                    logger.info(f"🌐 前端变量已注入: {list(variables.keys())}")
            
            # =================================================================
            # 阶段 2: 数据库操作（持久化 + 加载历史）
            # =================================================================
            # 注：为避免 SQLite 并发问题，保存和加载在同一个数据库会话中
            
            assistant_message_id = uuid4().hex
            content_json = json.dumps(message, ensure_ascii=False)
            
            history_messages = []
            async with AsyncSessionLocal() as session:
                # 2.1 保存用户消息（含文件元数据）
                user_metadata = {
                    "session_id": session_id,
                    "model": self.default_model
                }
                if files_metadata:
                    user_metadata["files"] = files_metadata
                
                await crud.create_message(
                    session=session,
                    conversation_id=conversation_id,
                    role="user",
                    content=content_json,
                    metadata=user_metadata
                )
                logger.debug(f"💾 用户消息已保存，files={len(files_metadata) if files_metadata else 0}")
                
                # 2.2 创建 Assistant 消息占位
                await crud.create_message(
                    session=session,
                    conversation_id=conversation_id,
                    role="assistant",
                    content="[]",
                    message_id=assistant_message_id,
                    status="processing",
                    metadata={
                        "session_id": session_id,
                        "model": self.default_model,
                    }
                )
                logger.info(f"✅ Assistant 占位记录已创建: id={assistant_message_id}")
                
                # 2.3 加载历史消息
                db_messages = await crud.list_messages(
                    session=session,
                    conversation_id=conversation_id,
                    limit=1000,
                    order="asc"
                )
                
                # 转换为 Agent 格式（使用 ClaudeAdaptor 统一处理）
                from core.llm.adaptor import ClaudeAdaptor
                
                raw_messages = []
                for db_msg in db_messages:
                    # 跳过 Assistant 占位消息
                    if db_msg.role == "assistant" and db_msg.status == "processing":
                        continue
                    
                    content = db_msg.content
                    try:
                        content = json.loads(content) if content else []
                    except json.JSONDecodeError:
                        pass
                    
                    raw_messages.append({
                        "role": db_msg.role,
                        "content": content
                    })
                
                # 使用 adaptor 清理和分离消息（处理 thinking/index/tool_result）
                history_messages = ClaudeAdaptor.prepare_messages_from_db(raw_messages)
                
                logger.info(f"📚 历史消息已加载: {len(history_messages)} 条")
            
            # =================================================================
            # 阶段 3: 执行 Agent
            # =================================================================
            
            # 3.1 发送 message_start 事件（通知前端开始生成）
            await events.message.emit_message_start(
                session_id=session_id,
                message_id=assistant_message_id,
                model=self.default_model,
                output_format=events.output_format,
                adapter=events.adapter
            )
            
            # 3.2 上下文管理（裁剪历史消息）
            # 三层防护策略：L1 Memory Tool / L2 智能裁剪 / L3 Token 预警
            original_count = len(history_messages)
            
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
            history_messages = trim_history_messages(history_messages, context_strategy)
            
            if len(history_messages) < original_count:
                logger.info(
                    f"✂️ 历史裁剪: {original_count} → {len(history_messages)} 条"
                )
            
            # L3: 后端 token 预警（用户无感知）
            estimated_tokens = estimate_tokens(history_messages)
            if should_warn_backend(estimated_tokens, context_strategy):
                logger.warning(
                    f"⚠️ Token 预警: {estimated_tokens:,} / {context_strategy.token_budget:,}"
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
            agent.broadcaster.start_message(session_id, assistant_message_id)
            
            # 路由决策（仅当启用路由时）
            use_multi_agent = False
            routing_intent = None
            
            if self.enable_routing:
                router = self._get_router()
                routing_decision = await router.route(
                    user_query=message,
                    conversation_history=history_messages
                )
                use_multi_agent = routing_decision.agent_type == "multi"
                routing_intent = routing_decision.intent
                
                # 获取复杂度评分
                complexity_score = routing_decision.complexity.score if routing_decision.complexity else 0.0
                
                logger.info(
                    f"🔀 路由决策: complexity={complexity_score:.2f}, "
                    f"use_multi_agent={use_multi_agent}, "
                    f"intent={routing_intent.task_type.value if routing_intent else 'N/A'}"
                )
            
            # 🆕 设置 Agent 的输出格式（EventBroadcaster 会使用）
            if hasattr(agent, 'broadcaster') and agent.broadcaster:
                agent.broadcaster.set_output_format(output_format, conversation_id)
            
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
                    # 跳过被过滤的事件（ZenO 适配器返回 None）
                    if event is None:
                        continue
                    
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
            
            # =================================================================
            # 阶段 4: 完成处理
            # =================================================================
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            # 4.1 检查最终状态
            final_status = await redis.get_session_status(session_id)
            status = final_status.get("status") if final_status else "completed"
            
            if status != "stopped":
                # 4.2 发送完成事件
                await events.session.emit_session_end(
                    session_id=session_id,
                    status="completed",
                    duration_ms=duration_ms,
                    output_format=events.output_format,
                    adapter=events.adapter
                )
                await self.session_service.end_session(session_id, status="completed")
                
                # 4.3 执行后台任务（如标题生成）
                if background_tasks:
                    user_text = extract_text_from_message(message)
                    
                    assistant_text = ""
                    accumulator = agent.broadcaster.get_accumulator(session_id)
                    if accumulator:
                        assistant_text = extract_text_from_message(
                            accumulator.build_for_db()
                        )
                    
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
                
                # 🆕 V7.4: 发送 usage SSE 事件（使用 emit_custom）
                try:
                    await events.emit_custom(
                        session_id=session_id,
                        event_type="usage",
                        event_data=usage_response.model_dump()
                    )
                except Exception as emit_err:
                    logger.debug(f"Usage 事件发送失败: {emit_err}")
                
            except Exception as audit_err:
                logger.warning(f"⚠️ Token 审计失败: {audit_err}")
            
            logger.info(f"✅ Agent 执行完成: session_id={session_id}, duration={duration_ms}ms")
        
        except Exception as e:
            logger.error(f"❌ Agent 执行失败: {str(e)}", exc_info=True)
            duration_ms = int((time.time() - start_time) * 1000)
            
            # 释放资源（异常情况）
            await self._cleanup_session_resources(
                session_id=session_id,
                user_id=user_id,
                agent_id=agent_id,
                status="failed"
            )
            
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
            
            # 注：Session 状态已在 _cleanup_session_resources 中更新
            
            # ⚠️ 不要 raise，避免 "Task exception was never retrieved"
            # 异常已经通过事件和日志记录，不需要传播
    
    # =========================================================================
    # 【待扩展】Multi-Agent 执行方法（已注释）
    # 
    # 如需启用 Multi-Agent 功能，取消注释以下方法，并：
    # 1. 取消注释顶部的 from core.multi_agent import ... 
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
            
            # 提取文件元数据（用于保存到消息 metadata，供历史记录展示）
            # 使用 file_url 方式，不依赖数据库
            files_metadata = []
            for pf in processed_files:
                files_metadata.append({
                    "file_url": pf.file_url,
                    "file_name": pf.filename,
                    "file_type": pf.mime_type,
                    "file_size": pf.file_size
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


def reset_chat_service() -> None:
    """
    重置聊天服务单例（仅用于测试）
    """
    global _default_service
    _default_service = None
