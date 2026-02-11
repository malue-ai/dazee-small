# ZenFlux Agent — Xiaodazi Desktop Instance

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

English | [中文](README_zh.md)

> A desktop AI agent designed as "A Little Partner living in your computer".
> 100% Local Storage, Skills-First Capability System, Cross-Platform (macOS / Windows / Linux).

## Technical Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Xiaodazi Desktop App (Tauri + Vue)                   │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                           UI Layer                                    │  │
│  │  ┌─────────┐ ┌─────────┐ ┌┌─────────────────┐                          │  │
│  │  │ Chat UI │ │ Projects│ │  Skills Market    │                          │  │
│  │  └─────────┘ └─────────┘  └─────────────────┘                          │  │
│  │                              ↕ postMessage                              │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │  │
│  │  │            MCP Apps Client (Vue Component)                      │  │  │
│  │  │  • iframe Lifecycle Mgmt • JSON-RPC Bridge • UI Resource Cache  │  │  │
│  │  └─────────────────────────────────────────────────────────────────┘  │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │  │
│  │  │         ProgressRenderer (Progress Display Component)           │  │  │
│  │  │  • Friendly Messages • Progress Bar • Hide Tech Details         │  │  │
│  │  └─────────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                   ↕ IPC
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Xiaodazi Agent Instance (Python/Rust)                  │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │              Intent & Planning (Simplified IntentAnalyzer)            │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │      State Consistency & Termination (StateConsistencyManager)        │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │          Agent Engine (RVRBAgent + BacktrackManager + PlanTodo)       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │     Skills-First Layer (SkillRegistry + 2D Classification OS x Dep)   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │       OS Compatibility (MacOS/Windows/Linux LocalNode)                │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  Local Knowledge (LocalKnowledgeManager: FTS5 + sqlite-vec)           │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │              MCP Apps Service Layer (UI Registry / ui:// / CSP)       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    Storage Layer (100% Local)                         │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐      │  │
│  │  │ SQLite      │ │ SQLite FTS5 │ │ sqlite-vec  │ │ Skills Cache│      │  │
│  │  │ (Msg/Sess)  │ │ (Full Text) │ │ (Vector)    │ │ (Lazy Load) │      │  │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘      │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
zenflux_agent/
├── main.py                      # FastAPI Entry Point
├── core/                        # Core Components
│   ├── agent/                   # Agent Orchestration (RVRBAgent / BacktrackManager)
│   ├── llm/                     # LLM Adapters (Claude / OpenAI / Gemini / Qwen)
│   ├── memory/                  # Memory Mgmt (Mem0 / System / Working Memory)
│   ├── planning/                # Planning System (PlanTodoTool / ProgressTransformer)
│   ├── routing/                 # Intent Analysis & Routing
│   ├── skill/                   # Skill Loaders (Dynamic / Lazy)
│   ├── tool/                    # Tool Selection & Execution
│   ├── events/                  # Event Management
│   └── context/                 # Runtime Context
├── infra/                       # Infrastructure
│   ├── database/                # PostgreSQL (Cloud)
│   ├── local_store/             # SQLite Local Storage (Desktop)   ← New
│   │   ├── engine.py            #   Async Engine (aiosqlite + WAL)
│   │   ├── models.py            #   ORM Models (Session / Msg / Skills Cache)
│   │   ├── fts.py               #   FTS5 Full Text Index
│   │   ├── vector.py            #   sqlite-vec Vector Search
│   │   ├── skills_cache.py      #   Skills Lazy Cache
│   │   ├── workspace.py         #   Workspace Manager (Unified Entry)
│   │   └── crud/                #   CRUD Operations
│   ├── cache/                   # Cache
│   ├── storage/                 # File Storage (Local / S3)
│   └── cache/                   # Cache Layer
├── instances/                   # Instance Configs (see instances/README.md)
│   ├── _template/               # Template (Starting point for new instances)
│   └── xiaodazi/                # Xiaodazi (Main Desktop Instance)
│       ├── config.yaml          #   Instance Config
│       ├── prompt.md            #   Persona Prompt
│       ├── config/              #   LLM Routing, Skills, Memory Config
│       ├── skills/              #   70+ Built-in Skills
│       └── prompt_results/      #   Auto-generated Scenario Prompts
├── routers/                     # API Routers
├── services/                    # Business Services
├── tools/                       # Tool Implementations
├── skills/                      # Global Skills Library
├── config/                      # Config Files
├── models/                      # Pydantic Data Models
├── frontend/                    # Vue Frontend
└── docs/                        # Documentation
    └── architecture/
        └── xiaodazi-desktop.md  # Desktop Architecture Design
```

## Quick Start (Developer Guide)

### Prerequisites

| Tool | Min Version | Recommended | Note |
|---|---|---|---|
| Python | 3.10+ | 3.12 | Backend Service |
| Node.js | 18+ | 20 LTS | Frontend Build |
| Rust | 1.70+ | latest stable | Tauri Desktop Shell (Optional) |
| pnpm / npm | - | pnpm | Frontend Package Manager |

### Step 1: Install Python

```bash
# macOS (Homebrew)
brew install python@3.12

# Ubuntu / Debian
sudo apt update && sudo apt install python3.12 python3.12-venv python3-pip

# Windows (winget)
winget install Python.Python.3.12

# Verify
python3 --version  # Python 3.12.x
```

### Step 2: Create Virtual Environment & Install Dependencies

```bash
# Enter project root
cd zenflux_agent

# Create venv
python3 -m venv .venv

# Activate venv
# macOS / Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Step 3: Configure Environment Variables

Configuration is located in `config.yaml` in the user data directory. It is created automatically on first launch.

```bash
# macOS: ~/Library/Application Support/com.zenflux.agent/config.yaml
# Linux: ~/.local/share/zenflux-agent/config.yaml
# Windows: %APPDATA%\zenflux-agent\config.yaml
```

**Method 1: Via Frontend Settings (Recommended)**

Launch the app and visit the settings page to enter your API Key.

**Method 2: Manual Edit**

```yaml
api_keys:
  ANTHROPIC_API_KEY: sk-ant-api03-your-key-here  # At least one LLM (Claude recommended)
  # OPENAI_API_KEY: sk-xxx  # Optional
  # DASHSCOPE_API_KEY: sk-xxx  # Optional (Qwen)

llm:
  COT_AGENT_MODEL: claude-sonnet-4-5-20250514  # Default Model
  QOS_LEVEL: PRO  # Service Level

app:
  LOG_LEVEL: INFO  # Log Level
```

### Step 4: Start Backend Service

```bash
# Ensure venv is active
source .venv/bin/activate

# Start dev server (default http://localhost:8000)
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Verify:

```bash
curl http://localhost:8000/health
```

### Step 5: Install Node.js & Frontend Dependencies

```bash
# macOS (Homebrew)
brew install node

# Ubuntu / Debian (via NodeSource)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Windows (winget)
winget install OpenJS.NodeJS.LTS

# Verify
node --version   # v20.x.x
npm --version    # 10.x.x
```

Install frontend dependencies:

```bash
cd frontend
npm install
```

### Step 6: Start Frontend Dev Server

```bash
# In frontend/ directory
npm run dev

# Frontend runs at http://localhost:5174 by default
```

### Step 7 (Optional): Tauri Desktop App Development

To develop the Tauri desktop app, install the Rust toolchain:

```bash
# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# macOS extras
xcode-select --install

# Ubuntu / Debian extras
sudo apt install libwebkit2gtk-4.1-dev build-essential curl wget file \
  libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev

# Verify
rustc --version  # rustc 1.70+
```

Start Tauri dev mode (Frontend + Backend + Desktop Shell):

```bash
cd frontend
npm run tauri:dev
```

Build desktop app:

```bash
cd frontend
npm run tauri:build
```

### Common Commands

```bash
# ---- Backend ----
source .venv/bin/activate            # Activate venv
uvicorn main:app --reload            # Start backend (dev)
pytest tests/unit/ -v                # Unit tests
pytest tests/integration/ -v         # Integration tests

# ---- Frontend ----
cd frontend
npm run dev                          # Start frontend dev
npm run build                        # Build frontend
npm run type-check                   # TypeScript check
npm run lint                         # ESLint check

# ---- Desktop ----
cd frontend
npm run tauri:dev                    # Tauri dev
npm run tauri:build                  # Tauri build
```

### Troubleshooting

**Q: `pip install` fails on system dependencies?**

Some packages (Pillow, sqlite-vec) need system libs:

```bash
# macOS
brew install libjpeg libpng

# Ubuntu / Debian
sudo apt install libjpeg-dev libpng-dev
```

**Q: Frontend page is blank?**

Ensure backend is running at `http://localhost:8000`.

**Q: Tauri build fails?**

Update Rust: `rustup update`

**Q: "Claude API Key is empty" on startup?**

Ensure `.env` exists in root with `ANTHROPIC_API_KEY=...` OR configure `config.yaml` in user data directory.

**Q: Port conflicts?**

Backend default 8000, Frontend 5174. To change:

```bash
# Backend
uvicorn main:app --port 9000 --reload

# Frontend
npm run dev -- --port 3000
```

## Core Mechanisms

### 1. Storage Layer (100% Local)

| Component | Tech | Note |
|---|---|---|
| Msg/Session | SQLite + aiosqlite | WAL mode, Async I/O |
| Full Text | SQLite FTS5 | BM25, unicode61 tokenizer |
| Vector | sqlite-vec | Optional, graceful degradation |
| Skills Cache | SQLite Table | Lazy load + mtime check |

Entry: `infra/local_store/workspace.py` → `LocalWorkspace`

### 2. Skills-First System

2D Classification (OS × Dependency Complexity):

```
                    Dependency →
           ┌──────────┬─────────────┬──────────┬───────────┐
           │ builtin  │ lightweight │ external │ cloud_api │
    OS ↓   │ (Builtin)│ (Light)     │ (Ext App)│ (Cloud)   │
┌──────────┼──────────┼─────────────┼──────────┼───────────┤
│ common   │summarize │excel-       │obsidian  │notion     │
│ (All)    │canvas    │analyzer     │          │gemini-img │
├──────────┼──────────┼─────────────┼──────────┼───────────┤
│ darwin   │screenshot│apple-notes  │peekaboo  │           │
├──────────┼──────────┼─────────────┼──────────┼───────────┤
│ win32    │screenshot│outlook-cli  │powershell│           │
├──────────┼──────────┼─────────────┼──────────┼───────────┤
│ linux    │screenshot│notify-send  │xdotool   │           │
└──────────┴──────────┴─────────────┴──────────┴───────────┘

State: ready → need_auth → need_setup → unavailable
```

### 3. Zero-Config / Low-Config Design

**LLM Configuration** (BYOK - Bring Your Own Key):

| Priority | Plan | Setup Time | Use Case |
|---|---|---|---|
| 1 | Gemini (Free tier) | 3 mins | Most Users |
| 2 | Local (Ollama) | 10 mins | Privacy / Offline |
| 3 | OpenAI / Claude | API Key | Pro Users |

**Local Knowledge Retrieval**:

| Level | Scheme | Config | Dependency |
|---|---|---|---|
| Level 1 | SQLite FTS5 | Zero | Builtin |
| Level 2 | sqlite-vec | One-click | LLM API |
| Level 3 | External Vector DB | Manual | Chroma/Qdrant |

### 4. State Consistency

```
Start Task → Snapshot (File Backup + Env State)
    ↓
Execute → Op Log (with Undo definition)
    ↓
  ┌─ Success → Commit (Clear Snapshot)
  └─ Fail/Interrupt → HITL Ask → Rollback / Keep / Continue
```

### 5. Multi-Dimensional Termination

```
LLM Self-Termination
    + HITL (Human Intervention)
    + User Stop
    + Safety Net (max_turns=100 / 30min timeout)
    + Long Task Confirmation (>20 turns)
```

### 6. OS Compatibility

| Platform | Node | Capabilities |
|---|---|---|
| macOS | `MacOSLocalNode` | AppleScript / screencapture / pbcopy |
| Windows | `WindowsLocalNode` | PowerShell / WinAPI / clip |
| Linux | `LinuxLocalNode` | X11 & Wayland / xdotool / xclip |

### 7. MCP Apps UI Integration

> "Other agents return text, Xiaodazi returns UI."

Tool Execution → Return `_meta.ui` result → Frontend renders iframe → User interacts

## Roadmap

| Phase | Content | Duration |
|---|---|---|
| Phase 1 | Basic Instance (Structure / Persona / Skills) | 2 Weeks |
| Phase 2 | Adaptive Terminator / HITL | 1 Week |
| Phase 3 | OS Compatibility (LocalNodes) | 2 Weeks |
| Phase 4 | MCP Apps Integration | 2 Weeks |
| Phase 5 | Tauri Shell (IPC / Packaging) | 2 Weeks |

## Instance Configuration

ZenFlux Agent uses **Instances** to isolate config and data.

**Detailed Guide**: [instances/README.md](instances/README.md)

Quick view:
- `config.yaml`: Basic config, LLM, Switches.
- `prompt.md`: Persona definition.
- `config/skills.yaml`: Skills list.

Create new instance:
```bash
cp -r instances/_template instances/my-agent
# Edit config.yaml and prompt.md
AGENT_INSTANCE=my-agent uvicorn main:app --host 0.0.0.0 --port 8000
```

## Documentation

- [Instance Configuration](instances/README.md)
- [Desktop Architecture](docs/architecture/xiaodazi-desktop.md)
- [V4 Architecture](docs/architecture/00-ARCHITECTURE-V4.md)
- [Memory Protocol](docs/architecture/01-MEMORY-PROTOCOL.md)
- [Event Protocol](docs/architecture/03-EVENT-PROTOCOL.md)

## License

MIT License

## Authors

- **Liu Yi** (ironliuyi) - liuyi@zenflux.cn
- **Wang Kangcheng** - wangkangcheng@zenflux.cn
- **Zeng Mengqi** - zengmengqi@zenflux.cn
- **Xie Haipeng** - xiehaipeng@zenflux.cn
