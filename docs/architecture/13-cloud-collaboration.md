# 13 — Cloud Collaboration

> Local-first, cloud-enhanced. The local agent is always the brain; the cloud is a gateway, a fallback, and a specialized executor.

[< Prev: Playbook Online Learning](12-playbook-learning.md) | [Back to Overview](README.md)

---

## Design Goals

1. **Local priority** — Any request, from any entry point, is routed to the local agent first if it is online. The local agent handles everything it can.
2. **Cloud as Skill** — When the local agent determines that the cloud is more suitable (guided by `SKILL.md`), it delegates via a standard Skill + fallback tool, just like any other skill.
3. **Cloud as gateway** — Mobile/IM requests arrive at the cloud (only public endpoint), but the cloud's first action is to check if local is online and forward to it.
4. **Cloud as fallback** — When local is offline, the cloud handles requests directly with degraded capabilities (no desktop operations).
5. **Transparent to user** — The user talks to "xiaodazi" regardless of which end does the work. The routing is invisible.

---

## Architecture Overview

### Two-Layer Routing

Every request — whether from the desktop app, a phone, an IM channel, or a scheduled trigger — follows the same two-layer routing logic:

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
    |           +-- YES --> Local delegates via cloud_agent Skill
    |
    +-- NO  --> Cloud fallback (degraded: no desktop operations)
```

Layer 1 is a simple online-status check (WebSocket heartbeat). Layer 2 is an LLM decision guided by the `cloud-agent` SKILL.md — no keyword matching, no hardcoded rules.

### Three Roles of the Cloud

```
                        +------------------+
                        |    User          |
                        +--------+---------+
                                 |
              +------------------+------------------+
              v                  v                  v
        Desktop App        Mobile / IM         Scheduled
        (Tauri)          (WeChat/Feishu)       (cron)
              |                  |                  |
              v                  v                  v
        +-----------+    +-------------+    +-------------+
        |  Local    |    |   Cloud     |    |   Cloud     |
        |  Agent    |    |   Gateway   |    |   Scheduler |
        +-----------+    +------+------+    +------+------+
              |                 |                  |
              |          Local online?             |
              |           /        \               |
              |         YES         NO             |
              |          |           |             |
              |    Forward to    Cloud Agent       |
              |    local agent   handles it        |
              |          |                         |
              +<---------+                         |
              |                                    |
              v                                    v
        +-------------------------------------------+
        |           Bidirectional ACP                |
        |                                           |
        |  Forward: Local --> Cloud (Skill delegate) |
        |  Reverse: Cloud --> Local (Mobile/IM fwd)  |
        +-------------------------------------------+
```

| Role | What it does | When |
|---|---|---|
| **Gateway** | Receives Mobile/IM webhooks, checks local online status, forwards to local if online | Mobile/IM entry, local online |
| **Fallback** | Handles requests directly when local is offline (search, writing, sandbox — but no desktop ops) | Any entry, local offline |
| **Executor** | Runs tasks delegated by local via cloud_agent Skill (sandbox, persistent scheduled tasks) | Local online, cloud more suitable |

### Two Codebases

| | Local | Cloud |
|---|---|---|
| **Repo** | `xiaodazi/zenflux_agent` | `zeno-backend-agent` |
| **Framework** | ZenFlux (shared engine) | ZenFlux (shared engine) |
| **Database** | SQLite + FTS5 + sqlite-vec | PostgreSQL + Redis |
| **Deployment** | Tauri desktop app | Docker + Nginx |
| **Entry points** | Tauri UI | IM webhooks, Web UI, scheduled triggers |
| **ACP role** | Client (Forward) + Server (Reverse) | Server (Forward) + Client (Reverse) |
| **Coupling** | Zero shared runtime code | Zero shared runtime code |

ACP (Agent Collaboration Protocol) is the only contract between the two codebases. Either side can be replaced independently as long as it speaks ACP.

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
| "Spend the afternoon researching this industry, no rush" | Yes | Multi-hour task, user may close laptop |
| "Remind me about my meeting at 3pm" | **No** | User is actively using the computer now |

**2. Sandbox execution** — The task needs code execution, project build, or app publishing. Local has no Docker/sandbox.

| User says | Cloud? | Why |
|---|---|---|
| "Run this Python data analysis script" | Yes | Needs isolated sandbox environment |
| "Build a birthday invitation webpage and send the link to friends" | Yes | Sandbox build + publish to public URL |
| "Check if this code snippet works" | Yes | Needs safe execution environment |
| "Analyze this Excel spreadsheet" | **No** | Built-in analysis capability, no sandbox needed |
| "Make me a PPT" | **No** | Local has PPT skills |

**3. Mobile/IM reachability** — The user wants to track progress or interact from their phone.

| User says | Cloud? | Why |
|---|---|---|
| "Research the AI agent market" (from phone during commute) | Yes | Results pushed to phone, progress checkable anytime |
| "How's that research going?" (from WeChat) | Yes | Check cloud task progress |
| "The industry report is done" (Feishu notification) | Yes | Cloud pushes completion notification |

### SKILL.md Few-Shot Examples

The SKILL.md includes both positive and negative examples to teach the LLM the boundary:

```markdown
## When to use cloud

