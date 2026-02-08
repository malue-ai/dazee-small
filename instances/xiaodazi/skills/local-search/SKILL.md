---
name: local-search
description: Search user's local knowledge base and files using the knowledge_search tool (FTS5 + semantic) and macOS Spotlight (mdfind) for filename lookup.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 本地文件搜索

在用户电脑上搜索文件内容和文件名。

## 使用场景

- 用户说「帮我找一下上次写的报告」「搜一下包含 XXX 的文件」
- 用户需要查找特定文件但不记得存在哪里
- 任务执行中需要定位参考文件

## 搜索方式

### 方式 1：knowledge_search 工具（内容搜索，首选）

搜索已索引知识库中的文档内容。支持 FTS5 全文搜索和语义搜索。

```
工具名: knowledge_search

参数:
  query:     搜索查询（自然语言），必填
  limit:     返回结果数量，默认 5
  file_type: 过滤文件类型（如 .md, .txt, .pdf），可选
```

<example>
<query>帮我找一下之前写的季度总结</query>
<action>
调用 knowledge_search，参数：{"query": "季度总结"}
</action>
<reasoning>用户要搜索文档内容，knowledge_search 覆盖已索引文件，优先使用</reasoning>
</example>

<example>
<query>搜一下包含"预算审批"的 PDF 文件</query>
<action>
调用 knowledge_search，参数：{"query": "预算审批", "file_type": ".pdf"}
</action>
<reasoning>有明确的文件类型过滤需求，使用 file_type 参数</reasoning>
</example>

<example>
<query>我上传的产品文档里有没有提到竞品分析？</query>
<action>
调用 knowledge_search，参数：{"query": "竞品分析"}
</action>
<reasoning>搜索已索引文档中的特定内容</reasoning>
</example>

### 方式 2：mdfind（文件名搜索，补充）

knowledge_search 无结果时，用 macOS Spotlight 按文件名或元数据搜索。

```bash
# 按文件名搜索
mdfind -name "报告"

# 限定目录
mdfind -onlyin ~/Documents "预算"

# 限定文件类型
mdfind "kind:pdf 合同"
mdfind "kind:word 报告"
```

## 搜索策略

1. **优先用 knowledge_search**：覆盖已索引的知识库文件，支持内容搜索和语义匹配
2. **knowledge_search 无结果时用 mdfind**：按文件名或元数据搜索，覆盖面更广
3. **两者都无结果时**：告知用户，询问是否需要将目标目录加入知识库索引

## 输出规范

- 展示搜索结果，包含文件路径和摘要片段
- 路径用 `~` 简写用户目录
- 告知用户总共找到多少结果
- 结果过多时询问用户是否要进一步筛选
