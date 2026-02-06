# Usage Tracking - Token 使用统计架构

## 概述

Usage Tracking 用于追踪 LLM API 调用的 token 使用情况，支持多轮对话的累积统计、成本估算和性能分析。

## 架构设计

### 核心组件

```
┌─────────────────────────────────────────────────────────┐
│                    Chat Service                         │
│  - 创建 Agent                                           │
│  - 收集 content blocks                                  │
│  - 保存消息 + metadata (含 usage)                       │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                    SimpleAgent                          │
│  - RVR 循环（多轮 LLM 调用）                            │
│  - 每次 LLM 响应后累积 usage                            │
│  - 提供 usage_stats 属性给外部访问                      │
└─────────────────────────────────────────────────────────┘
                           │
                           │ 使用
                           ▼
┌─────────────────────────────────────────────────────────┐
│                  UsageTracker                           │
│  - 累积 token 统计                                      │
│  - 计算总成本                                           │
│  - 提供统计快照                                         │
└─────────────────────────────────────────────────────────┘
                           │
                           │ 从中提取
                           ▼
┌─────────────────────────────────────────────────────────┐
│                  LLMResponse                            │
│  - 每次 LLM 调用的响应                                  │
│  - 包含单次调用的 usage 信息                            │
└─────────────────────────────────────────────────────────┘
```

---

## 数据流

### 1. LLM 调用 → Usage 数据生成

```python
# core/llm/claude.py:889-913

def _parse_response(self, response, invocation_type=None) -> LLMResponse:
    # ... 解析内容 ...
    
    # 提取 usage 信息
    usage = {}
    if hasattr(response, 'usage'):
        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens
        }
        if hasattr(response.usage, 'cache_read_input_tokens'):
            usage["cache_read_tokens"] = response.usage.cache_read_input_tokens
        if hasattr(response.usage, 'cache_creation_input_tokens'):
            usage["cache_creation_tokens"] = response.usage.cache_creation_input_tokens
    
    return LLMResponse(
        content=content_text,
        thinking=thinking_text,
        tool_calls=tool_calls,
        stop_reason=response.stop_reason,
        usage=usage,  # ← 每次调用的 usage
        raw_content=raw_content,
        cache_read_tokens=usage.get("cache_read_tokens", 0),
        cache_creation_tokens=usage.get("cache_creation_tokens", 0)
    )
```

### 2. Agent 累积 Usage

```python
# core/agent/simple/simple_agent.py

async def _process_stream(...):
    # ... 流式处理 ...
    
    # 保存最终响应到 ctx
    if final_response:
        # 🔢 累积 usage 统计
        self.usage_tracker.accumulate(final_response)
        # 存到 ctx，供 RVR 循环使用
        ctx.last_llm_response = final_response
```

**关键点：**
- 流式模式：在流结束时累积，响应存到 ctx
- 非流式模式：在响应返回时累积
- 每个 RVR turn 都会调用一次 LLM，每次都会累积

### 3. Chat Service 保存到消息 metadata

```python
# services/chat_service.py:592-598

# 提取 usage 统计（从 agent.usage_stats）
if agent and hasattr(agent, 'usage_stats'):
    usage_stats = agent.usage_stats
    if usage_stats:
        metadata["usage"] = {
            "input_tokens": usage_stats.get("total_input_tokens", 0),
            "output_tokens": usage_stats.get("total_output_tokens", 0)
        }

# 保存到数据库
await self.conversation_service.update_message(
    message_id=message_id,
    content=content_json,
    status=status,
    metadata=metadata  # ← 包含 usage
)
```

### 4. 数据库存储

```sql
-- infra/database/models/message.py

messages 表:
  - id (UUID)
  - conversation_id
  - role
  - content (JSON)
  - status
  - extra_data (JSON) ← 存储 metadata，包含 usage
    {
      "completed_at": "2025-01-05T10:30:00",
      "usage": {
        "input_tokens": 1500,
        "output_tokens": 800
      }
    }
```

---

## UsageTracker 详细设计

### 核心方法

```python
class UsageTracker:
    """Token 使用统计跟踪器"""
    
    def __init__(self):
        self._stats = {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cache_read_tokens": 0,
            "total_cache_creation_tokens": 0,
            "llm_calls": 0
        }
    
    def accumulate(self, llm_response):
        """累积 LLM 响应的 usage"""
        # 从 llm_response.usage 中提取并累加
    
    def get_stats(self) -> dict:
        """获取当前统计（副本）"""
        return self._stats.copy()
    
    def get_total_tokens(self) -> int:
        """获取总 token 数"""
        return self._stats["total_input_tokens"] + self._stats["total_output_tokens"]
    
    def get_cost_estimate(self, ...) -> float:
        """估算成本（美元）"""
        # 基于 Claude Sonnet 4.5 定价
    
    def reset(self):
        """重置统计"""
    
    def snapshot(self) -> dict:
        """创建详细快照（含计算指标）"""
```

