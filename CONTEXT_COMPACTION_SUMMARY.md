# 上下文压缩优化 - 最终方案

## 🎯 核心决策

**基于当前 RVR 架构，采用三层防护策略**

### 设计反思

| 之前（错误） | 现在（正确） |
|------------|-------------|
| 使用 Context Awareness Prompt | 使用 Memory Guidance Prompt |
| 说"上下文会自动压缩" | 指导 Claude 主动保存状态 |
| 期望 tool_runner 自动处理 | 服务层智能裁剪 + Claude 自主 |

### 为什么这样改？

```
❌ 之前的问题：
   我们没有使用 tool_runner，所以没有自动 compaction
   但 Context Awareness Prompt 说"上下文会自动压缩"
   → 这是对 Claude 的误导！

✅ 现在的方案：
   1. 指导 Claude 使用 Memory Tool 保存重要状态
   2. 服务层智能裁剪历史消息
   3. 后端静默监控 token 使用
   → 与我们的架构完全匹配！
```

## ✅ 三层防护策略

### L1：Memory Tool 状态保存（Claude 自主）

```python
# 在 System Prompt 中添加指导
from core.context.compaction import get_memory_guidance_prompt

# 指导 Claude：
# - 使用 memory 工具保存重要发现
# - 周期性保存当前状态
# - 完整完成任务，不提前停止
```

### L2：历史消息智能裁剪（服务层自动）

```python
# 在 ChatService 中执行
from core.context.compaction import trim_history_messages

# 裁剪逻辑：
# - 保留首轮对话（任务定义）
# - 保留最近 N 轮（当前工作上下文）
# - 保留关键 tool_result（数据和结果）
history_messages = trim_history_messages(messages, strategy)
```

### L3：QoS 成本控制（后端静默）

```python
# 仅后端日志，用户无感知
if should_warn_backend(estimated_tokens, strategy):
    logger.warning(f"⚠️ Token 预警: {tokens} / {budget}")
    # 用户不会看到任何提示！
```

## 📊 效果对比

| 指标 | 之前 | 现在 |
|------|------|------|
| **用户体验** | 可能警告用户 | 完全静默 |
| **架构匹配** | ❌ 不匹配（没有 tool_runner） | ✅ 完全匹配 |
| **问答效果** | 可能丢关键信息 | 智能保留关键上下文 |
| **代码复杂度** | 1,500+ 行 | ~200 行 |

## 📁 代码结构

```
core/context/compaction/
└── __init__.py         # 三层策略实现（~200行）
    ├── QoSLevel        # QoS 等级枚举
    ├── ContextStrategy # 策略配置
    ├── get_memory_guidance_prompt()  # L1
    ├── trim_history_messages()       # L2
    └── should_warn_backend()         # L3

services/chat_service.py  # L2/L3 执行点
core/agent/simple/simple_agent.py  # L1 Prompt 注入点
```

## 🎉 关键收益

1. **用户体验一流**：完全静默，用户无感知
2. **架构匹配**：与当前 RVR 循环完全兼容
3. **问答效果**：智能保留关键上下文，不丢信息
4. **维护简单**：~200 行代码，逻辑清晰

## 🔮 未来方向

仅在以下情况考虑集成 `tool_runner`：
- 用户反馈 200K+ 对话频繁出问题
- Memory + 裁剪策略效果不足
- 有充足资源进行大规模重构

**当前方案已足够应对 95% 的场景！**

---

## 📋 配置管理决策

### ❌ 不暴露给运营人员

上下文管理是 **P0 级别的稳定性保障**，应该"开箱即用"：

```yaml
# instances/_template/config.yaml
# ❌ 已移除 context_management 配置段
# 运营人员无需了解技术细节
```

**理由**：
1. 这是基础稳定性保障，不应该是可选配置
2. 增加运营学习成本，违背"简化运营"的设计原则
3. 用户完全无感知，运营人员不需要关心技术细节

### ✅ 框架层统一管理

```yaml
# config/context_compaction.yaml
compaction:
  enabled: true  # 默认启用
  qos_level: "pro"  # 可通过环境变量 QOS_LEVEL 覆盖
```

### 环境变量支持（极少数场景）

```bash
# 如果需要调整（极少数情况）
export QOS_LEVEL=enterprise  # 更宽松的上下文限制
export QOS_LEVEL=free        # 更严格的成本控制
```

---

## 🔄 tool_runner 评估决策

### ❌ 不切换到 tool_runner

经过深入评估，决定保持当前的 `messages.stream()` + 自主 RVR 循环架构。

**核心理由**：
1. **RVR 架构已经非常成熟**：IntentAnalyzer, ToolSelector, ToolExecutor 经过充分验证
2. **三层策略已解决问题**：L1+L2+L3 组合有效应对长对话场景
3. **灵活性更高**：细粒度控制，支持 Prompt-First、配置优先级等产品特色
4. **重构成本极高**：收益有限，不值得大规模重写核心代码

详见：[上下文管理架构决策](docs/architecture/context_management_decision.md)

---

**总结：基于当前架构，采用"Memory 指导 + 智能裁剪 + QoS 控制"三层策略，用户体验和问答效果优先！配置默认启用，运营人员无需学习，开箱即用。**
