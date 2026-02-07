---
name: paper-search
description: Search academic papers across Semantic Scholar, CrossRef, and DBLP. Returns titles, abstracts, citations, and BibTeX.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 学术论文搜索

搜索学术论文，支持 Semantic Scholar、CrossRef 等开放 API（无需 API Key）。

## 使用场景

- 用户说「帮我搜一下关于 XXX 的论文」「找几篇 LLM Agent 的最新论文」
- 用户需要论文的摘要、引用数、BibTeX
- 用户需要了解某个研究领域的最新进展

## 搜索方式

### Semantic Scholar（推荐，免费，无需 Key）

```bash
# 搜索论文
curl -s "https://api.semanticscholar.org/graph/v1/paper/search?query=large+language+model+agent&limit=10&fields=title,abstract,year,citationCount,authors,url" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for i, paper in enumerate(data.get('data', []), 1):
    title = paper.get('title', '')
    year = paper.get('year', '?')
    citations = paper.get('citationCount', 0)
    authors = ', '.join(a.get('name', '') for a in paper.get('authors', [])[:3])
    url = paper.get('url', '')
    print(f'{i}. [{year}] {title}')
    print(f'   作者: {authors}')
    print(f'   引用: {citations} | {url}')
    print()
"
```

### 获取论文详情

```bash
# 通过论文 ID 获取详情（含摘要）
curl -s "https://api.semanticscholar.org/graph/v1/paper/{paper_id}?fields=title,abstract,year,citationCount,authors,references,url" | python3 -m json.tool
```

### 获取 BibTeX

```bash
# 通过 DOI 获取 BibTeX
curl -sH "Accept: application/x-bibtex" "https://doi.org/{doi}"
```

### CrossRef（通过 DOI 搜索）

```bash
curl -s "https://api.crossref.org/works?query=transformer+attention&rows=5" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for item in data.get('message', {}).get('items', []):
    title = item.get('title', [''])[0]
    doi = item.get('DOI', '')
    year = item.get('published', {}).get('date-parts', [['']])[0][0]
    print(f'[{year}] {title}')
    print(f'  DOI: {doi}')
    print()
"
```

## 输出规范

- 展示前 5-10 篇最相关论文
- 每篇包含：标题、作者（前 3 位）、年份、引用数、链接
- 用户要求时提供 BibTeX
- 如果有摘要，展示前 200 字
