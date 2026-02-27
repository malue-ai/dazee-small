# 12 — Playbook Online Learning

> The agent learns reusable strategies from successful sessions, confirmed by users, and applies them to similar future tasks — a closed-loop online learning system.

[< Prev: Evaluation & Quality](11-evaluation.md) | [Back to Overview](README.md)

---

## Design Goals

1. **Learn from success** — Automatically extract reusable strategies from sessions where the agent used tools effectively.
2. **Human-in-the-loop confirmation** — Users approve or dismiss suggested strategies. No strategy is applied without user consent.
3. **Semantic matching** — When a new task arrives, find the most relevant approved strategy using vector similarity, not keyword matching.
4. **Non-intrusive injection** — Matched strategies are injected as hints the agent can reference but is not forced to follow.

## Architecture

```
━━━ Strategy Extraction ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Successful Session (tools used, response complete)
       │
       ▼
  playbook_extraction (background task)
       │
       ▼
  PlaybookManager.extract_from_session() ──→ ┌──────────────────────────────┐
       │                                     │ Storage                      │
       ▼                                     │   JSON files (per-instance)  │
  PlaybookEntry (status: DRAFT)              │   Mem0 vectors (semantic)    │
       │                                     │   index.json (entry list)    │
       │                                     └──────────────────────────────┘
━━━ User Confirmation ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       │
       ▼
  WebSocket: playbook_suggestion event
       │
       ▼
  PlaybookSuggestionCard (frontend)
       │
       ├─ "记住" ──→ POST /api/v1/playbook/{id}/action (approve) ──→ APPROVED
       └─ "忽略" ──→ POST /api/v1/playbook/{id}/action (dismiss) ──→ deleted

━━━ Strategy Application ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  New user query
       │
       ▼
  PlaybookHintInjector (Phase 2)
       │
       ▼
  Two-layer matching: task_type filter → Mem0 semantic search
       │                                   ▲
       ▼                                   │ (reads from Storage)
  <playbook_hint> injected into agent context
       │
       ▼
  Agent references hint (not mandatory)
```

## The Learning Loop

The full lifecycle of a playbook, from extraction to application:

```
Step 1: EXTRACT
  User completes a chat session with tool usage
    → Background task fires (fire-and-forget, never blocks chat)
    → Pre-filter: skip trivial sessions (short response, no tools)
    → Build lightweight SessionReward from conversation messages
    → PlaybookManager.extract_from_session() creates DRAFT entry
    → Entry saved to JSON file + indexed in Mem0 vectors

Step 2: CONFIRM
  → playbook_suggestion event pushed via WebSocket
  → Frontend shows PlaybookSuggestionCard: "学到了一个新技巧"
  → User clicks "记住" → POST /api/v1/playbook/{id}/action (approve)
  → LLM regenerates description if still default template (light model, ~1s)
  → Mem0 upsert: old vectors deleted, new vectors indexed
  → Status: DRAFT → PENDING_REVIEW → APPROVED
  (Or user clicks "忽略" → entry deleted + Mem0 cleaned)

Step 3: APPLY
  → New chat request arrives
  → PlaybookHintInjector (Phase 2, priority 80) activates
  → Two-layer matching finds best strategy:
      Layer 1: task_type pre-filter + staleness check, 30 days (<1ms)
      Layer 2: Mem0 semantic search (vector similarity, score ≥ 0.5)
  → Best match formatted as <playbook_hint>
  → Injected into agent context (not mandatory, reference only)
  → Fire-and-forget: record_usage updates last_used_at (never blocks chat)

Step 4: EXPIRE (automatic, lazy evaluation)
  → On every match attempt, stale entries (unused > 30 days) are skipped
  → No background scan, no cron job — checked at match time
  → Stale playbooks remain in storage (user can still see/manage them)
  → API response includes is_stale flag for frontend display
```

## PlaybookEntry

Each playbook captures a complete execution pattern:

```python
PlaybookEntry(
    id="a1b2c3d4e5f6",
    name="Excel data analysis with chart",
    description="Analyze Excel data and generate visual charts",

    # When to use this strategy
    trigger={
        "task_types": ["data_analysis"],
        "complexity_range": [4, 8],
    },

    # How to execute
    strategy={
        "execution_strategy": "rvr-b",
        "suggested_tools": ["data_analysis_skill", "chart_generation"],
        "max_turns": 15,
    },

    # Tool sequence template
    tool_sequence=[
        {"tool": "data_analysis_skill", "purpose": "Load and analyze data"},
        {"tool": "chart_generation", "purpose": "Generate visualization"},
    ],

    # Quality metrics from source session
    quality_metrics={
        "avg_reward": 0.85,
        "success_rate": 1.0,
        "avg_turns": 8,
    },

    # Lifecycle
    status=PlaybookStatus.APPROVED,
    source="auto",
    source_session_id="sess-abc123",
    usage_count=5,
    last_used_at="2026-01-15T10:30:00",  # Auto-updated on injection
)
```

