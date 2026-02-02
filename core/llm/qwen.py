"""
通义千问 LLM 服务实现

基于 OpenAI 兼容接口实现，与 Claude 服务保持相同的接口规范。

支持的功能：
- 基础对话（流式/非流式）
- Function Calling（工具调用）
- 深度思考模式（enable_thinking）
- 多模态输入（图像、视频、音频）
- 显式缓存（cache_control）
- 结构化输出（response_format）

模型对应关系：
- qwen3-max ↔ claude-sonnet-4-5（旗舰模型）
- qwen-plus ↔ claude-haiku-4-5（快速模型）

参考文档：
- https://help.aliyun.com/zh/model-studio/qwen-api-reference
"""

import os
import json
from typing import Dict, Any, Optional, List, Union, AsyncIterator, Callable
from dataclasses import dataclass

from openai import AsyncOpenAI
import httpx

from logger import get_logger
from infra.resilience import with_retry
from .base import (
    BaseLLMService,
    LLMConfig,
    LLMResponse,
    Message,
    ToolType,
    LLMProvider
)
from .adaptor import OpenAIAdaptor


logger = get_logger("llm.qwen")

# 详细日志开关
LLM_DEBUG_VERBOSE = os.getenv("LLM_DEBUG_VERBOSE", "").lower() in ("1", "true", "yes")


# ============================================================
# 千问配置和常量
# ============================================================

# 千问 API 限制
# 参考官方文档（qwen官方定价.md）中 qwen3-max 在全球/国际部署模式下的配置：
# - 上下文长度：262,144
# - 最大输入：258,048
# - 最大输出：65,536
# 这里取「最大输出 65,536」作为通用的 max_tokens 上限，用于对调用参数进行硬性裁剪，
# 以确保在将 qwen-max 升级为 qwen3-max 后也不会因为 max_tokens 超出官方限制而报错。
QWEN_MAX_TOKENS = 65536  # 千问模型（按 qwen3-max）单次响应的 max_tokens 上限

@dataclass
class QwenConfig(LLMConfig):
    """
    千问配置类
    
    扩展 LLMConfig，添加千问特有配置
    """
    # 地域配置
    region: str = "cn-beijing"  # cn-beijing, singapore, us-virginia, finance
    base_url: Optional[str] = None  # 🆕 自定义 API 端点（优先级高于 region）
    
    # 千问特有功能
    enable_thinking: bool = False      # 深度思考模式
    thinking_budget: Optional[int] = None  # 思考长度限制
    
    # 视觉模型参数
    vl_high_resolution_images: bool = False
    min_pixels: Optional[int] = None
    max_pixels: Optional[int] = None
    total_pixels: Optional[int] = None
    fps: Optional[float] = None
    
    # 音频模型参数
    audio_voice: Optional[str] = None  # 音色
    audio_format: str = "wav"
    modalities: List[str] = None  # ["text"] 或 ["text", "audio"]
    
    # 其他参数
    seed: Optional[int] = None
    top_k: Optional[int] = None
    presence_penalty: float = 0.0
    response_format: Optional[Dict[str, Any]] = None  # 结构化输出


class QwenRegions:
    """千问服务地域端点"""
    CN_BEIJING = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    SINGAPORE = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    US_VIRGINIA = "https://dashscope-us.aliyuncs.com/compatible-mode/v1"
    FINANCE = "https://dashscope-finance.aliyuncs.com/compatible-mode/v1"
    
    MAPPING = {
        "cn-beijing": CN_BEIJING,
        "singapore": SINGAPORE,
        "us-virginia": US_VIRGINIA,
        "finance": FINANCE,
    }


class QwenModelCapability:
    """千问模型能力检测"""
    
    # 支持深度思考的模型
    THINKING_MODELS = {
        "qwen3-max-preview", "qwen3-max", "qwen-max",
        "qwen-plus", "qwen-turbo", "qwen-flash",
        "qwen3-vl-plus", "qwen3-vl-flash",
        "qwen3", "qwen3-235b-a22b-thinking",
    }
    
    # 支持视觉的模型
    VISION_MODELS = {
        "qwen-vl-max", "qwen-vl-plus",
        "qwen3-vl-plus", "qwen3-vl-flash",
        "qvq-72b-preview", "qvq-max",
    }
    
    # 支持音频的模型
    AUDIO_MODELS = {
        "qwen-omni-turbo",
        "qwen3-omni-flash",
        "qwen-audio-turbo",
    }
    
    # 支持 Function Calling 的模型（大部分模型都支持）
    TOOL_CALLING_MODELS = {
        "qwen-max", "qwen-plus", "qwen-turbo", "qwen-flash",
        "qwen3-max", "qwen3-plus",
        "qwen-vl-max", "qwen-vl-plus",
        "qwen3-vl-plus", "qwen3-vl-flash",
    }
    
    @staticmethod
    def supports_thinking(model: str) -> bool:
        """检查模型是否支持深度思考"""
        return any(m in model for m in QwenModelCapability.THINKING_MODELS)
    
    @staticmethod
    def supports_vision(model: str) -> bool:
        """检查模型是否支持视觉"""
        return any(m in model for m in QwenModelCapability.VISION_MODELS)
    
    @staticmethod
    def supports_audio(model: str) -> bool:
        """检查模型是否支持音频"""
        return any(m in model for m in QwenModelCapability.AUDIO_MODELS)
    
    @staticmethod
    def supports_tools(model: str) -> bool:
        """检查模型是否支持工具调用"""
        return any(m in model for m in QwenModelCapability.TOOL_CALLING_MODELS)