<example>
<query>Every morning at 8am, give me a summary of tech news</query>
<use_cloud>true</use_cloud>
<reason>Scheduled task — user's computer may not be on at 8am</reason>
</example>

<example>
<query>Build a birthday invitation webpage and send the link to friends</query>
<use_cloud>true</use_cloud>
<reason>Needs sandbox to build the project and publish a public URL</reason>
</example>

## When NOT to use cloud (local handles it)

<example>
<query>Help me organize the files on my desktop</query>
<use_cloud>false</use_cloud>
<reason>Local file operation — xiaodazi handles this directly</reason>
</example>

<example>
<query>Search for the latest AI papers</query>
<use_cloud>false</use_cloud>
<reason>Local has search skills (Tavily/DuckDuckGo), instant results</reason>
</example>

<example>
<query>Analyze this Excel spreadsheet</query>
<use_cloud>false</use_cloud>
<reason>Built-in Excel analysis — no sandbox needed</reason>
</example>
```

### Skill Registration

The cloud-agent skill is registered like any other skill:

- Directory: `skills/library/cloud-agent/SKILL.md`
- Type: `SKILL` in `capabilities.yaml` with `fallback_tool: cloud_agent`
- Group: `cloud_skills` in `instances/xiaodazi/config/skills.yaml`
- IntentAnalyzer selects `cloud_skills` group when relevant → SKILL.md injected into system prompt → LLM decides

---

## 2 — ACP Protocol: Bidirectional

ACP (Agent Collaboration Protocol) is a lightweight HTTP + WebSocket protocol connecting the two codebases. It has two directions.

### Forward ACP (Local → Cloud): Skill Delegation

When the local agent's LLM selects the `cloud_agent` tool, the tool calls these endpoints:

```
POST   /acp/tasks                           Create a task
GET    /acp/tasks/{task_id}                 Query task status and result
GET    /acp/tasks/{task_id}/stream?last_seq=N   SSE event stream
PATCH  /acp/tasks/{task_id}/state           Pause / resume / cancel
POST   /acp/tasks/{task_id}/input           HITL input
```

Request body for task creation:

```json
{
  "task": "Research the AI agent market and write a report",
  "context": "User is interested in open-source projects",
  "conversation_id": "conv_xxx"
}
```

All endpoints require `Authorization: Bearer <acp_token>`.

### Reverse ACP (Cloud → Local): Mobile/IM Forwarding

When a Mobile/IM message arrives at the cloud and local is online, the cloud forwards it via WebSocket:

```
WS  /acp/ws    Persistent WebSocket connection (local → cloud)
```

The local agent connects on startup and maintains a heartbeat (30s interval). The cloud maintains an online registry: `{user_id: ws_connection}`.

Message flow:

```
IM webhook --> Cloud receives
                  |
                  v
            Local online? (check WS registry)
                  |
            +-----+-----+
            |           |
           YES          NO
            |           |
    Forward via WS    Cloud ChatService
    to local agent    handles directly
            |           |
    Local processes    Cloud responds
    (may delegate     to IM channel
     back to cloud
     via Skill)
            |
    Result via WS
    back to cloud
            |
    Cloud responds
    to IM channel
