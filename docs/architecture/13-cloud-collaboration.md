# 13 — Cloud Collaboration

> Local-first, cloud-enhanced. The local agent is always the brain; the cloud is a gateway, a fallback, and a specialized executor.

[< Prev: Playbook Online Learning](12-playbook-learning.md) | [Back to Overview](README.md)

---

## Implementation Status

| Phase | Status | Description |
|---|---|---|
| Phase 0.5: Direct API Call | **Completed** | cloud_agent tool calls cloud's `/api/v1/chat` SSE directly |
| Phase 1: Forward ACP + Local Task Tracking | **90% Complete** | Backend done; frontend components exist but event bridging broken |
| Phase 2: Reverse ACP + WebSocket | Not started | Mobile/IM forwarding to local agent |
| Phase 3: Memory/Context Sync | Not started | Shared user memory between local and cloud |
| Phase 4: Multi-Channel + Degradation | Not started | WeChat, Feishu, DingTalk adapters |

### Lessons Learned (from Phase 1 debugging)

Three root causes blocked cloud_agent for weeks. All three were architectural gaps, not prompt/error-message issues:

| Root Cause | Symptom | Fix |
|---|---|---|
| `capabilities.yaml` missing `input_schema` for cloud_agent | LLM could not call cloud_agent directly (not in `tools` param); routed through `api_calling` which rejected it | Added `input_schema` to YAML; added fallback in `ToolExecutor._load_custom_tool()` to auto-fill from tool class |
| `ToolContext.instance_id` never set | cloud_agent got `instance_id=""`, `get_cloud_client_for_instance("")` returned None, reported "cloud not enabled" | `create_tool_context()` now defaults to `AGENT_INSTANCE` env var |
| `_emit_progress()` emits wrong event type | Frontend `CloudProgressCard` exists but never receives data; 221s blank "thinking" spinner | `_emit_progress` calls `emit_progress_update` (generic), not `content_block` (what frontend expects). **Still broken, next priority.** |

**Key architectural insight**: When a tool is registered in `capabilities.yaml` without `input_schema`, it gets loaded by `ToolExecutor` but filtered out by `get_tools_for_llm()`. The LLM literally cannot call it. This applies to ANY tool, not just cloud_agent. The auto-fill fallback in `_load_custom_tool()` now prevents this class of bugs.

---

## Design Goals

1. **Local priority** — Any request, from any entry point, is routed to the local agent first if it is online.
2. **Cloud as Skill** — When the local agent determines that the cloud is more suitable (guided by `SKILL.md`), it delegates via a standard Skill + tool, just like any other skill.
3. **Cloud as gateway** — Mobile/IM requests arrive at the cloud (only public endpoint), but the cloud's first action is to check if local is online and forward to it.
4. **Cloud as fallback** — When local is offline, the cloud handles requests directly with degraded capabilities (no desktop operations).
5. **Transparent to user** — The user talks to "xiaodazi" regardless of which end does the work.

---

## Architecture Overview

### Two-Layer Routing

```
Any request (Desktop / Mobile / IM / Scheduled)
    |
    v
  Layer 1: Is local online?
    |
    +-- YES --> Route to local agent
    |           |
    |           v
    |         Layer 2: Is cloud more suitable? (SKILL.md boundary)
    |           |
    |           +-- NO  --> Local handles it directly
    |           +-- YES --> Local delegates via cloud_agent tool
    |
    +-- NO  --> Cloud fallback (degraded: no desktop operations)
```

### Three Roles of the Cloud

| Role | What it does | When |
|---|---|---|
| **Gateway** | Receives Mobile/IM webhooks, checks local online status, forwards to local if online | Mobile/IM entry, local online |
| **Fallback** | Handles requests directly when local is offline (search, writing, sandbox — but no desktop ops) | Any entry, local offline |
| **Executor** | Runs tasks delegated by local via cloud_agent tool (sandbox, persistent tasks, deep research) | Local online, cloud more suitable |

### Two Codebases

| | Local | Cloud |
|---|---|---|
| **Repo** | `xiaodazi/zenflux_agent` | `zeno-backend-agent` |
| **Framework** | ZenFlux (shared engine) | ZenFlux (shared engine) |
| **Database** | SQLite + FTS5 + sqlite-vec | PostgreSQL + Redis |
| **Deployment** | Tauri desktop app | Docker + Nginx |
| **Coupling** | Zero shared runtime code | Zero shared runtime code |

