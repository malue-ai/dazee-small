# 06 — Tool System

> Two-layer registry (global + instance), three-level selection (core → capability → whitelist), and intent-driven pruning that balances capability with token efficiency.

[< Prev: Context Engineering](05-context-engineering.md) | [Back to Overview](README.md) | [Next: Skill Ecosystem >](07-skill-ecosystem.md)

---

## Design Goals

1. **Unified abstraction** — Tools, skills, and code executors share the same `Capability` model. The agent doesn't distinguish between a native tool and an MCP skill.
2. **Token-aware selection** — Simple tasks get 4 tools (~500 tokens). Complex tasks get 15+ tools (~3000 tokens). Tool definitions are expensive.
3. **Dynamic registration** — Instance-level tools (REST APIs) can be registered at runtime without restarting.

## Architecture

```
━━━ Registration ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  capabilities.yaml ──┐
  Skill Scanner ──────┼──→ CapabilityRegistry (global, singleton)
                      │
  Runtime REST API ───┼──→ InstanceRegistry (per-instance)
                      │
━━━ Three-Level Selection ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                      │
                      ▼
  Level 1: Core Tools (always available)
      │
      ▼
  Level 2: Capability Tag Matching (intent-driven)
      │
      ▼
  Level 3: Whitelist Filtering (allowed_tools ∩ matched)
      │
━━━ Execution ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
      │
      ▼
  ToolExecutor ──→ ToolResultCompressor (if > 1500 chars)
```

## Capability Model

Every tool/skill/code executor is represented as a `Capability`:

```yaml
- name: memory_recall
  type: TOOL              # TOOL | SKILL | CODE
  subtype: NATIVE
  provider: user
  level: 1                # 1 = core (always available), 2+ = optional
  implementation:
    module: tools.memory_recall
    class: MemoryRecallTool
  capabilities:           # Semantic tags for selection
    - memory
    - user_profile
  priority: 70            # Higher = preferred when multiple tools match
  cost:
    time: fast
    money: free
  constraints:
    requires_api: false
    requires_network: false
  input_schema:           # Claude-compatible tool schema
    type: object
    properties: { ... }
```

## Two-Layer Registry

| Layer | Source | Lifecycle | Contents |
|---|---|---|---|
| **CapabilityRegistry** (global) | `config/capabilities.yaml` + `skills/library/` scan | Singleton, loaded at startup | All known tools and skills (~70 capabilities) |
| **InstanceRegistry** (per-instance) | Runtime registration via API | Per-agent-instance, dynamic | REST API endpoints, instance-specific tools |

The registries are merged at query time: `get_all_tools_unified()` returns the union of global and instance tools.

## Three-Level Selection

`ToolSelector.select()` builds the tool set in layers:

### Level 1: Core Tools

Tools with `level: 1` are always included (unless overridden by `core_tools_override`):

```
Core tools: plan, nodes, knowledge_search, hitl, memory_recall, observe_screen, ...
```

These are essential for basic agent operation regardless of the task.

### Level 2: Capability Tag Matching

Additional tools are selected based on `required_capabilities` — semantic tags derived from:
- Agent schema `tools` list
- Current plan's tool requirements
- Intent-driven skill group expansion

```
Intent: relevant_skill_groups=["data_analysis"]
  → SkillGroupRegistry expands to capabilities: ["data_processing", "visualization", ...]
  → ToolSelector finds tools with matching capability tags
  → excel-analyzer, csv-processor, chart-generator added
```

### Level 3: Whitelist Filtering

If `allowed_tools` is provided (from schema or intent), only whitelisted tools pass through:

```
allowed_tools ∩ (core_tools ∪ capability_matched_tools) = final_tool_set
```

## Intent-Driven Pruning

For `complexity=simple` tasks, the tool set is drastically reduced:

```python
simple_task_tools = ["nodes", "knowledge_search", "hitl", "memory_recall"]
# Only 4 tools → ~500 tokens of tool definitions
# vs. full set: 15+ tools → ~3000 tokens
```

This saves ~1500 tokens per simple interaction — significant at scale.

## Tool Execution

`ToolExecutor` handles the actual execution:

```
Agent calls tool_use("memory_recall", {query: "user preferences"})
  → ToolExecutor looks up "memory_recall" in registry
  → Dynamically loads MemoryRecallTool class
  → Injects ToolContext (session_id, user_id, instance_id)
  → Calls tool.execute(params, context)
  → Compresses result if > 1500 chars
  → Returns to agent
```

### Invocation Strategies

| Strategy | When | How |
|---|---|---|
| DIRECT | Standard tools | Direct function call |
| PROGRAMMATIC | API-calling tools | HTTP request via configured endpoints |
| STREAMING | Long-running tools | Yield results progressively |

### Error Handling

Tool errors are classified into `ToolError` types, which feed into the RVR-B error classification system:

```
ToolError types: TIMEOUT, AUTH_FAILURE, VALIDATION_ERROR, EXECUTION_ERROR, NOT_FOUND
  → ErrorClassifier determines CONTINUE / BACKTRACK / FAIL_GRACEFULLY / ESCALATE
```

## Key Files

| File | Purpose |
|---|---|
| `core/tool/registry.py` | `CapabilityRegistry`, `InstanceRegistry` |
| `core/tool/selector.py` | `ToolSelector` — three-level selection logic |
| `core/tool/executor.py` | `ToolExecutor` — execution + compression |
| `core/tool/loader.py` | `ToolLoader` — loads tools from registry |
| `core/tool/registry_config.py` | Config helpers (`get_simple_task_tools`, `get_core_tools`) |
| `config/capabilities.yaml` | Global tool/skill definitions |

## Highlights

- **Token-aware** — Tool definitions are one of the largest context consumers. Intent-driven pruning keeps costs proportional to task complexity.
- **Unified model** — No distinction between "tools" and "skills" at the selection/execution layer. A skill is just a capability with a different `type`.
- **Dynamic** — Instance-level tools can be registered via API without restarting the server.
- **Automatic compression** — Large tool results are transparently compressed, with full data saved for later retrieval.

## Limitations & Future Work

- **No tool chaining** — Tools are executed independently. Composing tool outputs (piping) requires the LLM to orchestrate manually.
- **Sequential only** — Tools execute one at a time. Parallel execution for independent tools is planned.
- **Static priority** — Tool priority is configured in YAML, not dynamically adjusted based on success rates.
- **No tool versioning** — Tools don't have version numbers. Breaking changes require manual migration.

---

[< Prev: Context Engineering](05-context-engineering.md) | [Back to Overview](README.md) | [Next: Skill Ecosystem >](07-skill-ecosystem.md)
