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

# 1. 标准库
import asyncio
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import uuid4


from logger import get_logger
from core.agent import SimpleAgent
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
        qos_level: QoSLevel = QoSLevel.PRO,  # 🆕 P0: QoS 等级，默认 Pro
        enable_routing: bool = True,  # ✅ V7.2: 启用路由层（单/多智能体路由决策）
        multi_agent_config: Optional["MultiAgentConfig"] = None,  # ✅ V7.2: 多智能体配置
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
        
        # 日志记录初始化状态
        logger.info(
            f"✅ ChatService 初始化完成: qos_level={qos_level.value}, "
            f"compaction_threshold={self.compaction_threshold:,} tokens"
        )
        
        # 🆕 V7: 路由器（单智能体/多智能体路由决策）
        # enable_routing=False: 意图分析在 SimpleAgent 内部完成（向后兼容）
        # enable_routing=True: 意图分析在路由层完成，支持多智能体路由
        self.enable_routing = enable_routing
        self._router: Optional[AgentRouter] = None
        
        # 🆕 V8.1: 意图识别开关（暂时关闭，跳过 IntentAnalyzer 调用）
        # 设置为 False 时，跳过意图识别，使用默认的 IntentResult
        self.enable_intent_analysis = False  # TODO: 需要时改回 True
        
        # 🆕 V8.2: Preface 开场白开关（独立于意图识别）
        # 设置为 True 时，会在 Agent 响应前生成简短的开场白
        self.enable_preface = True
        
        if enable_routing:
            if self.enable_intent_analysis:
                logger.info("🔀 路由层已启用：意图分析将在路由层完成")
            else:
                logger.info("🔀 路由层已启用（意图识别已关闭）")
        
        # 🆕 V7: Token 审计器
        self.token_auditor: TokenAuditor = get_token_auditor()
        
    
    def _get_router(self, prompt_cache=None) -> AgentRouter:
        """
        延迟初始化路由器
        
        🆕 V7.6 修复：传入 LLM 服务，使意图分析真正调用 LLM
        使用 haiku 模型以获得更快的响应速度和更低的成本
        
        🆕 V7.6.1: 支持传入 prompt_cache（使用实例自定义的意图识别提示词）
        
        Args:
            prompt_cache: InstancePromptCache（可选，用于加载实例自定义的 intent_prompt）
        
        Returns:
            AgentRouter 实例
        """
        # 🆕 V7.6.1: 如果传入了 prompt_cache，需要重新创建 router（因为 prompt 可能不同）
        if self._router is None or prompt_cache is not None:
            # 🆕 V7.10: 创建轻量级 LLM 服务（用于意图分析）
            # 使用 haiku 模型：快速、低成本，适合分类任务
            # 🔧 使用 intent_analyzer profile（支持多模型容灾）
            intent_profile = get_llm_profile("intent_analyzer")
            routing_llm = create_llm_service(**intent_profile)
            
            self._router = AgentRouter(
                llm_service=routing_llm,
                enable_llm=True,
                prompt_cache=prompt_cache  # 🆕 V7.6.1: 传入实例级 prompt_cache
            )
            
            cache_info = "（使用实例自定义提示词）" if prompt_cache else "（使用默认提示词）"
            logger.info(f"🔀 AgentRouter 已初始化 {cache_info}")
        return self._router
    
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
    
    # ==================== 前置处理层 ====================
    
    async def _emit_intent_event(
        self,
        intent: "IntentResult",
        session_id: str,
        message_id: str,
        broadcaster
    ) -> None:
        """
        发送意图识别结果到前端
        
        从 SimpleAgent.chat() 阶段 2 移入，实现关注点分离。
        
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
        # 仅当 platform 有值时才添加
        if intent.platform:
            intent_content["platform"] = intent.platform
        
        intent_delta = {
            "type": "intent",
            "content": intent_content
        }
        
        await broadcaster.emit_message_delta(
            session_id=session_id,
            delta=intent_delta,
            message_id=message_id
        )
        
        logger.info(
            f"🎯 Intent 事件已发送: intent_id={intent.intent_id}, "
            f"intent_name={intent.intent_name}"
        )
    
    async def _generate_preface_stream(
        self,
        intent: "IntentResult",
        user_message: str,
        session_id: str,
        message_id: str,
        broadcaster,
        tracker=None
    ) -> Optional[str]:
        """
        流式生成 Preface 开场白（在 intent 之后执行）
        
        从 SimpleAgent 移入，实现关注点分离。
        使用 haiku 模型快速生成简短开场白，边生成边发送 delta 事件。
        
        Args:
            intent: 意图识别结果
            user_message: 用户原始消息
            session_id: Session ID
            message_id: 消息 ID
            broadcaster: EventBroadcaster 实例
            tracker: UsageTracker（可选，用于计费追踪）
            
        Returns:
            完整的开场白文本，失败返回 None
        """
        try:
            logger.info("📝 _generate_preface_stream: 开始执行")
            # 🆕 V7.10: 使用 haiku 模型：快速、低成本
            # 🔧 使用 intent_analyzer profile（支持多模型容灾）
            intent_profile = get_llm_profile("intent_analyzer")
            preface_llm = create_llm_service(**intent_profile)
            logger.info("📝 _generate_preface_stream: LLM 服务已创建")
            
            # 构建 Preface 生成提示词
            intent_info = f"意图: {intent.intent_name or intent.task_type.value}"
            if intent.platform:
                intent_info += f", 平台: {intent.platform}"
            
            prompt = f"""你是一个友好的AI助手。用户发送了一条消息，系统已识别出用户意图。
