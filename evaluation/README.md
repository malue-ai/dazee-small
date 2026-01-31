# ZenFlux Agent 评估系统

基于 Anthropic 方法论的三层评分器（Code + Model + Human）评估系统，用于全面评估 Agent 性能。

## 📋 目录结构

```
evaluation/
├── models.py              # 数据模型定义
├── harness.py            # 评估执行引擎
├── graders/              # 评分器实现
│   ├── code_based.py     # 代码级评分器（客观、快速）
│   ├── model_based.py    # 模型级评分器（LLM-as-Judge）
│   └── human.py          # 人工评分器接口
├── metrics.py            # 指标计算模块
├── calibration.py        # 人工校准工作流
├── dashboard.py          # 指标看板
├── alerts.py             # 告警机制
├── ci_integration.py     # CI/CD 集成
├── qos_config.py         # QoS 评估配置
├── case_converter.py     # 失败案例转换器
├── case_reviewer.py      # 失败案例复审
├── promptfoo_adapter.py  # Promptfoo 结果转换器
├── promptfoo_mapping.md  # Promptfoo 能力映射文档
├── suites/               # 评测套件
│   ├── promptfoo/       # Promptfoo 套件（Prompt 级别回归）
│   ├── conversation/     # 对话类任务
│   ├── coding/           # 编码类任务
│   ├── multi_agent/      # 多智能体任务
│   └── regression/       # 回归测试（从生产失败案例生成）
└── reports/              # 评估报告输出
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 运行单个评测套件

```python
from evaluation.harness import EvaluationHarness

harness = EvaluationHarness()
report = await harness.run_suite(
    suite_name="conversation/basic",
    num_trials=3
)
```

### 3. 查看评估指标

```python
from evaluation.metrics import MetricsCalculator, format_metric_summary

calculator = MetricsCalculator()
summary = calculator.calculate(report)
print(format_metric_summary(summary))
```

### 4. 在 CI/CD 中运行

```bash
# 运行 BASIC 级别评估
python -m evaluation.ci_integration --qos-level BASIC

# 运行所有级别评估
python -m evaluation.ci_integration --qos-level ALL

# 使用基线报告进行回归检测
python -m evaluation.ci_integration \
    --qos-level PRO \
    --baseline evaluation/baselines/baseline.json
```

## 📊 评测套件

### Promptfoo 套件 (promptfoo/)

**适用场景：Prompt 级别的回归测试**

- **prompt_regression**: Prompt 回归测试
- **format_validation**: 格式验证
- **cost_check**: 成本检查

**特点：**
- 使用 Promptfoo 框架运行（快速、轻量）
- 适合单轮对话、格式验证、成本检查
- 结果自动转换为 ZenFlux 报告格式

**不适用：** 多轮对话、工具调用、中间检查点 → 使用 Agent 套件

详见：[promptfoo/README.md](suites/promptfoo/README.md)

### Agent 套件（完整流程评估）

#### 对话类 (conversation/)

- **basic**: 基础对话理解
- **multi_turn**: 多轮对话
- **context_tracking**: 上下文跟踪

#### 编码类 (coding/)

- **basic_code_generation**: 基础代码生成
- **file_operations**: 文件操作
- **sandbox_execution**: 沙盒执行

#### 多智能体 (multi_agent/)

- **task_decomposition**: 任务分解
- **sub_agent_coordination**: 子智能体协作
- **checkpoint_recovery**: 检查点恢复

#### 回归测试 (regression/)

从生产失败案例库自动生成，包括：
- 技术报错（context overflow, tool call failure 等）
- 用户反馈不满意（thumbs down, negative comments）
- 响应质量问题（incomplete, logical inconsistency 等）

### 套件选择指南

| 场景 | 推荐套件 | 原因 |
|------|---------|------|
| Prompt 变更回归 | `promptfoo/` | 快速、轻量、适合单轮测试 |
| 多轮对话评估 | `conversation/` | 需要上下文跟踪 |
| 工具调用验证 | `coding/` | 需要 Transcript 和工具调用记录 |
| 多智能体协作 | `multi_agent/` | 需要任务分解和检查点 |
| 生产失败回归 | `regression/` | 从真实失败案例生成 |

## 🎯 评分器

### Code-based Graders（代码级评分器）

客观、快速、可复现：

```python
from evaluation.graders.code_based import CodeBasedGraders

graders = CodeBasedGraders()

# 检查工具调用
result = graders.check_tool_calls(transcript, expected_tools=["write_file"])

