"""
缓存计费 E2E 测试

测试场景：
1. 缓存命中（cache_read_tokens > 0）
2. 缓存写入（cache_creation_tokens > 0）
3. 混合场景（同时有缓存读写）

关键验证点：
1. ✅ cache_read_tokens 正确累积
2. ✅ cache_creation_tokens 正确累积  
3. ✅ 缓存价格计算正确（每个模型独立价格）
4. ✅ prompt_tokens = input_tokens + cache_read_tokens + cache_write_tokens
5. ✅ total_tokens 包含所有输入 tokens
6. ✅ JSON 格式符合规范
"""

import asyncio
import logging
import os
import sys

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


def test_cache_hit_scenario():
    """
    测试场景 1：缓存命中
    
    模拟大量 cache_read_tokens 的情况，验证：
    - prompt_tokens 包含 cache_read_tokens
    - cache_read_price 计算正确
    - 缓存命中率计算正确
    """
    from core.billing.tracker import EnhancedUsageTracker
    from core.billing.models import UsageResponse
    from core.billing.pricing import get_pricing_for_model
    
    print("\n" + "="*70)
    print("🧪 测试场景 1：缓存命中（Cache Hit）")
    print("="*70)
    
    tracker = EnhancedUsageTracker()
    
    # 模拟一次有大量缓存命中的调用
    # 假设有 5000 tokens 是从缓存读取的
    class MockResponse:
        usage = {
            "input_tokens": 100,      # 新输入（cache breakpoint 之后的部分）
            "output_tokens": 200,
            "thinking_tokens": 0,
            "cache_read_tokens": 5000,  # 缓存命中！
            "cache_creation_tokens": 0
        }
    
    model = "claude-sonnet-4.5"
    record = tracker.record_call(
        llm_response=MockResponse(),
        model=model,
        purpose="cache_hit_test",
        latency_ms=1500,
        message_id="test_cache_hit_001"
    )
    
    # 验证记录
    assert record is not None, "记录不应为 None"
    assert record.cache_read_tokens == 5000, f"cache_read_tokens 应为 5000, 实际: {record.cache_read_tokens}"
    assert record.input_tokens == 100, f"input_tokens 应为 100, 实际: {record.input_tokens}"
    print(f"✅ 记录创建成功: {record.call_id}")
    print(f"   • input_tokens: {record.input_tokens}")
    print(f"   • cache_read_tokens: {record.cache_read_tokens}")
    
    # 验证价格计算
    pricing = get_pricing_for_model(model)
    expected_cache_read_price = (5000 / 1_000_000) * pricing['cache_read']
    expected_input_price = (100 / 1_000_000) * pricing['input']
    
    assert abs(record.cache_read_price - expected_cache_read_price) < 0.000001, \
        f"cache_read_price 计算错误: {record.cache_read_price} != {expected_cache_read_price}"
    print(f"✅ 缓存价格计算正确: ${record.cache_read_price:.6f}")
    print(f"   • cache_read 单价: ${pricing['cache_read']}/M tokens")
    print(f"   • input 单价: ${pricing['input']}/M tokens")
    
    # 生成 UsageResponse
    usage_response = UsageResponse.from_tracker(tracker, latency=1.5)
    
    # 验证 prompt_tokens 包含 cache_read_tokens
    # 根据 Claude Platform 规范：prompt_tokens = input_tokens + cache_read_tokens + cache_write_tokens
    expected_prompt_tokens = 100 + 5000 + 0  # input + cache_read + cache_write
    assert usage_response.prompt_tokens == expected_prompt_tokens, \
        f"prompt_tokens 应为 {expected_prompt_tokens}, 实际: {usage_response.prompt_tokens}"
    print(f"✅ prompt_tokens 正确: {usage_response.prompt_tokens} (包含 cache_read)")
    
    # 验证 total_tokens
    expected_total = expected_prompt_tokens + 200 + 0  # prompt + output + thinking
    assert usage_response.total_tokens == expected_total, \
        f"total_tokens 应为 {expected_total}, 实际: {usage_response.total_tokens}"
    print(f"✅ total_tokens 正确: {usage_response.total_tokens}")
    
    # 验证缓存命中率
    expected_hit_rate = 5000 / (100 + 5000)  # cache_read / (input + cache_read)
    assert abs(usage_response.cache_hit_rate - expected_hit_rate) < 0.001, \
        f"cache_hit_rate 应为 {expected_hit_rate:.4f}, 实际: {usage_response.cache_hit_rate}"
    print(f"✅ 缓存命中率正确: {usage_response.cache_hit_rate:.2%}")
    
    # 验证节省的成本
    assert usage_response.cost_saved_by_cache > 0, "应该有缓存节省的成本"
    print(f"✅ 缓存节省成本: ${usage_response.cost_saved_by_cache:.6f}")
    
    print("\n🎉 场景 1 测试通过！")
    return usage_response