# ============================================================
# 千问 LLM 服务
# ============================================================

class QwenLLMService(BaseLLMService):
    """
    通义千问 LLM 服务实现
    
    基于 OpenAI 兼容接口，保持与 Claude 服务相同的接口规范。
    
    模型对应关系：
    - qwen3-max: 对标 claude-sonnet-4-5（旗舰模型，适用于复杂推理）
    - qwen-plus: 对标 claude-haiku-4-5（快速模型，适用于简单任务）
    
    支持的功能：
    - 基础对话（流式/非流式）
    - Function Calling（工具调用）
    - 深度思考模式（enable_thinking）
    - 多模态输入（图像、视频、音频）
    - 显式缓存（cache_control）
    - 结构化输出（response_format）
    
    使用示例：
    ```python
    config = QwenConfig(
        model="qwen3-max",  # 或 qwen-plus
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        enable_thinking=True
    )
    llm = QwenLLMService(config)
    
    response = await llm.create_message_async(
        messages=[Message(role="user", content="你好")],
        system="你是一个有帮助的助手"
    )
    ```
    """
    
    def __init__(self, config: Union[LLMConfig, QwenConfig]):
        """
        初始化千问服务
        
        Args:
            config: 千问配置（LLMConfig 或 QwenConfig）
        """
        # 如果传入的是 LLMConfig，转换为 QwenConfig
        if isinstance(config, LLMConfig) and not isinstance(config, QwenConfig):
            self.config = QwenConfig(
                provider=config.provider,
                model=config.model,
                api_key=config.api_key,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
                enable_thinking=config.enable_thinking,
                thinking_budget=config.thinking_budget,
                enable_caching=config.enable_caching,
                timeout=getattr(config, 'timeout', 120.0),
                max_retries=getattr(config, 'max_retries', 3),
            )
        else:
            self.config = config
        
        # 消息适配器（统一处理消息格式转换）
        self._adaptor = OpenAIAdaptor()
        
        # API Key（优先级：配置 > 环境变量）
        api_key = self.config.api_key or os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            raise ValueError(
                "千问 API Key 未设置。请设置 DASHSCOPE_API_KEY 环境变量或传入 api_key 参数"
            )
        
        # 打印 API Key 信息（仅显示前8位和后4位）
        masked_key = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
        logger.info(f"🔑 Qwen API Key: {masked_key} (长度: {len(api_key)})")
        
        # 获取 API 端点（优先使用 base_url，否则根据 region 选择）
        base_url = getattr(self.config, 'base_url', None)
        if base_url:
            logger.info(f"🌐 千问端点（自定义）: {base_url}")
        else:
            region = getattr(self.config, 'region', 'cn-beijing')
            base_url = QwenRegions.MAPPING.get(region, QwenRegions.CN_BEIJING)
            logger.info(f"🌐 千问地域: {region} ({base_url})")
        
        # 初始化 OpenAI 客户端
        timeout = getattr(self.config, 'timeout', 120.0)
        max_retries = getattr(self.config, 'max_retries', 3)
        
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries
        )
        
        # 自定义工具存储
        self._custom_tools: List[Dict[str, Any]] = []
        
        logger.info(f"✅ 千问服务初始化成功: model={self.config.model}")
    
    # ============================================================
    # 自定义工具管理（与 Claude 保持一致）
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
    
    def convert_to_tool_schema(self, capability: Dict[str, Any]) -> Dict[str, Any]:
        """
        将能力定义转换为千问 API 格式
        
        Args:
            capability: 能力定义
            
        Returns:
            千问 API 格式的工具定义
        """
        name = capability.get("name", "")
        input_schema = capability.get("input_schema", {
            "type": "object",
            "properties": {},
            "required": []
        })
        description = capability.get("metadata", {}).get("description", f"Tool: {name}")
        
        # 千问使用标准的 OpenAI Function Calling 格式
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": input_schema
            }
        }
    
    def _format_tools(self, tools: List[Union[ToolType, str, Dict]]) -> List[Dict[str, Any]]:
        """
        格式化工具列表
        
        支持三种输入：
        1. ToolType 枚举（会被忽略，千问不支持原生工具）
        2. 字符串（工具名称）
        3. 完整 schema 字典
        """
        formatted = []
        
        for idx, tool in enumerate(tools):
            try:
                if isinstance(tool, ToolType):
                    # 千问没有原生工具，跳过
                    logger.warning(f"千问不支持 ToolType 枚举: {tool}，已跳过")
                    continue
                        
                elif isinstance(tool, str):
                    # 从自定义工具中查找
                    found = False
                    for custom_tool in self._custom_tools:
                        if custom_tool.get("name") == tool:
                            formatted.append(self._convert_tool_to_openai_format(custom_tool))
                            found = True
                            break
                    if not found:
                        logger.warning(f"未找到工具: {tool}")
                        
                elif isinstance(tool, dict):
                    formatted.append(self._convert_tool_to_openai_format(tool))
                    
                else:
                    raise ValueError(f"Invalid tool format: {tool}")
                
                # 验证 JSON 可序列化
                if formatted:
                    json.dumps(formatted[-1])
                
            except Exception as e:
                logger.error(f"处理工具 #{idx} 时出错: {e}")
                raise
        
        return formatted
    
    def _convert_tool_to_openai_format(self, tool: Dict[str, Any]) -> Dict[str, Any]:
        """
        转换工具为 OpenAI Function Calling 格式
        
        Args:
            tool: 工具定义（可能是 Claude 格式或自定义格式）
            
        Returns:
            OpenAI 格式的工具定义
        """
        # 如果已经是 OpenAI 格式（包含 type: function），直接返回
        if tool.get("type") == "function":
            return tool
        
        # 转换 Claude 格式到 OpenAI 格式
        return {
            "type": "function",
            "function": {
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {})
            }
        }
    
    # ============================================================
    # 核心 API 方法
    # ============================================================
    
    @with_retry(
        max_retries=3,
        base_delay=1.0,
        retryable_errors=(
            # OpenAI SDK 异常
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
        override_thinking: Optional[bool] = None,
        is_probe: bool = False,
        **kwargs
    ) -> LLMResponse:
        """
        创建消息（异步）
        
        Args:
            messages: 消息列表
            system: 系统提示词（支持字符串或列表）
            tools: 工具列表
            invocation_type: 调用方式（千问不需要）
            override_thinking: 动态覆盖思考配置
            is_probe: 是否为探测请求
            **kwargs: 其他参数
            
        Returns:
            LLMResponse 响应对象
        """
        # 使用 adaptor 转换消息
        converted = self._adaptor.convert_messages_to_provider(messages)
        openai_messages = converted["messages"]
        
        # 构建请求参数
        # ⚠️ 千问限制: max_tokens 不能超过 8192
        max_tokens = min(
            kwargs.get("max_tokens", self.config.max_tokens),
            QWEN_MAX_TOKENS
        )
        request_params = {
            "model": self.config.model,
            "messages": openai_messages,
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": max_tokens,
            "stream": False,
        }
        
        # System prompt（千问支持列表格式用于显式缓存）
        if system:
            if isinstance(system, list):
                # 转换为千问格式（添加到 messages 开头）
                system_message = self._build_system_message(system)
                request_params["messages"].insert(0, system_message)
            else:
                request_params["messages"].insert(0, {
                    "role": "system",
                    "content": system
                })
        
        # 千问特有参数（通过 extra_body 传递）
        extra_body = self._build_extra_body(override_thinking, kwargs)
        if extra_body:
            # OpenAI SDK 的 extra_body 参数
            for key, value in extra_body.items():
                request_params[key] = value
        
        # Tools（Function Calling）
        all_tools = []
        tool_names_seen = set()
        
        # 添加用户指定的工具
        if tools:
            for tool in self._format_tools(tools):
                tool_name = tool.get("function", {}).get("name", "")
                if tool_name and tool_name not in tool_names_seen:
                    all_tools.append(tool)
                    tool_names_seen.add(tool_name)
        
        # 添加自定义工具
        for custom_tool in self._custom_tools:
            tool_name = custom_tool.get("name", "")
            if tool_name and tool_name not in tool_names_seen:
                all_tools.append(self._convert_tool_to_openai_format(custom_tool))
                tool_names_seen.add(tool_name)
        
        if all_tools:
            request_params["tools"] = all_tools
            request_params["tool_choice"] = kwargs.get("tool_choice", "auto")
            logger.debug(f"Tools: {[t['function']['name'] for t in all_tools]}")
        
        # 记录 max_tokens 限制警告
        original_max_tokens = kwargs.get("max_tokens", self.config.max_tokens)
        if original_max_tokens > QWEN_MAX_TOKENS:
            logger.warning(
                f"⚠️ max_tokens 已限制: {original_max_tokens} → {QWEN_MAX_TOKENS} "
                f"(千问上限)"
            )
        
        # 调试日志
        logger.debug(f"📤 千问请求: model={self.config.model}, messages={len(openai_messages)}")
        
        if LLM_DEBUG_VERBOSE:
            logger.info("=" * 80)
            logger.info("🔍 [DEBUG-ASYNC] 完整 request_params:")
            logger.info(f"   model: {request_params.get('model')}")
            logger.info(f"   messages: {len(request_params.get('messages', []))}")
            for i, msg in enumerate(request_params.get('messages', [])):
                logger.info(f"   [{i}] role={msg.get('role')}, content={str(msg.get('content'))[:200]}...")
            logger.info("=" * 80)
        
        # API 调用
        try:
            response = await self.client.chat.completions.create(**request_params)
        except Exception as e:
            if not is_probe:
                logger.error(f"千问 API 调用失败: {e}")
            raise
        
        # 转换响应
        return self._parse_response(response)
    
    async def create_message_stream(
        self,
        messages: List[Message],
        system: Optional[Union[str, List[Dict[str, Any]]]] = None,
        tools: Optional[List[Union[ToolType, str, Dict]]] = None,
        on_thinking: Optional[Callable[[str], None]] = None,
        on_content: Optional[Callable[[str], None]] = None,
        on_tool_call: Optional[Callable[[Dict], None]] = None,
        override_thinking: Optional[bool] = None,
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
            override_thinking: 动态覆盖 thinking 配置
            **kwargs: 其他参数
            
        Yields:
            LLMResponse 片段
        """
        # 使用 adaptor 转换消息
        converted = self._adaptor.convert_messages_to_provider(messages)
        openai_messages = converted["messages"]
        
        # 构建请求参数
        # ⚠️ 千问限制: max_tokens 不能超过 8192
        max_tokens = min(
            kwargs.get("max_tokens", self.config.max_tokens),
            QWEN_MAX_TOKENS
        )
        request_params = {
            "model": self.config.model,
            "messages": openai_messages,
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True}
        }
        
        # System prompt
        if system:
            if isinstance(system, list):
                system_message = self._build_system_message(system)
                request_params["messages"].insert(0, system_message)
            else:
                request_params["messages"].insert(0, {
                    "role": "system",
                    "content": system
                })
        
        # 千问特有参数（通过 extra_body 传递）
        # ⚠️ 注意：以下参数为 Qwen 非标准参数，需要放在 extra_body 中：
        # - enable_thinking: 思考模式
        # - top_k: 采样参数
        # - vl_high_resolution_images: 高分辨率图像处理
        # - thinking_budget: 思考过程的最大 Token 数
        extra_body = self._build_extra_body(override_thinking, kwargs)
        if extra_body:
            request_params["extra_body"] = extra_body
        
        # Tools
        all_tools = []
        tool_names_seen = set()
        
        if tools:
            for tool in self._format_tools(tools):
                tool_name = tool.get("function", {}).get("name", "")
                if tool_name and tool_name not in tool_names_seen:
                    all_tools.append(tool)
                    tool_names_seen.add(tool_name)
        
        for custom_tool in self._custom_tools:
            tool_name = custom_tool.get("name", "")
            if tool_name and tool_name not in tool_names_seen:
                all_tools.append(self._convert_tool_to_openai_format(custom_tool))
                tool_names_seen.add(tool_name)
        
        if all_tools:
            request_params["tools"] = all_tools
            request_params["tool_choice"] = kwargs.get("tool_choice", "auto")
        
        # 记录 max_tokens 限制警告
        original_max_tokens = kwargs.get("max_tokens", self.config.max_tokens)
        if original_max_tokens > QWEN_MAX_TOKENS:
            logger.warning(
                f"⚠️ max_tokens 已限制: {original_max_tokens} → {QWEN_MAX_TOKENS} "
                f"(千问上限)"
            )
        
        logger.info(f"📤 千问流式请求: model={self.config.model}, messages={len(openai_messages)}")
        
        # 累积变量
        accumulated_thinking = ""
        accumulated_content = ""
        tool_calls = []
        stop_reason = None
        usage = {}
        
        try:
            stream = await self.client.chat.completions.create(**request_params)
            
            async for chunk in stream:
                if not chunk.choices:
                    # 最后一个 chunk（包含 usage）
                    if chunk.usage:
                        usage = {
                            "input_tokens": chunk.usage.prompt_tokens,
                            "output_tokens": chunk.usage.completion_tokens,
                            "thinking_tokens": 0
                        }
                        
                        # 估算 thinking tokens
                        if accumulated_thinking:
                            usage["thinking_tokens"] = self.count_tokens(accumulated_thinking)
                        
                        # Token 使用量日志
                        logger.info(
                            f"📊 Token 使用: input={usage['input_tokens']:,}, "
                            f"output={usage['output_tokens']:,}, "
                            f"thinking={usage['thinking_tokens']:,}"
                        )
                    continue
                
                choice = chunk.choices[0]
                delta = choice.delta
                
                # 处理思维链内容（千问通过 reasoning_content 返回）
                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    accumulated_thinking += delta.reasoning_content
                    if on_thinking:
                        on_thinking(delta.reasoning_content)
                    yield LLMResponse(
                        content="",
                        thinking=delta.reasoning_content,
                        model=self.config.model,  # 🆕 流式中间块也需要 model
                        is_stream=True
                    )
                
                # 处理普通内容
                if delta.content:
                    accumulated_content += delta.content
                    if on_content:
                        on_content(delta.content)
                    yield LLMResponse(
                        content=delta.content,
                        model=self.config.model,  # 🆕 流式中间块也需要 model
                        is_stream=True
                    )
                
                # 处理工具调用
                if delta.tool_calls:
                    for tool_call in delta.tool_calls:
                        # 🔍 调试日志 - 仅在有 id/name 时记录 INFO，否则 DEBUG
                        if tool_call.id or (tool_call.function and tool_call.function.name):
                            logger.info(f"🔍 [DEBUG-STREAM] 收到工具调用 delta: index={tool_call.index}, id={tool_call.id}, name={tool_call.function.name if tool_call.function else 'None'}")
                        else:
                            # 只累积 arguments，使用 DEBUG 级别避免日志过多
                            logger.debug(f"🔍 [DEBUG-STREAM] 累积 arguments chunk: index={tool_call.index}")
                        
                        # ✅ 累积工具调用到列表中
                        # OpenAI 流式 API 的工具调用可能分多个 chunk 返回，需要按 index 累积
                        index = tool_call.index
                        
                        # 确保 tool_calls 列表足够长
                        while len(tool_calls) <= index:
                            tool_calls.append({
                                "id": "",
                                "name": "",
                                "arguments": "",
                                "type": "function"
                            })
                        
                        # 累积字段
                        if tool_call.id:
                            tool_calls[index]["id"] = tool_call.id
                        if tool_call.function:
                            if tool_call.function.name:
                                tool_calls[index]["name"] = tool_call.function.name
                            if tool_call.function.arguments:
                                tool_calls[index]["arguments"] += tool_call.function.arguments
                        
                        # 回调
                        if on_tool_call:
                            on_tool_call({
                                "id": tool_call.id,
                                "name": tool_call.function.name if tool_call.function else "",
                                "arguments": tool_call.function.arguments if tool_call.function else ""
                            })
                
                # 停止原因
                if choice.finish_reason:
                    stop_reason = choice.finish_reason
            
            # ✅ 处理累积的工具调用，转换为标准格式
            formatted_tool_calls = []
            if tool_calls:
                logger.info(f"🔍 [DEBUG-STREAM] 累积的工具调用数量: {len(tool_calls)}")
                for tc in tool_calls:
                    if tc.get("name"):  # 只添加有效的工具调用
                        try:
                            # 解析 arguments 字符串为 JSON
                            # 🔧 修复：Qwen 可能返回包含控制字符的 JSON，需要使用 strict=False
                            input_dict = json.loads(tc["arguments"], strict=False) if tc["arguments"] else {}
                            
                            # 🆕 参数规范化：确保所有参数都是基本类型，扁平化嵌套结构
                            normalized_input = self._normalize_tool_input(input_dict)
                            
                            formatted_tool_calls.append({
                                "id": tc["id"],
                                "name": tc["name"],
                                "input": normalized_input,
                                "type": "tool_use"  # 🔄 统一转换为 Claude 格式（适配器层职责）
                            })
                            logger.info(f"🔍 [DEBUG-STREAM] 格式化工具调用: id={tc['id']}, name={tc['name']}")
                            logger.info(f"🔍 [DEBUG-STREAM] 工具调用参数: {json.dumps(normalized_input, ensure_ascii=False)[:500]}")
                        except json.JSONDecodeError as e:
                            logger.error(f"❌ 工具调用参数解析失败: {e}")
                            logger.error(f"   原始 arguments（前200字符）: {tc['arguments'][:200] if tc.get('arguments') else 'None'}")
            
            # 构建 raw_content
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
            # 添加工具调用到 raw_content
            for tc in formatted_tool_calls:
                raw_content.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["input"]
                })
            
            logger.info(f"📥 千问响应: stop_reason={stop_reason or 'stop'}")
            
            # 🔄 统一转换 stop_reason（Qwen -> Claude 格式）
            # OpenAI/Qwen: "tool_calls" -> Claude: "tool_use"
            if stop_reason == "tool_calls":
                stop_reason = "tool_use"
                logger.debug("🔄 转换 stop_reason: tool_calls -> tool_use")
            
            # 返回最终响应
            yield LLMResponse(
                content=accumulated_content,
                thinking=accumulated_thinking if accumulated_thinking else None,
                tool_calls=formatted_tool_calls if formatted_tool_calls else None,
                stop_reason=stop_reason or "stop",  # ✅ 已转换为 Claude 格式
                usage=usage if usage else None,
                model=self.config.model,  # 🆕 实际使用的模型名称
                raw_content=raw_content,
                is_stream=False
            )
        
        except Exception as e:
            logger.error(f"千问流式传输错误: {e}")
            raise
    
    def count_tokens(self, text: str) -> int:
        """
        计算 token 数量（估算）
        
        千问 token 计算规则：
        - 中文：1 字符 ≈ 1 token
        - 英文：4 字符 ≈ 1 token
        
        Args:
            text: 要计算的文本
            
        Returns:
            估算的 token 数量
        """
        if not text:
            return 0
        
        # 统计中文字符
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        
        return chinese_chars + max(1, other_chars // 4)
    
    # ============================================================
    # 辅助方法
    # ============================================================
    
    def _build_system_message(self, system_blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        构建系统消息（支持显式缓存）
        
        Args:
            system_blocks: 系统提示词块列表
            
        Returns:
            系统消息
        """
        # 千问的显式缓存通过 cache_control 实现
        # 格式与 Claude 类似，但只支持 ephemeral 类型
        content_blocks = []
        
        for block in system_blocks:
            if isinstance(block, dict):
                content_blocks.append(block)
            else:
                content_blocks.append({"type": "text", "text": str(block)})
        
        # 如果只有一个纯文本块，简化格式
        if len(content_blocks) == 1 and content_blocks[0].get("type") == "text":
            return {
                "role": "system",
                "content": content_blocks[0].get("text", "")
            }
        
        return {
            "role": "system",
            "content": content_blocks
        }
    
    def _build_extra_body(
        self,
        override_thinking: Optional[bool],
        kwargs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        构建千问特有参数
        
        Args:
            override_thinking: 动态覆盖思考配置
            kwargs: 其他参数
            
        Returns:
            extra_body 字典
        """
        extra = {}
        
        # 深度思考
        effective_thinking = (
            override_thinking if override_thinking is not None 
            else getattr(self.config, 'enable_thinking', False)
        )
        if effective_thinking and QwenModelCapability.supports_thinking(self.config.model):
            extra["enable_thinking"] = True
            thinking_budget = getattr(self.config, 'thinking_budget', None)
            if thinking_budget:
                extra["thinking_budget"] = thinking_budget
        
        # 视觉模型参数
        if QwenModelCapability.supports_vision(self.config.model):
            if getattr(self.config, 'vl_high_resolution_images', False):
                extra["vl_high_resolution_images"] = True
        
        # 其他参数
        seed = getattr(self.config, 'seed', None)
        if seed is not None:
            extra["seed"] = seed
        
        top_k = getattr(self.config, 'top_k', None)
        if top_k is not None:
            extra["top_k"] = top_k
        
        presence_penalty = getattr(self.config, 'presence_penalty', 0.0)
        if presence_penalty != 0.0:
            extra["presence_penalty"] = presence_penalty
        
        # 结构化输出
        response_format = getattr(self.config, 'response_format', None) or kwargs.get("response_format")
        if response_format:
            extra["response_format"] = response_format
        
        return extra
    
    def _normalize_tool_input(self, input_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        规范化工具输入参数，确保所有嵌套的字典/对象都被扁平化为基本类型
        
        Qwen 可能会将某些参数作为嵌套对象传递，例如：
        {
            "api_name": {"name": "wenshu_api", "config": {...}},
            "url": "..."
        }
        
        需要扁平化为：
        {
            "api_name": "wenshu_api",
            "url": "..."
        }
        
        🎯 设计原则：所有 Qwen 特有的参数适配都在此处理，
        业务层的工具代码（如 api_calling）无需关心模型差异。
        
        Args:
            input_dict: 原始输入参数
            
        Returns:
            规范化后的参数
        """
        normalized = {}
        
        for key, value in input_dict.items():
            if isinstance(value, dict):
                # 🔧 策略 1: 优先提取 "name" 字段（常见于 api_name 等标识符参数）
                if "name" in value:
                    normalized[key] = value["name"]
                    if len(value) > 1:
                        logger.debug(f"🔧 Qwen 参数规范化: {key} -> 从多字段 dict 提取 'name': {value['name']} (忽略其他字段: {list(value.keys())})")
                    else:
                        logger.debug(f"🔧 Qwen 参数规范化: {key} -> 从 dict 提取 'name': {value['name']}")
                
                # 🔧 策略 2: 提取 "value" 字段（常见于值类型参数）
                elif "value" in value:
                    normalized[key] = value["value"]
                    logger.debug(f"🔧 Qwen 参数规范化: {key} -> 从 dict 提取 'value': {value['value']}")
                
                # 🔧 策略 3: 特殊处理常见的嵌套参数模式
                # 例如：body/parameters 可能包含实际的请求数据
                elif key in ("body", "parameters", "headers", "data", "json", "config"):
                    # 这些字段通常应该保留为字典（是合法的嵌套结构）
                    normalized[key] = value
                    logger.debug(f"🔧 Qwen 参数规范化: {key} -> 保留原始 dict（合法嵌套结构）")
                
                # 🔧 策略 4: 单字段字典，直接提取值
                elif len(value) == 1:
                    # 获取唯一的值
                    single_value = next(iter(value.values()))
                    normalized[key] = single_value
                    logger.debug(f"🔧 Qwen 参数规范化: {key} -> 从单字段 dict 提取值: {single_value}")
                
                # 🔧 策略 5: 多字段且无明确模式，保留原始结构（但打印警告）
                else:
                    normalized[key] = value
                    logger.warning(f"⚠️ Qwen 参数规范化: {key} -> 保留复杂 dict（无法扁平化），字段: {list(value.keys())}")
            
            elif isinstance(value, list):
                # 递归处理列表中的元素
                normalized[key] = [
                    self._normalize_tool_input(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                # 基本类型直接使用
                normalized[key] = value
        
        # ======== V2.1 增强：处理 Qwen 特殊调用模式 ========
        
        # 🔧 策略 6: 自动将 body 转换为 parameters（针对简化 API 调用）
        # Qwen 有时会使用 body 而不是 parameters，但简化调用的标准格式是 parameters
        if "body" in normalized and "parameters" not in normalized and "api_name" in normalized:
            logger.info(f"🔄 Qwen 参数规范化: 检测到旧格式 'body'，自动转换为 'parameters' (api_name={normalized.get('api_name')})")
            normalized["parameters"] = normalized.pop("body")
        
        # 🔧 策略 7: 过滤框架注入字段（LLM 不应该传递这些）
        # 这些字段应该由框架在 ToolContext 中提供，而不是由 LLM 传递
        FRAMEWORK_FIELDS = {"user_id", "session_id", "conversation_id", "task_id"}
        filtered_fields = []
        for field in FRAMEWORK_FIELDS:
            if field in normalized:
                filtered_fields.append(field)
                del normalized[field]
        
        if filtered_fields:
            logger.info(f"🧹 Qwen 参数规范化: 过滤框架注入字段 {filtered_fields}（这些字段应由框架提供，不应由 LLM 传递）")
        
        # 🔧 策略 8: 移除底层 HTTP 参数（如果使用简化调用）
        # 如果同时存在 api_name（表示简化调用），则不应该有 path/method 等底层参数
        if "api_name" in normalized and "parameters" in normalized:
            REMOVED_FIELDS = []
            for field in ["path", "url", "method"]:
                if field in normalized:
                    REMOVED_FIELDS.append(field)
                    del normalized[field]
            
            if REMOVED_FIELDS:
                logger.info(f"🧹 Qwen 参数规范化: 移除底层参数 {REMOVED_FIELDS}（简化调用不应包含这些字段）")
        
        # 🔧 策略 9: API 特定的参数名映射（解决 Qwen 语义推理问题）
        # Qwen 倾向于根据语义推理参数名，而非严格遵守 schema 定义
        # 例如："分析学生成绩" → 使用 "analysis_type" 而非 schema 要求的 "question"
        # 
        # ⚠️ 问题根源：Qwen 的训练目标是"语义优先"，Claude 是"Schema First"
        # 详见：qwen_参数名推理优先级分析.md
        API_PARAM_MAPPING = {
            "wenshu_api": {
                # Qwen 常用的语义推理参数名 → API 实际要求的参数名
                "analysis_type": "question",  # "分析类型" → "问题"
                "query": "question",          # "查询" → "问题"
                "prompt": "question",         # "提示" → "问题"
                "分析类型": "question",        # 中文语义名
                "分析内容": "question",        # 中文语义名
                "问题": "question",           # 中文直译
                "content": "question",        # "内容" → "问题"
                # file_url 通常正确，保留映射作为文档
                "file_url": "file_url"
            },
            # 🔧 可在此为其他 API 添加映射规则
            # "other_api": {
            #     "wrong_param": "correct_param",
            # }
        }
        
        if "api_name" in normalized and "parameters" in normalized:
            api_name = normalized["api_name"]
            if api_name in API_PARAM_MAPPING:
                mapping = API_PARAM_MAPPING[api_name]
                params = normalized["parameters"]
                fixed_count = 0
                fixed_details = []
                
                for wrong_name, correct_name in mapping.items():
                    # 只有当错误参数名存在、正确参数名不存在、且两者不同时才修复
                    if wrong_name in params and correct_name not in params and wrong_name != correct_name:
                        # 执行参数名修复
                        params[correct_name] = params.pop(wrong_name)
                        fixed_count += 1
                        fixed_details.append(f"{wrong_name}→{correct_name}")
                        logger.info(
                            f"🔧 Qwen 参数名修复: {wrong_name} → {correct_name} "
                            f"(api={api_name}, 避免第一次调用失败)"
                        )
                
                if fixed_count > 0:
                    logger.info(
                        f"✅ 成功修复 {fixed_count} 个参数名: [{', '.join(fixed_details)}]，"
                        f"避免了额外的 LLM 调用（节省约 $0.015 + 8秒）"
                    )
        
        # 🔧 策略 10: API 必需参数智能补全（解决 Qwen 参数缺失问题）
        # Qwen 有时会遗漏必需参数，认为某些参数"显而易见"可以省略
        # 例如：调用 wenshu_api 只传 file_url，认为"分析文件"的意图已经很明确
        if "api_name" in normalized and "parameters" in normalized:
            api_name = normalized["api_name"]
            params = normalized["parameters"]
            
            # 定义 API 必需参数的智能补全规则
            # 格式：{api_name: {required_param: default_value_generator}}
            API_REQUIRED_PARAMS = {
                "wenshu_api": {
                    "question": lambda p: (
                        # 策略 1: 如果有 file_url，生成文件分析提示
                        "请分析这个文件的内容" if "file_url" in p
                        # 策略 2: 默认通用分析提示
                        else "请分析数据"
                    )
                },
                # 🔧 可在此为其他 API 添加必需参数补全规则
            }
            
            if api_name in API_REQUIRED_PARAMS:
                rules = API_REQUIRED_PARAMS[api_name]
                补全_count = 0
                补全_details = []
                
                for required_param, generator in rules.items():
                    # 只有当必需参数缺失时才补全
                    if required_param not in params:
                        # 生成默认值（支持动态生成器函数）
                        default_value = generator(params) if callable(generator) else generator
                        params[required_param] = default_value
                        补全_count += 1
                        补全_details.append(f"{required_param}='{default_value}'")
                        logger.info(
                            f"🔧 Qwen 参数补全: 添加缺失的必需参数 {required_param}='{default_value}' "
                            f"(api={api_name}, 避免 HTTP 422 错误)"
                        )
                
                if 补全_count > 0:
                    logger.info(
                        f"✅ 成功补全 {补全_count} 个必需参数: [{', '.join(补全_details)}]，"
                        f"避免了第一次调用失败（节省约 $0.015 + 8秒）"
                    )
        
        return normalized
    
    def _parse_response(self, response) -> LLMResponse:
        """
        解析千问响应为统一格式
        
        Args:
            response: OpenAI 格式的响应
            
        Returns:
            LLMResponse
        """
        choice = response.choices[0]
        message = choice.message
        
        # 提取内容
        content_text = message.content or ""
        thinking_text = getattr(message, "reasoning_content", None)
        
        # 提取工具调用
        tool_calls = []
        # 🔍 调试日志
        logger.info(f"🔍 [DEBUG] message.tool_calls: {message.tool_calls}")
        if message.tool_calls:
            logger.info(f"🔍 [DEBUG] message.tool_calls 数量: {len(message.tool_calls)}")
            for tc in message.tool_calls:
                logger.info(f"🔍 [DEBUG] 工具调用: id={tc.id}, name={tc.function.name}, args={tc.function.arguments[:100] if tc.function.arguments else 'None'}")
                
                # 解析参数并规范化
                input_dict = json.loads(tc.function.arguments) if tc.function.arguments else {}
                normalized_input = self._normalize_tool_input(input_dict)
                
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "input": normalized_input,
                    "type": "tool_use"  # 🔄 统一转换为 Claude 格式（适配器层职责）
                })
        else:
            # 🔧 降级为 DEBUG，避免健康探测时的误报
            logger.debug(f"message.tool_calls 为空（stop_reason={choice.finish_reason}）")
        
        # Usage 信息
        usage = {}
        if response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
                "thinking_tokens": 0
            }
            
            # 估算 thinking tokens
            if thinking_text:
                usage["thinking_tokens"] = self.count_tokens(thinking_text)
            
            # Token 使用量日志
            logger.info(
                f"📊 Token 使用: input={usage['input_tokens']:,}, "
                f"output={usage['output_tokens']:,}, "
                f"thinking={usage['thinking_tokens']:,}"
            )
        
        # 🔄 统一转换 stop_reason（Qwen -> Claude 格式）
        # OpenAI/Qwen: "tool_calls" -> Claude: "tool_use"
        stop_reason = choice.finish_reason
        if stop_reason == "tool_calls":
            stop_reason = "tool_use"
            logger.debug("🔄 转换 stop_reason: tool_calls -> tool_use")
        
        # 构建 raw_content
        raw_content = []
        if thinking_text:
            raw_content.append({
                "type": "thinking",
                "thinking": thinking_text
            })
        if content_text:
            raw_content.append({
                "type": "text",
                "text": content_text
            })
        for tc in tool_calls:
            raw_content.append({
                "type": "tool_use",
                "id": tc["id"],
                "name": tc["name"],
                "input": tc["input"]
            })
        
        return LLMResponse(
            content=content_text,
            thinking=thinking_text,
            tool_calls=tool_calls if tool_calls else None,
            stop_reason=stop_reason,  # ✅ 已转换为 Claude 格式
            usage=usage,
            model=self.config.model,  # 🆕 实际使用的模型名称
            raw_content=raw_content
        )


# ============================================================
# 工厂函数
# ============================================================

def create_qwen_service(
    model: str = "qwen3-max",
    api_key: Optional[str] = None,
    region: str = "cn-beijing",
    base_url: Optional[str] = None,
    enable_thinking: bool = False,
    **kwargs
) -> QwenLLMService:
    """
    创建千问服务的便捷函数
    
    Args:
        model: 模型名称（qwen3-max 或 qwen-plus）
        api_key: API 密钥（默认从环境变量读取）
        region: 地域（cn-beijing, singapore, us-virginia, finance）
        base_url: 自定义 API 端点（优先级高于 region）
        enable_thinking: 启用深度思考
        **kwargs: 其他配置参数
        
    Returns:
        QwenLLMService 实例
        
    示例：
        # qwen3-max: 对标 claude-sonnet-4-5（旗舰模型）
        llm = create_qwen_service(
            model="qwen3-max",
            enable_thinking=True
        )
        
        # qwen-plus: 对标 claude-haiku-4-5（快速模型）
        llm = create_qwen_service(
            model="qwen-plus",
            enable_thinking=False
        )
        
        # 自定义端点（使用代理）
        llm = create_qwen_service(
            model="qwen3-max",
            base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        )
    """
    if api_key is None:
        api_key = os.getenv("DASHSCOPE_API_KEY")
    
    config = QwenConfig(
        provider=LLMProvider.QWEN,
        model=model,
        api_key=api_key,
        region=region,
        base_url=base_url,
        enable_thinking=enable_thinking,
        **kwargs
    )
    
    return QwenLLMService(config)
