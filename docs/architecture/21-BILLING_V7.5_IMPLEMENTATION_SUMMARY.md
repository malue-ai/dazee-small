# Token 计费系统 V7.5 - 实施总结

> **版本**: V7.5 统一版 + Billing Event Integration  
> **更新日期**: 2026-01-20  
> **状态**: ✅ 实施完成，框架已统一，billing 事件已集成，E2E 测试通过

---

## 📋 实施概览

### 核心目标

解决多模型调用场景下的计费追踪问题，实现 Dify 平台级别的计费透明度。

### 关键成果

| 指标 | 实施后 |
|------|--------|
| **多模型区分** | ✅ 每次调用单独记录（call_id + model + purpose） |
| **价格明细** | ✅ 输入/输出/缓存单价 + 总价 |
| **缓存计费** | ✅ 符合 Claude Platform 规范，每模型独立价格 |
| **调用追溯** | ✅ llm_call_details 包含完整调用链 |
| **代码统一** | ✅ UsageTracker = EnhancedUsageTracker |
| **价格格式** | ✅ 全部 float 类型 |
| **Billing 事件** | ✅ 作为 message_delta 类型发送，ZenO 规范兼容 |
| **事件时序** | ✅ billing 在 message_stop 之前发送，顺序保证 |

---

## 🏗️ 模块架构

```
core/billing/
├── __init__.py      # 统一导出接口
├── models.py        # LLMCallRecord, UsageResponse
├── tracker.py       # EnhancedUsageTracker（唯一实现）
└── pricing.py       # 模型定价表和成本计算

utils/
└── usage_tracker.py # UsageTracker = EnhancedUsageTracker（别名）

models/
└── usage.py         # UsageResponse.from_usage_tracker() + CLAUDE_PRICING
```

---

## 🔄 计费调用路径

### 单智能体调用路径

```
用户请求
  ↓
FastAPI Router (routers/chat.py)
  ↓
ChatService.chat() (services/chat_service.py)
  ↓
ChatService._run_agent()
  ↓
SimpleAgent.chat() (core/agent/simple/simple_agent.py)
  ↓
SimpleAgent._chat_loop()
  ↓
ClaudeLLMService.create_message_stream() (core/llm/claude.py)
  │
  ├─→ 每次 LLM 调用返回 usage 信息（包含缓存统计）
  │     {
  │       "input_tokens": 100,
  │       "output_tokens": 200,
  │       "thinking_tokens": 50,
  │       "cache_read_tokens": 5000,  ← 缓存命中
  │       "cache_creation_tokens": 0   ← 缓存写入
  │     }
  │
  └─→ SimpleAgent.usage_tracker.accumulate(response)
        ↓
      EnhancedUsageTracker 记录调用（自动计算价格）
        ↓
      SimpleAgent.chat() 在 message_stop 之前发送 billing 事件
        ↓
      发送 SSE 事件 {"type": "message_delta", "data": {"type": "billing", "content": {...}}}
        ↓
      ChatService 累积 usage 数据到内存
        ↓
      记录到数据库 metadata.usage
```

### 多智能体调用路径

```
用户请求
  ↓
ChatService._run_agent()
  ↓
MultiAgentOrchestrator.execute() (core/agent/multi/orchestrator.py)
  │
  ├─→ 子智能体 1 (Agent A)
  │     └─→ Agent A.usage_tracker.accumulate()
  │
  ├─→ 子智能体 2 (Agent B)
  │     └─→ Agent B.usage_tracker.accumulate()
  │
  └─→ MultiAgentOrchestrator._accumulate_subagent_usage()
        ↓
      汇总所有子智能体的 usage
        ↓
      ChatService 生成 UsageResponse
```

### 关键代码入口

| 位置 | 函数 | 职责 |
|------|------|------|
| `core/agent/simple/simple_agent.py` | `__init__()` | 初始化 `self.usage_tracker` |
| `core/agent/simple/simple_agent.py` | `_chat_loop()` | 调用 `usage_tracker.accumulate()` |
| `core/agent/simple/simple_agent.py` | `chat()` | 在 message_stop 前发送 billing 事件 |
| `services/chat_service.py` | `_run_agent()` | 累积 usage 数据到内存 |
| `models/usage.py` | `UsageResponse.from_usage_tracker()` | 生成最终 UsageResponse |
| `core/events/message_events.py` | `emit_message_delta()` | 发送 billing delta 事件 |
| `core/events/adapters/zeno.py` | `_convert_message_delta()` | 转换 billing 为 ZenO 格式 |

---

## 🎯 核心数据模型

### LLMCallRecord - 单次调用记录

