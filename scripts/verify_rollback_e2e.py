"""
B9 / B10 文件修改回滚 — 端到端验证脚本

验证小搭子最核心的差异化能力：文件修改过程中遇到异常或用户中止时，
所有已修改文件自动恢复到修改前的内容。

测试矩阵（6 个子场景）：

  B9.1 — 多文件修改中途异常 → 自动回滚（核心场景）
  B9.2 — 快照磁盘持久化 → 进程崩溃后恢复
  B9.3 — 动态文件捕获 → 未预先声明的文件也能回滚
  B10.1 — 用户中止 → 全部回滚
  B10.2 — 用户中止 → 选择性回滚（仅回滚部分文件）
  B10.3 — 用户中止 → 保留已完成（不回滚，清理快照）

Usage:
    source .venv/bin/activate
    python scripts/verify_rollback_e2e.py           # 运行全部
    python scripts/verify_rollback_e2e.py --case B9  # 仅 B9
    python scripts/verify_rollback_e2e.py --case B10 # 仅 B10
    python scripts/verify_rollback_e2e.py -v         # 详细输出
"""

import argparse
import json
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Source data (committed to git, never modified)
SOURCE_DATA = PROJECT_ROOT / "docs" / "benchmark" / "data" / "rollback_test"

# Working copy (temp dir, safe to modify)
WORK_DIR = PROJECT_ROOT / "docs" / "benchmark" / "data" / "_rollback_work"

# Snapshot storage (mimic real config)
SNAPSHOT_DIR = WORK_DIR / ".snapshots"


# ─────────────────────────────────────────────────────────────────────
# Terminal helpers
# ─────────────────────────────────────────────────────────────────────

class C:
    G = "\033[92m"
    R = "\033[91m"
    Y = "\033[93m"
    B = "\033[1m"
    D = "\033[2m"
    N = "\033[0m"


def _ok(msg: str) -> None:
    print(f"  {C.G}✓{C.N} {msg}")


def _fail(msg: str) -> None:
    print(f"  {C.R}✗{C.N} {msg}")


def _info(msg: str) -> None:
    print(f"  {C.D}·{C.N} {msg}")


# ─────────────────────────────────────────────────────────────────────
# Test result model
# ─────────────────────────────────────────────────────────────────────

@dataclass
class SubResult:
    name: str
    passed: bool
    detail: str = ""
    elapsed_ms: float = 0.0


@dataclass
class CaseResult:
    case_id: str
    description: str
    passed: bool
    sub_results: List[SubResult] = field(default_factory=list)
    elapsed_ms: float = 0.0


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _prepare_work_dir() -> None:
    """Copy source data to a working directory (safe to modify)."""
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    shutil.copytree(SOURCE_DATA, WORK_DIR)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _files_identical(path: Path, original_content: str) -> bool:
    """Byte-level comparison: current file content === original."""
    return _read(path) == original_content


def _make_manager():
    """Create a fresh StateConsistencyManager pointed at WORK_DIR."""
    from core.state.consistency_manager import (
        StateConsistencyConfig,
        StateConsistencyManager,
        SnapshotConfig,
        RollbackConfig,
    )

    config = StateConsistencyConfig(
        enabled=True,
        snapshot=SnapshotConfig(
            storage_path=str(SNAPSHOT_DIR),
            retention_hours=1,
            capture_cwd=False,
            capture_clipboard=False,
            capture_files=True,
        ),
        rollback=RollbackConfig(
            auto_rollback_on_consecutive_failures=2,
            auto_rollback_on_critical_error=True,
            rollback_timeout_seconds=30,
        ),
    )
    return StateConsistencyManager(config)


# ─────────────────────────────────────────────────────────────────────
# B9.1 — Multi-file modification error → auto rollback
# ─────────────────────────────────────────────────────────────────────

