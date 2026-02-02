# Claude Context Editing & Compression 支持分析报告

> **日期**: 2026-01-15  
> **版本**: V7.0  
> **状态**: 部分支持，需要修复

---

## 一、功能概述

根据 [Claude Platform 官方文档](https://platform.claude.com/docs/en/build-with-claude/context-editing)，Claude 提供了两种上下文管理方式：

### 1.1 Server-side Context Editing（服务端）

**功能**：在 API 层面自动清理对话历史，无需客户端处理。

**策略**：
- `clear_tool_uses_20250919`: 自动清理工具结果
- `clear_thinking_20251015`: 自动清理 thinking blocks

**优势**：
- 服务端处理，客户端无需修改
- 与 Prompt Caching 兼容
- 自动触发，无需手动管理

### 1.2 Client-side Compaction（客户端）

**功能**：SDK 的 `tool_runner` 模式提供的自动压缩功能。

**工作原理**：
1. 监控 token 使用量
2. 超过阈值时生成摘要
3. 替换完整历史为摘要
4. 继续执行任务

**限制**：
- 仅在使用 `tool_runner` 时可用
- 需要重构核心循环（从 `messages.stream()` 切换到 `tool_runner`）

---

## 二、当前实现状态

### 2.1 Context Editing（服务端）✅ 部分支持

**代码位置**: `core/llm/claude.py`

**当前实现**:
```python
def enable_context_editing(
    self,
    mode: str = "progressive",
    clear_threshold: int = 150000,
    retain_tool_uses: int = 10
):
    """启用 Context Editing"""
    self._context_editing_enabled = True
    self._context_editing_config = {
        "mode": mode,
        "clear_threshold": clear_threshold,
        "retain_tool_uses": retain_tool_uses
    }
    self._add_beta("context-management-2025-06-27")
```

**问题**：
1. ❌ **配置格式不正确**：当前格式不符合 Claude API 规范
2. ❌ **未在 API 调用中使用**：虽然设置了 `request_params["context_management"]`，但格式错误
3. ❌ **未启用**：代码中没有任何地方调用 `enable_context_editing()`

**正确格式**（根据官方文档）：
```python
context_management = {
    "edits": [
        {
            "type": "clear_tool_uses_20250919",
            "trigger": {
                "type": "input_tokens",
                "value": 30000
            },
            "keep": {
                "type": "tool_uses",
                "value": 3
            },
            "clear_at_least": {
                "type": "input_tokens",
                "value": 5000
            }
        }
    ]
}
```

### 2.2 Context Compression（客户端）❌ 不支持

**原因**：
- 项目使用 `messages.stream()` + 自主 RVR 循环架构
- 不使用 `tool_runner`，因此无法使用 SDK 的自动 compaction
- 架构决策：保持当前架构，使用自己的三层防护策略

**替代方案**：
- ✅ L1: Memory Tool 状态保存（Claude 自主）
- ✅ L2: 历史消息智能裁剪（服务层自动）
- ✅ L3: QoS 成本控制（后端静默）

详见：[上下文管理架构决策](docs/architecture/context_management_decision.md)

---

## 三、修复方案

### 3.1 修复 Context Editing 配置格式

**文件**: `core/llm/claude.py`

**修改点 1**: `enable_context_editing()` 方法

```python
def enable_context_editing(
    self,
    clear_tool_uses: bool = True,
    clear_thinking: bool = False,
    trigger_threshold: int = 30000,  # input_tokens
    keep_tool_uses: int = 10,
    clear_at_least: int = 5000,  # input_tokens
    exclude_tools: Optional[List[str]] = None
):
    """
    启用 Context Editing（服务端自动清理）
    
    Args:
        clear_tool_uses: 是否清理工具结果
        clear_thinking: 是否清理 thinking blocks
        trigger_threshold: 触发清理的 token 阈值
        keep_tool_uses: 保留最近 N 个工具调用
        clear_at_least: 每次至少清理的 token 数
        exclude_tools: 排除的工具列表（不清理）
    """
    self._context_editing_enabled = True
    
    edits = []
    
    # Tool result clearing
    if clear_tool_uses:
        tool_edit = {
            "type": "clear_tool_uses_20250919",
            "trigger": {
                "type": "input_tokens",
                "value": trigger_threshold
            },
            "keep": {
                "type": "tool_uses",
                "value": keep_tool_uses
            },
            "clear_at_least": {
                "type": "input_tokens",
                "value": clear_at_least
            }
        }
        if exclude_tools:
            tool_edit["exclude_tools"] = exclude_tools
        edits.append(tool_edit)
    
    # Thinking block clearing
    if clear_thinking:
        edits.append({
            "type": "clear_thinking_20251015",
            "keep": {
                "type": "thinking_turns",
                "value": 1  # 默认只保留最后一轮的 thinking
            }
        })
    
    self._context_editing_config = {
        "edits": edits
    }
    
    self._add_beta("context-management-2025-06-27")
    logger.info(f"✅ Context Editing 已启用: {len(edits)} 个策略")
```

**修改点 2**: `create_message_async()` 和 `create_message_stream()` 方法

当前代码（第 700-702 行）：
```python
# Context Editing
if self._context_editing_enabled:
    request_params["context_management"] = self._context_editing_config
```

✅ 已正确，但需要确保 `_context_editing_config` 格式正确。

### 3.2 添加配置选项

**文件**: `config/context_compaction.yaml`

添加 Context Editing 配置段：

```yaml
# Context Editing（服务端自动清理）
context_editing:
  enabled: false  # 默认禁用（需要显式启用）
  
  # Tool result clearing
  clear_tool_uses: true
  trigger_threshold: 30000  # input_tokens
  keep_tool_uses: 10
  clear_at_least: 5000  # input_tokens
  exclude_tools: []  # 不清理的工具列表
  
  # Thinking block clearing
  clear_thinking: false
  keep_thinking_turns: 1  # 保留最近 N 轮的 thinking
```

### 3.3 在 Agent 初始化时启用

**文件**: `core/agent/simple/simple_agent.py` 或 `services/chat_service.py`

在 LLM 服务初始化后，根据配置启用 Context Editing：

```python
# 在 SimpleAgent.__init__() 或 ChatService.__init__() 中
if self.llm_service and isinstance(self.llm_service, ClaudeLLMService):
    # 从配置加载
    from config.context_compaction import load_context_editing_config
    ctx_editing_config = load_context_editing_config()
    
    if ctx_editing_config.get("enabled", False):
        self.llm_service.enable_context_editing(
            clear_tool_uses=ctx_editing_config.get("clear_tool_uses", True),
            clear_thinking=ctx_editing_config.get("clear_thinking", False),
            trigger_threshold=ctx_editing_config.get("trigger_threshold", 30000),
            keep_tool_uses=ctx_editing_config.get("keep_tool_uses", 10),
            clear_at_least=ctx_editing_config.get("clear_at_least", 5000),
            exclude_tools=ctx_editing_config.get("exclude_tools", [])
        )
```

---

## 四、支持情况总结

| 功能 | 状态 | 说明 |
|------|------|------|
| **Server-side Context Editing** | ⚠️ 部分支持 | 代码框架存在，但配置格式错误，未启用 |
| - Tool result clearing | ⚠️ 需修复 | 需要修复配置格式 |
| - Thinking block clearing | ⚠️ 需修复 | 需要修复配置格式 |
| **Client-side Compaction** | ❌ 不支持 | 不使用 `tool_runner`，使用自己的三层防护策略 |
| **替代方案（三层防护）** | ✅ 已实现 | L1/L2/L3 策略已完整实现 |

---

## 五、推荐行动

### P0（高优先级）

1. **修复 Context Editing 配置格式**
   - 修改 `enable_context_editing()` 方法，使用正确的 API 格式
   - 确保 `context_management` 参数格式符合官方规范

2. **添加配置支持**
   - 在 `config/context_compaction.yaml` 中添加 Context Editing 配置
   - 在 Agent 初始化时根据配置自动启用

3. **测试验证**
   - 验证 Context Editing 是否正常工作
   - 验证与 Prompt Caching 的兼容性

### P1（中优先级）

1. **文档更新**
   - 更新架构文档，说明 Context Editing 的使用方式
   - 添加配置示例

2. **监控指标**
   - 添加 Context Editing 触发次数统计
   - 监控清理的 token 数量

---

## 六、与现有架构的兼容性

### 6.1 与三层防护策略的关系

**不冲突**：Context Editing 是服务端自动清理，三层防护是客户端策略。

**协同工作**：
- Context Editing：服务端自动清理工具结果和 thinking blocks
- L1/L2/L3：客户端智能裁剪历史消息

**推荐配置**：
- 启用 Context Editing：自动清理工具结果（减少 token 消耗）
- 启用 L2 历史裁剪：保留关键消息（保证上下文连续性）

### 6.2 与 Prompt Caching 的关系

**兼容**：根据官方文档，Context Editing 与 Prompt Caching 兼容。

**注意事项**：
- Tool result clearing 会失效缓存（需要重新写入）
- Thinking block clearing 保留缓存（如果保留 thinking blocks）

---

## 七、参考文档

- [Claude Platform: Context Editing](https://platform.claude.com/docs/en/build-with-claude/context-editing)
- [上下文管理架构决策](docs/architecture/context_management_decision.md)
- [上下文压缩策略](docs/guides/context_compression_strategy.md)

---

## 附录：API 格式示例

### 完整 Context Editing 配置

```python
context_management = {
    "edits": [
        {
            "type": "clear_tool_uses_20250919",
            "trigger": {
                "type": "input_tokens",
                "value": 30000
            },
            "keep": {
                "type": "tool_uses",
                "value": 3
            },
            "clear_at_least": {
                "type": "input_tokens",
                "value": 5000
            },
            "exclude_tools": ["web_search"]  # 可选
        },
        {
            "type": "clear_thinking_20251015",
            "keep": {
                "type": "thinking_turns",
                "value": 1
            }
        }
    ]
}
```

### 最小配置（仅清理工具结果）

```python
context_management = {
    "edits": [
        {"type": "clear_tool_uses_20250919"}
    ]
}
```
