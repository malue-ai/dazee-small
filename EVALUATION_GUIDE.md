# 小搭子 (ZenFlux Agent) 测评体系完整使用手册

## 一、体系总览

整个测评体系由 **三大核心目录** 组成，覆盖从基础连通性检查到端到端 Agent 质量验证的完整链路：

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                     │
│   📁 docs/benchmark/          文档层：测试用例定义 + 测试数据 + 历史报告            │
│   📁 evaluation/              引擎层：评分器 + 测试套件 YAML + 运行框架             │
│   📁 scripts/                 执行层：E2E 自动化脚本 + 验证脚本 + 工具脚本          │
│                                                                                     │
│   流程：YAML 定义用例 → scripts 调度执行 → evaluation 评分 → reports 输出           │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 1.1 三层评分架构

| 评分层 | 类型 | 决定 PASS/FAIL？ | 说明 |
|---|---|---|---|
| **Code Grader** | 确定性代码检查 | **是（硬门槛）** | 毫秒级，零成本，可重复 |
| **Model Grader** | LLM-as-Judge | **否（仅诊断）** | 提供质量评分和优化方向，需人工确认 |
| **Human Grader** | 人工标注 | 边界场景 | 每周采样 100 条校准 |

### 1.2 测试分阶段

| 阶段 | 内容 | 是否需要 LLM |
|---|---|---|
| **Phase 0** | B9/B10 状态层回滚验证 | 不需要 |
| **Phase 1** | 核心 E2E 用例（A1/B1/D4/C1/B9/B10） | 需要 |
| **Phase 2** | 场景级用例（G1-G4/F4/H1/I1-I4/P1-P5） | 需要 |
| **Phase 3** | 扩展 Skill 测试（Prompt/Tool/Chain） | 需要 |

---

## 二、目录结构详解

### 2.1 `docs/benchmark/` — 文档与测试数据

```
docs/benchmark/
├── README.md                        # 总纲：维度定义、快速开始、最新结果
├── test_cases.md                    # 39 个测试用例详细定义（A1~P5）
├── E2E_AUTOMATION_REPORT.md         # E2E 自动化运行指南和历史结果
├── xiaodazi_eval.md                 # 可行性/效率评估方法论
└── data/                            # 测试数据文件
    ├── messy_sales.xlsx             # A1: 格式混乱销售表格
    ├── error_prone.csv              # D4: 错误恢复 CSV
    ├── rollback_test/               # B9/B10: 回滚测试数据
    │   ├── config.json
    │   ├── nginx.conf
    │   ├── README.md
    │   └── docs/                    # B10: 5 个公司文档
    ├── pipeline_test/               # G2: 季度销售原始数据
    ├── office_test/                 # G4: 会议纪要
    ├── research_test/               # G3: 论文草稿
    ├── style_test/                  # G1: 风格范文
    ├── context_test/                # F4: Q1/Q2/竞品报告
    ├── backtrack_test/              # I1-I4: RVR-B 毒药数据
    └── playbook_test/               # P1-P5: Playbook 测试数据
```

### 2.2 `evaluation/` — 评估引擎核心