## Status Lifecycle

```
     ┌───────────┐
     │   DRAFT   │  ← Auto-extracted from session
     └─────┬─────┘
           │ submit_for_review()
     ┌─────▼──────────┐
     │ PENDING_REVIEW  │  ← Waiting for user action
     └──┬──────────┬───┘
        │          │
  approve()    reject()
        │          │
  ┌─────▼───┐  ┌───▼─────┐
  │ APPROVED │  │ REJECTED │
  └─────┬────┘  └─────────┘
        │
        ├── used within 30 days ──→ stays APPROVED (active)
        │
        ├── unused > 30 days ──→ still APPROVED but is_stale=true (skipped during matching)
        │
        └── deprecate() ──→ DEPRECATED (Mem0 vectors cleaned)
```

| Status | Meaning | Can be injected? |
|---|---|---|
| DRAFT | Auto-generated, not yet confirmed | No |
| PENDING_REVIEW | Submitted for user review | No |
| APPROVED | User confirmed, active | Yes (if not stale) |
| APPROVED + stale | Unused > 30 days | No (skipped at match time) |
| REJECTED | User declined | No |
| DEPRECATED | Previously approved, now retired | No |

## Two-Layer Matching (Precision-First)

Strategy matching follows the LLM-First principle with **precision over recall**: a false positive (injecting an irrelevant strategy) is worse than a false negative (missing a relevant one), because irrelevant hints can mislead the agent's tool selection and execution flow.

| Layer | Method | Latency | Purpose |
|---|---|---|---|
| **Layer 1** | `task_type` filter + staleness check | <1ms | Quick pre-filter: status=APPROVED, matches task_type, not stale (unused > 30 days). |
| **Layer 2** | Mem0 semantic search | ~50ms | Vector similarity + FTS5 keyword hybrid search. Deduplication by playbook_id. Score threshold ≥ 0.5. |

```python
# Layer 1: deterministic filter + staleness check
candidates = {
    id: entry for id, entry in entries.items()
    if entry.status == APPROVED
    and entry.matches_task_type(task_type)
    and not entry.is_stale()  # unused > 30 days → skip
}

# Layer 2: semantic search via Mem0 (no prefix noise)
results = pool.search(user_id="playbook", query=query, limit=top_k * 2)

# Deduplicate by playbook_id, filter by min_score (0.5)
```

**Precision safeguards:**
- **min_score = 0.5** (raised from 0.3) — filters out weak/ambiguous matches.
- **No dangerous fallback** — if Mem0 is unavailable, returns empty (no guessing).
- **Deduplication by playbook_id** — prevents the same playbook appearing multiple times in results.
- **Staleness filter** — entries unused for 90+ days are excluded from matching.
- **Agent-side defense** — prompt instructs the agent to ignore hints with confidence < 0.5 and to trust its own judgment over hints.

## Context Injection

`PlaybookHintInjector` injects the best-matching strategy into Phase 2 (User Context):

```xml
<playbook_hint confidence="0.78">
类似任务的成功策略：Analyze Excel data and generate visual charts
建议工具序列：data_analysis_skill → chart_generation
平均约 8 步，成功率 100%
</playbook_hint>
```

**Key design decisions:**
- **Priority 80** — Lower than user memory (which has higher priority), ensuring personal context takes precedence.
- **Budget ~300 tokens** — Kept compact to avoid overwhelming the context window.
- **Non-mandatory** — The hint is a reference, not an instruction. The agent can choose to follow a different approach. The system prompt explicitly tells the agent: "confidence < 0.5 时忽略; 如果你的判断与 hint 冲突，以你的判断为准".
- **Top-1 only** — Only the single best match is injected, avoiding information overload.
- **SESSION cache** — The same hint is reused within a session, avoiding repeated Mem0 queries.
- **Fire-and-forget usage tracking** — On successful injection, `record_usage()` is called via `asyncio.create_task()`, updating `last_used_at` without adding any latency to the chat response.

## Background Extraction

The extraction task runs as a fire-and-forget background task after each chat response:

```
Chat response complete
  → BackgroundTaskService schedules playbook_extraction
  → Pre-filter checks:
      - Assistant response ≥ 100 chars?
      - User message ≥ 10 chars?
      - Conversation had tool calls?
  → If all pass: build SessionReward, call extract_from_session()
  → If entry created: push playbook_suggestion via WebSocket
  → Failure is non-critical: logged and swallowed
```

**Deduplication**: If a playbook already exists for the same `session_id`, extraction is skipped.

**WebSocket delivery**: Background tasks run after the chat SSE stream is closed. The suggestion is delivered via the persistent WebSocket connection (`ConnectionManager.broadcast_notification()`), ensuring it reaches the frontend even after the chat response ends.

## Frontend Experience

The `PlaybookSuggestionCard` component appears inline in the chat:

