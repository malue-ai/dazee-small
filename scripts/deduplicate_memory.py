"""
Deduplicate MEMORY.md — one-shot cleanup script.

Reads the current MEMORY.md, merges duplicate entries within each section,
removes low-quality noise (transient instructions, excessive emotion logs),
and rewrites the file in-place.

Usage:
    python scripts/deduplicate_memory.py [--instance xiaodazi] [--dry-run]
"""

import argparse
import asyncio
import os
import re
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Tuple

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _normalize(text: str) -> str:
    """Normalize entry text for dedup comparison (lowercase, collapse spaces)."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _is_noise(content: str) -> bool:
    """Return True for entries that should be removed entirely."""
    noise_patterns = [
        re.compile(r"这.*文件.*保持一致", re.I),
        re.compile(r"请直接修改", re.I),
        re.compile(r"给我恢复", re.I),
        re.compile(r"帮我.*吧$", re.I),
        re.compile(r"^（.*）$"),  # template placeholder
    ]
    return any(p.search(content) for p in noise_patterns)


def _cap_emotion_entries(entries: List[str], max_per_signal: int = 2) -> List[str]:
    """Limit duplicate emotion entries (e.g. 'frustrated' x10 -> keep 2)."""
    emotion_pattern = re.compile(r"^情绪状态:\s*(.+)$", re.I)
    emotion_counts: Dict[str, int] = {}
    result: List[str] = []

    for entry in entries:
        m = emotion_pattern.match(entry)
        if m:
            signal = m.group(1).strip().lower()
            emotion_counts[signal] = emotion_counts.get(signal, 0) + 1
            if emotion_counts[signal] > max_per_signal:
                continue  # drop excess
        result.append(entry)

    return result


def deduplicate_entries(entries: List[str]) -> List[str]:
    """Deduplicate a list of entry strings, preserving order."""
    seen: OrderedDict[str, str] = OrderedDict()
    for entry in entries:
        key = _normalize(entry)
        if key not in seen:
            seen[key] = entry  # keep first occurrence (original casing)
    return list(seen.values())


def process_memory_text(text: str) -> Tuple[str, Dict[str, int]]:
    """
    Process full MEMORY.md text: deduplicate and clean.

    Returns:
        (cleaned_text, stats) where stats has before/after counts.
    """
    lines = text.split("\n")
    result_lines: List[str] = []
    current_section = ""
    section_entries: List[str] = []
    total_before = 0
    total_after = 0

    def flush_section():
        nonlocal total_before, total_after
        if not section_entries:
            return

        total_before += len(section_entries)

        # 1. Remove noise
        cleaned = [e for e in section_entries if not _is_noise(e)]

        # 2. Deduplicate
        cleaned = deduplicate_entries(cleaned)

        # 3. Cap emotion entries
        cleaned = _cap_emotion_entries(cleaned)

        total_after += len(cleaned)

        for entry in cleaned:
            result_lines.append(f"- {entry}")

    for line in lines:
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            # Flush previous section entries
            flush_section()
            section_entries = []
            current_section = heading_match.group(2).strip()
            result_lines.append(line)
            continue

        # List item
        item_match = re.match(r"^\s*[-*]\s+(.+)$", line)
        if item_match and current_section:
            section_entries.append(item_match.group(1).strip())
            continue

        # Non-list content (blank lines, blockquotes, etc.)
        flush_section()
        section_entries = []
        result_lines.append(line)

    # Flush any remaining entries
    flush_section()

    stats = {
        "entries_before": total_before,
        "entries_after": total_after,
        "removed": total_before - total_after,
    }

    return "\n".join(result_lines), stats


async def main(instance_name: str, dry_run: bool = False) -> None:
    """Run deduplication on an instance's MEMORY.md."""
    from utils.app_paths import get_instance_memory_dir

    memory_dir = get_instance_memory_dir(instance_name)
    memory_file = memory_dir / "MEMORY.md"

    if not memory_file.exists():
        print(f"MEMORY.md not found at {memory_file}")
        return

    import aiofiles

    async with aiofiles.open(memory_file, "r", encoding="utf-8") as f:
        original = await f.read()

    cleaned, stats = process_memory_text(original)

    print(f"Instance: {instance_name}")
    print(f"File:     {memory_file}")
    print(f"Before:   {stats['entries_before']} entries")
    print(f"After:    {stats['entries_after']} entries")
    print(f"Removed:  {stats['removed']} entries")

    if dry_run:
        print("\n[DRY RUN] No changes written.")
        print("\n--- Preview (first 2000 chars) ---")
        print(cleaned[:2000])
        return

    if stats["removed"] == 0:
        print("Nothing to deduplicate.")
        return

    # Back up original
    backup_path = memory_file.with_suffix(".md.bak")
    async with aiofiles.open(backup_path, "w", encoding="utf-8") as f:
        await f.write(original)
    print(f"Backup:   {backup_path}")

    # Write cleaned version
    async with aiofiles.open(memory_file, "w", encoding="utf-8") as f:
        await f.write(cleaned)
    print("Done. MEMORY.md has been deduplicated.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deduplicate MEMORY.md")
    parser.add_argument(
        "--instance",
        default=os.getenv("AGENT_INSTANCE", "xiaodazi"),
        help="Instance name (default: AGENT_INSTANCE env or 'xiaodazi')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing",
    )
    args = parser.parse_args()
    asyncio.run(main(args.instance, args.dry_run))
