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
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import uuid4

from config.llm_config.loader import get_llm_profile
from core.agent import Agent
from core.agent.errors import ErrorClassifier
from core.context.compaction import (  # 🆕 带摘要的智能压缩（双阈值机制）
    CompressionPhase,
    QoSLevel,
    TrimStats,
    compress_with_summary,
    get_context_strategy,
    get_memory_guidance_prompt,
    load_with_existing_summary,
    trim_by_token_budget,
)
from core.context.failure_summary import FailureSummaryManager, get_failure_summary_config
from core.events.broadcaster import EventBroadcaster
from core.llm import Message, create_llm_service
from core.llm.router import ModelRouter
from core.monitoring import TokenAuditor, get_token_auditor
from core.output import OutputFormatter, create_output_formatter
from core.routing import AgentRouter, IntentResult, RoutingDecision

from core.routing.types import Complexity
from core.schemas.validator import AgentSchema
from evaluation.models import TokenUsage
from infra.local_store import crud as local_crud
from infra.local_store.engine import get_local_session_factory
from infra.local_store.pools import get_local_agent_pool, get_local_session_pool
from infra.resilience import get_circuit_breaker, with_retry, with_timeout
from logger import clear_request_context, get_logger, log_execution_time, set_request_context
from models.usage import UsageResponse, UsageTracker
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
from utils.background_tasks import TaskContext, get_background_task_service
from utils.file_processor import get_file_processor
from utils.message_utils import (
    append_to_last_user_message,
    dict_list_to_messages,
    extract_text_from_message,
    get_last_user_message_content,
    normalize_message_format,
)
from utils.query_utils import apply_conversation_delta, format_variables

logger = get_logger("chat_service")


# ==================== 前置处理层 ====================


@dataclass
class PreprocessingResult:
    """前置处理结果"""

    intent: Optional["IntentResult"]


class PreprocessingHandler:
    """
    前置处理器：意图识别

    职责：
    1. 意图识别（路由决策）

    使用示例：
        handler = PreprocessingHandler(intent_llm=self.intent_llm)
        result = await handler.process(
            user_message=current_message,
            history_messages=history_messages,
            session_id=session_id,
            message_id=assistant_message_id,
            broadcaster=agent.broadcaster,
            tracker=shared_tracker,
            router=router,
            enable_intent=True,
        )
    """

    def __init__(self, intent_llm):
        """
        初始化前置处理器

        Args:
            intent_llm: 意图分析 LLM 服务
        """
        self.intent_llm = intent_llm

    async def process(
        self,
        user_message: Any,
        history_messages: List[Dict[str, Any]],
        session_id: str,
        message_id: str,
        agent_schema: Optional["AgentSchema"],
        broadcaster: "EventBroadcaster",
        tracker: Optional["UsageTracker"],
        router: Optional["AgentRouter"],
        enable_intent: bool = True,
    ) -> PreprocessingResult:
        """
        执行前置处理

        Args:
            user_message: 用户消息（支持 str 或多模态 list）
            history_messages: 历史消息列表
            session_id: Session ID
            message_id: Assistant 消息 ID
            agent_schema: Agent Schema 配置
            broadcaster: EventBroadcaster 实例
            tracker: UsageTracker 实例
            router: AgentRouter 实例
            enable_intent: 是否启用意图识别

        Returns:
            PreprocessingResult 包含 intent
        """
        routing_intent = None

        # 意图识别
        if enable_intent and router:
            history_for_intent = history_messages[:-1] if history_messages else []

            routing_intent = await self._analyze_intent(
                user_message=user_message,
                history_messages=history_for_intent,
                router=router,
                tracker=tracker,
            )
        elif not enable_intent:
            # 意图识别已关闭，使用默认 IntentResult
            routing_intent = IntentResult(
                complexity=Complexity.MEDIUM, skip_memory=False, confidence=1.0
            )
            logger.debug("意图识别已跳过，使用默认 IntentResult")

        return PreprocessingResult(intent=routing_intent)

    async def _analyze_intent(
        self,
        user_message: Any,
        history_messages: List[Dict[str, Any]],
        router: "AgentRouter",
        tracker: Optional["UsageTracker"],
    ) -> Optional["IntentResult"]:
        """
        执行意图识别

        Args:
            user_message: 用户消息（支持 str 或多模态 list）

        Returns:
            routing_intent: 意图分析结果
        """
        with log_execution_time("路由决策", logger):
            routing_decision = await router.route(
                user_query=user_message, conversation_history=history_messages, tracker=tracker
            )
            routing_intent = routing_decision.intent

        logger.info(
            "路由决策",
            extra={
                "complexity": routing_intent.complexity.value if routing_intent else "medium",
            },
        )

        if routing_intent:
            logger.debug(
                "Intent 详情",
                extra={
                    "complexity": routing_intent.complexity.value,
                    "skip_memory": routing_intent.skip_memory,
                    "needs_plan": routing_intent.needs_plan,
                    "confidence": routing_intent.confidence,
                },
            )

        return routing_intent