---

## 1 — Cloud Skill: Delegation Boundary

### SKILL.md-Driven Decision (LLM-First)

The boundary between "local handles it" and "delegate to cloud" is defined entirely in `skills/library/cloud-agent/SKILL.md`. The LLM reads the SKILL.md and decides — no hardcoded routing rules.

### Three Reasons to Delegate

**1. Persistent execution** — The task should survive laptop shutdown.

| User says | Cloud? | Why |
|---|---|---|
| "Send me a tech news briefing every morning at 8am" | Yes | User may not have their computer on at 8am |
| "Monitor this product's price over the weekend" | Yes | Computer may be off all weekend |
| "Remind me about my meeting at 3pm" | **No** | User is actively using the computer now |

**2. Sandbox execution** — The task needs code execution, project build, or app publishing.

| User says | Cloud? | Why |
|---|---|---|
| "Run this Python data analysis script" | Yes | Needs isolated sandbox environment |
| "Build a birthday invitation webpage and send the link" | Yes | Sandbox build + publish to public URL |
| "Analyze this Excel spreadsheet" | **No** | Built-in analysis capability |

**3. Deep research** — Multi-hour research with web search, content extraction, and synthesis.

| User says | Cloud? | Why |
|---|---|---|
| "Research the AI agent market and write a report" | Yes | Long-running, benefits from cloud tools |
| "Search for the latest AI papers" | **No** | Local has search skills, instant results |

### Tool Registration (Current Implementation)

cloud_agent is registered as **both** a tool and a skill:

- **Tool**: `config/capabilities.yaml` — type TOOL, with `input_schema` (task, context), loaded by `ToolExecutor`, appears in LLM's `tools` param
- **Skill**: `instances/xiaodazi/config/skills.yaml` — `backend_type: tool`, `tool_name: cloud_agent`, in `cloud_skills` group
- **SKILL.md**: `skills/library/cloud-agent/SKILL.md` — delegation boundary guide with examples

The `backend_type: tool` attribute in the skill config tells the prompt system (Type A) to instruct the LLM to call the tool directly, rather than executing code via nodes.

---

## 2 — Current Implementation (Phase 0.5 + Phase 1)

### File Map

| File | Purpose | Status |
|---|---|---|
| `tools/cloud_agent.py` | BaseTool subclass — SSE consumption + event bridging + task tracking | Implemented |
| `services/cloud_client.py` | CloudClient — HTTP + SSE consumer + auto-login | Implemented |
| `core/cloud/task_manager.py` | Local task tracking in SQLite | Implemented |
| `core/cloud/models.py` | `LocalCloudTask` SQLite model | Implemented |
| `skills/library/cloud-agent/SKILL.md` | Delegation boundary guide | Implemented |
| `config/capabilities.yaml` | cloud_agent tool registration with `input_schema` | Implemented |
| `instances/xiaodazi/config.yaml` | `cloud.enabled: true`, `cloud.url` | Implemented |
| `instances/xiaodazi/config/skills.yaml` | `cloud_skills` group with `cloud-agent` | Implemented |
| `frontend/src/components/chat/CloudProgressCard.vue` | Progress card UI component | Implemented (not receiving events) |
| `frontend/src/composables/useChat.ts` | `cloud_progress` content block handling | Implemented (initContentBlock only) |
| `frontend/src/components/chat/MessageContent.vue` | Routes `cloud_progress` blocks to CloudProgressCard | Implemented |
| `frontend/src/views/settings/SettingsView.vue` | Cloud config UI (URL, username, password, test) | Implemented |

### Call Chain (Working)

```
User: "用云端智能体分析伊朗局势"
    |
    v
IntentAnalyzer → relevant_skill_groups: ["research", "cloud_skills"]
    |
    v
ToolSelector → tools_for_llm includes cloud_agent (has input_schema)
    |
    v
LLM (qwen3-max) → tool_calls: [{name: "cloud_agent", input: {task: "..."}}]
    |
    v
ToolExecutor.execute("cloud_agent", {task: "..."})
    |
    v
CloudAgentTool.execute()
    ├── get_cloud_client_for_instance(instance_id)  # instance_id from AGENT_INSTANCE env
    ├── client.health_check()
    ├── TaskManager.create_task()
    └── async for evt in client.chat_stream_with_tracking():
            ├── session_info → record conversation_id
            ├── tool_start  → _emit_progress("cloud_tool", ...)
            ├── tool_end    → _emit_progress("cloud_tool_done", ...)
            ├── text_delta  → final_text += evt.text
            └── completed   → break
    |
    v
Return {success: true, result: final_text, task_id: "ct_xxx"}
```

