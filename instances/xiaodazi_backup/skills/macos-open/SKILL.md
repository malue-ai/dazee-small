---
name: macos-open
description: Open files, URLs, and applications on macOS using the open command. The universal entry point for launching anything.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [darwin]
    backend_type: local
    user_facing: true
    bins: ["open"]
---

# macOS 打开

使用 macOS `open` 命令打开文件、URL、应用、文件夹。

## 使用场景

- 用户说「帮我打开这个文件」「打开浏览器到某个网址」
- 任务完成后打开生成的文件让用户查看
- 需要启动某个应用

## 命令参考

### 打开文件（用默认应用）

```bash
open "/path/to/document.pdf"
open ~/Downloads/report.xlsx
```

### 打开文件（指定应用）

```bash
# 用 VS Code 打开
open -a "Visual Studio Code" /path/to/project

# 用 Preview 打开图片
open -a "Preview" /path/to/image.png

# 用 Pages 打开文档
open -a "Pages" /path/to/document.docx
```

### 打开 URL

```bash
open "https://www.google.com"
open "https://notion.so"
```

### 打开应用

```bash
open -a "Safari"
open -a "Finder"
open -a "System Preferences"
# macOS Ventura+
open -a "System Settings"
```

### 打开文件夹

```bash
# 在 Finder 中打开
open ~/Documents
open ~/Downloads

# 在终端中打开（新窗口）
open -a "Terminal" ~/Projects
```

### 显示文件在 Finder 中的位置

```bash
open -R "/path/to/file.txt"
```

### 打开多个文件

```bash
open file1.pdf file2.pdf file3.pdf
```

## 输出规范

- 打开后告知用户「已打开 XXX」
- 如果文件不存在，说明原因并帮助查找
- 打开 URL 时直接打开，不需要确认
- 打开应用时如果应用不存在，推荐替代或安装方式
