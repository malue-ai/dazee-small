"""
真实 Qwen 端到端：PlanTodoTool 计划生成（禁止 mock LLM）
"""

# 1. 标准库
import os
from pathlib import Path

# 2. 第三方库
import pytest

# 3. 本地模块
from config.llm_config import reload_config
from tools.plan_todo_tool import create_plan_todo_tool


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).resolve().parents[1] / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=True)
    except Exception:
        env_path = Path(__file__).resolve().parents[1] / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                raw = line.strip()
                if not raw or raw.startswith("#"):
                    continue
                sep = "=" if "=" in raw else ":"
                if sep not in raw:
                    continue
                key, value = raw.split(sep, 1)
                key = key.strip().replace("export ", "")
                value = value.strip().strip('"').strip("'")
                if key in {"QWEN_API_KEY", "DASHSCOPE_API_KEY", "QWEN_BASE_URL"}:
                    os.environ.setdefault(key, value)


@pytest.mark.asyncio
async def test_plan_todo_create_plan_qwen(tmp_path, monkeypatch):
    """
    真实 Qwen 接口：PlanTodoTool.create_plan
    """
    _load_env()
    api_key = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    assert api_key, "未检测到 QWEN_API_KEY/DASHSCOPE_API_KEY，请检查 .env 配置"
    os.environ.setdefault("QWEN_API_KEY", api_key)
    
    base_url = os.getenv(
        "QWEN_BASE_URL",
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    )
    
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join([
            "llm_global:",
            "  enabled: true",
            "  provider: \"qwen\"",
            f"  base_url: \"{base_url}\"",
            "  api_key_env: \"QWEN_API_KEY\"",
            "  compat: \"qwen\"",
            "  model_map:",
            "    intent_analyzer: \"qwen-plus\"",
            "    default: \"qwen-max\"",
        ]) + "\n",
        encoding="utf-8"
    )
    monkeypatch.setenv("LLM_GLOBAL_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("LLM_PLAN_MANAGER_MAX_TOKENS", "512")
    reload_config()
    
    tool = create_plan_todo_tool(registry=None, memory_manager=None)
    
    result = await tool.execute(
        operation="create_plan",
        data={"user_query": "请给我一个两步的学习计划，并输出JSON"}
    )
    
    assert result.get("status") == "success"
    assert "plan" in result
