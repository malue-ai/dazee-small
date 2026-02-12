"""
评估系统数据模型

基于 Anthropic 的 AI Agent 评估方法论设计。
参考：https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents

核心概念：
- Task（任务）：单个测试用例，包含输入和成功标准
- Trial（试验）：对同一Task的一次执行（因模型随机性需多次运行）
- Transcript（转录）：完整执行记录（LLM调用、工具调用、推理过程）
- Outcome（结果）：环境中的最终状态（ground truth）
- Grader（评分器）：评分逻辑，包含多个assertions
- Evaluation Suite（评估套件）：一组相关Task，测试特定能力
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


class GraderType(str, Enum):
    """评分器类型"""
    CODE = "code"       # 代码评分器：快速、客观、便宜
    MODEL = "model"     # 模型评分器：灵活、主观、需校准
    HUMAN = "human"     # 人工评分器：黄金标准、定期抽样


class TrialStatus(str, Enum):
    """试验状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class ToolCall(BaseModel):
    """工具调用记录"""
    name: str = Field(..., description="工具名称")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="工具参数")
    result: Optional[Any] = Field(None, description="工具返回结果")
    error: Optional[str] = Field(None, description="工具调用错误信息")
    duration_ms: Optional[int] = Field(None, description="工具执行耗时（毫秒）")
    timestamp: datetime = Field(default_factory=datetime.now)


class Message(BaseModel):
    """消息记录"""
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    tool_calls: List[ToolCall] = Field(default_factory=list)
    thinking: Optional[str] = Field(None, description="Extended Thinking内容")
    timestamp: datetime = Field(default_factory=datetime.now)


# Re-exported from models.usage to avoid circular dependency
# (services/ and core/ should import from models.usage directly)
from models.usage import TokenUsage  # noqa: F401


class Transcript(BaseModel):
    """
    转录记录（Transcript）
    
    完整执行记录，包括：
    - LLM调用历史（messages数组）
    - 工具调用记录（tool_calls）
    - 推理过程（thinking）
    - Token使用统计
    
    用于评估"智能体说了什么"
    """
    messages: List[Message] = Field(default_factory=list, description="消息历史")
    tool_calls: List[ToolCall] = Field(default_factory=list, description="所有工具调用")
    token_usage: TokenUsage = Field(default_factory=TokenUsage, description="Token使用统计")
    duration_ms: int = Field(0, description="总执行时间（毫秒）")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="额外元数据")
    
    def get_all_tool_names(self) -> List[str]:
        """获取所有调用过的工具名称"""
        return [tc.name for tc in self.tool_calls]
    
    def get_assistant_responses(self) -> List[str]:
        """获取所有助手回复"""
        return [msg.content for msg in self.messages if msg.role == "assistant"]
    
    def get_final_response(self) -> Optional[str]:
        """获取最终回复"""
        assistant_msgs = [msg for msg in self.messages if msg.role == "assistant"]
        return assistant_msgs[-1].content if assistant_msgs else None


class Outcome(BaseModel):
    """
    结果记录（Outcome）
    
    环境中的最终状态（ground truth），包括：
    - 数据库记录变化
    - 文件系统变化
    - 外部系统状态
    - 其他可验证的副作用
    
    用于评估"智能体真正做了什么"
    """
    database_changes: List[Dict[str, Any]] = Field(default_factory=list, description="数据库变化")
    file_changes: List[Dict[str, Any]] = Field(default_factory=list, description="文件系统变化")
    external_api_calls: List[Dict[str, Any]] = Field(default_factory=list, description="外部API调用")
    custom_outcomes: Dict[str, Any] = Field(default_factory=dict, description="自定义结果")
    
    def has_database_record(self, table: str, conditions: Dict[str, Any]) -> bool:
        """检查数据库中是否存在符合条件的记录"""
        for change in self.database_changes:
            if change.get("table") == table:
                match = all(
                    change.get("data", {}).get(k) == v 
                    for k, v in conditions.items()
                )
                if match:
                    return True
        return False
    
    def has_file(self, path: str) -> bool:
        """检查是否创建了指定文件"""
        return any(
            change.get("path") == path and change.get("action") == "create"
            for change in self.file_changes
        )


