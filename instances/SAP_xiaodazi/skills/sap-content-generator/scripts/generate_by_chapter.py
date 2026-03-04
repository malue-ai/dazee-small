"""
SAP 逐章生成编排 — 模板驱动的动态章节体系

核心原则：生成 -> 写文件 -> 忘记 -> 下一章

章节序列从 template_structure.json 动态加载，不再硬编码章节编号。
通过 content_type 字段匹配 Prompt 文件，适配任意 SAP 模板格式。

每次 LLM 调用的上下文只含：System Prompt + 本章 Prompt + 本章实体子集。
禁止累积前序章节。
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional


# ==================== content_type -> Prompt 路由 ====================

PROMPT_ROUTER: Dict[str, Optional[str]] = {
    "estimand":             "prompts/estimand.md",
    "endpoint_objectives":  "prompts/estimand.md",
    "primary_analysis":     "prompts/primary_analysis.md",
    "secondary_analysis":   "prompts/secondary_analysis.md",
    "sensitivity_analysis": "prompts/sensitivity.md",
    "safety_analysis":      "prompts/safety.md",
    "multiplicity":         "prompts/multiplicity.md",
    "hypothesis_testing":   "prompts/multiplicity.md",
    "general_considerations": "prompts/sensitivity.md",
    "study_info":           None,   # template type: fill from entities
    "study_design":         None,
    "population_definition": None,
    "sample_size":          None,
    "manual_input":         None,   # placeholder
    "boilerplate":          None,
}

# content_type -> generation type mapping
GENERATION_TYPE: Dict[str, str] = {
    "estimand":             "llm",
    "endpoint_objectives":  "llm",
    "primary_analysis":     "llm_per_endpoint",
    "secondary_analysis":   "llm",
    "sensitivity_analysis": "llm",
    "safety_analysis":      "llm",
    "multiplicity":         "llm",
    "hypothesis_testing":   "llm",
    "general_considerations": "llm",
    "study_info":           "template",
    "study_design":         "template",
    "population_definition": "template",
    "sample_size":          "template",
    "manual_input":         "placeholder",
    "boilerplate":          "boilerplate",
}

# content_type -> entity dependency mapping
ENTITY_DEPENDENCIES: Dict[str, List[str]] = {
    "estimand":             ["endpoints", "study_design", "intercurrent_events"],
    "endpoint_objectives":  ["endpoints", "study_design"],
    "primary_analysis":     ["endpoints.primary", "statistical_methods", "study_design"],
    "secondary_analysis":   ["endpoints.key_secondary", "endpoints.other_secondary", "statistical_methods"],
    "sensitivity_analysis": ["endpoints.primary", "missing_data"],
    "safety_analysis":      ["endpoints.safety", "study_design"],
    "multiplicity":         ["multiplicity", "endpoints.primary"],
    "hypothesis_testing":   ["multiplicity", "endpoints.primary"],
    "general_considerations": ["study_design", "missing_data"],
    "study_info":           ["study_identification"],
    "study_design":         ["study_design"],
    "population_definition": ["analysis_populations"],
    "sample_size":          ["sample_size"],
}

# Downstream Skill triggers by content_type
DOWNSTREAM_BY_TYPE: Dict[str, List[str]] = {
    "estimand":             ["document-assembler", "compliance-checker"],
    "primary_analysis":     ["statistical-code-generator", "document-assembler", "compliance-checker"],
    "secondary_analysis":   ["statistical-code-generator", "document-assembler", "compliance-checker"],
    "sensitivity_analysis": ["document-assembler", "compliance-checker"],
    "safety_analysis":      ["statistical-code-generator", "document-assembler", "compliance-checker"],
    "multiplicity":         ["document-assembler", "compliance-checker"],
}
DOWNSTREAM_DEFAULT = ["document-assembler"]


def _sanitize_id(section_id: str) -> str:
    """Convert section ID to safe filename component."""
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", section_id)


# ==================== 动态加载 ====================


def load_chapter_sequence(template_structure_path: str) -> List[dict]:
    """
    从 template_structure.json 动态生成章节序列。

    每个章节条目包含：
      id, title, content_type, type (template/llm/...), prompt, depends, filename

    如果 template_structure.json 不存在或为空，返回 FALLBACK_SEQUENCE。
    """
    path = Path(template_structure_path)
    if not path.exists():
        print(f"WARN: {path} not found, using fallback sequence")
        return FALLBACK_SEQUENCE

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"WARN: Failed to parse {path}: {e}, using fallback")
        return FALLBACK_SEQUENCE

    sections = data.get("sections", [])
    if not sections:
        print("WARN: template_structure.json has no sections, using fallback")
        return FALLBACK_SEQUENCE

    sequence = []
    for i, sec in enumerate(sections):
        sid = sec.get("id", str(i + 1))
        content_type = sec.get("content_type", "boilerplate")
        title = sec.get("title", f"Section {sid}")
        gen_type = GENERATION_TYPE.get(content_type, "template")
        prompt = PROMPT_ROUTER.get(content_type)
        depends = ENTITY_DEPENDENCIES.get(content_type, [])
        filename = f"{i:02d}_{_sanitize_id(sid)}.md"

        sequence.append({
            "id": sid,
            "title": title,
            "content_type": content_type,
            "type": gen_type,
            "prompt": prompt,
            "depends": depends,
            "filename": filename,
        })

    print(f"Loaded {len(sequence)} chapters from template_structure.json")
    return sequence


def build_filename_map(sequence: List[dict]) -> Dict[str, str]:
    """Build chapter ID -> filename mapping from sequence."""
    return {ch["id"]: ch["filename"] for ch in sequence}


def build_downstream_triggers(sequence: List[dict]) -> Dict[str, List[str]]:
    """Build chapter ID -> downstream Skill triggers from sequence."""
    result = {}
    for ch in sequence:
        ct = ch.get("content_type", "")
        result[ch["id"]] = DOWNSTREAM_BY_TYPE.get(ct, DOWNSTREAM_DEFAULT)
    return result


# ==================== Fallback: 硬编码序列（模板解析失败时使用） ====================

FALLBACK_SEQUENCE = [
    {"id": "title_page", "title": "Title Page", "content_type": "study_info",
     "type": "template", "prompt": None, "depends": ["study_identification"],
     "filename": "00_title_page.md"},
    {"id": "1", "title": "Objectives, Endpoints, and Estimands", "content_type": "estimand",
     "type": "llm", "prompt": "prompts/estimand.md", "depends": ["endpoints", "study_design"],
     "filename": "01_estimand.md"},
    {"id": "2", "title": "Study Design", "content_type": "study_design",
     "type": "template", "prompt": None, "depends": ["study_design"],
     "filename": "02_study_design.md"},
    {"id": "3", "title": "Statistical Hypotheses and Multiplicity", "content_type": "multiplicity",
     "type": "llm", "prompt": "prompts/multiplicity.md", "depends": ["multiplicity", "endpoints.primary"],
     "filename": "03_multiplicity.md"},
    {"id": "4", "title": "Analysis Sets", "content_type": "population_definition",
     "type": "template", "prompt": None, "depends": ["analysis_populations"],
     "filename": "04_analysis_sets.md"},
    {"id": "5.1", "title": "General Considerations", "content_type": "general_considerations",
     "type": "llm", "prompt": "prompts/sensitivity.md", "depends": ["study_design", "missing_data"],
     "filename": "05_1_general.md"},
    {"id": "5.2", "title": "Primary Endpoint Analysis", "content_type": "primary_analysis",
     "type": "llm_per_endpoint", "prompt": "prompts/primary_analysis.md",
     "depends": ["endpoints.primary", "statistical_methods"],
     "filename": "05_2_primary.md"},
    {"id": "5.3", "title": "Secondary Endpoint Analysis", "content_type": "secondary_analysis",
     "type": "llm", "prompt": "prompts/secondary_analysis.md",
     "depends": ["endpoints.key_secondary", "statistical_methods"],
     "filename": "05_3_secondary.md"},
    {"id": "5.4", "title": "Other Secondary and Exploratory", "content_type": "secondary_analysis",
     "type": "llm", "prompt": "prompts/secondary_analysis.md",
     "depends": ["endpoints.other_secondary"],
     "filename": "05_4_other_secondary.md"},
    {"id": "5.5", "title": "Safety Analyses", "content_type": "safety_analysis",
     "type": "llm", "prompt": "prompts/safety.md", "depends": ["endpoints.safety", "study_design"],
     "filename": "05_5_safety.md"},
    {"id": "5.6", "title": "Other Analyses", "content_type": "study_info",
     "type": "template", "prompt": None, "depends": ["study_design.stratification_factors"],
     "filename": "05_6_subgroup.md"},
    {"id": "5.7", "title": "Interim Analysis / Changes", "content_type": "manual_input",
     "type": "placeholder", "prompt": None, "depends": [],
     "filename": "05_7_interim_changes.md"},
    {"id": "6", "title": "Sample Size Determination", "content_type": "sample_size",
     "type": "template", "prompt": None, "depends": ["sample_size"],
     "filename": "06_sample_size.md"},
    {"id": "7", "title": "References", "content_type": "boilerplate",
     "type": "boilerplate", "prompt": None, "depends": [],
     "filename": "07_references.md"},
    {"id": "appendix_a", "title": "Appendix A: Abbreviations", "content_type": "boilerplate",
     "type": "boilerplate", "prompt": None, "depends": [],
     "filename": "08_appendix_abbreviations.md"},
]

# Legacy compatibility aliases
CHAPTER_SEQUENCE = FALLBACK_SEQUENCE
CHAPTER_FILENAME = build_filename_map(FALLBACK_SEQUENCE)
DOWNSTREAM_TRIGGERS = build_downstream_triggers(FALLBACK_SEQUENCE)