def test_b9_1_error_auto_rollback(verbose: bool = False) -> SubResult:
    """
    Scenario:
      1. Snapshot 3 files (config.json, nginx.conf, README.md)
      2. Modify config.json (port 3000 → 8080) — success
      3. Attempt to modify nginx.conf — simulate error
      4. Rollback should restore config.json to original
      5. Verify: all 3 files === original content
    """
    _prepare_work_dir()
    mgr = _make_manager()
    task_id = "b9_test_task"

    cfg_path = str(WORK_DIR / "config.json")
    nginx_path = str(WORK_DIR / "nginx.conf")
    readme_path = str(WORK_DIR / "README.md")
    affected = [cfg_path, nginx_path, readme_path]

    # Save originals for comparison
    originals = {p: _read(Path(p)) for p in affected}

    # 1. Create snapshot
    snapshot_id = mgr.create_snapshot(task_id, affected)
    if verbose:
        _info(f"Snapshot created: {snapshot_id}")

    # 2. Modify config.json (simulate successful tool execution)
    from core.state.operation_log import create_file_write_record

    new_cfg = originals[cfg_path].replace('"port": 3000', '"port": 8080')
    record = create_file_write_record(cfg_path, originals[cfg_path], new_cfg)
    mgr.record_operation(task_id, record)
    _write(Path(cfg_path), new_cfg)

    if verbose:
        _info(f"config.json modified: port 3000 → 8080")

    # 3. Simulate error on nginx.conf modification
    # (In real scenario, ErrorClassifier would classify this and trigger rollback)

    # 4. Trigger rollback (simulating auto_rollback_if_needed)
    rollback_msgs = mgr.rollback(snapshot_id)
    if verbose:
        for m in rollback_msgs:
            _info(f"Rollback: {m}")

    # 5. Verify all files restored
    checks = []
    for p in affected:
        match = _files_identical(Path(p), originals[p])
        fname = Path(p).name
        checks.append((fname, match))
        if verbose:
            status = "✓ restored" if match else "✗ MISMATCH"
            _info(f"  {fname}: {status}")

    all_pass = all(ok for _, ok in checks)
    failed = [n for n, ok in checks if not ok]
    detail = "all files restored" if all_pass else f"MISMATCH: {failed}"
    return SubResult("B9.1 error_auto_rollback", all_pass, detail)


# ─────────────────────────────────────────────────────────────────────
# B9.2 — Snapshot disk persistence → crash recovery
# ─────────────────────────────────────────────────────────────────────

def test_b9_2_crash_recovery(verbose: bool = False) -> SubResult:
    """
    Scenario:
      1. Create snapshot + modify file + persist to disk
      2. Destroy manager instance (simulate process crash)
      3. Create NEW manager, load snapshot from disk
      4. Rollback using disk-persisted snapshot
      5. Verify: file restored
    """
    _prepare_work_dir()
    mgr1 = _make_manager()
    task_id = "b9_crash_task"

    cfg_path = str(WORK_DIR / "config.json")
    original = _read(Path(cfg_path))

    # 1. Snapshot + modify
    snapshot_id = mgr1.create_snapshot(task_id, [cfg_path])
    new_content = original.replace('"port": 3000', '"port": 9999')
    _write(Path(cfg_path), new_content)

    if verbose:
        _info(f"Snapshot {snapshot_id} persisted, file modified, destroying manager")

    # 2. Destroy manager (simulate crash — no commit, no rollback)
    del mgr1

    # Verify file is still modified
    assert _read(Path(cfg_path)) == new_content, "File should still be modified"

    # 3. New manager — recover from disk
    mgr2 = _make_manager()

    # 4. Rollback using persisted snapshot
    rollback_msgs = mgr2.rollback(snapshot_id)
    if verbose:
        for m in rollback_msgs:
            _info(f"Recovery rollback: {m}")

    # 5. Verify restored
    restored = _files_identical(Path(cfg_path), original)
    detail = "crash recovery OK" if restored else "file NOT restored after crash recovery"
    return SubResult("B9.2 crash_recovery", restored, detail)


# ─────────────────────────────────────────────────────────────────────
# B9.3 — Dynamic file capture (lazy snapshot)
# ─────────────────────────────────────────────────────────────────────

