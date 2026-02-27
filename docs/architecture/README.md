# xiaodazi (小搭子) — Architecture Overview

> A local-first desktop AI agent with persistent memory, 150+ skills, and multi-model flexibility.

---

## What is xiaodazi?

xiaodazi (小搭子, meaning "little buddy") is an open-source AI agent designed to **live on your desktop**. Unlike cloud-only AI assistants, it runs locally as a Tauri desktop application, keeps all data on your machine, and can operate your computer directly — managing files, automating apps, generating documents, and remembering your preferences across sessions.

It is a personal AI assistant that combines 150+ skills, three-layer memory, and multi-model support into a native desktop experience.

**Key differentiators:**
- **Local-first** — Your data (conversations, memory, files) stays on your machine. SQLite + FTS5 + sqlite-vec, no cloud database required. LLM inference uses cloud APIs by default, with local model support (Ollama/LM Studio) for fully offline use.
- **Persistent memory** — The agent remembers your preferences, habits, and past interactions via a user-editable memory file + semantic vector search.
- **150+ plug-and-play skills with lazy allocation** — From Excel analysis to UI automation, classified on a 2D matrix (OS × dependency). Only intent-relevant skills are loaded per request (0-15 out of 150+), so the library scales without token overhead. Add new skills by writing a Markdown file.
- **Multi-model flexibility** — Switch between Claude, OpenAI, Qwen, DeepSeek, Gemini, GLM (智谱), or local models (Ollama) by changing one config value.
- **Smart error recovery** — The RVR-B execution loop classifies errors, backtracks from failed approaches, and degrades gracefully instead of crashing.

---

## Design Philosophy

Four principles govern every architectural decision:

### LLM-First

All semantic tasks — intent classification, complexity inference, tool selection, backtrack decisions — are performed by the LLM, not by keyword matching or rule-based systems. Hard-coded rules are used only for deterministic tasks: format validation, numeric calculation, security boundaries.

*Why it matters:* "Don't make a PPT" correctly results in zero PPT skills being loaded. A keyword system would match "PPT" and load the wrong tools.

### Prompt-Driven

The agent's behavior is defined by a natural-language persona prompt (`prompt.md`). The framework uses an LLM to analyze this prompt and auto-generate:
- An agent configuration schema (`agent_schema.yaml`)
- Complexity-graded system prompts (simple/medium/complex)
- Tool and skill recommendations

*Why it matters:* Non-technical users can customize agent behavior by editing a Markdown file, not YAML configs or Python code.

### Local-First

All data storage is local by default:
- **Messages & conversations** — SQLite with WAL mode
- **Full-text search** — SQLite FTS5 (built-in, zero-config)
- **Semantic vectors** — sqlite-vec (optional, single file)
- **User memory** — Plain Markdown file (`MEMORY.md`)
- **File attachments** — Local filesystem, instance-isolated

No cloud database, no external vector store, no third-party analytics. LLM inference requires a cloud API (Claude, OpenAI, Qwen, GLM, etc.) by default, but local models via Ollama or LM Studio are fully supported for users who need complete offline operation.

### Skills-First

Capabilities are modular skills, not hard-coded features. Each skill is a directory with a `SKILL.md` file that describes when and how to use it. The framework handles discovery, dependency checking, status management, and intent-driven injection.

Skills are classified on two axes (2D classification matrix):
- **OS compatibility**: common / darwin (macOS) / win32 / linux
- **Dependency complexity**: builtin (zero-config) / lightweight (pip install) / external (CLI/app) / cloud_api (API key)

Despite having 150+ skills, the system uses **lazy allocation**: zero skills are loaded by default. Each request activates only the skill groups matching the user's intent (typically 0-15 out of 150+). Token cost scales with task complexity, not library size — a simple "hi" costs 0 skill tokens; a complex multi-tool task costs ~1200 tokens. The library can grow to 500+ without impacting simple queries.

*Why it matters:* The agent works out of the box with builtin skills, progressively unlocks more capabilities as users install dependencies, and never pays the token cost for skills it doesn't need.

---

## Full-Stack Architecture

