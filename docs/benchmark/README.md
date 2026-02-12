# 小搭子 Benchmark & E2E 测评

> 面向开源社区（开发者 + 用户）的对比测试 + 端到端自动化测评

## 最新结果（2026-02-08）

| Provider | A1 Excel | B1 记忆 | D4 错误恢复 | C1 Token | B9 回滚 | B10 中止 | 通过率 |
|----------|---------|---------|------------|---------|---------|---------|--------|
| **claude** (sonnet-4-5) | ✅ 4 轮 | ✅ 5 轮 | ✅ 多轮 | ✅ 2 轮 | ✅ | ✅ | **100%** |
| **qwen** (qwen3-max) | ⚠️ 10+ | ✅ | ⏳ 23+ | ✅ | ✅ | ✅ | 83%+ |
| **glm** (glm-5) | ⏳ | ⏳ | ⏳ | ⏳ | ✅ | ✅ | — |

> B9/B10 为状态管理层验证，不依赖 LLM Provider，两端均 PASS。

**Grader**: Claude Opus 4.6 + Extended Thinking（独立评估，不做 PASS/FAIL 闸门）

## 测评维度

| 维度 | 用例数 | 说明 | E2E 阶段 |
|------|--------|------|----------|
| **A. 效果差异化** | 3 | 任务完成率 + 用户体验 | Phase 1 |
| **B. 特色差异化** | 10 | 记忆/环境感知/HITL/长任务/回滚安全 | Phase 1 |
| **C. Token 消耗** | 3 | 量化成本对比 | Phase 1 |
| **D. 场景差异化** | 6 | 各自强项 + 短板 | Phase 1 |
| **E. 电脑操作** | 4 | 长程 GUI 任务可靠性 | Phase 1 |
| **F. 开发者体验** | 4 | Skill 扩展 / 多模型 / 实例隔离 / 上下文工程 | **Phase 2** |
| **G. 垂直场景** | 5 | 写稿 / 表格 / 研究 / 办公 / 隐私 | **Phase 2** |
| **H. 产品健壮性** | 4 | 降级 / 大文件 / 多语言 / 中断恢复 | **Phase 2** |
| **P. Playbook 学习** | 5 | 策略提取 / 确认 / 匹配注入 / 拒绝 / 删除清理 | **Phase 2** |

详见 [test_cases.md](test_cases.md)

## 目录结构

```
docs/benchmark/
├── README.md                          # 本文件
├── E2E_AUTOMATION_REPORT.md           # E2E 操作指南 + 最新结果
├── test_cases.md                      # 完整对比测试用例（39 个）
└── data/                              # 测试数据
    ├── generate_test_data.py          # Phase1 数据生成（A1/B4 等）
    ├── generate_benchmark_data.py     # Phase2 数据生成（F/G/H 维度）
    │
    │  ── Phase 1 数据 ──
    ├── messy_sales.xlsx               # A1: 格式混乱 Excel
    ├── error_prone.csv                # D4: 含异常值 CSV
    ├── academic_abstract.txt          # A2: 论文摘要
    ├── coffee_article.txt             # B1: 毒舌风格样本
    ├── tea_culture_prompt.txt         # B1: 茶文化写作提示
    ├── mixed_files/                   # B4: 100 个混合文件
    ├── rollback_test/                 # B9/B10: 文件回滚验证
    │   ├── config.json / nginx.conf / README.md
    │   └── docs/ (about/product/team/contact/faq.md)
    │
    │  ── Phase 2 数据 ──
    ├── pipeline_test/                 # G2: 表格搭子
    │   ├── quarterly_sales_raw.xlsx   #   200 行, 6 种格式问题
    │   └── expected_result.json       #   清洗后 195 行, 验证规则
    ├── style_test/                    # G1: 写稿搭子
    │   ├── coffee_sample.txt          #   毒舌犀利风格范文 (3 篇)
    │   ├── book_sample.txt            #   温暖治愈风格范文 (3 篇)
    │   └── expected_result.json       #   风格关键词 + 隔离规则
    ├── research_test/                 # G3: 研究搭子
    │   ├── my_draft.md                #   论文初稿 (含引用遗漏)
    │   └── expected_result.json       #   润色规则 + 引用检查点
    ├── office_test/                   # G4: 办公搭子
    │   ├── meeting_notes_raw.txt      #   非结构化会议纪要
    │   └── expected_result.json       #   5 个行动项 + 日期推算
    ├── privacy_test/                  # G5: 隐私搭子
    │   ├── sample_contract.txt        #   股权收购协议
    │   ├── contract_template.md       #   对照检查模板
    │   └── expected_result.json       #   5 个风险点 + 离线验证
    ├── context_test/                  # F4: 上下文工程极限
    │   ├── report_q1.txt              #   Q1 报告 (~15KB)
    │   ├── report_q2.txt              #   Q2 报告 (~18KB)
    │   ├── competitor_analysis.md     #   竞品分析 (~20KB)
    │   └── expected_result.json       #   Q1=¥120万 精确引用验证
    ├── stress_test/                   # H2: 大文件压力测试
    │   ├── large_doc_100kb.txt        #   100KB 文本
    │   ├── large_data_500kb.csv       #   500KB CSV (~12000 行)
    │   └── expected_result.json       #   处理策略验证
    └── playbook_test/                 # P1-P5: Playbook 在线学习
        ├── product_feedback.xlsx      #   150 行用户反馈 (5 类问题)
        ├── customer_survey.xlsx       #   200 行客户满意度 (6 类服务)
        └── expected_result.json       #   全生命周期验证规则
```

