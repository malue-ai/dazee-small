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

## UI 自动化（必读）

**优先使用 Peekaboo CLI** 进行所有 GUI 操作，而不是盲目 `osascript`。

### 核心工作流：see → click → type

```bash
# 1. 先看屏幕，获取带标注的 UI 元素 ID
peekaboo see --app "<目标应用>" --annotate --json

# 2. 用元素 ID 精确点击（不用猜坐标）
peekaboo click --on B3 --app "<目标应用>"

# 3. 输入文字
peekaboo type "Hello" --app "<目标应用>"
```

### 截图 + AI 分析（看懂屏幕内容）

```bash
# 截图并用 AI 分析内容（--analyze 接自然语言提问）
peekaboo see --app "<目标应用>" --analyze "描述当前页面内容"

# 仅截图保存
peekaboo image --mode frontmost --retina --path /tmp/screenshot.png
```

### 键盘 / 鼠标操作

```bash
peekaboo hotkey --keys "cmd,s"                          # 快捷键
peekaboo press tab --count 2                             # 按键
peekaboo scroll --direction down --amount 5 --app "<应用>"  # 滚动
```

### 应用 / 窗口管理

```bash
peekaboo app list --json                                 # 列出运行中的应用
peekaboo app launch "<应用>" --open https://example.com   # 启动应用
peekaboo window focus --app "<应用>"                      # 聚焦窗口
peekaboo menu click --app "<应用>" --item "New Tab"       # 点击菜单
```

### ⚠️ 何时回退到 osascript

仅当 Peekaboo 不可用时（`which peekaboo` 失败）才使用 osascript。

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

### 文件操作
```bash
mkdir -p ~/path/to/dir      # 创建文件夹
cp source dest               # 复制文件
mv source dest               # 移动文件
```

---

*添加任何能帮你完成工作的配置。这是你的备忘录。*
