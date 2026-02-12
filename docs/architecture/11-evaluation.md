# 11 — Evaluation & Quality

> Three-layer grading (code + model + human), automated E2E pipeline, runtime failure detection, and token audit — ensuring agent quality is measurable and improvable.

[< Prev: Instance & Config](10-instance-and-config.md) | [Back to Overview](README.md) | [Next: Playbook Online Learning >](12-playbook-learning.md)

---

## Design Goals

1. **Quality is measurable** — Every agent response can be objectively scored (code graders) and subjectively evaluated (model graders).
2. **Failures are classified** — Runtime failures are detected, categorized, and feed back into optimization.
3. **Regression prevention** — Production failures are automatically converted into test cases.

## Architecture

```
┌─ Three-Layer Grading ─────────────────────────────────────────────┐
│  Code Grader (deterministic)    — PASS/FAIL authority              │
│  Model Grader (LLM-as-Judge)    — quality scores, advisory         │
│  Human Review                   — final judgment on edge cases     │
└───────────────────────────────────────────────────────────────────┘

┌─ E2E Pipeline ────────────────────────────────────────────────────┐
│  run_e2e_auto.py ──→ Test Suites (phase1/2/3)                     │
│       └──→ Code + Model Grading ──→ JSON + Markdown Reports       │
└──────────────────────────────────────┬────────────────────────────┘
                                       │
┌─ Runtime Monitoring ─────────────────┼────────────────────────────┐
│  FailureDetector (12 types)          │                             │
│  TokenAuditor (multi-level)          │                             │
│  QualityScanner                      │                             │
└──────────────────────┬───────────────┘                             │
                       │                                             │
                       ▼                                             ▼
              ┌─ Feedback Loop ─────────────────────────────────────┐
              │  Auto-generated Regression Tests                     │
              │  Prompt / Strategy Optimization                      │
              └─────────────────────────────────────────────────────┘
```

## Three-Layer Grading

### Code Grader (Deterministic)

Objective, fast, repeatable checks:

| Grader | What It Checks |
|---|---|
| `check_no_tool_errors` | All tool calls succeeded (no errors in results) |
| `check_response_not_empty` | Agent produced a non-empty response |
| `check_token_budget` | Token usage within limits |
| `check_max_turns` | Execution completed within turn limit |
| `check_checkpoint` | Expected intermediate states were reached |

Code graders are **authoritative** — they determine PASS/FAIL.

### Model Grader (LLM-as-Judge)

Subjective quality evaluation via a separate LLM:

| Grader | What It Evaluates |
|---|---|
| `grade_response_quality` | Overall response quality (1-5 scale) |
| `grade_intent_understanding` | Did the agent correctly understand the request? |
| `grade_over_engineering` | Did the agent do more than asked? |
| `grade_logical_coherence` | Is the response logically consistent? |

Model graders are **advisory** — they produce scores and explanations for human review, but don't trigger PASS/FAIL.

```json
{
  "grader_type": "model",
  "grader_name": "grade_response_quality",
  "passed": true,
  "score": 0.8,
  "explanation": "Response addressed all user requirements...",
  "details": {
    "weighted_score": 4.0,
    "strengths": ["Comprehensive analysis", "Clear structure"],
    "weaknesses": ["Missing visualization"],
    "needs_human_review": true
  }
}
```

### Human Review

Final layer for edge cases:

- Model grader flags `needs_human_review=true`
- Human reviewers validate model grader assessments
- Disagreements feed back into grader calibration

## E2E Test Pipeline

### Test Suites

| Suite | Scope | Cases |
|---|---|---|
| `phase1_core` | Basic agent capabilities | Intent analysis, tool calling, memory |
| `phase2_scenarios` | User scenario walkthroughs | Multi-turn conversations, file processing |
| `phase3_full` | Full integration | Complex tasks with planning + tools + memory |
| `feasibility` | Desktop operation capabilities | File operations, UI automation |
| `efficiency` | Performance metrics | Path optimality, token efficiency |
| `regression` | Auto-generated from failures | Specific failure reproduction |

### Pipeline Execution

```bash
# Full run
python scripts/run_e2e_auto.py --clean

# Single case
python scripts/run_e2e_auto.py --case A1

# Resume from a case
python scripts/run_e2e_auto.py --from D4

# Use existing server
python scripts/run_e2e_auto.py --no-start --port 8000
```

The pipeline:
1. Starts a backend server (or uses existing)
2. Executes test cases sequentially
3. Runs code graders + model graders on each result
4. Generates JSON report + Markdown summary
5. Outputs pass rate and failure analysis

### Report Structure

```
evaluation/reports/
├── e2e_phase2_scenarios_20260210_202433.json    # Full results
├── e2e_phase2_scenarios_20260210_202433.md       # Human-readable summary
└── e2e_triage_phase2_scenarios_20260210_202433.md # Failure triage
```

