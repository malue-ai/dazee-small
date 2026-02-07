# 小搭子端到端自动化测评操作指南

> 面向测试人员的完整操作说明，用于执行 E2E 自动化测评并解读报告。

---

## 一、文档目的与适用范围

| 项目 | 说明 |
|------|------|
| **目标读者** | 测试人员、验收人员、参与回归的开发者 |
| **测评对象** | 小搭子实例（xiaodazi），通过**真实 HTTP API** 调用后端 |
| **测评范围** | Phase1 端到端 4 用例（A1/B1/D4/C1），覆盖文件分析、跨会话记忆、错误恢复、Token 效率 |
| **自动化工具** | `scripts/run_e2e_auto.py`（一键全自动） / `scripts/run_e2e_eval.py`（手动模式） + `evaluation/adapters/http_agent.py` + EvaluationHarness 评分 |

**与 Benchmark 的关系**：

- **Benchmark 文档**（`docs/benchmark/test_cases.md`、`xiaodazi_eval.md`）：定义用例含义、预期行为、对比维度。
- **本指南**：说明如何**执行**自动化 E2E、如何**查看报告**、如何**根据结果做评估**。

---

## 二、测评体系概览

### 2.1 双维度（参考 xiaodazi_eval.md）

| 维度 | 含义 | E2E Phase1 对应 |
|------|------|------------------|
| **可行性** | 任务能否完成、是否有工具错误 | A1、D4（check_no_tool_errors + 响应质量） |
| **效率性** | 完成质量、Token、路径 | C1（check_token_limit + 响应质量） |
| **特色能力** | 记忆、风格延续、跨会话 | B1（多会话 4 轮，风格与偏好记忆） |

### 2.2 Phase1 四用例速览

| 用例 ID | 名称 | 类型 | 核心验证 | 超时 |
|---------|------|------|----------|------|
| **A1** | 格式混乱 Excel 分析 | 单轮 + 附件 | 无工具报错、有分析结论、RVR-B 回溯 | 120s |
| **B1** | 跨会话记忆（毒舌风格） | 4 轮 / 3 会话 | 新会话中延续风格、能回忆偏好 | 180s |
| **D4** | 连续错误恢复（CSV→Excel→图→PDF） | 单轮 + 附件 | 含错误数据下仍完成或优雅失败、回溯 | 120s |
| **C1** | 简单问答 Token 对比 | 2 轮同会话 | 单轮 Token≤8K、第二轮缓存命中 | 90s |

---

## 三、环境与前置条件

### 3.1 必需环境

- **Python**：3.11+，建议使用项目约定虚拟环境（见 README）。
- **后端**：必须已启动且可访问，默认 `http://localhost:8000`。
- **配置**：项目根目录 `.env` 中至少配置 `ANTHROPIC_API_KEY`；实例 `instances/xiaodazi/.env` 若存在会覆盖/补充。

### 3.2 测试数据

E2E 使用的数据文件（需存在）：

| 用例 | 数据路径 | 说明 |
|------|----------|------|
| A1 | `docs/benchmark/data/messy_sales.xlsx` | 格式混乱销售表（多种日期/数字格式、空行等） |
| D4 | `docs/benchmark/data/error_prone.csv` | 含 N/A、待确认、空值等易触发错误的 CSV |
| B1/C1 | 无附件 | 纯文本对话 |

若缺少数据，可先生成或检查：

```bash
cd docs/benchmark/data
python generate_test_data.py   # 生成 messy_sales.xlsx、mixed_files 等
# error_prone.csv 为项目自带，无需生成
```

### 3.3 后端启动

有两种方式运行 E2E 测评：

| 方式 | 命令 | 说明 |
|------|------|------|
| **一键全自动**（推荐） | `python scripts/run_e2e_auto.py` | 自动启动服务 → 跑测试 → 自动关闭 |
| **手动模式** | 先启动服务，再 `python scripts/run_e2e_eval.py` | 适合调试，服务常驻 |

---

## 四、一键全自动测评（推荐）

### 4.1 跑全部用例

```bash
python scripts/run_e2e_auto.py
```

