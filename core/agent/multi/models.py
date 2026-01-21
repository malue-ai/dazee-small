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


class OrchestratorConfig(BaseModel):
    """
    Orchestrator（编排器）配置
    
    V7.1 新增：强弱配对策略
    - Orchestrator 使用强大的模型（Opus 4.5）进行任务分解和综合
    """
    model: str = Field("claude-opus-4-5-20251101", description="Orchestrator 使用的模型")
    enable_thinking: bool = Field(True, description="是否启用扩展思考")
    max_tokens: int = Field(16384, description="最大 token 数（必须大于 thinking_budget）")
    thinking_budget: int = Field(10000, description="Thinking token 预算（必须小于 max_tokens）")
    temperature: float = Field(0.3, description="温度参数")
    llm_profile_name: Optional[str] = Field(None, description="LLM Profile 名称（可选）")


class WorkerConfig(BaseModel):
    """
    Worker（工作者）配置
    
    V7.1 新增：强弱配对策略
    - Worker 使用轻量级模型（如 Sonnet）执行具体任务
    """
    model: str = Field("claude-sonnet-4-5-20250929", description="Worker 使用的模型")
    enable_thinking: bool = Field(True, description="是否启用扩展思考")
    max_tokens: int = Field(8192, description="最大 token 数（必须大于 thinking_budget）")
    thinking_budget: int = Field(5000, description="Thinking token 预算（必须小于 max_tokens）")
    temperature: float = Field(0.5, description="温度参数")
    llm_profile_name: Optional[str] = Field(None, description="LLM Profile 名称（可选）")


class MultiAgentConfig(BaseModel):
    """多智能体编排配置"""
    config_id: str = Field(..., description="配置唯一标识")
    name: str = Field("", description="配置名称")
    description: str = Field("", description="配置描述")
    
    # 执行模式
    mode: ExecutionMode = Field(ExecutionMode.SEQUENTIAL, description="执行模式")
    
    # 智能体配置
    agents: List[AgentConfig] = Field(default_factory=list, description="智能体列表")
    
    # V7.1: 强弱配对策略
    orchestrator_config: Optional[OrchestratorConfig] = Field(None, description="Orchestrator 配置")
    worker_config: Optional[WorkerConfig] = Field(None, description="Worker 配置")
    
    # V7.2: Critic 配置（使用字符串引用，因为 CriticConfig 在后面定义）
    critic_config: Optional["CriticConfig"] = Field(None, description="Critic Agent 配置")
    
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


class SubagentResult(BaseModel):
    """
    Subagent 执行结果（上下文隔离版本）
    
    V7.1 新增：参考 Anthropic Multi-Agent System
    - Subagent 在独立的上下文中执行
    - 只返回压缩的摘要给 Orchestrator
    - Orchestrator 不保留 Subagent 的完整历史
    """
    result_id: str = Field(..., description="结果唯一标识")
    agent_id: str = Field(..., description="执行的 Subagent")
    subtask_id: Optional[str] = Field(None, description="关联的子任务 ID")
    
    # 执行结果（压缩版本）
    success: bool = Field(True, description="是否成功")
    summary: str = Field("", description="结果摘要（< 500 tokens）")
    full_output: str = Field("", description="完整输出（仅用于存档/调试）")
    error: Optional[str] = Field(None, description="错误信息")
    
    # 统计信息
    turns_used: int = Field(0, description="使用的轮次")
    token_usage: Dict[str, int] = Field(default_factory=dict, description="Token 使用")
    duration_ms: int = Field(0, description="执行耗时")
    
    # 上下文隔离信息
    context_length: int = Field(0, description="Subagent 使用的上下文长度")
    summary_compression_ratio: float = Field(0.0, description="摘要压缩比")
    
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


class CriticAction(str, Enum):
    """
    Critic 推荐行动
    
    V7.2 新增：Critic Agent 的推荐行动类型
    注意：这是推荐，不是强制决策。最终由人或上层系统决定。
    """
    PASS = "pass"           # 继续下一步（结果满足需求）
    RETRY = "retry"         # 带建议重试（有明确改进方向）
    REPLAN = "replan"       # 调整计划（任务定义有问题）
    ASK_HUMAN = "ask_human" # 请求人工介入（无法判断或需要澄清）


class CriticConfidence(str, Enum):
    """
    Critic 对推荐的信心程度
    
    V7.2 新增：用于决定是否需要人工确认
    """
    HIGH = "high"           # 有充足依据，系统可自动执行
    MEDIUM = "medium"       # 有一定依据，建议人工确认
    LOW = "low"             # 缺乏判断依据，必须人工介入


# 向后兼容的别名
CriticVerdict = CriticAction


class PlanAdjustmentHint(BaseModel):
    """
    Plan 调整建议
    
    V7.2 新增：Critic 提供的计划调整建议
    """
    action: str = Field(..., description="调整动作：insert_before, modify, skip")
    reason: str = Field(..., description="调整原因")
    new_step: Optional[str] = Field(None, description="新步骤描述（如需要）")
    context_for_replan: Optional[str] = Field(None, description="传递给 plan_todo 的上下文")


