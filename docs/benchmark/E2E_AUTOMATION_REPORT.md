# 小搭子端到端自动化测评操作指南

> 面向测试人员的完整操作说明，用于执行 E2E 自动化测评并解读报告。

---

## 一、文档目的与适用范围

| 项目 | 说明 |
|------|------|
| **目标读者** | 测试人员、验收人员、参与回归的开发者 |
| **测评对象** | 小搭子实例（xiaodazi），通过**真实 HTTP API** 调用后端 |
| **测评范围** | Phase1 端到端 4 用例（A1/B1/D4/C1），覆盖文件分析、跨会话记忆、错误恢复、Token 效率 |
| **模型兼容性** | 支持 `--provider qwen` / `--provider claude` 切换，验证多模型下的表现 |
| **评估模型** | LLM-as-Judge 使用 Claude Opus 4.6 + Extended Thinking（独立于被测 Agent） |

---

## 二、最新测评结果（2026-02-08）

### Claude Provider（claude-sonnet-4-5 主 Agent）

```
🧪 Grader LLM: claude-opus-4-6 (thinking=True)
▶ A1: 格式混乱 Excel 分析        ✅ PASS
▶ B1: 跨会话记忆                  ✅ PASS
▶ D4: 连续错误恢复                ✅ PASS
▶ C1: 简单问答 Token 对比         ✅ PASS
📊 Pass rate: 100% (4/4)
```

| 用例 | Agent 模型 | 轮次 | 耗时 | Code Grader | Model Grader |
|------|-----------|------|------|-------------|-------------|
| A1 | claude-sonnet-4-5 | 4 轮 | ~63s | ✅ 0 错误 | 待 Opus 评分 |
| B1 | claude-sonnet-4-5 | 5 轮(跨 3 会话) | ~70s | — | 待 Opus 评分 |
| D4 | claude-sonnet-4-5 | 多轮 | 数分钟 | ✅ 0 错误 | 待 Opus 评分 |
| C1 | claude-sonnet-4-5 | 2 轮 | ~30s | ✅ Token 达标 | 待 Opus 评分 |

### Qwen Provider（qwen3-max 主 Agent）

| 用例 | Agent 模型 | 结果 | 说明 |
|------|-----------|------|------|
| A1 | qwen3-max | FAIL | Agent 完成但评分未通过（旧 grader 问题） |
| B1 | qwen3-max | PASS | 记忆功能与模型无关 |
| D4 | qwen3-max | 进行中(23 轮) | 正常执行复杂多步骤任务，非卡死 |
| C1 | qwen3-max | PASS | Token 达标 |

### 模型对比发现

| 指标 | claude-sonnet-4-5 | qwen3-max |
|------|-------------------|-----------|
| A1 完成轮次 | 4 轮 | 10+ 轮 |
| A1 耗时 | ~63 秒 | 180+ 秒 |
| D4 完成轮次 | 数轮 | 23+ 轮（仍在正常推进） |
| 数据清洗能力 | 一次成功 | 反复试错后成功 |
| Plan 创建 | 正常（修复后） | 正常（修复后） |

---

## 三、测评体系

### 3.1 评估架构

```
E2E 测试
│
├── 1. Agent 执行任务（RVR-B 策略，内部回溯/Plan/Memory）
│   └── 输出：最终回复 + 工具调用记录
│
├── 2. Code Grader — 流程通没通（自动 PASS/FAIL）
│   ├── check_no_tool_errors → 工具调用零错误
│   └── check_token_limit → Token 消耗在预算内
│
└── 3. LLM Judge — 流程好不好（管道诊断报告，不做闸门）
    ├── 意图理解分析
    ├── 规划质量分析
    ├── 工具使用效率分析
    ├── 上下文管理分析
    ├── 输出质量分析
    └── optimization_suggestions → 优化建议
        ├── target: "prompt"   → 改提示词
        ├── target: "skill"    → 改工具/技能
        ├── target: "model"    → 换模型
        ├── target: "memory"   → 改记忆策略
        └── target: "framework" → 改框架逻辑
```

### 3.2 PASS/FAIL 判定规则

| 评分器类型 | 角色 | 决定 PASS/FAIL？ | 说明 |
|---|---|---|---|
| Code Grader | 确定性检查 | **是** | 硬性标准（工具错误、Token 限制等） |
| Model Grader | 质量评估 | **否** | 独立于 Agent 执行逻辑，评分供人类审查 |

Model Grader（LLM-as-Judge）核心原则：
- **独立于 Agent**：不干预 Agent 的 plan-todo、回溯等内部逻辑
- **评估不是闸门**：评分只供参考，不触发重试或循环
- **使用最强模型**：Claude Opus 4.6 + Thinking，比被评对象更强
- **配置位置**：`evaluation/config/settings.yaml` + `evaluation/config/judge_prompts.yaml`

### 3.3 Phase1 四用例

