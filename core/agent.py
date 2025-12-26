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
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
from pathlib import Path

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
        enable_hitl: bool = True,
        verbose: bool = False,
        log_file: str = None,
        on_progress: Optional[Callable[[str], None]] = None,  # 进度回调
        on_plan_change: Optional[Callable[[Dict, str], None]] = None,  # 计划变更回调（Dict格式）
        # 🆕 上下文压缩配置
        max_full_messages: int = 10,  # 保留完整消息的阈值
        recent_keep: int = 6  # 保留最近 N 条完整消息
    ):
        """
        初始化Agent
        
        Args:
            api_key: Anthropic API密钥
            model: 模型名称
            system_prompt: 系统提示词（可选，默认使用通用框架）
            workspace_dir: 工作目录（用于 plan.json/todo.md 持久化）
            max_turns: 最大轮次
            enable_hitl: 是否启用Human-in-the-Loop（默认True）
            verbose: 是否详细输出
            log_file: 日志文件路径
            on_progress: 进度更新回调（用于UI展示）
            on_plan_change: 计划变更回调（用于通知用户）
            max_full_messages: 保留完整消息的阈值（默认10）
            recent_keep: 保留最近 N 条完整消息（默认6）
        
        多轮对话使用方式：
            agent = create_simple_agent()
            
            # 开始会话
            result1 = await agent.chat("帮我生成一个PPT")
            
            # 继续对话（保持上下文）
            result2 = await agent.chat("把标题改成'AI技术分享'")
            
            # 结束会话
            agent.end_session()
        """
        self.model = model
        self.workspace_dir = workspace_dir
        self.max_turns = max_turns
        self.enable_hitl = enable_hitl
        self.verbose = verbose
        self.log_file = log_file
        self.on_progress = on_progress
        self.on_plan_change = on_plan_change
        
        # 🆕 上下文压缩配置
        self.max_full_messages = max_full_messages
        self.recent_keep = recent_keep
        
        # 🆕 会话状态
        self._session_active = False
        self._session_id: Optional[str] = None
        self._turn_count = 0
        
        # ===== 核心组件初始化 =====
        
        # 1. 能力注册表
        self.capability_registry = create_capability_registry()
        if self.verbose:
            print(f"✅ CapabilityRegistry loaded: {len(self.capability_registry.capabilities)} capabilities")
        
        # 2. 能力路由器
        self.capability_router = create_capability_router(self.capability_registry)
        if self.verbose:
            print(f"✅ CapabilityRouter initialized")
        
        # 3. Skills管理器
        self.skills_manager = create_skills_manager()
        if self.verbose:
            print(f"✅ SkillsManager loaded: {len(self.skills_manager.skills)} skills")
        
        # 4. 工具执行器
        self.tool_executor = create_tool_executor(self.capability_registry)
        if self.verbose:
            print(f"✅ ToolExecutor initialized")
        
        # 5. 记忆管理
        self.memory = create_memory_manager(workspace_dir=workspace_dir)
        if self.verbose:
            print(f"✅ MemoryManager initialized")
        
        # 6. Plan/Todo 工具（会话级短期记忆）
        # 🆕 关键：将 WorkingMemory 和 Registry 传给工具，实现动态 Schema
        # User Query → Agent → 载入/写入 → Short Memory → CRUD → plan_todo Tool
        from tools.plan_todo_tool import create_plan_todo_tool
        self.plan_todo_tool = create_plan_todo_tool(
            memory=self.memory.working,
            registry=self.capability_registry  # 🆕 传入 Registry
        )
        if self.verbose:
            print(f"✅ PlanTodoTool initialized (integrated with WorkingMemory + dynamic schema)")
        
        # 🆕 7. InvocationSelector - 调用方式选择器
        from core.invocation_selector import create_invocation_selector
        total_tools = len(self.capability_registry.capabilities)
        self.invocation_selector = create_invocation_selector(
            enable_tool_search=(total_tools > 30),  # 工具数量>30时启用
            enable_code_execution=True,
            enable_programmatic=True,
            enable_streaming=True
        )
        if self.verbose:
            print(f"✅ InvocationSelector initialized (total tools: {total_tools})")
        
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
        
        # 🆕 Context Editing（待 Claude API 稳定后启用）
        # TODO: 当前使用应用层消息压缩替代（_build_messages_from_history）
        # self.llm.enable_context_editing()
        
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
        
        if self.verbose:
            print(f"✅ LLM Service initialized with custom tools")
        
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
        
        if self.verbose:
            print(f"\n{'='*60}")
            print(f"🤖 SimpleAgent V3.5 initialized")
            print(f"   Model: {model}")
            print(f"   Capabilities: {len(self.capability_registry.capabilities)}")
            print(f"   Skills: {len(self.skills_manager.skills)}")
            print(f"   Workspace: {workspace_dir or 'None'}")
            print(f"   Plan/Todo: Enabled")
            print(f"{'='*60}\n")
    
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
        
        if self.verbose:
            print(f"   💡 Inferred capabilities for '{task_type}': {capabilities}")
        
        return capabilities
    
    def _handle_progress_update(self, plan: Dict):
        """处理进度更新"""
        if self.on_progress:
            progress_display = self._format_progress_display(plan)
            self.on_progress(progress_display)
        
        if self.verbose:
            self._print_progress(plan)
    
    def _handle_plan_change(self, plan: Dict, reason: str):
        """处理计划变更"""
        # 记录变更
        self.session_log["plan_changes"].append({
            "timestamp": datetime.now().isoformat(),
            "version": plan.get("version", 1),
            "reason": reason
        })
        
        # 通知用户
        if self.on_plan_change:
            self.on_plan_change(plan, reason)
        
        if self.verbose:
            print(f"\n⚠️  Plan Updated (v{plan.get('version', 1)}): {reason}")
            self._print_progress(plan)
    
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
    
    def _print_progress(self, plan: Dict):
        """打印进度（verbose模式）"""
        steps = plan.get("steps", [])
        total = len(steps)
        completed = sum(1 for s in steps if s.get("status") == "completed")
        progress_ratio = completed / total if total > 0 else 0
        bar = self._generate_progress_bar(progress_ratio)
        
        print(f"\n{'─'*50}")
        print(f"📋 Plan Progress: {completed}/{total}")
        print(f"   {bar}")
        print(f"{'─'*50}")
        
        for step in steps:
            status = step.get("status", "pending")
            icon = {"completed": "✅", "in_progress": "🔄", "failed": "❌"}.get(status, "○")
            print(f"   {icon} Step {step.get('step_id', 0)}: {step.get('action', '')} ({status})")
        
        print(f"{'─'*50}\n")
    
    def _generate_progress_bar(self, progress: float, width: int = 30) -> str:
        """生成进度条"""
        filled = int(width * progress)
        empty = width - filled
        return f"[{'█' * filled}{'░' * empty}] {progress*100:.0f}%"
    
    # ============================================================
    # 🆕 多轮对话 API
    # ============================================================
    
    def start_session(self, session_id: Optional[str] = None) -> str:
        """
        开始新会话
        
        Args:
            session_id: 会话ID（可选，自动生成）
            
        Returns:
            会话ID
            
        Example:
            agent.start_session()
            result = await agent.chat("你好")
            agent.end_session()
        """
        self._session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self._session_active = True
        self._turn_count = 0
        
        # 清空工作记忆，开始新会话
        self.memory.working.clear()
        self.memory.working.update_metadata("session_id", self._session_id)
        self.memory.working.update_metadata("start_time", datetime.now().isoformat())
        
        if self.verbose:
            print(f"\n{'='*60}")
            print(f"🚀 Session Started: {self._session_id}")
            print(f"{'='*60}\n")
        
        return self._session_id
    
    def end_session(self) -> Dict[str, Any]:
        """
        结束当前会话
        
        Returns:
            会话摘要
        """
        if not self._session_active:
            return {"status": "no_active_session"}
        
        session_summary = {
            "session_id": self._session_id,
            "turns": self._turn_count,
            "start_time": self.memory.working.metadata.get("start_time"),
            "end_time": datetime.now().isoformat(),
            "message_count": len(self.memory.working.messages),
            "tool_calls": len(self.memory.working.tool_calls),
            "has_plan": self.memory.working.has_plan()
        }
        
        # 清空工作记忆
        self.memory.working.clear()
        
        self._session_active = False
        self._session_id = None
        self._turn_count = 0
        
        if self.verbose:
            print(f"\n{'='*60}")
            print(f"🔚 Session Ended")
            print(f"   Turns: {session_summary['turns']}")
            print(f"   Messages: {session_summary['message_count']}")
            print(f"{'='*60}\n")
        
        return session_summary
    
    async def chat(self, user_input: str) -> Dict[str, Any]:
        """
        多轮对话入口（推荐使用）
        
        自动管理会话状态，支持连续对话。
        
        Args:
            user_input: 用户输入
            
        Returns:
            响应结果
            
        Example:
            agent = create_simple_agent()
            
            # 第一轮对话
            result1 = await agent.chat("帮我生成一个PPT")
            print(result1["content"])
            
            # 第二轮对话（保持上下文）
            result2 = await agent.chat("把标题改成'AI技术分享'")
            print(result2["content"])
            
            # 第三轮...
            result3 = await agent.chat("再加一页关于LLM的内容")
            
            # 结束会话
            agent.end_session()
        """
        # 自动开始会话（如果没有活跃会话）
        if not self._session_active:
            self.start_session()
        
        self._turn_count += 1
        
        if self.verbose:
            print(f"\n{'─'*50}")
            print(f"💬 Turn {self._turn_count}: {user_input[:50]}{'...' if len(user_input) > 50 else ''}")
            print(f"{'─'*50}")
        
        # 调用核心 run 方法（带上下文）
        result = await self.run(user_input)
        
        return result
    
    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """
        获取当前会话的对话历史
        
        Returns:
            消息列表
        """
        return self.memory.working.get_messages()
    
    def get_session_info(self) -> Dict[str, Any]:
        """
        获取当前会话信息
        
        Returns:
            会话信息
        """
        return {
            "session_id": self._session_id,
            "active": self._session_active,
            "turns": self._turn_count,
            "message_count": len(self.memory.working.messages),
            "has_plan": self.memory.working.has_plan()
        }
    
    def _build_messages_from_history(self, current_input: str) -> List[Message]:
        """
        🆕 高效构建消息历史（优化上下文传入）
        
        策略：
        1. 如果消息 <= 10 条：传入完整历史
        2. 如果消息 > 10 条：压缩早期消息为摘要
        3. 始终传入 Plan/Todo 精简状态（如果存在）
        
        Args:
            current_input: 当前用户输入
            
        Returns:
            消息列表（优化后的上下文 + 当前输入）
        """
        messages = []
        
        # 从 WorkingMemory 获取历史消息
        history = self.memory.working.get_messages()
        
        # 🔍 输出历史消息统计
        if self.verbose or len(history) > 0:
            print(f"\n{'='*60}")
            print(f"🧠 构建对话上下文:")
            print(f"   📊 历史消息总数: {len(history)}")
            print(f"   📝 当前输入: {current_input[:80]}{'...' if len(current_input) > 80 else ''}")
        
        # ===== 策略 1: 添加 Plan 精简状态（如果存在）=====
        plan_context = self.memory.working.get_plan_context_for_llm()
        if plan_context:
            if self.verbose:
                print(f"   📋 包含任务计划上下文")
            # 作为系统上下文的一部分，添加到第一条消息前
            messages.append(Message(
                role="user", 
                content=f"[CONTEXT] Current task state:\n{plan_context}"
            ))
            messages.append(Message(
                role="assistant", 
                content="I understand the current task state. Let me continue."
            ))
        
        # ===== 策略 2: 智能压缩历史消息 =====
        if len(history) <= self.max_full_messages:
            # 消息数量少，传入完整历史
            if self.verbose or len(history) > 0:
                print(f"   ✅ 使用完整历史 (≤{self.max_full_messages}条)")
            
            for msg in history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role in ["user", "assistant"]:
                    messages.append(Message(role=role, content=content))
        else:
            # 消息数量多，压缩早期消息
            early_messages = history[:-self.recent_keep]
            recent_messages = history[-self.recent_keep:]
            
            if self.verbose:
                print(f"   📦 压缩早期消息: {len(early_messages)}条 → 摘要")
                print(f"   📌 保留最近消息: {len(recent_messages)}条完整内容")
            
            # 生成早期消息摘要
            summary = self._summarize_messages(early_messages)
            messages.append(Message(
                role="user", 
                content=f"[HISTORY SUMMARY] Earlier conversation:\n{summary}"
            ))
            messages.append(Message(
                role="assistant", 
                content="I understand the earlier context. Continuing with the conversation."
            ))
            
            # 添加最近的完整消息
            for msg in recent_messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role in ["user", "assistant"]:
                    messages.append(Message(role=role, content=content))
        
        # 添加当前用户输入
        messages.append(Message(role="user", content=current_input))
        
        if self.verbose or len(history) > 0:
            print(f"   📤 最终构建: {len(messages)}条消息发送给LLM")
            print(f"{'='*60}\n")
        
        return messages
    
    def _summarize_messages(self, messages: List[Dict]) -> str:
        """
        压缩早期消息为摘要（简单实现）
        
        TODO: 可以使用 LLM 生成更智能的摘要
        
        Args:
            messages: 早期消息列表
            
        Returns:
            摘要文本
        """
        summary_lines = []
        
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            # 只保留关键信息，截断长内容
            if len(content) > 200:
                content = content[:200] + "..."
            
            # 提取工具调用信息
            if "tool_use" in content.lower() or "tool_result" in content.lower():
                # 工具调用只保留名称和状态
                summary_lines.append(f"- [{role}] [Tool interaction]")
            else:
                # 普通消息保留摘要
                summary_lines.append(f"- [{role}] {content[:100]}...")
        
        return "\n".join(summary_lines[-10:])  # 最多保留 10 条摘要
    
    async def stream(self, user_input: str):
        """
        🆕 流式执行Agent（实时输出进度和结果）
        
        架构原则：
        - LLM Service 层：封装 Claude 原生流式能力
        - Agent 层：集成 RVR 机制，产生统一格式事件
        - 用户体验：实时看到 thinking、content、工具执行进度、Plan 更新
        
        基于 run() 方法的完整 RVR 循环，关键差异：
        - run(): 同步调用 llm.create_message()
        - stream(): 流式调用 llm.create_message_stream()，产生增量事件
        
        Args:
            user_input: 用户输入
            
        Yields:
            事件字典，格式：
            {
                "type": str,        # 事件类型
                "data": Dict,       # 事件数据
                "timestamp": str    # ISO格式时间戳
            }
            
        事件类型：
        - session_start/turn_start: 会话/轮次开始
        - status: 状态消息
        - intent_analysis: 意图识别结果
        - tool_selection: 工具筛选结果
        - thinking: LLM思考过程（增量）
        - content: LLM回复内容（增量）
        - tool_call_start: 工具调用开始
        - tool_call_complete: 工具执行完成
        - plan_update: Plan进度更新
        - complete: 任务完成
        - error: 错误信息
        
        Example:
            ```python
            agent = create_simple_agent()
            
            async for event in agent.stream("帮我生成一个PPT"):
                if event["type"] == "thinking":
                    print(f"💭 {event['data']['text']}", end="", flush=True)
                elif event["type"] == "content":
                    print(event['data']['text'], end="", flush=True)
                elif event["type"] == "tool_call_start":
                    print(f"\n🔧 {event['data']['tool_name']}")
                elif event["type"] == "plan_update":
                    print(f"\n📋 {event['data']['progress']}")
                elif event["type"] == "complete":
                    print(f"\n✅ 完成")
            ```
        """
        from datetime import datetime
        import json
        
        # ===== 1. 会话启动 =====
        if not self._session_active:
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.memory.start_session(session_id, user_input)
            self.plan_todo_tool.reset()
            self._session_active = True
            self._session_id = session_id
            self._turn_count = 1
            
            yield self._create_event("session_start", {
                "session_id": session_id,
                "user_input": user_input
            })
        else:
            yield self._create_event("turn_start", {
                "session_id": self._session_id,
                "turn": self._turn_count,
                "user_input": user_input
            })
        
        # ===== 2. 意图识别（Haiku - 快速分类）=====
        yield self._create_event("status", {"message": "🎯 分析任务意图..."})
        
        from prompts.intent_recognition_prompt import get_intent_recognition_prompt
        
        intent_response: LLMResponse = self.intent_llm.create_message(
            messages=[Message(role="user", content=user_input)],
            system=get_intent_recognition_prompt()
        )
        
        intent_analysis = self._parse_intent_analysis(intent_response.content)
        yield self._create_event("intent_analysis", intent_analysis)
        
        # 选择系统提示词
        execution_config = self._get_execution_config(
            intent_analysis['prompt_level'], 
            intent_analysis['complexity']
        )
        self.system_prompt = execution_config['system_prompt']
        
        # ===== 3. 动态工具筛选 + 调用方式选择 =====
        yield self._create_event("status", {"message": "🔧 准备工具..."})
        
        plan = self.memory.working.get_plan()
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
        selected_tools = select_tools_for_capabilities(
            self.capability_router,
            required_capabilities=required_capabilities,
            context={
                "plan": plan, 
                "task_type": intent_analysis['task_type'],
                "available_apis": ["slidespeak", "ragie", "exa"]  # 🆕 声明可用的API
            }
        )
        
        # InvocationSelector 选择调用方式
        invocation_strategy = self.invocation_selector.select_strategy(
            task_type=intent_analysis['task_type'],
            selected_tools=[t.name for t in selected_tools],
            estimated_input_size=len(str(plan)) if plan else 0
        )
        
        yield self._create_event("tool_selection", {
            "required_capabilities": required_capabilities,
            "selected_tools": [t.name for t in selected_tools],
            "invocation_strategy": invocation_strategy.type.value,
            "reason": invocation_strategy.reason
        })
        
        # ===== 4. RVR 循环（流式版本）=====
        messages = self._build_messages_from_history(user_input)
        self.memory.working.add_message("user", user_input)
        
        final_result = None
        
        for turn in range(self.max_turns):
            yield self._create_event("turn_progress", {
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
            
            # 🔑 关键：使用 LLM Service 的流式接口
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
                    yield self._create_event("thinking", {
                        "text": llm_response.thinking
                    })
                    accumulated_thinking += llm_response.thinking
                
                # 🆕 实时输出 content（增量）
                if llm_response.content and llm_response.is_stream:
                    yield self._create_event("content", {
                        "text": llm_response.content
                    })
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
            
            # 记录到 Memory
            self.memory.working.add_message("assistant", response.content)
            
            # 处理 stop_reason
            stop_reason = response.stop_reason
            
            if stop_reason == "end_turn":
                final_result = response.content
                yield self._create_event("status", {"message": "✅ 任务完成"})
                break
            
            elif stop_reason == "tool_use" and response.tool_calls:
                # 🆕 工具调用开始通知
                for tool_call in response.tool_calls:
                    yield self._create_event("tool_call_start", {
                        "tool_name": tool_call.get("name", ""),
                        "tool_id": tool_call.get("id", ""),
                        "input": tool_call.get("input", {})
                    })
                    
                    # 记录调用统计
                    invocation_method = tool_call.get('invocation_method', 'direct')
                    self.invocation_stats[invocation_method] += 1
                
                # 🆕 执行工具（简化版，不使用复杂的进度回调）
                tool_results = await self._execute_tools(response.tool_calls)
                
                # 通知工具完成
                for tool_call, tool_result in zip(response.tool_calls, tool_results):
                    result_content = json.loads(tool_result.get("content", "{}"))
                    yield self._create_event("tool_call_complete", {
                        "tool_name": tool_call.get("name", ""),
                        "success": result_content.get("success", True),
                        "result": result_content.get("result")
                    })
                
                # 🆕 更新 Plan 进度
                self._update_plan_progress_after_tools(response.tool_calls, tool_results)
                
                # 🆕 通知 Plan 进度更新
                updated_plan = self.memory.working.get_plan()
                if updated_plan:
                    yield self._create_event("plan_update", {
                        "plan": updated_plan,
                        "progress": self._format_progress_display(updated_plan)
                    })
                
                # 更新 messages
                messages.append(Message(role="assistant", content=response.raw_content))
                messages.append(Message(role="user", content=tool_results))
            
            else:
                yield self._create_event("error", {
                    "message": f"未知的 stop_reason: {stop_reason}",
                    "turn": turn + 1
                })
                break
        
        # ===== 5. 返回最终结果 =====
        yield self._create_event("complete", {
            "status": "success" if final_result else "incomplete",
            "final_result": final_result,
            "turns": turn + 1,
            "session_id": self._session_id
        })
    
    def _create_event(self, event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建标准化事件"""
        from datetime import datetime
        return {
            "type": event_type,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }
    
    def _emit_event(self, on_event: Optional[Callable], event: Dict[str, Any]):
        """发送事件到回调函数"""
        if on_event:
            try:
                on_event(event)
            except Exception as e:
                if self.verbose:
                    print(f"⚠️ Event callback error: {e}")
    
    async def _execute_tools_with_progress(
        self,
        tool_calls: List[Dict],
        on_progress: Optional[Callable[[str, str, Dict], None]] = None
    ) -> List[Dict]:
        """
        🆕 执行工具（带进度反馈）
        
        Args:
            tool_calls: 工具调用列表
            on_progress: 进度回调 (tool_name, status, data)
        """
        results = []
        
        for tool_call in tool_calls:
            tool_name = tool_call['name']
            tool_input = tool_call['input']
            tool_id = tool_call['id']
            invocation_method = tool_call.get('invocation_method', 'direct')
            
            # 通知开始执行
            if on_progress:
                on_progress(tool_name, "executing", {"input": tool_input})
            
            try:
                # 执行工具
                if tool_name in ["bash", "str_replace_based_edit_tool", "web_search"]:
                    result = {
                        "success": True,
                        "note": f"Native tool {tool_name} executed by Claude API",
                        "invocation_method": invocation_method
                    }
                elif tool_name == "plan_todo":
                    operation = tool_input.get('operation', 'get_plan')
                    data = tool_input.get('data', {})
                    result = self.plan_todo_tool.execute(operation, data)
                    result['invocation_method'] = invocation_method
                else:
                    # 🆕 注入 WorkingMemory 的上下文信息（user_id, conversation_id 等）
                    enriched_input = tool_input.copy()
                    if hasattr(self.memory.working, 'user_id') and self.memory.working.user_id:
                        enriched_input['user_id'] = self.memory.working.user_id
                    if hasattr(self.memory.working, 'conversation_id') and self.memory.working.conversation_id:
                        enriched_input['conversation_id'] = self.memory.working.conversation_id
                    
                    result = await self.tool_executor.execute(tool_name, enriched_input)
                    result['invocation_method'] = invocation_method
                
                # 更新Memory
                if self.memory.working.tool_calls:
                    self.memory.working.tool_calls[-1]['result'] = result
                
                results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": json.dumps(result, ensure_ascii=False)
                })
                
                # 通知完成
                if on_progress:
                    on_progress(tool_name, "completed", {
                        "success": result.get("success", True),
                        "result": result
                    })
            
            except Exception as e:
                error_result = {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": json.dumps({"success": False, "error": str(e)}),
                    "is_error": True
                }
                results.append(error_result)
                
                # 通知失败
                if on_progress:
                    on_progress(tool_name, "failed", {"error": str(e)})
        
        return results
    
    async def run(self, user_input: str) -> Dict[str, Any]:
        """
        运行Agent - 简化版框架
        
        核心原则：Agent 只做框架管理，所有业务逻辑在系统提示词中
        - LLM 自己决定是否需要 Plan
        - LLM 自己执行 RVR
        - LLM 自己决定何时 end_turn
        - Agent 只负责：调用 LLM → 执行工具 → 通知进度 → 返回结果
        
        Args:
            user_input: 用户输入
            
        Returns:
            {
                "status": "success" | "failed" | "incomplete",
                "turns": int,
                "final_result": any,
                "hitl_enabled": bool
            }
        """
        # ===== 1. 会话管理 =====
        # 🆕 多轮对话支持：如果已有活跃会话，复用上下文
        if not self._session_active:
            # 新会话
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.memory.start_session(session_id, user_input)
            self.plan_todo_tool.reset()
            self._session_active = True
            self._session_id = session_id
            self._turn_count = 1
            
            if self.verbose:
                print(f"\n{'='*60}")
                print(f"🚀 New session: {session_id}")
                print(f"📝 User: {user_input[:100]}...")
                print(f"{'='*60}")
        else:
            # 多轮对话：复用现有会话
            if self.verbose:
                print(f"\n{'─'*50}")
                print(f"💬 Continue session: {self._session_id} (turn {self._turn_count})")
                print(f"📝 User: {user_input[:100]}...")
                print(f"{'─'*50}")
        
        # ===== 2. 能力路由（预分析，仅用于日志） =====
        keywords = extract_keywords(user_input)
        routing_result = self.capability_router.route(keywords)
        
        if routing_result:
            self.session_log["routing_decisions"].append({
                "keywords": keywords,
                "selected": routing_result.capability.name,
                "score": routing_result.score,
                "reason": routing_result.reason
            })
            if self.verbose:
                print(f"\n🎯 Routing: {routing_result.capability.name} (score: {routing_result.score:.1f})")
        
        # ===== 3. 意图识别（Haiku 4.5 - 快速分类）→ 选择提示词 =====
        # 🎯 双LLM架构优势：节省input token、用户延迟等待和成本
        # 📝 提示词分层：根据任务复杂度选择合适提示词，但Plan/Todo由Claude自主决定
        from prompts.intent_recognition_prompt import get_intent_recognition_prompt
        
        if self.verbose:
            print(f"\n🎯 Stage 1: Intent Recognition (Haiku 4.5)...")
        
        intent_response: LLMResponse = self.intent_llm.create_message(
            messages=[Message(role="user", content=user_input)],
            system=get_intent_recognition_prompt()
        )
        
        intent_analysis = self._parse_intent_analysis(intent_response.content)
        self.session_log["intent_recognition"] = intent_analysis
        
        if self.verbose:
            print(f"   Task Type: {intent_analysis['task_type']}")
            print(f"   Complexity: {intent_analysis['complexity']}")
            print(f"   Prompt Level: {intent_analysis['prompt_level']}")
        
        # 根据意图选择系统提示词（分层优化）
        execution_config = self._get_execution_config(
            intent_analysis['prompt_level'], 
            intent_analysis['complexity']
        )
        self.system_prompt = execution_config['system_prompt']
        
        if self.verbose:
            print(f"\n🧠 Stage 2: Task Execution (Sonnet 4.5)")
            print(f"   System Prompt: {execution_config['prompt_name']}")
        
        # 🆕 ===== 3.5. 动态工具筛选 + 调用方式选择 =====
        # 策略：
        # 1. 有 Plan → 从 Plan 提取 required_capabilities
        # 2. 无 Plan（简单任务）→ 根据 task_type 推断基础能力
        # 3. 都没有（首轮复杂任务）→ 传入所有工具让 Sonnet 创建 Plan
        selected_tools = None
        invocation_strategy = None
        required_capabilities = []
        
        # ===== 能力推断策略（统一逻辑）=====
        # 优先级：
        #   1. 已有 Plan → 从 Plan 提取（更精确，Sonnet 分析后的结果）
        #   2. 无 Plan → 从 task_type_mappings 推断（不区分简单/复杂任务）
        #
        # 🎯 关键改进：复杂任务首轮也能筛选工具，不再"传入所有工具"
        
        plan = self.memory.working.get_plan()
        
        # 策略1: 已有 Plan → 从 Plan 提取（更精确）
        if plan:
            # 优先从 required_capabilities 字段提取
            required_capabilities = plan.get('required_capabilities', [])
            
            # 备选：从 steps 中提取 capability
            if not required_capabilities:
                required_capabilities = list(set([
                    step.get('capability', '') 
                    for step in plan.get('steps', []) 
                    if step.get('capability')
                ]))
            
            if self.verbose and required_capabilities:
                print(f"\n📋 Capabilities from Plan: {required_capabilities}")
        
        # 策略2: 无 Plan → 从 task_type_mappings 推断（统一适用于简单/复杂任务）
        if not required_capabilities:
            required_capabilities = self._infer_capabilities_from_task_type(
                intent_analysis['task_type']
            )
            
            if self.verbose:
                task_desc = "Simple" if intent_analysis.get('complexity') == 'simple' else "Complex (first turn)"
                print(f"\n💡 {task_desc} task - inferred capabilities: {required_capabilities}")
        
        # 🆕 统一使用 Router 筛选工具（所有任务都走这条路径）
        from core.capability_router import select_tools_for_capabilities
        selected_tools = select_tools_for_capabilities(
            self.capability_router,
            required_capabilities=required_capabilities,
            context={
                "plan": plan, 
                "task_type": intent_analysis['task_type'],
                "available_apis": ["slidespeak"]  # 🆕 声明可用的API
            }
        )
        
        # 🆕 使用 InvocationSelector 选择调用方式
        invocation_strategy = self.invocation_selector.select_strategy(
            task_type=intent_analysis['task_type'],
            selected_tools=[t.name for t in selected_tools],
            estimated_input_size=len(str(plan)) if plan else 0
        )
        
        if self.verbose:
            print(f"\n🔧 Dynamic Tool Selection:")
            print(f"   Required capabilities: {required_capabilities}")
            print(f"   Selected {len(selected_tools)} tools (from {len(self.capability_registry.capabilities)} total)")
            print(f"   Tools: {[t.name for t in selected_tools]}")
            print(f"   Invocation: {invocation_strategy.type.value} - {invocation_strategy.reason}")
        
        # ===== 4. 主循环：LLM 决定一切 =====
        # 🆕 多轮对话：从 WorkingMemory 构建完整消息历史
        messages = self._build_messages_from_history(user_input)
        
        # 将用户消息添加到 Memory（用于下一轮）
        self.memory.working.add_message("user", user_input)
        
        final_result = None
        turn = 0
        
        # max_turns = 框架安全上限（默认20），与 Todo 步骤数无关
        # Todo 步骤数仅用于用户进度显示
        for turn in range(self.max_turns):
            if self.verbose:
                print(f"\n{'─'*40}")
                print(f"🔄 Turn {turn + 1}/{self.max_turns}")
                print(f"{'─'*40}")
            
            # 🆕 4.1 准备工具列表（始终使用动态筛选后的工具）
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
                        # SKILL 类型需要通过其他方式执行（如 bash + scripts）
                        if capability.type.value != "TOOL":
                            if self.verbose:
                                print(f"⚠️ '{tool_name}' 是 {capability.type.value} 类型，不是 TOOL，跳过")
                            continue
                        
                        # 检查是否有有效的 input_schema
                        if not capability.input_schema:
                            if self.verbose:
                                print(f"⚠️ 工具 '{tool_name}' 缺少 input_schema，跳过")
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
                    else:
                        if self.verbose:
                            print(f"⚠️ 工具 '{tool_name}' 未找到，跳过")
            
            # 🆕 4.2 准备工具配置（根据 invocation_strategy）
            # invocation_selector 需要工具名列表来决定策略配置
            tools_config = self.invocation_selector.get_tools_config(
                all_tools=[{"name": t if isinstance(t, str) else t.get("name", "")} for t in tools_for_llm],
                strategy=invocation_strategy
            )
            llm_kwargs = tools_config.get('extra', {})
            
            # 4.3 调用 LLM（传入混合列表：字符串 + 完整 schema）
            response: LLMResponse = self.llm.create_message(
                messages=messages,
                system=self.system_prompt,
                tools=tools_for_llm,  # 混合列表：["bash", {...schema...}, "web_search"]
                **llm_kwargs
            )
            
            # 4.2 记录到 Memory
            self.memory.working.add_message("assistant", response.content)
            
            # 4.3 记录交互（简化版，不解析 thinking）
            self._log_interaction(turn + 1, "llm_response", {
                "stop_reason": response.stop_reason,
                "has_thinking": bool(response.thinking),
                "response_length": len(response.content) if response.content else 0,
                "tool_calls_count": len(response.tool_calls) if response.tool_calls else 0
            })
            
            # 4.4 显示信息
            if self.verbose and response.thinking:
                print(f"💭 Thinking: {response.thinking[:200]}...")
                
                # 提取并展示 Plan（纯展示，不做业务判断）
                self._display_plan_from_thinking(response.thinking, turn + 1)
            
            # 4.5 处理 stop_reason（Agent 不判断业务逻辑，LLM 自己决定）
            if response.stop_reason == "end_turn":
                # LLM 决定结束，直接接受结果
                final_result = response.content
                
                if self.verbose:
                    print(f"\n✅ LLM ended turn")
                break
            
            elif response.stop_reason == "tool_use" and response.tool_calls:
                # 4.6 执行工具
                for tool_call in response.tool_calls:
                    invocation_method = tool_call.get('invocation_method', 'direct')
                    self.invocation_stats[invocation_method] += 1
                    
                    if self.verbose:
                        method_emoji = {"direct": "🔧", "code_execution": "💻", "programmatic": "🔗"}.get(invocation_method, "🔧")
                        print(f"   {method_emoji} Tool: {tool_call['name']}")
                    
                    # 通知进度（用户输出）
                    self._notify_tool_progress(tool_call)
                
                tool_results = await self._execute_tools(response.tool_calls)
                
                # 🆕 更新并显示 Plan 进度（每次工具执行后）
                self._update_plan_progress_after_tools(response.tool_calls, tool_results)
                
                # 更新 messages
                messages.append(Message(role="assistant", content=response.raw_content))
                messages.append(Message(role="user", content=tool_results))
            
            else:
                if self.verbose:
                    print(f"⚠️ Unexpected stop_reason: {response.stop_reason}")
                break
        
        # ===== 5. 会话结束 =====
        self.memory.end_session(final_result, metadata={
            "turns": turn + 1,
            "invocation_stats": self.invocation_stats
        })
        
        if self.verbose:
            print(f"\n{'='*60}")
            print(f"📊 Session Summary: {turn + 1} turns")
            total_calls = sum(self.invocation_stats.values())
            if total_calls > 0:
                print(f"   Tool calls: {total_calls}")
            print(f"{'='*60}\n")
        
        if self.log_file:
            self._save_log()
        
        # 返回结果
        return {
            "status": "success" if final_result else "incomplete",
            "turns": turn + 1,
            "final_result": final_result,
            "routing_decisions": self.session_log["routing_decisions"],
            "hitl_enabled": self.enable_hitl,
            "invocation_stats": self.invocation_stats,
            "interactions": self.session_log["interactions"],
            "session_log": self.session_log
        }
    
    def _notify_tool_progress(self, tool_call: Dict):
        """通知工具执行进度（用户输出）"""
        if self.on_progress:
            tool_name = tool_call.get('name', 'unknown')
            self.on_progress(f"🔧 Executing: {tool_name}")
    
    def _update_plan_progress_after_tools(self, tool_calls: List[Dict], tool_results: List[Dict]):
        """
        🆕 工具执行后更新 Plan 进度（用户可见的实时进度）
        
        逻辑：
        1. 检查 WorkingMemory 中是否有 Plan
        2. 根据工具调用更新对应步骤的状态
        3. 显示更新后的进度
        """
        # 检查是否有 Plan
        if not self.memory.working.has_plan():
            return
        
        plan = self.memory.working.get_plan()
        if not plan or 'steps' not in plan:
            return
        
        steps = plan.get('steps', [])
        if not steps:
            return
        
        # 更新步骤状态：匹配工具名和步骤
        for tool_call in tool_calls:
            tool_name = tool_call.get('name', '')
            
            for step in steps:
                # 如果步骤还是 pending 且包含这个工具名
                if step.get('status') == 'pending':
                    action = step.get('action', '').lower()
                    if tool_name.lower() in action or action in tool_name.lower():
                        step['status'] = 'completed'
                        break
        
        # 计算进度
        total = len(steps)
        completed = sum(1 for s in steps if s.get('status') == 'completed')
        progress = completed / total if total > 0 else 0
        
        # 更新 WorkingMemory
        self.memory.working.set_plan(plan, self.memory.working.get_todo())
        
        # 显示进度更新（用户可见）
        if self.verbose:
            self._display_plan_progress_update(plan, completed, total, progress)
    
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
    
    def _display_plan_from_thinking(self, thinking: str, turn: int):
        """
        从 LLM 的 thinking 中提取并展示 Plan/Todo（纯展示，不做业务判断）
        
        注意：
        - plan.json - 内部状态（存储到 WorkingMemory）
        - todo.md - 用户可见的 Markdown 格式进度展示
        """
        import re
        
        # 只在第一轮展示
        if turn > 1:
            return
        
        # 尝试提取 Goal
        goal = None
        goal_match = re.search(r'Goal:\s*(.+?)(?=\n|$)', thinking, re.IGNORECASE)
        if goal_match:
            goal = goal_match.group(1).strip()
        
        # 尝试提取 [Plan] 块
        plan_match = re.search(r'\[Plan\](.*?)(?=\[|$)', thinking, re.DOTALL | re.IGNORECASE)
        if plan_match:
            plan_content = plan_match.group(1).strip()
            if plan_content:
                # 解析步骤
                steps_raw = re.findall(r'(\d+)\.\s*(.+?)(?=\d+\.|$)', plan_content, re.DOTALL)
                if steps_raw:
                    # 构建 plan.json（内部状态）
                    plan_json = {
                        "goal": goal or "执行任务",
                        "version": 1,
                        "steps": []
                    }
                    
                    # 构建步骤列表
                    for num, step_text in steps_raw:
                        step_clean = step_text.strip().split('\n')[0]
                        plan_json["steps"].append({
                            "step_id": int(num),
                            "action": step_clean,
                            "status": "pending"
                        })
                    
                    # 存储到 WorkingMemory（plan.json 是内部状态）
                    self.memory.working.set_plan(plan_json, None)
                    
                    # === 展示 Todo.md 风格（用户可见）===
                    print(f"\n┌─────────────────────────────────────")
                    if goal:
                        print(f"│ 🎯 Goal: {goal}")
                    print(f"├─────────────────────────────────────")
                    print(f"│ 📋 Todo List ({len(steps_raw)} items)")
                    print(f"│")
                    
                    # Todo.md 风格：Markdown checkbox
                    for num, step_text in steps_raw:
                        step_clean = step_text.strip().split('\n')[0]
                        # 提取描述（去掉工具调用细节）
                        if '→' in step_clean:
                            desc = step_clean.split('→')[-1].strip()
                        else:
                            desc = step_clean
                        # 截断
                        if len(desc) > 35:
                            desc = desc[:32] + '...'
                        print(f"│ - [ ] {desc}")
                    
                    print(f"│")
                    print(f"│ [{'░' * 20}] 0%")
                    print(f"└─────────────────────────────────────")
                    print()
                else:
                    # 按行显示（简化版）
                    print(f"\n📋 Todo:")
                    for line in plan_content.split('\n')[:5]:
                        line = line.strip()
                        if line and not line.startswith('['):
                            print(f"   - [ ] {line}")
                    print()
        
        # 检查是否有 "Needs Plan: false" 或 "不需要Plan"
        if 'needs plan: false' in thinking.lower() or ('不需要' in thinking.lower() and 'plan' in thinking.lower()):
            if self.verbose:
                print(f"   ℹ️ 简单任务，无需 Plan/Todo")
    
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
            if self.verbose:
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
        """执行工具调用"""
        results = []
        
        for tool_call in tool_calls:
            tool_name = tool_call['name']
            tool_input = tool_call['input']
            tool_id = tool_call['id']
            invocation_method = tool_call.get('invocation_method', 'direct')
            
            if self.verbose:
                print(f"🔧 Executing: {tool_name}")
            
            # 记录到Memory
            self.memory.working.add_tool_call(tool_name, tool_input)
            
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
                    if self.verbose and result.get('display'):
                        print(f"\n{result['display']}\n")
                else:
                    # 其他自定义工具
                    # 🆕 注入 user_id 和 conversation_id 到工具参数（从 WorkingMemory）
                    enriched_input = {**tool_input}
                    if hasattr(self.memory.working, 'user_id') and self.memory.working.user_id:
                        enriched_input['user_id'] = self.memory.working.user_id
                    if hasattr(self.memory.working, 'conversation_id') and self.memory.working.conversation_id:
                        enriched_input['conversation_id'] = self.memory.working.conversation_id
                    
                    result = await self.tool_executor.execute(tool_name, enriched_input)
                    result['invocation_method'] = invocation_method
                
                # 更新Memory
                if self.memory.working.tool_calls:
                    self.memory.working.tool_calls[-1]['result'] = result
                
                results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": json.dumps(result, ensure_ascii=False)
                })
                
                if self.verbose:
                    status = "✅" if result.get("success") else "❌"
                    print(f"   {status} Result: {str(result)[:100]}...")
            
            except Exception as e:
                results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": json.dumps({"success": False, "error": str(e)}),
                    "is_error": True
                })
                
                if self.verbose:
                    print(f"   ❌ Error: {e}")
        
        return results
    
    # ============================================================
    # 🆕 HITL (Human-in-the-Loop) 增强 API
    # ============================================================
    
    async def refine(
        self,
        original_query: str,
        previous_result: str,
        user_feedback: str
    ) -> Dict[str, Any]:
        """
        基于用户反馈改进结果 (HITL - Post-task Feedback)
        
        场景：用户对完成的结果不满意，请求改进
        
        Example:
            result = await agent.chat("生成一个PPT")
            # 用户不满意
            refined = await agent.refine(
                original_query="生成一个PPT",
                previous_result=result['final_result'],
                user_feedback="标题字体太小了，内容太少"
            )
        """
        if self.verbose:
            print(f"\n{'='*60}")
            print(f"🔄 HITL Refinement")
            print(f"📝 User Feedback: {user_feedback[:100]}...")
            print(f"{'='*60}")
        
        # 如果有现有计划，添加重试步骤
        if self.plan_todo_tool.has_plan():
            self.plan_todo_tool.execute("add_step", {
                "action": "refine",
                "purpose": f"根据用户反馈改进: {user_feedback[:50]}..."
            })
        
        refine_query = f"""
原始请求：{original_query}

之前的结果：
{previous_result}

用户反馈：
{user_feedback}

请根据用户反馈改进结果。
"""
        
        return await self.chat(refine_query)  # 🆕 使用 chat 保持上下文
    
    async def confirm(self, question: str) -> str:
        """
        请求用户确认 (HITL - Confirmation)
        
        场景：Agent 需要用户确认后才继续执行
        
        注意：这是一个同步阻塞调用，需要 UI 层支持
        
        Example:
            # 在 UI 层
            confirmation = await agent.confirm("是否删除所有文件？")
            if confirmation == "yes":
                await agent.chat("继续删除")
        """
        self._pending_confirmation = {
            "type": "confirmation",
            "question": question,
            "timestamp": datetime.now().isoformat()
        }
        
        if self.on_progress:
            self.on_progress(f"❓ 需要确认: {question}")
        
        # 返回问题，等待用户响应
        return question
    
    async def clarify(self, clarification_needed: str) -> Dict[str, Any]:
        """
        请求用户澄清 (HITL - Clarification)
        
        场景：用户指令模糊，Agent 需要更多信息
        
        Example:
            # Agent 发现指令模糊
            response = await agent.clarify("你希望PPT是什么风格？商务/学术/创意？")
            # 用户回复后继续
            result = await agent.chat("商务风格")
        """
        self._pending_clarification = {
            "type": "clarification",
            "question": clarification_needed,
            "timestamp": datetime.now().isoformat()
        }
        
        if self.on_progress:
            self.on_progress(f"🤔 需要澄清: {clarification_needed}")
        
        # 在多轮对话中，用户的下一条消息会自动作为澄清回复
        return {
            "status": "needs_clarification",
            "question": clarification_needed,
            "instruction": "请用 chat() 提供更多信息"
        }
    
    def get_pending_interaction(self) -> Optional[Dict[str, Any]]:
        """
        获取待处理的用户交互请求
        
        Returns:
            {
                "type": "confirmation" | "clarification",
                "question": str,
                "timestamp": str
            }
            或 None（无待处理交互）
        """
        if hasattr(self, '_pending_confirmation') and self._pending_confirmation:
            return self._pending_confirmation
        if hasattr(self, '_pending_clarification') and self._pending_clarification:
            return self._pending_clarification
        return None
    
    def clear_pending_interaction(self):
        """清除待处理的用户交互请求"""
        self._pending_confirmation = None
        self._pending_clarification = None
    
    
    def _log_interaction(self, turn: int, event_type: str, data: Dict):
        """记录交互"""
        self.session_log["interactions"].append({
            "turn": turn,
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "data": data
        })
    
    def _save_log(self):
        """保存日志"""
        if not self.log_file:
            return
        
        self.session_log["end_time"] = datetime.now().isoformat()
        
        log_dir = os.path.dirname(self.log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        
        with open(self.log_file, 'w', encoding='utf-8') as f:
            json.dump(self.session_log, f, ensure_ascii=False, indent=2)
        
        if self.verbose:
            print(f"\n💾 Log saved: {self.log_file}")
    
    # ==================== 辅助方法 ====================
    
    def get_plan(self) -> Optional[Dict]:
        """获取当前计划（从 Short Memory）"""
        return self.memory.working.get_plan()
    
    def get_todo_md(self) -> Optional[str]:
        """获取当前 Todo.md 内容（从 Short Memory）"""
        return self.memory.working.get_todo()
    
    def get_progress(self) -> Dict[str, Any]:
        """获取当前进度"""
        plan = self.memory.working.get_plan()
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
            f"HITL Enabled: {self.enable_hitl}",
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
    verbose: bool = False,
    log_file: str = None,
    on_progress: Optional[Callable[[str], None]] = None,
    on_plan_change: Optional[Callable[[Dict, str], None]] = None,
    max_full_messages: int = 10,
    recent_keep: int = 6
) -> SimpleAgent:
    """
    创建SimpleAgent
    
    Args:
        model: 模型名称
        workspace_dir: 工作目录
        verbose: 是否详细输出
        log_file: 日志文件路径
        on_progress: 进度更新回调
        on_plan_change: 计划变更回调（Dict格式）
        max_full_messages: 保留完整消息的阈值（默认10）
        recent_keep: 保留最近 N 条完整消息（默认6）
        
    Returns:
        配置好的SimpleAgent实例
    """
    return SimpleAgent(
        model=model,
        workspace_dir=workspace_dir,
        verbose=verbose,
        log_file=log_file,
        on_progress=on_progress,
        on_plan_change=on_plan_change,
        max_full_messages=max_full_messages,
        recent_keep=recent_keep
    )
