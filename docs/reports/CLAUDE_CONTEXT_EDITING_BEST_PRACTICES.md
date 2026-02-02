# Claude Context Editing 最佳实践指南

> **日期**: 2026-01-15  
> **版本**: V7.0  
> **参考**: [Claude Platform 官方文档](https://platform.claude.com/docs/en/build-with-claude/context-editing)

---

## 一、文档核心建议总结

### 1.1 使用时机和场景

根据官方文档，Context Editing 适用于以下场景：

**✅ 推荐使用**：
- **工具调用频繁的场景**：每次对话有大量工具调用（>10 次）
- **长对话场景**：对话轮次多，上下文快速增长
- **成本优化需求**：需要控制 token 消耗
- **上下文窗口限制**：接近或超过上下文窗口限制

**❌ 不推荐使用**：
- 短对话（<10 轮）
- 需要完整工具结果历史的场景
- 调试阶段（需要查看完整上下文）

### 1.2 与 Prompt Caching 的交互（关键）

**重要提示**：Context Editing 与 Prompt Caching 的交互需要特别注意：

#### Tool Result Clearing
- **会失效缓存**：清理工具结果时，会失效缓存的 prompt prefix
- **建议**：使用 `clear_at_least` 参数，确保每次清理足够的 tokens，以抵消缓存失效的成本
- **文档原文**：
  > "We recommend clearing enough tokens to make the cache invalidation worthwhile. Use the `clear_at_least` parameter to ensure a minimum number of tokens is cleared each time."

#### Thinking Block Clearing
- **保留 thinking blocks**：如果保留 thinking blocks，可以保持缓存，实现缓存命中
- **清理 thinking blocks**：如果清理 thinking blocks，会在清理点失效缓存
- **最大化缓存命中**：设置 `keep: "all"` 可以保留所有 thinking blocks，最大化缓存命中率

### 1.3 默认行为

**Extended Thinking 的默认行为**：
- 如果启用 Extended Thinking 但**未配置** `clear_thinking_20251015`，API 默认只保留最后一轮的 thinking blocks
- 等价于：`keep: {type: "thinking_turns", value: 1}`
- **要最大化缓存命中**：需要显式设置 `keep: "all"`

---

## 二、当前实现分析

### 2.1 实现状态

**✅ 已实现**：
- Tool result clearing 配置格式正确
- Thinking block clearing 配置格式正确
- `clear_at_least` 自动计算（根据 Prompt Caching 状态）
- 默认排除服务端工具（`web_search`, `web_fetch`）
- 支持 `keep_all_thinking`（`keep: "all"`）
- 自适应触发：上下文长度为主，轮次/工具结果为辅

**✅ 已优化**：
- 触发阈值按上下文窗口比例自动计算（默认 70%）
- 轮次与工具结果作为提前触发信号（接近阈值时生效）

### 2.2 配置建议对比

| 参数 | 当前默认值 | 文档建议 | 说明 |
|------|-----------|---------|------|
| `trigger_threshold` | 0.7 * context_window | 30000 | ✅ 与上下文窗口关联 |
| `keep_tool_uses` | 10 | 3-10 | ✅ 合理 |
| `clear_at_least` | 自动计算 | **更大值** | ✅ 已根据缓存自动调整 |
| `exclude_tools` | web_search/web_fetch | 建议排除 `web_search` | ✅ 已默认排除 |

---

## 三、优化建议

> 说明：以下优化已在代码中落地，保留作为最佳实践参考。

### 3.1 优化 `clear_at_least` 参数

**问题**：当前默认值 5000 可能不够大，无法抵消缓存失效的成本。

**建议**：
- 如果启用 Prompt Caching，`clear_at_least` 应该设置得更大（如 10000-15000）
- 如果未启用 Prompt Caching，可以使用较小的值（如 3000-5000）

**实现建议**：
```python
def enable_context_editing(
    self,
    clear_tool_uses: bool = True,
    clear_thinking: bool = False,
    trigger_threshold: int = 30000,
    keep_tool_uses: int = 10,
    clear_at_least: Optional[int] = None,  # 自动计算
    exclude_tools: Optional[List[str]] = None
):
    # 如果未指定 clear_at_least，根据 Prompt Caching 状态自动计算
    if clear_at_least is None:
        if self.config.enable_caching:
            # 启用缓存时，需要清理更多 tokens 以抵消缓存失效成本
            clear_at_least = max(10000, trigger_threshold // 3)
        else:
            # 未启用缓存时，可以使用较小的值
            clear_at_least = max(3000, trigger_threshold // 6)
```

### 3.2 支持 `keep: "all"` 选项

**问题**：当前只支持 `keep: {type: "thinking_turns", value: 1}`，不支持 `keep: "all"`。

**建议**：添加 `keep_all_thinking` 参数，支持最大化缓存命中。

**实现建议**：
```python
def enable_context_editing(
    self,
    ...
    clear_thinking: bool = False,
    keep_all_thinking: bool = False,  # 🆕 保留所有 thinking blocks
    ...
):
    # Thinking block clearing
    if clear_thinking:
        if keep_all_thinking:
            # 最大化缓存命中：保留所有 thinking blocks
            edits.append({
                "type": "clear_thinking_20251015",
                "keep": "all"
            })
        else:
            # 默认：只保留最后一轮的 thinking
            edits.append({
                "type": "clear_thinking_20251015",
                "keep": {
                    "type": "thinking_turns",
                    "value": 1
                }
            })
```

### 3.3 智能排除工具

**建议**：根据文档建议，默认排除 `web_search` 等服务端工具。

**原因**：
- 服务端工具（如 `web_search`）的结果通常很重要，不应该被清理
- 文档示例中也建议排除 `web_search`

**实现建议**：
```python
def enable_context_editing(
    self,
    ...
    exclude_tools: Optional[List[str]] = None
):
    # 默认排除服务端工具
    default_exclude = ["web_search", "web_fetch"]
    
    if exclude_tools is None:
        exclude_tools = default_exclude
    else:
        # 合并用户指定的排除工具
        exclude_tools = list(set(exclude_tools + default_exclude))
```

### 3.4 根据对话长度自动启用

**建议**：在长对话场景下自动启用 Context Editing。

**实现建议**：
```python
# 在 SimpleAgent 或 ChatService 中
async def _should_enable_context_editing(self, messages: List[Dict]) -> bool:
    """判断是否应该启用 Context Editing"""
    # 估算当前 token 使用量
    estimated_tokens = sum(len(str(msg.get("content", ""))) // 4 for msg in messages)
    
    # 如果超过阈值，建议启用
    return estimated_tokens > 20000  # 20K tokens
```

---

## 四、推荐配置方案

### 4.1 标准配置（推荐）

**适用场景**：大多数生产环境

```python
llm.enable_context_editing(
    clear_tool_uses=True,
    trigger_threshold=30000,      # 30K tokens 时触发
    keep_tool_uses=10,            # 保留最近 10 个工具调用
    clear_at_least=10000,          # 每次至少清理 10K tokens（考虑缓存成本）
    exclude_tools=["web_search"]    # 排除服务端工具
)
```

### 4.2 成本优化配置（激进）

**适用场景**：成本敏感，需要严格控制 token 消耗

```python
llm.enable_context_editing(
    clear_tool_uses=True,
    clear_thinking=True,           # 同时清理 thinking blocks
    trigger_threshold=20000,       # 20K tokens 时触发（更早触发）
    keep_tool_uses=5,              # 只保留最近 5 个工具调用
    clear_at_least=15000,           # 每次至少清理 15K tokens
    exclude_tools=["web_search", "memory"]  # 排除关键工具
)
```

### 4.3 缓存优化配置（保守）

**适用场景**：启用 Prompt Caching，需要最大化缓存命中率

```python
llm.enable_context_editing(
    clear_tool_uses=True,
    clear_thinking=True,
    keep_all_thinking=True,        # 🆕 保留所有 thinking blocks（最大化缓存命中）
    trigger_threshold=40000,       # 40K tokens 时触发（较晚触发）
    keep_tool_uses=15,             # 保留更多工具调用
    clear_at_least=12000,          # 每次至少清理 12K tokens
    exclude_tools=["web_search"]
)
```

### 4.4 长对话专用配置

**适用场景**：超长对话（>100 轮），需要持续清理

```python
llm.enable_context_editing(
    clear_tool_uses=True,
    trigger_threshold=25000,       # 25K tokens 时触发
    keep_tool_uses=8,              # 保留最近 8 个工具调用
    clear_at_least=8000,           # 每次至少清理 8K tokens
    exclude_tools=["web_search", "memory", "plan_todo"]  # 排除关键工具
)
```

---

## 五、监控和调试

### 5.1 监控指标

**建议监控**：
- Context Editing 触发次数
- 每次清理的 token 数量
- 清理的工具调用数量
- 缓存命中率变化（如果启用 Prompt Caching）

### 5.2 调试建议

**启用详细日志**：
```python
import logging
logging.getLogger("core.llm.claude").setLevel(logging.DEBUG)
```

**检查 API 响应**：
```python
# 检查是否应用了 Context Editing
if hasattr(response, "context_management"):
    applied_edits = getattr(response.context_management, "applied_edits", [])
    if applied_edits:
        logger.info(f"Context Editing 已应用: {applied_edits}")
```

---

## 六、实施计划

### P0（高优先级）

1. **优化 `clear_at_least` 自动计算**
   - 根据 Prompt Caching 状态自动调整
   - 确保清理足够的 tokens 以抵消缓存成本

2. **支持 `keep: "all"` 选项**
   - 添加 `keep_all_thinking` 参数
   - 支持最大化缓存命中率

### P1（中优先级）

1. **智能排除工具**
   - 默认排除服务端工具（`web_search`, `web_fetch`）
   - 允许用户自定义排除列表

2. **配置化支持**
   - 在 `config/context_compaction.yaml` 中添加 Context Editing 配置
   - 支持根据场景自动选择配置方案

### P2（低优先级）

1. **自动启用机制**
   - 根据对话长度自动启用 Context Editing
   - 根据工具调用频率自动调整参数

2. **监控和告警**
   - 添加 Context Editing 触发统计
   - 监控缓存命中率变化

---

## 七、参考文档

- [Claude Platform: Context Editing](https://platform.claude.com/docs/en/build-with-claude/context-editing)
- [上下文管理架构决策](docs/architecture/context_management_decision.md)
- [详细分析报告](CLAUDE_CONTEXT_EDITING_SUPPORT.md)

---

## 八、关键要点总结

1. **`clear_at_least` 很重要**：确保清理足够的 tokens 以抵消缓存失效成本
2. **`keep: "all"` 可最大化缓存命中**：如果启用 Extended Thinking 和 Prompt Caching，建议使用
3. **排除服务端工具**：默认排除 `web_search` 等关键工具
4. **根据场景选择配置**：不同场景需要不同的配置方案
5. **监控和调试**：启用详细日志，监控 Context Editing 的效果
