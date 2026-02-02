"""
测试：全局一键切换配置覆盖
"""

# 1. 标准库
import os

# 2. 第三方库
import pytest

# 3. 本地模块
from config.llm_config import get_llm_profile, reload_config


@pytest.mark.parametrize(
    "profile_name,expected_model",
    [
        ("intent_analyzer", "qwen-plus"),
        ("main_agent", "qwen-max"),
        ("plan_manager", "qwen-max"),
    ]
)
def test_global_override_qwen(profile_name: str, expected_model: str, monkeypatch, tmp_path):
    """
    全局切换到 Qwen 时，默认模型映射正确
    """
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join([
            "llm_global:",
            "  enabled: true",
            "  provider: \"qwen\"",
            "  base_url: \"https://dashscope-intl.aliyuncs.com/compatible-mode/v1\"",
            "  api_key_env: \"QWEN_API_KEY\"",
            "  compat: \"qwen\"",
            "  model_map:",
            "    intent_analyzer: \"qwen-plus\"",
            "    default: \"qwen-max\"",
        ]) + "\n",
        encoding="utf-8"
    )
    monkeypatch.setenv("LLM_GLOBAL_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("QWEN_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
    monkeypatch.setenv("QWEN_API_KEY", "test_key")
    
    reload_config()
    profile = get_llm_profile(profile_name)
    
    assert profile["provider"] == "qwen"
    assert profile["model"] == expected_model
    assert profile["base_url"] == "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    assert profile["api_key_env"] == "QWEN_API_KEY"
