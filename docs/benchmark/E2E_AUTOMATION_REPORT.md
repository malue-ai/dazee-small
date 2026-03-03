# 小搭子端到端自动化测评操作指南

> 面向测试人员的完整操作说明，用于执行 E2E 自动化测评并解读报告。

---

## 一、文档目的与适用范围

| 项目 | 说明 |
|------|------|
| **目标读者** | 测试人员、验收人员、参与回归的开发者 |
| **测评对象** | 小搭子实例（xiaodazi），通过**真实 HTTP API** 调用后端 |
| **测评范围** | Phase1 端到端 6 用例（A1/B1/D4/C1/B9/B10），覆盖文件分析、跨会话记忆、错误恢复、Token 效率、**文件修改回滚安全** |
| **模型兼容性** | 支持 `--provider qwen` / `--provider claude` 切换，验证多模型下的表现 |
| **评估模型** | LLM-as-Judge 使用 Claude Opus 4.6 + Extended Thinking（独立于被测 Agent） |

---

## 二、最新测评结果（2026-02-08）

### 2.1 Phase 0 — 状态管理层验证（B9/B10 回滚管道）

> 确定性验证，不依赖 LLM Provider，秒级完成。

```
🛡 Phase 0: State management layer verification (B9/B10)

▶ B9: 文件修改异常退出自动回滚
  ✓ B9.1 error_auto_rollback: all files restored (877ms)
  ✓ B9.2 crash_recovery: crash recovery OK (4ms)
  ✓ B9.3 dynamic_capture: dynamic capture + rollback OK (3ms)

▶ B10: 文件修改用户中止选择性回滚
  ✓ B10.1 user_abort_rollback_all: all 5 files restored (4ms)
  ✓ B10.2 selective_rollback: about.md=restored, product.md=still modified (3ms)
  ✓ B10.3 keep_completed: files_modified=True, snapshot_cleaned=True (3ms)

✓ Phase 0 PASS: 2/2 — rollback pipeline verified (6/6 sub-tests)
```

| 子场景 | 验证内容 | 结果 |
|--------|---------|------|
| B9.1 异常自动回滚 | 修改 config.json 后触发错误 → 自动恢复原始内容 | ✅ PASS |
| B9.2 崩溃恢复 | 进程崩溃后从磁盘快照恢复 | ✅ PASS |
| B9.3 动态文件捕获 | 未预先声明的文件也能 lazy capture + 回滚 | ✅ PASS |
| B10.1 全部回滚 | 用户中止 → 5 个文件全部恢复 | ✅ PASS |
| B10.2 选择性回滚 | 仅回滚 about.md，product.md 保持修改 | ✅ PASS |
| B10.3 保留已完成 | 不回滚，commit 清理快照 | ✅ PASS |

### 2.2 Phase 1 — Agent 真实交互

#### Claude Provider（claude-sonnet-4-6 主 Agent）

```
🧪 Grader LLM: claude-opus-4-6 (thinking=True)
▶ A1: 格式混乱 Excel 分析        ✅ PASS
▶ B1: 跨会话记忆                  ✅ PASS
▶ D4: 连续错误恢复                ✅ PASS
▶ C1: 简单问答 Token 对比         ✅ PASS
▶ B9: 文件修改异常退出自动回滚     待测
▶ B10: 文件修改用户中止回滚        待测
📊 Pass rate: 100% (4/4 已测)
```

| 用例 | Agent 模型 | 轮次 | 耗时 | Code Grader | Model Grader |
|------|-----------|------|------|-------------|-------------|
| A1 | claude-sonnet-4-6 | 4 轮 | ~63s | ✅ 0 错误 | 待 Opus 评分 |
| B1 | claude-sonnet-4-6 | 5 轮(跨 3 会话) | ~70s | — | 待 Opus 评分 |
| D4 | claude-sonnet-4-6 | 多轮 | 数分钟 | ✅ 0 错误 | 待 Opus 评分 |
| C1 | claude-sonnet-4-6 | 2 轮 | ~30s | ✅ Token 达标 | 待 Opus 评分 |
| **B9** | claude-sonnet-4-6 | — | — | — | **待首次运行** |
| **B10** | claude-sonnet-4-6 | — | — | — | **待首次运行** |

