<p align="center">
  <img src="frontend/src-tauri/icons/icon.png" width="80" alt="xiaodazi logo" />
</p>

<h1 align="center">xiaodazi (小搭子)</h1>

<p align="center">
  A local-first desktop AI agent with 150+ skills, persistent memory, and multi-model support.
</p>

<p align="center">
  <a href="README_zh.md">中文</a> &nbsp;|&nbsp; English
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT License" /></a>
  <img src="https://img.shields.io/badge/python-3.12-blue.svg" alt="Python 3.12" />
  <img src="https://img.shields.io/badge/vue-3.4-green.svg" alt="Vue 3.4" />
  <img src="https://img.shields.io/badge/tauri-2.10-orange.svg" alt="Tauri 2.10" />
  <a href="https://github.com/malue-ai/dazee-small/issues"><img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg" alt="PRs Welcome" /></a>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> &nbsp;·&nbsp;
  <a href="docs/architecture/README.md">Architecture</a> &nbsp;·&nbsp;
  <a href="#extending-xiaodazi">Extending</a> &nbsp;·&nbsp;
  <a href="#contributing">Contributing</a>
</p>

---

xiaodazi ("little buddy") is an open-source AI agent that **lives on your desktop**. It runs as a native Tauri application, keeps all data on your machine, and can operate your computer directly — managing files, automating apps, generating documents, and remembering your preferences across sessions.

<!-- TODO: Add a 30-second demo GIF here -->
<!-- <p align="center"><img src="docs/assets/demo.gif" width="720" alt="demo" /></p> -->

## Why xiaodazi?

Most AI assistants are cloud-hosted chat interfaces. xiaodazi is different:

| | Cloud AI Assistants | xiaodazi |
|---|---|---|
| **Data** | Stored on provider's servers | 100% local (SQLite, plain files) |
| **Memory** | Forgets between sessions | Remembers preferences via editable `MEMORY.md` + semantic search |
| **Skills** | Fixed capabilities | 150+ plug-and-play skills, add new ones by writing Markdown |
| **Models** | Locked to one provider | Switch between Claude, GPT, Qwen, DeepSeek, Gemini, GLM, or Ollama |
| **Errors** | Fails silently or retries | Classifies errors, backtracks from bad approaches, degrades gracefully |

## Key Design Decisions

<details>
<summary><b>LLM-First — No keyword matching, ever</b></summary>

All semantic tasks — intent classification, skill selection, complexity inference, backtrack decisions — are performed by the LLM. Hard-coded rules exist only for format validation, numeric calculations, and security boundaries.

**Why it matters:** When a user says *"Don't make a PPT, just give me the key points"*, a keyword system matches "PPT" and loads the wrong tools. xiaodazi's LLM-driven intent analysis correctly loads zero PPT skills.

</details>

<details>
<summary><b>Skills as Markdown — 150+ and growing</b></summary>

Each skill is a directory with a `SKILL.md` file. No Python code required for most skills — the LLM reads the instructions and uses built-in tools to execute them. Skills are classified on two axes:

- **OS compatibility**: common / macOS / Windows / Linux
- **Dependency level**: builtin (zero-config) / lightweight (pip) / external (CLI) / cloud_api (API key)

Despite 150+ skills, **zero are loaded by default**. Each request activates only the skill groups matching the user's intent (typically 0–15 out of 150+). A simple "hi" costs 0 skill tokens; a complex research task costs ~1,200.

</details>

<details>
<summary><b>Local-First — Your data stays on your machine</b></summary>

| Storage | Technology | Purpose |
|---|---|---|
| Messages & conversations | SQLite (WAL mode) | Async read/write, concurrent access |
| Full-text search | SQLite FTS5 | BM25 ranking, zero-config |
| Semantic vectors | sqlite-vec (optional) | Vector similarity, single file |
| User memory | `MEMORY.md` | Plain text, user-editable |
| File attachments | Local filesystem | Instance-isolated |

No cloud database, no external vector store, no third-party analytics. LLM inference uses cloud APIs by default (Claude, OpenAI, etc.), with full local model support via Ollama or LM Studio for completely offline operation.

