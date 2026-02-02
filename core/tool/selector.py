"""
ToolSelector - 工具选择器

职责：
1. 根据意图和能力需求选择合适的工具
2. 管理基础工具和动态工具的选择
3. 提供工具 Schema 转换（用于 LLM API）

设计原则：
- 单一职责：只做工具选择
- 配置驱动：工具配置从 capabilities.yaml 加载
"""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional

from logger import get_logger
from core.tool.capability import (
    CapabilityRegistry,
    CapabilityType,
    create_capability_registry
)
from core.tool.registry_config import get_core_tools

logger = get_logger(__name__)


@dataclass
class ToolSelectionResult:
    """
    工具选择结果
    
    包含选中的工具列表和选择原因
    """
    tools: List[Any]           # 选中的工具列表（Capability 对象）
    tool_names: List[str]      # 工具名称列表
    base_tools: List[str]      # 基础工具名称
    dynamic_tools: List[str]   # 动态选择的工具名称
    reason: str = ""           # 选择原因
    
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
    
    根据任务需求智能选择合适的工具。
    
    工具分层设计：
    - Level 1（核心工具）：始终加载，如 plan_todo
    - Level 2（动态工具）：按需加载，如 exa_search, sandbox_run_command
    
    使用方式：
        selector = ToolSelector(registry)
        result = selector.select(
            required_capabilities=["web_search", "ppt_generation"],
            context={"task_type": "content_generation"}
        )
        print(result.tool_names)
    """
    
    def __init__(self, registry: Optional[CapabilityRegistry] = None):
        """
        初始化工具选择器
        
        Args:
            registry: CapabilityRegistry 实例
        """
        self.registry = registry or create_capability_registry()
        self._core_tools_cache: Optional[List[str]] = None
    
    def get_core_tools(self) -> List[str]:
        """
        获取核心工具名称列表（Level 1）
        
        核心工具始终加载，不受动态选择影响。
        优先从 capabilities.yaml 读取 level=1 的工具，
        如果没有则使用配置文件中的默认列表。
        
        Returns:
            核心工具名称列表
        """
        if self._core_tools_cache is not None:
            return self._core_tools_cache
        
        # 从 Registry 获取 Level 1 工具
        core_caps = self.registry.get_core_tools()
        
        if core_caps:
            self._core_tools_cache = [c.name for c in core_caps]
        else:
            # 备用：从配置文件读取
            self._core_tools_cache = get_core_tools()
        
        logger.debug(f"核心工具 (Level 1): {self._core_tools_cache}")
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
    ) -> ToolSelectionResult:
        """
        选择工具
        
        分层选择逻辑：
        1. 始终加载 Level 1 核心工具（plan_todo 等）
        2. 根据能力需求从 Level 2 动态工具中选择
        
        Args:
            required_capabilities: 所需能力列表（如 ["web_search", "ppt_generation"]）
            context: 上下文信息（包含 task_type, available_apis 等）
            
        Returns:
            ToolSelectionResult 选择结果
        """
        context = context or {}
        selected = []
        selected_skills_capabilities = set()
        
        # 1. 添加核心工具（Level 1）- 始终加载
        base_tools = []
        core_tool_names = self.get_core_tools()
        for name in core_tool_names:
            cap = self.registry.get(name)
            if cap and cap not in selected:
                selected.append(cap)
                base_tools.append(name)
        
        # 2. 根据能力标签选择工具
        dynamic_tools = []
        fallback_tools_to_add = []
        
        for capability_tag in required_capabilities:
            matched = self.registry.find_by_capability_tag(capability_tag)
            
            if not matched:
                logger.warning(f"未找到匹配能力的工具: {capability_tag}")
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
                        
                        # 如果 SKILL 有 fallback_tool，添加到待处理列表
                        if tool.fallback_tool:
                            fallback_tools_to_add.append(tool.fallback_tool)
                            logger.debug(f"SKILL '{tool.name}' 指定 fallback_tool: {tool.fallback_tool}")
        
        # 3. 优先添加 fallback 工具
        for fallback_name in fallback_tools_to_add:
            fallback_cap = self.registry.get(fallback_name)
            if fallback_cap and fallback_cap not in selected:
                if fallback_cap.meets_constraints(context):
                    selected.append(fallback_cap)
                    dynamic_tools.append(fallback_name)
                    logger.info(f"添加 fallback 工具: {fallback_name}")
        
        # 4. 自动包含 Skills 依赖的底层工具
        for skill_capability in selected_skills_capabilities:
            tools_for_capability = [
                c for c in self.registry.find_by_capability_tag(skill_capability)
                if c.type == CapabilityType.TOOL
            ]
            
            for tool in tools_for_capability:
                if tool not in selected and tool.meets_constraints(context):
                    selected.append(tool)
                    dynamic_tools.append(tool.name)
                    logger.debug(f"自动包含工具 {tool.name} (Skills 依赖)")
        
        # 5. 按优先级排序
        selected.sort(key=lambda c: c.priority, reverse=True)
        
        # 6. 提取工具名称
        tool_names = [t.name for t in selected]
        
        logger.info(
            f"工具选择完成: 基础={len(base_tools)}, "
            f"动态={len(dynamic_tools)}, 总计={len(tool_names)}"
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
            capability = self.registry.get(tool_name)
            if not capability:
                continue
            
            # 只有 TOOL 类型且有 input_schema 的才能作为 LLM API 工具
            if capability.type != CapabilityType.TOOL:
                continue
            
            if not capability.input_schema:
                continue
            
            # 转换为 LLM API 格式
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
        
        logger.debug(f"自动发现可用 API: {list(available_apis)}")
        return list(available_apis)


def create_tool_selector(
    registry: Optional[CapabilityRegistry] = None
) -> ToolSelector:
    """
    创建工具选择器
    
    Args:
        registry: CapabilityRegistry 实例
        
    Returns:
        ToolSelector 实例
    """
    return ToolSelector(registry=registry)