The system is organized into five layers, from user interface down to infrastructure:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Layer 1 — User Interface                                                    │
│   Tauri Desktop Shell (Rust)                                                │
│   Vue 3 SPA (Chat / Skills / Settings)                                      │
│   Apple Liquid Design System                                                │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Layer 2 — API & Services                                                    │
│   FastAPI Routers (HTTP REST + SSE + WebSocket)                             │
│   Services (Chat / Session / Conversation / Settings)                       │
│   Multi-Channel Gateway (Telegram / Feishu)                                 │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Layer 3 — Agent Engine                                                      │
│   Intent Analyzer (LLM semantic, 4-layer cache)                             │
│   RVR-B Executor (React-Validate-Reflect-Backtrack)                         │
│   Context Engineering (3-phase inject, compress, KV-Cache)                  │
│   Plan Manager (DAG tasks, progress tracking)                               │
│   Adaptive Terminator (multi-signal)                                        │
├──────────────────────────────────┬──────────────────────────────────────────┤
                 ▼                                    ▼
┌──────────────────────────────────────┐  ┌──────────────────────────────────┐
│ Layer 4 — Capability                  │  │ Layer 5 — Infrastructure         │
│   Tool System (2-layer, 3-level)      │  │   LLM Abstraction (6 providers)  │
│   Skill Ecosystem (150+, 20 groups)   │  │   Local Storage (SQLite + FTS5)  │
│   Memory System (MD + FTS5 + Mem0)    │  │   Instance System (isolation)    │
│   Knowledge Base (FTS5 + embeddings)  │  │   Evaluation (3-layer grading)   │
│   Playbook Learning (online)          │  │   Monitoring (failure + audit)   │
└──────────────────────────┬───────────┘  └──────────────────────────────────┘
                           └──────────────────────────▲
