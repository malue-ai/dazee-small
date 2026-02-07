---
name: linux-screenshot
description: Capture screenshots on Linux using scrot or gnome-screenshot.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [linux]
    backend_type: local
    user_facing: true
---

# Linux 截图

使用 scrot 或 gnome-screenshot 截取屏幕。

## 命令参考

### 使用 scrot（通用）

```bash
# 全屏截图
scrot "/tmp/screenshot_$(date +%Y%m%d_%H%M%S).png"

# 选区截图
scrot -s "/tmp/region_$(date +%Y%m%d_%H%M%S).png"

# 延时截图
scrot -d 3 "/tmp/delayed_$(date +%Y%m%d_%H%M%S).png"
```

### 使用 gnome-screenshot（GNOME 桌面）

```bash
gnome-screenshot -f "/tmp/screenshot_$(date +%Y%m%d_%H%M%S).png"
```

## 安装

```bash
# Debian/Ubuntu
sudo apt install scrot

# Fedora
sudo dnf install scrot
```

## 输出规范

- 默认保存到 /tmp/ 目录
- 截图完成后告知用户保存路径
