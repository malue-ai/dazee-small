"""
Schema 验证器 - 定义 Agent 配置的强类型规范

核心理念：
- 每个组件有明确的配置字段和默认值
- LLM 生成的 Schema 必须通过验证
- 缺失字段自动使用合理默认值

参考：docs/15-FRAMEWORK_PROMPT_CONTRACT.md
"""

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from logger import get_logger

logger = get_logger(__name__)


# ============================================================
# 枚举定义
# ============================================================


class ComplexityLevel(str, Enum):
    """复杂度级别"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class OutputFormat(str, Enum):
    """输出格式"""

    TEXT = "text"
    JSON = "json"
    MARKDOWN = "markdown"
    HTML = "html"


class SelectionStrategy(str, Enum):
    """工具选择策略"""

    CAPABILITY_BASED = "capability_based"  # 基于能力匹配
    PRIORITY_BASED = "priority_based"  # 基于优先级
    ALL = "all"  # 返回所有可用


class RetentionPolicy(str, Enum):
    """记忆保留策略"""

    SESSION = "session"  # 会话级（会话结束清除）
    USER = "user"  # 用户级（跨会话保留）
    PERSISTENT = "persistent"  # 持久化（永久保存）


class PlanGranularity(str, Enum):
    """计划粒度"""

    FINE = "fine"  # 细粒度（每步详细）
    MEDIUM = "medium"  # 中等粒度
    COARSE = "coarse"  # 粗粒度（只有主要步骤）


# ============================================================
# Prompt 相关配置类
# ============================================================


class PrefaceConfig(BaseModel):
    """前言配置（在回复前插入简短引导语）"""

    enabled: bool = Field(default=True, description="是否启用前言")
    max_tokens: int = Field(default=150, description="前言最大 token 数")
    template: str = Field(default="", description="前言模板")


class SimulatedThinkingConfig(BaseModel):
    """模拟思考配置（Agent 生成的思考过程展示）"""

    guide: str = Field(default="", description="模拟思考引导提示词")


class PromptsConfig(BaseModel):
    """提示词配置"""

    preface: Optional[PrefaceConfig] = Field(default=None, description="前言配置")
    simulated_thinking: Optional[SimulatedThinkingConfig] = Field(
        default=None, description="模拟思考配置"
    )


# ============================================================
# 组件配置类
# ============================================================


class ComponentConfig(BaseModel):
    """组件配置基类"""

    enabled: bool = True

    class Config:
        extra = "allow"  # 允许子类扩展字段


class IntentAnalyzerConfig(ComponentConfig):
    """
    意图分析器配置

    用途：分析用户意图，判断任务类型和复杂度
    """

    # 支持的复杂度级别
    complexity_levels: List[str] = Field(
        default=["low", "medium", "high"], description="支持的复杂度级别"
    )

    # 支持的任务类型
    task_types: List[str] = Field(
        default_factory=lambda: [
            "question_answering",  # 问答
            "data_analysis",  # 数据分析
            "content_generation",  # 内容生成
            "code_execution",  # 代码执行
            "web_search",  # 网络搜索
            "file_operation",  # 文件操作
        ],
        description="支持的任务类型",
    )

    # 支持的输出格式
    output_formats: List[str] = Field(
        default=["text", "json", "markdown"], description="支持的输出格式"
    )

    # 是否使用 LLM 进行意图分析（false 则使用规则匹配）
    use_llm: bool = Field(default=True, description="是否使用 LLM 进行意图分析")

    # LLM 模型（用于意图分析的轻量模型）
    llm_model: str = Field(
        default="claude-haiku-4-5-20251001",
        description="意图分析使用的 LLM 模型（Haiku 4.5 支持 64K output tokens）",
    )

    # V11 小搭子：意图分析扩展配置
    fast_mode: bool = Field(default=False, description="快速模式（使用更快模型减少延迟）")
    semantic_cache_threshold: Optional[float] = Field(
        default=None, description="语义缓存命中阈值（0-1），未设则用环境默认"
    )
    simplified_output: bool = Field(default=True, description="仅输出简化字段（complexity/skip_memory/is_follow_up）")


class PlanManagerConfig(ComponentConfig):
    """
    计划管理器配置

    用途：管理复杂任务的执行计划
    """

    # 触发条件（Python 表达式）
    trigger_condition: str = Field(
        default="complexity == 'high' or step_count > 3", description="触发计划管理的条件"
    )

    # 最大步骤数
    max_steps: int = Field(default=10, ge=1, le=50, description="计划最大步骤数")

    # 计划粒度
    granularity: str = Field(default="medium", description="计划粒度 (fine/medium/coarse)")

    # 是否允许动态调整计划
    allow_dynamic_adjustment: bool = Field(
        default=True, description="是否允许执行过程中动态调整计划"
    )

    # 计划验证间隔（每 N 步验证一次）
    validation_interval: int = Field(default=3, ge=1, description="计划验证间隔")

    # ===== 🆕 Re-Plan 配置（V4.2.1） =====

    # 是否允许重新生成计划
    replan_enabled: bool = Field(default=True, description="是否允许在执行过程中重新生成计划")

    # 最大重新规划次数
    max_replan_attempts: int = Field(
        default=2, ge=0, le=5, description="最大重新规划次数（0 表示不限制）"
    )

    # 重新规划策略
    replan_strategy: str = Field(
        default="incremental",
        description="重新规划策略 (full: 全量重新规划 / incremental: 保留已完成步骤)",
    )

    # 失败率阈值（超过此值触发重规划建议）
    failure_threshold: float = Field(
        default=0.3, ge=0.0, le=1.0, description="步骤失败率阈值，超过时 Claude 应考虑 replan"
    )

    @field_validator("granularity")
    @classmethod
    def validate_granularity(cls, v):
        valid = ["fine", "medium", "coarse"]
        if v not in valid:
            raise ValueError(f"granularity 必须是 {valid} 之一")
        return v

    @field_validator("replan_strategy")
    @classmethod
    def validate_replan_strategy(cls, v):
        valid = ["full", "incremental"]
        if v not in valid:
            raise ValueError(f"replan_strategy 必须是 {valid} 之一")
        return v


class ToolSelectorConfig(ComponentConfig):
    """
    工具选择器配置

    用途：根据任务需求选择合适的工具
    """

    # 可用工具列表（空列表表示使用全部）
    available_tools: List[str] = Field(
        default_factory=list, description="可用工具列表，空表示全部可用"
    )

    # 选择策略
    selection_strategy: str = Field(default="capability_based", description="工具选择策略")

    # 是否允许并行调用
    allow_parallel: bool = Field(default=False, description="是否允许并行工具调用")

    # 最大并行工具数
    max_parallel_tools: int = Field(default=3, ge=1, le=10, description="最大并行工具数")

    # 基础工具（始终包含）
    base_tools: List[str] = Field(
        default_factory=lambda: ["plan_todo", "api_calling"], description="始终包含的基础工具"
    )

    # 工具超时（秒）
    tool_timeout: int = Field(default=300, ge=10, le=3600, description="单个工具执行超时时间（秒）")

    @field_validator("selection_strategy")
    @classmethod
    def validate_strategy(cls, v):
        valid = ["capability_based", "priority_based", "all"]
        if v not in valid:
            raise ValueError(f"selection_strategy 必须是 {valid} 之一")
        return v


class MemoryManagerConfig(ComponentConfig):
    """
    记忆管理器配置

    用途：管理会话记忆和上下文
    """

    # 记忆保留策略
    retention_policy: str = Field(
        default="session", description="记忆保留策略 (session/user/persistent)"
    )

    # 是否启用情景记忆
    episodic_memory: bool = Field(default=False, description="是否启用情景记忆（跨会话）")

    # 工作记忆限制（消息数）
    working_memory_limit: int = Field(default=20, ge=5, le=100, description="工作记忆消息数限制")

    # 是否自动压缩
    auto_compress: bool = Field(default=True, description="是否自动压缩长对话")

    # 压缩阈值（消息数）
    compress_threshold: int = Field(default=15, ge=5, description="触发压缩的消息数阈值")

    @field_validator("retention_policy")
    @classmethod
    def validate_policy(cls, v):
        valid = ["session", "user", "persistent"]
        if v not in valid:
            raise ValueError(f"retention_policy 必须是 {valid} 之一")
        return v


class OutputFormatterConfig(ComponentConfig):
    """
    输出格式化器配置

    用途：格式化 Agent 的最终输出

    V6.3 改进：
    - 默认使用 text 格式（最简单、最兼容）
    - JSON 校验使用 Pydantic 模型（替代 jsonschema）
    - 支持动态 Pydantic 模型定义
    """

    # 默认输出格式
    default_format: str = Field(default="text", description="默认输出格式（text/markdown/json）")

    # 支持的格式列表
    supported_formats: List[str] = Field(
        default=["text", "markdown", "json", "html"], description="支持的输出格式"
    )

    # 是否启用代码高亮
    code_highlighting: bool = Field(default=True, description="是否启用代码高亮")

    # 最大输出长度（字符）
    max_output_length: int = Field(default=50000, ge=1000, description="最大输出长度")

    # JSON 输出配置（使用 Pydantic 模型校验）
    json_model_name: Optional[str] = Field(
        default=None, description="Pydantic 模型名称（用于校验，从 output_models 目录加载）"
    )

    json_schema: Optional[Dict[str, Any]] = Field(
        default=None, description="动态 JSON Schema 定义（仅当 json_model_name 未指定时使用）"
    )

    strict_json_validation: bool = Field(
        default=False, description="是否启用严格 JSON 校验（不通过则抛出错误）"
    )

    json_ensure_ascii: bool = Field(
        default=False, description="JSON 序列化时是否确保 ASCII（False 支持中文）"
    )

    json_indent: Optional[int] = Field(
        default=2, ge=0, le=8, description="JSON 缩进空格数（None 为紧凑格式）"
    )

    # 是否包含元数据
    include_metadata: bool = Field(default=False, description="是否在输出中包含元数据")

    @field_validator("default_format")
    @classmethod
    def validate_format(cls, v):
        valid = ["text", "markdown", "json", "html"]
        if v not in valid:
            raise ValueError(f"default_format 必须是 {valid} 之一")
        return v


# ============================================================
# 辅助配置类
# ============================================================


class SkillConfig(BaseModel):
    """Skill 配置（本地 Skill 系统）"""

    # Skill 名称
    name: str = Field(..., description="Skill 名称")

    # 是否启用
    enabled: bool = Field(default=True, description="是否启用")

    # Skill 描述
    description: str = Field(default="", description="Skill 描述")


class ContextLimitsConfig(BaseModel):
    """上下文限制配置"""

    # 最大 Context Token 数
    max_context_tokens: int = Field(default=200000, ge=1000, description="最大 Context Token 数")

    # 警告阈值（百分比）
    warning_threshold: float = Field(
        default=0.8, ge=0.5, le=0.95, description="Context 使用警告阈值"
    )

    # 自动截断阈值
    truncate_threshold: float = Field(default=0.9, ge=0.7, le=0.99, description="自动截断阈值")


# ============================================================
# Agent Schema - 核心定义
# ============================================================


class AgentSchema(BaseModel):
    """
    Agent Schema - 框架与 Prompt 之间的契约

    这是 Agent 配置的完整定义，包含所有组件配置和运行参数。
    可以由 LLM 根据 System Prompt 生成，或使用预设值。
    """

    # 基本信息
    name: str = Field(default="GeneralAgent", description="Agent 名称")
    description: str = Field(default="通用智能助手", description="Agent 描述")

    # ============================================================
    # 组件配置 - 强类型定义
    # ============================================================

    intent_analyzer: IntentAnalyzerConfig = Field(
        default_factory=IntentAnalyzerConfig, description="意图分析器配置"
    )

    plan_manager: PlanManagerConfig = Field(
        default_factory=PlanManagerConfig, description="计划管理器配置"
    )

    tool_selector: ToolSelectorConfig = Field(
        default_factory=ToolSelectorConfig, description="工具选择器配置"
    )

    memory_manager: MemoryManagerConfig = Field(
        default_factory=MemoryManagerConfig, description="记忆管理器配置"
    )

    output_formatter: OutputFormatterConfig = Field(
        default_factory=OutputFormatterConfig, description="输出格式化器配置"
    )

    # ============================================================
    # Skills 和 Tools
    # ============================================================

    skills: List[SkillConfig] = Field(default_factory=list, description="启用的 Skills 列表")

    tools: List[str] = Field(default_factory=list, description="启用的工具名称列表")

    # ============================================================
    # 运行时参数
    # ============================================================

    model: str = Field(
        default="",
        description="主 LLM 模型（运行时由 instance_config 注入，不由 LLM 生成）",
    )

    max_turns: Optional[int] = Field(
        default=None,
        description="已废弃：终止由 AdaptiveTerminator 自主决策，此字段仅为向后兼容保留",
    )

    # 🆕 V10.1: 执行策略
    execution_strategy: str = Field(
        default="rvr-b", description="执行策略: rvr (标准), rvr-b (带回溯，默认)"
    )

    allow_parallel_tools: bool = Field(default=False, description="是否允许并行工具调用")

    # ============================================================
    # 上下文限制
    # ============================================================

    context_limits: ContextLimitsConfig = Field(
        default_factory=ContextLimitsConfig, description="上下文限制配置"
    )

    # ============================================================
    # V11.0: 移除 multi_agent 配置（小搭子固定 RVR-B）

    # ============================================================
    # LLM 超参数配置（可选覆盖）
    # ============================================================

    temperature: Optional[float] = Field(
        default=None, ge=0.0, le=2.0, description="LLM 温度参数（None 使用默认值）"
    )

    max_tokens: Optional[int] = Field(
        default=None, ge=1, description="LLM 最大输出 token 数（None 使用默认值）"
    )

    enable_thinking: Optional[bool] = Field(
        default=None, description="是否启用 Extended Thinking（None 使用默认值）"
    )

    enable_caching: Optional[bool] = Field(
        default=None, description="是否启用 Prompt Caching（None 使用默认值）"
    )

    # 🆕 V10.3: thinking_mode 控制思考展示方式
    thinking_mode: Optional[str] = Field(
        default=None,
        description="思考模式: native (LLM 原生 Extended Thinking), simulated (模拟思考), none (不展示思考)"
    )

    # 🆕 prompts 配置
    prompts: Optional["PromptsConfig"] = Field(
        default=None, description="提示词配置（preface、simulated_thinking 等）"
    )

    # ============================================================
    # 可解释性
    # ============================================================

    reasoning: str = Field(default="", description="配置理由（用于可解释性）")

    # ============================================================
    # 验证器
    # ============================================================

    @model_validator(mode="before")
    @classmethod
    def handle_legacy_format(cls, values):
        """
        处理旧格式兼容性

        旧格式使用 components: Dict[str, Any]
        新格式使用独立的强类型字段
        """
        if not isinstance(values, dict):
            return values

        # 如果有旧格式的 components 字段，转换为新格式
        if "components" in values and isinstance(values["components"], dict):
            components = values.pop("components")

            for comp_name in [
                "intent_analyzer",
                "plan_manager",
                "tool_selector",
                "memory_manager",
                "output_formatter",
            ]:
                if comp_name in components and comp_name not in values:
                    values[comp_name] = components[comp_name]

        return values

    @field_validator("model")
    @classmethod
    def validate_model(cls, v):
        """验证模型名称"""
        # 空字符串表示「待由 config.yaml 注入」，不告警
        if not v or not v.strip():
            return v
        valid_prefixes = [
            "claude-", "gpt-", "gemini-", "qwen",
            "deepseek-", "glm-", "MiniMax-", "minimax-", "kimi-",
            "o1", "o3", "o4-",
            "text-",  # OpenAI embedding 等（少数场景会经此校验）
        ]
        if not any(v.startswith(p) for p in valid_prefixes):
            logger.warning(f"未知模型 '{v}'，可能不受支持", extra={"model": v})
        return v

    # ============================================================
    # 便捷属性
    # ============================================================

    @property
    def is_intent_analysis_enabled(self) -> bool:
        """意图识别是否启用"""
        return self.intent_analyzer.enabled

    # ============================================================
    # 转换方法
    # ============================================================

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（兼容旧格式）"""
        result = {
            "name": self.name,
            "description": self.description,
            "components": {
                "intent_analyzer": self.intent_analyzer.dict(),
                "plan_manager": self.plan_manager.dict(),
                "tool_selector": self.tool_selector.dict(),
                "memory_manager": self.memory_manager.dict(),
                "output_formatter": self.output_formatter.dict(),
            },
            "skills": [s.dict() if isinstance(s, SkillConfig) else s for s in self.skills],
            "tools": self.tools,
            "model": self.model,
            "max_turns": self.max_turns,
            "allow_parallel_tools": self.allow_parallel_tools,
            "context_limits": self.context_limits.dict(),
            "reasoning": self.reasoning,
        }

        # 🆕 V7: 包含 LLM 超参数（仅非空值）
        if self.temperature is not None:
            result["temperature"] = self.temperature
        if self.max_tokens is not None:
            result["max_tokens"] = self.max_tokens
        if self.enable_thinking is not None:
            result["enable_thinking"] = self.enable_thinking
        if self.enable_caching is not None:
            result["enable_caching"] = self.enable_caching

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentSchema":
        """
        从字典创建（安全解析，缺失字段使用默认值）

        这是从 LLM 输出创建 Schema 的主要入口
        """
        try:
            return cls(**data)
        except Exception as e:
            logger.warning(f"⚠️ Schema 解析部分失败，使用默认值: {e}")
            # 逐字段尝试
            safe_data = {}
            for key, value in data.items():
                try:
                    # 尝试创建临时实例验证单个字段
                    test_data = {key: value}
                    cls(**{**DEFAULT_AGENT_SCHEMA.dict(), **test_data})
                    safe_data[key] = value
                except Exception:
                    logger.debug(f"   跳过无效字段: {key}")
            return cls(**safe_data)

    @classmethod
    def from_llm_output(cls, raw: Dict[str, Any]) -> "AgentSchema":
        """
        从 LLM 输出安全创建 Schema

        LLM 可能生成不完整或格式有误的配置，此方法会：
        1. 尝试解析所有字段
        2. 对无效字段使用默认值
        3. 记录警告但不抛出异常
        4. 强制丢弃 model 字段（model 由运行时 instance_config 决定，不由 LLM 推断）
        """
        # model 是运行时配置，不是 LLM 应该推断的字段
        # 即使 LLM 返回了 model，也丢弃，避免硬编码污染
        if "model" in raw:
            logger.info(
                f"   丢弃 LLM 生成的 model 字段: {raw['model']}（model 由运行时配置决定）"
            )
            raw = {k: v for k, v in raw.items() if k != "model"}
        return cls.from_dict(raw)

    class Config:
        # 允许使用枚举值
        use_enum_values = True
        # 验证赋值
        validate_assignment = True


