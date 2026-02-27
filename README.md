<p align="center">
  <img src="docs/assets/logo.png" width="80" alt="xiaodazi logo" />
</p>

<h1 align="center">xiaodazi</h1>

<p align="center">
  <strong>Open-source AI agent that lives on your desktop.</strong><br/>
  Local-first storage · 200+ plug-and-play skills · 7+ LLM providers · macOS & Windows
</p>

<p align="center">
  <a href="https://www.dazee.ai"><img src="https://img.shields.io/badge/Website-dazee.ai-F59E0B?style=flat&logo=safari&logoColor=white" alt="Official Website" /></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT" /></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+" /></a>
  <a href="https://github.com/malue-ai/dazee-small/stargazers"><img src="https://img.shields.io/github/stars/malue-ai/dazee-small?style=social" alt="GitHub Stars" /></a>
</p>

<p align="center">
  <a href="https://www.dazee.ai">Official Website</a> | <a href="README_zh.md">中文</a> | English
</p>

<p align="center">
  <img src="docs/assets/quick-start.jpg" width="720" alt="Get started in 3 steps" />
</p>

---

## What is xiaodazi?

xiaodazi ("little buddy") is an open-source AI agent that **runs as a native desktop app** (Tauri). It keeps all data on your machine, operates your computer directly — managing files, automating apps, generating documents — and remembers your preferences across sessions.

### Demo

<video src="docs/assets/demo.mp4" width="720" controls>
  Your browser does not support the video tag. <a href="docs/assets/demo.mp4">Download the demo video</a>.
</video>

### Why xiaodazi?

<p align="center">
  <img src="docs/assets/core-advantages.jpg" width="720" alt="5 core advantages" />
</p>

| | Cloud AI Assistants | xiaodazi |
|---|---|---|
| **Data** | Stored on provider's servers | 100% local (SQLite, plain files) |
| **Memory** | Forgets between sessions | Remembers preferences via editable `MEMORY.md` + semantic search |
| **Skills** | Fixed capabilities | 200+ plug-and-play skills, add new ones by writing Markdown |
| **Models** | Locked to one provider | Switch between Claude, GPT, Qwen, DeepSeek, Gemini, GLM, or Ollama |
| **Errors** | Fails silently or retries | Classifies errors, backtracks from bad approaches, degrades gracefully |

---

## Quick Start

### Option A: One-click install (end users)

**Windows** — Download the installer from [Releases](https://github.com/malue-ai/dazee-small/releases), double-click to run.

**macOS** — Open Terminal and run:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/malue-ai/dazee-small/main/scripts/auto_build_app.sh)
```

Then configure an API key in the Settings page (DeepSeek or Gemini free tier recommended for beginners).

### Option B: From source (developers)

```bash
git clone https://github.com/malue-ai/dazee-small.git
cd dazee-small

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Create `config.yaml` in the project root (or use the Settings page after starting):

```yaml
api_keys:
  ANTHROPIC_API_KEY: sk-ant-api03-your-key-here   # Recommended
  # OPENAI_API_KEY: sk-xxx
  # DASHSCOPE_API_KEY: sk-xxx                      # Qwen
  # GOOGLE_API_KEY: xxx                            # Gemini (free: 1500 req/day)
```

Start the backend:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Start the frontend:

```bash
cd frontend
npm install && npm run dev
# Open http://localhost:5174
```

<details>
<summary><strong>Desktop app (Tauri) — requires Rust toolchain</strong></summary>

```bash
# Install Rust: https://rustup.rs/
# Requires Node.js >= 18 (Vite 5 requirement)

# 1. Build backend sidecar binary (requires PyInstaller)
pip install pyinstaller
python scripts/build_backend.py

# 2. Start Tauri dev / build
cd frontend
npm run tauri:dev     # Development
npm run tauri:build   # Production build
```

</details>

<details>
<summary><strong>Fully offline with Ollama</strong></summary>

