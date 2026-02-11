# 04 — Agent Execution Framework

> RVR-B (React-Validate-Reflect-Backtrack) execution loop with error classification, two-level circuit breakers, adaptive termination, and state consistency.

[< Prev: Intent & Routing](03-intent-and-routing.md) | [Back to Overview](README.md) | [Next: Context Engineering >](05-context-engineering.md)

---

## Design Goals

1. **Resilient execution** — Tool failures don't crash the agent. Errors are classified, and the agent can backtrack, retry with alternatives, or fail gracefully.
2. **Adaptive termination** — The agent stops when the task is done, not at a fixed turn count. Multiple termination signals are evaluated per turn.
3. **State safety** — File system and environment changes are snapshotted. Users can rollback if the agent makes unwanted modifications.

## Architecture

```
┌─ Agent (base.py) ──────────────────────────────────────────────────┐
│  Orchestrator ──→ Tool Selection                                    │
│       │      ──→ Context Injection                                  │
│       ▼                                                             │
│  ┌─ RVR-B Executor ───────────────────────────────────────────┐    │
│  │                                                             │    │
│  │  ┌──→ REACT ──→ VALIDATE ──┐                                │    │
│  │  │     (LLM)    (tools)    │                                │    │
│  │  │                         │                                │    │
│  │  │    success ─────────────┘ (loop back to REACT)           │    │
│  │  │                                                          │    │
│  │  │    error ──→ REFLECT ──┬─ CONTINUE ──→ (back to REACT)  │    │
│  │  │              (classify) ├─ BACKTRACK ──→ clean context ──┘    │
│  │  │                        ├─ FAIL_GRACEFULLY ──→ Terminator │    │
│  │  │                        └─ ESCALATE ─────────→ Terminator │    │
│  │  └────────────────────────────────────────────────────────  │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  Support: AdaptiveTerminator · CircuitBreaker · StateManager        │
│           ErrorClassifier                                           │
└─────────────────────────────────────────────────────────────────────┘
```

## Strategy Pattern

The execution logic is decoupled from the `Agent` class via a strategy pattern:

```
ExecutorProtocol (interface)
  ├── BaseExecutor (shared utilities)
  │   ├── RVRExecutor (React-Validate-Reflect)
  │   │   └── RVRBExecutor (+ Backtrack)
```

The `Agent` class handles orchestration (tool selection, context injection, event broadcasting) and delegates the execution loop to the injected `Executor`. Currently, all agents use `RVRBExecutor`.

## RVR-B Loop

Each turn in the loop:

```
Turn N:
  1. REACT    — Call LLM with current messages + tools
                LLM returns text and/or tool_calls
  2. VALIDATE — Execute tool calls via ToolExecutor
                Check results for errors
  3. REFLECT  — If errors:
                  ErrorClassifier categorizes the failure
                  Decide: CONTINUE / BACKTRACK / FAIL_GRACEFULLY / ESCALATE
  4. BACKTRACK (if needed)
                  Clean polluted context (replace error details with reflection summary)
                  Try alternative tool or approach
  5. TERMINATE? — AdaptiveTerminator checks all termination conditions
                  If met, exit loop
```

## Error Classification & Backtrack Decisions

When a tool call fails, the `ErrorClassifier` categorizes it:

| Decision | When | Action |
|---|---|---|
| **CONTINUE** | Transient error, likely self-recoverable | Let the LLM see the error and self-correct |
| **BACKTRACK** | Systematic failure, current approach won't work | Clean context, try alternative tool/approach |
| **FAIL_GRACEFULLY** | Unrecoverable, but can give a partial answer | Summarize what was accomplished, explain the limitation |
| **ESCALATE** | Critical failure or safety concern | Stop execution, request human intervention (HITL) |

### Context Cleaning

When backtracking, the executor doesn't just retry — it cleans the context:

```
Before: [tool_call → error_details → tool_call → error_details → ...]
After:  [reflection_summary: "Approach X failed because Y. Trying Z instead."]
```

This prevents the LLM from being confused by accumulating error messages (context pollution).

## Two-Level Circuit Breaker

Prevents the agent from getting stuck in failure loops:

| Level | Trigger | Action |
|---|---|---|
| **Level 1** | 3 consecutive tool errors | Force reflection — LLM must explain what's wrong before continuing |
| **Level 2** | 5 total backtrack attempts | Terminate execution — the task is beyond recovery |

## Adaptive Termination

`AdaptiveTerminator` evaluates multiple signals each turn:

| Signal | Condition | Default |
|---|---|---|
| **LLM stop** | LLM returns `end_turn` without tool calls | Always active |
| **Max turns** | Turn count exceeds limit | 100 turns |
| **Max duration** | Wall-clock time exceeds limit | 30 minutes |
| **Max failures** | Consecutive failures exceed threshold | 5 failures |
| **HITL** | User stops via UI | Always active |
| **Long-task confirm** | After 20+ turns, ask user if they want to continue | Configurable |
| **User intent** | `wants_to_stop=true` from intent analysis | Always active |

The terminator is **adaptive** — thresholds adjust based on task complexity:
- `simple` tasks: lower turn/duration limits
- `complex` tasks: higher limits, more tolerance for tool failures

## State Consistency

For tasks that modify the file system or environment, `StateConsistencyManager` provides a safety net:

```
Task starts
  → Create snapshot (file backups + environment state)
  → Record operations (with inverse operation definitions)
  → On success: commit (clean snapshot)
  → On failure/abort: HITL asks user → rollback / keep / continue
```

Snapshots are stored in `data/instances/{name}/snapshots/`.

## Key Files

| File | Purpose |
|---|---|
| `core/agent/base.py` | `Agent` class — orchestration, tool selection, context injection |
| `core/agent/execution/protocol.py` | `ExecutorProtocol`, `ExecutionContext`, `ExecutorConfig` |
| `core/agent/execution/rvr.py` | `RVRExecutor` — base React-Validate-Reflect loop |
| `core/agent/execution/rvrb.py` | `RVRBExecutor` — adds backtracking, error classification |
| `core/agent/factory.py` | `AgentFactory` — creates agents from schema/prompt |
| `core/termination/` | `AdaptiveTerminator` and termination conditions |
| `core/state/` | `StateConsistencyManager`, snapshots, rollback |

## Highlights

- **Self-healing** — Most tool failures are handled automatically. The agent classifies errors and adapts strategy without user intervention.
- **Context hygiene** — Backtrack cleans polluted context with reflection summaries, preventing error cascade.
- **Graceful degradation** — When the agent can't complete a task, it summarizes progress and explains limitations instead of crashing.
- **HITL integration** — Dangerous operations and long-running tasks have explicit user checkpoints.

## Limitations & Future Work

- **No parallel tool execution** — Tools execute sequentially. Parallel execution would speed up independent tool calls.
- **Fixed circuit breaker thresholds** — Thresholds are static. Dynamic adjustment based on task complexity is planned.
- **Limited backtrack depth** — The agent backtracks at the tool level, not at the plan level. Plan-level backtracking (replanning) is separate.
- **Snapshot granularity** — File-level snapshots work, but database state or remote API effects cannot be rolled back.

---

[< Prev: Intent & Routing](03-intent-and-routing.md) | [Back to Overview](README.md) | [Next: Context Engineering >](05-context-engineering.md)