# 检查 Token 限制
result = graders.check_token_limit(transcript, max_tokens=10000)

# 检查中间结果
result = graders.check_checkpoint(transcript, checkpoint_step=2, expression="result > 0")
```

### Model-based Graders（模型级评分器）

灵活、主观、带置信度：

```python
from evaluation.graders.model_based import ModelBasedGraders

graders = ModelBasedGraders(llm=llm_instance)

# 意图理解
result = await graders.grade_intent_understanding(query, transcript)

# 响应质量
result = await graders.grade_response_quality(query, transcript, expected_outcome)

# 过度工程化检测
result = await graders.grade_over_engineering(query, transcript)

# 使用 ensemble（多 Judge 投票）
result = await graders.grade_with_ensemble(
    query, transcript, grading_func="grade_response_quality", num_judges=3
)
```

### Human Graders（人工评分器）

用于校准和处理复杂案例：

```python
from evaluation.graders.human import HumanGraderInterface

interface = HumanGraderInterface()

# 提交人工复审请求
review_id = interface.submit_for_review(task, trial, context="Low confidence from LLM")

# 获取待复审任务
pending = interface.get_pending_reviews()

# 提交人工评分
interface.submit_review(review_id, grades=[...], notes="...")
```

## 📈 指标体系

### 准确率指标（40%权重）

- **code_pass_rate**: 代码级检查通过率（≥95%）
- **model_pass_rate**: 模型级检查通过率（≥80%）
- **task_success_rate**: 整体任务成功率（≥85%）

### 质量指标（30%权重）

- **avg_quality_score**: LLM-as-Judge 平均得分（≥7.0/10）
- **high_confidence_rate**: 高置信度评分占比（≥70%）
- **human_review_rate**: 需人工复审的比例（≤15%）

### 完整度指标（15%权重）

- **response_completeness**: 响应完整性（≥98%）
- **tool_success_rate**: 工具调用成功率（≥90%）

### 稳定性指标（10%权重）

- **trial_consistency**: 多次试验一致性（≥80%）
- **error_rate**: 执行错误率（≤5%）

### 效率指标（5%权重）

- **avg_execution_time**: 平均执行时间（≤30s）
- **token_efficiency**: Token 使用效率
- **avg_tool_calls**: 平均工具调用次数

## 🔔 告警机制

系统会自动检测以下情况并发送告警：

### 🔴 严重告警（阻塞发布）

- 性能回归检测
- 质量分层为 POOR
- 任务成功率 < 70%
- 错误率 > 10%

### 🟡 警告告警（建议修复）

- 质量分层为 ACCEPTABLE
- 代码级检查通过率 < 90%
- 模型级检查通过率 < 70%
- 平均质量得分 < 6.0/10
- 平均执行时间 > 60s

### 🔵 信息告警（提示关注）

- 人工复审比例 > 25%

### 配置通知渠道

```python
from evaluation.alerts import AlertManager, slack_notifier, email_notifier

alert_manager = AlertManager()

# 添加 Slack 通知
alert_manager.add_notifier(slack_notifier(webhook_url="https://..."))

# 添加邮件通知
alert_manager.add_notifier(email_notifier(
    smtp_server="smtp.gmail.com",
    smtp_port=587,
    sender="alerts@example.com",
    password="***",
    recipients=["team@example.com"]
))
```

## 🔄 人工校准工作流

LLM-as-Judge 需要定期校准以保证可靠性：

```python
from evaluation.calibration import CalibrationWorkflow

workflow = CalibrationWorkflow(model_graders=graders)

# 1. 创建校准集（采样 50 个案例）
calibration_cases = await workflow.create_calibration_set(
    tasks=all_tasks,
    sample_size=50,
    strategy="diverse"  # diverse/edge_cases/random
)

# 2. 人工标注
for case in calibration_cases:
    # 人工复审并提交评分
    human_grades = [...]  # 人工给出的评分
    workflow.submit_human_grades(case.task_id, human_grades)

# 3. 生成校准报告
report = workflow.generate_calibration_report()
print(format_calibration_report(report))

# 4. 更新 grader prompts（根据不一致案例）
workflow.update_grader_prompts(report)
```

## 📊 评估看板

实时监控评估指标：

```python
from evaluation.dashboard import EvaluationDashboard

dashboard = EvaluationDashboard()

# 生成文本看板
text = dashboard.generate_dashboard(days=7)
print(text)

