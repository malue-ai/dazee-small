"""
SimpleAgent - V3.6 核心Agent
完整集成版本：LLM Service + Capability Router + Memory + Plan/Todo Tool

核心改进（V3.6版本）：
1. ✅ Plan/Todo 作为工具能力 - 存储到 Short Memory（WorkingMemory）
2. ✅ Memory Protocol - 每步骤开始读取 plan，结束写回更新
3. ✅ 简化架构 - 移除 PlanningManager，统一使用 plan_todo_tool
4. ✅ 实时进度展示 - 用户友好的进度显示
5. ✅ 完整的 React+Validation+Reflection 循环

架构文档：
- docs/v3/00-ARCHITECTURE-OVERVIEW.md
- /prompts/MEMORY_PROTOCOL.md
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# LLM Service
from core.llm_service import (
    create_claude_service,
    Message,
    ToolType,
    LLMResponse
)

# 能力路由
from core.capability_registry import (
    CapabilityRegistry,
    create_capability_registry
)
from core.capability_router import (
    CapabilityRouter,
    create_capability_router,
    extract_keywords
)

# 记忆管理
from core.memory import (
    MemoryManager,
    create_memory_manager
)

# Skills管理
from core.skills_manager import (
    SkillsManager,
    create_skills_manager
)

# 工具执行
from tools.executor import (
    ToolExecutor,
    create_tool_executor
)

# 系统提示词
from prompts.universal_agent_prompt import get_universal_agent_prompt


class SimpleAgent:
    """
    V3.6 Simple Agent - Plan/Todo 作为工具能力版本
    
    核心组件：
    - LLM Service: 统一LLM封装（双LLM架构：Haiku + Sonnet）
    - CapabilityRouter: 智能能力路由
    - MemoryManager: 记忆管理（包含 WorkingMemory/Short Memory）
    - PlanTodoTool: Plan/Todo 工具（存储到 Short Memory）
    - SkillsManager: Skills管理
    - ToolExecutor: 工具执行
    
    Memory Protocol（参考 Claude Platform Memory Tool）：
    - ALWAYS READ: 每个步骤开始前，LLM 调用 plan_todo.get_plan() 读取状态
    - ALWAYS WRITE: 每个步骤完成后，LLM 调用 plan_todo.update_step() 写回更新
    - 避免依赖 thinking 中的"记忆"，始终从 Short Memory 读取真实状态
    
    工作流程（Memory-First + RVR）：
    1. Read (读取) - 调用 plan_todo.get_plan() 获取当前状态
    2. Reason (推理) - 通过 Extended Thinking 理解当前步骤
    3. Act (行动) - 执行当前步骤
    4. Observe (观察) - 获取执行结果
    5. Validate (验证) - 检查结果质量
    6. Write (写回) - 调用 plan_todo.update_step() 更新状态
    7. Repeat - 继续下一步骤直到完成
    """
    
    def __init__(
        self,
        api_key: str = None,
        model: str = "claude-sonnet-4-5-20250929",
        system_prompt: str = None,
        workspace_dir: str = None,
        max_turns: int = 20,
        event_manager=None  # EventManager 实例（必需，用于 SSE 流式输出）
    ):
        """
        初始化Agent
        
        Args:
            api_key: Anthropic API密钥
            model: 模型名称
            system_prompt: 系统提示词（可选，默认使用通用框架）
            workspace_dir: 工作目录（用于 plan.json/todo.md 持久化）
            max_turns: 最大轮次
            event_manager: EventManager 实例（必需，用于 SSE 流式输出）
        
        多轮对话使用方式：
            agent = create_simple_agent()
            
            # 开始会话
            result1 = await agent.chat("帮我生成一个PPT")
            
            # 继续对话（保持上下文）
            result2 = await agent.chat("把标题改成'AI技术分享'")
        """
        # 验证必需参数
        if event_manager is None:
            raise ValueError("event_manager 是必需参数，用于实现 SSE 流式输出")
        
        self.model = model
        self.workspace_dir = workspace_dir
        self.max_turns = max_turns
        
        # 🆕 事件管理器
        self.event_manager = event_manager
        
        # 🆕 HITL 事件队列（用于工具发出的 SSE 事件）
        import asyncio
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._current_session_id: str = ""  # 当前会话ID
        
        # ===== 核心组件初始化 =====
        
        # 1. 能力注册表
        self.capability_registry = create_capability_registry()
        logger.debug(f"CapabilityRegistry loaded: {len(self.capability_registry.capabilities)} capabilities")
        
        # 2. 能力路由器
        self.capability_router = create_capability_router(self.capability_registry)
        logger.debug("CapabilityRouter initialized")
        
        # 3. Skills管理器
        self.skills_manager = create_skills_manager()
        logger.debug(f"SkillsManager loaded: {len(self.skills_manager.skills)} skills")
        
        # 4. 工具执行器（传入架构级依赖）
        from core.memory import WorkingMemory
        self.working_memory = WorkingMemory()
        
        tool_context = {
            "memory": self.working_memory,
            "event_manager": self.event_manager,
            "workspace_dir": workspace_dir
        }
        self.tool_executor = create_tool_executor(self.capability_registry, tool_context=tool_context)
        logger.debug("ToolExecutor initialized")
        
        # 5. Plan/Todo 状态管理（仅保留任务状态，不管理对话历史）
        self.plan_state = {
            "plan": None,
            "todo": None,
            "tool_calls": []
        }
        logger.debug("Plan state initialized")
        
        # 6. Plan/Todo 工具（会话级短期记忆）
        # 注意：plan_todo_tool 接受 memory 参数（WorkingMemory），但我们当前使用简单的 plan_state dict
        # 这里传入 None，工具会使用内部状态管理
        from tools.plan_todo_tool import create_plan_todo_tool
        self.plan_todo_tool = create_plan_todo_tool(
            memory=None,  # 传入 None，工具使用内部状态
            registry=self.capability_registry  # 传入 Registry 用于动态 Schema
        )
        logger.debug("PlanTodoTool initialized (using internal state + dynamic schema)")
        
        # 🆕 6.5. E2B Template Manager - 模板管理器
        try:
            from tools.e2b_template_manager import create_e2b_template_manager
            self.e2b_template_manager = create_e2b_template_manager()
            logger.debug("E2B Template Manager initialized")
        except Exception as e:
            self.e2b_template_manager = None
            logger.warning(f"E2B Template Manager initialization skipped: {e}")
        
        # 🆕 7. InvocationSelector - 调用方式选择器
        from core.invocation_selector import create_invocation_selector
        total_tools = len(self.capability_registry.capabilities)
        self.invocation_selector = create_invocation_selector(
            enable_tool_search=(total_tools > 30),  # 工具数量>30时启用
            enable_code_execution=True,
            enable_programmatic=True,
            enable_streaming=True
        )
        logger.debug(f"InvocationSelector initialized (total tools: {total_tools})")
        
        # 8. LLM Service - 双 LLM 架构
        # 7.1 Intent Recognition LLM (Haiku 4.5 - 快速、便宜)
        self.intent_llm = create_claude_service(
            model="claude-haiku-4-5-20251001",  # Haiku 4.5（最新版本）
            enable_thinking=False,  # 🆕 不需要 Extended Thinking
            enable_caching=False,
            tools=[]  # 🆕 不需要工具
        )
        
        # 7.2 Execution LLM (Sonnet 4.5 - 强大、准确)
        self.llm = create_claude_service(
            model=model,
            enable_thinking=True,  # 根据任务复杂度动态调整
            enable_caching=False,
            tools=[
                ToolType.BASH,
                ToolType.TEXT_EDITOR,
                ToolType.WEB_SEARCH
            ]
        )
        
        # 启用 Programmatic Tool Calling 检测
        self.llm.enable_programmatic_tool_calling()
        
        # 注册自定义工具
        self._register_tools_to_llm()
        
        # 工具列表
        self._tools = [
            ToolType.BASH,
            ToolType.TEXT_EDITOR,
            ToolType.WEB_SEARCH
        ]
        self._custom_tool_names = [schema['name'] for schema in self.capability_registry.get_tool_schemas()]
        
        # 调用方式统计
        self.invocation_stats = {
            "direct": 0,
            "code_execution": 0,
            "programmatic": 0,
            "streaming": 0
        }
        
        logger.debug("LLM Service initialized with custom tools")
        
        # 8. 系统提示词
        self.system_prompt = system_prompt or self._build_system_prompt()
        
        # ===== 日志初始化 =====
        self.session_log = {
            "session_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "model": model,
            "architecture_version": "V3.5",
            "features": {
                "plan_todo_integration": True,  # 🆕
                "capability_router": True,
                "memory_manager": True,
                "planning_manager": True,
                "skills_manager": True,
                "react_vr": True
            },
            "start_time": datetime.now().isoformat(),
            "interactions": [],
            "plan_changes": [],  # 🆕 计划变更记录
            "routing_decisions": [],
            "quality_metrics": {
                "validations": [],
                "reflections": [],
                "iterations": []
            }
        }
        
    def _register_tools_to_llm(self):
        """
        🆕 从Registry注册工具到LLM Service（使用动态 Schema）
        """
        tool_schemas = self.capability_registry.get_tool_schemas()
        for schema in tool_schemas:
            # 🆕 plan_todo 使用动态生成的 Schema
            if schema['name'] == 'plan_todo':
                schema['input_schema'] = self.plan_todo_tool.get_input_schema()
            
            self.llm.add_custom_tool(
                name=schema['name'],
                description=schema['description'],
                input_schema=schema['input_schema']
            )
    
    def _build_system_prompt(self) -> str:
        """
        🆕 构建系统提示词（动态注入能力分类 + Skills元数据）
        """
        base_prompt = get_universal_agent_prompt()
        
        # 🆕 动态生成能力分类说明（从 Registry）
        capability_categories = self.capability_registry.get_categories_for_prompt()
        
        # Skills 元数据
        skills_metadata = self.skills_manager.generate_skills_metadata_for_prompt()
        
        # 组合：基础提示词 + 能力分类 + Skills
        return f"{base_prompt}\n\n{capability_categories}\n\n{skills_metadata}"
    
    def _get_available_apis(self) -> List[str]:
        """
        🆕 自动发现可用的API（完全从配置和运行时状态推断）
        
        架构原则（V3.7）：
        - 零硬编码：不在代码中维护任何工具/API列表
        - 配置驱动：所有信息来自 capabilities.yaml
        - 运行时发现：工具加载成功 = API可用
        
        发现逻辑：
        1. 遍历 ToolExecutor 已成功加载的工具
        2. 从 capabilities.yaml 读取工具的 api_name
        3. 工具加载成功 → 其 api_name 可用
        
        Returns:
            可用API名称列表
        """
        available_apis = set()
        
        # 从ToolExecutor获取已加载的工具
        loaded_tools = self.tool_executor._tool_instances
        
        for tool_name, tool_instance in loaded_tools.items():
            if tool_instance is None:
                continue  # 未成功加载的工具跳过
            
            # 从Registry获取工具的约束配置
            capability = self.capability_registry.get(tool_name)
            if capability and capability.constraints:
                api_name = capability.constraints.get('api_name')
                if api_name:
                    available_apis.add(api_name)
        
        logger.debug(f"🔍 自动发现可用API: {list(available_apis)}")
        return list(available_apis)
    
    def _infer_capabilities_from_task_type(self, task_type: str) -> List[str]:
        """
        🆕 根据任务类型推断所需的基础能力（从配置文件动态加载）
        
        通用能力推断，适用于所有任务（简单/复杂）：
        - 简单任务：直接使用推断结果
        - 复杂任务首轮：作为初始能力集，后续轮次从 Plan 提取更精确的
        
        架构改进：
        - 映射关系从 capabilities.yaml 的 task_type_mappings 读取
        - 符合"单一数据源"原则，便于调整和维护
        - 避免硬编码，配置即时生效
        - 复杂任务首轮也能筛选工具，不再"传入所有工具"
        
        Args:
            task_type: 任务类型（来自 Intent Analysis）
            
        Returns:
            推断的能力列表
            
        Example:
            task_type="information_query" → ["web_search", "file_operations", "task_planning"]
            task_type="content_generation" → ["document_creation", "ppt_generation", "file_operations", "code_execution", "task_planning"]
        """
        # 🆕 从 Registry 动态获取映射（配置文件定义）
        capabilities = self.capability_registry.get_capabilities_for_task_type(task_type)
        
        logger.debug(f"Inferred capabilities for '{task_type}': {capabilities}")
        return capabilities
    
    def _format_progress_display(self, plan: Dict) -> str:
        """格式化进度显示（Dict格式）"""
        steps = plan.get("steps", [])
        total = len(steps)
        completed = sum(1 for s in steps if s.get("status") == "completed")
        progress = completed / total if total > 0 else 0
        
        lines = [
            f"📊 Progress: {completed}/{total} ({progress*100:.0f}%)",
            f"🎯 Goal: {plan.get('goal', '')}",
            ""
        ]
        
        for step in steps:
            status = step.get("status", "pending")
            icon = {"completed": "✅", "in_progress": "🔄", "failed": "❌"}.get(status, "○")
            lines.append(f"  {icon} Step {step.get('step_id', 0)}: {step.get('action', '')}")
        
        return "\n".join(lines)
    
    
    async def chat(
        self, 
        user_input: str, 
        history_messages: List[Dict[str, str]] = None, 
        session_id: str = None,
        enable_stream: bool = True
    ):
        """
        Agent 统一执行入口（支持流式和非流式）
        
        架构原则：
        - LLM Service 层：封装 Claude 原生流式能力
        - Agent 层：集成 RVR 机制，产生统一格式事件
        - Service 层：负责数据库操作和历史消息加载
        
        Args:
            user_input: 用户输入
            history_messages: 历史消息列表（Service 层从数据库加载）
                格式: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]
            session_id: 通信会话ID（由 SessionService 传入，用于事件路由）
            enable_stream: 是否启用流式输出（默认 True）
                - True: 使用 llm.create_message_stream()，实时输出事件
                - False: 使用 llm.create_message()，一次性返回完整结果
            
        Yields:
            事件字典，格式：
            {
                "type": str,        # 事件类型
                "data": Dict,       # 事件数据
                "timestamp": str    # ISO格式时间戳
            }
            
        事件类型：
        - session_start: 会话开始
        - status: 状态消息
        - intent_analysis: 意图识别结果
        - tool_selection: 工具筛选结果
        - thinking: LLM思考过程（增量，仅 enable_stream=True）
        - content_start/delta/stop: LLM回复内容（仅 enable_stream=True）
        - tool_call_start: 工具调用开始
        - tool_call_complete: 工具执行完成
        - plan_update: Plan进度更新
        - complete: 任务完成
        - error: 错误信息
        
        Example:
            ```python
            # 流式模式（SSE）
            agent = create_simple_agent()
            async for event in agent.chat("你好", session_id=sess_id, enable_stream=True):
                if event["type"] == "content_delta":
                    print(event['data']['delta']['text'], end="", flush=True)
            
            # 非流式模式（普通 HTTP）
            async for event in agent.chat("你好", session_id=sess_id, enable_stream=False):
                if event["type"] == "complete":
                    print(event['data']['final_result'])
            ```
        """
        # ===== 0. 初始化运行时上下文 =====
        # TODO: 创建 RuntimeContext 管理消息、system_prompt、tools
        history_messages = history_messages or []
        logger.debug(f"接收到 {len(history_messages)} 条历史消息")
        
        # session_id 由 Service 层传入（用于事件路由）
        if not session_id:
            # 降级：如果没有提供 session_id，生成一个临时的
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            logger.warning(f"未提供 session_id，生成临时 ID: {session_id}")
        
        # ===== 1. 意图识别（Haiku - 快速分类）=====
        yield await self._emit_agent_event(session_id, "status", {"message": "🎯 分析任务意图..."})
        
        from prompts.intent_recognition_prompt import get_intent_recognition_prompt
        
        intent_response: LLMResponse = self.intent_llm.create_message(
            messages=[Message(role="user", content=user_input)],
            system=get_intent_recognition_prompt()
        )
        
        intent_analysis = self._parse_intent_analysis(intent_response.content)
        yield await self._emit_agent_event(session_id, "intent_analysis", intent_analysis)
        
        # 选择系统提示词
        execution_config = self._get_execution_config(
            intent_analysis['prompt_level'], 
            intent_analysis['complexity']
        )
        self.system_prompt = execution_config['system_prompt']
        
        # ===== 2. 动态工具筛选 + 调用方式选择 =====
        yield await self._emit_agent_event(session_id, "status", {"message": "🔧 准备工具..."})
        
        plan = self.plan_state.get("plan")
        required_capabilities = []
        
        # 从 Plan 或 task_type 推断能力需求
        if plan:
            required_capabilities = plan.get('required_capabilities', [])
            if not required_capabilities:
                required_capabilities = list(set([
                    step.get('capability', '') 
                    for step in plan.get('steps', []) 
                    if step.get('capability')
                ]))
        
        if not required_capabilities:
            required_capabilities = self._infer_capabilities_from_task_type(
                intent_analysis['task_type']
            )
        
        # Router 筛选工具
        from core.capability_router import select_tools_for_capabilities
        
        # 🆕 自动发现可用API（从已加载的工具推断）
        available_apis = self._get_available_apis()
        
        selected_tools = select_tools_for_capabilities(
            self.capability_router,
            required_capabilities=required_capabilities,
            context={
                "plan": plan, 
                "task_type": intent_analysis['task_type'],
                "available_apis": available_apis  # 🆕 自动发现，不硬编码
            }
        )
        
        # 🔍 调试：打印Router结果
        logger.debug(f"🔍 Router返回工具数量: {len(selected_tools)}")
        for t in selected_tools:
            logger.debug(f"  - {t.name} (capabilities={t.capabilities})")
        
        # InvocationSelector 选择调用方式
        invocation_strategy = self.invocation_selector.select_strategy(
            task_type=intent_analysis['task_type'],
            selected_tools=[t.name for t in selected_tools],
            estimated_input_size=len(str(plan)) if plan else 0
        )
        
        yield await self._emit_agent_event(session_id, "tool_selection", {
            "required_capabilities": required_capabilities,
            "selected_tools": [t.name for t in selected_tools],
            "invocation_strategy": invocation_strategy.type.value,
            "reason": invocation_strategy.reason
        })
        
        # ===== 3. RVR 循环（流式版本）=====
        # 🆕 构建消息列表：历史 + 当前用户输入
        messages = []
        
        # 添加历史消息
        for hist_msg in history_messages:
            messages.append(Message(
                role=hist_msg["role"],
                content=hist_msg["content"]
            ))
        
        # 添加当前用户输入
        messages.append(Message(role="user", content=user_input))
        
        logger.debug(f"构建消息列表: {len(messages)} 条（{len(history_messages)} 条历史 + 1 条新消息）")
        
        final_result = None
        
        for turn in range(self.max_turns):
            yield await self._emit_agent_event(session_id, "turn_progress", {
                "turn": turn + 1,
                "max_turns": self.max_turns
            })
            
            # 🆕 准备工具列表（与 run() 方法保持一致）
            # 第一步：收集工具名
            tool_names = [t.name for t in selected_tools]
            
            # 第二步：确保包含原生工具（bash, text_editor, web_search）
            for native_tool in self._tools:
                # ToolType 枚举需要转换为字符串
                native_tool_name = native_tool.value if isinstance(native_tool, ToolType) else native_tool
                if native_tool_name not in tool_names:
                    tool_names.append(native_tool_name)
            
            # 第三步：构建完整工具 schema（用于传给 LLM）
            tools_for_llm = []
            for tool_name in tool_names:
                # 检查是否是 Claude 原生工具
                if tool_name in ["bash", "text_editor", "web_search", "computer", "memory"]:
                    # 原生工具：直接使用字符串，llm_service 会处理
                    tools_for_llm.append(tool_name)
                else:
                    # 自定义工具：需要从 capability_registry 获取完整 schema
                    capability = self.capability_registry.get(tool_name)
                    if capability:
                        # ⚠️ 只有 TOOL 类型的能力才能作为 Claude API 工具
                        if capability.type.value != "TOOL":
                            continue
                        
                        # 检查是否有有效的 input_schema
                        if not capability.input_schema:
                            continue
                        
                        # Capability 对象转换为字典格式
                        capability_dict = {
                            "name": capability.name,
                            "type": capability.type.value,
                            "provider": capability.provider,
                            "metadata": capability.metadata,
                            "input_schema": capability.input_schema
                        }
                        # 使用 llm.convert_to_claude_tool() 转换为 Claude API 格式
                        tool_schema = self.llm.convert_to_claude_tool(capability_dict)
                        tools_for_llm.append(tool_schema)
            
            # 准备工具配置
            tools_config = self.invocation_selector.get_tools_config(
                all_tools=[{"name": t if isinstance(t, str) else t.get("name", "")} for t in tools_for_llm],
                strategy=invocation_strategy
            )
            llm_kwargs = tools_config.get('extra', {})
            
            # 🔑 关键：根据 enable_stream 选择 LLM 调用方式
            if enable_stream:
                # 流式模式：使用 create_message_stream()
                stream_generator = self.llm.create_message_stream(
                    messages=messages,
                    system=self.system_prompt,
                    tools=tools_for_llm,
                    **llm_kwargs
                )
                
                # 🔑 简洁清晰：直接遍历流
                accumulated_thinking = ""
                accumulated_content = ""
                final_response = None
                
                for llm_response in stream_generator:
                    # 🆕 实时输出 thinking（增量）
                    if llm_response.thinking and llm_response.is_stream:
                        if not hasattr(self, '_thinking_started'):
                            # 发送 content_start
                            thinking_start_event = await self.event_manager.content.emit_content_start(
                                session_id=session_id,
                                index=0,
                                block_type="thinking"
                            )
                            yield thinking_start_event
                            self._thinking_started = True
                        
                        # 发送 content_delta
                        thinking_delta_event = await self.event_manager.content.emit_content_delta(
                            session_id=session_id,
                            index=0,
                            delta_type="thinking",
                            delta_data={"text": llm_response.thinking}
                        )
                        yield thinking_delta_event
                        accumulated_thinking += llm_response.thinking
                    
                    # 🆕 实时输出 content（增量）
                    if llm_response.content and llm_response.is_stream:
                        if not hasattr(self, '_content_started'):
                            # 发送 content_start
                            content_start_event = await self.event_manager.content.emit_content_start(
                                session_id=session_id,
                                index=1,
                                block_type="text"
                            )
                            yield content_start_event
                            self._content_started = True
                        
                        # 发送 content_delta
                        content_delta_event = await self.event_manager.content.emit_content_delta(
                            session_id=session_id,
                            index=1,
                            delta_type="text",
                            delta_data={"text": llm_response.content}
                        )
                        yield content_delta_event
                        accumulated_content += llm_response.content
                    
                    # 保存最终响应（包含 tool_calls 和 stop_reason）
                    if not llm_response.is_stream:
                        final_response = llm_response
                
                # 使用最终响应（如果没有收到，构建一个）
                response = final_response or LLMResponse(
                    content=accumulated_content,
                    thinking=accumulated_thinking,
                    stop_reason="end_turn"
                )
                
                # 🆕 发送 content_stop 事件（每个 turn 结束后）
                if hasattr(self, '_thinking_started'):
                    thinking_stop_event = await self.event_manager.content.emit_content_stop(
                        session_id=session_id,
                        index=0
                    )
                    yield thinking_stop_event
                    delattr(self, '_thinking_started')
                    
                if hasattr(self, '_content_started'):
                    content_stop_event = await self.event_manager.content.emit_content_stop(
                        session_id=session_id,
                        index=1
                    )
                    yield content_stop_event
                    delattr(self, '_content_started')
            else:
                # 非流式模式：使用 create_message()，一次性返回
                response = self.llm.create_message(
                    messages=messages,
                    system=self.system_prompt,
                    tools=tools_for_llm,
                    **llm_kwargs
                )
                
                # 非流式模式：发送完整的 content 事件（不分 start/delta/stop）
                if response.thinking:
                    yield await self._emit_agent_event(session_id, "thinking", {
                        "text": response.thinking
                    })
                
                if response.content:
                    yield await self._emit_agent_event(session_id, "content", {
                        "text": response.content
                    })
            
            # 处理 stop_reason
            stop_reason = response.stop_reason
            
            if stop_reason == "end_turn":
                final_result = response.content
                yield await self._emit_agent_event(session_id, "status", {"message": "✅ 任务完成"})
                break
            
            elif stop_reason == "tool_use" and response.tool_calls:
                # 🆕 工具调用开始通知
                for tool_call in response.tool_calls:
                    yield await self._emit_agent_event(session_id, "tool_call_start", {
                        "tool_name": tool_call.get("name", ""),
                        "tool_id": tool_call.get("id", ""),
                        "input": tool_call.get("input", {})
                    })
                    
                    # 记录调用统计
                    invocation_method = tool_call.get('invocation_method', 'direct')
                    self.invocation_stats[invocation_method] += 1
                
                # 执行工具
                tool_results = await self._execute_tools(response.tool_calls)
                
                # 通知工具完成
                for tool_call, tool_result in zip(response.tool_calls, tool_results):
                    result_content = json.loads(tool_result.get("content", "{}"))
                    yield await self._emit_agent_event(session_id, "tool_call_complete", {
                        "tool_name": tool_call.get("name", ""),
                        "success": result_content.get("success", True),
                        "result": result_content  
                    })
                
                # 🆕 更新 Plan 进度
                # 注：Plan进度由 plan_todo 工具管理，Agent 不直接更新
                
                # 🆕 通知 Plan 进度更新
                updated_plan = self.plan_state.get("plan")
                if updated_plan:
                    yield await self._emit_agent_event(session_id, "plan_update", {
                        "plan": updated_plan,
                        "progress": self._format_progress_display(updated_plan)
                    })
                
                # 更新 messages
                messages.append(Message(role="assistant", content=response.raw_content))
                messages.append(Message(role="user", content=tool_results))
            
            else:
                yield await self._emit_agent_event(session_id, "error", {
                    "message": f"未知的 stop_reason: {stop_reason}",
                    "turn": turn + 1
                })
                break
        
        # ===== 4. 返回最终结果 =====
        yield await self._emit_agent_event(session_id, "complete", {
            "status": "success" if final_result else "incomplete",
            "final_result": final_result,
            "turns": turn + 1
        })
    
    async def _emit_agent_event(self, session_id: str, event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        发送 Agent 事件（通过 EventManager）
        
        Args:
            session_id: 通信会话ID（用于事件路由）
            event_type: 事件类型
            data: 事件数据
            
        Returns:
            事件字典
        """
        return await self.event_manager.system.emit_custom(
            session_id=session_id,
            event_type=event_type,
            event_data=data
        )
    
    def _display_plan_progress_update(self, plan: Dict, completed: int, total: int, progress: float):
        """
        🆕 显示 Todo 进度更新（用户可见）
        
        注意：用户看到的是 Todo 风格（Markdown），不是 Plan（JSON）
        
        格式（Todo.md 风格）：
        ┌─────────────────────────────────────
        │ 📋 Todo Progress: 2/4 completed
        ├─────────────────────────────────────
        │ - [x] 搜索工具调用技术信息
        │ - [x] 搜索记忆管理信息
        │ - [ ] 搜索规划能力信息
        │ - [ ] 整合信息生成报告
        │
        │ [██████████░░░░░░░░░░] 50%
        └─────────────────────────────────────
        """
        steps = plan.get('steps', [])
        bar_filled = int(progress * 20)
        bar_empty = 20 - bar_filled
        
        print(f"\n  ┌─────────────────────────────────────")
        print(f"  │ 📋 Todo Progress: {completed}/{total} completed")
        print(f"  ├─────────────────────────────────────")
        
        # Todo.md 风格：使用 Markdown checkbox 格式
        for i, step in enumerate(steps):
            status = step.get('status', 'pending')
            
            # Markdown checkbox 风格
            if status == 'completed':
                checkbox = '[x]'
                icon = '✅'
            elif status == 'in_progress':
                checkbox = '[-]'
                icon = '🔄'
            elif status == 'failed':
                checkbox = '[!]'
                icon = '❌'
            else:  # pending
                checkbox = '[ ]'
                icon = '○'
            
            # 提取 action 描述（移除工具调用细节，只保留目的）
            action = step.get('action', f'Step {i+1}')
            # 如果是工具调用格式，提取目的
            if '→' in action:
                # "web_search(...) → 获取信息" → "获取信息"
                action = action.split('→')[-1].strip()
            
            # 截断过长的描述
            if len(action) > 35:
                action = action[:32] + '...'
            
            print(f"  │ - {checkbox} {action}")
        
        print(f"  │")
        print(f"  │ [{'█' * bar_filled}{'░' * bar_empty}] {progress*100:.0f}%")
        print(f"  └─────────────────────────────────────")
    
    def _parse_intent_analysis(self, content: str) -> Dict[str, Any]:
        """
        🆕 解析 Haiku 返回的意图分析结果（JSON 格式）
        
        Args:
            content: Haiku 的响应内容（JSON）
            
        Returns:
            {
                "task_type": str,
                "complexity": "simple"|"medium"|"complex",
                "needs_plan": bool,
                "prompt_level": "simple"|"standard"|"full"  # 根据 complexity 推导
            }
        """
        import json
        import re
        
        result = {
            "task_type": "other",
            "complexity": "medium",
            "needs_plan": True,
            "prompt_level": "standard"
        }
        
        if not content:
            return result
        
        try:
            # 尝试提取 JSON
            json_match = re.search(r'\{[^}]+\}', content, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                result["task_type"] = parsed.get("task_type", "other")
                result["complexity"] = parsed.get("complexity", "medium")
                result["needs_plan"] = parsed.get("needs_plan", True)
                
                # 根据 complexity 推导 prompt_level
                if result["complexity"] == "simple":
                    result["prompt_level"] = "simple"
                elif result["complexity"] == "medium":
                    result["prompt_level"] = "standard"
                else:  # complex
                    result["prompt_level"] = "full"
            
        except Exception as e:
                print(f"⚠️ Failed to parse intent analysis: {e}")
        return result
    
    
    def _get_execution_config(self, prompt_level: str, complexity: str) -> Dict[str, Any]:
        """
        根据意图分析结果返回执行配置
        
        Args:
            prompt_level: simple|standard|full
            complexity: simple|medium|complex
            
        Returns:
            {
                "system_prompt": str,
                "prompt_name": str,
                "tools": List[ToolType],
                "enable_thinking": bool
            }
        """
        from prompts.simple_prompt import get_simple_prompt
        from prompts.standard_prompt import get_standard_prompt
        
        if prompt_level == "simple":
            return {
                "system_prompt": get_simple_prompt(),
                "prompt_name": "simple_prompt",
                "tools": [ToolType.WEB_SEARCH, ToolType.BASH],
                "enable_thinking": False  # 简单任务不需要 Extended Thinking
            }
        elif prompt_level == "standard":
            return {
                "system_prompt": get_standard_prompt(),
                "prompt_name": "standard_prompt",
                "tools": self._tools,  # 使用基础工具集
                "enable_thinking": True
            }
        else:  # full
            # 使用完整的系统提示词（包含 Skills）
            return {
                "system_prompt": self._build_system_prompt(),
                "prompt_name": "full_prompt",
                "tools": self._tools + self._custom_tool_names,  # 所有工具
                "enable_thinking": True
            }
    async def _execute_tools(self, tool_calls: List[Dict]) -> List[Dict]:
        """
        执行工具调用
        
        🆕 HITL 支持：
        - 为 request_human_confirmation 工具注入 emit_event 回调
        - 回调会将事件放入 _event_queue，由 stream() 方法消费
        """
        results = []
        
        for tool_call in tool_calls:
            tool_name = tool_call['name']
            tool_input = tool_call['input']
            tool_id = tool_call['id']
            invocation_method = tool_call.get('invocation_method', 'direct')
            
            logger.debug(f"Executing tool: {tool_name}")
            # 记录工具调用（用于 Plan 进度跟踪）
            self.plan_state.setdefault("tool_calls", []).append({
                "tool": tool_name,
                "input": tool_input,
                "timestamp": datetime.now().isoformat()
            })
            
            try:
                # 执行工具
                if tool_name in ["bash", "str_replace_based_edit_tool", "web_search"]:
                    # Claude 原生工具
                    result = {
                        "success": True,
                        "note": f"Native tool {tool_name} executed by Claude API",
                        "invocation_method": invocation_method
                    }
                elif tool_name == "plan_todo":
                    # 会话级 Plan/Todo 工具（短期记忆）
                    operation = tool_input.get('operation', 'get_plan')
                    data = tool_input.get('data', {})
                    result = self.plan_todo_tool.execute(operation, data)
                    result['invocation_method'] = invocation_method
                    
                    # 如果创建或更新了Plan，显示进度
                    if result.get('display'):
                        logger.debug(f"\n{result['display']}\n")
                elif tool_name == "request_human_confirmation":
                    # 🆕 HITL 工具：注入 emit_event 回调和 session_id
                    result = await self._execute_hitl_tool(tool_input)
                    result['invocation_method'] = invocation_method
                elif tool_name == "e2b_python_sandbox":
                    # 🆕 E2B Python Sandbox：注入 session_id 用于流式输出
                    enriched_input = {
                        **tool_input,
                        "session_id": self._current_session_id  # 注入 session_id
                    }
                    result = await self.tool_executor.execute(tool_name, enriched_input)
                    result['invocation_method'] = invocation_method
                else:
                    # 其他自定义工具
                    # 注意：user_id/conversation_id 应该由 Service 层设置
                    enriched_input = {**tool_input}
                    
                    result = await self.tool_executor.execute(tool_name, enriched_input)
                    result['invocation_method'] = invocation_method
                
                # 更新 tool_calls 记录（用于 Plan 进度跟踪）
                if "tool_calls" in self.plan_state and self.plan_state["tool_calls"]:
                    self.plan_state["tool_calls"][-1]['result'] = result
                
                results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": json.dumps(result, ensure_ascii=False)
                })
                
                status = "✅" if result.get("success") else "❌"
                logger.debug(f"   {status} Result: {str(result)[:100]}...")
            except Exception as e:
                results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": json.dumps({"success": False, "error": str(e)}),
                    "is_error": True
                })
                
                logger.error(f"   ❌ Error: {e}")
        return results
    
    async def _execute_hitl_tool(self, tool_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        🆕 执行 HITL (Human-in-the-Loop) 工具
        
        核心机制：
        1. 创建 emit_event 回调，将事件放入 _event_queue
        2. 调用 RequestHumanConfirmationTool.execute()
        3. 工具会阻塞等待用户响应，但不阻塞事件循环
        
        Args:
            tool_input: 工具输入参数
            
        Returns:
            工具执行结果
        """
        from tools.request_human_confirmation import RequestHumanConfirmationTool
        
        # 创建 emit_event 回调
        async def emit_event(event: Dict[str, Any]):
            """将事件放入队列，由 stream() 方法消费"""
            await self._event_queue.put(event)
            logger.debug(f"HITL 事件已入队: {event.get('type')}")
        
        # 创建工具实例并执行
        hitl_tool = RequestHumanConfirmationTool()
        
        result = await hitl_tool.execute(
            question=tool_input.get("question", ""),
            options=tool_input.get("options"),
            timeout=tool_input.get("timeout", 60),
            confirmation_type=tool_input.get("confirmation_type", "yes_no"),
            metadata=tool_input.get("metadata"),
            emit_event=emit_event,  # 🔥 注入回调
            session_id=self._current_session_id  # 🔥 注入会话ID
        )
        
        return result
    
    def set_session_id(self, session_id: str):
        """
        🆕 设置当前会话ID（由 Service 层调用）
        
        Args:
            session_id: 会话ID
        """
        self._current_session_id = session_id
        logger.debug(f"会话ID已设置: {session_id}")
    
    async def get_hitl_event(self, timeout: float = 0.1) -> Optional[Dict[str, Any]]:
        """
        🆕 获取 HITL 事件（由 stream() 方法调用）
        
        非阻塞方式从队列获取事件，用于在 SSE 流中插入 HITL 请求
        
        Args:
            timeout: 超时时间（秒）
        
        Returns:
            HITL 事件，或 None（无事件）
        """
        import asyncio
        try:
            event = await asyncio.wait_for(
                self._event_queue.get(),
                timeout=timeout
            )
            return event
        except asyncio.TimeoutError:
            return None
    
    # ============================================================
    # 🆕 HITL (Human-in-the-Loop) - 工具调用模式
    # ============================================================
    # 
    # 旧的 HITL API (refine, confirm, clarify 等) 已移除。
    # 现在 HITL 通过工具调用实现：
    #
    # 1. LLM 调用 request_human_confirmation 工具
    # 2. 工具发送 SSE 事件到前端
    # 3. 用户通过 HTTP POST 响应
    # 4. 工具获取响应后继续执行
    #
    # 相关组件：
    # - core/confirmation_manager.py - 确认请求管理器
    # - tools/request_human_confirmation.py - HITL 工具
    # - routers/human_confirmation.py - HTTP 接口
    #
    # 使用方式：
    # - 在 system prompt 中告诉 LLM：危险操作需要调用 request_human_confirmation 工具
    # - LLM 会自动判断何时需要用户确认
    # ============================================================
    
    def _log_interaction(self, turn: int, event_type: str, data: Dict):
        """记录交互"""
        self.session_log["interactions"].append({
            "turn": turn,
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "data": data
        })
    
    # ==================== 辅助方法 ====================
    
    def get_plan(self) -> Optional[Dict]:
        """获取当前计划"""
        return self.plan_state.get("plan")
    
    def get_todo_md(self) -> Optional[str]:
        """获取当前 Todo.md 内容"""
        return self.plan_state.get("todo")
    
    def get_progress(self) -> Dict[str, Any]:
        """获取当前进度"""
        plan = self.plan_state.get("plan")
        if not plan:
            return {"total": 0, "completed": 0, "progress": 0.0}
        
        total = len(plan.get("steps", []))
        completed = sum(1 for s in plan.get("steps", []) if s.get("status") == "completed")
        return {
            "total": total,
            "completed": completed,
            "progress": completed / total if total > 0 else 0.0,
            "current_step": plan.get("current_step", 0)
        }
    
    def get_capability_info(self, name: str) -> Optional[Dict]:
        """获取能力信息"""
        cap = self.capability_registry.get(name)
        if cap:
            return {
                "name": cap.name,
                "type": cap.type.value,
                "description": cap.metadata.get('description', ''),
                "priority": cap.priority
            }
        return None
    
    def list_capabilities(self) -> List[str]:
        """列出所有可用能力"""
        return self.capability_registry.list_all()
    
    def list_skills(self) -> List[str]:
        """列出所有可用Skills"""
        return self.skills_manager.list_skills()
    
    def summary(self) -> str:
        """生成Agent摘要"""
        lines = [
            "SimpleAgent V3.5 Summary",
            "=" * 40,
            f"Model: {self.model}",
            f"Capabilities: {len(self.capability_registry.capabilities)}",
            f"Skills: {len(self.skills_manager.skills)}",
            f"Max Turns: {self.max_turns}",
            f"Plan/Todo Integration: Enabled (Short Memory)",
            "",
            self.capability_registry.summary(),
            "",
            self.tool_executor.summary()
        ]
        
        # 从 Short Memory 获取计划状态
        if self.plan_todo_tool.has_plan():
            lines.append("")
            lines.append("Current Plan (Short Memory):")
            lines.append(self.plan_todo_tool.get_full_display())
        
        return "\n".join(lines)


# ==================== 便捷函数 ====================

def create_simple_agent(
    model: str = "claude-sonnet-4-5-20250929",
    workspace_dir: str = None,
    event_manager=None  # EventManager 实例（必需）
) -> SimpleAgent:
    """
    创建SimpleAgent
    
    Args:
        model: 模型名称
        workspace_dir: 工作目录
        event_manager: EventManager 实例（必需，用于 SSE 流式输出）
        
    Returns:
        配置好的SimpleAgent实例
        
    Raises:
        ValueError: 如果未提供 event_manager
    """
    if event_manager is None:
        raise ValueError("event_manager 是必需参数，请传入 EventManager 实例")
    
    return SimpleAgent(
        model=model,
        workspace_dir=workspace_dir,
        event_manager=event_manager
    )
