# 上下文管理框架使用指南

**版本**: V1.0  
**日期**: 2024-01-14  
**目标**: 指导开发者如何使用统一的上下文管理框架

---

## 一、快速开始

### 1.1 基本概念

**ContextManager** 是统一的上下文管理框架，负责从多个数据源（Ragie/Mem0）检索相关上下文，并注入到系统提示词中。

**核心设计理念**：
- ✅ **管理需要检索的数据源**：知识库（Ragie）、用户记忆（Mem0）
- ❌ **不管理历史对话**：历史消息已在 `messages` 数组中，无需额外检索

### 1.2 简单示例

```python
from core.context import get_context_manager

# 获取全局单例
context_mgr = get_context_manager()

# 获取增强后的系统提示词
enhanced_prompt = await context_mgr.get_enhanced_prompt(
    base_prompt="你是一个智能助手",
    query="推荐一些适合我的书",
    user_id="user_123"
)

# enhanced_prompt 现在包含：
# - 原始系统提示词
# - 从知识库检索到的相关文档
# - 从 Mem0 检索到的用户偏好
```

---

## 二、在 ChatService 中集成

### 2.1 完整流程

```python
# services/chat_service.py
from core.context import get_context_manager, ContextType

class ChatService:
    def __init__(self):
        self.context_manager = get_context_manager()
        self.llm = get_llm_service()
        # ...
    
    async def chat(
        self,
        user_message: str,
        user_id: str,
        conversation_id: str
    ):
        """
        完整的对话流程
        
        1. 获取历史消息（直接从 DB，不经过 ContextManager）
        2. 意图分析（可选）
        3. 获取外部上下文（通过 ContextManager）
        4. 调用 LLM
        5. 更新用户记忆
        """
        
        # ===== 步骤 1：获取历史消息 =====
        # 注意：直接从 DB 获取，不需要检索
        history_messages = await self.get_messages(
            conversation_id=conversation_id,
            limit=10  # 最近10条
        )
        
        # ===== 步骤 2：意图分析（可选）=====
        intent = await self.analyze_intent(user_message)
        # intent = {
        #     "needs_personalization": True,  # 需要个性化（Mem0）
        #     "needs_knowledge": True,        # 需要知识库（Ragie）
        # }
        
        # ===== 步骤 3：获取外部上下文 =====
        base_prompt = "你是一个智能助手，擅长推荐书籍。"
        enhanced_prompt = await self.context_manager.get_enhanced_prompt(
            base_prompt=base_prompt,
            query=user_message,
            user_id=user_id,
            intent=intent,  # 可选：根据意图决定检索哪些数据源
            conversation_id=conversation_id
        )
        
        # ===== 步骤 4：调用 LLM =====
        # 构建 messages 数组
        messages = history_messages + [
            {"role": "user", "content": user_message}
        ]
        
        # 调用 LLM（历史 + 增强提示词）
        response = await self.llm.chat(
            messages=messages,  # 包含历史对话
            system_prompt=enhanced_prompt  # 包含 Ragie/Mem0
        )
        
        # ===== 步骤 5：更新用户记忆 =====
        # 对话结束后，提取重要信息更新到 Mem0
        await self.context_manager.update_context(
            user_id=user_id,
            source_type=ContextType.MEMORY,
            data={
                "messages": [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": response}
                ]
            }
        )
        
        return response
```

### 2.2 关键点说明

| 组件 | 如何获取 | 说明 |
|------|---------|------|
| **历史消息** | 直接从 DB: `get_messages(conversation_id)` | ❌ 不经过 ContextManager<br>✅ 性能高，无需索引 |
| **知识库** | 通过 ContextManager 检索 | ✅ 需要向量检索 |
| **用户记忆** | 通过 ContextManager 检索 | ✅ 需要语义匹配 |

---

## 三、高级用法

### 3.1 根据意图控制数据源

```python
# 场景 1：纯知识问答（不需要个性化）
intent = {
    "needs_knowledge": True,
    "needs_personalization": False
}

enhanced_prompt = await context_mgr.get_enhanced_prompt(
    base_prompt="你是一个知识助手",
    query="什么是量子计算？",
    user_id="user_123",
    intent=intent  # 只检索知识库，不检索 Mem0
)

# 场景 2：个性化推荐（需要用户画像）
intent = {
    "needs_knowledge": True,
    "needs_personalization": True
}

enhanced_prompt = await context_mgr.get_enhanced_prompt(
    base_prompt="你是一个推荐助手",
    query="推荐一些书",
    user_id="user_123",
    intent=intent  # 检索知识库 + Mem0
)
```

### 3.2 自定义融合策略

```python
# 加权合并（默认）
enhanced_prompt = await context_mgr.get_enhanced_prompt(
    base_prompt="系统提示词",
    query="用户查询",
    user_id="user_123",
    fusion_strategy="weighted_merge"  # 按权重排序
)

# 轮询策略（保证各数据源都有代表性）
enhanced_prompt = await context_mgr.get_enhanced_prompt(
    base_prompt="系统提示词",
    query="用户查询",
    user_id="user_123",
    fusion_strategy="round_robin"  # 轮流取
)
```

### 3.3 自定义格式化风格