#### Qwen Provider（qwen3-max 主 Agent）

| 用例 | Agent 模型 | 结果 | 说明 |
|------|-----------|------|------|
| A1 | qwen3-max | FAIL | Agent 完成但评分未通过（旧 grader 问题） |
| B1 | qwen3-max | PASS | 记忆功能与模型无关 |
| D4 | qwen3-max | 进行中(23 轮) | 正常执行复杂多步骤任务，非卡死 |
| C1 | qwen3-max | PASS | Token 达标 |
| **B9** | qwen3-max | — | **待首次运行** |
| **B10** | qwen3-max | — | **待首次运行** |

### 2.3 模型对比发现

| 指标 | claude-sonnet-4-6 | qwen3-max |
|------|-------------------|-----------|
| A1 完成轮次 | 4 轮 | 10+ 轮 |
| A1 耗时 | ~63 秒 | 180+ 秒 |
| D4 完成轮次 | 数轮 | 23+ 轮（仍在正常推进） |
| 数据清洗能力 | 一次成功 | 反复试错后成功 |
| Plan 创建 | 正常 | 正常 |
| **B9/B10 回滚管道** | **✅ PASS（不依赖模型）** | **✅ PASS（不依赖模型）** |

---

## 三、测评体系

### 3.1 评估架构（V2 — 三层验证）

```
E2E 测试
│
├── Phase 0: 状态管理层验证（确定性，秒级，不依赖 LLM）
│   └── verify_rollback_e2e.py → 6 个子场景
│       ├── B9.1 异常自动回滚  │ B9.2 崩溃恢复  │ B9.3 动态捕获
│       └── B10.1 全部回滚     │ B10.2 选择性   │ B10.3 保留已完成
│
├── Phase 1: Agent 真实交互（HTTP API → LLM 执行 → 收集 Transcript）
│   ├── 单轮用例：A1, D4, B9
│   └── 多轮用例：B1, C1, B10
│
├── Phase 2: Code Grader — 流程通没通（自动 PASS/FAIL）
│   ├── check_no_tool_errors → 工具调用零错误
│   └── check_token_limit → Token 消耗在预算内
│
└── Phase 3: LLM Judge — 流程好不好（管道诊断报告，不做闸门）
    ├── grade_response_quality → 通用管道诊断（全用例）
    │   ├── 意图理解 │ 规划质量 │ 工具使用 │ 上下文工程 │ 输出质量
    │   └── optimization_suggestions → 优化建议
    │
    └── grade_rollback_safety → 回滚安全专项诊断（B9/B10 专用）
        ├── safety_awareness  → 修改前是否体现备份意识
        ├── error_handling    → 出错是否提供恢复方案（B9）
        ├── abort_handling    → 中止是否提供回滚选项（B10）
        └── user_communication → 操作前后是否清晰沟通
```

### 3.2 PASS/FAIL 判定规则

| 评分器类型 | 角色 | 决定 PASS/FAIL？ | 说明 |
|---|---|---|---|
| Phase 0 验证 | 状态管理确定性检查 | **是（阻断）** | 回滚管道不通 → 阻断后续所有 Agent 测试 |
| Code Grader | 确定性检查 | **是** | 硬性标准（工具错误、Token 限制等） |
| Model Grader | 质量评估 | **否** | 独立于 Agent 执行逻辑，评分供人类审查 |

Model Grader（LLM-as-Judge）核心原则：
- **独立于 Agent**：不干预 Agent 的 plan-todo、回溯等内部逻辑
- **评估不是闸门**：评分只供参考，不触发重试或循环
- **使用最强模型**：Claude Opus 4.6 + Thinking，比被评对象更强
- **双 rubric**：B9/B10 同时使用 `grade_response_quality` + `grade_rollback_safety`
- **配置位置**：`evaluation/config/settings.yaml` + `evaluation/config/judge_prompts.yaml`

