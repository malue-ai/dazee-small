"""
上下文注入器

职责：
1. 将上下文转换为自然语言
2. 注入到系统提示词
3. 控制 Token 预算
"""
from typing import List, Dict, Any

from core.context.provider import ContextType
from logger import get_logger

logger = get_logger(__name__)


class ContextInjector:
    """
    上下文注入器
    
    支持多种格式化风格：
    - structured: 结构化格式（分组展示）
    - narrative: 叙述格式（自然语言）
    """
    
    def __init__(self, max_tokens: int = 2000) -> None:
        """
        Args:
            max_tokens: 上下文最大 Token 数量（预算控制）
        """
        self.max_tokens = max_tokens
        logger.info(f"ContextInjector initialized: max_tokens={max_tokens}")
    
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
        if not contexts:
            logger.debug("无上下文可注入，返回原始提示词")
            return base_prompt
        
        logger.info(
            f"ContextInjector.inject: format_style={format_style}, "
            f"contexts_count={len(contexts)}"
        )
        
        # 1. 按数据源分组
        grouped = self._group_by_source(contexts)
        
        # 2. 格式化上下文
        if format_style == "structured":
            context_text = self._format_structured(grouped)
        elif format_style == "narrative":
            context_text = self._format_narrative(grouped)
        else:
            logger.warning(f"未知的格式化风格: {format_style}，使用默认风格 structured")
            context_text = self._format_structured(grouped)
        
        # 3. Token 预算控制
        context_text = self._truncate_to_budget(context_text)
        
        # 4. 注入到提示词
        final_prompt = f"""{base_prompt}

## 相关上下文信息

{context_text}

请基于以上上下文信息回答用户问题。如果上下文中没有相关信息，请明确说明。
"""
        
        logger.debug(
            f"ContextInjector.inject: final_prompt_length={len(final_prompt)}"
        )
        return final_prompt
    
    def _group_by_source(
        self,
        contexts: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """按数据源分组"""
        grouped = {}
        for ctx in contexts:
            source = ctx.get("source", "unknown")
            if source not in grouped:
                grouped[source] = []
            grouped[source].append(ctx)
        return grouped
    
    def _format_structured(
        self,
        grouped: Dict[str, List[Dict[str, Any]]]
    ) -> str:
        """
        结构化格式（分组展示）
        
        输出示例：
        ```
        **知识库**：
        - 文档内容1...
        - 文档内容2...
        
        **用户画像**：
        - 用户偏好1
        - 用户偏好2
        ```
        
        注意：历史对话不在这里，已通过 messages 数组传给 LLM
        """
        sections = []
        
        # 知识库
        if "knowledge" in grouped:
            kb_items = "\n".join([
                f"- {ctx['content'][:200]}..."
                if len(ctx['content']) > 200 else f"- {ctx['content']}"
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
        
        return "\n\n".join(sections)
    
    def _format_narrative(
        self,
        grouped: Dict[str, List[Dict[str, Any]]]
    ) -> str:
        """
        叙述格式（自然语言）
        
        输出示例：
        ```
        关于这位用户，我了解到：喜欢科幻小说；偏好Python编程。
        相关的知识信息包括：文档1内容；文档2内容。
        ```
        
        注意：历史对话不在这里，已通过 messages 数组传给 LLM
        """
        parts = []
        
        if "memory" in grouped:
            memories = [ctx['content'] for ctx in grouped["memory"]]
            parts.append(f"关于这位用户，我了解到：{'; '.join(memories)}")
        
        if "knowledge" in grouped:
            knowledge = [
                ctx['content'][:100] + "..."
                if len(ctx['content']) > 100 else ctx['content']
                for ctx in grouped["knowledge"]
            ]
            parts.append(f"相关的知识信息包括：{'; '.join(knowledge)}")
        
        return " ".join(parts)
    
    def _truncate_to_budget(self, text: str) -> str:
        """
        Token 预算控制
        
        简化实现：按字符数估算
        - 英文：1 token ≈ 4 字符
        - 中文：1 token ≈ 1.5 字符
        
        Args:
            text: 原始文本
            
        Returns:
            截断后的文本
        """
        # 混合语言估算：平均 1 token ≈ 2 字符
        max_chars = int(self.max_tokens * 2)
        
        if len(text) > max_chars:
            truncated = text[:max_chars] + "\n\n..."
            logger.warning(
                f"上下文超出预算，已截断: {len(text)} -> {len(truncated)} chars"
            )
            return truncated
        
        return text
