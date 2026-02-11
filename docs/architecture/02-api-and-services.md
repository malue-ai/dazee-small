# 02 — API & Services

> Three-layer architecture (Routers → Services → Core) with a preprocessing pipeline, session management, and multi-channel gateway.

[< Prev: Frontend & Desktop](01-frontend-and-desktop.md) | [Back to Overview](README.md) | [Next: Intent & Routing >](03-intent-and-routing.md)

---

## Design Goals

1. **Protocol-agnostic services** — Business logic lives in `services/`, reusable across HTTP, WebSocket, and gateway channels.
2. **Streaming-first** — Chat responses are always streamable. Sync mode collects the stream internally.
3. **Multi-channel** — The same agent can be reached via browser, Telegram, Feishu, or any future channel.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│ Clients                                                             │
│   Browser (SSE / WS)    Telegram Bot    Feishu Bot                  │
└──────┬──────────┬───────────┬──────────────┬────────────────────────┘
       │          │           │              │
       ▼          ▼           ▼              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Routers (Protocol Layer)                                            │
│                                                                     │
│   chat.py ─── POST /api/v1/chat          conversation.py ── CRUD   │
│   websocket.py ── WS /api/v1/ws/chat     skills.py ── Skill mgmt  │
│   gateway.py ── Gateway status            settings.py ── Config    │
└──────┬──────────┬─────────────────────┬─────────────┬──────────────┘
       │          │                     │             │
       ▼          ▼                     ▼             ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Services (Business Logic)                                           │
│                                                                     │
│   ChatService ──→ SessionService      ConversationService           │
│       │                               SettingsService               │
│       └──→ AgentRegistry                                            │
│                 │                                                    │
└─────────────────┼───────────────────────────────────────────────────┘
                  ▼
┌─────────────────────────┐    ┌──────────────────────────────────────┐
│ Core Engine              │    │ Gateway                              │
│   Agent (RVR-B)          │◄───│   ChannelManager → GatewayBridge     │
└──────────────────────────┘    │       → SessionMapper → ChatService  │
                                └──────────────────────────────────────┘
```

## Three-Layer Architecture

| Layer | Directory | Responsibility |
|---|---|---|
| **Routers** | `routers/` | HTTP/WS protocol handling, request validation, response formatting |
| **Services** | `services/` | Business logic, session lifecycle, agent orchestration |
| **Core** | `core/` | Agent engine, tools, memory, LLM — no knowledge of HTTP |

This separation means:
- Routers only parse requests and format responses
- Services can be called by routers, WebSocket handlers, gateway bridge, or scheduled tasks
- Core modules have zero dependency on the web framework

## Chat Preprocessing Pipeline

Every chat request passes through a preprocessing pipeline before reaching the agent:

```
Router → ChatService.chat(request)
           │
           ├─→ PreprocessingHandler.process(messages)
           │       │
           │       ├─→ IntentAnalyzer.analyze(messages)
           │       │       └──→ IntentResult
           │       │
           │       └──→ intent + preface
           │
           ├─→ SessionService.get_or_create_session()
           │
           └─→ Agent.execute(messages, intent)
                   └──→ Stream events back to ChatService
```

The `PreprocessingHandler` performs:
1. **Intent analysis** — Determines complexity, required skill groups, whether to skip memory
2. **Preface generation** (optional) — Streams a brief acknowledgment while the agent prepares
3. **Intent event emission** — Notifies the frontend of the classified intent

## API Endpoints

### Chat

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/chat` | Unified chat endpoint (SSE stream) |
| POST | `/api/v1/session/{id}/stop` | Stop a running session |
| POST | `/api/v1/session/{id}/rollback` | Rollback to a snapshot |
| GET | `/api/v1/session/{id}` | Get session info |

### Conversations

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/conversations` | List conversations |
| POST | `/api/v1/conversations` | Create conversation |
| GET | `/api/v1/conversations/{id}/messages` | Get messages (cursor pagination) |
| GET | `/api/v1/conversations/search` | Full-text search via FTS5 |
| DELETE | `/api/v1/conversations/{id}` | Delete conversation |

### Skills & Settings

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/skills` | List all skills with status |
| POST | `/api/v1/skills/{name}/refresh` | Refresh skill status |
| GET | `/api/v1/settings` | Get current settings |
| PUT | `/api/v1/settings` | Update settings |
| GET | `/api/v1/models` | List available LLM models |

