"""
SAP 模板解析编排

用法：python parse_template.py <template_path> <output_dir>
"""
import asyncio, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
from utils.document_parser import get_document_parser

async def main(template_path, output_dir):
    parser = get_document_parser()
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    result = await parser.parse(template_path, chunking=True, chunk_max_chars=4000)
    (out / "template_parsed.md").write_text(result.markdown, encoding="utf-8")
    structure = {"template_info": {"source": Path(template_path).name, "parser": result.parser_used,
        "elements": len(result.elements), "tables": result.table_count},
        "sections": [{"title": el.text.split("\n")[0].strip(), "type": el.type.value,
            "page": el.metadata.get("page_number")} for el in result.elements]}
    (out / "template_structure.json").write_text(json.dumps(structure, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Done. {len(result.elements)} elements, {result.table_count} tables → {out}")

if __name__ == "__main__":
    if len(sys.argv) < 3: print(f"Usage: {sys.argv[0]} <template> <output_dir>"); sys.exit(1)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
