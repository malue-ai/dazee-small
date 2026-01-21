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
        
        # Mock 模式（通过配置启用，chat() 接口自动返回 mock 数据）
        # 设置环境变量 ENABLE_MOCK_MODE=true 或初始化时传入 enable_mock=True
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
        enable_mock: bool = True,  # 🆕 Mock 模式：启用后 chat() 返回 mock 数据
        mock_scenario: str = "analytics"  # 🆕 Mock 场景：analytics / build
    ):
        # Session 管理
        self.session_service = session_service or get_session_service()
        self.default_model = default_model
        
        # 🆕 Mock 模式配置
        self.enable_mock = enable_mock
        self.mock_scenario = mock_scenario
        
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
        mock_status = f"mock_mode={enable_mock}, scenario={mock_scenario}" if enable_mock else "mock_mode=disabled"
        logger.info(
            f"✅ ChatService 初始化完成: qos_level={qos_level.value}, "
            f"compaction_threshold={self.compaction_threshold:,} tokens, {mock_status}"
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
        output_format: str = "zenflux",
        mock_scenario: Optional[str] = None  # 🆕 允许请求级别覆盖 mock 场景
    ):
        """
        统一的对话入口 ⭐
        
        根据 stream 参数自动选择模式：
        - stream=True  → 返回 AsyncGenerator，用于 SSE
        - stream=False → 返回 Dict，用于 API 集成
        
        Mock 模式：
        - 当 enable_mock=True 时，直接返回 mock 数据，不调用真实 Agent
        - 可通过 mock_scenario 参数指定场景（analytics/build）
        
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
            mock_scenario: Mock 场景（可选，覆盖服务级别配置）
            
        Returns:
            stream=True  → AsyncGenerator
            stream=False → Dict
        """
        msg_preview = str(message)[:50] if message else ""
        
        # 🆕 Mock 模式：直接返回 mock 数据
        if self.enable_mock:
            scenario = mock_scenario or self.mock_scenario
            logger.info(f"🎭 Mock 模式: user={user_id}, scenario={scenario}, msg={msg_preview}...")
            
            if stream:
                # 流式模式：返回 mock 事件流
                return self.chat_mock(scenario=scenario, delay_ms=50)
            else:
                # 同步模式：返回 mock 任务信息
                mock_session_id = f"mock_sess_{uuid4().hex[:12]}"
                mock_conv_id = conversation_id or f"mock_conv_{uuid4().hex[:12]}"
                return {
                    "task_id": mock_session_id,
                    "conversation_id": mock_conv_id,
                    "message": "[Mock] 任务已启动",
                    "status": "running",
                    "mock": True
                }
        
        logger.info(f"📨 对话请求: user={user_id}, agent={agent_id or '默认'}, msg={msg_preview}...")
        
        # ========== 1. 验证 agent_id ==========
        if agent_id:
            registry = get_agent_registry()
            if not registry.has_agent(agent_id):
                available = [a["agent_id"] for a in registry.list_agents()]
                raise AgentNotFoundError(f"Agent '{agent_id}' 不存在，可用: {available}")
        
        # ========== 2. 创建/校验 Conversation ==========
        is_new_conversation = False
        if not conversation_id:
            # 创建新对话
            async with AsyncSessionLocal() as session:
                conv = await crud.create_conversation(session=session, user_id=user_id, title="新对话")
                conversation_id = conv.id
                is_new_conversation = True
                logger.info(f"✅ 新对话: {conversation_id}")
        else:
            # 🆕 修复：校验 conversation_id 存在性和归属
            try:
                conv = await self.conversation_service.get_conversation(conversation_id)
                if conv.user_id != user_id:
                    raise ValueError(f"对话 {conversation_id} 不属于用户 {user_id}")
                logger.debug(f"✅ 对话校验通过: {conversation_id}")
            except ConversationNotFoundError:
                raise ValueError(f"对话 {conversation_id} 不存在")
            except Exception as e:
                raise ValueError(f"对话校验失败: {e}") from e
        
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
        assistant_message_id = None  # 用于异常处理时更新状态
        
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
            
            assistant_message_id = uuid4().hex  # 提升到外层，供异常处理使用
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
                
                # 🆕 修复：多智能体分支结束后，需要触发 message_stop 和最终持久化
                # 否则 assistant 占位会一直停在 processing，历史里看不到最终内容
                await agent.broadcaster.emit_message_stop(
                    session_id=session_id,
                    message_id=assistant_message_id
                )
                logger.info(f"✅ 多智能体执行完成，已触发 message_stop: {session_id}")
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
                        # 🆕 修复：先 checkpoint 当前累积内容，再 finalize
                        # 使用公开方法 finalize_message（会先 checkpoint），而不是 _finalize_message
                        await agent.broadcaster.finalize_message(session_id)
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
                
                # 🆕 V7.4: 发送 usage SSE 事件
                try:
                    await events.system.emit_custom(
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
    
    # ==================== Mock 数据返回（用于前端测试）====================
    
    async def chat_mock(
        self,
        scenario: str = "analytics",
        delay_ms: int = 50
    ) -> AsyncGenerator[str, None]:
        """
        返回 Mock SSE 事件流（用于前端测试和演示）
        
        Args:
            scenario: 场景类型，支持 "analytics"（智能分析）和 "build"（系统搭建）
            delay_ms: 事件之间的延迟（毫秒），默认 50ms
            
        Yields:
            SSE 格式的事件字符串
            
        使用示例：
            async for event in service.chat_mock(scenario="analytics"):
                yield event
        """
        import time
        
        # 生成唯一标识
        timestamp_base = int(time.time() * 1000)
        session_id = f"sess_mock_{uuid4().hex[:12]}"
        message_id = f"msg_{session_id}"
        conversation_id = f"conv_mock_{uuid4().hex[:12]}"
        
        # 根据场景选择 mock 数据
        if scenario == "build":
            events = self._get_mock_events_build(
                session_id=session_id,
                message_id=message_id,
                conversation_id=conversation_id,
                timestamp_base=timestamp_base
            )
        else:
            # 默认使用 analytics 场景
            events = self._get_mock_events_analytics(
                session_id=session_id,
                message_id=message_id,
                conversation_id=conversation_id,
                timestamp_base=timestamp_base
            )
        
        # 逐个发送事件
        delay_s = delay_ms / 1000.0
        for event in events:
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            await asyncio.sleep(delay_s)
        
        logger.info(f"✅ Mock 数据发送完成: scenario={scenario}, events={len(events)}")
    
    def _get_mock_events_analytics(
        self,
        session_id: str,
        message_id: str,
        conversation_id: str,
        timestamp_base: int
    ) -> List[Dict[str, Any]]:
        """
        获取智能分析场景的 Mock 事件序列
        
        包含：intent → thinking → progress → sql → data → chart → mind → report → response → files → recommended → done
        """
        seq = 0
        events = []
        
        def next_event(event_type: str, **kwargs) -> Dict[str, Any]:
            nonlocal seq
            seq += 1
            base = {
                "type": event_type,
                "message_id": message_id,
                "session_id": session_id,
                "seq": seq,
                "timestamp": timestamp_base + seq * 50
            }
            if seq == 1:
                base["conversation_id"] = conversation_id
            base.update(kwargs)
            return base
        
        # 1. message.assistant.start
        events.append(next_event("message.assistant.start"))
        
        # 2. intent
        events.append(next_event(
            "message.assistant.delta",
            delta={"type": "intent", "content": json.dumps({
                "intent_id": 2,
                "intent_name": "智能分析",
                "platform": "analytics"
            }, ensure_ascii=False)}
        ))
        
        # 3. thinking（分段发送）
        thinking_parts = [
            "用", "户想要", "分析", "本月的", "销售数据，", "这是一个", "智能分析", "场景。",
            "\n\n我需要：", "\n1. 首先", "构建SQL", "查询语句", "，从订单表", "中获取数据",
            "\n2. 然后", "生成可视化", "图表", "进行展示",
            "\n3. 最后", "总结分析", "结果并", "给出建议",
            "\n\n让我", "开始执行", "这个分析", "任务..."
        ]
        for part in thinking_parts:
            events.append(next_event(
                "message.assistant.delta",
                delta={"type": "thinking", "content": part}
            ))
        
        # 4. progress - 开始
        events.append(next_event(
            "message.assistant.delta",
            delta={"type": "progress", "content": json.dumps({
                "title": "销售数据分析",
                "status": "running",
                "current": 0,
                "total": 4,
                "subtasks": [
                    {"title": "构建查询", "status": "running", "desc": ""},
                    {"title": "执行查询", "status": "pending", "desc": ""},
                    {"title": "生成图表", "status": "pending", "desc": ""},
                    {"title": "生成报告", "status": "pending", "desc": ""}
                ]
            }, ensure_ascii=False)}
        ))
        
        # 5. SQL
        sql_content = """SELECT 
  product_name,
  product_category,
  SUM(quantity) as total_quantity,
  SUM(sales_amount) as total_sales,
  COUNT(DISTINCT order_id) as order_count
FROM orders o
JOIN products p ON o.product_id = p.id
WHERE order_date >= '2026-01-01' 
  AND order_date < '2026-02-01'
GROUP BY product_name, product_category
ORDER BY total_sales DESC
LIMIT 10"""
        events.append(next_event(
            "message.assistant.delta",
            delta={"type": "sql", "content": sql_content}
        ))
        
        # 6. progress - SQL 完成
        events.append(next_event(
            "message.assistant.delta",
            delta={"type": "progress", "content": json.dumps({
                "title": "销售数据分析",
                "status": "running",
                "current": 1,
                "total": 4,
                "subtasks": [
                    {"title": "构建查询", "status": "success", "desc": "SQL已生成"},
                    {"title": "执行查询", "status": "running", "desc": ""},
                    {"title": "生成图表", "status": "pending", "desc": ""},
                    {"title": "生成报告", "status": "pending", "desc": ""}
                ]
            }, ensure_ascii=False)}
        ))
        
        # 7. data
        data_content = [
            {"product_name": "智能手表Pro", "product_category": "电子产品", "total_quantity": 1250, "total_sales": 187500, "order_count": 892},
            {"product_name": "无线蓝牙耳机", "product_category": "电子产品", "total_quantity": 2100, "total_sales": 147000, "order_count": 1560},
            {"product_name": "运动跑鞋X1", "product_category": "运动服饰", "total_quantity": 1800, "total_sales": 126000, "order_count": 1420},
            {"product_name": "羽绒服冬季款", "product_category": "服装", "total_quantity": 680, "total_sales": 108800, "order_count": 520},
            {"product_name": "智能台灯", "product_category": "家居", "total_quantity": 1500, "total_sales": 97500, "order_count": 1280}
        ]
        events.append(next_event(
            "message.assistant.delta",
            delta={"type": "data", "content": json.dumps(data_content, ensure_ascii=False)}
        ))
        
        # 8. progress - 查询完成
        events.append(next_event(
            "message.assistant.delta",
            delta={"type": "progress", "content": json.dumps({
                "title": "销售数据分析",
                "status": "running",
                "current": 2,
                "total": 4,
                "subtasks": [
                    {"title": "构建查询", "status": "success", "desc": "SQL已生成"},
                    {"title": "执行查询", "status": "success", "desc": "获取5条记录"},
                    {"title": "生成图表", "status": "running", "desc": ""},
                    {"title": "生成报告", "status": "pending", "desc": ""}
                ]
            }, ensure_ascii=False)}
        ))
        
        # 9. chart - 柱状图
        chart_bar = {
            "title": {"text": "本月产品销售额排行榜", "subtext": "2026年1月", "left": "center"},
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
            "legend": {"data": ["销售额", "订单数"], "top": "bottom"},
            "xAxis": {
                "type": "category",
                "data": ["智能手表Pro", "无线蓝牙耳机", "运动跑鞋X1", "羽绒服冬季款", "智能台灯"],
                "axisLabel": {"rotate": 45}
            },
            "yAxis": [
                {"type": "value", "name": "销售额(元)", "position": "left"},
                {"type": "value", "name": "订单数", "position": "right"}
            ],
            "series": [
                {"name": "销售额", "type": "bar", "data": [187500, 147000, 126000, 108800, 97500], "itemStyle": {"color": "#5470c6"}},
                {"name": "订单数", "type": "line", "yAxisIndex": 1, "data": [892, 1560, 1420, 520, 1280], "itemStyle": {"color": "#91cc75"}}
            ]
        }
        events.append(next_event(
            "message.assistant.delta",
            delta={"type": "chart", "content": json.dumps(chart_bar, ensure_ascii=False)}
        ))
        
        # 10. chart - 饼图
        chart_pie = {
            "title": {"text": "各品类销售占比", "left": "center"},
            "tooltip": {"trigger": "item", "formatter": "{a} <br/>{b}: {c} ({d}%)"},
            "legend": {"orient": "vertical", "left": "left"},
            "series": [{
                "name": "品类销售",
                "type": "pie",
                "radius": ["40%", "70%"],
                "data": [
                    {"value": 334500, "name": "电子产品"},
                    {"value": 126000, "name": "运动服饰"},
                    {"value": 97500, "name": "家居"},
                    {"value": 108800, "name": "服装"}
                ]
            }]
        }
        events.append(next_event(
            "message.assistant.delta",
            delta={"type": "chart", "content": json.dumps(chart_pie, ensure_ascii=False)}
        ))
        
        # 11. mind - 脑图
        mind_content = {
            "mermaid_content": """mindmap
  root((销售分析))
    电子产品
      智能手表Pro: 18.75万
      无线蓝牙耳机: 14.7万
    运动服饰
      运动跑鞋X1: 12.6万
    家居
      智能台灯: 9.75万
    服装
      羽绒服: 10.88万""",
            "chart_type": "mindmap"
        }
        events.append(next_event(
            "message.assistant.delta",
            delta={"type": "mind", "content": json.dumps(mind_content, ensure_ascii=False)}
        ))
        
        # 12. progress - 图表完成
        events.append(next_event(
            "message.assistant.delta",
            delta={"type": "progress", "content": json.dumps({
                "title": "销售数据分析",
                "status": "running",
                "current": 3,
                "total": 4,
                "subtasks": [
                    {"title": "构建查询", "status": "success", "desc": "SQL已生成"},
                    {"title": "执行查询", "status": "success", "desc": "获取5条记录"},
                    {"title": "生成图表", "status": "success", "desc": "已生成3个图表"},
                    {"title": "生成报告", "status": "running", "desc": ""}
                ]
            }, ensure_ascii=False)}
        ))
        
        # 13. report
        report_content = {
            "title": "2026年1月销售数据分析报告",
            "summary": "本月总销售额达到66.68万元，电子产品品类表现最佳，占比50.2%",
            "sections": [
                {"title": "销售概览", "content": "本月共产生5,572笔订单，涉及5款热销产品，总销售额66.68万元。"},
                {"title": "热销产品分析", "content": "TOP3产品分别是：智能手表Pro（18.75万）、无线蓝牙耳机（14.7万）、运动跑鞋X1（12.6万）。"},
                {"title": "趋势与建议", "content": "1. 建议加大智能手表Pro的推广力度\n2. 电子产品品类可继续拓展新品"}
            ]
        }
        events.append(next_event(
            "message.assistant.delta",
            delta={"type": "report", "content": json.dumps(report_content, ensure_ascii=False)}
        ))
        
        # 14. progress - 全部完成
        events.append(next_event(
            "message.assistant.delta",
            delta={"type": "progress", "content": json.dumps({
                "title": "销售数据分析",
                "status": "completed",
                "current": 4,
                "total": 4,
                "subtasks": [
                    {"title": "构建查询", "status": "success", "desc": "SQL已生成"},
                    {"title": "执行查询", "status": "success", "desc": "获取5条记录"},
                    {"title": "生成图表", "status": "success", "desc": "已生成3个图表"},
                    {"title": "生成报告", "status": "success", "desc": "报告已生成"}
                ]
            }, ensure_ascii=False)}
        ))
        
        # 15. response（分段发送）
        response_parts = [
            "根据", "您的", "需求，", "我已完成", "本月", "销售数据", "分析，", "主要", "发现", "如下：",
            "\n\n", "## 📊", " 销售", "概览", "\n\n",
            "- **总销售额**", "：66.68万元", "\n- **总订单数**", "：5,572笔", "\n- **热销产品**", "：5款",
            "\n\n", "## 🏆", " TOP3", " 热销产品", "\n\n",
            "| 排名 |", " 产品名称 |", " 销售额 |", "\n|:---:|", "------|", "------:|",
            "\n| 🥇 |", " 智能手表Pro |", " 18.75万 |",
            "\n| 🥈 |", " 无线蓝牙耳机 |", " 14.7万 |",
            "\n| 🥉 |", " 运动跑鞋X1 |", " 12.6万 |",
            "\n\n", "以上图表", "和报告", "已为您", "生成完毕。"
        ]
        for part in response_parts:
            events.append(next_event(
                "message.assistant.delta",
                delta={"type": "response", "content": part}
            ))
        
        # 16. files
        files_content = [
            {"name": "sales_report_202601.xlsx", "type": "xlsx", "url": "https://cdn.example.com/files/sales_report_202601.xlsx", "size": 156800},
            {"name": "sales_chart_bar.png", "type": "image", "url": "https://cdn.example.com/files/sales_chart_bar.png", "size": 89600}
        ]
        events.append(next_event(
            "message.assistant.delta",
            delta={"type": "files", "content": json.dumps(files_content, ensure_ascii=False)}
        ))
        
        # 17. recommended
        recommended_content = {"questions": ["查看上月销售对比", "分析各区域销售情况", "查看电子产品品类详情", "预测下月销售趋势"]}
        events.append(next_event(
            "message.assistant.delta",
            delta={"type": "recommended", "content": json.dumps(recommended_content, ensure_ascii=False)}
        ))
        
        # 18. message.assistant.done
        final_content = """根据您的需求，我已完成本月销售数据分析，主要发现如下：

## 📊 销售概览

- **总销售额**：66.68万元
- **总订单数**：5,572笔
- **热销产品**：5款

## 🏆 TOP3 热销产品

| 排名 | 产品名称 | 销售额 |
|:---:|------|------:|
| 🥇 | 智能手表Pro | 18.75万 |
| 🥈 | 无线蓝牙耳机 | 14.7万 |
| 🥉 | 运动跑鞋X1 | 12.6万 |

以上图表和报告已为您生成完毕。"""
        events.append(next_event(
            "message.assistant.done",
            data={"content": final_content}
        ))
        
        return events
    
    def _get_mock_events_build(
        self,
        session_id: str,
        message_id: str,
        conversation_id: str,
        timestamp_base: int
    ) -> List[Dict[str, Any]]:
        """
        获取系统搭建场景的 Mock 事件序列
        
        包含：intent → thinking → progress → mind → response → files → application → recommended → done
        """
        seq = 0
        events = []
        
        def next_event(event_type: str, **kwargs) -> Dict[str, Any]:
            nonlocal seq
            seq += 1
            base = {
                "type": event_type,
                "message_id": message_id,
                "session_id": session_id,
                "seq": seq,
                "timestamp": timestamp_base + seq * 50
            }
            if seq == 1:
                base["conversation_id"] = conversation_id
            base.update(kwargs)
            return base
        
        # 1. message.assistant.start
        events.append(next_event("message.assistant.start"))
        
        # 2. intent
        events.append(next_event(
            "message.assistant.delta",
            delta={"type": "intent", "content": json.dumps({
                "intent_id": 1,
                "intent_name": "系统搭建",
                "platform": "ontology"
            }, ensure_ascii=False)}
        ))
        
        # 3. thinking（分段发送）
        thinking_parts = [
            "用户", "想要", "搭建一个", "待办事项", "管理系统，", "这是一个", "系统搭建", "任务。",
            "\n\n我需要：", "\n1. 分析", "用户需求，", "确定功能", "模块",
            "\n2. 设计", "系统架构", "和数据模型",
            "\n3. 使用", "代码沙箱", "生成代码",
            "\n4. 部署", "并测试", "应用"
        ]
        for part in thinking_parts:
            events.append(next_event(
                "message.assistant.delta",
                delta={"type": "thinking", "content": part}
            ))
        
        # 4. progress - 开始
        events.append(next_event(
            "message.assistant.delta",
            delta={"type": "progress", "content": json.dumps({
                "title": "搭建待办事项管理系统",
                "status": "running",
                "current": 0,
                "total": 5,
                "subtasks": [
                    {"title": "需求分析", "status": "running", "desc": ""},
                    {"title": "架构设计", "status": "pending", "desc": ""},
                    {"title": "代码生成", "status": "pending", "desc": ""},
                    {"title": "部署应用", "status": "pending", "desc": ""},
                    {"title": "功能测试", "status": "pending", "desc": ""}
                ]
            }, ensure_ascii=False)}
        ))
        
        # 5. progress - 需求分析完成
        events.append(next_event(
            "message.assistant.delta",
            delta={"type": "progress", "content": json.dumps({
                "title": "搭建待办事项管理系统",
                "status": "running",
                "current": 1,
                "total": 5,
                "subtasks": [
                    {"title": "需求分析", "status": "success", "desc": "已确定4个核心功能"},
                    {"title": "架构设计", "status": "running", "desc": ""},
                    {"title": "代码生成", "status": "pending", "desc": ""},
                    {"title": "部署应用", "status": "pending", "desc": ""},
                    {"title": "功能测试", "status": "pending", "desc": ""}
                ]
            }, ensure_ascii=False)}
        ))
        
        # 6. mind - 架构图
        mind_content = {
            "mermaid_content": """graph TD
    A[待办事项系统] --> B[前端界面]
    A --> C[后端逻辑]
    A --> D[数据存储]
    B --> B1[任务列表]
    B --> B2[添加任务]
    B --> B3[筛选排序]
    C --> C1[CRUD操作]
    C --> C2[状态管理]
    D --> D1[SQLite数据库]""",
            "chart_type": "flowchart"
        }
        events.append(next_event(
            "message.assistant.delta",
            delta={"type": "mind", "content": json.dumps(mind_content, ensure_ascii=False)}
        ))
        
        # 7. progress - 架构设计完成
        events.append(next_event(
            "message.assistant.delta",
            delta={"type": "progress", "content": json.dumps({
                "title": "搭建待办事项管理系统",
                "status": "running",
                "current": 2,
                "total": 5,
                "subtasks": [
                    {"title": "需求分析", "status": "success", "desc": "已确定4个核心功能"},
                    {"title": "架构设计", "status": "success", "desc": "Streamlit + SQLite"},
                    {"title": "代码生成", "status": "running", "desc": ""},
                    {"title": "部署应用", "status": "pending", "desc": ""},
                    {"title": "功能测试", "status": "pending", "desc": ""}
                ]
            }, ensure_ascii=False)}
        ))
        
        # 8. response - 开始部分
        response_parts_1 = [
            "好的", "，我", "来帮您", "搭建一个", "待办事项", "管理系统。",
            "\n\n", "## 📋", " 系统", "功能", "\n\n",
            "- ✅", " 添加/", "编辑/", "删除", "任务",
            "\n- 🔄", " 状态", "切换", "（待办/", "进行中/", "已完成）",
            "\n- 🎯", " 优先级", "设置", "（高/中/低）",
            "\n- 📅", " 截止日期", "管理",
            "\n\n", "## 🛠️", " 技术", "栈", "\n\n",
            "- **前端**", "：Streamlit",
            "\n- **后端**", "：Python",
            "\n- **数据库**", "：SQLite",
            "\n\n", "正在", "为您", "生成", "代码..."
        ]
        for part in response_parts_1:
            events.append(next_event(
                "message.assistant.delta",
                delta={"type": "response", "content": part}
            ))
        
        # 9. progress - 代码生成完成
        events.append(next_event(
            "message.assistant.delta",
            delta={"type": "progress", "content": json.dumps({
                "title": "搭建待办事项管理系统",
                "status": "running",
                "current": 3,
                "total": 5,
                "subtasks": [
                    {"title": "需求分析", "status": "success", "desc": "已确定4个核心功能"},
                    {"title": "架构设计", "status": "success", "desc": "Streamlit + SQLite"},
                    {"title": "代码生成", "status": "success", "desc": "生成3个文件"},
                    {"title": "部署应用", "status": "running", "desc": ""},
                    {"title": "功能测试", "status": "pending", "desc": ""}
                ]
            }, ensure_ascii=False)}
        ))
        
        # 10. files
        files_content = [
            {"name": "app.py", "type": "python", "url": "https://cdn.example.com/sandbox/todo_app/app.py", "size": 8500},
            {"name": "database.py", "type": "python", "url": "https://cdn.example.com/sandbox/todo_app/database.py", "size": 3200},
            {"name": "requirements.txt", "type": "text", "url": "https://cdn.example.com/sandbox/todo_app/requirements.txt", "size": 120}
        ]
        events.append(next_event(
            "message.assistant.delta",
            delta={"type": "files", "content": json.dumps(files_content, ensure_ascii=False)}
        ))
        
        # 11. application - pending
        events.append(next_event(
            "message.assistant.delta",
            delta={"type": "application", "content": json.dumps({
                "application_id": "app_todo_system_001",
                "status": "pending",
                "name": "待办事项管理系统"
            }, ensure_ascii=False)}
        ))
        
        # 12. application - building
        for progress in [20, 50, 80]:
            events.append(next_event(
                "message.assistant.delta",
                delta={"type": "application", "content": json.dumps({
                    "application_id": "app_todo_system_001",
                    "status": "building",
                    "name": "待办事项管理系统",
                    "build_progress": progress
                }, ensure_ascii=False)}
            ))
        
        # 13. application - success
        events.append(next_event(
            "message.assistant.delta",
            delta={"type": "application", "content": json.dumps({
                "application_id": "app_todo_system_001",
                "status": "success",
                "name": "待办事项管理系统",
                "build_progress": 100,
                "url": "https://app.example.com/todo_system_001"
            }, ensure_ascii=False)}
        ))
        
        # 14. progress - 部署完成
        events.append(next_event(
            "message.assistant.delta",
            delta={"type": "progress", "content": json.dumps({
                "title": "搭建待办事项管理系统",
                "status": "running",
                "current": 4,
                "total": 5,
                "subtasks": [
                    {"title": "需求分析", "status": "success", "desc": "已确定4个核心功能"},
                    {"title": "架构设计", "status": "success", "desc": "Streamlit + SQLite"},
                    {"title": "代码生成", "status": "success", "desc": "生成3个文件"},
                    {"title": "部署应用", "status": "success", "desc": "应用已上线"},
                    {"title": "功能测试", "status": "running", "desc": ""}
                ]
            }, ensure_ascii=False)}
        ))
        
        # 15. progress - 全部完成
        events.append(next_event(
            "message.assistant.delta",
            delta={"type": "progress", "content": json.dumps({
                "title": "搭建待办事项管理系统",
                "status": "completed",
                "current": 5,
                "total": 5,
                "subtasks": [
                    {"title": "需求分析", "status": "success", "desc": "已确定4个核心功能"},
                    {"title": "架构设计", "status": "success", "desc": "Streamlit + SQLite"},
                    {"title": "代码生成", "status": "success", "desc": "生成3个文件"},
                    {"title": "部署应用", "status": "success", "desc": "应用已上线"},
                    {"title": "功能测试", "status": "success", "desc": "全部通过"}
                ]
            }, ensure_ascii=False)}
        ))
        
        # 16. response - 完成部分
        response_parts_2 = [
            "\n\n", "## ✅", " 搭建", "完成", "\n\n",
            "您的", "待办事项", "管理系统", "已经", "搭建", "完成", "并部署", "上线！",
            "\n\n", "🔗 **访问", "地址**", "：", "https://app", ".example.com/", "todo_system_001",
            "\n\n", "### 使用", "说明", "\n\n",
            "1. 点击", "\"添加任务\"", "按钮", "创建", "新任务",
            "\n2. 点击", "任务", "状态", "切换", "完成", "状态",
            "\n3. 使用", "侧边栏", "筛选", "不同", "状态", "的任务",
            "\n\n", "源代码", "已打包", "，您可以", "下载", "后进行", "二次", "开发。"
        ]
        for part in response_parts_2:
            events.append(next_event(
                "message.assistant.delta",
                delta={"type": "response", "content": part}
            ))
        
        # 17. recommended
        recommended_content = {"questions": ["添加用户登录功能", "增加任务分类标签", "添加提醒通知功能", "导出任务列表为Excel"]}
        events.append(next_event(
            "message.assistant.delta",
            delta={"type": "recommended", "content": json.dumps(recommended_content, ensure_ascii=False)}
        ))
        
        # 18. message.assistant.done
        final_content = """好的，我来帮您搭建一个待办事项管理系统。

## 📋 系统功能

- ✅ 添加/编辑/删除任务
- 🔄 状态切换（待办/进行中/已完成）
- 🎯 优先级设置（高/中/低）
- 📅 截止日期管理

## 🛠️ 技术栈

- **前端**：Streamlit
- **后端**：Python
- **数据库**：SQLite

## ✅ 搭建完成

您的待办事项管理系统已经搭建完成并部署上线！

🔗 **访问地址**：https://app.example.com/todo_system_001

### 使用说明

1. 点击"添加任务"按钮创建新任务
2. 点击任务状态切换完成状态
3. 使用侧边栏筛选不同状态的任务

源代码已打包，您可以下载后进行二次开发。"""
        events.append(next_event(
            "message.assistant.done",
            data={"content": final_content}
        ))
        
        return events


# ==================== 便捷函数 ====================

_default_service: Optional[ChatService] = None


def get_chat_service(
    session_service: Optional[SessionService] = None,
    default_model: str = "claude-sonnet-4-5-20250929",
    enable_mock: Optional[bool] = None,
    mock_scenario: Optional[str] = None
) -> ChatService:
    """
    获取默认聊天服务单例
    
    Mock 模式配置：
    - 🎭 默认启用 Mock 模式（enable_mock=True）
    - 可通过函数参数覆盖（enable_mock=False 禁用）
    - 默认场景：analytics
    """
    global _default_service
    if _default_service is None:
        # 🎭 Mock 模式：默认启用，返回预定义数据（不调用 LLM）
        # 如需使用真实 LLM，传入 enable_mock=False
        final_mock = enable_mock if enable_mock is not None else True
        final_scenario = mock_scenario if mock_scenario is not None else "analytics"
        
        _default_service = ChatService(
            session_service=session_service,
            default_model=default_model,
            enable_mock=final_mock,
            mock_scenario=final_scenario
        )
    return _default_service


def reset_chat_service() -> None:
    """
    重置聊天服务单例（仅用于测试）
    """
    global _default_service
    _default_service = None
