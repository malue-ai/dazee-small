"""
多模型调用计费 E2E 测试

测试场景：意图识别（Haiku）+ 主对话（Sonnet）

关键验证点：
1. ✅ 每次调用单独记录（模型、tokens、价格）
2. ✅ Message ID 去重（避免重复计费）
3. ✅ 价格字段全部使用 float 类型
4. ✅ 累积统计正确
5. ✅ 返回的 JSON 格式符合规范
"""

import asyncio
import logging
import os
import sys
import time
from uuid import uuid4

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


async def test_multi_model_billing():
    """
    E2E 测试：多模型调用计费
    
    场景：
    1. 意图识别：Claude Haiku ($1/M input, $5/M output)
    2. 主对话：Claude Sonnet ($3/M input, $15/M output)
    
    验证：
    - 每次调用单独记录
    - 价格计算正确
    - 所有字段类型正确（int/float）
    - 累积统计正确
    """
    from core.billing import EnhancedUsageTracker, UsageResponse, calculate_cost
    from core.llm import create_claude_service
    from core.llm.base import Message
    
    print("\n" + "="*70)
    print("🧪 多模型调用计费 E2E 测试")
    print("="*70)
    
    # 创建 tracker
    tracker = EnhancedUsageTracker()
    
    # ========== 场景 1：意图识别（Haiku）==========
    print("\n📍 场景 1：意图识别（Claude Haiku）")
    
    # 使用真正的 Haiku 模型（Haiku 也支持 Extended Thinking）
    haiku_llm = create_claude_service(model="claude-haiku-4-5-20251001")
    intent_message = "用一个词回答：这是什么类型的问题？"
    messages = [Message(role="user", content=intent_message)]
    
    intent_start = time.time()
    intent_response_text = ""
    intent_usage = None
    
    # max_tokens 必须大于 thinking_budget (10000)
    async for chunk in haiku_llm.create_message_stream(messages=messages, max_tokens=15000):
        if chunk.content:
            intent_response_text += chunk.content
        if chunk.usage:
            intent_usage = chunk
    
    intent_latency = int((time.time() - intent_start) * 1000)
    
    # 记录意图识别调用（Haiku：$1/M input, $5/M output）
    intent_model = "claude-haiku-4.5"
    intent_record = tracker.record_call(
        llm_response=intent_usage,
        model=intent_model,
        purpose="intent_analysis",
        latency_ms=intent_latency,
        message_id=f"intent_{uuid4().hex[:8]}"
    )
    
    assert intent_record is not None, "意图识别记录不应为 None"
    print(f"✅ 意图识别调用已记录: call_id={intent_record.call_id}")
    print(f"   • model: {intent_record.model}")
    print(f"   • input_tokens: {intent_record.input_tokens}")
    print(f"   • output_tokens: {intent_record.output_tokens}")
    print(f"   • thinking_tokens: {intent_record.thinking_tokens}")
    print(f"   • input_unit_price: {intent_record.input_unit_price} USD/M")
    print(f"   • output_unit_price: {intent_record.output_unit_price} USD/M")
    print(f"   • total_price: {intent_record.total_price} USD")
    
    # 验证类型
    assert isinstance(intent_record.input_tokens, int), "input_tokens 应该是 int"
    assert isinstance(intent_record.output_tokens, int), "output_tokens 应该是 int"
    assert isinstance(intent_record.input_unit_price, float), "input_unit_price 应该是 float"
    assert isinstance(intent_record.output_unit_price, float), "output_unit_price 应该是 float"
    assert isinstance(intent_record.input_total_price, float), "input_total_price 应该是 float"
    assert isinstance(intent_record.output_total_price, float), "output_total_price 应该是 float"
    assert isinstance(intent_record.total_price, float), "total_price 应该是 float"
    
    # 验证价格计算（包含 thinking tokens）
    expected_total, details = calculate_cost(
        input_tokens=intent_record.input_tokens,
        output_tokens=intent_record.output_tokens,
        thinking_tokens=intent_record.thinking_tokens,
        model=intent_model
    )
    assert abs(intent_record.total_price - expected_total) < 0.000001, \
        f"价格计算错误: {intent_record.total_price} != {expected_total}"
    
    print(f"✅ 价格验证通过")
    
    # ========== 场景 2：主对话（Sonnet）==========
    print("\n📍 场景 2：主对话（Claude Sonnet）")
    
    sonnet_llm = create_claude_service(model="claude-sonnet-4-5-20250929")
    main_message = "你好，请用一句话介绍自己。"
    messages = [Message(role="user", content=main_message)]
    
    main_start = time.time()
    main_response_text = ""
    main_usage = None
    
    async for chunk in sonnet_llm.create_message_stream(messages=messages, max_tokens=15000):
        if chunk.content:
            main_response_text += chunk.content
        if chunk.usage:
            main_usage = chunk
    
    main_latency = int((time.time() - main_start) * 1000)
    
    # 记录主对话调用
    main_record = tracker.record_call(
        llm_response=main_usage,
        model="claude-sonnet-4.5",  # 简化模型名
        purpose="main_response",
        latency_ms=main_latency,
        message_id=f"main_{uuid4().hex[:8]}"
    )
    
    assert main_record is not None, "主对话记录不应为 None"
    print(f"✅ 主对话调用已记录: call_id={main_record.call_id}")
    print(f"   • model: {main_record.model}")
    print(f"   • input_tokens: {main_record.input_tokens}")
    print(f"   • output_tokens: {main_record.output_tokens}")
    print(f"   • thinking_tokens: {main_record.thinking_tokens}")
    print(f"   • input_unit_price: {main_record.input_unit_price} USD/M")
    print(f"   • output_unit_price: {main_record.output_unit_price} USD/M")
    print(f"   • total_price: {main_record.total_price} USD")
    
    # 验证类型
    assert isinstance(main_record.thinking_tokens, int), "thinking_tokens 应该是 int"
    
    # ========== 场景 3：重复调用去重测试 ==========
    print("\n📍 场景 3：Message ID 去重测试")
    
    # 使用相同的 message_id 再次调用
    duplicate_record = tracker.record_call(
        llm_response=main_usage,
        model="claude-sonnet-4.5",
        purpose="main_response_duplicate",
        message_id=main_record.message_id  # 使用相同的 message_id
    )
    
    assert duplicate_record is None, "重复的 message_id 应该被去重，返回 None"
    print(f"✅ Message ID 去重测试通过")
    
    # ========== 场景 4：生成最终响应 ==========
    print("\n📍 场景 4：生成最终 UsageResponse")
    
    total_latency = (intent_latency + main_latency) / 1000.0
    usage_response = UsageResponse.from_tracker(tracker, latency=total_latency)
    
    print("\n📊 累积统计：")
    print(f"   • prompt_tokens: {usage_response.prompt_tokens:,}")
    print(f"   • completion_tokens: {usage_response.completion_tokens:,}")
    print(f"   • thinking_tokens: {usage_response.thinking_tokens:,}")
    print(f"   • total_tokens: {usage_response.total_tokens:,}")
    print(f"   • prompt_price: {usage_response.prompt_price} USD")
    print(f"   • completion_price: {usage_response.completion_price} USD")
    print(f"   • total_price: {usage_response.total_price} USD")
    print(f"   • prompt_unit_price: {usage_response.prompt_unit_price} USD/M")
    print(f"   • completion_unit_price: {usage_response.completion_unit_price} USD/M")
    print(f"   • llm_calls: {usage_response.llm_calls}")
    print(f"   • latency: {usage_response.latency:.2f}s")
    
    # 验证累积统计
    assert usage_response.llm_calls == 2, f"应该有 2 次调用，实际: {usage_response.llm_calls}"
    assert usage_response.prompt_tokens == intent_record.input_tokens + main_record.input_tokens
    assert usage_response.completion_tokens == intent_record.output_tokens + main_record.output_tokens
    
    # 验证类型
    assert isinstance(usage_response.prompt_tokens, int), "prompt_tokens 应该是 int"
    assert isinstance(usage_response.prompt_price, float), "prompt_price 应该是 float"
    assert isinstance(usage_response.total_price, float), "total_price 应该是 float"
    assert isinstance(usage_response.prompt_unit_price, float), "prompt_unit_price 应该是 float"
    
    # ========== 场景 5：验证调用明细 ==========
    print("\n📍 场景 5：验证调用明细")
    
    assert len(usage_response.llm_call_details) == 2, "应该有 2 条调用明细"
    
    detail_1 = usage_response.llm_call_details[0]
    detail_2 = usage_response.llm_call_details[1]
    
    assert detail_1.model == "claude-haiku-4.5", "第一条应该是 Haiku（意图识别）"
    assert detail_1.purpose == "intent_analysis"
    assert detail_2.model == "claude-sonnet-4.5", "第二条应该是 Sonnet（主对话）"
    assert detail_2.purpose == "main_response"
    
    print(f"✅ 调用明细验证通过")
    print(f"   • 调用 1: {detail_1.model} ({detail_1.purpose})")
    print(f"   • 调用 2: {detail_2.model} ({detail_2.purpose})")
    
    # ========== 场景 6：JSON 格式验证 ==========
    print("\n📍 场景 6：JSON 格式验证")
    
    import json
    # 使用 mode='json' 确保 datetime 等类型被正确序列化
    usage_json = usage_response.model_dump(mode='json')
    json_str = json.dumps(usage_json, ensure_ascii=False, indent=2)
    
    print("\n📋 最终 JSON 输出（部分）:")
    # 只显示关键字段
    compact_json = {
        "total_price": usage_json["total_price"],
        "currency": usage_json["currency"],
        "llm_calls": usage_json["llm_calls"],
        "llm_call_details": [
            {
                "call_id": call["call_id"],
                "model": call["model"],
                "purpose": call["purpose"],
                "input_tokens": call["input_tokens"],
                "output_tokens": call["output_tokens"],
                "input_unit_price": call["input_unit_price"],
                "output_unit_price": call["output_unit_price"],
                "total_price": call["total_price"]
            }
            for call in usage_json["llm_call_details"]
        ]
    }
    print(json.dumps(compact_json, ensure_ascii=False, indent=2))
    
    # 验证所有价格字段都是数字类型
    assert isinstance(usage_json["total_price"], (int, float)), "total_price 必须是数字"
    assert isinstance(usage_json["prompt_price"], (int, float)), "prompt_price 必须是数字"
    
    for call in usage_json["llm_call_details"]:
        assert isinstance(call["input_unit_price"], (int, float)), "input_unit_price 必须是数字"
        assert isinstance(call["output_unit_price"], (int, float)), "output_unit_price 必须是数字"
        assert isinstance(call["input_total_price"], (int, float)), "input_total_price 必须是数字"
        assert isinstance(call["output_total_price"], (int, float)), "output_total_price 必须是数字"
        assert isinstance(call["total_price"], (int, float)), "total_price 必须是数字"
    
    print(f"\n✅ JSON 格式验证通过（所有价格字段都是数字类型）")
    
    # ========== 最终总结 ==========
    print("\n" + "="*70)
    print("🎉 所有测试通过！")
    print("="*70)
    print(f"\n✅ 多模型调用记录正确")
    print(f"✅ Message ID 去重正常工作")
    print(f"✅ 价格计算准确")
    print(f"✅ 所有价格字段使用 float 类型")
    print(f"✅ 累积统计正确")
    print(f"✅ JSON 格式符合规范")
    print(f"\n💰 总成本: ${usage_response.total_price:.6f} USD")
    print(f"⏱️ 总延迟: {usage_response.latency:.2f}s")
    print(f"📞 LLM 调用次数: {usage_response.llm_calls}")
    
    return usage_response


async def main():
    """运行测试"""
    try:
        usage_response = await test_multi_model_billing()
        print("\n✅ E2E 测试成功！")
        return 0
    except Exception as e:
        print(f"\n❌ E2E 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
