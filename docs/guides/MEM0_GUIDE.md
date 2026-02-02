# Mem0 使用指南（统一版）

> **更新日期**：2026-01-20  
> **范围**：配置、Embedding 选择、Schema 入口、验证方式

---

## 1. 设计原则（与 Mem0 框架对齐）

- **Extraction Phase**：从对话中抽取新记忆（LLM 驱动）
- **Update Phase**：基于相似记忆进行 ADD / UPDATE / NONE / DELETE（LLM 驱动）
- 数据库存储是中心仓库，检索用于更新阶段的候选集合

---

## 2. 必需环境变量

```bash
# Mem0 集合
MEM0_COLLECTION_NAME=mem0_user_memories

# Vector Store（腾讯云 VectorDB 或 Qdrant）
TENCENT_VDB_URL=...
TENCENT_VDB_API_KEY=...

# Embedding（示例：OpenAI）
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-...
EMBEDDING_MODEL=text-embedding-3-small

# LLM（示例：Claude）
MEM0_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
MEM0_LLM_MODEL=claude-sonnet-4-5-20250929
```

---

## 3. Embedding 选择（简表）

| 方案 | 优点 | 约束 |
|---|---|---|
| OpenAI Embedding | 质量稳定、配置简单 | 需 OpenAI Key |
| Ollama 本地 | 免费、本地化 | 需本地服务 |
| Google / HF | 可选方案 | 维度差异需重建 collection |

> Claude 只提供 LLM，不提供 embedding 服务。

---

## 4. Schema 入口（唯一真源）

请以代码为准：`core/memory/mem0/schemas/`

核心类型：
- `FragmentMemory`（碎片记忆）
- `BehaviorPattern`（行为模式）
- `WorkPlan`（计划）
- `EmotionState`（情绪）
- `UserPersona`（用户画像）
- `MemoryCard`（显式记忆）

---

## 5. 验证与测试

```bash
# 基础连接验证
python tests/test_mem0_setup.py

# 端到端验证（需要完整环境变量）
python tests/test_mem0_e2e.py
```

---

## 6. 参考

- 论文：Mem0 — Building Production-Ready AI Agents with Scalable Long-Term Memory  
  https://arxiv.org/pdf/2504.19413