```python
# 结构化格式（默认）
enhanced_prompt = await context_mgr.get_enhanced_prompt(
    base_prompt="系统提示词",
    query="用户查询",
    user_id="user_123",
    format_style="structured"  # 分组展示
)
# 输出：
# **知识库**：
# - 文档1...
# - 文档2...
# **用户画像**：
# - 用户偏好1

# 叙述格式
enhanced_prompt = await context_mgr.get_enhanced_prompt(
    base_prompt="系统提示词",
    query="用户查询",
    user_id="user_123",
    format_style="narrative"  # 自然语言
)
# 输出：
# 关于这位用户，我了解到：喜欢科幻小说；偏好Python编程。相关的知识信息包括：...
```

### 3.4 设置数据源权重

```python
from core.context import ContextType

# 提高用户记忆的权重
context_mgr.set_fusion_weights({
    ContextType.KNOWLEDGE: 0.8,
    ContextType.MEMORY: 1.0  # 用户记忆权重更高
})
```

### 3.5 上传文档到知识库

```python
# 用户上传文档
success = await context_mgr.update_context(
    user_id="user_123",
    source_type=ContextType.KNOWLEDGE,
    data={
        "content": "这是一篇关于AI的文章...",
        "metadata": {
            "title": "AI技术概述",
            "tags": ["AI", "技术"],
            "source": "用户上传"
        }
    }
)
```

### 3.6 健康检查

```python
# 检查所有数据源是否健康
health_status = await context_mgr.health_check()
# 返回：
# {
#     "knowledge": True,
#     "memory": True
# }

if not all(health_status.values()):
    logger.warning(f"部分数据源不健康: {health_status}")
```

---

## 四、性能优化建议

### 4.1 控制检索数量

```python
# 通过初始化参数控制
from core.context import ContextManager

context_mgr = ContextManager(
    max_contexts=10,   # 融合后最多保留10条上下文
    max_tokens=2000    # 上下文最大 Token 数量
)
```

### 4.2 缓存策略（未来优化）

```python
# TODO: 实现缓存层
# - 用户记忆缓存（短期内不会变化）
# - 知识库缓存（热门文档）
# - 减少重复检索
```

### 4.3 异步并发

ContextManager 已经实现了并发检索：
- 知识库和用户记忆**同时检索**
- 使用 `asyncio.gather` 并发执行
- 大幅降低延迟

---

## 五、常见问题

### Q1: 为什么历史对话不在 ContextManager 中？

**A**: 因为性能问题：
- **当前会话历史**：已在 `messages` 数组中，无需检索
- **跨会话检索**：需要向量索引，在线检索太慢，影响用户体验

正确做法：
```python
# ✅ 正确：历史消息直接从 DB 获取
history_messages = await self.get_messages(conversation_id, limit=10)

# ❌ 错误：不要通过 ContextManager 检索历史
# enhanced_prompt = await context_mgr.get_enhanced_prompt(...)  # 不包含历史
```

### Q2: 如何实现跨会话检索？

**A**: 如果确实需要（高级功能），建议：
1. 作为独立的功能模块，不放在 ContextManager 中
2. 使用异步任务或缓存，避免阻塞主流程
3. 只在特定场景下启用（如"回顾历史"功能）

```python
# 示例：独立的跨会话检索服务
from services.history_search_service import HistorySearchService

history_search = HistorySearchService()

# 异步任务：后台检索相关历史
related_history = await history_search.search(
    user_id="user_123",
    query="上次推荐的书",
    limit=5
)
```

### Q3: Ragie 和 Mem0 哪个先集成？

**A**: 建议顺序：
1. **先集成 Mem0**（用户记忆）
   - 更简单，已有服务
   - 立即提升个性化体验

2. **后集成 Ragie**（知识库）
   - 需要文档上传流程
   - 需要向量索引配置

### Q4: 如何调试上下文注入？

**A**: 使用日志：
```python
import logging

# 开启详细日志
logging.getLogger("core.context").setLevel(logging.DEBUG)

# 调用
enhanced_prompt = await context_mgr.get_enhanced_prompt(...)

# 查看日志输出：
# - 检索了哪些数据源
# - 每个数据源返回多少结果
# - 融合后保留多少条
# - 最终提示词长度
```

---

## 六、总结

**核心要点**：
1. ✅ **ContextManager** 管理需要检索的数据源（Ragie/Mem0）
2. ❌ **不管理历史对话**，由 ChatService 直接处理
3. 🚀 **并发检索**，性能优化
4. 🎯 **统一接口**，易于扩展

**使用模式**：
```python
# 1. 获取历史（DB）
history = await get_messages(conversation_id)

# 2. 获取上下文（ContextManager）
enhanced_prompt = await context_mgr.get_enhanced_prompt(
    base_prompt="系统提示词",
    query=user_message,
    user_id=user_id
)

# 3. 调用 LLM（历史 + 上下文）
response = await llm.chat(
    messages=history + [user_message],
    system_prompt=enhanced_prompt
)

# 4. 更新记忆（ContextManager）
await context_mgr.update_context(
    user_id=user_id,
    source_type=ContextType.MEMORY,
    data={"messages": [...]}
)
```

---

**文档版本**: V1.0  
**最后更新**: 2024-01-14  
**维护者**: ZenFlux Agent Team
