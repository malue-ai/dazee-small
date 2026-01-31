# Promptfoo 套件目录

此目录存放 **Prompt 级别的回归测试套件**，使用 Promptfoo 框架运行。

## 适用场景

- ✅ Prompt 级别的回归测试
- ✅ 单轮对话质量评估
- ✅ 模型输出格式验证
- ✅ 成本/延迟检查
- ✅ LLM-as-Judge 评分

## 不适用场景

- ❌ 多轮对话（需要上下文跟踪）→ 使用 `agent/conversation/`
- ❌ 工具调用验证（需要 Transcript）→ 使用 `agent/coding/`
- ❌ 中间检查点（需要 Checkpoint）→ 使用 `agent/multi_agent/`
- ❌ 多智能体协作 → 使用 `agent/multi_agent/`

## 使用方式

### 1. 创建 Promptfoo 配置文件

创建 `promptfoo.yaml`：

```yaml
prompts:
  - prompt: "{{input}}"
    provider: openai:chat:gpt-4
    config:
      temperature: 0.7

tests:
  - vars:
      input: "写一个 Python 函数计算斐波那契数列"
    assert:
      - type: contains
        value: "def"
      - type: contains
        value: "fibonacci"
      - type: llm-rubric
        value: "代码应该正确实现斐波那契数列计算"
      - type: cost
        threshold: 1000
```

### 2. 运行 Promptfoo

```bash
npx promptfoo eval -c promptfoo.yaml -o results.json
```

### 3. 转换为 ZenFlux 报告

```python
from evaluation.promptfoo_adapter import convert_promptfoo_result

report = convert_promptfoo_result(
    promptfoo_result_path="results.json",
    suite_name="prompt_regression"
)
```

### 4. 查看指标

```python
from evaluation.metrics import MetricsCalculator, format_metric_summary

calculator = MetricsCalculator()
summary = calculator.calculate(report)
print(format_metric_summary(summary))
```

## 套件示例

- `prompt_regression.yaml` - Prompt 回归测试
- `format_validation.yaml` - 格式验证
- `cost_check.yaml` - 成本检查

## 与 Agent 套件的区别

| 特性 | Promptfoo 套件 | Agent 套件 |
|------|---------------|-----------|
| 执行环境 | Promptfoo CLI | ZenFlux Harness |
| 输入 | 单轮 Prompt | 多轮对话 + 工具调用 |
| 验证方式 | Assertions | Graders (Code/Model/Human) |
| 结果格式 | Promptfoo JSON | ZenFlux EvaluationReport |
| 适用场景 | Prompt 回归 | Agent 完整流程 |

## 最佳实践

1. **快速回归**：使用 Promptfoo 快速验证 Prompt 变更
2. **全面评估**：使用 Agent 套件评估完整执行流程
3. **CI 集成**：先跑 Promptfoo（快速），再跑 Agent（全面）
