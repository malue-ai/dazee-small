"""
模型路由器

用于在多个 LLM 服务之间进行主备切换，降低单点故障风险。
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Union, AsyncIterator, Callable
import os
import time

from logger import get_logger
from .base import BaseLLMService, LLMResponse, Message, ToolType, LLMProvider
from .health_monitor import LLMHealthMonitor, get_llm_health_monitor

logger = get_logger("llm.router")


@dataclass
class RouterPolicy:
    """
    路由策略
    
    Attributes:
        max_failures: 最大失败次数（超过即进入冷却）
        cooldown_seconds: 冷却时间（秒），可通过 LLM_ROUTER_COOLDOWN_SECONDS 环境变量覆盖
    """
    max_failures: int = 2
    cooldown_seconds: int = 600  # 默认 10 分钟（V7.11：从 1 小时改为 10 分钟）


def _resolve_policy(policy: Optional[Dict[str, Any]]) -> RouterPolicy:
    """
    解析路由策略（支持环境变量兜底）
    """
    resolved = dict(policy or {})
    
    if "max_failures" not in resolved:
        env_max_failures = os.getenv("LLM_ROUTER_MAX_FAILURES")
        if env_max_failures:
            resolved["max_failures"] = int(env_max_failures)
    
    if "cooldown_seconds" not in resolved:
        env_cooldown = os.getenv("LLM_ROUTER_COOLDOWN_SECONDS")
        if env_cooldown:
            resolved["cooldown_seconds"] = int(env_cooldown)
    
    return RouterPolicy(**resolved)


@dataclass
class RouteTarget:
    """
    路由目标
    
    Attributes:
        service: LLM 服务实例
        provider: 提供商
        model: 模型名称
        name: 目标名称（用于日志与状态跟踪）
    """
    service: BaseLLMService
    provider: LLMProvider
    model: str
    name: str


class ModelRouter(BaseLLMService):
    """
    模型路由器（支持主备切换）
    """
    
    def __init__(
        self,
        primary: RouteTarget,
        fallbacks: Optional[List[RouteTarget]] = None,
        policy: Optional[Dict[str, Any]] = None,
        health_monitor: Optional[LLMHealthMonitor] = None
    ):
        """
        初始化路由器
        
        Args:
            primary: 主模型
            fallbacks: 备选模型列表
            policy: 路由策略配置
            health_monitor: 健康监控器
        """
        self.primary = primary
        self.fallbacks = fallbacks or []
        self.targets = [self.primary] + self.fallbacks
        self.policy = _resolve_policy(policy)
        self.health_monitor = health_monitor or get_llm_health_monitor()
        
        # 🆕 V7.10: 暴露 Primary 的 config，供上层兼容性检查（如 prompt caching）
        self.config = getattr(self.primary.service, 'config', None)
        
        # 失败统计
        self._failure_counts: Dict[str, int] = {t.name: 0 for t in self.targets}
        self._last_failure_ts: Dict[str, float] = {t.name: 0.0 for t in self.targets}
        self._last_selected: str = self.primary.name
    
    def _target_available(self, target: RouteTarget) -> bool:
        """
        判断目标是否可用
        
        Args:
            target: 目标
            
        Returns:
            是否可用
        """
        if self.health_monitor and not self.health_monitor.is_healthy(target.name):
            return False
        
        failures = self._failure_counts.get(target.name, 0)
        if failures < self.policy.max_failures:
            return True
        
        # 已达到熔断阈值，检查冷却时间
        last_ts = self._last_failure_ts.get(target.name, 0.0)
        elapsed = time.time() - last_ts
        cooldown_passed = elapsed >= self.policy.cooldown_seconds
        
        if cooldown_passed:
            # 🆕 冷却时间已过，尝试恢复
            logger.info(
                f"🔄 尝试恢复熔断目标: target={target.name}, "
                f"冷却时间已过={int(elapsed)}秒"
            )
            return True
        
        return False
    
    def _record_failure(self, target: RouteTarget, error: Exception, force_down: bool = False, is_probe: bool = False) -> None:
        """
        记录失败
        
        Args:
            target: 目标
            error: 异常
            force_down: 是否强制标记为不可用
            is_probe: 是否为探测请求（探测失败不记录 WARNING）
        """
        previous_failures = self._failure_counts.get(target.name, 0)
        
        if force_down:
            self._failure_counts[target.name] = max(
                previous_failures,
                self.policy.max_failures
            )
        else:
            self._failure_counts[target.name] = previous_failures + 1
        
        current_failures = self._failure_counts[target.name]
        self._last_failure_ts[target.name] = time.time()
        
        # 探测请求的失败不记录 WARNING（已在 probe 方法中记录 INFO）
        if not is_probe:
            # 🔍 DEBUG: 打印 API Key 信息（脱敏）
            api_key = getattr(target.service, 'config', None)
            api_key = getattr(api_key, 'api_key', None) if api_key else None
            if api_key:
                masked_key = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
            else:
                masked_key = "未配置"
            
            logger.warning(
                f"⚠️ 模型调用失败: target={target.name}, "
                f"failures={current_failures}, api_key={masked_key}, error={error}"
            )
        
        # 🆕 检测是否刚达到熔断阈值
        if previous_failures < self.policy.max_failures <= current_failures:
            logger.warning(
                f"🔒 模型已熔断: target={target.name}, "
                f"failures={current_failures}/{self.policy.max_failures}, "
                f"冷却时间={self.policy.cooldown_seconds}秒"
            )
    
    def _record_success(self, target: RouteTarget) -> None:
        """
        记录成功（重置失败计数）
        
        Args:
            target: 目标
        """
        if self._failure_counts.get(target.name, 0) > 0:
            self._failure_counts[target.name] = 0
            self._last_failure_ts[target.name] = 0.0
            logger.info(f"✅ 模型恢复: target={target.name}")

    def _format_target(self, target: RouteTarget) -> Dict[str, str]:
        """
        格式化目标信息（用于事件与日志）
        """
        base_url = ""
        if hasattr(target.service, "config"):
            base_url = getattr(target.service.config, "base_url", "") or ""
        return {
            "name": target.name,
            "provider": target.provider.value,
            "model": target.model,
            "base_url": base_url
        }
    
    def _select_targets(self) -> List[RouteTarget]:
        """
        选择可用目标
        
        Returns:
            目标列表（优先级排序）
        """
        available = [t for t in self.targets if self._target_available(t)]
        return available if available else [self.primary]
    
    def _filter_tools_for_provider(
        self,
        tools: Optional[List[Union[ToolType, str, Dict]]],
        provider: LLMProvider
    ) -> Optional[List[Union[ToolType, str, Dict]]]:
        """
        针对不同提供商过滤工具
        
        Args:
            tools: 工具列表
            provider: 目标提供商
            
        Returns:
            过滤后的工具列表
        """
        if not tools:
            return tools
        if provider == LLMProvider.CLAUDE:
            return tools
        # 非 Claude：仅保留 dict 类型工具（避免 native tool 字符串）
        return [tool for tool in tools if isinstance(tool, dict)]

    async def probe(
        self,
        max_retries: int = 3,
        message: str = "ping",
        include_unhealthy: bool = False
    ) -> Dict[str, Any]:
        """
        服务存活探针（主备切换）
        
        Args:
            max_retries: 每个目标的最大重试次数
            message: 探针消息内容
            include_unhealthy: 是否探测不可用目标（用于高优先级恢复探测）
        
        Returns:
            探针结果（包含是否发生切换）
        """
        from infra.resilience.retry import retry_async
        
        last_error: Optional[Exception] = None
        errors: List[Dict[str, str]] = []
        
        targets = self.targets if include_unhealthy else self._select_targets()
        previous_selected = self._last_selected
        
        for target in targets:
            start_time = time.time()
            
            async def _call():
                return await target.service.create_message_async(
                    messages=[Message(role="user", content=message)],
                    system=None,
                    tools=None,
                    max_tokens=100,  # 轻量级探针
                    temperature=0.0,
                    override_thinking=False,  # 禁用 thinking（避免 budget_tokens 冲突）
                    enable_caching=False,
                    is_probe=True,  # 标记为探测请求，避免 ERROR 日志
                )
            
            try:
                if target.provider == LLMProvider.CLAUDE:
                    await _call()
                else:
                    await retry_async(_call, max_retries=max_retries)
                
                latency_ms = (time.time() - start_time) * 1000
                if self.health_monitor:
                    self.health_monitor.record_success(target.name, latency_ms)
                self._record_success(target)
                self._last_selected = target.name
                
                # 探测成功时记录 INFO 日志
                logger.info(f"✅ 探测成功: {target.name} ({latency_ms:.0f}ms)")
                
                return {
                    "primary": self._format_target(self.primary),
                    "selected": self._format_target(target),
                    "switched": target.name != previous_selected,
                    "errors": errors
                }
            except Exception as e:
                latency_ms = (time.time() - start_time) * 1000
                if self.health_monitor:
                    self.health_monitor.record_failure(target.name, latency_ms, e)
                
                # 提取 API key 环境变量名（用于日志展示）
                api_key_env = "未知"
                if hasattr(target.service, 'config') and hasattr(target.service.config, 'api_key_env'):
                    api_key_env = target.service.config.api_key_env
                
                errors.append({
                    "target": target.name,
                    "provider": target.provider.value,
                    "model": target.model,
                    "api_key_env": api_key_env,
                    "error": str(e)
                })
                
                # 探测失败时记录 INFO 日志（非 ERROR）
                logger.info(f"❌ 探测失败: {target.name} (密钥: {api_key_env}) - {str(e)[:100]}")
                
                self._record_failure(target, e, force_down=True, is_probe=True)
                last_error = e
                continue
        
        raise last_error if last_error else RuntimeError("模型探针失败：无可用目标")
    
    async def create_message_async(
        self,
        messages: List[Message],
        system: Optional[str] = None,
        tools: Optional[List[Union[ToolType, str, Dict]]] = None,
        **kwargs
    ) -> LLMResponse:
        """
        创建消息（异步）
        """
        last_error: Optional[Exception] = None
        
        for target in self._select_targets():
            start_time = time.time()
            try:
                filtered_tools = self._filter_tools_for_provider(tools, target.provider)
                response = await target.service.create_message_async(
                    messages=messages,
                    system=system,
                    tools=filtered_tools,
                    **kwargs
                )
                latency_ms = (time.time() - start_time) * 1000
                if self.health_monitor:
                    self.health_monitor.record_success(target.name, latency_ms)
                self._record_success(target)
                self._last_selected = target.name
                return response
            except Exception as e:
                latency_ms = (time.time() - start_time) * 1000
                if self.health_monitor:
                    self.health_monitor.record_failure(target.name, latency_ms, e)
                self._record_failure(target, e)
                last_error = e
                continue
        
        raise last_error if last_error else RuntimeError("模型调用失败：无可用目标")
    
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
        """
        last_error: Optional[Exception] = None
        
        for target in self._select_targets():
            yielded = False
            start_time = time.time()
            try:
                filtered_tools = self._filter_tools_for_provider(tools, target.provider)
                async for chunk in target.service.create_message_stream(
                    messages=messages,
                    system=system,
                    tools=filtered_tools,
                    on_thinking=on_thinking,
                    on_content=on_content,
                    on_tool_call=on_tool_call,
                    **kwargs
                ):
                    yielded = True
                    yield chunk
                latency_ms = (time.time() - start_time) * 1000
                if self.health_monitor:
                    self.health_monitor.record_success(target.name, latency_ms)
                self._record_success(target)
                self._last_selected = target.name
                return
            except Exception as e:
                latency_ms = (time.time() - start_time) * 1000
                if self.health_monitor:
                    self.health_monitor.record_failure(target.name, latency_ms, e)
                self._record_failure(target, e)
                last_error = e
                # 已经开始输出时不切换，避免重复输出
                if yielded:
                    raise
                continue
        
        raise last_error if last_error else RuntimeError("模型流式调用失败：无可用目标")
    
    def count_tokens(self, text: str) -> int:
        """
        计算 token 数量（使用主模型估算）
        
        Args:
            text: 文本内容
            
        Returns:
            token 数量
        """
        return self.primary.service.count_tokens(text)
    
    def supports_native_tools(self) -> bool:
        """
        路由器是否支持原生工具（以主模型为准）
        """
        if hasattr(self.primary.service, "supports_native_tools"):
            return self.primary.service.supports_native_tools()
        return False
    
    def supports_skills(self) -> bool:
        """
        路由器是否支持 Skills（以主模型为准）
        """
        if hasattr(self.primary.service, "supports_skills"):
            return self.primary.service.supports_skills()
        return False
    
    def add_custom_tool(self, name: str, description: str, input_schema: Dict[str, Any]) -> None:
        """
        注册自定义工具
        """
        for target in self.targets:
            if hasattr(target.service, "add_custom_tool"):
                target.service.add_custom_tool(name=name, description=description, input_schema=input_schema)

    def convert_to_claude_tool(self, capability: Dict[str, Any]) -> Dict[str, Any]:
        """
        兼容工具转换（优先使用主模型的转换逻辑）
        
        Args:
            capability: 工具定义
            
        Returns:
            Claude 格式工具定义
        """
        if hasattr(self.primary.service, "convert_to_claude_tool"):
            return self.primary.service.convert_to_claude_tool(capability)
        return capability
    
    def enable_skills(self, skills: List[Dict[str, Any]]) -> None:
        """
        启用 Skills（仅对支持的提供商生效）
        """
        for target in self.targets:
            if hasattr(target.service, "supports_skills") and target.service.supports_skills():
                if hasattr(target.service, "enable_skills"):
                    target.service.enable_skills(skills)
    
    def disable_skills(self) -> None:
        """
        禁用 Skills
        """
        for target in self.targets:
            if hasattr(target.service, "disable_skills"):
                target.service.disable_skills()