def test_cache_write_scenario():
    """
    测试场景 2：缓存写入
    
    模拟首次调用时创建缓存的情况，验证：
    - cache_write_tokens 正确累积
    - cache_write_price 计算正确
    """
    from core.billing.tracker import EnhancedUsageTracker
    from core.billing.models import UsageResponse
    from core.billing.pricing import get_pricing_for_model
    
    print("\n" + "="*70)
    print("🧪 测试场景 2：缓存写入（Cache Write）")
    print("="*70)
    
    tracker = EnhancedUsageTracker()
    
    # 模拟首次调用，创建缓存
    class MockResponse:
        usage = {
            "input_tokens": 100,
            "output_tokens": 150,
            "thinking_tokens": 500,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 8000  # 创建缓存！
        }
    
    model = "claude-sonnet-4.5"
    record = tracker.record_call(
        llm_response=MockResponse(),
        model=model,
        purpose="cache_write_test",
        latency_ms=3000,
        message_id="test_cache_write_001"
    )
    
    assert record is not None, "记录不应为 None"
    assert record.cache_write_tokens == 8000, f"cache_write_tokens 应为 8000, 实际: {record.cache_write_tokens}"
    print(f"✅ 记录创建成功: {record.call_id}")
    print(f"   • input_tokens: {record.input_tokens}")
    print(f"   • cache_write_tokens: {record.cache_write_tokens}")
    
    # 验证缓存写入价格
    pricing = get_pricing_for_model(model)
    expected_cache_write_price = (8000 / 1_000_000) * pricing['cache_write']
    
    assert abs(record.cache_write_price - expected_cache_write_price) < 0.000001, \
        f"cache_write_price 计算错误: {record.cache_write_price} != {expected_cache_write_price}"
    print(f"✅ 缓存写入价格正确: ${record.cache_write_price:.6f}")
    print(f"   • cache_write 单价: ${pricing['cache_write']}/M tokens")
    
    # 生成 UsageResponse
    usage_response = UsageResponse.from_tracker(tracker, latency=3.0)
    
    # 验证 prompt_tokens 包含 cache_write_tokens
    expected_prompt_tokens = 100 + 0 + 8000  # input + cache_read + cache_write
    assert usage_response.prompt_tokens == expected_prompt_tokens, \
        f"prompt_tokens 应为 {expected_prompt_tokens}, 实际: {usage_response.prompt_tokens}"
    print(f"✅ prompt_tokens 正确: {usage_response.prompt_tokens} (包含 cache_write)")
    
    # 验证 cache_write_price 在响应中
    assert usage_response.cache_write_price > 0, "cache_write_price 应大于 0"
    print(f"✅ cache_write_price: ${usage_response.cache_write_price:.6f}")
    
    print("\n🎉 场景 2 测试通过！")
    return usage_response


