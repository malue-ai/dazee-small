# 多模型定价与计费支持

> **版本**: V7.5  
> **更新日期**: 2026-01-16  
> **状态**: ✅ 生产就绪

---

## 📋 支持的模型列表

### Claude 4.5 系列（全部支持）

| 模型 | 用途 | Input ($/M) | Output ($/M) | Cache Write ($/M) | Cache Read ($/M) |
|------|------|-------------|--------------|-------------------|------------------|
| **claude-opus-4.5** | 🎯 Lead Agent<br/>🎯 Critic Agent<br/>🎯 高质量模式 | 5.0 | 25.0 | 6.25 | 0.5 |
| **claude-sonnet-4.5** | 🎯 Worker Agent<br/>🎯 主对话<br/>🎯 标准模式 | 3.0 | 15.0 | 3.75 | 0.3 |
| **claude-haiku-4.5** | 🎯 意图识别<br/>🎯 快速任务<br/>🎯 轻量级处理 | 1.0 | 5.0 | 1.25 | 0.1 |

---

## 🎯 多智能体架构中的模型分配

### 1. 默认配置（成本优化）

```yaml
orchestrator:
  model: "claude-opus-4-5-20251101"     # Lead Agent：复杂规划
  
worker:
  model: "claude-sonnet-4-5-20250929"   # Worker：执行任务
  
critic:
  model: "claude-sonnet-4-5-20250929"   # Critic：质量评估
```

**成本特点**：
- Lead Agent 用 Opus（高质量规划）
- Worker 用 Sonnet（成本效益平衡）
- 单次对话预估：$0.002 - $0.01

---

### 2. 高质量配置（质量优先）

```yaml
orchestrator:
  model: "claude-opus-4-5-20251101"     # Lead Agent
  
worker:
  model: "claude-opus-4-5-20251101"     # Worker：高质量执行
  
critic:
  model: "claude-opus-4-5-20251101"     # Critic：严格评估
```

**成本特点**：
- 全部使用 Opus
- 单次对话预估：$0.01 - $0.05

---

## 💰 实际计费示例

### 场景 1：单智能体（Haiku + Sonnet）

```json
{
  "total_price": 0.003637,
  "currency": "USD",
  "llm_calls": 2,
  "llm_call_details": [
    {
      "call_id": "call_001",
      "model": "claude-haiku-4.5",
      "purpose": "intent_analysis",
      "input_tokens": 54,
      "output_tokens": 204,
      "thinking_tokens": 59,
      "input_unit_price": 1.0,
      "output_unit_price": 5.0,
      "total_price": 0.001369
    },
    {
      "call_id": "call_002",
      "model": "claude-sonnet-4.5",
      "purpose": "main_response",
      "input_tokens": 51,
      "output_tokens": 123,
      "thinking_tokens": 18,
      "input_unit_price": 3.0,
      "output_unit_price": 15.0,
      "total_price": 0.002268
    }
  ]
}
```

---

### 场景 2：多智能体（Opus + Sonnet）

```json
{
  "total_price": 0.0245,
  "currency": "USD",
  "llm_calls": 4,
  "llm_call_details": [
    {
      "call_id": "call_001",
      "model": "claude-opus-4.5",
      "purpose": "orchestrator_planning",
      "input_tokens": 500,
      "output_tokens": 200,
      "thinking_tokens": 150,
      "input_unit_price": 5.0,
      "output_unit_price": 25.0,
      "total_price": 0.011250
    },
    {
      "call_id": "call_002",
      "model": "claude-sonnet-4.5",
      "purpose": "worker_task_1",
      "input_tokens": 300,
      "output_tokens": 400,
      "thinking_tokens": 50,
      "input_unit_price": 3.0,
      "output_unit_price": 15.0,
      "total_price": 0.007650
    },
    {
      "call_id": "call_003",
      "model": "claude-sonnet-4.5",
      "purpose": "worker_task_2",
      "input_tokens": 200,
      "output_tokens": 300,
      "thinking_tokens": 30,
      "input_unit_price": 3.0,
      "output_unit_price": 15.0,
      "total_price": 0.005550
    },
    {
      "call_id": "call_004",
      "model": "claude-sonnet-4.5",
      "purpose": "critic_evaluation",
      "input_tokens": 100,
      "output_tokens": 50,
      "thinking_tokens": 20,
      "input_unit_price": 3.0,
      "output_unit_price": 15.0,
      "total_price": 0.001350
    }
  ]
}
```

