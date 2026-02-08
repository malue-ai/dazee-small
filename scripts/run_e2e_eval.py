"""
E2E evaluation runner: call ZenFlux HTTP API, collect transcript, run harness graders.

- Checks server (GET /health)
- Loads evaluation/suites/xiaodazi/e2e/phase1_core.yaml
- For each case: run via HttpAgentAdapter (single or multi-turn), then grade with
  EvaluationHarness graders. Supports multi-turn/multi-session via metadata.multi_turn_sequence.
- Checkpoint after each case to evaluation/reports/_e2e_checkpoint.json; resume skips completed.
- Outputs: _e2e_checkpoint.json, e2e_phase1_*.json, e2e_phase1_*.md, e2e_triage_*.md,
  e2e_regression_*.yaml on failures.

Usage:
    python scripts/run_e2e_eval.py                    # run all
    python scripts/run_e2e_eval.py --case A1         # run only A1
    python scripts/run_e2e_eval.py --from D4         # resume from D4
    python scripts/run_e2e_eval.py --check-server    # only check server
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

REPORTS_DIR = PROJECT_ROOT / "evaluation" / "reports"
CHECKPOINT_FILE = REPORTS_DIR / "_e2e_checkpoint.json"
SUITE_PATH = PROJECT_ROOT / "evaluation" / "suites" / "xiaodazi" / "e2e" / "phase1_core.yaml"


def load_checkpoint() -> dict:
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"completed_cases": [], "results": {}, "updated_at": None}


def save_checkpoint(ckpt: dict) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ckpt["updated_at"] = datetime.now().isoformat()
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(ckpt, f, ensure_ascii=False, indent=2, default=str)


async def check_server(base_url: str) -> bool:
    """GET / to check if server is running (root returns status: running)."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{base_url.rstrip('/')}/")
        return r.status_code == 200
    except Exception:
        return False