请生成一句简短的开场白（15-30字），让用户知道你已理解需求并即将开始处理。

要求：
1. 语气友好、专业
2. 简洁明了，不要啰嗦
3. 体现你理解了用户的需求
4. 不要重复用户的原话
5. 使用与用户相同的语言（中文/英文）

{intent_info}
用户消息: {user_message[:200]}

直接输出开场白，不要任何解释或前缀："""

            # 调用 LLM 流式生成 Preface
            llm_messages = [Message(role="user", content=prompt)]
            
            accumulated_text = ""
            final_response = None
            
            async for chunk in preface_llm.create_message_stream(
                messages=llm_messages,
                max_tokens=150
            ):
                # 流式输出内容
                if chunk.content and chunk.is_stream:
                    accumulated_text += chunk.content
                    # 发送流式 delta 事件
                    # persist=False: preface 不需要保存到数据库
                    await broadcaster.emit_message_delta(
                        session_id=session_id,
                        delta={"type": "preface", "content": chunk.content},
                        message_id=message_id,
                        persist=False
                    )
                
                # 保存最终响应（用于计费）
                if not chunk.is_stream:
                    final_response = chunk
            
            # 记录 Token 使用（如果提供了 tracker）
            if tracker and final_response:
                tracker.record_call(
                    llm_response=final_response,
                    model="claude-haiku-4-5-20251001",
                    purpose="preface"
                )
            
            preface_text = accumulated_text.strip()
            if preface_text:
                logger.info(f"✨ Preface 流式生成完成: {preface_text[:50]}...")
                return preface_text
            
            return None
            
        except Exception as e:
            logger.warning(f"⚠️ Preface 流式生成失败: {str(e)}")
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
    
    @asynccontextmanager
    async def acquire_agent_context(
        self,
        agent_id: str,
        session_id: str,
        user_id: str
    ):
        """
        Agent 资源上下文管理器
        
        自动管理 Agent 获取和释放，无论成功/失败/异常都能正确清理资源。
        
        用法：
            async with self.acquire_agent_context(agent_id, session_id, user_id) as agent:
                # 使用 agent
                await agent.chat(...)
            # 退出时自动释放 Agent 和更新 SessionPool
        
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
            # 获取 Agent
            agent = await self.agent_pool.acquire(
                agent_id=agent_id,
                event_manager=self.session_service.events,
                conversation_service=self.conversation_service
            )
            logger.debug(f"✅ Agent 已获取: {agent_id}")
            
            # 创建并注入共享 Tracker
            from core.billing.tracker import EnhancedUsageTracker
            shared_tracker = EnhancedUsageTracker()
            agent.usage_tracker = shared_tracker
            logger.debug(f"🔨 共享 Tracker 已注入: session_id={session_id}")
            
            # 更新 SessionPool 状态
            await self.session_pool.on_session_start(session_id, user_id, agent_id)
            session_pool_updated = True
            
            yield agent
            
        except Exception as e:
            logger.error(f"❌ Agent 上下文错误: {e}")
            raise AgentExecutionError(f"资源获取失败: {e}") from e
            
        finally:
            # 释放 Agent
            if agent is not None:
                try:
                    await self.agent_pool.release(agent_id)
                    logger.debug(f"🧹 Agent 已释放: {agent_id}")
                except Exception as e:
                    logger.warning(f"⚠️ 释放 Agent 失败: {e}")
            
            # 更新 SessionPool
            if session_pool_updated:
                try:
                    await self.session_pool.on_session_end(session_id, user_id, agent_id)
                except Exception as e:
                    logger.warning(f"⚠️ 更新 SessionPool 失败: {e}")
    
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
        6. 保存用户消息
        7. 创建 Assistant 占位
        8. 检查并发 + 创建 Session
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
        msg_preview = str(message)[:50] if message else ""
        logger.info(f"📨 对话请求: user={user_id}, agent={agent_id or '默认'}, conv={conversation_id}, msg_id={message_id}, msg={msg_preview}...")
        
        # ========== 1. 验证 agent_id ==========
        if agent_id:
            registry = get_agent_registry()
            if not registry.has_agent(agent_id):
                available = [a["agent_id"] for a in registry.list_agents()]
                raise AgentNotFoundError(f"Agent '{agent_id}' 不存在，可用: {available}")
        
        # ========== 2. 创建/校验 Conversation ==========
        try:
            conv, is_new_conversation = await self.conversation_service.get_or_create_conversation(
                user_id=user_id,
                conversation_id=conversation_id,
                title="新对话"
            )
            conversation_id = conv.id
        except Exception as e:
            raise ValueError(f"对话创建/校验失败: {e}") from e
        
        # ========== 3. 生成 assistant_message_id ==========
        assistant_message_id = str(uuid4())
        
        # ========== 4. 处理文件 ==========
        files_metadata = None
        raw_message = message  # 保存原始消息
        if files:
            processor = get_file_processor()
            # 统一转换为字典列表
            files_data = [
                f.model_dump() if hasattr(f, "model_dump") else f
                for f in files if isinstance(f, (dict,)) or hasattr(f, "model_dump")
            ]
            if files_data:
                processed_files = await processor.process_files(files_data)
                if processed_files:
                    # 提取文件元数据
                    files_metadata = [
                        {"file_url": pf.file_url, "file_name": pf.filename, 
                         "file_type": pf.mime_type, "file_size": pf.file_size}
                        for pf in processed_files
                    ]
                    # 获取原始消息文本
                    original_text = raw_message if isinstance(raw_message, str) else str(raw_message)
                    if isinstance(raw_message, list):
                        original_text = "".join(
                            b.get("text", "") for b in raw_message 
                            if isinstance(b, dict) and b.get("type") == "text"
                        )
                    # 构建 content blocks
                    raw_message = processor.build_message_content(processed_files, original_text)
                    logger.info(f"📎 文件处理完成: {len(files_metadata)} 个文件")
        
        # ========== 5. 标准化消息 ==========
        normalized_message = normalize_message_format(raw_message)
        
        # ========== 6. 保存用户消息 + 7. 创建 Assistant 占位 ==========
        content_json = json.dumps(normalized_message, ensure_ascii=False)
        user_message_id = None
        
        try:
            async with AsyncSessionLocal() as session:
                # 6. 保存用户消息（含文件元数据）
                user_metadata = {
                    "session_id": None,  # Session 尚未创建，后续可更新
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
                logger.info(f"💾 用户消息已保存: conversation_id={conversation_id}, message_id={user_message_id}, files={len(files_metadata) if files_metadata else 0}")
                
                # 7. 创建 Assistant 占位
                await crud.create_message(
                    session=session,
                    conversation_id=conversation_id,
                    role="assistant",
                    content="[]",
                    message_id=assistant_message_id,
                    status="processing",
                    metadata={
                        "model": self.default_model,
                    }
                )
                logger.info(f"✅ Assistant 占位已创建: id={assistant_message_id}")
        except Exception as e:
            logger.error(f"❌ 消息保存失败: {e}")
            raise ValueError(f"消息保存失败: {e}") from e
        
        # ========== 8. 检查并发 + 创建 Session ==========
        await self.session_pool.check_can_create_session(user_id)
        
        session_id = await self.session_service.create_session(
            user_id=user_id,
            message=message,
            conversation_id=conversation_id,
            message_id=message_id,
        )
        logger.info(f"✅ Session: {session_id}")
        
        # 更新用户消息的 session_id（可选，用于追踪）
        try:
            await self.conversation_service.update_message(
                message_id=user_message_id,
                metadata={"session_id": session_id}
            )
        except Exception as e:
            logger.warning(f"⚠️ 更新用户消息 session_id 失败: {e}")
        
        # ========== 9. 获取 Agent ==========
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
            
            # 创建共享 Tracker 并注入到 Agent
            from core.billing.tracker import EnhancedUsageTracker
            shared_tracker = EnhancedUsageTracker()
            agent.usage_tracker = shared_tracker
            logger.debug(f"🔨 共享 Tracker 已注入: session_id={session_id}")
            
            # 更新 SessionPool 状态
            await self.session_pool.on_session_start(session_id, user_id, pool_key)
            session_pool_updated = True
            
        except Exception as e:
            logger.error(f"❌ 资源获取失败: {e}")
            # 更新 Assistant 占位状态为 failed
            try:
                await self.conversation_service.update_message(
                    message_id=assistant_message_id,
                    status="failed"
                )
            except Exception as update_err:
                logger.warning(f"⚠️ 更新 Assistant 状态失败: {update_err}")
            # 清理 Session
            try:
                if agent_acquired:
                    await self.agent_pool.release(pool_key)
                await self.session_service.end_session(session_id, status="failed")
            except Exception as cleanup_error:
                logger.warning(f"⚠️ 清理失败: {cleanup_error}")
            raise AgentExecutionError(f"资源获取失败: {e}") from e
        
        # ========== 10. 调度执行 ==========
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
            
            logger.info(f"✅ 流式对话完成: {session_id}")
                
        except asyncio.CancelledError:
            # SSE 断开，Agent 继续后台运行
            logger.info(f"⚠️ SSE 断开，Agent 后台继续: {session_id}")
        
        except Exception as e:
            logger.error(f"❌ 流式对话失败: {e}", exc_info=True)
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
        
        # 将 events 和 redis 提前初始化，确保 except 块可以访问
        redis = self.session_service.redis
        events = self.session_service.events
        
        # 提前设置 output_format，确保 error 事件也使用正确的格式
        events.set_output_format(output_format, conversation_id)
        
        try:
            logger.info(f"🚀 Agent 开始执行: session_id={session_id}")
            
            # =================================================================
            # 阶段 1: 数据准备
            # =================================================================
            
            # 1.1 加载历史消息
            history_messages = []
            async with AsyncSessionLocal() as session:
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
                        # PostgreSQL JSONB 已自动反序列化，只对字符串类型解析
                        if isinstance(content, str):
                            content = json.loads(content) if content else []
                        elif content is None:
                            content = []
                    except json.JSONDecodeError:
                        logger.warning(f"JSON 解析失败: message_id={db_msg.id}")
                    
                    raw_messages.append({
                        "role": db_msg.role,
                        "content": content
                    })
                
                # 使用 adaptor 清理和分离消息（处理 thinking/index/tool_result）
                history_messages = ClaudeAdaptor.prepare_messages_from_db(raw_messages)
                
                logger.info(f"📚 历史消息已加载: conversation_id={conversation_id}, count={len(history_messages)} 条")
            
            # 1.2 注入前端变量到最新的用户消息（传给 LLM，但不保存到数据库）
            # 原因：前端上下文（时区、timestamp等）对 LLM 有用，但不应污染历史记录
            if variables and history_messages:
                # 获取最后一条用户消息（就是刚才保存的）
                last_message = history_messages[-1]
                if last_message.get("role") == "user":
                    context_text = format_variables(variables)
                    if append_text_to_last_block(last_message["content"], context_text):
                        logger.info(f"🌐 前端变量已注入到 LLM 消息: {list(variables.keys())}")
            
            # =================================================================
            # 阶段 2: 执行 Agent
            # =================================================================
            
            # 2.1 发送 message_start 事件（通知前端开始生成）
            await events.message.emit_message_start(
                session_id=session_id,
                conversation_id=conversation_id,
                message_id=assistant_message_id,
                model=self.default_model,
                output_format=events.output_format,
                adapter=events.adapter
            )
            
            # 2.2 上下文管理（裁剪历史消息）
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
            
            # 🆕 L2 策略：纯 token 驱动的上下文裁剪
            # 基于 token 预算而非消息数量，更精确地控制上下文长度
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
                    f"✂️ 历史裁剪: {trim_stats.original_count} → {trim_stats.trimmed_count} 条"
                )
            
            # L3: 后端 token 预警（用户无感知）
            if trim_stats.should_warn:
                logger.warning(
                    f"⚠️ Token 预警: {trim_stats.estimated_tokens:,} / {context_strategy.token_budget:,}"
                )
            
            # =====================================================================
            # 🆕 共享 Tracker 方案：使用 Agent 已注入的共享 Tracker（避免重复创建）
            # =====================================================================
            # shared_tracker 已在 chat() 方法中创建并注入到 agent.usage_tracker
            shared_tracker = agent.usage_tracker
            logger.debug(f"✅ 使用 Agent 的共享 Tracker: session_id={session_id}, tracker_id={id(shared_tracker)}")
            
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
            
            if self.enable_routing and self.enable_intent_analysis:
                # 🆕 V7.6.1: 传入 agent 的 prompt_cache（使用实例自定义的 intent_prompt）
                agent_prompt_cache = getattr(agent, 'prompt_cache', None)
                router = self._get_router(prompt_cache=agent_prompt_cache)
                routing_decision = await router.route(
                    user_query=message,
                    conversation_history=history_messages,
                    tracker=shared_tracker  # 🆕 传递共享 Tracker 用于意图识别计费
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
                
                # 🔧 DEBUG: 打印完整的 intent 结果
                if routing_intent:
                    logger.info(
                        f"🎯 Intent 详情: "
                        f"intent_id={routing_intent.intent_id}, "
                        f"intent_name={routing_intent.intent_name}, "
                        f"task_type={routing_intent.task_type.value}, "
                        f"complexity={routing_intent.complexity.value}, "
                        f"needs_plan={routing_intent.needs_plan}, "
                        f"confidence={routing_intent.confidence}"
                    )
            elif self.enable_routing and not self.enable_intent_analysis:
                # 🆕 V8.1: 意图识别已关闭，使用默认 IntentResult（跳过 LLM 调用）
                from core.agent.types import IntentResult, TaskType, Complexity
                routing_intent = IntentResult(
                    task_type=TaskType.OTHER,
                    complexity=Complexity.MEDIUM,
                    needs_plan=False,
                    intent_id=3,
                    intent_name="综合咨询",
                    confidence=1.0
                )
                logger.info("⏭️ 意图识别已跳过，使用默认 IntentResult")
            
            # 🆕 V8.2: 已移除 intent 事件发送（不再向前端发送意图识别结果）
            # routing_intent 仅用于内部逻辑（preface、后台任务等）
                
            # 生成 Preface 开场白（独立于意图识别）
            if self.enable_preface and routing_intent:
                user_text = extract_text_from_message(message)
                preface_text = await self._generate_preface_stream(
                    intent=routing_intent,
                    user_message=user_text,
                    session_id=session_id,
                    message_id=assistant_message_id,
                    broadcaster=agent.broadcaster,
                    tracker=shared_tracker
                )
                
                # 3. 将 preface 添加到消息历史（避免 Agent 重复生成）
                if preface_text:
                    history_messages.append({
                        "role": "assistant",
                        "content": [{"type": "text", "text": preface_text}]
                    })
                    logger.info(f"✨ Preface 已添加到上下文: len={len(preface_text)}")
            
            # 🆕 设置 Agent 的输出格式（EventBroadcaster 会使用）
            if hasattr(agent, 'broadcaster') and agent.broadcaster:
                agent.broadcaster.set_output_format(output_format, conversation_id)
            
            # 🔧 更新 Session context，增加 assistant_message_id
            # 工具（如 api_calling）可以通过 agent.event_manager.storage.get_session_context(session_id) 获取
            await redis.set_session_context(
                session_id=session_id,
                conversation_id=conversation_id,
                user_id=user_id,
                message_id=assistant_message_id  # 🆕 存储 assistant_message_id
            )
            logger.debug(f"🔑 Session context 已就绪: session_id={session_id}, conversation_id={conversation_id}, user_id={user_id}, message_id={assistant_message_id}")
            
            # 🔧 用于保存 assistant_text（在 message_stop 清理 accumulator 前获取）
            _assistant_text_for_tasks = ""
            
            # 根据路由决策选择执行路径
            if use_multi_agent:
                # ✅ V7.2: 多智能体执行
                logger.info(f"🚀 启用多智能体模式: session_id={session_id}")
                
                # 加载多智能体配置
                if self.multi_agent_config is None:
                    from core.agent.multi.models import load_multi_agent_config
                    self.multi_agent_config = await load_multi_agent_config()
                
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
                
                # 🔧 在 message_stop 前执行后台任务（保证 recommended 在 done 之前）
                if background_tasks:
                    accumulator = agent.broadcaster.get_accumulator(session_id)
                    if accumulator:
                        _assistant_text_for_tasks = extract_text_from_message(
                            accumulator.build_for_db()
                        )
                    
                    # 执行后台任务
                    user_text = extract_text_from_message(message)
                    task_context = TaskContext(
                        session_id=session_id,
                        conversation_id=conversation_id,
                        user_id=user_id,
                        message_id=assistant_message_id,
                        user_message=user_text,
                        assistant_response=_assistant_text_for_tasks,
                        is_new_conversation=is_new_conversation,
                        event_manager=events,
                        conversation_service=self.conversation_service,
                        # 🆕 V7.7: 传递 intent_id 到后台任务（用于 clue_generation 判断）
                        metadata={"intent_id": routing_intent.intent_id if routing_intent else None}
                    )
                    await self.background_tasks.dispatch_tasks(
                        task_names=background_tasks,
                        context=task_context
                    )
                    # 标记已执行，阶段 3 不再重复执行
                    background_tasks = []
                
                # 🆕 修复：多智能体分支结束后，需要触发 message_stop 和最终持久化
                # 否则 assistant 占位会一直停在 processing，历史里看不到最终内容
                await agent.broadcaster.emit_message_stop(
                    session_id=session_id,
                    message_id=assistant_message_id
                )
                logger.info(f"✅ 多智能体执行完成，已触发 message_stop: {session_id}")
            else:
                # 🎯 单智能体执行
                # 🆕 V8.0: 意图事件和 Preface 已在服务层完成
                # - 内容累积：broadcaster 自动处理 content_start/delta/stop
                # - Checkpoint：broadcaster 在每个 content_stop 后自动保存
                # - 最终保存：broadcaster 在 message_stop 时自动完成
                # - variables：直接注入到 System Prompt（前端上下文）
                
                async for event in agent.chat(
                    messages=history_messages,
                    session_id=session_id,
                    conversation_id=conversation_id,
                    message_id=assistant_message_id,
                    enable_stream=True,
                    variables=variables
                ):
                    # 跳过被过滤的事件（ZenO 适配器返回 None）
                    if event is None:
                        continue
                    
                    # 检查停止标志（异步）
                    if await redis.is_stopped(session_id):
                        logger.warning(f"🛑 检测到停止标志: session_id={session_id}")
                        
                        # 发送 billing 事件（使用 Agent 的 Tracker，已经是共享的）
                        try:
                            # 1. 生成 UsageResponse（Agent 的 Tracker 已经是共享的）
                            usage_response = UsageResponse.from_usage_tracker(
                                tracker=agent.usage_tracker,  # 使用 Agent 的 Tracker（已注入共享 Tracker）
                                model=agent.model,
                                latency=int((time.time() - start_time) * 1000)
                            )
                            
                            # 2. 发送 billing 事件到前端
                            await agent.broadcaster.emit_message_delta(
                                session_id=session_id,
                                delta={
                                    "type": "billing",
                                    "content": usage_response.model_dump(mode='json')
                                },
                                message_id=assistant_message_id,
                                persist=False
                            )
                            logger.info(f"📊 中止时已发送 billing 事件: total_price=${usage_response.total_price:.6f}")
                            
                            # 3. 保存 usage 到数据库
                            await agent.broadcaster.accumulate_usage(
                                session_id=session_id,
                                usage=usage_response.model_dump(mode='json')
                            )
                        except Exception as e:
                            logger.error(f"❌ 中止时发送 billing 事件失败: {str(e)}", exc_info=True)
                        
                        # 4. finalize 消息
                        await agent.broadcaster.finalize_message(session_id)
                        
                        # 5. 发送 message_stop 事件（对应 ZenO 的 message.assistant.done）
                        # 🔧 修复：中止时必须发送 done 来正确结束 SSE 流
                        await agent.broadcaster.emit_message_stop(
                            session_id=session_id,
                            message_id=assistant_message_id
                        )
                        logger.info(f"✅ 中止时已发送 message_stop (done) 事件")
                        
                        # 6. 发送 session_stopped 事件（在 done 之后）
                        await events.session.emit_session_stopped(
                            session_id=session_id,
                            conversation_id=conversation_id,
                            reason="user_requested",
                            output_format=events.output_format,
                            adapter=events.adapter
                        )
                        
                        # 7. 结束 session
                        await self.session_service.end_session(session_id, status="stopped")
                        break
                    
                    # 🎯 只处理需要额外逻辑的事件
                    event_type = event.get("type", "")
                    
                    # 🔧 在收到 billing 事件时执行后台任务（在 message_stop 前）
                    # 事件顺序：... → billing → [recommended] → message_stop → session_end
                    # 这样 recommended 会在 message.assistant.done 之前发送
                    if event_type in ("message_delta", "message.assistant.delta") and background_tasks:
                        delta = event.get("data", {}).get("delta", {})
                        # 兼容 ZenO 格式（delta 直接在 event 中）
                        if not delta:
                            delta = event.get("delta", {})
                        if delta.get("type") == "billing":
                            # 1. 保存 assistant_text
                            accumulator = agent.broadcaster.get_accumulator(session_id)
                            if accumulator:
                                _assistant_text_for_tasks = extract_text_from_message(
                                    accumulator.build_for_db()
                                )
                                logger.debug(f"🔧 已保存 assistant_text: {len(_assistant_text_for_tasks)} 字符")
                            
                            # 2. 执行后台任务（在 message_stop 之前）
                            user_text = extract_text_from_message(message)
                            task_context = TaskContext(
                                session_id=session_id,
                                conversation_id=conversation_id,
                                user_id=user_id,
                                message_id=assistant_message_id,
                                user_message=user_text,
                                assistant_response=_assistant_text_for_tasks,
                                is_new_conversation=is_new_conversation,
                                event_manager=events,
                                conversation_service=self.conversation_service,
                                # 🆕 V7.7: 传递 intent_id 到后台任务（用于 clue_generation 判断）
                                metadata={"intent_id": routing_intent.intent_id if routing_intent else None}
                            )
                            await self.background_tasks.dispatch_tasks(
                                task_names=background_tasks,
                                context=task_context
                            )
                            # 标记已执行，阶段 3 不再重复执行
                            background_tasks = []
                    
                    if event_type == "conversation_delta":
                        # conversation 更新同步到数据库
                        await apply_conversation_delta(self.conversation_service, event, conversation_id)
            
            # =================================================================
            # 阶段 3: 完成处理
            # =================================================================
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            # 🔧 使用事件循环中保存的 assistant_text（在 message_stop 清理 accumulator 前获取）
            assistant_text = _assistant_text_for_tasks
            
            # 3.1 检查最终状态
            final_status = await redis.get_session_status(session_id)
            status = final_status.get("status") if final_status else "completed"
            
            if status != "stopped":
                # 3.2 执行后台任务（回退机制）
                # 注意：正常情况下后台任务已在 billing 事件时执行（message_stop 之前）
                # 这里作为回退，防止 billing 事件未触发的情况
                if background_tasks:
                    user_text = extract_text_from_message(message)
                    
                    task_context = TaskContext(
                        session_id=session_id,
                        conversation_id=conversation_id,
                        user_id=user_id,
                        message_id=assistant_message_id,
                        user_message=user_text,
                        assistant_response=assistant_text,  # 使用提前获取的 assistant_text
                        is_new_conversation=is_new_conversation,
                        event_manager=events,
                        conversation_service=self.conversation_service,
                        # 🆕 V7.7: 传递 intent_id 到后台任务（用于 clue_generation 判断）
                        metadata={"intent_id": routing_intent.intent_id if routing_intent else None}
                    )
                    
                    await self.background_tasks.dispatch_tasks(
                        task_names=background_tasks,
                        context=task_context
                    )
                
                # 3.3 发送完成事件（在后台任务之后，确保推荐问题等已发送）
                await events.session.emit_session_end(
                    session_id=session_id,
                    conversation_id=conversation_id,
                    status="completed",
                    duration_ms=duration_ms,
                    output_format=events.output_format,
                    adapter=events.adapter
                )
                await self.session_service.end_session(session_id, status="completed")
            
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
                    f"📊 Token 审计: input={token_usage.input_tokens:,}, "
                    f"output={token_usage.output_tokens:,}, "
                    f"thinking={token_usage.thinking_tokens:,}, "
                    f"cache_read={token_usage.cache_read_tokens:,}, "
                    f"total_price=${usage_response.total_price:.6f}"
                )
                
                # ✅ 补充更新：将完整的 usage（包含 latency）更新到消息
                # 注意：Agent 已经发送了 message_stop 并保存了基础数据（latency=0）
                # 这里更新消息的 metadata.usage 字段
                try:
                    await self.conversation_service.update_message(
                        message_id=assistant_message_id,
                        metadata={"usage": usage_response.model_dump(mode='json')}
                    )
                    logger.debug(f"✅ 完整 Usage 数据已补充更新 (latency={duration_ms / 1000.0:.2f}s)")
                except Exception as update_err:
                    logger.warning(f"⚠️ 更新 Usage 数据失败: {update_err}")
                
            except Exception as audit_err:
                logger.warning(f"⚠️ Token 审计失败: {audit_err}")
            
            logger.info(f"✅ Agent 执行完成: session_id={session_id}, duration={duration_ms}ms")
        
        except Exception as e:
            logger.error(f"❌ Agent 执行失败: {str(e)}", exc_info=True)
            duration_ms = int((time.time() - start_time) * 1000)
            
            # 🆕 修复：更新 assistant 消息状态（避免 DB 留下 processing 占位）
            if assistant_message_id:
                try:
                    await self.conversation_service.update_message(
                        message_id=assistant_message_id,
                        status="failed"
                    )
                    logger.debug(f"📝 Assistant 消息状态已更新为 failed: {assistant_message_id}")
                except Exception as update_err:
                    logger.warning(f"⚠️ 更新消息状态失败: {update_err}")
            
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
            
            # 🎯 发送详细的错误事件到前端（使用正确的输出格式）
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
                logger.warning(f"⚠️ 发送错误事件失败: {str(ex)}")
            
            # 🎯 发送 session_end 事件（使用正确的输出格式）
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
                logger.warning(f"⚠️ 发送 session_end 失败: {str(ex)}")
            
            # 注：Session 状态将在 finally 块中清理
            
            # ⚠️ 不要 raise，避免 "Task exception was never retrieved"
            # 异常已经通过事件和日志记录，不需要传播
        
        finally:
            # 🆕 修复：确保资源始终释放（成功/失败/停止都执行）
            # 无论正常完成、异常失败还是被停止，都需要释放 Agent 和更新 SessionPool
            try:
                await self._cleanup_session_resources(
                    session_id=session_id,
                    user_id=user_id,
                    agent_id=agent_id,
                    status="completed"  # 这里的 status 只影响 Session，不影响 Message
                )
                logger.debug(f"🧹 资源已释放: session_id={session_id}, agent_id={agent_id}")
            except Exception as cleanup_err:
                logger.error(f"❌ 资源清理失败: {cleanup_err}", exc_info=True)
    
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
    