脚本自动完成：
1. 在 port 18234 启动 uvicorn（避免与开发服务器 8000 冲突）
2. 等待服务就绪（TCP 端口检测 + HTTP GET / 确认）
3. 依次执行 A1 → B1 → D4 → C1
4. 生成报告（JSON + Markdown + 失败分类）
5. 自动关闭服务进程

### 4.2 只跑单个用例

```bash
python scripts/run_e2e_auto.py --case A1
```

### 4.3 断点续跑

```bash
python scripts/run_e2e_auto.py --from D4
```

### 4.4 清理断点重跑

```bash
python scripts/run_e2e_auto.py --clean
```

### 4.5 自定义端口

```bash
python scripts/run_e2e_auto.py --port 9000
```

### 4.6 复用已运行的服务（调试场景）

若已手动启动了服务，可跳过自动启动：

```bash
# 先手动启动服务
uvicorn main:app --host 0.0.0.0 --port 18234

# 另一个终端，跳过自动启动
python scripts/run_e2e_auto.py --no-start
```

---

## 五、手动模式（高级）

适合需要反复调试、服务常驻的场景。

### 5.1 启动后端

```bash
AGENT_INSTANCE=xiaodazi uvicorn main:app --host 0.0.0.0 --port 8000
```

### 5.2 检查后端可达

```bash
python scripts/run_e2e_eval.py --check-server
```

### 5.3 执行测评

```bash
python scripts/run_e2e_eval.py
python scripts/run_e2e_eval.py --case A1
python scripts/run_e2e_eval.py --from D4
python scripts/run_e2e_eval.py --base-url http://localhost:9000
```

---

## 六、报告产出与存放位置

### 6.1 产出文件一览

| 产出 | 路径 | 说明 |
|------|------|------|
| 断点 | `evaluation/reports/_e2e_checkpoint.json` | 已完成用例 ID、简要结果；用于断点续跑 |
| 报告 JSON | `evaluation/reports/e2e_phase1_<时间戳>.json` | 机器可读：用例、通过率、各 grader 结果、trial 等 |
| 报告 Markdown | `evaluation/reports/e2e_phase1_<时间戳>.md` | 人可读：通过率、各用例 PASS/FAIL、描述 |
| 失败分类（若有失败） | `evaluation/reports/e2e_triage_<时间戳>.md` | 失败用例按类别汇总，便于排期修复 |
| 回归套件（若有失败） | `evaluation/suites/xiaodazi/e2e_regression_<时间戳>.yaml` | 将失败用例导出为回归 YAML，便于后续单独回归 |

### 6.2 如何查看本次运行结果

1. **控制台**：脚本结束时会打印报告与 triage 的保存路径。
2. **Markdown 报告**：打开 `evaluation/reports/e2e_phase1_<时间戳>.md`，查看：
   - 总体通过率、通过/失败用例数；
   - 每个用例的 PASS/FAIL 及简短描述。
3. **JSON 报告**：需要细粒度结果（如每个 grader 的 passed/score）时，查看同时间戳的 `.json`。

### 6.3 如何根据报告做评估

- **PASS**：该用例下配置的 grader 均通过（如无工具错误、响应质量达标、Token 未超限等）。
- **FAIL**：至少一个 grader 未通过；可结合 `e2e_triage_<时间戳>.md` 看失败分类，结合 JSON 看具体是哪个 grader、哪条 trial 失败。
- **测试结论**：可汇总为「Phase1 E2E：x/4 通过，未通过用例：…，建议修复后再回归」。

---

## 七、故障排查

### 7.1 Server failed to start（仅全自动模式）

- **原因**：uvicorn 子进程在 120s 内未就绪。
- **操作**：
  1. 脚本会自动打印服务端输出（最后 2000 字符），根据报错定位原因。
  2. 常见原因：`AGENT_INSTANCE` 未设置、实例 `.env` 配置缺失、端口被占用。
  3. 可切换为 `--no-start` 手动调试。

### 7.2 Server not reachable（仅手动模式）

- **原因**：`run_e2e_eval.py` 连不上 `--base-url`（默认 8000）。
- **操作**：
  1. 确认后端已在该端口启动。
  2. 若后端在其他端口，使用 `--base-url` 指定。
  3. 本机可先执行 `curl http://localhost:8000/` 自检。

