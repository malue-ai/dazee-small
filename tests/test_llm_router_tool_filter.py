"""
测试 ModelRouter 的工具过滤行为
"""

import pytest

from core.llm.base import BaseLLMService, LLMConfig, LLMProvider, LLMResponse, Message
from core.llm.router import ModelRouter, RouteTarget


class CaptureLLMService(BaseLLMService):
    """记录传入 tools 的 LLM Stub"""
    
    def __init__(self, provider: LLMProvider, model: str):
        self.config = LLMConfig(
            provider=provider,
            model=model,
            api_key="test_key",
            enable_thinking=False,
            enable_caching=False
        )
        self.last_tools = None
    
    async def create_message_async(
        self,
        messages,
        system=None,
        tools=None,
        **kwargs
    ) -> LLMResponse:
        self.last_tools = tools
        return LLMResponse(content="ok")
    
    async def create_message_stream(
        self,
        messages,
        system=None,
        tools=None,
        on_thinking=None,
        on_content=None,
        on_tool_call=None,
        **kwargs
    ):
        self.last_tools = tools
        yield LLMResponse(content="ok", is_stream=True)
    
    def count_tokens(self, text: str) -> int:
        return 1


class TestModelRouterToolFilter:
    """ModelRouter 工具过滤测试"""
    
    @pytest.mark.asyncio
    async def test_filter_tools_for_non_claude(self):
        """非 Claude 模型仅保留 dict 工具"""
        service = CaptureLLMService(LLMProvider.QWEN, "qwen-max")
        router = ModelRouter(
            primary=RouteTarget(
                service=service,
                provider=LLMProvider.QWEN,
                model="qwen-max",
                name="qwen:qwen-max"
            )
        )
        
        tools = ["web_search", {"name": "plan_todo", "input_schema": {"type": "object"}}]
        await router.create_message_async(
            messages=[Message(role="user", content="ping")],
            tools=tools
        )
        
        assert service.last_tools == [{"name": "plan_todo", "input_schema": {"type": "object"}}]

    @pytest.mark.asyncio
    async def test_filter_tools_for_non_claude_stream(self):
        """流式场景同样过滤非 dict 工具"""
        service = CaptureLLMService(LLMProvider.QWEN, "qwen-max")
        router = ModelRouter(
            primary=RouteTarget(
                service=service,
                provider=LLMProvider.QWEN,
                model="qwen-max",
                name="qwen:qwen-max"
            )
        )
        
        tools = ["web_search", {"name": "plan_todo", "input_schema": {"type": "object"}}]
        async for _ in router.create_message_stream(
            messages=[Message(role="user", content="ping")],
            tools=tools
        ):
            pass
        
        assert service.last_tools == [{"name": "plan_todo", "input_schema": {"type": "object"}}]

    def test_router_policy_env_override(self, monkeypatch):
        """环境变量可覆盖默认路由策略"""
        monkeypatch.setenv("LLM_ROUTER_MAX_FAILURES", "5")
        monkeypatch.setenv("LLM_ROUTER_COOLDOWN_SECONDS", "10")
        
        service = CaptureLLMService(LLMProvider.QWEN, "qwen-max")
        router = ModelRouter(
            primary=RouteTarget(
                service=service,
                provider=LLMProvider.QWEN,
                model="qwen-max",
                name="qwen:qwen-max"
            )
        )
        
        assert router.policy.max_failures == 5
        assert router.policy.cooldown_seconds == 10