```
evaluation/
├── harness.py                       # 核心引擎：加载套件、执行任务、生成报告
├── models.py                        # 数据模型：Task, Trial, Transcript, GradeResult
├── metrics.py                       # 指标计算器
├── calibration.py                   # 人工校准工作流
├── dashboard.py                     # 指标仪表板
├── alerts.py                        # 质量告警
├── ci_integration.py                # CI/CD 集成
├── loop_automation.py               # 闭环自动化：失败 → 回归套件
│
├── config/
│   ├── settings.yaml                # 全局配置（评分器、QoS、报告格式）
│   └── judge_prompts.yaml           # LLM-as-Judge 提示词（700+ 行）
│
├── adapters/
│   └── http_agent.py                # HTTP API 适配器（调用 /api/v1/chat）
│
├── graders/
│   ├── code_based.py                # 代码评分器（15+ 个检查方法）
│   ├── model_based.py               # 模型评分器（LLM-as-Judge）
│   └── human.py                     # 人工评分接口
│
├── suites/                          # 测试套件 YAML
│   ├── xiaodazi/
│   │   ├── e2e/
│   │   │   ├── phase1_core.yaml           # Phase 1: 6 个核心用例
│   │   │   ├── phase2_scenarios.yaml      # Phase 2: 场景级用例
│   │   │   ├── phase3_full.yaml           # Phase 3: 全量测试
│   │   │   ├── playbook_learning.yaml     # Playbook 学习专项
│   │   │   ├── playbook_false_positive.yaml
│   │   │   ├── phase2_prompt_skills.yaml  # Phase 2: Prompt 技能
│   │   │   ├── phase2_tool_common.yaml    # Phase 2: 通用工具
│   │   │   ├── phase2_skill_chains.yaml   # Phase 2: 技能链
│   │   │   ├── phase3_*.yaml              # Phase 3: 各类扩展
│   │   │   └── ...
│   │   ├── feasibility/                   # 可行性测试套件
│   │   │   ├── content_generation.yaml
│   │   │   ├── file_processing.yaml
│   │   │   ├── memory_context.yaml
│   │   │   ├── search_retrieval.yaml
│   │   │   ├── error_recovery.yaml
│   │   │   ├── safety_confirmation.yaml
│   │   │   └── desktop_operations.yaml
│   │   ├── efficiency/                    # 效率测试套件
│   │   │   ├── token_efficiency.yaml
│   │   │   ├── planning_depth.yaml
│   │   │   ├── path_optimality.yaml
│   │   │   └── skill_selection.yaml
│   │   └── e2e_regression_*.yaml          # 自动生成的回归套件
│   ├── conversation/                      # 对话意图理解
│   ├── coding/                            # 代码生成
│   └── intent/                            # Haiku 意图精度
│
├── scripts/                         # 内置执行脚本
│   ├── run_e2e_auto.py
│   ├── run_e2e_eval.py
│   └── ...
│
└── docs/benchmark/                  # 文档副本
```

### 2.3 `scripts/` — 执行脚本

| 脚本 | 用途 | 核心功能 |
|---|---|---|
| `run_e2e_auto.py` | **E2E 主入口**（最常用） | 自动启动服务器 → 运行测试 → 停止服务器 |
| `run_e2e_eval.py` | E2E 执行器 | 加载 YAML → HTTP 调用 → 采集 transcript → 评分 |
| `run_eval.py` | 通用评估 | 预检、连通性、SSE、日志分析 |
| `run_xiaodazi_eval.py` | 小搭子能力评估 | 可行性 + 效率维度 |
| `verify_rollback_e2e.py` | B9/B10 回滚验证 | 无 LLM 的确定性状态层测试 |
| `generate_eval_report.py` | 报告生成 | JSON → Markdown 报告 |
| `verify_memory_identity.py` | 记忆一致性验证 | 跨会话记忆 E2E |
| `verify_gateway_session_mapper.py` | 网关会话映射验证 | Session Key 回归测试 |
| `test_knowledge_e2e.py` | 知识检索验证 | Embedding → FTS5 → 语义搜索 → 混合搜索 |
| `test_playbook_extraction.py` | Playbook 提取测试 | WebSocket 实时监听 |

---

## 三、测试维度与用例矩阵

### 3.1 九大测试维度（39 个用例）