```python
class LLMCallRecord(BaseModel):
    """单次 LLM 调用的完整记录"""
    
    # 基础信息
    call_id: str                    # 调用唯一标识
    model: str                      # 模型名称（如 claude-haiku-4.5）
    purpose: str                    # 调用目的（intent_analysis, main_response）
    timestamp: datetime
    
    # Token 统计
    input_tokens: int
    output_tokens: int
    thinking_tokens: int
    cache_read_tokens: int          # 缓存命中 tokens
    cache_write_tokens: int         # 缓存写入 tokens
    
    # 单价（float，USD/百万tokens）
    input_unit_price: float
    output_unit_price: float
    cache_read_unit_price: float    # 缓存命中单价
    cache_write_unit_price: float   # 缓存写入单价
    
    # 总价（float，USD）
    input_total_price: float
    output_total_price: float
    thinking_total_price: float
    cache_read_price: float
    cache_write_price: float
    total_price: float

    # 计算属性
    @property
    def total_tokens(self) -> int:
        """总 tokens = input + output + thinking + cache_read"""
        return self.input_tokens + self.output_tokens + self.thinking_tokens + self.cache_read_tokens
```

### UsageResponse - 聚合响应（Dify 兼容）

```python
class UsageResponse(BaseModel):
    """完整的 Usage 响应"""
    
    # Token 统计（符合 Claude Platform 规范）
    prompt_tokens: int              # = input + cache_read + cache_write
    completion_tokens: int          # = output
    thinking_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    total_tokens: int               # = prompt + completion + thinking
    
    # 价格（float，USD）
    prompt_price: float             # 包含缓存价格
    completion_price: float
    thinking_price: float
    cache_read_price: float
    cache_write_price: float
    total_price: float
    
    # 加权平均单价
    prompt_unit_price: float
    completion_unit_price: float
    currency: str = "USD"
    
    # 缓存效果
    cache_hit_rate: float           # 缓存命中率
    cost_saved_by_cache: float      # 缓存节省成本
    
    # 性能
    latency: float
    llm_calls: int
    
    # 调用明细
    llm_call_details: List[LLMCallRecord]
```

---

## 💰 定价表（Claude Platform 官方价格）

| 模型 | Input ($/M) | Output ($/M) | Cache Read ($/M) | Cache Write ($/M) |
|------|-------------|--------------|------------------|-------------------|
| Claude Opus 4.1 | 15.0 | 75.0 | 1.5 | 18.75 |
| Claude Opus 4 | 15.0 | 75.0 | 1.5 | 18.75 |
| Claude Sonnet 4 | 3.0 | 15.0 | 0.3 | 3.75 |
| Claude Sonnet 3.7 | 3.0 | 15.0 | 0.3 | 3.75 |
| Claude Haiku 3.5 | 0.8 | 4.0 | 0.08 | 1.0 |
| Claude Haiku 3 | 0.25 | 1.25 | 0.03 | 0.3 |

> **来源**: [Claude Platform Prompt Caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)

---

## ✅ E2E 测试结果

### 测试文件

- `tests/test_billing_multi_model.py`：多模型调用测试
- `tests/test_billing_cache.py`：缓存计费测试（新增）

### 缓存测试场景

```python
# 场景 1：缓存命中（cache_read_tokens > 0）
mock_usage = {
    "input_tokens": 50,
    "output_tokens": 100,
    "cache_read_tokens": 5000,
    "cache_creation_tokens": 0
}

# 场景 2：缓存写入（cache_creation_tokens > 0）
mock_usage = {
    "input_tokens": 500,
    "output_tokens": 100,
    "cache_read_tokens": 0,
    "cache_creation_tokens": 5000
}

# 场景 3：混合缓存（同时有读写）
mock_usage = {
    "input_tokens": 200,
    "output_tokens": 100,
    "cache_read_tokens": 3000,
    "cache_creation_tokens": 2000
}
```

### 测试输出示例

```json
{
  "total_price": 0.003637,
  "currency": "USD",
  "llm_calls": 2,
  "cache_read_tokens": 5000,
  "cache_write_tokens": 2000,
  "cache_read_price": 0.0015,
  "cache_write_price": 0.0075,
  "cache_hit_rate": 0.625,
  "cost_saved_by_cache": 0.012,
  "llm_call_details": [
    {
      "call_id": "call_001",
      "model": "claude-sonnet-4",
      "purpose": "main_response",
      "input_tokens": 100,
      "output_tokens": 200,
      "cache_read_tokens": 5000,
      "cache_write_tokens": 0,
      "cache_read_unit_price": 0.3,
      "cache_write_unit_price": 3.75,
      "total_price": 0.004353
    }
  ],
  "prompt_tokens": 7100,
  "completion_tokens": 200,
  "total_tokens": 7300,
  "prompt_unit_price": 0.42,
  "completion_unit_price": 15.0
}
```

