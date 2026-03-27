---
name: knowledge-base
description: "Local knowledge base with SQLite FTS5 full-text search for saving, organizing, and retrieving knowledge snippets. Use when a user wants to save, search, or organize personal knowledge and notes."
metadata:
  xiaodazi:
    dependency_level: lightweight
    os: [common]
    backend_type: local
    user_facing: true
    python_packages: ["sqlite-utils"]
---

# 个人知识库

基于 SQLite + FTS5 的本地知识库。数据存储在 `~/Documents/xiaodazi/knowledge.db`。

## 数据库初始化

首次使用时创建表结构：

```python
import sqlite3, os

db_path = os.path.expanduser("~/Documents/xiaodazi/knowledge.db")
os.makedirs(os.path.dirname(db_path), exist_ok=True)
db = sqlite3.connect(db_path)
db.executescript("""
CREATE TABLE IF NOT EXISTS knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL, content TEXT NOT NULL,
    tags TEXT DEFAULT '', source TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
    title, content, tags, content='knowledge', content_rowid='id'
);
""")
```

## 核心操作

### 保存知识

```python
db = sqlite3.connect(db_path)
cursor = db.execute(
    "INSERT INTO knowledge (title, content, tags, source) VALUES (?, ?, ?, ?)",
    ["Python GIL", "全局解释器锁，同一时刻只有一个线程执行字节码", "python,并发", ""])
row_id = cursor.lastrowid
db.execute(
    "INSERT INTO knowledge_fts (rowid, title, content, tags) VALUES (?, ?, ?, ?)",
    [row_id, "Python GIL", "全局解释器锁，同一时刻只有一个线程执行字节码", "python,并发"])
db.commit()

# 验证保存成功
saved = db.execute("SELECT title, tags FROM knowledge WHERE id = ?", [row_id]).fetchone()
assert saved is not None, "保存失败"
```

**回复用户:** `已保存 ✅「Python GIL」— 标签：python, 并发`

### 搜索知识

```python
results = db.execute("""
    SELECT k.id, k.title, snippet(knowledge_fts, 1, '**', '**', '...', 30) as excerpt,
           k.tags, k.created_at
    FROM knowledge_fts JOIN knowledge k ON knowledge_fts.rowid = k.id
    WHERE knowledge_fts MATCH ?
    ORDER BY rank LIMIT 10
""", ["Python"]).fetchall()
```

### 按标签浏览

```python
results = db.execute("""
    SELECT title, substr(content, 1, 100) as preview, created_at
    FROM knowledge WHERE tags LIKE '%python%'
    ORDER BY updated_at DESC
""").fetchall()
```

## 完整交互示例

```
用户: 帮我记住——Python 的 GIL 是全局解释器锁
→ 自动提取标签 [python, 并发]
→ INSERT + 验证
→ 回复: 已保存 ✅「Python GIL」— 标签：python, 并发

用户: 我之前存过什么关于 Python 的知识？
→ FTS5 搜索
→ 找到 3 条:
  1. Python 装饰器原理（2/20）
  2. Python GIL（2/26）
  3. Python 异步编程（2/22）
```

## 输出规范

- 保存时确认标题和标签，让用户知道怎么找回
- 搜索结果按相关度排序，显示摘要预览
- 标签自动提取，用户也可手动指定
- 支持从其他 Skill 的输出直接存入（如深度调研的结论）