def test_b9_3_dynamic_capture(verbose: bool = False) -> SubResult:
    """
    Scenario:
      1. Snapshot with empty affected_files (Agent doesn't know upfront)
      2. Before modifying a file, call ensure_file_captured() (lazy capture)
      3. Modify the file
      4. Rollback
      5. Verify: dynamically captured file is also restored
    """
    _prepare_work_dir()
    mgr = _make_manager()
    task_id = "b9_dynamic_task"

    readme_path = str(WORK_DIR / "README.md")
    original = _read(Path(readme_path))

    # 1. Create snapshot with EMPTY affected_files
    snapshot_id = mgr.create_snapshot(task_id, affected_files=[])

    # 2. Dynamically capture before modification
    captured = mgr.ensure_file_captured(task_id, readme_path)
    if verbose:
        _info(f"Dynamic capture: {captured}")

    # 3. Modify
    _write(Path(readme_path), original.replace("端口 3000", "端口 8080"))

    # 4. Rollback
    mgr.rollback(snapshot_id)

    # 5. Verify
    restored = _files_identical(Path(readme_path), original)
    detail = "dynamic capture + rollback OK" if restored else "dynamic capture NOT restored"
    return SubResult("B9.3 dynamic_capture", restored, detail)


# ─────────────────────────────────────────────────────────────────────
# B10.1 — User abort → rollback all
# ─────────────────────────────────────────────────────────────────────

def test_b10_1_user_abort_rollback_all(verbose: bool = False) -> SubResult:
    """
    Scenario:
      1. Snapshot 5 docs files
      2. Modify 2 files (replace "北极星科技" → "星辰大海科技")
      3. User says "算了，恢复原样"
      4. Rollback ALL
      5. Verify: all 5 files === original (no traces of modification)
    """
    _prepare_work_dir()
    mgr = _make_manager()
    task_id = "b10_abort_task"

    docs_dir = WORK_DIR / "docs"
    doc_files = sorted(docs_dir.glob("*.md"))
    paths = [str(f) for f in doc_files]

    originals = {p: _read(Path(p)) for p in paths}

    # 1. Snapshot
    snapshot_id = mgr.create_snapshot(task_id, paths)

    # 2. Modify first 2 files
    from core.state.operation_log import create_file_write_record

    modified_count = 0
    for p in paths[:2]:
        old = originals[p]
        new = old.replace("北极星科技", "星辰大海科技")
        record = create_file_write_record(p, old, new)
        mgr.record_operation(task_id, record)
        _write(Path(p), new)
        modified_count += 1
        if verbose:
            _info(f"Modified: {Path(p).name}")

    # Verify they're actually modified
    for p in paths[:2]:
        assert "星辰大海科技" in _read(Path(p)), f"{p} should contain new name"

    # 3. User abort → rollback all
    rollback_msgs = mgr.rollback(snapshot_id)
    if verbose:
        for m in rollback_msgs:
            _info(f"Rollback: {m}")

    # 4. Verify ALL files restored
    checks = []
    for p in paths:
        match = _files_identical(Path(p), originals[p])
        checks.append((Path(p).name, match))

    all_pass = all(ok for _, ok in checks)
    failed = [n for n, ok in checks if not ok]
    detail = f"all {len(paths)} files restored" if all_pass else f"MISMATCH: {failed}"
    return SubResult("B10.1 user_abort_rollback_all", all_pass, detail)


# ─────────────────────────────────────────────────────────────────────
# B10.2 — User abort → selective rollback (only some files)
# ─────────────────────────────────────────────────────────────────────

