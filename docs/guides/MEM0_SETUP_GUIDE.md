# Mem0 + Qdrant 快速设置指南

## 1. 腾讯云 Qdrant 配置

### 1.1 获取连接信息

从腾讯云控制台获取 Qdrant 实例信息：

```
实例详情页面：
- 内网地址：http://172.16.32.30:6333  （同 VPC 内访问）
- 外网地址：http://gz-vdb-3a69s7xq.sql.tencentcdb.com:8100  （公网访问）
- 端口：80 (外网) / 6333 (内网)
```

**推荐配置**：
- **生产环境**：使用内网地址（更快、更安全、免流量费）
- **开发环境**：使用外网地址（方便本地调试）

### 1.2 创建 .env 文件

```bash
cd /Users/liuyi/Documents/langchain/CoT_agent/mvp/zenflux_agent

# 复制模板
cp env.template .env

# 编辑配置
vim .env  # 或使用任何编辑器
```

### 1.3 填写配置（根据您的截图）

```bash
# 腾讯云 Qdrant（使用内网地址）
QDRANT_URL=http://172.16.32.30:6333
QDRANT_API_KEY=  # 如果未启用认证，留空

# 或使用外网地址
# QDRANT_URL=http://gz-vdb-3a69s7xq.sql.tencentcdb.com:8100

# Mem0 配置
MEM0_COLLECTION_NAME=mem0_user_memories

# OpenAI 配置（必需）
OPENAI_API_KEY=sk-proj-your-key-here
EMBEDDING_MODEL=text-embedding-3-small
MEM0_LLM_MODEL=gpt-4o-mini

# Claude 配置
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

## 2. 验证配置

### 2.1 安装依赖

```bash
cd /Users/liuyi/Documents/langchain/CoT_agent/mvp/zenflux_agent

# 安装 Mem0
pip install mem0ai

# 安装 Qdrant 客户端
pip install qdrant-client
```

### 2.2 测试连接

创建测试脚本 `test_mem0_setup.py`：

```python
import os
from core.memory.mem0 import get_mem0_pool

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

# 测试 Mem0 连接
def test_mem0_connection():
    print("1. 测试 Mem0 + Qdrant 连接...")
    
    pool = get_mem0_pool()
    
    # 健康检查
    health = pool.health_check()
    print(f"   健康状态: {health}")
    
    if health["status"] != "healthy":
        print(f"   ❌ 连接失败: {health.get('error')}")
        return False
    
    # 测试添加记忆
    print("\n2. 测试添加用户记忆...")
    result = pool.add(
        user_id="test_user_123",
        messages=[
            {"role": "user", "content": "我喜欢喝咖啡"},
            {"role": "assistant", "content": "好的，我记住了您喜欢咖啡。"}
        ],
        metadata={"source": "test"}
    )
    print(f"   添加结果: {result}")
    
    # 测试搜索记忆
    print("\n3. 测试搜索用户记忆...")
    memories = pool.search(
        user_id="test_user_123",
        query="用户的饮品偏好",
        limit=5
    )
    print(f"   搜索到 {len(memories)} 条记忆:")
    for i, mem in enumerate(memories):
        print(f"   [{i+1}] {mem.get('memory')} (score: {mem.get('score', 0):.2f})")
    
    print("\n✅ 所有测试通过！Mem0 配置成功。")
    return True

if __name__ == "__main__":
    try:
        test_mem0_connection()
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
```

运行测试：

```bash
python test_mem0_setup.py
```

## 3. Qdrant Collection 初始化

首次运行时，Mem0 会自动创建 collection。如果需要手动管理：

### 3.1 使用 Qdrant Web UI

访问腾讯云 Qdrant 控制台或直接访问：
```
http://172.16.32.30:6333/dashboard  # 内网
```

### 3.2 使用 Python 脚本

```python
from qdrant_client import QdrantClient

# 连接 Qdrant
client = QdrantClient(
    url="http://172.16.32.30:6333",
    # api_key="your-key"  # 如果需要
)

# 查看所有 collections
collections = client.get_collections()
print("现有 Collections:", [c.name for c in collections.collections])

# 创建 collection（Mem0 会自动创建，一般不需要手动）
# client.create_collection(
#     collection_name="mem0_user_memories",
#     vectors_config=models.VectorParams(
#         size=1536,  # text-embedding-3-small 的维度
#         distance=models.Distance.COSINE
#     )
# )
```

## 4. 集成到 Agent

### 4.1 自动注入用户画像

Agent 会自动从 Mem0 获取用户画像并注入到 System Prompt：

```python
# simple_agent.py 会自动处理
# 无需手动调用，框架透明
```

### 4.2 API 端点使用

**搜索用户记忆**：
```bash
curl -X POST http://localhost:8000/api/v1/mem0/search \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_123",
    "query": "用户的偏好",
    "limit": 10
  }'
```

**批量更新记忆**（定时任务）：
```bash
curl -X POST http://localhost:8000/api/v1/mem0/batch_update \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_123",
    "updates": [
      {
        "id": "mem_xxx",
        "memory": "更新后的记忆内容",
        "metadata": {"source": "batch_job"}
      }
    ]
  }'
```

## 5. 常见问题

### Q1: 连接超时

```
Error: Connection timeout
```

**解决方案**：
1. 检查网络连接（内网需要在同一 VPC）
2. 确认端口是否正确（内网 6333，外网 80）
3. 检查安全组规则是否开放

### Q2: 认证失败

```
Error: Authentication failed
```

**解决方案**：
1. 检查 `QDRANT_API_KEY` 是否正确
2. 确认腾讯云实例是否启用了认证

### Q3: Collection 不存在

```
Error: Collection not found
```

**解决方案**：
Mem0 会自动创建 collection，如果报错：
```python
from core.memory.mem0 import get_mem0_pool
pool = get_mem0_pool()
# 首次调用会自动创建 collection
pool.search(user_id="test", query="test", limit=1)
```

### Q4: 向量维度不匹配

```
Error: Vector dimension mismatch
```

**解决方案**：
如果更改了 `EMBEDDING_MODEL`，需要删除旧的 collection 并重建：
```python
from qdrant_client import QdrantClient

client = QdrantClient(url=os.getenv("QDRANT_URL"))
client.delete_collection("mem0_user_memories")
# 重启服务，Mem0 会自动重建
```

## 6. 生产环境最佳实践

### 6.1 性能优化

```bash
# .env 配置
MEM0_COLLECTION_NAME=prod_memories  # 生产环境独立 collection
EMBEDDING_MODEL=text-embedding-3-small  # 性价比高
MEM0_LLM_MODEL=gpt-4o-mini  # 快速且便宜
```

### 6.2 监控指标

建议监控：
- Qdrant 连接状态
- 记忆搜索延迟（< 500ms）
- Embedding API 调用量
- Collection 存储大小

### 6.3 备份策略

定期备份 Qdrant 数据：
```bash
# 使用腾讯云控制台的备份功能
# 或使用 Qdrant 快照 API
```

## 7. 下一步

- ✅ 完成 Qdrant 配置
- ✅ 运行测试脚本验证
- ✅ 集成到 Agent
- 📊 监控性能指标
- 🔄 设置定时批量更新任务（可选）

---

**需要帮助？**
- 查看 Qdrant 文档：https://qdrant.tech/documentation/
- 查看 Mem0 文档：https://docs.mem0.ai/
- 腾讯云向量数据库：https://cloud.tencent.com/product/vdb

