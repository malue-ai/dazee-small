---
name: skill-creator
description: Create new skills and improve existing skills. Use when users want to create a skill from scratch, capture a workflow as a skill, update or optimize an existing skill, improve a skill's description for better triggering accuracy, or ask anything about how skills work in this system.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# Skill 创建器

帮助用户创建新的 Skill 或改进已有 Skill。一个 Skill 就是一组指令，教 Agent 如何完成特定任务。

## 使用场景

- 用户说「帮我做一个 Skill」「把这个流程变成 Skill」「创建一个 XX 技能」
- 用户对某个已有 Skill 不满意，想要改进
- 用户想把当前对话中的成功工作流固化下来
- 用户问「Skill 怎么写」「SKILL.md 格式是什么」

## 核心流程

创建 Skill 的过程：

1. **捕获意图** — 弄清楚用户想让 Skill 做什么
2. **访谈研究** — 追问边界情况、输入输出格式、依赖
3. **编写 SKILL.md** — 生成文件并保存
4. **测试验证** — 用几个真实场景测试
5. **迭代改进** — 根据反馈优化

你的任务是判断用户在这个流程的哪个阶段，然后帮他推进。

---

## 第一步：捕获意图

如果用户想从零开始，先搞清楚这几个问题（可以从对话上下文推断，不必每个都问）：

1. **这个 Skill 让 Agent 做什么？** — 核心功能
2. **什么时候应该触发这个 Skill？** — 用户说什么话、什么场景
3. **输出格式是什么？** — 文件、文本、还是执行动作
4. **有什么依赖？** — 需要命令行工具、Python 包、API Key、还是纯 LLM 就够

如果用户说「把这个流程变成 Skill」，从当前对话中提取：用了什么工具、执行了什么步骤、用户做了什么修正、输入输出长什么样。

## 第二步：访谈研究

主动追问：

- 边界情况怎么处理？
- 有没有示例文件或参考？
- 成功标准是什么？
- 有没有类似的现有 Skill 可以参考？

如果涉及外部工具或 API，确认依赖信息（命令名、包名、API Key 字段名）。

## 第三步：编写 SKILL.md

### SKILL.md 结构

```
skill-name/
├── SKILL.md          (必需)
├── scripts/          (可选 - 确定性/重复性任务的脚本)
├── references/       (可选 - 按需加载的参考文档)
└── assets/           (可选 - 模板、图标等资源文件)
```

### frontmatter 格式

每个 SKILL.md 必须以 YAML frontmatter 开头：

```yaml
---
name: my-skill-name
description: 清晰描述这个 Skill 做什么、什么时候用它。
metadata:
  xiaodazi:
    dependency_level: builtin    # builtin / lightweight / external / cloud_api
    os: [common]                 # [common] / [darwin] / [win32] / [linux]
    backend_type: local          # local / tool / mcp / api
    user_facing: true
---
```

**字段说明：**

- `name`：唯一标识，小写，用连字符分隔（如 `my-cool-skill`）
- `description`：触发机制的核心。要包含：做什么 + 什么时候用。写得稍微"积极"一些，让 Agent 更容易触发。例如不要写"生成仪表盘"，要写"生成仪表盘。当用户提到数据可视化、报表、图表、监控面板时都应该使用这个 Skill"
- `dependency_level`：
  - `builtin` — 装好就能用，无需额外安装
  - `lightweight` — 需要 pip install 一个包或系统授权
  - `external` — 需要安装外部应用/CLI 工具
  - `cloud_api` — 需要 API Key
- `os`：`[common]` 表示全平台，也可以是 `[darwin]`、`[win32]`、`[linux]`
- `backend_type`：`local` 表示通过 SKILL.md 指导 Agent 执行

### 正文编写指南

**渐进式加载（Progressive Disclosure）**：

Skill 的内容分三层加载：
1. **Metadata**（name + description）— 始终在上下文中，约 100 词
2. **SKILL.md 正文** — Skill 被触发时加载，理想情况 < 500 行
3. **附属资源** — 按需读取，无上限

所以 SKILL.md 正文要精炼。超过 500 行时，把详细内容放到 `references/` 子目录，正文中用指针引导。

**写作原则：**

- **解释为什么，而不是堆砌 MUST**。今天的 LLM 很聪明，理解了原因比死记规则更有效。如果你发现自己在写"ALWAYS"或"NEVER"（全大写），停下来想想能不能换个方式解释背后的道理。
- **用祈使句**。直接说"搜索文件"而不是"你应该搜索文件"。
- **给例子**。展示输入和输出的对应关系比长篇描述更清晰。
- **泛化，不要过拟合**。Skill 会被用在很多不同场景，不要让指令只适用于某个特定例子。
- **先写草稿，再审视优化**。写完后换个角度看一遍，删掉不必要的内容。