def test_b10_2_selective_rollback(verbose: bool = False) -> SubResult:
    """
    Scenario:
      1. Snapshot 5 docs files
      2. Modify 2 files (about.md, product.md)
      3. User chooses selective rollback: only restore about.md
      4. Verify: about.md === original, product.md still modified
    """
    _prepare_work_dir()
    mgr = _make_manager()
    task_id = "b10_selective_task"

    docs_dir = WORK_DIR / "docs"
    about_path = str(docs_dir / "about.md")
    product_path = str(docs_dir / "product.md")
    paths = [about_path, product_path]

    originals = {p: _read(Path(p)) for p in paths}

    # 1. Snapshot
    snapshot_id = mgr.create_snapshot(task_id, paths)

    # 2. Modify both
    from core.state.operation_log import create_file_write_record

    for p in paths:
        old = originals[p]
        new = old.replace("北极星科技", "星辰大海科技")
        record = create_file_write_record(p, old, new)
        mgr.record_operation(task_id, record)
        _write(Path(p), new)

    # 3. Selective rollback: only restore about.md using OperationLog
    #    (simulate user selecting specific files from rollback_options)
    log = mgr._task_logs.get(task_id)
    if log:
        # Find the record for about.md and rollback only that one
        for record in log._records:
            if record.target == about_path and record.rollback_action:
                record.rollback_action()
                if verbose:
                    _info(f"Selective rollback: {Path(about_path).name}")
                break

    # 4. Verify
    about_restored = _files_identical(Path(about_path), originals[about_path])
    product_still_modified = "星辰大海科技" in _read(Path(product_path))

    passed = about_restored and product_still_modified
    detail = (
        f"about.md={'restored' if about_restored else 'NOT restored'}, "
        f"product.md={'still modified' if product_still_modified else 'WRONGLY restored'}"
    )
    return SubResult("B10.2 selective_rollback", passed, detail)


# ─────────────────────────────────────────────────────────────────────
# B10.3 — User abort → keep completed (no rollback, just commit)
# ─────────────────────────────────────────────────────────────────────

def test_b10_3_keep_completed(verbose: bool = False) -> SubResult:
    """
    Scenario:
      1. Snapshot 5 docs files
      2. Modify 2 files
      3. User chooses "保留已完成" → commit (no rollback)
      4. Verify: modified files stay modified, snapshot cleaned up
    """
    _prepare_work_dir()
    mgr = _make_manager()
    task_id = "b10_keep_task"

    docs_dir = WORK_DIR / "docs"
    about_path = str(docs_dir / "about.md")
    product_path = str(docs_dir / "product.md")
    paths = [about_path, product_path]

    originals = {p: _read(Path(p)) for p in paths}

    # 1. Snapshot
    snapshot_id = mgr.create_snapshot(task_id, paths)

    # 2. Modify both
    from core.state.operation_log import create_file_write_record

    for p in paths:
        old = originals[p]
        new = old.replace("北极星科技", "星辰大海科技")
        record = create_file_write_record(p, old, new)
        mgr.record_operation(task_id, record)
        _write(Path(p), new)

    # 3. User chooses "keep completed" → commit
    mgr.commit(task_id)
    if verbose:
        _info("User chose 'keep completed' → committed")

    # 4. Verify: files stay modified + snapshot cleaned
    about_modified = "星辰大海科技" in _read(Path(about_path))
    product_modified = "星辰大海科技" in _read(Path(product_path))
    snapshot_gone = snapshot_id not in mgr._snapshots
    log_gone = task_id not in mgr._task_logs

    passed = all([about_modified, product_modified, snapshot_gone, log_gone])
    detail = (
        f"files_modified={about_modified and product_modified}, "
        f"snapshot_cleaned={snapshot_gone}, log_cleaned={log_gone}"
    )
    return SubResult("B10.3 keep_completed", passed, detail)


# ─────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────

ALL_TESTS = {
    "B9": [
        ("B9.1", test_b9_1_error_auto_rollback),
        ("B9.2", test_b9_2_crash_recovery),
        ("B9.3", test_b9_3_dynamic_capture),
    ],
    "B10": [
        ("B10.1", test_b10_1_user_abort_rollback_all),
        ("B10.2", test_b10_2_selective_rollback),
        ("B10.3", test_b10_3_keep_completed),
    ],
}


