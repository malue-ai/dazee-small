"""
端到端验证：V9.0 意图识别优化 + 完整架构流程

验证目标：
Phase 0: ChatService 入口
Phase 1: 语义路由决策（IntentAnalyzer 用户问题聚焦过滤 + AgentRouter）
Phase 2: Agent 创建与执行（SimpleAgent/RVRBAgent）
Phase 3: 意图状态转换（追问复用 vs 新意图重置）

真实场景：
1. 用户首次问题 → 新意图 → 创建 plan
2. 用户追问 → 检测追问 → 复用 plan
3. 用户新问题 → 新意图 → 重置 plan
"""

# 1. 标准库
import os
import sys
import asyncio
from pathlib import Path
from typing import Any, Dict, List

# 添加项目根目录到 sys.path
project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 2. 第三方库
import pytest

# 3. 本地模块


def load_env():
    """加载 .env 文件"""
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).resolve().parents[1] / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=True)
            print(f"✅ 加载 .env: {env_path}")
        else:
            print(f"⚠️ .env 不存在: {env_path}")
    except Exception as e:
        # Fallback: 手动解析
        env_path = Path(__file__).resolve().parents[1] / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                raw = line.strip()
                if not raw or raw.startswith("#"):
                    continue
                if "=" not in raw:
                    continue
                key, value = raw.split("=", 1)
                key = key.strip().replace("export ", "")
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)
            print(f"✅ 手动加载 .env: {env_path}")


class DummyEventStorage:
    """最小事件存储实现"""
    
    def __init__(self):
        self._seq = 0
        self._events = []
    
    async def generate_session_seq(self, session_id: str) -> int:
        self._seq += 1
        return self._seq
    
    async def get_session_context(self, session_id: str) -> dict:
        return {
            "conversation_id": "conv_e2e_v9",
            "user_id": "user_test"
        }
    
    async def buffer_event(self, session_id: str, event_data: dict) -> None:
        self._events.append(event_data)
        return None
    
    async def update_heartbeat(self, session_id: str) -> None:
        return None
    
    def get_events(self) -> List[Dict]:
        return self._events


async def verify_phase_1_intent_filtering():
    """Phase 1: 验证意图识别的上下文过滤"""
    print("\n" + "=" * 80)
    print("Phase 1: 意图识别上下文过滤验证")
    print("=" * 80)
    
    from core.routing.intent_analyzer import IntentAnalyzer
    
    # 创建 IntentAnalyzer（无 LLM，仅验证过滤逻辑）
    analyzer = IntentAnalyzer(llm_service=None, enable_llm=False)
    
    # 模拟真实对话历史（含大量工具调用）
    messages = [
        {"role": "user", "content": "query 1"},
        {"role": "assistant", "content": "response 1 " * 100},  # 长回复
        {"role": "user", "content": "query 2"},
        {"role": "assistant", "content": [
            {"type": "tool_use", "name": "web_search", "input": {"query": "xxx"}},
        ]},
        {"role": "assistant", "content": [
            {"type": "tool_result", "content": "search result " * 200},  # 大量工具结果
        ]},
        {"role": "user", "content": "query 3"},
        {"role": "assistant", "content": "response 3"},
        {"role": "user", "content": "query 4"},
    ]
    
    # 执行过滤
    filtered = analyzer._filter_for_intent(messages)
    
    print(f"\n📊 过滤结果:")
    print(f"  原始消息: {len(messages)} 条")
    print(f"  过滤后: {len(filtered)} 条")
    
    user_count = sum(1 for m in filtered if m['role'] == 'user')
    assistant_count = sum(1 for m in filtered if m['role'] == 'assistant')
    print(f"  用户消息: {user_count} 条")
    print(f"  助手消息: {assistant_count} 条")
    
    # 验证最后一条 assistant 被截断
    if assistant_count > 0:
        last_assistant = [m for m in filtered if m['role'] == 'assistant'][-1]
        content = last_assistant['content']
        print(f"  最后助手消息长度: {len(content)} 字符 (应 <= 103)")
        assert len(content) <= 103, "助手消息应被截断为 100 字符 + '...'"
    
    # 验证工具调用被过滤
    has_tool_use = any(
        isinstance(m.get('content'), list) for m in filtered
    )
    assert not has_tool_use, "工具调用应被过滤"
    
    print("\n✅ Phase 1 验证通过: 意图识别上下文过滤正常")