### 7.3 POST /api/v1/chat 返回 4xx/5xx

- **现象**：脚本报错并打印响应体（若已使用带响应体输出的 adapter 版本）。
- **操作**：
  1. 查看**运行 uvicorn 的终端**中是否有 Python 异常栈，定位后端错误（如配置缺失、依赖服务不可用）。
  2. 确认 `.env` 与实例 `.env` 中 API Key 等配置正确。
  3. 确认请求体符合 Chat API 要求（脚本已按文档发送 message、user_id、stream=false 等）。

### 7.4 某用例超时

- **现象**：轮询 session 或单次请求超时。
- **操作**：该用例可能确实执行较慢（如 B1 多轮、D4 复杂流程）；可先单独 `--case <ID>` 重跑一次；若仍超时，可考虑调大 adapter 内 `poll_max_wait_seconds` 或请求 timeout（需改代码）。

### 7.5 文件上传失败或用例未带附件

- A1、D4 依赖附件；脚本会尝试通过 `POST /api/v1/files/upload` 上传后再发 chat。若上传失败（如未配置存储），可能退化为无附件请求，导致用例行为与预期不符。
- **操作**：确认后端文件上传与存储配置正确；或查看脚本日志是否提示上传失败。

---

## 八、附录

### 8.1 Phase1 用例与 Benchmark 对应关系

| E2E 用例 | Benchmark 文档中的对应 | 主要 Graders |
|----------|------------------------|--------------|
| A1 | test_cases.md 中 A1（格式混乱 Excel） | check_no_tool_errors, grade_response_quality≥4 |
| B1 | test_cases.md 中 B1（跨会话记忆/风格） | grade_response_quality≥3（风格与偏好回忆） |
| D4 | test_cases.md 中 D4（连续错误恢复） | check_no_tool_errors, grade_response_quality≥3 |
| C1 | test_cases.md 中 C1（简单问答 Token） | check_token_limit(8000), grade_response_quality≥3 |

### 8.2 相关文档与代码

| 资源 | 路径 | 用途 |
|------|------|------|
| Benchmark 总览 | `docs/benchmark/README.md` | 测试数据、对比维度、目录结构 |
| 完整测试用例 | `docs/benchmark/test_cases.md` | 各用例输入、预期、对比指标 |
| 小搭子测评方案 | `docs/benchmark/xiaodazi_eval.md` | 可行性/效率性维度、F/E 套件说明 |
| E2E 套件定义 | `evaluation/suites/xiaodazi/e2e/phase1_core.yaml` | 4 用例的 input、graders、metadata |
| 一键自动测评 | `scripts/run_e2e_auto.py` | 自动启停服务 + 跑测试 + 生成报告 |
| 手动 E2E 脚本 | `scripts/run_e2e_eval.py` | 手动模式入口、参数、断点与报告逻辑 |
| HTTP 适配器 | `evaluation/adapters/http_agent.py` | 调用 /chat、轮询 session、拉取 messages |

### 8.3 快速命令速查

```bash
# ===== 一键全自动（推荐） =====

# 跑全部 E2E（自动启停服务）
python scripts/run_e2e_auto.py

# 只跑 A1
python scripts/run_e2e_auto.py --case A1

# 清理断点重跑
python scripts/run_e2e_auto.py --clean

# 从 D4 断点续跑
python scripts/run_e2e_auto.py --from D4

# 自定义端口
python scripts/run_e2e_auto.py --port 9000

# 跳过自动启动（已有服务运行时）
python scripts/run_e2e_auto.py --no-start

# ===== 手动模式（高级） =====

# 检查后端
python scripts/run_e2e_eval.py --check-server

# 跑全部 E2E
python scripts/run_e2e_eval.py

# 指定后端地址
python scripts/run_e2e_eval.py --base-url http://localhost:9000
```

---

**文档版本**：与 `evaluation/suites/xiaodazi/e2e/phase1_core.yaml` 及 `scripts/run_e2e_eval.py` 当前行为一致。若套件或脚本有变更，请同步更新本指南。
