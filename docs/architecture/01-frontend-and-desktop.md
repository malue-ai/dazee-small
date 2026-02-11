# 01 — Frontend & Desktop App

> Tauri + Vue 3 desktop application with Apple Liquid design, real-time streaming, and human-in-the-loop interactions.

[< Back to Overview](README.md) | [Next: API & Services >](02-api-and-services.md)

---

## Design Goals

1. **Desktop-native experience** — Not a web app in a wrapper. Tauri provides native window management, file system access, and system tray integration.
2. **Real-time streaming** — Users see the agent "thinking" in real-time via SSE/WebSocket, not waiting for a complete response.
3. **Human-in-the-loop (HITL)** — Dangerous operations (file deletion, system changes) require explicit user confirmation before execution.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│ Tauri Shell (Rust)                                                    │
│   Window Manager (1200x800) ──→ IPC Bridge ──→ Bundled Python Backend │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│ Vue 3 Application                                                     │
│                                                                       │
│   Views (Chat / Skills / Settings / Knowledge)                        │
│     └─→ Pinia Stores (chat / conversation / agent / skill)            │
│           └─→ Composables (useChat / useSSE / useWebSocketChat)       │
│                 └─→ API Layer (Axios)                                  │
│                       ├─→ POST /api/v1/chat (SSE)                     │
│                       ├─→ WS /api/v1/ws/chat                          │
│                       └─→ REST endpoints                               │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│ FastAPI Backend                                                       │
│   SSE endpoint  ·  WebSocket endpoint  ·  REST endpoints              │
└──────────────────────────────────────────────────────────────────────┘
```

## Tech Stack

| Component | Technology | Purpose |
|---|---|---|
| Framework | Vue 3.4 + TypeScript | Reactive UI with type safety |
| Desktop | Tauri 2.10 | Native shell, cross-platform (macOS/Windows/Linux) |
| Styling | Tailwind CSS 4.1 | Utility-first CSS with design tokens |
| State | Pinia 2.1 | Centralized state management |
| Icons | Lucide Vue Next | Consistent line-icon system |
| Markdown | markstream-vue | Real-time streaming markdown rendering |
| Routing | Vue Router 4.2 | SPA navigation |

## Design System — Apple Liquid

The UI follows an Apple-inspired liquid glass aesthetic with an amber yellow accent:

| Element | Specification |
|---|---|
| Style | Frosted glass (`backdrop-filter: blur`) |
| Primary Color | Amber `#F59E0B` (buttons, active states, accents) |
| Base | Pure white + grayscale system |
| Dark Mode | Not supported (light only) |
| Border | `rgba(0,0,0,0.06)` — subtle, consistent |
| Corner Radius | Modals `24px`, Cards `16px`, Buttons `12px`, Badges `8px` |

Glass effect classes:
- `glass-sidebar` — `rgba(255,255,255,0.72)` + `blur(20px)`
- `glass-header` — `rgba(255,255,255,0.85)` + `blur(16px)`
- `glass-footer` — `rgba(255,255,255,0.9)` + `blur(12px)`

All colors are defined as CSS custom properties in `frontend/src/style.css` via `@theme`, ensuring a single source of truth.

## Communication Protocols

### SSE (Primary)

The primary chat protocol uses Server-Sent Events over a POST request:

```
POST /api/v1/chat?format=zenflux
Content-Type: application/json

→ SSE stream with event types:
  message_start    — new assistant message
  content_delta    — text chunk / thinking chunk
  tool_use_start   — tool call begins
  tool_result      — tool execution result
  message_stop     — response complete
```

Key features:
- Reconnection via `lastEventId`
- Structured 5-layer event system: Session → Conversation → Message → Content → System

### WebSocket (Alternative)

A persistent WebSocket connection for lower-latency scenarios:

```
WS /api/v1/ws/chat

Frame protocol: { type: "req"|"res"|"event", method, params, id }
Methods: chat.send, chat.abort
```

Key features:
- Heartbeat every 30 seconds
- Delta throttling (150ms batching)
- Exponential backoff reconnection

## Key Interactions

### Real-Time Streaming

The `useSSE` composable manages the streaming lifecycle:

```
User types message
  → useChat.send()
  → useSSE connects to POST /api/v1/chat
  → content_delta events arrive
  → markstream-vue renders markdown incrementally
  → User sees response "typing" in real-time
```

### HITL Confirmation

When the agent attempts a dangerous operation (file deletion, system setting change):

```
Agent calls tool with requires_confirmation=true
  → Backend emits hitl_confirmation_request event
  → Frontend shows HITLConfirmModal
  → User clicks Approve / Reject
  → POST /api/v1/hitl/{confirmation_id}/respond
  → Agent continues or aborts
```

### Rollback

If the agent makes an unwanted change:

```
User says "undo that" or clicks rollback
  → Intent analyzer detects wants_rollback=true
  → RollbackOptionsModal shows available snapshots
  → User selects snapshot to restore
  → StateConsistencyManager reverts changes
```

### Plan Widget

For complex multi-step tasks, a sidebar widget shows real-time progress:

```
Agent creates plan (plan_todo tool)
  → plan_update events stream to frontend
  → PlanWidget renders TODO items with status
  → Items update from pending → in_progress → completed
```

## Tauri Integration

The desktop application bundles the Python backend as an external binary:

| Aspect | Detail |
|---|---|
| Window | 1200x800 default, 800x600 minimum |
| Backend | `zenflux-backend` sidecar process |
| Dev URL | `http://localhost:5174` (Vite dev server) |
| Build | `npm run tauri:build` produces platform-specific installer |

## Frontend Directory Structure

```
frontend/src/
├── api/            # HTTP/WebSocket client layer
├── components/     # Vue components
│   ├── chat/       #   MessageList, ChatInputArea, MarkdownRenderer, ToolBlock
│   ├── common/     #   GuideOverlay, shared components
│   ├── modals/     #   HITLConfirmModal, RollbackOptionsModal
│   ├── sidebar/    #   PlanWidget
│   └── workspace/  #   FileTree, FilePreview
├── composables/    # useChat, useSSE, useWebSocketChat, useHITL, useFileUpload
├── layouts/        # DashboardLayout, DefaultLayout
├── stores/         # Pinia: chat, conversation, session, agent, skill, workspace
├── types/          # TypeScript type definitions
├── views/          # Chat, Skills, Settings, Knowledge, Onboarding
└── style.css       # Design system tokens (@theme)
```

## Highlights

- **Streaming-first UX** — Users never stare at a loading spinner. Every token is rendered as it arrives.
- **HITL safety net** — The agent cannot silently modify files or settings without user approval.
- **Unified design tokens** — All colors, radii, and shadows defined in one `@theme` block, preventing style drift.
- **Dual transport** — SSE for simplicity, WebSocket for persistent connections. Framework supports both seamlessly.

## Limitations & Future Work

- **No dark mode** — Current design is light-only. Adding dark mode requires extending the `@theme` token system.
- **No offline mode** — Frontend requires the backend process. True offline (bundled LLM) is a future goal.
- **Limited mobile** — Tauri 2.x has experimental mobile support, but the UI is designed for desktop viewports.
- **MCP Apps iframe** — The iframe integration for rich tool UIs works but has limited cross-origin communication capabilities.

---

[< Back to Overview](README.md) | [Next: API & Services >](02-api-and-services.md)
