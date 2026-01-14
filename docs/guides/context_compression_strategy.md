# 输入上下文压缩策略（最终版）

## 🎯 设计目标

**用户体验和问答效果优先**

| 优先级 | 目标 | 实现 |
|--------|------|------|
| P0 | 不因上下文过长导致报错 | 三层防护策略 |
| P1 | 保证问答效果（不丢关键信息） | 智能裁剪逻辑 |
| P2 | 用户完全无感知 | 静默处理 |
| P3 | 成本可控 | QoS 分级 |

---

## 🏗️ 三层防护架构

```
┌─────────────────────────────────────────────────────────────┐
│                   用户体验优先的上下文管理                   │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  L1. Memory Tool 状态保存（Claude 自主）             │   │
│  │      → System Prompt 中指导 Claude 使用 memory 工具 │   │
│  │      → 跨 context window 保持状态连续性             │   │
│  │      → 由 Claude 自主决定保存什么                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                            ↓                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  L2. 历史消息智能裁剪（服务层自动）                  │   │
│  │      → 保留首轮对话（建立任务上下文）               │   │
│  │      → 保留最近 N 轮（当前工作上下文）              │   │
│  │      → 保留关键 tool_result（含文件/数据）          │   │
│  │      → 中间轮次丢弃细节                             │   │
│  └─────────────────────────────────────────────────────┘   │
│                            ↓                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  L3. QoS 成本控制（后端静默）                        │   │
│  │      → 根据用户等级设置 token 预算                  │   │
│  │      → 仅后端日志警告，用户无感知                   │   │
│  │      → 不警告用户，不建议开启新会话                 │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## L1：Memory Tool 状态保存

### 为什么？

根据 [Claude 官方文档](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-4-best-practices)：

> Memory Tool 与 Context Awareness 自然配对，用于跨 context window 保持状态连续性

### 实现

在 System Prompt 中添加指导：

```python
from core.context.compaction import get_memory_guidance_prompt

# 指导 Claude 使用 Memory Tool 保存重要发现
memory_guidance = get_memory_guidance_prompt()
system_prompt = f"{base_prompt}\n\n{memory_guidance}"
```

### Prompt 内容

```markdown
## 🧠 Long-Running Task Guidelines

For complex or multi-step tasks:

1. **Save Important Discoveries**
   - Use the `memory` tool to store key findings, decisions, and progress
   - Save any data that would be costly to re-compute or re-discover

2. **State Management**
   - Periodically save your current state and next steps
   - This ensures continuity if the conversation is long

3. **Work Autonomously**
   - Complete tasks fully without stopping early
   - Break complex tasks into manageable steps

4. **Preserve Critical Context**
   - File paths, configurations, and user preferences
   - Error patterns and solutions found
```

### 效果

- ✅ Claude 自主保存重要状态
- ✅ 长任务不会因为"忘记"早期发现而重复工作
- ✅ 用户无感知

---

## L2：历史消息智能裁剪

### 为什么？

当消息历史过长时，直接截断会丢失关键上下文。智能裁剪可以：
- 保留首轮对话（任务定义）
- 保留最近对话（当前工作）
- 保留关键 tool_result（数据和结果）

### 实现

```python
from core.context.compaction import get_context_strategy, trim_history_messages

# 获取策略配置
strategy = get_context_strategy(qos_level)

# 智能裁剪
# 保留：首轮 + 最近 N 轮 + 关键 tool_result
history_messages = trim_history_messages(history_messages, strategy)
```

### 裁剪逻辑

```
原始消息：[M1, M2, M3, M4, M5, M6, M7, M8, M9, M10, M11, M12, ...]

裁剪后：
┌───────────┐ ┌────────────────┐ ┌─────────────────┐
│ 首 2 轮    │ │ 含 tool_result │ │ 最近 10 轮      │
│ M1, M2    │ │ M5 (有数据)    │ │ M21...M30      │
└───────────┘ └────────────────┘ └─────────────────┘
     ↑                ↑                   ↑
  任务定义      关键数据/结果        当前工作上下文
```

### 配置参数

```python
@dataclass
class ContextStrategy:
    max_history_messages: int = 50     # 最大保留消息数
    preserve_first_n: int = 2          # 始终保留前 N 轮
    preserve_last_n: int = 10          # 始终保留最近 N 轮
    preserve_tool_results: bool = True # 保留含 tool_result 的消息
