---
name: arxiv-search
description: Search arXiv papers by keyword, category, or author. Returns abstracts, PDF links, and BibTeX entries.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# arXiv 论文搜索

搜索 arXiv 预印本论文（免费，无需 API Key）。

## 使用场景

- 用户说「搜一下 arXiv 上关于 XXX 的最新论文」
- 用户需要某个领域的最新研究
- 用户需要下载论文 PDF

## 搜索方式

### arXiv API 搜索

```bash
# 按关键词搜索（最近 10 篇）
curl -s "http://export.arxiv.org/api/query?search_query=all:large+language+model+agent&start=0&max_results=10&sortBy=submittedDate&sortOrder=descending" | python3 -c "
import xml.etree.ElementTree as ET
import sys

ns = {'atom': 'http://www.w3.org/2005/Atom'}
tree = ET.parse(sys.stdin)
root = tree.getroot()

for i, entry in enumerate(root.findall('atom:entry', ns), 1):
    title = entry.find('atom:title', ns).text.strip().replace('\n', ' ')
    published = entry.find('atom:published', ns).text[:10]
    authors = [a.find('atom:name', ns).text for a in entry.findall('atom:author', ns)]
    summary = entry.find('atom:summary', ns).text.strip()[:200]
    
    # 获取 PDF 链接
    pdf_link = ''
    for link in entry.findall('atom:link', ns):
        if link.get('title') == 'pdf':
            pdf_link = link.get('href')
    
    arxiv_id = entry.find('atom:id', ns).text.split('/')[-1]
    
    print(f'{i}. [{published}] {title}')
    print(f'   作者: {\", \".join(authors[:3])}{\"...\" if len(authors) > 3 else \"\"}')
    print(f'   ID: {arxiv_id}')
    print(f'   PDF: {pdf_link}')
    print(f'   摘要: {summary}...')
    print()
"
```

### 按分类搜索

```bash
# 搜索 cs.AI 分类的最新论文
curl -s "http://export.arxiv.org/api/query?search_query=cat:cs.AI&start=0&max_results=5&sortBy=submittedDate&sortOrder=descending"
```

### 按作者搜索

```bash
curl -s "http://export.arxiv.org/api/query?search_query=au:hinton&max_results=5&sortBy=submittedDate&sortOrder=descending"
```

### 下载 PDF

```bash
# 下载论文 PDF
curl -L -o "/tmp/paper.pdf" "https://arxiv.org/pdf/2301.12345"
```

### 生成 BibTeX

```python
# 从 arXiv ID 生成 BibTeX
arxiv_id = "2301.12345"
bibtex = f"""@article{{{arxiv_id.replace('.', '_')},
  title={{论文标题}},
  author={{作者}},
  journal={{arXiv preprint arXiv:{arxiv_id}}},
  year={{2023}}
}}"""
print(bibtex)
```

## 常用 arXiv 分类

| 分类代码 | 领域 |
|---------|------|
| cs.AI | 人工智能 |
| cs.CL | 计算语言学（NLP） |
| cs.CV | 计算机视觉 |
| cs.LG | 机器学习 |
| cs.SE | 软件工程 |
| stat.ML | 统计机器学习 |

## 输出规范

- 展示前 5-10 篇论文
- 每篇包含：标题、作者、日期、arXiv ID、PDF 链接
- 默认按提交日期排序（最新优先）
- 用户要求时展示摘要或下载 PDF
