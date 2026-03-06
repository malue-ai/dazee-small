# GitHub main 分支已推送内容排查报告

基于对 `github/main` 的 `git ls-tree` 与代码扫描，整理出**已推送到 GitHub main、按规范应排除或存在敏感/内部信息的代码**。

---

## 一、按规范应排除（22-git-workflow）

推送到 **github** 时必须排除的目录/文件，当前 **仍存在于 github main**：

| 类别 | 路径/规则 | 当前状态 |
|------|-----------|----------|
| 内部实例 | `instances/SAP_xiaodazi/` 整个目录 | ❌ 仍在 main（约 50+ 文件） |
| 实例配置 | `instances/*/config.yaml` | ❌ xiaodazi、_template、SAP_xiaodazi 均在 |
| 实例子配置 | `instances/*/config/`（skills/llm_profiles/memory） | ❌ 三个实例的 config/ 均在 |
| 提示词缓存 | `instances/*/prompt_results/` | ❌ xiaodazi、_template 的 prompt_results 均在 |
| 测试临时脚本 | `scripts/verify_*.py` | ✅ 当前 main 上未见 verify_*.py（可能未推过） |

---

## 二、测试与评测（已上 main）

- **evaluation/ 目录：保留**。评测框架与 suites 可留在 GitHub，但**必须脱敏**：
  - 所有真实服务 URL（如 `https://your-cloud-agent.example.com`）→ 改为占位符（如 `https://your-cloud-agent.example.com`）。
  - 所有涉及 API Key / 凭证的配置或示例 → 改为占位符（如 `your-dashscope-api-key`），不得出现真实 Key。
- **tests/ 目录：从 GitHub main 删除**。含 test_cloud_agent_e2e.py、zenflux_tests_backup 等，不宜出现在公开 main。
- **脚本与示例**：scripts/test_cloud_e2e.py、scripts/test_feishu_urgent_phone.py、examples/test_zeno_e2e.py 若保留在 GitHub，需脱敏（URL + Key 占位符）。test_feishu_urgent_phone.py 含硬编码飞书凭证，**见下节，必须处理**。
- pytest.ini 可保留。

---

## 三、云端/协同相关（已上 main）

| 路径 | 说明 |
|------|------|
| core/cloud/ | 云端任务、模型等 |
| services/cloud_client.py | 默认 `cloud_url: "https://your-cloud-agent.example.com"` |
| tools/cloud_agent.py | 云端 Agent 工具 |
| frontend/.../CloudProgressCard.vue | 前端云端进度 |
| skills/library/cloud-agent/SKILL.md | 云端 Agent 技能说明 |
| docs/architecture/13-cloud-collaboration.md | 架构文档，含 your-cloud-agent.example.com 示例 |
| docs/cloud-collaboration-architecture.md | 云端协同架构 |
| evaluation/suites/xiaodazi/e2e/cloud_collaboration.yaml | 见上 |

**涉及真实服务地址的文件（your-cloud-agent.example.com）：**

- instances/xiaodazi/config.yaml
- instances/xiaodazi/README.md
- instances/_template/config.yaml、env.example
- instances/SAP_xiaodazi/env.example
- services/cloud_client.py
- routers/agents.py、routers/settings.py
- models/agent.py
- frontend/.../SettingsView.vue
- tests/test_cloud_agent_e2e.py
- scripts/test_cloud_e2e.py
- evaluation/suites/xiaodazi/e2e/cloud_collaboration.yaml
- docs/architecture/13-cloud-collaboration.md
- docs/benchmark/test_cases.md、README.md
- README.md（官网 dazee.ai 链接可保留）

说明：框架内默认 URL 示例（如 `https://your-cloud-agent.example.com`）是否算「内部」由你方定义；若希望 GitHub 完全中性，可改为占位符如 `https://your-cloud-agent.example.com`。

---

## 四、敏感信息（必须立即处理）

### 1. 飞书凭证硬编码（严重）

**文件：** `scripts/test_feishu_urgent_phone.py`（已上 main）

