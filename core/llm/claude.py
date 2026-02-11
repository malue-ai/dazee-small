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
- Skills API (Custom Skills)
- Files API (文件上传/下载)
- Citations (引用)

参考：
- https://platform.claude.com/docs/en/build-with-claude/overview
- https://platform.claude.com/docs/en/api/overview
- https://docs.claude.com/en/docs/build-with-claude/skills
- https://docs.claude.com/en/docs/build-with-claude/citations
"""

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Union

import aiofiles
import anthropic
import httpx

from core.tool.registry_config import get_frequent_tools  # 🆕 从统一配置读取
from infra.resilience import with_retry  # 🆕 V7.3: 使用统一的重试机制
from logger import get_logger
from utils.message_utils import messages_to_dict_list

from .adaptor import ClaudeAdaptor
from .base import BaseLLMService, LLMConfig, LLMProvider, LLMResponse, Message, ToolType

# ============================================================
# Files API 数据结构
# ============================================================


@dataclass
class FileInfo:
    """文件信息"""

    file_id: str
    filename: str
    size_bytes: int
    mime_type: str
    created_at: str
    downloadable: bool = True


logger = get_logger("llm.claude")

# 详细日志开关：设置 LLM_DEBUG_VERBOSE=1 可打印完整请求/响应
LLM_DEBUG_VERBOSE = os.getenv("LLM_DEBUG_VERBOSE", "").lower() in ("1", "true", "yes")


class ClaudeLLMService(BaseLLMService):
    """
    Claude LLM 服务实现

    支持的功能：
    - Extended Thinking: 深度推理能力
    - Prompt Caching: 减少重复 token 消耗
    - Client Tools: computer_use
    - Context Editing: 自动清理长上下文

    注：所有服务器工具已移除，搜索通过 Skills 提供

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
    # 注：所有服务器工具已移除（web_search, code_execution, tool_search, memory）
    # 搜索通过 Skills 提供
    NATIVE_TOOLS = {
        # Client-side Tools
        "computer": {
            "type": "computer_20250124",
            "name": "computer",
            "display_width_px": 1024,
            "display_height_px": 768,
        },
    }

    def __init__(self, config: LLMConfig):
        """
        初始化 Claude 服务

        Args:
            config: LLM 配置
        """
        self.config = config

        # 消息适配器（统一处理消息格式转换）
        self._adaptor = ClaudeAdaptor()

        # 🆕 V5.0: 使用配置中的超时和重试设置
        timeout = getattr(config, "timeout", 120.0)
        max_retries = getattr(config, "max_retries", 3)

        # 🔍 DEBUG: 打印 API Key 信息（仅显示前8位和后4位）
        api_key = config.api_key or ""
        if api_key:
            masked_key = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
            logger.info(f"🔑 Claude API Key: {masked_key} (长度: {len(api_key)})")
        else:
            logger.warning("⚠️ Claude API Key 为空！")

        # 🆕 支持自定义 API 端点（如万界方舟）
        # 优先级：config.base_url > ANTHROPIC_BASE_URL 环境变量 > None（使用官方默认）
        base_url = getattr(config, "base_url", None) or os.getenv("ANTHROPIC_BASE_URL") or None

        # 🔧 如果 base_url 是官方默认地址，将其设置为 None（让 SDK 使用默认值）
        # 这样可以避免 SDK 的认证检查问题
        if base_url == "https://api.anthropic.com":
            base_url = None

        # 🔧 万界方舟需要 Authorization: Bearer 认证，而不是 x-api-key
        # 检测是否使用万界方舟端点
        is_wanjie = base_url and "wanjiedata.com" in base_url

        if base_url:
            logger.info(f"🌐 使用自定义 API 端点: {base_url}")
            if is_wanjie:
                logger.info("🔑 检测到万界方舟，使用 Bearer Token 认证")

        # 异步客户端（增加 timeout 和重试配置）
        # 注意：对于流式响应，timeout 是首个响应的超时，不是整体超时
        if is_wanjie:
            # 万界方舟：使用 auth_token（Bearer 认证）
            self.async_client = anthropic.AsyncAnthropic(
                auth_token=config.api_key,
                base_url=base_url,
                timeout=timeout,
                max_retries=max_retries,
            )
            self.sync_client = anthropic.Anthropic(
                auth_token=config.api_key,
                base_url=base_url,
                timeout=timeout,
                max_retries=max_retries,
            )
        else:
            # 官方 API：使用 api_key（x-api-key 认证）
            # 当 base_url 为 None 时，SDK 会使用默认的官方端点
            self.async_client = anthropic.AsyncAnthropic(
                api_key=config.api_key, base_url=base_url, timeout=timeout, max_retries=max_retries
            )
            self.sync_client = anthropic.Anthropic(
                api_key=config.api_key, base_url=base_url, timeout=timeout, max_retries=max_retries
            )

        # Beta 功能配置
        self._betas: List[str] = []

        # 调用方式配置
        self._programmatic_mode = False

        # Context Editing 配置
        self._context_editing_enabled = False
        self._context_editing_config: Dict[str, Any] = {}

        # 工具注册表（用于自定义工具）
        self._tool_registry: Dict[str, Dict[str, Any]] = {}

        # 自定义工具存储
        self._custom_tools: List[Dict[str, Any]] = []

        # Citations 配置
        self._citations_enabled = False

    # ============================================================
    # Beta Headers 管理
    # ============================================================

    def _add_beta(self, beta_header: str) -> None:
        """添加 Beta Header"""
        if beta_header not in self._betas:
            self._betas.append(beta_header)

    def _remove_beta(self, beta_header: str) -> None:
        """移除 Beta Header"""
        if beta_header in self._betas:
            self._betas.remove(beta_header)

    # ============================================================
    # 功能开关
    # ============================================================

    def enable_context_editing(
        self, mode: str = "progressive", clear_threshold: int = 150000, retain_tool_uses: int = 10
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
            "retain_tool_uses": retain_tool_uses,
        }
        self._add_beta("context-management-2025-06-27")

    def disable_context_editing(self) -> None:
        """禁用 Context Editing"""
        self._context_editing_enabled = False
        self._context_editing_config = {}
        self._remove_beta("context-management-2025-06-27")

    def enable_programmatic_tool_calling(self) -> None:
        """启用 Programmatic Tool Calling 模式"""
        self._programmatic_mode = True

    def disable_programmatic_tool_calling(self) -> None:
        """禁用 Programmatic Tool Calling 模式"""
        self._programmatic_mode = False

    # ============================================================
    # 自定义工具管理
    # ============================================================

    def add_custom_tool(self, name: str, description: str, input_schema: Dict[str, Any]) -> None:
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
                    "input_schema": input_schema,
                }
                logger.debug(f"更新自定义工具: {name}")
                return

        # 添加新工具
        self._custom_tools.append(
            {"name": name, "description": description, "input_schema": input_schema}
        )
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
        if tool_name in self.NATIVE_TOOLS:
            schema = self.NATIVE_TOOLS[tool_name].copy()
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
        input_schema = capability.get(
            "input_schema", {"type": "object", "properties": {}, "required": []}
        )
        description = capability.get("metadata", {}).get("description", f"Tool: {name}")

        tool_def = {"name": name, "description": description, "input_schema": input_schema}

        # 🔧 不在这里添加 cache_control，统一在 create_message_* 方法中处理
        # Claude API 限制最多 4 个带 cache_control 的 block

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
        self, tools: List[Dict[str, Any]], frequent_tools: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        配置延迟加载的工具

        Args:
            tools: 工具定义列表
            frequent_tools: 常用工具名称（不延迟加载）

        Returns:
            配置好的工具列表
        """
        if frequent_tools is None:
            # 🆕 从 config/tool_registry.yaml 统一配置读取
            frequent_tools = get_frequent_tools()

        configured = []

        # 配置工具
        for tool in tools:
            tool_name = tool.get("name", "")
            tool_copy = tool.copy()

            if tool_name not in frequent_tools:
                tool_copy["defer_loading"] = True

            configured.append(tool_copy)

        return configured

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

    def _validate_tool_dict(self, tool_dict: Dict[str, Any], index: int) -> None:
        """验证工具字典是否包含不可序列化的对象"""
        for key, value in tool_dict.items():
            if isinstance(value, ToolType):
                raise ValueError(f"Tool #{index} contains ToolType enum in key '{key}': {value}")
            elif isinstance(value, dict):
                self._validate_tool_dict(value, index)
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        self._validate_tool_dict(item, index)
                    elif isinstance(item, ToolType):
                        raise ValueError(f"Tool #{index} contains ToolType in list '{key}[{i}]'")

    # ============================================================
    # 缓存断点管理
    # ============================================================

    def _apply_cache_breakpoints(self, system_blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        🆕 前缀缓存优化：智能添加多层缓存断点

        Claude 的缓存是累积式前缀匹配：
        - 从开头到断点的整个前缀序列会被缓存
        - 多个断点可以实现分级缓存，提高不同场景的命中率
        - 最多支持 4 个断点

        策略：
        - 根据 _cache_layer 元数据识别每层的缓存边界
        - 在每层的最后一个 block 添加 cache_control
        - 动态内容（_cache_layer=0）不添加断点

        缓存效果：
        - 断点 1 (框架规则): 跨 Agent、跨用户共享
        - 断点 2 (实例提示词): 同 Agent 不同用户共享
        - 断点 3 (Skills+工具): 同 Agent 同用户不同轮次共享

        Args:
            system_blocks: 带 _cache_layer 元数据的 system blocks

        Returns:
            添加了 cache_control 的 system blocks
        """
        if not system_blocks:
            return system_blocks

        # 🔍 分析每层的边界
        # 找到每个 cache_layer 的最后一个 block 索引
        layer_boundaries: Dict[int, int] = {}  # {layer: last_index}

        for idx, block in enumerate(system_blocks):
            layer = block.get("_cache_layer", 0)
            if layer > 0:  # 只处理需要缓存的层
                layer_boundaries[layer] = idx

        # 🔧 在每层边界添加缓存断点（最多 4 个）
        # Claude API 限制最多 4 个带 cache_control 的 block
        breakpoint_count = 0
        max_breakpoints = 4

        # 按层级排序（1, 2, 3...），依次添加断点
        for layer in sorted(layer_boundaries.keys()):
            if breakpoint_count >= max_breakpoints:
                logger.warning(f"⚠️ 已达到缓存断点上限 ({max_breakpoints})，跳过 Layer {layer}")
                break

            idx = layer_boundaries[layer]
            system_blocks[idx]["cache_control"] = {"type": "ephemeral", "ttl": "1h"}
            breakpoint_count += 1

            # 计算该层的 token 数（用于日志）
            layer_text = system_blocks[idx].get("text", "")
            layer_tokens = self.count_tokens(layer_text)

            logger.debug(
                f"🔒 缓存断点 {breakpoint_count}: block[{idx}] "
                f"(Layer {layer}, ~{layer_tokens:,} tokens, 1h TTL)"
            )

        # 📊 缓存策略日志
        total_cached_tokens = sum(
            self.count_tokens(b.get("text", "")) for b in system_blocks if b.get("cache_control")
        )
        uncached_blocks = [i for i, b in enumerate(system_blocks) if not b.get("cache_control")]

        logger.info(
            f"🗂️ 前缀缓存策略: {breakpoint_count} 个断点, "
            f"~{total_cached_tokens:,} tokens 可缓存, "
            f"未缓存 blocks: {uncached_blocks or '无'}"
        )

        return system_blocks

    # ============================================================
    # 核心 API 方法
    # ============================================================

    @with_retry(
        max_retries=3,
        base_delay=1.0,
        retryable_errors=(
            # Anthropic 特定异常
            anthropic.APIConnectionError,
            anthropic.APITimeoutError,
            anthropic.RateLimitError,
            # HTTPX 底层异常
            httpx.RemoteProtocolError,
            httpx.ConnectError,
            httpx.TimeoutException,
        ),
    )
    async def create_message_async(
        self,
        messages: List[Message],
        system: Optional[Union[str, List[Dict[str, Any]]]] = None,
        tools: Optional[List[Union[ToolType, str, Dict]]] = None,
        invocation_type: Optional[str] = None,
        override_thinking: Optional[bool] = None,
        is_probe: bool = False,
        **kwargs,
    ) -> LLMResponse:
        """
        创建消息（异步）

        🆕 V7.3: 自动网络重试（指数退避策略）
        - 最大重试 3 次
        - 基础延迟 1 秒（指数增长：1s → 2s → 4s）
        - 自动处理：连接错误、超时、限流（429）

        Args:
            messages: 消息列表
            system: 系统提示词，支持两种格式：
                - str: 单层缓存（向后兼容，启用缓存时自动包装为 5 分钟 TTL）
                - List[Dict]: 多层缓存（支持自定义 TTL，如 1h）
            tools: 工具列表
            invocation_type: 调用方式
            is_probe: 是否为探测请求（探测失败不记录 ERROR）
            **kwargs: 其他参数（支持 max_tokens, temperature 覆盖）

        Returns:
            LLMResponse 响应对象

        Example:
            # 单层缓存（向后兼容）
            response = await llm.create_message_async(messages, system="You are helpful")

            # 多层缓存（Claude 固定 5 分钟 TTL）
            system_blocks = [
                {"type": "text", "text": "框架规则", "cache_control": {"type": "ephemeral", "ttl": "1h"}},
                {"type": "text", "text": "实例提示词", "cache_control": {"type": "ephemeral", "ttl": "1h"}},
                {"type": "text", "text": "用户画像"}  # 不缓存
            ]
            response = await llm.create_message_async(messages, system=system_blocks)
        """
        # 构建请求参数（支持 kwargs 覆盖）
        # 使用 adaptor 转换消息（自动处理 tool_result 分离等）
        converted = self._adaptor.convert_messages_to_provider(messages)
        formatted_messages = converted["messages"]

        # 🛡️ 断言：adaptor 层已确保消息以 user 结尾，此处仅检测异常
        if formatted_messages and formatted_messages[-1].get("role") == "assistant":
            logger.error(
                "🐛 [Async] adaptor 输出的消息仍以 assistant 结尾"
                f"（共 {len(formatted_messages)} 条），请排查 adaptor 逻辑"
            )

        request_params = {
            "model": self.config.model,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "messages": formatted_messages,
        }

        # System prompt（支持多层缓存）
        if system:
            if isinstance(system, list):
                # 多层缓存格式：智能添加缓存断点
                system_blocks = [
                    block.copy() if isinstance(block, dict) else {"type": "text", "text": block}
                    for block in system
                ]

                if self.config.enable_caching and system_blocks:
                    # 🆕 前缀缓存优化：根据 _cache_layer 元数据智能添加断点
                    system_blocks = self._apply_cache_breakpoints(system_blocks)

                # 清理元数据（Claude API 不接受自定义字段）
                for block in system_blocks:
                    block.pop("_cache_layer", None)

                request_params["system"] = system_blocks
                logger.debug(f"🗂️ 使用多层缓存 system prompt: {len(system_blocks)} 层")
            elif self.config.enable_caching:
                # 字符串格式 + 启用缓存：自动包装为单层缓存（1 小时 TTL）
                request_params["system"] = [
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral", "ttl": "1h"},
                    }
                ]
            else:
                # 字符串格式 + 禁用缓存：直接使用
                request_params["system"] = system

        # Extended Thinking（支持动态覆盖）
        # override_thinking 优先级高于配置：None=使用配置, True/False=强制开启/关闭
        effective_thinking = (
            override_thinking if override_thinking is not None else self.config.enable_thinking
        )
        if effective_thinking:
            request_params["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.config.thinking_budget,
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
                all_tools.append(tool_def)
                tool_names_seen.add(tool_name)

        if all_tools:
            # 🔧 缓存策略：只对最后一个工具添加 cache_control（1 小时 TTL）
            # Claude API 限制最多 4 个带 cache_control 的 block
            # 工具定义在运行期稳定，使用较长的缓存时间
            if self.config.enable_caching and all_tools:
                all_tools[-1] = all_tools[-1].copy()
                all_tools[-1]["cache_control"] = {"type": "ephemeral", "ttl": "1h"}

            request_params["tools"] = all_tools

            # tool_choice: force specific tool usage (e.g. structured output)
            tool_choice = kwargs.get("tool_choice")
            if tool_choice:
                request_params["tool_choice"] = tool_choice

            # 调试日志
            logger.debug(f"Tools: {[t.get('name', 'unknown') for t in all_tools]}")

        # Context Editing
        if self._context_editing_enabled:
            request_params["context_management"] = self._context_editing_config

        # 调试日志
        logger.debug(f"📤 LLM 请求: model={self.config.model}, messages={len(messages)}")

        # 🚨 调试日志：打印完整 messages（用于排查 403 错误）
        logger.info("=" * 80)
        logger.info("🔍 [DEBUG-ASYNC] 完整 request_params:")
        logger.info(f"   model: {request_params.get('model')}")
        logger.info(f"   max_tokens: {request_params.get('max_tokens')}")
        if "system" in request_params:
            system_val = request_params.get("system")
            if isinstance(system_val, list):
                logger.info(f"   system: (list, {len(system_val)} blocks)")
            else:
                logger.info(f"   system: {str(system_val)[:200]}...")
        logger.info(f"   messages ({len(request_params.get('messages', []))}):")
        for i, msg in enumerate(request_params.get("messages", [])):
            logger.info(f"   ── Message [{i}] ──")
            logger.info(f"      role: {msg.get('role')}")
            content = msg.get("content")
            if isinstance(content, list):
                logger.info(f"      content: (list, {len(content)} blocks)")
                for j, block in enumerate(content):
                    if isinstance(block, dict):
                        block_type = block.get("type", "unknown")
                        if block_type == "text":
                            text_preview = str(block.get("text", ""))[:300]
                            logger.info(f"         [{j}] type=text, text={text_preview}...")
                        elif block_type == "tool_use":
                            logger.info(
                                f"         [{j}] type=tool_use, id={block.get('id')}, name={block.get('name')}"
                            )
                        elif block_type == "tool_result":
                            logger.info(
                                f"         [{j}] type=tool_result, tool_use_id={block.get('tool_use_id')}"
                            )
                        else:
                            logger.info(f"         [{j}] type={block_type}")
                    else:
                        logger.info(f"         [{j}] (non-dict): {str(block)[:100]}...")
            elif isinstance(content, str):
                logger.info(f"      content: {content[:300]}...")
            else:
                logger.info(f"      content: (type={type(content).__name__})")
        logger.info("=" * 80)

        # API 调用
        try:
            if self._betas:
                response = await self.async_client.beta.messages.create(
                    betas=self._betas, **request_params
                )
            else:
                response = await self.async_client.messages.create(**request_params)
        except Exception as e:
            # 探测请求失败时不记录 ERROR（在 router.probe 中已记录 INFO）
            if not is_probe:
                logger.error(f"Claude API 调用失败: {e}")
            raise

        # 调试日志
        logger.debug(f"📥 LLM 响应: stop_reason={response.stop_reason}")

        return self._parse_response(response, invocation_type)

    async def create_message_stream(
        self,
        messages: List[Message],
        system: Optional[Union[str, List[Dict[str, Any]]]] = None,
        tools: Optional[List[Union[ToolType, str, Dict]]] = None,
        on_thinking: Optional[Callable[[str], None]] = None,
        on_content: Optional[Callable[[str], None]] = None,
        on_tool_call: Optional[Callable[[Dict], None]] = None,
        override_thinking: Optional[bool] = None,
        **kwargs,
    ) -> AsyncIterator[LLMResponse]:
        """
        创建消息（流式）

        Args:
            messages: 消息列表
            system: 系统提示词，支持两种格式：
                - str: 单层缓存（向后兼容，启用缓存时自动包装为 5 分钟 TTL）
                - List[Dict]: 多层缓存（支持自定义 TTL，如 1h）
            tools: 工具列表
            on_thinking: thinking 回调
            on_content: content 回调
            on_tool_call: tool_call 回调
            override_thinking: 动态覆盖 thinking 配置（None 使用默认配置，True/False 强制开启/关闭）
            **kwargs: 其他参数（支持 max_tokens 覆盖）

        Yields:
            LLMResponse 片段
        """
        # 构建请求参数（支持 kwargs 覆盖）
        # 使用 adaptor 转换消息（自动处理 tool_result 分离等）
        converted = self._adaptor.convert_messages_to_provider(messages)
        formatted_messages = converted["messages"]

        # 🛡️ 断言：adaptor 层已确保消息以 user 结尾，此处仅检测异常
        if formatted_messages and formatted_messages[-1].get("role") == "assistant":
            logger.error(
                "🐛 [Stream] adaptor 输出的消息仍以 assistant 结尾"
                f"（共 {len(formatted_messages)} 条），请排查 adaptor 逻辑"
            )

        request_params = {
            "model": self.config.model,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "messages": formatted_messages,
        }

        # System prompt（支持多层缓存，与 create_message_async 保持一致）
        if system:
            if isinstance(system, list):
                # 多层缓存格式：智能添加缓存断点
                system_blocks = [
                    block.copy() if isinstance(block, dict) else {"type": "text", "text": block}
                    for block in system
                ]

                if self.config.enable_caching and system_blocks:
                    # 🆕 前缀缓存优化：根据 _cache_layer 元数据智能添加断点
                    system_blocks = self._apply_cache_breakpoints(system_blocks)

                # 清理元数据（Claude API 不接受自定义字段）
                for block in system_blocks:
                    block.pop("_cache_layer", None)

                request_params["system"] = system_blocks
                logger.debug(f"🗂️ [Stream] 使用多层缓存 system prompt: {len(system_blocks)} 层")
            elif self.config.enable_caching:
                # 字符串格式 + 启用缓存：自动包装为单层缓存（1 小时 TTL）
                request_params["system"] = [
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral", "ttl": "1h"},
                    }
                ]
            else:
                # 字符串格式 + 禁用缓存：直接使用
                request_params["system"] = system

        # Extended Thinking（支持动态覆盖）
        # override_thinking 优先级高于配置：None=使用配置, True/False=强制开启/关闭
        effective_thinking = (
            override_thinking if override_thinking is not None else self.config.enable_thinking
        )
        if effective_thinking:
            request_params["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.config.thinking_budget,
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
                all_tools.append(tool_def)
                tool_names_seen.add(tool_name)

        if all_tools:
            # 🔧 缓存策略：只对最后一个工具添加 cache_control（1 小时 TTL）
            # Claude API 限制最多 4 个带 cache_control 的 block
            if self.config.enable_caching:
                all_tools[-1] = all_tools[-1].copy()
                all_tools[-1]["cache_control"] = {"type": "ephemeral", "ttl": "1h"}

            request_params["tools"] = all_tools

        # 请求日志（INFO 级别）
        logger.info(
            f"📤 Claude 请求: model={self.config.model}, tools={len(all_tools)}, messages={len(formatted_messages)}"
        )

        # Request detail logging (DEBUG level to avoid stdout buffer overflow)
        if logger.isEnabledFor(10):  # DEBUG
            logger.debug("=" * 80)
            logger.debug("🔍 完整 request_params:")
            logger.debug(f"   model: {request_params.get('model')}")
            logger.debug(f"   max_tokens: {request_params.get('max_tokens')}")
            if "thinking" in request_params:
                logger.debug(f"   thinking: {request_params.get('thinking')}")
            if "system" in request_params:
                system_val = request_params.get("system")
                if isinstance(system_val, list):
                    logger.debug(f"   system: (list, {len(system_val)} blocks)")
                    for idx, block in enumerate(system_val):
                        if isinstance(block, dict):
                            text_preview = str(block.get("text", ""))[:200]
                            logger.debug(
                                f"      [{idx}] type={block.get('type')}, text={text_preview}..."
                            )
                else:
                    logger.debug(f"   system: {str(system_val)[:200]}...")
            logger.debug(f"   messages ({len(request_params.get('messages', []))}):")
            for i, msg in enumerate(request_params.get("messages", [])):
                logger.debug(f"   ── Message [{i}] ──")
                logger.debug(f"      role: {msg.get('role')}")
                content = msg.get("content")
                if isinstance(content, list):
                    logger.debug(f"      content: (list, {len(content)} blocks)")
                    for j, block in enumerate(content):
                        if isinstance(block, dict):
                            block_type = block.get("type", "unknown")
                            if block_type == "text":
                                text_preview = str(block.get("text", ""))[:300]
                                logger.debug(f"         [{j}] type=text, text={text_preview}...")
                            elif block_type == "tool_use":
                                logger.debug(
                                    f"         [{j}] type=tool_use, id={block.get('id')}, name={block.get('name')}"
                                )
                            elif block_type == "tool_result":
                                logger.debug(
                                    f"         [{j}] type=tool_result, tool_use_id={block.get('tool_use_id')}"
                                )
                            else:
                                logger.debug(
                                    f"         [{j}] type={block_type}"
                                )
                elif isinstance(content, str):
                    logger.debug(f"      content: {content[:300]}...")
            if "tools" in request_params:
                logger.debug(f"   tools ({len(request_params['tools'])}):")
                for tool in request_params["tools"]:
                    logger.debug(f"      - {tool.get('name', 'unknown')}")
            logger.debug("=" * 80)

        # 详细日志：完整请求参数
        if LLM_DEBUG_VERBOSE:
            logger.info("=" * 60)
            logger.info("📤 [VERBOSE] 完整请求参数:")
            # 复制一份，避免修改原始数据
            verbose_params = request_params.copy()
            # 打印 system prompt（可能很长，截断）
            if "system" in verbose_params:
                system_preview = str(verbose_params["system"])[:500]
                logger.info(
                    f"   system: {system_preview}{'...' if len(str(verbose_params['system'])) > 500 else ''}"
                )
            # 打印完整 messages（安全序列化）
            logger.info(f"   messages ({len(verbose_params.get('messages', []))}):")
            for i, msg in enumerate(verbose_params.get("messages", [])):
                msg_preview = self._safe_json_dumps(msg, indent=2)
                logger.info(f"   [{i}] {msg_preview}")
            # 打印 tools
            if "tools" in verbose_params:
                logger.info(f"   tools ({len(verbose_params['tools'])}):")
                for tool in verbose_params["tools"]:
                    logger.info(f"      - {tool.get('name', 'unknown')}")
            logger.info("=" * 60)
        else:
            logger.debug(f"📤 Messages 数量: {len(request_params.get('messages', []))}")
        for i, msg in enumerate(request_params.get("messages", [])):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                types = [b.get("type", "unknown") for b in content if isinstance(b, dict)]
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
        final_message = None  # 🚨 必须在 try 外初始化，防止中断时 UnboundLocalError

        # 🔄 流式重试配置：网络中断时自动重试（最多 2 次）
        _STREAM_MAX_RETRIES = 2
        _stream_attempt = 0

        event_count = 0  # 🚨 在 try 外初始化，确保 except 中可用
        try:
            stream_ctx = self.async_client.messages.stream(**request_params)

            async with stream_ctx as stream:
                async for event in stream:
                    event_count += 1
                    if not hasattr(event, "type"):
                        continue

                    if event.type == "content_block_start":
                        if hasattr(event, "content_block"):
                            block = event.content_block
                            if hasattr(block, "type"):
                                block_type = block.type

                                if block_type == "thinking" and on_thinking:
                                    on_thinking("")
                                elif block_type == "text" and on_content:
                                    on_content("")
                                # 🆕 客户端工具调用 - 立即 yield tool_use_start
                                elif block_type == "tool_use":
                                    tool_id = getattr(block, "id", "")
                                    tool_name = getattr(block, "name", "")
                                    if on_tool_call:
                                        on_tool_call(
                                            {
                                                "id": tool_id,
                                                "name": tool_name,
                                                "input": {},  # input 后续流式发送
                                                "type": "tool_use",
                                            }
                                        )
                                    # 🆕 yield tool_use_start 事件
                                    yield LLMResponse(
                                        content="",
                                        model=self.config.model,  # 🆕
                                        is_stream=True,
                                        tool_use_start={
                                            "id": tool_id,
                                            "name": tool_name,
                                            "type": "tool_use",
                                        },
                                    )

                    elif event.type == "content_block_delta":
                        if hasattr(event, "delta"):
                            delta = event.delta
                            if hasattr(delta, "type"):
                                if delta.type == "thinking_delta":
                                    text = getattr(delta, "thinking", "")
                                    accumulated_thinking += text
                                    if on_thinking:
                                        on_thinking(text)
                                    yield LLMResponse(
                                        content="",
                                        thinking=text,
                                        model=self.config.model,
                                        is_stream=True,
                                    )

                                elif delta.type == "text_delta":
                                    text = getattr(delta, "text", "")
                                    accumulated_content += text
                                    if on_content:
                                        on_content(text)
                                    yield LLMResponse(
                                        content=text, model=self.config.model, is_stream=True
                                    )

                                elif delta.type == "input_json_delta":
                                    partial_json = getattr(delta, "partial_json", "")
                                    if on_tool_call:
                                        on_tool_call(
                                            {"partial_input": partial_json, "type": "input_delta"}
                                        )
                                    # 🆕 yield input_delta 事件
                                    yield LLMResponse(
                                        content="",
                                        model=self.config.model,  # 🆕
                                        is_stream=True,
                                        input_delta=partial_json,
                                    )

                    elif event.type == "message_stop":
                        final_message = None
                        try:
                            final_message = await stream.get_final_message()
                            stop_reason = getattr(final_message, "stop_reason", None)

                            # 🔢 提取 usage 信息
                            if hasattr(final_message, "usage") and final_message.usage:
                                usage = {
                                    "input_tokens": final_message.usage.input_tokens,
                                    "output_tokens": final_message.usage.output_tokens,
                                    "thinking_tokens": 0,  # 🆕 Extended Thinking tokens
                                }
                                if hasattr(final_message.usage, "cache_read_input_tokens"):
                                    usage["cache_read_tokens"] = (
                                        final_message.usage.cache_read_input_tokens
                                    )
                                if hasattr(final_message.usage, "cache_creation_input_tokens"):
                                    usage["cache_creation_tokens"] = (
                                        final_message.usage.cache_creation_input_tokens
                                    )

                                # 🆕 计算 Extended Thinking tokens
                                if accumulated_thinking:
                                    usage["thinking_tokens"] = self.count_tokens(
                                        accumulated_thinking
                                    )

                                # 📊 Token 使用量日志
                                input_tokens = usage.get("input_tokens", 0)
                                output_tokens = usage.get("output_tokens", 0)
                                thinking_tokens = usage.get("thinking_tokens", 0)
                                total_tokens = input_tokens + output_tokens + thinking_tokens
                                logger.info(
                                    f"📊 Token 使用: input={input_tokens:,}, output={output_tokens:,}, "
                                    f"thinking={thinking_tokens:,}, total={total_tokens:,} (model={self.config.model})"
                                )

                                # 🆕 Cache 效果日志（Context Engineering 监控）
                                cache_read = usage.get("cache_read_tokens", 0)
                                cache_create = usage.get("cache_creation_tokens", 0)
                                if cache_read > 0:
                                    # cache 命中，节省成本（90% 折扣）
                                    saved = cache_read * 0.003 * 0.9 / 1000  # $3/M * 90% off
                                    logger.info(
                                        f"✅ Cache HIT: {cache_read:,} tokens (saved ~${saved:.4f})"
                                    )
                                elif cache_create > 0:
                                    logger.debug(f"📦 Cache CREATED: {cache_create:,} tokens")

                            if hasattr(final_message, "content"):
                                for block in final_message.content:
                                    if not hasattr(block, "type"):
                                        continue
                                    block_type = block.type

                                    # 工具调用
                                    if block_type == "tool_use":
                                        tool_calls.append(
                                            {
                                                "id": getattr(block, "id", ""),
                                                "name": getattr(block, "name", ""),
                                                "input": getattr(block, "input", {}),
                                                "type": "tool_use",
                                            }
                                        )
                        except Exception as e:
                            logger.warning(f"获取最终消息失败: {e}")
        except (
            httpx.RemoteProtocolError,  # peer closed / incomplete chunked read
            httpx.ConnectError,         # connection refused / reset
            httpx.TimeoutException,     # read timeout mid-stream
            anthropic.APIConnectionError,  # SDK wrapper for network errors
            anthropic.APITimeoutError,     # SDK timeout wrapper
        ) as stream_error:
            # 🔄 可重试的网络错误：流式传输中断
            _stream_attempt += 1
            error_msg = str(stream_error)
            logger.warning(
                f"⚠️ 流式传输中断 (attempt {_stream_attempt}/{_STREAM_MAX_RETRIES}): {error_msg}"
            )
            logger.warning(f"   已接收事件数: {event_count}")
            logger.warning(f"   已累积 content: {len(accumulated_content)} chars")
            logger.warning(f"   已解析 tool_calls: {len(tool_calls)}")

            # 如果还有重试次数，且没有完整解析出 tool_call → 重试
            if _stream_attempt <= _STREAM_MAX_RETRIES and not tool_calls:
                import asyncio as _asyncio

                delay = 1.0 * _stream_attempt
                logger.info(f"🔄 {delay}s 后重试流式调用...")
                await _asyncio.sleep(delay)

                # 保存累积状态（fallback 失败时用于降级返回）
                _saved_content = accumulated_content
                _saved_thinking = accumulated_thinking

                # 重置累积变量
                accumulated_thinking = ""
                accumulated_content = ""
                tool_calls = []
                stop_reason = None
                usage = {}
                event_count = 0

                # 使用非流式 fallback：用 create_message_async 替代
                logger.info("🔄 回退到非流式调用以确保完整性...")
                try:
                    fallback_response = await self.create_message_async(
                        messages=messages,
                        system=system,
                        tools=tools,
                        override_thinking=override_thinking,
                        **kwargs,
                    )
                    # 将非流式结果转为单次 yield
                    yield fallback_response
                    return
                except Exception as fallback_err:
                    logger.error(f"❌ 非流式 fallback 也失败: {fallback_err}")
                    # Restore accumulated state for partial response below
                    accumulated_content = _saved_content
                    accumulated_thinking = _saved_thinking

            # 超过重试次数或已有 tool_calls → 降级返回部分响应
            if accumulated_content or accumulated_thinking or tool_calls:
                logger.warning("⚠️ 返回部分响应（重试已耗尽）...")
                raw_content = self._build_raw_content_from_parts(
                    accumulated_thinking, accumulated_content, tool_calls
                )
                yield LLMResponse(
                    content=accumulated_content,
                    thinking=accumulated_thinking if accumulated_thinking else None,
                    tool_calls=tool_calls if tool_calls else None,
                    stop_reason="stream_error",
                    model=self.config.model,
                    raw_content=raw_content,
                    is_stream=False,
                )
                return

            # 没有任何内容，抛出原始错误
            raise
        except Exception as stream_error:
            # 🚨 非网络错误（如 API 错误）：不重试，直接降级
            error_msg = str(stream_error)
            logger.error(f"❌ 流式传输异常: {error_msg}")
            logger.error(f"   已接收事件数: {event_count}")
            logger.error(f"   已累积 content: {len(accumulated_content)} chars")
            logger.error(f"   已解析 tool_calls: {len(tool_calls)}")

            if accumulated_content or accumulated_thinking or tool_calls:
                logger.warning("⚠️ 返回部分响应...")
                raw_content = self._build_raw_content_from_parts(
                    accumulated_thinking, accumulated_content, tool_calls
                )
                yield LLMResponse(
                    content=accumulated_content,
                    thinking=accumulated_thinking if accumulated_thinking else None,
                    tool_calls=tool_calls if tool_calls else None,
                    stop_reason="stream_error",
                    model=self.config.model,
                    raw_content=raw_content,
                    is_stream=False,
                )
                return

            raise

        # 🚨 Guard: stream ended without message_stop (silent disconnect)
        #
        # Per Anthropic docs: "When receiving a streaming response via SSE,
        # it's possible that an error can occur after returning a 200 response,
        # in which case error handling wouldn't follow standard mechanisms."
        #
        # The SDK may NOT raise RemoteProtocolError if the server closed
        # gracefully after HTTP 200 + partial SSE. Detect this by checking
        # for missing message_stop (final_message is None).
        if final_message is None and stop_reason is None:
            logger.warning(
                f"⚠️ 流式结束但无 message_stop (events={event_count}, "
                f"content={len(accumulated_content)} chars) — 视为静默断连"
            )
            if _stream_attempt < _STREAM_MAX_RETRIES and not tool_calls:
                _stream_attempt += 1
                import asyncio as _asyncio

                delay = 1.0 * _stream_attempt
                logger.info(f"🔄 {delay}s 后重试（静默断连恢复）...")
                await _asyncio.sleep(delay)

                _saved_content = accumulated_content
                _saved_thinking = accumulated_thinking

                logger.info("🔄 回退到非流式调用以确保完整性...")
                try:
                    fallback_response = await self.create_message_async(
                        messages=messages,
                        system=system,
                        tools=tools,
                        override_thinking=override_thinking,
                        **kwargs,
                    )
                    yield fallback_response
                    return
                except Exception as fallback_err:
                    logger.error(f"❌ 非流式 fallback 也失败: {fallback_err}")
                    accumulated_content = _saved_content
                    accumulated_thinking = _saved_thinking

            # Fallback failed or retries exhausted → return partial
            if accumulated_content or accumulated_thinking:
                raw_content = self._build_raw_content_from_parts(
                    accumulated_thinking, accumulated_content, tool_calls
                )
                yield LLMResponse(
                    content=accumulated_content,
                    thinking=accumulated_thinking if accumulated_thinking else None,
                    tool_calls=tool_calls if tool_calls else None,
                    stop_reason="stream_error",
                    model=self.config.model,
                    raw_content=raw_content,
                    is_stream=False,
                )
                return

        # 构建 raw_content
        # 优先使用 final_message（包含 thinking signature）
        if final_message and hasattr(final_message, "content"):
            raw_content = self._build_raw_content(final_message)
        else:
            # 降级：使用累积的内容（没有 signature）
            raw_content = self._build_raw_content_from_parts(
                accumulated_thinking, accumulated_content, tool_calls
            )

        # 响应日志（INFO 级别）
        raw_types = [b.get("type", "unknown") for b in raw_content]
        tool_names = [tc.get("name", "") for tc in tool_calls] if tool_calls else []
        logger.info(
            f"📥 Claude 响应: stop_reason={stop_reason or 'end_turn'}, blocks={raw_types}, tools={tool_names}"
        )

        # 详细日志：完整响应内容
        if LLM_DEBUG_VERBOSE:
            logger.info("=" * 60)
            logger.info("📥 [VERBOSE] 完整响应内容:")
            logger.info(f"   stop_reason: {stop_reason}")
            if accumulated_thinking:
                thinking_preview = accumulated_thinking[:1000]
                logger.info(
                    f"   thinking ({len(accumulated_thinking)} chars): {thinking_preview}{'...' if len(accumulated_thinking) > 1000 else ''}"
                )
            if accumulated_content:
                content_preview = accumulated_content[:2000]
                logger.info(
                    f"   content ({len(accumulated_content)} chars): {content_preview}{'...' if len(accumulated_content) > 2000 else ''}"
                )
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
                model=self.config.model,  # 🆕 实际使用的模型名称
                raw_content=raw_content,
                is_stream=False,
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

        def default_handler(o) -> Any:
            """自定义序列化处理器"""
            if hasattr(o, "model_dump"):
                # Pydantic v2 对象
                return o.model_dump()
            elif hasattr(o, "dict"):
                # Pydantic v1 对象
                return o.dict()
            elif hasattr(o, "__dict__"):
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
        计算 token 数量

        TODO: 使用 Claude 官方 API 精确计算
        - client.messages.count_tokens() 支持消息、工具、图片等
        - 参考: https://docs.anthropic.com/en/api/messages-count-tokens

        当前使用父类的 tiktoken 实现。

        Args:
            text: 要计算的文本

        Returns:
            token 数量
        """
        # TODO: 实现 Claude 官方 token 计算
        # response = self.sync_client.messages.count_tokens(
        #     model=self.model,
        #     messages=[{"role": "user", "content": text}]
        # )
        # return response.input_tokens
        return super().count_tokens(text)

    # ============================================================
    # 响应解析
    # ============================================================

    def _parse_response(
        self, response: anthropic.types.Message, invocation_type: Optional[str] = None
    ) -> LLMResponse:
        """解析 Claude API 响应为统一格式"""
        thinking_text = ""
        content_text = ""
        tool_calls = []
        invocation_method = invocation_type or "direct"

        for block in response.content:
            if not hasattr(block, "type"):
                continue

            if block.type == "thinking":
                thinking_text = getattr(block, "thinking", "")
            elif block.type == "text":
                content_text = getattr(block, "text", "")
            elif block.type == "tool_use":
                tool_name = getattr(block, "name", "")

                tool_calls.append(
                    {
                        "id": getattr(block, "id", ""),
                        "name": tool_name,
                        "input": getattr(block, "input", {}),
                        "invocation_method": "direct",
                    }
                )

        # Usage 信息
        usage = {}
        if hasattr(response, "usage"):
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "thinking_tokens": 0,  # 🆕 Extended Thinking tokens
            }
            if hasattr(response.usage, "cache_read_input_tokens"):
                usage["cache_read_tokens"] = response.usage.cache_read_input_tokens
            if hasattr(response.usage, "cache_creation_input_tokens"):
                usage["cache_creation_tokens"] = response.usage.cache_creation_input_tokens

            # 🆕 计算 Extended Thinking tokens
            if thinking_text:
                # Anthropic 目前未在 usage 中单独返回 thinking_tokens
                # 使用 tiktoken 进行近似计算
                usage["thinking_tokens"] = self.count_tokens(thinking_text)

            # 📊 Token 使用量日志
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            thinking_tokens = usage.get("thinking_tokens", 0)
            total_tokens = input_tokens + output_tokens + thinking_tokens
            logger.info(
                f"📊 Token 使用: input={input_tokens:,}, output={output_tokens:,}, "
                f"thinking={thinking_tokens:,}, total={total_tokens:,} (model={self.config.model})"
            )

            # 🆕 Cache 效果日志（Context Engineering 监控）
            cache_read = usage.get("cache_read_tokens") or 0
            cache_create = usage.get("cache_creation_tokens") or 0
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
            model=self.config.model,  # 🆕 实际使用的模型名称
            raw_content=raw_content,
            cache_read_tokens=usage.get("cache_read_tokens", 0),
            cache_creation_tokens=usage.get("cache_creation_tokens", 0),
        )

    def _build_raw_content(self, response: anthropic.types.Message) -> List[Dict[str, Any]]:
        """
        构建原始 content 块列表（用于消息续传）

        Claude 原生协议支持的 content block 类型：
        - thinking: 思考过程（带 signature）
        - text: 文本内容
        - tool_use: 工具调用

        规则：
        1. thinking 块必须有有效的 signature 字段
        2. tool_use 块必须有 id 和 name
        3. 跳过空文本块
        """
        raw_content = []

        for block in response.content:
            if not hasattr(block, "type"):
                continue

            block_type = block.type

            if block_type == "thinking":
                thinking_text = getattr(block, "thinking", "")
                signature = getattr(block, "signature", "")

                if thinking_text and signature:
                    raw_content.append(
                        {"type": "thinking", "thinking": thinking_text, "signature": signature}
                    )
                elif thinking_text:
                    logger.warning(f"Thinking block without signature, skipping")

            elif block_type == "text":
                text_content = getattr(block, "text", "")
                if text_content:
                    raw_content.append({"type": "text", "text": text_content})

            # 客户端工具调用
            elif block_type == "tool_use":
                tool_id = getattr(block, "id", "")
                tool_name = getattr(block, "name", "")
                tool_input = getattr(block, "input", {})

                if tool_id and tool_name:
                    raw_content.append(
                        {"type": "tool_use", "id": tool_id, "name": tool_name, "input": tool_input}
                    )
                else:
                    logger.warning(f"Invalid tool_use block: id={tool_id}, name={tool_name}")

            else:
                # 未知类型，记录警告但不跳过（可能是新的 block 类型）
                logger.warning(f"Unknown content block type: {block_type}")
                # 尝试转换为字典
                try:
                    block_dict = {"type": block_type}
                    for attr in ["id", "name", "input", "content", "tool_use_id"]:
                        if hasattr(block, attr):
                            block_dict[attr] = getattr(block, attr)
                    raw_content.append(block_dict)
                except Exception as e:
                    logger.error(f"Failed to convert unknown block: {e}")

        return raw_content

    def _build_raw_content_from_parts(
        self, thinking: str, content: str, tool_calls: List[Dict[str, Any]]
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
            raw_content.append({"type": "text", "text": content})

        for tc in tool_calls:
            raw_content.append(
                {"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc["input"]}
            )

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
                    block
                    for block in content
                    if isinstance(block, dict)
                    and block.get("type") not in ("thinking", "redacted_thinking")
                ]

                if filtered_content:
                    cleaned_messages.append({"role": "assistant", "content": filtered_content})
                # 如果过滤后为空，跳过该消息
            else:
                cleaned_messages.append(msg)

        return cleaned_messages

    # ============================================================
    # Files API
    # ============================================================

    async def download_file(
        self, file_id: str, output_path: str, overwrite: bool = True
    ) -> Optional[FileInfo]:
        """
        下载文件（异步版本）

        Args:
            file_id: 文件 ID
            output_path: 输出路径
            overwrite: 是否覆盖已有文件

        Returns:
            FileInfo 或 None
        """
        try:
            # 检查文件是否存在
            if os.path.exists(output_path) and not overwrite:
                logger.warning(f"文件已存在: {output_path}")
                return None

            # 确保输出路径为绝对路径（打包后 cwd 可能只读）
            if not os.path.isabs(output_path):
                from utils.app_paths import get_user_data_dir
                output_path = str(get_user_data_dir() / output_path)

            # 创建目录
            output_dir = os.path.dirname(output_path)
            if output_dir:
                Path(output_dir).mkdir(parents=True, exist_ok=True)

            # 获取元数据
            metadata = self.sync_client.beta.files.retrieve_metadata(file_id=file_id)

            # 下载文件
            file_content = self.sync_client.beta.files.download(file_id=file_id)

            # 异步写入文件
            async with aiofiles.open(output_path, "wb") as f:
                await f.write(file_content.read())

            logger.info(f"✅ 文件已下载: {output_path} ({metadata.size_bytes} bytes)")

            return FileInfo(
                file_id=metadata.id,
                filename=metadata.filename,
                size_bytes=metadata.size_bytes,
                mime_type=metadata.mime_type,
                created_at=metadata.created_at,
                downloadable=metadata.downloadable,
            )

        except Exception as e:
            logger.error(f"❌ 下载文件失败: {e}")
            return None

    def get_file_info(self, file_id: str) -> Optional[FileInfo]:
        """
        获取文件元数据

        Args:
            file_id: 文件 ID

        Returns:
            FileInfo 或 None
        """
        try:
            metadata = self.sync_client.beta.files.retrieve_metadata(file_id=file_id)
            return FileInfo(
                file_id=metadata.id,
                filename=metadata.filename,
                size_bytes=metadata.size_bytes,
                mime_type=metadata.mime_type,
                created_at=metadata.created_at,
                downloadable=metadata.downloadable,
            )
        except Exception as e:
            logger.error(f"❌ 获取文件信息失败: {e}")
            return None

    def list_files(self) -> List[FileInfo]:
        """
        列出所有文件

        Returns:
            FileInfo 列表
        """
        try:
            files = self.sync_client.beta.files.list()
            return [
                FileInfo(
                    file_id=f.id,
                    filename=f.filename,
                    size_bytes=f.size_bytes,
                    mime_type=f.mime_type,
                    created_at=f.created_at,
                    downloadable=f.downloadable,
                )
                for f in files.data
            ]
        except Exception as e:
            logger.error(f"❌ 获取文件列表失败: {e}")
            return []

    def extract_file_ids_from_response(self, response) -> List[str]:
        """
        从响应中提取 file_id

        Args:
            response: Claude API 响应

        Returns:
            file_id 列表
        """
        file_ids = []

        def find_file_ids(obj, depth=0) -> None:
            """递归查找 file_id"""
            if depth > 10:
                return

            if hasattr(obj, "file_id") and obj.file_id:
                file_ids.append(obj.file_id)

            if hasattr(obj, "content"):
                content = obj.content
                if isinstance(content, (list, tuple)):
                    for item in content:
                        find_file_ids(item, depth + 1)
                elif hasattr(content, "__dict__"):
                    find_file_ids(content, depth + 1)

            if hasattr(obj, "__dict__"):
                for key, value in obj.__dict__.items():
                    if key == "file_id" and value:
                        if value not in file_ids:
                            file_ids.append(value)
                    elif hasattr(value, "__dict__") or isinstance(value, (list, tuple)):
                        find_file_ids(value, depth + 1)

        if hasattr(response, "content"):
            for block in response.content:
                find_file_ids(block)

        return list(set(file_ids))

    # ============================================================
    # Citations (引用)
    # ============================================================

    def enable_citations(self) -> None:
        """启用 Citations 功能"""
        self._citations_enabled = True
        logger.info("✅ Citations 已启用")

    def disable_citations(self) -> None:
        """禁用 Citations 功能"""
        self._citations_enabled = False

    def create_document_content(
        self, documents: List[Dict[str, Any]], enable_citations: bool = True
    ) -> List[Dict[str, Any]]:
        """
        创建带引用的文档内容

        Args:
            documents: 文档列表，每个文档包含：
                - type: "text" 或 "pdf"
                - data: 文档内容（text/base64）
                - title: 文档标题（可选）
            enable_citations: 是否启用引用

        Returns:
            格式化的文档内容列表

        示例：
            docs = llm.create_document_content([
                {"type": "text", "data": "这是文档内容...", "title": "文档1"}
            ])
        """
        formatted = []

        for doc in documents:
            doc_type = doc.get("type", "text")
            data = doc.get("data", "")
            title = doc.get("title", "")

            if doc_type == "text":
                formatted.append(
                    {
                        "type": "document",
                        "source": {"type": "text", "media_type": "text/plain", "data": data},
                        "title": title,
                        "citations": {"enabled": enable_citations},
                    }
                )
            elif doc_type == "pdf":
                formatted.append(
                    {
                        "type": "document",
                        "source": {"type": "base64", "media_type": "application/pdf", "data": data},
                        "title": title,
                        "citations": {"enabled": enable_citations},
                    }
                )

        return formatted

    async def create_message_with_citations(
        self, query: str, documents: List[Dict[str, Any]], system: Optional[str] = None, **kwargs
    ) -> LLMResponse:
        """
        使用引用功能创建消息

        Args:
            query: 用户查询
            documents: 文档列表
            system: 系统提示词
            **kwargs: 其他参数

        Returns:
            LLMResponse（包含引用信息）

        示例：
            response = await llm.create_message_with_citations(
                query="文档中提到了什么?",
                documents=[
                    {"type": "text", "data": "这是文档内容...", "title": "文档1"}
                ]
            )
        """
        # 构建带引用的内容
        content = self.create_document_content(documents, enable_citations=True)
        content.append({"type": "text", "text": query})

        messages = [{"role": "user", "content": content}]

        request_params = {
            "model": self.config.model,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "messages": messages,
        }

        if system:
            request_params["system"] = system

        try:
            response = await self.async_client.messages.create(**request_params)
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"❌ Citations 调用失败: {e}")
            raise


# ============================================================
# 工厂函数
# ============================================================


def create_claude_service(
    model: str = "claude-sonnet-4-5-20250929",
    api_key: Optional[str] = None,
    enable_thinking: bool = True,
    enable_caching: bool = False,
    **kwargs,
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
        **kwargs,
    )

    return ClaudeLLMService(config)


# ============================================================
# 注册到 LLMRegistry
# ============================================================


def _register_claude():
    """延迟注册 Claude Provider（避免循环导入）"""
    from .registry import LLMRegistry

    LLMRegistry.register(
        name="claude",
        service_class=ClaudeLLMService,
        adaptor_class=ClaudeAdaptor,
        default_model="claude-sonnet-4-5-20250929",
        api_key_env="ANTHROPIC_API_KEY",
        display_name="Claude",
        description="Anthropic Claude 系列模型",
        supported_features=[
            "extended_thinking",
            "prompt_caching",
            "streaming",
            "tool_calling",
            "skills",
            "files_api",
            "citations",
        ],
    )


# 模块加载时注册
_register_claude()