```

WebSocket message format (reuses existing event envelope):

```json
{
  "type": "acp_request",
  "seq": 1,
  "data": {
    "request_id": "req_xxx",
    "message": "Send the contract on my desktop to Zhang San",
    "channel": "wechat",
    "user_id": "user_xxx"
  }
}
```

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

## 3 — Authentication: Device Binding

The cloud has an account system. The local desktop app needs to authenticate without frequent logins.

### One-Time Binding

The user opens Settings > Cloud Collaboration in the Tauri app, enters the cloud URL, username, and password. The app calls:

```
POST /acp/auth/bind
{
  "username": "liuyi",
  "password": "***",
  "device_name": "MacBook-Pro-liuyi"
}
```

The cloud verifies credentials (reuses existing `AuthService.authenticate()`), generates:

| Token | Lifetime | Purpose | Storage |
|---|---|---|---|
| `acp_token` | 90 days | Daily ACP request auth | Keychain |
| `refresh_token` | Permanent (revocable) | Silent refresh of `acp_token` | Keychain |
| `device_id` | Permanent | Identifies this device | Keychain |

### Silent Refresh

The local `ACPClient` checks token expiry before each request. When `acp_token` is within 7 days of expiry:

```
POST /acp/auth/refresh
{ "refresh_token": "..." }
--> { "acp_token": "new_token_90_days" }
```

### Security

| Risk | Mitigation |
|---|---|
| Token leak | Stored in OS Keychain (macOS) / Credential Manager (Windows) |
| Refresh token leak | Bound to `device_id`; revoke via cloud web UI |
| Man-in-the-middle | HTTPS enforced in production |
| Device lost | User revokes device binding from cloud web UI; tokens invalidated immediately |
| Brute-force bind | Rate limit: 5 attempts/minute + lockout |

### Why Not Reuse Existing Web JWT?

The cloud's existing JWT is designed for browser sessions (24h expiry, no refresh, no device binding). ACP needs a separate token system for machine-to-machine long-lived access.

---

## 4 — Local Implementation

### New Files

| File | Purpose |
|---|---|
| `skills/library/cloud-agent/SKILL.md` | Delegation boundary guide with Few-Shot examples |
| `tools/cloud_agent.py` | `BaseTool` subclass — Forward ACP call + event tunneling bridge |
| `core/acp/client.py` | `ACPClient` — HTTP + SSE consumer + token auto-refresh |
| `core/acp/models.py` | ACP data models (`ACPTask`, `ACPEvent`, `ACPUser`) |
| `core/acp/token_store.py` | Keychain / encrypted config storage for tokens |
| `core/acp/connection.py` | WebSocket persistent connection for Reverse ACP + heartbeat |

### Modified Files

| File | Change |
|---|---|
| `config/capabilities.yaml` | Add `cloud_agent` tool registration (type: TOOL, fallback for cloud-agent SKILL) |
| `instances/xiaodazi/config/skills.yaml` | Add `cloud_skills` group |

### cloud_agent Tool (Pseudocode)

```python
class CloudAgentTool(BaseTool):
    name = "cloud_agent"
    description = "Delegate a task to the cloud agent"

    async def execute(self, params, context):
        task = await acp_client.create_task(
            task=params["task"],
            context=params.get("context"),
        )
        final_result = ""
        async for event in acp_client.stream_events(task.task_id):
            if event.type == "acp_tool_start":
                await self._emit_progress(context, phase="tool_call",
                    tool=event.data["tool"], status="running")
            elif event.type == "acp_tool_end":
                await self._emit_progress(context, phase="tool_call",
                    tool=event.data["tool"], status="done",
                    summary=event.data["summary"])
            elif event.type == "acp_text_delta":
                final_result += event.data["delta"]
            elif event.type == "acp_task_completed":
                final_result = event.data.get("result_summary", final_result)
                break
        return {"success": True, "result": final_result}

    async def _emit_progress(self, context, **progress):
        if context.event_manager:
            await context.event_manager.message.emit_message_delta(
                session_id=context.session_id,
                conversation_id=context.conversation_id,
                delta={"type": "cloud_progress", "content": progress},
            )