### 为什么独立出 UsageTracker？

1. **复用性**：未来多个 Agent 都可以使用
2. **单一职责**：Agent 只负责编排，UsageTracker 负责统计
3. **易测试**：纯数据操作，便于单元测试
4. **扩展性**：可以轻松添加新功能（如持久化、实时上报）

---

## Agent 集成

### SimpleAgent 使用方式

```python
class SimpleAgent:
    def __init__(...):
        # 创建 UsageTracker
        from utils.usage_tracker import create_usage_tracker
        self.usage_tracker = create_usage_tracker()
    
    @property
    def usage_stats(self) -> dict:
        """兼容属性：返回统计字典"""
        return self.usage_tracker.get_stats()
    
    async def chat(...):
        # RVR 循环
        for turn in range(self.max_turns):
            # 调用 LLM
            response = await self.llm.create_message_async(...)
            
            # 累积 usage
            self.usage_tracker.accumulate(response)
```

### 多 Agent 扩展示例

```python
class AdvancedAgent:
    def __init__(...):
        self.usage_tracker = create_usage_tracker()
    
    @property
    def usage_stats(self) -> dict:
        return self.usage_tracker.get_stats()
    
    # ... 其他实现 ...

class StreamingAgent:
    def __init__(...):
        self.usage_tracker = create_usage_tracker()
    
    # ... 同样的接口 ...
```

---

## 统计数据结构

### 基础统计 (`get_stats()`)

```json
{
  "total_input_tokens": 1500,
  "total_output_tokens": 800,
  "total_cache_read_tokens": 500,
  "total_cache_creation_tokens": 200,
  "llm_calls": 3
}
```

### 详细快照 (`snapshot()`)

```json
{
  "total_input_tokens": 1500,
  "total_output_tokens": 800,
  "total_cache_read_tokens": 500,
  "total_cache_creation_tokens": 200,
  "llm_calls": 3,
  
  "total_tokens": 2300,
  "estimated_cost_usd": 0.0345,
  "average_input_per_call": 500,
  "average_output_per_call": 266.67,
  "cache_hit_rate": 0.25
}
```

---

## 成本计算

### Claude Sonnet 4.5 定价（2025）

| 类型 | 价格（每 1M tokens） |
|------|---------------------|
| Input tokens | $3.00 |
| Output tokens | $15.00 |
| Cache read tokens | $0.30 |
| Cache creation tokens | $3.75 |

### 计算公式

```python
cost = (
    (input_tokens / 1_000_000) * 3.00 +
    (output_tokens / 1_000_000) * 15.00 +
    (cache_read_tokens / 1_000_000) * 0.30 +
    (cache_creation_tokens / 1_000_000) * 3.75
)
```

---

## 使用场景

### 1. 对话结束时保存统计

```python
# services/chat_service.py

async def _save_assistant_message(...):
    # 从 agent 获取累积的 usage
    usage_stats = agent.usage_stats
    
    # 保存到 message metadata
    metadata["usage"] = {
        "input_tokens": usage_stats.get("total_input_tokens", 0),
        "output_tokens": usage_stats.get("total_output_tokens", 0)
    }
```

### 2. 实时监控（未来扩展）

```python
class UsageTracker:
    def __init__(self, on_update_callback=None):
        self.on_update_callback = on_update_callback
    
    def accumulate(self, llm_response):
        # ... 累积逻辑 ...
        
        if self.on_update_callback:
            self.on_update_callback(self.get_stats())
```

### 3. 成本预警（未来扩展）

```python
tracker = create_usage_tracker()

# 设置成本阈值
cost_threshold = 1.0  # $1

# 检查成本
if tracker.get_cost_estimate() > cost_threshold:
    logger.warning(f"成本超过阈值: ${tracker.get_cost_estimate():.4f}")
```

### 4. 性能分析

```python
snapshot = agent.usage_tracker.snapshot()

print(f"总调用次数: {snapshot['llm_calls']}")
print(f"平均每次 input: {snapshot['average_input_per_call']:.0f} tokens")
print(f"缓存命中率: {snapshot['cache_hit_rate']:.2%}")
print(f"总成本: ${snapshot['estimated_cost_usd']:.4f}")
```

---

## 前端展示

### 消息元数据返回格式

