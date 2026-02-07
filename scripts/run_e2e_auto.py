"""
E2E automated test runner — auto-start server, run tests, auto-stop.

Lifecycle:
  1. Start uvicorn as subprocess (port auto-detect or specified)
  2. Wait for server ready (GET / returns 200)
  3. Run E2E evaluation (reuses run_e2e_eval logic)
  4. Generate reports
  5. Kill server process on exit (always, even on failure)

Usage:
    source /Users/liuyi/Documents/langchain/liuy/bin/activate

    # Run all E2E cases
    python scripts/run_e2e_auto.py

    # Run single case
    python scripts/run_e2e_auto.py --case A1

    # Resume from a case
    python scripts/run_e2e_auto.py --from D4

    # Custom port (default: 18234 to avoid conflict with dev server)
    python scripts/run_e2e_auto.py --port 9000

    # Skip auto-start if server already running
    python scripts/run_e2e_auto.py --no-start

    # Clean checkpoint and re-run
    python scripts/run_e2e_auto.py --clean
"""

import argparse
import asyncio
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Default port deliberately different from dev server (8000) to avoid conflict
DEFAULT_PORT = 18234
STARTUP_TIMEOUT = 120  # seconds
POLL_INTERVAL = 1.0  # seconds


# ---------------------------------------------------------------------------
# Terminal color helpers
# ---------------------------------------------------------------------------

class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def _log(icon: str, msg: str) -> None:
    print(f"{Colors.CYAN}{icon}{Colors.RESET} {msg}")


def _ok(msg: str) -> None:
    print(f"  {Colors.GREEN}✓{Colors.RESET} {msg}")


def _fail(msg: str) -> None:
    print(f"  {Colors.RED}✗{Colors.RESET} {msg}")


def _warn(msg: str) -> None:
    print(f"  {Colors.YELLOW}!{Colors.RESET} {msg}")


# ---------------------------------------------------------------------------
# Port helpers
# ---------------------------------------------------------------------------