</details>

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Layer 1 — User Interface                                                   │
│    Tauri 2.10 (Rust) · Vue 3.4 + TypeScript · Apple Liquid Design           │
├─────────────────────────────────────────────────────────────────────────────┤
│  Layer 2 — API & Services                                                   │
│    FastAPI (REST + SSE + WebSocket) · Multi-Channel Gateway                  │
├─────────────────────────────────────────────────────────────────────────────┤
│  Layer 3 — Agent Engine                                                     │
│    Intent Analyzer (LLM, 4-layer cache, <200ms)                              │
│    RVR-B Executor (React → Validate → Reflect → Backtrack)                   │
│    Context Engineering (3-phase inject, KV-Cache 90%+ hit, scratchpad)       │
│    Plan Manager (DAG tasks, real-time progress UI)                           │
├──────────────────────────────────┬──────────────────────────────────────────┤
│  Layer 4 — Capability            │  Layer 5 — Infrastructure                │
│    150+ Skills (20 groups)       │    6 LLM Providers + Ollama               │
│    Tool System (intent-pruned)   │    SQLite + FTS5 + sqlite-vec             │
│    3-Layer Memory                │    Instance Isolation                     │
│    Playbook Learning             │    3-Layer Evaluation                     │
└──────────────────────────────────┴──────────────────────────────────────────┘
```

**Lifecycle of a request:** User message → Intent analysis (<200ms, cached) → Skill & tool selection → RVR-B execution loop (stream tokens, call tools, validate, backtrack if needed) → Memory extraction → Response complete.

For a full walkthrough, see [Architecture Documentation](docs/architecture/README.md) (12 deep-dive modules).

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/malue-ai/dazee-small.git
cd dazee-small

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure an LLM provider

Create `config.yaml` in the project root (or use the Settings page after starting the frontend):

```yaml
api_keys:
  ANTHROPIC_API_KEY: sk-ant-api03-your-key-here   # Recommended
  # OPENAI_API_KEY: sk-xxx                         # Or OpenAI
  # DASHSCOPE_API_KEY: sk-xxx                      # Or Qwen
  # GOOGLE_API_KEY: xxx                            # Or Gemini (free tier: 1500 req/day)
```

For fully offline use, install [Ollama](https://ollama.ai) and set:

```yaml
llm:
  COT_AGENT_MODEL: ollama/llama3.1
```

### 3. Start the backend

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Verify: `curl http://localhost:8000/health`

### 4. Start the frontend (optional)

```bash
cd frontend
npm install && npm run dev
# Open http://localhost:5174
```

### 5. Desktop app (optional)

