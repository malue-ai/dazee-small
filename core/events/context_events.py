"""
上下文管理事件

V6.3 新增：提供上下文管理操作的透明化反馈

核心功能：
1. 上下文使用进度条（实时更新，类似 Cursor）
2. 裁剪/压缩完成通知（临时显示）
3. Token 预算警告（可选）

设计理念：
- 自动化：上下文管理自动执行，用户无需手动操作
- 透明化：通过事件系统告知用户系统在做什么
- 非侵入式：通知不打断用户当前操作（5秒淡出）
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional
from datetime import datetime


class ContextEventType(str, Enum):
    """上下文管理事件类型"""
    CONTEXT_USAGE_UPDATE = "context_usage_update"        # 上下文使用更新（实时）
    CONTEXT_TRIMMING_START = "context_trimming_start"    # 开始裁剪
    CONTEXT_TRIMMING_DONE = "context_trimming_done"      # 裁剪完成
    CONTEXT_COMPACTION_START = "context_compaction_start"  # 开始压缩
    CONTEXT_COMPACTION_DONE = "context_compaction_done"    # 压缩完成
    CONTEXT_BUDGET_WARNING = "context_budget_warning"      # Token 预算警告


@dataclass
class ContextUsageUpdateEvent:
    """
    上下文使用更新事件（实时）
    
    用于驱动上下文进度条更新（类似 Cursor）
    
    前端展示示例：
    ┌───────────────────────────────────────────────────┐
    │ 上下文: ████████░░░░░░░░ 45%  (90K / 200K tokens) │
    └───────────────────────────────────────────────────┘
    
    颜色编码：
    - 🟢 0-60%: 绿色（正常）
    - 🟡 60-80%: 黄色（提示即将优化）
    - 🟠 80-95%: 橙色（即将触发裁剪）
    - 🔴 95-100%: 红色（建议新会话，极少触发）
    """
    event_type: ContextEventType = ContextEventType.CONTEXT_USAGE_UPDATE
    timestamp: datetime = None
    
    # 使用情况
    current_tokens: int         # 当前使用 tokens
    budget_tokens: int          # 总预算 tokens
    usage_percentage: float     # 使用百分比 (0-1)
    
    # 颜色等级（用于前端渲染）
    color_level: str            # "green" / "yellow" / "orange" / "red"
    
    # 统计信息
    message_count: int          # 当前消息数
    turn_count: int             # 对话轮次数
    
    # 可选的建议
    suggestion: Optional[str] = None  # 如 "建议新开对话"（极少触发）
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    def to_dict(self) -> dict:
        """转换为字典（用于 SSE 发送）"""
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "current_tokens": self.current_tokens,
            "budget_tokens": self.budget_tokens,
            "usage_percentage": self.usage_percentage,
            "color_level": self.color_level,
            "message_count": self.message_count,
            "turn_count": self.turn_count,
            "suggestion": self.suggestion
        }


@dataclass
class ContextTrimmingEvent:
    """
    上下文裁剪事件
    
    前端展示示例（类似 Cursor）：
    ┌────────────────────────────────────────────────────┐
    │ ✓ 对话历史已智能优化，保留 15 条关键消息            │
    │ 已节省约 50,000 tokens，保持流畅对话  了解更多 >   │
    └────────────────────────────────────────────────────┘
    
    展示特性：
    - 淡灰色背景，顶部提示条
    - 5 秒后自动淡出
    - 不打断用户当前操作
    - 可点击"了解更多"链接
    """
    event_type: ContextEventType
    timestamp: datetime = None
    
    # 裁剪统计
    original_messages: int      # 原始消息数
    trimmed_messages: int       # 裁剪后消息数
    preserved_turns: int        # 保留的对话轮次
    
    # 优化效果
    tokens_before: Optional[int] = None
    tokens_after: Optional[int] = None
    tokens_saved: Optional[int] = None
    
    # 用户可读消息
    display_message: str = "对话历史已智能优化，保留关键上下文"
    details: Optional[str] = None
    learn_more_url: Optional[str] = "/docs/context-management"
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    def to_dict(self) -> dict:
        """转换为字典（用于 SSE 发送）"""
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "original_messages": self.original_messages,
            "trimmed_messages": self.trimmed_messages,
            "preserved_turns": self.preserved_turns,
            "tokens_before": self.tokens_before,
            "tokens_after": self.tokens_after,
            "tokens_saved": self.tokens_saved,
            "display_message": self.display_message,
            "details": self.details,
            "learn_more_url": self.learn_more_url
        }


@dataclass
class ContextCompactionEvent:
    """
    上下文压缩事件（如果使用 Claude SDK 的 compaction）
    
    类似 Cursor 的 "Chat context summarized. Learn more"
    """
    event_type: ContextEventType
    timestamp: datetime = None
    
    # 压缩统计
    original_turns: int
    summarized_turns: int
    
    # 用户消息
    display_message: str = "对话上下文已智能总结，保持流畅对话"
    learn_more_url: Optional[str] = "/docs/context-management"
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    def to_dict(self) -> dict:
        """转换为字典（用于 SSE 发送）"""
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "original_turns": self.original_turns,
            "summarized_turns": self.summarized_turns,
            "display_message": self.display_message,
            "learn_more_url": self.learn_more_url
        }


def calculate_color_level(usage_percentage: float) -> str:
    """
    根据使用百分比计算颜色等级
    
    Args:
        usage_percentage: 使用百分比 (0-1)
        
    Returns:
        颜色等级: "green" / "yellow" / "orange" / "red"
    """
    if usage_percentage < 0.6:
        return "green"
    elif usage_percentage < 0.8:
        return "yellow"
    elif usage_percentage < 0.95:
        return "orange"
    else:
        return "red"


def should_suggest_new_session(usage_percentage: float) -> bool:
    """
    判断是否应该建议用户开启新会话
    
    Args:
        usage_percentage: 使用百分比 (0-1)
        
    Returns:
        是否建议新会话
    """
    return usage_percentage > 0.95
