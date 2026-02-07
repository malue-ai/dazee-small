---
name: xdotool
description: Linux UI automation using xdotool for window management, keyboard/mouse simulation, and desktop control.
metadata:
  xiaodazi:
    dependency_level: external
    os: [linux]
    backend_type: local
    user_facing: true
    bins: ["xdotool"]
---

# Linux UI 自动化

使用 xdotool 控制 Linux 桌面窗口和输入。

## 安装

```bash
# Debian/Ubuntu
sudo apt install xdotool

# Fedora
sudo dnf install xdotool

# Arch
sudo pacman -S xdotool
```

## 命令参考

### 窗口管理

```bash
# 获取当前活动窗口
xdotool getactivewindow getwindowname

# 按名称查找窗口
xdotool search --name "Firefox"

# 激活窗口
xdotool windowactivate $(xdotool search --name "Firefox" | head -1)

# 最小化/最大化
xdotool windowminimize $(xdotool getactivewindow)

# 移动和调整大小
xdotool windowmove --sync $(xdotool getactivewindow) 100 100
xdotool windowsize --sync $(xdotool getactivewindow) 1200 800
```

### 键盘输入

```bash
# 输入文本
xdotool type "Hello World"

# 按键
xdotool key Return
xdotool key ctrl+c
xdotool key ctrl+shift+t
xdotool key super
```

### 鼠标操作

```bash
# 移动鼠标
xdotool mousemove 500 300

# 点击
xdotool click 1  # 左键
xdotool click 3  # 右键

# 移动并点击
xdotool mousemove 500 300 click 1
```

### 等待

```bash
# 等待窗口出现
xdotool search --sync --name "Save"
```

## 注意

- 仅支持 X11，Wayland 下需要用 `ydotool` 替代
- 某些应用可能不响应 xdotool 的键盘输入