class CriticResult(BaseModel):
    """
    Critic 评估结果（人机协同版本）
    
    V7.2 新增：Critic Agent 的评估输出
    
    设计原则：
    - Critic 是顾问，不是裁判
    - 提供观察和建议，不做硬编码评分
    - 最终决策由人或上层系统做出
    """
    # 观察与分析
    observations: List[str] = Field(default_factory=list, description="对结果的客观观察")
    gaps: List[str] = Field(default_factory=list, description="与预期的差距")
    root_cause: Optional[str] = Field(None, description="问题根因分析")
    
    # 建议
    suggestions: List[str] = Field(default_factory=list, description="具体的改进建议")
    
    # 推荐行动（注意：是推荐，不是决策）
    recommended_action: CriticAction = Field(..., description="推荐的下一步行动")
    reasoning: str = Field(..., description="推荐理由")
    confidence: CriticConfidence = Field(CriticConfidence.MEDIUM, description="对推荐的信心程度")
    
    # 计划调整（当 recommended_action=replan 时）
    plan_adjustment: Optional[PlanAdjustmentHint] = Field(None, description="计划调整建议")
    
    # 向后兼容
    @property
    def verdict(self) -> CriticAction:
        """向后兼容的 verdict 属性"""
        return self.recommended_action
    
    @property
    def improvement_hints(self) -> List[str]:
        """向后兼容的 improvement_hints 属性"""
        return self.suggestions


class CriticConfig(BaseModel):
    """
    Critic 配置
    
    V7.2 新增：Critic Agent 的配置选项
    """
    enabled: bool = Field(True, description="是否启用 Critic")
    model: str = Field("claude-sonnet-4-5-20250929", description="Critic 使用的模型")
    enable_thinking: bool = Field(True, description="是否启用扩展思考")
    max_retries: int = Field(2, description="最大重试次数")
    llm_profile_name: Optional[str] = Field(None, description="LLM Profile 名称（可选）")
    
    # 人机协同配置
    auto_pass_on_high_confidence: bool = Field(True, description="高信心时自动通过")
    require_human_on_low_confidence: bool = Field(True, description="低信心时必须人工介入")
    default_action_on_timeout: CriticAction = Field(CriticAction.ASK_HUMAN, description="超时时的默认行动")


# 解析前向引用（Pydantic V2 需要）
MultiAgentConfig.model_rebuild()


def load_multi_agent_config(config_path: str = "config/multi_agent_config.yaml") -> MultiAgentConfig:
    """
    ✅ V7.2: 加载多智能体配置
    
    从 YAML 文件加载配置，如果文件不存在则使用默认配置
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        MultiAgentConfig: 多智能体配置对象
    """
    import yaml
    from pathlib import Path
    from logger import get_logger
    
    logger = get_logger("multi_agent.config")
    
    config_file = Path(config_path)
    
    if config_file.exists():
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            
            logger.info(f"✅ 已加载多智能体配置: {config_path}")
            
            # 解析配置
            orchestrator_config = OrchestratorConfig(**config_data.get("orchestrator", {}))
            worker_config = WorkerConfig(**config_data.get("workers", {}))
            critic_config = CriticConfig(**config_data.get("critic", {})) if "critic" in config_data else None
            
            # 构建 Agent 配置列表（从 YAML 中的 agents 节点）
            agents_data = config_data.get("agents", [])
            agent_configs = [AgentConfig(**agent) for agent in agents_data]
            
            # 如果没有配置 agents，使用默认的 3 个研究者
            if not agent_configs:
                agent_configs = [
                    AgentConfig(
                        agent_id="researcher_1",
                        role=AgentRole.RESEARCHER,
                        model=worker_config.model,
                        tools=["web_search", "exa_search", "wikipedia"],
                    ),
                    AgentConfig(
                        agent_id="researcher_2",
                        role=AgentRole.RESEARCHER,
                        model=worker_config.model,
                        tools=["web_search", "exa_search", "wikipedia"],
                    ),
                    AgentConfig(
                        agent_id="researcher_3",
                        role=AgentRole.RESEARCHER,
                        model=worker_config.model,
                        tools=["web_search", "exa_search", "wikipedia"],
                    ),
                ]
            
            return MultiAgentConfig(
                config_id=f"config_{config_file.stem}",
                mode=ExecutionMode(config_data.get("mode", "parallel")),
                agents=agent_configs,
                orchestrator_config=orchestrator_config,
                worker_config=worker_config,
                critic_config=critic_config,
            )
            
        except Exception as e:
            logger.warning(f"⚠️ 加载配置失败: {e}，使用默认配置")
    
    # 默认配置
    logger.info("使用默认多智能体配置")
    return MultiAgentConfig(
        config_id="config_default",
        mode=ExecutionMode.PARALLEL,
        agents=[
            AgentConfig(
                agent_id="researcher_1",
                role=AgentRole.RESEARCHER,
                model="claude-sonnet-4-5-20250929",
                tools=["web_search", "exa_search", "wikipedia"],
            ),
            AgentConfig(
                agent_id="researcher_2",
                role=AgentRole.RESEARCHER,
                model="claude-sonnet-4-5-20250929",
                tools=["web_search", "exa_search", "wikipedia"],
            ),
            AgentConfig(
                agent_id="researcher_3",
                role=AgentRole.RESEARCHER,
                model="claude-sonnet-4-5-20250929",
                tools=["web_search", "exa_search", "wikipedia"],
            ),
        ],
        orchestrator_config=OrchestratorConfig(),
        worker_config=WorkerConfig(),
        critic_config=CriticConfig(enabled=True),
    )