def is_port_in_use(port: int) -> bool:
    """Check if TCP port is already listening."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------

VENV_PYTHON = Path("/Users/liuyi/Documents/langchain/liuy/bin/python3")


def start_server(port: int) -> subprocess.Popen:
    """Start uvicorn as a subprocess, return Popen handle."""
    # Use project venv python; fall back to current interpreter
    python = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
    env = os.environ.copy()
    env.setdefault("AGENT_INSTANCE", "xiaodazi")

    cmd = [
        python, "-m", "uvicorn",
        "main:app",
        "--host", "127.0.0.1",
        "--port", str(port),
        "--log-level", "warning",
    ]

    _log("🚀", f"Starting server on port {port} (python: {python})")
    proc = subprocess.Popen(
        cmd,
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        # Make sure we can kill the whole process tree
        preexec_fn=os.setsid if sys.platform != "win32" else None,
    )
    return proc


async def wait_for_ready(base_url: str, timeout: float = STARTUP_TIMEOUT) -> bool:
    """
    Poll GET / until 200 or timeout.

    Uses simple TCP check first (fast), then HTTP check for real readiness.
    """
    import httpx

    start = time.monotonic()
    port = int(base_url.rsplit(":", 1)[-1].rstrip("/"))
    phase = "tcp"

    while (time.monotonic() - start) < timeout:
        if phase == "tcp":
            if is_port_in_use(port):
                phase = "http"
            else:
                await asyncio.sleep(POLL_INTERVAL)
                continue

        # HTTP check — server fully initialized
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{base_url}/")
            if r.status_code == 200:
                elapsed = time.monotonic() - start
                _ok(f"Server ready in {elapsed:.1f}s")
                return True
        except Exception:
            pass
        await asyncio.sleep(POLL_INTERVAL)

    return False


def kill_server(proc: subprocess.Popen) -> None:
    """Gracefully stop server, escalate to SIGKILL if needed."""
    if proc.poll() is not None:
        return

    _log("🛑", "Stopping server ...")
    try:
        if sys.platform != "win32":
            # Kill the whole process group
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        else:
            proc.terminate()
    except ProcessLookupError:
        return

    try:
        proc.wait(timeout=10)
        _ok("Server stopped")
    except subprocess.TimeoutExpired:
        _warn("Server didn't stop, sending SIGKILL")
        if sys.platform != "win32":
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        else:
            proc.kill()
        proc.wait(timeout=5)


# ---------------------------------------------------------------------------
# E2E runner (delegates to run_e2e_eval logic)
# ---------------------------------------------------------------------------

async def run_e2e(
    base_url: str,
    case_filter: str | None = None,
    from_case: str | None = None,
    clean: bool = False,
) -> int:
    """Run E2E evaluation, return exit code (0=pass, 1=fail)."""
    from scripts.run_e2e_eval import (
        CHECKPOINT_FILE,
        SUITE_PATH,
        load_checkpoint,
        save_checkpoint,
        run_case,
    )
    from evaluation.harness import EvaluationHarness
    from evaluation.models import EvaluationReport, TaskResult
    from datetime import datetime
    import json

    REPORTS_DIR = PROJECT_ROOT / "evaluation" / "reports"

    # Clean checkpoint if requested
    if clean and CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        _warn("Checkpoint cleared")

    harness = EvaluationHarness(
        agent_factory=None,
        llm_service=None,
        suites_dir=str(PROJECT_ROOT / "evaluation" / "suites"),
    )
    suite = harness.load_suite(str(SUITE_PATH))
    checkpoint = load_checkpoint()

    _log("📋", f"Suite: {suite.name} ({len(suite.tasks)} cases)")
    if checkpoint.get("completed_cases"):
        _warn(f"Checkpoint found: {checkpoint['completed_cases']} already done")

    task_results: list[TaskResult] = []
    for task in suite.tasks:
        _log("▶", f"Case {task.id}: {task.description}")
        tr = await run_case(
            task,
            base_url,
            "eval_e2e_user",
            harness,
            checkpoint,
            case_filter,
            from_case,
        )
        if tr is not None:
            passed = tr.pass_rate >= 1.0
            status = f"{Colors.GREEN}PASS{Colors.RESET}" if passed else f"{Colors.RED}FAIL{Colors.RESET}"
            print(f"  [{status}] {task.id}: {task.description}")
            task_results.append(tr)

    if not task_results:
        _warn("No cases run (filter/checkpoint may have skipped all)")
        return 0

    # Build report
    report = EvaluationReport(
        report_id=f"e2e_phase1_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        suite_id=suite.id,
        suite_name=suite.name,
        task_results=task_results,
        total_tasks=len(task_results),
        passed_tasks=sum(1 for tr in task_results if tr.pass_rate >= 1.0),
        failed_tasks=sum(1 for tr in task_results if tr.pass_rate < 1.0),
        unstable_tasks=0,
        total_duration_seconds=0.0,
    )

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # JSON report
    report_path = REPORTS_DIR / f"e2e_phase1_{ts}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report.model_dump(), f, ensure_ascii=False, indent=2, default=str)

    # Markdown report
    md_path = REPORTS_DIR / f"e2e_phase1_{ts}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# E2E Phase1 Report\n\n")
        f.write(f"- Suite: {suite.name}\n")
        f.write(f"- Pass rate: {report.pass_rate:.0%}\n")
        f.write(f"- Passed: {report.passed_tasks} / {report.total_tasks}\n\n")
        for tr in task_results:
            status_str = "PASS" if tr.pass_rate >= 1.0 else "FAIL"
            f.write(f"## {status_str} {tr.task_id}\n\n{tr.task_description}\n\n")

    # Triage + regression suite on failures
    if report.failed_tasks > 0:
        from evaluation.loop_automation import LoopAutomation
        loop = LoopAutomation()
        classified = loop.extract_and_classify(report)
        triage_path = REPORTS_DIR / f"e2e_triage_{ts}.md"
        with open(triage_path, "w", encoding="utf-8") as f:
            f.write(loop.generate_triage_report(classified))
        reg_path = (
            PROJECT_ROOT / "evaluation" / "suites" / "xiaodazi" / f"e2e_regression_{ts}.yaml"
        )
        loop.export_regression_suite(classified, output_file=str(reg_path))

    # Final summary
    print()
    print("=" * 60)
    _log("📊", f"Pass rate: {report.pass_rate:.0%} "
         f"({report.passed_tasks}/{report.total_tasks})")
    _log("📄", f"Report: {report_path.relative_to(PROJECT_ROOT)}")
    _log("📝", f"Markdown: {md_path.relative_to(PROJECT_ROOT)}")
    if report.failed_tasks > 0:
        _fail(f"{report.failed_tasks} case(s) FAILED")
    else:
        _ok("ALL CASES PASSED")
    print("=" * 60)

    return 0 if report.failed_tasks == 0 else 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="E2E automated test — auto-start server, run tests, auto-stop",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/run_e2e_auto.py                  # all cases
  python scripts/run_e2e_auto.py --case A1        # single case
  python scripts/run_e2e_auto.py --from D4        # resume
  python scripts/run_e2e_auto.py --clean          # fresh run
  python scripts/run_e2e_auto.py --no-start       # skip server startup
  python scripts/run_e2e_auto.py --port 9000      # custom port
""",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"Server port (default: {DEFAULT_PORT})")
    parser.add_argument("--case", type=str, default=None,
                        help="Run only this case (e.g. A1)")
    parser.add_argument("--from", dest="from_case", type=str, default=None,
                        help="Resume from this case (e.g. D4)")
    parser.add_argument("--clean", action="store_true",
                        help="Clear checkpoint and re-run all")
    parser.add_argument("--no-start", action="store_true",
                        help="Skip auto-start, assume server already running")
    return parser.parse_args()


