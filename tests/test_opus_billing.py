"""
Opus 模型计费验证测试

验证 claude-opus-4.5 的计费逻辑是否正确
"""

import pytest
from core.billing import EnhancedUsageTracker, UsageResponse, calculate_cost
from core.billing.pricing import get_pricing_for_model


def test_opus_pricing_table():
    """测试 Opus 定价表配置"""
    print("\n======================================================================")
    print("🧪 Opus 定价表验证")
    print("======================================================================")
    
    # 获取 Opus 定价
    opus_pricing = get_pricing_for_model("claude-opus-4.5")
    
    print("\n📊 Claude Opus 4.5 定价：")
    print(f"   • Input: ${opus_pricing['input']}/M tokens")
    print(f"   • Output: ${opus_pricing['output']}/M tokens")
    print(f"   • Cache Write: ${opus_pricing['cache_write']}/M tokens")
    print(f"   • Cache Read: ${opus_pricing['cache_read']}/M tokens")
    
    # 验证定价
    assert opus_pricing['input'] == 5.0, "Opus input 价格应为 $5.0/M"
    assert opus_pricing['output'] == 25.0, "Opus output 价格应为 $25.0/M"
    assert opus_pricing['cache_write'] == 6.25, "Opus cache_write 价格应为 $6.25/M"
    assert opus_pricing['cache_read'] == 0.5, "Opus cache_read 价格应为 $0.5/M"
    
    print("\n✅ Opus 定价表验证通过")


def test_opus_cost_calculation():
    """测试 Opus 成本计算"""
    print("\n======================================================================")
    print("🧪 Opus 成本计算验证")
    print("======================================================================")
    
    # 场景：Lead Agent 使用 Opus 进行复杂规划
    input_tokens = 500
    output_tokens = 200
    thinking_tokens = 150
    
    print(f"\n📍 测试场景：Lead Agent 复杂规划")
    print(f"   • Input tokens: {input_tokens:,}")
    print(f"   • Output tokens: {output_tokens:,}")
    print(f"   • Thinking tokens: {thinking_tokens:,}")
    
    # 计算成本
    total_cost, details = calculate_cost(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        thinking_tokens=thinking_tokens,
        model="claude-opus-4.5"
    )
    
    print(f"\n💰 成本明细：")
    print(f"   • Input cost: ${details['input_cost']:.6f}")
    print(f"   • Output cost: ${details['output_cost']:.6f}")
    print(f"   • Thinking cost: ${details['thinking_cost']:.6f}")
    print(f"   • Total cost: ${total_cost:.6f}")
    
    # 验证计算（手动计算验证）
    expected_input = (500 / 1_000_000) * 5.0  # 0.0025
    expected_output = (200 / 1_000_000) * 25.0  # 0.005
    expected_thinking = (150 / 1_000_000) * 25.0  # 0.00375
    expected_total = expected_input + expected_output + expected_thinking  # 0.01125
    
    assert abs(details['input_cost'] - expected_input) < 0.000001
    assert abs(details['output_cost'] - expected_output) < 0.000001
    assert abs(details['thinking_cost'] - expected_thinking) < 0.000001
    assert abs(total_cost - expected_total) < 0.000001
    
    print(f"\n✅ 成本计算验证通过（总成本: ${total_cost:.6f}）")


