---
name: competitive-intel
description: Monitor competitor websites, products, and social media for updates. Generate periodic competitive intelligence reports.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 竞品动态监控

监控竞品网站、产品更新和社交媒体动态，生成竞争情报报告。

## 使用场景

- 用户说「帮我跟踪一下 XX 竞品的动态」「XX 最近有什么更新」
- 产品经理需要定期了解竞品变化
- 创业者需要监控市场动态

## 监控方式

### 1. 网站变更检测

```bash
# 抓取网页内容快照
curl -s "https://competitor.com/pricing" | python3 -c "
import sys
from html.parser import HTMLParser

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.texts = []
    def handle_data(self, data):
        text = data.strip()
        if text:
            self.texts.append(text)

parser = TextExtractor()
parser.feed(sys.stdin.read())
print('\n'.join(parser.texts[:50]))
" > /tmp/competitor_$(date +%Y%m%d).txt

# 与上次快照对比
diff /tmp/competitor_prev.txt /tmp/competitor_$(date +%Y%m%d).txt
```

### 2. RSS/博客监控

配合 `blogwatcher` Skill 追踪竞品博客更新。

### 3. GitHub 监控（开源竞品）

配合 `github` Skill 追踪竞品仓库的 Release、Issue、PR。

```bash
# 查看竞品最近的 Release
gh release list --repo competitor/product --limit 5
```

### 4. 社交媒体关键词监控

```bash
# 通过公开 API 搜索关键词（示例：Twitter/X API）
# 需要 API Key，可选
curl -s "https://api.twitter.com/2/tweets/search/recent?query=竞品名称" \
  -H "Authorization: Bearer $TWITTER_BEARER_TOKEN"
```

## 报告格式

```markdown
## 竞品动态报告 — {竞品名称}
**报告日期**: 2025-02-07
**监控周期**: 过去 7 天

### 产品更新
- [2025-02-05] 发布 v3.2，新增 XX 功能
- [2025-02-03] 定价页面调整，企业版涨价 10%

### 社交媒体动态
- 官方博客发布了关于 AI 集成的文章
- Twitter 上获得 500+ 转发

### 关键变化
1. 功能差异：新增了我们没有的 XX 功能
2. 定价变化：企业版价格上调
3. 市场信号：加大了 AI 方向的投入

### 建议行动
- 评估 XX 功能的用户需求优先级
- 关注其 AI 集成方案的用户反馈
```

## 数据存储

```bash
# 竞品追踪配置
mkdir -p ~/.xiaodazi/competitive

# 竞品列表
cat > ~/.xiaodazi/competitive/watchlist.json << 'EOF'
{
  "competitors": [
    {
      "name": "CompetitorA",
      "website": "https://competitor-a.com",
      "blog_rss": "https://competitor-a.com/blog/rss",
      "github": "competitor-a/product",
      "keywords": ["竞品A", "CompetitorA"]
    }
  ]
}
EOF
```

## 输出规范

- 报告简洁，聚焦「变化」和「行动建议」
- 区分事实（客观变化）和分析（主观判断）
- 注明信息来源和时间
