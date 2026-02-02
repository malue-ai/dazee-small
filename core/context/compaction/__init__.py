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
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

import tiktoken

from logger import get_logger

logger = get_logger("context.compaction")

# 全局 tokenizer 缓存（延迟初始化）
_tokenizer = None


def _get_tokenizer():
    """获取 tokenizer（延迟初始化，全局缓存）"""
    global _tokenizer
    if _tokenizer is None:
        try:
            _tokenizer = tiktoken.get_encoding("cl100k_base")
            logger.debug("✅ tiktoken tokenizer 初始化成功")
        except Exception as e:
            logger.warning(f"⚠️ 无法加载 tiktoken: {e}，将使用字符数估算")
    return _tokenizer


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
    L2: 历史消息裁剪（纯 token 驱动，服务层自动执行）
    L3: QoS 成本控制（后端静默）
    
    配置来源优先级：
    1. 实例配置 config.yaml 中的 context_management 字段
    2. 框架默认值
    """
    # L1: Memory Tool 指导
    # 可在实例 config.yaml 中配置：context_management.enable_memory_guidance
    enable_memory_guidance: bool = True  # 是否在 Prompt 中添加 Memory 使用指导
    
    # L2: 历史消息裁剪（纯 token 驱动）
    # 可在实例 config.yaml 中配置：context_management.enable_history_trimming
    enable_history_trimming: bool = True     # 是否启用历史消息裁剪
    preserve_first_messages: int = 4         # 始终保留开头 N 条消息（任务上下文）
    preserve_last_messages: int = 20         # 尽量保留最近 N 条消息（当前上下文）
    preserve_tool_results: bool = True       # 保留中间的 tool_result（含重要数据）
    trim_threshold: float = 0.8              # token 使用率超过此阈值时触发裁剪
    
    # L3: QoS 成本控制
    qos_level: QoSLevel = QoSLevel.PRO
    token_budget: int = 200_000
    warning_threshold: float = 0.8           # 80% 时后端日志警告（用户无感知）


@dataclass
class TrimStats:
    """
    历史消息裁剪统计信息
    
    用于单次遍历同时完成裁剪和 token 估算，避免重复遍历。
    """
    original_count: int = 0              # 原始消息数量
    trimmed_count: int = 0               # 裁剪后消息数量
    estimated_tokens: int = 0            # 估算的 token 数
    exceeded_budget: bool = False        # 是否超过预算阈值
    should_warn: bool = False            # 是否应该后端警告


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


def _estimate_message_tokens(msg: Dict[str, Any], tokenizer) -> int:
    """
    估算单条消息的 token 数
    
    Args:
        msg: 消息字典
        tokenizer: tiktoken tokenizer 实例
        
    Returns:
        token 数量
    """
    def _extract_text(content: Any) -> str:
        """递归提取所有文本内容"""
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            return " ".join(_extract_text(item) for item in content)
        elif isinstance(content, dict):
            block_type = content.get("type", "")
            if block_type == "text":
                return content.get("text", "")
            elif block_type == "tool_result":
                return _extract_text(content.get("content", ""))
            elif block_type == "tool_use":
                tool_name = content.get("name", "")
                tool_input = content.get("input", {})
                return f"{tool_name}: {str(tool_input)}"
            elif block_type == "thinking":
                return content.get("thinking", "")
            else:
                return str(content.get("text", "") or content.get("content", ""))
        return str(content)
    
    role = msg.get("role", "")
    content = msg.get("content", "")
    text = f"{role}: {_extract_text(content)}"
    
    if tokenizer:
        try:
            return len(tokenizer.encode(text))
        except Exception:
            pass
    
    # Fallback：字符估算
    return len(text) // 2


def _has_tool_result(msg: Dict[str, Any]) -> bool:
    """
    检查消息是否包含 tool_result
    
    Args:
        msg: 消息字典
        
    Returns:
        是否包含 tool_result
    """
    content = msg.get("content", "")
    if isinstance(content, list):
        return any(
            isinstance(block, dict) and block.get("type") == "tool_result"
            for block in content
        )
    return False


def trim_by_token_budget(
    messages: List[Dict[str, Any]],
    token_budget: int,
    preserve_first_messages: int = 4,
    preserve_last_messages: int = 20,
    preserve_tool_results: bool = True,
    system_prompt: str = ""
) -> Tuple[List[Dict[str, Any]], TrimStats]:
    """
    基于 token 预算裁剪消息（纯 token 驱动，L2 策略核心实现）
    
    裁剪逻辑：
    1. 估算总 token 数，如果未超预算则直接返回
    2. 始终保留开头 N 条消息（任务上下文）
    3. 从最近消息向前累计 token，找到预算分割点
    4. 中间部分可选保留 tool_result 消息（含重要数据）
    
    Args:
        messages: 消息列表
        token_budget: token 预算上限
        preserve_first_messages: 始终保留开头 N 条消息
        preserve_last_messages: 尽量保留最近 N 条消息
        preserve_tool_results: 是否保留中间的 tool_result 消息
        system_prompt: 系统提示词（计入 token）
    
    Returns:
        (裁剪后的消息, 统计信息)
    """
    original_count = len(messages)
    tokenizer = _get_tokenizer()
    
    # 边界情况：消息数很少，无需裁剪
    min_preserve = preserve_first_messages + preserve_last_messages
    if original_count <= min_preserve:
        estimated_tokens = estimate_tokens(messages, system_prompt)
        return messages, TrimStats(
            original_count=original_count,
            trimmed_count=original_count,
            estimated_tokens=estimated_tokens,
            exceeded_budget=estimated_tokens >= token_budget,
            should_warn=estimated_tokens >= token_budget * 0.8
        )
    
    # 1. 计算 system_prompt 的 token 数（基础开销）
    base_tokens = 0
    if system_prompt:
        if tokenizer:
            try:
                base_tokens = len(tokenizer.encode(system_prompt))
            except Exception:
                base_tokens = len(system_prompt) // 2
        else:
            base_tokens = len(system_prompt) // 2
    
    # 2. 计算每条消息的 token 数
    message_tokens = [_estimate_message_tokens(msg, tokenizer) for msg in messages]
    total_tokens = base_tokens + sum(message_tokens)
    
    # 3. 如果未超预算，直接返回
    if total_tokens <= token_budget:
        return messages, TrimStats(
            original_count=original_count,
            trimmed_count=original_count,
            estimated_tokens=total_tokens,
            exceeded_budget=False,
            should_warn=total_tokens >= token_budget * 0.8
        )
    
    logger.info(
        f"⚠️ Token 超预算: {total_tokens:,} > {token_budget:,}，开始裁剪..."
    )
    
    # 4. 保留开头 N 条消息（任务上下文）
    first_part = messages[:preserve_first_messages]
    first_tokens = sum(message_tokens[:preserve_first_messages])
    
    # 5. 从最近消息向前累计，找到能放进预算的最大范围
    # 剩余预算 = token_budget - base_tokens - first_tokens - 缓冲区
    buffer_tokens = 5000  # 留出缓冲区给后续工具调用
    remaining_budget = token_budget - base_tokens - first_tokens - buffer_tokens
    
    # 从后向前累计 token
    last_part = []
    last_tokens = 0
    last_start_idx = original_count  # 从后向前的起始索引
    
    for i in range(original_count - 1, preserve_first_messages - 1, -1):
        msg_token = message_tokens[i]
        if last_tokens + msg_token <= remaining_budget:
            last_tokens += msg_token
            last_start_idx = i
        else:
            break
    
    # 确保至少保留 preserve_last_messages 条最近消息（如果有的话）
    min_last_idx = max(preserve_first_messages, original_count - preserve_last_messages)
    if last_start_idx > min_last_idx:
        # 强制保留最近 N 条，即使超预算
        last_start_idx = min_last_idx
        last_tokens = sum(message_tokens[last_start_idx:])
    
    last_part = messages[last_start_idx:]
    
    # 6. 中间部分：可选保留 tool_result 消息
    middle_part = []
    middle_tokens = 0
    
    if preserve_tool_results and last_start_idx > preserve_first_messages:
        middle_budget = remaining_budget - last_tokens
        
        for i in range(preserve_first_messages, last_start_idx):
            msg = messages[i]
            if _has_tool_result(msg):
                msg_token = message_tokens[i]
                if middle_tokens + msg_token <= middle_budget:
                    middle_part.append(msg)
                    middle_tokens += msg_token
    
    # 7. 组合结果
    result = first_part + middle_part + last_part
    trimmed_count = len(result)
    estimated_tokens = base_tokens + first_tokens + middle_tokens + last_tokens
    
    logger.info(
        f"✂️ 裁剪完成: {original_count} → {trimmed_count} 条消息, "
        f"token: {total_tokens:,} → {estimated_tokens:,} "
        f"(first={len(first_part)}, middle={len(middle_part)}, last={len(last_part)})"
    )
    
    return result, TrimStats(
        original_count=original_count,
        trimmed_count=trimmed_count,
        estimated_tokens=estimated_tokens,
        exceeded_budget=estimated_tokens >= token_budget,
        should_warn=estimated_tokens >= token_budget * 0.8
    )


def trim_history_messages(
    messages: List[Dict[str, Any]],
    strategy: ContextStrategy
) -> List[Dict[str, Any]]:
    """
    智能裁剪历史消息（L2 策略，纯 token 驱动）
    
    裁剪逻辑：
    1. 估算总 token 数，如果未超预算则直接返回
    2. 始终保留开头 N 条消息（任务上下文）
    3. 从最近消息向前累计 token，找到预算分割点
    4. 中间部分可选保留 tool_result 消息（含重要数据）
    
    Args:
        messages: 完整消息历史
        strategy: 上下文策略
        
    Returns:
        裁剪后的消息列表
    """
    # 计算 token 预算
    token_budget = int(strategy.token_budget * strategy.trim_threshold)
    
    # 调用新的 token 驱动裁剪函数
    trimmed_messages, _ = trim_by_token_budget(
        messages=messages,
        token_budget=token_budget,
        preserve_first_messages=strategy.preserve_first_messages,
        preserve_last_messages=strategy.preserve_last_messages,
        preserve_tool_results=strategy.preserve_tool_results
    )
    
    return trimmed_messages


def trim_history_messages_with_stats(
    messages: List[Dict[str, Any]],
    strategy: ContextStrategy,
    system_prompt: str = ""
) -> Tuple[List[Dict[str, Any]], TrimStats]:
    """
    智能裁剪历史消息并返回统计信息（纯 token 驱动）
    
    相比 trim_history_messages + estimate_tokens 分开调用：
    - 单次遍历完成裁剪 + token 估算
    - 避免对大消息列表的重复遍历
    - 返回完整的统计信息
    
    Args:
        messages: 完整消息历史
        strategy: 上下文策略
        system_prompt: 系统提示词（用于 token 估算）
        
    Returns:
        (trimmed_messages, stats) - 裁剪后的消息列表和统计信息
    """
    # 计算 token 预算
    token_budget = int(strategy.token_budget * strategy.trim_threshold)
    
    # 调用新的 token 驱动裁剪函数（已包含统计信息）
    return trim_by_token_budget(
        messages=messages,
        token_budget=token_budget,
        preserve_first_messages=strategy.preserve_first_messages,
        preserve_last_messages=strategy.preserve_last_messages,
        preserve_tool_results=strategy.preserve_tool_results,
        system_prompt=system_prompt
    )


def estimate_tokens(messages: List[Dict[str, Any]], system_prompt: str = "") -> int:
    """
    计算消息列表的 token 数
    
    使用 tiktoken（cl100k_base 编码）进行精确计算。
    如果 tiktoken 不可用，则使用字符估算（1 字符 ≈ 0.5 tokens）。
    
    Args:
        messages: 消息列表
        system_prompt: 系统提示词
        
    Returns:
        token 数量
    """
    tokenizer = _get_tokenizer()
    
    def _extract_text(content: Any) -> str:
        """递归提取所有文本内容"""
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            texts = []
            for item in content:
                texts.append(_extract_text(item))
            return " ".join(texts)
        elif isinstance(content, dict):
            block_type = content.get("type", "")
            if block_type == "text":
                return content.get("text", "")
            elif block_type == "tool_result":
                result_content = content.get("content", "")
                return _extract_text(result_content)
            elif block_type == "tool_use":
                # 工具名称 + 参数
                tool_name = content.get("name", "")
                tool_input = content.get("input", {})
                return f"{tool_name}: {str(tool_input)}"
            elif block_type == "thinking":
                return content.get("thinking", "")
            else:
                # 其他类型，尝试提取常见字段
                return str(content.get("text", "") or content.get("content", ""))
        else:
            return str(content)
    
    # 收集所有文本
    all_text = system_prompt or ""
    
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        msg_text = f"{role}: {_extract_text(content)}"
        all_text += "\n" + msg_text
    
    # 使用 tiktoken 精确计算
    if tokenizer:
        try:
            tokens = len(tokenizer.encode(all_text))
            return tokens
        except Exception as e:
            logger.warning(f"tiktoken 编码失败: {e}，使用字符估算")
    
    # Fallback：字符估算（1 token ≈ 2 字符，对中英文混合较准确）
    return len(all_text) // 2


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


# 别名函数（兼容旧 API）
def get_compaction_threshold(qos_level: QoSLevel = QoSLevel.PRO) -> int:
    """
    获取压缩阈值（token 数）
    
    当 token 数超过此阈值时，应触发历史消息裁剪
    
    Args:
        qos_level: QoS 等级
        
    Returns:
        Token 阈值
    """
    strategy = get_context_strategy(qos_level)
    return int(strategy.token_budget * strategy.warning_threshold)


def get_context_awareness_prompt() -> str:
    """
    获取上下文感知提示词
    
    别名：get_memory_guidance_prompt
    用于向 Claude 提供长任务处理指导
    """
    return get_memory_guidance_prompt()


# 导出
__all__ = [
    "QoSLevel",
    "QOS_TOKEN_BUDGETS",
    "ContextStrategy",
    "TrimStats",
    "get_context_strategy",
    "get_memory_guidance_prompt",
    "get_context_awareness_prompt",  # 别名
    "get_compaction_threshold",      # 别名
    "trim_by_token_budget",          # 🆕 纯 token 驱动裁剪（推荐使用）
    "trim_history_messages",         # 向后兼容
    "trim_history_messages_with_stats",  # 向后兼容
    "estimate_tokens",
    "should_warn_backend",
]