| 维度 | 代号 | 用例数 | 关注点 |
|---|---|---|---|
| **A - 效果验证** | A1-A3 | 3 | Excel 分析、多轮追问、PDF 生成 |
| **B - 功能特性** | B1-B10 | 10 | 记忆、环境感知、HITL、长任务、回滚 |
| **C - Token 效率** | C1-C3 | 3 | 缓存命中、多工具控制、长对话不膨胀 |
| **D - 场景覆盖** | D1-D6 | 6 | 代码、翻译、文案、调研、错误恢复、桌面 |
| **E - 桌面操作** | E1-E4 | 4 | GUI 操作、屏幕感知、多窗口 |
| **F - 开发者体验** | F1-F4 | 4 | Prompt 定义、API、日志、上下文工程 |
| **G - 垂直场景** | G1-G5 | 5 | 写稿、表格、研究、办公、翻译 |
| **H - 鲁棒性** | H1-H4 | 4 | 降级、恶意输入、大文件、并发 |
| **I - RVR-B 回溯** | I1-I4 | 4 | 参数调整、工具替换、重规划、升级链 |
| **P - Playbook** | P1-P5 | 5 | 提取、应用、闭环、拒绝、删除 |

### 3.2 代码评分器（Code Grader）清单

| 评分器 | 功能 | 典型用法 |
|---|---|---|
| `check_no_tool_errors()` | 工具调用无报错 | 所有含工具的用例 |
| `check_tool_calls(tools)` | 调用了指定工具 | 验证 Agent 选择了正确工具 |
| `check_token_limit(N)` | Token 不超过 N | C1: `check_token_limit(25000)` |
| `check_backtrack_occurred(min, max)` | 发生了指定次数回溯 | I1: `check_backtrack_occurred(1)` |
| `check_response_contains(keywords)` | 回复包含关键词 | 验证输出内容 |
| `check_response_not_contains(keywords)` | 回复不包含关键词 | 安全性检查 |
| `check_response_non_empty()` | 回复非空 | 基础检查 |
| `check_turn_count(min, max)` | 轮次在范围内 | 效率检查 |

### 3.3 模型评分器（Model Grader / LLM-as-Judge）清单

| 评分器 | 用途 | 适用用例 |
|---|---|---|
| `grade_response_quality` | 通用管道诊断（意图/规划/工具/上下文/输出） | 几乎所有用例 |
| `grade_rollback_safety` | 回滚安全专项评估 | B9, B10 |
| `grade_data_pipeline_quality` | 数据管道质量（清洗/分析/准确性） | G2 |
| `grade_action_item_extraction` | 行动项提取准确性 | G4 |
| `grade_research_quality` | 论文润色/引用检查质量 | G3 |
| `grade_style_memory` | 风格记忆跨会话验证 | G1 |
| `grade_context_engineering` | 上下文工程效率 | F4 |
| `grade_backtrack_quality` | RVR-B 回溯机制质量 | I1-I4 |
| `grade_intent_understanding` | 意图理解准确性 | 意图相关用例 |
| `grade_over_engineering` | 过度工程化检测 | 防止简单任务用复杂方案 |
| `grade_playbook_extraction` | Playbook 策略提取质量 | P1 |
| `grade_playbook_application` | Playbook 策略应用效果 | P2 |
| `grade_playbook_lifecycle` | Playbook 全生命周期闭环 | P3 |
| `grade_playbook_crud` | Playbook 拒绝/删除流程正确性 | P4, P5 |

---

## 四、使用手册 — 命令速查

### 4.1 最常用：全量 E2E 测试

```bash
# 激活虚拟环境
source /Users/liuyi/Documents/langchain/liuy/bin/activate

# 全量运行（自动启服务 → Phase 0 回滚 → Phase 1 E2E → 停服务）
python scripts/run_e2e_auto.py --clean

# 指定 LLM 提供商
python scripts/run_e2e_auto.py --clean --provider claude
python scripts/run_e2e_auto.py --clean --provider qwen
```

### 4.2 单用例调试

```bash
# 只跑 A1（Excel 分析）
python scripts/run_e2e_auto.py --case A1

# 只跑 B9（回滚安全）
python scripts/run_e2e_auto.py --case B9

# 只跑 I1（RVR-B 回溯）
python scripts/run_e2e_auto.py --case I1
```

