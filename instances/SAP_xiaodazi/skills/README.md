# 实例级 Skills 配置指南

本目录存放该智能体实例的自定义 Skills。

## 两级加载机制

zenflux agent 采用两级 Skill 加载机制：

| 优先级 | 来源 | 说明 |
|--------|------|------|
| 1（低）| `skills/library/` | 系统级内置技能（所有实例共享） |
| 2（高）| `instances/{agent_id}/skills/` | 实例级自定义技能（运营人员配置） |

**实例级技能会覆盖同名的系统级技能**，这允许运营人员针对特定场景定制技能行为。

## 目录结构

```
skills/
├── README.md                  # 本文件
├── skill_registry.yaml        # Skills 注册表（声明启用哪些 Skills）
├── _template/                 # Skill 模板（供复制创建新 Skill）
│   └── SKILL.md
└── [your-skill-name]/         # 自定义 Skill 目录
    ├── SKILL.md              # 必需：Skill 入口文件
    ├── references/           # 可选：参考资料
    │   └── *.md
    └── scripts/              # 可选：Python 脚本
        └── *.py
```

## 快速开始

### Step 1: 创建 Skill 目录

```bash
# 复制模板
cp -r _template my-skill-name
```

### Step 2: 编辑 SKILL.md

按照模板格式填写 `my-skill-name/SKILL.md`：

```yaml
---
name: my-skill-name
description: "技能描述（用于系统提示词注入）"
metadata:
  priority: high
  preferred_for: ["关键词1", "关键词2"]
---

# My Skill Name

## 使用场景
当用户需要...

## 工作流程
1. 分析需求
2. 执行操作
3. 返回结果
```

### Step 3: 在注册表中声明

编辑 `skill_registry.yaml`，添加：

```yaml
skills:
  - name: my-skill-name
    enabled: true
    description: "我的技能描述"
```

### Step 4: 启动实例

Skills 会在实例启动时自动加载到系统提示词中。

## 与系统级 Skills 的关系

- 如果实例级定义了与系统级同名的 Skill，实例级会覆盖系统级
- 这允许运营人员定制特定场景的技能行为
- 例如：实例级的 `excel-analyzer` 可以覆盖系统级的通用版本

## 注意事项

1. **SKILL.md 必需**：每个 Skill 目录必须包含 `SKILL.md` 文件
2. **YAML Frontmatter**：`SKILL.md` 必须以 `---` 开头的 YAML frontmatter
3. **name 和 description**：frontmatter 中必须包含这两个字段
