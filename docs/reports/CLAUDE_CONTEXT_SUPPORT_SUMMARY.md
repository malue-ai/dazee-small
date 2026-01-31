# Claude Context Editing & Compression 支持总结

> **日期**: 2026-01-15  
> **版本**: V7.0  
> **状态**: ✅ 已修复 Context Editing，❌ 不支持 Client-side Compaction

---

## 一、支持情况

### ✅ Server-side Context Editing（服务端自动清理）

**状态**: ✅ **已支持**（已修复配置格式）

**功能**:
- ✅ Tool result clearing (`clear_tool_uses_20250919`)
- ✅ Thinking block clearing (`clear_thinking_20251015`)

**使用方法**:
```python
from core.llm.claude import ClaudeLLMService

llm = ClaudeLLMService(config)

# 标准配置（推荐，自动优化）
llm.enable_context_editing(
    clear_tool_uses=True,      # 清理工具结果
    trigger_threshold=30000,    # 触发阈值（input_tokens）
    keep_tool_uses=10         # 保留最近 N 个工具调用
    # clear_at_least 和 exclude_tools 自动计算/设置
)

# 缓存优化配置（最大化缓存命中率）
llm.enable_context_editing(
    clear_tool_uses=True,
    clear_thinking=True,
    keep_all_thinking=True,    # 🆕 保留所有 thinking blocks
    trigger_threshold=30000,
    keep_tool_uses=10
)
```

**API 格式**（已修复）:
```python
context_management = {
    "edits": [
        {
            "type": "clear_tool_uses_20250919",
            "trigger": {"type": "input_tokens", "value": 30000},
            "keep": {"type": "tool_uses", "value": 10},
            "clear_at_least": {"type": "input_tokens", "value": 5000}
        }
    ]
}
```

### ❌ Client-side Compaction（客户端自动压缩）

**状态**: ❌ **不支持**

**原因**:
- 项目使用 `messages.stream()` + 自主 RVR 循环架构
- 不使用 `tool_runner`，因此无法使用 SDK 的自动 compaction
- 架构决策：保持当前架构，使用自己的三层防护策略

**替代方案**:
- ✅ L1: Memory Tool 状态保存（Claude 自主）
- ✅ L2: 历史消息智能裁剪（服务层自动）
- ✅ L3: QoS 成本控制（后端静默）

详见：[上下文管理架构决策](docs/architecture/context_management_decision.md)

---

## 二、修复和优化内容

### 2.1 修复 Context Editing 配置格式

**文件**: `core/llm/claude.py`

**修改**:
- ✅ 修复 `enable_context_editing()` 方法，使用正确的 API 格式
- ✅ 支持 `clear_tool_uses_20250919` 和 `clear_thinking_20251015` 两种策略
- ✅ 添加完整的配置参数（trigger_threshold, keep_tool_uses, clear_at_least, exclude_tools）

**修复前**（错误格式）:
```python
self._context_editing_config = {
    "mode": "progressive",
    "clear_threshold": 150000,
    "retain_tool_uses": 10
}
```

**修复后**（正确格式）:
```python
self._context_editing_config = {
    "edits": [
        {
            "type": "clear_tool_uses_20250919",
            "trigger": {"type": "input_tokens", "value": 30000},
            "keep": {"type": "tool_uses", "value": 10},
            "clear_at_least": {"type": "input_tokens", "value": 5000}
        }
    ]
}
```

### 2.2 根据文档最佳实践优化（🆕）

**优化内容**（基于官方文档建议）:

1. **✅ 自动计算 `clear_at_least`**
   - 根据 Prompt Caching 状态自动调整
   - 启用缓存时：`max(10000, trigger_threshold // 3)`（确保清理足够的 tokens 以抵消缓存成本）
   - 未启用缓存时：`max(3000, trigger_threshold // 6)`

2. **✅ 支持 `keep: "all"` 选项**
   - 新增 `keep_all_thinking` 参数
   - 支持最大化缓存命中率（保留所有 thinking blocks）

3. **✅ 智能排除服务端工具**
   - 默认排除 `web_search` 和 `web_fetch`
   - 允许用户自定义排除列表

**优化后的使用示例**:
```python
# 标准配置（自动优化）
llm.enable_context_editing(
    clear_tool_uses=True,
    trigger_threshold=30000,
    keep_tool_uses=10
    # clear_at_least 和 exclude_tools 自动计算/设置
)

# 缓存优化配置（最大化缓存命中）
llm.enable_context_editing(
    clear_tool_uses=True,
    clear_thinking=True,
    keep_all_thinking=True,  # 🆕 保留所有 thinking blocks
    trigger_threshold=30000,
    keep_tool_uses=10
)
```

---

## 三、使用建议

### 3.1 何时启用 Context Editing

**推荐场景**:
- ✅ 长对话场景（>50 轮）
- ✅ 工具调用频繁的场景（每次对话 >10 次工具调用）
- ✅ 需要控制 token 成本的场景