## Runtime Failure Detection

`FailureDetector` monitors agent execution and classifies failures:

| Failure Type | Detection Method | Severity |
|---|---|---|
| `CONTEXT_OVERFLOW` | Token count exceeds budget | HIGH |
| `TOOL_CALL_FAILURE` | Tool returns error | MEDIUM |
| `CONSECUTIVE_TOOL_ERRORS` | 3+ tool errors in a row | HIGH |
| `USER_NEGATIVE_FEEDBACK` | User expresses dissatisfaction | MEDIUM |
| `INTENT_MISMATCH` | Agent misunderstands the request | MEDIUM |
| `TIMEOUT` | Execution exceeds time limit | HIGH |
| `RESPONSE_QUALITY` | LLM judge scores below threshold | LOW |
| `SAFETY_VIOLATION` | Output contains unsafe content | CRITICAL |
| `OVER_ENGINEERING` | Agent does more than asked | LOW |
| `LOGICAL_INCOHERENCE` | Response contradicts itself | MEDIUM |
| `USER_RETRY` | User rephrases similar query (Jaccard similarity) | MEDIUM |
| `UNKNOWN_ERROR` | Unclassified error | HIGH |

Detected failures are:
1. Recorded with full context (input, output, error details)
2. Dispatched to registered failure handlers
3. Available via `get_statistics()` for analysis

## Token Audit

`TokenAuditor` tracks all LLM token consumption:

| Level | Scope | Purpose |
|---|---|---|
| `TURN` | Per LLM call | Detect runaway calls |
| `SESSION` | Per chat session | Budget enforcement |
| `CONVERSATION` | Per conversation | Usage reporting |
| `USER` | Per user | Billing, quotas |
| `AGENT` | Per agent instance | Capacity planning |

Features:
- **Anomaly detection** — Flags calls that exceed per-turn thresholds (e.g., > 50K tokens in one call)
- **JSONL persistence** — Records written to `{user_id}_{date}.jsonl` for billing
- **Real-time stats** — `get_stats()` with time range filtering

## QoS Levels

The evaluation system supports Quality-of-Service tiers:

| Level | Token Budget | Max Turns | Features |
|---|---|---|---|
| FREE | 50K/session | 10 | Basic tools only |
| BASIC | 100K/session | 30 | + Planning, memory |
| PRO | 200K/session | 100 | + Full skills, backtracking |
| ENTERPRISE | Custom | Custom | + Priority routing, SLA |

## Feedback Loop

### Auto-Regression

Production failures are automatically converted to test cases:

```
Failure detected in production
  → FailureDetector records case
  → Converted to evaluation suite entry
  → Added to regression/ test suite
  → Runs in next E2E cycle
  → Ensures fix doesn't regress
```

### Optimization Direction

Each failure type maps to an optimization direction:

| Failure Type | Optimization Target |
|---|---|
| Intent mismatch | Improve few-shot examples in intent prompt |
| Tool errors | Fix tool implementation or add error handling |
| Over-engineering | Adjust system prompt complexity boundaries |
| Context overflow | Tune compression thresholds |
| User retry | Analyze response quality, improve prompt |

## Key Files

| File | Purpose |
|---|---|
| `evaluation/harness.py` | E2E test harness |
| `evaluation/graders/code_based.py` | Deterministic graders |
| `evaluation/graders/model_based.py` | LLM-as-Judge graders |
| `evaluation/models.py` | `LLMJudge`, grading models |
| `core/monitoring/failure_detector.py` | `FailureDetector` (12 failure types) |
| `core/monitoring/token_audit.py` | `TokenAuditor` (multi-level tracking) |
| `scripts/run_e2e_auto.py` | Automated E2E pipeline |
| `evaluation/suites/` | Test suite definitions |

## Highlights

- **Three-layer separation** — Code graders for objectivity, model graders for nuance, humans for edge cases. Clear roles.
- **Automated pipeline** — One command runs the full E2E suite with grading and reporting.
- **12-type failure classification** — Not just "error" vs "success." Specific failure types enable targeted optimization.
- **Auto-regression** — Production failures automatically become test cases, preventing the same bug from recurring.

## Limitations & Future Work

- **No real-time dashboard** — Monitoring data is in logs and JSONL files. A Grafana/Prometheus integration is planned.
- **Model grader calibration** — LLM-as-Judge accuracy depends on prompt quality. Systematic calibration with human labels is needed.
- **No A/B testing** — No built-in mechanism to compare two prompt/strategy variants on the same test suite.
- **Single-machine E2E** — The pipeline runs locally. CI/CD integration for automated testing on every commit is planned.

---

[< Prev: Instance & Config](10-instance-and-config.md) | [Back to Overview](README.md) | [Next: Playbook Online Learning >](12-playbook-learning.md)
