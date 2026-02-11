# 实例配置指南

ZenFlux Agent 通过**实例（Instance）**来隔离不同 AI 智能体的配置、人格、技能和运行时数据。每个实例是一个独立的目录，包含该智能体的全部定义。

## 目录结构

```
instances/
├── _template/                  # 实例模板（创建新实例的起点）
├── xiaodazi/                   # 小搭子（桌面版主力实例）
├── ea1f6ec6/                   # 产品视觉生成助手（示例实例）
└── README.md                   # ← 你在看的这个文件
```

每个实例的标准目录结构：

```
my-agent/
├── config.yaml                 # 实例配置（必须）
├── prompt.md                   # 人格提示词（必须）
├── config/
│   ├── llm_profiles.yaml       # LLM 路由配置
│   ├── skills.yaml             # Skills 清单与分组
│   └── memory.yaml             # 记忆与语义搜索配置
├── skills/                     # 实例专属 Skill 目录
│   ├── skill-name/
│   │   └── SKILL.md            # Skill 定义文件
│   └── skill_registry.yaml     # 运行时状态注册（自动生成）
├── prompt_results/             # 自动生成的场景化提示词
│   ├── agent_schema.yaml       # Agent 参数配置
│   ├── intent_prompt.md        # 意图识别提示词
│   ├── simple_prompt.md        # 简单任务提示词
│   ├── medium_prompt.md        # 中等任务提示词
│   ├── complex_prompt.md       # 复杂任务提示词
│   └── _metadata.json          # 元数据（系统维护）
└── .cache/                     # 运行时缓存（自动生成，不提交 Git）
```

## 快速开始：创建新实例

```bash
# 1. 复制模板
cp -r instances/_template instances/my-agent

# 2. 编辑实例配置
vi instances/my-agent/config.yaml

# 3. 编辑人格提示词
vi instances/my-agent/prompt.md

# 4. 启动
AGENT_INSTANCE=my-agent uvicorn main:app --host 0.0.0.0 --port 8000
```

> 只有一个实例时，框架会自动检测，无需设置 `AGENT_INSTANCE` 环境变量。

## 配置文件详解

### 1. config.yaml — 实例配置（必须）

实例的核心配置文件，定义基础信息和运行参数。

```yaml
# ==================== 基础信息（必填） ====================
instance:
  name: "my-agent"                  # 实例名（与目录名一致）
  description: "我的 AI 搭子"
  version: "1.0.0"

# ==================== 大模型配置 ====================
# 不预设 provider/model，从用户配置的 API Key 自动激活
# 也可手动指定：
agent:
  provider: "qwen"                  # 一键切换：qwen / claude / deepseek
  # model: "qwen3-max"             # 不填则由 provider 自动决定
```

**可选配置段**（按需添加）：

| 配置段 | 用途 | 默认行为 |
|---|---|---|
| `persona` | 个性化（称呼、语气、详细度） | 无个性化 |
| `user_prompt` | 用户自定义提示词补充 | 空 |
| `storage` | 自定义数据存储位置 | `data/instances/{name}/` |
| `state_consistency` | 文件快照与回滚策略 | 启用，默认参数 |
| `knowledge` | 本地知识库目录与语义搜索 | 仅关键词搜索 |
| `memory` | 跨对话记忆 | 启用 |
| `planning` | 规划系统模式 | `implicit`（隐式规划） |
| `playbook` | 持续学习策略提取 | 启用 |

**运行时数据存储**（自动按实例名隔离）：

```
data/instances/{name}/
├── db/           # 数据库（会话、消息）
├── memory/       # 记忆文件（MEMORY.md）
├── store/        # 向量索引
├── storage/      # 上传文件
├── playbooks/    # 策略
└── snapshots/    # 状态快照
```

> 完整配置参考：`instances/_template/config.yaml`（含每个配置段的详细注释）

### 2. prompt.md — 人格提示词（必须）

定义智能体的角色、能力和行为规则。这是最重要的配置之一——直接决定 Agent 的"性格"。

```markdown
# 我的 AI 搭子

你是一个养在电脑里的 AI 助手。

## 核心原则
- 有问必答，直接给结果
- 需要确认的操作先问用户
- 记住用户的偏好和习惯
```

框架会根据 `prompt.md` + `config.yaml` 自动生成场景化提示词到 `prompt_results/` 目录。详见 `prompt_results/README.md`。

**编写建议**：

- 用自然语言描述角色定位和行为准则
- 明确列出"可以做什么"和"不能做什么"
- 参考 `instances/xiaodazi/prompt.md`（完整示例）

### 3. config/llm_profiles.yaml — LLM 路由配置

控制框架内部各模块使用的大模型。通过 `config.yaml` 的 `agent.provider` 一键切换所有模型，**普通用户通常不需要修改此文件**。

**Provider 对应的模型分配**：

| 角色 | qwen | claude | deepseek |
|---|---|---|---|
| 主 Agent | qwen3-max | claude-sonnet-4-5 | deepseek-reasoner |
| 重型任务（heavy） | qwen3-max | claude-sonnet-4-5 | deepseek-reasoner |
| 轻型任务（light） | qwen-plus | claude-haiku-4-5 | deepseek-chat |

**高级用法**：可覆盖单个调用点的模型配置（如让意图分析用更快的模型、规划生成用更强的模型）。

> 完整配置参考：`instances/_template/config/llm_profiles.yaml`

### 4. config/skills.yaml — Skills 清单与分组