# ============================================================
# 默认 Schema（高质量兜底配置）
# ============================================================
#
# 设计理念：
# - 这是框架的"安全网"，即使运营配置不全/错误，Agent 也能高质量运行
# - 配置优先级：config.yaml 显式配置 > LLM 推断 > DEFAULT_AGENT_SCHEMA
# - 默认值应该是"最佳实践"而非"最小化配置"
#

DEFAULT_AGENT_SCHEMA = AgentSchema(
    name="GeneralAgent",
    description="通用智能助手（高质量默认配置）",
    # 意图分析器：启用 LLM 分析，覆盖常见任务类型
    intent_analyzer=IntentAnalyzerConfig(
        enabled=True,
        use_llm=True,
        task_types=[
            "question_answering",
            "data_analysis",
            "content_generation",
            "code_execution",
            "web_search",
            "file_operation",
        ],
        complexity_levels=["low", "medium", "high"],
    ),
    # 计划管理器：适中规模，适应大多数任务
    plan_manager=PlanManagerConfig(
        enabled=True,
        max_steps=15,  # 适中的步骤数
        granularity="medium",  # 中等粒度
        allow_dynamic_adjustment=True,  # 允许动态调整
        replan_enabled=True,  # 允许重规划
        max_replan_attempts=2,  # 最多重规划 2 次
        replan_strategy="incremental",  # 增量重规划（保留已完成步骤）
        failure_threshold=0.3,  # 30% 失败率触发重规划建议
    ),
    # 工具选择器：基于能力的选择策略
    tool_selector=ToolSelectorConfig(
        enabled=True,
        selection_strategy="capability_based",
        allow_parallel=False,  # 默认串行（更稳定）
        max_parallel_tools=3,
        base_tools=["plan_todo", "api_calling"],  # 始终包含计划工具和 HTTP 请求能力
        tool_timeout=300,  # 5 分钟超时
    ),
    # 记忆管理器：session 级别，适度的工作记忆
    memory_manager=MemoryManagerConfig(
        enabled=True,
        retention_policy="session",
        working_memory_limit=20,  # 适中的记忆容量
        auto_compress=True,  # 自动压缩长对话
        compress_threshold=15,  # 15 条消息触发压缩
    ),
    # 输出格式化器：Markdown 格式，支持代码高亮
    output_formatter=OutputFormatterConfig(
        enabled=True,
        default_format="text",
        code_highlighting=True,
        max_output_length=50000,
    ),
    # 运行时参数
    model="",  # 不预设默认模型，必须由 config.yaml 显式配置
    max_turns=15,  # 适中的对话长度
    allow_parallel_tools=False,  # 默认串行（更稳定）
    skills=[],  # 由 config.yaml 配置
    tools=[],  # 由 config.yaml 配置
    reasoning="高质量默认配置：适应大多数场景，平衡能力和稳定性。作为 config.yaml 配置缺失时的兜底。",
)


# ============================================================
# 工具函数
# ============================================================


def validate_schema(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    验证 Schema 数据

    Returns:
        (is_valid, error_message)
    """
    try:
        AgentSchema(**data)
        return True, None
    except Exception as e:
        return False, str(e)


def merge_with_defaults(data: Dict[str, Any]) -> AgentSchema:
    """
    将部分配置与默认值合并

    用于处理 LLM 只生成部分配置的情况
    """
    default_dict = DEFAULT_AGENT_SCHEMA.dict()

    # 深度合并
    def deep_merge(base: dict, override: dict) -> dict:
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    merged = deep_merge(default_dict, data)
    return AgentSchema(**merged)
