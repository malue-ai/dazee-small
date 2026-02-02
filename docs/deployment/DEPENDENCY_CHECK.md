# 实例依赖检查指南

🆕 V6.1: 借鉴 clawdbot 的部署检查机制

## 概述

在部署 ZenFlux Agent 实例前，建议运行依赖检查脚本确保所有 Skills 的依赖已满足。

## 快速开始

### 1. 检查依赖状态

```bash
# 检查 client_agent 实例
python scripts/check_instance_dependencies.py client_agent
```

**输出示例：**
```
======================================================================
📋 client_agent 依赖检查报告
======================================================================

总计: 52 个 Skills
✅ 可用: 22 个
❌ 缺少依赖: 30 个

======================================================================
❌ 缺少依赖的 Skills
======================================================================

## 需要安装命令行工具的 Skills

### peekaboo
   缺少: peekaboo
   安装: brew install steipete/tap/peekaboo

...
```

---

### 2. 生成自动安装脚本

```bash
# 生成安装脚本
python scripts/check_instance_dependencies.py client_agent \
  --generate-install \
  --output install_deps.sh

# 执行安装
chmod +x install_deps.sh
./install_deps.sh
```

**生成的脚本包含：**
- Homebrew 工具安装
- npm 包安装
- Go 模块安装
- 环境变量配置提示

---

### 3. 交互式引导配置

```bash
# 交互式模式
python scripts/check_instance_dependencies.py client_agent --interactive
```

会逐步引导你配置缺失的依赖。

---

## 依赖类型

### 命令行工具（bins）

需要通过包管理器安装：

| 工具 | 安装方式 | 用途 |
|------|----------|------|
| `peekaboo` | `brew install steipete/tap/peekaboo` | macOS UI 自动化 |
| `bird` | `npm install -g @steipete/bird` | Twitter/X CLI |
| `imsg` | `brew install steipete/tap/imsg` | iMessage CLI |

### 环境变量（env）

需要在 `instances/<name>/.env` 中配置：

```bash
# Google Places API
GOOGLE_PLACES_API_KEY=your_key_here

# Notion API
NOTION_API_KEY=your_key_here

# OpenAI API
OPENAI_API_KEY=your_key_here
```

### 操作系统（os）

某些 Skills 仅支持特定操作系统：
- `darwin` (macOS)
- `linux`
- `win32` (Windows)

---

## Skills 资格检查机制

### 静态检查（启动时）

实例加载时自动过滤不满足依赖的 Skills：

```python
# 在 instance_loader.py 中
def _check_skill_eligibility(skill: SkillConfig) -> bool:
    # 检查 bins
    for bin_name in required_bins:
        if shutil.which(bin_name) is None:
            return False
    
    # 检查 env
    for env_name in required_env:
        if not os.getenv(env_name):
            return False
    
    # 检查 OS
    if supported_os and current_os not in supported_os:
        return False
    
    return True
```

### 动态检查（运行时）

🆕 可选：支持运行时检查和热重载

```python
from core.skill.dynamic_loader import DynamicSkillLoader

loader = DynamicSkillLoader(skills_dir)

# 检查单个 skill
if loader.is_skill_eligible("bird"):
    print("✅ bird skill 可用")

# 获取安装说明
instructions = loader.get_install_instructions("bird")
print(instructions)
```

---

## CI/CD 集成

### 在部署脚本中使用

```bash
#!/bin/bash

# 检查依赖
if ! python scripts/check_instance_dependencies.py client_agent; then
    echo "❌ 依赖检查失败"
    echo "💡 运行以下命令查看详情："
    echo "   python scripts/check_instance_dependencies.py client_agent"
    exit 1
fi

echo "✅ 依赖检查通过"
```

### 在 GitHub Actions 中使用

```yaml
- name: Check dependencies
  run: |
    python scripts/check_instance_dependencies.py client_agent
  continue-on-error: true

- name: Generate install script
  if: failure()
  run: |
    python scripts/check_instance_dependencies.py client_agent \
      --generate-install \
      --output install_deps.sh
    
    echo "::warning::部分 Skills 依赖缺失，查看 install_deps.sh"
```

---

## 最佳实践

### 1. 部署前检查

每次部署新实例前运行依赖检查：

```bash
# 创建新实例后
python scripts/check_instance_dependencies.py my_instance

# 安装缺失依赖
python scripts/check_instance_dependencies.py my_instance \
  --generate-install --output /tmp/install.sh
bash /tmp/install.sh
```

### 2. 选择性启用 Skills

如果不需要所有 Skills，可以在 `config.yaml` 中禁用：

```yaml
enabled_skills:
  peekaboo: 1          # 启用
  bird: 0              # 禁用（即使依赖满足）
  notion: 1            # 启用（需配置 API Key）
```

### 3. 环境变量管理

使用 `.env.example` 作为模板：

```bash
# 复制模板
cp instances/client_agent/.env.example instances/client_agent/.env

# 编辑配置
vim instances/client_agent/.env
```

---

## 故障排查

### Q: 为什么某些 Skills 始终不可用？

**A:** 检查依赖：

```bash
# 详细检查
python scripts/check_instance_dependencies.py client_agent

# 查看特定 skill
python -c "
from core.skill.dynamic_loader import DynamicSkillLoader
from pathlib import Path

loader = DynamicSkillLoader(Path('instances/client_agent/skills'))
dep = loader.check_skill_dependency('peekaboo')

print(f'缺少的工具: {dep.missing_bins}')
print(f'缺少的环境变量: {dep.missing_env}')
"
```

### Q: 安装后 Skill 仍不可用？

**A:** 需要重启实例：

```bash
# 实例会在启动时重新检查依赖
# 确保新安装的工具在 PATH 中
which peekaboo  # 验证工具可用

# 重启实例
python scripts/instance_loader.py client_agent
```

### Q: 如何贡献新的 Skills？

**A:** 确保 SKILL.md 包含完整的依赖信息：

```yaml
---
name: my-skill
metadata: {"moltbot":{
  "requires": {
    "bins": ["my-tool"],
    "env": ["MY_API_KEY"]
  },
  "install": [
    {"kind": "brew", "formula": "my-tool"}
  ],
  "os": ["darwin", "linux"]
}}
---
```

---

## 参考

- clawdbot skill eligibility check: `src/agents/skills/config.ts`
- skill metadata format: `docs/tools/skills.md`
- 动态加载器: `core/skill/dynamic_loader.py`