async def verify_phase_2_intent_state_transition():
    """Phase 2: 验证意图状态转换（追问复用 vs 新意图重置）"""
    print("\n" + "=" * 80)
    print("Phase 2: 意图状态转换验证")
    print("=" * 80)
    
    from core.agent.simple.simple_agent import SimpleAgent
    from core.agent.types import IntentResult, TaskType, Complexity
    from core.events import create_event_manager
    
    # 创建 SimpleAgent
    event_manager = create_event_manager(storage=DummyEventStorage())
    agent = SimpleAgent(event_manager=event_manager)
    
    # 场景 1: 新意图 → 创建 plan
    print("\n📋 场景 1: 新意图")
    agent._plan_cache = {"plan": {"steps": ["step1"]}, "todo": None, "tool_calls": []}
    
    intent_new = IntentResult(
        task_type=TaskType.CODE_DEVELOPMENT,
        complexity=Complexity.MEDIUM,
        needs_plan=True,
        is_follow_up=False  # 新意图
    )
    
    agent._handle_intent_transition(intent_new)
    
    # 验证 plan_cache 被重置
    assert agent._plan_cache["plan"] is None, "新意图应重置 plan_cache"
    print("  ✅ plan_cache 已重置")
    
    # 场景 2: 追问 → 复用 plan
    print("\n📋 场景 2: 追问")
    agent._plan_cache = {"plan": {"steps": ["step1"]}, "todo": None, "tool_calls": []}
    agent._last_intent_result = IntentResult(
        task_type=TaskType.CODE_DEVELOPMENT,
        complexity=Complexity.MEDIUM,
        needs_plan=True,
        is_follow_up=False
    )
    
    intent_followup = IntentResult(
        task_type=TaskType.INFORMATION_QUERY,  # 原本识别为信息查询
        complexity=Complexity.SIMPLE,
        needs_plan=False,
        is_follow_up=True  # 追问
    )
    
    agent._handle_intent_transition(intent_followup)
    
    # 验证 plan_cache 被保留，task_type 被继承
    assert agent._plan_cache["plan"] is not None, "追问应保留 plan_cache"
    assert intent_followup.task_type == TaskType.CODE_DEVELOPMENT, "追问应继承上轮 task_type"
    print("  ✅ plan_cache 已复用")
    print(f"  ✅ task_type 继承: {intent_followup.task_type.value}")
    
    print("\n✅ Phase 2 验证通过: 意图状态转换正常")


async def verify_end_to_end_real_query():
    """Phase 3: 端到端集成验证（仅验证架构）"""
    print("\n" + "=" * 80)
    print("Phase 3: 端到端架构集成验证")
    print("=" * 80)
    
    # 加载配置
    load_env()
    
    # 验证 ChatService 和 AgentRouter 可以正常初始化
    print("\n📋 验证组件初始化:")
    
    try:
        from services.chat_service import get_chat_service
        chat_service = get_chat_service()
        print("  ✅ ChatService 初始化成功")
    except Exception as e:
        print(f"  ❌ ChatService 初始化失败: {e}")
        raise
    
    try:
        from core.routing import AgentRouter
        from core.llm import create_llm_service
        
        # 创建 mock LLM（避免真实调用）
        llm = create_llm_service(provider="claude", model="claude-sonnet-4-5", api_key="test")
        router = AgentRouter(llm_service=llm, enable_llm=False)
        print("  ✅ AgentRouter 初始化成功")
    except Exception as e:
        print(f"  ❌ AgentRouter 初始化失败: {e}")
        raise
    
    print("\n📋 验证路由决策流程:")
    
    # 测试路由决策（不调用真实 LLM）
    decision = await router.route(
        user_query="帮我写一个 Python 快速排序函数",
        conversation_history=[]
    )
    
    print(f"  路由决策: agent_type={decision.agent_type}")
    print(f"  执行策略: execution_strategy={decision.execution_strategy}")
    print(f"  意图类型: task_type={decision.intent.task_type.value}")
    print(f"  是否追问: is_follow_up={decision.intent.is_follow_up}")
    print("  ✅ 路由决策流程正常")
    
    print("\n✅ Phase 3 验证通过: 端到端架构集成正常")
    print("\n💡 提示: 完整的 LLM 调用测试需要设置 ANTHROPIC_API_KEY")


@pytest.mark.asyncio
async def test_e2e_v9_intent_optimization():
    """V9.0 意图识别优化端到端验证"""
    print("\n" + "=" * 80)
    print("🚀 V9.0 意图识别优化端到端验证")
    print("=" * 80)
    
    try:
        # Phase 1: 意图识别上下文过滤
        await verify_phase_1_intent_filtering()
        
        # Phase 2: 意图状态转换
        await verify_phase_2_intent_state_transition()
        
        # Phase 3: 真实用户查询（需要 API Key）
        await verify_end_to_end_real_query()
        
        print("\n" + "=" * 80)
        print("✅ 所有验证通过")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ 验证失败: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    """直接运行脚本"""
    asyncio.run(test_e2e_v9_intent_optimization())
