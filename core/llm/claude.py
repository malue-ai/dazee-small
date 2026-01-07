"""
Claude LLM 服务实现

封装 Claude 的所有核心功能：
- Extended Thinking
- Prompt Caching
- Memory Tool
- Bash Tool / Text Editor
- Web Search
- Streaming
- Tool Search
- Code Execution

参考：
- https://platform.claude.com/docs/en/build-with-claude/overview
- https://platform.claude.com/docs/en/api/overview
"""

import os
import json
from typing import Dict, Any, Optional, List, Union, AsyncIterator, Callable

import anthropic
import httpx

from logger import get_logger
from .base import (
    BaseLLMService,
    LLMConfig,
    LLMResponse,
    Message,
    ToolType,
    LLMProvider
)

logger = get_logger("llm.claude")

# 详细日志开关：设置 LLM_DEBUG_VERBOSE=1 可打印完整请求/响应
LLM_DEBUG_VERBOSE = os.getenv("LLM_DEBUG_VERBOSE", "").lower() in ("1", "true", "yes")


class ClaudeLLMService(BaseLLMService):
    """
    Claude LLM 服务实现
    
    支持的功能：
    - Extended Thinking: 深度推理能力
    - Prompt Caching: 减少重复 token 消耗
    - Server Tools: web_search, code_execution, memory
    - Client Tools: bash, text_editor, computer_use
    - Tool Search: 动态工具发现（>30 工具时）
    - Context Editing: 自动清理长上下文
    
    使用示例：
    ```python
    config = LLMConfig(
        provider=LLMProvider.CLAUDE,
        model="claude-sonnet-4-5-20250929",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        enable_thinking=True
    )
    llm = ClaudeLLMService(config)
    
    response = await llm.create_message_async(
        messages=[Message(role="user", content="Hello")],
        system="You are helpful"
    )
    ```
    """
    
    # Claude 原生工具的 API 格式映射
    NATIVE_TOOLS = {
        # Server-side Tools
        "web_search": {"type": "web_search_20250305", "name": "web_search"},
        "web_fetch": {"type": "web_fetch", "name": "web_fetch"},
        "code_execution": {"type": "code_execution", "name": "code_execution"},
        "memory": {"type": "memory_20250818", "name": "memory"},
        "tool_search_bm25": {"type": "tool_search_tool_bm25_20251119", "name": "tool_search_tool"},
        "tool_search_regex": {"type": "tool_search_tool_regex_20251119", "name": "tool_search_tool"},
        
        # Client-side Tools
        "bash": {"type": "bash_20250124", "name": "bash"},
        "text_editor": {"type": "text_editor_20250728", "name": "str_replace_based_edit_tool"},
        "computer": {"type": "computer_20250124", "name": "computer", "display_width_px": 1024, "display_height_px": 768},
    }
    
    def __init__(self, config: LLMConfig):
        """
        初始化 Claude 服务
        
        Args:
            config: LLM 配置
        """
        self.config = config
        
        # 异步客户端（增加 timeout 和重试配置）
        # 注意：对于流式响应，timeout 是首个响应的超时，不是整体超时
        self.async_client = anthropic.AsyncAnthropic(
            api_key=config.api_key,
            timeout=600.0,    # 10 分钟超时
            max_retries=3     # 自动重试 3 次
        )
        
        # Beta 功能配置
        self._betas: List[str] = []
        
        # 调用方式配置
        self._programmatic_mode = False
        self._tool_search_mode = False
        self._tool_search_type = "bm25"
        self._code_execution_mode = False
        
        # Memory Tool 配置
        self._memory_enabled = False
        self._memory_base_path = "./memory_storage"
        
        # Context Editing 配置
        self._context_editing_enabled = False
        self._context_editing_config: Dict[str, Any] = {}
        
        # 工具注册表（用于自定义工具）
        self._tool_registry: Dict[str, Dict[str, Any]] = {}
    
        # 自定义工具存储
        self._custom_tools: List[Dict[str, Any]] = []
    
    # ============================================================
    # Beta Headers 管理
    # ============================================================
    
    def _add_beta(self, beta_header: str):
        """添加 Beta Header"""
        if beta_header not in self._betas:
            self._betas.append(beta_header)
    
    def _remove_beta(self, beta_header: str):
        """移除 Beta Header"""
        if beta_header in self._betas:
            self._betas.remove(beta_header)
    
    # ============================================================
    # 功能开关
    # ============================================================
    
    def enable_memory_tool(self, base_path: str = "./memory_storage"):
        """
        启用 Memory Tool
        
        Args:
            base_path: 记忆文件存储路径
        """
        self._memory_enabled = True
        self._memory_base_path = base_path
        self._add_beta("context-management-2025-06-27")
    
    def disable_memory_tool(self):
        """禁用 Memory Tool"""
        self._memory_enabled = False
        if not self._context_editing_enabled:
            self._remove_beta("context-management-2025-06-27")
    
    def enable_context_editing(
        self,
        mode: str = "progressive",
        clear_threshold: int = 150000,
        retain_tool_uses: int = 10
    ):
        """
        启用 Context Editing
        
        Args:
            mode: 清理模式 ("progressive" | "aggressive")
            clear_threshold: 触发清理的 token 阈值
            retain_tool_uses: 保留最近 N 个工具调用
        """
        self._context_editing_enabled = True
        self._context_editing_config = {
            "mode": mode,
            "clear_threshold": clear_threshold,
            "retain_tool_uses": retain_tool_uses
        }
        self._add_beta("context-management-2025-06-27")
    
    def disable_context_editing(self):
        """禁用 Context Editing"""
        self._context_editing_enabled = False
        self._context_editing_config = {}
        if not self._memory_enabled:
            self._remove_beta("context-management-2025-06-27")
    
    def enable_tool_search(self, search_type: str = "bm25"):
        """
        启用 Tool Search 模式
        
        Args:
            search_type: "bm25" 或 "regex"
        """
        self._tool_search_mode = True
        self._tool_search_type = search_type
        self._add_beta("advanced-tool-use-2025-11-20")
    
    def disable_tool_search(self):
        """禁用 Tool Search 模式"""
        self._tool_search_mode = False
        self._remove_beta("advanced-tool-use-2025-11-20")
    
    def enable_programmatic_tool_calling(self):
        """启用 Programmatic Tool Calling 模式"""
        self._programmatic_mode = True
        self._code_execution_mode = True
    
    def disable_programmatic_tool_calling(self):
        """禁用 Programmatic Tool Calling 模式"""
        self._programmatic_mode = False
    
    def enable_code_execution(self):
        """启用 Code Execution 模式"""
        self._code_execution_mode = True
    
    def disable_code_execution(self):
        """禁用 Code Execution 模式"""
        self._code_execution_mode = False
    
    # ============================================================
    # 自定义工具管理
    # ============================================================
    
    def add_custom_tool(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any]
    ) -> None:
        """
        添加自定义工具
        
        Args:
            name: 工具名称
            description: 工具描述
            input_schema: 输入参数 schema（JSON Schema 格式）
        """
        # 检查是否已存在同名工具
        for i, tool in enumerate(self._custom_tools):
            if tool["name"] == name:
                # 更新现有工具
                self._custom_tools[i] = {
                    "name": name,
                    "description": description,
                    "input_schema": input_schema
                }
                logger.debug(f"更新自定义工具: {name}")
                return
        
        # 添加新工具
        self._custom_tools.append({
            "name": name,
            "description": description,
            "input_schema": input_schema
        })
        logger.debug(f"注册自定义工具: {name}")
    
    def remove_custom_tool(self, name: str) -> bool:
        """
        移除自定义工具
        
        Args:
            name: 工具名称
            
        Returns:
            是否成功移除
        """
        for i, tool in enumerate(self._custom_tools):
            if tool["name"] == name:
                self._custom_tools.pop(i)
                logger.debug(f"移除自定义工具: {name}")
                return True
        return False
    
    def get_custom_tools(self) -> List[Dict[str, Any]]:
        """
        获取所有自定义工具
        
        Returns:
            自定义工具列表
        """
        return self._custom_tools.copy()
    
    def clear_custom_tools(self) -> None:
        """清空所有自定义工具"""
        self._custom_tools.clear()
        logger.debug("清空所有自定义工具")
    
    # ============================================================
    # 工具处理
    # ============================================================
    
    def get_native_tool(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        获取 Claude 原生工具的 API 格式
        
        Args:
            tool_name: 工具名称
            
        Returns:
            工具 schema，如果不是原生工具则返回 None
        """
        # Tool Search 特殊处理
        if tool_name == "tool_search":
            key = f"tool_search_{self._tool_search_type}"
            if key in self.NATIVE_TOOLS:
                schema = self.NATIVE_TOOLS[key].copy()
                if self.config.enable_caching:
                    schema["cache_control"] = {"type": "ephemeral"}
                return schema
        
        if tool_name in self.NATIVE_TOOLS:
            schema = self.NATIVE_TOOLS[tool_name].copy()
            if self.config.enable_caching:
                schema["cache_control"] = {"type": "ephemeral"}
            return schema
        
        return None
    
    def get_claude_native_tool(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        获取 Claude 原生工具的 API 格式（别名方法，兼容 llm_service.py）
        
        Args:
            tool_name: 工具名称
            
        Returns:
            工具 schema，如果不是原生工具则返回 None
        """
        return self.get_native_tool(tool_name)
    
    def add_custom_tool(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any]
    ):
        """
        添加自定义工具到注册表
        
        Args:
            name: 工具名称
            description: 工具描述
            input_schema: 输入schema（JSON Schema格式）
        """
        self._tool_registry[name] = {
            "name": name,
            "description": description,
            "input_schema": input_schema
        }
    
    def convert_to_tool_schema(self, capability: Dict[str, Any]) -> Dict[str, Any]:
        """
        将能力定义转换为 Claude API 格式
        
        Args:
            capability: 能力定义
            
        Returns:
            Claude API 格式的工具定义
        """
        name = capability.get("name", "")
        
        # 检查是否是原生工具
        native_tool = self.get_native_tool(name)
        if native_tool:
            return native_tool
        
        # 自定义工具
        input_schema = capability.get("input_schema", {
            "type": "object",
            "properties": {},
            "required": []
        })
        description = capability.get("metadata", {}).get("description", f"Tool: {name}")
        
        tool_def = {
            "name": name,
            "description": description,
            "input_schema": input_schema
        }
        
        if self.config.enable_caching:
            tool_def["cache_control"] = {"type": "ephemeral"}
        
        return tool_def
    
    def convert_to_claude_tool(self, capability: Dict[str, Any]) -> Dict[str, Any]:
        """
        将 capabilities.yaml 中的工具定义转换为 Claude API 格式（兼容方法）
        
        Args:
            capability: capabilities.yaml 中的能力定义
            
        Returns:
            Claude API 格式的工具定义
        """
        return self.convert_to_tool_schema(capability)
    
    def configure_deferred_tools(
        self,
        tools: List[Dict[str, Any]],
        frequent_tools: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        配置延迟加载的工具（用于 Tool Search）
        
        Args:
            tools: 工具定义列表
            frequent_tools: 常用工具名称（不延迟加载）
            
        Returns:
            配置好的工具列表
        """
        if frequent_tools is None:
            frequent_tools = ["bash", "web_search", "plan_todo"]
        
        configured = []
        
        # 添加 Tool Search Tool
        if self._tool_search_mode:
            tool_search_schema = self.get_native_tool("tool_search")
            if tool_search_schema:
                configured.append(tool_search_schema)
        
        # 配置其他工具
        for tool in tools:
            tool_name = tool.get("name", "")
            tool_copy = tool.copy()
            
            if tool_name not in frequent_tools:
                tool_copy["defer_loading"] = True
            
            configured.append(tool_copy)
        
        return configured
    
    def _format_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """格式化消息为 Claude API 格式"""
        return [{"role": msg.role, "content": msg.content} for msg in messages]
    
    def _format_tools(self, tools: List[Union[ToolType, str, Dict]]) -> List[Dict[str, Any]]:
        """
        格式化工具列表
        
        支持三种输入：
        1. ToolType 枚举
        2. 字符串
        3. 完整 schema 字典
        """
        formatted = []
        
        for idx, tool in enumerate(tools):
            try:
                if isinstance(tool, ToolType):
                    schema = self.get_native_tool(tool.value)
                    if schema:
                        formatted.append(schema)
                    else:
                        raise ValueError(f"Unknown ToolType: {tool}")
                        
                elif isinstance(tool, str):
                    schema = self.get_native_tool(tool)
                    if schema:
                        formatted.append(schema)
                    else:
                        raise ValueError(f"Unknown tool name: {tool}")
                        
                elif isinstance(tool, dict):
                    self._validate_tool_dict(tool, idx)
                    formatted.append(tool)
                    
                else:
                    raise ValueError(f"Invalid tool format: {tool}")
                
                # 验证 JSON 可序列化
                json.dumps(formatted[-1])
                
            except Exception as e:
                logger.error(f"处理工具 #{idx} 时出错: {e}")
                raise
        
        return formatted
    
    def _validate_tool_dict(self, tool_dict: Dict[str, Any], index: int):
        """验证工具字典是否包含不可序列化的对象"""
        for key, value in tool_dict.items():
            if isinstance(value, ToolType):
                raise ValueError(
                    f"Tool #{index} contains ToolType enum in key '{key}': {value}"
                )
            elif isinstance(value, dict):
                self._validate_tool_dict(value, index)
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        self._validate_tool_dict(item, index)
                    elif isinstance(item, ToolType):
                        raise ValueError(
                            f"Tool #{index} contains ToolType in list '{key}[{i}]'"
                        )
    
    # ============================================================
    # 核心 API 方法
    # ============================================================
    
    async def create_message_async(
        self,
        messages: List[Message],
        system: Optional[str] = None,
        tools: Optional[List[Union[ToolType, str, Dict]]] = None,
        invocation_type: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        创建消息（异步）
        
        Args:
            messages: 消息列表
            system: 系统提示词
            tools: 工具列表
            invocation_type: 调用方式
            **kwargs: 其他参数（支持 max_tokens, temperature 覆盖）
            
        Returns:
            LLMResponse 响应对象
        """
        # 构建请求参数（支持 kwargs 覆盖）
        formatted_messages = self._format_messages(messages)
        request_params = {
            "model": self.config.model,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "messages": formatted_messages
        }
        
        # System prompt
        if system:
            if self.config.enable_caching:
                request_params["system"] = [{
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"}
                }]
            else:
                request_params["system"] = system
        
        # Extended Thinking（由 LLM Service 配置控制）
        if self.config.enable_thinking:
            request_params["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.config.thinking_budget
            }
            request_params["temperature"] = 1.0  # Required for thinking
        else:
            request_params["temperature"] = self.config.temperature
        
        # Tools
        all_tools = []
        tool_names_seen = set()
        
        # 添加用户指定的工具
        if tools:
            for tool in self._format_tools(tools):
                tool_name = tool.get("name", "")
                if tool_name and tool_name not in tool_names_seen:
                    all_tools.append(tool)
                    tool_names_seen.add(tool_name)
        
        # 添加自定义工具（避免重复）
        for custom_tool in self._custom_tools:
            tool_name = custom_tool.get("name", "")
            if tool_name and tool_name not in tool_names_seen:
                tool_def = custom_tool.copy()
                if self.config.enable_caching:
                    tool_def["cache_control"] = {"type": "ephemeral"}
                all_tools.append(tool_def)
                tool_names_seen.add(tool_name)
        
        if all_tools:
            # Tool Search 模式
            if invocation_type == "tool_search" and self._tool_search_mode:
                all_tools = self.configure_deferred_tools(all_tools)
            
            request_params["tools"] = all_tools
            
            # 调试日志
            logger.debug(f"Tools: {[t.get('name', 'unknown') for t in all_tools]}")
        
        # Context Editing
        if self._context_editing_enabled:
            request_params["context_management"] = self._context_editing_config
        
        # 调试日志
        logger.debug(f"📤 LLM 请求: model={self.config.model}, messages={len(messages)}")
        
        # API 调用
        try:
            if self._betas:
                response = await self.async_client.beta.messages.create(
                    betas=self._betas,
                    **request_params
                )
            else:
                response = await self.async_client.messages.create(**request_params)
        except Exception as e:
            logger.error(f"Claude API 调用失败: {e}")
            raise
        
        # 调试日志
        logger.debug(f"📥 LLM 响应: stop_reason={response.stop_reason}")
        
        return self._parse_response(response, invocation_type)
    
    async def create_message_stream(
        self,
        messages: List[Message],
        system: Optional[str] = None,
        tools: Optional[List[Union[ToolType, str, Dict]]] = None,
        on_thinking: Optional[Callable[[str], None]] = None,
        on_content: Optional[Callable[[str], None]] = None,
        on_tool_call: Optional[Callable[[Dict], None]] = None,
        **kwargs
    ) -> AsyncIterator[LLMResponse]:
        """
        创建消息（流式）
        
        Args:
            messages: 消息列表
            system: 系统提示词
            tools: 工具列表
            on_thinking: thinking 回调
            on_content: content 回调
            on_tool_call: tool_call 回调
            **kwargs: 其他参数（支持 max_tokens 覆盖）
            
        Yields:
            LLMResponse 片段
        """
        # 构建请求参数（支持 kwargs 覆盖）
        formatted_messages = self._format_messages(messages)
        request_params = {
            "model": self.config.model,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "messages": formatted_messages
        }
        
        if system:
            request_params["system"] = system
        
        # Extended Thinking（由 LLM Service 配置控制）
        if self.config.enable_thinking:
            request_params["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.config.thinking_budget
            }
            request_params["temperature"] = 1.0
        
        # Tools
        all_tools = []
        tool_names_seen = set()
        
        # 添加用户指定的工具
        if tools:
            for tool in self._format_tools(tools):
                tool_name = tool.get("name", "")
                if tool_name and tool_name not in tool_names_seen:
                    all_tools.append(tool)
                    tool_names_seen.add(tool_name)
        
        # 添加自定义工具（避免重复）
        for custom_tool in self._custom_tools:
            tool_name = custom_tool.get("name", "")
            if tool_name and tool_name not in tool_names_seen:
                tool_def = custom_tool.copy()
                if self.config.enable_caching:
                    tool_def["cache_control"] = {"type": "ephemeral"}
                all_tools.append(tool_def)
                tool_names_seen.add(tool_name)
        
        if all_tools:
            request_params["tools"] = all_tools
        
        # 请求日志（INFO 级别）
        logger.info(f"📤 Claude 请求: model={self.config.model}, tools={len(all_tools)}, messages={len(formatted_messages)}")
        
        # 详细日志：完整请求参数
        if LLM_DEBUG_VERBOSE:
            logger.info("=" * 60)
            logger.info("📤 [VERBOSE] 完整请求参数:")
            # 复制一份，避免修改原始数据
            verbose_params = request_params.copy()
            # 打印 system prompt（可能很长，截断）
            if "system" in verbose_params:
                system_preview = str(verbose_params["system"])[:500]
                logger.info(f"   system: {system_preview}{'...' if len(str(verbose_params['system'])) > 500 else ''}")
            # 打印完整 messages（安全序列化）
            logger.info(f"   messages ({len(verbose_params.get('messages', []))}):")
            for i, msg in enumerate(verbose_params.get('messages', [])):
                msg_preview = self._safe_json_dumps(msg, indent=2)
                logger.info(f"   [{i}] {msg_preview}")
            # 打印 tools
            if "tools" in verbose_params:
                logger.info(f"   tools ({len(verbose_params['tools'])}):")
                for tool in verbose_params['tools']:
                    logger.info(f"      - {tool.get('name', 'unknown')}")
            logger.info("=" * 60)
        else:
            logger.debug(f"📤 Messages 数量: {len(request_params.get('messages', []))}")
        for i, msg in enumerate(request_params.get('messages', [])):
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            if isinstance(content, list):
                types = [b.get('type', 'unknown') for b in content if isinstance(b, dict)]
                logger.debug(f"   [{i}] {role}: blocks={types}")
            else:
                preview = str(content)[:100] + "..." if len(str(content)) > 100 else str(content)
                logger.debug(f"   [{i}] {role}: {preview}")
        
        # 累积变量
        accumulated_thinking = ""
        accumulated_content = ""
        tool_calls = []
        stop_reason = None
        usage = {}  # 🔢 流式模式下从 final_message 获取
        
        event_count = 0  # 🚨 在 try 外初始化，确保 except 中可用
        try:
            async with self.async_client.messages.stream(**request_params) as stream:
                async for event in stream:
                    event_count += 1
                    if not hasattr(event, 'type'):
                        continue
                    
                    if event.type == "content_block_start":
                        if hasattr(event, 'content_block'):
                            block = event.content_block
                            if hasattr(block, 'type'):
                                block_type = block.type
                                
                                if block_type == "thinking" and on_thinking:
                                    on_thinking("")
                                elif block_type == "text" and on_content:
                                    on_content("")
                                # 客户端工具调用
                                elif block_type == "tool_use" and on_tool_call:
                                    on_tool_call({
                                        "id": getattr(block, 'id', ''),
                                        "name": getattr(block, 'name', ''),
                                        "input": getattr(block, 'input', {}),
                                        "type": "tool_use"
                                    })
                                # 服务端工具调用（如 web_search）
                                elif block_type == "server_tool_use" and on_tool_call:
                                    on_tool_call({
                                        "id": getattr(block, 'id', ''),
                                        "name": getattr(block, 'name', ''),
                                        "input": getattr(block, 'input', {}),
                                        "type": "server_tool_use"
                                    })
                                # 工具结果（如 web_search_tool_result）
                                elif block_type.endswith("_tool_result"):
                                    # 工具结果通过 final_message 获取完整内容
                                    logger.debug(f"📥 工具结果开始: {block_type}")
                    
                    elif event.type == "content_block_delta":
                        if hasattr(event, 'delta'):
                            delta = event.delta
                            if hasattr(delta, 'type'):
                                if delta.type == "thinking_delta":
                                    text = getattr(delta, 'thinking', '')
                                    accumulated_thinking += text
                                    if on_thinking:
                                        on_thinking(text)
                                    yield LLMResponse(content="", thinking=text, is_stream=True)
                                    
                                elif delta.type == "text_delta":
                                    text = getattr(delta, 'text', '')
                                    accumulated_content += text
                                    if on_content:
                                        on_content(text)
                                    yield LLMResponse(content=text, is_stream=True)
                                    
                                elif delta.type == "input_json_delta":
                                    partial_json = getattr(delta, 'partial_json', '')
                                    if on_tool_call:
                                        on_tool_call({
                                            "partial_input": partial_json,
                                            "type": "input_delta"
                                        })
                    
                    elif event.type == "message_stop":
                        final_message = None
                        try:
                            final_message = await stream.get_final_message()
                            stop_reason = getattr(final_message, 'stop_reason', None)
                            
                            # 🔢 提取 usage 信息
                            if hasattr(final_message, 'usage') and final_message.usage:
                                usage = {
                                    "input_tokens": final_message.usage.input_tokens,
                                    "output_tokens": final_message.usage.output_tokens
                                }
                                if hasattr(final_message.usage, 'cache_read_input_tokens'):
                                    usage["cache_read_tokens"] = final_message.usage.cache_read_input_tokens
                                if hasattr(final_message.usage, 'cache_creation_input_tokens'):
                                    usage["cache_creation_tokens"] = final_message.usage.cache_creation_input_tokens
                                
                                # 📊 Token 使用量日志
                                input_tokens = usage.get("input_tokens", 0)
                                output_tokens = usage.get("output_tokens", 0)
                                total_tokens = input_tokens + output_tokens
                                logger.info(
                                    f"📊 Token 使用: input={input_tokens:,}, output={output_tokens:,}, "
                                    f"total={total_tokens:,} (model={self.config.model})"
                                )
                                
                                # 🆕 Cache 效果日志（Context Engineering 监控）
                                cache_read = usage.get("cache_read_tokens", 0)
                                cache_create = usage.get("cache_creation_tokens", 0)
                                if cache_read > 0:
                                    # cache 命中，节省成本（90% 折扣）
                                    saved = cache_read * 0.003 * 0.9 / 1000  # $3/M * 90% off
                                    logger.info(f"✅ Cache HIT: {cache_read:,} tokens (saved ~${saved:.4f})")
                                elif cache_create > 0:
                                    logger.debug(f"📦 Cache CREATED: {cache_create:,} tokens")
                            
                            if hasattr(final_message, 'content'):
                                for block in final_message.content:
                                    if not hasattr(block, 'type'):
                                        continue
                                    block_type = block.type
                                    
                                    # 客户端工具调用
                                    if block_type == "tool_use":
                                        tool_calls.append({
                                            "id": getattr(block, 'id', ''),
                                            "name": getattr(block, 'name', ''),
                                            "input": getattr(block, 'input', {}),
                                            "type": "tool_use"
                                        })
                                    # 服务端工具调用
                                    elif block_type == "server_tool_use":
                                        tool_calls.append({
                                            "id": getattr(block, 'id', ''),
                                            "name": getattr(block, 'name', ''),
                                            "input": getattr(block, 'input', {}),
                                            "type": "server_tool_use"
                                        })
                        except Exception as e:
                            logger.warning(f"获取最终消息失败: {e}")
        except (httpx.RemoteProtocolError, Exception) as stream_error:
            # 🚨 流式传输中断：记录已接收的事件数和已累积的内容
            error_msg = str(stream_error)
            logger.error(f"❌ 流式传输中断: {error_msg}")
            logger.error(f"   已接收事件数: {event_count}")
            logger.error(f"   已累积 thinking: {len(accumulated_thinking)} chars")
            logger.error(f"   已累积 content: {len(accumulated_content)} chars")
            logger.error(f"   已解析 tool_calls: {len(tool_calls)}")
            
            # 如果有部分内容，尝试返回（降级处理）
            if accumulated_content or accumulated_thinking or tool_calls:
                logger.warning("⚠️ 尝试返回部分响应...")
                raw_content = self._build_raw_content_from_parts(
                    accumulated_thinking, accumulated_content, tool_calls
                )
                yield LLMResponse(
                    content=accumulated_content,
                    thinking=accumulated_thinking if accumulated_thinking else None,
                    tool_calls=tool_calls if tool_calls else None,
                    stop_reason="stream_error",
                    raw_content=raw_content,
                    is_stream=False
                )
                return
            
            # 没有任何内容，抛出原始错误
            raise
        
        # 构建 raw_content
        # 优先使用 final_message（包含 thinking signature）
        if final_message and hasattr(final_message, 'content'):
            raw_content = self._build_raw_content(final_message)
        else:
            # 降级：使用累积的内容（没有 signature）
            raw_content = self._build_raw_content_from_parts(
                accumulated_thinking, accumulated_content, tool_calls
            )
        
        # 响应日志（INFO 级别）
        raw_types = [b.get('type', 'unknown') for b in raw_content]
        tool_names = [tc.get('name', '') for tc in tool_calls] if tool_calls else []
        logger.info(f"📥 Claude 响应: stop_reason={stop_reason or 'end_turn'}, blocks={raw_types}, tools={tool_names}")
        
        # 详细日志：完整响应内容
        if LLM_DEBUG_VERBOSE:
            logger.info("=" * 60)
            logger.info("📥 [VERBOSE] 完整响应内容:")
            logger.info(f"   stop_reason: {stop_reason}")
            if accumulated_thinking:
                thinking_preview = accumulated_thinking[:1000]
                logger.info(f"   thinking ({len(accumulated_thinking)} chars): {thinking_preview}{'...' if len(accumulated_thinking) > 1000 else ''}")
            if accumulated_content:
                content_preview = accumulated_content[:2000]
                logger.info(f"   content ({len(accumulated_content)} chars): {content_preview}{'...' if len(accumulated_content) > 2000 else ''}")
            if tool_calls:
                logger.info(f"   tool_calls ({len(tool_calls)}):")
                for tc in tool_calls:
                    logger.info(f"      {self._safe_json_dumps(tc, indent=2)}")
            logger.info(f"   raw_content ({len(raw_content)} blocks):")
            for i, block in enumerate(raw_content):
                block_preview = self._safe_json_dumps(block)
                if len(block_preview) > 500:
                    block_preview = block_preview[:500] + "..."
                logger.info(f"      [{i}] {block_preview}")
            logger.info("=" * 60)
        
        # 返回最终响应
        if accumulated_content or accumulated_thinking or tool_calls:
            yield LLMResponse(
                content=accumulated_content,
                thinking=accumulated_thinking if accumulated_thinking else None,
                tool_calls=tool_calls if tool_calls else None,
                stop_reason=stop_reason or "end_turn",
                usage=usage if usage else None,  # 🔢 流式模式也返回 usage
                raw_content=raw_content,
                is_stream=False
            )
    
    def _safe_json_dumps(self, obj: Any, indent: int = None) -> str:
        """
        安全的 JSON 序列化，处理特殊对象（如 WebSearchResultBlock）
        
        Args:
            obj: 要序列化的对象
            indent: 缩进级别
            
        Returns:
            JSON 字符串
        """
        def default_handler(o):
            """自定义序列化处理器"""
            if hasattr(o, 'model_dump'):
                # Pydantic v2 对象
                return o.model_dump()
            elif hasattr(o, 'dict'):
                # Pydantic v1 对象
                return o.dict()
            elif hasattr(o, '__dict__'):
                # 普通对象
                return o.__dict__
            else:
                # Fallback
                return str(o)
        
        try:
            return json.dumps(obj, ensure_ascii=False, indent=indent, default=default_handler)
        except Exception:
            return str(obj)
    
    def count_tokens(self, text: str) -> int:
        """
        计算 token 数量（本地快速估算）
        
        估算规则：
        - 英文：1 token ≈ 4 characters
        - 中文：1 token ≈ 1.5 characters
        - 混合文本：使用 4 characters per token
        
        精确度：±10%
        
        Args:
            text: 要计算的文本
            
        Returns:
            估算的 token 数量
        """
        if not text:
            return 0
        return max(1, len(text) // 4)
    
    # ============================================================
    # 响应解析
    # ============================================================
    
    def _parse_response(
        self,
        response: anthropic.types.Message,
        invocation_type: Optional[str] = None
    ) -> LLMResponse:
        """解析 Claude API 响应为统一格式"""
        thinking_text = ""
        content_text = ""
        tool_calls = []
        invocation_method = invocation_type or "direct"
        
        for block in response.content:
            if not hasattr(block, 'type'):
                continue
            
            if block.type == "thinking":
                thinking_text = getattr(block, 'thinking', '')
            elif block.type == "text":
                content_text = getattr(block, 'text', '')
            elif block.type == "tool_use":
                tool_name = getattr(block, 'name', '')
                
                if tool_name == "code_execution":
                    invocation_method = "code_execution"
                else:
                    invocation_method = "direct"
                
                tool_calls.append({
                    "id": getattr(block, 'id', ''),
                    "name": tool_name,
                    "input": getattr(block, 'input', {}),
                    "invocation_method": invocation_method
                })
                
                # Programmatic 模式检测
                if self._programmatic_mode and tool_name == "code_execution":
                    code_input = getattr(block, 'input', {})
                    code_text = code_input.get('code', '')
                    if 'tool_calling' in code_text or 'invoke' in code_text:
                        tool_calls[-1]['invocation_method'] = "programmatic"
        
        # Usage 信息
        usage = {}
        if hasattr(response, 'usage'):
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens
            }
            if hasattr(response.usage, 'cache_read_input_tokens'):
                usage["cache_read_tokens"] = response.usage.cache_read_input_tokens
            if hasattr(response.usage, 'cache_creation_input_tokens'):
                usage["cache_creation_tokens"] = response.usage.cache_creation_input_tokens
            
            # 📊 Token 使用量日志
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            total_tokens = input_tokens + output_tokens
            logger.info(
                f"📊 Token 使用: input={input_tokens:,}, output={output_tokens:,}, "
                f"total={total_tokens:,} (model={self.config.model})"
            )
            
            # 🆕 Cache 效果日志（Context Engineering 监控）
            cache_read = usage.get("cache_read_tokens", 0)
            cache_create = usage.get("cache_creation_tokens", 0)
            if cache_read > 0:
                saved = cache_read * 0.003 * 0.9 / 1000
                logger.info(f"✅ Cache HIT: {cache_read:,} tokens (saved ~${saved:.4f})")
            elif cache_create > 0:
                logger.debug(f"📦 Cache CREATED: {cache_create:,} tokens")
        
        # 构建 raw_content
        raw_content = self._build_raw_content(response)
        
        return LLMResponse(
            content=content_text,
            thinking=thinking_text if thinking_text else None,
            tool_calls=tool_calls if tool_calls else None,
            stop_reason=response.stop_reason,
            usage=usage,
            raw_content=raw_content,
            cache_read_tokens=usage.get("cache_read_tokens", 0),
            cache_creation_tokens=usage.get("cache_creation_tokens", 0)
        )
    
    def _build_raw_content(self, response: anthropic.types.Message) -> List[Dict[str, Any]]:
        """
        构建原始 content 块列表（用于消息续传）
        
        Claude 原生协议支持的 content block 类型：
        - thinking: 思考过程（带 signature）
        - text: 文本内容
        - tool_use: 客户端工具调用
        - server_tool_use: 服务端工具调用（如 web_search）
        - *_tool_result: 工具结果（如 web_search_tool_result）
        
        规则：
        1. thinking 块必须有有效的 signature 字段
        2. tool_use/server_tool_use 块必须有 id 和 name
        3. 跳过空文本块
        4. tool_result 需要保留完整内容
        """
        raw_content = []
        
        for block in response.content:
            if not hasattr(block, 'type'):
                continue
            
            block_type = block.type
            
            if block_type == "thinking":
                thinking_text = getattr(block, 'thinking', '')
                signature = getattr(block, 'signature', '')
                
                if thinking_text and signature:
                    raw_content.append({
                        "type": "thinking",
                        "thinking": thinking_text,
                        "signature": signature
                    })
                elif thinking_text:
                    logger.warning(f"Thinking block without signature, skipping")
                    
            elif block_type == "text":
                text_content = getattr(block, 'text', '')
                if text_content:
                    raw_content.append({
                        "type": "text",
                        "text": text_content
                    })
            
            # 客户端工具调用
            elif block_type == "tool_use":
                tool_id = getattr(block, 'id', '')
                tool_name = getattr(block, 'name', '')
                tool_input = getattr(block, 'input', {})
                
                if tool_id and tool_name:
                    raw_content.append({
                        "type": "tool_use",
                        "id": tool_id,
                        "name": tool_name,
                        "input": tool_input
                    })
                else:
                    logger.warning(f"Invalid tool_use block: id={tool_id}, name={tool_name}")
            
            # 服务端工具调用（如 web_search, code_execution）
            elif block_type == "server_tool_use":
                tool_id = getattr(block, 'id', '')
                tool_name = getattr(block, 'name', '')
                tool_input = getattr(block, 'input', {})
                
                if tool_id and tool_name:
                    raw_content.append({
                        "type": "server_tool_use",
                        "id": tool_id,
                        "name": tool_name,
                        "input": tool_input
                    })
                else:
                    logger.warning(f"Invalid server_tool_use block: id={tool_id}, name={tool_name}")
            
            # 工具结果（如 web_search_tool_result, code_execution_tool_result）
            elif block_type.endswith("_tool_result"):
                tool_use_id = getattr(block, 'tool_use_id', '')
                content = getattr(block, 'content', [])
                
                raw_content.append({
                    "type": block_type,  # 保留原始类型（如 web_search_tool_result）
                    "tool_use_id": tool_use_id,
                    "content": content
                })
                logger.debug(f"📥 服务端工具结果: {block_type}, tool_use_id={tool_use_id}")
            
            else:
                # 未知类型，记录警告但不跳过（可能是新的 block 类型）
                logger.warning(f"Unknown content block type: {block_type}")
                # 尝试转换为字典
                try:
                    block_dict = {"type": block_type}
                    for attr in ['id', 'name', 'input', 'content', 'tool_use_id']:
                        if hasattr(block, attr):
                            block_dict[attr] = getattr(block, attr)
                    raw_content.append(block_dict)
                except Exception as e:
                    logger.error(f"Failed to convert unknown block: {e}")
        
        return raw_content
    
    def _build_raw_content_from_parts(
        self,
        thinking: str,
        content: str,
        tool_calls: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        从流式累积的部分构建 raw_content（降级方案）
        
        注意：这是降级方案，仅在无法获取 final_message 时使用。
        不包含 thinking 块（因为没有 signature），会导致后续轮次
        Extended Thinking 失败。
        
        优先使用 _build_raw_content(final_message) 来获取完整的
        thinking 块（包括 signature）。
        """
        raw_content = []
        
        # 不包含 thinking 块（没有 signature 会导致后续 Extended Thinking 失败）
        
        if content:
            raw_content.append({
                "type": "text",
                "text": content
            })
        
        for tc in tool_calls:
            raw_content.append({
                "type": "tool_use",
                "id": tc["id"],
                "name": tc["name"],
                "input": tc["input"]
            })
        
        return raw_content
    
    def _remove_thinking_blocks(self, messages: List[Dict]) -> List[Dict]:
        """
        从消息中移除 thinking blocks
        
        当禁用 Extended Thinking 时，必须从历史消息中移除 thinking blocks，
        否则 Claude API 会报错：
        "When thinking is disabled, assistant message cannot contain thinking blocks"
        
        参考官方文档：
        "You may omit thinking blocks from previous assistant turns"
        
        Args:
            messages: 格式化后的消息列表
            
        Returns:
            移除 thinking blocks 后的消息列表
        """
        cleaned_messages = []
        
        for msg in messages:
            if not isinstance(msg, dict):
                cleaned_messages.append(msg)
                continue
            
            role = msg.get("role")
            content = msg.get("content")
            
            # 只处理 assistant 消息
            if role == "assistant" and isinstance(content, list):
                # 过滤掉 thinking 和 redacted_thinking blocks
                filtered_content = [
                    block for block in content
                    if isinstance(block, dict) and 
                    block.get("type") not in ("thinking", "redacted_thinking")
                ]
                
                if filtered_content:
                    cleaned_messages.append({
                        "role": "assistant",
                        "content": filtered_content
                    })
                # 如果过滤后为空，跳过该消息
            else:
                cleaned_messages.append(msg)
        
        return cleaned_messages


# ============================================================
# 工厂函数
# ============================================================

def create_claude_service(
    model: str = "claude-sonnet-4-5-20250929",
    api_key: Optional[str] = None,
    enable_thinking: bool = True,
    enable_caching: bool = False,
    **kwargs
) -> ClaudeLLMService:
    """
    创建 Claude 服务的便捷函数
    
    Args:
        model: 模型名称
        api_key: API 密钥（默认从环境变量读取）
        enable_thinking: 启用 Extended Thinking
        enable_caching: 启用 Prompt Caching
        **kwargs: 其他配置参数
        
    Returns:
        ClaudeLLMService 实例
    """
    if api_key is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
    
    config = LLMConfig(
        provider=LLMProvider.CLAUDE,
        model=model,
        api_key=api_key,
        enable_thinking=enable_thinking,
        enable_caching=enable_caching,
        **kwargs
    )
    
    return ClaudeLLMService(config)