### WebSocket

| Endpoint | Description |
|---|---|
| WS `/api/v1/ws/chat` | Persistent chat connection |

Methods: `chat.send`, `chat.abort`. Heartbeat every 30s, delta throttling at 150ms.

## Session Management

`SessionService` manages the lifecycle of active chat sessions:

```
Session States:
  IDLE → RUNNING → COMPLETED
                 → STOPPED (user abort)
                 → ERROR

Each session holds:
  - session_id (UUID)
  - conversation_id
  - agent reference (cloned per session)
  - stop_event (asyncio.Event)
  - HITL confirmation queue
  - state snapshots (for rollback)
```

Key behaviors:
- **Stop** — Setting the `stop_event` causes the agent loop to terminate gracefully after the current turn
- **HITL** — Confirmation requests are queued; the agent blocks until the user responds via the HITL endpoint
- **Rollback** — `StateConsistencyManager` restores file system and environment state from snapshots

## Multi-Channel Gateway

The gateway system bridges external messaging platforms to the internal `ChatService`:

```
┌─────────────────────┐     ┌───────────────────────────────┐     ┌─────────────┐
│ Channel Adapters     │     │ Gateway Core                  │     │ Internal    │
│                     │     │                               │     │             │
│  Telegram (polling) ─┼──→  ChannelManager ──→ GatewayBridge ──→  │ ChatService │
│  Feishu (WebSocket) ─┤     │       └──→ SessionMapper ────┼──→  │             │
└─────────────────────┘     └───────────────────────────────┘     └─────────────┘
```

### Flow

1. **Inbound** — `ChannelAdapter` receives a message, wraps it as `InboundMessage`
2. **Mapping** — `SessionMapper` maps `channel_id + sender_id` → internal `user_id / conversation_id`
3. **Routing** — `GatewayBridge` resolves which agent should handle the message via `GatewayBinding` config
4. **Execution** — Calls `ChatService.chat(stream=True)`, accumulates the event stream
5. **Delivery** — Sends the accumulated text response back through the channel adapter

### Configuration

Gateway bindings are defined in `config/gateway.yaml`:

```yaml
channels:
  - type: telegram
    token: ${TELEGRAM_BOT_TOKEN}
    bind_agent: xiaodazi
  - type: feishu
    app_id: ${FEISHU_APP_ID}
    app_secret: ${FEISHU_APP_SECRET}
    bind_agent: xiaodazi
```

## Conversation Persistence

`ConversationService` handles CRUD operations via `infra/local_store/`:

| Feature | Implementation |
|---|---|
| Storage | SQLite with WAL mode (aiosqlite) |
| Full-text search | FTS5 index on message content |
| Pagination | Cursor-based (by message timestamp) |
| File attachments | Stored in instance-isolated directory |

## Highlights

- **Protocol-agnostic** — Adding a new channel (e.g., Discord, Slack) requires only implementing `ChannelAdapter`, zero changes to business logic.
- **Preprocessing pipeline** — Intent analysis happens before agent execution, enabling smart routing and resource optimization.
- **Graceful shutdown** — FastAPI lifespan manager ensures gateway channels stop, agents clean up, and schedulers halt on shutdown.

## Limitations & Future Work

- **No gRPC** — Currently HTTP/WS only. gRPC support would benefit high-throughput internal service communication.
- **In-memory sessions** — Sessions are not persisted across server restarts. Planned: session recovery from conversation history.
- **Gateway channels** — Only Telegram and Feishu are implemented. Slack, Discord, and webhook channels are planned.
- **No rate limiting** — The API layer has no built-in rate limiting. Should be added before public deployment.

---

[< Prev: Frontend & Desktop](01-frontend-and-desktop.md) | [Back to Overview](README.md) | [Next: Intent & Routing >](03-intent-and-routing.md)
