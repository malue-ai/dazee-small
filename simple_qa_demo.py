"""
简单问答场景演示 - 完全独立运行
直接测试 Agent 对话能力
"""

import sys
import os
import asyncio
import time
from pathlib import Path

# 设置路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv(project_root / ".env", override=True)

# 导入项目模块
from core.routing import AgentRouter
from core.llm import create_llm_service
from services.agent_registry import get_agent_registry
from services.chat_service import ChatService


async def test_simple_qa():
    """
    简单问答场景测试
    
    场景：用户问"什么是RAG技术？"
    验证：Agent 能够准确回答技术问题
    """
    print("=" * 80)
    print("【简单问答场景测试】")
    print("=" * 80)
    
    # 1. 检查 API Key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ 缺少 ANTHROPIC_API_KEY")
        return False
    
    print(f"✅ API Key 已配置: {api_key[:20]}...")
    
    # 2. 测试查询
    query = "什么是RAG技术？它和传统搜索有什么区别？"
    print(f"\n📝 用户问题: {query}")
    
    # 3. 意图识别测试
    print("\n" + "-" * 80)
    print("阶段 1: 意图识别")
    print("-" * 80)
    
    try:
        intent_start = time.time()
        llm = create_llm_service(
            provider="claude",
            model="claude-3-5-haiku-20241022",
            api_key=api_key,
            enable_thinking=False,
            max_tokens=1024
        )
        router = AgentRouter(llm_service=llm, enable_llm=True)
        
        decision = await router.route(
            user_query=query,
            conversation_history=[]
        )
        
        intent_time = (time.time() - intent_start) * 1000
        
        intent_id = getattr(decision.intent, 'intent_id', 3) if hasattr(decision, 'intent') else 3
        complexity = str(getattr(decision.intent, 'complexity', 'simple')) if hasattr(decision, 'intent') else 'simple'
        
        print(f"✅ 意图识别完成:")
        print(f"   Intent ID: {intent_id}")
        print(f"   复杂度: {complexity}")
        print(f"   耗时: {intent_time:.2f}ms")
        
    except Exception as e:
        print(f"❌ 意图识别失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 4. Agent 执行测试
    print("\n" + "-" * 80)
    print("阶段 2: Agent 回答")
    print("-" * 80)
    
    try:
        # 预加载 test_agent
        registry = get_agent_registry()
        await registry.preload_instance("test_agent")
        print("✅ Agent 已加载")
        
        # 创建 ChatService
        chat_service = ChatService(enable_routing=True)
        
        # 生成测试 user_id
        test_user_id = f"test_user_{int(time.time())}"
        
        # 执行对话
        exec_start = time.time()
        full_response = ""
        token_usage = {"input_tokens": 0, "output_tokens": 0}
        
        print("🤖 Agent 回答中...")
        async for event in chat_service.chat(
            message=query,
            user_id=test_user_id,
            stream=True,
            agent_id="test_agent"
        ):
            event_type = event.get("type", "")
            
            if event_type == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    full_response += text
                    # 实时显示（每100字符一个点）
                    if len(full_response) % 100 == 0:
                        print(".", end="", flush=True)
            
            elif event_type == "message_stop":
                usage = event.get("usage", {})
                token_usage["input_tokens"] = usage.get("input_tokens", 0)
                token_usage["output_tokens"] = usage.get("output_tokens", 0)
        
        exec_time = (time.time() - exec_start) * 1000
        
        print(f"\n\n✅ 回答完成:")
        print(f"   耗时: {exec_time:.2f}ms")
        print(f"   Token: input={token_usage['input_tokens']}, output={token_usage['output_tokens']}")
        
    except Exception as e:
        print(f"\n❌ Agent 执行失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 5. 输出结果
    print("\n" + "=" * 80)
    print("📄 Agent 回答")
    print("=" * 80)
    print(full_response)
    print("=" * 80)
    
    # 6. 简单质量评估
    print("\n📊 质量评估:")
    
    # 检查关键词
    keywords = ["RAG", "检索", "生成", "增强", "Retrieval", "Generation"]
    matched = [kw for kw in keywords if kw in full_response]
    
    if len(matched) >= 3:
        print(f"✅ 包含关键概念: {', '.join(matched)}")
        quality_pass = True
    else:
        print(f"⚠️ 关键概念不足: {', '.join(matched)}")
        quality_pass = False
    
    # 检查长度
    if len(full_response) > 100:
        print(f"✅ 回答长度合理: {len(full_response)} 字符")
    else:
        print(f"⚠️ 回答过短: {len(full_response)} 字符")
        quality_pass = False
    
    # 总结
    print("\n" + "=" * 80)
    if quality_pass:
        print("✅ 测试通过 - Agent 能够准确回答技术问题")
    else:
        print("⚠️ 测试需要改进 - 回答质量有待提升")
    print("=" * 80)
    
    return quality_pass


if __name__ == "__main__":
    success = asyncio.run(test_simple_qa())
    sys.exit(0 if success else 1)
