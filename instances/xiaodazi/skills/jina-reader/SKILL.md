---
name: jina-reader
description: Extract clean readable content from any URL using Jina Reader API. No API key required.
quickstart: |
  # 读取网页内容（通过 nodes 工具执行）:
  {"action": "run", "command": ["python3", "-c", "import httpx; r=httpx.get('https://r.jina.ai/目标URL', headers={'Accept':'text/markdown','X-Retain-Images':'none'}, timeout=30, follow_redirects=True); print(r.text[:8000])"], "output_handling": "full"}
  # 搜索（同 ddg-search）:
  {"action": "run", "command": ["python3", "-c", "import httpx,json; r=httpx.get('https://s.jina.ai/搜索关键词', headers={'Accept':'application/json','X-Retain-Images':'none'}, timeout=30); print(json.dumps(r.json(), ensure_ascii=False, indent=2))"], "output_handling": "full"}
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# Jina Reader — 网页内容提取

将任意网页 URL 转换为干净的 Markdown 文本，去除广告、导航栏等噪声。免费，无需 API Key。

## 使用场景

- 用户说「帮我读一下这个链接的内容」「总结这篇文章」
- 需要获取网页完整内容用于分析、翻译、摘要
- deep-research 流程中需要抓取网页正文
- 用户分享了一个 URL，想了解内容

## 执行方式

**必须通过 `nodes` 工具执行，禁止使用 api_calling！**

### 读取网页内容

将目标 URL 拼接到 `https://r.jina.ai/` 后面：

```json
{
  "action": "run",
  "command": ["python3", "-c", "import httpx; r=httpx.get('https://r.jina.ai/https://example.com/article', headers={'Accept':'text/markdown','X-Retain-Images':'none'}, timeout=30, follow_redirects=True); print(r.text[:8000])"],
  "output_handling": "full"
}
```

### 搜索功能

```json
{
  "action": "run",
  "command": ["python3", "-c", "import httpx,json; r=httpx.get('https://s.jina.ai/搜索关键词', headers={'Accept':'application/json','X-Retain-Images':'none'}, timeout=30); print(json.dumps(r.json(), ensure_ascii=False, indent=2))"],
  "output_handling": "full"
}
```

### 使用建议

1. **优先用于长文章**：短页面直接搜索摘要即可，长文用 Jina Reader 获取完整内容
2. **配合搜索使用**：先用 `ddg-search` 找到 URL，再用 Jina Reader 提取正文
3. **超时处理**：设置 30 秒超时
4. **内容截断**：超长文章只取前 8000 字符，避免上下文溢出

## 输出规范

- 提取的内容保持原文结构（标题、段落、列表）
- 标注来源 URL
- 如果提取失败，告知用户并说明原因

## 注意事项

- **不要用 api_calling**，Jina Reader 不是注册 API
- **不要打开 Safari/浏览器**做手动搜索，直接用 nodes 执行 Python 命令
- 使用 `nodes` 工具 + `python3 -c` 执行 httpx 请求