### 4.3 从某个用例恢复（断点续跑）

```bash
# 从 D4 开始，跳过已完成的 A1/B1
python scripts/run_e2e_auto.py --from D4
```

### 4.4 使用已运行的服务（开发调试）

```bash
# 先手动启动服务
uvicorn main:app --host 0.0.0.0 --port 8000

# 然后只跑测试（不自动启停服务）
python scripts/run_e2e_auto.py --no-start --port 8000
```

### 4.5 Phase 2 场景测试

```bash
# Phase 2 全量（G2/G4/G3/G1/F4/H1/I1-I4/P1-P5）
python scripts/run_e2e_auto.py --suite phase2_scenarios

# 延迟评分（先跑完所有用例，再统一评分）
python scripts/run_e2e_auto.py --suite phase2_scenarios --defer-grading

# Playbook 专项
python scripts/run_e2e_auto.py --suite playbook_learning
```

### 4.6 Phase 0：回滚状态层独立验证（无需 LLM）

```bash
# 全量 B9 + B10
python scripts/verify_rollback_e2e.py

# 只跑 B9
python scripts/verify_rollback_e2e.py --case B9

# 详细输出
python scripts/verify_rollback_e2e.py -v
```

### 4.7 基础设施验证（连通性/SSE/日志）

```bash
# 预检 + 连通性
python scripts/run_eval.py --phase connectivity

# SSE 协议检查
python scripts/run_eval.py --phase sse

# 日志分析
python scripts/run_eval.py --phase log

# 指定服务地址
python scripts/run_eval.py --phase connectivity --base-url http://127.0.0.1:8000
```

### 4.8 能力维度评估

```bash
# 全量（可行性 + 效率）
python scripts/run_xiaodazi_eval.py --all

# 只跑可行性
python scripts/run_xiaodazi_eval.py --suite feasibility

# 只跑效率
python scripts/run_xiaodazi_eval.py --suite efficiency

# 只看失败用例 + 根因分类
python scripts/run_xiaodazi_eval.py --failures-only --classify
```

### 4.9 其他验证脚本

```bash
# 知识检索 E2E
python scripts/test_knowledge_e2e.py

# 记忆一致性验证
python scripts/verify_memory_identity.py

# 网关会话映射回归
python scripts/verify_gateway_session_mapper.py

# Playbook 提取（WebSocket 实时监听）
python scripts/test_playbook_extraction.py

# 生成 Markdown 报告
python scripts/generate_eval_report.py --latest
```

---

## 五、测试套件 YAML 格式说明

每个 YAML 文件就是一个测试套件，结构如下：

```yaml
id: suite_id                     # 套件唯一 ID
name: Suite Name                 # 套件名称
description: ...                 # 描述
category: xiaodazi_e2e           # 分类
default_trials: 1                # 默认试验次数

metadata:
  version: "1.0.0"
  dimension: e2e                 # 测评维度
  runner: run_e2e_eval           # 执行器

tasks:
  - id: A1                       # 用例 ID
    description: "..."           # 用例描述
    category: e2e_file           # 用例分类
    input:
      user_query: "用户输入"      # 用户查询（单轮）
      files:                     # 附件文件
        - "docs/benchmark/data/xxx.xlsx"
    expected_outcome: {}          # 预期结果（供评分器参考）
    graders:                     # 评分器配置
      - type: code               # 代码评分器
        name: check_no_tool_errors
        check: "check_no_tool_errors()"
      - type: model              # 模型评分器
        rubric: grade_response_quality
        min_score: 4             # 最低评分（1-5）
    trials: 1                    # 试验次数
    timeout_seconds: 600         # 超时时间
    tags: ["e2e", "excel"]       # 标签
    metadata:
      # 多轮对话定义（可选）
      multi_turn_sequence:
        - new_conversation: true   # true=新建会话, false=同会话追加
          user_query: "第一轮"
        - new_conversation: false
          user_query: "第二轮追问"
      expected_behavior: "..."    # 预期行为（供 Judge 参考）
```

