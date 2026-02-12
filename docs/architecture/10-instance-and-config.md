# 10 — Instance & Configuration

> Prompt-Driven agent schema generation, instance-level storage isolation, three-tier config priority, and complexity-graded prompts — making each agent instance independently configurable.

[< Prev: LLM Multi-Model](09-llm-multi-model.md) | [Back to Overview](README.md) | [Next: Evaluation >](11-evaluation.md)

---

## Design Goals

1. **Prompt-Driven configuration** — Write a persona prompt, get a fully configured agent. The framework infers tools, planning strategy, and behavior from the prompt.
2. **Instance isolation** — Each agent instance has its own database, memory, vectors, snapshots, and file storage. No cross-contamination.
3. **Override at any level** — Defaults → LLM-inferred schema → explicit config. Each layer can override the previous.

## Architecture

```
┌─ Instance Directory ──────────────────────────────────────────────┐
│  prompt.md              (persona definition)                       │
│  config.yaml            (explicit overrides)                       │
│  config/skills.yaml     (skill groups)                             │
│  config/llm_profiles.yaml (provider templates)                     │
│  config/memory.yaml     (memory config)                            │
│  skills/                (150+ skill directories)                   │
└─────┬──────────────────────┬──────────────────────────────────────┘
      │                      │
      ▼                      ▼
┌─ Schema Generation ──┐   ┌─ Instance Loading ────────────────────┐
│ (one-time)            │   │                                       │
│  prompt.md            │   │  Config Priority Merge:               │
│    │                  │   │    Tier 1: Framework defaults          │
│    ▼                  │   │      ↓ overridden by                  │
│  LLM Analyzer         │   │    Tier 2: agent_schema.yaml ◄────────┤
│    ├──→ agent_schema  │───┤      ↓ overridden by                  │
│    └──→ simple/medium/│   │    Tier 3: config.yaml                │
│         complex_prompt│   │                                       │
└───────────────────────┘   │  create_agent_from_instance()         │
                            │    └──→ Configured Agent              │
                            └──────────────┬────────────────────────┘
                                           │
                                           ▼
                            ┌─ Isolated Storage ────────────────────┐
                            │  data/instances/{name}/db/             │
                            │  data/instances/{name}/memory/         │
                            │  data/instances/{name}/store/          │
                            │  data/instances/{name}/snapshots/      │
                            │  data/instances/{name}/playbooks/      │
                            └───────────────────────────────────────┘
```

## Prompt-Driven Schema

The core idea: **the prompt is the specification**.

When a new instance is created with a `prompt.md`, the framework:

1. Sends the prompt to an LLM analyzer
2. The LLM infers an `agent_schema.yaml` containing:
   - Complexity levels needed
   - Suggested tools and skills
   - Planning strategy
   - Memory configuration
   - Output format preferences
3. Generates complexity-graded system prompts:
   - `simple_prompt.md` — minimal, for quick queries
   - `medium_prompt.md` — standard, for multi-step tasks
   - `complex_prompt.md` — full, for complex planning tasks
4. Caches everything in `prompt_results/`

The schema is regenerated only when `prompt.md` changes.

## Config Priority (Three Tiers)

Configuration follows a strict override chain:

```
Tier 1: Framework defaults (DEFAULT_AGENT_SCHEMA)
  ↓ overridden by
Tier 2: LLM-inferred schema (prompt_results/agent_schema.yaml)
  ↓ overridden by
Tier 3: Explicit config (config.yaml)
```

Example:
```yaml
# agent_schema.yaml (LLM-inferred)
model: claude-sonnet-4-20250514
max_turns: 30
execution_strategy: rvr-b

# config.yaml (explicit override)
agent:
  provider: qwen
  model: qwen3-max    # Overrides schema's model
  # max_turns not specified → uses schema's 30
```

## Instance Directory Structure

```
instances/xiaodazi/
├── prompt.md                    # Agent persona (source of truth)
├── prompt_desktop.md            # Alternative prompt variant
├── config.yaml                  # Explicit configuration overrides
├── config/
│   ├── skills.yaml              # Skill groups + 2D classification
│   ├── llm_profiles.yaml        # Provider templates + role assignments
│   └── memory.yaml              # Memory + search configuration
├── skills/                      # 90+ instance-specific skills
│   ├── skill_registry.yaml      # Skill registration (137 entries)
│   ├── excel-analyzer/
│   ├── file-manager/
│   └── ...
└── prompt_results/              # LLM-generated cache
    ├── agent_schema.yaml        # Inferred agent configuration
    ├── simple_prompt.md         # Minimal system prompt
    ├── medium_prompt.md         # Standard system prompt
    ├── complex_prompt.md        # Full system prompt
    └── _metadata.json           # Generation metadata
```

