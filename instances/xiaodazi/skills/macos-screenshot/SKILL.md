---
name: macos-screenshot
description: Capture screenshots on macOS using the built-in screencapture command. Supports full screen, window, and region capture.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [darwin]
    backend_type: local
    user_facing: true
    bins: ["screencapture"]
---

# macOS 截图

使用 macOS 内置的 screencapture 命令截取屏幕。

## 使用场景

- 用户说「帮我截个图」「截一下当前屏幕」
- 用户需要保存当前页面内容
- 任务需要查看屏幕上的信息

## 命令参考

### 全屏截图

```bash
screencapture -x "/tmp/screenshot_$(date +%Y%m%d_%H%M%S).png"
```

参数说明：
- `-x` 静默模式（不播放快门声）

### 窗口截图

```bash
# 交互式选择窗口
screencapture -x -w "/tmp/window_$(date +%Y%m%d_%H%M%S).png"
```

### 区域截图

```bash
# 交互式选择区域
screencapture -x -s "/tmp/region_$(date +%Y%m%d_%H%M%S).png"
```

### 延时截图

```bash
# 延迟 3 秒后截图
screencapture -x -T 3 "/tmp/delayed_$(date +%Y%m%d_%H%M%S).png"
```

### 截图到剪贴板

```bash
# 截图直接复制到剪贴板
screencapture -x -c
```

## 常用参数

| 参数 | 说明 |
|------|------|
| `-x` | 静默，不播放声音 |
| `-w` | 窗口模式 |
| `-s` | 区域选择模式 |
| `-c` | 输出到剪贴板 |
| `-T <秒>` | 延时截图 |
| `-t <格式>` | 输出格式（png/jpg/pdf） |

## 输出规范

- 默认保存到 `/tmp/` 目录，文件名包含时间戳
- 截图完成后告知用户保存路径
- 如果用户指定了保存位置，使用用户指定的路径
