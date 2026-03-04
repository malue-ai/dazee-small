---
name: compliance-checker
description: Validate SAP documents against ICH E9(R1) requirements, CDISC standards, and internal consistency using 30 hardcoded compliance rules.
---
# 合规性检查
审核 SAP 的合规性和内部一致性（30 条规则，5 组）。
## 规则文件
- [rules/structural.md](rules/structural.md) — 8 条结构完整性
- [rules/ich_e9r1.md](rules/ich_e9r1.md) — 5 条 ICH E9(R1) 合规
- [rules/terminology.md](rules/terminology.md) — 7 条术语一致性
- [rules/methods.md](rules/methods.md) — 6 条方法适当性
- [rules/code_consistency.md](rules/code_consistency.md) — 4 条代码一致性
## Scripts
- [scripts/run_checks.py](scripts/run_checks.py) — 规则引擎主程序