# 导出 JSON（用于外部可视化）
dashboard.export_to_json("dashboard.json")
```

看板内容包括：
- 📈 趋势分析（总体得分、成功率、质量得分）
- 📊 最新评估摘要
- 📉 关键指标历史
- ❌ 失败案例 Top 5
- ⚠️  告警信息

## 🔧 失败案例采集

从生产环境自动采集失败案例并转换为回归测试：

### 1. 失败检测器

```python
from core.monitoring.failure_detector import FailureDetector

detector = FailureDetector()

# 自动检测各类失败
# - 技术报错: context_overflow, tool_call_failure, timeout
# - 用户反馈: user_negative_feedback, user_retry
# - 质量问题: over_engineering, logical_incoherence

# 在生产代码中集成
await detector.detect_and_record(
    conversation_id=conv_id,
    failure_type=FailureType.TOOL_CALL_FAILURE,
    context={"tool_name": "write_file", "error": str(e)}
)
```

### 2. 质量扫描器

定期扫描对话质量：

```python
from core.monitoring.quality_scanner import QualityScanner

scanner = QualityScanner(
    model_graders=graders,
    failure_detector=detector
)

# 后台运行（建议每小时运行一次）
await scanner.scan_recent_conversations(hours=1)
```

### 3. 案例转换器

将失败案例转换为评测任务：

```python
from evaluation.case_converter import FailureCaseConverter

converter = FailureCaseConverter(failure_detector=detector)

# 批量转换
tasks = converter.convert_batch(limit=50, min_severity="medium")

# 导出为评测套件
converter.export_to_suite(
    tasks=tasks,
    output_file="evaluation/suites/regression/production_failures.yaml"
)
```

### 4. 案例复审

人工复审失败案例：

```python
from evaluation.case_reviewer import CaseReviewer

reviewer = CaseReviewer(failure_detector=detector)

# 获取待复审案例
pending_cases = reviewer.get_pending_cases(category="user_feedback")

# 提交复审
reviewer.submit_review(
    case_id=case.id,
    is_valid_failure=True,
    root_cause="intent_misunderstanding",
    suggested_fix="Update intent detection prompt",
    priority="high"
)
```

## 🎚️ QoS 差异化评估

不同服务等级有不同的评估配置：

```python
from evaluation.qos_config import QOS_EVAL_CONFIGS, QoSLevel

config = QOS_EVAL_CONFIGS[QoSLevel.PRO]

print(f"评测套件: {config.suites}")
print(f"试验次数: {config.trials}")
print(f"最低总分: {config.min_overall_score}")
print(f"最低成功率: {config.min_task_success_rate}")
```

| QoS Level | 套件数 | 试验次数 | 最低总分 | 最低成功率 |
|-----------|--------|----------|----------|------------|
| FREE      | 1      | 1        | 60%      | 70%        |
| BASIC     | 2      | 2        | 75%      | 80%        |
| PRO       | 4      | 3        | 85%      | 90%        |
| ENTERPRISE| 5      | 5        | 90%      | 95%        |

## 🔄 CI/CD 集成

### GitHub Actions 工作流

参见 `.github/workflows/evaluation.yml`

触发时机：
- **PR 提交**: 运行 BASIC 级别评估
- **合并到 main**: 运行 PRO 级别评估
- **每日定时**: 运行 ALL 级别全面评估
- **手动触发**: 可选择任意级别

### 本地运行

```bash
# 开发阶段：快速验证
python -m evaluation.ci_integration --qos-level FREE

# PR 前：完整测试
python -m evaluation.ci_integration --qos-level BASIC --strict

# 发布前：全面回归
python -m evaluation.ci_integration --qos-level ALL --baseline evaluation/baselines/baseline.json
```

## 📝 编写评测套件

YAML 格式示例：

```yaml
name: "基础代码生成"
description: "测试 Agent 的基础代码生成能力"
version: "1.0"

tasks:
  - task_id: "fibonacci"
    input:
      query: "写一个 Python 函数计算斐波那契数列第 n 项"
      agent_type: "simple"
      qos_level: "BASIC"
    
    expected_outcome:
      status: "success"
      tool_calls: ["write_file", "run_python"]
    
    reference_answer: |
      def fibonacci(n):
          if n <= 1:
              return n
          return fibonacci(n-1) + fibonacci(n-2)
    
    graders:
      - type: "code"
        name: "check_tool_calls"
        config:
          expected_tools: ["write_file"]
          
      - type: "code"
        name: "check_code_syntax"
        config:
          language: "python"
      
      - type: "model"
        name: "grade_response_quality"
        config:
          min_score: 7.0
          confidence_threshold: 0.7
