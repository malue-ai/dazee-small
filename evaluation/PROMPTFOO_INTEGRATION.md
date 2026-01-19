# Promptfoo 集成总结

## 完成情况

### ✅ 已完成的工作

1. **能力映射** (`promptfoo_mapping.md`)
   - 梳理了 Promptfoo 断言类型与 ZenFlux Graders 的对应关系
   - 定义了结果格式映射和评分口径对齐标准
   - 明确了套件拆分规范（Promptfoo vs Agent）

2. **结果转换器** (`promptfoo_adapter.py`)
   - 实现了 `PromptfooAdapter` 类
   - 支持将 Promptfoo JSON 结果转换为 ZenFlux `EvaluationReport`
   - 支持多种断言类型转换：
     - `contains` / `not-contains` → `check_response_contains`
     - `regex` → `check_response_matches`
     - `llm-rubric` / `model-graded` → `grade_with_custom_rubric`
     - `cost` → `check_token_limit`
     - `latency` → `check_latency`
     - `equals` → `check_response_equals`
     - `is-json` → `check_json_schema`
     - `similar` → `grade_semantic_similarity`

3. **套件拆分规范**
   - 创建了 `evaluation/suites/promptfoo/` 目录
   - 定义了 Promptfoo 套件的适用场景和不适用场景
   - 更新了 README 说明套件选择指南

4. **线上效果回流** (`case_converter.py`)
   - 增强了 `CaseConverter` 类
   - 添加了 `export_to_promptfoo()` 方法
   - 支持将失败案例自动转换为 Promptfoo YAML 格式
   - 智能筛选适合 Promptfoo 的案例（单轮、无工具调用）

5. **CI/CD 集成** (`ci_integration.py` + `.github/workflows/evaluation.yml`)
   - 在 `CIEvaluationRunner` 中添加了 `_run_promptfoo_suites()` 方法
   - 实现了报告合并功能（`_merge_reports()`）
   - CI 流程：先跑 Promptfoo（快速回归），再跑 ZenFlux（全面评估）
   - 更新了 GitHub Actions 工作流，添加 Node.js 和 Promptfoo 安装步骤

## 架构设计

### 集成流程

```
┌─────────────────┐
│  Promptfoo CLI  │ 运行 YAML 套件
└────────┬────────┘
         │ JSON 结果
         ▼
┌─────────────────┐
│ PromptfooAdapter│ 转换结果
└────────┬────────┘
         │ EvaluationReport
         ▼
┌─────────────────┐
│ MetricsCalculator│ 计算指标
└────────┬────────┘
         │ MetricSummary
         ▼
┌─────────────────┐
│  AlertManager   │ 检查告警
└─────────────────┘
```

### 套件分工

| 特性 | Promptfoo 套件 | Agent 套件 |
|------|---------------|-----------|
| **执行环境** | Promptfoo CLI | ZenFlux Harness |
| **输入** | 单轮 Prompt | 多轮对话 + 工具调用 |
| **验证方式** | Assertions | Graders (Code/Model/Human) |
| **结果格式** | Promptfoo JSON | ZenFlux EvaluationReport |
| **适用场景** | Prompt 回归 | Agent 完整流程 |
| **速度** | 快速（秒级） | 较慢（分钟级） |

## 使用方式

### 1. 创建 Promptfoo 套件

在 `evaluation/suites/promptfoo/` 目录下创建 YAML 文件：

```yaml
prompts:
  - prompt: "{{input}}"
    provider: openai:chat:gpt-4

tests:
  - vars:
      input: "写一个 Python 函数计算斐波那契数列"
    assert:
      - type: contains
        value: "def"
      - type: llm-rubric
        value: "代码应该正确实现斐波那契数列计算"
```

### 2. 运行 Promptfoo

```bash
npx promptfoo eval -c evaluation/suites/promptfoo/prompt_regression.yaml -o results.json
```

### 3. 转换为 ZenFlux 报告

```python
from evaluation.promptfoo_adapter import convert_promptfoo_result

report = convert_promptfoo_result(
    promptfoo_result_path=Path("results.json"),
    suite_name="prompt_regression"
)
```

### 4. 在 CI 中自动运行

CI 会自动：
1. 运行所有 Promptfoo 套件（快速回归）
2. 运行 ZenFlux Agent 套件（全面评估）
3. 合并报告并计算统一指标
4. 检查告警并决定是否通过

## 优势总结

### 取长补短

- ✅ **Promptfoo 优势**：轻量、快速、YAML 配置化、社区活跃
- ✅ **ZenFlux 优势**：Agent 级评估、多轮对话、工具调用、检查点、QoS

### 避免重复造轮子

- ✅ 复用 Promptfoo 的断言生态和 YAML 配置
- ✅ 复用 ZenFlux 的指标计算、告警、CI 门禁
- ✅ 统一报告格式，便于对比和分析

### 工作流优化

- ✅ **快速反馈**：Promptfoo 在 CI 中快速运行，快速发现问题
- ✅ **全面评估**：ZenFlux 提供完整的 Agent 流程评估
- ✅ **统一指标**：所有结果统一到 ZenFlux 指标体系

## 后续优化建议

1. **缓存机制**：Promptfoo 结果缓存，避免重复运行
2. **并行执行**：Promptfoo 和 ZenFlux 可以并行运行（如果资源允许）
3. **结果对比**：提供 Promptfoo vs ZenFlux 的对比分析
4. **自动生成**：从失败案例自动生成 Promptfoo 套件（已实现基础功能）

## 参考资料

- [Promptfoo 官方文档](https://www.promptfoo.dev/)
- [能力映射文档](promptfoo_mapping.md)
- [评估系统 README](README.md)