### 5.1 单轮用例示例

```yaml
- id: A1
  description: "格式混乱 Excel 分析"
  input:
    user_query: "帮我分析这个表格的销售趋势"
    files:
      - "docs/benchmark/data/messy_sales.xlsx"
  graders:
    - type: code
      name: check_no_tool_errors
      check: "check_no_tool_errors()"
    - type: model
      rubric: grade_response_quality
      min_score: 4
  timeout_seconds: 600
```

### 5.2 多轮对话用例示例

```yaml
- id: B1
  description: "跨会话记忆验证"
  input:
    user_query: ""               # 多轮时此字段为空
  metadata:
    multi_turn_sequence:
      - new_conversation: true   # 会话 1
        user_query: "帮我写篇关于咖啡的文章"
      - new_conversation: false  # 同会话追问
        user_query: "我喜欢毒舌风格，重新写"
      - new_conversation: true   # 会话 2（新建）
        user_query: "写篇关于茶文化的文章"
      - new_conversation: true   # 会话 3（新建）
        user_query: "你记住了什么关于我的写作偏好？"
```

### 5.3 Playbook 跨会话用例示例（含 API 中间步骤）

```yaml
- id: P3
  description: "Playbook 闭环 — 跨会话：提取→确认→注入→相似执行"
  metadata:
    multi_turn_sequence:
      - new_conversation: true
        user_query: "分析这份产品反馈数据"
        files: ["docs/benchmark/data/playbook_test/product_feedback.xlsx"]
      - new_conversation: true
        user_query: "分析这份客户满意度数据"
        files: ["docs/benchmark/data/playbook_test/customer_survey.xlsx"]
    inter_session_steps:          # 会话间 API 操作
      - description: "等待 playbook_extraction 后台任务"
        wait_seconds: 10
      - description: "获取提取的 playbook ID"
        api_call: "GET /api/v1/playbook?status=draft&source=auto"
      - description: "确认策略"
        api_call: "POST /api/v1/playbook/{id}/action body={action:approve}"
```

---

## 六、评分报告解读

报告输出到 `evaluation/reports/` 目录，格式为 JSON + Markdown。

### 6.1 报告结构

```json
{
  "suite_id": "xiaodazi_e2e_phase1_core",
  "total_tasks": 6,
  "passed": 5,
  "failed": 1,
  "pass_rate": 0.833,
  "results": [
    {
      "task_id": "A1",
      "status": "PASS",
      "grade_results": [
        {
          "grader_type": "code",
          "grader_name": "check_no_tool_errors",
          "passed": true,
          "score": 1.0,
          "details": {
            "total_calls": 7,
            "error_count": 0
          }
        },
        {
          "grader_type": "model",
          "grader_name": "grade_response_quality",
          "passed": true,
          "score": 0.85,
          "explanation": "Agent 正确识别...",
          "details": {
            "weighted_score": 4.25,
            "strengths": ["准确识别产品A为最佳", "..."],
            "weaknesses": ["缺少可视化图表"]
          },
          "needs_human_review": true
        }
      ]
    }
  ]
}
```

### 6.2 PASS/FAIL 判定规则

```
整体 PASS = 所有 Code Grader 通过
            （Model Grader 不影响 PASS/FAIL，仅提供诊断）

单个 Code Grader:
  check_no_tool_errors()        → 有工具报错即 FAIL
  check_token_limit(25000)      → 超过 25K token 即 FAIL
  check_backtrack_occurred(1)   → 未发生回溯即 FAIL（I 系列用例）
```

### 6.3 关键字段说明