**推荐的正文结构：**

```markdown
# Skill 名称（中文）

一句话描述这个 Skill 做什么。

## 使用场景

- 用户说「...」
- 需要做 XX 的时候

## 执行方式

### 方式 1：XXX（首选）

具体步骤和代码示例...

### 方式 2：YYY（备选）

备选方案...

## 输出规范

- 输出格式要求
- 注意事项
```

### 依赖声明

如果 Skill 需要外部依赖，在 frontmatter 中声明：

```yaml
# 需要 Python 包
metadata:
  xiaodazi:
    dependency_level: lightweight
    # ...
# 在 skills.yaml 注册时加上：
# python_packages: ["pandas", "openpyxl"]
# auto_install: true

# 需要命令行工具
metadata:
  xiaodazi:
    dependency_level: external
    # ...
# 在 skills.yaml 注册时加上：
# bins: ["ffmpeg"]

# 需要 API Key
metadata:
  xiaodazi:
    dependency_level: cloud_api
    # ...
# 在 skills.yaml 注册时加上：
# api_config: { auth_type: "bearer", auth_key_field: "MY_API_KEY" }
```

### 保存文件

确定好内容后，用 `nodes` 工具执行 Python 代码保存文件：

```python
import os
from pathlib import Path

skill_name = "my-skill-name"
instance_name = os.environ.get("AGENT_INSTANCE", "xiaodazi")

# 保存 SKILL.md
skill_dir = Path(f"instances/{instance_name}/skills/{skill_name}")
skill_dir.mkdir(parents=True, exist_ok=True)

skill_content = """---
name: {name}
description: {description}
metadata:
  {instance_name}:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# ...正文...
"""

(skill_dir / "SKILL.md").write_text(skill_content, encoding="utf-8")
print(f"✅ Skill 已保存到 {skill_dir / 'SKILL.md'}")
```

### 注册到 skill_registry.yaml

保存 SKILL.md 后，追加到注册表让系统感知：

```python
import yaml
from pathlib import Path

instance_name = os.environ.get("AGENT_INSTANCE", "xiaodazi")
registry_path = Path(f"instances/{instance_name}/skills/skill_registry.yaml")

registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
skills_list = registry.get("skills", [])

# 检查是否已注册
skill_name = "my-skill-name"
if not any(s.get("name") == skill_name for s in skills_list):
    skills_list.append({
        "name": skill_name,
        "enabled": True,
        "status": "ready",
    })
    registry["skills"] = skills_list
    registry_path.write_text(
        yaml.dump(registry, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    print(f"✅ 已注册到 {registry_path}")
else:
    print(f"ℹ️ {skill_name} 已在注册表中")
```

注册后，用户下次提到这个 Skill 时，Agent 可以直接按路径读取 SKILL.md 并执行。如果要让它出现在 `<available_skills>` 列表中（无需用户主动提起就能自动匹配），还需要编辑 `instances/{instance_name}/config/skills.yaml`，但这通常不必在创建时立即做。

---

## 第四步：测试验证

Skill 创建后，验证它能正常工作：

1. **构造 2-3 个真实测试场景** — 用户实际会怎么说
2. **模拟执行** — 按照 SKILL.md 的指引走一遍流程
3. **检查输出** — 是否符合预期

把测试场景和结果告诉用户，让用户确认是否满意。

## 第五步：迭代改进

根据测试反馈改进 Skill：

- **从反馈中泛化** — 不要只修复特定测试用例，要理解背后的模式
- **保持精简** — 删掉不起作用的内容
- **解释 why** — 如果 Agent 总是犯同一个错，与其加"MUST NOT"，不如解释为什么那样做不好
- **提取重复工作** — 如果每次执行都要写同样的脚本，把它放到 `scripts/` 目录

---

## 改进已有 Skill

如果用户想改进现有 Skill：

1. 先读取现有 SKILL.md 内容
2. 了解用户不满意的地方
3. 分析问题原因（指令不清楚？缺少边界情况处理？格式不对？）
4. 修改并保存
5. 测试验证

---

## Description 优化技巧

description 是 Skill 被触发的核心机制。优化原则：

- **包含同义词和常见说法**：用户可能用不同的词描述同一件事
- **稍微"积极"一些**：当前系统倾向于"少触发"，所以 description 要覆盖面广一点
- **说明 what + when**：不仅说做什么，还要说什么情况下用

好的例子：
> "生成数据可视化图表。当用户提到图表、柱状图、折线图、饼图、数据可视化、报表生成时使用。"

不好的例子：
> "生成图表"

## 输出规范

- 创建完成后，告知用户 Skill 文件路径和注册状态
- 建议用户试一试新 Skill（给出测试用的话术）
- 如果 Skill 有外部依赖，提醒用户还需要在 `config/skills.yaml` 中注册依赖信息
