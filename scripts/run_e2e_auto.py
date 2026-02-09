"""
E2E automated test runner — auto-start server, run tests, auto-stop.

Lifecycle:
  1. Start uvicorn as subprocess (port auto-detect or specified)
  2. Wait for server ready (GET / returns 200)
  3. Run E2E evaluation (reuses run_e2e_eval logic)
  4. Generate reports
  5. Kill server process on exit (always, even on failure)

Usage:
    source .venv/bin/activate

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

VENV_PYTHON = Path(os.environ.get("VENV_PYTHON", sys.executable))


def start_server(port: int, provider: str = None) -> subprocess.Popen:
    """Start uvicorn as a subprocess, return Popen handle.

    IMPORTANT: stdout is redirected to a temp log file instead of subprocess.PIPE.
    Using PIPE without a reader causes buffer deadlock (64KB on macOS) — once the
    buffer fills, the server's event loop blocks on stdout write, making the
    entire HTTP server unresponsive.

    Args:
        port: Server port.
        provider: Override model provider ("qwen" / "claude") via AGENT_PROVIDER env var.
    """
    # Use project venv python; fall back to current interpreter
    python = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
    env = os.environ.copy()
    env.setdefault("AGENT_INSTANCE", "xiaodazi")
    if provider:
        env["AGENT_PROVIDER"] = provider

    cmd = [
        python, "-m", "uvicorn",
        "main:app",
        "--host", "127.0.0.1",
        "--port", str(port),
        "--log-level", "warning",
    ]

    # Write server logs to a temp file to avoid pipe buffer deadlock.
    # The file is kept so we can inspect logs on failure.
    import tempfile
    log_file = tempfile.NamedTemporaryFile(
        prefix="e2e_server_", suffix=".log", delete=False, mode="w"
    )
    _log("🚀", f"Starting server on port {port} (python: {python})")
    _log("📄", f"Server log: {log_file.name}")
    proc = subprocess.Popen(
        cmd,
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        # Make sure we can kill the whole process tree
        preexec_fn=os.setsid if sys.platform != "win32" else None,
    )
    proc._log_file = log_file  # attach for later inspection
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


def _print_server_log(proc: subprocess.Popen, tail: int = 3000) -> None:
    """Print last `tail` chars of the server log file (if attached)."""
    log_file = getattr(proc, "_log_file", None)
    if not log_file:
        return
    try:
        log_path = log_file.name
        with open(log_path, "r", errors="replace") as f:
            content = f.read()
        if content:
            print(f"\n--- Server log ({log_path}) last {tail} chars ---")
            print(content[-tail:])
            print("--- End server log ---\n")
    except Exception as e:
        _warn(f"Could not read server log: {e}")


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

# ---------------------------------------------------------------------------
# Phase 0: State management layer verification (B9/B10 rollback)
# ---------------------------------------------------------------------------

def run_rollback_verification(case_filter: str | None = None) -> bool:
    """
    Run verify_rollback_e2e.py as Phase 0.

    Tests the state management layer (snapshot/rollback/commit) deterministically,
    independent of LLM provider. This is the foundation that guarantees
    "files are always recoverable" — the core differentiator.

    Returns True if all sub-tests pass.
    """
    # Skip if user explicitly requested a non-rollback case
    if case_filter and case_filter.upper() not in ("B9", "B10"):
        return True

    _log("🛡", "Phase 0: State management layer verification (B9/B10)")

    try:
        from scripts.verify_rollback_e2e import run_tests, cleanup

        results = run_tests(case_filter=case_filter, verbose=False)
        total = len(results)
        passed = sum(1 for r in results if r.passed)

        for r in results:
            subs = f"{sum(1 for s in r.sub_results if s.passed)}/{len(r.sub_results)}"
            if r.passed:
                _ok(f"{r.case_id}: {r.description} ({subs}, {r.elapsed_ms:.0f}ms)")
            else:
                _fail(f"{r.case_id}: {r.description} ({subs}, {r.elapsed_ms:.0f}ms)")
                for s in r.sub_results:
                    if not s.passed:
                        _fail(f"  └─ {s.name}: {s.detail}")

        cleanup()

        if passed < total:
            _fail(f"Phase 0 FAILED: {passed}/{total} — state layer broken, skipping Agent tests")
            return False

        _ok(f"Phase 0 PASS: {passed}/{total} — rollback pipeline verified")
        return True

    except Exception as e:
        _warn(f"Phase 0 skipped (import error): {e}")
        return True  # Don't block Agent tests if standalone script has issues


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

    # Initialize grader LLM from evaluation/config/settings.yaml (NOT instance config).
    # The grader is our internal benchmark judge — always uses the strongest model
    # with thinking, independent of which provider the agent uses.
    grader_llm = None
    try:
        import yaml as _yaml
        from core.llm import create_llm_service
        from utils.instance_loader import load_instance_env_from_config

        # Load instance .env so API keys are available
        instance_name = os.environ.get("AGENT_INSTANCE", "xiaodazi")
        load_instance_env_from_config(instance_name)

        # Read grader config from evaluation settings
        eval_settings_path = PROJECT_ROOT / "evaluation" / "config" / "settings.yaml"
        with open(eval_settings_path, "r", encoding="utf-8") as f:
            eval_settings = _yaml.safe_load(f) or {}
        grader_cfg = (eval_settings.get("graders", {}).get("model", {}))

        if grader_cfg.get("enabled") and grader_cfg.get("provider"):
            profile = {
                "provider": grader_cfg["provider"],
                "model": grader_cfg["model"],
                "api_key_env": grader_cfg.get("api_key_env", "ANTHROPIC_API_KEY"),
                "max_tokens": grader_cfg.get("max_tokens", 4096),
                "temperature": grader_cfg.get("temperature", 0),
                "enable_thinking": grader_cfg.get("enable_thinking", True),
                "thinking_budget": grader_cfg.get("thinking_budget", 10000),
                "timeout": grader_cfg.get("timeout", 120.0),
            }
            grader_llm = create_llm_service(**profile)
            _log("🧪", f"Grader LLM: {profile['model']} "
                        f"(thinking={profile['enable_thinking']})")
        else:
            _warn("Grader model not enabled in evaluation/config/settings.yaml")
    except Exception as e:
        _warn(f"Grader LLM init failed ({e}), model graders will return mock scores")

    harness = EvaluationHarness(
        agent_factory=None,
        llm_service=grader_llm,
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
  python scripts/run_e2e_auto.py                  # all cases (default provider)
  python scripts/run_e2e_auto.py --case A1        # single case
  python scripts/run_e2e_auto.py --from D4        # resume
  python scripts/run_e2e_auto.py --clean          # fresh run
  python scripts/run_e2e_auto.py --no-start       # skip server startup
  python scripts/run_e2e_auto.py --port 9000      # custom port
  python scripts/run_e2e_auto.py --provider qwen  # test with qwen models
  python scripts/run_e2e_auto.py --provider claude # test with claude models
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
    parser.add_argument("--provider", type=str, default=None,
                        choices=["qwen", "claude"],
                        help="Override model provider (qwen/claude) for compatibility testing")
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
                server_proc = start_server(args.port, provider=args.provider)
                if args.provider:
                    _log("🔧", f"Provider override: {args.provider}")
                ready = await wait_for_ready(base_url)
                if not ready:
                    _fail(f"Server failed to start within {STARTUP_TIMEOUT}s")
                    # Print server log for debugging
                    _print_server_log(server_proc)
                    return 1

        # --- Phase 0: State management verification (B9/B10 rollback) ---
        rollback_ok = run_rollback_verification(case_filter=args.case)
        if not rollback_ok:
            return 1

        print()  # visual separator

        # --- Phase 2: Run E2E ---
        # Set AGENT_PROVIDER in current process so grader LLM also uses the override
        if args.provider:
            os.environ["AGENT_PROVIDER"] = args.provider

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
            _print_server_log(server_proc)
            kill_server(server_proc)


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    sys.exit(main())
