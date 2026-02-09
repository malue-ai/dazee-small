# 语义搜索配置与调用路径验证

本文档描述从 `config/memory.yaml` 到运行时生效的完整调用路径，用于全链路验证与排错。

## 1. 配置文件

**路径**: `instances/{instance_name}/config/memory.yaml`

```yaml
semantic_search:
  mode: disabled   # disabled | local | cloud
  local:
    repo: ""       # 留空 = lm-kit/bge-m3-gguf
    model: ""      # 留空 = bge-m3-Q4_K_M.gguf
  cloud:
    model: ""      # 留空 = text-embedding-3-small
    # base_url: ""
    # api_key: ""
memory:
  enabled: true
```

- **只改 `mode`**：local 用默认 BGE-M3 Q4 GGUF，cloud 用默认 text-embedding-3-small。
- **改 local.repo / local.model 或 cloud.model**：高级用法，需与下游读取一致。

---

## 2. 读取路径（config → 内部结构）

| 步骤 | 位置 | 输入 | 输出 |
|------|------|------|------|
| 1 | `knowledge_service._load_knowledge_config()` | `config/memory.yaml` | `dict`: `semantic_enabled`, `embedding_provider`, `embedding_model?`, `gguf_repo?`, `gguf_model?`, `embedding_base_url?`, `embedding_api_key?` |
| 2 | `knowledge_service._create_knowledge_manager()` | 上一步 dict | 设置 `os.environ`: `GGUF_REPO`, `GGUF_MODEL`, `OPENAI_BASE_URL`, `OPENAI_API_KEY`（仅当 config 中非空）；创建 `LocalKnowledgeManager(embedding_provider, embedding_model)` |

**Key 映射**（memory.yaml → 内部）:

- `semantic_search.mode` → `semantic_enabled` (bool), `embedding_provider` ("auto"|"local"|"openai")
- `semantic_search.local.repo` → `gguf_repo` → `os.environ["GGUF_REPO"]`
- `semantic_search.local.model` → `gguf_model` → `os.environ["GGUF_MODEL"]`
- `semantic_search.cloud.model` → `embedding_model` → 传给 `LocalKnowledgeManager` 再传给 `create_embedding_provider(..., model=...)`
- `semantic_search.cloud.base_url` → `embedding_base_url` → `os.environ["OPENAI_BASE_URL"]`
- `semantic_search.cloud.api_key` → `embedding_api_key` → `os.environ["OPENAI_API_KEY"]`

---

## 3. 运行时使用路径

### 3.1 知识检索（KnowledgeManager）

```
get_knowledge_manager()
  → _create_knowledge_manager()
      → _load_knowledge_config()   # 读 config/memory.yaml
      → 设置 os.environ（见上）
      → LocalKnowledgeManager(embedding_provider, embedding_model)
  → km.search() 等
      → _get_embedding_provider()
          → create_embedding_provider(provider=embedding_provider, model=embedding_model)
```

- **provider=local**: `create_embedding_provider("local")` → `GGUFEmbeddingProvider()`，内部 `repo_id=os.getenv("GGUF_REPO", DEFAULT_GGUF_REPO)`, `filename=os.getenv("GGUF_MODEL", DEFAULT_GGUF_FILE)`。
- **provider=openai**: `create_embedding_provider("openai", model=embedding_model)` → `OpenAIEmbeddingProvider(model=model or "text-embedding-3-small")`，api_key/base_url 用 `os.getenv`（已被 _create_knowledge_manager 注入）。

### 3.2 意图缓存（IntentCache）

```
IntentSemanticCache.lookup() / store()
  → EmbeddingService.embed()
      → _get_provider()
          → create_embedding_provider("auto")   # 固定 "auto"，不读 memory.yaml
```

- IntentCache 不读 instance 配置，始终用 `auto`（GGUF → sentence-transformers → OpenAI）。
- 若选 local 且已下载默认模型，`auto` 会选到 GGUF；若未下载则静默降级为 hash 匹配。
- **自定义 local repo/model 仅对 KnowledgeManager 生效**；IntentCache 的 GGUF 仍为默认（除非在调用前设置了 `GGUF_REPO`/`GGUF_MODEL` 且 IntentCache 尚未初始化）。

### 3.3 Mem0 记忆池

```
get_mem0_pool() → _create_memory() → _create_local_embedder()
  → 检查 get_models_dir() / os.getenv("GGUF_MODEL", DEFAULT_GGUF_FILE) 是否存在
  → 存在则 GGUFEmbeddingProvider()（内部读 GGUF_REPO/GGUF_MODEL），否则云端
```

- 不读 `config/memory.yaml`，但使用与 KnowledgeManager 相同的 env：若已通过 memory 配置或 reload 设置 `GGUF_REPO`/`GGUF_MODEL`，Mem0 会使用同一套本地模型。

---

## 4. 写入路径（用户操作 → 落盘）

| 入口 | 位置 | 行为 |
|------|------|------|
| POST /api/v1/settings/semantic-search/setup | `settings_service.setup_semantic_search(mode)` | `_write_instance_memory_config(mode)` 只写 `semantic_search.mode` 到 `config/memory.yaml`；若 mode=local 且默认模型未下载则 `download_gguf_model()`；最后 `_reload_semantic_components()` |

- **只写入 `mode`**，不写入 `local.repo`/`local.model` 或 `cloud.*`；高级字段需用户手改 YAML。

---

## 5. 验证清单

- [ ] **默认 local**：`mode: local`，不填 local.repo/model → 使用 `lm-kit/bge-m3-gguf` + `bge-m3-Q4_K_M.gguf`，KnowledgeManager 与 IntentCache（若已下载）一致。
- [ ] **默认 cloud**：`mode: cloud`，不填 cloud.model → OpenAI `text-embedding-3-small`，需 `OPENAI_API_KEY`。
- [ ] **自定义 local**：填 `local.repo` / `local.model` → `_load_knowledge_config` 得到 `gguf_repo`/`gguf_model` → `_create_knowledge_manager` 设置 `GGUF_REPO`/`GGUF_MODEL` → `GGUFEmbeddingProvider()` 与 Mem0Pool 的 `_create_local_embedder()` 均读取 env。文件需用户自行放到 `get_models_dir()`，不自动下载。
- [ ] **自定义 cloud**：填 `cloud.model`（及可选 base_url/api_key）→ `embedding_model` 传入 LocalKnowledgeManager → `create_embedding_provider("openai", model=...)`；base_url/api_key 经 env 注入。
- [ ] **Setup 后生效**：`setup_semantic_search()` 写 `config/memory.yaml` 后调用 `_reload_semantic_components()`，重置 KnowledgeManager 单例并重置 IntentCache 的 EmbeddingService，无需重启进程。
- [ ] **Mem0 与 Knowledge 同源**：Mem0Pool 使用 `GGUF_MODEL`（及 GGUFEmbeddingProvider 读 `GGUF_REPO`/`GGUF_MODEL`），与 KnowledgeManager 共用同一套 env，自定义 local 模型时记忆与知识检索一致。

---

## 6. 默认值汇总

| 层级 | 默认 |
|------|------|
| `embeddings.py` | `DEFAULT_GGUF_REPO`, `DEFAULT_GGUF_FILE`, OpenAI `text-embedding-3-small` |
| `GGUFEmbeddingProvider` | `repo_id=os.getenv("GGUF_REPO", DEFAULT_GGUF_REPO)`, `filename=os.getenv("GGUF_MODEL", DEFAULT_GGUF_FILE)` |
| `memory.yaml` | `mode: disabled`；local.repo/model、cloud.model 留空即用上述默认 |