| 字段 | 含义 | 关注点 |
|---|---|---|
| `grader_type` | code / model | 哪个评分器 |
| `passed` | true/false | 是否通过 |
| `score` | 0-1 | 具体分数 |
| `explanation` | 评分说明 | **最重要：失败原因** |
| `details.strengths` | 做得好的方面 | 保持优势 |
| `details.weaknesses` | 弱项列表 | **优化方向** |
| `needs_human_review` | 是否需人工复核 | mock 评分必须标记 |

---

## 七、失败分析流程

### 7.1 标准排查步骤（不允许跳过）

```
发现 FAIL
    │
    ▼
Step 1: 读评分报告
    evaluation/reports/e2e_phase1_*.json
    │
    ▼
Step 2: 区分失败类型
    │
    ├─ 基础设施失败
    │   特征: LLM 未配置、文件找不到、API Key 缺失
    │   修复: 修配置/环境，重跑
    │
    ├─ 评分器故障
    │   特征: "LLM服务未配置，返回模拟评分"
    │   修复: 修评分器 LLM 配置
    │
    ├─ Agent 质量不达标
    │   特征: 评分器正常工作，但给了低分
    │   修复: 优化提示词/策略
    │
    └─ 工具执行失败
        特征: check_no_tool_errors 不通过
        修复: 修工具/回溯策略
    │
    ▼
Step 3: 修复后重跑验证
```

### 7.2 服务端日志分析

E2E 测试启动的服务日志保存在临时文件中（脚本会打印路径）。

```bash
# 查看 Agent 工具调用链
grep "Turn\|工具调用参数\|error\|失败" /path/to/server.log

# 查看 LLM 配置是否生效
grep "LLM Profiles\|已合并\|agent.model" /path/to/server.log

# 查看文件处理
grep "上传成功\|file://\|xlsx" /path/to/server.log
```

### 7.3 质量优化闭环

```
E2E 失败
    │
    ├─ 基础设施问题 → 修代码/配置 → 重跑 → 验证通过
    │
    └─ 质量问题 → 分析 weaknesses
        │
        ├─ 提示词不够好 → 优化 prompt.md / intent_prompt.md
        ├─ 工具选择错误 → 优化 Skill 配置 / 工具裁剪策略
        ├─ 回溯不充分 → 调整回溯策略 / 错误分类
        ├─ 上下文丢失 → 检查 compaction / injector
        └─ 模型能力不足 → 切换更强模型 / 调整 temperature
        │
        └─ 修改 → 重跑 E2E → 验证分数提升
```

---

## 八、闭环自动化（失败 → 回归套件）

`evaluation/loop_automation.py` 实现了失败用例自动回归的闭环：

```
E2E 运行结束 → 检测 FAIL 用例 → 根因分类
    │
    ├─ PROMPT_QUALITY    → 提示词优化
    ├─ TOOL_FAILURE      → 工具修复
    ├─ CONTEXT_OVERFLOW   → 上下文策略调整
    ├─ BACKTRACK_FAILURE  → 回溯逻辑优化
    └─ ...
    │
    └─ 自动导出 → evaluation/suites/xiaodazi/e2e_regression_YYYYMMDD_HHMMSS.yaml
                    （可直接作为回归套件重跑验证修复效果）
```

---

## 九、开发者快速上手指南

### Step 1：首次运行（验证环境）

```bash
source /Users/liuyi/Documents/langchain/liuy/bin/activate

# 1. 先验证回滚（不需要 LLM，最快验证环境是否正常）
python scripts/verify_rollback_e2e.py

# 2. 跑基础连通性
python scripts/run_eval.py --phase connectivity

# 3. 跑单个 E2E 用例
python scripts/run_e2e_auto.py --case C1
```

### Step 2：日常开发验证

```bash
# 改了提示词 → 跑 A1 验证效果
python scripts/run_e2e_auto.py --case A1 --no-start --port 8000

# 改了回溯逻辑 → 跑 I 系列
python scripts/run_e2e_auto.py --suite phase2_scenarios --case I1

# 改了记忆模块 → 跑 B1
python scripts/run_e2e_auto.py --case B1

# 改了 Playbook → 跑 P 系列
python scripts/run_e2e_auto.py --suite playbook_learning
```