## 快速开始

```bash
# ── Phase 1: 核心能力（已有 6 用例） ──

# 全量 E2E
python scripts/run_e2e_auto.py --clean --provider claude

# GLM-5 全量 E2E
python scripts/run_e2e_auto.py --clean --provider glm

# 单用例调试
python scripts/run_e2e_auto.py --case A1

# B9/B10 回滚验证（无需 LLM，秒级）
python scripts/verify_rollback_e2e.py

# ── Phase 2: 开源场景（新增 6 用例） ──

# 生成 Phase2 测试数据（首次必须）
python docs/benchmark/data/generate_benchmark_data.py

# 全量 Phase2 场景
python scripts/run_e2e_auto.py --clean --suite phase2_scenarios

# 单个场景
python scripts/run_e2e_auto.py --case G2   # 表格搭子
python scripts/run_e2e_auto.py --case G4   # 办公搭子
python scripts/run_e2e_auto.py --case G1   # 写稿搭子（跨会话）
python scripts/run_e2e_auto.py --case F4   # 上下文工程

# ── Playbook 在线学习验证（P1-P5） ──

# 逐个验证（推荐，playbook 有状态依赖）
python scripts/run_e2e_auto.py --case P1 --provider qwen   # 提取 + 持久化
python scripts/run_e2e_auto.py --case P2 --provider qwen   # 确认 + 匹配 + 注入
python scripts/run_e2e_auto.py --case P3 --provider qwen   # 完整闭环（跨会话）
python scripts/run_e2e_auto.py --case P4 --provider qwen   # 拒绝流程
python scripts/run_e2e_auto.py --case P5 --provider qwen   # 删除 + 清理

# 后台运行
PYTHONUNBUFFERED=1 nohup python scripts/run_e2e_auto.py --clean --suite phase2_scenarios > /tmp/e2e_p2.log 2>&1 &
```

## 评估体系

```
Agent 执行任务 → Code Grader (PASS/FAIL) + LLM Judge (诊断报告)
                        ↓                          ↓
                  流程通没通                   流程好不好
              (工具错误、Token)         (每个环节的质量 + 优化建议)
```

| 评分器 | 角色 | 决定 PASS/FAIL | 输出 |
|--------|------|---------------|------|
| Code Grader | 确定性检查 | **是** | passed/failed |
| Model Grader (Opus 4.6) | 质量评估 | **否** | 管道诊断报告 + 优化建议 |

