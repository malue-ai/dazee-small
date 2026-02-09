# 系统级 Skills

本目录存放平台内置的系统级 Skills，所有实例共享。

## 两级加载机制

zenflux agent 采用两级 Skill 加载机制：

| 优先级 | 来源 | 说明 |
|--------|------|------|
| 1（低）| `skills/library/`（本目录） | 系统级内置技能（所有实例共享） |
| 2（高）| `instances/{agent_id}/skills/` | 实例级自定义技能（运营人员配置） |

## 目录结构

```
skills/library/
├── README.md                    # 本文件
├── planning-task/               # 任务规划技能
│   └── SKILL.md
├── slidespeak-generator/        # PPT 生成技能
│   ├── SKILL.md
│   └── scripts/
├── ontology-builder/            # 本体构建技能
│   └── SKILL.md
└── ...                          # 其他内置技能
```

## 添加新的系统级 Skill

1. 创建技能目录：`mkdir skills/library/my-skill`
2. 创建 `SKILL.md` 文件，包含 YAML frontmatter
3. 可选：添加 `scripts/` 和 `resources/` 目录

## SKILL.md 格式

```yaml
---
name: skill-name
description: "技能描述"
metadata:
  priority: medium
  preferred_for: ["关键词"]
---

# Skill Name

## 使用场景
...

## 工作流程
...
```

## 注意

- 系统级 Skills 会被同名的实例级 Skills 覆盖
- 修改系统级 Skills 会影响所有实例
