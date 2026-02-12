---
name: file-manager
description: Local file management skill for creating, organizing, searching, and batch-renaming files and folders on the user desktop.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 文件管理

帮助用户管理本地文件和文件夹：创建、整理、搜索、重命名、移动。

## 使用场景

- 用户说「帮我整理下载文件夹」「把这些文件按类型分类」
- 用户需要批量重命名文件
- 用户想查找某个文件

## 执行方式

通过 bash 命令操作本地文件系统。

### 查看目录内容

```bash
ls -la "/path/to/dir"
```

### 创建文件夹

```bash
mkdir -p "/path/to/new/folder"
```

### 移动文件

```bash
mv "/source/file.txt" "/destination/"
```

### 按类型整理

将文件按扩展名分类到对应文件夹：

```bash
# 示例：按文件类型分类
for ext in pdf docx xlsx png jpg; do
  mkdir -p "$TARGET_DIR/$ext"
  mv "$SOURCE_DIR"/*.$ext "$TARGET_DIR/$ext/" 2>/dev/null
done
```

### 搜索文件

```bash
# 按名称搜索
find "/path" -name "*.pdf" -type f

# 按内容搜索（文本文件）
grep -rl "关键词" "/path" --include="*.txt" --include="*.md"
```

### 批量重命名

```bash
# 示例：添加日期前缀
for f in /path/*.pdf; do
  mv "$f" "/path/$(date +%Y%m%d)_$(basename "$f")"
done
```

## 安全规则

- **删除操作前必须确认**：使用 HITL 工具请求用户确认
- **优先移动到回收站**：macOS 用 `trash` 命令，避免直接 `rm`
- **操作前展示预览**：先列出将要操作的文件，用户确认后执行
- **不操作系统目录**：不修改 /System、/Library、/usr 等系统路径
- **路径中有空格时正确引用**：所有路径用双引号包裹
