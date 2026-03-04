"""
SAP 逐章生成编排 — 核心原则：生成 → 写文件 → 忘记 → 下一章

本文件是流程参考文档，Agent 读取后按指引执行。

章节顺序：
  Phase A: 模板填充（title_page, 1.2, 1.3, 3）
  Phase B: LLM 核心（1.1 Estimand, 2.1, 4.2 per-endpoint, 4.3）
  Phase C: LLM 依赖（4.4, 4.5, 4.7）
  Phase D: 收尾（4.6, 6, 7, appendix_a）

每次 LLM 调用的上下文只含：System Prompt + 本章 Prompt + 本章实体子集。
禁止累积前序章节。
"""

CHAPTER_SEQUENCE = [
    {"id": "title_page", "type": "template", "prompt": None, "depends": ["study_identification"]},
    {"id": "1.2", "type": "template", "prompt": None, "depends": ["study_design"]},
    {"id": "1.3", "type": "template", "prompt": None, "depends": ["sample_size"]},
    {"id": "3", "type": "template", "prompt": None, "depends": ["analysis_populations"]},
    {"id": "1.1", "type": "llm", "prompt": "prompts/estimand.md", "depends": ["endpoints", "study_design"]},
    {"id": "2.1", "type": "llm", "prompt": "prompts/multiplicity.md", "depends": ["multiplicity", "endpoints.primary"]},
    {"id": "4.2", "type": "llm_per_endpoint", "prompt": "prompts/primary_analysis.md", "depends": ["endpoints.primary", "statistical_methods"]},
    {"id": "4.3", "type": "llm", "prompt": "prompts/secondary_analysis.md", "depends": ["endpoints.key_secondary", "statistical_methods"]},
    {"id": "4.4", "type": "llm", "prompt": "prompts/secondary_analysis.md", "depends": ["endpoints.other_secondary"]},
    {"id": "4.5", "type": "llm", "prompt": "prompts/sensitivity.md", "depends": ["endpoints.primary", "missing_data"]},
    {"id": "4.7", "type": "llm", "prompt": "prompts/safety.md", "depends": ["endpoints.safety", "study_design"]},
    {"id": "4.6", "type": "template", "prompt": None, "depends": ["study_design.stratification_factors"]},
    {"id": "6", "type": "placeholder", "prompt": None, "depends": []},
    {"id": "7", "type": "boilerplate", "prompt": None, "depends": []},
    {"id": "appendix_a", "type": "boilerplate", "prompt": None, "depends": []},
]

CHAPTER_FILENAME = {
    "title_page": "title_page.md", "1.1": "section_1_1_estimand.md",
    "1.2": "section_1_2_study_design.md", "1.3": "section_1_3_sample_size.md",
    "2.1": "section_2_1_multiplicity.md", "3": "section_3_analysis_sets.md",
    "4.2": "section_4_2_primary.md", "4.3": "section_4_3_key_secondary.md",
    "4.4": "section_4_4_other_secondary.md", "4.5": "section_4_5_sensitivity.md",
    "4.6": "section_4_6_subgroup.md", "4.7": "section_4_7_safety.md",
    "6": "section_6_changes.md", "7": "section_7_references.md",
    "appendix_a": "appendix_a_abbreviations.md",
}

# 选择性重新生成：章节 → 需要重跑的下游 Skill
DOWNSTREAM_TRIGGERS = {
    "title_page": ["skill-5"],
    "1.1": ["skill-5", "skill-6"], "1.2": ["skill-5"], "1.3": ["skill-5"],
    "2.1": ["skill-5", "skill-6"], "3": ["skill-5", "skill-6"],
    "4.2": ["skill-4", "skill-5", "skill-6"],
    "4.3": ["skill-4", "skill-5", "skill-6"],
    "4.4": ["skill-4", "skill-5", "skill-6"],
    "4.5": ["skill-5", "skill-6"],
    "4.6": ["skill-5"],
    "4.7": ["skill-4", "skill-5", "skill-6"],
    "6": ["skill-5"], "7": ["skill-5"], "appendix_a": ["skill-5"],
}
