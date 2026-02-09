"""
ToolExecutor - 工具执行器

合并自：
- core/tool/executor.py (原 ToolExecutor)
- core/tool/capability/invocation.py (InvocationSelector)

职责：
1. 执行工具调用
2. 管理工具实例
3. 结果压缩（可选）
4. 调用策略选择（原 InvocationSelector）

设计原则：
- 单一职责：工具执行和策略选择
- 显式依赖：通过 ToolContext 传递依赖，不使用魔法反射
- 简单直接：线性执行流程，易于理解和调试
"""

import asyncio
import json
from importlib import import_module
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

from core.context.compaction.tool_result import ToolResultCompressor
from core.tool.types import (
    BaseTool,
    Capability,
    CapabilityType,
    InvocationStrategy,
    InvocationType,
    LegacyToolAdapter,
    ToolContext,
    create_tool_context,
)
from logger import get_logger

logger = get_logger(__name__)


# 延迟导入，避免循环依赖
def _get_registry():
    from core.tool.registry import get_capability_registry

    return get_capability_registry()


class ToolExecutor:
    """
    工具执行器（合并 InvocationSelector）

    从 CapabilityRegistry 加载工具配置，执行工具调用。
    使用 ToolContext 显式传递依赖，不使用反射魔法。

    使用方式:
        executor = ToolExecutor(registry)

        # 执行工具
        result = await executor.execute("api_calling", params)

        # 流式执行
        async for chunk in executor.execute_stream("api_calling", params):
            print(chunk)

        # 选择调用策略（原 InvocationSelector）
        strategy = executor.select_invocation_strategy(
            task_type="multi_tool",
            selected_tools=["tool1", "tool2", "tool3"]
        )
    """

    # 大参数阈值 (10KB)
    LARGE_INPUT_THRESHOLD = 10 * 1024

    def __init__(
        self,
        registry=None,
        tool_context: Optional[ToolContext] = None,
        enable_compaction: bool = True,
        enable_programmatic: bool = True,
        enable_streaming: bool = True,
    ):
        """
        初始化工具执行器

        Args:
            registry: 能力注册表（如果为 None 则使用单例）
            tool_context: 工具上下文（用于依赖传递）
            enable_compaction: 是否启用结果精简（默认 True）
            enable_programmatic: 是否启用程序化调用（原 InvocationSelector）
            enable_streaming: 是否启用流式调用（原 InvocationSelector）
        """
        self._registry = registry
        self._context = tool_context or create_tool_context()
        self._tool_instances: Dict[str, Any] = {}
        self._tool_handlers: Dict[str, Callable] = {}

        # 调用策略配置（原 InvocationSelector）
        self.enable_programmatic = enable_programmatic
        self.enable_streaming = enable_streaming

        # 工具结果压缩器（统一的 ToolResultCompressor）
        self.enable_compaction = enable_compaction
        self.compressor = ToolResultCompressor() if enable_compaction else None

        self._load_tools()

    @property
    def registry(self):
        """延迟获取 Registry（避免循环导入）"""
        if self._registry is None:
            self._registry = _get_registry()
        return self._registry

    @registry.setter
    def registry(self, value):
        """设置 Registry"""
        self._registry = value

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
        **extra,
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

        except (ModuleNotFoundError, ImportError) as e:
            logger.warning(
                "⚠️ 工具 %s 未安装或未实现，已跳过: %s. 若需使用请安装对应依赖或实现该模块。",
                tool_name,
                e,
            )
            self._tool_instances[tool_name] = None
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
        skip_compaction: bool = False,
        tool_id: Optional[str] = None,
    ) -> Any:
        """
        执行工具

        Args:
            tool_name: 工具名称
            tool_input: 工具输入参数
            context: 执行上下文（可选，默认使用实例上下文）
            skip_compaction: 是否跳过结果精简
            tool_id: 工具调用 ID（用于压缩后的引用）

        Returns:
            执行结果（dict 或多模态 content blocks list）
        """
        ctx = context or self._context
        # 如果没有传入 tool_id，生成一个临时 ID
        effective_tool_id = tool_id or f"tool_{id(tool_input)}"

        # 1. 自定义处理器优先
        if tool_name in self._tool_handlers:
            try:
                handler = self._tool_handlers[tool_name]
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(tool_input, ctx)
                else:
                    result = handler(tool_input, ctx)
                return await self._maybe_compact(
                    tool_name, effective_tool_id, result, skip_compaction
                )
            except Exception as e:
                return {"success": False, "error": f"Handler error: {str(e)}"}

        # 2. 检查工具是否在 Registry 中
        cap = self.registry.get(tool_name)
        if not cap or cap.type != CapabilityType.TOOL:
            return {"success": False, "error": f"工具 {tool_name} 未找到"}

        # 3. 系统工具：直接返回 tool_input
        if cap.provider == "system":
            return {"success": True, "handled_by": "system", **tool_input}

        # 4. 用户自定义工具
        tool_instance = self._tool_instances.get(tool_name)
        if not tool_instance:
            return {"success": False, "error": f"工具 {tool_name} 未加载"}

        try:
            result = await self._execute_tool(tool_name, tool_instance, tool_input, ctx)
            return await self._maybe_compact(tool_name, effective_tool_id, result, skip_compaction)
        except Exception as e:
            logger.error(f"执行工具 {tool_name} 失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _execute_tool(
        self, tool_name: str, tool_instance: Any, tool_input: Dict[str, Any], context: ToolContext
    ) -> Any:
        """执行工具实例（返回 dict 或多模态 content blocks list）"""
        # 新式工具（BaseTool 子类）
        if isinstance(tool_instance, BaseTool):
            return await tool_instance.execute(tool_input, context)

        # 旧式工具（有 execute 方法）
        if hasattr(tool_instance, "execute"):
            execute_method = getattr(tool_instance, "execute")

            # 注入 conversation_id 和 user_id 到参数
            params = {
                "conversation_id": context.conversation_id,
                "user_id": context.user_id,
                **tool_input,
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
        return hasattr(tool_instance, "execute_stream") and callable(
            getattr(tool_instance, "execute_stream")
        )

    async def execute_stream(
        self, tool_name: str, tool_input: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> AsyncGenerator[str, None]:
        """
        流式执行工具

        如果工具支持 execute_stream()，则流式返回结果。
        否则回退到普通执行。
        """
        ctx = context or self._context
        tool_instance = self._tool_instances.get(tool_name)

        # 如果工具支持流式执行
        if tool_instance and hasattr(tool_instance, "execute_stream"):
            import inspect

            execute_stream_method = getattr(tool_instance, "execute_stream")

            if inspect.isasyncgenfunction(execute_stream_method):
                try:
                    # 新式工具（BaseTool 子类）：传递 params 和 context
                    if isinstance(tool_instance, BaseTool):
                        async for chunk in execute_stream_method(tool_input, ctx):
                            yield chunk
                    else:
                        # 旧式工具：使用 **kwargs
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

    async def _maybe_compact(
        self, tool_name: str, tool_id: str, result: Any, skip_compaction: bool = False
    ) -> Any:
        """
        根据配置决定是否压缩结果

        使用统一的 ToolResultCompressor：
        - 超过阈值则压缩
        - 完整内容存本地文件
        - 返回压缩后的文本
        """
        if not self.enable_compaction or skip_compaction or not self.compressor:
            return result

        # 多模态内容块列表（如 observe_screen 返回的 [text, image]）不压缩
        if isinstance(result, list):
            return result

        # 非 dict 结果不压缩
        if not isinstance(result, dict):
            return result

        # 错误结果不压缩
        if not result.get("success", True) and "error" in result:
            return result

        # 使用新的统一压缩器
        compressed_text, metadata = await self.compressor.compress_if_needed(
            tool_name=tool_name, tool_id=tool_id, result=result
        )

        # 如果被压缩了，返回压缩后的结果
        if metadata:
            return {
                "success": True,
                "compressed": True,
                "content": compressed_text,
                "_compression_metadata": metadata,  # 可用于更新 message.extra_data
            }

        # 未压缩，返回原结果
        return result

    def get_available_tools(self) -> Dict[str, Dict]:
        """获取所有可用工具及其信息"""
        tools = {}

        for cap in self.registry.find_by_type(CapabilityType.TOOL):
            tools[cap.name] = {
                "description": cap.metadata.get("description", ""),
                "provider": cap.provider,
                "subtype": cap.subtype,
                "input_schema": cap.input_schema,
                "loaded": (
                    cap.name in self._tool_instances and self._tool_instances[cap.name] is not None
                ),
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

        return tool_name in self._tool_instances and self._tool_instances[tool_name] is not None

    def summary(self) -> str:
        """生成工具执行器摘要"""
        tools = self.get_available_tools()

        lines = ["ToolExecutor Summary:"]
        lines.append(f"  Total tools: {len(tools)}")

        loaded_count = sum(1 for t in tools.values() if t.get("loaded"))
        lines.append(f"  Loaded: {loaded_count}")

        if self.compressor:
            stats = self.compressor.get_stats()
            lines.append(f"  Compaction: enabled (threshold={stats['threshold']})")
            if stats["total_compressed"] > 0:
                lines.append(f"    - Compressed: {stats['total_compressed']} results")
                lines.append(f"    - Bytes saved: {stats['total_bytes_saved']:,}")
        else:
            lines.append("  Compaction: disabled")

        lines.append("  Tools:")
        for name, info in tools.items():
            status = "✅" if info.get("loaded") else "⚠️"
            lines.append(f"    {status} {name} ({info['provider']})")

        return "\n".join(lines)

    def get_compaction_stats(self) -> Optional[Dict[str, Any]]:
        """获取结果压缩统计信息"""
        if self.compressor:
            return self.compressor.get_stats()
        return None

    def reset_compaction_stats(self):
        """重置结果压缩统计"""
        if self.compressor:
            self.compressor.reset_stats()

    # ==================== 调用策略选择（原 InvocationSelector）====================

    def select_invocation_strategy(
        self,
        task_type: str,
        selected_tools: List[str],
        estimated_input_size: int = 0,
        total_available_tools: int = 0,
        context: Optional[Dict[str, Any]] = None,
        plan_result: Optional[Dict[str, Any]] = None,
    ) -> Optional[InvocationStrategy]:
        """
        选择最合适的调用策略（原 InvocationSelector.select_strategy）

        Args:
            task_type: 任务类型 (simple, multi_tool, batch_processing)
            selected_tools: 选中的工具列表
            estimated_input_size: 预估输入参数大小（bytes）
            total_available_tools: 总可用工具数
            context: 额外上下文
            plan_result: Plan 阶段结果（用于检查是否匹配 Skill）

        Returns:
            InvocationStrategy: 推荐的调用策略
            None: 如果匹配到 Skill，返回 None 表示跳过
        """
        context = context or {}

        # Skill 跳过逻辑
        if plan_result and plan_result.get("recommended_skill"):
            return None

        # Fine-grained Streaming（大参数输入）
        if self.enable_streaming and estimated_input_size > self.LARGE_INPUT_THRESHOLD:
            return InvocationStrategy(
                type=InvocationType.STREAMING,
                reason=f"输入参数大小({estimated_input_size}bytes)超过阈值，使用Fine-grained Streaming",
                config={"stream_input": True, "chunk_size": 4096},
            )

        # 多工具编排 → Programmatic Tool Calling
        if (
            len(selected_tools) > 2
            and self.enable_programmatic
            and task_type in ["multi_tool", "batch_processing", "orchestration"]
        ):
            return InvocationStrategy(
                type=InvocationType.PROGRAMMATIC,
                reason=f"多工具编排({len(selected_tools)}个工具)，使用Programmatic Tool Calling减少往返",
                config={"tools": selected_tools},
            )

        # 批量处理 → Programmatic Tool Calling
        if task_type == "batch_processing" and self.enable_programmatic:
            return InvocationStrategy(
                type=InvocationType.PROGRAMMATIC,
                reason="批量处理任务，使用Programmatic Tool Calling提高效率",
                config={"batch_mode": True},
            )

        # 默认 Direct Tool Call
        return InvocationStrategy(
            type=InvocationType.DIRECT, reason="标准工具调用场景，使用Direct Tool Call", config={}
        )

    def get_tools_config_for_strategy(
        self, all_tools: List[Dict[str, Any]], strategy: InvocationStrategy
    ) -> Dict[str, Any]:
        """
        根据策略配置工具列表

        Args:
            all_tools: 所有工具定义
            strategy: 选择的策略

        Returns:
            配置好的工具配置
        """
        if strategy.type == InvocationType.STREAMING:
            return {"tools": all_tools, "stream": True, "stream_options": {"include_usage": True}}

        elif strategy.type == InvocationType.PROGRAMMATIC:
            return {"tools": all_tools, "programmatic_mode": True}

        else:
            return {"tools": all_tools}


def create_tool_executor(
    registry=None,
    tool_context: ToolContext = None,
    enable_compaction: bool = True,
    enable_programmatic: bool = True,
    enable_streaming: bool = True,
) -> ToolExecutor:
    """
    创建工具执行器

    Args:
        registry: 能力注册表（可选，默认使用单例）
        tool_context: 工具上下文
        enable_compaction: 是否启用结果精简
        enable_programmatic: 是否启用程序化调用
        enable_streaming: 是否启用流式调用

    Returns:
        ToolExecutor 实例
    """
    return ToolExecutor(
        registry=registry,
        tool_context=tool_context,
        enable_compaction=enable_compaction,
        enable_programmatic=enable_programmatic,
        enable_streaming=enable_streaming,
    )


# ==================== 导出 ====================

__all__ = [
    "ToolExecutor",
    "create_tool_executor",
]
