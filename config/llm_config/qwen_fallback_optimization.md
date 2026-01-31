# Qwen 作为备选模型的配置优化策略

本文档基于模型选择策略文档，针对不同 Agent 角色的核心需求，为 Qwen 备选模型提供针对性配置优化。

## 📋 策略概览

### 为什么选择 Claude 作为主模型？

Claude 在以下方面表现优异：
- ✅ 强指令遵循能力
- ✅ 准确复杂推理
- ✅ 稳定工具调用
- ✅ 标准化输出格式
- ✅ 低幻觉率

### Qwen 作为备选模型的风险与机会

| 维度 | 机会 | 风险 |
|------|------|------|
| **效果** | Qwen-Max 是最强国产模型，部分场景接近 Claude | 复杂推理和工具调用可能不如 Claude，存在性能差距 |
| **成本** | Qwen 成本显著低于 Claude，可降低运营成本 | 如果性能差距大，可能需要更多重试，抵消成本优势 |
| **可用性** | 国内服务，网络稳定，响应快速 | 高并发下的稳定性需要验证 |
| **兼容性** | API 兼容 OpenAI 格式，集成成本低 | 工具调用格式可能不同，需要适配 |

**结论**：Qwen 作为备选模型可以确保服务可用性，但效果可能不如 Claude。需要在迭代1后进行充分测试，评估实际性能差距。

---

## 🎯 各 Agent 角色的 Qwen 配置优化

### 1. IntentAnalyzer（意图分析）

**核心需求**：低延迟、准确意图理解

| 配置项 | 主模型 (Claude Haiku) | 备选模型 (Qwen-Plus) | 优化说明 |
|--------|----------------------|---------------------|---------|
| **模型** | `claude-haiku-4-5-20251001` | `qwen-plus` | 高性价比，适合意图分析 |
| **temperature** | `0` | `0` | 确定性输出，保证意图识别准确性 |
| **top_p** | - | `0.9` | 核采样阈值 |
| **max_tokens** | `2048` | `2048` | 与主模型保持一致 |
| **result_format** | - | `message` | 便于多轮对话处理 |

**配置要点**：
- ✅ 使用 `qwen-plus`（非 `qwen-max`），平衡性能和成本
- ✅ `temperature=0` 确保意图分类的确定性
- ✅ 快速响应，适合低延迟场景

---

### 2. SimpleAgent（主 Agent 对话）

**核心需求**：稳定工具调用、指令遵循

| 配置项 | 主模型 (Claude Sonnet) | 备选模型 (Qwen-Max) | 优化说明 |
|--------|----------------------|---------------------|---------|
| **模型** | `claude-sonnet-4-5-20250929` | `qwen-max` | 最强 Qwen 模型 |
| **temperature** | `1.0` | `0.8` | 略低于 Claude，平衡创造性和稳定性 |
| **top_p** | - | `0.9` | 核采样 |
| **max_tokens** | `64000` | `32000` | Qwen 最大输出可能小于 Claude |
| **result_format** | - | `message` | 必须设置，支持工具调用 |
| **repetition_penalty** | - | `1.05` | 降低重复，提升输出质量 |
| **tool_choice** | - | `auto` (可选) | 自动选择工具 |
| **parallel_tool_calls** | - | `true` (可选) | 并行工具调用提升效率 |

**配置要点**：
- ⚠️ **工具调用格式可能不同**，需要适配
- ⚠️ **复杂推理可能不如 Claude**，需要充分测试
- ✅ 使用 `qwen-max` 获得最强能力
- ✅ 适当降低 `temperature` 提升稳定性

---

### 3. LeadAgent（多智能体 Lead）

**核心需求**：强推理能力、任务分解能力

| 配置项 | 主模型 (Claude Opus) | 备选模型 (Qwen-Max) | 优化说明 |
|--------|---------------------|---------------------|---------|
| **模型** | `claude-opus-4-5-20251101` | `qwen-max` | 最强 Qwen 模型 |
| **temperature** | `0.3` | `0.3` | 与主模型保持一致，保证任务分解准确性 |
| **top_p** | - | `0.9` | 核采样 |
| **max_tokens** | `16384` | `16384` | 与主模型保持一致 |
| **result_format** | - | `message` | 必须设置 |
| **enable_thinking** | `true` | `false` (当前) | Qwen3 系列支持，但 `qwen-max` 暂不支持 |
| **thinking_budget** | `10000` | - | 如果使用 Qwen3，建议 `8000` |

