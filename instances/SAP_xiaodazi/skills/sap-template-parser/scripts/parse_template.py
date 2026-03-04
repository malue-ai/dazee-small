"""
SAP 模板解析编排

解析 SAP 模板文档，输出章节结构（含 content_type 分类）。
content_type 是连接模板结构与生成 Prompt 的桥梁。

用法：python parse_template.py <template_path> <output_dir>
"""
import asyncio, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
from utils.document_parser import get_document_parser


CONTENT_TYPE_RULES = [
    (r"estimand|objectives?\s+(and|&)\s+endpoints?|clinical\s+question", "estimand"),
    (r"primary\s+(endpoint|analysis|efficacy)", "primary_analysis"),
    (r"(key\s+)?secondary\s+(endpoint|analysis)|other\s+secondary|exploratory\s+endpoint", "secondary_analysis"),
    (r"sensitivity\s+analys|general\s+consideration|missing\s+data\s+handl", "sensitivity_analysis"),
    (r"safety|adverse\s+event|laboratory|vital\s+sign|ECG|immunogenicity|pharmacokinetic", "safety_analysis"),
    (r"multiplic|multiple\s+compar|hypothesis\s+test|type\s+I\s+error|alpha\s+control|gatekeep", "multiplicity"),
    (r"analysis\s+set|analysis\s+population|\bITT\b|safety\s+population", "population_definition"),
    (r"study\s+design|study\s+schema|randomiz|stratif|blinding|study\s+period", "study_design"),
    (r"sample\s+size|power\s+calc|recruitment", "sample_size"),
    (r"title\s+page|introduction|protocol\s+summary|version\s+history|amendment", "study_info"),
    (r"change.+protocol|interim\s+analys", "manual_input"),
    (r"reference|abbreviat|appendix|software", "boilerplate"),
]


def classify_content_type(title: str) -> str:
    """Classify a section title into a standard content_type."""
    lower = title.lower()
    for pattern, ct in CONTENT_TYPE_RULES:
        if re.search(pattern, lower):
            return ct
    return "boilerplate"


def _extract_section_id(title: str) -> str:
    """Extract section numbering from title (e.g. '4.2.1 Primary Endpoint' -> '4.2.1')."""
    m = re.match(r"^(\d+(?:\.\d+)*)\s", title.strip())
    return m.group(1) if m else ""


def _detect_level(title: str, element_type: str) -> int:
    """Detect heading level from section ID depth."""
    sid = _extract_section_id(title)
    if sid:
        return sid.count(".") + 1
    if element_type == "Title":
        return 1
    return 2


async def main(template_path, output_dir):
    parser = get_document_parser()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    result = await parser.parse(template_path, chunking=True, chunk_max_chars=4000)
    (out / "template_parsed.md").write_text(result.markdown, encoding="utf-8")

    sections = []
    for idx, el in enumerate(result.elements):
        title = el.text.split("\n")[0].strip()
        if not title:
            continue

        sid = _extract_section_id(title) or str(idx + 1)
        ct = classify_content_type(title)
        level = _detect_level(title, el.type.value)

        parent_id = None
        if "." in sid:
            parent_id = sid.rsplit(".", 1)[0]

        sections.append({
            "id": sid,
            "title": title,
            "content_type": ct,
            "level": level,
            "page": el.metadata.get("page_number"),
            "required": ct not in ("boilerplate", "manual_input"),
            "parent_id": parent_id,
        })

    structure = {
        "template_info": {
            "source": Path(template_path).name,
            "parser": result.parser_used,
            "total_sections": len(sections),
            "elements": len(result.elements),
            "tables": result.table_count,
        },
        "sections": sections,
    }

    (out / "template_structure.json").write_text(
        json.dumps(structure, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Done. {len(sections)} sections, {result.table_count} tables -> {out}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <template> <output_dir>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
