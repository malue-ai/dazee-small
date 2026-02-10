"""
单智能体框架数据模型

V11.0: 简化架构，仅支持 RVR-B 执行策略，移除所有多智能体功能。

定义单智能体执行所需的数据结构。
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AgentRole(str, Enum):
    """智能体角色"""

    PLANNER = "planner"  # 规划者：分解任务、制定计划
    RESEARCHER = "researcher"  # 研究者：信息收集、知识检索
    EXECUTOR = "executor"  # 执行者：执行具体任务
    REVIEWER = "reviewer"  # 审核者：验证结果、质量检查
    SUMMARIZER = "summarizer"  # 汇总者：整合结果、生成摘要
    CUSTOM = "custom"  # 自定义角色


class AgentConfig(BaseModel):
    """
    单个智能体配置

    V7.7 更新：移除 depends_on 字段，依赖关系统一由 PlanStep.dependencies 管理
    """

    agent_id: str = Field(..., description="智能体唯一标识")
    role: AgentRole = Field(AgentRole.EXECUTOR, description="智能体角色")
    model: str = Field("", description="使用的模型（必须由 config.yaml 显式配置）")

    # 系统提示词
    system_prompt: Optional[str] = Field(None, description="自定义系统提示词")
    role_prompt: Optional[str] = Field(None, description="角色专用提示词")

    # 能力配置
    tools: List[str] = Field(default_factory=list, description="可用工具列表")

    # 执行参数
    timeout_seconds: int = Field(60, description="执行超时")
    priority: int = Field(0, description="执行优先级（越大越优先）")

    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentResult(BaseModel):
    """智能体执行结果"""

    result_id: str = Field(..., description="结果唯一标识")
    agent_id: str = Field(..., description="执行的 Agent")
    task_id: Optional[str] = Field(None, description="关联的任务 ID")

    # 执行结果
    success: bool = Field(True, description="是否成功")
    output: str = Field("", description="输出内容")
    error: Optional[str] = Field(None, description="错误信息")

    # 统计信息
    turns_used: int = Field(0, description="使用的轮次")
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list, description="工具调用记录")
    token_usage: Dict[str, int] = Field(default_factory=dict, description="Token 使用")
    duration_ms: int = Field(0, description="执行耗时")

    # 时间戳
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentSelectionResult(BaseModel):
    """
    Agent 选择结果

    V7.9 新增：工具选择三级优化（V7.6）

    封装 Agent 选择的完整决策过程，包括：
    - 三层候选记录（Config/Task/Capability）
    - 最终选择和来源
    - 覆盖关系记录
    - 有效性验证结果
    """

    # 最终选择
    selected_agent: AgentConfig = Field(..., description="选中的 Agent 配置")
    selection_source: str = Field(
        ..., description="选择来源: config/task/capability/default/auto_created"
    )

    # 覆盖记录（透明化）
    overridden_sources: List[str] = Field(
        default_factory=list, description="被覆盖的候选来源，格式: 'layer:agent_id'"
    )

    # 有效性验证
    validation_passed: bool = Field(True, description="验证是否通过")
    validation_issues: List[str] = Field(default_factory=list, description="验证问题列表")

    # 三层候选记录（用于 Tracer 追踪）
    config_candidate: Optional[str] = Field(None, description="Config 层候选 Agent ID")
    task_candidate: Optional[str] = Field(None, description="Task 层候选 Agent ID")
    capability_candidate: Optional[str] = Field(None, description="Capability 层候选 Agent ID")

    def to_trace_dict(self) -> Dict[str, Any]:
        """转换为 Tracer 记录格式"""
        return {
            "selected_agent": self.selected_agent.agent_id,
            "selection_source": self.selection_source,
            "overridden_sources": self.overridden_sources,
            "validation_passed": self.validation_passed,
            "validation_issues": self.validation_issues,
            "config_candidate": self.config_candidate,
            "task_candidate": self.task_candidate,
            "capability_candidate": self.capability_candidate,
        }
