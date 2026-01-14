"""
上下文压缩模块

架构决策：基于当前 RVR 架构（非 tool_runner），采用以下策略：

┌─────────────────────────────────────────────────────────────┐
│  策略层级（从用户体验和效果优先）                            │
│                                                              │
│  L1. Memory Tool 状态保存（Claude 自主）                     │
│      → 告诉 Claude 使用 memory 工具保存重要发现              │
│      → 跨 context window 保持状态连续性                      │
│                                                              │
│  L2. 历史消息智能裁剪（服务层自动）                          │
│      → 保留关键消息：首轮 + 最近 N 轮 + tool_result          │
│      → 中间轮次丢弃细节，保留摘要                            │
│                                                              │
│  L3. QoS 成本控制（后端静默）                                │
│      → 根据用户等级设置 token 预算                           │
│      → 仅用于成本统计，不影响用户体验                        │
└─────────────────────────────────────────────────────────────┘

核心原则：
1. 静默处理，用户无感知
2. 不警告用户，不建议开启新会话
3. 优先保证问答效果，其次控制成本

参考文档：
- https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-4-best-practices
"""

from enum import Enum
from typing import Dict, Any, List, Optional
from dataclasses import dataclass


class QoSLevel(str, Enum):
    """
    服务质量等级
    
    仅用于后端成本控制和计费，不影响用户体验
    """
    FREE = "free"           # 免费用户：50K tokens
    BASIC = "basic"         # 基础付费：150K tokens
    PRO = "pro"             # 专业版：200K tokens（默认）
    ENTERPRISE = "enterprise"  # 企业版：1M tokens


# QoS 等级对应的 token 预算
QOS_TOKEN_BUDGETS: Dict[QoSLevel, int] = {
    QoSLevel.FREE: 50_000,
    QoSLevel.BASIC: 150_000,
    QoSLevel.PRO: 200_000,
    QoSLevel.ENTERPRISE: 1_000_000,
}


@dataclass
class ContextStrategy:
    """
    上下文管理策略配置
    
    L1: Memory Tool 指导（通过 System Prompt）
    L2: 历史消息裁剪（服务层自动执行）
    L3: QoS 成本控制（后端静默）
    
    配置来源优先级：
    1. 实例配置 config.yaml 中的 context_management 字段
    2. 框架默认值
    """
    # L1: Memory Tool 指导
    # 可在实例 config.yaml 中配置：context_management.enable_memory_guidance
    enable_memory_guidance: bool = True  # 是否在 Prompt 中添加 Memory 使用指导
    
    # L2: 历史消息裁剪
    # 可在实例 config.yaml 中配置：context_management.enable_history_trimming
    enable_history_trimming: bool = True  # 是否启用历史消息裁剪
    max_history_messages: int = 50       # 最大保留消息数
    preserve_first_n: int = 2            # 始终保留前 N 轮（建立上下文）
    preserve_last_n: int = 10            # 始终保留最近 N 轮（当前上下文）
    preserve_tool_results: bool = True   # 保留关键 tool_result（含文件/数据）
    
    # L3: QoS 成本控制
    qos_level: QoSLevel = QoSLevel.PRO
    token_budget: int = 200_000
    warning_threshold: float = 0.8       # 80% 时后端日志警告（用户无感知）


def get_context_strategy(qos_level: QoSLevel = QoSLevel.PRO) -> ContextStrategy:
    """
    获取上下文管理策略
    
    配置来源：
    1. 环境变量 QOS_LEVEL（控制 QoS 等级）
    2. 框架配置 config/context_compaction.yaml
    
    注意：不从实例配置读取，运营人员无需配置此项
    
    Args:
        qos_level: QoS 等级（默认 PRO）
        
    Returns:
        ContextStrategy 实例
    """
    return ContextStrategy(
        qos_level=qos_level,
        token_budget=QOS_TOKEN_BUDGETS.get(qos_level, 200_000)
    )


