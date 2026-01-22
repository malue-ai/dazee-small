"""
Usage Tracking 端到端测试

真正的 E2E 测试：直接调用 LLM 服务，验证 UsageResponse 返回
（跳过 Agent/ChatService 层，最轻量级验证）
"""

import asyncio
import logging
import os
import sys
import time

# 确保项目路径在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_llm_with_usage():
    """
    测试 LLM 调用并验证 usage 返回
    
    流程：
    1. 创建 LLM 服务
    2. 发送简单问题
    3. 验证 response.usage
    4. 测试 UsageTracker 累积
    5. 测试 UsageResponse 构建
    """
    from core.llm import create_claude_service
    from core.llm.base import Message
    from utils.usage_tracker import UsageTracker
    from models.usage import UsageResponse
    
    print("\n" + "="*60)
    print("🧪 E2E Usage Tracking 测试 (直接 LLM 调用)")
    print("="*60)
    
    # 1. 创建 LLM 服务
    llm_service = create_claude_service()
    print(f"✅ LLM 服务: {llm_service.config.model}")
    
    # 2. 创建 UsageTracker
    usage_tracker = UsageTracker()
    
    # 3. 简单问题（使用 Message 对象）
    test_message = "你好，请用一句话介绍自己。"
    messages = [Message(role="user", content=test_message)]
    
    print(f"\n📤 发送消息: {test_message}")
    
    # 4. 调用 LLM
    start_time = time.time()
    full_response = ""
    
    try:
        async for chunk in llm_service.create_message_stream(messages=messages):
            # chunk 是 LLMResponse 对象
            if chunk.content:
                full_response += chunk.content
            
            # 累积 usage（只累积最后一个有 usage 的 chunk）
            if chunk.usage:
                usage_tracker.accumulate(chunk)
                print(f"   📊 收到 usage: input={chunk.usage.get('input_tokens', 0)}, output={chunk.usage.get('output_tokens', 0)}")
    
    except Exception as e:
        logger.error(f"❌ LLM 调用失败: {e}", exc_info=True)
        raise
    
    duration = time.time() - start_time
    
    # 5. 获取 usage 统计
    usage_stats = usage_tracker.get_stats()
    cost_estimate = usage_tracker.get_cost_estimate()
    
    # 6. 构建 UsageResponse
    usage_response = UsageResponse.from_tracker(
        tracker=usage_tracker,
        latency=duration
    )
    
    # 7. 输出结果
    print("\n" + "-"*60)
    print("📊 测试结果")
    print("-"*60)
    
    print(f"\n📝 AI 响应 ({len(full_response)} 字符):")
    print(f"   {full_response[:300]}{'...' if len(full_response) > 300 else ''}")
    
    print(f"\n⏱️ 耗时: {duration:.2f}s")
    
    print("\n💰 UsageTracker 原始统计:")
    for key, value in usage_stats.items():
        if isinstance(value, int):
            print(f"   • {key}: {value:,}")
        else:
            print(f"   • {key}: {value}")
    print(f"   • estimated_cost: ${cost_estimate:.6f}")
    
    print("\n📊 UsageResponse (Dify 兼容格式):")
    print(f"   • prompt_tokens: {usage_response.prompt_tokens:,}")
    print(f"   • completion_tokens: {usage_response.completion_tokens:,}")
    print(f"   • thinking_tokens: {usage_response.thinking_tokens:,}")
    print(f"   • cache_read_tokens: {usage_response.cache_read_tokens:,}")
    print(f"   • cache_write_tokens: {usage_response.cache_write_tokens:,}")
    print(f"   • total_tokens: {usage_response.total_tokens:,}")
    print(f"   • prompt_price: ${usage_response.prompt_price}")
    print(f"   • completion_price: ${usage_response.completion_price}")
    print(f"   • total_price: ${usage_response.total_price}")
    print(f"   • prompt_unit_price: ${usage_response.prompt_unit_price}/M tokens")
    print(f"   • completion_unit_price: ${usage_response.completion_unit_price}/M tokens")
    print(f"   • latency: {usage_response.latency:.2f}s")
    print(f"   • llm_calls: {usage_response.llm_calls}")
    print(f"   • model: {usage_response.model}")
    print(f"   • currency: {usage_response.currency}")
    
    # 8. 验证关键字段
    print("\n🔍 验证检查:")
    
    checks = [
        ("prompt_tokens > 0", usage_response.prompt_tokens > 0),
        ("completion_tokens > 0", usage_response.completion_tokens > 0),
        ("total_tokens > 0", usage_response.total_tokens > 0),
        ("total_price > 0", float(usage_response.total_price) > 0),
        ("llm_calls >= 1", usage_response.llm_calls >= 1),
        ("latency > 0", usage_response.latency > 0),
        ("model 非空", bool(usage_response.model)),
    ]
    
    all_passed = True
    for check_name, result in checks:
        status = "✅" if result else "❌"
        print(f"   {status} {check_name}")
        if not result:
            all_passed = False
    
    if not all_passed:
        raise AssertionError("部分验证失败")
    
    print("\n✅ 所有验证通过!")
    
    print("\n" + "="*60)
    print("🎉 E2E 测试完成!")
    print("="*60)
    
    # 9. 返回完整的 usage 数据（类似 SSE usage 事件）
    return {
        "event": "usage",
        "data": usage_response.model_dump()
    }


async def main():
    """运行测试"""
    try:
        usage_event = await test_llm_with_usage()
        
        if usage_event:
            print("\n✅ 测试成功: Usage 正确返回")
            # 打印最终 JSON（可用于 API 响应）
            import json
            print("\n📋 最终 usage 事件 (JSON):")
            print(json.dumps(usage_event["data"], indent=2, ensure_ascii=False))
            return 0
        else:
            print("\n⚠️ 测试警告: 未生成 usage")
            return 1
            
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