```

### Layer 1 — User Interface

A native desktop application built with **Tauri 2.10** (Rust shell) and **Vue 3.4** (TypeScript SPA). The UI follows an Apple-inspired liquid glass design with amber yellow accent. Communication uses SSE for streaming chat and WebSocket for persistent connections. Key UI features include real-time markdown rendering, HITL confirmation dialogs for dangerous operations, a plan progress widget, and a skill management market.

### Layer 2 — API & Services

A strict three-layer architecture: **Routers** handle protocol (HTTP/WS), **Services** contain business logic (reusable across protocols), **Core** runs the agent engine (no web framework knowledge). The `ChatService` orchestrates a preprocessing pipeline: intent analysis → session management → agent execution → event streaming. A **Gateway** system bridges external channels (Telegram, Feishu) to the same `ChatService`, enabling multi-channel access.

### Layer 3 — Agent Engine

The brain of the system. Every user request first passes through the **Intent Analyzer**, which uses an LLM to classify complexity (simple/medium/complex), detect behavioral signals (follow-up, stop, rollback), and identify relevant skill groups. The classified request then enters the **RVR-B Executor** — a React-Validate-Reflect-Backtrack loop that:

1. **Reacts** — Calls the LLM to generate a response and/or tool calls
2. **Validates** — Executes tools and checks results
3. **Reflects** — Classifies any errors (transient? systematic? critical?)
4. **Backtracks** — If needed, cleans context pollution and tries alternative approaches

The engine is surrounded by supporting systems: **Context Engineering** manages what goes into the LLM's context window (three-phase injection, tool result compression, progressive history decay, KV-Cache optimization). The **Plan Manager** handles multi-step task decomposition. The **Adaptive Terminator** evaluates multiple signals each turn (LLM completion, max turns, duration, failures, user stop, HITL) to decide when to stop.

### Layer 4 — Capability

The agent's hands. The **Tool System** uses a two-layer registry (global capabilities + instance-level dynamic tools) with three-level selection (core tools → capability matching → whitelist filtering). For simple tasks, only 4 core tools are loaded (~500 tokens); complex tasks get the full set (~3000 tokens).

The **Skill Ecosystem** provides 150+ plug-and-play skills classified on a 2D matrix (OS compatibility × dependency complexity) across 20 intent-driven groups. Despite the large library, lazy allocation means zero skills are loaded by default — only intent-matching groups are injected per request (typically 0-15 skills, ~0-1200 tokens). The library can scale to 500+ skills without impacting simple queries.

The **Memory System** combines three layers: `MEMORY.md` (user-editable source of truth), FTS5 (keyword search), and Mem0 (semantic vector search). Dual-write ensures consistency. Fusion search combines keyword precision with semantic recall. Memory is automatically extracted from conversations and injected into context with budget control (~500 tokens).

### Layer 5 — Infrastructure

The foundation. The **LLM Abstraction** provides a unified interface over 6 providers (Claude, OpenAI, Qwen, DeepSeek, Gemini, GLM) plus local models via Ollama. Format adapters handle protocol differences (Claude content blocks vs. OpenAI function calling vs. Gemini parts vs. GLM ChatGLM). A ModelRouter provides automatic failover with health tracking.

**Local Storage** uses SQLite exclusively — WAL mode for concurrent access, FTS5 for full-text search, sqlite-vec for optional vector similarity. The **Instance System** isolates each agent's data (DB, memory, vectors, snapshots, files) and uses Prompt-Driven configuration: write a prompt, get a configured agent.

The **Evaluation System** provides three-layer grading (code-based deterministic + LLM-as-Judge + human review), an automated E2E pipeline, 12-type failure detection, and token audit.

---

## Lifecycle of a Chat Request

To understand how the layers work together, here is the complete lifecycle of a single chat interaction:

```
User → Frontend → Router (POST /api/v1/chat, SSE stream)
                    │
                    ▼
              ChatService
                    │
                    ├─→ IntentAnalyzer.analyze() [< 200ms]
                    │       └──→ complexity=medium, groups=["writing"], skip_memory=false
                    │
                    └─→ Agent.execute(messages, intent)
                            │
                            ├── Setup ──────────────────────────────────────────
                            │   ├─→ Select tools (intent-driven pruning)
                            │   └─→ Context Engineering (3-phase injection)
                            │           ├─→ Memory: fetch user memory (3-source parallel, 500 tokens)
                            │           ├─→ Skills: load "writing" group instructions
                            │           └──→ Assembled messages + tools
                            │
                            ├── RVR-B Execution Loop ───────────────────────────
                            │   Each Turn:
                            │     Agent ──→ LLM: create message (stream)
                            │     LLM   ──→ Agent: text + tool_calls
                            │     Agent ──→ Frontend: stream content_delta events
                            │     Agent ──→ ToolExecutor: execute tool calls
                            │     ToolExecutor ──→ Agent: results (compressed if > 1500 chars)
                            │     Agent: validate results
                            │       └─ Error? → classify → CONTINUE / BACKTRACK / FAIL / ESCALATE
                            │     Agent: check termination conditions
                            │
                            └── Complete ────────────────────────────────────────
                                Agent ──→ ChatService: execution complete
                                ChatService: background flush memory, generate title
                                Router ──→ Frontend: message_stop
                                Frontend ──→ User: display complete response
