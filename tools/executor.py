"""
工具执行器 - V3.5版本
配置驱动，自动注册

设计原则：
1. 配置驱动：从CapabilityRegistry加载工具
2. 自动注册：从capabilities.yaml自动加载工具实现
3. 动态加载：支持运行时加载新工具
4. 统一接口：所有工具通过相同方式执行

使用方式：
1. 在capabilities.yaml中添加工具配置：
   - name: my_tool
     implementation:
       module: "agent_v3.tools.my_tool"
       class: "MyTool"
2. 实现工具类继承BaseTool
3. 无需修改此文件 - 工具会自动加载！

参考文档：
- docs/v3/04-TOOL-CALLING-STRATEGIES.md
- docs/v3/TOOL_CALLING_DECISION_FRAMEWORK.md
- TOOL_AUTO_REGISTRATION_PROPOSAL.md
"""

from typing import Dict, Any, Optional, List, Callable
from importlib import import_module
import asyncio

from agent_v3.core.capability_registry import (
    CapabilityRegistry,
    CapabilityType,
    Capability,
    create_capability_registry
)


class ToolExecutor:
    """
    配置驱动的工具执行器
    
    从CapabilityRegistry加载工具，动态执行
    """
    
    # 工具类映射：工具名 → (模块路径, 类名)
    # ⚠️ 已废弃 - 仅用于向后兼容
    # 推荐：在capabilities.yaml中使用implementation字段配置
    TOOL_CLASS_MAPPING = {
        "slidespeak_render": ("agent_v3.tools.slidespeak", "SlideSpeakTool"),
        # 添加更多工具映射...（不推荐）
    }
    
    def __init__(self, registry: Optional[CapabilityRegistry] = None):
        """
        初始化工具执行器
        
        Args:
            registry: 能力注册表（如果为None则自动创建）
        """
        self.registry = registry or create_capability_registry()
        self._tool_instances: Dict[str, Any] = {}
        self._tool_handlers: Dict[str, Callable] = {}
        self._load_tools()
    
    def _load_tools(self):
        """从Registry加载所有工具"""
        tool_caps = self.registry.find_by_type(CapabilityType.TOOL)
        
        for cap in tool_caps:
            tool_name = cap.name
            
            # 根据provider决定如何加载
            if cap.provider == "system":
                # 系统工具（Claude原生）- 不需要实例化
                self._tool_instances[tool_name] = None
            elif cap.provider == "user":
                # 用户自定义工具 - 尝试动态加载
                self._load_custom_tool(cap)
    
    def _load_custom_tool(self, cap: Capability):
        """
        动态加载自定义工具
        
        优先级：
        1. capabilities.yaml 中的 implementation 配置（推荐）
        2. TOOL_CLASS_MAPPING 硬编码映射（向后兼容）
        """
        tool_name = cap.name
        
        # 方法1：从 capabilities.yaml 的 implementation 配置加载（优先）
        implementation = cap.metadata.get("implementation")
        if implementation:
            try:
                # 支持两种配置格式：
                # 格式1: {module: "...", class: "..."}
                if "module" in implementation and "class" in implementation:
                    module_path = implementation["module"]
                    class_name = implementation["class"]
                
                # 格式2: {path: "module.path.ClassName"} (未来扩展)
                elif "path" in implementation:
                    full_path = implementation["path"]
                    module_path, class_name = full_path.rsplit(".", 1)
                
                else:
                    print(f"⚠️ Warning: Tool {tool_name} has invalid 'implementation' format")
                    self._tool_instances[tool_name] = None
                    return
                
                # 动态导入并实例化
                module = import_module(module_path)
                tool_class = getattr(module, class_name)
                self._tool_instances[tool_name] = tool_class()
                print(f"✅ Auto-loaded tool: {tool_name} from {module_path}.{class_name}")
                return
            
            except Exception as e:
                print(f"❌ Failed to load tool {tool_name} from implementation config: {e}")
                # 继续尝试方法2
        
        # 方法2：从硬编码的 TOOL_CLASS_MAPPING 加载（向后兼容）
        if tool_name in self.TOOL_CLASS_MAPPING:
            module_path, class_name = self.TOOL_CLASS_MAPPING[tool_name]
            try:
                module = import_module(module_path)
                tool_class = getattr(module, class_name)
                self._tool_instances[tool_name] = tool_class()
                print(f"✅ Loaded tool (legacy): {tool_name} from TOOL_CLASS_MAPPING")
                return
            except Exception as e:
                print(f"❌ Failed to load tool {tool_name} from TOOL_CLASS_MAPPING: {e}")
        
        # 未找到任何加载方式
        print(f"⚠️ Warning: Tool {tool_name} has no implementation config or mapping, skipped")
        self._tool_instances[tool_name] = None
    
    def register_handler(self, tool_name: str, handler: Callable):
        """
        注册自定义工具处理器
        
        Args:
            tool_name: 工具名称
            handler: 处理函数 async def handler(tool_input: Dict) -> Dict
        """
        self._tool_handlers[tool_name] = handler
    
    # Claude原生工具列表（这些工具由Claude自己处理）
    CLAUDE_NATIVE_TOOLS = {
        "bash",
        "str_replace_based_edit_tool",
        "web_search",
        "memory",
        "text_editor",
        "pptx",  # Pre-built Anthropic skill
        "code_execution"  # Beta feature
    }
    
    async def execute(
        self,
        tool_name: str,
        tool_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        执行工具
        
        Args:
            tool_name: 工具名称
            tool_input: 工具输入参数
            
        Returns:
            执行结果字典
        """
        # 0. 检查是否是Claude原生工具（直接返回成功，由Claude处理）
        if tool_name in self.CLAUDE_NATIVE_TOOLS:
            return {
                "success": True,
                "message": f"System tool {tool_name} is handled by Claude natively",
                "handled_by": "claude"
            }
        
        # 1. 检查自定义处理器
        if tool_name in self._tool_handlers:
            try:
                handler = self._tool_handlers[tool_name]
                if asyncio.iscoroutinefunction(handler):
                    return await handler(tool_input)
                else:
                    return handler(tool_input)
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Handler error: {str(e)}"
                }
        
        # 2. 检查能力注册表
        cap = self.registry.get(tool_name)
        if not cap or cap.type != CapabilityType.TOOL:
            return {
                "success": False,
                "error": f"Tool {tool_name} not found in registry"
            }
        
        # 3. 系统工具（Claude原生）
        if cap.provider == "system":
            return {
                "success": True,
                "message": f"System tool {tool_name} is handled by Claude natively",
                "handled_by": "claude"
            }
        
        # 4. 用户自定义工具
        tool_instance = self._tool_instances.get(tool_name)
        if not tool_instance:
            return {
                "success": False,
                "error": f"Tool {tool_name} instance not loaded. Check TOOL_CLASS_MAPPING."
            }
        
        try:
            result = await self._execute_tool_instance(tool_name, tool_instance, tool_input)
            return result
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _execute_tool_instance(
        self,
        tool_name: str,
        tool_instance: Any,
        tool_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        执行工具实例
        
        处理不同工具的输入格式差异
        """
        # 针对slidespeak_render的特殊处理
        if tool_name == "slidespeak_render":
            if "config" in tool_input:
                # Claude传递的格式: {"config": {...}, "save_dir": "..."}
                result = await tool_instance.execute(
                    config=tool_input["config"],
                    save_dir=tool_input.get("save_dir")
                )
            else:
                # 直接传递整个input作为config
                result = await tool_instance.execute(
                    config=tool_input,
                    save_dir=None
                )
            return result
        
        # 通用处理：检查是否有execute方法
        if hasattr(tool_instance, 'execute'):
            execute_method = getattr(tool_instance, 'execute')
            
            # 检查是否是协程
            if asyncio.iscoroutinefunction(execute_method):
                return await execute_method(**tool_input)
            else:
                return execute_method(**tool_input)
        
        # 尝试直接调用
        if callable(tool_instance):
            return tool_instance(**tool_input)
        
        return {
            "success": False,
            "error": f"Tool {tool_name} does not have an execute method"
        }
    
    def get_available_tools(self) -> Dict[str, Dict]:
        """
        获取所有可用工具及其信息
        
        Returns:
            工具信息字典
        """
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
        """
        获取所有工具的Schema（用于Claude API）
        
        Returns:
            工具schema列表
        """
        return self.registry.get_tool_schemas()
    
    def is_tool_available(self, tool_name: str) -> bool:
        """
        检查工具是否可用
        
        Args:
            tool_name: 工具名称
            
        Returns:
            是否可用
        """
        cap = self.registry.get(tool_name)
        if not cap or cap.type != CapabilityType.TOOL:
            return False
        
        # 系统工具总是可用
        if cap.provider == "system":
            return True
        
        # 自定义工具检查实例
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
        
        lines.append("  Tools:")
        for name, info in tools.items():
            status = "✅" if info.get('loaded') else "⚠️"
            lines.append(f"    {status} {name} ({info['provider']})")
        
        return "\n".join(lines)


# ==================== 便捷函数 ====================

def create_tool_executor(registry: CapabilityRegistry = None) -> ToolExecutor:
    """
    创建工具执行器
    
    Args:
        registry: 能力注册表
        
    Returns:
        配置好的ToolExecutor实例
    """
    return ToolExecutor(registry=registry)
