---
name: winget
description: Manage software on Windows using winget (Windows Package Manager). Search, install, upgrade, and list applications from the command line.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [win32]
    backend_type: local
    user_facing: true
    bins: ["winget"]
---

# winget 包管理器（Windows）

使用 Windows 官方包管理器 winget 搜索、安装、升级和管理应用程序。
类似 macOS 上的 Homebrew，是 Windows 10 (1709+) / 11 内置的命令行工具。

## 使用场景

- 用户说「帮我安装 XX 软件」「看看有没有 XX 可以装」
- 需要批量安装/升级应用
- 查看已安装软件列表和版本
- 其他 Skill 依赖的软件需要安装时自动调用

## 命令参考

### 搜索应用

```powershell
# 搜索应用
winget search "Visual Studio Code"

# 精确匹配 ID
winget search --id "Microsoft.VisualStudioCode"

# 按来源筛选（winget / msstore）
winget search "Python" --source winget
```

### 安装应用

```powershell
# 安装应用（静默模式）
winget install --id "Microsoft.VisualStudioCode" --silent --accept-package-agreements --accept-source-agreements

# 安装指定版本
winget install --id "Python.Python.3.12" --version "3.12.4"

# 安装到自定义路径
winget install --id "Git.Git" --location "D:\Tools\Git"

# 从 Microsoft Store 安装
winget install --id "9NBLGGH4NNS1" --source msstore  # EarTrumpet
```

### 列出已安装

```powershell
# 列出所有已安装应用
winget list

# 按名称过滤
winget list "Python"

# 检查可升级的应用
winget upgrade
```

### 升级应用

```powershell
# 升级特定应用
winget upgrade --id "Microsoft.VisualStudioCode"

# 升级所有可升级的应用
winget upgrade --all --silent --accept-package-agreements

# 升级并忽略版本限制
winget upgrade --id "Git.Git" --include-unknown
```

### 卸载应用

```powershell
# 卸载应用
winget uninstall --id "Mozilla.Firefox"
```

### 导出/导入应用列表

```powershell
# 导出当前已安装应用到 JSON
winget export -o "$env:USERPROFILE\Desktop\apps.json"

# 从 JSON 批量安装（换机迁移）
winget import -i "$env:USERPROFILE\Desktop\apps.json" --accept-package-agreements
```

### 查看应用详情

```powershell
# 查看应用详细信息
winget show --id "Microsoft.VisualStudioCode"
```

## 常用安装命令速查

| 应用 | 安装命令 |
|------|----------|
| VS Code | `winget install Microsoft.VisualStudioCode` |
| Git | `winget install Git.Git` |
| Python 3.12 | `winget install Python.Python.3.12` |
| Node.js LTS | `winget install OpenJS.NodeJS.LTS` |
| 7-Zip | `winget install 7zip.7zip` |
| Everything | `winget install voidtools.Everything` |
| PowerToys | `winget install Microsoft.PowerToys` |
| Windows Terminal | `winget install Microsoft.WindowsTerminal` |
| Chrome | `winget install Google.Chrome` |
| Firefox | `winget install Mozilla.Firefox` |
| VLC | `winget install VideoLAN.VLC` |
| Obsidian | `winget install Obsidian.Obsidian` |
| Notion | `winget install Notion.Notion` |

## 与其他 Skill 联动

当其他 Skill 提示「需要安装 XX」时，自动使用 winget 安装：

```
用户: "帮我用 Everything 搜索文件"
→ 检测 Everything 未安装
→ 提示: "Everything 未安装，需要安装吗？"
→ 用户确认
→ winget install voidtools.Everything --silent
→ 安装完成，继续执行搜索
```

## 输出规范

- 安装前展示应用名、版本、来源、大小
- 安装过程展示进度（静默模式下展示"安装中..."）
- 安装完成后确认结果
- 列表输出格式化为表格

## 安全规则

- **安装前必须 HITL 确认**：展示将要安装的应用信息
- **卸载前必须 HITL 确认**
- **始终使用 `--silent` 和 `--accept-package-agreements`** 避免弹窗阻塞
- **不自动执行 `upgrade --all`**：逐个确认
- 优先使用 winget 官方源，避免不可信来源
