"""
统一类型定义

合并自：
- core/tool/base.py (ToolContext, ToolResult, BaseTool)
- core/tool/capability/types.py (Capability, CapabilityType, CapabilitySubtype)

设计原则：
1. 显式依赖：通过 ToolContext 传递依赖，不使用魔法反射
2. 统一抽象：所有能力（Skills/Tools/Code）统一为 Capability
3. 向后兼容：支持旧式工具的适配

术语说明：
- Capability: 抽象能力描述（包含能力标签、优先级、约束等）
- Tool: 具体的可调用实现（TOOL 类型的 Capability）
- Skill: Claude Skills 或本地工作流（SKILL 类型的 Capability）
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from core.events.manager import EventManager
    from core.memory.working import WorkingMemory


# ==================== 枚举类型 ====================


class CapabilityType(Enum):
    """
    能力实现类型

    - SKILL: Claude Skills 或本地工作流技能（系统提示词注入）
    - TOOL: 预定义函数工具（通过 tool_use 调用）
    - CODE: 动态代码执行
    """

    SKILL = "SKILL"
    TOOL = "TOOL"
    CODE = "CODE"


class CapabilitySubtype(Enum):
    """
    能力子类型

    - PREBUILT: 预置/内置（如 Claude Skills）
    - CUSTOM: 用户自定义
    - NATIVE: 系统原生
    - EXTERNAL: 外部服务
    - DYNAMIC: 动态生成
    """

    PREBUILT = "PREBUILT"
    CUSTOM = "CUSTOM"
    NATIVE = "NATIVE"
    EXTERNAL = "EXTERNAL"
    DYNAMIC = "DYNAMIC"


class InvocationType(Enum):
    """
    调用方式类型

    - DIRECT: 标准 tool_use 调用
    - PROGRAMMATIC: 程序化多工具调用（批量/循环）
    - STREAMING: 细粒度流式（大参数场景）
    """

    DIRECT = "direct"
    PROGRAMMATIC = "programmatic"
    STREAMING = "streaming"


# ==================== 结构化工具错误 ====================


class ToolErrorType(str, Enum):
    """
    Structured error types for tool failures.

    Agent can use error_type to decide recovery strategy programmatically,
    instead of guessing from free-text error messages.
    """

    PERMISSION_DENIED = "permission_denied"     # → auto-open system preferences
    DEPENDENCY_MISSING = "dependency_missing"   # → prompt install
    TIMEOUT = "timeout"                         # → inform user, stop retry
    INPUT_INVALID = "input_invalid"             # → Agent fixes params and retries
    RATE_LIMITED = "rate_limited"               # → wait and retry
    AUTH_EXPIRED = "auth_expired"               # → guide re-auth
    TRANSIENT = "transient"                     # → retry immediately
    PERMANENT = "permanent"                     # → switch approach


@dataclass
class ToolError:
    """
    Structured tool error with recovery hints.

    Backward-compatible: to_dict() returns the same {"success": False, "error": ...}
    format, but adds error_type and recovery_hint for programmatic handling.
    """

    error_type: ToolErrorType
    message: str
    recovery_hint: Optional[str] = None
    retry_after_seconds: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict format (backward-compatible with existing error format)."""
        result: Dict[str, Any] = {
            "success": False,
            "error": self.message,
            "error_type": self.error_type.value,
        }
        if self.recovery_hint:
            result["recovery_hint"] = self.recovery_hint
        if self.retry_after_seconds > 0:
            result["retry_after_seconds"] = self.retry_after_seconds
        return result


# ==================== 工具上下文 ====================


@dataclass
class ToolContext:
    """
    工具执行上下文

    显式传递所有依赖，不再使用 inspect 魔法注入。
    工具可以按需从 context 中获取所需依赖。

    Attributes:
        session_id: 会话 ID
        conversation_id: 对话 ID
        user_id: 用户 ID
        memory: 工作记忆实例（可选）
        event_manager: 事件管理器实例（可选）
        apis_config: 预配置的 API 列表（用于 api_calling 等工具）
        extra: 扩展字段，用于传递其他自定义数据
    """

    session_id: str = ""
    conversation_id: str = ""
    user_id: str = "default_user"
    instance_id: str = ""  # Instance name for storage isolation
    memory: Optional["WorkingMemory"] = None
    event_manager: Optional["EventManager"] = None
    apis_config: Optional[List[Dict[str, Any]]] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        """从 extra 中获取扩展数据"""
        return self.extra.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """设置扩展数据"""
        self.extra[key] = value


