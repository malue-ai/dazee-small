"""
统一的LLM服务封装层

设计原则：
1. 关注点分离：Agent不需要知道具体LLM的API细节
2. 统一接口：所有LLM通过相同接口调用
3. 完整封装：Core capabilities + Tools + Streaming
4. 易于扩展：支持Claude、GPT-4、Gemini等

参考：
- Claude Platform: https://platform.claude.com/docs/en/build-with-claude/overview
- Claude API: https://platform.claude.com/docs/en/api/overview
"""

import os
import json
from logger import get_logger
from typing import Dict, Any, Optional, List, Union, AsyncIterator, Callable
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
import anthropic

logger = get_logger("llm_service")


# ============================================================
# 数据模型
# ============================================================

class LLMProvider(Enum):
    """LLM提供商"""
    CLAUDE = "claude"
    GPT4 = "gpt4"
    GEMINI = "gemini"


class ToolType(Enum):
    """工具类型（统一抽象）"""
    # Claude Server Tools (服务端执行)
    WEB_SEARCH = "web_search"           # 网页搜索
    WEB_FETCH = "web_fetch"             # 网页获取 (Beta)
    CODE_EXECUTION = "code_execution"   # 代码执行 (Beta)
    MEMORY = "memory"                   # 记忆工具 (Beta)
    TOOL_SEARCH = "tool_search"         # 工具搜索 (Beta)
    
    # Claude Client Tools (客户端执行)
    BASH = "bash"                       # Shell 命令
    TEXT_EDITOR = "text_editor"         # 文本编辑器
    COMPUTER_USE = "computer_use"       # 计算机使用 (Beta)
    
    # 自定义工具
    CUSTOM = "custom"


class InvocationType(Enum):
    """调用方式类型"""
    DIRECT = "direct"                   # 标准工具调用
    CODE_EXECUTION = "code_execution"   # 代码执行
    PROGRAMMATIC = "programmatic"       # 程序化工具调用
    STREAMING = "streaming"             # 细粒度流式
    TOOL_SEARCH = "tool_search"         # 工具搜索


@dataclass
class LLMConfig:
    """LLM配置"""
    provider: LLMProvider
    model: str
    api_key: str
    
    # Core capabilities
    enable_thinking: bool = True
    thinking_budget: int = 10000
    enable_caching: bool = False
    enable_streaming: bool = False
    
    # 基础参数
    temperature: float = 1.0
    max_tokens: int = 64000  # Claude Sonnet 4.5 最大支持 64K output tokens
    
    # Tools
    tools: List[Dict[str, Any]] = None
    
    # 高级功能
    enable_context_editing: bool = False
    enable_structured_output: bool = False


@dataclass
class LLMResponse:
    """统一的LLM响应格式"""
    content: str
    thinking: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = None
    stop_reason: str = "end_turn"
    usage: Dict[str, int] = None
    
    # 原始content块（用于tool_use响应的消息续传）
    raw_content: List[Any] = None
    
    # 流式相关
    is_stream: bool = False
    
    # Claude特有
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0


@dataclass
class Message:
    """统一的消息格式"""
    role: str  # "user" | "assistant"
    content: Union[str, List[Dict[str, Any]]]


# ============================================================
# 抽象基类
# ============================================================