```
┌──────────────────────────────────────────────┐
│  💡  学到了一个新技巧                          │
│      工具序列: data_analysis → chart_gen       │
│                                              │
│      [ 记住 ]  [ 忽略 ]                       │
└──────────────────────────────────────────────┘
```

- **"记住"** → `POST /api/v1/playbook/{id}/action` with `action: "approve"` → LLM regenerates description (light model, ~1s) → Mem0 upsert → Card shows "已记住：..."
- **"忽略"** → `POST /api/v1/playbook/{id}/action` with `action: "dismiss"` → Entry deleted + Mem0 cleaned → Card fades out

**Non-blocking guarantee**: The card has its own `loading` state (button shows "..."), but the chat input (`ChatInputArea`) is never disabled. Users can continue typing and sending messages while the approve/dismiss HTTP request is pending. The `isCurrentLoading` flag that controls input availability only tracks conversation loading and session state — playbook actions are completely independent.

## API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/playbook` | List all playbooks (filter by status/source) |
| GET | `/api/v1/playbook/{id}` | Get playbook details |
| POST | `/api/v1/playbook/{id}/action` | Execute action (approve/reject/dismiss) |
| DELETE | `/api/v1/playbook/{id}` | Delete a playbook |

## Storage

Playbooks are stored per-instance as JSON files:

```
data/instances/{name}/playbooks/
├── index.json              # Entry list + stats
├── a1b2c3d4e5f6.json      # Individual playbook entry
├── f7e8d9c0b1a2.json
└── ...
```

Additionally, each playbook's searchable text is indexed in **Mem0 vectors** (with `user_id="playbook"`) for semantic matching. This dual-storage approach keeps file-based CRUD simple while enabling vector similarity search.

## Key Files

| File | Purpose |
|---|---|
| `core/playbook/__init__.py` | Module exports |
| `core/playbook/manager.py` | `PlaybookManager` — CRUD, extraction, two-layer matching |
| `core/playbook/storage.py` | `FileStorage` — JSON file backend |
| `core/context/injectors/phase2/playbook_hint.py` | `PlaybookHintInjector` — strategy → context injection |
| `utils/background_tasks/tasks/playbook_extraction.py` | Background extraction task |
| `routers/playbook.py` | REST API endpoints |
| `frontend/src/api/playbook.ts` | Frontend API client |
| `frontend/src/components/chat/PlaybookSuggestionCard.vue` | Inline suggestion card |

## Highlights

- **Closed-loop learning** — Extract → Confirm → Apply → Expire. The agent gets better at recurring task types over time, and silently forgets strategies that are no longer used.
- **Human-in-the-loop** — No strategy is auto-applied. Users control what the agent "remembers", preventing bad patterns from persisting.
- **Precision-first matching** — Score threshold ≥ 0.5, no dangerous fallback, playbook_id deduplication, and staleness filtering. False positives (injecting irrelevant strategies) are treated as more harmful than false negatives (missing a match).
- **Automatic staleness** — Lazy evaluation: entries unused for 30+ days are silently skipped during matching. No cron jobs, no background scans. The entry stays in storage; users can see `is_stale` in the management UI.
- **Zero-blocking guarantee** — Every step is designed to never block the chat input:
  - Extraction: fire-and-forget background task
  - Approve/dismiss: frontend card has local loading state; `ChatInputArea` is independent
  - Usage tracking: `asyncio.create_task()` fire-and-forget
  - Injection: Phase 2 injector runs before the LLM call, not during user input
- **LLM-enhanced descriptions on approve** — When a user clicks "记住", the system uses a light model (Haiku-class) to regenerate the description with few-shot examples, improving semantic matching precision. This happens in ~1s and only on the card button — never delays the chat.
- **Mem0 data consistency** — Upsert semantics (delete-then-add) on every sync. approve/update/delete/deprecate all synchronize the Mem0 vector index. No stale or duplicate vectors.
- **Semantic matching** — Strategies are found by meaning (vector similarity + FTS5 hybrid), not keywords. "Analyze sales data" matches a playbook about "data analysis with charts".
- **Instance-isolated** — Each agent instance has its own playbook library. Strategies are not shared across instances.

## Limitations & Future Work

- **No cross-session learning** — Each playbook comes from a single session. Merging patterns across multiple similar sessions would produce more robust strategies.
- **No playbook management UI** — Users can only approve/dismiss via inline cards. A dedicated management page (list, edit, delete, search with `is_stale` indicators) is planned.
- **Fixed reward threshold** — The `min_reward_threshold=0.7` is static. Adaptive thresholds based on task type and historical data would improve extraction quality.
- **Single-strategy injection** — Only the top-1 match is injected. For complex tasks, multiple complementary strategies could be combined.
- **No quality feedback loop** — Usage count is tracked but ongoing success/failure rate after injection is not measured. Tracking post-injection outcomes would enable automatic deprecation of underperforming strategies.

---

[< Prev: Evaluation & Quality](11-evaluation.md) | [Back to Overview](README.md) | [Next: Cloud Collaboration >](13-cloud-collaboration.md)