### Step 3：全量回归（发版前）

```bash
# Claude 全量
python scripts/run_e2e_auto.py --clean --provider claude

# Qwen 全量
python scripts/run_e2e_auto.py --clean --provider qwen

# 查看报告
python scripts/generate_eval_report.py --latest
```

### Step 4：新增测试用例

1. 在 `docs/benchmark/data/` 添加测试数据文件
2. 在对应的 `evaluation/suites/xiaodazi/e2e/*.yaml` 中添加 task 定义
3. 如需新评分标准，在 `evaluation/config/judge_prompts.yaml` 添加 rubric
4. 运行验证：`python scripts/run_e2e_auto.py --case <新用例ID>`
5. 检查报告：`evaluation/reports/` 目录

---

## 十、配置参考

### 10.1 `evaluation/config/settings.yaml` 关键配置

```yaml
# 评分器配置
graders:
  code:
    enabled: true
    default_token_limit: 100000    # 默认 Token 上限
  model:
    enabled: true
    provider: claude               # LLM-as-Judge 使用 Claude
    model: claude-opus-4-6         # 模型版本
    extended_thinking: true        # 启用深度思考
    timeout_seconds: 300           # 评分超时
  human:
    enabled: true
    weekly_sample: 100             # 每周人工校准样本数
    raters: 3                      # 标注人数

# QoS 分级
qos:
  free:    { max_tasks: 10,  model_grader: false }
  basic:   { max_tasks: 50,  model_grader: true }
  pro:     { max_tasks: 200, model_grader: true }
  enterprise: { max_tasks: -1, model_grader: true }

# CI/CD
ci:
  fail_on_regression: true
  regression_threshold: 0.05      # 5% 回归即失败
```

### 10.2 `run_e2e_auto.py` 完整参数

| 参数 | 说明 | 默认值 |
|---|---|---|
| `--clean` | 清理旧报告和 checkpoint | 否 |
| `--case <ID>` | 只跑指定用例 | 全部 |
| `--from <ID>` | 从指定用例开始 | 从头 |
| `--suite <name>` | 指定测试套件 | `phase1_core` |
| `--provider <name>` | LLM 提供商（claude/qwen） | 默认配置 |
| `--no-start` | 不自动启停服务 | 自动启停 |
| `--port <N>` | 服务端口 | 8000 |
| `--defer-grading` | 延迟评分 | 即时评分 |
| `--parallel` | 并行执行 | 串行 |

---

## 十一、关键文件速查表

| 需求 | 文件 |
|---|---|
| 了解所有测试用例 | `docs/benchmark/test_cases.md` |
| 了解评估方法论 | `docs/benchmark/xiaodazi_eval.md` |
| 查看/修改评分配置 | `evaluation/config/settings.yaml` |
| 查看/修改 Judge 提示词 | `evaluation/config/judge_prompts.yaml` |
| 查看 Phase 1 用例 | `evaluation/suites/xiaodazi/e2e/phase1_core.yaml` |
| 查看 Phase 2 用例 | `evaluation/suites/xiaodazi/e2e/phase2_scenarios.yaml` |
| 查看代码评分器实现 | `evaluation/graders/code_based.py` |
| 查看模型评分器实现 | `evaluation/graders/model_based.py` |
| 查看 E2E 执行逻辑 | `evaluation/scripts/run_e2e_eval.py` |
| 查看 HTTP 适配器 | `evaluation/adapters/http_agent.py` |
| 查看评估架构设计 | `docs/architecture/11-evaluation.md` |
| 查看自动回归逻辑 | `evaluation/loop_automation.py` |
| 查看 E2E 自动化报告 | `docs/benchmark/E2E_AUTOMATION_REPORT.md` |
| 查看测试数据 | `docs/benchmark/data/` |
