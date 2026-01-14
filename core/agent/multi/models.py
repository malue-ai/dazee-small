"""
多智能体框架数据模型

定义多智能体协作所需的数据结构。
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ExecutionMode(str, Enum):
    """执行模式"""
    SEQUENTIAL = "sequential"       # 串行执行
    PARALLEL = "parallel"           # 并行执行
    HIERARCHICAL = "hierarchical"   # 层级执行（主/子 Agent）


class AgentRole(str, Enum):
    """智能体角色"""
    PLANNER = "planner"         # 规划者：分解任务、制定计划
    RESEARCHER = "researcher"   # 研究者：信息收集、知识检索
    EXECUTOR = "executor"       # 执行者：执行具体任务
    REVIEWER = "reviewer"       # 审核者：验证结果、质量检查
    SUMMARIZER = "summarizer"   # 汇总者：整合结果、生成摘要
    CUSTOM = "custom"           # 自定义角色


class AgentConfig(BaseModel):
    """单个智能体配置"""
    agent_id: str = Field(..., description="智能体唯一标识")
    role: AgentRole = Field(AgentRole.EXECUTOR, description="智能体角色")
    model: str = Field("claude-sonnet-4-5-20250929", description="使用的模型")
    
    # 系统提示词
    system_prompt: Optional[str] = Field(None, description="自定义系统提示词")
    role_prompt: Optional[str] = Field(None, description="角色专用提示词")
    
    # 能力配置
    tools: List[str] = Field(default_factory=list, description="可用工具列表")
    max_turns: int = Field(10, description="最大对话轮次")
    
    # 执行参数
    timeout_seconds: int = Field(60, description="执行超时")
    priority: int = Field(0, description="执行优先级（越大越优先）")
    
    # 依赖关系（用于串行/层级模式）
    depends_on: List[str] = Field(default_factory=list, description="依赖的其他 Agent")
    
    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MultiAgentConfig(BaseModel):
    """多智能体编排配置"""
    config_id: str = Field(..., description="配置唯一标识")
    name: str = Field("", description="配置名称")
    description: str = Field("", description="配置描述")
    
    # 执行模式
    mode: ExecutionMode = Field(ExecutionMode.SEQUENTIAL, description="执行模式")
    
    # 智能体配置
    agents: List[AgentConfig] = Field(default_factory=list, description="智能体列表")
    
    # 全局参数
    max_total_turns: int = Field(30, description="所有 Agent 总共最大轮次")
    timeout_seconds: int = Field(300, description="总超时时间")
    
    # 结果汇总配置
    enable_final_summary: bool = Field(True, description="是否生成最终汇总")
    summary_agent: Optional[str] = Field(None, description="负责汇总的 Agent ID")
    
    # 错误处理
    fail_fast: bool = Field(False, description="遇到错误立即停止")
    retry_on_failure: bool = Field(True, description="失败时重试")
    max_retries: int = Field(2, description="最大重试次数")
    
    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)


class TaskAssignment(BaseModel):
    """任务分配"""
    task_id: str = Field(..., description="任务唯一标识")
    agent_id: str = Field(..., description="分配给的 Agent")
    
    # 任务内容
    task_type: str = Field("execute", description="任务类型")
    instruction: str = Field("", description="任务指令")
    input_data: Dict[str, Any] = Field(default_factory=dict, description="输入数据")
    
    # 来源（串行模式中前一个 Agent 的输出）
    source_agent: Optional[str] = Field(None, description="来源 Agent")
    source_output: Optional[str] = Field(None, description="来源输出")
    
    # 状态
    status: str = Field("pending", description="任务状态")
    created_at: datetime = Field(default_factory=datetime.now)


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


class OrchestratorState(BaseModel):
    """编排器状态"""
    state_id: str = Field(..., description="状态唯一标识")
    session_id: str = Field(..., description="会话 ID")
    
    # 配置
    config_id: str = Field(..., description="使用的配置 ID")
    mode: ExecutionMode = Field(ExecutionMode.SEQUENTIAL)
    
    # 执行状态
    status: str = Field("initialized", description="编排状态")
    current_agent: Optional[str] = Field(None, description="当前执行的 Agent")
    completed_agents: List[str] = Field(default_factory=list, description="已完成的 Agent")
    pending_agents: List[str] = Field(default_factory=list, description="待执行的 Agent")
    
    # 任务状态
    task_assignments: List[TaskAssignment] = Field(default_factory=list)
    
    # 结果收集
    agent_results: List[AgentResult] = Field(default_factory=list)
    final_output: Optional[str] = Field(None, description="最终输出")
    
    # 统计
    total_turns: int = Field(0, description="总轮次")
    total_duration_ms: int = Field(0, description="总耗时")
    
    # 错误
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    
    # 时间戳
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