```

### 效果

- ✅ 不丢失任务定义和当前上下文
- ✅ 保留关键数据和计算结果
- ✅ 用户无感知

---

## L3：QoS 成本控制

### 为什么？

不同用户等级有不同的成本预算，需要在后端进行控制。

### 实现

```python
from core.context.compaction import (
    QoSLevel, 
    estimate_tokens, 
    should_warn_backend
)

# 估算 token 使用
estimated_tokens = estimate_tokens(history_messages)

# 仅后端日志警告（用户无感知）
if should_warn_backend(estimated_tokens, strategy):
    logger.warning(
        f"⚠️ Token 预警: {estimated_tokens:,} / "
        f"{strategy.token_budget:,} tokens"
    )
```

### QoS 等级

| 等级 | Token 预算 | 适用场景 |
|------|-----------|----------|
| FREE | 50K | 免费试用 |
| BASIC | 150K | 基础付费 |
| PRO | 200K | 专业版（默认）|
| ENTERPRISE | 1M | 企业版 |

### 关键原则

```python
# ❌ 错误做法：警告用户
yield {"type": "warning", "message": "接近上下文限制，建议开启新会话"}

# ✅ 正确做法：后端静默处理
logger.warning(f"Token 预警: {tokens} / {budget}")
# 用户不会看到任何提示
```

### 效果

- ✅ 成本可控
- ✅ 运维可监控
- ✅ 用户完全无感知

---

## 📊 效果对比

### 之前（错误）

```python
# 使用了错误的 Context Awareness Prompt
# 告诉 Claude "上下文会自动压缩"，但实际上我们没有 tool_runner
system_prompt += """
Your context window will be automatically compacted...
"""
# ❌ 可能导致 Claude 错误地期望"无限上下文"
```

### 现在（正确）

```python
# 使用 Memory Guidance Prompt
# 指导 Claude 主动保存重要状态，而非被动等待压缩
system_prompt += """
## Long-Running Task Guidelines
1. Use the `memory` tool to store key findings...
"""
# ✅ Claude 主动管理状态，适应我们的架构
```

---

## 🔮 未来优化方向

### 方向 1：集成 tool_runner（大改动）

如果确实需要自动 compaction：
- 在 LLM 服务层添加 `tool_runner` 模式
- 仅用于超长任务（>200K tokens）
- 作为备用模式，不改变主流程

### 方向 2：摘要注入（中等改动）

当裁剪历史消息时，生成被裁剪部分的摘要：
```
[早期对话摘要] + [保留的消息]
```

### 方向 3：分段加载（小改动）

对于超长历史：
- 首轮加载摘要 + 最近消息
- 按需加载更早的消息（通过 tool_result 触发）

---

## ✅ 验收标准

| 场景 | 预期表现 |
|------|----------|
| 短对话（<50条消息） | 无裁剪，直接处理 |
| 中长对话（50-100条） | L2 裁剪，用户无感知 |
| 超长对话（>100条） | L2 裁剪 + L3 后端警告 |
| 用户查看界面 | 无任何警告或提示 |
| 问答效果 | 不因裁剪丢失关键上下文 |

---

## 📁 相关代码

```
core/context/compaction/
└── __init__.py     # 三层策略实现

services/
└── chat_service.py # L2/L3 执行点

core/agent/
└── simple_agent.py # L1 Prompt 注入点
```

---

## 配置管理原则

### 运营不可见（默认启用）

上下文管理是 **P0 级别的稳定性保障**，应该"开箱即用"：

❌ **不在实例配置中暴露**
```yaml
# instances/_template/config.yaml
# ❌ 已移除 context_management 配置段
# 运营人员无需了解技术细节
```

✅ **在框架层统一管理**
```yaml
# config/context_compaction.yaml
compaction:
  enabled: true  # 默认启用
  qos_level: "pro"  # 默认 QoS 等级
```

✅ **环境变量支持（极少数场景）**
```bash
# 如果需要调整（极少数情况），使用环境变量
export QOS_LEVEL=enterprise  # 更宽松的上下文限制
export QOS_LEVEL=free        # 更严格的成本控制
```

**设计原则**：
1. 默认启用：防止上下文溢出是基础保障
2. 用户无感：运营人员不需要学习和配置
3. 静默处理：终端用户完全不知道后台在做上下文管理
4. 环境变量覆盖：为极少数特殊需求保留灵活性

---

**总结：基于当前 RVR 架构，采用"Memory 指导 + 智能裁剪 + QoS 控制"的三层策略，在不改变核心架构的前提下，实现用户无感知的上下文管理。运营人员无需配置，开箱即用。**