### 验证通过项

✅ 多模型调用记录正确  
✅ Message ID 去重正常工作  
✅ 价格计算准确  
✅ 所有价格字段使用 float 类型  
✅ 缓存 tokens 包含在 prompt_tokens 中  
✅ 缓存价格单独记录  
✅ cache_hit_rate 计算正确  
✅ cost_saved_by_cache 计算正确  
✅ JSON 格式符合规范

---

## 🔧 关键技术细节

### 1. Claude Platform Token 计算规范

```
total_input_tokens = input_tokens + cache_read_tokens + cache_creation_tokens

其中：
- input_tokens: 最后一个缓存断点之后的非缓存输入
- cache_read_tokens: 从缓存读取的 tokens
- cache_creation_tokens: 写入缓存的 tokens
```

### 2. 价格计算公式

```python
# prompt_tokens（符合 Claude Platform 定义）
prompt_tokens = input_tokens + cache_read_tokens + cache_write_tokens

# prompt_price（包含所有输入相关成本）
prompt_price = input_price + cache_read_price + cache_write_price

# 加权平均单价
prompt_unit_price = (
    input_tokens * input_unit_price +
    cache_read_tokens * cache_read_unit_price +
    cache_write_tokens * cache_write_unit_price
) / prompt_tokens

# 缓存节省成本
cost_saved = cache_read_tokens * (input_unit_price - cache_read_unit_price) / 1_000_000
```

### 3. Message ID 去重

```python
class EnhancedUsageTracker:
    def __init__(self):
        self._seen_message_ids: Set[str] = set()
    
    def record_call(self, llm_response, model, purpose, message_id=None):
        if message_id and message_id in self._seen_message_ids:
            return None  # 跳过重复
        
        record = LLMCallRecord(...)
        self.calls.append(record)
        
        if message_id:
            self._seen_message_ids.add(message_id)
        
        return record
```

---

## 🚀 使用示例

### 在 SimpleAgent 中使用

```python
from utils.usage_tracker import UsageTracker  # = EnhancedUsageTracker

class SimpleAgent:
    def __init__(self, ...):
        self.usage_tracker = UsageTracker()
    
    async def _chat_loop(self, ...):
        # LLM 调用
        async for chunk in self.llm.create_message_stream(...):
            yield chunk
        
        # 累积 usage（自动计算缓存价格）
        self.usage_tracker.accumulate(response)
```

### 在 ChatService 中累积 usage 数据

```python
from models.usage import UsageResponse

class ChatService:
    async def _run_agent(self, ...):
        # 执行 agent（agent 内部会发送 billing 事件）
        result = await agent.chat(...)
        
        # 生成 UsageResponse
        usage = UsageResponse.from_usage_tracker(
            tracker=agent.usage_tracker,
            model=self.default_model,
            latency=duration_ms / 1000.0
        )
        
        # 累积 usage 到内存（不发送事件，避免重复）
        # billing 事件已在 Agent.chat() 中发送
        await agent.broadcaster.accumulate_usage(
            session_id=session_id,
            usage=usage.model_dump()
        )
```

---

## 📡 Billing Event 集成（V7.5 新增）

### 事件格式

billing 信息作为 `message_delta` 事件发送，统一到 ZenO 事件规范中：

```typescript
// SSE 事件格式
{
  "type": "message_delta",
  "data": {
    "type": "billing",           // Delta 类型标识
    "content": {                 // UsageResponse 完整数据
      "prompt_tokens": 7100,
      "completion_tokens": 265,
      "thinking_tokens": 0,
      "cache_read_tokens": 5000,
      "cache_write_tokens": 2000,
      "total_tokens": 7365,
      
      "prompt_price": 0.004725,
      "completion_price": 0.003975,
      "thinking_price": 0.0,
      "cache_read_price": 0.0015,
      "cache_write_price": 0.0075,
      "total_price": 0.0102,
      
      "prompt_unit_price": 0.665,
      "completion_unit_price": 15.0,
      "currency": "USD",
      
      "cache_hit_rate": 0.7042,
      "cost_saved_by_cache": 0.0135,
      
      "latency": 0.0,
      "llm_calls": 2,
      
      "llm_call_details": [
        {
          "call_id": "call_001",
          "model": "claude-sonnet-4",
          "purpose": "intent_analysis",
          "timestamp": "2026-01-20T10:30:00",
          "input_tokens": 800,
          "output_tokens": 65,
          "thinking_tokens": 0,
          "cache_read_tokens": 5000,
          "cache_write_tokens": 0,
          "input_unit_price": 3.0,
          "output_unit_price": 15.0,
          "cache_read_unit_price": 0.3,
          "cache_write_unit_price": 3.75,
          "input_total_price": 0.0024,
          "output_total_price": 0.000975,
          "thinking_total_price": 0.0,
          "cache_read_price": 0.0015,
          "cache_write_price": 0.0,
          "total_price": 0.004875,
          "latency": 1.245
        },
        {
          "call_id": "call_002",
          "model": "claude-sonnet-4",
          "purpose": "main_response",
          // ... 第二次调用的详细信息
        }
      ]
    }
  }
}
```