def run_tests(
    case_filter: Optional[str] = None,
    verbose: bool = False,
) -> List[CaseResult]:
    results: List[CaseResult] = []

    for case_id, tests in ALL_TESTS.items():
        if case_filter and case_filter.upper() != case_id:
            continue

        desc = {
            "B9": "文件修改异常退出自动回滚",
            "B10": "文件修改用户中止选择性回滚",
        }[case_id]

        print(f"\n{C.B}▶ {case_id}: {desc}{C.N}")
        case_start = time.monotonic()

        sub_results: List[SubResult] = []
        for test_id, test_fn in tests:
            t0 = time.monotonic()
            try:
                sr = test_fn(verbose=verbose)
                sr.elapsed_ms = (time.monotonic() - t0) * 1000
            except Exception as e:
                sr = SubResult(
                    test_id, False,
                    f"Exception: {type(e).__name__}: {e}",
                    (time.monotonic() - t0) * 1000,
                )
            sub_results.append(sr)

            if sr.passed:
                _ok(f"{sr.name}: {sr.detail} ({sr.elapsed_ms:.0f}ms)")
            else:
                _fail(f"{sr.name}: {sr.detail} ({sr.elapsed_ms:.0f}ms)")

        case_pass = all(s.passed for s in sub_results)
        case_elapsed = (time.monotonic() - case_start) * 1000
        results.append(CaseResult(
            case_id=case_id,
            description=desc,
            passed=case_pass,
            sub_results=sub_results,
            elapsed_ms=case_elapsed,
        ))

    return results


def print_summary(results: List[CaseResult]) -> int:
    print(f"\n{'=' * 60}")
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed

    for r in results:
        status = f"{C.G}PASS{C.N}" if r.passed else f"{C.R}FAIL{C.N}"
        subs = f"{sum(1 for s in r.sub_results if s.passed)}/{len(r.sub_results)}"
        print(f"  [{status}] {r.case_id}: {r.description} ({subs} sub-tests, {r.elapsed_ms:.0f}ms)")

    print(f"\n  Total: {passed}/{total} cases passed", end="")
    if failed > 0:
        print(f" ({C.R}{failed} FAILED{C.N})")
    else:
        print(f" ({C.G}ALL PASS{C.N})")
    print(f"{'=' * 60}")

    return 0 if failed == 0 else 1


def save_report(results: List[CaseResult]) -> Path:
    """Save JSON report to evaluation/reports/."""
    reports_dir = PROJECT_ROOT / "evaluation" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    ts = time.strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir / f"rollback_e2e_{ts}.json"

    report = {
        "suite": "B9_B10_rollback",
        "timestamp": ts,
        "results": [
            {
                "case_id": r.case_id,
                "description": r.description,
                "passed": r.passed,
                "elapsed_ms": r.elapsed_ms,
                "sub_results": [
                    {
                        "name": s.name,
                        "passed": s.passed,
                        "detail": s.detail,
                        "elapsed_ms": s.elapsed_ms,
                    }
                    for s in r.sub_results
                ],
            }
            for r in results
        ],
        "summary": {
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
        },
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"  Report: {report_path.relative_to(PROJECT_ROOT)}")
    return report_path


def cleanup() -> None:
    """Remove working directory."""
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="B9/B10 文件修改回滚 — 端到端验证",
    )
    parser.add_argument("--case", type=str, default=None,
                        choices=["B9", "B10", "b9", "b10"],
                        help="Run only B9 or B10")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Verbose output")
    parser.add_argument("--keep-work", action="store_true",
                        help="Keep working directory after test")
    args = parser.parse_args()

    print(f"\n{C.B}{'=' * 60}{C.N}")
    print(f"{C.B}  B9/B10 文件修改回滚 — E2E 验证{C.N}")
    print(f"{C.B}{'=' * 60}{C.N}")

    try:
        results = run_tests(
            case_filter=args.case,
            verbose=args.verbose,
        )
        save_report(results)
        exit_code = print_summary(results)
    finally:
        if not args.keep_work:
            cleanup()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
