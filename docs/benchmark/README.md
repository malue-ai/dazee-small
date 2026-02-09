# 小搭子 Benchmark & E2E 测评

> 面向小白用户的对比测试 + 端到端自动化测评

## 最新结果（2026-02-08）

| Provider | A1 Excel | B1 记忆 | D4 错误恢复 | C1 Token | B9 回滚 | B10 中止 | 通过率 |
|----------|---------|---------|------------|---------|---------|---------|--------|
| **claude** (sonnet-4-5) | ✅ 4 轮 | ✅ 5 轮 | ✅ 多轮 | ✅ 2 轮 | ✅ | ✅ | **100%** |
| **qwen** (qwen3-max) | ⚠️ 10+ | ✅ | ⏳ 23+ | ✅ | ✅ | ✅ | 83%+ |

> B9/B10 为状态管理层验证，不依赖 LLM Provider，两端均 PASS。

**Grader**: Claude Opus 4.6 + Extended Thinking（独立评估，不做 PASS/FAIL 闸门）

## 目录结构

```
docs/benchmark/
├── README.md                     # 本文件
├── E2E_AUTOMATION_REPORT.md      # E2E 操作指南 + 最新结果 + 修复记录
├── test_cases.md                 # 完整对比测试用例（17 个）
└── data/                         # 测试数据
    ├── generate_test_data.py     # 一键生成测试数据
    ├── messy_sales.xlsx          # A1 用 — 格式混乱 Excel
    ├── error_prone.csv           # D4 用 — 含异常值 CSV
    ├── academic_abstract.txt     # A2 用 — 论文摘要
    ├── rollback_test/            # B9/B10 用 — 文件回滚验证
    │   ├── config.json           # 项目配置（端口 3000）
    │   ├── nginx.conf            # Nginx 反代配置
    │   ├── README.md             # 项目说明
    │   └── docs/                 # 5 个公司文档（含"北极星科技"）
    │       ├── about.md / product.md / team.md / contact.md / faq.md
    └── ...
```

## 快速开始

```bash
# 全量 E2E（claude provider）
python scripts/run_e2e_auto.py --clean --provider claude

# 全量 E2E（qwen provider）
python scripts/run_e2e_auto.py --clean --provider qwen

# B9/B10 回滚验证（无需 LLM，秒级完成）
python scripts/verify_rollback_e2e.py          # 全部 6 个子场景
python scripts/verify_rollback_e2e.py --case B9 # 仅异常回滚
python scripts/verify_rollback_e2e.py --case B10 -v  # 用户中止（详细）

# 后台运行（推荐，长任务）
PYTHONUNBUFFERED=1 nohup python scripts/run_e2e_auto.py --clean --provider claude > /tmp/e2e.log 2>&1 &
grep -E "PASS|FAIL|▶" /tmp/e2e.log   # 查进度
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

详见 [E2E_AUTOMATION_REPORT.md](E2E_AUTOMATION_REPORT.md)

## 对比维度（vs clawdbot/OpenClaw）

| 维度 | 用例数 | 说明 |
|------|--------|------|
| **A. 效果差异化** | 3 | 任务完成率 + 用户体验 |
| **B. 特色差异化** | 10 | 记忆/环境感知/HITL/长任务/回滚安全 |
| **C. Token 消耗** | 3 | 量化成本对比 |
| **D. 场景差异化** | 6 | 各自强项 + 短板 |
| **E. 电脑操作 + 浏览器** | 7 | 长程 GUI/浏览器任务可靠性（E1-E4 桌面、E5-E7 浏览器） |

详见 [test_cases.md](test_cases.md)

## 相关配置

| 文件 | 用途 |
|------|------|
| `evaluation/config/settings.yaml` | Grader LLM 配置（Opus 4.6） |
| `evaluation/config/judge_prompts.yaml` | LLM-as-Judge 评估提示词 |
| `evaluation/suites/xiaodazi/e2e/phase1_core.yaml` | E2E 用例定义（6 个用例） |
| `scripts/verify_rollback_e2e.py` | B9/B10 回滚独立验证（6 个子场景） |
| `instances/xiaodazi/config/llm_profiles.yaml` | Provider 模板（qwen/claude 一键切换） |