@dataclass
class ToolResult:
    """
    工具执行结果

    标准化的结果格式，包含成功/失败状态和数据。
    """

    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {"success": self.success, **self.data}
        if self.error:
            result["error"] = self.error
        return result

    @classmethod
    def ok(cls, **data) -> "ToolResult":
        """创建成功结果"""
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, error: str, **data) -> "ToolResult":
        """创建失败结果"""
        return cls(success=False, error=error, data=data)


# ==================== 能力定义 ====================


@dataclass
class Capability:
    """
    统一能力定义

    抽象所有执行方式（Skills/Tools/Code）

    Attributes:
        name: 能力名称（唯一标识）
        type: 能力类型（SKILL/TOOL/CODE）
        subtype: 子类型（PREBUILT/CUSTOM/NATIVE/EXTERNAL/DYNAMIC）
        provider: 提供者（system/user/anthropic/local 等）
        capabilities: 能力标签列表（如 ppt_generation, data_analysis）
        priority: 基础优先级 0-100
        cost: 成本信息 {time: fast/medium/slow, money: free/low/high}
        constraints: 约束条件（requires_api, requires_network 等）
        metadata: 扩展信息（description, keywords, preferred_for 等）
        input_schema: 工具输入 Schema（用于 Claude API）
        fallback_tool: 替代工具（Skill 无法执行时使用的 TOOL）
        skill_path: Skill 本地路径（skills/library/ 下）
        level: 工具层级（1=核心/始终加载，2=动态/按需加载）
        cache_stable: 结果是否稳定可缓存（同输入同输出）
    """

    name: str
    type: CapabilityType
    subtype: str
    provider: str
    capabilities: List[str]
    priority: int
    cost: Dict[str, str]
    constraints: Dict[str, Any]
    metadata: Dict[str, Any]
    input_schema: Optional[Dict] = None
    fallback_tool: Optional[str] = None
    skill_path: Optional[str] = None
    level: int = 2
    cache_stable: bool = False

    def meets_constraints(self, context: Dict[str, Any] = None) -> bool:
        """
        检查是否满足约束条件

        Args:
            context: 当前上下文（如可用的 API、网络状态等）

        Returns:
            是否满足约束
        """
        if not context:
            return True

        # 检查 API 依赖
        if self.constraints.get("requires_api"):
            api_name = self.constraints.get("api_name")
            available_apis = context.get("available_apis", [])
            if api_name and api_name not in available_apis:
                return False

        # 检查网络依赖
        if self.constraints.get("requires_network"):
            if not context.get("network_available", True):
                return False

        # 检查认证依赖
        if self.constraints.get("requires_auth"):
            if not context.get("authenticated", False):
                return False

        return True

    def to_tool_schema(self) -> Optional[Dict]:
        """
        转换为 Claude API 的 tool schema 格式

        Returns:
            符合 Claude API 规范的 tool schema，或 None
        """
        if self.type != CapabilityType.TOOL:
            return None

        if not self.input_schema:
            return None

        return {
            "name": self.name,
            "description": self.metadata.get("description", self.name),
            "input_schema": self.input_schema,
        }


# ==================== 工具基类 ====================


class BaseTool(ABC):
    """
    工具基类（新版接口）

    所有工具应继承此类并实现 execute 方法。
    可选实现 execute_stream 方法以支持流式输出。

    示例:
        class MyTool(BaseTool):
            name = "my_tool"
            description = "示例工具"

            async def execute(
                self,
                params: Dict[str, Any],
                context: ToolContext
            ) -> Dict[str, Any]:
                # 从 context 获取依赖
                memory = context.memory
                # 执行逻辑
                return {"success": True, "result": "..."}

            async def execute_stream(
                self,
                params: Dict[str, Any],
                context: ToolContext
            ) -> AsyncGenerator[str, None]:
                # 流式输出（可选）
                yield "chunk1"
                yield "chunk2"
    """

    # 子类需要定义这些属性
    name: str = ""
    description: str = ""
    input_schema: Optional[Dict[str, Any]] = None
    execution_timeout: int = 60  # seconds; override per tool (e.g. browser=120)

    @abstractmethod
    async def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        """
        执行工具

        Args:
            params: 工具输入参数（从 LLM 调用中提取）
            context: 执行上下文（包含 session_id、memory 等）

        Returns:
            执行结果字典，必须包含 "success" 字段
        """
        pass

    def get_schema(self) -> Optional[Dict[str, Any]]:
        """获取工具的 JSON Schema（用于 Claude API）"""
        if self.input_schema:
            return {
                "name": self.name,
                "description": self.description,
                "input_schema": self.input_schema,
            }
        return None


