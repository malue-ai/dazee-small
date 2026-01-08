# Mem0 Embedding 配置指南

## ⚠️ 重要说明：Claude 不提供 Embedding 服务

**Claude (Anthropic) 只提供大语言模型 (LLM)**，不提供 text embedding 向量化服务。

### Mem0 架构中的两个角色

| 组件 | 功能 | Claude 是否支持 |
|------|------|----------------|
| **Embedder** | 将文本转换为向量，存储到 Qdrant | ❌ **不支持** |
| **LLM** | 从对话中提取记忆事实 (fact extraction) | ✅ **支持** |

## 🎯 推荐方案：混合使用

```
┌─────────────────────────────────────────────────────┐
│                    Mem0 架构                         │
├─────────────────────────────────────────────────────┤
│                                                      │
│  用户对话                                            │
│     │                                                │
│     ▼                                                │
│  ┌──────────────────────────┐                       │
│  │  LLM (Claude)            │ ← ANTHROPIC_API_KEY   │
│  │  - 提取记忆事实          │                       │
│  │  - 理解对话上下文        │                       │
│  └──────────┬───────────────┘                       │
│             │                                        │
│             │ Facts: ["用户喜欢咖啡", "偏好美式"]    │
│             │                                        │
│             ▼                                        │
│  ┌──────────────────────────┐                       │
│  │  Embedder (OpenAI/其他)  │ ← OPENAI_API_KEY      │
│  │  - 将文本转换为向量      │   (或其他 API Key)    │
│  │  - 生成 1536 维向量      │                       │
│  └──────────┬───────────────┘                       │
│             │                                        │
│             │ Vector: [0.123, -0.456, ...]          │
│             │                                        │
│             ▼                                        │
│  ┌──────────────────────────┐                       │
│  │  Qdrant 向量数据库       │ ← 腾讯云服务          │
│  │  - 存储向量              │                       │
│  │  - 相似度搜索            │                       │
│  └──────────────────────────┘                       │
│                                                      │
└─────────────────────────────────────────────────────┘
```

**结论**：
- **LLM 使用 Claude** ✅（您的需求）
- **Embedding 必须用其他提供商**（技术限制）

## 📊 Embedding 方案对比

### 方案 1：OpenAI Embedding（推荐 ⭐）

**优点**：
- ✅ 性价比高（$0.02/1M tokens）
- ✅ 质量稳定，广泛使用
- ✅ API 简单，无需部署

**缺点**：
- ❌ 需要额外的 OpenAI API Key

**配置**：
```bash
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-proj-xxx
EMBEDDING_MODEL=text-embedding-3-small  # 1536维
```

**成本估算**：
- 每条记忆约 50-100 tokens
- 1000 条记忆 ≈ $0.002（不到 1 分钱）

---

### 方案 2：Google Embedding

**优点**：
- ✅ 如果已有 Google Cloud 账号，无额外成本
- ✅ 与 Gemini 生态整合

**缺点**：
- ❌ 需要 Google Cloud 账号和配置

**配置**：
```bash
EMBEDDING_PROVIDER=google
GOOGLE_API_KEY=your-google-api-key
EMBEDDING_MODEL=models/embedding-001  # 768维
```

**注意**：维度是 768，需要重新配置 Qdrant collection。

---

### 方案 3：Hugging Face Embedding

**优点**：
- ✅ 开源模型，可本地部署
- ✅ 免费

**缺点**：
- ❌ 需要自行部署服务
- ❌ 质量可能不如商业模型

**配置**：
```bash
EMBEDDING_PROVIDER=huggingface
HUGGINGFACE_API_KEY=hf_xxx
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2  # 384维
```

---

### 方案 4：Ollama 本地 Embedding（完全免费）

**优点**：
- ✅ 完全免费，本地运行
- ✅ 无需 API Key
- ✅ 数据隐私

**缺点**：
- ❌ 需要本地部署 Ollama
- ❌ 需要硬件资源（GPU 加速更好）

**配置**：
```bash
# 1. 安装 Ollama
# macOS/Linux: https://ollama.ai/download

# 2. 拉取 embedding 模型
ollama pull nomic-embed-text

# 3. 配置环境变量
EMBEDDING_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
EMBEDDING_MODEL=nomic-embed-text  # 768维
```

---

## 🎯 推荐配置组合

### 组合 1：Claude + OpenAI Embedding（推荐 ⭐⭐⭐）

**最佳性价比，质量稳定**

