---
name: skill-finder
description: Search and discover skills, browse installed skills, and install new skills from the community. Use when users ask "is there a skill for X", "find a skill", "what skills do I have", "install a skill", want to extend capabilities, or mention skills.sh or the skills ecosystem.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# Skill 搜索与发现

帮助用户发现和安装新的 Skill，浏览已安装的 Skill，以及从社区搜索和下载 Skill。

## 使用场景

- 用户说「有没有 XX 的 Skill」「帮我找一个能做 XX 的技能」
- 用户说「我有哪些 Skill」「列出所有技能」
- 用户说「安装一个 XX Skill」「从社区找 Skill」
- 用户想扩展 Agent 的能力，问「能不能做 XX」而当前没有对应 Skill
- 用户提到 skills.sh 或 Agent Skills 生态

---

## 功能 1：浏览已安装的 Skill

### 列出所有已安装 Skill

读取 `skill_registry.yaml` 获取完整列表：

```python
import os
import yaml
from pathlib import Path

instance_name = os.environ.get("AGENT_INSTANCE", "xiaodazi")
registry_path = Path(f"instances/{instance_name}/skills/skill_registry.yaml")
registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))

skills = registry.get("skills", [])
for s in skills:
    status_icon = {"ready": "✅", "need_auth": "🔐", "need_setup": "⚙️", "unavailable": "❌"}.get(s.get("status", ""), "❓")
    name = s.get("name", "")
    enabled = "启用" if s.get("enabled", True) else "禁用"
    print(f"{status_icon} {name} ({enabled})")

print(f"\n共 {len(skills)} 个 Skill")
```

### 查看 Skill 详情

读取指定 Skill 的 SKILL.md 获取详细信息：

```python
import os
from pathlib import Path

instance_name = os.environ.get("AGENT_INSTANCE", "xiaodazi")
skill_name = "要查看的skill名称"

# 按优先级搜索
for base in [
    Path(f"instances/{instance_name}/skills"),
    Path("skills/library"),
]:
    skill_md = base / skill_name / "SKILL.md"
    if skill_md.exists():
        content = skill_md.read_text(encoding="utf-8")
        print(content[:2000])  # 输出前 2000 字符
        break
else:
    print(f"未找到 Skill: {skill_name}")
```

### 按分类筛选

读取 `config/skills.yaml` 中的 `skill_groups` 按分组展示：

```python
import os
import yaml
from pathlib import Path

instance_name = os.environ.get("AGENT_INSTANCE", "xiaodazi")
config_path = Path(f"instances/{instance_name}/config/skills.yaml")
config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

groups = config.get("skill_groups", {})
for group_name, group_info in groups.items():
    if group_name.startswith("_"):
        continue
    desc = group_info.get("description", "")
    skills = group_info.get("skills", [])
    print(f"\n📂 {group_name} ({len(skills)} 个)")
    print(f"   {desc}")
    for s in skills:
        print(f"   - {s}")
```

---

## 功能 2：在线搜索社区 Skill

### 方式 A：通过 skills.sh 搜索（推荐）

使用 `npx skills find` 命令搜索开放 Skill 生态系统：

```bash
npx skills find "搜索关键词"
```

如果用户没有安装 Node.js 或 npx 不可用，回退到方式 B。

### 方式 B：通过 GitHub API 搜索

直接搜索知名 Skill 仓库：

```python
import urllib.request
import json

def search_github_skills(query, repos=None):
    """搜索 GitHub 上的 Skill 仓库"""
    if repos is None:
        repos = [
            "anthropics/skills",
            "vercel-labs/agent-skills",
        ]

    results = []
    for repo in repos:
        url = f"https://api.github.com/search/code?q={query}+filename:SKILL.md+repo:{repo}"
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github.v3+json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                for item in data.get("items", []):
                    path = item.get("path", "")
                    html_url = item.get("html_url", "")
                    # 提取 skill 名称（目录名）
                    parts = path.split("/")
                    if len(parts) >= 2:
                        skill_name = parts[-2]
                        results.append({
                            "name": skill_name,
                            "repo": repo,
                            "path": path,
                            "url": html_url,
                        })
        except Exception as e:
            print(f"搜索 {repo} 失败: {e}")

    return results

results = search_github_skills("关键词")
for r in results:
    print(f"📦 {r['name']} (from {r['repo']})")
    print(f"   {r['url']}")
```