```

The `_emit_progress` pattern follows the existing HITL timeout event in `core/tool/executor.py` (lines 342-366).

---

## 5 — Cloud Implementation

### New Files

| File | Purpose |
|---|---|
| `routers/acp.py` | ACP endpoints: auth, tasks, SSE stream, WebSocket, control |
| `services/acp_service.py` | Business logic: wraps ChatService, event mapping, local-online routing |
| `services/acp_auth_service.py` | Device binding, ACP token issue / verify / refresh |
| `infra/database/models/acp.py` | `acp_devices` + `acp_tasks` tables |
| `infra/database/crud/acp.py` | CRUD operations for ACP tables |

### Modified Files

| File | Change |
|---|---|
| `main.py` | `app.include_router(acp_router)` (1 line) |

### ACP Service (Core Logic)

```python
class ACPService:
    async def create_and_run_task(self, task, context, user_id, device_id):
        """Forward ACP: wrap ChatService.chat()"""
        # 1. Insert into acp_tasks table
        # 2. Call ChatService.chat(message=task, user_id=user_id, stream=True)
        #    (ChatService launches Agent internally, events go to Redis)
        # 3. Return task_id + session_id

    async def stream_task_events(self, task_id, last_seq):
        """Event tunnel: map internal events to ACP event types"""
        # 1. Look up session_id from acp_tasks
        # 2. Call redis_manager.subscribe_events(session_id, after_id=last_seq)
        # 3. Map each internal event to ACP event type:
        #    content_start(tool_use)  -> acp_tool_start
        #    content_stop(tool_use)   -> acp_tool_end
        #    content_delta(text)      -> acp_text_delta
        #    message_delta(thinking)  -> acp_thinking
        #    message_stop             -> acp_task_completed
        # 4. Yield mapped events

    async def route_request(self, message, user_id, channel):
        """Reverse ACP: Mobile/IM routing"""
        ws = self.online_registry.get(user_id)
        if ws and ws.is_connected:
            # Forward to local agent via WebSocket
            result = await self._forward_to_local(ws, message, user_id)
            return result
        else:
            # Cloud fallback: handle directly
            return await self._handle_on_cloud(message, user_id, channel)
```

### Database Tables

```python
class ACPDevice(Base):
    __tablename__ = "acp_devices"
    id: str              # device_id
    user_id: str         # FK -> users.id
    device_name: str
    refresh_token_hash: str
    is_active: bool
    created_at: datetime
    last_seen_at: datetime

class ACPTask(Base):
    __tablename__ = "acp_tasks"
    id: str              # task_id
    user_id: str         # FK -> users.id
    device_id: str       # FK -> acp_devices.id
    status: str          # submitted/working/completed/failed/canceled
    task_description: str
    context: JSONB
    session_id: str      # Maps to ChatService session (for event subscription)
    result_summary: str
    created_at: datetime
    completed_at: datetime
