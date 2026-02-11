# 03 — Intent Analysis & Routing

> LLM-First semantic analysis that classifies every user request into complexity, skill groups, and behavioral signals — driving downstream tool selection, memory retrieval, and planning.

[< Prev: API & Services](02-api-and-services.md) | [Back to Overview](README.md) | [Next: Agent Execution >](04-agent-execution.md)

---

## Design Goals

1. **LLM-First** — No keyword matching. Intent classification is done by the LLM, using structured output and few-shot examples.
2. **Low latency** — Intent analysis must complete in < 200ms. Message filtering, caching, and a lightweight model (Haiku-class) make this possible.
3. **High recall for skill groups** — Better to include an unnecessary skill group than to miss a relevant one. False positives are cheap; false negatives break functionality.

## Architecture

```
User Messages (filtered)
    │
    ▼
┌─ Four-Layer Cache ─────────────────────────────────────────────────┐
│                                                                     │
│  L1: Hash Cache (exact SHA-256 match)                               │
│    │ miss                                                           │
│    ▼                                                                │
│  L2: Semantic Cache (embedding similarity)                          │
│    │ miss                                                           │
│    ▼                                                                │
│  L3: LLM Analysis (structured output via tool_choice)               │
│    │                                                                │
│    ├──→ L4: Skill Name Match (deterministic, augments L3 result)    │
│    │                                                                │
└────┼────────────────────────────────────────────────────────────────┘
     ▼
┌─ Output: IntentResult ─────────────────────────────────────────────┐
│  complexity:              simple | medium | complex                  │
│  skip_memory:             bool                                      │
│  is_follow_up:            bool                                      │
│  wants_to_stop:           bool                                      │
│  wants_rollback:          bool                                      │
│  relevant_skill_groups:   list[str]  ← augmented by L4              │
└─────────────────────────────────────────────────────────────────────┘
```

## Output Schema

The intent analyzer outputs 6 core fields:

| Field | Type | Purpose |
|---|---|---|
| `complexity` | `simple \| medium \| complex` | Drives tool set size, planning depth, prompt length |
| `skip_memory` | `bool` | Skip memory retrieval for objective queries (weather, math) |
| `is_follow_up` | `bool` | Reuse plan cache and inherit previous tool context |
| `wants_to_stop` | `bool` | User wants to cancel/stop the current task |
| `wants_rollback` | `bool` | User wants to undo/revert changes |
| `relevant_skill_groups` | `list[str]` | Which skill groups to inject (e.g., `["writing", "data_analysis"]`) |

**Derived field**: `needs_plan` is computed from `complexity` (not output by LLM), eliminating contradictions between complexity and planning signals.

## Four-Layer Cache

Intent analysis uses a cascading cache to minimize LLM calls:

| Layer | Strategy | Latency | Hit Scenario |
|---|---|---|---|
| **L1 Hash** | Exact SHA-256 match of user query | < 1ms | Identical repeat query |
| **L2 Semantic** | Embedding similarity above threshold | ~10ms | Paraphrased query |
| **L3 LLM** | Structured output via tool_choice | ~100-200ms | Novel query |
| **L4 Skill Match** | Deterministic skill name lookup | < 1ms | Augments L3 result with explicitly named skills |

L4 runs after L3 to catch cases where the user mentions a skill by name (e.g., "use the excel-analyzer") that the LLM might not map to the correct skill group.

## Message Filtering

Before sending to the LLM, messages are aggressively filtered to stay within the latency budget:

```
_filter_for_intent():
  1. Keep only the last 5 user messages (role=user)
  2. Keep the last 1 assistant message, truncated to 100 chars
  3. Strip all tool_use / tool_result blocks
  4. Strip image/file content blocks
  5. Extract pure text only

Result: < 2000 tokens input → < 200ms total latency
```

This filtering is O(n) with < 0.1ms overhead. No LLM calls, no network requests.

## Structured Output

The analyzer uses Claude's `tool_choice` to force structured JSON output:

```python
_INTENT_TOOL = {
    "name": "classify_intent",
    "input_schema": {
        "type": "object",
        "properties": {
            "complexity": {"type": "string", "enum": ["simple", "medium", "complex"]},
            "skip_memory": {"type": "boolean"},
            "is_follow_up": {"type": "boolean"},
            "wants_to_stop": {"type": "boolean"},
            "wants_rollback": {"type": "boolean"},
            "relevant_skill_groups": {"type": "array", "items": {"type": "string"}}
        },
        "required": [...]
    }
}
```

This guarantees valid JSON output — no parsing failures, no missing fields.

## Few-Shot Examples

The prompt includes 20+ few-shot examples covering:

- Simple queries: "What's the weather?" → `simple, skip_memory=true, groups=[]`
- Medium tasks: "Write an article about AI" → `medium, skip_memory=false, groups=["writing"]`
- Complex tasks: "Research competitors and write a report" → `complex, groups=["research", "writing"]`
- Follow-ups: "Make it shorter" → `simple, is_follow_up=true`
- Stop signals: "Never mind, stop" → `wants_to_stop=true`
- Rollback: "Undo the file changes" → `wants_rollback=true`
- Multi-group: "Analyze this Excel and create a presentation" → `groups=["data_analysis", "writing"]`

Key principle: **40%+ of examples demonstrate multi-select** for `relevant_skill_groups`, counteracting the LLM's tendency toward single-select.

## Downstream Impact

The intent result drives multiple downstream decisions:

| Field | Downstream Effect |
|---|---|
| `complexity=simple` | Minimal tool set (4 core tools), no planning, shortest system prompt |
| `complexity=complex` | Full tool set, planning enabled, complete system prompt |
| `skip_memory=true` | `UserMemoryInjector` skipped, saving ~100ms |
| `relevant_skill_groups` | `SkillGroupRegistry` filters skills → only relevant skills injected into prompt |
| `is_follow_up=true` | Reuse `plan_cache`, inherit previous `task_type` |
| `wants_to_stop` | Session stop event triggered |
| `wants_rollback` | Rollback flow activated |

## Key Files

| File | Purpose |
|---|---|
| `core/routing/intent_analyzer.py` | `IntentAnalyzer` class with four-layer cache |
| `core/routing/types.py` | `IntentResult`, `Complexity` enum |
| `prompts/intent_recognition_prompt.py` | Few-shot prompt template |

## Highlights

- **Zero keyword matching** — Pure LLM semantic understanding. "Don't make a PPT" correctly results in no PPT skill group.
- **Derived fields** — `needs_plan` is derived from `complexity`, not output by LLM, eliminating a common source of contradictions.
- **High-recall skill groups** — Overselection is intentional. The tool selector downstream handles precision.
- **Sub-200ms** — Message filtering + Haiku-class model + caching keeps latency minimal.

## Limitations & Future Work

- **No streaming intent** — Intent analysis is a blocking call. For very long messages, this could add latency.
- **Semantic cache cold start** — L2 cache requires enough history to be useful. First interactions always hit L3.
- **Skill group coverage** — If a new skill group is added but not represented in few-shot examples, the LLM may not select it.
- **Single-turn analysis** — The analyzer looks at the current message + recent history, but doesn't maintain a session-level intent model.

---

[< Prev: API & Services](02-api-and-services.md) | [Back to Overview](README.md) | [Next: Agent Execution >](04-agent-execution.md)
