"""
工具服务层 - Tool Service

职责：
1. 工具注册与管理（User-defined 工具）
2. 工具执行（直接返回 / 流式返回）
3. 工具状态监控

设计原则：
- 不包含 HTTP 相关逻辑（由 router 层处理）
- 支持多种工具类型和返回模式
- 统一的错误处理（抛出业务异常）

注意：MCP 工具管理已迁移到以下模块：
- services/mcp_client.py - MCPClientWrapper（使用官方 MCP SDK）
- infra/pools/mcp_pool.py - MCP 连接池管理
- core/tool/instance_registry.py - 实例级工具注册表
"""

import asyncio
import importlib
from typing import Dict, Any, Optional, List, Callable, AsyncIterator
from datetime import datetime

from logger import get_logger
from models.tool import (
    # 枚举
    ToolType,
    ReturnMode,
    ToolStatus,
    ExecutionStatus,
    # 工具定义
    ToolInputSchema,
    ToolDefinition,
    # 工具执行
    ToolInvocation,
    ToolResultChunk,
    ToolResult,
    # 工具注册
    ToolRegistration,
    ToolRegistrationResponse,
    # 工具查询
    ToolListQuery,
    ToolListResponse,
    ToolDetailResponse,
)

logger = get_logger("tool_service")


# ============================================================
# 异常定义
# ============================================================

class ToolServiceError(Exception):
    """工具服务异常基类"""
    pass


class ToolNotFoundError(ToolServiceError):
    """工具不存在异常"""
    pass


class ToolAlreadyExistsError(ToolServiceError):
    """工具已存在异常"""
    pass


class ToolExecutionError(ToolServiceError):
    """工具执行失败异常"""
    pass


class ToolRegistrationError(ToolServiceError):
    """工具注册失败异常"""
    pass


# ============================================================
# 工具处理器协议
# ============================================================

class ToolHandler:
    """
    工具处理器基类
    
    用户自定义工具需要实现此接口
    """
    
    async def execute(self, **kwargs) -> Any:
        """
        执行工具（直接返回）
        
        Args:
            **kwargs: 工具输入参数
            
        Returns:
            执行结果
        """
        raise NotImplementedError
    
    async def execute_streaming(self, **kwargs) -> AsyncIterator[ToolResultChunk]:
        """
        执行工具（流式返回）
        
        Args:
            **kwargs: 工具输入参数
            
        Yields:
            ToolResultChunk 流式结果块
        """
        # 默认实现：将直接返回转为单个结果块
        result = await self.execute(**kwargs)
        yield ToolResultChunk(
            invocation_id=kwargs.get("_invocation_id", ""),
            chunk_index=0,
            chunk_type="data",
            content=result
        )
        yield ToolResultChunk(
            invocation_id=kwargs.get("_invocation_id", ""),
            chunk_index=1,
            chunk_type="done",
            content={"total_chunks": 2}
        )


# ============================================================
# 工具服务
# ============================================================