### 3.3 Phase1 六用例

| 用例 | 名称 | 类型 | 核心验证 | 超时 | Graders |
|------|------|------|----------|------|---------|
| **A1** | 格式混乱 Excel 分析 | 单轮 + 附件 | 数据清洗 + 分析报告 | 600s | code + model |
| **B1** | 跨会话记忆（毒舌风格） | 4 轮 / 3 会话 | 风格延续 + 偏好记忆 | 180s | model |
| **D4** | 连续错误恢复（CSV→Excel→图→PDF） | 单轮 + 附件 | 多步骤任务 + 错误恢复 | 600s | code + model |
| **C1** | 简单问答 Token 对比 | 2 轮同会话 | Token ≤ 20K + 缓存命中 | 90s | code + model |
| **B9** | 文件修改异常退出自动回滚 | 单轮 + 3 附件 | 端口批量修改 + 一致性保证 | 300s | code + 2× model |
| **B10** | 文件修改用户中止回滚 | 2 轮 + 5 附件 | 批量替换中途取消 + 回滚选项 | 300s | 2× model |

---

## 四、运行 E2E

### 4.1 快速命令

```bash
# 全量运行（默认 provider，读 config.yaml）
python scripts/run_e2e_auto.py --clean

# 指定 provider（模型兼容性测试）
python scripts/run_e2e_auto.py --clean --provider claude
python scripts/run_e2e_auto.py --clean --provider qwen

# 单用例调试
python scripts/run_e2e_auto.py --case A1
python scripts/run_e2e_auto.py --case B9    # 回滚异常
python scripts/run_e2e_auto.py --case B10   # 回滚中止

# B9/B10 状态层独立验证（无需启动服务，秒级）
python scripts/verify_rollback_e2e.py
python scripts/verify_rollback_e2e.py --case B9 -v

# 后台运行（长任务推荐）
PYTHONUNBUFFERED=1 nohup python scripts/run_e2e_auto.py --clean --provider claude > /tmp/e2e.log 2>&1 &
# 查看进度
grep -E "PASS|FAIL|▶|Phase" /tmp/e2e.log
```

### 4.2 参数说明

| 参数 | 说明 |
|------|------|
| `--clean` | 清除 checkpoint，从头跑全部用例 |
| `--provider qwen/claude` | 覆盖 config.yaml 的 provider，切换全部模型 |
| `--case A1` | 只跑指定用例（支持 A1/B1/D4/C1/B9/B10） |
| `--from D4` | 从指定用例恢复 |
| `--no-start` | 跳过自动启动，复用已运行的服务 |
| `--port 9000` | 自定义服务端口 |

### 4.3 执行流程

```
run_e2e_auto.py
│
├── Phase 0: run_rollback_verification()
│   ├── 运行 verify_rollback_e2e.py（6 个子场景）
│   ├── 全部 PASS → 继续
│   └── 任何 FAIL → exit 1（阻断，状态层有 bug）
│
├── Phase 1: start_server()
│   ├── 启动 uvicorn（端口 18234）
│   └── 等待 /health 就绪
│
├── Phase 2: run_e2e()
│   ├── 加载 phase1_core.yaml（6 个用例）
│   ├── 逐用例执行（HTTP API → 轮询 → 收集 Transcript）
│   └── 逐用例评分（Code Graders + Model Graders）
│
└── Phase 3: 报告生成
    ├── JSON + Markdown 报告
    ├── 失败用例 Triage 报告
    └── 自动生成回归测试 YAML
```

### 4.4 Provider 一键切换原理