**配置要点**：
- ✅ 良好长上下文支持，适合任务分解
- ⚠️ 推理能力可能不如 Claude Opus
- 💡 未来可考虑使用 `qwen3-max-preview` 启用思考模式

---

### 4. WorkerAgent（多智能体 Worker）

**核心需求**：稳定执行、工具调用

| 配置项 | 主模型 (Claude Sonnet) | 备选模型 (Qwen-Max) | 优化说明 |
|--------|----------------------|---------------------|---------|
| **模型** | `claude-sonnet-4-5-20250929` | `qwen-max` | 能力最接近 Claude Sonnet |
| **temperature** | `0.5` | `0.5` | 与主模型保持一致 |
| **top_p** | - | `0.9` | 核采样 |
| **max_tokens** | `8192` | `8192` | 与主模型保持一致 |
| **result_format** | - | `message` | 必须设置，支持工具调用 |
| **repetition_penalty** | - | `1.05` | 降低重复，提升执行质量 |
| **tool_choice** | - | `auto` (可选) | 自动选择工具 |
| **parallel_tool_calls** | - | `true` (可选) | 并行工具调用提升效率 |

**配置要点**：
- ⚠️ **工具调用格式可能不同**，需要适配
- ✅ 使用 `repetition_penalty` 提升执行质量
- ✅ 考虑启用 `parallel_tool_calls` 提升效率

---

### 5. CriticAgent（多智能体 Critic）

**核心需求**：低幻觉、准确评审

| 配置项 | 主模型 (Claude Sonnet) | 备选模型 (Qwen-Max) | 优化说明 |
|--------|----------------------|---------------------|---------|
| **模型** | `claude-sonnet-4-5-20250929` | `qwen-max` | 强评审能力 |
| **temperature** | `0.3` | `0.2` | 更低温度，降低幻觉，提升评审准确性 |
| **top_p** | - | `0.9` | 核采样 |
| **max_tokens** | `4096` | `4096` | 与主模型保持一致 |
| **result_format** | - | `message` | 必须设置 |
| **repetition_penalty** | - | `1.05` | 降低重复 |
| **presence_penalty** | - | `0.3` | 轻微降低内容重复度 |

**配置要点**：
- ⚠️ **幻觉率可能略高于 Claude**，但已是最佳选择
- ✅ 使用更低 `temperature` 提升准确性
- ✅ 使用 `presence_penalty` 降低内容重复

---

## 🔧 通用配置优化建议

### 1. 参数调优原则

| 场景 | temperature | top_p | repetition_penalty | presence_penalty |
|------|------------|-------|-------------------|------------------|
| **意图分析** | `0` | `0.9` | - | - |
| **工具调用** | `0.3-0.5` | `0.9` | `1.05` | - |
| **任务分解** | `0.3` | `0.9` | - | - |
| **质量评审** | `0.2` | `0.9` | `1.05` | `0.3` |
| **通用对话** | `0.7-0.8` | `0.9` | `1.05` | - |

### 2. 工具调用优化

**关键配置**：
```yaml
result_format: "message"  # 必须设置
tool_choice: "auto"        # 自动选择工具
parallel_tool_calls: true  # 并行工具调用（如果支持）
```

**注意事项**：
- ⚠️ Qwen 的工具调用格式可能与 Claude 不同，需要适配
- ⚠️ 复杂工具调用场景下，Qwen 可能不如 Claude 稳定
- ✅ API 兼容 OpenAI 格式，集成成本低

### 3. 成本优化

**策略**：
- ✅ 使用 `qwen-plus` 替代 `qwen-max` 用于简单任务（如意图分析）
- ✅ 合理设置 `max_tokens`，避免不必要的长输出
- ⚠️ 如果性能差距大导致重试增加，可能抵消成本优势

### 4. 可用性保障

**优势**：
- ✅ 国内服务，网络稳定
- ✅ 响应快速
- ⚠️ 高并发下的稳定性需要验证