```json
{
  "id": "msg-123",
  "role": "assistant",
  "content": [...],
  "metadata": {
    "completed_at": "2025-01-05T10:30:00",
    "usage": {
      "input_tokens": 1500,
      "output_tokens": 800
    }
  }
}
```

### 前端渲染示例

```vue
<template>
  <div class="message-usage">
    <span class="usage-label">Token 使用:</span>
    <span class="usage-input">{{ usage.input_tokens }} in</span>
    <span class="usage-output">{{ usage.output_tokens }} out</span>
    <span class="usage-cost">≈ ${{ estimatedCost }}</span>
  </div>
</template>

<script>
export default {
  props: ['metadata'],
  computed: {
    usage() {
      return this.metadata?.usage || { input_tokens: 0, output_tokens: 0 }
    },
    estimatedCost() {
      const { input_tokens, output_tokens } = this.usage
      const cost = (input_tokens / 1_000_000) * 3 + (output_tokens / 1_000_000) * 15
      return cost.toFixed(4)
    }
  }
}
</script>
```

---

## 测试指南

### 单元测试示例

```python
# tests/test_usage_tracker.py

import pytest
from utils.usage_tracker import UsageTracker
from core.llm.base import LLMResponse

def test_accumulate():
    tracker = UsageTracker()
    
    # 模拟 LLM 响应
    response = LLMResponse(
        content="Hello",
        usage={
            "input_tokens": 100,
            "output_tokens": 50
        }
    )
    
    tracker.accumulate(response)
    
    stats = tracker.get_stats()
    assert stats["total_input_tokens"] == 100
    assert stats["total_output_tokens"] == 50
    assert stats["llm_calls"] == 1

def test_multiple_accumulate():
    tracker = UsageTracker()
    
    # 累积多次
    for i in range(3):
        response = LLMResponse(
            content=f"Response {i}",
            usage={"input_tokens": 100, "output_tokens": 50}
        )
        tracker.accumulate(response)
    
    stats = tracker.get_stats()
    assert stats["total_input_tokens"] == 300
    assert stats["total_output_tokens"] == 150
    assert stats["llm_calls"] == 3

def test_cost_estimate():
    tracker = UsageTracker()
    
    response = LLMResponse(
        content="Test",
        usage={
            "input_tokens": 1_000_000,  # 1M tokens
            "output_tokens": 1_000_000   # 1M tokens
        }
    )
    tracker.accumulate(response)
    
    cost = tracker.get_cost_estimate()
    assert cost == pytest.approx(18.0)  # 3 + 15 = 18
```

---

## 最佳实践

### ✅ 应该做的

1. **在 Agent 初始化时创建 UsageTracker**
   ```python
   def __init__(self):
       self.usage_tracker = create_usage_tracker()
   ```

2. **每次 LLM 响应后立即累积**
   ```python
   response = await self.llm.create_message_async(...)
   self.usage_tracker.accumulate(response)
   ```

3. **提供标准接口**
   ```python
   @property
   def usage_stats(self) -> dict:
       return self.usage_tracker.get_stats()
   ```

4. **保存到 message metadata**
   ```python
   metadata["usage"] = {
       "input_tokens": stats.get("total_input_tokens", 0),
       "output_tokens": stats.get("total_output_tokens", 0)
   }
   ```

### ❌ 不应该做的

1. **不要忘记累积**
   ```python
   # ❌ 错误：没有调用 accumulate
   response = await self.llm.create_message_async(...)
   # 忘记累积了！
   ```

2. **不要直接修改内部状态**
   ```python
   # ❌ 错误：直接访问内部变量
   agent.usage_tracker._stats["total_input_tokens"] = 0
   
   # ✅ 正确：使用公开方法
   agent.usage_tracker.reset()
   ```

3. **不要在多个地方重复计算成本**
   ```python
   # ❌ 错误：重复实现成本计算
   cost = (tokens / 1_000_000) * 3.0
   
   # ✅ 正确：使用 UsageTracker 的方法
   cost = tracker.get_cost_estimate()
   ```

---

## 总结

### 设计亮点

1. **分层清晰**：LLM → Agent → UsageTracker → ChatService
2. **职责单一**：UsageTracker 只做统计，Agent 只做编排
3. **易于复用**：所有 Agent 都可以使用同一个 UsageTracker
4. **便于扩展**：可以轻松添加新功能（如实时上报、成本预警）

### 数据流向

```
LLM API Response (每次调用)
    ↓
LLMResponse.usage (单次 usage)
    ↓
UsageTracker.accumulate (累积多次)
    ↓
Agent.usage_stats (对外接口)
    ↓
Message.metadata.usage (持久化)
    ↓
前端展示
```