```bash
# Embedding: OpenAI
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-proj-xxx
EMBEDDING_MODEL=text-embedding-3-small

# LLM: Claude
MEM0_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-xxx
MEM0_LLM_MODEL=claude-sonnet-4-5-20250929
```

**月度成本估算**（假设 10,000 次对话）：
- Embedding: $2
- LLM (Fact Extraction): $50
- **总计**: ~$52/月

---

### 组合 2：Claude + Ollama Embedding（完全免费）

**完全本地化，无 API 成本**

```bash
# Embedding: Ollama (本地)
EMBEDDING_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
EMBEDDING_MODEL=nomic-embed-text

# LLM: Claude
MEM0_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-xxx
MEM0_LLM_MODEL=claude-sonnet-4-5-20250929
```

**月度成本估算**：
- Embedding: $0（本地）
- LLM (Fact Extraction): $50
- **总计**: ~$50/月

**前提**：需要本地运行 Ollama（建议有 GPU）

---

## 🔧 实际配置示例

### 示例 1：使用 Claude + OpenAI Embedding

创建 `.env` 文件：

```bash
# Qdrant
QDRANT_URL=http://172.16.32.30:6333
MEM0_COLLECTION_NAME=mem0_user_memories

# Embedding: OpenAI
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-proj-your-openai-key
EMBEDDING_MODEL=text-embedding-3-small

# LLM: Claude
MEM0_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-your-claude-key
MEM0_LLM_MODEL=claude-sonnet-4-5-20250929
```

### 示例 2：使用 Claude + Ollama Embedding（本地）

```bash
# Qdrant
QDRANT_URL=http://172.16.32.30:6333
MEM0_COLLECTION_NAME=mem0_user_memories

# Embedding: Ollama (本地)
EMBEDDING_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
EMBEDDING_MODEL=nomic-embed-text

# LLM: Claude
MEM0_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-your-claude-key
MEM0_LLM_MODEL=claude-sonnet-4-5-20250929
```

**注意**：使用 Ollama 前需要先安装并拉取模型：

```bash
# 安装 Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 拉取 embedding 模型
ollama pull nomic-embed-text

# 验证
ollama list
```

---

## 🔍 验证配置

运行测试脚本：

```bash
python test_mem0_setup.py
```

应该看到：

```
============================================================
3. 测试 Mem0 Memory Pool
============================================================

初始化 Mem0 Pool...
✅ Embedder: openai (text-embedding-3-small)
✅ LLM: anthropic (claude-sonnet-4-5-20250929)
✅ Vector Store: qdrant (mem0_user_memories)

执行健康检查...
✅ Mem0 Pool 健康
```

---

## ❓ 常见问题

### Q1: 为什么不能全部用 Claude？

**A**: Claude 只提供 LLM 服务，不提供 embedding 向量化服务。这是 Anthropic 公司的产品策略决定的。

### Q2: 用 OpenAI Embedding 会不会泄露数据给 OpenAI？

**A**: OpenAI 的 API 政策声明不会使用 API 数据训练模型。但如果对隐私极其敏感，建议使用**方案 4: Ollama 本地 Embedding**。

### Q3: 不同 Embedding 模型的向量维度不同，如何选择？

**A**: 
- **1536 维**（OpenAI text-embedding-3-small）：推荐，性价比高
- **768 维**（Google, Ollama）：维度低，存储省空间
- **384 维**（Hugging Face 小模型）：最轻量

**注意**：更改维度需要重建 Qdrant collection！

### Q4: 可以混用不同 LLM 提供商吗？

**A**: 可以！配置独立：
- Agent 主模型：`CLAUDE_MODEL=...`
- Mem0 fact extraction：`MEM0_LLM_PROVIDER=anthropic`

### Q5: 如何降低成本？

**成本优化建议**：
1. **Embedding**: 用 Ollama 本地（免费）
2. **LLM**: 用 Claude Haiku（便宜，`claude-3-5-haiku-20241022`）
3. **减少 Mem0 调用频率**：不是每条消息都需要存储

---

## 📖 相关文档

- [Mem0 官方文档](https://docs.mem0.ai/)
- [Anthropic Claude API](https://docs.anthropic.com/)
- [OpenAI Embedding](https://platform.openai.com/docs/guides/embeddings)
- [Ollama Embedding](https://ollama.ai/library/nomic-embed-text)
- [Qdrant 文档](https://qdrant.tech/documentation/)