### Phase 2 专用 Graders（高标准严要求）

| Grader | 用例 | 评分铁律 |
|--------|------|---------|
| `grade_data_pipeline_quality` | G2 | 数据丢失（行数 < 195）→ ≤ 2 分 |
| `grade_action_item_extraction` | G4 | 日期推算错误（差 > 1 天）→ ≤ 2 分 |
| `grade_research_quality` | G3 | 润色改变原意 → ≤ 2 分 |
| `grade_style_memory` | G1 | 跨会话风格丢失 → ≤ 2 分 |
| `grade_context_engineering` | F4 | Q1 收入引用错误（非 ¥120 万）→ ≤ 2 分 |
| `grade_playbook_extraction` | P1 | 有工具调用但未提取 → ≤ 2 分 |
| `grade_playbook_application` | P2 | 有 APPROVED 策略但未注入 → ≤ 2 分 |
| `grade_playbook_lifecycle` | P3 | 跨会话策略未注入（闭环断裂）→ ≤ 2 分 |
| `grade_playbook_crud` | P4/P5 | 被拒绝/删除策略仍注入 → ≤ 2 分 |

**设计原则**：每个 Grader 都有"铁律"——触犯即低分，不妥协。

## Phase 2 用例详情

### G2 — 表格搭子（核心 Demo）

| 项 | 内容 |
|----|------|
| **Query** | 分析季度销售数据（清洗+分析+报告） |
| **Data** | `pipeline_test/quarterly_sales_raw.xlsx` (200 行, 6 种格式问题) |
| **Expected** | 清洗后 195 行（零丢行），日期统一，金额转数字，回答 3 个问题 |
| **Grader 铁律** | 数据丢失 → ≤ 2 分；最佳产品答错 → analysis_accuracy ≤ 2 |

### G4 — 办公搭子

| 项 | 内容 |
|----|------|
| **Query** | 整理会议纪要，提取行动项，推算截止日期 |
| **Data** | `office_test/meeting_notes_raw.txt` (非结构化纪要，5 人，5 个行动项) |
| **Expected** | ≥ 4 个行动项，"下周三" → 2026-02-17，责任人精确到人名 |
| **Grader 铁律** | 日期推算差 > 1 天 → ≤ 2 分；编造行动项 → 扣分 |

### G3 — 研究搭子

| 项 | 内容 |
|----|------|
| **Query** | 润色论文摘要 + 检查引用遗漏 |
| **Data** | `research_test/my_draft.md` (LLM 记忆机制综述初稿) |
| **Expected** | 术语统一，引用遗漏标注≥2处，润色不改原意 |
| **Grader 铁律** | 改变原意 → ≤ 2 分；引用检查全漏 → ≤ 2 分 |

### G1 — 写稿搭子（跨会话记忆）

| 项 | 内容 |
|----|------|
| **Query** | 学习毒舌风格 → 写文章 → 新会话验证记忆 |
| **Data** | `style_test/coffee_sample.txt` (毒舌犀利风格 3 篇) |
| **Expected** | 会话 2 自动应用毒舌风格（不重复提）；回到温和风格 = 记忆失败 |
| **Grader 铁律** | 跨会话风格丢失 → ≤ 2 分（记忆系统失效） |

### F4 — 上下文工程极限

| 项 | 内容 |
|----|------|
| **Query** | 3 份大文件 + 4 轮深度分析 → 写战略摘要 |
| **Data** | `context_test/` (Q1=15KB, Q2=18KB, 竞品=20KB) |
| **Expected** | 第 4 轮引用 Q1 收入精确 = ¥120 万，token 不膨胀 |
| **Grader 铁律** | Q1 收入引用错误 → ≤ 2 分；出现幻觉数据 → 扣 2 分 |

### H1 — LLM 服务降级

| 项 | 内容 |
|----|------|
| **Query** | 写分析 → 翻译（验证多轮上下文保留） |
| **Data** | 无文件 |
| **Expected** | 翻译内容与分析一致（上下文完整） |
| **Grader** | 通用 `grade_response_quality` |

