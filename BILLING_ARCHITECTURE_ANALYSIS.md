# 计费系统架构分析（V7.5 统一版）

## 1. V7.5 统一重构成果

### ✅ 框架已统一

**重构内容：**

1. **统一 Tracker 系统**
   - `UsageTracker` 现在是 `EnhancedUsageTracker` 的别名
   - 所有旧代码无需修改，完全向后兼容
   - 新代码可使用增强功能（`record_call()`, `message_id` 去重, 调用明细）

2. **符合 Claude Platform 规范**
   - `prompt_tokens = input_tokens + cache_read_tokens + cache_write_tokens`
   - `total_tokens = prompt_tokens + completion_tokens + thinking_tokens`
   - 每个模型独立的缓存价格

3. **新增功能**
   - `cache_hit_rate`: 缓存命中率
   - `cost_saved_by_cache`: 缓存节省的成本
   - `llm_call_details`: 每次调用的详细记录

## 2. 模块架构

```
core/billing/
├── __init__.py      # 统一导出接口
├── models.py        # LLMCallRecord, UsageResponse（V7.5 增强版）
├── tracker.py       # EnhancedUsageTracker（统一实现）
└── pricing.py       # 模型定价表和成本计算

utils/
└── usage_tracker.py # 向后兼容包装（UsageTracker = EnhancedUsageTracker）

models/
└── usage.py         # UsageResponse（Dify 兼容格式）+ 定价表
```

## 3. 使用方式

### 3.1 推荐方式（V7.5+）

```python
from utils.usage_tracker import create_usage_tracker
from core.billing.models import UsageResponse

# 创建 tracker
tracker = create_usage_tracker()

# 记录调用（支持多模型 + Message ID 去重）
tracker.record_call(
    llm_response=response,
    model="claude-sonnet-4.5",
    purpose="main_response",
    message_id=response.id  # 自动去重
)

# 生成响应（包含完整调用明细）
usage = UsageResponse.from_tracker(tracker, latency=2.0)
print(f"调用明细: {len(usage.llm_call_details)} 次")
print(f"缓存命中率: {usage.cache_hit_rate:.2%}")
print(f"缓存节省: ${usage.cost_saved_by_cache}")
```

### 3.2 旧方式（仍然兼容）

```python
from utils.usage_tracker import create_usage_tracker

tracker = create_usage_tracker()

# 旧接口完全兼容
tracker.accumulate(llm_response)
stats = tracker.get_stats()
print(f"总 input tokens: {stats['total_input_tokens']}")
```

## 4. Token 计算规范

遵循 [Claude Platform 规范](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)：

```
total_input_tokens = input_tokens + cache_read_input_tokens + cache_creation_input_tokens
                     ↓              ↓                        ↓
                 未缓存部分      缓存命中部分              缓存创建部分
```

### 4.1 JSON 响应示例

```json
{
  "prompt_tokens": 7100,       // input + cache_read + cache_write
  "completion_tokens": 200,
  "thinking_tokens": 300,
  "cache_read_tokens": 5000,   // 缓存命中
  "cache_write_tokens": 2000,  // 缓存创建
  "total_tokens": 7600,        // prompt + completion + thinking
  "prompt_price": 0.0003,      // input 价格
  "cache_read_price": 0.0015,  // 缓存命中价格（90% 折扣）
  "cache_write_price": 0.0075, // 缓存创建价格（25% 加价）
  "total_price": 0.0168,
  "cache_hit_rate": 0.9804,    // 缓存命中率
  "cost_saved_by_cache": 0.0135,
  "llm_call_details": [...]    // 每次调用的详细记录
}
```

## 5. 定价表

### 5.1 Claude 4.5 系列（2026-01）

| 模型 | Input | Output | Cache Write | Cache Read |
|------|-------|--------|-------------|------------|
| claude-opus-4.5 | $5.0/M | $25.0/M | $6.25/M | $0.5/M |
| claude-sonnet-4.5 | $3.0/M | $15.0/M | $3.75/M | $0.3/M |
| claude-haiku-4.5 | $1.0/M | $5.0/M | $1.25/M | $0.1/M |

### 5.2 旧版模型（参考）

| 模型 | Input | Output | Cache Write | Cache Read |
|------|-------|--------|-------------|------------|
| claude-opus-4 | $15.0/M | $75.0/M | $18.75/M | $1.5/M |
| claude-sonnet-4 | $3.0/M | $15.0/M | $3.75/M | $0.3/M |
| claude-haiku-3.5 | $0.8/M | $4.0/M | $1.0/M | $0.08/M |

## 6. 测试验证

### ✅ 通过的测试

1. **缓存计费测试** (`tests/test_billing_cache.py`)
   - 缓存命中场景
   - 缓存写入场景
   - 混合场景（多次调用）
   - 多模型 + 缓存
   - JSON 格式验证

2. **多模型计费测试** (`tests/test_billing_multi_model.py`)
   - 多模型调用记录
   - Message ID 去重
   - 价格计算验证
   - 类型验证（int/float）

### 验证命令

```bash
# 运行缓存计费测试
python tests/test_billing_cache.py

# 运行多模型计费测试
python tests/test_billing_multi_model.py
```

## 7. 智能体框架调用路径

### 7.1 单智能体路径

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
      EnhancedUsageTracker 记录调用
        ↓
      ChatService 生成 UsageResponse
        ↓
      发送 SSE 事件 {"event": "usage", "data": {...}}
```

### 7.2 多智能体路径

```
用户请求
  ↓
ChatService._run_agent()
  ↓
AgentRouter.route() → 决定单/多智能体
  ↓
MultiAgentOrchestrator.execute() (core/agent/multi/orchestrator.py)
  │
  ├─→ 子智能体 1 (Agent A)
  │     └─→ Agent A.usage_tracker
  │
  ├─→ 子智能体 2 (Agent B)
  │     └─→ Agent B.usage_tracker
  │
  └─→ orchestrator._accumulate_subagent_usage()
        ↓
      汇总所有子智能体的 usage
```

## 8. 关键改进（V7.5）

| 特性 | V7.5 之前 | V7.5 之后 |
|------|-----------|-----------|
| Tracker 实现 | 两套独立系统 | 统一为 EnhancedUsageTracker |
| 向后兼容 | - | ✅ 旧代码无需修改 |
| Message ID 去重 | ❌ 不支持 | ✅ 支持 |
| 调用明细 | ❌ 无 | ✅ llm_call_details |
| 多模型支持 | ⚠️ 混合统计 | ✅ 分别记录 |
| 缓存效果可见性 | ⚠️ 有限 | ✅ cache_hit_rate, cost_saved_by_cache |
| 符合 Claude 规范 | ⚠️ 部分 | ✅ 完全符合 |

## 9. 注意事项

1. **循环导入问题**
   - `utils/usage_tracker.py` 和 `core/billing/__init__.py` 之间有依赖
   - 解决方案：`core/billing/__init__.py` 不再从 `utils` 导入，而是直接使用别名

2. **价格字段类型**
   - `core/billing/models.py` 中的 `UsageResponse` 使用 `float` 类型
   - `models/usage.py` 中的 `UsageResponse` 使用 `str` 类型（Dify 兼容）
   - 两者可以共存，根据场景选择使用

3. **Thinking Token 计费**
   - Extended Thinking 使用 output 价格计费
   - 已在 `models/usage.py` 的 `from_usage_tracker()` 中正确处理

---

**生成时间**：2026-01-18
**文档版本**：2.0（V7.5 统一重构后）