### 方式 C：浏览 skills.sh 网站

如果以上方式都不方便，引导用户访问 https://skills.sh/ 在线浏览和搜索。

---

## 功能 3：安装社区 Skill

从 GitHub 下载 Skill 并安装到当前实例。

### 步骤 1：下载 SKILL.md

```python
import os
import urllib.request
from pathlib import Path

def download_skill(repo, skill_path):
    """从 GitHub 下载 SKILL.md"""
    # 构建 raw URL
    raw_url = f"https://raw.githubusercontent.com/{repo}/main/{skill_path}"
    req = urllib.request.Request(raw_url)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8")

# 示例：从 anthropics/skills 下载 frontend-design
content = download_skill("anthropics/skills", "skills/frontend-design/SKILL.md")
print(content[:500])
```

### 步骤 2：适配 frontmatter

社区 Skill 的 frontmatter 可能没有 `metadata.xiaodazi` 块，需要补充：

```python
import yaml

def adapt_frontmatter(content, instance_name="xiaodazi"):
    """为社区 Skill 添加实例适配的 metadata"""
    if not content.startswith("---"):
        return content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return content

    meta = yaml.safe_load(parts[1])
    if not isinstance(meta, dict):
        return content

    # 补充 metadata.xiaodazi 块（如果缺失）
    if "metadata" not in meta:
        meta["metadata"] = {}
    if instance_name not in meta.get("metadata", {}):
        meta["metadata"][instance_name] = {
            "dependency_level": "builtin",
            "os": ["common"],
            "backend_type": "local",
            "user_facing": True,
        }

    # 重新组装
    new_frontmatter = yaml.dump(meta, allow_unicode=True, default_flow_style=False)
    return f"---\n{new_frontmatter}---{parts[2]}"

adapted = adapt_frontmatter(content)
```

### 步骤 3：保存并注册

```python
import os
import yaml
from pathlib import Path

instance_name = os.environ.get("AGENT_INSTANCE", "xiaodazi")
skill_name = "下载的skill名称"

# 保存 SKILL.md
skill_dir = Path(f"instances/{instance_name}/skills/{skill_name}")
skill_dir.mkdir(parents=True, exist_ok=True)
(skill_dir / "SKILL.md").write_text(adapted_content, encoding="utf-8")

# 注册到 skill_registry.yaml
registry_path = Path(f"instances/{instance_name}/skills/skill_registry.yaml")
registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
skills_list = registry.get("skills", [])

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

print(f"✅ {skill_name} 已安装到 {skill_dir}")
print(f"   当前对话即可使用（Agent 会按路径读取 SKILL.md）")
```

---

## 常用 Skill 来源

| 来源 | 地址 | 特点 |
|------|------|------|
| Anthropic 官方 | `anthropics/skills` | 高质量示范，包含文档处理、前端设计、MCP 构建等 |
| Vercel Agent Skills | `vercel-labs/agent-skills` | 社区精选，覆盖 React/Next.js 最佳实践等 |
| Skills 目录 | https://skills.sh | 开放生态搜索引擎 |

### Anthropic 仓库中的可用 Skill

- `algorithmic-art` — 算法艺术生成
- `brand-guidelines` — 品牌指南
- `canvas-design` — Canvas 设计
- `doc-coauthoring` — 文档协作
- `frontend-design` — 前端设计
- `internal-comms` — 内部沟通
- `mcp-builder` — MCP Server 构建
- `slack-gif-creator` — Slack GIF 创建
- `theme-factory` — 主题工厂
- `web-artifacts-builder` — Web 组件构建
- `webapp-testing` — Web 应用测试

---

## 输出规范

- 列出 Skill 时用表格或清单格式，包含名称、状态、简介
- 安装完成后告知用户文件路径，并建议试用话术
- 如果搜索无结果，建议用户使用 `skill-creator` 自己创建
- 安装社区 Skill 前，先用 hitl 工具请求用户确认（展示 Skill 内容摘要）
