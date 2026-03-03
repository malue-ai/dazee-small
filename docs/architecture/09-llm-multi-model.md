# 09 — LLM Multi-Model Support

> Unified abstraction over 6 LLM providers with format adapters, ModelRouter failover, YAML-driven profiles, and one-key provider switching — from free Gemini to local Ollama to cloud Claude.

[< Prev: Memory System](08-memory-system.md) | [Back to Overview](README.md) | [Next: Instance & Config >](10-instance-and-config.md)

---

## Design Goals

1. **Provider freedom** — Users choose their LLM provider based on budget, privacy, and capability. The framework adapts transparently.
2. **Zero-effort switching** — Change one config value (`agent.provider: qwen`) and the entire model family switches.
3. **Resilient routing** — If the primary model fails, the system automatically tries alternatives with health tracking and cooldown.

## Architecture

```
  Agent._llm
      │
      ▼
┌─ ModelRouter ──────────────────────────────────────────────────────────────────┐
│  RouterPolicy (max_failures, cooldown)                                          │
│  LLMHealthMonitor (failure_count, cooldown_until, probe)                        │
│  RouteTarget[] (ordered by priority)                                            │
└──────┬────────────┬────────────┬────────────┬────────────┬────────────┬────────┘
       │            │            │            │            │            │
       ▼            ▼            ▼            ▼            ▼            ▼
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│  Claude   │ │  OpenAI  │ │   Qwen   │ │ DeepSeek │ │  Gemini  │ │   GLM    │
│  Service  │ │  Service │ │  Service │ │  Service │ │  Service │ │  Service │
└─────┬────┘ └─────┬────┘ └─────┬────┘ └─────┬────┘ └─────┬────┘ └─────┬────┘
      ▼            ▼            ▼            ▼            ▼            ▼
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│  Claude   │ │  OpenAI  │ │  OpenAI  │ │ DeepSeek │ │  Gemini  │ │  OpenAI  │
│  Adaptor  │ │  Adaptor │ │  Adaptor │ │  Adaptor │ │  Adaptor │ │  Adaptor │
│ (native)  │ │(func call)│ │(func call)│ │(reasoning)│ │ (parts) │ │(func call)│
└──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘
```

## Supported Providers

| Provider | Models | Protocol | Thinking Support |
|---|---|---|---|
| **Claude** (Anthropic) | claude-sonnet-4, claude-haiku, opus | Native Messages API | Extended thinking |
| **OpenAI** | gpt-4o, gpt-4-turbo, o1, o3 | Chat Completions | Reasoning tokens |
| **Qwen** (Alibaba) | qwen3-max, qwen-plus, qwen-turbo | OpenAI-compatible | Thinking blocks |
| **DeepSeek** | deepseek-chat, deepseek-reasoner | OpenAI-compatible | `reasoning_content` |
| **Gemini** (Google) | gemini-2.5-pro, gemini-flash | Generative Language API | Thinking |
| **GLM** (Zhipu AI) | glm-4-plus, glm-4-flash, glm-4-long | OpenAI-compatible | — |
| **Ollama** (Local) | llama3, mistral, qwen2, etc. | OpenAI-compatible | Varies |

## Format Adapters

Each provider has a different API format for tool calling. Adapters handle bidirectional conversion:

### The Problem

```
Claude format:    content blocks with tool_use / tool_result
OpenAI format:    tool_calls array + separate tool messages
Gemini format:    parts with function_call / function_response
GLM format:       OpenAI-compatible tool_calls (via Zhipu AI API)
```

The agent internally uses Claude's format (content blocks). Adapters convert on the fly:

### ClaudeAdaptor

Handles Claude's strict requirements:
- **Interleave separation** — Claude requires strict user/assistant alternation. Adjacent same-role messages are merged.
- **Tool pair enforcement** — Every `tool_use` must have a matching `tool_result`. Orphaned blocks are removed.
- **Consecutive dedup** — Duplicate tool_use blocks (from retries) are cleaned.

### OpenAIAdaptor

Converts between Claude and OpenAI formats:
- `tool_use` block → `tool_calls` array in assistant message
- `tool_result` block → `tool` role message with `tool_call_id`
- Handles function calling response format differences

### DeepSeekAdaptor

