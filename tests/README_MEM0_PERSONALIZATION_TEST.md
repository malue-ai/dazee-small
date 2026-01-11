# Mem0 个性化机制验证测试

## 概述

`test_mem0_personalization_e2e.py` 是一个完整的端到端测试，用于验证 Mem0 用户记忆机制的有效性。

## 核心验证流程

```
跨会话对话历史 → Mem0 自动提取特征 → 语义检索 → Prompt 注入 → 个性化响应
```

### 测试场景

**用户 Alice（前端开发者）**
- 会话 1: "我是前端开发者，使用 React 和 TypeScript"
- 会话 2: "我喜欢函数式组件和 hooks"
- 会话 3: "我用 Tailwind CSS 做样式"
- **验证查询**: "帮我写一个用户注册表单组件"
- **期望**: 检索到 React 偏好，响应使用 React 函数组件

**用户 Bob（产品经理）**
- 会话 1: "我是产品经理，需要做数据分析"
- 会话 2: "我偏好用图表和可视化方式呈现数据"
- **验证查询**: "帮我分析这个月的销售数据"
- **期望**: 检索到可视化偏好，响应优先推荐图表

## 验证点

| 验证点 | 功能 | 方法 |
|-------|------|------|
| V1 | Fact Extraction | 验证 Mem0 自动提取的记忆是否包含关键特征 |
| V2 | 跨会话检索 | 验证新查询能否检索到历史记忆 |
| V3 | Prompt 注入 | 验证用户画像是否正确格式化并注入 |
| V4 | 个性化响应 | 验证 System Prompt 包含用户画像 |

## 环境要求

### 必需环境变量

```bash
# LLM 配置
OPENAI_API_KEY=sk-...          # Embedding 和 Mem0 Fact Extraction
ANTHROPIC_API_KEY=sk-ant-...   # Agent LLM（可选，V4 需要）

# 向量存储（二选一）
## 选项 1: Qdrant
VECTOR_STORE_PROVIDER=qdrant
QDRANT_URL=http://localhost:6333
MEM0_COLLECTION_NAME=mem0_memories

## 选项 2: 腾讯云 VectorDB
VECTOR_STORE_PROVIDER=tencent
TENCENT_VDB_URL=http://...
TENCENT_VDB_API_KEY=...
MEM0_COLLECTION_NAME=mem0_collection

# Mem0 配置
MEM0_LLM_PROVIDER=anthropic
MEM0_LLM_MODEL=claude-sonnet-4-5-20250929
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
```

### 依赖安装

```bash
pip install mem0ai tcvectordb qdrant-client openai anthropic
```

## 运行测试

### 基本运行

```bash
cd CoT_agent/mvp/zenflux_agent
python tests/test_mem0_personalization_e2e.py
```

### 测试输出

测试会实时输出彩色日志：

```
======================================================================
Mem0 个性化机制端到端验证测试
======================================================================
开始时间: 2026-01-11 15:30:00
测试用户数: 2
======================================================================

======================================================================
步骤 0: 环境配置验证
======================================================================
   ✅ OPENAI_API_KEY: sk-proj-k...
   ✅ ANTHROPIC_API_KEY: sk-ant-ap...
   ✅ TENCENT_VDB_URL: http://vectordb-...
✅ 环境配置验证

======================================================================
步骤 1: 模拟跨会话对话历史
======================================================================
清理旧测试数据...

开始模拟跨会话对话...

   📝 用户: Alice（前端开发者） (user_id=test_alice_mem0_001)
      会话 1: 你好，我是一名前端开发者，主要使用 React 和...
         ✅ 提取了 2 条记忆
      会话 2: 我更喜欢函数式组件和 hooks，不太喜欢用 cl...
         ✅ 提取了 1 条记忆
      会话 3: 我的项目通常使用 Tailwind CSS 做样式，感觉...
         ✅ 提取了 1 条记忆
      ✅ Alice（前端开发者） 总计提取 4 条记忆

   📝 用户: Bob（产品经理） (user_id=test_bob_mem0_002)
      ...
✅ 跨会话对话历史模拟完成

======================================================================
步骤 2: V1 验证 Fact Extraction
======================================================================

   🔍 验证用户: Alice（前端开发者）
      找到 4 条记忆
      记忆内容:
         1. 用户是一名前端开发者
         2. 用户主要使用 React 和 TypeScript 开发项目
         3. 用户喜欢函数式组件和 hooks
         4. 用户使用 Tailwind CSS 做样式
      ✅ 检测到特征: React, TypeScript, 函数式, Tailwind
✅ Alice（前端开发者） Fact Extraction 验证通过

...

======================================================================
Mem0 个性化机制验证总结
======================================================================
✅ 通过: 5
❌ 失败: 0
⚠️  警告: 0
通过率: 100.0%
总耗时: 15.32秒
======================================================================

   📄 详细报告已生成: MEM0_PERSONALIZATION_VALIDATION_REPORT.md
```

