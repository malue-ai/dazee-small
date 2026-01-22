"""
智能调用方式选择器 (Invocation Strategy Selector)

根据工具特性和任务类型，智能选择最合适的调用方式：
1. Direct Tool Call - 单工具+简单参数
2. Code Execution - 配置生成/计算逻辑
3. Programmatic Tool Calling - 多工具编排+循环
4. Fine-grained Streaming - 大参数(>10KB)
5. Tool Search - 工具数量>30时动态发现

🆕 V4.4 更新：
- 添加 Skill 跳过逻辑：如果 Plan 阶段匹配到 Skill，则跳过 InvocationSelector
- 仅在无匹配 Skill 时激活，选择 DIRECT/PROGRAMMATIC/TOOL_SEARCH

参考：
- https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview
- https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool
- https://www.anthropic.com/engineering/advanced-tool-use
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum


class InvocationType(Enum):
    """调用方式类型"""
    DIRECT = "direct"                       # 标准工具调用
    CODE_EXECUTION = "code_execution"       # 代码执行
    PROGRAMMATIC = "programmatic"           # 程序化工具调用
    STREAMING = "streaming"                 # 细粒度流式
    TOOL_SEARCH = "tool_search"             # 工具搜索（元调用）


@dataclass
class InvocationStrategy:
    """调用策略"""
    type: InvocationType
    reason: str
    config: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "reason": self.reason,
            "config": self.config or {}
        }


@dataclass
class ToolCharacteristics:
    """工具特性"""
    name: str
    is_server_tool: bool = False        # 是否是 Claude Server 工具
    has_large_input: bool = False       # 是否有大参数 (>10KB)
    requires_computation: bool = False   # 是否需要计算逻辑
    supports_batch: bool = False        # 是否支持批量操作
    is_stateful: bool = False           # 是否有状态
    estimated_input_size: int = 0       # 预估输入大小（bytes）


class InvocationSelector:
    """
    智能调用方式选择器
    
    根据任务类型、工具特性、参数大小等因素，
    选择最合适的调用方式。
    """
    
    # Claude Server 内置工具（无需客户端实现）
    # 🆕 仅保留 code_execution 用于 Skills 功能
    # web_search/web_fetch/memory 已移除，改用客户端工具
    SERVER_TOOLS = {
        "code_execution"
    }
    
    # 大参数阈值 (10KB)
    LARGE_INPUT_THRESHOLD = 10 * 1024
    
    # 工具数量阈值（超过则启用 Tool Search）
    TOOL_SEARCH_THRESHOLD = 30
    
    def __init__(
        self,
        enable_tool_search: bool = False,
        enable_code_execution: bool = True,
        enable_programmatic: bool = True,
        enable_streaming: bool = True
    ):
        """
        初始化选择器
        
        Args:
            enable_tool_search: 是否启用 Tool Search（需要 beta header）
            enable_code_execution: 是否启用 Code Execution
            enable_programmatic: 是否启用 Programmatic Tool Calling
            enable_streaming: 是否启用 Fine-grained Streaming
        """
        self.enable_tool_search = enable_tool_search
        self.enable_code_execution = enable_code_execution
        self.enable_programmatic = enable_programmatic
        self.enable_streaming = enable_streaming
        
        # 工具特性缓存
        self._tool_characteristics: Dict[str, ToolCharacteristics] = {}
    
    def register_tool_characteristics(
        self,
        name: str,
        is_server_tool: bool = False,
        has_large_input: bool = False,
        requires_computation: bool = False,
        supports_batch: bool = False,
        is_stateful: bool = False
    ):
        """
        注册工具特性
        
        在 capabilities.yaml 加载时调用，记录每个工具的特性。
        """
        self._tool_characteristics[name] = ToolCharacteristics(
            name=name,
            is_server_tool=is_server_tool or name in self.SERVER_TOOLS,
            has_large_input=has_large_input,
            requires_computation=requires_computation,
            supports_batch=supports_batch,
            is_stateful=is_stateful
        )
    
    def select_strategy(
        self,
        task_type: str,
        selected_tools: List[str],
        estimated_input_size: int = 0,
        total_available_tools: int = 0,
        context: Optional[Dict[str, Any]] = None,
        plan_result: Optional[Dict[str, Any]] = None
    ) -> Optional[InvocationStrategy]:
        """
        选择最合适的调用策略
        
        🆕 V4.4 更新：
        - 如果 Plan 匹配到 Skill，返回 None（跳过 InvocationSelector）
        - 由 Skill 路径处理（container.skills）
        
        Args:
            task_type: 任务类型 (simple, config_generation, multi_tool, batch_processing)
            selected_tools: 选中的工具列表
            estimated_input_size: 预估输入参数大小（bytes）
            total_available_tools: 总可用工具数
            context: 额外上下文
            plan_result: 🆕 Plan 阶段结果（用于检查是否匹配 Skill）
            
        Returns:
            InvocationStrategy: 推荐的调用策略
            None: 🆕 如果匹配到 Skill，返回 None 表示跳过
        """
        context = context or {}
        
        # ============ 🆕 V4.4: Skill 跳过逻辑 ============
        # 如果 Plan 匹配到 Skill，使用 Skill 路径，跳过 InvocationSelector
        if plan_result and plan_result.get("recommended_skill"):
            return None  # 由 Skill 机制处理（container.skills）
        
        # ============ 规则1: Tool Search ============
        # 如果工具数量超过阈值，先使用 Tool Search 发现工具
        if (self.enable_tool_search and 
            total_available_tools > self.TOOL_SEARCH_THRESHOLD and
            not selected_tools):
            return InvocationStrategy(
                type=InvocationType.TOOL_SEARCH,
                reason=f"工具数量({total_available_tools})超过阈值({self.TOOL_SEARCH_THRESHOLD})，使用Tool Search动态发现",
                config={
                    "search_type": "bm25",
                    "defer_loading": True
                }
            )
        
        # ============ 规则2: Fine-grained Streaming ============
        # 大参数输入，使用流式传输
        if (self.enable_streaming and 
            estimated_input_size > self.LARGE_INPUT_THRESHOLD):
            return InvocationStrategy(
                type=InvocationType.STREAMING,
                reason=f"输入参数大小({estimated_input_size}bytes)超过阈值，使用Fine-grained Streaming",
                config={
                    "stream_input": True,
                    "chunk_size": 4096
                }
            )
        
        # ============ 规则3: 根据任务类型选择 ============
        
        # 3a. 配置生成任务 → Code Execution
        if task_type == "config_generation" and self.enable_code_execution:
            return InvocationStrategy(
                type=InvocationType.CODE_EXECUTION,
                reason="配置生成任务，使用Code Execution确保结构正确性",
                config={
                    "language": "python",
                    "validate_output": True
                }
            )
        
        # 3b. 多工具编排 → Programmatic Tool Calling
        if (len(selected_tools) > 2 and 
            self.enable_programmatic and
            task_type in ["multi_tool", "batch_processing", "orchestration"]):
            return InvocationStrategy(
                type=InvocationType.PROGRAMMATIC,
                reason=f"多工具编排({len(selected_tools)}个工具)，使用Programmatic Tool Calling减少往返",
                config={
                    "tools": selected_tools,
                    "container": "code_execution"
                }
            )
        
        # 3c. 批量处理 → Programmatic Tool Calling
        if task_type == "batch_processing" and self.enable_programmatic:
            return InvocationStrategy(
                type=InvocationType.PROGRAMMATIC,
                reason="批量处理任务，使用Programmatic Tool Calling提高效率",
                config={
                    "batch_mode": True
                }
            )
        
        # 3d. 计算密集型 → Code Execution
        tool_chars = [
            self._tool_characteristics.get(t)
            for t in selected_tools
            if t in self._tool_characteristics
        ]
        if any(tc and tc.requires_computation for tc in tool_chars):
            return InvocationStrategy(
                type=InvocationType.CODE_EXECUTION,
                reason="工具需要计算逻辑，使用Code Execution",
                config={}
            )
        
        # ============ 规则4: 默认 Direct Tool Call ============
        return InvocationStrategy(
            type=InvocationType.DIRECT,
            reason="标准工具调用场景，使用Direct Tool Call",
            config={}
        )
    
    def get_tools_config(
        self,
        all_tools: List[Dict[str, Any]],
        strategy: InvocationStrategy
    ) -> Dict[str, Any]:
        """
        根据策略配置工具列表
        
        Args:
            all_tools: 所有工具定义
            strategy: 选择的策略
            
        Returns:
            配置好的工具配置
        """
        if strategy.type == InvocationType.TOOL_SEARCH:
            return self._configure_tool_search(all_tools)
        
        elif strategy.type == InvocationType.STREAMING:
            return {
                "tools": all_tools,
                "stream": True,
                "stream_options": {
                    "include_usage": True
                }
            }
        
        elif strategy.type == InvocationType.CODE_EXECUTION:
            code_exec_tool = {
                "type": "code_execution",
                "name": "code_execution"
            }
            return {
                "tools": [code_exec_tool] + all_tools,
                "betas": ["code-execution-2025-05-22"]
            }
        
        elif strategy.type == InvocationType.PROGRAMMATIC:
            return {
                "tools": all_tools,
                "programmatic_mode": True,
                "betas": ["code-execution-2025-05-22"]
            }
        
        else:
            return {"tools": all_tools}
    
    def _configure_tool_search(
        self,
        all_tools: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        配置 Tool Search 模式
        
        核心思路：
        1. 常用工具不延迟加载（立即可用）
        2. 其他工具设置 defer_loading: true
        3. 添加 tool_search_tool
        """
        # 常用工具（不延迟加载）
        frequent_tools = {"bash", "web_search", "plan_todo", "str_replace_based_edit_tool"}
        
        configured_tools = []
        
        # 1. 添加 Tool Search Tool
        configured_tools.append({
            "type": "tool_search_tool_bm25_20251119",
            "name": "tool_search_tool"
        })
        
        # 2. 配置其他工具
        for tool in all_tools:
            tool_name = tool.get("name", "")
            
            if tool_name in frequent_tools:
                configured_tools.append(tool)
            else:
                tool_copy = tool.copy()
                tool_copy["defer_loading"] = True
                configured_tools.append(tool_copy)
        
        return {
            "tools": configured_tools,
            "betas": ["advanced-tool-use-2025-11-20"]
        }


# ============================================================
# 工厂函数
# ============================================================

def create_invocation_selector(
    enable_tool_search: bool = False,
    **kwargs
) -> InvocationSelector:
    """
    创建调用方式选择器
    
    🆕 V4.4 更新：
    - InvocationSelector 仅在无匹配 Skill 时生效
    - 如果 Plan 阶段匹配到 Skill，select_strategy 返回 None
    - 调用方应检查返回值，None 表示使用 Skill 路径
    
    Args:
        enable_tool_search: 是否启用 Tool Search
        **kwargs: 其他参数
        
    Returns:
        InvocationSelector 实例
        
    使用示例:
        selector = create_invocation_selector()
        strategy = selector.select_strategy(
            task_type="multi_tool",
            selected_tools=["exa_search", "ppt_generator"],
            plan_result=plan  # 🆕 传入 Plan 结果
        )
        
        if strategy is None:
            # Skill 路径：使用 container.skills
            pass
        else:
            # Tool 路径：使用 InvocationStrategy
            tools_config = selector.get_tools_config(tools, strategy)
    """
    return InvocationSelector(
        enable_tool_search=enable_tool_search,
        **kwargs
    )

