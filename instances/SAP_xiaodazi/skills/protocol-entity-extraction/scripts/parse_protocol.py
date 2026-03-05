"""
Protocol 多段定向解析编排

用法：python parse_protocol.py <protocol_path> <output_dir>
"""
import asyncio, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
from utils.document_parser import get_document_parser

PASSES = [
    {"label": "synopsis", "page_range": [1, 15]},
    {"label": "design", "page_range": [30, 50]},
    {"label": "statistics", "page_range": [90, 115]},
]

async def main(protocol_path, output_dir):
    parser = get_document_parser()
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    summary = []
    for p in PASSES:
        print(f"[{p['label']}] pages {p['page_range']}...")
        result = await parser.parse(protocol_path, page_range=p["page_range"])
        (out / f"protocol_{p['label']}.md").write_text(result.markdown, encoding="utf-8")
        summary.append({"pass": p["label"], "elements": len(result.elements), "tables": result.table_count, "parser": result.parser_used})
        print(f"  → {len(result.elements)} elements, {result.table_count} tables")
    (out / "parse_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Done. {out}")

if __name__ == "__main__":
    if len(sys.argv) < 3: print(f"Usage: {sys.argv[0]} <protocol> <output_dir>"); sys.exit(1)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
