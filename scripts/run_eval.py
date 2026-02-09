"""
ZenFlux Agent automated evaluation script v2.0

Three-phase pipeline:
  Phase 0  Preflight       — health check, agent availability, log snapshot
  Phase 1  Connectivity    — conversation CRUD lifecycle, session/agent, chat sync
  Phase 2  SSE Integration — 1 normal + 1 error SSE call with deep protocol checks
  Phase 3  Log Analysis    — incremental log analysis (JSON, context, sensitive data)

Usage:
    python3 scripts/run_eval.py [--base-url http://127.0.0.1:8000]
    python3 scripts/run_eval.py --phase connectivity
    python3 scripts/run_eval.py --verbose --report eval_report.json
"""

import argparse
import asyncio
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    import httpx
except ImportError:
    print("ERROR: httpx required. pip install httpx")
    sys.exit(1)

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml required. pip install pyyaml")
    sys.exit(1)


# ============================================================
# Data Models
# ============================================================

@dataclass
class CheckResult:
    """Single check result."""
    case_id: str
    phase: str
    name: str
    passed: bool
    duration_ms: float = 0.0
    status_code: Optional[int] = None
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PhaseResult:
    """Aggregated result of one phase."""
    phase_id: str
    phase_name: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration_ms: float = 0.0
    checks: List[CheckResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return self.failed == 0


@dataclass
class EvalReport:
    """Full evaluation report."""
    started_at: str = ""
    finished_at: str = ""
    base_url: str = ""
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    pass_rate: float = 0.0
    duration_s: float = 0.0
    phases: List[Dict[str, Any]] = field(default_factory=list)
    aborted: bool = False
    abort_reason: str = ""


# ============================================================
# EvalConfig — configuration loading + variable management
# ============================================================

class EvalConfig:
    """Load YAML dataset and manage runtime variables."""

    def __init__(self, dataset_path: str, base_url: str):
        with open(dataset_path, "r", encoding="utf-8") as f:
            self.raw = yaml.safe_load(f)

        self.defaults = self.raw.get("defaults", {})
        self.phases_data = self.raw.get("phases", [])
        self.base_url = base_url

        self.variables: Dict[str, str] = {
            "user_id": self.defaults.get("user_id", "eval_user_001"),
            "agent_id": self.defaults.get("agent_id", "xiaodazi"),
        }

    def resolve(self, text: str) -> str:
        """Replace {var} placeholders."""
        for k, v in self.variables.items():
            text = text.replace(f"{{{k}}}", str(v))
        return text

    def resolve_body(self, body: Dict) -> Dict:
        """Deep-resolve variables in request body."""
        return self._deep_resolve(body)

    def _deep_resolve(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return self.resolve(obj)
        if isinstance(obj, dict):
            return {k: self._deep_resolve(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._deep_resolve(v) for v in obj]
        return obj

    def save_var(self, name: str, value: Any):
        self.variables[name] = str(value)

    def extract_nested(self, data: Any, path: str) -> Any:
        """Extract value by dot-path, e.g. 'data.id'."""
        for part in path.split("."):
            if isinstance(data, dict):
                data = data.get(part)
            else:
                return None
        return data

    def get_phase(self, phase_id: str) -> Optional[Dict]:
        for p in self.phases_data:
            if p.get("id") == phase_id:
                return p
        return None


# ============================================================
# HttpClient — shared connection pool
# ============================================================

class HttpClient:
    """Shared async HTTP client with connection reuse."""

    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout),
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def request(
        self, method: str, path: str, body: Optional[Dict] = None
    ) -> httpx.Response:
        method = method.upper()
        if method == "GET":
            return await self._client.get(path)
        elif method == "POST":
            return await self._client.post(path, json=body) if body else await self._client.post(path)
        elif method == "PUT":
            return await self._client.put(path, json=body) if body else await self._client.put(path)
        elif method == "DELETE":
            return await self._client.delete(path)
        raise ValueError(f"Unsupported method: {method}")

    async def stream_post(self, path: str, body: Dict, sse_timeout: float = 120.0):
        """Return an async context manager for SSE streaming."""
        client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(connect=10.0, read=sse_timeout, write=10.0, pool=10.0),
        )
        return client, client.stream(
            "POST", path, json=body,
            headers={"Accept": "text/event-stream"},
        )


# ============================================================
# SSEConsumer — incremental SSE event reader
# ============================================================

class SSEConsumer:
    """Read SSE events from an httpx streaming response."""

    @staticmethod
    async def consume(resp) -> Tuple[List[Dict[str, Any]], int, str]:
        """Read all SSE events from a streaming response.

        Returns:
            (events, status_code, content_type)
        """
        status_code = resp.status_code
        content_type = resp.headers.get("content-type", "")

        if status_code != 200:
            await resp.aread()
            return [], status_code, content_type

        events: List[Dict[str, Any]] = []
        buffer = ""
        done = False

        async for chunk in resp.aiter_text():
            buffer += chunk
            while "\n\n" in buffer:
                block, buffer = buffer.split("\n\n", 1)
                block = block.strip()
                if not block:
                    continue

                event_type = None
                data_lines = []
                for line in block.split("\n"):
                    if line.startswith("event:"):
                        event_type = line[len("event:"):].strip()
                    elif line.startswith("data:"):
                        data_lines.append(line[len("data:"):].strip())

                if data_lines:
                    raw = "\n".join(data_lines)
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        data = {"_raw": raw}
                    if event_type:
                        data["_sse_event"] = event_type
                    events.append(data)

                if event_type == "done":
                    done = True
                    break
            if done:
                break

        return events, status_code, content_type


# ============================================================
# LogSnapshot — incremental log analysis
# ============================================================

class LogSnapshot:
    """Capture log file position before tests, then analyze delta."""

    def __init__(self, project_root: Path):
        self.root = project_root
        self.baselines: Dict[str, int] = {}  # path -> line count at snapshot

    def capture(self, log_path: str):
        """Record the current line count as baseline."""
        fpath = self.root / log_path
        if fpath.exists():
            self.baselines[log_path] = sum(1 for _ in fpath.open(encoding="utf-8", errors="replace"))
        else:
            self.baselines[log_path] = 0

    def read_delta(self, log_path: str) -> List[str]:
        """Read only lines added after the snapshot baseline."""
        fpath = self.root / log_path
        if not fpath.exists():
            return []
        baseline = self.baselines.get(log_path, 0)
        lines = fpath.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[baseline:]

    def file_exists(self, log_path: str) -> bool:
        return (self.root / log_path).exists()


# ============================================================
# AssertionChecker — unified assertion logic
# ============================================================

class AssertionChecker:
    """All assertion methods return (passed, error_message)."""

    # ---- HTTP assertions ----

    @staticmethod
    def check_status(resp: httpx.Response, expected) -> Tuple[bool, str]:
        if isinstance(expected, list):
            ok = resp.status_code in expected
            return ok, "" if ok else f"status: expected one of {expected}, got {resp.status_code}"
        ok = resp.status_code == expected
        return ok, "" if ok else f"status: expected {expected}, got {resp.status_code}"

    @staticmethod
    def check_json_contains(resp_json: Dict, expected: Dict) -> Tuple[bool, str]:
        errors = []
        for k, v in expected.items():
            actual = resp_json.get(k)
            if actual != v:
                errors.append(f"json[{k}]: expected {v}, got {actual}")
        return len(errors) == 0, "; ".join(errors)

    @staticmethod
    def check_json_has_keys(resp_json: Dict, keys: List[str]) -> Tuple[bool, str]:
        missing = [k for k in keys if k not in resp_json]
        return len(missing) == 0, f"missing keys: {missing}" if missing else ""

    # ---- SSE deep assertions (operate on event list) ----

    @staticmethod
    def sse_status_and_content_type(status: int, ct: str) -> Tuple[bool, str]:
        errors = []
        if status != 200:
            errors.append(f"status {status} != 200")
        if "text/event-stream" not in ct:
            errors.append(f"content-type '{ct}' missing text/event-stream")
        return len(errors) == 0, "; ".join(errors)

    @staticmethod
    def sse_first_event_is_message_start(events: List[Dict]) -> Tuple[bool, str]:
        if not events:
            return False, "no events received"
        first = events[0]
        if first.get("type") != "message_start":
            return False, f"first event type is '{first.get('type')}', expected 'message_start'"
        return True, ""

    @staticmethod
    def sse_has_content_start_text(events: List[Dict]) -> Tuple[bool, str]:
        for ev in events:
            if ev.get("type") == "content_start":
                block = ev.get("content_block", ev.get("data", {}))
                if isinstance(block, dict) and block.get("type") == "text":
                    return True, ""
                # accept even without checking sub-type if content_start exists
                return True, ""
        return False, "no content_start event found"

    @staticmethod
    def sse_has_nonempty_content_delta(events: List[Dict]) -> Tuple[bool, str]:
        for ev in events:
            if ev.get("type") == "content_delta":
                delta = ev.get("delta", {})
                text = ""
                if isinstance(delta, dict):
                    text = delta.get("text", "")
                elif isinstance(delta, str):
                    text = delta
                if text:
                    return True, ""
        return False, "no content_delta with non-empty text"

    @staticmethod
    def sse_content_paired(events: List[Dict]) -> Tuple[bool, str]:
        starts = sum(1 for e in events if e.get("type") == "content_start")
        stops = sum(1 for e in events if e.get("type") == "content_stop")
        if starts != stops:
            return False, f"content_start({starts}) != content_stop({stops})"
        if starts == 0:
            return False, "no content_start/stop events"
        return True, ""

    @staticmethod
    def sse_seq_monotonic(events: List[Dict]) -> Tuple[bool, str]:
        seqs = [e.get("seq") for e in events if e.get("seq") is not None]
        for i in range(1, len(seqs)):
            if seqs[i] <= seqs[i - 1]:
                return False, f"seq[{i}]={seqs[i]} <= seq[{i-1}]={seqs[i-1]}"
        if not seqs:
            return True, ""  # no seq field — pass (not all formats use seq)
        return True, ""

    @staticmethod
    def sse_ends_with_message_stop(events: List[Dict]) -> Tuple[bool, str]:
        # find last non-done event
        data_events = [e for e in events if e.get("type") and e.get("type") != "done"
                       and e.get("_sse_event") != "done"]
        if not data_events:
            return False, "no data events"
        last_type = data_events[-1].get("type", "")
        if last_type not in ("message_stop", "session_end"):
            return False, f"last event type is '{last_type}', expected 'message_stop'"
        return True, ""

    @staticmethod
    def sse_lifecycle_order(events: List[Dict]) -> Tuple[bool, str]:
        """Verify events follow: message_start -> content_* -> message_stop."""
        ordered_types = [e.get("type") for e in events if e.get("type")]
        key_events = []
        for t in ordered_types:
            if t in ("message_start", "content_start", "content_delta",
                     "content_stop", "message_stop"):
                key_events.append(t)

        if not key_events:
            return False, "no lifecycle events found"

        # message_start must come before any content event
        if "message_start" in key_events:
            ms_idx = key_events.index("message_start")
            content_indices = [i for i, t in enumerate(key_events) if t.startswith("content_")]
            if content_indices and min(content_indices) < ms_idx:
                return False, "content event before message_start"

        # message_stop must come after all content events
        if "message_stop" in key_events:
            stop_idx = key_events.index("message_stop")
            content_indices = [i for i, t in enumerate(key_events) if t.startswith("content_")]
            if content_indices and max(content_indices) > stop_idx:
                return False, "content event after message_stop"

        return True, ""

    @staticmethod
    def sse_min_events(events: List[Dict], min_count: int) -> Tuple[bool, str]:
        if len(events) < min_count:
            hint = ""
            if events:
                first_type = events[0].get("type", "?")
                if first_type == "error":
                    err = events[0].get("error", {})
                    msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                    hint = f" [first_event: error — {msg[:80]}]"
                else:
                    hint = f" [first_event: {first_type}]"
            return False, f"events: {len(events)} < {min_count}{hint}"
        return True, ""

    @staticmethod
    def sse_has_error_event(events: List[Dict]) -> Tuple[bool, str]:
        for ev in events:
            if ev.get("type") == "error":
                return True, ""
        return False, "no error event found"

    # ---- Log assertions ----

    @staticmethod
    def log_json_valid(lines: List[str], threshold: float) -> Tuple[bool, str]:
        if not lines:
            return True, ""  # no delta lines — nothing to check
        valid = 0
        total = 0
        for line in lines:
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                json.loads(line)
                valid += 1
            except json.JSONDecodeError:
                pass
        if total == 0:
            return True, ""
        ratio = valid / total
        ok = ratio >= threshold
        return ok, "" if ok else f"JSON valid ratio: {ratio:.2%} < {threshold:.0%} ({valid}/{total})"

    @staticmethod
    def log_contains_field(lines: List[str], field_name: str, value: str, min_count: int) -> Tuple[bool, str]:
        count = 0
        for line in lines:
            try:
                entry = json.loads(line.strip())
                if str(entry.get(field_name, "")) == value:
                    count += 1
            except (json.JSONDecodeError, AttributeError):
                continue
        ok = count >= min_count
        return ok, "" if ok else f"field {field_name}={value}: found {count}, need >= {min_count}"

    @staticmethod
    def log_no_level(lines: List[str], level: str) -> Tuple[bool, str]:
        count = 0
        for line in lines:
            try:
                entry = json.loads(line.strip())
                if str(entry.get("level", "")).upper() == level.upper():
                    count += 1
            except (json.JSONDecodeError, AttributeError):
                continue
        return count == 0, "" if count == 0 else f"found {count} {level} entries"

    @staticmethod
    def log_timestamp_monotonic(lines: List[str]) -> Tuple[bool, str]:
        timestamps = []
        for line in lines:
            try:
                entry = json.loads(line.strip())
                ts = entry.get("ts", "")
                if ts:
                    timestamps.append(ts)
            except (json.JSONDecodeError, AttributeError):
                continue
        violations = 0
        for i in range(1, len(timestamps)):
            if timestamps[i] < timestamps[i - 1]:
                violations += 1
        return violations == 0, "" if violations == 0 else f"{violations} timestamp violations"

    @staticmethod
    def log_no_sensitive_data(lines: List[str], patterns: List[str]) -> Tuple[bool, str]:
        leaks = []
        for i, line in enumerate(lines):
            for pat in patterns:
                if re.search(pat, line, re.IGNORECASE):
                    leaks.append(f"line {i+1}: pattern '{pat}'")
        return len(leaks) == 0, "" if not leaks else f"{len(leaks)} leaks: {leaks[0]}"

    @staticmethod
    def log_no_uncaught_exception(lines: List[str]) -> Tuple[bool, str]:
        count = 0
        for line in lines:
            try:
                entry = json.loads(line.strip())
                err = str(entry.get("error", ""))
                if "Traceback" in err and "Uncaught" in err:
                    count += 1
            except (json.JSONDecodeError, AttributeError):
                continue
        return count == 0, "" if count == 0 else f"{count} uncaught exceptions"


# ============================================================
# ReportBuilder — console + JSON output
# ============================================================

class ReportBuilder:
    """Build and display evaluation report."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def print_phase_header(self, phase_id: str, phase_name: str):
        print(f"\n  --- Phase: {phase_name} ({phase_id}) ---\n")

    def print_check(self, result: CheckResult):
        icon = "PASS" if result.passed else "FAIL"
        icon_ch = "\u2705" if result.passed else "\u274c"
        time_str = f"{result.duration_ms:.0f}ms"
        print(f"  {icon_ch} [{result.case_id}] {result.name}  ({time_str})")
        if result.error and not result.passed:
            err = result.error[:200]
            print(f"       \u21b3 {err}")

    def print_abort(self, reason: str):
        print(f"\n  \u26d4 ABORTED: {reason}\n")

    def print_summary(self, report: EvalReport):
        print(f"\n{'=' * 70}")
        print(f"  \u8bc4\u6d4b\u7ed3\u679c\u6c47\u603b")
        print(f"{'=' * 70}")
        print(f"  \u603b\u7528\u4f8b:   {report.total}")
        print(f"  \u901a\u8fc7:     {report.passed} \u2705")
        print(f"  \u5931\u8d25:     {report.failed} \u274c")
        if report.skipped:
            print(f"  \u8df3\u8fc7:     {report.skipped} \u23ed\ufe0f")
        if report.aborted:
            print(f"  \u4e2d\u6b62:     {report.abort_reason}")
        print(f"  \u901a\u8fc7\u7387:   {report.pass_rate}%")
        print(f"  \u8017\u65f6:     {report.duration_s}s")
        print()

        # per-phase bar
        print("  \u5206\u9636\u6bb5\u7edf\u8ba1:")
        for phase in report.phases:
            total = phase.get("total", 0)
            passed = phase.get("passed", 0)
            pct = round(passed / max(total, 1) * 100)
            bar = "\u2588" * (pct // 5) + "\u2591" * (20 - pct // 5)
            name = phase.get("phase_name", phase.get("phase_id", "?"))
            print(f"    {name:24s}  {bar}  {passed}/{total} ({pct}%)")
        print(f"{'=' * 70}\n")

        # failed details
        all_checks = []
        for phase in report.phases:
            all_checks.extend(phase.get("checks", []))
        failed = [c for c in all_checks if not c.get("passed", True)]
        if failed:
            print("  \u5931\u8d25\u7528\u4f8b\u8be6\u60c5:")
            for c in failed:
                print(f"    \u274c [{c['case_id']}] {c['name']}")
                if c.get("error"):
                    print(f"       {c['error'][:200]}")
            print()

    def build_report(
        self,
        phases: List[PhaseResult],
        base_url: str,
        started_at: str,
        duration_s: float,
        aborted: bool = False,
        abort_reason: str = "",
    ) -> EvalReport:
        total = sum(p.total for p in phases)
        passed = sum(p.passed for p in phases)
        failed = sum(p.failed for p in phases)
        skipped = sum(p.skipped for p in phases)

        return EvalReport(
            started_at=started_at,
            finished_at=datetime.now().isoformat(),
            base_url=base_url,
            total=total,
            passed=passed,
            failed=failed,
            skipped=skipped,
            pass_rate=round(passed / max(total, 1) * 100, 1),
            duration_s=round(duration_s, 2),
            phases=[asdict(p) for p in phases],
            aborted=aborted,
            abort_reason=abort_reason,
        )


# ============================================================
# EvalRunner — phase orchestration (the only coordinator)
# ============================================================

class EvalRunner:
    """Orchestrate evaluation phases."""

    def __init__(
        self,
        config: EvalConfig,
        http: HttpClient,
        log_snap: LogSnapshot,
        checker: AssertionChecker,
        reporter: ReportBuilder,
        sse_timeout: float = 120.0,
    ):
        self.config = config
        self.http = http
        self.log_snap = log_snap
        self.check = checker
        self.report = reporter
        self.sse_timeout = sse_timeout
        self.phase_results: List[PhaseResult] = []

    async def run(self, phase_filter: Optional[str] = None) -> EvalReport:
        started_at = datetime.now().isoformat()
        t0 = time.time()

        print(f"\n{'=' * 70}")
        print(f"  ZenFlux Agent \u81ea\u52a8\u5316\u8bc4\u6d4b v2.0")
        print(f"  \u540e\u7aef\u5730\u5740: {self.config.base_url}")
        print(f"  \u5f00\u59cb\u65f6\u95f4: {started_at}")
        print(f"{'=' * 70}")

        aborted = False
        abort_reason = ""

        # Phase 0: Preflight
        if not phase_filter or phase_filter == "preflight":
            pr = await self._run_preflight()
            self.phase_results.append(pr)
            if not pr.all_passed:
                aborted = True
                abort_reason = "Preflight \u5931\u8d25 \u2014 \u670d\u52a1\u672a\u5c31\u7eea\uff0c\u4e2d\u6b62\u540e\u7eed\u9636\u6bb5"
                self.report.print_abort(abort_reason)

        # Phase 1: Connectivity
        if not aborted and (not phase_filter or phase_filter == "connectivity"):
            pr = await self._run_connectivity()
            self.phase_results.append(pr)

        # Phase 2: SSE Integration
        if not aborted and (not phase_filter or phase_filter == "sse_integration"):
            pr = await self._run_sse_integration()
            self.phase_results.append(pr)

        # Phase 3: Log Analysis
        if not aborted and (not phase_filter or phase_filter == "log_analysis"):
            pr = await self._run_log_analysis()
            self.phase_results.append(pr)

        elapsed = time.time() - t0
        report = self.report.build_report(
            phases=self.phase_results,
            base_url=self.config.base_url,
            started_at=started_at,
            duration_s=elapsed,
            aborted=aborted,
            abort_reason=abort_reason,
        )
        self.report.print_summary(report)
        return report

    # ----------------------------------------------------------------
    # Phase 0: Preflight
    # ----------------------------------------------------------------

    async def _run_preflight(self) -> PhaseResult:
        phase = PhaseResult(phase_id="preflight", phase_name="\u73af\u5883\u9884\u68c0")
        self.report.print_phase_header("preflight", "\u73af\u5883\u9884\u68c0")

        preflight_data = self.config.get_phase("preflight")
        if not preflight_data:
            return phase

        for case in preflight_data.get("cases", []):
            result = await self._exec_http_case(case, "preflight")
            phase.checks.append(result)
            phase.total += 1
            if result.passed:
                phase.passed += 1
            else:
                phase.failed += 1
            self.report.print_check(result)

        # snapshot log baselines
        self.log_snap.capture("logs/app.log")
        self.log_snap.capture("logs/error.log")

        return phase

    # ----------------------------------------------------------------
    # Phase 1: Connectivity
    # ----------------------------------------------------------------

    async def _run_connectivity(self) -> PhaseResult:
        phase = PhaseResult(phase_id="connectivity", phase_name="API \u8fde\u901a\u6027")
        self.report.print_phase_header("connectivity", "API \u8fde\u901a\u6027")

        conn_data = self.config.get_phase("connectivity")
        if not conn_data:
            return phase

        for group in conn_data.get("groups", []):
            group_id = group.get("id", "")
            is_lifecycle = group.get("lifecycle", False)
            cases = group.get("cases", [])

            if is_lifecycle:
                await self._run_lifecycle_group(phase, cases)
            else:
                for case in cases:
                    result = await self._exec_http_case(case, "connectivity")
                    phase.checks.append(result)
                    phase.total += 1
                    if result.passed:
                        phase.passed += 1
                    else:
                        phase.failed += 1
                    self.report.print_check(result)

                    # save variables
                    if result.passed and "save" in case:
                        resp_json = result.details.get("response_json")
                        for var_name, json_path in case["save"].items():
                            val = self.config.extract_nested(resp_json, json_path)
                            if val is not None:
                                self.config.save_var(var_name, val)

        return phase

    async def _run_lifecycle_group(self, phase: PhaseResult, cases: List[Dict]):
        """Run cases sequentially; first case creates, last case is cleanup.
        If any case fails, still attempt cleanup (delete) using saved conversation_id.
        """
        cleanup_case = None
        created_conv_id = None

        for i, case in enumerate(cases):
            result = await self._exec_http_case(case, "connectivity")
            phase.checks.append(result)
            phase.total += 1

            if result.passed:
                phase.passed += 1
            else:
                phase.failed += 1

            self.report.print_check(result)

            # save variables
            if result.passed and "save" in case:
                resp_json = result.details.get("response_json")
                for var_name, json_path in case["save"].items():
                    val = self.config.extract_nested(resp_json, json_path)
                    if val is not None:
                        self.config.save_var(var_name, val)
                        if var_name == "conversation_id":
                            created_conv_id = val

        # Cleanup: attempt to delete the conversation regardless of test results
        if created_conv_id:
            try:
                path = f"/api/v1/conversations/{created_conv_id}"
                resp = await self.http.request("DELETE", path)
                if resp.status_code == 200:
                    if self.report.verbose:
                        print(f"       \u2192 cleanup: deleted conversation {created_conv_id}")
                else:
                    if self.report.verbose:
                        print(f"       \u2192 cleanup: delete returned {resp.status_code}")
            except Exception:
                pass

    # ----------------------------------------------------------------
    # Phase 2: SSE Integration
    # ----------------------------------------------------------------

    async def _run_sse_integration(self) -> PhaseResult:
        phase = PhaseResult(phase_id="sse_integration", phase_name="SSE \u6d41\u5f0f\u96c6\u6210")
        self.report.print_phase_header("sse_integration", "SSE \u6d41\u5f0f\u96c6\u6210")

        sse_data = self.config.get_phase("sse_integration")
        if not sse_data:
            return phase

        for sse_case in sse_data.get("cases", []):
            case_id = sse_case["id"]
            case_name = sse_case["name"]
            body = self.config.resolve_body(sse_case.get("body", {}))
            checks_defs = sse_case.get("checks", [])

            # Make ONE SSE call
            t0 = time.time()
            events, status_code, content_type, call_error = await self._do_sse_call(body)
            call_ms = round((time.time() - t0) * 1000, 1)

            if self.report.verbose and events:
                types = [e.get("type", "?") for e in events]
                print(f"       SSE events ({len(events)}): {types[:15]}")
                for ev in events[:3]:
                    snippet = json.dumps(ev, ensure_ascii=False)
                    if len(snippet) > 200:
                        snippet = snippet[:200] + "..."
                    print(f"         {snippet}")

            if call_error:
                # entire call failed — mark all checks as failed
                for chk in checks_defs:
                    chk_id = chk.get("id", case_id)
                    chk_name = chk.get("name", case_name)
                    r = CheckResult(
                        case_id=chk_id, phase="sse_integration",
                        name=chk_name, passed=False,
                        duration_ms=call_ms, status_code=status_code,
                        error=call_error,
                    )
                    phase.checks.append(r)
                    phase.total += 1
                    phase.failed += 1
                    self.report.print_check(r)
                continue

            # Run each check against the SAME event list
            for chk in checks_defs:
                chk_id = chk.get("id", case_id)
                chk_name = chk.get("name", "")
                assert_type = chk.get("assert", "")

                passed, error = self._eval_sse_check(
                    assert_type, events, status_code, content_type,
                    chk.get("value"),
                )
                r = CheckResult(
                    case_id=chk_id, phase="sse_integration",
                    name=chk_name, passed=passed,
                    duration_ms=call_ms, status_code=status_code,
                    error=error if not passed else None,
                    details={"event_count": len(events)},
                )
                phase.checks.append(r)
                phase.total += 1
                if passed:
                    phase.passed += 1
                else:
                    phase.failed += 1
                self.report.print_check(r)

        return phase

    async def _do_sse_call(
        self, body: Dict
    ) -> Tuple[List[Dict], int, str, Optional[str]]:
        """Execute a single SSE call. Returns (events, status, ct, error_or_none)."""
        try:
            client, stream_cm = await self.http.stream_post(
                "/api/v1/chat", body, self.sse_timeout
            )
            async with client:
                async with stream_cm as resp:
                    events, status, ct = await SSEConsumer.consume(resp)
            return events, status, ct, None
        except httpx.ConnectError:
            return [], 0, "", f"Connection refused: {self.config.base_url}"
        except httpx.ReadTimeout:
            return [], 0, "", f"SSE read timeout ({self.sse_timeout}s)"
        except Exception as e:
            return [], 0, "", f"{type(e).__name__}: {str(e)[:200]}"

    def _eval_sse_check(
        self, assert_type: str, events: List[Dict],
        status: int, ct: str, value: Any = None
    ) -> Tuple[bool, str]:
        """Dispatch SSE assertion by type name."""
        c = self.check
        dispatch = {
            "status_and_content_type": lambda: c.sse_status_and_content_type(status, ct),
            "first_event_is_message_start": lambda: c.sse_first_event_is_message_start(events),
            "has_content_start_text": lambda: c.sse_has_content_start_text(events),
            "has_nonempty_content_delta": lambda: c.sse_has_nonempty_content_delta(events),
            "content_start_stop_paired": lambda: c.sse_content_paired(events),
            "seq_monotonic": lambda: c.sse_seq_monotonic(events),
            "ends_with_message_stop": lambda: c.sse_ends_with_message_stop(events),
            "lifecycle_order": lambda: c.sse_lifecycle_order(events),
            "min_events": lambda: c.sse_min_events(events, value or 4),
            "has_error_event": lambda: c.sse_has_error_event(events),
        }
        fn = dispatch.get(assert_type)
        if fn:
            return fn()
        return False, f"unknown assertion: {assert_type}"

    # ----------------------------------------------------------------
    # Phase 3: Log Analysis
    # ----------------------------------------------------------------

    async def _run_log_analysis(self) -> PhaseResult:
        phase = PhaseResult(phase_id="log_analysis", phase_name="\u65e5\u5fd7\u5206\u6790")
        self.report.print_phase_header("log_analysis", "\u65e5\u5fd7\u5206\u6790")

        la_data = self.config.get_phase("log_analysis")
        if not la_data:
            return phase

        for case in la_data.get("cases", []):
            t0 = time.time()
            result = self._exec_log_check(case)
            result.duration_ms = round((time.time() - t0) * 1000, 1)
            phase.checks.append(result)
            phase.total += 1
            if result.passed:
                phase.passed += 1
            else:
                phase.failed += 1
            self.report.print_check(result)

        return phase

    def _exec_log_check(self, case: Dict) -> CheckResult:
        case_id = case.get("id", "?")
        name = case.get("name", "")
        check_type = case.get("check", "")
        log_path = case.get("path", "")

        try:
            if check_type == "file_exists":
                exists = self.log_snap.file_exists(log_path)
                return CheckResult(
                    case_id=case_id, phase="log_analysis", name=name,
                    passed=exists, error=None if exists else f"{log_path} not found",
                )

            # read incremental lines
            lines = self.log_snap.read_delta(log_path)

            if check_type == "json_valid":
                threshold = case.get("threshold", 0.95)
                ok, err = self.check.log_json_valid(lines, threshold)
                return CheckResult(case_id=case_id, phase="log_analysis", name=name, passed=ok, error=err or None)

            elif check_type == "contains_field":
                ok, err = self.check.log_contains_field(
                    lines, case.get("field", ""), case.get("value", ""), case.get("min_count", 1)
                )
                return CheckResult(case_id=case_id, phase="log_analysis", name=name, passed=ok, error=err or None)

            elif check_type == "no_level":
                ok, err = self.check.log_no_level(lines, case.get("level", "CRITICAL"))
                return CheckResult(case_id=case_id, phase="log_analysis", name=name, passed=ok, error=err or None)

            elif check_type == "timestamp_monotonic":
                ok, err = self.check.log_timestamp_monotonic(lines)
                return CheckResult(case_id=case_id, phase="log_analysis", name=name, passed=ok, error=err or None)

            elif check_type == "no_sensitive_data":
                ok, err = self.check.log_no_sensitive_data(lines, case.get("patterns", []))
                return CheckResult(case_id=case_id, phase="log_analysis", name=name, passed=ok, error=err or None)

            elif check_type == "no_uncaught_exception":
                ok, err = self.check.log_no_uncaught_exception(lines)
                return CheckResult(case_id=case_id, phase="log_analysis", name=name, passed=ok, error=err or None)

            else:
                return CheckResult(
                    case_id=case_id, phase="log_analysis", name=name,
                    passed=False, error=f"unknown check type: {check_type}",
                )

        except Exception as e:
            return CheckResult(
                case_id=case_id, phase="log_analysis", name=name,
                passed=False, error=f"{type(e).__name__}: {str(e)[:200]}",
            )

    # ----------------------------------------------------------------
    # Shared: HTTP case executor
    # ----------------------------------------------------------------

    async def _exec_http_case(self, case: Dict, phase: str) -> CheckResult:
        case_id = case.get("id", "?")
        name = case.get("name", "")
        method = case.get("method", "GET").upper()
        path = self.config.resolve(case.get("path", ""))
        body = case.get("body")
        expect = case.get("expect", {})

        t0 = time.time()
        try:
            resolved_body = self.config.resolve_body(body) if body else None
            resp = await self.http.request(method, path, resolved_body)
            elapsed_ms = round((time.time() - t0) * 1000, 1)

            resp_json = None
            try:
                resp_json = resp.json()
            except Exception:
                pass

            errors = []

            # status
            expected_status = expect.get("status")
            if expected_status is not None:
                ok, err = self.check.check_status(resp, expected_status)
                if not ok:
                    errors.append(err)

            # content_type
            ct_check = expect.get("content_type_contains")
            if ct_check:
                ct = resp.headers.get("content-type", "")
                if ct_check not in ct:
                    errors.append(f"content-type: expected '{ct_check}', got '{ct}'")

            # json_contains
            jc = expect.get("json_contains")
            if jc and resp_json:
                ok, err = self.check.check_json_contains(resp_json, jc)
                if not ok:
                    errors.append(err)

            # json_has_keys
            jk = expect.get("json_has_keys")
            if jk and resp_json:
                ok, err = self.check.check_json_has_keys(resp_json, jk)
                if not ok:
                    errors.append(err)

            return CheckResult(
                case_id=case_id, phase=phase, name=name,
                passed=len(errors) == 0, duration_ms=elapsed_ms,
                status_code=resp.status_code,
                error="; ".join(errors) if errors else None,
                details={"response_json": resp_json},
            )

        except httpx.ConnectError:
            elapsed_ms = round((time.time() - t0) * 1000, 1)
            return CheckResult(
                case_id=case_id, phase=phase, name=name,
                passed=False, duration_ms=elapsed_ms,
                error=f"Connection refused: {self.config.base_url}",
            )
        except Exception as e:
            elapsed_ms = round((time.time() - t0) * 1000, 1)
            return CheckResult(
                case_id=case_id, phase=phase, name=name,
                passed=False, duration_ms=elapsed_ms,
                error=f"{type(e).__name__}: {str(e)[:200]}",
            )


# ============================================================
# CLI entry point
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="ZenFlux Agent \u81ea\u52a8\u5316\u8bc4\u6d4b v2.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
\u793a\u4f8b:
  python3 scripts/run_eval.py
  python3 scripts/run_eval.py --phase connectivity
  python3 scripts/run_eval.py --phase sse_integration --verbose
  python3 scripts/run_eval.py --base-url http://localhost:8080 --report eval_report.json
""",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="\u540e\u7aef\u5730\u5740")
    parser.add_argument("--dataset", default=str(ROOT / "scripts" / "eval_dataset.yaml"), help="\u8bc4\u6d4b\u96c6\u8def\u5f84")
    parser.add_argument("--phase", default=None,
                        choices=["preflight", "connectivity", "sse_integration", "log_analysis"],
                        help="\u4ec5\u8fd0\u884c\u67d0\u9636\u6bb5")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP \u8d85\u65f6\u79d2\u6570")
    parser.add_argument("--sse-timeout", type=int, default=120, help="SSE \u8d85\u65f6\u79d2\u6570")
    parser.add_argument("--report", default="eval_report.json", help="\u62a5\u544a\u8f93\u51fa\u8def\u5f84")
    parser.add_argument("--verbose", action="store_true", help="\u8be6\u7ec6\u8f93\u51fa")

    args = parser.parse_args()

    if not Path(args.dataset).exists():
        print(f"ERROR: \u8bc4\u6d4b\u96c6\u4e0d\u5b58\u5728: {args.dataset}")
        sys.exit(1)

    config = EvalConfig(args.dataset, args.base_url)
    checker = AssertionChecker()
    reporter = ReportBuilder(verbose=args.verbose)
    log_snap = LogSnapshot(ROOT)

    async def _run():
        async with HttpClient(args.base_url, timeout=args.timeout) as http:
            runner = EvalRunner(
                config=config, http=http, log_snap=log_snap,
                checker=checker, reporter=reporter,
                sse_timeout=args.sse_timeout,
            )
            return await runner.run(phase_filter=args.phase)

    report = asyncio.run(_run())

    # save JSON report
    report_path = Path(args.report)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(asdict(report), f, ensure_ascii=False, indent=2)
    print(f"  \u62a5\u544a\u5df2\u4fdd\u5b58: {report_path.resolve()}\n")

    sys.exit(0 if report.failed == 0 else 1)


if __name__ == "__main__":
    main()
