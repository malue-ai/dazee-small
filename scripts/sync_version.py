"""
Version synchronization script

Reads the version from the root VERSION file (single source of truth)
and writes it to all downstream files:
  - frontend/package.json           ("version" field)
  - frontend/src-tauri/Cargo.toml   (package.version)
  - frontend/src-tauri/tauri.conf.json ("version" field)

Usage:
    python scripts/sync_version.py            # sync all
    python scripts/sync_version.py --check    # dry-run, exit 1 if out of sync
"""

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
VERSION_FILE = PROJECT_ROOT / "VERSION"

TARGETS = {
    "package.json": PROJECT_ROOT / "frontend" / "package.json",
    "Cargo.toml": PROJECT_ROOT / "frontend" / "src-tauri" / "Cargo.toml",
    "tauri.conf.json": PROJECT_ROOT / "frontend" / "src-tauri" / "tauri.conf.json",
}


def read_version() -> str:
    """Read version string from VERSION file."""
    if not VERSION_FILE.exists():
        print(f"ERROR: {VERSION_FILE} not found")
        sys.exit(1)
    version = VERSION_FILE.read_text().strip()
    if not version:
        print("ERROR: VERSION file is empty")
        sys.exit(1)
    return version


def sync_package_json(version: str, check: bool) -> bool:
    """Sync version into frontend/package.json."""
    path = TARGETS["package.json"]
    if not path.exists():
        print(f"  SKIP {path} (not found)")
        return True

    data = json.loads(path.read_text())
    current = data.get("version", "")
    if current == version:
        print(f"  OK   {path.name} ({current})")
        return True

    if check:
        print(f"  DIFF {path.name}: {current} -> {version}")
        return False

    data["version"] = version
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"  SYNC {path.name}: {current} -> {version}")
    return True


def sync_cargo_toml(version: str, check: bool) -> bool:
    """Sync version into frontend/src-tauri/Cargo.toml."""
    path = TARGETS["Cargo.toml"]
    if not path.exists():
        print(f"  SKIP {path} (not found)")
        return True

    content = path.read_text()

    # Match version = "x.y.z" in [package] section (first occurrence)
    pattern = r'^(version\s*=\s*)"[^"]+"'
    match = re.search(pattern, content, re.MULTILINE)
    if not match:
        print(f"  WARN {path.name}: version field not found")
        return True

    current = re.search(r'"([^"]+)"', match.group(0)).group(1)
    if current == version:
        print(f"  OK   {path.name} ({current})")
        return True

    if check:
        print(f"  DIFF {path.name}: {current} -> {version}")
        return False

    new_content = re.sub(pattern, f'\\1"{version}"', content, count=1, flags=re.MULTILINE)
    path.write_text(new_content)
    print(f"  SYNC {path.name}: {current} -> {version}")
    return True


def sync_tauri_conf(version: str, check: bool) -> bool:
    """Sync version into frontend/src-tauri/tauri.conf.json."""
    path = TARGETS["tauri.conf.json"]
    if not path.exists():
        print(f"  SKIP {path} (not found)")
        return True

    data = json.loads(path.read_text())
    current = data.get("version", "")
    if current == version:
        print(f"  OK   {path.name} ({current})")
        return True

    if check:
        print(f"  DIFF {path.name}: {current} -> {version}")
        return False

    data["version"] = version
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"  SYNC {path.name}: {current} -> {version}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Sync VERSION to all project files")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if versions are in sync (exit 1 if not)",
    )
    args = parser.parse_args()

    version = read_version()
    mode = "CHECK" if args.check else "SYNC"
    print(f"[{mode}] VERSION = {version}")

    all_ok = True
    all_ok &= sync_package_json(version, args.check)
    all_ok &= sync_cargo_toml(version, args.check)
    all_ok &= sync_tauri_conf(version, args.check)

    if args.check and not all_ok:
        print("\nVersions are out of sync. Run: python scripts/sync_version.py")
        sys.exit(1)
    elif not args.check:
        print("\nAll versions synchronized.")


if __name__ == "__main__":
    main()
