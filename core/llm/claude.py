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

import os
import json
import re
from typing import Dict, Any, Optional, List, Union, AsyncIterator, Callable
from pathlib import Path
from dataclasses import dataclass, field

import anthropic
import httpx

from logger import get_logger
from utils.message_utils import messages_to_dict_list
from infra.resilience import with_retry  # 🆕 V7.3: 使用统一的重试机制
from .base import (
    BaseLLMService,
    LLMConfig,
    LLMResponse,
    Message,
    ToolType,
    LLMProvider
)


# ============================================================
# Skills API 数据结构
# ============================================================

@dataclass
class SkillInfo:
    """Skill 信息"""
    id: str
    display_title: str
    latest_version: str
    created_at: str
    source: str  # "custom" or "anthropic"
    
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

# Context Editing 触发阈值（默认比例）
DEFAULT_CONTEXT_WINDOW_TOKENS = 200_000
DEFAULT_CONTEXT_TRIGGER_RATIO = 0.7
MODEL_CONTEXT_WINDOWS = {
    "claude-opus-4-5": 200_000,
    "claude-opus-4-1": 200_000,
    "claude-opus-4": 200_000,
    "claude-sonnet-4-5": 200_000,
    "claude-sonnet-4": 200_000,
    "claude-haiku-4-5": 200_000,
}


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
        
        # 🆕 V5.0: 使用配置中的超时和重试设置
        timeout = getattr(config, 'timeout', 120.0)
        max_retries = getattr(config, 'max_retries', 3)
        
        # 🔍 DEBUG: 打印 API Key 信息（仅显示前8位和后4位）
        api_key = config.api_key or ""
        if api_key:
            masked_key = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
            logger.info(f"🔑 Claude API Key: {masked_key} (长度: {len(api_key)})")
        else:
            logger.warning("⚠️ Claude API Key 为空！")
        
        # 异步客户端（增加 timeout 和重试配置）
        # 注意：对于流式响应，timeout 是首个响应的超时，不是整体超时
        self.async_client = anthropic.AsyncAnthropic(
            api_key=config.api_key,
            timeout=timeout,
            max_retries=max_retries
        )
        
        # 同步客户端（用于 Skills/Files API）
        self.sync_client = anthropic.Anthropic(
            api_key=config.api_key,
            timeout=timeout,
            max_retries=max_retries
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
        self._context_editing_policy: Dict[str, Any] = {
            "adaptive": True,
            "adaptive_trigger_tokens": 0,
            "early_trigger_tokens": 0,
            "min_turns": 30,
            "tool_result_count_threshold": 8,
            "tool_result_tokens_threshold": 5000,
        }
        
        # 工具注册表（用于自定义工具）
        self._tool_registry: Dict[str, Dict[str, Any]] = {}
    
        # 自定义工具存储
        self._custom_tools: List[Dict[str, Any]] = []
        
        # Skills 配置
        self._skills_enabled = False
        self._skills_container: Dict[str, Any] = {}
        
        # Citations 配置
        self._citations_enabled = False
    
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

    def _get_model_context_window(self) -> int:
        """
        获取模型上下文窗口（用于自适应触发阈值）
        
        Returns:
            上下文窗口 token 数
        """
        model_name = (self.config.model or "").lower()
        for key, window in MODEL_CONTEXT_WINDOWS.items():
            if key in model_name:
                return window
        return DEFAULT_CONTEXT_WINDOW_TOKENS
    
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
        clear_tool_uses: bool = True,
        clear_thinking: bool = False,
        trigger_threshold: Optional[int] = None,  # input_tokens
        keep_tool_uses: int = 10,
        clear_at_least: Optional[int] = None,  # input_tokens，None 则自动计算
        exclude_tools: Optional[List[str]] = None,
        keep_all_thinking: bool = False  # 🆕 保留所有 thinking blocks（最大化缓存命中）
    ):
        """
        启用 Context Editing（服务端自动清理）
        
        根据 Claude Platform 官方文档：
        https://platform.claude.com/docs/en/build-with-claude/context-editing
        
        **最佳实践**：
        - 如果启用 Prompt Caching，`clear_at_least` 应该设置得更大（如 10000-15000），
          以抵消缓存失效的成本
        - 如果启用 Extended Thinking 和 Prompt Caching，建议设置 `keep_all_thinking=True`
          以最大化缓存命中率
        - 默认排除服务端工具（如 `web_search`），因为它们的结果通常很重要
        - 自适应触发以**上下文长度**为主，当长度接近阈值时，
          轮次/工具结果作为**提前触发**的辅助信号
        
        Args:
            clear_tool_uses: 是否清理工具结果（clear_tool_uses_20250919）
            clear_thinking: 是否清理 thinking blocks（clear_thinking_20251015）
            trigger_threshold: 触发清理的 token 阈值（input_tokens）
                - None: 按模型上下文窗口比例自动计算（默认 70%）
            keep_tool_uses: 保留最近 N 个工具调用
            clear_at_least: 每次至少清理的 token 数（input_tokens）
                - None: 根据 Prompt Caching 状态自动计算
                - 启用缓存时：max(10000, trigger_threshold // 3)
                - 未启用缓存时：max(3000, trigger_threshold // 6)
            exclude_tools: 排除的工具列表（不清理这些工具的结果）
                - None: 默认排除服务端工具（web_search, web_fetch）
            keep_all_thinking: 是否保留所有 thinking blocks（最大化缓存命中率）
                - True: keep: "all"（保留所有 thinking blocks）
                - False: keep: {type: "thinking_turns", value: 1}（只保留最后一轮）
        """
        self._context_editing_enabled = True
        
        edits = []
        
        # 🆕 触发阈值自动计算（按上下文窗口比例）
        if trigger_threshold is None:
            context_window = self._get_model_context_window()
            trigger_threshold = int(context_window * DEFAULT_CONTEXT_TRIGGER_RATIO)
            logger.debug(
                f"🔧 trigger_threshold 自动计算: {trigger_threshold} "
                f"(context_window={context_window}, ratio={DEFAULT_CONTEXT_TRIGGER_RATIO})"
            )

        # 🆕 自适应触发策略（上下文长度为主，轮次/工具结果为辅）
        adaptive_trigger_tokens = max(0, int(trigger_threshold))
        early_trigger_tokens = int(adaptive_trigger_tokens * 0.6)
        self._context_editing_policy = {
            "adaptive": True,
            "adaptive_trigger_tokens": adaptive_trigger_tokens,
            "early_trigger_tokens": early_trigger_tokens,
            "min_turns": 30,
            "tool_result_count_threshold": 8,
            "tool_result_tokens_threshold": 5000,
        }
        
        logger.debug(
            "🧭 Context Editing 自适应策略: "
            f"adaptive=True, trigger_tokens={adaptive_trigger_tokens}, "
            f"early_trigger_tokens={early_trigger_tokens}, "
            "min_turns=30, tool_result_count>=8, tool_result_tokens>=5000"
        )
        
        # 🆕 自动计算 clear_at_least（根据文档建议）
        if clear_at_least is None:
            if self.config.enable_caching:
                # 启用缓存时，需要清理更多 tokens 以抵消缓存失效成本
                # 文档建议：确保清理足够的 tokens 才值得
                clear_at_least = max(10000, trigger_threshold // 3)
                logger.debug(f"🔧 clear_at_least 自动计算（启用缓存）: {clear_at_least}")
            else:
                # 未启用缓存时，可以使用较小的值
                clear_at_least = max(3000, trigger_threshold // 6)
                logger.debug(f"🔧 clear_at_least 自动计算（未启用缓存）: {clear_at_least}")
        
        # 🆕 默认排除服务端工具（根据文档建议）
        default_exclude = ["web_search", "web_fetch"]
        if exclude_tools is None:
            exclude_tools = default_exclude
        else:
            # 合并用户指定的排除工具
            exclude_tools = list(set(exclude_tools + default_exclude))
        
        # Tool result clearing
        if clear_tool_uses:
            tool_edit: Dict[str, Any] = {
                "type": "clear_tool_uses_20250919",
                "trigger": {
                    "type": "input_tokens",
                    "value": trigger_threshold
                },
                "keep": {
                    "type": "tool_uses",
                    "value": keep_tool_uses
                },
                "clear_at_least": {
                    "type": "input_tokens",
                    "value": clear_at_least
                }
            }
            if exclude_tools:
                tool_edit["exclude_tools"] = exclude_tools
            edits.append(tool_edit)
            logger.debug(f"🔧 Tool result clearing: trigger={trigger_threshold}, keep={keep_tool_uses}, clear_at_least={clear_at_least}, exclude={exclude_tools}")
        
        # Thinking block clearing
        if clear_thinking:
            if keep_all_thinking:
                # 🆕 最大化缓存命中：保留所有 thinking blocks
                edits.append({
                    "type": "clear_thinking_20251015",
                    "keep": "all"
                })
                logger.debug("🔧 Thinking block clearing: keep=all (最大化缓存命中)")
            else:
                # 默认：只保留最后一轮的 thinking
                edits.append({
                    "type": "clear_thinking_20251015",
                    "keep": {
                        "type": "thinking_turns",
                        "value": 1
                    }
                })
                logger.debug("🔧 Thinking block clearing: keep=last_turn")
        
        self._context_editing_config = {
            "edits": edits
        }
        
        self._add_beta("context-management-2025-06-27")
        logger.info(f"✅ Context Editing 已启用: {len(edits)} 个策略 (trigger={trigger_threshold}, clear_at_least={clear_at_least})")
    
    def disable_context_editing(self):
        """禁用 Context Editing"""
        self._context_editing_enabled = False
        self._context_editing_config = {}
        if not self._memory_enabled:
            self._remove_beta("context-management-2025-06-27")

    def _estimate_block_tokens(self, block: Any) -> int:
        """
        估算单个 content block 的 token 数
        
        Args:
            block: content block
            
        Returns:
            估算 token 数
        """
        if isinstance(block, dict):
            block_type = block.get("type", "")
            if block_type == "text":
                return self.count_tokens(str(block.get("text", "")))
            if block_type in ("thinking", "redacted_thinking"):
                return self.count_tokens(str(block.get("thinking", "")))
            if block_type in ("tool_use", "server_tool_use"):
                return self.count_tokens(self._safe_json_dumps(block.get("input", {})))
            if block_type == "tool_result" or str(block_type).endswith("_tool_result"):
                return self.count_tokens(self._safe_json_dumps(block.get("content", "")))
            
            return self.count_tokens(self._safe_json_dumps(block))
        
        return self.count_tokens(str(block))

    def _analyze_context_for_editing(self, messages: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        分析上下文状态（用于自适应触发）
        
        Args:
            messages: 格式化后的消息列表
            
        Returns:
            上下文统计信息
        """
        total_tokens = 0
        turns = 0
        tool_result_count = 0
        tool_result_tokens = 0
        
        for msg in messages:
            if msg.get("role") == "user":
                turns += 1
            
            content = msg.get("content", "")
            if isinstance(content, list):
                for block in content:
                    tokens = self._estimate_block_tokens(block)
                    total_tokens += tokens
                    
                    if isinstance(block, dict):
                        block_type = block.get("type", "")
                        if block_type == "tool_result" or str(block_type).endswith("_tool_result"):
                            tool_result_count += 1
                            tool_result_tokens += tokens
            else:
                total_tokens += self.count_tokens(str(content))
        
        return {
            "turns": turns,
            "estimated_tokens": total_tokens,
            "tool_result_count": tool_result_count,
            "tool_result_tokens": tool_result_tokens,
        }

    def _should_apply_context_editing(self, messages: List[Dict[str, Any]]) -> bool:
        """
        判断是否附加 context_management（自适应触发）
        
        Args:
            messages: 格式化后的消息列表
            
        Returns:
            是否需要附加 context_management
        """
        if not self._context_editing_enabled:
            return False
        
        if not self._context_editing_config.get("edits"):
            return False
        
        policy = self._context_editing_policy or {}
        if not policy.get("adaptive", True):
            return True
        
        stats = self._analyze_context_for_editing(messages)
        trigger_tokens = policy.get("adaptive_trigger_tokens", 0)
        early_trigger_tokens = policy.get("early_trigger_tokens", 0)
        min_turns = policy.get("min_turns", 0)
        tool_result_count_threshold = policy.get("tool_result_count_threshold", 0)
        tool_result_tokens_threshold = policy.get("tool_result_tokens_threshold", 0)
        
        if trigger_tokens and stats["estimated_tokens"] >= trigger_tokens:
            logger.debug(
                f"🧠 Context Editing 触发: tokens={stats['estimated_tokens']}, "
                f"threshold={trigger_tokens}"
            )
            return True

        # 仅在上下文接近阈值时，允许辅助信号提前触发
        if early_trigger_tokens and stats["estimated_tokens"] >= early_trigger_tokens:
            if min_turns and stats["turns"] >= min_turns:
                logger.debug(
                    f"🧠 Context Editing 触发: turns={stats['turns']}, "
                    f"threshold={min_turns} (early_trigger_tokens={early_trigger_tokens})"
                )
                return True
            
            if (
                tool_result_count_threshold
                and stats["tool_result_count"] >= tool_result_count_threshold
            ):
                logger.debug(
                    f"🧠 Context Editing 触发: tool_results={stats['tool_result_count']}, "
                    f"threshold={tool_result_count_threshold} (early_trigger_tokens={early_trigger_tokens})"
                )
                return True
            
            if (
                tool_result_tokens_threshold
                and stats["tool_result_tokens"] >= tool_result_tokens_threshold
            ):
                logger.debug(
                    f"🧠 Context Editing 触发: tool_result_tokens={stats['tool_result_tokens']}, "
                    f"threshold={tool_result_tokens_threshold} (early_trigger_tokens={early_trigger_tokens})"
                )
                return True
        
        return False
    
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
                return schema
        
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
        )
    )
    async def create_message_async(
        self,
        messages: List[Message],
        system: Optional[Union[str, List[Dict[str, Any]]]] = None,
        tools: Optional[List[Union[ToolType, str, Dict]]] = None,
        invocation_type: Optional[str] = None,
        **kwargs
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
        formatted_messages = messages_to_dict_list(messages)
        request_params = {
            "model": self.config.model,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "messages": formatted_messages
        }
        
        # System prompt（支持多层缓存）
        if system:
            if isinstance(system, list):
                # 多层缓存格式：在最后一个要缓存的 block 上添加 cache_control
                system_blocks = [block.copy() if isinstance(block, dict) else {"type": "text", "text": block} for block in system]
                
                if self.config.enable_caching and system_blocks:
                    # 🔧 找到最后一个要缓存的 block（排除用户画像等动态内容）
                    # 策略：在倒数第二个 block（工具文档）上添加缓存断点
                    # 这样用户画像（最后一个）不会影响缓存命中
                    cache_index = len(system_blocks) - 2 if len(system_blocks) > 1 else 0
                    if cache_index >= 0:
                        system_blocks[cache_index]["cache_control"] = {"type": "ephemeral", "ttl": "1h"}
                        logger.debug(f"🗂️ 在 system block[{cache_index}] 添加缓存断点 (1h TTL)")
                
                request_params["system"] = system_blocks
                logger.debug(f"🗂️ 使用多层缓存 system prompt: {len(system_blocks)} 层")
            elif self.config.enable_caching:
                # 字符串格式 + 启用缓存：自动包装为单层缓存（1 小时 TTL）
                request_params["system"] = [{
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral", "ttl": "1h"}
                }]
            else:
                # 字符串格式 + 禁用缓存：直接使用
                request_params["system"] = system
        
        # Extended Thinking（支持覆盖 enable_thinking）
        enable_thinking = kwargs.get("enable_thinking", self.config.enable_thinking)
        if enable_thinking:
            request_params["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.config.thinking_budget
            }
            request_params["temperature"] = 1.0  # Required for thinking
        else:
            request_params["temperature"] = kwargs.get("temperature", self.config.temperature)
        
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
            # Tool Search 模式
            if invocation_type == "tool_search" and self._tool_search_mode:
                all_tools = self.configure_deferred_tools(all_tools)
            
            # 🔧 缓存策略：只对最后一个工具添加 cache_control（1 小时 TTL）
            # Claude API 限制最多 4 个带 cache_control 的 block
            # 工具定义在运行期稳定，使用较长的缓存时间
            if self.config.enable_caching and all_tools:
                all_tools[-1] = all_tools[-1].copy()
                all_tools[-1]["cache_control"] = {"type": "ephemeral", "ttl": "1h"}
            
            request_params["tools"] = all_tools
            
            # 调试日志
            logger.debug(f"Tools: {[t.get('name', 'unknown') for t in all_tools]}")
        
        # Context Editing（自适应触发）
        if self._should_apply_context_editing(formatted_messages):
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
        system: Optional[Union[str, List[Dict[str, Any]]]] = None,
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
            system: 系统提示词，支持两种格式：
                - str: 单层缓存（向后兼容，启用缓存时自动包装为 5 分钟 TTL）
                - List[Dict]: 多层缓存（支持自定义 TTL，如 1h）
            tools: 工具列表
            on_thinking: thinking 回调
            on_content: content 回调
            on_tool_call: tool_call 回调
            **kwargs: 其他参数（支持 max_tokens 覆盖）
            
        Yields:
            LLMResponse 片段
        """
        # 构建请求参数（支持 kwargs 覆盖）
        formatted_messages = messages_to_dict_list(messages)
        request_params = {
            "model": self.config.model,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "messages": formatted_messages
        }
        
        # System prompt（支持多层缓存，与 create_message_async 保持一致）
        if system:
            if isinstance(system, list):
                # 多层缓存格式：在最后一个要缓存的 block 上添加 cache_control
                system_blocks = [block.copy() if isinstance(block, dict) else {"type": "text", "text": block} for block in system]
                
                if self.config.enable_caching and system_blocks:
                    # 🔧 找到最后一个要缓存的 block（排除用户画像等动态内容）
                    # 策略：在倒数第二个 block（工具文档）上添加缓存断点
                    cache_index = len(system_blocks) - 2 if len(system_blocks) > 1 else 0
                    if cache_index >= 0:
                        system_blocks[cache_index]["cache_control"] = {"type": "ephemeral", "ttl": "1h"}
                        logger.debug(f"🗂️ [Stream] 在 system block[{cache_index}] 添加缓存断点 (1h TTL)")
                
                request_params["system"] = system_blocks
                logger.debug(f"🗂️ [Stream] 使用多层缓存 system prompt: {len(system_blocks)} 层")
            elif self.config.enable_caching:
                # 字符串格式 + 启用缓存：自动包装为单层缓存（1 小时 TTL）
                request_params["system"] = [{
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral", "ttl": "1h"}
                }]
            else:
                # 字符串格式 + 禁用缓存：直接使用
                request_params["system"] = system
        
        # Extended Thinking（支持覆盖 enable_thinking）
        enable_thinking = kwargs.get("enable_thinking", self.config.enable_thinking)
        if enable_thinking:
            request_params["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.config.thinking_budget
            }
            request_params["temperature"] = 1.0
        else:
            request_params["temperature"] = kwargs.get("temperature", self.config.temperature)
        
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

        # Context Editing（流式模式，自适应触发）
        if self._should_apply_context_editing(formatted_messages):
            request_params["context_management"] = self._context_editing_config
        
        # 🆕 Skills Container（如果启用）
        # 根据 Claude Skills 官方标准：Skills 模式下 tools 只能是 code_execution
        if self._skills_enabled and self._skills_container:
            request_params["betas"] = list(self._betas)
            request_params["container"] = self._skills_container
            
            # Skills 模式：tools 只能包含 code_execution（官方标准）
            request_params["tools"] = [
                {"type": "code_execution_20250825", "name": "code_execution"}
            ]
            
            logger.info(f"🎯 Skills 模式激活: {len(self._skills_container.get('skills', []))} 个技能")
            logger.info("   tools 已替换为 [code_execution]（Skills 标准要求）")
        
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
            # 🆕 根据是否启用 Skills 选择 API
            if self._skills_enabled and "betas" in request_params:
                # 使用 beta API（支持 Skills Container）
                stream_ctx = self.async_client.beta.messages.stream(**request_params)
            elif self._betas:
                # 使用 beta API（支持 Context Editing / Memory / Tool Search 等）
                stream_ctx = self.async_client.beta.messages.stream(
                    betas=self._betas,
                    **request_params
                )
            else:
                # 使用标准 API
                stream_ctx = self.async_client.messages.stream(**request_params)
            
            async with stream_ctx as stream:
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
                                # 🆕 客户端工具调用 - 立即 yield tool_use_start
                                elif block_type == "tool_use":
                                    tool_id = getattr(block, 'id', '')
                                    tool_name = getattr(block, 'name', '')
                                    if on_tool_call:
                                        on_tool_call({
                                            "id": tool_id,
                                            "name": tool_name,
                                            "input": {},  # input 后续流式发送
                                            "type": "tool_use"
                                        })
                                    # 🆕 yield tool_use_start 事件
                                    yield LLMResponse(
                                        content="",
                                        is_stream=True,
                                        tool_use_start={"id": tool_id, "name": tool_name, "type": "tool_use"}
                                    )
                                # 服务端工具调用（如 web_search）
                                elif block_type == "server_tool_use":
                                    tool_id = getattr(block, 'id', '')
                                    tool_name = getattr(block, 'name', '')
                                    if on_tool_call:
                                        on_tool_call({
                                            "id": tool_id,
                                            "name": tool_name,
                                            "input": {},
                                            "type": "server_tool_use"
                                        })
                                    # 🆕 yield tool_use_start 事件
                                    yield LLMResponse(
                                        content="",
                                        is_stream=True,
                                        tool_use_start={"id": tool_id, "name": tool_name, "type": "server_tool_use"}
                                    )
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
                                    # 🆕 yield input_delta 事件
                                    yield LLMResponse(
                                        content="",
                                        is_stream=True,
                                        input_delta=partial_json
                                    )
                    
                    elif event.type == "message_stop":
                        final_message = None
                        try:
                            final_message = await stream.get_final_message()
                            stop_reason = getattr(final_message, 'stop_reason', None)
                            
                            # 🔢 提取 usage 信息
                            if hasattr(final_message, 'usage') and final_message.usage:
                                usage = {
                                    "input_tokens": final_message.usage.input_tokens,
                                    "output_tokens": final_message.usage.output_tokens,
                                    "thinking_tokens": 0  # 🆕 Extended Thinking tokens
                                }
                                if hasattr(final_message.usage, 'cache_read_input_tokens'):
                                    usage["cache_read_tokens"] = final_message.usage.cache_read_input_tokens
                                if hasattr(final_message.usage, 'cache_creation_input_tokens'):
                                    usage["cache_creation_tokens"] = final_message.usage.cache_creation_input_tokens
                                
                                # 🆕 估算 Extended Thinking tokens
                                if accumulated_thinking:
                                    usage["thinking_tokens"] = len(accumulated_thinking) // 4
                                
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
        except (httpx.RemoteProtocolError, httpx.ReadError, ConnectionResetError, Exception) as stream_error:
            # 🚨 流式传输中断：记录已接收的事件数和已累积的内容
            error_msg = str(stream_error)
            is_connection_reset = (
                "connection reset" in error_msg.lower() or
                "read: connection reset by peer" in error_msg.lower() or
                isinstance(stream_error, ConnectionResetError)
            )
            
            logger.error(f"❌ 流式传输中断: {error_msg}")
            logger.error(f"   已接收事件数: {event_count}")
            logger.error(f"   已累积 thinking: {len(accumulated_thinking)} chars")
            logger.error(f"   已累积 content: {len(accumulated_content)} chars")
            logger.error(f"   已解析 tool_calls: {len(tool_calls)}")
            
            # 🆕 重试逻辑：connection reset 且没有累积内容时自动重试
            # 这种情况通常是 Claude 服务端因空字符串输出而崩溃
            if is_connection_reset and not accumulated_content and not accumulated_thinking and not tool_calls:
                retry_count = kwargs.get("_stream_retry_count", 0)
                max_retries = 2  # 最多重试 2 次
                
                if retry_count < max_retries:
                    import asyncio
                    delay = (retry_count + 1) * 1.0  # 指数退避：1s, 2s
                    logger.warning(f"🔄 Connection reset（无内容），第 {retry_count + 1}/{max_retries} 次重试，延迟 {delay}s...")
                    await asyncio.sleep(delay)
                    
                    # 递归重试
                    kwargs["_stream_retry_count"] = retry_count + 1
                    async for event in self.create_message_stream(
                        messages=messages,
                        system=system,
                        tools=tools,
                        on_thinking=on_thinking,
                        on_content=on_content,
                        on_tool_call=on_tool_call,
                        **kwargs
                    ):
                        yield event
                    return
                else:
                    logger.error(f"❌ 重试 {max_retries} 次后仍失败")
            
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
                "output_tokens": response.usage.output_tokens,
                "thinking_tokens": 0  # 🆕 Extended Thinking tokens
            }
            if hasattr(response.usage, 'cache_read_input_tokens'):
                usage["cache_read_tokens"] = response.usage.cache_read_input_tokens
            if hasattr(response.usage, 'cache_creation_input_tokens'):
                usage["cache_creation_tokens"] = response.usage.cache_creation_input_tokens
            
            # 🆕 提取 Extended Thinking tokens（在 thinking 内容中估算）
            if thinking_text:
                # 简单估算：thinking 文本长度 / 4 ≈ tokens
                # Anthropic 目前未在 usage 中单独返回 thinking_tokens，需自行估算
                estimated_thinking_tokens = len(thinking_text) // 4
                usage["thinking_tokens"] = estimated_thinking_tokens
            
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

    def supports_native_tools(self) -> bool:
        """
        Claude 支持原生工具
        
        Returns:
            是否支持原生工具
        """
        return True

    def supports_skills(self) -> bool:
        """
        Claude 支持 Skills 容器
        
        Returns:
            是否支持 Skills
        """
        return True

    # ============================================================
    # Skills API
    # ============================================================
    
    def enable_skills(self, skills: List[Dict[str, Any]]):
        """
        启用 Skills 功能
        
        Args:
            skills: Skills 配置列表，每个 skill 包含：
                - type: "custom" 或 "anthropic"
                - skill_id: Skill ID
                - version: 版本号（可选，默认 "latest"）
                
        示例：
            llm.enable_skills([
                {"type": "custom", "skill_id": "skill_abc123", "version": "latest"},
                {"type": "anthropic", "skill_id": "pptx", "version": "latest"}
            ])
        """
        self._skills_enabled = True
        self._skills_container = {"skills": skills}
        
        # 添加必要的 beta headers
        self._add_beta("code-execution-2025-08-25")
        self._add_beta("skills-2025-10-02")
        self._add_beta("files-api-2025-04-14")
        
        logger.info(f"✅ Skills 已启用: {len(skills)} 个技能")
    
    def disable_skills(self):
        """禁用 Skills 功能"""
        self._skills_enabled = False
        self._skills_container = {}
        self._remove_beta("skills-2025-10-02")
        # 保留 code-execution 和 files-api，因为可能被其他功能使用
    
    def create_skill(
        self,
        display_title: str,
        skill_path: str
    ) -> Optional[SkillInfo]:
        """
        创建 Custom Skill
        
        Args:
            display_title: Skill 显示名称
            skill_path: Skill 目录路径（包含 SKILL.md）
            
        Returns:
            SkillInfo 或 None（如果失败）
            
        示例：
            skill = llm.create_skill(
                display_title="PPT Generator",
                skill_path="./skills/library/ppt-generator"
            )
            print(f"Skill ID: {skill.id}")
        """
        try:
            from anthropic.lib import files_from_dir
            
            skill = self.sync_client.beta.skills.create(
                display_title=display_title,
                files=files_from_dir(skill_path)
            )
            
            logger.info(f"✅ Skill 创建成功: {skill.id}")
            
            return SkillInfo(
                id=skill.id,
                display_title=skill.display_title,
                latest_version=skill.latest_version,
                created_at=skill.created_at,
                source=skill.source
            )
            
        except Exception as e:
            logger.error(f"❌ Skill 创建失败: {e}")
            return None
    
    def list_skills(self) -> List[SkillInfo]:
        """
        列出所有 Custom Skills
        
        Returns:
            SkillInfo 列表
        """
        try:
            skills = self.sync_client.beta.skills.list()
            return [
                SkillInfo(
                    id=s.id,
                    display_title=s.display_title,
                    latest_version=s.latest_version,
                    created_at=s.created_at,
                    source=s.source
                )
                for s in skills.data
            ]
        except Exception as e:
            logger.error(f"❌ 获取 Skills 列表失败: {e}")
            return []
    
    def get_skill(self, skill_id: str) -> Optional[SkillInfo]:
        """
        获取 Skill 详情
        
        Args:
            skill_id: Skill ID
            
        Returns:
            SkillInfo 或 None
        """
        try:
            skill = self.sync_client.beta.skills.retrieve(skill_id)
            return SkillInfo(
                id=skill.id,
                display_title=skill.display_title,
                latest_version=skill.latest_version,
                created_at=skill.created_at,
                source=skill.source
            )
        except Exception as e:
            logger.error(f"❌ 获取 Skill 失败: {e}")
            return None
    
    def delete_skill(self, skill_id: str) -> bool:
        """
        删除 Skill
        
        Args:
            skill_id: Skill ID
            
        Returns:
            是否成功
        """
        try:
            # 先删除所有版本
            versions = self.sync_client.beta.skills.versions.list(skill_id=skill_id)
            for version in versions.data:
                self.sync_client.beta.skills.versions.delete(
                    skill_id=skill_id,
                    version=version.version
                )
            
            # 再删除 Skill
            self.sync_client.beta.skills.delete(skill_id)
            logger.info(f"✅ Skill 已删除: {skill_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 删除 Skill 失败: {e}")
            return False
    
    async def create_message_with_skills(
        self,
        messages: List[Message],
        skills: List[Dict[str, Any]],
        system: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        使用 Skills 创建消息
        
        Args:
            messages: 消息列表
            skills: Skills 配置
            system: 系统提示词
            **kwargs: 其他参数
            
        Returns:
            LLMResponse
            
        示例：
            response = await llm.create_message_with_skills(
                messages=[Message(role="user", content="创建一个 PPT")],
                skills=[
                    {"type": "custom", "skill_id": "skill_abc123", "version": "latest"}
                ]
            )
        """
        formatted_messages = messages_to_dict_list(messages)
        
        request_params = {
            "model": self.config.model,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "messages": formatted_messages,
            "betas": ["code-execution-2025-08-25", "skills-2025-10-02", "files-api-2025-04-14"],
            "container": {"skills": skills},
            "tools": [{"type": "code_execution_20250825", "name": "code_execution"}]
        }
        
        if system:
            request_params["system"] = system
        
        try:
            response = await self.async_client.beta.messages.create(**request_params)
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"❌ Skills 调用失败: {e}")
            raise
    
    # ============================================================
    # Files API
    # ============================================================
    
    def download_file(
        self,
        file_id: str,
        output_path: str,
        overwrite: bool = True
    ) -> Optional[FileInfo]:
        """
        下载文件
        
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
            
            # 创建目录
            output_dir = os.path.dirname(output_path)
            if output_dir:
                Path(output_dir).mkdir(parents=True, exist_ok=True)
            
            # 获取元数据
            metadata = self.sync_client.beta.files.retrieve_metadata(file_id=file_id)
            
            # 下载文件
            file_content = self.sync_client.beta.files.download(file_id=file_id)
            
            with open(output_path, 'wb') as f:
                f.write(file_content.read())
            
            logger.info(f"✅ 文件已下载: {output_path} ({metadata.size_bytes} bytes)")
            
            return FileInfo(
                file_id=metadata.id,
                filename=metadata.filename,
                size_bytes=metadata.size_bytes,
                mime_type=metadata.mime_type,
                created_at=metadata.created_at,
                downloadable=metadata.downloadable
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
                downloadable=metadata.downloadable
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
                    downloadable=f.downloadable
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
        
        def find_file_ids(obj, depth=0):
            """递归查找 file_id"""
            if depth > 10:
                return
            
            if hasattr(obj, 'file_id') and obj.file_id:
                file_ids.append(obj.file_id)
            
            if hasattr(obj, 'content'):
                content = obj.content
                if isinstance(content, (list, tuple)):
                    for item in content:
                        find_file_ids(item, depth + 1)
                elif hasattr(content, '__dict__'):
                    find_file_ids(content, depth + 1)
            
            if hasattr(obj, '__dict__'):
                for key, value in obj.__dict__.items():
                    if key == 'file_id' and value:
                        if value not in file_ids:
                            file_ids.append(value)
                    elif hasattr(value, '__dict__') or isinstance(value, (list, tuple)):
                        find_file_ids(value, depth + 1)
        
        if hasattr(response, 'content'):
            for block in response.content:
                find_file_ids(block)
        
        return list(set(file_ids))
    
    # ============================================================
    # Citations (引用)
    # ============================================================
    
    def enable_citations(self):
        """启用 Citations 功能"""
        self._citations_enabled = True
        logger.info("✅ Citations 已启用")
    
    def disable_citations(self):
        """禁用 Citations 功能"""
        self._citations_enabled = False
    
    def create_document_content(
        self,
        documents: List[Dict[str, Any]],
        enable_citations: bool = True
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
                formatted.append({
                    "type": "document",
                    "source": {
                        "type": "text",
                        "media_type": "text/plain",
                        "data": data
                    },
                    "title": title,
                    "citations": {"enabled": enable_citations}
                })
            elif doc_type == "pdf":
                formatted.append({
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": data
                    },
                    "title": title,
                    "citations": {"enabled": enable_citations}
                })
        
        return formatted
    
    async def create_message_with_citations(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        system: Optional[str] = None,
        **kwargs
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
        content.append({
            "type": "text",
            "text": query
        })
        
        messages = [{"role": "user", "content": content}]
        
        request_params = {
            "model": self.config.model,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "messages": messages
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
    enable_context_editing: Optional[bool] = None,
    context_editing: Optional[Dict[str, Any]] = None,
    **kwargs
) -> ClaudeLLMService:
    """
    创建 Claude 服务的便捷函数
    
    Args:
        model: 模型名称
        api_key: API 密钥（默认从环境变量读取）
        enable_thinking: 启用 Extended Thinking
        enable_caching: 启用 Prompt Caching
        enable_context_editing: 是否启用 Context Editing（None 则读取环境变量）
        context_editing: Context Editing 参数配置（可选）
        **kwargs: 其他配置参数
        
    Returns:
        ClaudeLLMService 实例
    """
    if api_key is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")

    # 🆕 Context Editing 开关（统一入口）
    if enable_context_editing is None:
        enable_context_editing = os.getenv("ENABLE_CONTEXT_EDITING", "").lower() in ("1", "true", "yes")
    elif isinstance(enable_context_editing, str):
        enable_context_editing = enable_context_editing.lower() in ("1", "true", "yes")
    
    # 兼容从 kwargs 传入（避免误传到 LLMConfig）
    if "context_editing" in kwargs:
        context_editing = kwargs.pop("context_editing")
    if "enable_context_editing" in kwargs:
        enable_context_editing = kwargs.pop("enable_context_editing")
    
    config = LLMConfig(
        provider=LLMProvider.CLAUDE,
        model=model,
        api_key=api_key,
        enable_thinking=enable_thinking,
        enable_caching=enable_caching,
        enable_context_editing=bool(enable_context_editing),
        **kwargs
    )
    
    llm_service = ClaudeLLMService(config)
    
    # 🆕 自动启用 Context Editing（全局统一入口）
    if enable_context_editing:
        if isinstance(context_editing, dict):
            llm_service.enable_context_editing(**context_editing)
        else:
            llm_service.enable_context_editing()
    
    return llm_service

