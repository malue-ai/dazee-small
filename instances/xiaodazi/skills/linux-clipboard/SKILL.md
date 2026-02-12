---
name: linux-clipboard
description: Read from and write to the Linux clipboard using xclip or xsel.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [linux]
    backend_type: local
    user_facing: true
---

# Linux 剪贴板

使用 xclip 或 xsel 操作 Linux 剪贴板。

## 命令参考

### 使用 xclip

```bash
# 读取剪贴板
xclip -selection clipboard -o

# 写入剪贴板
echo "要复制的内容" | xclip -selection clipboard

# 从文件复制到剪贴板
xclip -selection clipboard < "/path/to/file.txt"
```

### 使用 xsel（替代方案）

```bash
# 读取剪贴板
xsel --clipboard --output

# 写入剪贴板
echo "要复制的内容" | xsel --clipboard --input
```

## 安装

```bash
# Debian/Ubuntu
sudo apt install xclip

# Fedora
sudo dnf install xclip
```

## 输出规范

- 读取后展示内容（长文本截断前 500 字符）
- 写入后确认「已复制到剪贴板」
