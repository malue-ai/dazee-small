# 05 — Context Engineering

> Three-phase injection system with tool result compression, progressive history decay, and KV-Cache optimization — treating the context window as the most expensive cognitive space.

[< Prev: Agent Execution](04-agent-execution.md) | [Back to Overview](README.md) | [Next: Tool System >](06-tool-system.md)

---

## Design Goals

1. **Every token must earn its place** — The context window is finite and expensive. Only decision-relevant information belongs in it.
2. **Modular injection** — Each piece of context (system role, memory, skills, plan) is managed by an independent injector with its own token budget.
3. **Cache-friendly** — Stable content (system prompt, tool definitions) is placed first to maximize Claude's prompt caching hit rate.

## Architecture

```
┌─ Phase 1: System (STABLE cache) ──────────────────────────────────┐
│  SystemRoleInjector        — agent persona + rules                 │
│  ToolSystemRoleProvider    — tool definitions                      │
│  SkillPromptInjector       — active skill instructions             │
└─────────────────────────────────┬─────────────────────────────────┘
                                  │
┌─ Phase 2: User Context (SESSION cache) ───────────────────────────┐
│  UserMemoryInjector        — user preferences + history            │
│  KnowledgeInjector         — relevant documents                    │
│  PlaybookHintInjector      — strategy guidance                     │
└─────────────────────────────────┬─────────────────────────────────┘
                                  │
┌─ Phase 3: Runtime (DYNAMIC, no cache) ────────────────────────────┐
│  PlanInjector              — current plan status                   │
│  ErrorRetention            — past failure lessons                  │
│  TodoRewriter              — goal injection at end                 │
└─────────────────────────────────┬─────────────────────────────────┘
                                  │
                                  ▼
                     ┌──────────────────────┐
                     │  LLM Context Window   │
                     └──────────────────────┘
                              ▲     ▲
              ┌───────────────┘     └───────────────┐
┌─ Compression ────────────────┐  ┌─ Optimization ─────────────────┐
│  ToolResultCompressor         │  │  CacheOptimizer (KV-Cache)     │
│  Progressive History Decay    │  │  StructuralVariation (anti-    │
│  Old Image Stripping          │  │    pattern-matching)           │
└───────────────────────────────┘  └────────────────────────────────┘
```

## Three-Phase Injection

Each injector is registered with a phase, cache strategy, and priority:

| Phase | Cache Strategy | Content Type | Example Injectors |
|---|---|---|---|
| **Phase 1: System** | `STABLE` — long cache TTL | System prompt, tool definitions, skill instructions | `SystemRoleInjector`, `ToolSystemRoleProvider` |
| **Phase 2: User Context** | `SESSION` — medium cache TTL | User memory, knowledge, playbooks | `UserMemoryInjector`, `KnowledgeInjector` |
| **Phase 3: Runtime** | `DYNAMIC` — no cache | Plan state, error history, current-turn context | `PlanInjector`, `TodoRewriter` |

The `InjectionOrchestrator` executes all injectors in priority order within each phase, producing the final message array:

```
[system_message]          ← Phase 1 content (cached by Claude)
[user_context_message]    ← Phase 2 content (session-cached)
[conversation_history]    ← Compressed message history
[current_user_message]    ← Phase 3 content prepended/appended
```

### Token Budget per Injector

Each injector declares a `MAX_TOKENS` budget (enforced internally):

| Injector | Budget | Notes |
|---|---|---|
| System Role | 2000 tokens | Cached, one-time cost |
| Tool Definitions | 3000 tokens | Cached, varies by tool count |
| Skill Prompt | 1000 tokens | Only active skills |
| User Memory | 500 tokens | Top-3 most relevant memories |
| Knowledge | 800 tokens | Top-3 snippets + paths |
| Playbook | 300 tokens | Best-matching strategy |
| Plan Status | 300 tokens | Current goal + progress |
| Single tool_result | 3000 tokens | Exceeding → scratchpad |

**Total non-message budget**: ~12,000 tokens (~6% of a 200K context window).

## Tool Result Compression

Large tool outputs are compressed before entering the context:

| Tool Type | Strategy | Context Keeps |
|---|---|---|
| Search results | Extract top-5 titles + snippets | ~2000 chars |
| File reads | Head 10 lines + metadata + scratchpad path | ~1000 chars |
| Code execution | stdout/stderr first 50 lines + scratchpad | ~1500 chars |
| API responses | Key field extraction | ~1000 chars |

