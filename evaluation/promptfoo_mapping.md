# Promptfoo 与 ZenFlux 评估系统能力映射

## 断言类型映射

### Promptfoo 断言类型 → ZenFlux Graders

| Promptfoo 断言类型 | ZenFlux 对应 Grader | 说明 |
|-------------------|---------------------|------|
| `contains` | `CodeBasedGraders.check_response_contains()` | 字符串包含检查 |
| `not-contains` | `CodeBasedGraders.check_response_contains()` (negated) | 字符串不包含检查 |
| `regex` | `CodeBasedGraders.check_response_matches()` | 正则表达式匹配 |
| `javascript` | `CodeBasedGraders.check_custom_expression()` | 自定义 JS 表达式 |
| `python` | `CodeBasedGraders.check_custom_expression()` | 自定义 Python 表达式 |
| `llm-rubric` | `ModelBasedGraders.grade_with_custom_rubric()` | LLM-as-Judge 评分准则 |
| `model-graded` | `ModelBasedGraders.grade_response_quality()` | 模型评分 |
| `webhook` | 通过 `CodeBasedGraders` 或 `ModelBasedGraders` 扩展 | Webhook 回调 |
| `cost` | `CodeBasedGraders.check_token_limit()` | Token/成本限制 |
| `latency` | 通过 `Trial.duration_seconds` 计算 | 延迟检查 |
| `equals` | `CodeBasedGraders.check_response_equals()` | 精确匹配 |
| `is-json` | `CodeBasedGraders.check_json_schema()` | JSON 格式验证 |
| `is-valid-openapi` | `CodeBasedGraders.check_json_schema()` | OpenAPI 验证 |
| `contains-json` | `CodeBasedGraders.check_response_contains_json()` | JSON 包含检查 |
| `similar` | `ModelBasedGraders.grade_semantic_similarity()` | 语义相似度 |
| `rouge` | `ModelBasedGraders.grade_rouge_score()` | ROUGE 分数 |
| `levenshtein` | `CodeBasedGraders.check_levenshtein_distance()` | 编辑距离 |

## 结果格式映射

### Promptfoo 结果 JSON 结构

```json
{
  "results": [
    {
      "id": "test-case-id",
      "prompt": {
        "raw": "user input",
        "display": "formatted input"
      },
      "response": {
        "output": "model output",
        "tokenUsage": {
          "total": 100,
          "prompt": 50,
          "completion": 50
        }
      },
      "assert": [
        {
          "type": "contains",
          "value": "expected",
          "pass": true,
          "score": 1.0,
          "reason": "Found expected text"
        }
      ],
      "vars": {
        "input": "test input"
      },
      "metadata": {}
    }
  ],
  "stats": {
    "total": 10,
    "pass": 8,
    "fail": 2
  }
}
```

### ZenFlux 对应结构

- `Promptfoo Test Case` → `Task`
- `Promptfoo Assert` → `GradeResult`
- `Promptfoo Result` → `Trial`
- `Promptfoo Suite` → `EvaluationSuite`

## 评分口径对齐

### Pass/Fail 标准

- **Promptfoo**: `assert.pass === true` → 通过
- **ZenFlux**: `GradeResult.passed === true` → 通过

### 分数映射

- **Promptfoo**: `assert.score` (0-1 或自定义范围)
- **ZenFlux**: `GradeResult.score` (0-1 归一化)

### 置信度

- **Promptfoo**: 不直接支持，但可通过 `llm-rubric` 的 metadata 传递
- **ZenFlux**: `GradeResult.confidence` (0-1)

## 套件拆分规范

### Promptfoo 套件（`evaluation/suites/promptfoo/`）

**适用场景：**
- Prompt 级别的回归测试
- 单轮对话质量评估
- 模型输出格式验证
- 成本/延迟检查

**不适用场景：**
- 多轮对话（需要上下文跟踪）
- 工具调用验证（需要 Transcript）
- 中间检查点（需要 Checkpoint）
- 多智能体协作（需要 MultiAgentOrchestrator）

### ZenFlux Agent 套件（`evaluation/suites/agent/`）

**适用场景：**
- 多轮对话
- 工具调用序列
- 中间结果验证
- 多智能体任务分解与协作
- 检查点恢复

## 转换策略

### 最小集合断言

优先支持的 Promptfoo 断言类型（最小集合）：
1. `contains` - 字符串匹配
2. `regex` - 正则表达式
3. `llm-rubric` - LLM-as-Judge
4. `cost` - Token 限制
5. `latency` - 延迟检查

### 转换流程

```
Promptfoo YAML → Promptfoo CLI → JSON Result
    ↓
PromptfooAdapter.convert_result()
    ↓
ZenFlux EvaluationReport
    ↓
MetricsCalculator.calculate()
    ↓
统一指标与告警
```

## 使用建议

1. **Prompt 回归测试**：使用 Promptfoo，快速验证 prompt 变更
2. **Agent 级评估**：使用 ZenFlux，覆盖完整执行流程
3. **CI 门禁**：先跑 Promptfoo（快速），再跑 ZenFlux（全面）
4. **结果汇总**：统一在 ZenFlux 报告中查看，指标对齐
