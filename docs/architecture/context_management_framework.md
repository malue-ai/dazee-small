# 上下文管理框架设计

**版本**: V1.0  
**日期**: 2024-01-14  
**目标**: 统一管理知识库（Ragie）和用户记忆（Mem0），为 LLM 提供个性化上下文

---

## 一、核心理念

### 1.1 从用户视角看完整流程

```
用户 Query + 历史对话（messages）
    ↓
意图识别（是否需要个性化知识？）
    ↓
上下文检索（Context Retrieval）- 仅检索需要的数据源
    ├─ 知识库文档（Ragie）- 需要检索
    └─ 用户记忆（Mem0）- 需要检索
    ↓
上下文融合（Context Fusion）
    ↓
注入系统提示词（Prompt Injection）
    ↓
LLM 生成回复（包含历史对话 messages）
```

**关键洞察**：
- Ragie 和 Mem0 的**本质相同**：都是为 LLM 提供上下文的数据源，且需要检索
- 它们的**最终目标相同**：注入到系统提示词
- 它们的**检索方式相似**：都是向量检索 + 语义匹配
- **历史对话不同**：当前会话历史已在 messages 中，不需要额外检索（在线索引太慢）

**结论**: 应该设计一个**统一的上下文管理框架（Context Management Framework）**，管理需要检索的数据源（Ragie/Mem0），历史对话由 ChatService 直接管理。

---

## 二、架构设计：统一上下文管理框架

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│           上下文管理框架（Context Manager）                   │
│         仅管理需要检索的数据源（Ragie/Mem0）                  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   ┌──────────────────────────────────────────────┐          │
│   │        Context Retriever（上下文检索器）      │          │
│   │                                              │          │
│   │  ┌─────────────┐  ┌──────────────┐                    │
│   │  │ Knowledge   │  │ Memory       │                    │
│   │  │ Provider    │  │ Provider     │                    │
│   │  │ (Ragie)     │  │ (Mem0)       │                    │
│   │  └──────┬──────┘  └──────┬───────┘                    │
│   │         │                 │                            │
│   │         └─────────────────┘                            │
│   │                           ↓                            │
│   │              ┌────────────────────────┐               │
│   │              │   Fusion Engine        │               │
│   │              │   (结果融合引擎)        │               │
│   │              └────────────┬───────────┘               │
│   └───────────────────────────┼───────────────────────────┘
│                               ↓                            │
│   ┌──────────────────────────────────────────────┐        │
│   │     Context Injector（上下文注入器）          │        │
│   │                                              │        │
│   │  - Prompt Template 管理                      │        │
│   │  - 上下文权重分配                             │        │
│   │  - Token 预算控制                            │        │
│   └──────────────────┬───────────────────────────┘        │
│                      ↓                                     │
│              生成最终 Prompt                               │
│                                                            │
└─────────────────────────────────────────────────────────────┘

注意：历史对话（messages）由 ChatService 直接管理，不经过 ContextManager
```

### 2.2 核心组件

#### 2.2.1 ContextProvider（上下文提供者）接口

**统一抽象**：所有数据源都实现相同的接口

```python
# core/context/provider.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from enum import Enum

class ContextType(str, Enum):
    """上下文类型"""
    KNOWLEDGE = "knowledge"       # 知识（Ragie）- 需要检索
    MEMORY = "memory"             # 记忆（Mem0）- 需要检索
    # 注意：历史对话（History）不在这里，由 ChatService 直接管理
    # 原因：当前会话历史已在 messages 中，跨会话检索太慢