The `ToolResultCompressor` (threshold: 1500 chars) saves the full output to a local JSON file and returns a compressed summary with a reference path. The agent can later `cat` the full content if needed.

```
Tool returns 50KB of search results
  → Compressor saves full JSON to storage/tool_results/{ref_id}.json
  → Context receives: "Found 8 results. Top 3: [title + snippet] ... Full data: {ref_path}"
```

## Progressive History Decay

Older conversation turns are progressively compressed:

```
Timeline: ←─────────────────────────────→ Current

Messages: M1  M2  M3  ...  M15  M16  M17  M18  M19  M20

          [── Summary Zone ──]  [─ Fold Zone ─]  [─ Full Zone ─]
          LLM summary            Head+tail          Original text
          (≤500 tokens)          compression         preserved

          M1-M10 → one paragraph   M11-M16 folded   M17-M20 full
                                   tool_results
                                   → one-line summary
```

### Tool Pair Folding

Old tool_use + tool_result pairs are folded into a single line:

```
Before (3 turns ago):
  tool_use: web_search("Python sorting algorithms")
  tool_result: {"results": [...5000 chars...]}

After folding:
  "[Turn 3] web_search → Found 8 results, most relevant: quicksort O(nlogn), mergesort, TimSort"
```

### Image Decay

Old images (> 2 turns) are replaced with text descriptions:

```
Before: [image block with base64/URL]
After:  "[Image at Turn 3: user uploaded a screenshot of the settings page]"
```

## KV-Cache Optimization

`CacheOptimizer` maximizes Claude's prompt caching hit rate:

1. **Stable JSON serialization** — Tool definitions are serialized with sorted keys and consistent formatting, so the same tools produce identical cache keys across turns.
2. **Timestamp extraction** — Dynamic timestamps are moved out of cached content blocks, preventing cache invalidation on every turn.
3. **Phase ordering** — `STABLE` content (Phase 1) is placed first in the message array, maximizing the cacheable prefix.

## TodoRewriter

Places the current task goal at the **end** of the context (high-attention zone):

```
Research shows LLMs pay most attention to the beginning and end of context.
Middle content suffers from "Lost-in-the-Middle" effect.

TodoRewriter injects:
  "Current Goal: [task description]
   Progress: 3/5 steps completed
   Next: [specific next step]"

→ Placed at the end of the last user message
→ LLM always "sees" the current objective
```

## StructuralVariation

Randomizes prompt formatting to prevent LLM pattern matching:

| Element | Variations |
|---|---|
| Progress display | Percentage, fraction, progress bar, step count |
| Section separators | `---`, `===`, `***`, blank lines |
| List format | Numbered, bulleted, indented |
| Status labels | "Status:", "Progress:", "Current state:" |

This prevents the LLM from developing fixed response patterns for repeated prompt structures.

## Key Files

| File | Purpose |
|---|---|
| `core/context/context_engineering.py` | `ContextEngineeringManager`, `CacheOptimizer`, `TodoRewriter`, `StructuralVariation` |
| `core/context/injectors/base.py` | `BaseInjector`, `InjectionPhase`, `CacheStrategy` |
| `core/context/injectors/orchestrator.py` | `InjectionOrchestrator` — manages all injectors |
| `core/context/injectors/phase1/` | System-level injectors |
| `core/context/injectors/phase2/` | User context injectors (memory, knowledge) |
| `core/context/compaction/` | Tool result compression, history summarization |

## Highlights

- **Scratchpad exchange** — Large data stays in files, context holds only summaries + paths. 100x compression ratio for search results.
- **Budget discipline** — Every injector has a hard token cap. No single injector can overwhelm the context.
- **Cache-aware ordering** — Phase 1 content is stable across turns, maximizing KV-Cache reuse (up to 90% cache hits).
- **Anti-pattern-matching** — Structural variation keeps the LLM responsive to content, not formatting.

## Limitations & Future Work

- **No Context Folding** — Completed sub-tasks are truncated but not semantically folded into conclusions. Planned: automatic sub-task folding.
- **Fixed compression thresholds** — The 1500-char threshold is static. Should adapt based on remaining context budget.
- **Memory injection is session-cached** — If user memory changes mid-session, it won't be reflected until the cache expires (5 min).
- **No multi-modal scratchpad** — Images and files use the same compression path. Dedicated multi-modal summarization is planned.

---

[< Prev: Agent Execution](04-agent-execution.md) | [Back to Overview](README.md) | [Next: Tool System >](06-tool-system.md)
