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

import asyncio
import inspect
import logging
from importlib import import_module
from typing import Dict, Any, Optional, List, Callable

# 🆕 从 capability 子包导入
from core.tool.capability import (
    CapabilityRegistry,
    CapabilityType,
    Capability,
    create_capability_registry
)

logger = logging.getLogger(__name__)


class ToolExecutor:
    """
    配置驱动的工具执行器
    
    从 CapabilityRegistry 加载工具，动态执行
    """
    
    # 工具类映射（已废弃，仅向后兼容）
    TOOL_CLASS_MAPPING = {
        "slidespeak_render": ("tools.slidespeak", "SlideSpeakTool"),
    }
    
    # Claude Server-side 工具（由 Anthropic 服务器处理，不需要本地执行）
    CLAUDE_SERVER_TOOLS = {
        "web_search",      # 搜索由 Anthropic 服务器执行
        "code_execution",  # 代码执行在 Anthropic 沙箱中
        "memory",          # 记忆由 Anthropic 管理
    }
    
    # Claude Client-side 工具（需要本地执行！）
    # bash, text_editor 需要我们执行并返回结果给 Claude
    CLAUDE_CLIENT_TOOLS = {
        "bash",
        "str_replace_based_edit_tool",
        "text_editor",
    }
    
    def __init__(
        self, 
        registry: Optional[CapabilityRegistry] = None,
        tool_context: Optional[Dict[str, Any]] = None
    ):
        """
        初始化工具执行器
        
        Args:
            registry: 能力注册表（如果为 None 则自动创建）
            tool_context: 工具上下文（用于依赖注入）
                - memory: WorkingMemory 实例
                - event_manager: EventManager 实例
                - workspace_dir: 工作目录路径
        """
        self.registry = registry or create_capability_registry()
        self.tool_context = tool_context or {}
        self._tool_instances: Dict[str, Any] = {}
        self._tool_handlers: Dict[str, Callable] = {}
        self._load_tools()
    
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
        
        优先级：
        1. capabilities.yaml 中的 implementation 配置（推荐）
        2. TOOL_CLASS_MAPPING 硬编码映射（向后兼容）
        """
        tool_name = cap.name
        
        # 方法1：从 capabilities.yaml 的 implementation 配置加载
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
        
        # 方法2：从 TOOL_CLASS_MAPPING 加载（向后兼容）
        if tool_name in self.TOOL_CLASS_MAPPING:
            module_path, class_name = self.TOOL_CLASS_MAPPING[tool_name]
            try:
                module = import_module(module_path)
                tool_class = getattr(module, class_name)
                self._tool_instances[tool_name] = tool_class()
                logger.info(f"✅ 加载工具 (legacy): {tool_name}")
                return
            except Exception as e:
                logger.error(f"❌ 加载工具 {tool_name} 失败: {e}")
        
        # 未找到加载方式
        logger.warning(f"⚠️ 工具 {tool_name} 无法加载，跳过")
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
        
        只注入架构级依赖（memory, event_manager, workspace_dir）
        """
        kwargs = {}
        
        param_mapping = {
            "memory": "memory",
            "event_manager": "event_manager",
            "workspace_dir": "workspace_dir",
        }
        
        for param in params:
            if param in param_mapping:
                context_key = param_mapping[param]
                if context_key in self.tool_context and self.tool_context[context_key]:
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
        # 0. Claude Server-side 工具（由 Anthropic 处理）
        if tool_name in self.CLAUDE_SERVER_TOOLS:
            return {
                "success": True,
                "message": f"Server tool {tool_name} is handled by Anthropic",
                "handled_by": "anthropic_server"
            }
        
        # 0.1 Claude Client-side 工具（需要本地执行！）
        if tool_name in self.CLAUDE_CLIENT_TOOLS:
            return await self._execute_client_tool(tool_name, tool_input)
        
        # 1. 自定义处理器
        if tool_name in self._tool_handlers:
            try:
                handler = self._tool_handlers[tool_name]
                if asyncio.iscoroutinefunction(handler):
                    return await handler(tool_input)
                else:
                    return handler(tool_input)
            except Exception as e:
                return {"success": False, "error": f"Handler error: {str(e)}"}
        
        # 2. Registry 中的工具
        cap = self.registry.get(tool_name)
        if not cap or cap.type != CapabilityType.TOOL:
            return {"success": False, "error": f"Tool {tool_name} not found"}
        
        # 3. 系统工具
        if cap.provider == "system":
            return {
                "success": True,
                "message": f"System tool {tool_name} is handled by Claude natively",
                "handled_by": "claude"
            }
        
        # 4. 用户自定义工具
        tool_instance = self._tool_instances.get(tool_name)
        if not tool_instance:
            return {"success": False, "error": f"Tool {tool_name} not loaded"}
        
        try:
            return await self._execute_tool_instance(tool_name, tool_instance, tool_input)
        except Exception as e:
            return {"success": False, "error": str(e)}
    
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
            if asyncio.iscoroutinefunction(execute_method):
                return await execute_method(**tool_input)
            else:
                return execute_method(**tool_input)
        
        if callable(tool_instance):
            return tool_instance(**tool_input)
        
        return {"success": False, "error": f"Tool {tool_name} has no execute method"}
    
    async def _execute_client_tool(
        self,
        tool_name: str,
        tool_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        执行 Claude Client-side 工具（bash, text_editor）
        
        这些工具需要本地执行，然后把结果返回给 Claude
        """
        import subprocess
        import os
        
        if tool_name == "bash":
            # 执行 bash 命令
            command = tool_input.get("command", "")
            restart = tool_input.get("restart", False)
            
            if not command:
                return {"success": False, "error": "命令不能为空"}
            
            try:
                # 获取 workspace 路径作为工作目录
                workspace_dir = self.tool_context.get("workspace_dir", "./workspace")
                
                # 执行命令
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    cwd=workspace_dir
                )
                
                output = result.stdout
                if result.stderr:
                    output += f"\n[stderr]\n{result.stderr}"
                
                return {
                    "success": result.returncode == 0,
                    "output": output,
                    "exit_code": result.returncode
                }
            except subprocess.TimeoutExpired:
                return {"success": False, "error": "命令执行超时（60秒）"}
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        elif tool_name in ("str_replace_based_edit_tool", "text_editor"):
            # 文件编辑工具
            command_type = tool_input.get("command")
            path = tool_input.get("path", "")
            
            # 获取 workspace 路径
            workspace_dir = self.tool_context.get("workspace_dir", "./workspace")
            
            # 安全检查：确保路径在 workspace 内
            full_path = os.path.abspath(os.path.join(workspace_dir, path)) if not os.path.isabs(path) else path
            
            if command_type == "view":
                # 查看文件
                try:
                    view_range = tool_input.get("view_range", [])
                    with open(full_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    
                    if view_range and len(view_range) == 2:
                        start, end = view_range
                        lines = lines[start-1:end]
                    
                    return {
                        "success": True,
                        "content": "".join(lines),
                        "total_lines": len(lines)
                    }
                except FileNotFoundError:
                    return {"success": False, "error": f"文件不存在: {path}"}
                except Exception as e:
                    return {"success": False, "error": str(e)}
            
            elif command_type == "create":
                # 创建文件
                file_text = tool_input.get("file_text", "")
                try:
                    os.makedirs(os.path.dirname(full_path), exist_ok=True)
                    with open(full_path, 'w', encoding='utf-8') as f:
                        f.write(file_text)
                    return {
                        "success": True,
                        "message": f"文件已创建: {path}",
                        "path": full_path
                    }
                except Exception as e:
                    return {"success": False, "error": str(e)}
            
            elif command_type == "str_replace":
                # 替换字符串
                old_str = tool_input.get("old_str", "")
                new_str = tool_input.get("new_str", "")
                try:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    if old_str not in content:
                        return {"success": False, "error": f"未找到要替换的内容: {old_str[:50]}..."}
                    
                    content = content.replace(old_str, new_str, 1)
                    with open(full_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    
                    return {
                        "success": True,
                        "message": "替换成功",
                        "path": full_path
                    }
                except FileNotFoundError:
                    return {"success": False, "error": f"文件不存在: {path}"}
                except Exception as e:
                    return {"success": False, "error": str(e)}
            
            elif command_type == "insert":
                # 插入内容
                insert_line = tool_input.get("insert_line", 0)
                new_str = tool_input.get("new_str", "")
                try:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    
                    lines.insert(insert_line, new_str + "\n")
                    
                    with open(full_path, 'w', encoding='utf-8') as f:
                        f.writelines(lines)
                    
                    return {
                        "success": True,
                        "message": f"内容已插入到第 {insert_line} 行",
                        "path": full_path
                    }
                except FileNotFoundError:
                    return {"success": False, "error": f"文件不存在: {path}"}
                except Exception as e:
                    return {"success": False, "error": str(e)}
            
            elif command_type == "undo_edit":
                # 撤销编辑（简化实现：返回不支持）
                return {"success": False, "error": "撤销功能暂不支持"}
            
            else:
                return {"success": False, "error": f"未知的编辑命令: {command_type}"}
        
        return {"success": False, "error": f"未知的 client 工具: {tool_name}"}
    
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
        
        lines.append("  Tools:")
        for name, info in tools.items():
            status = "✅" if info.get('loaded') else "⚠️"
            lines.append(f"    {status} {name} ({info['provider']})")
        
        return "\n".join(lines)


def create_tool_executor(
    registry: CapabilityRegistry = None,
    tool_context: Dict[str, Any] = None
) -> ToolExecutor:
    """
    创建工具执行器
    
    Args:
        registry: 能力注册表
        tool_context: 工具上下文（用于依赖注入）
        
    Returns:
        ToolExecutor 实例
    """
    return ToolExecutor(registry=registry, tool_context=tool_context)