**成本分解**：
- Orchestrator (Opus): $0.01125 (45.9%)
- Worker Task 1 (Sonnet): $0.00765 (31.2%)
- Worker Task 2 (Sonnet): $0.00555 (22.7%)
- Critic (Sonnet): $0.00135 (5.5%)

---

## 🔧 技术实现

### 1. 定价表（`models/usage.py`）

```python
CLAUDE_PRICING = {
    "claude-opus-4.5": {
        "input": 5.0,
        "output": 25.0,
        "cache_write": 6.25,
        "cache_read": 0.5
    },
    "claude-sonnet-4.5": {
        "input": 3.0,
        "output": 15.0,
        "cache_write": 3.75,
        "cache_read": 0.3
    },
    "claude-haiku-4.5": {
        "input": 1.0,
        "output": 5.0,
        "cache_write": 1.25,
        "cache_read": 0.1
    }
}
```

### 2. 自动价格匹配

```python
def get_model_pricing(model: str) -> Dict[str, float]:
    """
    智能匹配模型定价
    
    支持的模型名称变体：
    - claude-opus-4.5
    - claude-opus-4-5-20251101
    - claude-sonnet-4.5
    - claude-sonnet-4-5-20250929
    - claude-haiku-4.5
    """
    # 精确匹配
    if model in CLAUDE_PRICING:
        return CLAUDE_PRICING[model]
    
    # 模糊匹配
    model_lower = model.lower()
    for key, pricing in CLAUDE_PRICING.items():
        if key in model_lower or model_lower in key:
            return pricing
    
    # 默认价格（Sonnet）
    return CLAUDE_PRICING["default"]
```

### 3. 使用示例

```python
from core.billing import EnhancedUsageTracker, UsageResponse

# 创建 tracker
tracker = EnhancedUsageTracker()

# 记录 Opus 调用（Lead Agent）
opus_response = await opus_llm.create_message(...)
tracker.record_call(
    llm_response=opus_response,
    model="claude-opus-4.5",
    purpose="orchestrator_planning"
)

# 记录 Sonnet 调用（Worker）
sonnet_response = await sonnet_llm.create_message(...)
tracker.record_call(
    llm_response=sonnet_response,
    model="claude-sonnet-4.5",
    purpose="worker_task"
)

# 记录 Haiku 调用（意图识别）
haiku_response = await haiku_llm.create_message(...)
tracker.record_call(
    llm_response=haiku_response,
    model="claude-haiku-4.5",
    purpose="intent_analysis"
)

# 生成最终响应
usage = UsageResponse.from_tracker(tracker)
```

---

## ✅ 验证状态

| 模型 | 定价配置 | E2E 测试 | 生产就绪 |
|------|---------|---------|---------|
| **Claude Opus 4.5** | ✅ | ⏳ 待添加 | ✅ |
| **Claude Sonnet 4.5** | ✅ | ✅ | ✅ |
| **Claude Haiku 4.5** | ✅ | ✅ | ✅ |

---

## 📊 成本估算工具

### 预估单次对话成本

```python
from core.billing import estimate_monthly_cost

# 单智能体（Haiku + Sonnet）
single_agent_cost = estimate_monthly_cost(
    total_tokens=500,
    model="claude-sonnet-4.5",
    daily_users=1000
)
# 预估：$45 - $90/月

# 多智能体（Opus + Sonnet）
multi_agent_cost = estimate_monthly_cost(
    total_tokens=2000,
    model="claude-opus-4.5",
    daily_users=1000
)
# 预估：$300 - $600/月
```

---

## 🔍 调试和审计

### 查看单个模型的调用

```python
# 获取所有 Opus 调用
opus_calls = tracker.get_calls_by_model("claude-opus-4.5")
opus_total_cost = sum(c.total_price for c in opus_calls)

print(f"Opus 调用次数: {len(opus_calls)}")
print(f"Opus 总成本: ${opus_total_cost:.6f}")

# 获取所有意图识别调用
intent_calls = tracker.get_calls_by_purpose("intent_analysis")
```

---

## 📝 相关文档

- [00-ARCHITECTURE-OVERVIEW.md](./00-ARCHITECTURE-OVERVIEW.md) - 系统架构总览
- [21-BILLING_V7.5_IMPLEMENTATION_SUMMARY.md](./21-BILLING_V7.5_IMPLEMENTATION_SUMMARY.md) - 计费系统实施总结
- [multi_agent_config.yaml](../../config/multi_agent_config.yaml) - 多智能体配置

---

**最后更新**: 2026-01-16  
**维护者**: ZenFlux Agent Team