定义实例可用的 Skills 和意图分组。

```yaml
# 按意图分组（IntentAnalyzer 用于技能筛选）
skill_groups:
  _always:
    description: "始终注入（基础能力）"
    skills: [local-search, app-recommender]
  writing:
    description: "写作、润色、改写"
    skills: [writing-assistant, translator]

# 按 OS × 依赖复杂度 二维分类
skills:
  loading_mode: "lazy"          # lazy（延迟加载）/ eager（启动加载）
  os_aware: true                # 自动过滤当前 OS 不支持的 Skills

  common:                       # 跨平台 Skills
    builtin:                    # 内置（无外部依赖）
      - { name: plan-todo, backend_type: tool, tool_name: plan_todo, system: true, description: "任务规划" }
    lightweight: []             # 轻量依赖
    external: []                # 外部工具
    cloud_api: []               # 云服务 API

  darwin: ...                   # macOS 专属 Skills
  win32: ...                    # Windows 专属 Skills
  linux: ...                    # Linux 专属 Skills
```

**Skill 来源**：

| `skill_source` | 说明 |
|---|---|
| `instance` | 从实例 `skills/` 目录加载 SKILL.md |
| `library` | 从全局 `skills/` 目录加载 |

> 完整 Skills 清单参考：`instances/xiaodazi/config/skills.yaml`

### 5. config/memory.yaml — 记忆与语义搜索

控制 Agent 的记忆能力和知识检索方式。

```yaml
# 语义搜索（三种模式）
semantic_search:
  mode: disabled                # disabled | local | cloud

  # local 模式：本地 BGE-M3 模型（438MB，中英文双语，离线可用）
  local:
    repo: ""                    # 留空使用默认模型
    model: ""

  # cloud 模式：OpenAI embedding（需 API Key）
  cloud:
    model: ""                   # 留空 = text-embedding-3-small

# 用户记忆（跨对话持久保存用户偏好）
memory:
  enabled: true
```

### 6. skills/ — Skill 定义目录

每个 Skill 是一个子目录，包含 `SKILL.md` 文件（YAML frontmatter + Markdown 描述）。

```yaml
---
name: writing-assistant
description: 写作辅助、润色、改写
metadata:
  xiaodazi:
    dependency_level: builtin   # builtin / lightweight / external / cloud_api
    os: [common]                # common / darwin / win32 / linux
    backend_type: local         # tool / local / mcp / api
    user_facing: true
---

# 写作助手

帮助用户撰写、润色和改写各类文本...
```

> Skill 模板参考：`instances/_template/skills/_template/SKILL.md`

### 7. prompt_results/ — 自动生成的提示词

框架根据 `prompt.md` 和 `config.yaml` 自动生成场景化系统提示词。支持手动编辑——编辑过的文件不会被下次生成覆盖。

| 文件 | 用途 | 生成触发 |
|---|---|---|
| `agent_schema.yaml` | Agent 组件和参数配置 | 首次启动 / prompt.md 变更 |
| `intent_prompt.md` | 意图识别 | 同上 |
| `simple_prompt.md` | 简单任务处理 | 同上 |
| `medium_prompt.md` | 中等任务处理 | 同上 |
| `complex_prompt.md` | 复杂任务处理 | 同上 |

强制重新生成：

```bash
# 删除元数据，下次启动全部重新生成
rm instances/my-agent/prompt_results/_metadata.json
```

> 详细说明参考：`instances/_template/prompt_results/README.md`

## 已有实例参考

### xiaodazi（小搭子）

桌面端主力实例，功能最完整：

- 70+ Skills，覆盖写作、搜索、文件管理、应用推荐、数据分析等
- 完整的意图分组配置
- 支持 macOS / Windows / Linux 三平台
- 包含桌面端专用提示词（`prompt_desktop.md`）

适合作为参考模板，按需裁剪 Skills 和配置。

### ea1f6ec6（产品视觉生成助手）

聚焦型实例示例：

- 仅 1 个 Skill（nano-pdf）
- 精简配置
- 无记忆配置

展示了如何创建一个专注于特定场景的轻量实例。

## Git 版本控制

`instances/.gitignore` 排除了以下文件：

| 排除项 | 原因 |
|---|---|
| `**/.cache/` | 运行时缓存，自动生成 |
| `**/.env` | 包含 API Key 等敏感信息 |
| `**/config.yaml` | 可能包含个人配置 |
| `**/*.tmp` / `**/*.log` | 临时文件 |

> **注意**：`config.yaml` 被 gitignore，确保 `_template/config.yaml` 作为配置模板始终提交到版本库。

## 常见问题

**Q: 如何切换大模型？**

修改 `config.yaml` 中的 `agent.provider`（`qwen` / `claude` / `deepseek`），所有内部模块会自动切换。

**Q: Skills 从哪里加载？**

框架按 `config/skills.yaml` 中的声明加载。`skill_source: instance` 从实例 `skills/` 目录加载，`skill_source: library` 从全局 `skills/` 目录加载。

**Q: 修改 prompt.md 后需要重启吗？**

需要。`prompt_results/` 在启动时根据 `prompt.md` 生成。修改 `prompt.md` 后重启服务即可生效（框架自动检测变更并重新生成）。

**Q: 如何给实例添加新 Skill？**

1. 在 `skills/` 下创建目录和 `SKILL.md`
2. 在 `config/skills.yaml` 中添加 Skill 声明
3. 重启服务
