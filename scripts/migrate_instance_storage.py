"""
Instance Storage Migration Script

Migrates data from the legacy global layout to the new
per-instance isolated layout.

Legacy layout:
    data/local_store/zenflux.db           → shared DB
    data/local_store/xiaodazi/mem0_vectors.db → partial isolation
    ~/.xiaodazi/MEMORY.md                 → global memory
    workspace/storage/                    → shared uploads
    workspace/playbooks/                  → shared playbooks

New layout:
    data/instances/{instance}/db/instance.db
    data/instances/{instance}/store/mem0_vectors.db
    data/instances/{instance}/memory/MEMORY.md
    data/instances/{instance}/storage/
    data/instances/{instance}/playbooks/
    data/instances/{instance}/snapshots/

Usage:
    python3 scripts/migrate_instance_storage.py [--instance xiaodazi] [--dry-run]
"""

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.app_paths import (
    get_instance_data_dir,
    get_instance_db_dir,
    get_instance_memory_dir,
    get_instance_playbooks_dir,
    get_instance_snapshots_dir,
    get_instance_storage_dir,
    get_instance_store_dir,
    get_user_data_dir,
)


def _legacy_local_store_dir() -> Path:
    """Old global SQLite directory (before instance isolation)."""
    return get_user_data_dir() / "data" / "local_store"


def _legacy_storage_dir() -> Path:
    """Old global file storage directory."""
    return get_user_data_dir() / "workspace" / "storage"


def _legacy_playbooks_dir() -> Path:
    """Old global playbooks directory."""
    return get_user_data_dir() / "workspace" / "playbooks"


def migrate(instance_name: str, dry_run: bool = False):
    """Migrate legacy global data to instance-scoped layout."""
    print(f"{'[DRY RUN] ' if dry_run else ''}Migrating to instance: {instance_name}")
    print()

    migrations = []

    # 1. Main database
    old_db = _legacy_local_store_dir() / "zenflux.db"
    new_db = get_instance_db_dir(instance_name) / "instance.db"
    if old_db.exists() and not new_db.exists():
        migrations.append(("Main DB", old_db, new_db))
    # WAL/SHM files
    for ext in ["-wal", "-shm"]:
        old_extra = old_db.parent / f"zenflux.db{ext}"
        new_extra = new_db.parent / f"instance.db{ext}"
        if old_extra.exists():
            migrations.append((f"Main DB {ext}", old_extra, new_extra))

    # 2. Mem0 vectors
    old_mem0 = _legacy_local_store_dir() / instance_name / "mem0_vectors.db"
    new_mem0 = get_instance_store_dir(instance_name) / "mem0_vectors.db"
    if old_mem0.exists() and not new_mem0.exists():
        migrations.append(("Mem0 vectors", old_mem0, new_mem0))
    # Also check the legacy global path
    old_mem0_global = _legacy_local_store_dir() / "mem0_vectors.db"
    if old_mem0_global.exists() and not new_mem0.exists() and not old_mem0.exists():
        migrations.append(("Mem0 vectors (global)", old_mem0_global, new_mem0))

    # 3. MEMORY.md and daily logs
    old_memory_dir = Path.home() / ".xiaodazi"
    new_memory_dir = get_instance_memory_dir(instance_name)

    old_memory_md = old_memory_dir / "MEMORY.md"
    new_memory_md = new_memory_dir / "MEMORY.md"
    if old_memory_md.exists() and not new_memory_md.exists():
        migrations.append(("MEMORY.md", old_memory_md, new_memory_md))

    # Daily logs
    old_logs_dir = old_memory_dir / "memory"
    if old_logs_dir.exists():
        for log_file in old_logs_dir.glob("*.md"):
            new_log = new_memory_dir / log_file.name
            if not new_log.exists():
                migrations.append((f"Daily log {log_file.name}", log_file, new_log))

    # Project memories
    old_projects = old_memory_dir / "projects"
    if old_projects.exists():
        for project_dir in old_projects.iterdir():
            if project_dir.is_dir():
                new_proj = new_memory_dir / "projects" / project_dir.name
                for f in project_dir.glob("*"):
                    new_f = new_proj / f.name
                    if not new_f.exists():
                        migrations.append(
                            (f"Project {project_dir.name}/{f.name}", f, new_f)
                        )

    # 4. Memory FTS5
    old_fts = old_memory_dir / "store" / "memory_fts.db"
    new_fts = get_instance_store_dir(instance_name) / "memory_fts.db"
    if old_fts.exists() and not new_fts.exists():
        migrations.append(("Memory FTS5", old_fts, new_fts))

    # 5. File storage
    old_storage = _legacy_storage_dir()
    new_storage = get_instance_storage_dir(instance_name)
    if old_storage.exists() and any(old_storage.iterdir()):
        for item in old_storage.iterdir():
            new_item = new_storage / item.name
            if not new_item.exists():
                migrations.append((f"Storage {item.name}", item, new_item))

    # 6. Playbooks
    old_playbooks = _legacy_playbooks_dir()
    new_playbooks = get_instance_playbooks_dir(instance_name)
    if old_playbooks.exists() and any(old_playbooks.iterdir()):
        for item in old_playbooks.iterdir():
            new_item = new_playbooks / item.name
            if not new_item.exists():
                migrations.append((f"Playbook {item.name}", item, new_item))

    # 7. Snapshots
    old_snapshots = Path.home() / ".xiaodazi" / "snapshots"
    new_snapshots = get_instance_snapshots_dir(instance_name)
    if old_snapshots.exists() and any(old_snapshots.iterdir()):
        for item in old_snapshots.iterdir():
            new_item = new_snapshots / item.name
            if not new_item.exists():
                migrations.append((f"Snapshot {item.name}", item, new_item))

    # Execute
    if not migrations:
        print("  Nothing to migrate (already migrated or no legacy data).")
        return

    print(f"  Found {len(migrations)} items to migrate:\n")
    for label, src, dst in migrations:
        print(f"  {label}")
        print(f"    FROM: {src}")
        print(f"    TO:   {dst}")
        print()

    if dry_run:
        print("[DRY RUN] No files were moved.")
        return

    moved = 0
    for label, src, dst in migrations:
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            moved += 1
            print(f"  ✅ {label}")
        except Exception as e:
            print(f"  ❌ {label}: {e}")

    print(f"\nMigration complete: {moved}/{len(migrations)} items moved.")
    print("Original files preserved (not deleted). Remove manually after verification.")