# ==================== 便捷函数 ====================

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
                f"发送 LLM 切换事件失败: {e}",
                extra={"session_id": session_id},
                exc_info=True
            )
    
    async def _probe_llm_service(
        self,
        llm_service: Any,
        session_id: str,
        role: str = "simple_agent"
    ) -> Optional[dict]:
        """
        请求级 LLM 探针（条件探测策略）
        
        仅在后台健康探测不健康时执行，避免阻塞用户请求
        
        Args:
            llm_service: LLM 服务实例（可能是 ModelRouter）
            session_id: 会话 ID
            role: Agent 角色
        
        Returns:
            探测结果字典，如果跳过探测则返回 None
        """
        # 检查是否是 ModelRouter
        from core.llm.router import ModelRouter
        if not isinstance(llm_service, ModelRouter):
            return None
        
        # V7.11 条件探测策略：检查后台健康状态
        from services.health_probe_service import get_health_probe_service
        health_service = get_health_probe_service()
        
        if health_service and health_service.is_healthy(role):
            # 后台健康，跳过请求级探测
            logger.debug(
                "后台健康探测正常，跳过请求级探测",
                extra={"session_id": session_id, "role": role}
            )
            return None
        
        # 后台不健康，执行请求级探测确认
        try:
            import os
            timeout = float(os.getenv("LLM_PROBE_TIMEOUT", "5.0"))
            
            logger.info(
                "后台健康探测异常，执行请求级探测确认",
                extra={"session_id": session_id, "role": role, "timeout": timeout}
            )
            
            probe_result = await asyncio.wait_for(
                llm_service.probe(max_retries=0),
                timeout=timeout
            )
            
            # 如果发生切换，发送事件
            if probe_result.get("switched"):
                await self._emit_llm_switch_event(
                    session_id=session_id,
                    probe_result=probe_result,
                    role=role
                )
            
            return probe_result
            
        except asyncio.TimeoutError:
            logger.warning(
                f"请求级探测超时 ({timeout}s)",
                extra={"session_id": session_id, "role": role}
            )
            return None
        except Exception as e:
            logger.error(
                f"请求级探测失败: {e}",
                extra={"session_id": session_id, "role": role},
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