def get_memory_guidance_prompt() -> str:
    """
    获取 Memory Tool 使用指导（L1 策略）
    
    根据官方文档：Memory Tool 与 Context Awareness 自然配对
    用于跨 context window 保持状态连续性
    
    注意：这里不再说"上下文会自动压缩"（因为我们没用 tool_runner）
    而是指导 Claude 主动使用 Memory Tool 保存重要状态
    
    Returns:
        Memory 使用指导 Prompt
    """
    return """## 🧠 Long-Running Task Guidelines

For complex or multi-step tasks:

1. **Save Important Discoveries**
   - Use the `memory` tool to store key findings, decisions, and progress
   - Save any data that would be costly to re-compute or re-discover

2. **State Management**
   - Periodically save your current state and next steps
   - This ensures continuity if the conversation is long

3. **Work Autonomously**
   - Complete tasks fully without stopping early
   - Break complex tasks into manageable steps
   - Make steady progress on a few things at a time

4. **Preserve Critical Context**
   - File paths, configurations, and user preferences
   - Error patterns and solutions found
   - Progress markers for multi-file operations"""


def trim_history_messages(
    messages: List[Dict[str, Any]],
    strategy: ContextStrategy
) -> List[Dict[str, Any]]:
    """
    智能裁剪历史消息（L2 策略）
    
    裁剪逻辑：
    1. 始终保留前 N 轮（建立任务上下文）
    2. 始终保留最近 N 轮（当前工作上下文）
    3. 中间轮次：保留 tool_result（含重要数据），丢弃纯文本
    4. 总数超限时，从中间开始丢弃
    
    Args:
        messages: 完整消息历史
        strategy: 上下文策略
        
    Returns:
        裁剪后的消息列表
    """
    if len(messages) <= strategy.max_history_messages:
        return messages
    
    # 计算各部分
    first_part = messages[:strategy.preserve_first_n * 2]  # *2 因为 user+assistant
    last_part = messages[-strategy.preserve_last_n * 2:]
    middle_part = messages[strategy.preserve_first_n * 2:-strategy.preserve_last_n * 2]
    
    # 中间部分：只保留含 tool_result 的消息
    if strategy.preserve_tool_results:
        important_middle = []
        for msg in middle_part:
            content = msg.get("content", "")
            # 检查是否包含 tool_result
            if isinstance(content, list):
                has_tool_result = any(
                    block.get("type") == "tool_result" 
                    for block in content 
                    if isinstance(block, dict)
                )
                if has_tool_result:
                    important_middle.append(msg)
            # 或者包含重要关键词
            elif isinstance(content, str) and any(
                kw in content.lower() 
                for kw in ["file:", "path:", "error:", "found:", "created:"]
            ):
                important_middle.append(msg)
    else:
        important_middle = []
    
    # 组合结果
    result = first_part + important_middle + last_part
    
    # 如果仍然超限，进一步裁剪中间部分
    if len(result) > strategy.max_history_messages:
        excess = len(result) - strategy.max_history_messages
        # 从 important_middle 中移除最旧的
        keep_middle = len(important_middle) - excess
        if keep_middle > 0:
            important_middle = important_middle[-keep_middle:]
        else:
            important_middle = []
        result = first_part + important_middle + last_part
    
    return result


def estimate_tokens(messages: List[Dict[str, Any]], system_prompt: str = "") -> int:
    """
    估算消息列表的 token 数
    
    简化估算：1 个中文字符 ≈ 1.5 tokens，1 个英文单词 ≈ 1.3 tokens
    这是一个粗略估算，实际 token 数可能有 ±20% 误差
    
    Args:
        messages: 消息列表
        system_prompt: 系统提示词
        
    Returns:
        估算的 token 数
    """
    total_chars = len(system_prompt)
    
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        total_chars += len(block.get("text", ""))
                    elif block.get("type") == "tool_result":
                        total_chars += len(str(block.get("content", "")))
    
    # 粗略估算：平均 1 字符 ≈ 0.5 tokens（中英文混合）
    return int(total_chars * 0.5)


def should_warn_backend(
    estimated_tokens: int,
    strategy: ContextStrategy
) -> bool:
    """
    检查是否应该在后端日志中警告（用户无感知）
    
    Args:
        estimated_tokens: 估算的 token 数
        strategy: 上下文策略
        
    Returns:
        是否应该警告（仅后端日志）
    """
    return estimated_tokens >= strategy.token_budget * strategy.warning_threshold


# 导出
__all__ = [
    "QoSLevel",
    "QOS_TOKEN_BUDGETS",
    "ContextStrategy",
    "get_context_strategy",
    "get_memory_guidance_prompt",
    "trim_history_messages",
    "estimate_tokens",
    "should_warn_backend",
]
