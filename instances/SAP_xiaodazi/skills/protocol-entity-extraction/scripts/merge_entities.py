"""
实体合并与交叉验证

用法：python merge_entities.py <entities_dir> <output_path>
"""
import json, sys
from pathlib import Path
from typing import Any, Dict, List

def merge_field(existing, new, name):
    if not existing: return new
    if not new: return existing
    e_val, n_val = existing.get("value", existing), new.get("value", new)
    e_conf, n_conf = existing.get("confidence", 0.0), new.get("confidence", 0.0)
    if str(e_val).strip().lower() == str(n_val).strip().lower():
        return existing if e_conf >= n_conf else new
    return {"value": e_val, "confidence": e_conf, "conflict": True,
            "alternate": {"value": n_val, "confidence": n_conf}, "field": name}

def collect_review(entities, threshold=0.8):
    items = []
    def walk(obj, path=""):
        if isinstance(obj, dict):
            if obj.get("confidence", 1.0) < threshold:
                items.append({"path": path, "value": obj.get("value"), "confidence": obj.get("confidence")})
            if obj.get("conflict"): items.append({"path": path, "conflict": True, "alternate": obj.get("alternate")})
            for k, v in obj.items(): walk(v, f"{path}.{k}" if path else k)
        elif isinstance(obj, list):
            for i, item in enumerate(obj): walk(item, f"{path}[{i}]")
    walk(entities)
    return items

if __name__ == "__main__":
    if len(sys.argv) < 3: print(f"Usage: {sys.argv[0]} <dir> <output>"); sys.exit(1)
    d, out = Path(sys.argv[1]), Path(sys.argv[2])
    merged = {}
    for f in sorted(d.glob("*_entities_*.json")):
        for k, v in json.loads(f.read_text(encoding="utf-8")).items():
            merged[k] = merge_field(merged.get(k), v, k) if k in merged else v
    merged["needs_review_items"] = collect_review(merged)
    out.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Merged → {out} ({len(merged.get('needs_review_items',[]))} items need review)")
