---
name: local-search
description: Search local files by content using SQLite FTS5 full-text search and macOS Spotlight (mdfind). Supports txt, md, pdf, docx, and more.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 本地文件搜索

在用户电脑上搜索文件，支持按名称和内容搜索。

## 使用场景

- 用户说「帮我找一下上次写的报告」「搜一下包含 XXX 的文件」
- 用户需要查找特定文件但不记得存在哪里
- 任务执行中需要定位参考文件

## 搜索方式

### 方式 1：macOS Spotlight（推荐，最快）

利用系统已建好的索引，毫秒级返回。

```bash
# 按文件名搜索
mdfind -name "报告"

# 按内容搜索
mdfind "季度总结"

# 限定目录
mdfind -onlyin ~/Documents "预算"

# 限定文件类型
mdfind "kind:pdf 合同"
mdfind "kind:word 报告"
mdfind "kind:excel 数据"
mdfind "kind:presentation PPT"

# 按时间范围（最近 7 天修改的）
mdfind "kMDItemFSContentChangeDate >= $time.today(-7)"

# 组合条件
mdfind -onlyin ~/Documents "kind:pdf AND 合同"
```

### 方式 2：find + grep（精确匹配）

Spotlight 搜不到时用这个。

```bash
# 按文件名搜索（模糊）
find ~/Documents -iname "*报告*" -type f

# 按文件内容搜索（文本文件）
grep -rl "关键词" ~/Documents --include="*.txt" --include="*.md" --include="*.py"

# 最近 7 天修改的文件
find ~/Documents -type f -mtime -7

# 按大小搜索（大于 10MB）
find ~/Documents -type f -size +10M
```

### 方式 3：SQLite FTS5（结构化搜索）

对已建索引的文件做全文搜索，适合大量文档。

```python
import sqlite3
import os

DB_PATH = os.path.expanduser("~/.xiaodazi/search_index.db")

def search(query: str, limit: int = 20):
    """全文搜索已索引的文件"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # FTS5 搜索
    cursor.execute("""
        SELECT path, snippet(file_index, 1, '【', '】', '...', 32)
        FROM file_index
        WHERE file_index MATCH ?
        ORDER BY rank
        LIMIT ?
    """, (query, limit))
    
    results = cursor.fetchall()
    conn.close()
    return results
```

## 搜索策略

1. **优先用 mdfind**：系统级索引，覆盖面广，速度快
2. **mdfind 无结果时用 find + grep**：精确但慢，限定目录范围
3. **FTS5 用于项目内搜索**：对用户指定的监控文件夹建索引

## 输出规范

- 展示前 10 条结果，包含文件路径和摘要片段
- 路径用 `~` 简写用户目录
- 告知用户总共找到多少结果
- 文件过多时询问用户是否要进一步筛选