def verify(instance_name: str):
    """Verify instance storage isolation is correct."""
    print(f"\nVerifying instance storage: {instance_name}")
    print()

    checks = [
        ("Instance data dir", get_instance_data_dir(instance_name)),
        ("DB dir", get_instance_db_dir(instance_name)),
        ("Memory dir", get_instance_memory_dir(instance_name)),
        ("Store dir", get_instance_store_dir(instance_name)),
        ("Storage dir", get_instance_storage_dir(instance_name)),
        ("Playbooks dir", get_instance_playbooks_dir(instance_name)),
        ("Snapshots dir", get_instance_snapshots_dir(instance_name)),
    ]

    all_ok = True
    for label, path in checks:
        exists = path.exists()
        has_instance = instance_name in str(path)
        ok = has_instance  # Path must contain instance name
        status = "✅" if ok else "❌"
        print(f"  {status} {label}: {path} {'(exists)' if exists else '(not yet)'}")
        if not ok:
            all_ok = False

    # Check no path leaks to global
    print()
    print("  Checking for global path leaks...")
    global_paths = [
        _legacy_local_store_dir() / "zenflux.db",
        Path.home() / ".xiaodazi" / "MEMORY.md",
    ]
    for gp in global_paths:
        if gp.exists():
            print(f"  ⚠️  Legacy global file still exists: {gp}")
        else:
            print(f"  ✅ No legacy file: {gp}")

    print()
    if all_ok:
        print("All paths correctly instance-scoped.")
    else:
        print("Some paths are NOT instance-scoped!")

    return all_ok


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate instance storage")
    parser.add_argument(
        "--instance", default="xiaodazi", help="Instance name (default: xiaodazi)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without moving files"
    )
    parser.add_argument(
        "--verify-only", action="store_true", help="Only verify, don't migrate"
    )
    args = parser.parse_args()

    if args.verify_only:
        verify(args.instance)
    else:
        migrate(args.instance, dry_run=args.dry_run)
        verify(args.instance)
