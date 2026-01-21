"""
测试 Qwen Provider 兼容性
"""

from core.llm import create_base_llm_service, LLMProvider
from core.llm.qwen import QwenLLMService


def test_qwen_provider_uses_openai_service(monkeypatch):
    """Qwen Provider 使用 DashScope SDK 实现"""
    monkeypatch.setenv("QWEN_BASE_URL", "https://example.com/compatible-mode/v1")
    
    llm = create_base_llm_service(
        provider=LLMProvider.QWEN,
        model="qwen-max",
        api_key="test_key"
    )
    
    assert isinstance(llm, QwenLLMService)
    assert llm.base_url == "https://example.com/compatible-mode/v1"
    assert llm.config.compat == "qwen"
