"""
Context Manager - 上下文管理工具

职责：
1. 计算消息列表的 token 数量
2. 按 token 限制截断消息（保留最近的）
3. 支持保留重要消息（如 system prompt）

使用示例：
    from utils.context_manager import ContextManager
    
    cm = ContextManager(max_tokens=100000)
    
    # 截断消息，保留最近的
    truncated = cm.truncate_messages(messages, max_tokens=50000)
    
    # 获取消息的 token 统计
    stats = cm.get_token_stats(messages)
    print(f"总 token: {stats['total_tokens']}")
"""

import tiktoken
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from logger import get_logger

logger = get_logger("context_manager")


class TruncationStrategy(Enum):
    """截断策略"""
    KEEP_RECENT = "keep_recent"      # 保留最近的消息
    KEEP_FIRST = "keep_first"        # 保留最早的消息
    KEEP_BOTH = "keep_both"          # 保留首尾，删除中间


@dataclass
class TokenStats:
    """Token 统计信息"""
    total_tokens: int
    message_count: int
    avg_tokens_per_message: float
    by_role: Dict[str, int]  # 按角色统计
    details: List[Dict[str, Any]]  # 每条消息的详情


class ContextManager:
    """
    上下文管理器
    
    用于管理消息列表的 token 数量，支持智能截断
    """
    
    # 不同模型的 context window 大小
    MODEL_CONTEXT_WINDOWS = {
        # Claude 模型
        "claude-sonnet-4-5-20250929": 200000,
        "claude-3-5-sonnet-20241022": 200000,
        "claude-3-5-haiku-20241022": 200000,
        "claude-3-opus-20240229": 200000,
        # GPT 模型
        "gpt-4o": 128000,
        "gpt-4-turbo": 128000,
        "gpt-4": 8192,
        "gpt-3.5-turbo": 16385,
        # Gemini 模型
        "gemini-1.5-pro": 2000000,
        "gemini-1.5-flash": 1000000,
    }
    
    # 默认预留给输出的 token 数
    DEFAULT_OUTPUT_RESERVE = 8192
    
    def __init__(
        self,
        model: str = "claude-sonnet-4-5-20250929",
        output_reserve: int = DEFAULT_OUTPUT_RESERVE
    ):
        """
        初始化上下文管理器
        
        Args:
            model: 模型名称（用于确定 context window 大小）
            output_reserve: 预留给输出的 token 数
        """
        self.model = model
        self.output_reserve = output_reserve
        
        # 获取 context window 大小
        self.context_window = self.MODEL_CONTEXT_WINDOWS.get(model, 200000)
        self.max_input_tokens = self.context_window - output_reserve
        
        # 初始化 tokenizer（使用 cl100k_base，适用于大多数现代模型）
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception:
            # 如果 tiktoken 不可用，使用简单估算
            self.tokenizer = None
            logger.warning("tiktoken 不可用，使用简单估算（4字符≈1token）")
    
    def count_tokens(self, text: str) -> int:
        """
        计算文本的 token 数量
        
        Args:
            text: 要计算的文本
            
        Returns:
            token 数量
        """
        if not text:
            return 0
        
        if self.tokenizer:
            return len(self.tokenizer.encode(text))
        else:
            # 简单估算：中文约 1.5 字符/token，英文约 4 字符/token
            # 取平均值约 3 字符/token
            return max(1, len(text) // 3)
    
    def count_message_tokens(self, message: Dict[str, Any]) -> int:
        """
        计算单条消息的 token 数量
        
        Args:
            message: 消息对象 {"role": "user", "content": ...}
            
        Returns:
            token 数量
        """
        content = message.get("content", "")
        
        # 处理不同格式的 content
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            # content blocks 格式
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        # 工具调用：计算名称和输入
                        text_parts.append(block.get("name", ""))
                        text_parts.append(str(block.get("input", {})))
                    elif block.get("type") == "tool_result":
                        text_parts.append(str(block.get("content", "")))
                    elif block.get("type") == "image":
                        # 图片按固定 token 估算（Claude: ~1600 tokens/image）
                        text_parts.append("X" * 1600)
            text = " ".join(text_parts)
        else:
            text = str(content)
        
        # 加上 role 的开销（约 4 tokens）
        return self.count_tokens(text) + 4
    
    def count_messages_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """
        计算消息列表的总 token 数量
        
        Args:
            messages: 消息列表
            
        Returns:
            总 token 数量
        """
        total = 0
        for msg in messages:
            total += self.count_message_tokens(msg)
        return total
    
    def get_token_stats(self, messages: List[Dict[str, Any]]) -> TokenStats:
        """
        获取消息列表的 token 统计信息
        
        Args:
            messages: 消息列表
            
        Returns:
            TokenStats 对象
        """
        by_role = {}
        details = []
        total = 0
        
        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            tokens = self.count_message_tokens(msg)
            total += tokens
            
            # 按角色统计
            by_role[role] = by_role.get(role, 0) + tokens
            
            # 详情
            content_preview = str(msg.get("content", ""))[:50]
            details.append({
                "index": i,
                "role": role,
                "tokens": tokens,
                "preview": content_preview + "..." if len(content_preview) == 50 else content_preview
            })
        
        return TokenStats(
            total_tokens=total,
            message_count=len(messages),
            avg_tokens_per_message=total / len(messages) if messages else 0,
            by_role=by_role,
            details=details
        )
    
    def truncate_messages(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: Optional[int] = None,
        strategy: TruncationStrategy = TruncationStrategy.KEEP_RECENT,
        preserve_system: bool = True,
        min_messages: int = 2
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        截断消息列表，保持在 token 限制内
        
        Args:
            messages: 原始消息列表
            max_tokens: 最大 token 数（默认使用 max_input_tokens）
            strategy: 截断策略
            preserve_system: 是否保留 system 消息
            min_messages: 最少保留的消息数
            
        Returns:
            (截断后的消息列表, 实际 token 数)
        """
        if not messages:
            return [], 0
        
        max_tokens = max_tokens or self.max_input_tokens
        
        # 计算当前 token 数
        current_tokens = self.count_messages_tokens(messages)
        
        if current_tokens <= max_tokens:
            logger.debug(f"消息未超限: {current_tokens:,} <= {max_tokens:,} tokens")
            return messages, current_tokens
        
        logger.info(
            f"⚠️ 消息超限，开始截断: {current_tokens:,} > {max_tokens:,} tokens, "
            f"策略={strategy.value}"
        )
        
        # 分离 system 消息和其他消息
        system_messages = []
        other_messages = []
        system_tokens = 0
        
        for msg in messages:
            if msg.get("role") == "system" and preserve_system:
                system_messages.append(msg)
                system_tokens += self.count_message_tokens(msg)
            else:
                other_messages.append(msg)
        
        # 可用于其他消息的 token 数
        available_tokens = max_tokens - system_tokens
        
        if available_tokens < 1000:
            logger.warning(f"⚠️ System 消息过长 ({system_tokens:,} tokens)，可用空间不足")
            available_tokens = max(1000, max_tokens // 2)
        
        # 根据策略截断
        if strategy == TruncationStrategy.KEEP_RECENT:
            truncated = self._keep_recent(other_messages, available_tokens, min_messages)
        elif strategy == TruncationStrategy.KEEP_FIRST:
            truncated = self._keep_first(other_messages, available_tokens, min_messages)
        else:
            truncated = self._keep_both(other_messages, available_tokens, min_messages)
        
        # 合并结果
        result = system_messages + truncated
        final_tokens = self.count_messages_tokens(result)
        
        logger.info(
            f"✅ 截断完成: {len(messages)} → {len(result)} 条消息, "
            f"{current_tokens:,} → {final_tokens:,} tokens"
        )
        
        return result, final_tokens
    
    def _keep_recent(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int,
        min_messages: int
    ) -> List[Dict[str, Any]]:
        """保留最近的消息"""
        result = []
        current_tokens = 0
        
        # 从后往前遍历
        for msg in reversed(messages):
            msg_tokens = self.count_message_tokens(msg)
            
            if current_tokens + msg_tokens > max_tokens and len(result) >= min_messages:
                break
            
            result.insert(0, msg)
            current_tokens += msg_tokens
        
        return result
    
    def _keep_first(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int,
        min_messages: int
    ) -> List[Dict[str, Any]]:
        """保留最早的消息"""
        result = []
        current_tokens = 0
        
        for msg in messages:
            msg_tokens = self.count_message_tokens(msg)
            
            if current_tokens + msg_tokens > max_tokens and len(result) >= min_messages:
                break
            
            result.append(msg)
            current_tokens += msg_tokens
        
        return result
    
    def _keep_both(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int,
        min_messages: int
    ) -> List[Dict[str, Any]]:
        """保留首尾，删除中间"""
        if len(messages) <= min_messages:
            return messages
        
        # 分配：30% 给开头，70% 给最近
        first_budget = int(max_tokens * 0.3)
        recent_budget = max_tokens - first_budget
        
        first_part = self._keep_first(messages[:len(messages)//3], first_budget, 1)
        recent_part = self._keep_recent(messages[len(messages)//3:], recent_budget, 1)
        
        return first_part + recent_part
    
    def estimate_remaining_tokens(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None
    ) -> int:
        """
        估算剩余可用的 token 数
        
        Args:
            messages: 当前消息列表
            system_prompt: System prompt（如果有）
            
        Returns:
            剩余可用 token 数
        """
        used = self.count_messages_tokens(messages)
        if system_prompt:
            used += self.count_tokens(system_prompt)
        
        remaining = self.max_input_tokens - used
        return max(0, remaining)
    
    def should_truncate(
        self,
        messages: List[Dict[str, Any]],
        threshold: float = 0.8
    ) -> bool:
        """
        判断是否需要截断
        
        Args:
            messages: 消息列表
            threshold: 阈值（0-1，达到多少比例时需要截断）
            
        Returns:
            是否需要截断
        """
        used = self.count_messages_tokens(messages)
        limit = self.max_input_tokens * threshold
        return used > limit
    
    def format_stats(self, messages: List[Dict[str, Any]]) -> str:
        """
        格式化输出 token 统计信息
        
        Args:
            messages: 消息列表
            
        Returns:
            格式化的统计字符串
        """
        stats = self.get_token_stats(messages)
        
        lines = [
            f"📊 Token 统计 (model={self.model})",
            f"   总计: {stats.total_tokens:,} / {self.max_input_tokens:,} tokens",
            f"   消息数: {stats.message_count}",
            f"   平均: {stats.avg_tokens_per_message:.1f} tokens/msg",
            f"   按角色:",
        ]
        
        for role, tokens in stats.by_role.items():
            lines.append(f"      {role}: {tokens:,} tokens")
        
        return "\n".join(lines)


# ==================== 便捷函数 ====================

_default_manager: Optional[ContextManager] = None


def get_context_manager(model: str = "claude-sonnet-4-5-20250929") -> ContextManager:
    """获取默认的上下文管理器"""
    global _default_manager
    if _default_manager is None or _default_manager.model != model:
        _default_manager = ContextManager(model=model)
    return _default_manager


def truncate_messages(
    messages: List[Dict[str, Any]],
    max_tokens: int,
    keep_recent: bool = True
) -> List[Dict[str, Any]]:
    """
    便捷函数：截断消息列表
    
    Args:
        messages: 消息列表
        max_tokens: 最大 token 数
        keep_recent: 是否保留最近的（False 则保留最早的）
        
    Returns:
        截断后的消息列表
    """
    cm = get_context_manager()
    strategy = TruncationStrategy.KEEP_RECENT if keep_recent else TruncationStrategy.KEEP_FIRST
    result, _ = cm.truncate_messages(messages, max_tokens, strategy)
    return result


def count_tokens(text: str) -> int:
    """便捷函数：计算文本的 token 数"""
    return get_context_manager().count_tokens(text)


def count_messages_tokens(messages: List[Dict[str, Any]]) -> int:
    """便捷函数：计算消息列表的 token 数"""
    return get_context_manager().count_messages_tokens(messages)

