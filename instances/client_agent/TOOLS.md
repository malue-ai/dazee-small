# TOOLS.md - 本地配置

Skills 定义了工具*如何*工作，这个文件记录*你的*具体配置——你的设备独有的东西。

## 这里记录什么

- 应用程序路径和别名
- SSH 主机和别名
- 常用文件夹路径
- 设备昵称
- 任何环境特定的配置

## 常用路径

| 名称 | 路径 |
|------|------|
| 下载 | ~/Downloads |
| 文档 | ~/Documents |
| 桌面 | ~/Desktop |
| 应用程序 | /Applications |
| 用户目录 | ~ |

## 应用程序

| 名称 | 应用 |
|------|------|
| 浏览器 | Safari |
| 终端 | Terminal.app |
| 编辑器 | VS Code |
| 文件管理器 | Finder |
| 图片预览 | Preview |

## 常用命令

### 打开应用
```bash
open -a "Safari"
open -a "Finder"
```

### 打开 URL
```bash
open "https://apple.com"
```

### 打开文件夹
```bash
open ~/Downloads
```

### AppleScript 示例
```bash
osascript -e 'tell application "Safari" to open location "https://apple.com"'
osascript -e 'tell application "Finder" to open folder "Downloads" of home'
```

---

*添加任何能帮你完成工作的配置。这是你的备忘录。*
