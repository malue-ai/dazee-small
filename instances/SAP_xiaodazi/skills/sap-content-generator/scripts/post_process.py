"""
SAP 内容后处理：终点名称一致性检查 + AI 标记收集

用法：python post_process.py <sap_sections> <entities> <output>
"""
import json, re, sys
from pathlib import Path

def check_names(sections, entities):
    issues = []
    all_text = " ".join(str(v) for v in sections.values())
    for cat in ["primary", "key_secondary", "other_secondary"]:
        for ep in entities.get("endpoints", {}).get(cat, []):
            name = ep.get("name") or ep.get("value", {}).get("name", "")
            if not name: continue
            if name not in all_text:
                sev = "WARNING" if name.lower() in all_text.lower() else "ERROR"
                issues.append({"type": "name_" + sev.lower(), "endpoint": name, "severity": sev})
    return issues

def collect_inferred(sections):
    items = []
    for sid, content in sections.items():
        for m in re.finditer(r"\[AI-INFERRED\]", content):
            ctx = content[max(0,m.start()-50):min(len(content),m.end()+50)].strip()
            items.append({"section": sid, "context": ctx})
    return items

if __name__ == "__main__":
    if len(sys.argv) < 4: print(f"Usage: {sys.argv[0]} <sections> <entities> <output>"); sys.exit(1)
    sections = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    entities = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    report = {"endpoint_issues": check_names(sections, entities), "ai_inferred": collect_inferred(sections)}
    Path(sys.argv[3]).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Post-process: {len(report['endpoint_issues'])} issues, {len(report['ai_inferred'])} AI-inferred")