class GradeResult(BaseModel):
    """评分结果"""
    grader_type: GraderType
    grader_name: str = Field(..., description="评分器名称")
    passed: bool = Field(..., description="是否通过")
    score: Optional[float] = Field(None, description="评分（0-1或0-5）")
    explanation: Optional[str] = Field(None, description="评分说明")
    details: Dict[str, Any] = Field(default_factory=dict, description="详细信息")
    timestamp: datetime = Field(default_factory=datetime.now)
    # 新增：置信度机制
    confidence: Optional[float] = Field(None, description="置信度（0-1），低于0.7时触发人工复核")
    needs_human_review: bool = Field(False, description="是否需要人工复核")


class GraderConfig(BaseModel):
    """评分器配置"""
    type: GraderType
    name: str = Field(..., description="评分器名称")
    check: Optional[str] = Field(None, description="Code-based检查表达式")
    rubric: Optional[str] = Field(None, description="Model-based评分标准")
    min_score: Optional[float] = Field(None, description="最低通过分数")
    weight: float = Field(1.0, description="评分权重")


class TaskInput(BaseModel):
    """任务输入"""
    user_query: str = Field(..., description="用户查询")
    conversation_history: List[Dict[str, Any]] = Field(default_factory=list, description="历史对话")
    context: Dict[str, Any] = Field(default_factory=dict, description="上下文信息")
    files: List[str] = Field(default_factory=list, description="附件文件路径")


class ExpectedOutcome(BaseModel):
    """预期结果"""
    intent: Optional[str] = Field(None, description="预期意图")
    confidence: Optional[str] = Field(None, description="置信度要求，如'>0.7'")
    tool_calls: List[str] = Field(default_factory=list, description="预期调用的工具")
    response_contains: List[str] = Field(default_factory=list, description="回复应包含的关键词")
    custom_checks: Dict[str, Any] = Field(default_factory=dict, description="自定义检查")


class Checkpoint(BaseModel):
    """中间结果检查点"""
    name: str = Field(..., description="检查点名称")
    check: str = Field(..., description="检查表达式，如 'plan_step_count >= 1'")
    description: Optional[str] = Field(None, description="检查点说明")


class Task(BaseModel):
    """
    评估任务（Task）
    
    单个测试用例，包含：
    - 输入（user_query, conversation_history, context）
    - 预期结果（expected_outcome）
    - 评分器配置（graders）
    - 试验次数（trials）
    - 中间检查点（checkpoints）
    """
    id: str = Field(..., description="任务唯一标识")
    description: str = Field(..., description="任务描述")
    category: str = Field("general", description="任务类别")
    input: TaskInput = Field(..., description="任务输入")
    expected_outcome: ExpectedOutcome = Field(default_factory=ExpectedOutcome, description="预期结果")
    graders: List[GraderConfig] = Field(default_factory=list, description="评分器配置")
    trials: int = Field(3, description="试验次数（应对模型随机性）")
    timeout_seconds: int = Field(60, description="超时时间")
    tags: List[str] = Field(default_factory=list, description="标签")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    # 新增：中间结果检查点
    checkpoints: List[Checkpoint] = Field(default_factory=list, description="中间结果检查点")
    # 新增：推荐答案（用于人工对比和LLM Judge参考）
    reference_answer: Optional[str] = Field(None, description="推荐答案（用于对比评估）")


