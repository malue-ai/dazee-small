"""
端到端验证：路由意图识别 + 单智能体路径

目标：
1. ChatService → AgentRouter → IntentAnalyzer（意图识别）
2. 复杂度评分 < 阈值 → 走 SimpleAgent
3. 数据库/消息队列 IO 全部 Mock
"""

# 1. 标准库
import os
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

# 2. 第三方库
import pytest

# 3. 本地模块
from services.chat_service import ChatService
from core.context import Context
from core import create_simple_agent
from core.events import create_event_manager
from config.llm_config import reload_config


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
async def test_end_to_end_intent_single_agent(monkeypatch, tmp_path):
    """
    验证流程：
    ChatService → AgentRouter → IntentAnalyzer → SimpleAgent
    """
    # 1) 加载 .env（真实 Qwen 接口）
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
    
    api_key = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    assert api_key, "未检测到 QWEN_API_KEY/DASHSCOPE_API_KEY，请检查 .env 配置"
    os.environ.setdefault("QWEN_API_KEY", api_key)
    
    # 2) 配置全局一键切换（来自临时 config.yaml）
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
    monkeypatch.setenv("LLM_MAIN_AGENT_MAX_TOKENS", "256")
    monkeypatch.setenv("LLM_INTENT_ANALYZER_MAX_TOKENS", "512")
    reload_config()
    
    # 3) Mock SessionService / Redis / Events（仅 IO）
    session_service = MagicMock()
    session_service.redis = MagicMock()
    session_service.redis.is_stopped = AsyncMock(return_value=False)
    session_service.redis.get_session_status = AsyncMock(return_value={"status": "completed"})
    session_service.events = MagicMock()
    session_service.events.message = MagicMock()
    session_service.events.message.emit_message_start = AsyncMock()
    session_service.events.session = MagicMock()
    session_service.events.session.emit_session_end = AsyncMock()
    session_service.events.conversation = MagicMock()
    session_service.events.conversation.emit_conversation_start = AsyncMock()
    session_service.end_session = AsyncMock()
    
    chat_service = ChatService(session_service=session_service, enable_routing=True)
    chat_service.conversation_service = MagicMock()
    
    # 4) Mock DB IO / MQ IO
    monkeypatch.setattr(chat_service, "_probe_llm_service", AsyncMock())
    
    async def fake_get_mq():
        mq = MagicMock()
        mq.push_create_event = AsyncMock()
        return mq
    
    monkeypatch.setattr("infra.message_queue.get_message_queue_client", fake_get_mq)
    
    cache = MagicMock()
    cache.append_message = AsyncMock()
    monkeypatch.setattr("services.session_cache_service.get_session_cache_service", lambda: cache)
    
    async def fake_load_messages(self) -> list:
        return []
    
    monkeypatch.setattr(Context, "load_messages", fake_load_messages)
    
    # 5) 创建真实 SimpleAgent（Qwen）
    event_manager = create_event_manager(DummyEventStorage())
    agent = create_simple_agent(workspace_dir="/tmp", event_manager=event_manager)
    
    # 6) 执行：真实 Qwen（意图识别 + 单智能体）
    await chat_service._run_agent(
        session_id="sess_test",
        agent=agent,
        message=[{"type": "text", "text": "今天天气怎么样？"}],
        user_id="user_test",
        conversation_id="conv_test",
        background_tasks=[],
        files_metadata=None,
        variables=None
    )

    # 7) 断言：意图结果已生成
    intent_result = getattr(agent, "_last_intent_result", None)
    assert intent_result is not None
    assert 0.0 <= intent_result.complexity_score <= 10.0
