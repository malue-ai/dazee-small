---
name: deep-doc-reader
description: Deep analysis and Q&A for long documents (PDF reports, contracts, papers, manuals). Uses PageIndex MCP to build hierarchical tree indexes and reason over document structure for precise section-level retrieval.
metadata:
  xiaodazi:
    dependency_level: cloud_api
    os: [common]
    backend_type: mcp
    user_facing: true
    api_key_env: PAGEINDEX_API_KEY
---

# 长文档深度阅读与问答

对长 PDF（年报、合同、论文、手册）进行结构化理解和精准问答。通过 PageIndex MCP 将文档构建为层级树索引，实现章节级定位和推理检索。

## 使用场景

- 用户说「帮我分析这份年报里 Q3 的营收数据」
- 用户说「这份合同的违约条款在哪？具体怎么写的？」
- 用户说「这篇 80 页的论文，实验方法部分说了什么？」
- 用户说「帮我找这份手册里关于安装步骤的部分」
- 用户需要反复询问同一份长文档的不同内容

## 何时使用此 Skill（而非其他工具）

```
判断逻辑：

文档相关请求
  ├── 文件在哪？找某个文件 → 用 local-search
  ├── 简单摘要/概述 → 用 summarize
  ├── 编辑 PDF 内容 → 用 nano-pdf
  ├── 创建 Word/Excel → 用 word-processor / excel-analyzer
  └── 长文档深度问答（以下场景）→ 用 deep-doc-reader ✅
       ├── PDF 超过 20 页
       ├── 需要精确定位到具体章节/页码
       ├── 需要反复查询同一文档的不同部分
       └── 需要理解文档的层级结构
```

## 工作流程

### 第一步：上传文档建立索引

用户提供 PDF 文件后，通过 PageIndex MCP 工具上传并建立树索引：

```
用户提供 PDF 路径或 URL
    ↓
调用 PageIndex MCP 上传文档
    ↓
PageIndex 自动构建层级树索引（目录 → 章节 → 子章节）
    ↓
返回文档 ID，后续查询使用此 ID
```

**注意**：
- 首次上传需要等待索引构建（大文档约 1-3 分钟）
- 索引构建完成后，后续查询都是即时的
- 免费额度：1000 页

### 第二步：基于树索引进行问答

```
用户提问：「Q3 营收数据是多少？」
    ↓
PageIndex 通过树结构推理导航：
  文档根节点 → 财务数据章节 → Q3 季度报告 → 营收数据
    ↓
返回精确内容 + 页码引用
    ↓
整理回答，附上来源页码
```

### 第三步：多轮追问

同一文档支持多轮追问，无需重新上传：

```
用户：「Q3 营收多少？」 → 回答 + 页码
用户：「跟 Q2 对比呢？」 → 自动导航到 Q2 部分
用户：「管理层怎么解释这个变化？」 → 定位 MD&A 章节
```

## 输出格式

### 标准回答格式

```markdown
## 回答

[具体回答内容]

### 来源

- 📄 第 87 页 - 第三季度财务摘要
- 📄 第 92-93 页 - 营收明细表
```

### 结构概览格式（用户要求了解文档结构时）

```markdown
## 文档结构

📑 XXX 年度报告（共 156 页）
├── 第一章：公司概况（p.1-15）
├── 第二章：经营情况讨论（p.16-45）
│   ├── 2.1 行业形势（p.16-22）
│   ├── 2.2 经营成果（p.23-38）
│   └── 2.3 现金流分析（p.39-45）
├── 第三章：财务报表（p.46-120）
│   ├── 3.1 资产负债表（p.46-52）
│   ├── 3.2 利润表（p.53-60）
│   └── ...
└── 附录（p.121-156）
```

## 输出规范

- 回答必须附上页码引用（用户可验证）
- 数据类回答直接引用原文数字，不做推算
- 长回答分段落，每段标注来源章节
- 如果文档中找不到相关内容，明确告知用户
