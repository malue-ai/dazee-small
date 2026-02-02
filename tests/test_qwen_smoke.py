"""
Qwen 简单链路冒烟测试（需配置 QWEN_API_KEY）
"""

import os
from pathlib import Path
import pytest

from core import create_simple_agent
from core.events import create_event_manager


class DummyEventStorage:
    """最小事件存储实现"""

    def __init__(self):
        self._seq = 0

    async def generate_session_seq(self, session_id: str) -> int:
        self._seq += 1
        return self._seq

    async def get_session_context(self, session_id: str) -> dict:
        return {"conversation_id": "conv_test"}

    async def buffer_event(self, session_id: str, event_data: dict) -> None:
        return None

    async def update_heartbeat(self, session_id: str) -> None:
        return None


@pytest.mark.asyncio
async def test_qwen_simple_agent_smoke(monkeypatch):
    """用 Qwen 模型走一轮 SimpleAgent"""
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).resolve().parents[1] / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=True)
    except Exception:
        # python-dotenv 未安装或加载失败时，尝试手动加载关键环境变量
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
                key = key.strip()
                if key.startswith("export "):
                    key = key[len("export "):].strip()
                value = value.strip()
                if "#" in value and not (value.startswith('"') or value.startswith("'")):
                    value = value.split("#", 1)[0].strip()
                value = value.strip().strip('"').strip("'")
                if key in {"QWEN_API_KEY", "QWEN_BASE_URL"} and key not in os.environ:
                    os.environ[key] = value
    
    if "QWEN_API_KEY" not in os.environ and "DASHSCOPE_API_KEY" not in os.environ:
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
                key = key.strip()
                if key.startswith("export "):
                    key = key[len("export "):].strip()
                value = value.strip()
                if "#" in value and not (value.startswith('"') or value.startswith("'")):
                    value = value.split("#", 1)[0].strip()
                value = value.strip().strip('"').strip("'")
                if key in {"QWEN_API_KEY", "DASHSCOPE_API_KEY"} and key not in os.environ:
                    os.environ[key] = value
    
    api_key = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    assert api_key, "未检测到 QWEN_API_KEY/DASHSCOPE_API_KEY，请检查 .env 配置"
    if "QWEN_API_KEY" not in os.environ:
        os.environ["QWEN_API_KEY"] = api_key
    
    base_url = os.getenv("QWEN_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
    
    monkeypatch.setenv("LLM_MAIN_AGENT_PROVIDER", "qwen")
    monkeypatch.setenv("LLM_MAIN_AGENT_MODEL", "qwen-max")
    monkeypatch.setenv("LLM_MAIN_AGENT_BASE_URL", base_url)
    monkeypatch.setenv("LLM_MAIN_AGENT_API_KEY_ENV", "QWEN_API_KEY")
    monkeypatch.setenv("LLM_MAIN_AGENT_COMPAT", "qwen")
    
    event_manager = create_event_manager(DummyEventStorage())
    agent = create_simple_agent(workspace_dir="/tmp", event_manager=event_manager)
    
    async for event in agent.chat(
        messages=[{"role": "user", "content": "你好，简要自我介绍"}],
        session_id="sess_test",
        message_id="msg_test",
        enable_stream=True,
        variables={}
    ):
        if event.get("type") == "message_stop":
            break
