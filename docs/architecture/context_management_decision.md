# 上下文管理架构决策

## 决策时间
2026-01-14

## 背景
ZenFlux Agent 需要在长对话场景下防止上下文溢出，同时保持用户体验优先。讨论了两个关键问题：
1. 上下文管理配置是否应该暴露给运营人员？
2. 是否应该从 `messages.stream()` 切换到 `tool_runner`？

## 决策

### 1. 配置可见性：❌ 不暴露给运营

**决定**：从 `instances/_template/config.yaml` 移除 `context_management` 配置段。

**理由**：
- 这是 **P0 级别的稳定性保障**，防止上下文溢出导致会话报错
- 应该"开箱即用"，不需要运营学习和配置
- 增加运营学习成本，违背"简化运营"的设计原则
- 技术策略应该在框架层统一管理

**实现方式**：
```yaml
# ❌ 不在 instances/_template/config.yaml 中暴露
# context_management:
#   enable_memory_guidance: true
#   enable_history_trimming: true

# ✅ 在框架层 config/context_compaction.yaml 统一管理
compaction:
  enabled: true
  qos_level: "pro"  # 可通过环境变量 QOS_LEVEL 覆盖
```

**环境变量支持**（极少数场景）：
```bash
# 运营如果真的需要调整（极少数情况），使用环境变量
export QOS_LEVEL=enterprise  # 更宽松的上下文限制
export QOS_LEVEL=free        # 更严格的成本控制
```

### 2. 技术架构：❌ 不使用 tool_runner

**决定**：保持当前的 `messages.stream()` + 自主 RVR 循环架构，不切换到 `tool_runner`。

**评估对比**：

| 维度 | messages.stream (当前) | tool_runner (SDK封装) | 结论 |
|------|----------------------|---------------------|------|
| **成熟度** | ✅ RVR 循环充分验证 | ⚠️ 需要重构核心代码 | **保持现状** |
| **灵活性** | ✅ 细粒度控制（IntentAnalyzer, ToolSelector, ToolExecutor） | ❌ 黑盒封装，难以定制 | **保持现状** |
| **上下文管理** | ✅ 三层策略已解决问题 | ✅ 原生 compaction | **平局** |
| **重构成本** | - | ❌ 极高（核心循环全部重写） | **不值得** |
| **产品特色** | ✅ Prompt-First、配置优先级、分层缓存 | ❌ 可能无法支持现有特性 | **保持现状** |

**核心理由**：

1. **RVR 架构已经非常成熟**
   ```
   Read → IntentAnalyzer（意图识别）
   Reason → Extended Thinking（深度思考）
   Act → ToolSelector + ToolExecutor（工具执行）
   Observe → ResultCompactor（结果精简）
   Validate → 在 Thinking 中验证
   Write → PromptResultsWriter（持久化）
   Repeat → max_turns 控制
   ```

2. **三层上下文管理策略已解决问题**
   - **L1: Memory Guidance**（Claude 主动管理） → 比被动压缩更智能
   - **L2: 历史消息智能裁剪**（服务层自动） → 在问题发生前就解决了
   - **L3: QoS 成本控制**（后端静默） → 符合"不警告用户"的产品原则

3. **重构成本极高，收益有限**
   - 需要重写 `SimpleAgent` 核心循环
   - 需要重新适配 `IntentAnalyzer`, `ToolSelector`, `ToolExecutor`
   - 需要重新验证所有集成测试
   - 可能失去现有的 Prompt-First 特性

4. **tool_runner 的 compaction 质量优势不明显**
   - 我们的 L1 策略让 Claude 自主决定什么重要，更智能
   - L2 策略在服务层就解决了大部分问题
   - SDK 的自动压缩是"被动"的，我们的是"主动+被动"结合

## 三层上下文管理策略（最终方案）

```
┌─────────────────────────────────────────────────────────────┐
│  L1. Memory Tool 状态保存（Claude 自主）                     │
│      → 指导 Claude 使用 `memory` 工具保存重要发现和状态      │
│      → System Prompt 注入：get_memory_guidance_prompt()     │
│                                                              │
│  L2. 历史消息智能裁剪（服务层自动）                          │
│      → 在 ChatService 中，根据 QoS 配置对历史消息进行裁剪    │
│      → 策略：总是保留首轮 + 最近 N 轮 + 关键 tool_result     │
│      → 确保消息列表在合理长度，降低 LLM 成本和处理延迟       │
│                                                              │
│  L3. QoS 成本控制（后端静默预警）                            │
│      → 在 ChatService 中，根据 QoS 配置预估 token 数量       │
│      → 当预估 token 超过阈值时，仅在后端记录警告日志         │
│      → 用户完全无感知，不警告用户，不建议开启新会话          │
└─────────────────────────────────────────────────────────────┘
```

## 核心收益

1. **用户体验一流**：
   - **静默处理**：用户完全无感知
   - **持续对话**：Claude 主动管理记忆，避免中断
   - **不警告用户**：符合"不要让用户觉得技术low"的产品原则

2. **产品口碑好**：避免因技术限制而影响用户对产品的评价

3. **维护成本低**：
   - **无需重构**：保持现有 RVR 循环
   - **代码简洁**：核心逻辑集中，易于理解和维护

4. **效果务实**：L1 和 L2 策略结合，有效应对大部分长对话场景

## 未来考虑

**仅在以下情况考虑 tool_runner**：
1. Claude SDK 的 `compaction_control` 质量显著优于现有方案（需数据验证）
2. SDK 支持我们所有现有特性（Prompt-First、分层缓存、意图识别等）
3. 有充足的工程资源进行大规模重构和测试

**当前结论**：不满足上述条件，保持现有架构。

## 相关文档
- [上下文压缩策略指南](../guides/context_compression_strategy.md)
- [三层上下文管理实现](../../core/context/compaction/__init__.py)
- [ChatService 集成](../../services/chat_service.py)
- [SimpleAgent RVR 循环](../../core/agent/simple/simple_agent.py)

## 决策人
用户 + AI Assistant

## 状态
✅ 已实施
