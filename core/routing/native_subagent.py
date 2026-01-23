"""
原生 Subagent 集成模块

V8.0 新增

职责：
- 利用 Claude 4.5 的原生 Subagent 能力
- 简化中等复杂度场景的实现
- Subagent as Tool 模式

设计原则：
- 中等复杂度（4-7）使用原生 Subagent
- 利用模型原生的任务委托能力
- 减少框架层编排开销

复杂度分流：
- 简单（0-4）: SimpleAgent RVR-B
- 中等（4-7）: 原生 Subagent（本模块）
- 复杂（7-10）: MultiAgentOrchestrator
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Awaitable

from logger import get_logger

logger = get_logger(__name__)


class SubagentType(Enum):
    """Subagent 类型"""
    RESEARCH = "research"           # 研究型
    CODING = "coding"               # 编码型
    ANALYSIS = "analysis"           # 分析型
    WRITING = "writing"             # 写作型
    GENERAL = "general"             # 通用型


@dataclass
class SubagentSpec:
    """Subagent 规格定义"""
    name: str
    type: SubagentType
    description: str
    capabilities: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    system_prompt: Optional[str] = None
    max_tokens: int = 4096
    
    def to_tool_spec(self) -> Dict[str, Any]:
        """转换为工具规格（用于 LLM 工具调用）"""
        return {
            "name": f"delegate_to_{self.name}",
            "description": f"将任务委托给 {self.name} 子智能体。{self.description}",
            "input_schema": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "要委托的具体任务"
                    },
                    "context": {
                        "type": "string",
                        "description": "任务相关的上下文信息"
                    },
                    "expected_output": {
                        "type": "string",
                        "description": "期望的输出格式或内容"
                    }
                },
                "required": ["task"]
            }
        }


@dataclass
class SubagentResult:
    """Subagent 执行结果"""
    subagent_name: str
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    tokens_used: int = 0
    latency_ms: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "subagent_name": self.subagent_name,
            "success": self.success,
            "output": self.output[:500] + "..." if self.output and len(self.output) > 500 else self.output,
            "error": self.error,
            "tokens_used": self.tokens_used,
            "latency_ms": self.latency_ms,
        }


# 预定义的 Subagent 规格
DEFAULT_SUBAGENTS: Dict[str, SubagentSpec] = {
    "researcher": SubagentSpec(
        name="researcher",
        type=SubagentType.RESEARCH,
        description="专门负责信息收集和研究任务，擅长搜索、总结和分析信息。",
        capabilities=["web_search", "information_synthesis", "fact_checking"],
        tools=["web_search", "exa_search", "knowledge_search"],
    ),
    "coder": SubagentSpec(
        name="coder",
        type=SubagentType.CODING,
        description="专门负责编写和修改代码，擅长编程和代码分析。",
        capabilities=["code_writing", "code_review", "debugging"],
        tools=["bash", "text_editor", "sandbox_execute"],
    ),
    "analyst": SubagentSpec(
        name="analyst",
        type=SubagentType.ANALYSIS,
        description="专门负责数据分析和报告生成，擅长处理结构化数据。",
        capabilities=["data_analysis", "visualization", "report_generation"],
        tools=["sandbox_execute", "ppt_generator"],
    ),
    "writer": SubagentSpec(
        name="writer",
        type=SubagentType.WRITING,
        description="专门负责文档写作和内容创作，擅长各类文本生成。",
        capabilities=["content_writing", "summarization", "editing"],
        tools=["document_creation"],
    ),
}


class NativeSubagentOrchestrator:
    """
    原生 Subagent 编排器
    
    功能：
    1. 管理 Subagent 规格
    2. 将 Subagent 注册为工具
    3. 处理 Subagent 调用
    4. 协调主智能体和 Subagent 的交互
    
    使用方式：
        orchestrator = NativeSubagentOrchestrator(llm_service=claude)
        
        # 获取 Subagent 工具列表
        tools = orchestrator.get_subagent_tools()
        
        # 处理 Subagent 调用
        result = await orchestrator.execute_subagent(
            subagent_name="researcher",
            task="搜索最新的 AI 研究进展",
            context="用户需要了解 2026 年的 AI 趋势"
        )
    """
    
    def __init__(
        self,
        llm_service: Any = None,
        subagents: Optional[Dict[str, SubagentSpec]] = None,
        complexity_range: tuple = (4, 7),  # 适用的复杂度范围
    ):
        """
        初始化 Subagent 编排器
        
        Args:
            llm_service: LLM 服务
            subagents: 自定义 Subagent 规格
            complexity_range: 适用的复杂度范围
        """
        self.llm_service = llm_service
        self.subagents = subagents or DEFAULT_SUBAGENTS.copy()
        self.complexity_range = complexity_range
        
        # 执行历史
        self._execution_history: List[SubagentResult] = []
        
        logger.info(
            f"✅ NativeSubagentOrchestrator 初始化: "
            f"subagents={list(self.subagents.keys())}, "
            f"complexity_range={complexity_range}"
        )
    
    def should_use_native_subagent(
        self,
        complexity_score: float,
        task_type: Optional[str] = None,
    ) -> bool:
        """
        判断是否应该使用原生 Subagent
        
        Args:
            complexity_score: 复杂度评分
            task_type: 任务类型
            
        Returns:
            是否使用原生 Subagent
        """
        min_complexity, max_complexity = self.complexity_range
        return min_complexity <= complexity_score <= max_complexity
    
    def get_subagent_tools(self) -> List[Dict[str, Any]]:
        """
        获取所有 Subagent 工具规格
        
        Returns:
            工具规格列表
        """
        return [spec.to_tool_spec() for spec in self.subagents.values()]
    
    def get_subagent_by_type(
        self,
        subagent_type: SubagentType
    ) -> Optional[SubagentSpec]:
        """
        根据类型获取 Subagent
        
        Args:
            subagent_type: Subagent 类型
            
        Returns:
            SubagentSpec 或 None
        """
        for spec in self.subagents.values():
            if spec.type == subagent_type:
                return spec
        return None
    
    def select_subagent_for_task(
        self,
        task_description: str,
        required_capabilities: Optional[List[str]] = None,
    ) -> Optional[SubagentSpec]:
        """
        为任务选择合适的 Subagent
        
        Args:
            task_description: 任务描述
            required_capabilities: 所需能力
            
        Returns:
            最合适的 SubagentSpec 或 None
        """
        task_lower = task_description.lower()
        required_capabilities = required_capabilities or []
        
        # 关键词匹配
        type_keywords = {
            SubagentType.RESEARCH: ["搜索", "查找", "研究", "调研", "search", "research"],
            SubagentType.CODING: ["代码", "编程", "程序", "脚本", "code", "coding", "script"],
            SubagentType.ANALYSIS: ["分析", "数据", "报告", "图表", "analysis", "data", "report"],
            SubagentType.WRITING: ["写作", "文档", "内容", "文章", "write", "document", "content"],
        }
        
        best_match: Optional[SubagentSpec] = None
        best_score = 0
        
        for subagent_type, keywords in type_keywords.items():
            score = sum(1 for kw in keywords if kw in task_lower)
            if score > best_score:
                best_score = score
                best_match = self.get_subagent_by_type(subagent_type)
        
        # 如果有 required_capabilities，进一步筛选
        if required_capabilities and best_match:
            cap_overlap = set(best_match.capabilities) & set(required_capabilities)
            if not cap_overlap:
                # 尝试找更匹配的
                for spec in self.subagents.values():
                    overlap = set(spec.capabilities) & set(required_capabilities)
                    if len(overlap) > len(set(best_match.capabilities) & set(required_capabilities)):
                        best_match = spec
        
        # 默认使用 general 类型
        if not best_match:
            best_match = self.subagents.get("researcher")  # 默认使用 researcher
        
        return best_match
    
    async def execute_subagent(
        self,
        subagent_name: str,
        task: str,
        context: Optional[str] = None,
        expected_output: Optional[str] = None,
        tool_executor: Optional[Callable[..., Awaitable[Any]]] = None,
    ) -> SubagentResult:
        """
        执行 Subagent 任务
        
        Args:
            subagent_name: Subagent 名称
            task: 任务描述
            context: 上下文信息
            expected_output: 期望输出
            tool_executor: 工具执行器（用于 Subagent 调用工具）
            
        Returns:
            SubagentResult: 执行结果
        """
        import time
        start_time = time.time()
        
        # 获取 Subagent 规格
        spec = self.subagents.get(subagent_name)
        if not spec:
            return SubagentResult(
                subagent_name=subagent_name,
                success=False,
                error=f"Subagent '{subagent_name}' not found",
            )
        
        logger.info(f"🤖 执行 Subagent [{subagent_name}]: {task[:50]}...")
        
        if not self.llm_service:
            return SubagentResult(
                subagent_name=subagent_name,
                success=False,
                error="LLM service not available",
            )
        
        try:
            # 构建 Subagent 系统提示词
            system_prompt = self._build_subagent_system_prompt(spec, expected_output)
            
            # 构建用户消息
            user_message = self._build_subagent_user_message(task, context)
            
            # 调用 LLM
            response = await self.llm_service.create_message_async(
                messages=[{"role": "user", "content": user_message}],
                system=system_prompt,
                max_tokens=spec.max_tokens,
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            tokens_used = getattr(response, 'input_tokens', 0) + getattr(response, 'output_tokens', 0)
            
            result = SubagentResult(
                subagent_name=subagent_name,
                success=True,
                output=response.content,
                tokens_used=tokens_used,
                latency_ms=latency_ms,
            )
            
            logger.info(
                f"✅ Subagent [{subagent_name}] 完成: "
                f"tokens={tokens_used}, latency={latency_ms}ms"
            )
            
        except Exception as e:
            logger.error(f"❌ Subagent [{subagent_name}] 失败: {e}")
            result = SubagentResult(
                subagent_name=subagent_name,
                success=False,
                error=str(e),
                latency_ms=int((time.time() - start_time) * 1000),
            )
        
        # 记录执行历史
        self._execution_history.append(result)
        
        return result
    
    def _build_subagent_system_prompt(
        self,
        spec: SubagentSpec,
        expected_output: Optional[str] = None,
    ) -> str:
        """构建 Subagent 系统提示词"""
        parts = [
            f"你是 {spec.name}，{spec.description}",
            "",
            "## 你的能力",
        ]
        
        for cap in spec.capabilities:
            parts.append(f"- {cap}")
        
        if expected_output:
            parts.extend([
                "",
                "## 输出要求",
                expected_output,
            ])
        
        parts.extend([
            "",
            "## 工作原则",
            "- 专注于你的专业领域",
            "- 提供详细、准确的输出",
            "- 如果任务超出你的能力范围，明确说明",
        ])
        
        if spec.system_prompt:
            parts.extend([
                "",
                "## 额外指令",
                spec.system_prompt,
            ])
        
        return "\n".join(parts)
    
    def _build_subagent_user_message(
        self,
        task: str,
        context: Optional[str] = None,
    ) -> str:
        """构建 Subagent 用户消息"""
        parts = [f"## 任务\n{task}"]
        
        if context:
            parts.append(f"\n## 上下文\n{context}")
        
        return "\n".join(parts)
    
    def register_subagent(self, spec: SubagentSpec):
        """注册新的 Subagent"""
        self.subagents[spec.name] = spec
        logger.info(f"✅ 注册 Subagent: {spec.name}")
    
    def get_execution_history(self) -> List[SubagentResult]:
        """获取执行历史"""
        return self._execution_history.copy()
    
    def clear_execution_history(self):
        """清除执行历史"""
        self._execution_history.clear()


def create_native_subagent_orchestrator(
    llm_service: Any = None,
    subagents: Optional[Dict[str, SubagentSpec]] = None,
) -> NativeSubagentOrchestrator:
    """
    创建原生 Subagent 编排器
    
    Args:
        llm_service: LLM 服务
        subagents: 自定义 Subagent 规格
        
    Returns:
        NativeSubagentOrchestrator 实例
    """
    return NativeSubagentOrchestrator(
        llm_service=llm_service,
        subagents=subagents,
    )


# 复杂度分流函数
def get_agent_type_by_complexity(
    complexity_score: float,
    simple_threshold: float = 4.0,
    complex_threshold: float = 7.0,
) -> str:
    """
    根据复杂度分流到不同的智能体类型
    
    Args:
        complexity_score: 复杂度评分
        simple_threshold: 简单任务阈值
        complex_threshold: 复杂任务阈值
        
    Returns:
        智能体类型: "simple", "native_subagent", "multi"
    """
    if complexity_score < simple_threshold:
        return "simple"
    elif complexity_score <= complex_threshold:
        return "native_subagent"
    else:
        return "multi"
