"""
测试多轮对话机制

验证 Agent 的会话级多轮对话功能：
1. start_session() / end_session()
2. chat() 多轮对话
3. 消息历史累积
4. 上下文保持
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from  import create_simple_agent


async def test_multi_turn_basic():
    """测试基础多轮对话"""
    print("="*60)
    print("测试 1: 基础多轮对话")
    print("="*60)
    
    agent = create_simple_agent(verbose=True)
    
    # 自动开始会话
    print("\n📝 Turn 1: 简单问候")
    result1 = await agent.chat("你好，请记住我叫小明")
    print(f"✅ Response: {result1.get('content', result1.get('final_result', ''))[:100]}...")
    
    # 检查会话状态
    session_info = agent.get_session_info()
    print(f"\n📊 Session Info:")
    print(f"   Session ID: {session_info['session_id']}")
    print(f"   Turns: {session_info['turns']}")
    print(f"   Messages: {session_info['message_count']}")
    
    # 第二轮（应该记住上下文）
    print("\n📝 Turn 2: 测试上下文记忆")
    result2 = await agent.chat("我叫什么名字？")
    response2 = result2.get('content', result2.get('final_result', ''))
    print(f"✅ Response: {response2[:200]}...")
    
    # 验证上下文记忆
    if "小明" in str(response2):
        print("\n✅ 上下文记忆验证通过！Agent 记住了用户名字")
    else:
        print("\n⚠️  上下文记忆可能未生效")
    
    # 检查对话历史
    history = agent.get_conversation_history()
    print(f"\n📜 Conversation History: {len(history)} messages")
    for i, msg in enumerate(history):
        role = msg.get('role', 'unknown')
        content = str(msg.get('content', ''))[:50]
        print(f"   [{i+1}] {role}: {content}...")
    
    # 结束会话
    summary = agent.end_session()
    print(f"\n🔚 Session ended:")
    print(f"   Total turns: {summary['turns']}")
    print(f"   Total messages: {summary['message_count']}")
    
    return True


async def test_session_lifecycle():
    """测试会话生命周期"""
    print("\n" + "="*60)
    print("测试 2: 会话生命周期")
    print("="*60)
    
    agent = create_simple_agent(verbose=False)
    
    # 手动开始会话
    session_id = agent.start_session()
    print(f"✅ Session started: {session_id}")
    
    # 检查会话状态
    info = agent.get_session_info()
    assert info['active'] == True, "Session should be active"
    assert info['session_id'] == session_id, "Session ID mismatch"
    print(f"✅ Session active: {info['active']}")
    
    # 发送一条消息
    result = await agent.chat("1+1=?")
    print(f"✅ Chat response received")
    
    info = agent.get_session_info()
    assert info['turns'] == 1, "Should have 1 turn"
    print(f"✅ Turns count: {info['turns']}")
    
    # 结束会话
    summary = agent.end_session()
    assert summary['session_id'] == session_id, "Session ID should match"
    print(f"✅ Session ended properly")
    
    # 验证会话已结束
    info = agent.get_session_info()
    assert info['active'] == False, "Session should not be active"
    print(f"✅ Session inactive after end")
    
    return True


async def test_auto_session():
    """测试自动会话管理"""
    print("\n" + "="*60)
    print("测试 3: 自动会话管理")
    print("="*60)
    
    agent = create_simple_agent(verbose=False)
    
    # 不调用 start_session，直接 chat
    info_before = agent.get_session_info()
    assert info_before['active'] == False, "Should not have active session initially"
    print(f"✅ No active session before chat")
    
    # chat 应该自动开始会话
    result = await agent.chat("Hello")
    
    info_after = agent.get_session_info()
    assert info_after['active'] == True, "Should have active session after chat"
    print(f"✅ Session auto-started by chat()")
    
    # 清理
    agent.end_session()
    print(f"✅ Session ended")
    
    return True


async def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("🧪 多轮对话机制测试")
    print("="*60 + "\n")
    
    try:
        # 测试 1: 基础多轮对话
        await test_multi_turn_basic()
        
        # 测试 2: 会话生命周期
        await test_session_lifecycle()
        
        # 测试 3: 自动会话管理
        await test_auto_session()
        
        print("\n" + "="*60)
        print("✅ 所有测试通过!")
        print("="*60)
        
        print("\n多轮对话 API 使用示例：")
        print("""
agent = create_simple_agent()

# 方式 1: 自动会话管理
result1 = await agent.chat("你好")
result2 = await agent.chat("继续上一个话题...")
agent.end_session()

# 方式 2: 手动会话管理
agent.start_session(session_id="my_session")
result = await agent.chat("...")
history = agent.get_conversation_history()
agent.end_session()
        """)
        
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