**不推荐场景**:
- ❌ 短对话（<10 轮）
- ❌ 需要完整工具结果历史的场景
- ❌ 调试阶段（需要查看完整上下文）

### 3.2 配置建议

**默认配置**（推荐）:
```python
llm.enable_context_editing(
    clear_tool_uses=True,
    trigger_threshold=30000,  # 30K tokens 时触发
    keep_tool_uses=10,        # 保留最近 10 个工具调用
    clear_at_least=5000      # 每次至少清理 5K tokens
)
```

**激进配置**（更严格的成本控制）:
```python
llm.enable_context_editing(
    clear_tool_uses=True,
    clear_thinking=True,      # 同时清理 thinking blocks
    trigger_threshold=20000,  # 20K tokens 时触发
    keep_tool_uses=5,         # 只保留最近 5 个工具调用
    clear_at_least=10000      # 每次至少清理 10K tokens
)
```

**保守配置**（保留更多上下文）:
```python
llm.enable_context_editing(
    clear_tool_uses=True,
    trigger_threshold=50000,  # 50K tokens 时触发
    keep_tool_uses=20,        # 保留最近 20 个工具调用
    clear_at_least=3000      # 每次至少清理 3K tokens
)
```

### 3.3 与三层防护策略的协同

**推荐配置**:
- ✅ 启用 Context Editing：自动清理工具结果（减少 token 消耗）
- ✅ 启用 L2 历史裁剪：保留关键消息（保证上下文连续性）

**协同效果**:
- Context Editing 清理工具结果（服务端自动）
- L2 裁剪保留关键消息（客户端智能）
- 两者协同，既控制成本又保证效果

---

## 四、与现有架构的兼容性

### 4.1 与 Prompt Caching

**兼容**: ✅ Context Editing 与 Prompt Caching 兼容

**注意事项**:
- Tool result clearing 会失效缓存（需要重新写入）
- Thinking block clearing 保留缓存（如果保留 thinking blocks）

### 4.2 与 Extended Thinking

**兼容**: ✅ 支持清理 thinking blocks

**配置**:
```python
llm.enable_context_editing(
    clear_tool_uses=True,
    clear_thinking=True,  # 清理 thinking blocks
    ...
)
```

**默认行为**:
- 如果启用 Extended Thinking 但未配置 `clear_thinking_20251015`，API 默认只保留最后一轮的 thinking blocks
- 要保留所有 thinking blocks，需要设置 `keep: "all"`（当前实现中未支持，需要扩展）

### 4.3 与 Memory Tool

**兼容**: ✅ 不冲突

**说明**:
- Context Editing 清理工具结果，但不影响 Memory Tool 的存储
- Memory Tool 的状态保存在服务端，不受 Context Editing 影响

---

## 五、后续优化建议

### P1（中优先级）

1. **配置化支持**
   - 在 `config/context_compaction.yaml` 中添加 Context Editing 配置
   - 在 Agent 初始化时根据配置自动启用

2. **监控指标**
   - 添加 Context Editing 触发次数统计
   - 监控清理的 token 数量
   - 记录清理的工具调用数量

3. **文档完善**
   - 更新架构文档，说明 Context Editing 的使用方式
   - 添加配置示例和最佳实践

### P2（低优先级）

1. **高级配置**
   - 支持 `keep: "all"` 选项（保留所有 thinking blocks）
   - 支持 `clear_tool_inputs` 选项（同时清理工具调用参数）

2. **智能触发**
   - 根据对话历史自动调整触发阈值
   - 根据工具类型选择性地清理

---

## 六、参考文档

- [Claude Platform: Context Editing](https://platform.claude.com/docs/en/build-with-claude/context-editing)
- [上下文管理架构决策](docs/architecture/context_management_decision.md)
- [上下文压缩策略](docs/guides/context_compression_strategy.md)
- [详细分析报告](CLAUDE_CONTEXT_EDITING_SUPPORT.md)

---

## 七、总结

| 功能 | 状态 | 说明 |
|------|------|------|
| **Server-side Context Editing** | ✅ 已支持 | 已修复配置格式，可直接使用 |
| - Tool result clearing | ✅ 已支持 | 符合 API 规范 |
| - Thinking block clearing | ✅ 已支持 | 符合 API 规范 |
| **Client-side Compaction** | ❌ 不支持 | 不使用 `tool_runner` |
| **替代方案（三层防护）** | ✅ 已实现 | L1/L2/L3 策略已完整实现 |

**结论**: 
- ✅ Context Editing 已修复并优化，符合官方文档最佳实践
- ✅ 自动优化 `clear_at_least`（根据 Prompt Caching 状态）
- ✅ 支持 `keep: "all"` 选项（最大化缓存命中率）
- ✅ 智能排除服务端工具（默认排除 `web_search`）
- ❌ Client-side Compaction 不支持，使用三层防护策略替代
- ✅ 两者可以协同工作，实现更好的上下文管理

**详细最佳实践指南**: 参见 [CLAUDE_CONTEXT_EDITING_BEST_PRACTICES.md](CLAUDE_CONTEXT_EDITING_BEST_PRACTICES.md)