class ToolService:
    """
    工具服务
    
    提供工具注册、管理、执行等业务逻辑
    
    注意：MCP 工具管理已迁移到 mcp_client.py / mcp_pool.py / instance_registry.py
    """
    
    def __init__(self) -> None:
        """初始化工具服务"""
        # 工具定义存储
        self._tools: Dict[str, ToolDefinition] = {}
        
        # 工具处理器存储（User-defined 工具）
        self._handlers: Dict[str, ToolHandler] = {}
        
        # 执行统计
        self._invocation_count: Dict[str, int] = {}
        self._success_count: Dict[str, int] = {}
        self._failure_count: Dict[str, int] = {}
    
    # ==================== 工具注册 ====================
    
    def register_tool(
        self,
        definition: ToolDefinition,
        handler: Optional[ToolHandler] = None,
        replace_existing: bool = False
    ) -> ToolRegistrationResponse:
        """
        注册工具
        
        Args:
            definition: 工具定义
            handler: 工具处理器（User-defined 工具必须提供）
            replace_existing: 是否替换已存在的工具
            
        Returns:
            注册响应
            
        Raises:
            ToolAlreadyExistsError: 工具已存在且不允许替换
            ToolRegistrationError: 注册失败
        """
        tool_name = definition.name
        
        logger.info(f"📝 注册工具: name={tool_name}, type={definition.tool_type.value}")
        
        # 检查是否已存在
        if tool_name in self._tools and not replace_existing:
            raise ToolAlreadyExistsError(f"工具已存在: {tool_name}")
        
        # User-defined 工具需要处理器
        if definition.tool_type == ToolType.USER_DEFINED:
            if handler:
                self._handlers[tool_name] = handler
            elif definition.implementation:
                # 从配置动态加载处理器
                try:
                    handler = self._load_handler(definition.implementation)
                    self._handlers[tool_name] = handler
                except Exception as e:
                    raise ToolRegistrationError(f"加载处理器失败: {str(e)}") from e
            else:
                raise ToolRegistrationError(f"User-defined 工具需要提供 handler 或 implementation")
        
        # 存储工具定义
        self._tools[tool_name] = definition
        
        # 初始化统计
        if tool_name not in self._invocation_count:
            self._invocation_count[tool_name] = 0
            self._success_count[tool_name] = 0
            self._failure_count[tool_name] = 0
        
        logger.info(f"✅ 工具注册成功: {tool_name}")
        
        return ToolRegistrationResponse(
            success=True,
            tool_name=tool_name,
            message=f"工具 {tool_name} 注册成功",
            tool_definition=definition
        )
    
    def register_from_request(
        self,
        request: ToolRegistration
    ) -> ToolRegistrationResponse:
        """
        从注册请求注册工具
        
        Args:
            request: 注册请求
            
        Returns:
            注册响应
        """
        return self.register_tool(
            definition=request.definition,
            replace_existing=request.replace_existing
        )
    
    def register_function(
        self,
        name: str,
        description: str,
        func: Callable,
        input_schema: Optional[Dict[str, Any]] = None,
        return_mode: ReturnMode = ReturnMode.DIRECT,
        **kwargs
    ) -> ToolRegistrationResponse:
        """
        注册函数作为工具（简便方法）
        
        Args:
            name: 工具名称
            description: 工具描述
            func: 异步函数
            input_schema: 输入 Schema（可选，会自动推断）
            return_mode: 返回模式
            **kwargs: 其他 ToolDefinition 参数
            
        Returns:
            注册响应
        """
        # 推断 input_schema
        if input_schema is None:
            input_schema = self._infer_schema_from_function(func)
        
        # 创建定义
        definition = ToolDefinition(
            name=name,
            description=description,
            tool_type=ToolType.USER_DEFINED,
            return_mode=return_mode,
            input_schema=ToolInputSchema(**input_schema) if isinstance(input_schema, dict) else input_schema,
            **kwargs
        )
        
        # 创建处理器包装
        class FunctionHandler(ToolHandler):
            def __init__(self, fn):
                self._fn = fn
            
            async def execute(self, **kw):
                # 移除内部参数
                kw.pop("_invocation_id", None)
                if asyncio.iscoroutinefunction(self._fn):
                    return await self._fn(**kw)
                return self._fn(**kw)
        
        handler = FunctionHandler(func)
        
        return self.register_tool(definition, handler)
    
    def unregister_tool(self, tool_name: str) -> bool:
        """
        注销工具
        
        Args:
            tool_name: 工具名称
            
        Returns:
            是否成功注销
        """
        if tool_name not in self._tools:
            return False
        
        logger.info(f"🗑️ 注销工具: {tool_name}")
        
        del self._tools[tool_name]
        
        if tool_name in self._handlers:
            del self._handlers[tool_name]
        
        return True
    
    # ==================== 工具查询 ====================
    
    def get_tool(self, tool_name: str) -> Optional[ToolDefinition]:
        """
        获取工具定义
        
        Args:
            tool_name: 工具名称
            
        Returns:
            工具定义，不存在则返回 None
        """
        return self._tools.get(tool_name)
    
    def list_tools(
        self,
        query: Optional[ToolListQuery] = None
    ) -> ToolListResponse:
        """
        列出工具
        
        Args:
            query: 查询条件
            
        Returns:
            工具列表响应
        """
        tools = list(self._tools.values())
        
        # 应用过滤
        if query:
            if query.tool_type:
                tools = [t for t in tools if t.tool_type == query.tool_type]
            
            if query.category:
                tools = [t for t in tools if t.category == query.category]
            
            if query.status:
                tools = [t for t in tools if t.status == query.status]
            
            if query.keyword:
                keyword_lower = query.keyword.lower()
                tools = [
                    t for t in tools
                    if keyword_lower in t.name.lower()
                    or keyword_lower in t.description.lower()
                    or any(keyword_lower in kw.lower() for kw in t.keywords)
                ]
            
            # 分页
            total = len(tools)
            start = (query.page - 1) * query.page_size
            end = start + query.page_size
            tools = tools[start:end]
            
            return ToolListResponse(
                tools=tools,
                total=total,
                page=query.page,
                page_size=query.page_size
            )
        
        return ToolListResponse(
            tools=tools,
            total=len(tools),
            page=1,
            page_size=len(tools)
        )
    
    def get_tool_detail(self, tool_name: str) -> ToolDetailResponse:
        """
        获取工具详情（包含统计）
        
        Args:
            tool_name: 工具名称
            
        Returns:
            工具详情响应
            
        Raises:
            ToolNotFoundError: 工具不存在
        """
        definition = self._tools.get(tool_name)
        if not definition:
            raise ToolNotFoundError(f"工具不存在: {tool_name}")
        
        # 计算统计
        total = self._invocation_count.get(tool_name, 0)
        success = self._success_count.get(tool_name, 0)
        failure = self._failure_count.get(tool_name, 0)
        success_rate = (success / total * 100) if total > 0 else 0
        
        return ToolDetailResponse(
            definition=definition,
            statistics={
                "total_invocations": total,
                "success_count": success,
                "failure_count": failure,
                "success_rate": f"{success_rate:.1f}%"
            }
        )
    
    def get_claude_tool_schemas(
        self,
        tool_names: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        获取 Claude API 格式的工具 Schema
        
        Args:
            tool_names: 指定工具名称列表（None=全部）
            
        Returns:
            Claude API 兼容的工具定义列表
        """
        if tool_names:
            tools = [
                self._tools[name]
                for name in tool_names
                if name in self._tools
            ]
        else:
            tools = list(self._tools.values())
        
        return [
            tool.to_claude_schema()
            for tool in tools
            if tool.status == ToolStatus.AVAILABLE
        ]
    
    # ==================== 工具执行 ====================
    
    async def execute_tool(
        self,
        invocation: ToolInvocation
    ) -> ToolResult:
        """
        执行工具（直接返回）
        
        Args:
            invocation: 调用请求
            
        Returns:
            执行结果
        """
        tool_name = invocation.tool_name
        invocation_id = invocation.invocation_id
        
        logger.info(f"🔧 执行工具: name={tool_name}, invocation_id={invocation_id}")
        
        # 获取工具定义
        definition = self._tools.get(tool_name)
        if not definition:
            raise ToolNotFoundError(f"工具不存在: {tool_name}")
        
        # 更新统计
        self._invocation_count[tool_name] = self._invocation_count.get(tool_name, 0) + 1
        
        started_at = datetime.now()
        
        try:
            if definition.tool_type == ToolType.USER_DEFINED:
                # User-defined 工具
                result = await self._execute_user_defined_tool(
                    tool_name, invocation.input, invocation_id
                )
            else:
                # 不支持的工具类型（MCP 工具应通过 instance_registry 执行）
                raise ToolExecutionError(
                    f"不支持的工具类型: {definition.tool_type}。"
                    f"MCP 工具请通过 InstanceToolRegistry 执行。"
                )
            
            completed_at = datetime.now()
            duration_ms = int((completed_at - started_at).total_seconds() * 1000)
            
            # 更新成功统计
            self._success_count[tool_name] = self._success_count.get(tool_name, 0) + 1
            
            logger.info(f"✅ 工具执行成功: {tool_name}, duration={duration_ms}ms")
            
            return ToolResult(
                invocation_id=invocation_id,
                tool_name=tool_name,
                status=ExecutionStatus.SUCCESS,
                output=result,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms
            )
        
        except Exception as e:
            completed_at = datetime.now()
            duration_ms = int((completed_at - started_at).total_seconds() * 1000)
            
            # 更新失败统计
            self._failure_count[tool_name] = self._failure_count.get(tool_name, 0) + 1
            
            logger.error(f"❌ 工具执行失败: {tool_name} - {str(e)}", exc_info=True)
            
            return ToolResult(
                invocation_id=invocation_id,
                tool_name=tool_name,
                status=ExecutionStatus.FAILED,
                error=str(e),
                error_code="EXECUTION_ERROR",
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms
            )
    
    async def execute_tool_streaming(
        self,
        invocation: ToolInvocation
    ) -> AsyncIterator[ToolResultChunk]:
        """
        执行工具（流式返回）
        
        Args:
            invocation: 调用请求
            
        Yields:
            ToolResultChunk 流式结果块
        """
        tool_name = invocation.tool_name
        invocation_id = invocation.invocation_id
        
        logger.info(f"🔧 流式执行工具: name={tool_name}, invocation_id={invocation_id}")
        
        # 获取工具定义
        definition = self._tools.get(tool_name)
        if not definition:
            yield ToolResultChunk(
                invocation_id=invocation_id,
                chunk_index=0,
                chunk_type="error",
                content=f"工具不存在: {tool_name}"
            )
            return
        
        # 更新统计
        self._invocation_count[tool_name] = self._invocation_count.get(tool_name, 0) + 1
        
        try:
            if definition.tool_type == ToolType.USER_DEFINED:
                # User-defined 工具
                handler = self._handlers.get(tool_name)
                if not handler:
                    raise ToolExecutionError(f"工具处理器不存在: {tool_name}")
                
                # 添加 invocation_id 到参数
                input_with_id = {**invocation.input, "_invocation_id": invocation_id}
                
                async for chunk in handler.execute_streaming(**input_with_id):
                    yield chunk
            else:
                # 不支持的工具类型
                raise ToolExecutionError(
                    f"不支持的工具类型: {definition.tool_type}。"
                    f"MCP 工具请通过 InstanceToolRegistry 执行。"
                )
            
            # 更新成功统计
            self._success_count[tool_name] = self._success_count.get(tool_name, 0) + 1
        
        except Exception as e:
            # 更新失败统计
            self._failure_count[tool_name] = self._failure_count.get(tool_name, 0) + 1
            
            logger.error(f"❌ 流式执行失败: {tool_name} - {str(e)}", exc_info=True)
            
            yield ToolResultChunk(
                invocation_id=invocation_id,
                chunk_index=0,
                chunk_type="error",
                content=str(e)
            )
    
    # ==================== 内部方法 ====================
    
    async def _execute_user_defined_tool(
        self,
        tool_name: str,
        input_data: Dict[str, Any],
        invocation_id: str
    ) -> Any:
        """执行 User-defined 工具"""
        handler = self._handlers.get(tool_name)
        if not handler:
            raise ToolExecutionError(f"工具处理器不存在: {tool_name}")
        
        return await handler.execute(**input_data)
    
    def _load_handler(self, implementation: Dict[str, str]) -> ToolHandler:
        """从配置动态加载处理器"""
        module_path = implementation.get("module")
        class_name = implementation.get("class")
        
        if not module_path or not class_name:
            raise ToolRegistrationError("implementation 需要 module 和 class")
        
        try:
            module = importlib.import_module(module_path)
            handler_class = getattr(module, class_name)
            
            # 检查是否是 ToolHandler 子类或有 execute 方法
            instance = handler_class()
            
            if not hasattr(instance, "execute"):
                raise ToolRegistrationError(f"{class_name} 没有 execute 方法")
            
            # 包装为 ToolHandler
            if isinstance(instance, ToolHandler):
                return instance
            
            # 兼容旧的 BaseTool 接口
            class WrappedHandler(ToolHandler):
                def __init__(self, tool_instance):
                    self._tool = tool_instance
                
                async def execute(self, **kwargs):
                    return await self._tool.execute(**kwargs)
            
            return WrappedHandler(instance)
        
        except Exception as e:
            raise ToolRegistrationError(f"加载 {module_path}.{class_name} 失败: {str(e)}") from e
    
    def _infer_schema_from_function(self, func: Callable) -> Dict[str, Any]:
        """从函数签名推断 input_schema"""
        import inspect
        
        sig = inspect.signature(func)
        properties = {}
        required = []
        
        type_mapping = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object",
        }
        
        for name, param in sig.parameters.items():
            if name in ("self", "cls"):
                continue
            
            # 获取类型注解
            param_type = "string"
            if param.annotation != inspect.Parameter.empty:
                py_type = param.annotation
                # 处理 Optional 类型
                if hasattr(py_type, "__origin__"):
                    if py_type.__origin__ is type(None):
                        py_type = py_type.__args__[0]
                param_type = type_mapping.get(py_type, "string")
            
            properties[name] = {
                "type": param_type,
                "description": f"参数 {name}"
            }
            
            # 没有默认值的参数是必填的
            if param.default == inspect.Parameter.empty:
                required.append(name)
        
        return {
            "type": "object",
            "properties": properties,
            "required": required
        }


# ============================================================
# 便捷函数
# ============================================================

_default_service: Optional[ToolService] = None


def get_tool_service() -> ToolService:
    """获取默认工具服务单例"""
    global _default_service
    if _default_service is None:
        _default_service = ToolService()
    return _default_service


# ============================================================
# 装饰器（简便注册方式）
# ============================================================

def tool(
    name: str = None,
    description: str = "",
    return_mode: ReturnMode = ReturnMode.DIRECT,
    **kwargs
):
    """
    工具注册装饰器
    
    使用方式:
    
    @tool(name="search", description="搜索信息")
    async def search(query: str, num_results: int = 10) -> dict:
        ...
    """
    def decorator(func: Callable):
        tool_name = name or func.__name__
        tool_desc = description or func.__doc__ or ""
        
        # 延迟注册（在首次调用 get_tool_service 时）
        service = get_tool_service()
        service.register_function(
            name=tool_name,
            description=tool_desc,
            func=func,
            return_mode=return_mode,
            **kwargs
        )
        
        return func
    
    return decorator
