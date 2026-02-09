#!/usr/bin/env python3
"""
Verify Skills load from instances/xiaodazi/config/skills.yaml.
Run from repo root: PYTHONPATH=. python scripts/verify_skills_load.py
"""
import asyncio
import sys
from pathlib import Path

# repo root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


async def main():
    from utils.instance_loader import get_instances_dir, load_instance_config
    from core.skill import create_skills_loader

    instance_name = "xiaodazi"
    config = await load_instance_config(instance_name)
    if not config:
        print("ERROR: load_instance_config returned None")
        return 1

    skills_config = config.skills_first_config
    if not skills_config:
        print("ERROR: no skills_first_config (skills.yaml not in Skills-First format?)")
        return 1

    instance_path = get_instances_dir() / instance_name
    library_dir = ROOT / "skills" / "library"
    loader = create_skills_loader(
        skills_config=skills_config,
        instance_skills_dir=instance_path / "skills",
        library_skills_dir=library_dir,
        instance_name=instance_name,
    )
    entries = await loader.load()
    available = loader.get_available_skills()
    available_names = {e.name for e in available}
    entry_by_name = {e.name: e for e in entries}

    print(f"Loaded: {len(entries)} skills total")
    print(f"Available (enabled + ready): {len(available)}")
    missing_path = [e for e in entries if e.skill_path is None and e.backend_type.value == "local"]
    if missing_path:
        print(f"WARNING: {len(missing_path)} local skills have no SKILL path:")
        for e in missing_path[:10]:
            print(f"  - {e.name} (source={getattr(e, 'skill_source', '?')})")
        if len(missing_path) > 10:
            print(f"  ... and {len(missing_path) - 10} more")
    else:
        print("OK: all local skills have resolved paths")

    # Explicit check for expected (e.g. newly added) skills
    expected_skills = ["remotion"]
    print("\nExpected skills check:")
    all_ok = True
    for name in expected_skills:
        entry = entry_by_name.get(name)
        if not entry:
            print(f"  FAIL: '{name}' not in loaded entries")
            all_ok = False
            continue
        in_available = name in available_names
        status = getattr(entry, "status", None)
        status_str = str(status) if status else "?"
        if in_available:
            print(f"  OK: {name} (loaded, available, status={status_str})")
        else:
            print(f"  WARN: {name} (loaded but not available, status={status_str})")
            all_ok = False
    if not all_ok:
        return 1
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