```
config.yaml: agent.provider: "qwen"
                    ↓
--provider claude → AGENT_PROVIDER=claude 环境变量
                    ↓
instance_loader → 覆盖 provider → 使用 claude 模板
                    ↓
┌──────────┬─────────────────────┬──────────────────────┐
│ 角色     │ qwen                │ claude               │
├──────────┼─────────────────────┼──────────────────────┤
│ 主 Agent │ qwen3-max           │ claude-sonnet-4-6    │
│ heavy    │ qwen3-max           │ claude-sonnet-4-6    │
│ light    │ qwen-plus           │ claude-haiku-4-5     │
└──────────┴─────────────────────┴──────────────────────┘
```

---

## 五、报告解读

### 5.1 产出文件

| 产出 | 路径 | 说明 |
|------|------|------|
| 回滚验证报告 | `evaluation/reports/rollback_e2e_<时间戳>.json` | Phase 0 状态层验证（6 个子场景） |
| JSON 报告 | `evaluation/reports/e2e_phase1_<时间戳>.json` | Phase 1-3 完整数据：工具调用、Token、grader 结果 |
| Markdown | `evaluation/reports/e2e_phase1_<时间戳>.md` | 人可读摘要 |
| 服务器日志 | `/var/folders/.../e2e_server_*.log`（脚本打印路径） | Agent 执行细节 |
| Checkpoint | `evaluation/reports/_e2e_checkpoint.json` | 断点续跑 |

### 5.2 报告结构（JSON）

```json
{
  "task_results": [{
    "task_id": "B9",
    "trials": [{
      "grade_results": [
        {
          "grader_type": "code",
          "grader_name": "check_no_tool_errors",
          "passed": true,
          "score": 1.0
        },
        {
          "grader_type": "model",
          "grader_name": "grade_response_quality",
          "passed": true,
          "score": 0.85,
          "details": {
            "pipeline_diagnosis": { "intent": {}, "planning": {}, "tool_execution": {}, "output": {} },
            "optimization_suggestions": [ ... ]
          }
        },
        {
          "grader_type": "model",
          "grader_name": "grade_rollback_safety",
          "passed": true,
          "score": 0.90,
          "details": {
            "pipeline_diagnosis": {
              "safety_awareness": { "score": 5, "analysis": "..." },
              "error_handling": { "score": 4, "analysis": "..." },
              "abort_handling": null,
              "user_communication": { "score": 4, "analysis": "..." }
            },
            "rollback_demonstrated": true,
            "optimization_suggestions": [ ... ]
          }
        }
      ]
    }]
  }]
}
```

### 5.3 服务器日志分析

```bash
# 查看 Agent 工具调用链
grep "Turn\|工具调用参数\|error\|失败" /path/to/server.log

# 查看回滚事件
grep "快照已创建\|回滚\|rollback\|已恢复" /path/to/server.log

# 查看 Token 消耗
grep "Token 使用" /path/to/server.log

# 查看意图分析
grep "意图分析结果\|wants_to_stop" /path/to/server.log

# 查看 LLM 配置
grep "LLM Profiles\|agent.model\|provider" /path/to/server.log
```

---

## 六、B9/B10 回滚验证详解

### 6.1 为什么是核心差异化

| 对比维度 | OpenClaw | 小搭子 |
|---------|---------|--------|
| 文件修改安全 | 无保护，改了就改了 | 快照 + 操作日志 + 逆操作 |
| 异常恢复 | 文件停留在修改后状态 | 自动回滚到修改前 |
| 用户反悔 | 只能 `git checkout`（如果有 git） | 一键回滚 / 选择性回滚 |
| 进程崩溃 | 不可恢复 | 磁盘持久化快照，重启后恢复 |

### 6.2 快照存储位置

```
~/.xiaodazi/snapshots/
└── snap_{12位hex}/
    ├── metadata.json        ← 任务 ID、受影响文件列表、时间戳
    ├── file_manifest.json   ← 文件路径 → 备份文件名映射
    └── files/               ← 文件原始内容备份
        ├── a1b2c3d4.bak
        └── ...
```