```python
APP_ID = "<REDACTED-FEISHU-APP-ID>"
APP_SECRET = "<REDACTED-FEISHU-APP-SECRET>"
TARGET_USER_OPEN_ID = "<REDACTED-FEISHU-OPEN-ID>"
```

- **风险：** 飞书应用凭证 + 真实 open_id 泄露，可被滥用。
- **建议：**  
  - 立即在飞书开放平台撤销/轮换该应用凭证。  
  - 从仓库中删除或改为从环境变量/`.env` 读取，并确保该文件不再包含真实值后，再推送到 GitHub（若历史已推，需考虑从历史中清理或强制轮换凭证）。

### 2. ComputeNest 参数中的 Key（严重）

**文件：** `.computenest/.computenest_parameters.yaml`（已上 main）

```yaml
  Name: your-dashscope-api-key   # 疑似 DASHSCOPE_API_KEY
```

- **风险：** 阿里云 DashScope API Key 泄露。
- **建议：**  
  - 立即在阿里云控制台禁用/删除该 Key。  
  - 仓库中改为占位符或从环境/密钥服务读取，且不要将真实 Key 提交到任何公开仓库。

---

## 五、其他可能内部/敏感

| 路径 | 说明 |
|------|------|
| .computenest/ | 阿里云/华为云 ComputeNest 部署模板，含 RepoName、Branch、CustomParameters（已含 Key，见上） |
| scripts/init_instance_xiaodazi.py | 实例名写死为 xiaodazi |
| scripts/sync_capabilities.py、sync_version.py | 同步脚本，可能对应内部流程 |
| xiaodazi-backend.spec | 打包配置，产品名/用途可见 |
| config/ | 全局配置（gateway.example、llm_config 等），一般可保留；若有内部 URL/Key 需单独检查 |

---

## 六、建议行动顺序

1. **立即：**  
   - 轮换/撤销 `test_feishu_urgent_phone.py` 中的飞书 APP_ID/APP_SECRET，并处理 TARGET_USER_OPEN_ID。  
   - 禁用/删除 `.computenest_parameters.yaml` 中泄露的 DashScope Key。

2. **短期：**  
   - 从 **GitHub main** 上按规范排除：`instances/SAP_xiaodazi/`、`instances/*/config.yaml`、`instances/*/config/`、`instances/*/prompt_results/`（或整目录按规范做一次「推送到 github 的排除清单」落地）。  
   - 对 `scripts/test_feishu_urgent_phone.py`、`.computenest/.computenest_parameters.yaml` 做去敏感化（环境变量/占位符），并确保新提交不再含真实凭证；若需从历史中彻底移除，可考虑 `git filter-repo` 或 BFG，并强制轮换相关凭证。

3. **中期：**  
   - 明确「测试 + 云端协同」在 GitHub 上的策略：  
     - 要么从 main 移除/忽略：如 `evaluation/suites/xiaodazi/`、`tests/test_cloud_agent_e2e.py`、`scripts/test_cloud_e2e.py` 等；  
     - 要么保留但去敏感化：将 `https://your-cloud-agent.example.com` 改为占位符或配置项，避免暴露真实生产/测试端点。  
   - 在 22-git-workflow 中补充「推 github 时排除清单」的执行方式（例如单独分支 + 排除列表、或 CI 检查 main 是否包含禁止路径）。

---

## 七、汇总：建议从 GitHub main 排除或脱敏的清单

- **必须排除（规范 + 安全）：**  
  `instances/SAP_xiaodazi/`、`instances/*/config.yaml`、`instances/*/config/`、`instances/*/prompt_results/`  
  `scripts/test_feishu_urgent_phone.py`（或脱敏后保留）、`.computenest/.computenest_parameters.yaml`（或脱敏后保留）

- **evaluation/：保留，须脱敏**  
  所有真实 URL、Key 改为占位符；suites 可保留。

- **tests/：从 GitHub main 删除**  
  不保留在公开 main。

- **其他脱敏（若保留在 GitHub）：**  
  `scripts/test_cloud_e2e.py`、`scripts/test_feishu_urgent_phone.py` 等：URL + Key 占位符。

以上为基于当前 `github/main` 的排查结果；执行排除或历史清理时，请务必在单独分支或副本上操作并做好备份。
