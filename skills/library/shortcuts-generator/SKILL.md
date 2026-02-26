---
name: shortcuts-generator
description: Generate macOS/iOS Shortcuts by creating plist shortcut files programmatically.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [darwin]
    backend_type: local
    user_facing: true
---

# 快捷指令生成器

通过编程方式生成 macOS/iOS 快捷指令文件（.shortcut），实现自动化工作流。

## 使用场景

- 用户说「帮我创建一个快捷指令，每天自动打开工作用的 App」
- 用户说「做一个截图并发邮件的快捷指令」
- 用户说「创建一个自动整理下载文件夹的快捷方式」

## 执行方式

### 原理

快捷指令本质是 `.shortcut` 格式的 plist 文件，可以通过 Python 生成并导入。

### 生成快捷指令

```python
import plistlib
import uuid

def make_action(identifier, parameters=None):
    action = {
        "WFWorkflowActionIdentifier": identifier,
        "WFWorkflowActionParameters": parameters or {},
    }
    return action

shortcut = {
    "WFWorkflowMinimumClientVersion": 900,
    "WFWorkflowMinimumClientVersionString": "900",
    "WFWorkflowActions": [
        make_action("is.workflow.actions.openapp", {
            "WFAppIdentifier": "com.apple.Safari",
        }),
        make_action("is.workflow.actions.notification", {
            "WFNotificationActionBody": "工作模式已启动！",
        }),
    ],
    "WFWorkflowClientVersion": "2612.0.4",
    "WFWorkflowHasOutputFallback": False,
    "WFWorkflowIcon": {
        "WFWorkflowIconStartColor": 4282601983,
        "WFWorkflowIconGlyphNumber": 59511,
    },
    "WFWorkflowImportQuestions": [],
    "WFWorkflowInputContentItemClasses": [],
    "WFWorkflowOutputContentItemClasses": [],
    "WFWorkflowTypes": ["NCWidget", "WatchKit"],
}

output_path = "/tmp/work_mode.shortcut"
with open(output_path, "wb") as f:
    plistlib.dump(shortcut, f)
```

### 导入快捷指令

```bash
open /tmp/work_mode.shortcut
```

系统会弹出快捷指令 App 的导入确认界面。

### 常用 Action 标识符

| 功能 | Identifier |
|---|---|
| 打开 App | `is.workflow.actions.openapp` |
| 发送通知 | `is.workflow.actions.notification` |
| 获取剪贴板 | `is.workflow.actions.getclipboard` |
| 运行 Shell 脚本 | `is.workflow.actions.runscript` |
| 发送邮件 | `is.workflow.actions.sendmail` |
| 显示提醒 | `is.workflow.actions.alert` |

## 输出规范

- 生成 .shortcut 文件后提示用户双击导入
- 说明快捷指令的功能和触发方式
- 复杂快捷指令先列出步骤让用户确认