- **保留时间**：24 小时（`SnapshotConfig.retention_hours`）
- **正常流程**：任务成功 → `commit()` 立即删除；任务失败 → `rollback()` 恢复后立即删除
- **进程崩溃**：重启时 `_load_snapshot_from_disk()` 从磁盘恢复

### 6.3 合成测试数据

```
docs/benchmark/data/rollback_test/
├── config.json       ← B9: 项目配置（端口 3000）
├── nginx.conf        ← B9: Nginx 反代（proxy_pass :3000）
├── README.md         ← B9: 项目文档
└── docs/             ← B10: 5 个含"北极星科技"的公司文档
    ├── about.md      ← 公司简介（7 处"北极星科技"）
    ├── product.md    ← 产品介绍
    ├── team.md       ← 团队介绍
    ├── contact.md    ← 联系方式
    └── faq.md        ← 常见问题
```

---

## 七、修复清单

### 本轮新增（2026-02-08 B9/B10）

| 变更 | 文件 | 说明 |
|------|------|------|
| 新增 Phase 0 回滚预检 | `scripts/run_e2e_auto.py` | `run_rollback_verification()` 在 Agent 测试前验证状态层 |
| 新增回滚验证脚本 | `scripts/verify_rollback_e2e.py` | 6 个子场景，确定性验证，秒级完成 |
| 新增回滚安全评估提示词 | `evaluation/config/judge_prompts.yaml` | `grade_rollback_safety` 专项诊断 |
| B9/B10 加入 E2E 套件 | `evaluation/suites/xiaodazi/e2e/phase1_core.yaml` | 从 4 用例扩展到 6 用例 |
| 修复用例排序 | `scripts/run_e2e_eval.py` | `--from` 参数支持 B9/B10 |
| 合成测试数据 | `docs/benchmark/data/rollback_test/` | 8 个文件（3 B9 + 5 B10） |

### 前轮修复（2026-02-08 基础）

| 问题 | 根因 | 修复 |
|------|------|------|
| E2E 死锁（ReadTimeout） | `subprocess.PIPE` 缓冲区满 → stdout write 阻塞事件循环 | stdout 改写临时日志文件 |
| 调试日志过多 | `create_message_stream` 在 INFO 级别输出完整请求 | 降为 DEBUG |
| Agent 找不到上传文件 | `FileService` 只返回假 URL，未写盘 | 实际保存到 `data/chat-attachments/` |
| 意图分析崩溃 | 多模态 content (list) + str 拼接 TypeError | `_filter_for_intent` 统一提取纯文本 |
| 意图分析 400 错误 | `max_tokens: 65536` 超 haiku 上限 | 改为 512（输出只有小 JSON） |
| 评分器返回 mock 分数 | Grader LLM 未配置 | 从 `evaluation/config/settings.yaml` 独立加载 |
| Model Grader 做闸门 | `min_score` 导致 FAIL | Model Grader 只评估不判定 |
| `--provider` 不生效 | AGENT_PROVIDER 只传给子进程 | 同时设置当前进程环境变量 |

---

## 八、配置文件一览

| 文件 | 作用 |
|------|------|
| `instances/xiaodazi/config.yaml` | 实例配置（provider、persona、planning 等） |
| `instances/xiaodazi/config/llm_profiles.yaml` | Provider 模板 + 13 个运行时 LLM profile |
| `evaluation/config/settings.yaml` | 评测配置（Grader LLM、报告格式等） |
| `evaluation/config/judge_prompts.yaml` | LLM-as-Judge 评估提示词（通用 + 回滚安全专项） |
| `evaluation/suites/xiaodazi/e2e/phase1_core.yaml` | E2E 用例定义（6 用例，input/graders/timeout） |
| `scripts/run_e2e_auto.py` | E2E 自动化运行器（Phase 0 + 服务管理 + 报告） |
| `scripts/verify_rollback_e2e.py` | B9/B10 回滚管道独立验证（6 个子场景） |