### Event Bridge Gap (Current Bug)

The backend emits progress events, but they don't reach the frontend CloudProgressCard:

```
cloud_agent._emit_progress()
    └── broadcaster.emit_progress_update(session_id, step_id, message)
            └── Emits generic "progress_update" SSE event

Frontend expects:
    └── content_block type="cloud_progress" with {steps, status, task_id}
            └── Triggers CloudProgressCard.vue rendering
```

**Mismatch**: `emit_progress_update` emits a generic progress event (for progress bars), not a `content_block` event. The frontend CloudProgressCard listens for `content_block_start` with `type: "cloud_progress"`, which never arrives.

### Authentication

Current auth uses the cloud's existing web login API:

- `POST /api/v1/auth/login` with username/password → JWT
- JWT stored in memory, auto-refreshed via `_ensure_auth()` before each request
- No device binding, no Keychain storage, no refresh token (Phase 2+)
- If no credentials configured: requests sent anonymously (may fail with 401)

---

## 3 — Next Steps: Phase 1 Completion

### P0: Fix Event Bridge (cloud_progress → frontend)

**Problem**: User sees 221s blank "thinking" spinner during cloud execution.

**Fix**: Change `_emit_progress()` in `cloud_agent.py` to emit `content_block` events that the frontend can render:

```python
# Current (broken):
await broadcaster.emit_progress_update(session_id, step_id, message)

# Target (working):
await broadcaster.emit_message_delta(
    session_id=session_id,
    conversation_id=conversation_id,
    delta={
        "type": "content_block_delta",
        "content_block": {
            "type": "cloud_progress",
            "task_id": task_id,
            "status": "running",
            "steps": [...accumulated_steps...],
        }
    }
)
```

This requires:
1. `cloud_agent.py`: Maintain a running list of steps, emit as `content_block` events
2. `useChat.ts`: Verify `updateContentBlock` handles `cloud_progress` deltas (currently only `initContentBlock` has the branch)
3. `CloudProgressCard.vue`: Verify it renders the step list correctly

### P1: Cloud Auth Configuration

- Config: `instances/xiaodazi/config.yaml` should support `cloud.username` and `cloud.password`
- Alternatively: use `CLOUD_USERNAME` / `CLOUD_PASSWORD` environment variables
- SettingsView.vue already has the UI — wire it to the backend settings API

### P2: Streaming Text from Cloud

During cloud execution, `text_delta` events accumulate text but don't stream to the user. The user only sees the final result after the tool completes. Consider streaming `text_delta` as real-time content within the CloudProgressCard.

---

## 4 — ACP Protocol Design (Phase 2+)

ACP (Agent Collaboration Protocol) is a lightweight HTTP + WebSocket protocol connecting the two codebases. It has two directions.

### Forward ACP (Local → Cloud): Skill Delegation

Phase 1 uses direct API calls (`/api/v1/chat`). Phase 1.5+ will use dedicated ACP endpoints:

```
POST   /acp/tasks                           Create a task
GET    /acp/tasks/{task_id}                 Query task status and result
GET    /acp/tasks/{task_id}/stream?last_seq=N   SSE event stream
PATCH  /acp/tasks/{task_id}/state           Pause / resume / cancel
POST   /acp/tasks/{task_id}/input           HITL input
```

### Reverse ACP (Cloud → Local): Mobile/IM Forwarding

```
WS  /acp/ws    Persistent WebSocket connection (local → cloud)
```

The local agent connects on startup and maintains a heartbeat (30s interval). The cloud maintains an online registry.

### Task State Machine

```
submitted --> working --> completed
                |
                +--> failed
                |
                +--> canceled (via PATCH .../state)
                |
                +--> paused --> working (resumed)
```

---

## 5 — Authentication Design (Phase 2+)

### Device Binding (Future)

The user opens Settings > Cloud Collaboration in the Tauri app, enters the cloud URL, username, and password. The app calls:

```
POST /acp/auth/bind
{
  "username": "liuyi",
  "password": "***",
  "device_name": "MacBook-Pro-liuyi"
}
```