class Trial(BaseModel):
    """
    试验记录（Trial）
    
    对同一Task的一次执行，记录：
    - 执行状态
    - 转录记录（Transcript）
    - 结果记录（Outcome）
    - 评分结果
    """
    trial_id: str = Field(..., description="试验唯一标识")
    task_id: str = Field(..., description="关联的任务ID")
    trial_number: int = Field(..., description="试验序号（1, 2, 3...）")
    status: TrialStatus = Field(TrialStatus.PENDING, description="试验状态")
    transcript: Optional[Transcript] = Field(None, description="转录记录")
    outcome: Optional[Outcome] = Field(None, description="结果记录")
    grade_results: List[GradeResult] = Field(default_factory=list, description="评分结果")
    error: Optional[str] = Field(None, description="错误信息")
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """执行时长（秒）"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
    
    @property
    def passed(self) -> bool:
        """是否通过所有评分"""
        return all(gr.passed for gr in self.grade_results) if self.grade_results else False
    
    @property
    def average_score(self) -> Optional[float]:
        """平均评分"""
        scores = [gr.score for gr in self.grade_results if gr.score is not None]
        return sum(scores) / len(scores) if scores else None


class TaskResult(BaseModel):
    """任务结果（多次试验的汇总）"""
    task_id: str
    task_description: str
    trials: List[Trial] = Field(default_factory=list)
    
    @property
    def pass_rate(self) -> float:
        """通过率"""
        if not self.trials:
            return 0.0
        passed = sum(1 for t in self.trials if t.passed)
        return passed / len(self.trials)
    
    @property
    def average_score(self) -> Optional[float]:
        """平均分"""
        scores = [t.average_score for t in self.trials if t.average_score is not None]
        return sum(scores) / len(scores) if scores else None
    
    @property
    def score_std(self) -> Optional[float]:
        """分数标准差（用于检测不稳定任务）"""
        scores = [t.average_score for t in self.trials if t.average_score is not None]
        if len(scores) < 2:
            return None
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        return variance ** 0.5
    
    @property
    def is_stable(self) -> bool:
        """任务是否稳定（标准差 < 0.15）"""
        std = self.score_std
        return std is not None and std < 0.15


class EvaluationSuite(BaseModel):
    """
    评估套件（Evaluation Suite）
    
    一组相关Task，测试特定能力，如：
    - conversation（对话能力）
    - coding（代码能力）
    - research（研究能力）
    - document（文档处理能力）
    """
    id: str = Field(..., description="套件唯一标识")
    name: str = Field(..., description="套件名称")
    description: str = Field("", description="套件描述")
    category: str = Field("general", description="套件类别")
    tasks: List[Task] = Field(default_factory=list, description="任务列表")
    default_trials: int = Field(3, description="默认试验次数")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    created_at: datetime = Field(default_factory=datetime.now)


class EvaluationReport(BaseModel):
    """评估报告"""
    report_id: str
    suite_id: str
    suite_name: str
    task_results: List[TaskResult] = Field(default_factory=list)
    total_tasks: int = 0
    passed_tasks: int = 0
    failed_tasks: int = 0
    unstable_tasks: int = 0
    total_token_usage: TokenUsage = Field(default_factory=TokenUsage)
    total_duration_seconds: float = 0.0
    created_at: datetime = Field(default_factory=datetime.now)
    
    @property
    def pass_rate(self) -> float:
        """总体通过率"""
        return self.passed_tasks / self.total_tasks if self.total_tasks > 0 else 0.0
    
    @property
    def average_score(self) -> Optional[float]:
        """总体平均分"""
        scores = [tr.average_score for tr in self.task_results if tr.average_score is not None]
        return sum(scores) / len(scores) if scores else None
    
    def to_summary(self) -> Dict[str, Any]:
        """生成摘要"""
        return {
            "report_id": self.report_id,
            "suite": self.suite_name,
            "total_tasks": self.total_tasks,
            "pass_rate": f"{self.pass_rate:.1%}",
            "average_score": f"{self.average_score:.2f}" if self.average_score else "N/A",
            "unstable_tasks": self.unstable_tasks,
            "total_tokens": self.total_token_usage.total_tokens,
            "duration_seconds": f"{self.total_duration_seconds:.1f}s",
            "created_at": self.created_at.isoformat(),
        }