# ==================== 异常定义 ====================


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

    @property
    def default_agent_key(self) -> str:
        """动态获取默认 Agent 标识（单实例模式下使用当前加载的实例）"""
        current = self.agent_registry.get_current_instance()
        if current:
            return current
        # fallback: 取第一个已加载的 Agent
        agents = self.agent_registry.list_agents()
        if agents:
            return agents[0]["agent_id"]
        return "xiaodazi"

    def __init__(
        self,
        session_service: Optional[SessionService] = None,
        qos_level: QoSLevel = QoSLevel.PRO,
        enable_routing: bool = True,
    ):
        self.session_service = session_service or get_session_service()

        # 资源池（本地轻量实现）
        self.session_pool = get_local_session_pool()
        self.agent_pool = get_local_agent_pool()

        # 依赖服务
        self.conversation_service = get_conversation_service()
        self.background_tasks = get_background_task_service()

        # OutputFormatter 缓存
        self._formatters: Dict[str, OutputFormatter] = {}

        # 熔断器
        self.agent_breaker = get_circuit_breaker("agent_execution")

        # 上下文压缩配置
        self.qos_level = qos_level
        strategy = get_context_strategy(qos_level)
        self.compaction_threshold = int(strategy.token_budget * strategy.warning_threshold)

        # 路由层配置
        self.enable_routing = enable_routing
        self._routers: Dict[str, AgentRouter] = {}
        self._default_router: Optional[AgentRouter] = None

        # Token 审计器
        self.token_auditor: TokenAuditor = get_token_auditor()

        # 缓存常用服务（延迟初始化，避免重复创建）
        self._intent_llm = None  # 统一的意图分析 LLM（路由 + 开场白共用）
        self._file_processor = None
        self._agent_registry = None
        self._preprocessing_handler = None  # 前置处理器（意图识别 + Preface）

        logger.info(
            "ChatService 初始化完成",
            extra={
                "qos_level": qos_level.value,
                "compaction_threshold": self.compaction_threshold,
                "enable_routing": enable_routing,
            },
        )

    # ==================== 延迟初始化属性 ====================

    async def get_intent_llm(self):
        """
        统一的意图分析 LLM 服务（单例缓存，带主备切换）

        用于：
        - 路由决策（AgentRouter）
        - 开场白生成（Preface）

        配置来源：config/llm_profiles.yaml → intent_analyzer
        返回类型：ModelRouter（有 fallbacks 时）或单个 LLM Service
        """
        if self._intent_llm is None:
            intent_profile = await get_llm_profile("intent_analyzer")
            self._intent_llm = create_llm_service(**intent_profile)
            logger.info(
                "Intent LLM 服务已初始化",
                extra={"is_router": isinstance(self._intent_llm, ModelRouter)},
            )
        return self._intent_llm

    @property
    def file_processor(self):
        """延迟初始化的文件处理器（单例缓存）"""
        if self._file_processor is None:
            self._file_processor = get_file_processor()
            logger.debug("文件处理器已初始化")
        return self._file_processor

    @property
    def agent_registry(self):
        """延迟初始化的 Agent 注册表（单例缓存）"""
        if self._agent_registry is None:
            self._agent_registry = get_agent_registry()
            logger.debug("Agent 注册表已初始化")
        return self._agent_registry

    async def get_preprocessing_handler(self) -> PreprocessingHandler:
        """延迟初始化的前置处理器（单例缓存）"""
        if self._preprocessing_handler is None:
            intent_llm = await self.get_intent_llm()
            self._preprocessing_handler = PreprocessingHandler(intent_llm=intent_llm)
            logger.debug("前置处理器已初始化")
        return self._preprocessing_handler

    async def _get_router(self, prompt_cache=None) -> AgentRouter:
        """
        延迟初始化路由器（支持按实例缓存）

        Args:
            prompt_cache: InstancePromptCache，用于加载实例自定义的意图识别提示词

        Returns:
            AgentRouter 实例
        """
        # 获取缓存键：使用 instance_name 作为标识，无 prompt_cache 时用 "__default__"
        cache_key = getattr(prompt_cache, "instance_name", None) or "__default__"

        # 优先使用缓存的 Router
        if cache_key in self._routers:
            return self._routers[cache_key]

        # 创建新的 Router（共用 intent_llm，避免重复创建 LLM 服务）
        intent_llm = await self.get_intent_llm()
        # 从实例 Schema 注入意图分析器扩展配置（fast_mode / semantic_cache_threshold / simplified_output）
        intent_kw = {}
        if prompt_cache and getattr(prompt_cache, "agent_schema", None) and prompt_cache.agent_schema:
            ia = getattr(prompt_cache.agent_schema, "intent_analyzer", None)
            if ia is not None:
                intent_kw["fast_mode"] = getattr(ia, "fast_mode", False)
                intent_kw["semantic_cache_threshold"] = getattr(ia, "semantic_cache_threshold", None)
                intent_kw["simplified_output"] = getattr(ia, "simplified_output", True)
        router = AgentRouter(
            llm_service=intent_llm,
            enable_llm=True,
            prompt_cache=prompt_cache,
            **intent_kw,
        )

        self._routers[cache_key] = router

        logger.info(
            "AgentRouter 已初始化",
            extra={"cache_key": cache_key, "use_custom_prompt": prompt_cache is not None},
        )
        return router

    def get_output_formatter(self, agent: Agent) -> Optional[OutputFormatter]:
        """
        从 Agent Schema 获取 OutputFormatter（按需创建）

        Args:
            agent: Agent 实例

        Returns:
            OutputFormatter 实例，如果未启用则返回 None
        """
        if not agent.schema or not agent.schema.output_formatter.enabled:
            return None

        agent_id = getattr(agent, "agent_id", id(agent))
        cache_key = str(agent_id)

        if cache_key not in self._formatters:
            formatter_config = agent.schema.output_formatter
            self._formatters[cache_key] = create_output_formatter(config=formatter_config)
            logger.info(
                "OutputFormatter 已创建",
                extra={"agent_id": agent_id, "format": formatter_config.default_format},
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
        tracker: Optional["EnhancedUsageTracker"] = None
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
        self, session_id: str, user_id: str, agent_id: str, status: str = "failed"
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
            logger.warning(
                "更新 SessionPool 失败", extra={"session_id": session_id, "error": str(e)}
            )

        try:
            await self.session_service.end_session(session_id, status=status)
        except Exception as e:
            logger.warning("结束 Session 失败", extra={"session_id": session_id, "error": str(e)})

        # 清理停止事件（内存级）
        self.session_service.clear_stop_event(session_id)

        # V11: 注销状态一致性管理器
        self.session_service.unregister_state_manager(session_id)

    @asynccontextmanager
    async def acquire_agent_context(self, agent_id: str, session_id: str, user_id: str):
        """
        Agent 资源上下文管理器，自动管理获取和释放

        Args:
            agent_id: Agent ID（pool key）
            session_id: Session ID
            user_id: 用户 ID

        Yields:
            Agent 实例

        Raises:
            AgentExecutionError: 资源获取失败
        """
        agent = None
        session_pool_updated = False

        try:
            agent = await self.agent_pool.acquire(
                agent_id=agent_id,
                event_manager=self.session_service.events,
                conversation_service=self.conversation_service,
            )
            logger.debug("Agent 已获取", extra={"agent_id": agent_id})

            shared_tracker = UsageTracker()
            agent._usage_tracker = shared_tracker

            await self.session_pool.on_session_start(session_id, user_id, agent_id)
            session_pool_updated = True

            yield agent

        except Exception as e:
            logger.error("Agent 上下文错误", extra={"error": str(e)})
            raise AgentExecutionError(f"资源获取失败: {e}") from e

        finally:
            # 统一使用 _cleanup_session_resources 进行资源清理
            if agent is not None or session_pool_updated:
                await self._cleanup_session_resources(
                    session_id=session_id, user_id=user_id, agent_id=agent_id, status="completed"
                )

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
        output_format: str = "zenflux",
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
            output_format: 输出事件格式，默认 zenflux

        Returns:
            stream=True  → AsyncGenerator
            stream=False → Dict
        """
        # 设置日志上下文追踪（初始阶段，conversation_id 可能还未确定）
        set_request_context(
            user_id=user_id, conversation_id=conversation_id or "", message_id=message_id or ""
        )

        logger.info(
            "对话请求",
            extra={
                "user_id": user_id,
                "agent_id": agent_id or "default",
                "conversation_id": conversation_id,
                "message_preview": str(message)[:50] if message else "",
            },
        )

        # 1. 验证 agent_id（支持按需加载）
        if agent_id:
            if not self.agent_registry.has_agent(agent_id):
                # 尝试按需加载（instances/ 目录下可能存在但未预加载）
                try:
                    await self.agent_registry.preload_instance(agent_id)
                    logger.info(f"📦 按需加载 Agent '{agent_id}' 成功")
                except (FileNotFoundError, Exception):
                    available = [a["agent_id"] for a in self.agent_registry.list_agents()]
                    raise AgentNotFoundError(f"Agent '{agent_id}' 不存在，可用: {available}")

        # 2. 创建/校验 Conversation
        try:
            conv, is_new_conversation = await self.conversation_service.get_or_create_conversation(
                user_id=user_id, conversation_id=conversation_id, title="新对话"
            )
            conversation_id = conv.id

            # 🆕 更新日志上下文（conversation_id 已确定）
            set_request_context(
                user_id=user_id, conversation_id=conversation_id, message_id=message_id or ""
            )
        except Exception as e:
            raise ValueError(f"对话创建/校验失败: {e}") from e

        # 3. 生成 assistant_message_id
        assistant_message_id = str(uuid4())

        # 🆕 更新日志上下文（assistant_message_id 已生成）
        set_request_context(
            user_id=user_id, conversation_id=conversation_id, message_id=assistant_message_id
        )

        # 4. 处理文件
        files_metadata = None
        raw_message = message
        if files:
            with log_execution_time("文件处理", logger):
                files_data = [
                    f.model_dump() if hasattr(f, "model_dump") else f
                    for f in files
                    if isinstance(f, (dict,)) or hasattr(f, "model_dump")
                ]
                if files_data:
                    processed_files = await self.file_processor.process_files(files_data)
                    if processed_files:
                        files_metadata = [
                            {
                                "file_url": pf.file_url,
                                "file_name": pf.filename,
                                "file_type": pf.mime_type,
                                "file_size": pf.file_size,
                            }
                            for pf in processed_files
                        ]
                        original_text = (
                            raw_message if isinstance(raw_message, str) else str(raw_message)
                        )
                        if isinstance(raw_message, list):
                            original_text = "".join(
                                b.get("text", "")
                                for b in raw_message
                                if isinstance(b, dict) and b.get("type") == "text"
                            )
                        raw_message = self.file_processor.build_message_content(
                            processed_files, original_text
                        )
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

        # 7. 查询历史 + 保存用户消息 + 创建 Assistant 占位（合并到一个 session）
        content_json = json.dumps(normalized_message, ensure_ascii=False)
        user_message_id = None
        history_messages = []  # 在 chat() 中构建，传递给 _run_agent()

        try:
            with log_execution_time("查询历史+保存消息", logger):
                factory = await get_local_session_factory()
                async with factory() as db_session:
                    # 7.1 先查询历史消息（不包含当前这条）
                    db_messages = await local_crud.list_messages(
                        session=db_session, conversation_id=conversation_id, limit=1000, order="asc"
                    )

                    # 转换为 LLM 格式
                    history_messages = []
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
                            content = []

                        # 如果 content 是单个 dict，包装成 list
                        if isinstance(content, dict):
                            content = [content]

                        # 按 index 排序，移除 index 字段，过滤 thinking 块
                        # thinking/redacted_thinking 块不保留在历史中：
                        # - 无 signature 会导致 Claude API 400 错误
                        # - 官方文档允许省略: "You may omit thinking blocks from previous assistant turns"
                        if isinstance(content, list):
                            content = sorted(
                                content,
                                key=lambda b: b.get("index", 999) if isinstance(b, dict) else 999,
                            )
                            content = [
                                {k: v for k, v in b.items() if k != "index"}
                                for b in content
                                if isinstance(b, dict)
                                and b.get("type") not in ("thinking", "redacted_thinking")
                            ]

                        history_messages.append({"role": db_msg.role, "content": content})

                    # 🛡️ 确保 tool_use/tool_result 配对（DB 可能存有崩溃前的不完整数据）
                    from core.llm.adaptor import ClaudeAdaptor

                    history_messages = ClaudeAdaptor.ensure_tool_pairs(history_messages)

                    logger.info(
                        "历史消息已加载",
                        extra={"conversation_id": conversation_id, "count": len(history_messages)},
                    )

                    # 7.2 保存用户消息
                    user_metadata = {"session_id": session_id}
                    if files_metadata:
                        user_metadata["files"] = files_metadata

                    user_msg = await local_crud.create_message(
                        session=db_session,
                        conversation_id=conversation_id,
                        role="user",
                        content=content_json,
                        metadata=user_metadata,
                    )
                    user_message_id = user_msg.id
                    logger.info(
                        "用户消息已保存",
                        extra={
                            "conversation_id": conversation_id,
                            "message_id": user_message_id,
                            "session_id": session_id,
                            "file_count": len(files_metadata) if files_metadata else 0,
                        },
                    )

                    # 7.3 创建 Assistant 占位
                    await local_crud.create_message(
                        session=db_session,
                        conversation_id=conversation_id,
                        role="assistant",
                        content="[]",
                        message_id=assistant_message_id,
                        status="processing",
                        metadata={"session_id": session_id},
                    )
                    logger.debug("Assistant 占位已创建", extra={"message_id": assistant_message_id})

                    # 7.4 把当前用户消息追加到 history（内存操作，不再查 DB）
                    history_messages.append({"role": "user", "content": normalized_message})
        except Exception as e:
            logger.error("消息保存失败", extra={"error": str(e)}, exc_info=True)
            try:
                await self.session_service.end_session(session_id, status="failed")
            except Exception as cleanup_err:
                logger.warning("清理 Session 失败", extra={"error": str(cleanup_err)})
            raise ValueError(f"消息保存失败: {e}") from e

        # 9. 获取 Agent
        pool_key = agent_id or self.default_agent_key
        agent = None
        agent_acquired = False
        session_pool_updated = False

        try:
            agent = await self.agent_pool.acquire(
                agent_id=pool_key,
                event_manager=self.session_service.events,
                conversation_service=self.conversation_service,
            )
            agent_acquired = True
            logger.debug("Agent 就绪", extra={"agent_id": pool_key})

            shared_tracker = UsageTracker()
            agent._usage_tracker = shared_tracker

            await self.session_pool.on_session_start(session_id, user_id, pool_key)
            session_pool_updated = True

        except Exception as e:
            logger.error("资源获取失败", extra={"error": str(e)}, exc_info=True)
            try:
                await self.conversation_service.update_message(
                    message_id=assistant_message_id, status="failed"
                )
            except Exception as update_err:
                logger.warning("更新 Assistant 状态失败", extra={"error": str(update_err)})

            # 统一使用 _cleanup_session_resources 进行资源清理
            if agent_acquired or session_pool_updated:
                await self._cleanup_session_resources(
                    session_id=session_id, user_id=user_id, agent_id=pool_key, status="failed"
                )
            else:
                # 如果 agent 和 session_pool 都未获取，只需结束 session
                try:
                    await self.session_service.end_session(session_id, status="failed")
                except Exception as cleanup_error:
                    logger.warning("结束 Session 失败", extra={"error": str(cleanup_error)})

            raise AgentExecutionError(f"资源获取失败: {e}") from e

        # 10. 调度执行（history_messages 包含当前用户消息，避免 _run_agent 重复查 DB）
        if not stream:
            # 同步模式：后台运行，立即返回
            asyncio.create_task(
                self._run_agent(
                    session_id=session_id,
                    agent=agent,
                    agent_id=pool_key,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    assistant_message_id=assistant_message_id,
                    history_messages=history_messages,
                    is_new_conversation=is_new_conversation,
                    background_tasks=background_tasks,
                    variables=variables,
                    output_format=output_format,
                )
            )
            return {
                "task_id": session_id,
                "conversation_id": conversation_id,
                "message": "任务已启动，请轮询 /api/v1/session/{task_id} 查看结果",
                "status": "running",
            }

        # 流式模式：返回事件流
        return self._create_stream_generator(
            session_id=session_id,
            agent=agent,
            agent_id=pool_key,
            user_id=user_id,
            conversation_id=conversation_id,
            assistant_message_id=assistant_message_id,
            history_messages=history_messages,
            is_new_conversation=is_new_conversation,
            background_tasks=background_tasks,
            variables=variables,
            output_format=output_format,
        )

    async def _create_stream_generator(
        self,
        session_id: str,
        agent: Agent,
        agent_id: str,
        user_id: str,
        conversation_id: str,
        assistant_message_id: str,
        history_messages: List[Dict[str, Any]],
        is_new_conversation: bool,
        background_tasks: Optional[List[str]],
        variables: Optional[Dict[str, Any]],
        output_format: str = "zenflux",
    ):
        """
        创建流式事件生成器

        Args:
            session_id: Session ID
            agent: Agent 实例
            agent_id: Agent ID
            user_id: 用户 ID
            conversation_id: 对话 ID
            assistant_message_id: Assistant 消息 ID（在 chat() 中生成）
            history_messages: 完整历史消息（包含当前用户消息，从 chat() 传入）
            is_new_conversation: 是否新对话
            background_tasks: 后台任务列表
            variables: 前端上下文变量
            output_format: 输出事件格式
        """
        agent_task = None  # 提前声明，避免 except 块中 NameError

        try:
            store = self.session_service.store

            # 设置输出格式（EventManager 和 EventBroadcaster 都会使用）
            events = self.session_service.events
            events.set_output_format(output_format, conversation_id)
            if hasattr(agent, "broadcaster") and agent.broadcaster:
                agent.broadcaster.set_output_format(output_format, conversation_id)

            # 发送初始事件
            await events.session.emit_session_start(
                session_id=session_id,
                user_id=user_id,
                conversation_id=conversation_id,
                message_id=assistant_message_id,
                output_format=events.output_format,
                adapter=events.adapter,
            )

            if is_new_conversation:
                await events.conversation.emit_conversation_start(
                    session_id=session_id,
                    conversation_id=conversation_id,
                    conversation={
                        "id": conversation_id,
                        "title": "新对话",
                        "created_at": datetime.now().isoformat(),
                        "metadata": {},
                    },
                    output_format=events.output_format,
                    adapter=events.adapter,
                )

            # 启动 Agent 任务
            agent_task = asyncio.create_task(
                self._run_agent(
                    session_id=session_id,
                    agent=agent,
                    agent_id=agent_id,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    assistant_message_id=assistant_message_id,
                    history_messages=history_messages,
                    is_new_conversation=is_new_conversation,
                    background_tasks=background_tasks,
                    variables=variables,
                    output_format=output_format,
                )
            )

            # 订阅事件流
            async for event in store.subscribe_events(
                session_id=session_id, after_id=0, timeout=1800
            ):
                yield event
                if agent_task.done():
                    break

            if not agent_task.done():
                await agent_task

            logger.info("流式对话完成", extra={"session_id": session_id})

        except asyncio.CancelledError:
            logger.info("SSE 断开，Agent 后台继续", extra={"session_id": session_id})

        except Exception as e:
            logger.error(
                "流式对话失败", extra={"session_id": session_id, "error": str(e)}, exc_info=True
            )
            # 资源清理策略：
            # - 如果 agent_task 已启动，由其 finally 块统一处理，避免双重清理
            # - 如果 agent_task 未启动（异常发生在 create_task 之前），需要手动清理
            if agent_task is None:
                await self._cleanup_session_resources(
                    session_id=session_id, user_id=user_id, agent_id=agent_id, status="failed"
                )
            raise AgentExecutionError(f"流式对话失败: {e}") from e

    # NOTE: _handle_hitl_response 及相关方法已移除
    # HITL 表单式确认已改为阻塞模式：HITLTool.execute() 直接 await 用户响应
    # 前端通过 POST /api/v1/human-confirmation/{session_id} 唤醒 asyncio.Event
    # Agent 在同一个 SSE 流中继续执行，无需重建历史或新建 Session
    _HITL_BLOCKING_MODE_NOTE = True

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
        routing_intent: Optional[IntentResult] = None,
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
            metadata={},
        )

        await self.background_tasks.dispatch_tasks(
            task_names=background_tasks, context=task_context
        )

        return assistant_text

    async def _run_agent(
        self,
        session_id: str,
        agent: Agent,
        agent_id: str,
        user_id: str,
        conversation_id: str,
        assistant_message_id: str,
        history_messages: List[Dict[str, Any]],
        is_new_conversation: bool = False,
        background_tasks: Optional[List[str]] = None,
        variables: Optional[Dict[str, Any]] = None,
        output_format: str = "zenflux",
    ):
        """
        执行 Agent（核心逻辑，同步和流式共用）

        流程分为 3 个阶段：

        阶段 1: 数据准备
          1.1 从 history_messages 提取当前用户消息
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
            user_id: 用户 ID
            conversation_id: 对话 ID
            assistant_message_id: Assistant 消息 ID（在 chat() 中已创建）
            history_messages: 完整历史消息（包含当前用户消息，从 chat() 传入）
            is_new_conversation: 是否新对话
            background_tasks: 后台任务列表
            variables: 前端上下文变量（如位置、时区）
            output_format: 输出事件格式
        """
        start_time = time.time()
        background_tasks = list(background_tasks or [])

        # Always append learning tasks (fire-and-forget, never block user)
        if "memory_flush" not in background_tasks:
            background_tasks.append("memory_flush")

        # 跟踪执行状态，用于 finally 块的资源清理
        execution_status = "completed"

        # 将 events 和 store 提前初始化，确保 except 块可以访问
        store = self.session_service.store
        events = self.session_service.events

        # 提前设置 output_format，确保 error 事件也使用正确的格式
        events.set_output_format(output_format, conversation_id)

        try:
            logger.info("Agent 开始执行", extra={"session_id": session_id})

            # 阶段 1: 数据准备

            # 1.1 从 history_messages 提取当前用户消息
            current_message = get_last_user_message_content(history_messages)
            if not current_message:
                raise ValueError("history_messages 中没有用户消息")

            logger.debug(
                "历史消息已就绪",
                extra={"conversation_id": conversation_id, "count": len(history_messages)},
            )

            # 1.2 注入前端变量到最新用户消息（传给 LLM，不保存到数据库）
            if variables:
                context_text = format_variables(variables)
                if context_text:
                    append_to_last_user_message(history_messages, f"\n\n{context_text}")

            # 阶段 2: 执行 Agent

            # 2.1 发送 message_start 事件
            await events.message.emit_message_start(
                session_id=session_id,
                conversation_id=conversation_id,
                message_id=assistant_message_id,
                model=agent.model,
                output_format=events.output_format,
                adapter=events.adapter,
            )

            # 2.2 上下文管理（带摘要的智能压缩 - 双阈值机制）
            # 双阈值：pre_run=80% 运行前预检查，runtime=92% 运行中实时检查
            context_strategy = get_context_strategy(self.qos_level)

            # 运行前预检查使用 80% 阈值
            pre_run_budget = int(context_strategy.token_budget * context_strategy.pre_run_threshold)

            # 🆕 首先检查是否已有压缩摘要（上次对话已压缩）
            history_messages, applied_existing = await load_with_existing_summary(
                messages=history_messages,
                conversation_id=conversation_id,
                conversation_service=self.conversation_service,
            )

            if applied_existing:
                logger.info("已应用历史摘要", extra={"conversation_id": conversation_id})

            # 🆕 使用带摘要的智能压缩（运行前预检查，80% 阈值）
            history_messages, trim_stats = await compress_with_summary(
                messages=history_messages,
                token_budget=pre_run_budget,
                llm_client=None,  # 使用简单摘要，避免额外 LLM 调用
                conversation_id=conversation_id,
                conversation_service=self.conversation_service,
                preserve_first_messages=context_strategy.preserve_first_messages,
                preserve_last_messages=context_strategy.preserve_last_messages,
                preserve_tool_results=context_strategy.preserve_tool_results,
                compression_phase=CompressionPhase.PRE_RUN,  # 运行前预检查
            )

            if trim_stats.trimmed_count < trim_stats.original_count:
                logger.info(
                    "历史压缩",
                    extra={
                        "original": trim_stats.original_count,
                        "trimmed": trim_stats.trimmed_count,
                        "has_summary": trim_stats.has_summary,
                        "compressed_count": trim_stats.compressed_message_count,
                    },
                )

            if trim_stats.should_warn:
                logger.warning(
                    "Token 预警",
                    extra={
                        "estimated": trim_stats.estimated_tokens,
                        "budget": context_strategy.token_budget,
                    },
                )

            # 使用 Agent 已注入的共享 Tracker
            shared_tracker = agent.usage_tracker

            # 初始化 broadcaster 的消息累积
            agent.broadcaster.start_message(session_id, assistant_message_id)

            # 创建 tracer（用于 E2E 可观测性）
            from core.orchestration import create_pipeline_tracer

            tracer = create_pipeline_tracer(session_id=session_id, conversation_id=conversation_id)
            user_query_for_trace = (
                current_message[:200]
                if isinstance(current_message, str)
                else str(current_message)[:200]
            )
            tracer.set_user_query(user_query_for_trace)

            # 加载现有计划
            from tools.plan_todo_tool import load_plan_for_session

            existing_plan = await load_plan_for_session(conversation_id)

            # 注入会话上下文（Agent 要求在调用 execute() 之前注入）
            agent.inject_session_context(
                {
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    "message_id": assistant_message_id,
                    "tracer": tracer,
                    "plan": existing_plan,
                }
            )

            # 前置处理：意图识别
            enable_intent = agent.schema.is_intent_analysis_enabled if agent.schema else False

            # 获取 Router（如果启用意图识别）
            router = None
            if self.enable_routing and enable_intent:
                agent_prompt_cache = getattr(agent, "prompt_cache", None)
                router = await self._get_router(prompt_cache=agent_prompt_cache)

            # 执行前置处理（传入完整消息，支持多模态）
            preprocessing_handler = await self.get_preprocessing_handler()
            preprocessing_result = await preprocessing_handler.process(
                user_message=current_message,
                history_messages=history_messages,
                session_id=session_id,
                message_id=assistant_message_id,
                agent_schema=agent.schema,
                broadcaster=agent.broadcaster,
                tracker=shared_tracker,
                router=router,
                enable_intent=self.enable_routing and enable_intent,
            )

            routing_intent = preprocessing_result.intent

            # 确保 intent 不为 None（Agent 要求必须传入）
            if routing_intent is None:
                from core.routing.types import Complexity, IntentResult

                routing_intent = IntentResult(
                    complexity=Complexity.MEDIUM,
                    skip_memory=False,
                    confidence=1.0,
                )

            # V11: 用户停止信号语义识别（LLM 推断 wants_to_stop 时，设置停止事件）
            if getattr(routing_intent, "wants_to_stop", False):
                logger.info("意图分析: 用户希望停止/取消，设置停止标志")
                self.session_service.get_stop_event(session_id).set()

            # 设置输出格式
            if hasattr(agent, "broadcaster") and agent.broadcaster:
                agent.broadcaster.set_output_format(output_format, conversation_id)

            # 更新 Session context
            await store.set_session_context(
                session_id=session_id,
                conversation_id=conversation_id,
                user_id=user_id,
                message_id=assistant_message_id,
            )

            _assistant_text_for_tasks = ""

            # 单智能体执行（RVR-B 策略）
            single_agent_start = time.time()

            # V11: 注册状态一致性管理器，供回滚 API 使用
            state_mgr = getattr(agent, "_state_consistency_manager", None)
            if state_mgr and getattr(agent, "_state_consistency_enabled", False):
                self.session_service.register_state_manager(session_id, state_mgr)

            # V11: 长任务确认等待（执行器 yield long_running_confirm 后 await 此函数）
            agent._wait_long_run_confirm_async = (
                lambda s=session_id: self.session_service.wait_long_run_confirm(s)
            )

            # V11.1: HITL 危险操作确认等待（执行器 yield hitl_confirm 后 await 此函数）
            agent._wait_hitl_confirm_async = (
                lambda s=session_id: self.session_service.wait_hitl_confirm(s)
            )

            async for event in agent.chat(
                messages=history_messages,
                session_id=session_id,
                message_id=assistant_message_id,
                enable_stream=True,
                intent=routing_intent,
            ):
                    if event is None:
                        continue

                    # 检查停止事件（内存检查，无 IO 开销）
                    if self.session_service.is_stopped(session_id):
                        logger.warning("检测到停止标志", extra={"session_id": session_id})

                        # 发送 billing 事件
                        try:
                            usage_response = UsageResponse.from_tracker(
                                tracker=agent.usage_tracker,
                                model=agent.model,
                                latency=int((time.time() - start_time) * 1000),
                            )

                            await agent.broadcaster.emit_message_delta(
                                session_id=session_id,
                                delta={
                                    "type": "billing",
                                    "content": usage_response.model_dump(mode="json"),
                                },
                                message_id=assistant_message_id,
                                persist=False,
                            )
                            logger.info(
                                "中止时已发送 billing 事件",
                                extra={"total_price": usage_response.total_price},
                            )

                            await agent.broadcaster.accumulate_usage(
                                session_id=session_id, usage=usage_response.model_dump(mode="json")
                            )
                        except Exception as e:
                            logger.error(
                                "中止时发送 billing 事件失败",
                                extra={"error": str(e)},
                                exc_info=True,
                            )

                        await agent.broadcaster.emit_message_stop(
                            session_id=session_id, message_id=assistant_message_id
                        )
                        logger.debug("中止时已发送 message_stop 事件")

                        await events.session.emit_session_stopped(
                            session_id=session_id,
                            conversation_id=conversation_id,
                            reason="user_requested",
                            output_format=events.output_format,
                            adapter=events.adapter,
                        )

                        # 设置状态为 stopped，让 finally 块统一清理资源
                        execution_status = "stopped"
                        break

                    event_type = event.get("type", "")

                    # 在收到 billing 事件时执行后台任务
                    if (
                        event_type == "message_delta"
                        and background_tasks
                    ):
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
                                message=current_message,
                                is_new_conversation=is_new_conversation,
                                events=events,
                                broadcaster=agent.broadcaster,
                                routing_intent=routing_intent,
                            )
                            background_tasks = []

                    if event_type == "conversation_delta":
                        await apply_conversation_delta(
                            self.conversation_service, event, conversation_id
                        )

            single_agent_duration = (time.time() - single_agent_start) * 1000
            logger.info(
                "单智能体执行 完成",
                extra={
                    "operation": "单智能体执行",
                    "duration_ms": round(single_agent_duration, 2),
                },
            )

            # 阶段 3: 完成处理
            duration_ms = int((time.time() - start_time) * 1000)

            # 统一从 accumulator 获取 assistant_text，避免为空的问题
            if not _assistant_text_for_tasks:
                accumulator = agent.broadcaster.get_accumulator(session_id)
                if accumulator:
                    _assistant_text_for_tasks = extract_text_from_message(
                        accumulator.build_for_db()
                    )
            assistant_text = _assistant_text_for_tasks

            final_status = await store.get_session_status(session_id)
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
                        message=current_message,
                        is_new_conversation=is_new_conversation,
                        events=events,
                        broadcaster=agent.broadcaster,
                        routing_intent=routing_intent,
                    )

                await events.session.emit_session_end(
                    session_id=session_id,
                    conversation_id=conversation_id,
                    status="completed",
                    duration_ms=duration_ms,
                    output_format=events.output_format,
                    adapter=events.adapter,
                )
                # end_session 由 finally 块的 _cleanup_session_resources 统一处理

            # 生成 UsageResponse 并记录审计（用户手动停止时跳过）
            usage_response = None
            if status == "stopped":
                logger.info(
                    "用户手动停止，跳过 Token 审计",
                    extra={"session_id": session_id, "duration_ms": duration_ms},
                )
            else:
                try:
                    with log_execution_time("Token 审计", logger):
                        usage_stats = agent.usage_tracker.get_stats()

                        usage_response = UsageResponse.from_tracker(
                            tracker=agent.usage_tracker,
                            latency=duration_ms / 1000.0,
                            model=agent.model,
                        )

                        token_usage = TokenUsage(
                            input_tokens=usage_stats.get("total_input_tokens", 0),
                            output_tokens=usage_stats.get("total_output_tokens", 0),
                            thinking_tokens=usage_stats.get("total_thinking_tokens", 0),
                            cache_read_tokens=usage_stats.get("total_cache_read_tokens", 0),
                            cache_write_tokens=usage_stats.get("total_cache_creation_tokens", 0),
                        )

                        # 注意：这里传入的是会话累计值（所有 LLM 调用的总和）
                        # is_session_cumulative=True（默认），使用会话级阈值检测
                        await self.token_auditor.record(
                            session_id=session_id,
                            usage=token_usage,
                            conversation_id=conversation_id,
                            user_id=user_id,
                            agent_id=getattr(agent, "agent_id", None),
                            model=agent.model,
                            duration_ms=duration_ms,
                            query_length=len(str(current_message)),
                            is_session_cumulative=True,  # 明确标记为会话累计值
                        )

                    logger.info(
                        "Token 审计",
                        extra={
                            "input_tokens": token_usage.input_tokens,
                            "output_tokens": token_usage.output_tokens,
                            "thinking_tokens": token_usage.thinking_tokens,
                            "cache_read_tokens": token_usage.cache_read_tokens,
                            "estimated_cost": agent.usage_tracker.estimate_cost(),
                        },
                    )

                    try:
                        await self.conversation_service.update_message(
                            message_id=assistant_message_id,
                            metadata={"usage": usage_response.model_dump(mode="json")},
                        )
                    except Exception as update_err:
                        logger.warning("更新 Usage 数据失败", extra={"error": str(update_err)})

                except Exception as audit_err:
                    logger.warning("Token 审计失败", extra={"error": str(audit_err)})

            logger.info(
                "Agent 执行完成", extra={"session_id": session_id, "duration_ms": duration_ms}
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
                        message_id=assistant_message_id, status="failed"
                    )
                except Exception as update_err:
                    logger.warning("更新消息状态失败", extra={"error": str(update_err)})

            # 分类错误类型（使用 ErrorClassifier，避免字符串匹配）
            classification = ErrorClassifier.classify(e)
            error_type = classification.error_type.value
            user_message = classification.user_message

            try:
                await events.system.emit_error(
                    session_id=session_id,
                    conversation_id=conversation_id,
                    error_type=error_type,
                    error_message=user_message,
                    details={"error_class": type(e).__name__, "duration_ms": duration_ms},
                    output_format=events.output_format,
                    adapter=events.adapter,
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
                    adapter=events.adapter,
                )
            except Exception as ex:
                logger.warning("发送 session_end 失败", extra={"error": str(ex)})

            # 不要 raise，避免 "Task exception was never retrieved"

        finally:
            # 🆕 V10.0: 失败经验总结（Service 层处理）
            # 在资源清理之前执行，确保上下文仍然可用
            if self.session_service and agent:
                try:
                    # 获取配置（轻量级，async）
                    failure_config = await get_failure_summary_config()

                    if failure_config.enabled:
                        # 映射 stop_reason
                        # - failed -> error
                        # - stopped -> user_stopped
                        # - completed -> end_turn (Agent 内部可能因 max_turns 结束，这里暂视为 end_turn)
                        stop_reason_map = {
                            "failed": "error",
                            "stopped": "user_stopped",
                            "completed": "end_turn",
                        }
                        stop_reason = stop_reason_map.get(execution_status, "unknown")

                        # 获取 context_strategy (尝试从 agent 获取，或使用默认)
                        context_strategy = getattr(agent, "context_strategy", None)
                        if not context_strategy:
                            context_strategy = get_context_strategy(self.qos_level)

                        intent_llm = await self.get_intent_llm()
                        failure_manager = FailureSummaryManager(
                            conversation_service=self.conversation_service,
                            llm_service=(
                                agent.llm if hasattr(agent, "llm") else intent_llm
                            ),  # 优先使用 agent 的 LLM
                            config=failure_config,
                            context_strategy=context_strategy,
                        )

                        await failure_manager.maybe_generate(
                            conversation_id=conversation_id,
                            stop_reason=stop_reason,
                            session_id=session_id,
                            user_id=user_id,
                            message_id=assistant_message_id,
                        )
                        logger.debug("失败经验总结检查完成", extra={"status": execution_status})
                except Exception as fs_err:
                    logger.warning("失败经验总结执行出错", extra={"error": str(fs_err)})

            # 确保资源始终释放，使用跟踪的执行状态
            try:
                await self._cleanup_session_resources(
                    session_id=session_id,
                    user_id=user_id,
                    agent_id=agent_id,
                    status=execution_status,
                )
                logger.debug(
                    "资源已释放",
                    extra={
                        "session_id": session_id,
                        "agent_id": agent_id,
                        "status": execution_status,
                    },
                )
            except Exception as cleanup_err:
                logger.error("资源清理失败", extra={"error": str(cleanup_err)}, exc_info=True)

            # 🆕 清理日志上下文
            clear_request_context()

    async def process_scheduled_task(
        self,
        user_id: str,
        conversation_id: str,
        prompt: str,
        task_id: str,
    ) -> Dict[str, Any]:
        """
        处理定时任务的 Agent 执行

        用于 UserTaskScheduler 调用，执行用户设定的定时 Agent 任务。
        与普通 chat() 的区别：
        - 不走 SSE 流
        - 简化的执行流程
        - 结果直接返回

        Args:
            user_id: 用户 ID
            conversation_id: 会话 ID
            prompt: 任务提示词
            task_id: 定时任务 ID

        Returns:
            执行结果
        """
        logger.info(
            f"🤖 执行定时 Agent 任务: task_id={task_id}, prompt={prompt[:50]}..."
        )

        try:
            # 动态获取当前实例的 Agent（优先 AGENT_INSTANCE 环境变量）
            import os
            agent_id = os.getenv("AGENT_INSTANCE", "default")
            agent_config = await self.agent_registry.get_agent(agent_id)

            if not agent_config:
                return {
                    "success": False,
                    "error": f"Agent 不存在: {agent_id}",
                    "task_id": task_id,
                }

            # 创建 Agent 实例
            agent = await self._create_agent(
                agent_config=agent_config,
                session_id=f"scheduled_{task_id}",
                conversation_id=conversation_id,
                user_id=user_id,
            )

            # 构造消息
            messages = [Message(role="user", content=prompt)]

            # 执行 Agent（非流式）
            response = await agent.chat(messages=messages)

            # 提取响应文本
            response_text = ""
            if hasattr(response, "content"):
                for block in response.content:
                    if hasattr(block, "text"):
                        response_text += block.text

            # 存储响应到会话
            await self.conversation_service.create_message(
                conversation_id=conversation_id,
                role="assistant",
                content=[{"type": "text", "text": response_text}],
                metadata={
                    "type": "scheduled_task_response",
                    "task_id": task_id,
                },
            )

            logger.info(f"✅ 定时 Agent 任务完成: task_id={task_id}")

            return {
                "success": True,
                "task_id": task_id,
                "response": response_text[:500],  # 截断长响应
            }

        except Exception as e:
            logger.error(f"❌ 定时 Agent 任务失败: task_id={task_id}, error={e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "task_id": task_id,
            }


_default_service: Optional[ChatService] = None


def get_chat_service(
    session_service: Optional[SessionService] = None,
) -> ChatService:
    """
    获取默认聊天服务单例
    """
    global _default_service
    if _default_service is None:
        _default_service = ChatService(
            session_service=session_service,
        )
    return _default_service


def reset_chat_service() -> None:
    """
    重置聊天服务单例（仅用于测试）
    """
    global _default_service
    _default_service = None