def test_mixed_cache_scenario():
    """
    测试场景 3：混合场景
    
    模拟多次调用，包含：
    - 首次调用：创建缓存
    - 后续调用：命中缓存
    """
    from core.billing.tracker import EnhancedUsageTracker
    from core.billing.models import UsageResponse
    
    print("\n" + "="*70)
    print("🧪 测试场景 3：混合场景（多次调用）")
    print("="*70)
    
    tracker = EnhancedUsageTracker()
    
    # 调用 1：首次调用，创建缓存
    class MockResponse1:
        usage = {
            "input_tokens": 200,
            "output_tokens": 100,
            "thinking_tokens": 300,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 6000  # 创建缓存
        }
    
    record1 = tracker.record_call(
        llm_response=MockResponse1(),
        model="claude-sonnet-4.5",
        purpose="initial_call",
        latency_ms=2000,
        message_id="mixed_001"
    )
    print(f"✅ 调用 1: 创建缓存 {record1.cache_write_tokens} tokens")
    
    # 调用 2：后续调用，命中缓存
    class MockResponse2:
        usage = {
            "input_tokens": 50,
            "output_tokens": 150,
            "thinking_tokens": 200,
            "cache_read_tokens": 6000,  # 命中缓存
            "cache_creation_tokens": 0
        }
    
    record2 = tracker.record_call(
        llm_response=MockResponse2(),
        model="claude-sonnet-4.5",
        purpose="followup_call",
        latency_ms=1000,
        message_id="mixed_002"
    )
    print(f"✅ 调用 2: 命中缓存 {record2.cache_read_tokens} tokens")
    
    # 调用 3：追问，继续命中缓存
    class MockResponse3:
        usage = {
            "input_tokens": 80,
            "output_tokens": 200,
            "thinking_tokens": 150,
            "cache_read_tokens": 6000,  # 继续命中
            "cache_creation_tokens": 500  # 新增部分写入缓存
        }
    
    record3 = tracker.record_call(
        llm_response=MockResponse3(),
        model="claude-sonnet-4.5",
        purpose="followup_call_2",
        latency_ms=1200,
        message_id="mixed_003"
    )
    print(f"✅ 调用 3: 命中 {record3.cache_read_tokens} + 写入 {record3.cache_write_tokens} tokens")
    
    # 生成汇总
    usage_response = UsageResponse.from_tracker(tracker, latency=4.2)
    
    # 验证累积统计
    expected_input = 200 + 50 + 80
    expected_output = 100 + 150 + 200
    expected_thinking = 300 + 200 + 150
    expected_cache_read = 0 + 6000 + 6000
    expected_cache_write = 6000 + 0 + 500
    
    assert usage_response.cache_read_tokens == expected_cache_read, \
        f"cache_read_tokens 应为 {expected_cache_read}, 实际: {usage_response.cache_read_tokens}"
    assert usage_response.cache_write_tokens == expected_cache_write, \
        f"cache_write_tokens 应为 {expected_cache_write}, 实际: {usage_response.cache_write_tokens}"
    
    # 验证 prompt_tokens = input + cache_read + cache_write
    expected_prompt = expected_input + expected_cache_read + expected_cache_write
    assert usage_response.prompt_tokens == expected_prompt, \
        f"prompt_tokens 应为 {expected_prompt}, 实际: {usage_response.prompt_tokens}"
    
    print(f"\n📊 汇总统计:")
    print(f"   • 调用次数: {usage_response.llm_calls}")
    print(f"   • input_tokens: {expected_input}")
    print(f"   • cache_read_tokens: {usage_response.cache_read_tokens}")
    print(f"   • cache_write_tokens: {usage_response.cache_write_tokens}")
    print(f"   • prompt_tokens: {usage_response.prompt_tokens} (input + cache_read + cache_write)")
    print(f"   • completion_tokens: {usage_response.completion_tokens}")
    print(f"   • thinking_tokens: {usage_response.thinking_tokens}")
    print(f"   • total_tokens: {usage_response.total_tokens}")
    print(f"   • 缓存命中率: {usage_response.cache_hit_rate:.2%}")
    print(f"   • 缓存节省: ${usage_response.cost_saved_by_cache:.6f}")
    
    # 验证价格
    print(f"\n💰 价格明细:")
    print(f"   • prompt_price: ${usage_response.prompt_price:.6f}")
    print(f"   • completion_price: ${usage_response.completion_price:.6f}")
    print(f"   • thinking_price: ${usage_response.thinking_price:.6f}")
    print(f"   • cache_read_price: ${usage_response.cache_read_price:.6f}")
    print(f"   • cache_write_price: ${usage_response.cache_write_price:.6f}")
    print(f"   • total_price: ${usage_response.total_price:.6f}")
    
    # 验证 total_price 正确
    expected_total_price = (
        usage_response.prompt_price +
        usage_response.completion_price +
        usage_response.thinking_price +
        usage_response.cache_read_price +
        usage_response.cache_write_price
    )
    assert abs(usage_response.total_price - expected_total_price) < 0.000001, \
        f"total_price 应为 {expected_total_price}, 实际: {usage_response.total_price}"
    print(f"✅ total_price 计算正确")
    
    print("\n🎉 场景 3 测试通过！")
    return usage_response


