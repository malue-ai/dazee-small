"""
ToolSelector - 工具选择器

职责：
1. 根据意图和能力需求选择合适的工具
2. 管理基础工具和动态工具的选择
3. 提供工具 Schema 转换（用于 Claude API）

设计原则：
- 单一职责：只做工具选择
- 配置驱动：工具配置从 capabilities.yaml 加载
- 可扩展：支持自定义选择策略

注意：
- 能力管理使用 core/tool/capability/ 子包
- 具体工具实现在 tools/ 目录下
"""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional

from logger import Logger

# 🆕 从 capability 子包导入
from core.tool.capability import (
    CapabilityRegistry,
    CapabilityType,
    create_capability_registry
)

logger = Logger.get_logger(__name__)


@dataclass
class ToolSelectionResult:
    """
    工具选择结果
    
    包含选中的工具列表和选择原因
    """
    tools: List[Any]                         # 选中的工具列表（Capability 对象）
    tool_names: List[str]                    # 工具名称列表
    base_tools: List[str]                    # 基础工具名称
    dynamic_tools: List[str]                 # 动态选择的工具名称
    reason: str = ""                         # 选择原因
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "tool_names": self.tool_names,
            "base_tools": self.base_tools,
            "dynamic_tools": self.dynamic_tools,
            "total_count": len(self.tools),
            "reason": self.reason
        }


