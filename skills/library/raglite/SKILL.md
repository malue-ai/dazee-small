---
name: raglite
description: Local-first RAG cache — distill documents into structured Markdown for fast retrieval without external services.
metadata:
  xiaodazi:
    dependency_level: lightweight
    os: [common]
    backend_type: local
    user_facing: true
    python_packages: ["raglite"]
---

# RAGLite 本地知识检索

将文档蒸馏为结构化 Markdown 并建立本地索引，实现快速知识检索。无需外部向量数据库。

## 使用场景

- 用户说「帮我把这些文档建成知识库，方便以后查询」
- 用户有大量 PDF/Markdown 文档需要快速搜索
- 需要基于私有文档回答问题（RAG 场景）
- 与 knowledge-base 配合，提供语义搜索能力

## 执行方式

### 安装

```bash
pip install raglite
```

### 索引文档

```python
from raglite import RAGLiteConfig, insert_document

config = RAGLiteConfig(
    db_url="sqlite:///~/Documents/xiaodazi/raglite.db",
)

insert_document(
    doc_path="report.pdf",
    config=config,
)
```

### 检索

```python
from raglite import retrieve_chunks, rerank_chunks

chunks = retrieve_chunks(
    query="公司的营收增长情况",
    num_chunks=10,
    config=config,
)

reranked = rerank_chunks(query="公司的营收增长情况", chunk_ids=[c.id for c in chunks], config=config)
```

### RAG 问答

```python
from raglite import rag

response = rag(
    prompt="根据文档，公司去年的营收是多少？",
    config=config,
)
print(response)
```

### 支持的文档格式

- PDF（通过 MinerU 或 PyPDF 解析）
- Markdown
- 纯文本

## 输出规范

- 索引完成后显示文档数量和索引大小
- 检索结果附带来源文档和页码引用
- 回答时明确标注信息出处
- 数据库存储在本地，不上传
