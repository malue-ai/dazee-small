"""
ToolExecutor - 工具执行器

职责：
1. 执行工具调用
2. 管理工具实例
3. 结果压缩（可选）

设计原则：
- 单一职责：只负责执行，不负责加载（加载由 Registry 处理）
- 显式依赖：通过 ToolContext 传递依赖，不使用魔法反射
- 简单直接：线性执行流程，易于理解和调试
"""

import asyncio
import json
from importlib import import_module
from typing import Dict, Any, Optional, List, Callable, AsyncGenerator

from core.tool.base import BaseTool, ToolContext, LegacyToolAdapter, create_tool_context
from core.tool.capability import (
    CapabilityRegistry,
    CapabilityType,
    Capability,
    create_capability_registry
)
from core.tool.result_compactor import ResultCompactor, create_result_compactor
from logger import get_logger

logger = get_logger(__name__)


class ToolExecutor:
    """
    工具执行器
    
    从 CapabilityRegistry 加载工具配置，执行工具调用。
    使用 ToolContext 显式传递依赖，不使用反射魔法。
    """
    
    def __init__(
        self, 
        registry: Optional[CapabilityRegistry] = None,
        tool_context: Optional[ToolContext] = None,
        enable_compaction: bool = True
    ):
        """
        初始化工具执行器
        
        Args:
            registry: 能力注册表（如果为 None 则自动创建）
            tool_context: 工具上下文（用于依赖传递）
            enable_compaction: 是否启用结果精简（默认 True）
        """
        self.registry = registry or create_capability_registry()
        self._context = tool_context or create_tool_context()
        self._tool_instances: Dict[str, Any] = {}
        self._tool_handlers: Dict[str, Callable] = {}
        
        # 结果精简器
        self.enable_compaction = enable_compaction
        self.result_compactor = create_result_compactor(
            capability_registry=self.registry
        ) if enable_compaction else None
        
        self._load_tools()
    
    @property
    def tool_context(self) -> ToolContext:
        """获取当前工具上下文"""
        return self._context
    
    def update_context(
        self,
        session_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        memory: Optional[Any] = None,
        event_manager: Optional[Any] = None,
        apis_config: Optional[List[Dict]] = None,
        **extra
    ):
        """
        更新工具上下文
        
        用于 Agent 克隆或会话切换时更新上下文。
        只更新传入的非 None 字段。
        """
        if session_id is not None:
            self._context.session_id = session_id
        if conversation_id is not None:
            self._context.conversation_id = conversation_id
        if user_id is not None:
            self._context.user_id = user_id
        if memory is not None:
            self._context.memory = memory
        if event_manager is not None:
            self._context.event_manager = event_manager
        if apis_config is not None:
            self._context.apis_config = apis_config
        
        # 更新扩展字段
        for key, value in extra.items():
            self._context.set(key, value)
        
        logger.debug(f"工具上下文已更新: session={session_id}, conversation={conversation_id}")
    
    def _load_tools(self):
        """从 Registry 加载所有工具"""
        tool_caps = self.registry.find_by_type(CapabilityType.TOOL)
        
        for cap in tool_caps:
            tool_name = cap.name
            
            if cap.provider == "system":
                # 系统工具不需要实例化
                self._tool_instances[tool_name] = None
            elif cap.provider == "user":
                # 用户自定义工具 - 动态加载
                self._load_custom_tool(cap)
    
    def _load_custom_tool(self, cap: Capability):
        """
        动态加载自定义工具
        
        从 capabilities.yaml 的 implementation 配置加载工具类
        """
        tool_name = cap.name
        implementation = cap.metadata.get("implementation")
        
        if not implementation:
            logger.warning(f"工具 {tool_name} 无 implementation 配置，跳过")
            self._tool_instances[tool_name] = None
            return
        
        try:
            # 解析 implementation 配置
            if "module" in implementation and "class" in implementation:
                module_path = implementation["module"]
                class_name = implementation["class"]
            elif "path" in implementation:
                full_path = implementation["path"]
                module_path, class_name = full_path.rsplit(".", 1)
            else:
                logger.warning(f"工具 {tool_name} 的 implementation 格式无效")
                self._tool_instances[tool_name] = None
                return
            
            # 动态导入
            module = import_module(module_path)
            tool_class = getattr(module, class_name)
            
            # 实例化工具（不再使用魔法注入，工具自己负责获取依赖）
            tool_instance = tool_class()
            
            # 检查是否是新式工具（继承 BaseTool 且接受 context）
            # 如果是旧式工具，用适配器包装
            if not isinstance(tool_instance, BaseTool):
                tool_instance = LegacyToolAdapter(tool_instance)
            
            self._tool_instances[tool_name] = tool_instance
            logger.info(f"✅ 加载工具: {tool_name}")
            
        except Exception as e:
            logger.error(f"❌ 加载工具 {tool_name} 失败: {e}")
            self._tool_instances[tool_name] = None
    
    def register_handler(self, tool_name: str, handler: Callable):
        """
        注册自定义工具处理器
        
        Args:
            tool_name: 工具名称
            handler: 处理函数 async def handler(params: Dict, context: ToolContext) -> Dict
        """
        self._tool_handlers[tool_name] = handler
    
    async def execute(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        context: Optional[ToolContext] = None,
        skip_compaction: bool = False
    ) -> Dict[str, Any]:
        """
        执行工具
        
        Args:
            tool_name: 工具名称
            tool_input: 工具输入参数
            context: 执行上下文（可选，默认使用实例上下文）
            skip_compaction: 是否跳过结果精简
            
        Returns:
            执行结果字典
        """
        ctx = context or self._context
        
        # 1. 自定义处理器优先
        if tool_name in self._tool_handlers:
            try:
                handler = self._tool_handlers[tool_name]
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(tool_input, ctx)
                else:
                    result = handler(tool_input, ctx)
                return self._maybe_compact(tool_name, result, skip_compaction)
            except Exception as e:
                return {"success": False, "error": f"Handler error: {str(e)}"}
        
        # 2. 检查工具是否在 Registry 中
        cap = self.registry.get(tool_name)
        if not cap or cap.type != CapabilityType.TOOL:
            return {"success": False, "error": f"工具 {tool_name} 未找到"}
        
        # 3. 系统工具：直接返回 tool_input
        if cap.provider == "system":
            return {
                "success": True,
                "handled_by": "system",
                **tool_input
            }
        
        # 4. 用户自定义工具
        tool_instance = self._tool_instances.get(tool_name)
        if not tool_instance:
            return {"success": False, "error": f"工具 {tool_name} 未加载"}
        
        try:
            result = await self._execute_tool(tool_name, tool_instance, tool_input, ctx)
            return self._maybe_compact(tool_name, result, skip_compaction)
        except Exception as e:
            logger.error(f"执行工具 {tool_name} 失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def _execute_tool(
        self,
        tool_name: str,
        tool_instance: Any,
        tool_input: Dict[str, Any],
        context: ToolContext
    ) -> Dict[str, Any]:
        """执行工具实例"""
        # 新式工具（BaseTool 子类）
        if isinstance(tool_instance, BaseTool):
            return await tool_instance.execute(tool_input, context)
        
        # 旧式工具（有 execute 方法）
        if hasattr(tool_instance, 'execute'):
            execute_method = getattr(tool_instance, 'execute')
            
            # 注入 conversation_id 和 user_id 到参数
            params = {
                "conversation_id": context.conversation_id,
                "user_id": context.user_id,
                **tool_input
            }
            
            if asyncio.iscoroutinefunction(execute_method):
                return await execute_method(**params)
            else:
                return execute_method(**params)
        
        # 可调用对象
        if callable(tool_instance):
            return tool_instance(**tool_input)
        
        return {"success": False, "error": f"工具 {tool_name} 没有 execute 方法"}
    
    def supports_stream(self, tool_name: str) -> bool:
        """检查工具是否支持流式执行"""
        tool_instance = self._tool_instances.get(tool_name)
        if not tool_instance:
            return False
        return hasattr(tool_instance, 'execute_stream') and callable(
            getattr(tool_instance, 'execute_stream')
        )
    
    async def execute_stream(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        context: Optional[ToolContext] = None
    ) -> AsyncGenerator[str, None]:
        """
        流式执行工具
        
        如果工具支持 execute_stream()，则流式返回结果。
        否则回退到普通执行。
        """
        ctx = context or self._context
        tool_instance = self._tool_instances.get(tool_name)
        
        # 如果工具支持流式执行
        if tool_instance and hasattr(tool_instance, 'execute_stream'):
            import inspect
            execute_stream_method = getattr(tool_instance, 'execute_stream')
            
            if inspect.isasyncgenfunction(execute_stream_method):
                try:
                    async for chunk in execute_stream_method(**tool_input):
                        yield chunk
                    return
                except Exception as e:
                    logger.error(f"流式执行工具 {tool_name} 失败: {e}", exc_info=True)
                    yield json.dumps({"error": str(e)})
                    return
        
        # 回退到非流式执行
        logger.debug(f"工具 {tool_name} 不支持流式，回退到非流式执行")
        result = await self.execute(tool_name, tool_input, ctx, skip_compaction=True)
        yield json.dumps(result, ensure_ascii=False)
    
    def _maybe_compact(
        self,
        tool_name: str,
        result: Dict[str, Any],
        skip_compaction: bool = False
    ) -> Dict[str, Any]:
        """根据配置决定是否精简结果"""
        if not self.enable_compaction or skip_compaction or not self.result_compactor:
            return result
        
        # 错误结果不精简
        if not result.get("success", True) and "error" in result:
            return result
        
        return self.result_compactor.compact(tool_name, result)
    
    def get_available_tools(self) -> Dict[str, Dict]:
        """获取所有可用工具及其信息"""
        tools = {}
        
        for cap in self.registry.find_by_type(CapabilityType.TOOL):
            tools[cap.name] = {
                "description": cap.metadata.get('description', ''),
                "provider": cap.provider,
                "subtype": cap.subtype,
                "input_schema": cap.input_schema,
                "loaded": (
                    cap.name in self._tool_instances and 
                    self._tool_instances[cap.name] is not None
                )
            }
        
        return tools
    
    def get_tool_schemas(self) -> List[Dict]:
        """获取所有工具的 Schema（用于 Claude API）"""
        return self.registry.get_tool_schemas()
    
    def is_tool_available(self, tool_name: str) -> bool:
        """检查工具是否可用"""
        cap = self.registry.get(tool_name)
        if not cap or cap.type != CapabilityType.TOOL:
            return False
        
        if cap.provider == "system":
            return True
        
        return (
            tool_name in self._tool_instances and 
            self._tool_instances[tool_name] is not None
        )
    
    def summary(self) -> str:
        """生成工具执行器摘要"""
        tools = self.get_available_tools()
        
        lines = ["ToolExecutor Summary:"]
        lines.append(f"  Total tools: {len(tools)}")
        
        loaded_count = sum(1 for t in tools.values() if t.get('loaded'))
        lines.append(f"  Loaded: {loaded_count}")
        
        if self.result_compactor:
            stats = self.result_compactor.get_stats()
            lines.append(f"  Compaction: enabled ({stats['rules_count']} rules)")
            if stats['total_compacted'] > 0:
                lines.append(f"    - Compacted: {stats['total_compacted']} results")
                lines.append(f"    - Bytes saved: {stats['total_bytes_saved']:,}")
        else:
            lines.append("  Compaction: disabled")
        
        lines.append("  Tools:")
        for name, info in tools.items():
            status = "✅" if info.get('loaded') else "⚠️"
            lines.append(f"    {status} {name} ({info['provider']})")
        
        return "\n".join(lines)
    
    def get_compaction_stats(self) -> Optional[Dict[str, Any]]:
        """获取结果精简统计信息"""
        if self.result_compactor:
            return self.result_compactor.get_stats()
        return None
    
    def reset_compaction_stats(self):
        """重置结果精简统计"""
        if self.result_compactor:
            self.result_compactor.reset_stats()


def create_tool_executor(
    registry: CapabilityRegistry = None,
    tool_context: ToolContext = None,
    enable_compaction: bool = True
) -> ToolExecutor:
    """
    创建工具执行器
    
    Args:
        registry: 能力注册表
        tool_context: 工具上下文
        enable_compaction: 是否启用结果精简
        
    Returns:
        ToolExecutor 实例
    """
    return ToolExecutor(
        registry=registry, 
        tool_context=tool_context,
        enable_compaction=enable_compaction
    )