class ToolSelector:
    """
    工具选择器
    
    根据任务需求智能选择合适的工具
    
    🆕 V4.2.4 工具分层设计：
    - Level 1（核心工具）：始终加载，如 plan_todo
    - Level 2（动态工具）：按需加载，如 exa_search, e2b_python_sandbox
    
    🆕 V10.0 配置化重构：
    - 核心工具、原生工具列表从 capabilities.yaml 读取
    - 代码中的列表仅作为 fallback 默认值
    
    使用方式：
        selector = ToolSelector(registry)
        result = selector.select(
            required_capabilities=["web_search", "ppt_generation"],
            context={"task_type": "content_generation"}
        )
        print(result.tool_names)  # ["plan_todo", "bash", "web_search", "slidespeak_render"]
    """
    
    # 默认核心工具（作为配置文件不存在时的 fallback）
    # 🆕 V10.0: 实际值从 capabilities.yaml 的 tool_selection.core_tools 读取
    DEFAULT_CORE_TOOLS = ["plan_todo", "request_human_confirmation"]
    
    # 默认原生工具（作为配置文件不存在时的 fallback）
    # 🆕 V10.0: 实际值从 capabilities.yaml 的 tool_selection.native_tools 读取
    DEFAULT_NATIVE_TOOLS = ["bash", "text_editor", "web_search"]
    
    def __init__(
        self,
        registry: CapabilityRegistry = None
    ):
        """
        初始化工具选择器
        
        🆕 V10.0: 从 capabilities.yaml 加载工具配置
        
        Args:
            registry: CapabilityRegistry 实例
        """
        self.registry = registry
        
        # 如果没有提供，创建默认实例
        if self.registry is None:
            self.registry = create_capability_registry()
        
        # 🆕 缓存核心工具列表（Level 1）
        self._core_tools_cache: Optional[List[str]] = None
        
        # 🆕 V10.0: 从配置加载工具列表
        tool_selection_config = self._load_tool_selection_config()
        self.NATIVE_TOOLS = tool_selection_config.get("native_tools", self.DEFAULT_NATIVE_TOOLS)
        self.SERIAL_ONLY_TOOLS = set(tool_selection_config.get("serial_only_tools", ["plan_todo", "request_human_confirmation"]))
        self._config_core_tools = tool_selection_config.get("core_tools", self.DEFAULT_CORE_TOOLS)
        
        logger.debug(
            f"📦 ToolSelector 初始化: "
            f"core_tools={self._config_core_tools}, "
            f"native_tools={self.NATIVE_TOOLS}"
        )
    
    def _load_tool_selection_config(self) -> Dict[str, Any]:
        """
        从 capabilities.yaml 加载工具选择配置
        
        🆕 V10.0: 配置化工具列表
        
        Returns:
            Dict: tool_selection 配置，如果加载失败返回空字典
        """
        import yaml
        from pathlib import Path
        
        # 查找配置文件
        config_paths = [
            Path(__file__).parent.parent.parent / "config" / "capabilities.yaml",
            Path("/Users/liuyi/Documents/langchain/CoT_agent/mvp/zenflux_agent/config/capabilities.yaml"),
        ]
        
        for config_path in config_paths:
            if config_path.exists():
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = yaml.safe_load(f) or {}
                    
                    tool_selection = config.get("tool_selection", {})
                    if tool_selection:
                        logger.debug(f"✅ 从 {config_path} 加载工具选择配置")
                        return tool_selection
                except Exception as e:
                    logger.warning(f"⚠️ 加载工具选择配置失败: {e}")
        
        logger.debug("📌 使用默认工具选择配置")
        return {}
    
    def get_core_tools(self) -> List[str]:
        """
        获取核心工具名称列表（Level 1）
        
        核心工具始终加载，不受动态选择影响。
        
        🆕 V10.0: 优先级
        1. 从 Registry 读取 level=1 的工具
        2. 配置文件中的 tool_selection.core_tools
        3. DEFAULT_CORE_TOOLS 硬编码默认值
        
        Returns:
            核心工具名称列表
        """
        if self._core_tools_cache is not None:
            return self._core_tools_cache
        
        # 从 Registry 获取 Level 1 工具
        core_caps = self.registry.get_core_tools()
        
        if core_caps:
            self._core_tools_cache = [c.name for c in core_caps]
            logger.debug(f"📌 核心工具 (Level 1 from Registry): {self._core_tools_cache}")
        elif self._config_core_tools:
            # 🆕 V10.0: 使用配置文件中的核心工具
            self._core_tools_cache = list(self._config_core_tools)
            logger.debug(f"📌 核心工具 (from config): {self._core_tools_cache}")
        else:
            # 备用：使用硬编码默认值
            self._core_tools_cache = self.DEFAULT_CORE_TOOLS.copy()
            logger.debug(f"📌 核心工具 (fallback default): {self._core_tools_cache}")
        
        return self._core_tools_cache
    
    def get_cacheable_tools(self) -> List[str]:
        """
        获取可缓存工具名称列表
        
        cache_stable=true 的工具，同输入产生同输出，
        可安全使用 prompt cache。
        
        Returns:
            可缓存工具名称列表
        """
        return self.registry.get_cacheable_tools()
    
    def select(
        self,
        required_capabilities: List[str],
        context: Optional[Dict[str, Any]] = None,
        include_native: bool = True
    ) -> ToolSelectionResult:
        """
        选择工具
        
        🆕 V4.2.4 分层选择逻辑：
        1. 始终加载 Level 1 核心工具（plan_todo 等）
        2. 根据能力需求从 Level 2 动态工具中选择
        
        Args:
            required_capabilities: 所需能力列表（如 ["web_search", "ppt_generation"]）
            context: 上下文信息（包含 task_type, available_apis 等）
            include_native: 是否包含 Claude 原生工具
            
        Returns:
            ToolSelectionResult 选择结果
        """
        context = context or {}
        selected = []
        selected_skills_capabilities = set()
        
        # 1. 🆕 添加核心工具（Level 1）- 始终加载
        base_tools = []
        core_tool_names = self.get_core_tools()
        for name in core_tool_names:
            cap = self.registry.get(name)
            if cap and cap not in selected:
                selected.append(cap)
                base_tools.append(name)
        
        # 2. 根据能力标签选择工具
        dynamic_tools = []
        fallback_tools_to_add = []  # 🆕 收集需要添加的 fallback 工具
        
        for capability_tag in required_capabilities:
            matched = self.registry.find_by_capability_tag(capability_tag)
            
            if not matched:
                # 兼容：直接按工具/能力名称匹配
                direct_cap = self.registry.get(capability_tag)
                if direct_cap:
                    matched = [direct_cap]
                else:
                    logger.warning(f"⚠️ 未找到匹配能力的工具: {capability_tag}")
                    continue
            
            # 按优先级排序
            matched.sort(key=lambda c: c.priority, reverse=True)
            
            for tool in matched:
                # 检查约束条件
                if not tool.meets_constraints(context):
                    continue
                
                if tool not in selected:
                    selected.append(tool)
                    dynamic_tools.append(tool.name)
                    
                    # 如果是 Skill，收集其能力需求
                    if tool.type == CapabilityType.SKILL:
                        selected_skills_capabilities.update(tool.capabilities)
                        
                        # 🆕 如果 SKILL 有 fallback_tool，添加到待处理列表
                        if tool.fallback_tool:
                            fallback_tools_to_add.append(tool.fallback_tool)
                            logger.debug(f"📌 SKILL '{tool.name}' 指定 fallback_tool: {tool.fallback_tool}")
        
        # 🆕 3. 优先添加 fallback 工具（确保 SKILL 的替代实现可用）
        for fallback_name in fallback_tools_to_add:
            fallback_cap = self.registry.get(fallback_name)
            if fallback_cap and fallback_cap not in selected:
                if fallback_cap.meets_constraints(context):
                    selected.append(fallback_cap)
                    dynamic_tools.append(fallback_name)
                    logger.info(f"✅ 添加 fallback 工具: {fallback_name}")
        
        # 4. 自动包含 Skills 依赖的底层工具（非 fallback 的情况）
        for skill_capability in selected_skills_capabilities:
            tools_for_capability = [
                c for c in self.registry.find_by_capability_tag(skill_capability)
                if c.type == CapabilityType.TOOL
            ]
            
            for tool in tools_for_capability:
                if tool not in selected and tool.meets_constraints(context):
                    selected.append(tool)
                    dynamic_tools.append(tool.name)
                    logger.debug(f"✅ 自动包含工具 {tool.name} (Skills 依赖)")
        
        # 5. 按优先级排序
        selected.sort(key=lambda c: c.priority, reverse=True)
        
        # 6. 提取工具名称
        tool_names = [t.name for t in selected]
        
        # 7. 添加原生工具（如果需要）
        if include_native:
            for native_tool in self.NATIVE_TOOLS:
                if native_tool not in tool_names:
                    tool_names.append(native_tool)
        
        logger.info(
            f"🔧 工具选择完成: "
            f"基础={len(base_tools)}, "
            f"动态={len(dynamic_tools)}, "
            f"总计={len(tool_names)}"
        )
        
        return ToolSelectionResult(
            tools=selected,
            tool_names=tool_names,
            base_tools=base_tools,
            dynamic_tools=dynamic_tools,
            reason=f"基于能力需求 {required_capabilities} 选择"
        )
    
    def select_for_task_type(
        self,
        task_type: str,
        context: Optional[Dict[str, Any]] = None
    ) -> ToolSelectionResult:
        """
        根据任务类型选择工具
        
        Args:
            task_type: 任务类型（如 "information_query"）
            context: 上下文信息
            
        Returns:
            ToolSelectionResult 选择结果
        """
        # 从 Registry 获取任务类型对应的能力
        required_capabilities = self.registry.get_capabilities_for_task_type(task_type)
        
        logger.debug(f"任务类型 '{task_type}' 推断能力: {required_capabilities}")
        
        return self.select(required_capabilities, context)
    
    def get_tools_for_llm(
        self,
        selection: ToolSelectionResult,
        llm_service=None
    ) -> List[Any]:
        """
        将选择结果转换为 LLM API 格式
        
        Args:
            selection: 工具选择结果
            llm_service: LLM 服务（用于 schema 转换）
            
        Returns:
            LLM API 格式的工具列表
        """
        tools_for_llm = []
        
        for tool_name in selection.tool_names:
            # Claude 原生工具：直接使用字符串
            if tool_name in self.NATIVE_TOOLS:
                tools_for_llm.append(tool_name)
                continue
            
            # 自定义工具：需要转换为 schema
            capability = self.registry.get(tool_name)
            if not capability:
                continue
            
            # 只有 TOOL 类型且有 input_schema 的才能作为 Claude API 工具
            if capability.type != CapabilityType.TOOL:
                continue
            
            if not capability.input_schema:
                continue
            
            # 转换为 Claude API 格式
            if llm_service and hasattr(llm_service, 'convert_to_claude_tool'):
                capability_dict = {
                    "name": capability.name,
                    "type": capability.type.value,
                    "provider": capability.provider,
                    "metadata": capability.metadata,
                    "input_schema": capability.input_schema
                }
                tool_schema = llm_service.convert_to_claude_tool(capability_dict)
                tools_for_llm.append(tool_schema)
            else:
                # 简化版：直接构建 schema
                tools_for_llm.append({
                    "name": capability.name,
                    "description": capability.metadata.get('description', capability.name),
                    "input_schema": capability.input_schema
                })
        
        return tools_for_llm
    
    def resolve_capabilities(
        self,
        schema_tools: Optional[List[str]] = None,
        plan: Optional[Dict[str, Any]] = None,
        intent_task_type: Optional[str] = None
    ) -> tuple[List[str], str, List[str]]:
        """
        🆕 V10.0: 三级优先级能力解析
        
        优先级（合并策略）：
        1. Schema 配置（schema.tools）- 运营显式配置，最高优先级
        2. Plan 推荐（plan.required_capabilities）- 任务规划补充
        3. Intent 推断（intent → task_type → capabilities）- 兜底
        
        将工具选择策略从 SimpleAgent 提取到 ToolSelector，
        保持 SimpleAgent 作为纯 RVR 编排层。
        
        Args:
            schema_tools: Schema 配置的工具列表（最高优先级）
            plan: Plan 规划结果（包含 required_capabilities）
            intent_task_type: 意图任务类型（用于推断能力）
            
        Returns:
            tuple: (required_capabilities, selection_source, overridden_sources)
            - required_capabilities: 解析后的能力列表
            - selection_source: 选择来源标识（如 "schema+plan"）
            - overridden_sources: 被覆盖的来源列表（用于日志）
        """
        required_capabilities = []
        selection_sources = []
        overridden_sources = []
        
        # 1. Schema 配置（最高优先级）
        if schema_tools:
            valid_tools = []
            invalid_tools = []
            for tool_name in schema_tools:
                if self.registry.get(tool_name) or tool_name in self.NATIVE_TOOLS:
                    valid_tools.append(tool_name)
                else:
                    invalid_tools.append(tool_name)
            
            if invalid_tools:
                logger.warning(
                    f"⚠️ Schema 配置了无效工具: {invalid_tools}，已自动过滤。"
                    f"有效工具: {valid_tools}"
                )
            
            required_capabilities.extend(valid_tools)
            if valid_tools:
                selection_sources.append("schema")
        
        # 2. Plan 推荐（补充，不覆盖已有的）
        plan_capabilities = plan.get('required_capabilities', []) if plan else []
        if plan_capabilities:
            added_from_plan = []
            for cap in plan_capabilities:
                if cap not in required_capabilities:
                    required_capabilities.append(cap)
                    added_from_plan.append(cap)
            if added_from_plan:
                selection_sources.append("plan")
                logger.debug(f"📋 Plan 补充能力: {added_from_plan}")
            elif required_capabilities:
                # 有 Schema 配置时，Plan 被覆盖
                overridden_sources.append(f"plan({len(plan_capabilities)})")
        
        # 3. Intent 推断（兜底，仅当前面都为空时使用）
        if not required_capabilities and intent_task_type:
            intent_capabilities = self.registry.get_capabilities_for_task_type(intent_task_type)
            if intent_capabilities:
                required_capabilities = intent_capabilities
                selection_sources.append("intent")
        elif intent_task_type and required_capabilities:
            # 有其他配置时，Intent 被覆盖
            intent_caps = self.registry.get_capabilities_for_task_type(intent_task_type)
            if intent_caps:
                overridden_sources.append(f"intent({len(intent_caps)})")
        
        # 确定最终来源标识
        selection_source = "+".join(selection_sources) if selection_sources else "intent"
        
        if len(selection_sources) > 1:
            logger.info(f"📋 工具选择合并策略: {selection_source}, 能力: {required_capabilities[:5]}")
        
        return required_capabilities, selection_source, overridden_sources

    def get_available_apis(self, executor=None) -> List[str]:
        """
        自动发现可用的 API（从已加载的工具推断）
        
        Args:
            executor: ToolExecutor 实例
            
        Returns:
            可用 API 名称列表
        """
        available_apis = set()
        
        if executor is None:
            return list(available_apis)
        
        # 从 ToolExecutor 获取已加载的工具
        loaded_tools = getattr(executor, '_tool_instances', {})
        
        for tool_name, tool_instance in loaded_tools.items():
            if tool_instance is None:
                continue
            
            # 从 Registry 获取工具的约束配置
            capability = self.registry.get(tool_name)
            if capability and capability.constraints:
                api_name = capability.constraints.get('api_name')
                if api_name:
                    available_apis.add(api_name)
        
        logger.debug(f"🔍 自动发现可用 API: {list(available_apis)}")
        return list(available_apis)


def create_tool_selector(
    registry: CapabilityRegistry = None
) -> ToolSelector:
    """
    创建工具选择器
    
    Args:
        registry: CapabilityRegistry 实例
        
    Returns:
        ToolSelector 实例
    """
    return ToolSelector(registry=registry)