```

## 🛠️ 最佳实践

### 1. 评测套件设计

- ✅ 覆盖核心用户场景
- ✅ 包含边界情况和失败案例
- ✅ 使用多轮对话测试上下文理解
- ✅ 设置合理的 checkpoint 验证中间步骤
- ✅ 从生产失败案例生成回归测试

### 2. Grader 选择

- 🎯 能用 Code-based 就不用 Model-based（快速、稳定）
- 🎯 Model-based grader 需要定期校准
- 🎯 低置信度的评分应提交人工复审
- 🎯 使用 ensemble 提高可靠性（重要场景）

### 3. 指标监控

- 📊 每日生成看板，关注趋势
- 📊 设置合理的告警阈值
- 📊 回归检测应使用稳定的基线
- 📊 不同 QoS 级别采用不同标准

### 4. CI/CD 集成

- 🔄 PR 阶段运行快速评估（FREE/BASIC）
- 🔄 发布前运行全面评估（PRO/ENTERPRISE）
- 🔄 严格模式下任何 CRITICAL 告警都阻塞发布
- 🔄 定期更新基线报告（每周/每次发布）

## 📎 附录：评估框架

为避免重复造轮子，建议根据场景组合开源/商业框架与本评估系统：

### 1. Promptfoo（推荐作为提示词级别评估）

- **适用**：提示词回归、YAML 配置化断言、LLM-as-Judge rubric
- **优势**：轻量、易上手、社区活跃
- **推荐组合方式**：
  - 使用 Promptfoo 做 prompt 级别的快速回归
  - 本系统负责智能体级别（多轮、工具调用、检查点、QoS）评估

#### Promptfoo 集成使用

**步骤 1：运行 Promptfoo 评估**

```bash
# 安装 Promptfoo
npm install -g promptfoo

# 运行评估
npx promptfoo eval -c evaluation/suites/promptfoo/prompt_regression.yaml -o promptfoo_results.json
```

**步骤 2：转换为 ZenFlux 报告**

```python
from evaluation.promptfoo_adapter import convert_promptfoo_result
from pathlib import Path

# 转换结果
report = convert_promptfoo_result(
    promptfoo_result_path=Path("promptfoo_results.json"),
    suite_name="prompt_regression"
)

# 计算指标
from evaluation.metrics import MetricsCalculator, format_metric_summary

calculator = MetricsCalculator()
summary = calculator.calculate(report)
print(format_metric_summary(summary))
```

**步骤 3：在 CI 中集成**

参见 [CI/CD 集成](#cicd-集成) 部分，Promptfoo 结果会自动转换为 ZenFlux 报告并统一处理。

**断言类型映射**

详见：[promptfoo_mapping.md](promptfoo_mapping.md)

### 2. Harbor（容器化任务基准）

- **适用**：在容器化环境中运行标准基准或大规模试验
- **优势**：统一任务/评分格式，支持云端规模化
- **推荐组合方式**：
  - 使用 Harbor 跑标准基准（如 Terminal-Bench）
  - 将结果导入本系统进行统一指标汇总

### 3. Braintrust（离线评估 + 生产可观测）

- **适用**：需要同时做离线评估与线上质量监控
- **优势**：`autoevals` 提供事实性、相关性等预置评分器
- **推荐组合方式**：
  - Braintrust 负责线上观测和实验跟踪
  - 本系统负责针对 agent 内部流程的细粒度评测

### 4. LangSmith / Langfuse（生态集成）

- **适用**：LangChain 生态用户，或有数据驻留需求
- **优势**：追踪、数据集管理、在线/离线评估
- **推荐组合方式**：
  - LangSmith/Langfuse 负责链路追踪与数据集管理
  - 本系统负责指标计算、校准与发布门禁

### 选择建议

- **优先选框架，再投入评测**：框架只是加速器，评测质量取决于任务和评分器
- **Promptfoo + 本系统**：最轻量、覆盖 prompt 与 agent 两层
- **已有观测平台**：接入本系统即可补齐 agent 内部流程评估能力

## 📚 参考资料

- [Anthropic: Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- [ZenFlux Agent 架构文档](../docs/architecture/00-ARCHITECTURE-OVERVIEW.md)
- [评估方法论详细说明](./docs/METHODOLOGY.md)

## 🤝 贡献指南

欢迎贡献新的评测套件、grader 或改进建议！

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/new-grader`)
3. 提交更改 (`git commit -am 'Add new grader'`)
4. 推送到分支 (`git push origin feature/new-grader`)
5. 创建 Pull Request

## 📄 许可证

MIT License
