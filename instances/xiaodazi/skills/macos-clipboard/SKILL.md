---
name: macos-clipboard
description: Read from and write to the macOS clipboard using pbcopy and pbpaste commands.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [darwin]
    backend_type: local
    user_facing: true
    bins: ["pbcopy", "pbpaste"]
---

# macOS 剪贴板

使用 macOS 内置的 pbcopy/pbpaste 操作剪贴板。

## 使用场景

- 用户说「读一下我剪贴板里的内容」「帮我复制这段话」
- 任务流程中需要在剪贴板传递数据
- 需要获取用户刚复制的内容进行处理

## 命令参考

### 读取剪贴板

```bash
pbpaste
```

### 写入剪贴板

```bash
echo "要复制的内容" | pbcopy
```

### 从文件复制到剪贴板

```bash
pbcopy < "/path/to/file.txt"
```

### 将剪贴板内容保存到文件

```bash
pbpaste > "/path/to/output.txt"
```

### 追加剪贴板内容到文件

```bash
pbpaste >> "/path/to/output.txt"
```

## 输出规范

- 读取剪贴板后，展示内容（长文本截断显示前 500 字符）
- 写入剪贴板后，确认「已复制到剪贴板」
- 处理剪贴板内容时，先展示内容再确认操作