### P1 — Playbook 策略提取

| 项 | 内容 |
|----|------|
| **Query** | 分析产品反馈数据，找出 TOP3 问题 |
| **Data** | `playbook_test/product_feedback.xlsx` (150 行, 5 类问题, 界面卡顿 35%) |
| **Expected** | 提取触发、DRAFT 状态、JSON 落盘、tool_sequence 非空 |
| **Grader 铁律** | 有工具调用但未提取 → ≤ 2 分 |

### P2 — 策略匹配 + 注入

| 项 | 内容 |
|----|------|
| **Query** | 分析客户满意度数据，找出最差类别 |
| **Data** | `playbook_test/customer_survey.xlsx` (200 行, 6 类服务, 售后服务最低) |
| **前置** | 已有 APPROVED 数据分析策略 |
| **Expected** | Mem0 语义匹配 score >= 0.3、`<playbook_hint>` 注入 |
| **Grader 铁律** | 有 APPROVED 策略但未注入 → ≤ 2 分 |

### P3 — 完整闭环（跨会话）

| 项 | 内容 |
|----|------|
| **流程** | 会话 1 分析反馈 → 提取 → approve → 会话 2 分析满意度 → 策略注入 |
| **Expected** | 8 项验证：提取、确认、持久化、跨会话注入、工具相似、质量持平 |
| **Grader 铁律** | 跨会话策略未注入 → ≤ 2 分（闭环断裂） |

### P4 — 拒绝流程

| 项 | 内容 |
|----|------|
| **流程** | 提取 → reject → 会话 2 验证不注入 |
| **Expected** | REJECTED 状态、后续无 hint、任务仍能完成 |
| **Grader 铁律** | 被拒绝策略仍注入 → ≤ 2 分 |

### P5 — 删除 + 清理

| 项 | 内容 |
|----|------|
| **流程** | APPROVED 策略 → DELETE → 验证 JSON 删除 + 后续无注入 |
| **Expected** | JSON 删除、index 清理、后续无 hint |
| **Grader 铁律** | 删除后 JSON 仍存在 → ≤ 2 分；删除后仍注入 → ≤ 2 分 |

## 合成数据生成

```bash
# Phase 1 数据（已有）
cd docs/benchmark/data && python generate_test_data.py

# Phase 2 数据（新增）
cd docs/benchmark/data && python generate_benchmark_data.py
```

每个数据目录都包含 `expected_result.json`，记录了 Grader 用于验证的期望结果：

```json
// pipeline_test/expected_result.json 示例
{
  "total_data_rows": 200,
  "expected_clean_rows": 195,
  "validation_rules": {
    "zero_data_loss": "清洗后 195 行，不允许丢任何数据行",
    "date_unified": "所有日期统一为 YYYY-MM-DD 格式",
    "amount_numeric": "所有金额为 float，无文本符号",
    "best_product": "销售额最高的产品必须与原始数据 sum 一致"
  }
}
```

## 相关配置

| 文件 | 用途 |
|------|------|
| `evaluation/config/settings.yaml` | Grader LLM 配置（Opus 4.6） |
| `evaluation/config/judge_prompts.yaml` | LLM-as-Judge 评估提示词（含 Phase2 专用 graders） |
| `evaluation/suites/xiaodazi/e2e/phase1_core.yaml` | Phase1 用例定义（6 个） |
| `evaluation/suites/xiaodazi/e2e/phase2_scenarios.yaml` | **Phase2 用例定义（6 个 — 新增）** |
| `scripts/run_e2e_auto.py` | E2E 运行器（Phase 0 + 服务管理 + 报告） |
| `scripts/verify_rollback_e2e.py` | B9/B10 回滚验证（6 个子场景） |
| `instances/xiaodazi/config/llm_profiles.yaml` | Provider 模板（含 claude/qwen/deepseek/glm） |

详见 [E2E_AUTOMATION_REPORT.md](E2E_AUTOMATION_REPORT.md)
