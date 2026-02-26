---
name: knowledge-base
description: Personal knowledge base with SQLite FTS5 full-text search. Save, organize, and retrieve knowledge locally.
metadata:
  xiaodazi:
    dependency_level: lightweight
    os: [common]
    backend_type: local
    user_facing: true
    python_packages: ["sqlite-utils"]
---

# 个人知识库

基于 SQLite + FTS5 的本地知识库，帮助用户保存、整理、检索知识片段。数据完全本地化。

## 使用场景

- 用户说「帮我记住这个」「把这个知识点存下来」
- 用户说「我之前保存过关于 XX 的内容吗」「搜索我的知识库」
- 用户说「整理一下我保存的关于 Python 的知识」
- 用户在调研/学习过程中想积累知识卡片

## 执行方式

### 数据库结构

知识库存储在 `~/Documents/xiaodazi/knowledge.db`：

```sql
CREATE TABLE knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT DEFAULT '',           -- 逗号分隔的标签
    source TEXT DEFAULT '',         -- 来源 URL 或文件
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE knowledge_fts USING fts5(
    title, content, tags,
    content='knowledge',
    content_rowid='id'
);
```

### 核心操作

**保存知识**：
```python
import sqlite3

db = sqlite3.connect("~/Documents/xiaodazi/knowledge.db")
db.execute(
    "INSERT INTO knowledge (title, content, tags, source) VALUES (?, ?, ?, ?)",
    ["Python 装饰器原理", "装饰器是一个接受函数并返回函数的高阶函数...", "python,编程", ""]
)
db.execute(
    "INSERT INTO knowledge_fts (rowid, title, content, tags) VALUES (last_insert_rowid(), ?, ?, ?)",
    ["Python 装饰器原理", "装饰器是一个接受函数并返回函数的高阶函数...", "python,编程"]
)
db.commit()
```

**搜索知识**：
```python
results = db.execute("""
    SELECT k.id, k.title, snippet(knowledge_fts, 1, '**', '**', '...', 30) as excerpt,
           k.tags, k.created_at
    FROM knowledge_fts
    JOIN knowledge k ON knowledge_fts.rowid = k.id
    WHERE knowledge_fts MATCH ?
    ORDER BY rank
    LIMIT 10
""", ["Python 装饰器"]).fetchall()
```

**按标签浏览**：
```python
results = db.execute("""
    SELECT title, substr(content, 1, 100) as preview, created_at
    FROM knowledge
    WHERE tags LIKE '%python%'
    ORDER BY updated_at DESC
""").fetchall()
```

### 交互流程

```
用户：帮我记住——Python 的 GIL 是全局解释器锁，同一时刻只有一个线程执行字节码
→ 保存到知识库，自动提取标签 [python, 并发]
→ 回复：已保存 ✅「Python GIL」— 标签：python, 并发

用户：我之前存过什么关于 Python 的知识？
→ 搜索知识库
→ 找到 3 条记录：
  1. Python 装饰器原理（2/20）
  2. Python GIL（2/26）
  3. Python 异步编程（2/22）
```

## 输出规范

- 保存时确认标题和标签，让用户知道怎么找回
- 搜索结果按相关度排序，显示摘要预览
- 标签自动提取，用户也可手动指定
- 支持从其他 skill 的输出直接存入（如 deep-research 的结论）