def test_multi_model_with_cache():
    """
    测试场景 4：多模型 + 缓存
    
    验证不同模型的缓存价格是否正确应用
    """
    from core.billing.tracker import EnhancedUsageTracker
    from core.billing.models import UsageResponse
    from core.billing.pricing import get_pricing_for_model
    
    print("\n" + "="*70)
    print("🧪 测试场景 4：多模型 + 缓存")
    print("="*70)
    
    tracker = EnhancedUsageTracker()
    
    # 调用 1：Haiku 意图识别（有缓存）
    class MockHaikuResponse:
        usage = {
            "input_tokens": 50,
            "output_tokens": 30,
            "thinking_tokens": 0,
            "cache_read_tokens": 2000,  # 命中系统提示缓存
            "cache_creation_tokens": 0
        }
    
    haiku_record = tracker.record_call(
        llm_response=MockHaikuResponse(),
        model="claude-haiku-4.5",
        purpose="intent_analysis",
        latency_ms=500,
        message_id="multi_haiku_001"
    )
    
    # 验证 Haiku 的缓存价格
    haiku_pricing = get_pricing_for_model("claude-haiku-4.5")
    expected_haiku_cache_price = (2000 / 1_000_000) * haiku_pricing['cache_read']
    assert abs(haiku_record.cache_read_price - expected_haiku_cache_price) < 0.000001
    print(f"✅ Haiku 缓存价格: ${haiku_record.cache_read_price:.6f} (单价: ${haiku_pricing['cache_read']}/M)")
    
    # 调用 2：Sonnet 主对话（有缓存）
    class MockSonnetResponse:
        usage = {
            "input_tokens": 100,
            "output_tokens": 200,
            "thinking_tokens": 500,
            "cache_read_tokens": 8000,  # 命中系统提示缓存
            "cache_creation_tokens": 1000  # 部分新内容写入
        }
    
    sonnet_record = tracker.record_call(
        llm_response=MockSonnetResponse(),
        model="claude-sonnet-4.5",
        purpose="main_response",
        latency_ms=2000,
        message_id="multi_sonnet_001"
    )
    
    # 验证 Sonnet 的缓存价格
    sonnet_pricing = get_pricing_for_model("claude-sonnet-4.5")
    expected_sonnet_cache_read_price = (8000 / 1_000_000) * sonnet_pricing['cache_read']
    expected_sonnet_cache_write_price = (1000 / 1_000_000) * sonnet_pricing['cache_write']
    
    assert abs(sonnet_record.cache_read_price - expected_sonnet_cache_read_price) < 0.000001
    assert abs(sonnet_record.cache_write_price - expected_sonnet_cache_write_price) < 0.000001
    print(f"✅ Sonnet 缓存读取价格: ${sonnet_record.cache_read_price:.6f} (单价: ${sonnet_pricing['cache_read']}/M)")
    print(f"✅ Sonnet 缓存写入价格: ${sonnet_record.cache_write_price:.6f} (单价: ${sonnet_pricing['cache_write']}/M)")
    
    # 生成汇总
    usage_response = UsageResponse.from_tracker(tracker, latency=2.5)
    
    print(f"\n📊 多模型汇总:")
    print(f"   • 调用次数: {usage_response.llm_calls}")
    print(f"   • cache_read_tokens: {usage_response.cache_read_tokens} (Haiku: 2000 + Sonnet: 8000)")
    print(f"   • cache_write_tokens: {usage_response.cache_write_tokens}")
    print(f"   • cache_read_price: ${usage_response.cache_read_price:.6f}")
    print(f"   • cache_write_price: ${usage_response.cache_write_price:.6f}")
    print(f"   • total_price: ${usage_response.total_price:.6f}")
    
    # 验证调用明细
    assert len(usage_response.llm_call_details) == 2, "应该有 2 条调用明细"
    assert usage_response.llm_call_details[0].model == "claude-haiku-4.5"
    assert usage_response.llm_call_details[1].model == "claude-sonnet-4.5"
    print(f"✅ 调用明细正确记录")
    
    print("\n🎉 场景 4 测试通过！")
    return usage_response