Requires [Rust toolchain](https://rustup.rs/).

```bash
cd frontend
npm run tauri:dev     # Development
npm run tauri:build   # Production build
```

## What Makes xiaodazi Different

<details>
<summary><b>vs. Typical Agent Frameworks</b></summary>

| Capability | xiaodazi | Typical frameworks |
|---|---|---|
| **Intent analysis** | LLM semantic analysis per request (4-layer cache, <200ms). Adjusts skill loading, planning depth, and token budget per request. | Route by session or fixed config. Same resource allocation for every request. |
| **Error recovery** | RVR-B loop: classify error → backtrack from wrong approaches → clean context pollution → degrade gracefully with partial results. | Retry + model failover. Solves infra failures, not strategy failures. |
| **Context management** | Proactive: 3-phase injection, progressive history decay, scratchpad file exchange (100x compression), KV-Cache optimization (90%+ hit). | Reactive: truncate or summarize when context overflows. Quality drops in a sudden step. |
| **Skill loading** | 0 skills loaded by default. Intent-driven lazy allocation. Token cost scales with task complexity, not library size. | Load all capabilities upfront, or manual tool selection. |
| **Planning** | Explicit DAG plan with UI progress widget and re-planning on failure. | Implicit chain-of-thought. No visibility, no recovery. |
| **Evaluation** | 3-layer grading (code + LLM-as-Judge + human), 12-type failure classification, auto-regression. | External eval tools or manual testing. |
| **Learning** | Playbook system: extract strategy → user confirms → apply to future tasks. Efficiency improves over time. | No built-in learning loop. |
| **Configuration** | Write a `prompt.md` → framework auto-generates agent config + graded system prompts. | YAML/JSON config files, manual coordination. |

</details>

<details>
<summary><b>vs. Cloud AI Assistants (ChatGPT, Claude.ai, etc.)</b></summary>

- **Privacy**: All data local. No conversations leave your machine (except LLM API calls, which you can eliminate with Ollama).
- **Persistence**: Memory survives across sessions. The agent learns your preferences.
- **Extensibility**: Add skills by writing Markdown. Add tools by implementing a Python class.
- **Model freedom**: Not locked to one provider. Switch with one config change.
- **Desktop integration**: Can manage files, automate apps, take screenshots — not just chat.

</details>

## Tech Stack

| Layer | Technology |
|---|---|
| Desktop shell | Tauri 2.10 (Rust) |
| Frontend | Vue 3.4 + TypeScript + Tailwind CSS 4.1 + Pinia |
| Backend | Python 3.12 + FastAPI + asyncio |
| Communication | SSE + WebSocket + REST |
| Storage | SQLite (WAL) + FTS5 + sqlite-vec |
| LLM providers | Claude, OpenAI, Qwen, DeepSeek, Gemini, GLM, Ollama |
| Memory | MEMORY.md + FTS5 + Mem0 |
| Evaluation | Code graders + LLM-as-Judge + human review |

## Extending xiaodazi

### Add a Skill (no code required)

Create a directory under `skills/` or `instances/xiaodazi/skills/` with a `SKILL.md`:

```markdown
# My Custom Skill

## When to Use
When the user asks to [describe the trigger scenario].

## Instructions
1. First, [step one]
2. Then, [step two]
3. Finally, [step three]

## metadata
os_compatibility: common
dependency_level: builtin
```

The skill is automatically discovered, classified, and available on next request. See [Skill Ecosystem docs](docs/architecture/07-skill-ecosystem.md) for the full specification.

### Add an LLM Provider

Implement a provider class in `core/llm/` following the existing adapters (Claude, OpenAI, Qwen, etc.). Register it in the `LLMRegistry`. See [LLM Multi-Model docs](docs/architecture/09-llm-multi-model.md).

### Add a Messaging Channel

Implement a gateway adapter in `core/gateway/`. The `ChatService` is protocol-agnostic — your adapter only handles message format conversion. Currently supported: Web, Telegram, Feishu.

## Project Structure

<details>
<summary>Click to expand</summary>

```
xiaodazi/
├── frontend/            # Vue 3 + Tauri desktop app
├── core/
│   ├── agent/           # RVR-B execution, backtracking
│   ├── routing/         # LLM-First intent analysis
│   ├── context/         # Context engineering (inject, compress, cache)
│   ├── tool/            # Tool registry, selector, executor
│   ├── skill/           # Skill loader, group registry
│   ├── memory/          # 3-layer memory (Markdown + FTS5 + Mem0)
│   ├── playbook/        # Online learning (strategy extraction)
│   ├── llm/             # 6 LLM providers + format adapters
│   ├── planning/        # DAG task planning + progress tracking
│   ├── termination/     # Adaptive termination strategies
│   ├── state/           # Snapshot / rollback
│   └── monitoring/      # Failure detection, token audit
├── routers/             # FastAPI HTTP/WS endpoints
├── services/            # Business logic (protocol-agnostic)
├── tools/               # Built-in tool implementations
├── skills/              # Shared skill library
├── instances/           # Agent instance configs
├── evaluation/          # E2E test suites + graders
├── models/              # Pydantic data models
└── infra/               # Storage infrastructure (SQLite, cache)
```

</details>

## Known Issues

We are honest about what doesn't work well yet. These are real problems, not edge cases.

<details>
<summary><b>Stability</b></summary>

- **Long session memory pressure** — In 80+ turn conversations with heavy tool usage, context compression occasionally discards information the agent needs later. We are tuning decay thresholds.
- **Process crashes** — The Python backend can exit unexpectedly under concurrent file writes during snapshot or edge cases in SSE streaming. The Tauri shell does not yet auto-restart the sidecar. If the UI stops responding, restart the app.
- **SQLite write contention** — When memory extraction, conversation save, and playbook extraction fire simultaneously, WAL mode handles most cases, but `database is locked` errors occur occasionally on slower disks.

</details>

<details>
<summary><b>Agent Quality</b></summary>

- **Backtracking timing** — The RVR-B loop sometimes backtracks too late (context already polluted) or too eagerly (abandoning an approach that would have succeeded). Error classification thresholds are still being calibrated.
- **Planning granularity** — Plans are sometimes too coarse (one giant step) or too fine (20 micro-steps for a simple task). The complexity-to-depth mapping needs more real-world data.

</details>

<details>
<summary><b>Platform & Ecosystem</b></summary>

- **macOS is the primary test platform.** Windows support exists but has received less testing — expect path issues, permission edge cases, and platform-specific skill failures. We welcome Windows bug reports.
- **Single-machine only.** No remote access, no mobile app, no multi-device sync.
- **Text only.** No voice input/output yet.
- **3 channels** (Web, Telegram, Feishu). Discord, Slack, WhatsApp are planned.
- **Most skills are declarative.** Of 150+ skills, only ~17 have executable scripts. The rest are prompt-only — their effectiveness depends on the underlying LLM's capability.
- **No skill versioning or marketplace.** Skills are local files. Community sharing requires manual copying.

</details>

## Roadmap

- [ ] Windows platform hardening
- [ ] Sidecar auto-restart and health monitoring
- [ ] Importance-aware context compression
- [ ] Skill dependency version checking
- [ ] Skill marketplace / community registry
- [ ] Parallel tool execution
- [ ] Voice input/output
- [ ] Additional messaging channels (Discord, Slack, WhatsApp)
- [ ] CI/CD pipeline

## Documentation

<details>
<summary><b>12 deep-dive architecture modules</b></summary>

| Document | Description |
|---|---|
| **[Architecture Overview](docs/architecture/README.md)** | Full 5-layer architecture with 12 deep-dive modules |
| [Frontend & Desktop](docs/architecture/01-frontend-and-desktop.md) | Tauri + Vue 3, Apple Liquid design, HITL interactions |
| [API & Services](docs/architecture/02-api-and-services.md) | Three-layer architecture, preprocessing pipeline |
| [Intent Analysis](docs/architecture/03-intent-and-routing.md) | LLM-First semantic analysis, 4-layer caching |
| [Agent Execution](docs/architecture/04-agent-execution.md) | RVR-B loop, backtracking, adaptive termination |
| [Context Engineering](docs/architecture/05-context-engineering.md) | 3-phase injection, compression, KV-Cache |
| [Tool System](docs/architecture/06-tool-system.md) | 2-layer registry, intent-driven pruning |
| [Skill Ecosystem](docs/architecture/07-skill-ecosystem.md) | 150+ skills, 2D classification, lazy allocation |
| [Memory System](docs/architecture/08-memory-system.md) | 3-layer memory, dual-write, fusion search |
| [LLM Multi-Model](docs/architecture/09-llm-multi-model.md) | 6 providers, format adapters, failover |
| [Instance & Config](docs/architecture/10-instance-and-config.md) | Prompt-driven schema, instance isolation |
| [Evaluation](docs/architecture/11-evaluation.md) | 3-layer grading, E2E pipeline, failure detection |
| [Playbook Learning](docs/architecture/12-playbook-learning.md) | Closed-loop strategy learning |

</details>

## Contributing

We welcome contributions of all kinds:

- **Skill authoring** — The lowest-barrier way to contribute. Write a `SKILL.md`, open a PR.
- **Bug reports** — Especially on Windows. Every crash report improves the project.
- **Prompt tuning** — Help improve intent analysis accuracy or agent response quality.
- **Documentation** — Tutorials, examples, translations.
- **Code** — See the [Architecture docs](docs/architecture/README.md) to understand the codebase before diving in.

## Star History

<a href="https://star-history.com/#malue-ai/dazee-small&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=malue-ai/dazee-small&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=malue-ai/dazee-small&type=Date" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=malue-ai/dazee-small&type=Date" />
 </picture>
</a>

## Contributors

<a href="https://github.com/malue-ai/dazee-small/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=malue-ai/dazee-small" />
</a>

## License

[MIT](LICENSE) — Copyright (c) 2025-2026 ZenFlux
