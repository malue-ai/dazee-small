"""
调试：Agent中Router到底返回了什么工具
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core import create_simple_agent, create_event_manager
from core.tool.selector import ToolSelector

# 简单EventStorage
class SimpleEventStorage:
    def __init__(self):
        self.events = {}
        self.seq_counters = {}
        self.contexts = {}
    def generate_session_seq(self, session_id: str) -> int:
        if session_id not in self.seq_counters:
            self.seq_counters[session_id] = 0
        self.seq_counters[session_id] += 1
        return self.seq_counters[session_id]
    def get_session_context(self, session_id: str) -> dict:
        return self.contexts.get(session_id, {})
    def buffer_event(self, session_id: str, event_data: dict) -> None:
        if session_id not in self.events:
            self.events[session_id] = []
        self.events[session_id].append(event_data)
    def update_heartbeat(self, session_id: str) -> None:
        pass

def test_agent_router_debug_tools():
    """测试 Router 与 ToolSelector 基本行为"""
    storage = SimpleEventStorage()
    event_manager = create_event_manager(storage)
    agent = create_simple_agent(workspace_dir="/tmp", event_manager=event_manager)

    if not agent.tool_selector:
        pytest.skip("ToolSelector 未启用，跳过调试测试")

    print("=" * 70)
    print("Agent创建成功，现在测试Router")
    print("=" * 70)

    required_capabilities = [
        "code_execution",
        "code_sandbox",
        "app_generation",
        "file_operations",
        "task_planning",
    ]
    available_apis = agent.tool_selector.get_available_apis(agent.tool_executor)
    print(f"🔍 自动发现API: {available_apis}")

    context = {
        "plan": None,
        "task_type": "code_task",
        "available_apis": available_apis,
    }

    print(f"\n需要能力: {required_capabilities}")
    print("调用 ToolSelector.select()...")

    selector = ToolSelector(agent.capability_registry)
    result = selector.select(required_capabilities, context=context)

    print(f"\nToolSelector 返回工具数量: {len(result.tools)}")
    for t in result.tools:
        print(f"  - {t.name} (type={t.type.value}, capabilities={t.capabilities})")

    assert isinstance(result.tools, list)

