"""
ToolExecutor - 工具执行器

职责：
1. 配置驱动：从 CapabilityRegistry 加载工具
2. 自动注册：从 capabilities.yaml 自动加载工具实现
3. 依赖注入：通过 tool_context 注入 memory、event_manager 等
4. 动态加载：支持运行时加载新工具
5. 统一接口：所有工具通过相同方式执行

使用方式：
1. 在 capabilities.yaml 中添加工具配置
2. 实现工具类（放在 tools/ 目录）
3. 工具会自动加载

注意：
- 能力管理使用 core/tool/capability/ 子包
- 具体工具实现在 tools/ 目录下
"""

# 1. 标准库
import asyncio
import inspect
import json
from importlib import import_module
from typing import Dict, Any, Optional, List, Callable, AsyncGenerator

# 2. 第三方库（无）

# 3. 本地模块
from core.tool.capability import (
    CapabilityRegistry,
    CapabilityType,
    Capability,
    create_capability_registry
)
from core.tool.result_compactor import ResultCompactor, create_result_compactor
from infra.sandbox import (
    get_sandbox_provider,
    SandboxNotAvailableError,
    SandboxNotFoundError,
    SandboxConnectionError,
)
from logger import get_logger

logger = get_logger(__name__)


class ToolExecutor:
    """
    配置驱动的工具执行器
    
    从 CapabilityRegistry 加载工具，动态执行
    """
    
    # Claude Server-side 工具（由 Anthropic 服务器处理，不需要本地执行）
    # 🆕 仅保留 code_execution 用于 Skills 功能
    # web_search/memory 已移除，改用客户端工具（tavily_search, Mem0）
    CLAUDE_SERVER_TOOLS = {
        "code_execution",  # 代码执行在 Anthropic 沙箱中（Skills 需要）
    }
    
    # Claude Client-side 工具（需要本地执行！）
    # 🆕 bash, text_editor 已移除，统一使用自定义沙盒工具
    # sandbox_run_command 替代 bash
    # sandbox_write_file 替代 text_editor
    CLAUDE_CLIENT_TOOLS: set = set()  # 不再需要客户端工具
    
    def __init__(
        self, 
        registry: Optional[CapabilityRegistry] = None,
        tool_context: Optional[Dict[str, Any]] = None,
        enable_compaction: bool = True
    ):
        """
        初始化工具执行器
        
        Args:
            registry: 能力注册表（如果为 None 则自动创建）
            tool_context: 工具上下文（用于依赖注入）
                - memory: WorkingMemory 实例
                - event_manager: EventManager 实例
                - apis_config: 预配置的 API 列表
            enable_compaction: 是否启用结果精简（默认 True）
        """
        self.registry = registry or create_capability_registry()
        self.tool_context = tool_context or {}
        self._tool_instances: Dict[str, Any] = {}
        self._tool_handlers: Dict[str, Callable] = {}
        
        # 🆕 结果精简器（Context Engineering 优化）
        # 从 capabilities.yaml 自动加载精简规则
        self.enable_compaction = enable_compaction
        self.result_compactor = create_result_compactor(
            capability_registry=self.registry
        ) if enable_compaction else None
        
        self._load_tools()
    
    def update_context(self, context_updates: Dict[str, Any]):
        """
        🆕 V7.1: 更新工具上下文
        
        用于 Agent 克隆时更新 event_manager 等会话级依赖
        
        Args:
            context_updates: 要更新的上下文字段
        """
        self.tool_context.update(context_updates)
        logger.debug(f"🔧 ToolExecutor 上下文已更新: {list(context_updates.keys())}")
    
    def _load_tools(self):
        """从 Registry 加载所有工具"""
        tool_caps = self.registry.find_by_type(CapabilityType.TOOL)
        
        for cap in tool_caps:
            tool_name = cap.name
            
            if cap.provider == "system":
                # 系统工具（Claude 原生）- 不需要实例化
                self._tool_instances[tool_name] = None
            elif cap.provider == "user":
                # 用户自定义工具 - 尝试动态加载
                self._load_custom_tool(cap)
    
    def _load_custom_tool(self, cap: Capability):
        """
        动态加载自定义工具（支持依赖注入）
        
        从 capabilities.yaml 的 implementation 配置加载工具类
        """
        tool_name = cap.name
        
        # 从 capabilities.yaml 的 implementation 配置加载
        implementation = cap.metadata.get("implementation")
        if implementation:
            try:
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
                
                # 依赖注入
                init_params = self._get_init_params(tool_class)
                kwargs = self._resolve_dependencies(init_params, tool_name)
                
                # 实例化
                if kwargs:
                    self._tool_instances[tool_name] = tool_class(**kwargs)
                    logger.info(f"✅ 加载工具: {tool_name} (依赖: {list(kwargs.keys())})")
                else:
                    self._tool_instances[tool_name] = tool_class()
                    logger.info(f"✅ 加载工具: {tool_name}")
                return
            
            except Exception as e:
                logger.error(f"❌ 加载工具 {tool_name} 失败: {e}")
        
        # 未找到 implementation 配置
        logger.warning(f"⚠️ 工具 {tool_name} 无 implementation 配置，跳过")
        self._tool_instances[tool_name] = None
    
    def _get_init_params(self, tool_class) -> List[str]:
        """获取工具类构造函数的参数名"""
        try:
            sig = inspect.signature(tool_class.__init__)
            return [p for p in sig.parameters.keys() if p != 'self']
        except Exception:
            return []
    
    def _resolve_dependencies(self, params: List[str], tool_name: str) -> Dict[str, Any]:
        """
        根据参数名从 tool_context 解析依赖
        
        注入的依赖：
        - memory: WorkingMemory 实例
        - event_manager: EventManager 实例
        - apis_config: 预配置的 API 列表（用于 api_calling）
        """
        kwargs = {}
        
        param_mapping = {
            "memory": "memory",
            "event_manager": "event_manager",
            "apis_config": "apis_config",  # 🆕 用于 api_calling 自动注入认证
        }
        
        for param in params:
            if param in param_mapping:
                context_key = param_mapping[param]
                # 注意：使用 `is not None` 而不是 truthy 检查，避免空列表被跳过
                if context_key in self.tool_context and self.tool_context[context_key] is not None:
                    kwargs[param] = self.tool_context[context_key]
        
        return kwargs
    
    def register_handler(self, tool_name: str, handler: Callable):
        """
        注册自定义工具处理器
        
        Args:
            tool_name: 工具名称
            handler: 处理函数 async def handler(tool_input: Dict) -> Dict
        """
        self._tool_handlers[tool_name] = handler
    
    async def execute(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        skip_compaction: bool = False
    ) -> Dict[str, Any]:
        """
        执行工具
        
        Args:
            tool_name: 工具名称
            tool_input: 工具输入参数
            skip_compaction: 是否跳过结果精简（默认 False）
            
        Returns:
            执行结果字典（可能经过精简）
        """
        # 0. Claude Server-side 工具（由 Anthropic 处理）
        if tool_name in self.CLAUDE_SERVER_TOOLS:
            return {
                "success": True,
                "message": f"Server tool {tool_name} is handled by Anthropic",
                "handled_by": "anthropic_server"
            }
        
        # 0.1 Claude Client-side 工具（需要本地执行！）
        if tool_name in self.CLAUDE_CLIENT_TOOLS:
            result = await self._execute_client_tool(tool_name, tool_input)
            return self._maybe_compact(tool_name, result, skip_compaction)
        
        # 1. 自定义处理器
        if tool_name in self._tool_handlers:
            try:
                handler = self._tool_handlers[tool_name]
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(tool_input)
                else:
                    result = handler(tool_input)
                return self._maybe_compact(tool_name, result, skip_compaction)
            except Exception as e:
                return {"success": False, "error": f"Handler error: {str(e)}"}
        
        # 2. Registry 中的工具
        cap = self.registry.get(tool_name)
        if not cap or cap.type != CapabilityType.TOOL:
            return {"success": False, "error": f"Tool {tool_name} not found"}
        
        # 3. 系统工具：直接返回 tool_input 作为结果
        # 这样 ZenO 适配器可以统一从 tool_result 中提取数据
        if cap.provider == "system":
            return {
                "success": True,
                "handled_by": "claude",
                **tool_input  # 把 tool_input 中的字段合并到结果中
            }
        
        # 4. 用户自定义工具
        tool_instance = self._tool_instances.get(tool_name)
        if not tool_instance:
            return {"success": False, "error": f"Tool {tool_name} not loaded"}
        
        try:
            result = await self._execute_tool_instance(tool_name, tool_instance, tool_input)
            # 🆕 应用结果精简
            return self._maybe_compact(tool_name, result, skip_compaction)
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def supports_stream(self, tool_name: str) -> bool:
        """
        检查工具是否支持流式执行
        
        Args:
            tool_name: 工具名称
            
        Returns:
            是否支持流式执行
        """
        tool_instance = self._tool_instances.get(tool_name)
        if not tool_instance:
            return False
        
        # 检查工具是否实现了 execute_stream 方法
        return hasattr(tool_instance, 'execute_stream') and callable(getattr(tool_instance, 'execute_stream'))
    
    async def execute_stream(
        self,
        tool_name: str,
        tool_input: Dict[str, Any]
    ) -> AsyncGenerator[str, None]:
        """
        流式执行工具
        
        如果工具支持 execute_stream()，则流式返回结果。
        否则回退到普通执行，一次性返回完整结果。
        
        Args:
            tool_name: 工具名称
            tool_input: 工具输入参数
            
        Yields:
            字符串片段（工具结果的增量内容）
        """
        tool_instance = self._tool_instances.get(tool_name)
        
        # 如果工具支持流式执行
        if tool_instance and hasattr(tool_instance, 'execute_stream'):
            execute_stream_method = getattr(tool_instance, 'execute_stream')
            # 检测是否为 async generator 函数或协程函数
            if inspect.isasyncgenfunction(execute_stream_method) or asyncio.iscoroutinefunction(execute_stream_method):
                try:
                    # 流式执行（与 _execute_tool_instance 保持一致，直接传入 tool_input）
                    async for chunk in execute_stream_method(**tool_input):
                        yield chunk
                    return
                except Exception as e:
                    logger.error(f"流式执行工具 {tool_name} 失败: {e}", exc_info=True)
                    yield json.dumps({"error": str(e)})
                    return
        
        # 回退到非流式执行
        logger.debug(f"工具 {tool_name} 不支持流式，回退到非流式执行")
        result = await self.execute(tool_name, tool_input, skip_compaction=True)
        yield json.dumps(result, ensure_ascii=False)
    
    def _maybe_compact(
        self,
        tool_name: str,
        result: Dict[str, Any],
        skip_compaction: bool = False
    ) -> Dict[str, Any]:
        """
        根据配置决定是否精简结果
        
        Args:
            tool_name: 工具名称
            result: 原始结果
            skip_compaction: 是否跳过精简
            
        Returns:
            可能经过精简的结果
        """
        # 如果禁用精简或跳过精简，直接返回原始结果
        if not self.enable_compaction or skip_compaction or not self.result_compactor:
            return result
        
        # 错误结果不精简
        if not result.get("success", True) and "error" in result:
            return result
        
        # 应用精简
        return self.result_compactor.compact(tool_name, result)
    
    async def _execute_tool_instance(
        self,
        tool_name: str,
        tool_instance: Any,
        tool_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行工具实例"""
        # 特殊处理：slidespeak_render
        if tool_name == "slidespeak_render":
            if "config" in tool_input:
                return await tool_instance.execute(
                    config=tool_input["config"],
                    save_dir=tool_input.get("save_dir")
                )
            else:
                return await tool_instance.execute(config=tool_input, save_dir=None)
        
        # 通用处理
        if hasattr(tool_instance, 'execute'):
            execute_method = getattr(tool_instance, 'execute')
            
            # 🆕 依赖注入：从 tool_context 解析依赖参数
            sig = inspect.signature(execute_method)
            params = [p for p in sig.parameters.keys() if p != 'self']
            injected_kwargs = self._resolve_dependencies(params, tool_name)
            
            # 合并：tool_input 优先级更高（显式传入的参数覆盖注入的）
            final_kwargs = {**injected_kwargs, **tool_input}
            
            if asyncio.iscoroutinefunction(execute_method):
                return await execute_method(**final_kwargs)
            else:
                return execute_method(**final_kwargs)
        
        if callable(tool_instance):
            return tool_instance(**tool_input)
        
        return {"success": False, "error": f"Tool {tool_name} has no execute method"}
    
    async def _execute_client_tool(
        self,
        tool_name: str,
        tool_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        执行 Claude Client-side 工具（已废弃）
        
        🆕 bash/text_editor 已移除，统一使用自定义沙盒工具：
        - sandbox_run_command 替代 bash
        - sandbox_write_file 替代 text_editor
        
        此方法保留仅用于向后兼容，正常流程不会调用
        """
        logger.warning(
            f"⚠️ _execute_client_tool 被调用但已废弃: {tool_name}，"
            f"请改用 sandbox_run_command 或 sandbox_write_file"
        )
        return {
            "success": False, 
            "error": f"工具 {tool_name} 已废弃，请使用 sandbox_run_command 或 sandbox_write_file"
        }
    
    def get_available_tools(self) -> Dict[str, Dict]:
        """获取所有可用工具及其信息"""
        tools = {}
        
        for cap in self.registry.find_by_type(CapabilityType.TOOL):
            tools[cap.name] = {
                "description": cap.metadata.get('description', ''),
                "provider": cap.provider,
                "subtype": cap.subtype,
                "input_schema": cap.input_schema,
                "loaded": cap.name in self._tool_instances and self._tool_instances[cap.name] is not None
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
        
        # 🆕 精简器状态
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
        """
        获取结果精简统计信息
        
        Returns:
            精简统计字典，如果禁用则返回 None
        """
        if self.result_compactor:
            return self.result_compactor.get_stats()
        return None
    
    def reset_compaction_stats(self):
        """重置结果精简统计"""
        if self.result_compactor:
            self.result_compactor.reset_stats()


def create_tool_executor(
    registry: CapabilityRegistry = None,
    tool_context: Dict[str, Any] = None,
    enable_compaction: bool = True
) -> ToolExecutor:
    """
    创建工具执行器
    
    Args:
        registry: 能力注册表
        tool_context: 工具上下文（用于依赖注入）
        enable_compaction: 是否启用结果精简（默认 True，推荐）
        
    Returns:
        ToolExecutor 实例
    """
    return ToolExecutor(
        registry=registry, 
        tool_context=tool_context,
        enable_compaction=enable_compaction
    )

