---
name: trend-spotter
description: Discover emerging trends and hot topics from news, social media, and search data. Generate trend analysis reports.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 趋势与热点发现

从新闻、社交媒体和搜索数据中发现新兴趋势和热门话题。

## 使用场景

- 用户说「最近 AI 领域有什么新趋势」「今天有什么热点」
- 内容创作者需要找热门话题
- 产品经理需要了解行业动向

## 数据来源

### 1. Google Trends（搜索趋势）

```bash
# 实时热搜（中国）
curl -s "https://trends.google.com/trends/trendingsearches/daily/rss?geo=CN" | python3 -c "
import xml.etree.ElementTree as ET
import sys
tree = ET.parse(sys.stdin)
root = tree.getroot()
ns = {'ht': 'https://trends.google.com/trends/trendingsearches/daily'}
for item in root.findall('.//item')[:10]:
    title = item.find('title').text
    traffic = item.find('ht:approx_traffic', ns)
    traffic_text = traffic.text if traffic is not None else '?'
    print(f'🔥 {title} ({traffic_text})')
"
```

### 2. 新闻聚合

```bash
# 通过公开 RSS 获取行业新闻
# 配合 blogwatcher Skill 使用

# 或直接用 curl 获取新闻 API（免费的如 NewsAPI 有限额）
curl -s "https://newsapi.org/v2/top-headlines?country=cn&category=technology&apiKey=$NEWS_API_KEY&pageSize=10"
```

### 3. GitHub Trending

```bash
# 获取 GitHub 趋势项目
curl -s "https://api.github.com/search/repositories?q=stars:>100+pushed:>$(date -v-7d +%Y-%m-%d)&sort=stars&order=desc&per_page=10" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for repo in data.get('items', [])[:10]:
    name = repo['full_name']
    stars = repo['stargazers_count']
    desc = (repo.get('description') or '')[:60]
    print(f'⭐ {name} ({stars} stars)')
    print(f'   {desc}')
"
```

### 4. Hacker News 热门

```bash
curl -s "https://hacker-news.firebaseio.com/v0/topstories.json" | python3 -c "
import json, sys, urllib.request
ids = json.load(sys.stdin)[:10]
for id in ids:
    url = f'https://hacker-news.firebaseio.com/v0/item/{id}.json'
    item = json.loads(urllib.request.urlopen(url).read())
    title = item.get('title', '')
    score = item.get('score', 0)
    print(f'📰 [{score}分] {title}')
"
```

## 报告格式

```markdown
## 趋势报告 — {领域}
**日期**: 2025-02-07

### 🔥 热门话题 Top 5
1. **话题名** — 简要描述 + 热度指标
2. ...

### 📈 上升趋势
- 趋势 A：过去 7 天搜索量增长 200%
- 趋势 B：GitHub 相关项目 Star 数激增

### 💡 洞察
- 行业正在向 XX 方向发展
- 值得关注的新技术/产品：XX

### 📌 内容创作建议
- 热门选题：XX
- 最佳发布时间：XX
```

## 输出规范

- 数据附带来源和时间
- 区分「热点」（短期爆发）和「趋势」（持续上升）
- 给出可行动的建议（写什么内容、关注什么方向）