class LegacyToolAdapter(BaseTool):
    """
    旧式工具适配器

    将不使用 ToolContext 的旧工具包装为新接口。
    用于向后兼容，避免一次性修改所有工具。

    适配器会：
    1. 从 context 中提取 conversation_id、user_id 等注入到 params
    2. 调用旧工具的 execute(**params) 方法
    """

    def __init__(self, legacy_tool: Any):
        """
        初始化适配器

        Args:
            legacy_tool: 旧式工具实例（有 execute 方法但不接受 context）
        """
        self._legacy_tool = legacy_tool

        # 从旧工具获取元信息
        if hasattr(legacy_tool, "name"):
            self.name = legacy_tool.name() if callable(legacy_tool.name) else legacy_tool.name

        if hasattr(legacy_tool, "description"):
            self.description = (
                legacy_tool.description()
                if callable(legacy_tool.description)
                else legacy_tool.description
            )

        if hasattr(legacy_tool, "parameters"):
            params = (
                legacy_tool.parameters()
                if callable(legacy_tool.parameters)
                else legacy_tool.parameters
            )
            self.input_schema = params

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        """
        执行旧工具

        将 context 中的关键字段注入到 params 中，然后调用旧工具
        """
        import asyncio

        # 注入 context 中的关键字段到 params
        injected_params = {
            "conversation_id": context.conversation_id,
            "user_id": context.user_id,
            **params,
        }

        # 调用旧工具的 execute 方法
        execute_method = getattr(self._legacy_tool, "execute", None)
        if execute_method is None:
            return {"success": False, "error": "工具没有 execute 方法"}

        if asyncio.iscoroutinefunction(execute_method):
            return await execute_method(**injected_params)
        else:
            return execute_method(**injected_params)

    @property
    def legacy_tool(self) -> Any:
        """获取底层旧工具实例"""
        return self._legacy_tool


# ==================== 调用策略 ====================


@dataclass
class InvocationStrategy:
    """
    调用策略

    描述如何调用工具（直接调用、程序化调用、流式调用）
    """

    type: InvocationType
    reason: str
    config: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type.value, "reason": self.reason, "config": self.config or {}}


@dataclass
class ToolCharacteristics:
    """
    工具特性

    描述工具的运行特性，用于选择调用策略
    """

    name: str
    has_large_input: bool = False  # 是否有大参数 (>10KB)
    requires_computation: bool = False  # 是否需要计算逻辑
    supports_batch: bool = False  # 是否支持批量操作
    is_stateful: bool = False  # 是否有状态
    estimated_input_size: int = 0  # 预估输入大小（bytes）


# ==================== 工厂函数 ====================


def create_tool_context(
    session_id: str = "",
    conversation_id: str = "",
    user_id: str = "default_user",
    memory: Optional["WorkingMemory"] = None,
    event_manager: Optional["EventManager"] = None,
    apis_config: Optional[List[Dict[str, Any]]] = None,
    **extra
) -> ToolContext:
    """
    创建工具上下文

    Args:
        session_id: 会话 ID
        conversation_id: 对话 ID
        user_id: 用户 ID
        memory: 工作记忆
        event_manager: 事件管理器
        apis_config: API 配置列表
        **extra: 其他扩展数据

    Returns:
        ToolContext 实例
    """
    return ToolContext(
        session_id=session_id,
        conversation_id=conversation_id,
        user_id=user_id,
        memory=memory,
        event_manager=event_manager,
        apis_config=apis_config,
        extra=extra,
    )


# ==================== 导出 ====================

__all__ = [
    # 枚举类型
    "CapabilityType",
    "CapabilitySubtype",
    "InvocationType",
    "ToolErrorType",
    # 数据类
    "ToolContext",
    "ToolResult",
    "ToolError",
    "Capability",
    "InvocationStrategy",
    "ToolCharacteristics",
    # 基类
    "BaseTool",
    "LegacyToolAdapter",
    # 工厂函数
    "create_tool_context",
]