| Token | Lifetime | Purpose | Storage |
|---|---|---|---|
| `acp_token` | 90 days | Daily ACP request auth | Keychain |
| `refresh_token` | Permanent (revocable) | Silent refresh | Keychain |
| `device_id` | Permanent | Device identity | Keychain |

---

## 6 — Event Tunneling Design

### Problem

The cloud agent internally runs a full agent loop (intent → plan → tool calls → synthesis). The local user needs real-time visibility into this execution, not just a spinner.

### Solution: Event Tunneling

```
Cloud Agent         SSE Stream           Local cloud_agent    Frontend
(internal)                               Tool                 CloudProgressCard
    |                   |                    |                   |
 thinking          thinking_start ------> content_block       Step: "思考中"
                                         {cloud_progress}
    |                   |                    |                   |
 tool: web_search  tool_start ----------> content_block       Step: "搜索中"
                                         {cloud_progress}     (spinning)
    |                   |                    |                   |
 8 results found   tool_end -------------> content_block       Step: "搜索完成"
                                         {cloud_progress}
    |                   |                    |                   |
 "Analysis..."     text_delta ----------> content_block       Streaming text
                                         or content_delta      in card
    |                   |                    |                   |
 completed         completed ------------> tool_result         Card: "完成"
```

### CloudProgressCard Mockup

```
+-----------------------------------------------------------+
|  Cloud executing...                            [Cancel]    |
|                                                           |
|  * Analyzing intent                             Done      |
|  * Deep web search (exa_search)                 Done      |
|    - Found 8 relevant results                             |
|  * Competitor scraping (web_scraper)            Running   |
|    - Scraping competitor-a.com...                         |
|  o Comparative analysis                         Pending   |
|  o Generate report                              Pending   |
|                                                           |
|  ================================== 60%                   |
|  45s elapsed - est. 30s remaining                         |
+-----------------------------------------------------------+
```

---

## 7 — Phased Implementation Roadmap

### Phase 0.5: Direct API Call — COMPLETED

| Side | Work |
|---|---|
| **Cloud** | Zero changes — uses existing API |
| **Local** | `services/cloud_client.py`, `tools/cloud_agent.py`, `skills/library/cloud-agent/SKILL.md` |
| **Auth** | Username/password → JWT |

### Phase 1: Forward ACP + Local Task Tracking — 90% COMPLETE

| Side | Work | Status |
|---|---|---|
| **Cloud** | Zero changes | Done |
| **Local Backend** | Task Manager, instance config, tool registration with schema | Done |
| **Local Frontend** | CloudProgressCard, SettingsView cloud section, useChat cloud_progress | Components exist, event bridge broken |
| **Remaining** | Fix `_emit_progress` → `content_block` event type; wire SettingsView to backend | **Next** |

### Phase 2: Reverse ACP + WebSocket — NOT STARTED

| Side | Work |
|---|---|
| **Cloud** | WebSocket endpoint, online registry, `route_request()` |
| **Local** | WebSocket client + heartbeat + request handler |

### Phase 3: Memory/Context Sync — NOT STARTED

| Work |
|---|
| Memory sync protocol (MEMORY.md delta sync or API-based) |
| Scheduled task migration: local creates → cloud persists → cloud executes |

### Phase 4: Multi-Channel + Degradation — NOT STARTED

| Work |
|---|
| Channel adapters: WeChat, Feishu, DingTalk, Telegram |
| Degradation UX: "Your computer is off, I'll queue this" |

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| Cloud Skill (SKILL.md + tool), not hardcoded router | LLM-First: boundary defined in prompt, not code |
| Tool must have `input_schema` in capabilities.yaml | Without it, `get_tools_for_llm()` filters it out and LLM cannot call it |
| `instance_id` from `AGENT_INSTANCE` env var | Enables per-instance cloud config without explicit parameter passing |
| Event tunneling via `content_block` (not `progress_update`) | Frontend CloudProgressCard expects content_block events; generic progress_update is invisible |
| Bidirectional ACP, not cloud-centric | Local-first: local is always the brain when online |
| Separate ACP Token from Web JWT (Phase 2+) | Different lifecycle: desktop needs 90-day tokens; web needs 24h sessions |
| 3 delegation reasons only | Conservative boundary. Most tasks stay local (faster, private, offline-capable) |