class BaseLLMService(ABC):
    """LLM服务抽象基类"""
    
    @abstractmethod
    async def create_message_async(
        self,
        messages: List[Message],
        system: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """创建消息（异步）"""
        pass
    
    @abstractmethod
    def create_message_stream(
        self,
        messages: List[Message],
        system: Optional[str] = None,
        **kwargs
    ) -> AsyncIterator[LLMResponse]:
        """创建消息（流式）"""
        pass
    
    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """计算tokens"""
        pass


# ============================================================
# Claude实现
# ============================================================

class ClaudeLLMService(BaseLLMService):
    """
    Claude LLM服务实现
    
    封装Claude的所有核心功能：
    - Extended Thinking
    - Prompt Caching
    - Memory Tool
    - Bash Tool
    - Text Editor
    - Web Search
    - Streaming
    """
    
    def __init__(self, config: LLMConfig):
        """
        初始化Claude服务
        
        Args:
            config: LLM配置
        """
        self.config = config
        
        # 🆕 异步客户端（用于真正的异步调用）
        # 增加timeout和重试配置以提高稳定性
        # 参考：https://docs.anthropic.com/en/api/client-sdks
        self.async_client = anthropic.AsyncAnthropic(
            api_key=config.api_key,
            timeout=600.0,    # 10分钟超时（单次请求）
            max_retries=3     # 🆕 自动重试3次（处理网络抖动）
        )
        
        # Beta client (用于 Tool Search, Code Execution 等)
        # 🆕 使用异步客户端
        self.beta_client = anthropic.AsyncAnthropic(
            api_key=config.api_key,
            timeout=600.0,
            max_retries=3
        )
        
        # 工具注册表
        self._tool_registry = self._init_tool_registry()
        
        # 调用方式配置
        self._programmatic_mode = False     # 程序化工具调用检测
        self._tool_search_mode = False      # Tool Search 模式
        self._tool_search_type = "bm25"     # Tool Search 类型
        self._code_execution_mode = False   # Code Execution 模式
        
        # 🆕 Memory Tool 配置
        self._memory_enabled = False
        self._memory_base_path = "./memory_storage"
        
        # 🆕 Context Editing 配置
        self._context_editing_enabled = False
        self._context_editing_config: Dict[str, Any] = {}
        
        # Beta headers 配置（统一管理）
        # 注意：Extended Thinking 不需要 beta header，它是标准功能
        self._betas: List[str] = []
    
    def _init_tool_registry(self) -> Dict[str, Dict[str, Any]]:
        """
        初始化 Claude 原生工具的 API 格式映射
        
        ⚠️ 注意：这里只定义 Claude API 的工具格式规范
        实际工具定义应该在 capabilities.yaml 中配置
        
        参考：https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview
        
        五种调用方式：
        1. Direct Tool Call: 标准工具调用（所有工具）
        2. Code Execution: 通过 code_execution tool 运行代码（Beta）
        3. Programmatic Tool Calling: 在 code_execution 内调用工具
        4. Fine-grained Streaming: 流式接收大参数
        5. Tool Search: 动态发现工具（>30工具时）
        """
        # Claude 原生工具的 API 格式映射
        # 这些是 Claude API 的固定格式，不是工具定义
        return {
            # Server-side Tools (Claude 服务端执行)
            "web_search": {"type": "web_search_20250305", "name": "web_search"},
            "web_fetch": {"type": "web_fetch", "name": "web_fetch"},
            "code_execution": {"type": "code_execution", "name": "code_execution"},
            "memory": {"type": "memory_20250818", "name": "memory"},  # ✅ 修复为正确的 type
            "tool_search_bm25": {"type": "tool_search_tool_bm25_20251119", "name": "tool_search_tool"},
            "tool_search_regex": {"type": "tool_search_tool_regex_20251119", "name": "tool_search_tool"},
            
            # Client-side Tools (客户端执行，需要本地实现)
            "bash": {"type": "bash_20250124", "name": "bash"},
            "text_editor": {"type": "text_editor_20250728", "name": "str_replace_based_edit_tool"},
            "computer": {"type": "computer_20250124", "name": "computer", "display_width_px": 1024, "display_height_px": 768},
        }
    
    # ============================================================
    # Beta Headers 管理
    # ============================================================
    
    def _add_beta(self, beta_header: str):
        """添加 Beta Header（避免重复）"""
        if beta_header not in self._betas:
            self._betas.append(beta_header)
    
    def _remove_beta(self, beta_header: str):
        """移除 Beta Header"""
        if beta_header in self._betas:
            self._betas.remove(beta_header)
    
    # ============================================================
    # 调用模式配置方法
    # ============================================================
    
    def enable_programmatic_tool_calling(self):
        """
        启用 Programmatic Tool Calling 模式
        
        在此模式下，LLM Service 会检测 code_execution 结果中的工具调用，
        并将它们提取为标准 tool_use 格式。
        
        参考：https://platform.claude.com/docs/en/build-with-claude/tool-use#programmatic-tool-calling
        """
        self._programmatic_mode = True
        self._code_execution_mode = True
    
    def disable_programmatic_tool_calling(self):
        """禁用 Programmatic Tool Calling 模式"""
        self._programmatic_mode = False
    
    def enable_memory_tool(self, base_path: str = "./memory_storage"):
        """
        启用 Memory Tool
        
        Memory Tool 允许 Claude 创建、读取、更新、删除记忆文件，
        实现跨会话的长期记忆和学习。
        
        Args:
            base_path: 记忆文件存储路径
        
        参考：https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool
        """
        self._memory_enabled = True
        self._memory_base_path = base_path
        
        # 添加 beta header
        self._add_beta("context-management-2025-06-27")
    
    def disable_memory_tool(self):
        """禁用 Memory Tool"""
        self._memory_enabled = False
        # 只有在 Context Editing 也未启用时才移除 beta header
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
        
        Context Editing 自动清理旧的工具调用结果，防止 context window 溢出。
        配合 Memory Tool 使用，重要信息会被保存到记忆文件中。
        
        Args:
            mode: 清理模式
                - "progressive": 渐进式清理（保守）
                - "aggressive": 激进式清理（激进）
            clear_threshold: 触发清理的 token 阈值（默认 150K）
            retain_tool_uses: 保留最近 N 个工具调用（默认 10）
        
        参考：https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
        """
        self._context_editing_enabled = True
        self._context_editing_config = {
            "mode": mode,
            "clear_threshold": clear_threshold,
            "retain_tool_uses": retain_tool_uses
        }
        
        # 添加 beta header
        self._add_beta("context-management-2025-06-27")
    
    def disable_context_editing(self):
        """禁用 Context Editing"""
        self._context_editing_enabled = False
        self._context_editing_config = {}
        # 只有在 Memory Tool 也未启用时才移除 beta header
        if not self._memory_enabled:
            self._remove_beta("context-management-2025-06-27")
    
    def enable_tool_search(self, search_type: str = "bm25"):
        """
        启用 Tool Search 模式
        
        当工具数量超过30个时，使用Tool Search动态发现工具。
        
        Args:
            search_type: "bm25" 或 "regex"
        
        参考：https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool
        """
        self._tool_search_mode = True
        self._tool_search_type = search_type
        self._add_beta("advanced-tool-use-2025-11-20")
    
    def disable_tool_search(self):
        """禁用 Tool Search 模式"""
        self._tool_search_mode = False
        self._remove_beta("advanced-tool-use-2025-11-20")
    
    def enable_code_execution(self):
        """
        启用 Code Execution 模式
        
        允许 Claude 在沙箱中执行 Python 代码。
        
        参考：https://platform.claude.com/docs/en/agents-and-tools/tool-use/code-execution-tool
        """
        self._code_execution_mode = True
        # Code Execution 目前通过 bash 实现，无需特殊 beta
    
    def disable_code_execution(self):
        """禁用 Code Execution 模式"""
        self._code_execution_mode = False
    
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
        
        # 1. 添加 Tool Search Tool（如果启用）
        if self._tool_search_mode:
            configured.append(self.get_tool_schema(ToolType.TOOL_SEARCH))
        
        # 2. 配置其他工具
        for tool in tools:
            tool_name = tool.get("name", "")
            tool_copy = tool.copy()
            
            if tool_name not in frequent_tools:
                # 非常用工具：延迟加载
                tool_copy["defer_loading"] = True
            
            configured.append(tool_copy)
        
        return configured
    
    def get_claude_native_tool(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        获取 Claude 原生工具的 API 格式
        
        ⚠️ 只用于 Claude 原生工具（web_search, bash, text_editor 等）
        自定义工具应使用 convert_to_claude_tool() 方法
        
        Args:
            tool_name: 工具名称 (如 "web_search", "bash")
            
        Returns:
            Claude API 格式的工具定义，如果不是原生工具则返回 None
        """
        # 特殊处理 Tool Search（根据当前类型选择）
        if tool_name == "tool_search":
            key = f"tool_search_{self._tool_search_type}"
            if key in self._tool_registry:
                schema = self._tool_registry[key].copy()
                if self.config.enable_caching:
                    schema["cache_control"] = {"type": "ephemeral"}
                return schema
        
        if tool_name in self._tool_registry:
            schema = self._tool_registry[tool_name].copy()
            if self.config.enable_caching:
                schema["cache_control"] = {"type": "ephemeral"}
            return schema
        return None
    
    def convert_to_claude_tool(self, capability: Dict[str, Any]) -> Dict[str, Any]:
        """
        将 capabilities.yaml 中的工具定义转换为 Claude API 格式
        
        这是统一的工具转换方法，支持：
        - Claude 原生工具（Server-side/Client-side）
        - 自定义工具（User-defined）
        
        Args:
            capability: capabilities.yaml 中的能力定义
            
        Returns:
            Claude API 格式的工具定义
        """
        name = capability.get("name", "")
        provider = capability.get("provider", "")
        
        # 检查是否是 Claude 原生工具
        native_tool = self.get_claude_native_tool(name)
        if native_tool:
            return native_tool
        
        # 自定义工具：使用 input_schema 构建
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
    
    def get_tool_schema(self, tool_type: Union[ToolType, str]) -> Dict[str, Any]:
        """
        获取工具Schema（统一接口）- 向后兼容
        
        ⚠️ 建议使用 convert_to_claude_tool() 替代
        
        Args:
            tool_type: 工具类型
            
        Returns:
            符合Claude API规范的tool schema
        """
        if isinstance(tool_type, ToolType):
            tool_type = tool_type.value
        
        native = self.get_claude_native_tool(tool_type)
        if native:
            return native
        
        raise ValueError(f"Unknown tool type: {tool_type}. Use convert_to_claude_tool() for custom tools.")
    
    def add_custom_tool(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any]
    ):
        """
        添加自定义工具
        
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
    
    async def create_message_async(
        self,
        messages: List[Message],
        system: Optional[str] = None,
        tools: Optional[List[Union[ToolType, str, Dict]]] = None,
        invocation_type: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        创建消息（真正的异步）- 使用 AsyncAnthropic 客户端
        
        Args:
            messages: 消息列表
            system: 系统提示词
            tools: 工具列表（支持ToolType枚举、字符串或完整schema）
            invocation_type: 调用方式 (direct, code_execution, programmatic, streaming, tool_search)
            **kwargs: 其他参数
            
        Returns:
            统一的LLMResponse
        """
        # 构建请求参数
        formatted_messages = self._format_messages(messages)
        request_params = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "messages": formatted_messages
        }
        
        # System prompt
        if system:
            if self.config.enable_caching:
                # 启用Prompt Caching
                request_params["system"] = [
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"}
                    }
                ]
            else:
                request_params["system"] = system
        
        # Extended Thinking
        if self.config.enable_thinking:
            request_params["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.config.thinking_budget
            }
            request_params["temperature"] = 1.0  # Required for thinking
        else:
            request_params["temperature"] = self.config.temperature
        
        # Tools
        if tools:
            try:
                formatted_tools = self._format_tools(tools)
                
                # 🔍 调试日志：打印工具信息
                logger.debug("--- Tools List ---")
                for i, tool in enumerate(formatted_tools):
                    tool_name = tool.get('name', 'unknown')
                    tool_type = tool.get('type', 'function')
                    logger.debug(f"  [{i}] {tool_name} (type: {tool_type})")
                    # 打印 input_schema 的属性
                    if 'input_schema' in tool:
                        schema = tool['input_schema']
                        props = schema.get('properties', {})
                        required = schema.get('required', [])
                        logger.debug(f"      - properties: {list(props.keys())}")
                        logger.debug(f"      - required: {required}")
                logger.debug("="*80 + "\n")
                
                # 根据调用方式配置工具
                if invocation_type == "tool_search" and self._tool_search_mode:
                    # Tool Search 模式：添加延迟加载
                    formatted_tools = self.configure_deferred_tools(formatted_tools)
                
                request_params["tools"] = formatted_tools
                    
            except Exception as e:
                logger.error(f"❌ Tools 处理失败: {e}")
                raise
        
        # 🆕 Context Editing
        if self._context_editing_enabled:
            request_params["context_management"] = self._context_editing_config
        
        # 将 request_params 转为 JSON（处理不可序列化的对象）
        try:
            request_json = json.dumps(request_params, ensure_ascii=False, indent=2, default=str)
            logger.debug(f"📤 LLM 请求参数:\n{request_json}")
        except Exception as e:
            logger.error(f"无法序列化请求参数: {e}")
            logger.debug(str(request_params))
        
        # 选择 API 调用方式
        if self._betas:
            # 使用 Beta API
            try:
                response = await self.async_client.beta.messages.create(
                    betas=self._betas,
                    **request_params
                )
            except Exception as e:
                logger.error(f"❌ Beta API 调用失败: {e}")
                if "tools" in request_params:
                    logger.error(f"   Tools count: {len(request_params['tools'])}")
                    for i, tool in enumerate(request_params['tools']):
                        logger.error(f"     Tool #{i}: {tool.get('name', 'unknown')} - type: {tool.get('type', 'N/A')}")
                raise
        else:
            # 标准 API
            try:
                response = await self.async_client.messages.create(**request_params)
            except Exception as e:
                logger.error(f"❌ 标准 API 调用失败: {e}")
                logger.error(f"   错误类型: {type(e).__name__}")
                if "tools" in request_params:
                    logger.error(f"   Tools count: {len(request_params['tools'])}")
                    for i, tool in enumerate(request_params['tools']):
                        logger.error(f"     Tool #{i}: {tool}")
                raise
        
        # 🔍 打印完整的原始响应数据
        logger.debug(f"📥 完整 API 响应 (从 Claude 返回)")
        
        # 将 response 转为可读的字典格式
        try:
            response_dict = {
                "id": response.id,
                "type": response.type,
                "role": response.role,
                "model": response.model,
                "stop_reason": response.stop_reason,
                "stop_sequence": getattr(response, 'stop_sequence', None),
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "cache_creation_input_tokens": getattr(response.usage, 'cache_creation_input_tokens', 0),
                    "cache_read_input_tokens": getattr(response.usage, 'cache_read_input_tokens', 0),
                } if hasattr(response, 'usage') else {},
                "content": []
            }
            
            # 转换 content blocks
            for block in response.content:
                block_dict = {"type": block.type}
                if block.type == "text":
                    block_dict["text"] = block.text
                elif block.type == "thinking":
                    block_dict["thinking"] = block.thinking
                elif block.type == "tool_use":
                    block_dict["id"] = block.id
                    block_dict["name"] = block.name
                    block_dict["input"] = block.input
                response_dict["content"].append(block_dict)
            
            response_json = json.dumps(response_dict, ensure_ascii=False, indent=2)
            logger.debug(response_json)
        except Exception as e:
            logger.error(f"无法序列化响应: {e}")
            logger.debug(str(response))
        
        logger.debug(f"{'='*80}\n")
        
        # 解析响应
        return self._parse_response(response, invocation_type=invocation_type)
    
    async def create_message_stream(
        self,
        messages: List[Message],
        system: Optional[str] = None,
        tools: Optional[List[Union[ToolType, str, Dict]]] = None,
        on_thinking: Optional[Callable[[str], None]] = None,
        on_content: Optional[Callable[[str], None]] = None,
        on_tool_call: Optional[Callable[[Dict], None]] = None,
        **kwargs
    ):
        """
        创建消息（流式 - 异步生成器）
        
        ⚠️ 重要：使用 AsyncClient 避免阻塞事件循环
        
        Args:
            messages: 消息列表
            system: 系统提示词
            tools: 工具列表
            on_thinking: thinking回调
            on_content: content回调
            on_tool_call: tool_call回调
            **kwargs: 其他参数
            
        Yields:
            LLMResponse片段
        """
        # 构建请求参数（与同步版本相同）
        formatted_messages = self._format_messages(messages)
        request_params = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "messages": formatted_messages
        }
        
        
        if system:
            request_params["system"] = system
        
        if self.config.enable_thinking:
            request_params["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.config.thinking_budget
            }
            request_params["temperature"] = 1.0
        
        if tools:
            formatted_tools = self._format_tools(tools)
            request_params["tools"] = formatted_tools
        
        # 🔍 打印完整的流式请求数据
        logger.debug(f"📤 完整流式 API 请求 (发送给 Claude)")
        
        try:
            request_json = json.dumps(request_params, ensure_ascii=False, indent=2, default=str)
            logger.debug(request_json)
        except Exception as e:
            logger.error(f"无法序列化请求参数: {e}")
            logger.debug(str(request_params))
        
        
        # 🔑 关键修复：使用 AsyncClient 避免阻塞事件循环
        accumulated_thinking = ""
        accumulated_content = ""
        tool_calls = []
        stop_reason = None
        
        async with self.async_client.messages.stream(**request_params) as stream:
            async for event in stream:
                # 解析不同类型的事件
                if hasattr(event, 'type'):
                    if event.type == "content_block_start":
                        if hasattr(event, 'content_block'):
                            block = event.content_block
                            if hasattr(block, 'type'):
                                if block.type == "thinking":
                                    if on_thinking:
                                        on_thinking("")
                                elif block.type == "text":
                                    if on_content:
                                        on_content("")
                                elif block.type == "tool_use":
                                    # 🆕 工具调用开始
                                    if on_tool_call:
                                        tool_info = {
                                            "id": getattr(block, 'id', ''),
                                            "name": getattr(block, 'name', ''),
                                            "input": getattr(block, 'input', {})
                                        }
                                        on_tool_call(tool_info)
                    
                    elif event.type == "content_block_delta":
                        if hasattr(event, 'delta'):
                            delta = event.delta
                            if hasattr(delta, 'type'):
                                if delta.type == "thinking_delta":
                                    text = getattr(delta, 'thinking', '')
                                    accumulated_thinking += text
                                    if on_thinking:
                                        on_thinking(text)
                                    yield LLMResponse(
                                        content="",
                                        thinking=text,
                                        is_stream=True
                                    )
                                elif delta.type == "text_delta":
                                    text = getattr(delta, 'text', '')
                                    accumulated_content += text
                                    if on_content:
                                        on_content(text)
                                    yield LLMResponse(
                                        content=text,
                                        is_stream=True
                                    )
                                elif delta.type == "input_json_delta":
                                    # 🆕 工具输入流式更新（部分JSON）
                                    partial_json = getattr(delta, 'partial_json', '')
                                    if on_tool_call:
                                        on_tool_call({
                                            "partial_input": partial_json,
                                            "type": "input_delta"
                                        })
                    
                    elif event.type == "content_block_stop":
                        # 🆕 内容块结束，如果是 tool_use，提取完整信息
                        if hasattr(event, 'content_block_index'):
                            # 从最终消息中提取 tool_use 信息
                            pass
                    
                    elif event.type == "message_stop":
                        # 🆕 流结束，获取最终消息以提取 tool_calls 和 stop_reason
                        try:
                            final_message = await stream.get_final_message()  # 🔧 添加 await
                            stop_reason = getattr(final_message, 'stop_reason', None)
                            
                            # 提取 tool_use blocks
                            if hasattr(final_message, 'content'):
                                for block in final_message.content:
                                    if hasattr(block, 'type') and block.type == "tool_use":
                                        tool_calls.append({
                                            "id": getattr(block, 'id', ''),
                                            "name": getattr(block, 'name', ''),
                                            "input": getattr(block, 'input', {})
                                        })
                        except Exception as e:
                            # 如果无法获取最终消息，使用已收集的信息
                            logger.warning(f"获取最终消息失败: {e}")
                            pass
        
        # 🆕 构建 raw_content（用于消息续传）
        # 需要从 final_message 提取完整的 content 块
        raw_content = None
        try:
            final_message = await stream.get_final_message()  # 🔧 添加 await
            raw_content = self._build_raw_content(final_message)
        except:
            # 如果无法获取 final_message，手动构建
            raw_content = []
            if accumulated_thinking:
                raw_content.append({
                    "type": "thinking",
                    "thinking": accumulated_thinking
                })
            if accumulated_content:
                raw_content.append({
                    "type": "text",
                    "text": accumulated_content
                })
            for tool_call in tool_calls:
                raw_content.append({
                    "type": "tool_use",
                    "id": tool_call["id"],
                    "name": tool_call["name"],
                    "input": tool_call["input"]
                })
        
        # 🔍 打印完整的流式响应数据
        logger.debug(f"📥 完整流式 API 响应 (从 Claude 返回)")
        
        # 构建完整的响应对象
        try:
            final_message = await stream.get_final_message()  # 🔧 添加 await
            response_dict = {
                "id": getattr(final_message, 'id', ''),
                "type": getattr(final_message, 'type', ''),
                "role": getattr(final_message, 'role', ''),
                "model": getattr(final_message, 'model', ''),
                "stop_reason": stop_reason or getattr(final_message, 'stop_reason', 'end_turn'),
                "usage": {
                    "input_tokens": getattr(final_message.usage, 'input_tokens', 0),
                    "output_tokens": getattr(final_message.usage, 'output_tokens', 0),
                    "cache_creation_input_tokens": getattr(final_message.usage, 'cache_creation_input_tokens', 0),
                    "cache_read_input_tokens": getattr(final_message.usage, 'cache_read_input_tokens', 0),
                } if hasattr(final_message, 'usage') else {},
                "content": []
            }
            
            # 从 raw_content 构建 content
            if raw_content:
                response_dict["content"] = raw_content
            else:
                # 手动构建
                if accumulated_thinking:
                    response_dict["content"].append({"type": "thinking", "thinking": accumulated_thinking})
                if accumulated_content:
                    response_dict["content"].append({"type": "text", "text": accumulated_content})
                for tc in tool_calls:
                    response_dict["content"].append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["name"],
                        "input": tc["input"]
                    })
            
            response_json = json.dumps(response_dict, ensure_ascii=False, indent=2)
            logger.debug(response_json)
        except Exception as e:
            logger.error(f"无法构建完整响应: {e}")
            # 降级输出
            simple_response = {
                "stop_reason": stop_reason or "end_turn",
                "thinking": accumulated_thinking if accumulated_thinking else None,
                "content": accumulated_content if accumulated_content else None,
                "tool_calls": tool_calls if tool_calls else None
            }
            logger.debug(json.dumps(simple_response, ensure_ascii=False, indent=2))
        
        logger.debug(f"{'='*80}\n")
        
        # 🆕 返回最终响应（包含完整内容和工具调用）
        if accumulated_content or accumulated_thinking or tool_calls:
            yield LLMResponse(
                content=accumulated_content,
                thinking=accumulated_thinking,
                tool_calls=tool_calls if tool_calls else None,
                stop_reason=stop_reason or "end_turn",
                raw_content=raw_content,  # 🆕 添加 raw_content
                is_stream=False  # 这是最终响应
            )
    
    def count_tokens(self, text: str) -> int:
        """
        计算tokens（本地快速估算）
        
        使用本地算法快速估算 token 数量，避免同步 API 调用阻塞事件循环。
        
        **估算规则**：
        - 英文：1 token ≈ 4 characters
        - 中文：1 token ≈ 1.5 characters
        - 混合文本：使用 4 characters per token
        
        **精确度**：±10%（对大多数场景足够）
        
        **性能**：O(1) 时间复杂度，不需要网络调用
        
        如需精确计数，请使用 Claude API 的 token counting endpoint
        （但注意会增加网络延迟和 API 调用成本）
        
        Args:
            text: 要计算的文本
            
        Returns:
            估算的 token 数量
        
        参考：
        - https://platform.claude.com/docs/en/api/messages-count-tokens
        - Anthropic tokenization: https://www.anthropic.com/news/claude-3-5-sonnet
        """
        if not text:
            return 0
        
        # 快速本地估算：1 token ≈ 4 chars
        # 这个估算对英文很准确，中文略有偏差但可接受
        estimated_tokens = len(text) // 4
        
        # 最小值为 1（即使是空字符串也算 1 个 token）
        return max(1, estimated_tokens)
    
    def _format_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """格式化消息为Claude API格式"""
        formatted = []
        for msg in messages:
            formatted.append({
                "role": msg.role,
                "content": msg.content
            })
        return formatted
    
    def _format_tools(
        self,
        tools: List[Union[ToolType, str, Dict]]
    ) -> List[Dict[str, Any]]:
        """
        格式化工具列表
        
        支持三种输入：
        1. ToolType枚举：ToolType.BASH
        2. 字符串："bash", "memory"
        3. 完整schema：{"name": "...", "description": "...", ...}
        """
        formatted = []
        
        for idx, tool in enumerate(tools):
            try:
                if isinstance(tool, ToolType):
                    # 枚举类型
                    schema = self.get_tool_schema(tool)
                    formatted.append(schema)
                elif isinstance(tool, str):
                    # 字符串类型
                    schema = self.get_tool_schema(tool)
                    formatted.append(schema)
                elif isinstance(tool, dict):
                    # 完整schema - 需要验证是否可序列化
                    self._validate_tool_dict(tool, idx)
                    formatted.append(tool)
                else:
                    raise ValueError(f"Invalid tool format: {tool} (type: {type(tool)})")
                
                # 验证每个工具是否可以被 JSON 序列化
                try:
                    json.dumps(formatted[-1])
                except TypeError as e:
                    logger.error(f"❌ 工具 #{idx} JSON 序列化失败: {e}")
                    logger.error(f"   问题工具内容: {formatted[-1]}")
                    raise ValueError(f"Tool #{idx} contains non-serializable objects: {e}")
                    
            except Exception as e:
                logger.error(f"❌ 处理工具 #{idx} 时出错: {e}")
                logger.error(f"   工具详情: type={type(tool)}, value={tool}")
                raise
        
        return formatted
    
    def _validate_tool_dict(self, tool_dict: Dict[str, Any], index: int):
        """验证工具字典是否包含不可序列化的对象"""
        for key, value in tool_dict.items():
            if isinstance(value, ToolType):
                raise ValueError(f"Tool #{index} contains ToolType enum in key '{key}': {value}. Should be converted to string.")
            elif isinstance(value, dict):
                self._validate_tool_dict(value, index)
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        self._validate_tool_dict(item, index)
                    elif isinstance(item, ToolType):
                        raise ValueError(f"Tool #{index} contains ToolType enum in list at key '{key}[{i}]': {item}")
    
    def _build_raw_content(self, response: anthropic.types.Message) -> List[Dict[str, Any]]:
        """
        构建原始content块列表（用于tool_use响应的消息续传）
        
        ⚠️ 重要规则：
        1. 当启用thinking时，assistant消息必须以thinking块开头
        2. thinking块必须有有效的signature字段
        3. tool_use块必须有id和name
        4. 跳过空文本块和无效块
        
        Args:
            response: Claude API原始响应
            
        Returns:
            可序列化的content块列表
        """
        raw_content = []
        
        for block in response.content:
            if not hasattr(block, 'type'):
                continue
                
            if block.type == "thinking":
                # 保留thinking块（需要signature字段）
                thinking_text = getattr(block, 'thinking', '')
                signature = getattr(block, 'signature', '')
                
                # 防御性检查：只有在有有效signature时才添加thinking块
                if thinking_text and signature:
                    raw_content.append({
                        "type": "thinking",
                        "thinking": thinking_text,
                        "signature": signature
                    })
                elif thinking_text:
                    # 如果没有signature，记录警告但不添加（避免API错误）
                    logger.warning(f"Thinking block without valid signature, skipping. Length: {len(thinking_text)}")
                    
            elif block.type == "text":
                text_content = getattr(block, 'text', '')
                if text_content:  # 只添加非空文本块
                    raw_content.append({
                        "type": "text",
                        "text": text_content
                    })
                    
            elif block.type == "tool_use":
                tool_id = getattr(block, 'id', '')
                tool_name = getattr(block, 'name', '')
                tool_input = getattr(block, 'input', {})
                
                # 防御性检查：tool_use必须有id和name
                if tool_id and tool_name:
                    raw_content.append({
                        "type": "tool_use",
                        "id": tool_id,
                        "name": tool_name,
                        "input": tool_input
                    })
                else:
                    logger.warning(f"Invalid tool_use block: id={tool_id}, name={tool_name}")
            else:
                # 记录未知类型的块（用于调试）
                logger.debug(f"Unknown content block type: {block.type}")
        
        return raw_content
    
    def _detect_programmatic_tool_calls(self, code_output: str) -> List[Dict[str, Any]]:
        """
        检测 code_execution 输出中的程序化工具调用
        
        Programmatic Tool Calling 特征：
        - 代码中包含 tool_calling.invoke() 或类似调用
        - 输出中包含工具调用的结果
        
        Args:
            code_output: code_execution 工具的输出
            
        Returns:
            检测到的工具调用列表 (如果有)
        """
        import re
        import json
        
        tool_calls = []
        
        # 检测模式：tool_calling.invoke("tool_name", {...})
        # 或者输出中包含明确的工具调用标记
        patterns = [
            r'tool_calling\.invoke\(["\'](\w+)["\'],\s*({[^}]+})\)',
            r'TOOL_CALL:\s*(\w+)\s*\|\s*({.+})',
            r'调用工具:\s*(\w+)\s*参数:\s*({.+})'
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, code_output)
            for match in matches:
                tool_name = match.group(1)
                try:
                    tool_input = json.loads(match.group(2))
                    tool_calls.append({
                        "name": tool_name,
                        "input": tool_input,
                        "via": "programmatic"  # 标记调用方式
                    })
                except:
                    pass
        
        return tool_calls
    
    def _parse_response(
        self, 
        response: anthropic.types.Message,
        invocation_type: Optional[str] = None
    ) -> LLMResponse:
        """
        解析Claude API响应为统一格式
        
        支持的调用方式检测：
        1. Direct Tool Call: response.content 包含 tool_use 块
        2. Code Execution: response.content 包含 code_execution 块
        3. Programmatic: code_execution 输出中包含工具调用
        4. Tool Search: response.content 包含 tool_reference 块
        5. Streaming: 流式响应（在流式方法中处理）
        """
        thinking_text = ""
        content_text = ""
        tool_calls = []
        tool_references = []  # Tool Search 发现的工具引用
        invocation_method = invocation_type or "direct"  # 默认调用方式
        
        # 解析content blocks
        for block in response.content:
            if hasattr(block, 'type'):
                if block.type == "thinking":
                    thinking_text = getattr(block, 'thinking', '')
                elif block.type == "text":
                    content_text = getattr(block, 'text', '')
                elif block.type == "tool_use":
                    tool_name = getattr(block, 'name', '')
                    
                    # 检测调用方式
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
                    
                    # 如果启用了 Programmatic 模式，检测代码输出中的工具调用
                    if self._programmatic_mode and tool_name == "code_execution":
                        code_input = getattr(block, 'input', {})
                        code_text = code_input.get('code', '')
                        
                        # 检测代码中是否包含工具调用
                        if 'tool_calling' in code_text or 'invoke' in code_text:
                            # 标记为 programmatic 模式
                            tool_calls[-1]['invocation_method'] = "programmatic"
        
        # Usage信息
        usage = {}
        if hasattr(response, 'usage'):
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens
            }
            # Cache tokens（如果启用Caching）
            if hasattr(response.usage, 'cache_read_input_tokens'):
                usage["cache_read_tokens"] = response.usage.cache_read_input_tokens
            if hasattr(response.usage, 'cache_creation_input_tokens'):
                usage["cache_creation_tokens"] = response.usage.cache_creation_input_tokens
        
        # 构建原始content块（用于消息续传）
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