```

**What happens in a typical medium-complexity request (e.g., "Write an article about AI trends"):**

1. **Intent** (~150ms) — Classified as `medium`, `skip_memory=false`, `groups=["writing"]`
2. **Memory** (~100ms) — User's writing style preferences loaded from MEMORY.md + Mem0
3. **Skills** — Writing-group skills (writing-assistant, style-learner, etc.) injected into prompt
4. **Tools** — Core tools + writing-related tools selected (~8 tools total)
5. **Execution** — 3-5 turns: plan → research → draft → refine → deliver
6. **Streaming** — Every token streamed to UI as generated
7. **Post-processing** — Memory fragments extracted and saved for future sessions

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Desktop Shell | Tauri 2.10 (Rust) | Native window, file access, cross-platform |
| Frontend | Vue 3.4 + TypeScript + Tailwind CSS 4.1 + Pinia | Reactive UI, state management |
| Backend | Python 3.12 + FastAPI + asyncio | Async API server |
| Communication | SSE + WebSocket + REST | Real-time streaming + persistent connections |
| Storage | SQLite (WAL) + FTS5 + sqlite-vec | Messages, full-text search, optional vectors |
| LLM | Claude, OpenAI, Qwen, DeepSeek, Gemini, GLM, Ollama | Multi-provider with failover |
| Memory | MEMORY.md + FTS5 + Mem0 | User-editable + keyword + semantic |
| Evaluation | Code graders + LLM-as-Judge + Human review | Three-layer quality assurance |

## Project Structure

```
zenflux_agent/
├── frontend/               # Vue 3 + Tauri desktop app
├── routers/                # FastAPI HTTP/WS endpoints
├── services/               # Business logic (protocol-agnostic)
├── core/
│   ├── agent/              # Agent orchestration + RVR-B execution
│   ├── routing/            # Intent analysis + routing
│   ├── context/            # Context engineering (injectors, compression)
│   ├── tool/               # Tool registry, selector, executor
│   ├── skill/              # Skill loader, group registry
│   ├── memory/             # Three-layer memory (Markdown + FTS5 + Mem0)
│   ├── playbook/           # Online learning (strategy extraction + matching)
│   ├── llm/                # LLM abstraction (6 providers + adapters)
│   ├── gateway/            # Multi-channel gateway (Telegram, Feishu)
│   ├── planning/           # Task planning + progress tracking
│   ├── termination/        # Adaptive termination strategies
│   ├── state/              # Snapshot / rollback
│   ├── monitoring/         # Failure detection, token audit
│   └── prompt/             # Prompt parsing + generation
├── tools/                  # Built-in tool implementations
├── instances/              # Agent instance configs (xiaodazi, _template)
├── skills/                 # Shared skill library (78+ skills)
├── config/                 # Global config (capabilities.yaml)
├── evaluation/             # E2E test suites + graders
├── models/                 # Pydantic data models
├── prompts/                # Prompt templates
└── infra/                  # Storage infrastructure (SQLite, cache)
```

---

## Deep Dive — Module Documentation

Read in order, top-down from user interface to infrastructure:

### User Interface
- **[01 — Frontend & Desktop App](01-frontend-and-desktop.md)** — Tauri + Vue 3, Apple Liquid design system, SSE/WebSocket streaming, HITL interactions

### Service Layer
- **[02 — API & Services](02-api-and-services.md)** — Three-layer architecture, preprocessing pipeline, session management, multi-channel gateway

### Agent Engine
- **[03 — Intent Analysis & Routing](03-intent-and-routing.md)** — LLM-First semantic analysis, four-layer caching, skill group mapping
- **[04 — Agent Execution Framework](04-agent-execution.md)** — RVR-B loop, backtracking, adaptive termination, state consistency
- **[05 — Context Engineering](05-context-engineering.md)** — Three-phase injection, compression, KV-Cache optimization

### Capability Layer
- **[06 — Tool System](06-tool-system.md)** — Two-layer registry, three-level selection, intent-driven pruning
- **[07 — Skill Ecosystem](07-skill-ecosystem.md)** — 150+ skills, 2D classification, lifecycle management, progressive unlock
- **[08 — Memory System](08-memory-system.md)** — Three-layer memory, dual-write, fusion search, fragment extraction

### Infrastructure
- **[09 — LLM Multi-Model Support](09-llm-multi-model.md)** — 6 providers, format adapters, ModelRouter failover, local model support
- **[10 — Instance & Configuration](10-instance-and-config.md)** — Instance isolation, Prompt-Driven schema, LLM Profiles, config priority
- **[11 — Evaluation & Quality](11-evaluation.md)** — Three-layer grading, E2E pipeline, failure detection, token audit
- **[12 — Playbook Online Learning](12-playbook-learning.md)** — Closed-loop strategy learning from successful sessions, user confirmation, semantic matching, context injection
- **[13 — Cloud Collaboration](13-cloud-collaboration.md)** — Local-first, cloud-enhanced architecture: two-layer routing, bidirectional ACP protocol, cloud-agent Skill delegation, device binding auth, event tunneling, Mobile/IM gateway

---

## Summary

xiaodazi is built on a clear architectural thesis: **a desktop AI agent should be private, extensible, resilient, and model-agnostic**.

- **Private** — All user data (conversations, memory, files) stored 100% locally. LLM inference requires a cloud API by default, but local models (Ollama/LM Studio) are supported for fully offline operation.
- **Extensible** — Add skills by writing Markdown, add tools by implementing a Python class, add channels by implementing an adapter.
- **Resilient** — RVR-B error recovery, context compression, adaptive termination, state rollback.
- **Model-agnostic** — Switch providers with one config value. Format adapters handle the rest.

xiaodazi is designed to make the **simple things effortless** (write a prompt, get an agent) and the **complex things possible** (custom tools, multi-model failover, three-layer evaluation).

---

## Technical Comparison with OpenClaw

[OpenClaw](https://github.com/openclaw/openclaw) (formerly Clawdbot) is an excellent open-source local-first AI assistant with a strong community (5,700+ skills on ClawHub), 29+ messaging channel integrations, lane-based concurrency, cross-channel identity linking, and native mobile device nodes. It is a well-engineered project and we respect what it has accomplished.

Both projects share the local-first, open-source, multi-model philosophy. This section is not about "who is better" — it is about describing what xiaodazi invested its engineering effort into, and why those capabilities matter for a desktop AI agent.

### 1. LLM-First Intent Analysis

xiaodazi performs an LLM-driven semantic analysis on every user request **before** the agent starts working. A 4-layer cache (hash → semantic → LLM → skill match) keeps latency under 200ms.

**What it produces:** complexity classification (simple / medium / complex), behavioral signal detection (follow-up, stop, rollback), relevant skill group identification, and memory skip detection.

**Why it matters:**

- **Cost control** — A simple "hi" loads 0 skills and 4 tools (~500 tokens). A complex research task loads 3 skill groups and 15+ tools (~3000 tokens). Without intent analysis, the system would pay the same token cost for every request regardless of complexity.
- **Precision** — "Don't make a PPT" correctly loads zero PPT skills. Intent analysis understands negation and context, not just keyword presence.
- **Adaptive behavior** — The agent adjusts its planning depth, system prompt length, and memory retrieval strategy per request. Simple queries get fast, lean responses; complex tasks get full resource allocation.

OpenClaw routes by session key, which determines *which agent* handles a message — a different problem. xiaodazi's intent analysis determines *how* the agent should behave for each specific request.

### 2. RVR-B Execution Loop with Backtracking

xiaodazi's agent runs in a **React-Validate-Reflect-Backtrack** loop. When a tool call fails, the system doesn't just retry — it classifies the error and decides the best recovery strategy.

**How it works:**

- **Error classification** — Each failure is categorized: CONTINUE (transient, retry), BACKTRACK (wrong approach, try alternative), FAIL_GRACEFULLY (degrade with partial results), or ESCALATE (ask the user).
- **Context pollution prevention** — When backtracking, failed tool calls and their error output are replaced with a concise reflection summary. This prevents the LLM from seeing the failed attempt in detail and repeating the same mistake.
- **Two-level circuit breaker** — 3 consecutive errors trigger forced reflection; 5 backtracks trigger graceful termination with whatever partial results exist.
- **State rollback** — File system snapshots enable reverting to a known-good state after destructive tool failures.

**Why it matters:**

- **Higher task completion rate** — When the agent picks the wrong tool or a bad approach, it can course-correct instead of failing outright. For example: tried to use a web API that's down → backtrack → switch to a local file-based approach → succeed.
- **Cleaner context** — Failed attempts don't pollute the conversation history. The LLM sees a reflection ("approach A failed because X, trying approach B") instead of 2000 tokens of error traces.
- **Graceful degradation** — Even when the task can't be fully completed, the agent delivers partial results and explains what went wrong, instead of crashing silently.

Most agent frameworks (including OpenClaw) handle errors through retry and model failover — which solves infrastructure failures (expired API key, rate limit). Backtracking solves a different class of problem: *strategy failures* where the approach itself was wrong.

### 3. Proactive Context Engineering

xiaodazi treats the context window as its most valuable resource and manages it proactively — not waiting until it overflows.

**Key mechanisms:**

- **Three-phase injection** — Phase 1 (system prompt, tool definitions) is stable and heavily cached. Phase 2 (memory, skills, knowledge) is session-stable. Phase 3 (current messages, plan state) is dynamic. This ordering maximizes KV-Cache reuse (90%+ hit rate), which directly reduces latency and API cost.
- **Progressive history decay** — Recent turns are kept in full. Older turns have their tool results compressed to one-line conclusions and images replaced with text descriptions. The oldest turns collapse into a summary paragraph. The agent always has context, but never wastes tokens on stale details.
- **Token budget per injector** — Every context source has a hard cap (Memory: 500 tokens, Skills: 1000, Knowledge: 800, Plan: 300). No single source can monopolize the window.
- **Scratchpad exchange** — When a tool returns large output (search results, file contents), the full data is written to a scratchpad file and only a summary + file path enters the context. The agent can read the full file when needed. This achieves up to 100x compression for tool-heavy workflows.

**Why it matters:**

- **Long conversation stability** — The agent maintains consistent quality across 50+ turn conversations. Context never overflows because it's managed proactively, not reactively.
- **Lower API cost** — KV-Cache optimization means the provider doesn't recompute cached tokens. Progressive decay means you're not paying for stale history. Scratchpad exchange means large tool results don't inflate every subsequent API call.
- **Better LLM reasoning** — A well-structured context with relevant information in high-attention zones leads to better LLM output. The TodoRewriter places the current goal at the end of context (highest attention position), improving task focus.

OpenClaw uses session compaction — a reactive approach that truncates or summarizes after the context exceeds the model's limit. This works, but means context quality degrades in a sudden step rather than gradually. Their own documentation lists context overflow as a known challenge for long-running sessions.

### 4. Intent-Driven Lazy Skill Allocation

xiaodazi has 150+ skills but loads **zero by default**. Each request triggers intent analysis, which identifies relevant skill groups, and only those groups are injected into the context.

**How it works:**

- 150+ skills organized into 20 intent-driven groups (writing, productivity, research, media, etc.)
- Intent analyzer returns matching groups per request
- Only matched skills are injected (typically 0-15 skills, ~0-1200 tokens)
- Skills are further filtered by a **2D classification matrix**: OS compatibility (common / darwin / win32 / linux) × dependency complexity (builtin / lightweight / external / cloud_api)
- Runtime status checking verifies that dependencies are actually available (CLI binaries, Python packages, system permissions, API keys)

**Why it matters:**

- **Scalability** — The skill library can grow to 500+ without affecting simple query performance. Token cost scales with task complexity, not library size.
- **Progressive capability unlock** — Zero-config builtin skills work immediately out of the box. More powerful skills (UI automation, cloud APIs) unlock naturally as users install their dependencies. The agent never suggests a skill the user can't run.
- **Cross-platform correctness** — macOS-only skills are invisible on Linux. Windows-only skills don't appear on macOS. Users never see irrelevant capabilities.

OpenClaw also has a strong skill system with lazy on-demand reading of full `SKILL.md` files, which is a good design. The difference is in how skills are *discovered and filtered* — xiaodazi uses semantic intent matching with OS and dependency awareness, while OpenClaw uses a priority-based tier system (Workspace > Local > Bundled).

### 5. Structured Task Planning

For complex multi-step tasks, xiaodazi generates a **structured plan** with a DAG-based Plan Manager.

**How it works:**

- DAG-based task decomposition with dependency tracking between steps
- Real-time progress widget in the UI — users see what the agent is doing
- TodoRewriter places the current goal in the high-attention zone of the context
- Re-planning when a step fails or circumstances change
- Planning depth adjusts based on intent complexity (none / minimal / full)

**Why it matters:**

- **Transparency** — For "research 3 competitors and write a comparison report", the user sees a visible plan (search A → search B → search C → compare → draft → refine) with real-time progress per step. No guessing about what the agent is doing or how far along it is.
- **Reliability** — If step 3 fails, the agent can re-plan around it instead of abandoning the entire task. Dependency tracking ensures steps execute in the right order.
- **Focus** — The TodoRewriter keeps the current objective in the LLM's highest-attention zone. In long multi-step tasks, this prevents the agent from losing track of what it's supposed to be doing right now.

OpenClaw relies on the LLM's implicit chain-of-thought for multi-step tasks, which works for many scenarios. xiaodazi adds explicit structure on top for visibility, recovery, and focus.

### 6. Three-Layer Agent Quality Evaluation

xiaodazi includes a structured evaluation system designed specifically for measuring **agent output quality** — not just infrastructure correctness.

**Three layers:**

- **Code Grader** — Deterministic, authoritative. Checks: no tool errors, valid response format, execution timing. Pass/fail.
- **Model Grader** — LLM-as-Judge. Scores completeness, accuracy, reasoning quality with weighted dimensions. Advisory — feeds optimization direction.
- **Human Review** — Final authority. Automatically flagged when model grader confidence is low.

**Additional capabilities:**

- 12-type failure classification (CONTEXT_OVERFLOW, TOOL_CALL_FAILURE, INTENT_MISMATCH, etc.) — each type maps to a specific optimization direction
- Auto-regression: production failures automatically become test cases
- Token audit: multi-level tracking (turn / session / conversation / user) with anomaly detection

**Why it matters:**

- **Systematic quality improvement** — When the agent underperforms, the evaluation system identifies *why* (which failure type) and *where to optimize* (prompt tuning? tool selection? context management?). Without this, quality improvement is guesswork.
- **Regression prevention** — Auto-regression ensures that a bug fixed once never comes back.
- **Cost visibility** — Token audit reveals exactly where tokens are spent, enabling targeted optimization.

### 7. Playbook Online Learning

xiaodazi implements a **closed-loop learning** system: the agent gets better at recurring task types over time, with explicit user approval.

**How it works:**

1. After a successful session involving tool usage, the system automatically extracts the strategy (which tools, in what order, with what parameters)
2. The extracted strategy is presented to the user as a suggestion — "记住" (remember) or "忽略" (dismiss). No auto-application.
3. Approved strategies are stored with semantic embeddings. When a similar task appears in the future, the matching playbook is injected as a non-mandatory hint.
4. Strategies have a full lifecycle: DRAFT → PENDING_REVIEW → APPROVED → DEPRECATED

**Why it matters:**

- **Efficiency improvement** — A task that took 8 tool calls the first time may take 4 the next time, because the agent learned the efficient path. This saves tokens, time, and user patience.
- **User control** — The human decides which strategies to adopt. The agent suggests, never auto-applies. This prevents bad strategies from propagating.
- **Institutional knowledge** — Approved playbooks accumulate domain-specific knowledge over time. The agent becomes more competent in the user's specific workflow, not just generally capable.

### 8. Prompt-Driven Configuration

xiaodazi's configuration starts with a single file: `prompt.md`.

Write a natural-language description of the agent you want, and the framework auto-generates:
- `agent_schema.yaml` — configuration schema (tools, planning strategy, memory settings, behavior)
- Complexity-graded system prompts — Simple (~1000 tokens) / Medium (~2000) / Complex (~3500)
- Tool and skill recommendations — inferred from the prompt description

**Why it matters:**

- **Low barrier to entry** — Non-technical users can create a functional agent by writing one Markdown file. No YAML, no Python, no config files to coordinate.
- **Consistency** — The framework infers a coherent configuration from a single source of truth. No risk of configuration files contradicting each other.
- **Efficient token usage** — Complexity-graded prompts mean simple tasks don't pay the token cost of a complex system prompt. A "what time is it?" query uses a 1000-token prompt, not a 3500-token one.

### Summary

| Capability | xiaodazi | Benefit |
|---|---|---|
| LLM-First intent analysis | 4-layer cached semantic analysis per request | Cost control (500 vs 3000 tokens), precision, adaptive behavior |
| RVR-B backtracking | Error classification + context cleaning + state rollback | Higher task completion rate, cleaner context, graceful degradation |
| Proactive context engineering | 3-phase injection, KV-Cache (90%+ hit), progressive decay, scratchpad | Long conversation stability, lower API cost, better LLM reasoning |
| Lazy skill allocation | 0 loaded by default, intent-driven injection, 2D matrix filtering | Scales to 500+ skills, progressive unlock, cross-platform correctness |
| Structured planning | DAG-based plan + progress UI + re-planning | Transparency, reliability, focus |
| Three-layer evaluation | Code + Model + Human grading, 12-type failure classification | Systematic quality improvement, regression prevention, cost visibility |
| Playbook learning | Extract → confirm → apply → improve | Efficiency gains over time, user-controlled, institutional knowledge |
| Prompt-driven config | Write one `prompt.md`, framework infers the rest | Low barrier, consistency, efficient token usage |

OpenClaw is an excellent project with clear strengths in multi-channel integration (29+ platforms), community ecosystem (ClawHub), lane-based concurrency, and device nodes. xiaodazi's investment is in a different direction — making the agent engine itself more intelligent, efficient, and self-improving. Both are valid engineering choices for different priorities.

---

## Known Issues & Roadmap

xiaodazi is under active development. We are honest about the problems that still exist — listing them here so you know what to expect, and so you can help us improve.

### Stability

- **Long session memory pressure** — In conversations exceeding 80+ turns with heavy tool usage, context compression occasionally discards information that the agent needs later. We are tuning the decay thresholds and scratchpad hinting to mitigate this.
- **Abnormal process exit** — The Python backend may exit unexpectedly under certain conditions (e.g., concurrent file writes during snapshot, unhandled edge cases in streaming SSE). The Tauri shell does not yet auto-restart the sidecar on crash. If the UI stops responding, a manual restart is currently required.
- **SQLite write contention** — Under high concurrent write load (e.g., memory extraction + conversation save + playbook extraction firing simultaneously), WAL mode handles most cases, but we have observed occasional `database is locked` errors on slower disks.

### Agent Quality

- **Backtracking is not always effective** — The RVR-B loop sometimes backtracks too late (after context is already polluted) or too eagerly (abandoning an approach that would have worked with one more turn). Tuning the error classification thresholds is ongoing.
- **Planning granularity** — The Plan Manager sometimes generates plans that are too coarse (single giant step) or too fine (20 micro-steps for a simple task). The complexity-to-depth mapping needs more real-world calibration.
- **Model Grader variance** — LLM-as-Judge scores can vary across runs for the same output. We use weighted multi-dimension scoring to reduce noise, but the evaluation layer is advisory, not deterministic.

### Skill Ecosystem

- **External dependency fragility** — Skills that depend on CLI tools (e.g., `ffmpeg`, `pandoc`) or external apps can break silently when those tools update their CLI interface. Runtime status checking catches "not installed" but not "installed but incompatible version."
- **Skill coverage gaps** — 150+ skills sounds like a lot, but many real-world workflows hit edge cases that no existing skill covers. Custom skill authoring is straightforward (write a `SKILL.md`), but the documentation and examples need improvement.

### Platform

- **macOS is the primary tested platform** — Development and testing are primarily done on macOS. The majority of skills, file path handling, and Tauri integration have been thoroughly validated on macOS. Windows support exists but has not received the same level of testing — you may encounter path issues, permission edge cases, or platform-specific skill failures on Windows. We are actively improving Windows compatibility and welcome bug reports from Windows users.
- **Single-machine only (cloud collaboration in progress)** — xiaodazi currently runs on one desktop. Cloud collaboration via ACP protocol is designed ([see architecture](13-cloud-collaboration.md)) to enable mobile/IM access and persistent task execution, but is not yet implemented.
- **No voice interface** — Text-only. No speech-to-text or text-to-speech integration yet.
- **Limited channel support** — Currently 3 channels (Web, Telegram, Feishu). Adding more channels (WhatsApp, Discord, Slack) is planned but not yet implemented.

### What We Are Working On

- Windows platform hardening (path handling, permission model, platform-specific skill testing)
- Sidecar auto-restart and health monitoring in the Tauri shell
- More robust context decay with importance-aware compression
- Skill dependency version checking
- Voice input/output support
- Additional messaging channel adapters
- Better onboarding documentation and skill authoring guides

---

We believe the architecture is sound, but the implementation still has rough edges. If you encounter crashes, unexpected behavior, or quality issues — **please file an issue**. Every bug report directly improves the project. We read all of them.

Contributions are welcome: skill authoring, bug reports, prompt tuning, documentation, or just telling us what broke. xiaodazi gets better because people use it and tell us what's wrong.
