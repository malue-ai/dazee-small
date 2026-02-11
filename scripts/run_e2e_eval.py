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
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

REPORTS_DIR = PROJECT_ROOT / "evaluation" / "reports"
SUITES_DIR = PROJECT_ROOT / "evaluation" / "suites" / "xiaodazi" / "e2e"

# Suite registry — add new suites here
SUITE_REGISTRY = {
    "phase1_core": SUITES_DIR / "phase1_core.yaml",
    "phase2_scenarios": SUITES_DIR / "phase2_scenarios.yaml",
    "phase3_full": SUITES_DIR / "phase3_full.yaml",
}
DEFAULT_SUITE = "phase1_core"


def get_suite_path(suite_name: str | None = None) -> Path:
    """Resolve suite name to file path."""
    name = suite_name or DEFAULT_SUITE
    if name in SUITE_REGISTRY:
        return SUITE_REGISTRY[name]
    # Allow direct path
    p = Path(name)
    if p.exists():
        return p
    p = SUITES_DIR / f"{name}.yaml"
    if p.exists():
        return p
    raise FileNotFoundError(f"Suite not found: {name} (available: {list(SUITE_REGISTRY.keys())})")


def get_checkpoint_file(suite_name: str | None = None) -> Path:
    """Each suite has its own checkpoint file — Phase1/Phase2 don't mix."""
    name = suite_name or DEFAULT_SUITE
    return REPORTS_DIR / f"_e2e_checkpoint_{name}.json"


# Legacy alias for backward compatibility
SUITE_PATH = SUITE_REGISTRY[DEFAULT_SUITE]
CHECKPOINT_FILE = get_checkpoint_file(DEFAULT_SUITE)


def load_checkpoint(checkpoint_file: Optional[Path] = None) -> dict:
    path = checkpoint_file or CHECKPOINT_FILE
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"completed_cases": [], "results": {}, "updated_at": None}


def save_checkpoint(ckpt: dict, checkpoint_file: Optional[Path] = None) -> None:
    path = checkpoint_file or CHECKPOINT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    ckpt["updated_at"] = datetime.now().isoformat()
    with open(path, "w", encoding="utf-8") as f:
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