def test_json_format():
    """
    测试场景 5：JSON 格式验证
    
    确保所有缓存相关字段在 JSON 输出中正确
    """
    from core.billing.tracker import EnhancedUsageTracker
    from core.billing.models import UsageResponse
    import json
    
    print("\n" + "="*70)
    print("🧪 测试场景 5：JSON 格式验证")
    print("="*70)
    
    tracker = EnhancedUsageTracker()
    
    class MockResponse:
        usage = {
            "input_tokens": 100,
            "output_tokens": 200,
            "thinking_tokens": 300,
            "cache_read_tokens": 5000,
            "cache_creation_tokens": 2000
        }
    
    tracker.record_call(
        llm_response=MockResponse(),
        model="claude-sonnet-4.5",
        purpose="json_test",
        latency_ms=1000,
        message_id="json_test_001"
    )
    
    usage_response = UsageResponse.from_tracker(tracker, latency=1.0)
    usage_json = usage_response.model_dump(mode='json')
    json_str = json.dumps(usage_json, ensure_ascii=False, indent=2)
    
    print("📋 JSON 输出:")
    # 只显示关键字段
    compact = {
        "prompt_tokens": usage_json["prompt_tokens"],
        "completion_tokens": usage_json["completion_tokens"],
        "thinking_tokens": usage_json["thinking_tokens"],
        "cache_read_tokens": usage_json["cache_read_tokens"],
        "cache_write_tokens": usage_json["cache_write_tokens"],
        "total_tokens": usage_json["total_tokens"],
        "prompt_price": usage_json["prompt_price"],
        "cache_read_price": usage_json["cache_read_price"],
        "cache_write_price": usage_json["cache_write_price"],
        "total_price": usage_json["total_price"],
        "cache_hit_rate": usage_json["cache_hit_rate"],
        "cost_saved_by_cache": usage_json["cost_saved_by_cache"]
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2))
    
    # 验证所有价格字段都是数字
    assert isinstance(usage_json["cache_read_price"], (int, float)), "cache_read_price 必须是数字"
    assert isinstance(usage_json["cache_write_price"], (int, float)), "cache_write_price 必须是数字"
    assert isinstance(usage_json["cache_hit_rate"], (int, float)), "cache_hit_rate 必须是数字"
    assert isinstance(usage_json["cost_saved_by_cache"], (int, float)), "cost_saved_by_cache 必须是数字"
    
    # 验证 prompt_tokens 包含缓存
    assert usage_json["prompt_tokens"] == 100 + 5000 + 2000, "prompt_tokens 应包含 cache tokens"
    
    # 验证 llm_call_details 包含缓存信息
    assert len(usage_json["llm_call_details"]) == 1
    detail = usage_json["llm_call_details"][0]
    assert detail["cache_read_tokens"] == 5000
    assert detail["cache_write_tokens"] == 2000
    assert isinstance(detail["cache_read_price"], (int, float))
    assert isinstance(detail["cache_write_price"], (int, float))
    
    print("\n✅ 所有缓存字段在 JSON 中正确输出")
    print("🎉 场景 5 测试通过！")
    return usage_response


def run_all_tests():
    """运行所有缓存计费测试"""
    print("\n" + "="*70)
    print("🚀 开始缓存计费 E2E 测试")
    print("="*70)
    
    try:
        # 场景 1：缓存命中
        test_cache_hit_scenario()
        
        # 场景 2：缓存写入
        test_cache_write_scenario()
        
        # 场景 3：混合场景
        test_mixed_cache_scenario()
        
        # 场景 4：多模型 + 缓存
        test_multi_model_with_cache()
        
        # 场景 5：JSON 格式
        test_json_format()
        
        print("\n" + "="*70)
        print("✅ 所有缓存计费测试通过！")
        print("="*70)
        print("\n验证点总结:")
        print("  ✓ cache_read_tokens 正确累积")
        print("  ✓ cache_creation_tokens 正确累积")
        print("  ✓ 每个模型的缓存价格独立计算")
        print("  ✓ prompt_tokens = input + cache_read + cache_write")
        print("  ✓ total_tokens 包含所有输入 tokens")
        print("  ✓ 缓存命中率计算正确")
        print("  ✓ 缓存节省成本计算正确")
        print("  ✓ JSON 格式符合规范")
        
        return 0
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