async def run_single_turn(
    adapter: "HttpAgentAdapter",
    user_query: str,
    files: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    return await adapter.chat(user_query=user_query, conversation_history=[], files=files or [])


async def run_multi_turn(
    sequence: List[Dict[str, Any]],
    base_url: str,
    user_id: str,
) -> Dict[str, Any]:
    """Run multiple turns; new_conversation=true starts a new conversation."""
    from evaluation.adapters.http_agent import HttpAgentAdapter
    from evaluation.models import Message, TokenUsage, ToolCall

    all_messages: List[Message] = []
    all_tool_calls: List[ToolCall] = []
    total_input, total_output, total_thinking = 0, 0, 0
    total_cache_read, total_cache_write = 0, 0
    conversation_id: Optional[str] = None
    last_conv_id: Optional[str] = None

    for step in sequence:
        new_conv = step.get("new_conversation", True)
        query = step.get("user_query", "")
        if not query:
            continue
        conv_id = None if new_conv else conversation_id
        adapter = HttpAgentAdapter(
            base_url=base_url,
            user_id=user_id,
            conversation_id=conv_id,
            poll_interval_seconds=2.0,
            poll_max_wait_seconds=600.0,  # Long tasks with thinking can take minutes per turn
        )
        result = await adapter.chat(user_query=query, conversation_history=[])
        conversation_id = (result.get("metadata") or {}).get("conversation_id") or conversation_id
        last_conv_id = conversation_id

        ms = result.get("messages") or []
        for m in ms:
            if isinstance(m, dict):
                all_messages.append(
                    Message(
                        role=m.get("role", "user"),
                        content=m.get("content", ""),
                        tool_calls=m.get("tool_calls") or [],
                    )
                )
            else:
                all_messages.append(m)
        for tc in result.get("tool_calls") or []:
            if isinstance(tc, ToolCall):
                all_tool_calls.append(tc)
            else:
                all_tool_calls.append(
                    ToolCall(name=tc.get("name", ""), arguments=tc.get("arguments") or {})
                )
        usage = result.get("token_usage")
        if usage:
            if isinstance(usage, TokenUsage):
                total_input += usage.input_tokens
                total_output += usage.output_tokens
                total_thinking += usage.thinking_tokens
                total_cache_read += usage.cache_read_tokens
                total_cache_write += usage.cache_write_tokens
            elif isinstance(usage, dict):
                total_input += usage.get("input_tokens", 0)
                total_output += usage.get("output_tokens", 0)
                total_thinking += usage.get("thinking_tokens", 0)
                total_cache_read += usage.get("cache_read_tokens", 0)
                total_cache_write += usage.get("cache_write_tokens", 0)

    token_usage = TokenUsage(
        input_tokens=total_input,
        output_tokens=total_output,
        thinking_tokens=total_thinking,
        cache_read_tokens=total_cache_read,
        cache_write_tokens=total_cache_write,
    )
    return {
        "messages": all_messages,
        "tool_calls": all_tool_calls,
        "token_usage": token_usage,
        "metadata": {"conversation_id": last_conv_id},
    }


def resolve_files(base_dir: Path, file_paths: List[str], base_url: str, user_id: str) -> List[Dict[str, Any]]:
    """Resolve file paths to file refs for API. Optionally upload to get file_url."""
    if not file_paths:
        return []
    import httpx
    refs = []
    for rel in file_paths:
        path = (base_dir / rel).resolve() if not Path(rel).is_absolute() else Path(rel)
        if not path.exists():
            continue
        try:
            with open(path, "rb") as f:
                content = f.read()
            # Upload and use file_url from response
            files = {"file": (path.name, content)}
            data = {"user_id": user_id}
            r = httpx.post(
                f"{base_url.rstrip('/')}/api/v1/files/upload",
                files=files,
                data=data,
                timeout=30.0,
            )
            if r.status_code == 200:
                body = r.json()
                data_obj = body.get("data") or body
                refs.append({
                    "file_url": data_obj.get("file_url"),
                    "file_name": data_obj.get("file_name", path.name),
                    "file_size": data_obj.get("file_size", len(content)),
                    "file_type": data_obj.get("file_type", "application/octet-stream"),
                })
        except Exception:
            pass
    return refs


class PreloadedAgent:
    """Agent that returns a pre-built result for harness _execute_agent."""

    def __init__(self, result: Dict[str, Any]):
        self._result = result

    async def chat(
        self,
        user_query: str,
        conversation_history: Optional[List] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        return self._result


async def run_case(
    task: "Task",
    base_url: str,
    user_id: str,
    harness: "EvaluationHarness",
    checkpoint: dict,
    case_filter: Optional[str],
    from_case: Optional[str],
) -> Optional["TaskResult"]:
    from evaluation.adapters.http_agent import HttpAgentAdapter

    task_id = task.id
    if case_filter and task_id != case_filter:
        return None
    if from_case:
        order = ["A1", "B1", "D4", "C1", "B9", "B10"]
        try:
            from_idx = order.index(from_case)
            if task_id in order and order.index(task_id) < from_idx:
                return None
        except ValueError:
            pass
    if task_id in checkpoint.get("completed_cases", []):
        print(f"  [SKIP] {task_id} (already in checkpoint)")
        return None

    adapter = HttpAgentAdapter(
        base_url=base_url,
        user_id=user_id,
        conversation_id=None,
        poll_interval_seconds=2.0,
        poll_max_wait_seconds=float(task.timeout_seconds),
    )

    sequence = (task.metadata or {}).get("multi_turn_sequence")
    if sequence:
        result = await run_multi_turn(
            sequence,
            base_url=base_url,
            user_id=user_id,
        )
    else:
        files_refs = resolve_files(
            PROJECT_ROOT,
            task.input.files or [],
            base_url=base_url,
            user_id=user_id,
        )
        result = await run_single_turn(
            adapter,
            user_query=task.input.user_query,
            files=files_refs if files_refs else None,
        )

    async def _create_preloaded_agent():
        return PreloadedAgent(result)

    harness.agent_factory = _create_preloaded_agent
    trial = await harness.run_trial(task, trial_number=1)

    from evaluation.models import TaskResult as TR
    task_result = TR(task_id=task.id, task_description=task.description, trials=[trial])

    checkpoint.setdefault("completed_cases", []).append(task_id)
    checkpoint.setdefault("results", {})[task_id] = {
        "task_id": task.id,
        "passed": trial.passed,
        "grade_results": [gr.model_dump() if hasattr(gr, "model_dump") else {} for gr in trial.grade_results],
    }
    save_checkpoint(checkpoint)
    return task_result


async def main() -> int:
    parser = argparse.ArgumentParser(description="E2E evaluation runner")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--user-id", default="eval_e2e_user", help="User ID for chat")
    parser.add_argument("--case", type=str, default=None, help="Run only this case (e.g. A1)")
    parser.add_argument("--from", dest="from_case", type=str, default=None, help="Resume from case (e.g. D4)")
    parser.add_argument("--check-server", action="store_true", help="Only check server and exit")
    args = parser.parse_args()

    if args.check_server:
        ok = await check_server(args.base_url)
        print("Server OK" if ok else "Server not reachable")
        return 0 if ok else 1

    ok = await check_server(args.base_url)
    if not ok:
        print("Server not reachable at", args.base_url)
        return 1

    from evaluation.harness import EvaluationHarness
    from evaluation.models import EvaluationReport, TaskResult

    # Initialize grader LLM from evaluation/config/settings.yaml
    grader_llm = None
    try:
        import yaml as _yaml
        from core.llm import create_llm_service
        from utils.instance_loader import load_instance_env_from_config

        instance_name = os.environ.get("AGENT_INSTANCE", "xiaodazi")
        load_instance_env_from_config(instance_name)

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
            print(f"  ✓ Grader LLM: {profile['model']} (thinking={profile['enable_thinking']})")
    except Exception as e:
        print(f"  ⚠ Grader LLM init failed ({e}), model graders will return mock scores")

    harness = EvaluationHarness(
        agent_factory=None,
        llm_service=grader_llm,
        suites_dir=str(PROJECT_ROOT / "evaluation" / "suites"),
    )
    suite = harness.load_suite(str(SUITE_PATH))
    checkpoint = load_checkpoint()

    task_results: List[TaskResult] = []
    for task in suite.tasks:
        tr = await run_case(
            task,
            args.base_url,
            args.user_id,
            harness,
            checkpoint,
            args.case,
            args.from_case,
        )
        if tr is not None:
            task_results.append(tr)

    if not task_results:
        print("No cases run (filter/checkpoint may have skipped all).")
        return 0

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
    report_path = REPORTS_DIR / f"e2e_phase1_{ts}.json"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report.model_dump(), f, ensure_ascii=False, indent=2, default=str)
    print("Report saved:", report_path)

    md_path = REPORTS_DIR / f"e2e_phase1_{ts}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# E2E Phase1 Report\n\n")
        f.write(f"- Suite: {suite.name}\n")
        f.write(f"- Pass rate: {report.pass_rate:.0%}\n")
        f.write(f"- Passed: {report.passed_tasks} / {report.total_tasks}\n\n")
        for tr in task_results:
            status = "PASS" if tr.pass_rate >= 1.0 else "FAIL"
            f.write(f"## {status} {tr.task_id}\n\n{tr.task_description}\n\n")
    print("Markdown report:", md_path)

    if report.failed_tasks > 0:
        from evaluation.loop_automation import LoopAutomation
        loop = LoopAutomation()
        classified = loop.extract_and_classify(report)
        triage_path = REPORTS_DIR / f"e2e_triage_{ts}.md"
        with open(triage_path, "w", encoding="utf-8") as f:
            f.write(loop.generate_triage_report(classified))
        print("Triage report:", triage_path)
        reg_path = PROJECT_ROOT / "evaluation" / "suites" / "xiaodazi" / f"e2e_regression_{ts}.yaml"
        loop.export_regression_suite(classified, output_file=str(reg_path))
        print("Regression suite:", reg_path)

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