Install [Ollama](https://ollama.ai), then set in `config.yaml`:

```yaml
llm:
  COT_AGENT_MODEL: ollama/llama3.1
```

No API key needed. All inference runs locally.

</details>

---

## Key Design Decisions

### LLM-First — No keyword matching, ever

All semantic tasks — intent classification, skill selection, complexity inference, backtrack decisions — are performed by the LLM. Hard-coded rules exist only for format validation, numeric calculations, and security boundaries.

**Why it matters:** When a user says *"Don't make a PPT, just give me the key points"*, a keyword system matches "PPT" and loads the wrong tools. xiaodazi's LLM-driven intent analysis correctly loads zero PPT skills.

### Skills as Markdown — 200+ and growing

Each skill is a directory with a `SKILL.md` file. No Python code required for most skills — the LLM reads the instructions and uses built-in tools to execute them.

Despite 200+ skills, **zero are loaded by default**. Each request activates only the skill groups matching the user's intent (typically 0–15 out of 200+). A simple "hi" costs 0 skill tokens; a complex research task costs ~1,200.

### Command Execution Safety — Transparent rules for what AI can and cannot do

xiaodazi can execute commands directly on your computer (file operations, network diagnostics, script execution, etc.), but **every command passes through a built-in security policy engine**. Rules are evaluated top-to-bottom; the first match wins. Unmatched commands default to **allow**.

<details>
<summary><strong>✅ Allowed commands</strong></summary>

| Pattern | Description | Shell |
|---------|-------------|-------|
| `echo *` | Echo output | All |
| `Get-*` | PowerShell read-only query cmdlets | powershell / pwsh |
| `dir` / `dir *` | Directory listing | All |
| `hostname` | Hostname query | All |
| `whoami` | Current user | All |
| `systeminfo` | System information | All |
| `ipconfig` / `ipconfig *` | Network configuration | All |
| `ping *` | Network connectivity test | All |
| `type *` | Read file contents | cmd |
| `cat *` | Read file contents | All |
| `tasklist*` | Process list | All |
| `netstat*` | Network connections | All |
| `python *` / `python3 *` | Python script execution | All |
| `pip *` / `pip3 *` | Python package management | All |
| `git *` | Git version control | All |
| `node *` / `npm *` | Node.js runtime & package management | All |

</details>

<details>
<summary><strong>🚫 Explicitly blocked dangerous commands</strong></summary>

| Pattern | Reason |
|---------|--------|
| `Remove-Item *` / `rm *` / `del *` | Prevent accidental file deletion |
| `Format-*` | Prevent disk formatting |
| `Stop-Computer*` / `shutdown*` | Prevent unexpected shutdown |
| `Restart-Computer*` | Prevent unexpected restart |
| `*Invoke-WebRequest*` | Prevent downloading and executing unknown programs |
| `*Start-Process*` | Prevent bypassing security policy to launch processes |
| `*reg *` | Prevent registry modification |
| `net user*` / `net localgroup*` | Prevent account and permission tampering |
| `schtasks *` | Prevent scheduled task creation |

</details>

> **Customizable:** Policy rules are stored in a local `exec-policy.json` file. You can modify them via remote management commands (`system.execApprovals.get/set`) or by editing the JSON file directly. Adjust the allowlist and blocklist to fit your use case.

### Local-First — Your data stays on your machine

| Storage | Technology | Purpose |
|---|---|---|
| Messages & conversations | SQLite (WAL mode) | Async read/write, concurrent access |
| Full-text search | SQLite FTS5 | BM25 ranking, zero-config |
| Semantic vectors | sqlite-vec (optional) | Vector similarity, single file |
| User memory | `MEMORY.md` | Plain text, user-editable |
| File attachments | Local filesystem | Instance-isolated |

No cloud database, no external vector store, no third-party analytics. LLM inference uses cloud APIs by default, with full local model support via Ollama for completely offline operation.

---

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
├──────────────────────────────┬──────────────────────────────────────────────┤
│  Layer 4 — Capability        │  Layer 5 — Infrastructure                    │
│    200+ Skills (20 groups)   │    7 LLM Providers + Ollama                   │
│    Tool System (intent-      │    SQLite + FTS5 + sqlite-vec                 │
│      pruned)                 │    Instance Isolation                         │
│    3-Layer Memory            │    3-Layer Evaluation                         │
│    Playbook Learning         │                                               │
└──────────────────────────────┴──────────────────────────────────────────────┘
```

**Lifecycle of a request:** User message → Intent analysis (<200ms, cached) → Skill & tool selection → RVR-B execution loop (stream tokens, call tools, validate, backtrack if needed) → Memory extraction → Response complete.

<details>
<summary><strong>What makes xiaodazi different from typical agent frameworks?</strong></summary>

| Capability | xiaodazi | Typical frameworks |
|---|---|---|
| **Intent analysis** | LLM semantic analysis per request (4-layer cache, <200ms). Adjusts skill loading, planning depth, and token budget per request. | Route by session or fixed config. Same resource allocation for every request. |
| **Error recovery** | RVR-B loop: classify error → backtrack from wrong approaches → clean context pollution → degrade gracefully with partial results. | Retry + model failover. Solves infra failures, not strategy failures. |
| **Context management** | Proactive: 3-phase injection, progressive history decay, scratchpad file exchange (100x compression), KV-Cache optimization (90%+ hit). | Reactive: truncate or summarize when context overflows. |
| **Skill loading** | 0 skills loaded by default. Intent-driven lazy allocation. Token cost scales with task complexity, not library size. | Load all capabilities upfront, or manual tool selection. |
| **Planning** | Explicit DAG plan with UI progress widget and re-planning on failure. | Implicit chain-of-thought. No visibility, no recovery. |
| **Evaluation** | 3-layer grading (code + LLM-as-Judge + human), 12-type failure classification, auto-regression. | External eval tools or manual testing. |
| **Learning** | Playbook system: extract strategy → user confirms → apply to future tasks. | No built-in learning loop. |

</details>

---

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

## Project Structure

<details>
<summary><strong>Click to expand</strong></summary>

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
│   ├── llm/             # 7 LLM providers + format adapters
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

---

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

The skill is automatically discovered, classified, and available on next request.

### Add an LLM Provider

Implement a provider class in `core/llm/` following the existing adapters (Claude, OpenAI, Qwen, etc.). Register it in the `LLMRegistry`.

### Add a Messaging Channel

Implement a gateway adapter in `core/gateway/`. The `ChatService` is protocol-agnostic — your adapter only handles message format conversion.

---

## Known Issues

We are honest about what doesn't work well yet.

<details>
<summary><strong>Stability</strong></summary>

- **Long session memory pressure** — In 80+ turn conversations with heavy tool usage, context compression occasionally discards information the agent needs later.
- **Process crashes** — The Python backend can exit unexpectedly under concurrent file writes. The Tauri shell does not yet auto-restart the sidecar.
- **SQLite write contention** — When memory extraction, conversation save, and playbook extraction fire simultaneously, `database is locked` errors occur occasionally on slower disks.

</details>

<details>
<summary><strong>Agent Quality</strong></summary>

- **Backtracking timing** — The RVR-B loop sometimes backtracks too late or too eagerly. Error classification thresholds are still being calibrated.
- **Planning granularity** — Plans are sometimes too coarse or too fine. The complexity-to-depth mapping needs more real-world data.

</details>

<details>
<summary><strong>Platform</strong></summary>

- **macOS is the primary test platform.** Windows support exists but has received less testing.
- **Single-machine only.** No remote access, no mobile app, no multi-device sync.
- **Text only.** No voice input/output yet.

</details>

---

## Roadmap

- [ ] Windows platform hardening
- [ ] Sidecar auto-restart and health monitoring
- [ ] Importance-aware context compression
- [ ] Skill marketplace / community registry
- [ ] Parallel tool execution
- [ ] Voice input/output
- [ ] Additional messaging channels (Discord, Slack, WhatsApp)

---

## Documentation

| Document | Description |
|---|---|
| **[Architecture Overview](docs/architecture/README.md)** | Full 5-layer architecture with 12 deep-dive modules |
| [Frontend & Desktop](docs/architecture/01-frontend-and-desktop.md) | Tauri + Vue 3, Apple Liquid design |
| [API & Services](docs/architecture/02-api-and-services.md) | Three-layer architecture, preprocessing pipeline |
| [Intent Analysis](docs/architecture/03-intent-and-routing.md) | LLM-First semantic analysis, 4-layer caching |
| [Agent Execution](docs/architecture/04-agent-execution.md) | RVR-B loop, backtracking, adaptive termination |
| [Context Engineering](docs/architecture/05-context-engineering.md) | 3-phase injection, compression, KV-Cache |
| [Tool System](docs/architecture/06-tool-system.md) | 2-layer registry, intent-driven pruning |
| [Skill Ecosystem](docs/architecture/07-skill-ecosystem.md) | 200+ skills, 2D classification, lazy allocation |
| [Memory System](docs/architecture/08-memory-system.md) | 3-layer memory, dual-write, fusion search |
| [LLM Multi-Model](docs/architecture/09-llm-multi-model.md) | 7 providers, format adapters, failover |
| [Instance & Config](docs/architecture/10-instance-and-config.md) | Prompt-driven schema, instance isolation |
| [Evaluation](docs/architecture/11-evaluation.md) | 3-layer grading, E2E pipeline, failure detection |
| [Playbook Learning](docs/architecture/12-playbook-learning.md) | Closed-loop strategy learning |

---

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

## Authors

- **Yi Liu** ([@ironliuyi](https://github.com/ironliuyi)) — liuyi@zenflux.cn
- **Kangcheng Wang** — wangkangcheng@zenflux.cn
- **Mengqi Zeng** — zengmengqi@zenflux.cn
- **Haipeng Xie** — xiehaipeng@zenflux.cn

## License

[MIT](LICENSE) — Copyright (c) 2025-2026 ZenFlux
