---
name: macos-finder
description: Advanced Finder operations on macOS including file tags, Quick Look preview, Get Info, and smart folder creation.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [darwin]
    backend_type: local
    user_facing: true
---

# macOS Finder 操作

Finder 高级操作：标签管理、Quick Look、文件信息、智能文件夹。

## 使用场景

- 用户说「给这些文件打个标签」「预览一下这个文件」
- 用户需要查看文件的详细信息（大小、创建时间等）
- 用户需要按条件筛选文件

## 命令参考

### 文件标签（macOS Tags）

```bash
# 给文件打标签
tag -a "重要" /path/to/file.pdf
# 或者用 xattr
xattr -w com.apple.metadata:_kMDItemUserTags '("重要")' /path/to/file.pdf

# 查看文件标签
mdls -name kMDItemUserTags /path/to/file.pdf

# 按标签搜索文件
mdfind "kMDItemUserTags == '重要'"

# 移除标签
tag -r "重要" /path/to/file.pdf
```

### Quick Look 预览

```bash
# 预览文件（按空格关闭）
qlmanage -p /path/to/file.pdf

# 生成缩略图
qlmanage -t /path/to/file.pdf -s 512 -o /tmp/
```

### 文件详细信息

```bash
# 完整元数据
mdls /path/to/file.pdf

# 常用字段
mdls -name kMDItemDisplayName -name kMDItemFSSize -name kMDItemContentCreationDate -name kMDItemContentModificationDate -name kMDItemKind /path/to/file.pdf

# 人类可读的文件大小
stat -f "大小: %z bytes" /path/to/file.txt
du -sh /path/to/file.txt

# 文件类型
file /path/to/file
```

### 磁盘空间

```bash
# 磁盘总体使用
df -h /

# 当前目录大小
du -sh .

# 子目录大小排序（前 10）
du -sh */ 2>/dev/null | sort -rh | head -10
```

### 最近使用的文件

```bash
# 最近修改的 20 个文件
mdfind "kMDItemFSContentChangeDate >= $time.today(-1)" -onlyin ~ | head -20

# 最近打开的文件（通过 Finder recents）
mdfind "kMDItemLastUsedDate >= $time.today(-7)" -onlyin ~/Documents | head -20
```

### 文件夹统计

```bash
# 统计文件数量和类型
find /path/to/dir -type f | sed 's/.*\.//' | sort | uniq -c | sort -rn

# 统计总文件数
find /path/to/dir -type f | wc -l
```

## 输出规范

- 文件大小用人类可读格式（KB/MB/GB）
- 时间用「X 天前」「刚刚」等自然语言
- 标签操作后确认结果
- 磁盘空间展示用简洁表格