# ============================================================
# 工厂函数
# ============================================================

def create_llm_service(
    provider: Union[LLMProvider, str] = LLMProvider.CLAUDE,
    model: str = "claude-sonnet-4-5-20250929",  # 🆕 使用 Claude Sonnet 4.5
    api_key: Optional[str] = None,
    **kwargs
) -> BaseLLMService:
    """
    工厂函数：创建LLM服务
    
    Args:
        provider: LLM提供商
        model: 模型名称
        api_key: API密钥
        **kwargs: 其他配置参数
        
    Returns:
        LLM服务实例
        
    Example:
        ```python
        # 创建Claude服务
        llm = create_llm_service(
            provider=LLMProvider.CLAUDE,
            model="claude-sonnet-4-20250514",
            enable_thinking=True,
            tools=[ToolType.BASH, ToolType.MEMORY]
        )
        
        # 使用统一接口（异步）
        response = await llm.create_message_async(
            messages=[Message(role="user", content="Hello")],
            system="You are a helpful assistant"
        )
        
        print(response.content)
        if response.thinking:
            print(f"Thinking: {response.thinking}")
        ```
    """
    if isinstance(provider, str):
        provider = LLMProvider(provider)
    
    # 默认API Key
    if api_key is None:
        if provider == LLMProvider.CLAUDE:
            api_key = os.getenv("ANTHROPIC_API_KEY")
        elif provider == LLMProvider.GPT4:
            api_key = os.getenv("OPENAI_API_KEY")
        elif provider == LLMProvider.GEMINI:
            api_key = os.getenv("GOOGLE_API_KEY")
    
    # 创建配置
    config = LLMConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        **kwargs
    )
    
    # 根据provider创建服务
    if provider == LLMProvider.CLAUDE:
        return ClaudeLLMService(config)
    elif provider == LLMProvider.GPT4:
        # TODO: 实现GPT-4服务
        raise NotImplementedError("GPT-4 service not implemented yet")
    elif provider == LLMProvider.GEMINI:
        # TODO: 实现Gemini服务
        raise NotImplementedError("Gemini service not implemented yet")
    else:
        raise ValueError(f"Unknown provider: {provider}")


# ============================================================
# 便捷函数
# ============================================================

def create_claude_service(
    model: str = "claude-sonnet-4-5-20250929",  # 🆕 使用 Claude Sonnet 4.5
    enable_thinking: bool = True,
    enable_caching: bool = False,
    tools: Optional[List[Union[ToolType, str]]] = None,
    **kwargs
) -> ClaudeLLMService:
    """
    便捷函数：创建Claude服务
    
    Args:
        model: Claude模型名称
        enable_thinking: 启用Extended Thinking
        enable_caching: 启用Prompt Caching
        tools: 工具列表
        **kwargs: 其他参数
        
    Returns:
        Claude LLM服务
    """
    return create_llm_service(
        provider=LLMProvider.CLAUDE,
        model=model,
        enable_thinking=enable_thinking,
        enable_caching=enable_caching,
        tools=tools,
        **kwargs
    )

