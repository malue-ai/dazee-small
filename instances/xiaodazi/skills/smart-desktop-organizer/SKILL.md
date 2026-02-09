---
name: smart-desktop-organizer
description: Intelligently organize messy desktops and download folders by semantically categorizing files, deduplicating, and archiving old items.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 智能桌面整理

帮助用户智能整理桌面、下载文件夹等混乱目录：按语义分类、清理重复、归档旧文件。

## 使用场景

- 用户说「我的桌面太乱了，帮我整理一下」「下载文件夹清理一下」
- 用户说「把文件按项目/类型分类」「把旧文件归档」
- 用户说「找出重复文件」「清理不需要的临时文件」

## 执行方式

通过 bash 命令 + LLM 语义判断完成。先扫描目录，再由 LLM 分析每个文件的用途和分类，最后执行整理。

### Step 1: 扫描目录

```bash
# 列出目标目录的文件（含大小和修改日期）
ls -lhS ~/Desktop/ | head -50
ls -lhS ~/Downloads/ | head -50
```

### Step 2: LLM 语义分类

根据文件名、扩展名、修改日期，将文件分为以下类别：

| 类别 | 典型文件 | 目标文件夹 |
|---|---|---|
| Documents | .pdf, .docx, .xlsx, .pptx | ~/Documents/Organized/ |
| Images | .png, .jpg, .gif, .svg | ~/Pictures/Organized/ |
| Archives | .zip, .tar.gz, .rar | ~/Documents/Archives/ |
| Installers | .dmg, .exe, .pkg | 清理或归档 |
| Temp | .tmp, .crdownload, partial | 直接删除 |

### Step 3: 执行整理

```bash
# 创建分类目录
mkdir -p ~/Documents/Organized ~/Pictures/Organized ~/Documents/Archives

# 移动文件（示例）
mv ~/Desktop/*.pdf ~/Documents/Organized/
mv ~/Desktop/*.png ~/Pictures/Organized/
```

### Step 4: 找出重复文件

```bash
# 按 MD5 查找重复文件
find ~/Downloads -type f -exec md5sum {} + | sort | uniq -w32 -dD
```

### Step 5: 归档旧文件

```bash
# 找出 90 天未修改的文件
find ~/Desktop -type f -mtime +90 -not -name ".*"
```

## 安全规则

- **不自动删除任何文件**：只移动和归档，删除前必须用 HITL 工具确认
- **优先移到回收站**：macOS 用 `trash`，避免 `rm`
- **操作前展示计划**：先列出分类计划让用户确认，再执行
- **跳过隐藏文件**：不整理以 `.` 开头的文件
- **跳过系统文件**：不操作 /System、/Library 等路径

## 输出规范

- 先展示整理计划（哪些文件移到哪里）
- 执行后报告：移动了 X 个文件，清理了 Y MB 空间
- 提醒用户检查归档内容