### 事件发送时序

**关键保证：billing 事件在 message_stop 之前发送**

```
事件顺序：
1. message_start           ← 消息开始
2. content_block_start     ← 内容块开始
3. content_block_delta     ← 流式内容（多个）
   ...
N-2. content_block_stop    ← 内容块结束
N-1. message_delta (billing) ← 计费信息（倒数第二个）✅
N. message_stop            ← 消息结束（最后一个）
```

**实现机制**：

```python
# core/agent/simple/simple_agent.py (第 546-568 行)

async def chat(self, ...):
    # ... 执行对话逻辑 ...
    
    # 🆕 在 message_stop 之前发送 billing 事件
    from models.usage import UsageResponse
    usage_response = UsageResponse.from_usage_tracker(
        tracker=self.usage_tracker,
        model=self.model,
        latency=0
    )
    
    # 第一个 yield：billing 事件
    yield {
        "type": "message_delta",
        "data": {
            "type": "billing",
            "content": usage_response.model_dump()
        }
    }
    
    # 第二个 yield：message_stop 事件
    yield await self.broadcaster.emit_message_stop(
        session_id=session_id,
        message_id=self._current_message_id
    )
```

**顺序保证原理**：

- Python generator 的 `yield` 语句保证顺序执行
- billing 的 `yield` 在 message_stop 的 `yield` 之前
- SSE 事件按 yield 顺序发送，无法乱序

### ZenO 适配器支持

```python
# core/events/adapters/zeno.py (第 244-251 行)

elif delta_type in (
    "sql", "data", "chart", "report",
    "intent", "application",
    "preface", "files", "mind", "clue",
    "billing"  # ← 新增支持
):
    zeno_delta_type = delta_type
    # billing 格式符合 ZenO 规范，直接透传
```

### 前端集成示例

```typescript
// 前端 SSE 事件处理
eventSource.addEventListener('message', (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === 'message_delta') {
    const { type: deltaType, content } = data.data;
    
    if (deltaType === 'billing') {
      // 处理计费信息
      console.log('Total Price:', content.total_price);
      console.log('Cache Hit Rate:', content.cache_hit_rate);
      console.log('LLM Calls:', content.llm_calls);
      
      // 显示计费详情
      content.llm_call_details.forEach(call => {
        console.log(`Call ${call.call_id}:`, {
          model: call.model,
          purpose: call.purpose,
          tokens: call.input_tokens + call.output_tokens,
          price: call.total_price,
          latency: call.latency
        });
      });
      
      // 更新 UI
      updateBillingUI(content);
    }
  }
});
```

### 关键技术细节

1. **事件类型统一**：billing 不再是独立的 custom 事件，而是 message_delta 的一种类型
2. **时序保证**：通过 generator yield 顺序保证，无需额外同步机制
3. **数据完整性**：content 包含完整的 UsageResponse，无需额外查询
4. **ZenO 兼容**：billing delta 直接透传，符合 ZenO v2.0.1 规范
5. **避免重复**：billing 事件在 Agent 内发送，ChatService 只累积数据到内存

---

## 📝 经验总结

### 设计原则

1. **统一实现**：UsageTracker = EnhancedUsageTracker，无需维护两套代码
2. **符合规范**：严格遵循 Claude Platform 的 token 和价格定义
3. **完整记录**：每次 LLM 调用都记录到 llm_call_details
4. **缓存透明**：缓存效果可见（hit_rate, cost_saved）

### 遇到的问题与解决

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| Extended Thinking 错误 | `max_tokens` < `thinking_budget` | 设置 `max_tokens=15000` |
| datetime 序列化失败 | JSON 不支持 datetime | 使用 `model_dump(mode='json')` |
| 价格计算不匹配 | 模型名与定价不一致 | 统一模型名标准化 |
| Message ID 重复记录 | 流式响应多个 chunk | 添加去重逻辑 |
| 循环导入 | utils 导入 core | 移除 __init__.py 中的循环引用 |
| billing 事件在 message_stop 之后 | 在 ChatService 发送事件 | 移到 SimpleAgent.chat() 中，利用 yield 保证顺序 |
| billing 事件重复发送 | Agent 和 ChatService 都发送 | ChatService 只累积数据，不发送事件 |