### 生成的报告

测试完成后会生成 `MEM0_PERSONALIZATION_VALIDATION_REPORT.md`，包含：
- 测试概况统计
- 每个验证点的详细结果
- 测试用户的画像和提取的记忆
- 最终结论

## 测试架构

```python
class Mem0PersonalizationE2ETest:
    """Mem0 个性化机制端到端测试"""
    
    async def verify_environment(self):
        """验证环境配置"""
    
    async def setup_conversation_history(self):
        """模拟跨会话对话历史 → Mem0.add()"""
    
    async def test_fact_extraction(self):
        """V1: 验证自动提取的记忆包含关键特征"""
    
    async def test_cross_session_search(self):
        """V2: 验证新查询能检索到相关记忆"""
    
    async def test_prompt_injection(self):
        """V3: 验证用户画像格式化和注入"""
    
    async def test_personalized_response(self):
        """V4: 验证 System Prompt 包含用户画像"""
    
    async def cleanup(self):
        """清理测试数据并生成报告"""
```

## 关键实现细节

### 1. 跨会话对话模拟

```python
# 模拟用户在多个会话中透露信息
for session in user_sessions:
    result = pool.add(
        user_id=user_id,
        messages=session["messages"]
    )
    # Mem0 内部 LLM 自动提取事实性记忆
```

### 2. Fact Extraction 验证

```python
# 获取自动提取的记忆
memories = pool.get_all(user_id=user_id)

# 检查是否包含关键特征
all_memory_text = " ".join([m.get('memory', '') for m in memories])
found_features = [f for f in expected if f in all_memory_text]
```

### 3. 语义检索验证

```python
# 新会话查询
results = pool.search(
    user_id=user_id,
    query="帮我写一个表单组件",
    limit=5
)
# 应检索到 "React 开发者" 等相关记忆
```

### 4. Prompt 注入验证

```python
# 调用框架的 Prompt 注入函数
from prompts.universal_agent_prompt import _fetch_user_profile

user_profile = _fetch_user_profile(user_id, query)
# 返回格式化的用户画像文本，可直接注入 System Prompt
```

## 常见问题

### Q1: 测试报告 "未检测到特征"

**原因**: Mem0 的 LLM 可能用不同词汇表达特征（如 "偏好 React" 而非 "React"）

**解决**: 这是正常现象，只要提取了记忆就算成功

### Q2: API 超时错误

**原因**: OpenAI API 或 Mem0 LLM 调用超时

**解决**: 
- 检查网络连接
- 增加重试次数（代码已内置重试机制）
- 降低并发调用频率

### Q3: 向量存储连接失败

**原因**: Qdrant/腾讯云 VectorDB 未启动或配置错误

**解决**:
- 检查 `VECTOR_STORE_PROVIDER` 配置
- 验证向量存储服务是否运行
- 检查 URL 和 API Key 是否正确

### Q4: V4 端到端测试跳过

**说明**: 为了测试速度，V4 只验证 System Prompt 构建，不实际调用 Agent

**完整测试**: 如需测试 Agent 实际响应，可手动调用 `ChatService.chat()`

## 扩展测试

### 添加新用户画像

编辑 `MOCK_CONVERSATION_SESSIONS`：

```python
"data_scientist_charlie": {
    "user_id": "test_charlie_003",
    "name": "Charlie（数据科学家）",
    "sessions": [
        {
            "messages": [
                {"role": "user", "content": "我是数据科学家，擅长 Python 和机器学习"},
                {"role": "assistant", "content": "很高兴认识你！"}
            ]
        }
    ],
    "expected_features": ["数据科学", "Python", "机器学习"],
    "test_query": "帮我分析这个数据集"
}
```

### 测试真实 Agent 响应

```python
async def test_real_agent_response(self):
    """完整调用 Agent 验证个性化响应"""
    from services.chat_service import get_chat_service
    
    chat_service = get_chat_service()
    
    async for event in chat_service.chat(
        message="帮我写个组件",
        user_id="test_alice_mem0_001",
        stream=True
    ):
        if event.get("type") == "content_delta":
            # 检查响应是否提到 React
            pass
```

## 相关文档

- [Mem0 官方文档](https://docs.mem0.ai/)
- [架构文档: 01-MEMORY-PROTOCOL.md](../docs/architecture/01-MEMORY-PROTOCOL.md)
- [Prompt 分层系统](../docs/architecture/17-PROMPT_TEMPLATE_SYSTEM.md)
- [已有的 Mem0 集成测试](./test_mem0_e2e.py)

## 联系方式

如有问题，请查看项目 README 或提交 Issue。