async def _execute_inter_session_steps(
    steps: List[Dict[str, Any]],
    base_url: str,
) -> Dict[str, Any]:
    """Execute inter-session steps (wait, API calls) between multi-session turns.

    Supports:
    - wait_seconds: N  → asyncio.sleep(N)
    - api_call: "GET /api/v1/playbook?status=draft"  → HTTP GET, store response
    - api_call: "POST /api/v1/playbook/{id}/action body={...}"  → HTTP POST with path substitution

    Returns a context dict with extracted values (e.g. playbook_id) for path substitution.
    """
    import httpx
    import json as _json

    context: Dict[str, Any] = {}

    for step in steps:
        desc = step.get("description", "")

        # Wait step
        if "wait_seconds" in step:
            wait = step["wait_seconds"]
            logger.info(f"  [inter_session] wait {wait}s: {desc}")
            await asyncio.sleep(wait)
            continue

        # API call step
        api_call = step.get("api_call", "")
        if not api_call:
            continue

        # Parse: "METHOD /path" or "METHOD /path body={...}"
        parts = api_call.split(" body=", 1)
        method_path = parts[0].strip()
        body_str = parts[1].strip() if len(parts) > 1 else None

        method, path = method_path.split(" ", 1)
        method = method.upper()

        # Substitute {id} with stored playbook_id from context
        if "{id}" in path and context.get("playbook_id"):
            path = path.replace("{id}", context["playbook_id"])
        if "{extracted_id}" in path and context.get("playbook_id"):
            path = path.replace("{extracted_id}", context["playbook_id"])

        url = f"{base_url}{path}"

        # Parse body
        body = None
        if body_str:
            # Handle simplified format: {key:value,key2:value2}
            body_str = body_str.strip()
            if body_str.startswith("{") and not body_str.startswith('{"'):
                # Convert {action:approve,reviewer:e2e_test} to proper JSON
                body_str = body_str.replace("'", '"')
                # Add quotes around keys and simple values
                import re
                body_str = re.sub(r'(\w+):', r'"\1":', body_str)
                body_str = re.sub(r':(\w[\w_]*)', r':"\1"', body_str)
            try:
                body = _json.loads(body_str)
            except _json.JSONDecodeError:
                logger.warning(f"  [inter_session] invalid body: {body_str}")
                body = None

        logger.info(f"  [inter_session] {method} {path}: {desc}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if method == "GET":
                    resp = await client.get(url)
                elif method == "POST":
                    resp = await client.post(url, json=body or {})
                elif method == "DELETE":
                    resp = await client.delete(url)
                else:
                    logger.warning(f"  [inter_session] unsupported method: {method}")
                    continue

            resp_data = resp.json() if resp.status_code == 200 else {}
            logger.info(f"  [inter_session] → {resp.status_code}")

            # Extract playbook_id from list responses for path substitution
            if "playbook" in path and method == "GET":
                entries = resp_data.get("entries", [])
                if entries:
                    # Use the most recent entry
                    context["playbook_id"] = entries[0].get("id", "")
                    logger.info(f"  [inter_session] extracted playbook_id={context['playbook_id']}")

        except Exception as e:
            logger.warning(f"  [inter_session] API call failed: {e}")

    return context


async def run_multi_turn(
    sequence: List[Dict[str, Any]],
    base_url: str,
    user_id: str,
    files: Optional[List[Dict[str, Any]]] = None,
    inter_session_steps: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Run multiple turns; new_conversation=true starts a new conversation.

    Args:
        files: File refs (from resolve_files) to attach to the FIRST turn only.
        inter_session_steps: API calls to execute between sessions (e.g. approve playbook).
    """
    from evaluation.adapters.http_agent import HttpAgentAdapter
    from evaluation.models import Message, TokenUsage, ToolCall

    all_messages: List[Message] = []
    all_tool_calls: List[ToolCall] = []
    total_input, total_output, total_thinking = 0, 0, 0
    total_cache_read, total_cache_write = 0, 0
    conversation_id: Optional[str] = None
    last_conv_id: Optional[str] = None
    is_first_turn = True
    inter_steps_executed = False

    for step in sequence:
        new_conv = step.get("new_conversation", True)
        query = step.get("user_query", "")
        if not query:
            continue

        # Execute inter_session_steps between conversations (after first session ends)
        if new_conv and not is_first_turn and inter_session_steps and not inter_steps_executed:
            logger.info(f"  [inter_session] executing {len(inter_session_steps)} steps...")
            await _execute_inter_session_steps(inter_session_steps, base_url)
            inter_steps_executed = True

        # Resolve per-step files if specified
        step_files = step.get("files")
        if step_files and is_first_turn:
            # First turn uses pre-resolved files
            turn_files = files
        elif step_files and not is_first_turn:
            # Subsequent turns with files: resolve them
            turn_files = resolve_files(
                PROJECT_ROOT, step_files, base_url=base_url, user_id=user_id
            )
        else:
            turn_files = files if is_first_turn and files else None

        conv_id = None if new_conv else conversation_id
        adapter = HttpAgentAdapter(
            base_url=base_url,
            user_id=user_id,
            conversation_id=conv_id,
            poll_interval_seconds=2.0,
            poll_max_wait_seconds=600.0,  # Long tasks with thinking can take minutes per turn
        )
        # Attach files to the first turn only (subsequent turns are follow-ups)
        turn_files = files if is_first_turn and files else None
        result = await adapter.chat(user_query=query, conversation_history=[], files=turn_files)
        is_first_turn = False
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
    task_order: Optional[List[str]] = None,
    defer_grading: bool = False,
    checkpoint_file: Optional[Path] = None,
) -> Optional["TaskResult"]:
    from evaluation.adapters.http_agent import HttpAgentAdapter

    task_id = task.id
    if case_filter and task_id != case_filter:
        return None
    if from_case and task_order:
        try:
            from_idx = task_order.index(from_case)
            if task_id in task_order and task_order.index(task_id) < from_idx:
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

    # Resolve files (used by both single-turn and multi-turn)
    files_refs = resolve_files(
        PROJECT_ROOT,
        task.input.files or [],
        base_url=base_url,
        user_id=user_id,
    ) if (task.input.files) else []

    sequence = (task.metadata or {}).get("multi_turn_sequence")
    inter_steps = (task.metadata or {}).get("inter_session_steps")
    if sequence:
        result = await run_multi_turn(
            sequence,
            base_url=base_url,
            user_id=user_id,
            files=files_refs if files_refs else None,
            inter_session_steps=inter_steps,
        )
    else:
        result = await run_single_turn(
            adapter,
            user_query=task.input.user_query,
            files=files_refs if files_refs else None,
        )

    if defer_grading:
        # Save transcript only — grading happens in a separate pass
        checkpoint.setdefault("completed_cases", []).append(task_id)
        # Serialize result for later grading
        from evaluation.models import TokenUsage, ToolCall, Message
        serialized = {
            "messages": [
                m.model_dump() if hasattr(m, "model_dump") else m
                for m in (result.get("messages") or [])
            ],
            "tool_calls": [
                tc.model_dump() if hasattr(tc, "model_dump") else tc
                for tc in (result.get("tool_calls") or [])
            ],
            "token_usage": (
                result["token_usage"].model_dump()
                if hasattr(result.get("token_usage"), "model_dump")
                else result.get("token_usage")
            ),
            "metadata": result.get("metadata"),
        }
        checkpoint.setdefault("results", {})[task_id] = {
            "task_id": task.id,
            "transcript": serialized,
            "graded": False,
        }
        save_checkpoint(checkpoint, checkpoint_file)
        print(f"  [SAVED] {task_id} transcript (grading deferred)")
        return None

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
    save_checkpoint(checkpoint, checkpoint_file)
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