def test_multi_model_opus_sonnet():
    """测试多模型场景（Opus + Sonnet）"""
    print("\n======================================================================")
    print("🧪 多智能体场景：Opus (Lead) + Sonnet (Worker)")
    print("======================================================================")
    
    tracker = EnhancedUsageTracker()
    
    # 模拟 Lead Agent 调用（Opus）
    class MockOpusResponse:
        usage = {
            "input_tokens": 500,
            "output_tokens": 200,
            "thinking_tokens": 150,
            "total_tokens": 850
        }
    
    opus_record = tracker.record_call(
        llm_response=MockOpusResponse(),
        model="claude-opus-4.5",
        purpose="orchestrator_planning",
        latency_ms=3000
    )
    
    print(f"\n📍 Lead Agent (Opus):")
    print(f"   • call_id: {opus_record.call_id}")
    print(f"   • input_tokens: {opus_record.input_tokens:,}")
    print(f"   • output_tokens: {opus_record.output_tokens:,}")
    print(f"   • thinking_tokens: {opus_record.thinking_tokens:,}")
    print(f"   • input_unit_price: ${opus_record.input_unit_price}/M")
    print(f"   • output_unit_price: ${opus_record.output_unit_price}/M")
    print(f"   • total_price: ${opus_record.total_price:.6f}")
    
    # 模拟 Worker 调用（Sonnet）
    class MockSonnetResponse:
        usage = {
            "input_tokens": 300,
            "output_tokens": 400,
            "thinking_tokens": 50,
            "total_tokens": 750
        }
    
    sonnet_record = tracker.record_call(
        llm_response=MockSonnetResponse(),
        model="claude-sonnet-4.5",
        purpose="worker_task",
        latency_ms=2500
    )
    
    print(f"\n📍 Worker Agent (Sonnet):")
    print(f"   • call_id: {sonnet_record.call_id}")
    print(f"   • input_tokens: {sonnet_record.input_tokens:,}")
    print(f"   • output_tokens: {sonnet_record.output_tokens:,}")
    print(f"   • thinking_tokens: {sonnet_record.thinking_tokens:,}")
    print(f"   • input_unit_price: ${sonnet_record.input_unit_price}/M")
    print(f"   • output_unit_price: ${sonnet_record.output_unit_price}/M")
    print(f"   • total_price: ${sonnet_record.total_price:.6f}")
    
    # 生成最终响应
    usage = UsageResponse.from_tracker(tracker, latency=5.5)
    
    print(f"\n📊 累积统计:")
    print(f"   • total_tokens: {usage.total_tokens:,}")
    print(f"   • total_price: ${usage.total_price:.6f}")
    print(f"   • llm_calls: {usage.llm_calls}")
    print(f"   • prompt_unit_price: ${usage.prompt_unit_price:.2f}/M (加权平均)")
    print(f"   • completion_unit_price: ${usage.completion_unit_price:.2f}/M (加权平均)")
    
    # 验证
    assert usage.llm_calls == 2
    assert usage.total_tokens == 1600  # 850 + 750
    assert len(usage.llm_call_details) == 2
    assert usage.llm_call_details[0].model == "claude-opus-4.5"
    assert usage.llm_call_details[1].model == "claude-sonnet-4.5"
    
    # 验证成本（Opus 应该占大头）
    opus_cost = opus_record.total_price
    sonnet_cost = sonnet_record.total_price
    assert opus_cost > sonnet_cost, "Opus 成本应该高于 Sonnet"
    
    opus_ratio = opus_cost / usage.total_price
    print(f"\n💰 成本分析:")
    print(f"   • Opus 成本: ${opus_cost:.6f} ({opus_ratio*100:.1f}%)")
    print(f"   • Sonnet 成本: ${sonnet_cost:.6f} ({(1-opus_ratio)*100:.1f}%)")
    
    print("\n✅ 多模型场景验证通过")
    print("======================================================================")


def test_opus_model_name_variants():
    """测试 Opus 模型名称变体的定价匹配"""
    print("\n======================================================================")
    print("🧪 Opus 模型名称变体匹配")
    print("======================================================================")
    
    # 测试不同的模型名称变体
    variants = [
        "claude-opus-4.5",
        "claude-opus-4-5-20251101",
        "Claude-Opus-4.5",  # 大小写
    ]
    
    for variant in variants:
        pricing = get_pricing_for_model(variant)
        print(f"\n   • {variant:30s} → ${pricing['input']}/M input, ${pricing['output']}/M output")
        
        # 验证所有变体都能匹配到正确的定价
        assert pricing['input'] == 5.0, f"{variant} 应匹配 Opus 定价"
        assert pricing['output'] == 25.0, f"{variant} 应匹配 Opus 定价"
    
    print("\n✅ 模型名称变体匹配通过")
    print("======================================================================")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