```

---

## 6 — Event Tunneling and Progress Tracking

### Problem

The cloud agent internally runs a full agent loop (intent → plan → tool calls → synthesis). The local user needs real-time visibility into this execution, not just a spinner.

### Solution: Event Tunneling

The cloud agent's internal events are streamed through ACP SSE to the local `cloud_agent` tool, which bridges them into the local event system.

```
Cloud Agent         ACP SSE Stream       Local cloud_agent    Frontend
(internal)                               Tool
    |                   |                    |                   |
 thinking          acp_thinking -------> message_delta       Progress
                                         {cloud_progress}    card
    |                   |                    |                   |
 tool: exa_search  acp_tool_start -----> message_delta       Tool badge
                                         {cloud_progress}    (spinning)
    |                   |                    |                   |
 8 results found   acp_tool_end -------> message_delta       Tool done
                                         {cloud_progress}
    |                   |                    |                   |
 "Analysis shows..." acp_text_delta ---> content_delta(text)  Streaming
                                                              text
    |                   |                    |                   |
 task completed    acp_task_completed --> tool_result          ToolBlock
                                                              done
```

### ACP SSE Event Types

| Event | Trigger | Data |
|---|---|---|
| `acp_task_status` | Task state change | `{task_id, status}` |
| `acp_thinking` | Cloud agent reasoning | `{text}` |
| `acp_tool_start` | Cloud starts a tool call | `{tool, input_summary}` |
| `acp_tool_end` | Cloud tool finished | `{tool, summary, duration_ms}` |
| `acp_text_delta` | Cloud agent text output | `{delta}` |
| `acp_progress` | Structured progress | `{phase, completed, total, current}` |
| `acp_input_needed` | HITL required | `{prompt, options}` |
| `acp_task_completed` | Task finished | `{result_summary}` |

### Frontend: CloudProgressCard

The frontend adds a `CloudProgressCard` component that renders `message_delta {type: "cloud_progress"}` events as a live execution timeline:

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

### Reconnection

- **Short disconnect**: `GET /acp/tasks/{id}/stream?last_seq=N` resumes from the last received sequence number.
- **Long disconnect**: Cloud returns an `acp_gap` event with a task snapshot. Frontend renders a collapsed summary.
- **Page refresh**: `GET /acp/tasks/{id}` returns current task state for progress card recovery.

---

## 7 — Mobile/IM Entry

### How It Works

Mobile/IM messages arrive at the cloud via platform webhooks (only the cloud has a public endpoint). The cloud routes based on local online status.

```
IM Platform (WeChat/Feishu/DingTalk)
    |
    | Webhook
    v
Cloud: routers/channels.py
    |
    v
Cloud: acp_service.route_request()
    |
    +-- Local online (WS connected)
    |       |
    |   Forward via WebSocket to local agent
    |       |
    |   Local agent processes
    |   (may delegate back to cloud via cloud_agent Skill)
    |       |
    |   Result returns via WebSocket
    |       |
    |   Cloud replies to IM platform
    |
    +-- Local offline
            |
        Cloud ChatService handles directly
        (degraded: no desktop operations)
            |
        Cloud replies to IM platform
```

### Online Status

- Local agent establishes a WebSocket connection to `WS /acp/ws` on startup
- Heartbeat every 30 seconds
- Cloud maintains `{user_id: ws_connection}` registry
- WebSocket disconnect → cloud marks user's local as offline

### Degradation

When local is offline, the cloud agent can still do:
- Web search, writing, Q&A, translation
- Sandbox code execution and project build
- Scheduled task management

It cannot do:
- Desktop file operations
- UI automation, screenshots
- Local app control
- Access local-only files

When a request requires local capabilities but local is offline, the cloud responds: "Your computer is not on right now. I'll do what I can — want me to queue the rest for when you're back online?"

---

## 8 — Phased Implementation

### Phase 0.5: Direct API Call (Current — Zero Cloud Changes)

**Goal**: Local cloud_agent Skill calls the cloud's existing `/api/v1/chat/stream` endpoint directly. No custom ACP protocol, no cloud-side changes.

| Side | Work |
|---|---|
| **Cloud** | **Zero changes** — uses the existing containerized deployment as-is |
| **Local** | `core/cloud/client.py` (CloudClient: login + chat_stream SSE), `tools/cloud_agent.py` (simplified), `skills/library/cloud-agent/SKILL.md`, `config/capabilities.yaml`, `skills.yaml` |
| **Auth** | Reuses existing username/password → JWT (same as web frontend) |
| **Verify** | `python scripts/test_cloud_e2e.py --cloud-url http://cloud:8001` |