class ContextProvider(ABC):
    """
    上下文提供者接口
    
    所有数据源（Ragie/Mem0/History）都实现此接口
    """
    
    @property
    @abstractmethod
    def context_type(self) -> ContextType:
        """返回上下文类型"""
        pass
    
    @abstractmethod
    async def retrieve(
        self,
        query: str,
        user_id: str,
        filters: Dict[str, Any] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        检索相关上下文
        
        Args:
            query: 用户查询
            user_id: 用户ID
            filters: 过滤条件（可选）
            top_k: 返回结果数量
            
        Returns:
            上下文列表，格式：
            [
                {
                    "content": "上下文内容",
                    "score": 0.95,         # 相关性评分
                    "metadata": {...},      # 元数据
                    "source": "knowledge"   # 来源
                }
            ]
        """
        pass
    
    @abstractmethod
    async def update(
        self,
        user_id: str,
        data: Dict[str, Any]
    ) -> bool:
        """
        更新上下文（可选，某些 Provider 不支持）
        
        Args:
            user_id: 用户ID
            data: 更新数据
            
        Returns:
            是否成功
        """
        pass
```

#### 2.2.2 具体 Provider 实现

**Knowledge Provider（知识提供者 - Ragie）**

```python
# core/context/providers/knowledge.py
from core.context.provider import ContextProvider, ContextType
from services.ragie_service import get_ragie_service

class KnowledgeProvider(ContextProvider):
    """
    知识库提供者（基于 Ragie）
    
    数据源：
    - 企业知识库（产品文档、FAQ、操作手册）
    - 个人知识库（用户上传的文档）
    """
    
    def __init__(self):
        self.ragie = get_ragie_service()
    
    @property
    def context_type(self) -> ContextType:
        return ContextType.KNOWLEDGE
    
    async def retrieve(
        self,
        query: str,
        user_id: str,
        filters: Dict[str, Any] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """从知识库检索"""
        # 1. 调用 Ragie 检索
        ragie_results = await self.ragie.search(
            query=query,
            partition=f"user_{user_id}",  # 用户分区
            top_k=top_k,
            filters=filters
        )
        
        # 2. 转换为统一格式
        contexts = []
        for result in ragie_results:
            contexts.append({
                "content": result["text"],
                "score": result["score"],
                "metadata": {
                    "document_id": result["doc_id"],
                    "title": result.get("title", ""),
                    "source_type": "knowledge_base"
                },
                "source": "knowledge"
            })
        
        return contexts
    
    async def update(self, user_id: str, data: Dict[str, Any]) -> bool:
        """上传文档到知识库"""
        doc_id = await self.ragie.upload(
            content=data["content"],
            partition=f"user_{user_id}",
            metadata=data.get("metadata", {})
        )
        return bool(doc_id)
```

**Memory Provider（记忆提供者 - Mem0）**

```python
# core/context/providers/memory.py
from core.context.provider import ContextProvider, ContextType
from services.mem0_service import get_mem0_service

class MemoryProvider(ContextProvider):
    """
    用户记忆提供者（基于 Mem0）
    
    数据源：
    - 用户偏好（喜好、习惯）
    - 历史交互（重要对话、关键信息）
    - 个性化信息（用户画像）
    """
    
    def __init__(self):
        self.mem0 = get_mem0_service()
    
    @property
    def context_type(self) -> ContextType:
        return ContextType.MEMORY
    
    async def retrieve(
        self,
        query: str,
        user_id: str,
        filters: Dict[str, Any] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """从用户记忆检索"""
        # 1. 调用 Mem0 检索
        mem0_results = await self.mem0.search(
            user_id=user_id,
            query=query,
            limit=top_k
        )
        
        # 2. 转换为统一格式
        contexts = []
        for result in mem0_results:
            contexts.append({
                "content": result["memory"],
                "score": result.get("score", 0.8),
                "metadata": {
                    "memory_id": result["id"],
                    "created_at": result.get("created_at"),
                    "source_type": "user_memory"
                },
                "source": "memory"
            })
        
        return contexts
    
    async def update(self, user_id: str, data: Dict[str, Any]) -> bool:
        """添加用户记忆"""
        await self.mem0.add(
            user_id=user_id,
            messages=data["messages"],
            metadata=data.get("metadata", {})
        )
        return True
```

**History Provider（历史对话提供者）**

```python
# core/context/providers/history.py
from core.context.provider import ContextProvider, ContextType
from services.conversation_service import get_conversation_service

class HistoryProvider(ContextProvider):
    """
    历史对话提供者（基于数据库）
    
    数据源：
    - 当前会话的历史消息
    - 相关会话的历史消息（跨会话检索）
    """
    
    def __init__(self):
        self.conversation_service = get_conversation_service()
    
    @property
    def context_type(self) -> ContextType:
        return ContextType.HISTORY
    
    async def retrieve(
        self,
        query: str,
        user_id: str,
        filters: Dict[str, Any] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """检索历史对话"""
        conversation_id = filters.get("conversation_id") if filters else None
        
        # 1. 获取当前会话历史
        if conversation_id:
            messages = await self.conversation_service.get_messages(
                conversation_id=conversation_id,
                limit=top_k
            )
        else:
            # 2. 跨会话语义检索（可选）
            messages = await self.conversation_service.search_messages(
                user_id=user_id,
                query=query,
                limit=top_k
            )
        
        # 3. 转换为统一格式
        contexts = []
        for msg in messages:
            contexts.append({
                "content": f"{msg['role']}: {msg['content']}",
                "score": 1.0,  # 历史消息权重固定
                "metadata": {
                    "message_id": msg["id"],
                    "conversation_id": msg["conversation_id"],
                    "timestamp": msg["created_at"],
                    "source_type": "history"
                },
                "source": "history"
            })
        
        return contexts
    
    async def update(self, user_id: str, data: Dict[str, Any]) -> bool:
        """保存历史消息（通常由 ConversationService 处理）"""
        return True
```

#### 2.2.3 ContextRetriever（上下文检索器）

**统一检索入口**：

```python
# core/context/retriever.py
from typing import List, Dict, Any, Optional
from core.context.provider import ContextProvider, ContextType
from core.context.providers.knowledge import KnowledgeProvider
from core.context.providers.memory import MemoryProvider
from core.context.providers.history import HistoryProvider

class ContextRetriever:
    """
    上下文检索器
    
    职责：
    1. 管理多个 ContextProvider
    2. 根据意图决定调用哪些 Provider
    3. 并发检索，提升性能
    """
    
    def __init__(self):
        # 注册所有 Provider
        self.providers: Dict[ContextType, ContextProvider] = {
            ContextType.KNOWLEDGE: KnowledgeProvider(),
            ContextType.MEMORY: MemoryProvider(),
            ContextType.HISTORY: HistoryProvider(),
        }
    
    async def retrieve(
        self,
        query: str,
        user_id: str,
        sources: List[ContextType] = None,
        top_k_per_source: int = 5,
        filters: Dict[str, Any] = None
    ) -> Dict[ContextType, List[Dict[str, Any]]]:
        """
        从多个数据源检索上下文
        
        Args:
            query: 用户查询
            user_id: 用户ID
            sources: 要查询的数据源列表（None=全部）
            top_k_per_source: 每个数据源返回的结果数量
            filters: 过滤条件
            
        Returns:
            {
                ContextType.KNOWLEDGE: [...],
                ContextType.MEMORY: [...],
                ContextType.HISTORY: [...]
            }
        """
        # 1. 确定要查询的数据源
        if sources is None:
            sources = list(self.providers.keys())
        
        # 2. 并发查询所有数据源
        import asyncio
        tasks = {}
        for source_type in sources:
            provider = self.providers.get(source_type)
            if provider:
                tasks[source_type] = provider.retrieve(
                    query=query,
                    user_id=user_id,
                    filters=filters,
                    top_k=top_k_per_source
                )
        
        # 3. 等待所有查询完成
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        
        # 4. 组织结果
        context_map = {}
        for source_type, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                logger.error(f"检索失败: {source_type}, {str(result)}")
                context_map[source_type] = []
            else:
                context_map[source_type] = result
        
        return context_map
```

#### 2.2.4 FusionEngine（融合引擎）

**结果融合与重排序**：

```python
# core/context/fusion.py
from typing import List, Dict, Any
from core.context.provider import ContextType

class FusionEngine:
    """
    上下文融合引擎
    
    职责：
    1. 合并多个数据源的结果
    2. 去重（相似内容）
    3. 重排序（按相关性）
    4. 控制总数量（Token 预算）
    """
    
    def __init__(self, max_contexts: int = 10):
        self.max_contexts = max_contexts
        # 数据源权重（可配置）
        self.source_weights = {
            ContextType.KNOWLEDGE: 1.0,   # 知识库权重最高
            ContextType.MEMORY: 0.8,      # 用户记忆次之
            ContextType.HISTORY: 0.6      # 历史对话最低
        }
    
    def fuse(
        self,
        context_map: Dict[ContextType, List[Dict[str, Any]]],
        strategy: str = "weighted_merge"
    ) -> List[Dict[str, Any]]:
        """
        融合多个数据源的上下文
        
        Args:
            context_map: 各数据源的检索结果
            strategy: 融合策略（weighted_merge/round_robin）
            
        Returns:
            融合后的上下文列表（已排序）
        """
        if strategy == "weighted_merge":
            return self._weighted_merge(context_map)
        elif strategy == "round_robin":
            return self._round_robin(context_map)
        else:
            raise ValueError(f"未知的融合策略: {strategy}")
    
    def _weighted_merge(
        self,
        context_map: Dict[ContextType, List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """
        加权合并策略
        
        流程：
        1. 给每个上下文计算加权分数 = score * source_weight
        2. 按加权分数排序
        3. 去重（相似内容）
        4. 返回 Top-K
        """
        all_contexts = []
        
        # 1. 收集所有上下文，计算加权分数
        for source_type, contexts in context_map.items():
            weight = self.source_weights.get(source_type, 1.0)
            for ctx in contexts:
                ctx["weighted_score"] = ctx["score"] * weight
                all_contexts.append(ctx)
        
        # 2. 按加权分数排序
        all_contexts.sort(key=lambda x: x["weighted_score"], reverse=True)
        
        # 3. 去重（基于内容相似度）
        unique_contexts = self._deduplicate(all_contexts)
        
        # 4. 返回 Top-K
        return unique_contexts[:self.max_contexts]
    
    def _deduplicate(
        self,
        contexts: List[Dict[str, Any]],
        similarity_threshold: float = 0.9
    ) -> List[Dict[str, Any]]:
        """
        去重（移除相似的上下文）
        
        使用简单的文本相似度判断（可以升级为向量相似度）
        """
        unique = []
        for ctx in contexts:
            is_duplicate = False
            for existing in unique:
                # 简单判断：内容相似度（Jaccard）
                similarity = self._text_similarity(
                    ctx["content"],
                    existing["content"]
                )
                if similarity > similarity_threshold:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique.append(ctx)
        
        return unique
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """计算文本相似度（Jaccard）"""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union) if union else 0.0
    
    def _round_robin(
        self,
        context_map: Dict[ContextType, List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """
        轮询策略（每个数据源轮流取一条）
        
        适用场景：希望保证各数据源都有代表性
        """
        result = []
        iterators = {
            source: iter(contexts)
            for source, contexts in context_map.items()
        }
        
        while len(result) < self.max_contexts and iterators:
            for source in list(iterators.keys()):
                try:
                    ctx = next(iterators[source])
                    result.append(ctx)
                    if len(result) >= self.max_contexts:
                        break
                except StopIteration:
                    # 该数据源已耗尽
                    del iterators[source]
        
        return result
```

#### 2.2.5 ContextInjector（上下文注入器）

**注入到系统提示词**：

```python
# core/context/injector.py
from typing import List, Dict, Any
from core.context.provider import ContextType

class ContextInjector:
    """
    上下文注入器
    
    职责：
    1. 将上下文转换为自然语言
    2. 注入到系统提示词
    3. 控制 Token 预算
    """
    
    def __init__(self, max_tokens: int = 2000):
        self.max_tokens = max_tokens
    
    def inject(
        self,
        base_prompt: str,
        contexts: List[Dict[str, Any]],
        format_style: str = "structured"
    ) -> str:
        """
        注入上下文到提示词
        
        Args:
            base_prompt: 基础系统提示词
            contexts: 融合后的上下文列表
            format_style: 格式化风格（structured/narrative）
            
        Returns:
            注入后的完整提示词
        """
        # 1. 按数据源分组
        grouped = self._group_by_source(contexts)
        
        # 2. 格式化上下文
        if format_style == "structured":
            context_text = self._format_structured(grouped)
        else:
            context_text = self._format_narrative(grouped)
        
        # 3. Token 预算控制
        context_text = self._truncate_to_budget(context_text)
        
        # 4. 注入到提示词
        final_prompt = f"""{base_prompt}

## 相关上下文信息

{context_text}

请基于以上上下文信息回答用户问题。如果上下文中没有相关信息，请明确说明。
"""
        
        return final_prompt
    
    def _group_by_source(
        self,
        contexts: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """按数据源分组"""
        grouped = {}
        for ctx in contexts:
            source = ctx["source"]
            if source not in grouped:
                grouped[source] = []
            grouped[source].append(ctx)
        return grouped
    
    def _format_structured(
        self,
        grouped: Dict[str, List[Dict[str, Any]]]
    ) -> str:
        """结构化格式（分组展示）"""
        sections = []
        
        # 知识库
        if "knowledge" in grouped:
            kb_items = "\n".join([
                f"- {ctx['content'][:200]}..."
                for ctx in grouped["knowledge"]
            ])
            sections.append(f"**知识库**：\n{kb_items}")
        
        # 用户记忆
        if "memory" in grouped:
            mem_items = "\n".join([
                f"- {ctx['content']}"
                for ctx in grouped["memory"]
            ])
            sections.append(f"**用户画像**：\n{mem_items}")
        
        # 历史对话
        if "history" in grouped:
            hist_items = "\n".join([
                f"- {ctx['content'][:100]}..."
                for ctx in grouped["history"][:3]  # 最多3条
            ])
            sections.append(f"**历史对话**：\n{hist_items}")
        
        return "\n\n".join(sections)
    
    def _format_narrative(
        self,
        grouped: Dict[str, List[Dict[str, Any]]]
    ) -> str:
        """叙述格式（自然语言）"""
        parts = []
        
        if "memory" in grouped:
            memories = [ctx['content'] for ctx in grouped["memory"]]
            parts.append(f"关于这位用户，我了解到：{'; '.join(memories)}")
        
        if "knowledge" in grouped:
            knowledge = [ctx['content'][:100] for ctx in grouped["knowledge"]]
            parts.append(f"相关的知识信息包括：{'; '.join(knowledge)}")
        
        return " ".join(parts)
    
    def _truncate_to_budget(self, text: str) -> str:
        """Token 预算控制（简单实现：按字符数）"""
        # 简化：假设 1 token ≈ 1.5 字符（中文）
        max_chars = int(self.max_tokens * 1.5)
        if len(text) > max_chars:
            return text[:max_chars] + "..."
        return text
```

#### 2.2.6 ContextManager（统一入口）

**最终的统一框架**：

```python
# core/context/manager.py
from typing import List, Dict, Any, Optional
from core.context.retriever import ContextRetriever
from core.context.fusion import FusionEngine
from core.context.injector import ContextInjector
from core.context.provider import ContextType

class ContextManager:
    """
    上下文管理器（统一入口）
    
    这是 Ragie 和 Mem0 的统一框架：
    - 不再区分"知识库"和"记忆"
    - 都是上下文数据源
    - 统一检索、融合、注入
    
    使用方式：
        context_mgr = ContextManager()
        
        # 获取上下文并注入提示词
        enhanced_prompt = await context_mgr.get_enhanced_prompt(
            base_prompt="你是一个智能助手",
            query="推荐一些适合我的书",
            user_id="user_123"
        )
    """
    
    def __init__(self):
        self.retriever = ContextRetriever()
        self.fusion_engine = FusionEngine(max_contexts=10)
        self.injector = ContextInjector(max_tokens=2000)
    
    async def get_enhanced_prompt(
        self,
        base_prompt: str,
        query: str,
        user_id: str,
        intent: Dict[str, Any] = None,
        conversation_id: str = None
    ) -> str:
        """
        获取增强后的提示词（核心方法）
        
        完整流程：
        1. 根据意图决定检索哪些数据源
        2. 并发检索所有数据源
        3. 融合结果
        4. 注入到提示词
        
        Args:
            base_prompt: 基础系统提示词
            query: 用户查询
            user_id: 用户ID
            intent: 意图分析结果（可选）
            conversation_id: 会话ID（可选）
            
        Returns:
            增强后的系统提示词
        """
        # 1. 根据意图决定数据源
        sources = self._determine_sources(intent)
        
        # 2. 检索上下文
        filters = {"conversation_id": conversation_id} if conversation_id else None
        context_map = await self.retriever.retrieve(
            query=query,
            user_id=user_id,
            sources=sources,
            top_k_per_source=5,
            filters=filters
        )
        
        # 3. 融合结果
        fused_contexts = self.fusion_engine.fuse(
            context_map=context_map,
            strategy="weighted_merge"
        )
        
        # 4. 注入到提示词
        enhanced_prompt = self.injector.inject(
            base_prompt=base_prompt,
            contexts=fused_contexts,
            format_style="structured"
        )
        
        return enhanced_prompt
    
    def _determine_sources(
        self,
        intent: Dict[str, Any] = None
    ) -> List[ContextType]:
        """
        根据意图决定检索哪些数据源
        
        策略：
        - 默认：全部数据源
        - 如果意图明确不需要个性化：只用知识库
        - 如果意图是回顾历史：优先历史对话
        """
        if intent is None:
            # 默认：全部数据源
            return [
                ContextType.KNOWLEDGE,
                ContextType.MEMORY,
                ContextType.HISTORY
            ]
        
        # 根据意图标签决定
        needs_personalization = intent.get("needs_personalization", True)
        needs_knowledge = intent.get("needs_knowledge", True)
        
        sources = []
        
        if needs_knowledge:
            sources.append(ContextType.KNOWLEDGE)
        
        if needs_personalization:
            sources.append(ContextType.MEMORY)
        
        # 历史对话总是包含（除非明确排除）
        if intent.get("needs_history", True):
            sources.append(ContextType.HISTORY)
        
        return sources
    
    async def update_context(
        self,
        user_id: str,
        source_type: ContextType,
        data: Dict[str, Any]
    ) -> bool:
        """
        更新上下文数据
        
        Args:
            user_id: 用户ID
            source_type: 数据源类型
            data: 更新数据
            
        Returns:
            是否成功
        """
        provider = self.retriever.providers.get(source_type)
        if provider:
            return await provider.update(user_id, data)
        return False
```

---

## 三、使用示例

### 3.1 在 SimpleAgent 中使用

```python
# core/agent/simple/simple_agent.py
from core.context.manager import ContextManager

class SimpleAgent:
    def __init__(self, schema):
        self.schema = schema
        self.llm = get_llm_service()
        self.context_manager = ContextManager()  # 🆕 统一上下文管理
        # ...其他组件
    
    async def chat(self, messages, session_id, user_id):
        # 1. 意图分析
        intent = await self.intent_analyzer.analyze(messages[-1])
        
        # 2. 获取增强后的系统提示词 🆕
        base_prompt = self.schema.get("system_prompt", "")
        enhanced_prompt = await self.context_manager.get_enhanced_prompt(
            base_prompt=base_prompt,
            query=messages[-1],
            user_id=user_id,
            intent=intent,
            conversation_id=session_id
        )
        
        # 3. 使用增强后的提示词调用 LLM
        response = await self.llm.generate(
            prompt=enhanced_prompt,
            messages=messages
        )
        
        return response
```

### 3.2 更新用户记忆

```python
# 对话结束后，更新 Mem0
await context_manager.update_context(
    user_id="user_123",
    source_type=ContextType.MEMORY,
    data={
        "messages": [
            {"role": "user", "content": "我喜欢科幻小说"},
            {"role": "assistant", "content": "好的，我记住了"}
        ]
    }
)
```

### 3.3 上传文档到知识库

```python
# 用户上传文档
await context_manager.update_context(
    user_id="user_123",
    source_type=ContextType.KNOWLEDGE,
    data={
        "content": "这是一篇关于AI的文章...",
        "metadata": {
            "title": "AI技术概述",
            "tags": ["AI", "技术"]
        }
    }
)
```

---

## 四、与现有架构的关系

### 4.1 替换关系

**之前的设计（独立服务）**：
```python
# ❌ 旧设计
ragie_service = get_ragie_service()
mem0_service = get_mem0_service()

# 分别调用
kb_results = await ragie_service.search(query, user_id)
mem_results = await mem0_service.search(user_id, query)

# 手动合并
context = merge_results(kb_results, mem_results)
```

**新设计（统一框架）**：
```python
# ✅ 新设计
context_manager = ContextManager()

# 一次调用，自动检索、融合、注入
enhanced_prompt = await context_manager.get_enhanced_prompt(
    base_prompt="系统提示词",
    query="用户查询",
    user_id="user_123"
)
```

### 4.2 模块映射

| 旧模块 | 新模块 | 说明 |
|--------|--------|------|
| `services/ragie_service.py` | `core/context/providers/knowledge.py` | 封装为 Provider |
| `services/mem0_service.py` | `core/context/providers/memory.py` | 封装为 Provider |
| （无）| `core/context/manager.py` | **新增统一入口** |
| （无）| `core/context/fusion.py` | **新增融合引擎** |
| （无）| `core/context/injector.py` | **新增注入器** |

---

## 五、优势与收益

### 5.1 统一框架的优势

1. **接口统一**：所有数据源实现相同接口，易于扩展
2. **逻辑清晰**：从检索 → 融合 → 注入，流程清晰
3. **易于测试**：每个组件职责单一，易于单元测试
4. **性能优化**：并发检索多个数据源，融合引擎智能去重
5. **灵活配置**：数据源权重、融合策略、Token 预算可配置

### 5.2 解决的问题

| 问题 | 旧方案 | 新方案 |
|------|--------|--------|
| Ragie 和 Mem0 重复封装 | 分别实现 | 统一 Provider 接口 |
| 结果合并逻辑分散 | 手动合并 | FusionEngine 统一处理 |
| 提示词注入不规范 | 随意拼接 | ContextInjector 标准化 |
| 无法灵活扩展数据源 | 硬编码 | 新增 Provider 即可 |

---

## 六、总结

**核心理念**：
- Ragie（知识库）和 Mem0（用户记忆）**本质相同**：都是为 LLM 提供上下文的数据源
- 应该设计一个**统一的上下文管理框架**，而不是两个独立的服务
- 框架包含：检索器、融合引擎、注入器，提供统一入口

**回答您的问题**：
- ✅ **是的**，应该合并为一个框架（ContextManager）
- ✅ 从"注入提示词"的角度看，它们是同一个流程的不同数据源
- ✅ 这样设计更加清晰、统一、易扩展

---

**文档版本**: V1.0  
**最后更新**: 2024-01-14  
**维护者**: ZenFlux Agent Team
