"""
测试 UnifiedToolCaller 的 fallback 注入逻辑
"""

import pytest

from core.llm.base import BaseLLMService, LLMConfig, LLMProvider, LLMResponse
from core.llm.router import ModelRouter, RouteTarget
from core.tool.unified_tool_caller import UnifiedToolCaller
from core.tool.capability import Capability, CapabilityRegistry, CapabilityType


class DummyLLM:
    """简单 LLM Stub"""

    def __init__(self, supports_skills: bool):
        self._supports_skills = supports_skills

    def supports_skills(self) -> bool:
        return self._supports_skills


class DummyRouterLLM(BaseLLMService):
    """用于 ModelRouter 的 LLM Stub"""
    
    def __init__(self, provider: LLMProvider, model: str, supports_skills: bool):
        self.config = LLMConfig(
            provider=provider,
            model=model,
            api_key="test_key",
            enable_thinking=False,
            enable_caching=False
        )
        self._supports_skills = supports_skills
    
    def supports_skills(self) -> bool:
        return self._supports_skills
    
    async def create_message_async(self, messages, system=None, tools=None, **kwargs) -> LLMResponse:
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


def _create_registry() -> CapabilityRegistry:
    """创建最小化 Registry"""
    registry = CapabilityRegistry(config_path="/tmp/not_exists.yaml", skills_dir="/tmp/not_exists")
    registry.capabilities = {}
    
    registry.register(Capability(
        name="pptx",
        type=CapabilityType.SKILL,
        subtype="CUSTOM",
        provider="anthropic",
        capabilities=["ppt_generation"],
        priority=50,
        cost={"time": "medium", "money": "paid"},
        constraints={},
        metadata={"description": "测试 Skill"},
        input_schema=None,
        fallback_tool="slidespeak_render",
        skill_id="pptx",
        skill_path=None,
        level=2,
        cache_stable=False
    ))
    
    registry.register(Capability(
        name="slidespeak_render",
        type=CapabilityType.TOOL,
        subtype="CUSTOM",
        provider="user",
        capabilities=["ppt_generation"],
        priority=50,
        cost={"time": "medium", "money": "free"},
        constraints={},
        metadata={"description": "fallback tool"},
        input_schema={"type": "object", "properties": {}, "required": []},
        fallback_tool=None,
        skill_id=None,
        skill_path=None,
        level=2,
        cache_stable=False
    ))
    
    return registry


class TestUnifiedToolCaller:
    """UnifiedToolCaller 测试"""
    
    def test_skill_fallback_injected_when_skills_not_supported(self):
        """不支持 Skills 时注入 fallback 工具"""
        registry = _create_registry()
        caller = UnifiedToolCaller(registry)
        llm = DummyLLM(supports_skills=False)
        
        required = []
        result = caller.ensure_skill_fallback(
            required_capabilities=required,
            recommended_skill={"name": "pptx"},
            llm_service=llm
        )
        
        assert "slidespeak_render" in result
    
    def test_skill_fallback_not_injected_when_supported(self):
        """支持 Skills 时不注入 fallback 工具"""
        registry = _create_registry()
        caller = UnifiedToolCaller(registry)
        llm = DummyLLM(supports_skills=True)
        
        required = []
        result = caller.ensure_skill_fallback(
            required_capabilities=required,
            recommended_skill={"name": "pptx"},
            llm_service=llm
        )
        
        assert "slidespeak_render" not in result

    def test_skill_fallback_injected_when_router_has_non_skill_target(self):
        """路由包含非 Skills 目标时注入 fallback"""
        registry = _create_registry()
        caller = UnifiedToolCaller(registry)
        
        primary = DummyRouterLLM(LLMProvider.CLAUDE, "claude", supports_skills=True)
        fallback = DummyRouterLLM(LLMProvider.QWEN, "qwen", supports_skills=False)
        router = ModelRouter(
            primary=RouteTarget(
                service=primary,
                provider=LLMProvider.CLAUDE,
                model="claude",
                name="claude:primary"
            ),
            fallbacks=[
                RouteTarget(
                    service=fallback,
                    provider=LLMProvider.QWEN,
                    model="qwen",
                    name="fallback_0:qwen:qwen"
                )
            ]
        )
        
        required = []
        result = caller.ensure_skill_fallback(
            required_capabilities=required,
            recommended_skill={"name": "pptx"},
            llm_service=router
        )
        
        assert "slidespeak_render" in result
