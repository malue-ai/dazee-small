# 终点抽取 Prompt（用于 ENDPOINTS / OBJECTIVES 类章节）
```
从以下 Protocol 文本中抽取所有终点：
- name: 终点全称（与原文一致）
- category: primary / key_secondary / other_secondary / exploratory / safety
- type: continuous / binary / count_rate / time_to_event / composite
- timeframe: 评估时间点
- definition: 终点定义原文

Protocol 文本：
---
{section_text}
---
输出 JSON 数组。
```