**Key insight**: The cloud already provides a complete agent-as-a-service API (`/api/v1/chat/stream`). The SSE events use the same zenflux format as the local agent, so no event mapping layer is needed. The cloud_agent tool just consumes the SSE stream and bridges `content_delta` / `content_start(tool_use)` events to local `cloud_progress` message deltas.

### Phase 1: Forward ACP + Cloud Skill (Local delegates to cloud)

**Goal**: Add task-level tracking, structured progress events, and reconnection support on top of Phase 0.5.

| Side | Work |
|---|---|
| **Cloud** | `routers/acp.py` (task endpoints + SSE wrapper), `services/acp_service.py` (task state machine, event mapping) |
| **Local** | `core/acp/client.py` (task lifecycle: create/stream/control), enhanced `tools/cloud_agent.py` |
| **Frontend** | `CloudBindSettings.vue` (settings page), `CloudProgressCard.vue` (progress rendering), `useChat.ts` (cloud_progress handler) |
| **Verify** | Local sends "run this Python script" → cloud sandbox executes → progress streams back → result displayed |

### Phase 2: Reverse ACP + WebSocket (Mobile/IM routes to local)

**Goal**: Mobile/IM messages are forwarded to local agent when it is online.

| Side | Work |
|---|---|
| **Cloud** | WebSocket endpoint in `routers/acp.py`, online registry in `acp_service.py`, `route_request()` in channel handling |
| **Local** | `core/acp/connection.py` (WebSocket client + heartbeat + request handler) |
| **Verify** | WeChat message → cloud → local online → forward → local processes → result back to WeChat |

### Phase 3: Memory/Context Sync + Scheduled Task Hosting

**Goal**: Both agents share user memory and preferences. Scheduled tasks survive local shutdown.

| Work |
|---|
| Memory sync protocol (MEMORY.md delta sync or API-based) |
| Scheduled task migration: local creates → cloud persists → cloud executes at scheduled time |
| Task result push to Mobile/IM when completed |

### Phase 4: Multi-Channel + Degradation Polish

**Goal**: Full multi-channel support with graceful degradation.

| Work |
|---|
| Channel adapters: WeChat, Feishu, DingTalk, Telegram |
| Degradation UX: "Your computer is off, I'll queue this" |
| Task queue: requests requiring local capabilities are queued and executed when local comes online |

---

## Tech Stack

| Component | Local | Cloud |
|---|---|---|
| ACP Client | `httpx` + `httpx-sse` | — |
| ACP Server | — | FastAPI (`routers/acp.py`) |
| WebSocket | `websockets` client | FastAPI WebSocket endpoint |
| Token storage | `keyring` (Keychain) | PostgreSQL (`acp_devices`) |
| Event buffer | — | Redis (existing `subscribe_events`) |
| SSE | — | `StreamingResponse` (existing pattern) |

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| Cloud Skill (SKILL.md + fallback_tool), not a hardcoded router | LLM-First: boundary defined in prompt, not code. Consistent with all other skills. |
| Bidirectional ACP, not cloud-centric | Local-first: local is always the brain when online. Cloud is a relay, not a master. |
| Separate ACP Token from Web JWT | Different lifecycle: desktop app needs 90-day tokens with refresh; web needs 24h session tokens. |
| Event tunneling via existing `message_delta` | Zero new event infrastructure. Frontend adds one component. Follows existing patterns (HITL, search, intent). |
| No independent gateway service | Routing logic is a single function (`route_request`) in `acp_service.py`. The existing `channels.py` router is the entry point. |
| 3 delegation reasons only | Conservative boundary. Most tasks stay local (faster, private, offline-capable). Cloud only for: persistent execution, sandbox, mobile reachability. |
