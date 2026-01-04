"""
调试：Agent中Router到底返回了什么工具
"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ['E2B_API_KEY'] = 'e2b_83eb67de2fb85d4a8a87ddfe6fca5a89e9f7cc95'

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

# 创建Agent
storage = SimpleEventStorage()
event_manager = create_event_manager(storage)
agent = create_simple_agent(workspace_dir="/tmp", event_manager=event_manager)

print("="*70)
print("Agent创建成功，现在测试Router")
print("="*70)

# 模拟Agent内部的Router调用
required_capabilities = ['code_execution', 'code_sandbox', 'app_generation', 'file_operations', 'task_planning']
# 🆕 使用Agent的自动API发现机制
available_apis = agent._get_available_apis()
print(f"🔍 自动发现API: {available_apis}")

context = {
    "plan": None, 
    "task_type": "code_task",
    "available_apis": available_apis  # 🆕 自动发现，不硬编码
}

print(f"\n需要能力: {required_capabilities}")
print(f"调用 ToolSelector.select()...")

# 使用 ToolSelector 替代已废弃的 select_tools_for_capabilities
selector = ToolSelector(agent.capability_registry)
result = selector.select(required_capabilities, context=context)

print(f"\nToolSelector 返回工具数量: {len(result.tools)}")
for t in result.tools:
    print(f"  - {t.name} (type={t.type.value}, capabilities={t.capabilities})")

print("\n✅ E2B工具在列表中:", any('e2b' in name for name in result.tool_names))