## Instance Isolation

Each instance gets fully isolated storage, driven by `AGENT_INSTANCE` environment variable:

| Data Type | Path | Example |
|---|---|---|
| Database | `data/instances/{name}/db/` | `data/instances/xiaodazi/db/instance.db` |
| Memory files | `data/instances/{name}/memory/` | `data/instances/xiaodazi/memory/MEMORY.md` |
| Vector store | `data/instances/{name}/store/` | `data/instances/xiaodazi/store/mem0_vectors.db` |
| File uploads | `data/instances/{name}/storage/` | `data/instances/xiaodazi/storage/` |
| Snapshots | `data/instances/{name}/snapshots/` | `data/instances/xiaodazi/snapshots/` |
| Playbooks | `data/instances/{name}/playbooks/` | `data/instances/xiaodazi/playbooks/` |
| Shared models | `data/shared/models/` | Embedding models (shared, not isolated) |

`create_agent_from_instance()` automatically sets `os.environ["AGENT_INSTANCE"]` during loading. All storage components use this to resolve paths.

## Complexity-Graded Prompts

The `PromptGenerator` selects different system prompts based on task complexity:

| Complexity | Prompt | Size | Includes |
|---|---|---|---|
| `simple` | `simple_prompt.md` | ~1000 tokens | Core persona, basic rules, minimal tool guidance |
| `medium` | `medium_prompt.md` | ~2000 tokens | + Planning guidance, tool selection hints |
| `complex` | `complex_prompt.md` | ~3500 tokens | + Full planning protocol, HITL rules, backtrack guidance |

This saves ~2500 tokens on simple queries — significant when most interactions are simple.

### Module Exclusion

Active framework components are excluded from the prompt to avoid redundancy:

```
If intent_analyzer is active → exclude INTENT_RECOGNITION module from prompt
If plan_manager is active → exclude PLAN_OBJECT module from prompt
```

The agent doesn't need instructions for capabilities the framework handles automatically.

## Instance Loading Flow

`create_agent_from_instance()` in `utils/instance_loader.py`:

```
1. Set AGENT_INSTANCE environment variable
2. Load config files (config.yaml, skills.yaml, llm_profiles.yaml, memory.yaml)
3. Load or generate prompt_results (agent_schema.yaml, graded prompts)
4. Merge config: defaults → schema → explicit config
5. Create Agent via AgentFactory.from_schema()
6. Load tools (ToolLoader with enabled_capabilities + skills)
7. Create filtered registry (InstanceRegistry)
8. Inject SkillsLoader + SkillGroupRegistry
9. Configure ToolExecutor + ToolSelector with filtered registry
10. Return fully configured Agent
```

## Template System

New instances are created from `instances/_template/`:

```bash
# Create a new instance
cp -r instances/_template instances/my-agent
# Edit prompt.md with your agent's persona
# Edit config.yaml as needed
# Schema is auto-generated on first request
```

## Key Files

| File | Purpose |
|---|---|
| `utils/instance_loader.py` | `create_agent_from_instance()` — full loading pipeline |
| `core/agent/factory.py` | `AgentFactory` — creates agents from schema |
| `core/prompt/prompt_layer.py` | `PromptParser`, `PromptGenerator` — prompt analysis and assembly |
| `core/prompt/llm_analyzer.py` | LLM-based prompt analysis |
| `instances/xiaodazi/config.yaml` | Main instance configuration |
| `instances/_template/` | Template for new instances |

## Highlights

- **Prompt is the spec** — Non-technical users can define agent behavior by writing natural language. The framework handles the rest.
- **Complexity-graded prompts** — Simple queries don't pay the token cost of full planning instructions.
- **True isolation** — Multiple agents can run simultaneously without data interference.
- **Template system** — Creating a new agent instance is a directory copy + prompt edit.

## Limitations & Future Work

- **No hot-reload** — Config changes require a server restart. Planned: live config reload via API.
- **Single-machine** — Instance isolation is file-system-based. Distributed deployment would need shared storage.
- **Schema regeneration** — Changing `prompt.md` requires regenerating the schema (LLM call). No incremental update.
- **No instance marketplace** — Instances are local directories. A sharing/publishing mechanism is planned.

---

[< Prev: LLM Multi-Model](09-llm-multi-model.md) | [Back to Overview](README.md) | [Next: Evaluation >](11-evaluation.md)
