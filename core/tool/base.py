"""
工具基础接口定义

设计原则：
1. 显式依赖：通过 ToolContext 传递依赖，不使用魔法反射
2. 统一接口：所有工具实现相同的 execute(params, context) 方法
3. 向后兼容：支持旧式工具（无 context 参数）的适配
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from core.memory.working import WorkingMemory
    from core.events.manager import EventManager


@dataclass
class ToolContext:
    """
    工具执行上下文
    
    显式传递所有依赖，不再使用 inspect 魔法注入。
    工具可以按需从 context 中获取所需依赖。
    
    Attributes:
        session_id: 会话 ID
        conversation_id: 对话 ID（用于沙盒工具等需要关联对话的场景）
        user_id: 用户 ID
        memory: 工作记忆实例（可选）
        event_manager: 事件管理器实例（可选）
        apis_config: 预配置的 API 列表（用于 api_calling 等工具）
        extra: 扩展字段，用于传递其他自定义数据
    """
    session_id: str = ""
    conversation_id: str = ""
    user_id: str = "default_user"
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


class BaseTool(ABC):
    """
    工具基类（新版接口）
    
    所有工具应继承此类并实现 execute 方法。
    
    示例：
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
    """
    
    # 子类需要定义这些属性
    name: str = ""
    description: str = ""
    input_schema: Optional[Dict[str, Any]] = None
    
    @abstractmethod
    async def execute(
        self,
        params: Dict[str, Any],
        context: ToolContext
    ) -> Dict[str, Any]:
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
                "input_schema": self.input_schema
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
        if hasattr(legacy_tool, 'name'):
            self.name = (
                legacy_tool.name() if callable(legacy_tool.name) 
                else legacy_tool.name
            )
        
        if hasattr(legacy_tool, 'description'):
            self.description = (
                legacy_tool.description() if callable(legacy_tool.description)
                else legacy_tool.description
            )
        
        if hasattr(legacy_tool, 'parameters'):
            params = (
                legacy_tool.parameters() if callable(legacy_tool.parameters)
                else legacy_tool.parameters
            )
            self.input_schema = params
    
    async def execute(
        self,
        params: Dict[str, Any],
        context: ToolContext
    ) -> Dict[str, Any]:
        """
        执行旧工具
        
        将 context 中的关键字段注入到 params 中，然后调用旧工具
        """
        # 注入 context 中的关键字段到 params
        injected_params = {
            "conversation_id": context.conversation_id,
            "user_id": context.user_id,
            **params
        }
        
        # 调用旧工具的 execute 方法
        execute_method = getattr(self._legacy_tool, 'execute', None)
        if execute_method is None:
            return {"success": False, "error": "工具没有 execute 方法"}
        
        import asyncio
        if asyncio.iscoroutinefunction(execute_method):
            return await execute_method(**injected_params)
        else:
            return execute_method(**injected_params)
    
    @property
    def legacy_tool(self) -> Any:
        """获取底层旧工具实例"""
        return self._legacy_tool


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
    创建工具上下文（工厂函数）
    
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
        extra=extra
    )
