---
name: sap-content-generator
description: Generate SAP chapter content in Markdown following ICH E9(R1) Estimand framework. Chapters generated independently to avoid output token limits.
---
# SAP 内容生成
逐章生成 SAP 正文内容。绝对禁止单轮一次性生成。
## 核心原则：逐章生成、写文件即忘
详细编排见 [scripts/generate_by_chapter.py](scripts/generate_by_chapter.py)
## Prompts
- [prompts/system.md](prompts/system.md) — 共享 System Prompt
- [prompts/estimand.md](prompts/estimand.md) — Estimand 描述 (Section 1.1)
- [prompts/primary_analysis.md](prompts/primary_analysis.md) — 主要终点 (Section 4.2)
- [prompts/secondary_analysis.md](prompts/secondary_analysis.md) — 次要终点 (Section 4.3/4.4)
- [prompts/sensitivity.md](prompts/sensitivity.md) — 敏感性分析 (Section 4.5)
- [prompts/safety.md](prompts/safety.md) — 安全性分析 (Section 4.7)
- [prompts/multiplicity.md](prompts/multiplicity.md) — 多重比较 (Section 2.1)
## Scripts
- [scripts/post_process.py](scripts/post_process.py) — 后处理（终点名称校验、AI标记收集）