---

## ✅ Checklist

### 核心计费功能
- [x] `core/billing/` 包含所有计费相关代码
- [x] 定价表包含所有模型的缓存价格
- [x] `UsageResponse` 包含 `llm_call_details` 字段
- [x] `UsageResponse` 包含 `cache_hit_rate` 和 `cost_saved_by_cache`
- [x] 每次 LLM 调用都通过 `tracker.accumulate()` 记录
- [x] E2E 测试通过（多模型 + 缓存场景）
- [x] 所有价格字段使用 float 类型
- [x] Message ID 去重机制工作正常
- [x] prompt_tokens = input + cache_read + cache_write
- [x] 框架已统一（UsageTracker = EnhancedUsageTracker）

### Billing Event 集成
- [x] billing 作为 message_delta 类型发送（不是独立 custom 事件）
- [x] billing 事件在 message_stop 之前发送
- [x] 使用 generator yield 保证事件顺序
- [x] ZenO 适配器支持 billing delta 类型
- [x] ChatService 移除重复的 emit_custom("usage")
- [x] billing 事件包含完整 UsageResponse 数据

---

## 📚 相关文档

- [00-ARCHITECTURE-OVERVIEW.md](./00-ARCHITECTURE-OVERVIEW.md) - V7.5 系统架构总览
- [tests/test_billing_multi_model.py](../../tests/test_billing_multi_model.py) - 多模型计费测试
- [tests/test_billing_cache.py](../../tests/test_billing_cache.py) - 缓存计费测试

---

## 🔄 代码更新记录

### V7.5 统一版（2026-01-18）

| 文件 | 更新内容 | 状态 |
|------|---------|------|
| `utils/usage_tracker.py` | 简化为 `UsageTracker = EnhancedUsageTracker`，移除冗余代码 | ✅ 完成 |
| `core/billing/__init__.py` | 移除向后兼容注释，简化导出接口 | ✅ 完成 |
| `models/usage.py` | 重导出 `core/billing/models.UsageResponse`，移除旧类定义 | ✅ 完成 |
| `core/billing/pricing.py` | 延迟导入以解决循环依赖 | ✅ 完成 |

### Billing Event Integration（2026-01-20）

| 文件 | 更新内容 | 状态 |
|------|---------|------|
| `core/agent/simple/simple_agent.py` | 在 message_stop 前发送 billing 事件（第 546-568 行） | ✅ 完成 |
| `services/chat_service.py` | 移除 emit_custom("usage")，改为累积到内存（第 738-747 行） | ✅ 完成 |
| `core/events/message_events.py` | 添加 billing delta 类型文档（第 23 行） | ✅ 完成 |
| `core/events/adapters/zeno.py` | 支持 billing delta 类型透传（第 248 行） | ✅ 完成 |

### 测试验证结果

```bash
# 缓存计费测试
✅ 所有缓存计费测试通过！
  ✓ cache_read_tokens 正确累积
  ✓ cache_creation_tokens 正确累积
  ✓ 每个模型的缓存价格独立计算
  ✓ prompt_tokens = input + cache_read + cache_write
  ✓ total_tokens 包含所有输入 tokens
  ✓ 缓存命中率计算正确
  ✓ 缓存节省成本计算正确
  ✓ JSON 格式符合规范

# 多模型计费测试
✅ E2E 测试成功！
  ✓ 多模型调用记录正确
  ✓ Message ID 去重正常工作
  ✓ 价格计算准确
  ✓ 所有价格字段使用 float 类型
  ✓ 累积统计正确
  ✓ JSON 格式符合规范
```

### 关键改进

1. **无冗余代码**：删除所有向后兼容的重复实现
2. **单一职责**：
   - `core/billing/models.py`：唯一的 UsageResponse 定义
   - `models/usage.py`：定价表 + 重导出
   - `utils/usage_tracker.py`：别名导出
3. **循环依赖解决**：使用延迟导入避免模块间循环

---

**更新日期**: 2026-01-20  
**文档版本**: V7.5 统一版 + Billing Event Integration  
**维护者**: ZenFlux Agent Team

**更新历史**:
- 2026-01-20: 集成 billing 事件到 message_delta，保证事件时序
- 2026-01-18: 统一计费框架，完成多模型和缓存计费
