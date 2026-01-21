"""
端到端验证：Claude 不可用时自动切换到 Qwen

目标：
1. ChatService → AgentRouter → IntentAnalyzer（意图识别）
2. Claude 主模型失败 → 自动切换 Qwen
3. 数据库/消息队列 IO 全部 Mock
"""

# 1. 标准库
import os
from pathlib import Path
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


def _load_env() -> None:
    """
    读取本地 .env（仅加载 Qwen 相关配置）
    """
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
async def test_e2e_fallback_claude_to_qwen(monkeypatch):
    """
    Claude API Key 不可用时，验证自动切换到 Qwen
    """
    # 1) 加载 Qwen 环境变量
    _load_env()
    api_key = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    assert api_key, "未检测到 QWEN_API_KEY/DASHSCOPE_API_KEY，请检查 .env 配置"
    os.environ.setdefault("QWEN_API_KEY", api_key)
    os.environ.setdefault(
        "QWEN_BASE_URL",
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    )
    
    # 2) 禁用全局覆盖，强制走 profiles.yaml 的主备链路
    monkeypatch.delenv("LLM_GLOBAL_CONFIG_PATH", raising=False)
    monkeypatch.delenv("LLM_FORCE_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_GLOBAL_PROVIDER", raising=False)
    
    # 3) 设置 Claude Key 为不可用，触发切换
    monkeypatch.setenv("ANTHROPIC_API_KEY", "invalid")
    monkeypatch.setenv("CLAUDE_API_KEY_VENDOR_A", "invalid")
    monkeypatch.setenv("CLAUDE_API_KEY_VENDOR_B", "invalid")
    
    # 降低输出成本
    monkeypatch.setenv("LLM_MAIN_AGENT_MAX_TOKENS", "256")
    monkeypatch.setenv("LLM_INTENT_ANALYZER_MAX_TOKENS", "256")
    reload_config()
    
    # 4) Mock SessionService / Redis / Events（仅 IO）
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
    session_service.events.emit_custom = AsyncMock()
    session_service.end_session = AsyncMock()
    session_service.workspace_manager = MagicMock()
    session_service.workspace_manager.get_workspace_root = MagicMock(return_value="/tmp")
    
    chat_service = ChatService(session_service=session_service, enable_routing=True)
    chat_service.conversation_service = MagicMock()
    
    # 5) Mock DB IO / MQ IO
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
    
    # 6) 创建真实 SimpleAgent（Claude 主 + Qwen 备）
    event_manager = create_event_manager(DummyEventStorage())
    agent = create_simple_agent(workspace_dir="/tmp", event_manager=event_manager)
    
    # 7) 执行：IntentAnalyzer + SimpleAgent（应自动切换到 Qwen）
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
    
    # 8) 断言：意图结果已生成
    intent_result = getattr(agent, "_last_intent_result", None)
    assert intent_result is not None
    assert 0.0 <= intent_result.complexity_score <= 10.0
    
    # 9) 断言：发生 LLM 切换，且切换目标为 Qwen
    emit_calls = session_service.events.emit_custom.await_args_list
    switch_events = [
        call.kwargs.get("event_data")
        for call in emit_calls
        if call.kwargs.get("event_type") == "llm_switch"
    ]
    assert switch_events, "未捕获到 llm_switch 事件"
    
    switch_event = switch_events[-1] or {}
    assert switch_event.get("reason") == "probe_failed"
    assert switch_event.get("role") == "simple_agent"
    assert (switch_event.get("to") or {}).get("provider") == "qwen"
    assert (switch_event.get("from") or {}).get("provider") == "claude"
    assert isinstance(switch_event.get("errors", []), list)