Extends OpenAI adapter for DeepSeek's `reasoning_content` field:
- Maps `reasoning_content` → thinking blocks (compatible with Claude's extended thinking)

### GeminiAdaptor

Converts to/from Gemini's `parts`-based format:
- `tool_use` → `function_call` part
- `tool_result` → `function_response` part
- Handles Gemini's multi-part message structure

## ModelRouter & Failover

`ModelRouter` wraps multiple LLM services and provides automatic failover:

```
Request arrives
  → Check Target 1 (primary): healthy? → Try it
    → Success → record_success(), return
    → Failure → record_failure(), check cooldown
  → Check Target 2 (fallback): healthy? → Try it
    → Success → return
    → Failure → record_failure()
  → All targets exhausted → raise error
```

### Health Tracking

| Metric | Purpose |
|---|---|
| `failure_count` | Consecutive failures per target |
| `cooldown_until` | Timestamp after which a failed target can be retried |
| `last_success` | Last successful call timestamp |

### Probe Recovery

When all targets are in cooldown, `probe()` sends a lightweight ping to check if a service has recovered:

```python
async def probe(target):
    # Send minimal request: "Say 'ok'"
    # If successful, reset cooldown and failure count
    # Target becomes available again
```

### Tool Filtering

Different providers support different tool features. `_filter_tools_for_provider()` automatically removes unsupported tool definitions:

```
Claude: supports all tool features (computer_use, bash, text_editor)
OpenAI: supports function calling, no computer_use
Qwen: supports function calling via OpenAI-compatible API
Gemini: supports function_call, different schema format
```

## LLM Profiles (YAML)

Provider configuration is managed via `llm_profiles.yaml`:

```yaml
providers:
  qwen:
    agent: { model: qwen3-max, ... }
    heavy: { model: qwen-plus, ... }
    light: { model: qwen-turbo, ... }
    intent: { model: qwen-turbo, ... }

  claude:
    agent: { model: claude-sonnet-4-6, ... }
    heavy: { model: claude-sonnet-4-6, ... }
    light: { model: claude-haiku-4-5-20251001, ... }
    intent: { model: claude-haiku-4-5-20251001, ... }

  deepseek:
    agent: { model: deepseek-chat, ... }
    ...
```

### Role-Based Model Assignment

| Role | Purpose | Typical Model |
|---|---|---|
| `agent` | Main agent execution (RVR-B loop) | Most capable model |
| `heavy` | Complex reasoning tasks | Same as agent or stronger |
| `light` | Simple tasks, memory extraction | Fastest/cheapest model |
| `intent` | Intent analysis | Fast model (Haiku-class) |

### One-Key Switching

```yaml
# instances/xiaodazi/config.yaml
agent:
  provider: qwen    # Change this one value
  model: qwen3-max  # Optional: override specific model
```

Changing `provider` automatically maps all roles to the corresponding provider template. No need to update individual model references.

## Progressive Model Strategy

For open-source deployment, users choose based on budget:

| Priority | Provider | Cost | Setup Time | Best For |
|---|---|---|---|---|
| 1 | Gemini (free tier) | Free (1500 req/day) | 3 min (API key) | Getting started |
| 2 | Ollama / LM Studio | Free (local GPU) | 10 min install | Privacy, offline |
| 3 | Qwen / DeepSeek | Low cost | 5 min (API key) | Production use |
| 4 | Claude / OpenAI | Higher cost | 5 min (API key) | Maximum capability |

## Key Files

| File | Purpose |
|---|---|
| `core/llm/base.py` | `BaseLLMService`, `LLMConfig`, `Message`, `LLMResponse` |
| `core/llm/adaptor.py` | `BaseAdaptor`, `ClaudeAdaptor`, `OpenAIAdaptor`, `DeepSeekAdaptor`, `GeminiAdaptor` |
| `core/llm/router.py` | `ModelRouter`, `RouterPolicy`, `RouteTarget` |
| `core/llm/claude.py` | Claude service implementation |
| `core/llm/openai.py` | OpenAI service implementation |
| `core/llm/qwen.py` | Qwen service implementation |
| `core/llm/deepseek.py` | DeepSeek service implementation |
| `instances/xiaodazi/config/llm_profiles.yaml` | Provider templates and role assignments |

## Highlights

- **True multi-provider** — Not just "OpenAI-compatible." Each provider has a dedicated adapter handling format quirks correctly.
- **Lossless conversion** — Tool calls, thinking blocks, and multi-modal content are preserved across provider switches.
- **Self-healing routing** — Failed providers are automatically cooled down and probed for recovery.
- **One config change** — Switching from Claude to Qwen requires changing one YAML value, not touching any code.

## Limitations & Future Work

- **No cost optimization** — The router doesn't consider cost per token. Planned: cost-aware routing that prefers cheaper models for simple tasks.
- **No streaming failover** — If a stream fails mid-response, the entire request fails. Planned: mid-stream recovery.
- **Limited local model tool support** — Smaller local models (7B-13B) often struggle with tool calling. Better prompt engineering for local models is planned.
- **No model benchmarking** — No built-in way to compare model quality for this specific agent. Planned: integration with the evaluation system.

---

[< Prev: Memory System](08-memory-system.md) | [Back to Overview](README.md) | [Next: Instance & Config >](10-instance-and-config.md)
