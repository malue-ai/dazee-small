# Claude Skills 配置指南

本目录存放该智能体实例的 Claude Skills 配置。

## 目录结构

```
skills/
├── README.md                  # 本文件
├── skill_registry.yaml        # Skills 注册表（声明启用哪些 Skills）
├── _template/                 # Skill 模板（供复制创建新 Skill）
│   └── SKILL.md
└── [your-skill-name]/         # 自定义 Skill 目录
    ├── SKILL.md              # 必需：Skill 入口文件
    ├── reference/            # 可选：参考资料
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

按照模板格式填写 `my-skill-name/SKILL.md`。

### Step 3: 在注册表中声明

编辑 `skill_registry.yaml`，添加：

```yaml
skills:
  - name: my-skill-name
    enabled: true
    description: "我的技能描述"
```

### Step 4: 启动实例

Skills 会在实例启动时自动注册到 Claude 服务器。

```bash
python scripts/run_instance.py --instance test_agent
```

## 生命周期管理

| 阶段 | 操作 | 执行者 |
|------|------|--------|
| 创建 | 创建 Skill 目录 + SKILL.md | 运营/开发 |
| 声明 | 在 skill_registry.yaml 中添加 | 运营 |
| 注册 | 启动时自动调用 Anthropic API | instance_loader.py |
| 交互 | Agent 运行时通过 skill_id 调用 | SimpleAgent |
| 注销 | 停止实例时自动注销（可选） | instance_loader.py |

## 注意事项

1. **skill_id 自动管理**：注册成功后，skill_id 会自动回写到 `skill_registry.yaml`
2. **启用/禁用**：设置 `enabled: false` 可临时禁用 Skill，无需删除
3. **版本控制**：修改 SKILL.md 后会自动检测变更并更新注册