| 用例 | 名称 | 类型 | 核心验证 | 超时 |
|------|------|------|----------|------|
| **A1** | 格式混乱 Excel 分析 | 单轮 + 附件 | 数据清洗 + 分析报告 | 600s |
| **B1** | 跨会话记忆（毒舌风格） | 4 轮 / 3 会话 | 风格延续 + 偏好记忆 | 600s |
| **D4** | 连续错误恢复（CSV→Excel→图→PDF） | 单轮 + 附件 | 多步骤任务 + 错误恢复 | 600s |
| **C1** | 简单问答 Token 对比 | 2 轮同会话 | Token ≤ 8K + 缓存命中 | 90s |

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

# 后台运行（长任务推荐）
PYTHONUNBUFFERED=1 nohup python scripts/run_e2e_auto.py --clean --provider claude > /tmp/e2e.log 2>&1 &
# 查看进度
grep -E "PASS|FAIL|▶|Grader" /tmp/e2e.log
```

### 4.2 参数说明

| 参数 | 说明 |
|------|------|
| `--clean` | 清除 checkpoint，从头跑全部用例 |
| `--provider qwen/claude` | 覆盖 config.yaml 的 provider，切换全部模型 |
| `--case A1` | 只跑指定用例 |
| `--from D4` | 从指定用例恢复 |
| `--no-start` | 跳过自动启动，复用已运行的服务 |
| `--port 9000` | 自定义服务端口 |

### 4.3 Provider 一键切换原理

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
│ 主 Agent │ qwen3-max           │ claude-sonnet-4-5    │
│ heavy    │ qwen3-max           │ claude-sonnet-4-5    │
│ light    │ qwen-plus           │ claude-haiku-4-5     │
└──────────┴─────────────────────┴──────────────────────┘
```

---

## 五、报告解读

### 5.1 产出文件

| 产出 | 路径 | 说明 |
|------|------|------|
| JSON 报告 | `evaluation/reports/e2e_phase1_<时间戳>.json` | 完整数据：工具调用、Token、grader 结果 |
| Markdown | `evaluation/reports/e2e_phase1_<时间戳>.md` | 人可读摘要 |
| 服务器日志 | `/var/folders/.../e2e_server_*.log`（脚本打印路径） | Agent 执行细节 |
| Checkpoint | `evaluation/reports/_e2e_checkpoint.json` | 断点续跑 |

### 5.2 报告结构（JSON）

```json
{
  "task_results": [{
    "task_id": "A1",
    "trials": [{
      "grade_results": [
        {
          "grader_type": "code",
          "grader_name": "check_no_tool_errors",
          "passed": true,          // ← 决定 PASS/FAIL
          "score": 1.0
        },
        {
          "grader_type": "model",
          "grader_name": "grade_response_quality",
          "passed": true,          // ← 始终 true（不做闸门）
          "score": 0.9,
          "details": {
            "pipeline_diagnosis": { ... },   // 管道诊断
            "optimization_suggestions": [ ... ]  // 优化建议
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

# 查看 Token 消耗
grep "Token 使用" /path/to/server.log

# 查看意图分析
grep "意图分析结果" /path/to/server.log

# 查看 LLM 配置
grep "LLM Profiles\|agent.model\|provider" /path/to/server.log
```

---

## 六、本轮修复清单（2026-02-08）

| 问题 | 根因 | 修复 |
|------|------|------|
| E2E 死锁（ReadTimeout） | `subprocess.PIPE` 缓冲区满 → stdout write 阻塞事件循环 | stdout 改写临时日志文件 |
| 调试日志过多 | `create_message_stream` 在 INFO 级别输出完整请求 | 降为 DEBUG |
| Agent 找不到上传文件 | `FileService` 只返回假 URL，未写盘 | 实际保存到 `data/chat-attachments/` |
| 意图分析崩溃 | 多模态 content (list) + str 拼接 TypeError | `_filter_for_intent` 统一提取纯文本 |
| 意图分析 400 错误 | `max_tokens: 65536` 超 haiku 上限 | 改为 512（输出只有小 JSON） |
| 评分器返回 mock 分数 | Grader LLM 未配置 | 从 `evaluation/config/settings.yaml` 独立加载 |
| Model Grader 做闸门 | `min_score` 导致 FAIL | Model Grader 只评估不判定，PASS/FAIL 由 Code Grader 决定 |
| `--provider` 不生效 | AGENT_PROVIDER 只传给子进程 | 同时设置当前进程环境变量 |

---

## 七、配置文件一览

| 文件 | 作用 |
|------|------|
| `instances/xiaodazi/config.yaml` | 实例配置（provider、persona、planning 等） |
| `instances/xiaodazi/config/llm_profiles.yaml` | Provider 模板 + 13 个运行时 LLM profile |
| `evaluation/config/settings.yaml` | 评测配置（Grader LLM、报告格式等） |
| `evaluation/config/judge_prompts.yaml` | LLM-as-Judge 评估提示词（管道诊断） |
| `evaluation/suites/xiaodazi/e2e/phase1_core.yaml` | E2E 用例定义（input、graders、timeout） |
