"""
SAP 人工审核清单生成

扫描 chapters/*.md，汇总 [AI-INFERRED] 和 [PLACEHOLDER] 标记。
用法：python generate_checklist.py <chapters_dir> <output_path>
"""
import re, sys
from pathlib import Path

def main(chapters_dir, output_path):
    chapters = Path(chapters_dir)
    ai_items, placeholders = [], []
    for md in sorted(chapters.glob("*.md")):
        if md.name.startswith("_"): continue
        content, section = md.read_text(encoding="utf-8"), md.stem
        for m in re.finditer(r"\[AI-INFERRED\]", content):
            ctx = content[max(0,m.start()-60):min(len(content),m.end()+60)].strip().replace("\n"," ")
            ai_items.append({"section": section, "context": ctx[:80]})
        for m in re.finditer(r"\[PLACEHOLDER[^\]]*\]", content):
            placeholders.append({"section": section, "marker": m.group()})
    lines = ["# SAP 人工审核清单\n", "## AI 推断内容\n", "| # | 章节 | 上下文 | 状态 |", "|---|------|--------|------|"]
    for i, it in enumerate(ai_items, 1): lines.append(f"| {i} | {it['section']} | {it['context']} | [ ] |")
    lines += ["\n## 待人工填写\n", "| # | 章节 | 标记 |", "|---|------|------|"]
    for i, it in enumerate(placeholders, 1): lines.append(f"| {i} | {it['section']} | {it['marker']} |")
    Path(output_path).write_text("\n".join(lines), encoding="utf-8")
    print(f"Checklist: {len(ai_items)} AI-inferred, {len(placeholders)} placeholders → {output_path}")

if __name__ == "__main__":
    if len(sys.argv) < 3: print(f"Usage: {sys.argv[0]} <chapters_dir> <output>"); sys.exit(1)
    main(sys.argv[1], sys.argv[2])