**建议**：
- 设置合理的 `timeout` 和 `max_retries`
- 监控 Qwen 的失败率和响应时间
- 根据实际表现调整 `cooldown_seconds`

---

## 📊 性能差距评估建议

### 测试维度

1. **效果测试**
   - [ ] 意图识别准确率对比
   - [ ] 工具调用成功率对比
   - [ ] 任务分解质量对比
   - [ ] 评审准确性对比
   - [ ] 复杂推理能力对比

2. **稳定性测试**
   - [ ] 高并发下的稳定性
   - [ ] 工具调用格式兼容性
   - [ ] 错误处理和重试机制

3. **成本分析**
   - [ ] Token 消耗对比
   - [ ] 重试次数统计
   - [ ] 总体成本对比

### 评估指标

| 指标 | 目标 | 说明 |
|------|------|------|
| **意图识别准确率** | ≥ 95% | 与 Claude Haiku 对比 |
| **工具调用成功率** | ≥ 90% | 与 Claude Sonnet 对比 |
| **任务分解质量** | ≥ 85% | 与 Claude Opus 对比 |
| **评审准确性** | ≥ 90% | 与 Claude Sonnet 对比 |
| **平均响应时间** | ≤ 2s | 国内服务优势 |

---

## 🚀 未来优化方向

### 1. 启用 Qwen3 思考模式

对于需要强推理的场景（如 LeadAgent），可考虑使用 `qwen3-max-preview`：

```yaml
model: "qwen3-max-preview"
enable_thinking: true
thinking_budget: 8000  # 略低于 Claude
result_format: "message"  # 必须
stream: true  # Qwen3 只支持流式
incremental_output: true  # Qwen3 只支持增量输出
```

### 2. 工具调用格式适配

如果发现工具调用格式不兼容，需要：
- 实现格式转换适配器
- 统一工具定义格式
- 处理工具调用响应的差异

### 3. 动态参数调整

根据实际性能表现，动态调整：
- `temperature`：根据任务复杂度调整
- `max_tokens`：根据实际输出长度调整
- `repetition_penalty`：根据重复情况调整

---

## 📝 配置示例

### 完整配置示例（profiles.yaml）

```yaml
# IntentAnalyzer
intent_analyzer:
  fallbacks:
    - provider: "qwen"
      model: "qwen-plus"
      temperature: 0
      top_p: 0.9
      max_tokens: 2048
      result_format: "message"

# SimpleAgent / MainAgent
main_agent:
  fallbacks:
    - provider: "qwen"
      model: "qwen-max"
      temperature: 0.8
      top_p: 0.9
      max_tokens: 32000
      result_format: "message"
      repetition_penalty: 1.05
      # tool_choice: "auto"
      # parallel_tool_calls: true

# LeadAgent
lead_agent:
  fallbacks:
    - provider: "qwen"
      model: "qwen-max"
      temperature: 0.3
      top_p: 0.9
      max_tokens: 16384
      result_format: "message"

# WorkerAgent
worker_agent:
  fallbacks:
    - provider: "qwen"
      model: "qwen-max"
      temperature: 0.5
      top_p: 0.9
      max_tokens: 8192
      result_format: "message"
      repetition_penalty: 1.05
      # tool_choice: "auto"
      # parallel_tool_calls: true

# CriticAgent
critic_agent:
  fallbacks:
    - provider: "qwen"
      model: "qwen-max"
      temperature: 0.2
      top_p: 0.9
      max_tokens: 4096
      result_format: "message"
      repetition_penalty: 1.05
      presence_penalty: 0.3
```

---

## ⚠️ 重要提醒

1. **充分测试**：在迭代1后，必须进行充分测试，评估实际性能差距
2. **工具调用适配**：工具调用格式可能不同，需要适配
3. **监控指标**：持续监控 Qwen 的成功率、响应时间、成本等指标
4. **渐进式切换**：建议先在小流量场景测试，再逐步扩大使用范围
5. **保留 Claude**：Qwen 作为备选，确保服务可用性，但 Claude 仍是主模型

---

## 📚 参考文档

- [Qwen 推荐配置列表](./qwen_recommended_configs.md)
- [模型选择策略文档](../docs/architecture/00-ARCHITECTURE-OVERVIEW.md)
- [通义千问官方文档](https://help.aliyun.com/zh/model-studio/)
