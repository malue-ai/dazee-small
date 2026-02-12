---
name: applescript
description: Execute AppleScript and JXA (JavaScript for Automation) to control macOS apps, system settings, and UI automation.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [darwin]
    backend_type: local
    user_facing: false
    bins: ["osascript"]
---

# AppleScript 执行

通过 osascript 执行 AppleScript / JXA 脚本，控制 macOS 应用和系统。

## 使用场景

- 需要控制 macOS 原生应用（Finder, Safari, Mail 等）
- 需要弹窗对话框询问用户
- 需要操作系统设置（音量、亮度、Wi-Fi 等）
- 其他 Skill 内部调用

## AppleScript 常用命令

### 应用控制

```bash
# 打开应用
osascript -e 'tell application "Safari" to activate'

# 关闭应用
osascript -e 'tell application "Safari" to quit'

# 获取当前最前方应用
osascript -e 'tell application "System Events" to get name of first application process whose frontmost is true'
```

### 对话框

```bash
# 显示消息
osascript -e 'display dialog "操作完成！" with title "小搭子" buttons {"好的"} default button "好的"'

# 选择列表
osascript -e 'choose from list {"选项A", "选项B", "选项C"} with title "请选择" with prompt "你想要哪个？"'

# 选择文件
osascript -e 'choose file with prompt "选择一个文件"'

# 选择文件夹
osascript -e 'choose folder with prompt "选择一个文件夹"'
```

### 系统信息

```bash
# 获取当前 Wi-Fi 名称
osascript -e 'do shell script "networksetup -getairportnetwork en0 | cut -d: -f2 | xargs"'

# 获取系统音量
osascript -e 'output volume of (get volume settings)'

# 设置音量
osascript -e 'set volume output volume 50'

# 获取电池百分比
osascript -e 'do shell script "pmset -g batt | grep -o \"[0-9]\\+%\""'

# 获取屏幕亮度
osascript -e 'tell application "System Events" to get value of value indicator 1 of slider 1 of group 1 of window 1 of application process "System Preferences"'
```

### Finder 操作

```bash
# 获取当前 Finder 窗口路径
osascript -e 'tell application "Finder" to get POSIX path of (target of front Finder window as alias)'

# 在 Finder 中显示文件
osascript -e 'tell application "Finder" to reveal POSIX file "/path/to/file"'

# 获取选中的文件
osascript -e 'tell application "Finder" to get POSIX path of (selection as alias)'
```

### JXA（JavaScript for Automation）

```bash
# JXA 替代 AppleScript
osascript -l JavaScript -e '
  const app = Application.currentApplication();
  app.includeStandardAdditions = true;
  app.displayDialog("Hello from JXA!");
'

# JXA 获取 Safari 标签页
osascript -l JavaScript -e '
  const safari = Application("Safari");
  const tabs = safari.windows[0].tabs();
  tabs.map(t => t.url()).join("\n");
'
```

## 安全规则

- **不静默执行破坏性操作**：删除文件、发送邮件等必须先通过 HITL 确认
- **不操作密码和密钥**：不用 AppleScript 操作钥匙串
- **权限不足时直接打开设置**：如果操作因权限失败，调用 `open_system_preferences` 工具打开对应设置面板（如 accessibility），不要用文字描述步骤