async def async_main() -> int:
    args = parse_args()
    base_url = f"http://127.0.0.1:{args.port}"
    server_proc = None

    print()
    print(f"{Colors.BOLD}{'=' * 60}{Colors.RESET}")
    print(f"{Colors.BOLD}  E2E AUTOMATED TEST{Colors.RESET}")
    print(f"{Colors.BOLD}{'=' * 60}{Colors.RESET}")
    print()

    try:
        # --- Phase 1: Server lifecycle ---
        if args.no_start:
            _log("⏭", "Skipping auto-start (--no-start)")
            if not is_port_in_use(args.port):
                _fail(f"Port {args.port} not in use, server not running")
                return 1
            _ok(f"Server detected on port {args.port}")
        else:
            if is_port_in_use(args.port):
                _warn(f"Port {args.port} already in use, reusing existing server")
            else:
                server_proc = start_server(args.port)
                ready = await wait_for_ready(base_url)
                if not ready:
                    _fail(f"Server failed to start within {STARTUP_TIMEOUT}s")
                    # Print server stdout for debugging
                    if server_proc and server_proc.stdout:
                        output = server_proc.stdout.read()
                        if output:
                            print("\n--- Server output ---")
                            print(output.decode("utf-8", errors="replace")[-2000:])
                            print("--- End server output ---\n")
                    return 1

        # --- Phase 2: Run E2E ---
        exit_code = await run_e2e(
            base_url=base_url,
            case_filter=args.case,
            from_case=args.from_case,
            clean=args.clean,
        )
        return exit_code

    except KeyboardInterrupt:
        _warn("Interrupted by user")
        return 130

    except Exception as e:
        _fail(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        # --- Phase 3: Cleanup ---
        if server_proc is not None:
            kill_server(server_proc)


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    sys.exit(main())
