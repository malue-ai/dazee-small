"""
测试 LLM 切换事件
"""

import pytest

from services.chat_service import ChatService


class DummyEvents:
    """事件采集器"""

    def __init__(self):
        self.calls = []

    async def emit_custom(self, session_id: str, event_type: str, event_data: dict):
        self.calls.append({
            "session_id": session_id,
            "event_type": event_type,
            "event_data": event_data
        })
        return {"ok": True}


class DummySessionService:
    """简化的 SessionService"""

    def __init__(self):
        self.events = DummyEvents()


@pytest.mark.asyncio
async def test_llm_switch_event_emitted():
    """切换事件能被正确发送"""
    service = ChatService.__new__(ChatService)
    service.session_service = DummySessionService()
    
    probe_result = {
        "primary": {"provider": "claude", "model": "claude-sonnet"},
        "selected": {"provider": "qwen", "model": "qwen-max"},
        "errors": [{"error": "mock"}]
    }
    
    await service._emit_llm_switch_event(
        session_id="sess_test",
        probe_result=probe_result,
        role="simple_agent"
    )
    
    assert len(service.session_service.events.calls) == 1
    call = service.session_service.events.calls[0]
    assert call["event_type"] == "llm_switch"
    assert call["event_data"]["role"] == "simple_agent"
    assert call["event_data"]["from"]["provider"] == "claude"
    assert call["event_data"]["to"]["provider"] == "qwen"
