"""
测试 LLM 路由探针与自动切换
"""

import pytest

from core.llm.router import ModelRouter, RouteTarget
from core.llm.base import BaseLLMService, LLMConfig, LLMProvider, LLMResponse, Message


class DummyLLMService(BaseLLMService):
    """用于测试的 LLM 服务桩"""

    def __init__(self, provider: LLMProvider, model: str, should_fail: bool = False):
        self.config = LLMConfig(
            provider=provider,
            model=model,
            api_key="test_key",
            enable_thinking=False,
            enable_caching=False,
        )
        self.should_fail = should_fail

    async def create_message_async(
        self,
        messages,
        system=None,
        tools=None,
        **kwargs
    ) -> LLMResponse:
        if self.should_fail:
            raise RuntimeError("mock failure")
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
        yield LLMResponse(content="ok", is_stream=True)

    def count_tokens(self, text: str) -> int:
        return 1


class TestModelRouterProbe:
    """ModelRouter 探针测试"""

    @pytest.mark.asyncio
    async def test_probe_primary_ok(self):
        """主模型健康时不切换"""
        primary_service = DummyLLMService(LLMProvider.CLAUDE, "primary")
        fallback_service = DummyLLMService(LLMProvider.CLAUDE, "fallback")

        router = ModelRouter(
            primary=RouteTarget(
                service=primary_service,
                provider=LLMProvider.CLAUDE,
                model="primary",
                name="claude:primary"
            ),
            fallbacks=[
                RouteTarget(
                    service=fallback_service,
                    provider=LLMProvider.CLAUDE,
                    model="fallback",
                    name="fallback_0:claude:fallback"
                )
            ]
        )

        result = await router.probe(max_retries=0)
        assert result["switched"] is False
        assert result["selected"]["model"] == "primary"

    @pytest.mark.asyncio
    async def test_probe_switch_to_fallback(self):
        """主模型失败时自动切换到备选"""
        primary_service = DummyLLMService(LLMProvider.CLAUDE, "primary", should_fail=True)
        fallback_service = DummyLLMService(LLMProvider.CLAUDE, "fallback")

        router = ModelRouter(
            primary=RouteTarget(
                service=primary_service,
                provider=LLMProvider.CLAUDE,
                model="primary",
                name="claude:primary"
            ),
            fallbacks=[
                RouteTarget(
                    service=fallback_service,
                    provider=LLMProvider.CLAUDE,
                    model="fallback",
                    name="fallback_0:claude:fallback"
                )
            ],
            policy={"max_failures": 1, "cooldown_seconds": 60}
        )

        result = await router.probe(max_retries=0)
        assert result["switched"] is True
        assert result["selected"]["model"] == "fallback"
        assert router._target_available(router.primary) is False

    @pytest.mark.asyncio
    async def test_probe_switch_back_to_primary_when_recovered(self):
        """高优先级恢复后应切回主模型"""
        primary_service = DummyLLMService(LLMProvider.CLAUDE, "primary", should_fail=True)
        fallback_service = DummyLLMService(LLMProvider.CLAUDE, "fallback")
        
        router = ModelRouter(
            primary=RouteTarget(
                service=primary_service,
                provider=LLMProvider.CLAUDE,
                model="primary",
                name="claude:primary"
            ),
            fallbacks=[
                RouteTarget(
                    service=fallback_service,
                    provider=LLMProvider.CLAUDE,
                    model="fallback",
                    name="fallback_0:claude:fallback"
                )
            ],
            policy={"max_failures": 1, "cooldown_seconds": 60}
        )
        
        result = await router.probe(max_retries=0, include_unhealthy=True)
        assert result["selected"]["model"] == "fallback"
        
        primary_service.should_fail = False
        result = await router.probe(max_retries=0, include_unhealthy=True)
        assert result["selected"]["model"] == "primary"
        assert result["switched"] is True

