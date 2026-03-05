---
name: sap-content-generator
description: Generate SAP chapter content in Markdown following ICH E9(R1) Estimand framework. Chapters generated independently to avoid output token limits.
---
# SAP 内容生成
逐章生成 SAP 正文内容。绝对禁止单轮一次性生成。
## 核心原则：逐章生成、写文件即忘
详细编排见 [scripts/generate_by_chapter.py](scripts/generate_by_chapter.py)
## Prompts（按 content_type 路由，不依赖固定章节编号）
- [prompts/system.md](prompts/system.md) — 共享 System Prompt（写作规范、few-shot 示例、禁止事项）
- [prompts/estimand.md](prompts/estimand.md) — content_type: estimand / endpoint_objectives
- [prompts/primary_analysis.md](prompts/primary_analysis.md) — content_type: primary_analysis
- [prompts/secondary_analysis.md](prompts/secondary_analysis.md) — content_type: secondary_analysis
- [prompts/sensitivity.md](prompts/sensitivity.md) — content_type: sensitivity_analysis / general_considerations
- [prompts/safety.md](prompts/safety.md) — content_type: safety_analysis
- [prompts/multiplicity.md](prompts/multiplicity.md) — content_type: multiplicity / hypothesis_testing
## Scripts
- [scripts/post_process.py](scripts/post_process.py) — 后处理（终点名称校验、AI标记收集）
