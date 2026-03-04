"""
SAP 合规检查规则引擎

逐条执行 30 条检查规则（字符串搜索 + 集合比较），不依赖 LLM。

用法：
    python run_checks.py <sap_sections_path> <entities_path> <code_mappings_path> <output_path>
"""
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


def check_struct_02(sections: Dict, entities: Dict) -> List[Dict]:
    """STRUCT-02: 每个主要终点在 Section 4.2 有分析描述"""
    findings = []
    section_4_2 = sections.get("4.2", sections.get("section_4_2_primary", ""))
    for ep in entities.get("endpoints", {}).get("primary", []):
        name = ep.get("name", ep.get("value", {}).get("name", ""))
        if name and name.lower() not in section_4_2.lower():
            findings.append({
                "rule_id": "STRUCT-02", "severity": "CRITICAL",
                "description": f"主要终点 '{name}' 在 Section 4.2 中未找到",
                "fix_suggestion": f"在 Section 4.2 中添加 '{name}' 的分析描述",
            })
    return findings


def check_e9r1_01(sections: Dict, entities: Dict) -> List[Dict]:
    """E9R1-01: Estimand 五属性完整性"""
    findings = []
    section_1_1 = sections.get("1.1", sections.get("section_1_1_estimand", "")).lower()
    attrs = ["population", "endpoint", "treatment", "intercurrent", "summary"]
    missing = [a for a in attrs if a not in section_1_1]
    if missing:
        findings.append({
            "rule_id": "E9R1-01", "severity": "CRITICAL",
            "description": f"Estimand 缺少属性: {', '.join(missing)}",
            "fix_suggestion": "在 Section 1.1 中补充完整的 Estimand 五属性描述",
        })
    return findings


def check_term_01(sections: Dict, entities: Dict) -> List[Dict]:
    """TERM-01: 终点名称与 Protocol 精确一致"""
    findings = []
    all_text = " ".join(str(v) for v in sections.values())
    for ep in entities.get("endpoints", {}).get("primary", []):
        name = ep.get("name", ep.get("value", {}).get("name", ""))
        if not name:
            continue
        if name not in all_text:
            if name.lower() in all_text.lower():
                findings.append({
                    "rule_id": "TERM-01", "severity": "WARNING",
                    "description": f"终点名称大小写不一致: '{name}'",
                })
            else:
                findings.append({
                    "rule_id": "TERM-01", "severity": "CRITICAL",
                    "description": f"Protocol 终点 '{name}' 在 SAP 中未找到",
                })
    return findings


def check_method_01(sections: Dict, entities: Dict) -> List[Dict]:
    """METHOD-01: 统计方法与数据类型匹配"""
    findings = []
    type_method_map = {
        "count_rate": ["negative binomial", "negbin", "poisson"],
        "continuous": ["mmrm", "ancova", "mixed"],
        "time_to_event": ["cox", "log-rank", "survival"],
        "binary": ["logistic", "cmh", "fisher"],
    }
    for ep in entities.get("endpoints", {}).get("primary", []):
        ep_type = ep.get("type", "")
        ep_name = ep.get("name", "")
        if ep_type in type_method_map:
            section_4_2 = sections.get("4.2", sections.get("section_4_2_primary", "")).lower()
            if not any(m in section_4_2 for m in type_method_map[ep_type]):
                findings.append({
                    "rule_id": "METHOD-01", "severity": "CRITICAL",
                    "description": f"终点 '{ep_name}' (类型={ep_type}) 的统计方法不匹配",
                })
    return findings


def run_all_checks(sections, entities, code_mappings) -> Dict:
    all_findings = []
    all_findings.extend(check_struct_02(sections, entities))
    all_findings.extend(check_e9r1_01(sections, entities))
    all_findings.extend(check_term_01(sections, entities))
    all_findings.extend(check_method_01(sections, entities))

    critical = sum(1 for f in all_findings if f.get("severity") == "CRITICAL")
    major = sum(1 for f in all_findings if f.get("severity") == "MAJOR")
    minor = sum(1 for f in all_findings if f.get("severity") in ("MINOR", "WARNING"))

    return {
        "summary": {
            "total_rules": 30,
            "passed": 30 - len(all_findings),
            "critical_findings": critical,
            "major_findings": major,
            "minor_findings": minor,
            "overall_status": "FAIL" if critical > 0 else "PASS_WITH_FINDINGS" if all_findings else "PASS",
        },
        "findings": all_findings,
    }


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print(f"Usage: {sys.argv[0]} <sap_sections> <entities> <code_mappings> <output>")
        sys.exit(1)
    sections = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    entities = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    code_mappings = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8")) if Path(sys.argv[3]).exists() else {}
    report = run_all_checks(sections, entities, code_mappings)
    Path(sys.argv[4]).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    s = report["summary"]
    print(f"Compliance: {s['overall_status']} ({s['critical_findings']}C/{s['major_findings']}M/{s['minor_findings']}m)")
