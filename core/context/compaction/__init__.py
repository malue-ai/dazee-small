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

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from core.llm.base import (
    count_message_tokens,
    count_messages_tokens,
    count_request_tokens,
    count_tokens,
    count_tools_tokens,
)
from logger import get_logger

logger = get_logger("context.compaction")


class QoSLevel(str, Enum):
    """
    服务质量等级

    仅用于后端成本控制和计费，不影响用户体验
    """

    FREE = "free"  # 免费用户：50K tokens
    BASIC = "basic"  # 基础付费：150K tokens
    PRO = "pro"  # 专业版：200K tokens（默认）
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

    # L2: 历史消息压缩（双阈值机制）
    # 可在实例 config.yaml 中配置：context_management.enable_history_trimming
    enable_history_trimming: bool = True  # 是否启用历史消息压缩
    preserve_first_messages: int = 4  # 始终保留开头 N 条消息（任务上下文）
    preserve_last_messages: int = 10  # 尽量保留最近 N 条消息（当前上下文）
    preserve_tool_results: bool = True  # 保留中间的 tool_result（含重要数据）

    # 🆕 双阈值压缩机制
    pre_run_threshold: float = 0.80  # 80% 阈值 - 运行前预检查（Agent 启动前）
    runtime_threshold: float = 0.92  # 92% 阈值 - 运行中实时检查（Agent 执行中）

    # L3: QoS 成本控制
    qos_level: QoSLevel = QoSLevel.PRO
    token_budget: int = 200_000
    warning_threshold: float = 0.8  # 80% 时后端日志警告（用户无感知）


@dataclass
class TrimStats:
    """
    历史消息裁剪统计信息

    用于单次遍历同时完成裁剪和 token 估算，避免重复遍历。
    """

    original_count: int = 0  # 原始消息数量
    trimmed_count: int = 0  # 裁剪后消息数量
    estimated_tokens: int = 0  # 估算的 token 数
    exceeded_budget: bool = False  # 是否超过预算阈值
    should_warn: bool = False  # 是否应该后端警告

    # 🆕 摘要相关
    has_summary: bool = False  # 是否包含摘要
    summary_tokens: int = 0  # 摘要使用的 token 数
    compressed_message_count: int = 0  # 被压缩为摘要的消息数量


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
        qos_level=qos_level, token_budget=QOS_TOKEN_BUDGETS.get(qos_level, 200_000)
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
            isinstance(block, dict) and block.get("type") == "tool_result" for block in content
        )
    return False


# ============================================================
# 快速字符级预过滤（防止大上下文导致后续 token 计算延迟）
# ============================================================

# 单条消息内容的硬上限（字符数）—— 任何单条 tool_result 不允许超过此值进入历史
# 这是在昂贵的 token 计算之前的 O(n) 快速预过滤，防止上下文膨胀
_MAX_SINGLE_CONTENT_CHARS = 3000

# 总消息字符数的快速预检阈值（超过此值时触发激进裁剪，避免 token 计算延迟）
# 约等于 token_budget * 4（1 token ≈ 4 chars 粗略估算）
_FAST_PREFILTER_TOTAL_CHARS = 600_000


def _fast_cap_message_content(content: Any, cap: int = _MAX_SINGLE_CONTENT_CHARS) -> Any:
    """
    快速截断单条消息内容到硬上限（<0.01ms per message）

    不做 token 计算，纯字符截断。用于防止超大 tool_result
    在进入 token 计算流程前就被控制住。
    """
    if isinstance(content, str):
        if len(content) <= cap:
            return content
        head = cap * 2 // 3  # 2/3 给头部
        tail = cap // 3      # 1/3 给尾部
        return (
            content[:head]
            + f"\n\n... (已截断: 原文 {len(content)} 字符, 保留头 {head} + 尾 {tail}) ...\n\n"
            + content[-tail:]
        )

    if isinstance(content, list):
        capped = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    text = block.get("text", "")
                    if len(text) > cap:
                        head = cap * 2 // 3
                        tail = cap // 3
                        capped.append({
                            **block,
                            "text": (
                                text[:head]
                                + f"\n... (已截断: 原文 {len(text)} 字符) ...\n"
                                + text[-tail:]
                            ),
                        })
                    else:
                        capped.append(block)
                elif block.get("type") == "tool_result":
                    # 递归处理嵌套的 tool_result content
                    inner = block.get("content", "")
                    capped_inner = _fast_cap_message_content(inner, cap)
                    if capped_inner is not inner:
                        capped.append({**block, "content": capped_inner})
                    else:
                        capped.append(block)
                else:
                    capped.append(block)
            else:
                capped.append(block)
        return capped

    return content


def fast_prefilter_messages(
    messages: List[Dict[str, Any]],
    per_message_cap: int = _MAX_SINGLE_CONTENT_CHARS,
) -> List[Dict[str, Any]]:
    """
    快速字符级预过滤：在昂贵的 token 计算之前截断超大消息（O(n), <1ms）

    目的：防止上下文膨胀导致 count_message_tokens 等操作本身变慢。
    在 token 计算之前先做一遍粗粒度截断，确保每条消息内容都在合理范围内。

    Args:
        messages: 消息列表
        per_message_cap: 单条消息内容的字符硬上限

    Returns:
        预过滤后的消息列表
    """
    if not messages:
        return messages

    # 快速估算总字符数（O(n), <0.1ms）
    total_chars = sum(len(str(m.get("content", ""))) for m in messages)
    if total_chars <= _FAST_PREFILTER_TOTAL_CHARS:
        return messages  # 总量在安全范围内，跳过预过滤

    # 超过阈值，逐条截断
    capped_count = 0
    result = []
    for msg in messages:
        content = msg.get("content")
        if content is None:
            result.append(msg)
            continue
        capped = _fast_cap_message_content(content, per_message_cap)
        if capped is not content:
            result.append({**msg, "content": capped})
            capped_count += 1
        else:
            result.append(msg)

    if capped_count > 0:
        new_total = sum(len(str(m.get("content", ""))) for m in result)
        logger.warning(
            f"⚡ 快速预过滤: 截断 {capped_count} 条超大消息 "
            f"(总字符 {total_chars:,} → {new_total:,})"
        )

    return result


# ============================================================
# tool_result 内容级压缩（即时，O(n)，零 LLM 调用）
# ============================================================

# tool_result 内容超过此字符数时触发截断（历史消息中的 tool_result）
_TOOL_RESULT_TRUNCATE_THRESHOLD = 300
# 截断后保留的头尾字符数
_TOOL_RESULT_KEEP_HEAD = 150
_TOOL_RESULT_KEEP_TAIL = 80

# Immediate compression threshold for fresh tool results (before appending to messages)
# This prevents recent large tool_results from bloating context
_IMMEDIATE_COMPRESS_THRESHOLD = 1500
_IMMEDIATE_KEEP_HEAD = 500
_IMMEDIATE_KEEP_TAIL = 200


def _compress_tool_result_content(content: Any) -> Any:
    """
    压缩单个 tool_result 的 content 字段

    策略：
    - 字符串超长 → 保留头 200 + 尾 100 字符 + 截断标记
    - list of blocks → 递归压缩每个 text block
    - 其他 → 不变
    """
    if isinstance(content, str):
        if len(content) <= _TOOL_RESULT_TRUNCATE_THRESHOLD:
            return content
        return (
            content[:_TOOL_RESULT_KEEP_HEAD]
            + f"\n\n... (已省略 {len(content) - _TOOL_RESULT_KEEP_HEAD - _TOOL_RESULT_KEEP_TAIL} 字符) ...\n\n"
            + content[-_TOOL_RESULT_KEEP_TAIL:]
        )

    if isinstance(content, list):
        compressed = []
        for block in content:
            if isinstance(block, dict):
                block_type = block.get("type", "")
                if block_type == "text":
                    text = block.get("text", "")
                    if len(text) > _TOOL_RESULT_TRUNCATE_THRESHOLD:
                        compressed.append({
                            **block,
                            "text": (
                                text[:_TOOL_RESULT_KEEP_HEAD]
                                + f"\n... (已省略 {len(text) - _TOOL_RESULT_KEEP_HEAD - _TOOL_RESULT_KEEP_TAIL} 字符) ...\n"
                                + text[-_TOOL_RESULT_KEEP_TAIL:]
                            ),
                        })
                    else:
                        compressed.append(block)
                elif block_type == "image":
                    # 图片应已被 _strip_old_images 处理，这里做兜底
                    compressed.append({"type": "text", "text": "[图片已省略]"})
                else:
                    compressed.append(block)
            else:
                compressed.append(block)
        return compressed

    return content


def compress_fresh_tool_result(content: str) -> str:
    """Compress a fresh tool result BEFORE appending to messages.

    Unlike _compress_old_tool_results (which only handles old messages),
    this compresses immediately — preventing large tool outputs from
    bloating context from the start.

    Threshold: 1500 chars (vs 300 for old messages).
    Keeps more context (head=500 + tail=200) since this is recent/relevant.

    Args:
        content: Raw tool result string.

    Returns:
        Compressed string if over threshold, original otherwise.
    """
    if not isinstance(content, str):
        return content
    if len(content) <= _IMMEDIATE_COMPRESS_THRESHOLD:
        return content

    omitted = len(content) - _IMMEDIATE_KEEP_HEAD - _IMMEDIATE_KEEP_TAIL
    return (
        content[:_IMMEDIATE_KEEP_HEAD]
        + f"\n\n... (已省略 {omitted:,} 字符，完整结果已保存) ...\n\n"
        + content[-_IMMEDIATE_KEEP_TAIL:]
    )


def _compress_old_tool_results(
    messages: List[Dict[str, Any]],
    preserve_recent_n: int = 4,
) -> List[Dict[str, Any]]:
    """
    压缩非最近消息中的 tool_result 内容（即时，O(n)，零 LLM 调用）

    保留最近 N 条消息的 tool_result 原文不动，
    更早的消息中超长的 tool_result 内容截断为头+尾。

    Args:
        messages: 消息列表
        preserve_recent_n: 保留最近 N 条消息不压缩

    Returns:
        压缩后的消息列表
    """
    if not messages:
        return messages

    boundary = len(messages) - preserve_recent_n
    if boundary <= 0:
        return messages

    compressed_count = 0
    result = []

    for i, msg in enumerate(messages):
        if i >= boundary:
            result.append(msg)
            continue

        content = msg.get("content")
        if not isinstance(content, list):
            result.append(msg)
            continue

        # 检查是否包含 tool_result
        has_tr = any(
            isinstance(b, dict) and b.get("type") == "tool_result"
            for b in content
        )
        if not has_tr:
            result.append(msg)
            continue

        # 压缩 tool_result 内容
        new_content = []
        changed = False
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                original = block.get("content", "")
                compressed = _compress_tool_result_content(original)
                if compressed is not original:
                    new_content.append({**block, "content": compressed})
                    changed = True
                else:
                    new_content.append(block)
            else:
                new_content.append(block)

        if changed:
            compressed_count += 1
            result.append({**msg, "content": new_content})
        else:
            result.append(msg)

    if compressed_count > 0:
        logger.info(f"📦 已压缩 {compressed_count} 条消息中的 tool_result 内容")

    return result


def trim_by_token_budget(
    messages: List[Dict[str, Any]],
    token_budget: int,
    preserve_first_messages: int = 4,
    preserve_last_messages: int = 10,
    preserve_tool_results: bool = True,
    system_prompt: str = "",
) -> Tuple[List[Dict[str, Any]], TrimStats]:
    """
    基于 token 预算裁剪消息（纯 token 驱动，L2 策略核心实现）

    裁剪逻辑：
    0. 先压缩旧消息中的 tool_result 内容（即时，零 LLM 调用）
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
    # Step -1: 快速字符级预过滤（<1ms），防止超大消息导致后续 token 计算延迟
    messages = fast_prefilter_messages(messages)

    # Step 0: 分级压缩旧消息中超长的 tool_result 内容（即时，O(n)，零 LLM 调用）
    # 保留最近 4 条消息（约 2 轮对话）的 tool_result 原文
    # 第 5 条以前的 tool_result 截断为头+尾
    messages = _compress_old_tool_results(messages, preserve_recent_n=min(4, preserve_last_messages))

    original_count = len(messages)

    # ---------- P0: 绝对上限告警 ----------
    # 在昂贵的 token 计算前做粗略估算（1 char ≈ 0.33 token）
    _ABSOLUTE_WARN_TOKENS = 50_000
    _ABSOLUTE_ERROR_TOKENS = 100_000
    _rough_chars = sum(len(str(m.get("content", ""))) for m in messages)
    _rough_tokens = _rough_chars // 3
    if _rough_tokens > _ABSOLUTE_ERROR_TOKENS:
        logger.error(
            f"🚨 上下文绝对上限告警: 粗估 {_rough_tokens:,} tokens > {_ABSOLUTE_ERROR_TOKENS:,}，"
            f"将强制裁剪（消息数={original_count}）"
        )
    elif _rough_tokens > _ABSOLUTE_WARN_TOKENS:
        logger.warning(
            f"⚠️ 上下文绝对上限预警: 粗估 {_rough_tokens:,} tokens > {_ABSOLUTE_WARN_TOKENS:,}（消息数={original_count}）"
        )

    # 边界情况：消息数很少，无需裁剪
    min_preserve = preserve_first_messages + preserve_last_messages
    if original_count <= min_preserve:
        estimated_tokens = count_messages_tokens(messages, system_prompt)
        return messages, TrimStats(
            original_count=original_count,
            trimmed_count=original_count,
            estimated_tokens=estimated_tokens,
            exceeded_budget=estimated_tokens >= token_budget,
            should_warn=estimated_tokens >= token_budget * 0.8,
        )

    # 1. 计算 system_prompt 的 token 数（基础开销）
    base_tokens = count_tokens(system_prompt) if system_prompt else 0

    # 2. 计算每条消息的 token 数
    message_tokens = [count_message_tokens(msg) for msg in messages]
    total_tokens = base_tokens + sum(message_tokens)

    # 3. 如果未超预算，直接返回
    if total_tokens <= token_budget:
        return messages, TrimStats(
            original_count=original_count,
            trimmed_count=original_count,
            estimated_tokens=total_tokens,
            exceeded_budget=False,
            should_warn=total_tokens >= token_budget * 0.8,
        )

    logger.info(f"⚠️ Token 超预算: {total_tokens:,} > {token_budget:,}，开始裁剪...")

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

    # 8. 🛡️ 裁剪后确保 tool_use/tool_result 配对（裁剪可能破坏边界处的配对）
    from core.llm.adaptor import ClaudeAdaptor

    result = ClaudeAdaptor.ensure_tool_pairs(result)

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
        should_warn=estimated_tokens >= token_budget * 0.8,
    )


def should_warn_backend(estimated_tokens: int, strategy: ContextStrategy) -> bool:
    """
    检查是否应该在后端日志中警告（用户无感知）

    Args:
        estimated_tokens: 估算的 token 数
        strategy: 上下文策略

    Returns:
        是否应该警告（仅后端日志）
    """
    return estimated_tokens >= strategy.token_budget * strategy.warning_threshold


# ============================================================
# 🆕 带摘要的智能压缩（整合 conversation.py 功能）
# ============================================================


class CompressionPhase:
    """压缩阶段（双阈值机制）"""

    PRE_RUN = "pre_run"  # 运行前预检查（80% 阈值）
    RUNTIME = "runtime"  # 运行中实时检查（92% 阈值）


async def compress_with_summary(
    messages: List[Dict[str, Any]],
    token_budget: int,
    llm_client: Optional[Any] = None,
    conversation_id: Optional[str] = None,
    conversation_service: Optional[Any] = None,
    preserve_first_messages: int = 4,
    preserve_last_messages: int = 10,
    preserve_tool_results: bool = True,
    system_prompt: str = "",
    compression_phase: str = "pre_run",
) -> Tuple[List[Dict[str, Any]], TrimStats]:
    """
    带摘要的智能消息压缩（支持双阈值机制）

    双阈值机制：
    - pre_run (80%): 运行前预检查，Agent 启动前执行
    - runtime (92%): 运行中实时检查，Agent 执行过程中触发

    流程：
    1. 检查是否超阈值（根据 compression_phase 选择阈值）
    2. 如超阈值，对早期消息生成 LLM 摘要
    3. 可选：保存摘要到 conversation.metadata
    4. 返回 [摘要消息] + 中间 tool_result + 最近 N 条消息

    相比 trim_by_token_budget：
    - 不是简单丢弃中间消息，而是生成摘要保留关键信息
    - 支持持久化摘要到数据库
    - 下次加载时可自动应用已有摘要

    Args:
        messages: 消息列表
        token_budget: token 预算上限
        llm_client: LLM 客户端（用于生成摘要，推荐 Haiku）
        conversation_id: 对话 ID（用于保存摘要到数据库）
        conversation_service: 对话服务（用于保存摘要到数据库）
        preserve_first_messages: 始终保留开头 N 条消息
        preserve_last_messages: 尽量保留最近 N 条消息
        preserve_tool_results: 是否保留中间的 tool_result 消息
        system_prompt: 系统提示词（计入 token）
        compression_phase: 压缩阶段 ("pre_run" 或 "runtime")

    Returns:
        (压缩后的消息, 统计信息)
    """
    from datetime import datetime

    from .summarizer import ConversationSummarizer

    original_count = len(messages)
    phase_label = "运行前" if compression_phase == CompressionPhase.PRE_RUN else "运行中"

    # 1. 边界情况：消息数很少，无需压缩
    min_preserve = preserve_first_messages + preserve_last_messages
    if original_count <= min_preserve:
        estimated_tokens = count_messages_tokens(messages, system_prompt)
        return messages, TrimStats(
            original_count=original_count,
            trimmed_count=original_count,
            estimated_tokens=estimated_tokens,
            exceeded_budget=estimated_tokens >= token_budget,
            should_warn=estimated_tokens >= token_budget * 0.8,
        )

    # 2. 计算 token 使用情况
    base_tokens = count_tokens(system_prompt) if system_prompt else 0

    message_tokens = [count_message_tokens(msg) for msg in messages]
    total_tokens = base_tokens + sum(message_tokens)

    # 3. 如果未超预算，直接返回
    if total_tokens <= token_budget:
        return messages, TrimStats(
            original_count=original_count,
            trimmed_count=original_count,
            estimated_tokens=total_tokens,
            exceeded_budget=False,
            should_warn=total_tokens >= token_budget * 0.8,
        )

    logger.info(
        f"⚠️ [{phase_label}检查] Token 超预算: {total_tokens:,} > {token_budget:,}，开始带摘要压缩..."
    )

    # 4. 确定保留范围
    # 保留开头 N 条
    first_part = messages[:preserve_first_messages]
    first_tokens = sum(message_tokens[:preserve_first_messages])

    # 保留最近 N 条
    last_start_idx = max(preserve_first_messages, original_count - preserve_last_messages)
    last_part = messages[last_start_idx:]
    last_tokens = sum(message_tokens[last_start_idx:])

    # 中间需要压缩的消息
    middle_start = preserve_first_messages
    middle_end = last_start_idx
    early_messages = messages[middle_start:middle_end]

    # 5. 生成摘要
    summarizer = ConversationSummarizer()

    if llm_client:
        summary = await summarizer.generate_summary(early_messages, llm_client)
    else:
        summary = summarizer.generate_simple_summary(early_messages)

    # 计算摘要 token
    summary_tokens = count_tokens(summary)

    # 6. 构建摘要消息
    summary_message = {
        "role": "user",  # 作为 user 消息注入
        "content": f"[历史对话摘要 - 共 {len(early_messages)} 条消息]\n\n{summary}",
    }

    # 7. 中间部分：可选保留 tool_result 消息
    middle_tool_results = []
    middle_tool_tokens = 0

    if preserve_tool_results:
        # 计算可用预算
        buffer_tokens = 5000
        used_tokens = base_tokens + first_tokens + summary_tokens + last_tokens + buffer_tokens
        available_for_tools = max(0, token_budget - used_tokens)

        for i in range(middle_start, middle_end):
            msg = messages[i]
            if _has_tool_result(msg):
                msg_token = message_tokens[i]
                if middle_tool_tokens + msg_token <= available_for_tools:
                    middle_tool_results.append(msg)
                    middle_tool_tokens += msg_token

    # 8. 组合结果
    result = first_part + [summary_message] + middle_tool_results + last_part

    # 9. 🛡️ 压缩后确保 tool_use/tool_result 配对（压缩可能破坏边界处的配对）
    from core.llm.adaptor import ClaudeAdaptor

    result = ClaudeAdaptor.ensure_tool_pairs(result)

    trimmed_count = len(result)
    estimated_tokens = (
        base_tokens + first_tokens + summary_tokens + middle_tool_tokens + last_tokens
    )

    logger.info(
        f"✅ 带摘要压缩完成: {original_count} → {trimmed_count} 条消息, "
        f"token: {total_tokens:,} → {estimated_tokens:,} "
        f"(first={len(first_part)}, summary=1[{len(early_messages)}条], "
        f"middle_tools={len(middle_tool_results)}, last={len(last_part)})"
    )

    # 9. 可选：保存摘要到数据库
    if conversation_id and conversation_service:
        try:
            await _save_compression_metadata(
                conversation_id=conversation_id,
                conversation_service=conversation_service,
                summary=summary,
                original_count=original_count,
                summary_tokens=summary_tokens,
                middle_start=middle_start,
                middle_end=middle_end,
                summarized_count=len(early_messages),
                preserve_first_messages=preserve_first_messages,
                preserve_last_messages=preserve_last_messages,
                preserve_tool_results=preserve_tool_results,
                compression_phase=compression_phase,
            )
        except Exception as e:
            logger.warning(f"⚠️ 保存压缩元数据失败: {e}")

    return result, TrimStats(
        original_count=original_count,
        trimmed_count=trimmed_count,
        estimated_tokens=estimated_tokens,
        exceeded_budget=estimated_tokens >= token_budget,
        should_warn=estimated_tokens >= token_budget * 0.8,
        has_summary=True,
        summary_tokens=summary_tokens,
        compressed_message_count=len(early_messages),
    )


async def _save_compression_metadata(
    conversation_id: str,
    conversation_service: Any,
    summary: str,
    original_count: int,
    summary_tokens: int,
    middle_start: int,
    middle_end: int,
    summarized_count: int,
    preserve_first_messages: int,
    preserve_last_messages: int,
    preserve_tool_results: bool,
    compression_phase: str,
) -> None:
    """
    保存压缩元数据到数据库

    Args:
        conversation_id: 对话 ID
        conversation_service: 对话服务
        summary: 摘要文本
        original_count: 原始消息数量
        summary_tokens: 摘要 token 数
        middle_start: 被摘要替换的起始下标（包含）
        middle_end: 被摘要替换的结束下标（不包含）
        summarized_count: 被摘要覆盖的消息数量
        preserve_first_messages: 固定保留的开头消息数
        preserve_last_messages: 尽量保留的结尾消息数
        preserve_tool_results: 是否保留中间 tool_result（仅用于记录配置）
        compression_phase: 压缩阶段（pre_run/runtime）
    """
    from datetime import datetime

    compression_info = {
        "type": "context_summary",
        "compressed_at": datetime.now().isoformat(),
        "summary": summary,
        "original_count": original_count,
        "summary_tokens": summary_tokens,
        # 使用范围而不是 count，避免“保存/加载语义不一致”
        "middle_start": middle_start,
        "middle_end": middle_end,
        "summarized_count": summarized_count,
        # 记录当时的策略参数，便于调试与回放
        "preserve_first_messages": preserve_first_messages,
        "preserve_last_messages": preserve_last_messages,
        "preserve_tool_results": preserve_tool_results,
        "compression_phase": compression_phase,
    }

    # 获取现有 metadata 并合并
    conversation = await conversation_service.get_conversation(conversation_id)
    existing_metadata = {}
    if conversation and hasattr(conversation, "metadata"):
        existing_metadata = conversation.metadata if isinstance(conversation.metadata, dict) else {}

    existing_metadata["compression"] = compression_info

    await conversation_service.update_conversation(
        conversation_id=conversation_id, metadata=existing_metadata
    )

    logger.info(f"💾 压缩元数据已保存: conversation_id={conversation_id}")


async def load_with_existing_summary(
    messages: List[Dict[str, Any]], conversation_id: str, conversation_service: Any
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    加载消息时应用已有的压缩摘要

    如果对话已有压缩摘要，则自动应用：
    - 用摘要替换早期消息
    - 保留最近的消息

    Args:
        messages: 原始消息列表
        conversation_id: 对话 ID
        conversation_service: 对话服务

    Returns:
        (处理后的消息列表, 是否应用了摘要)
    """
    try:
        conversation = await conversation_service.get_conversation(conversation_id)
        if not conversation or not hasattr(conversation, "metadata"):
            return messages, False

        metadata = conversation.metadata if isinstance(conversation.metadata, dict) else {}
        compression = metadata.get("compression")

        if not compression or not compression.get("summary"):
            return messages, False

        # 只应用“上下文压缩摘要”，避免误用 failure_summary 等其他复用字段
        compression_type = compression.get("type")
        if compression_type and compression_type != "context_summary":
            return messages, False
        if not compression_type:
            # 兼容：如果没有 type，但包含 failure_summary 常用字段，直接跳过
            if compression.get("from_message_id"):
                return messages, False

        summary = compression["summary"]
        middle_start = compression.get("middle_start")
        middle_end = compression.get("middle_end")

        # 旧 schema（只有 compressed_count）无法可靠回放，会导致消息错删；保守跳过，等下次重新生成
        if middle_start is None or middle_end is None:
            logger.warning("⚠️ 压缩摘要 schema 过旧，跳过应用（等待重新生成）")
            return messages, False

        if not isinstance(middle_start, int) or not isinstance(middle_end, int):
            logger.warning("⚠️ 压缩摘要 schema 异常（middle_start/middle_end 非整数），跳过应用")
            return messages, False

        if middle_end <= middle_start:
            return messages, False

        # 检查消息数量是否足够应用摘要
        if len(messages) <= middle_end:
            return messages, False

        covered = middle_end - middle_start

        # 构建摘要消息
        summary_message = {
            "role": "user",
            "content": f"[历史对话摘要 - 覆盖 {covered} 条消息]\n\n{summary}",
        }

        # 用摘要替换指定范围
        result = messages[:middle_start] + [summary_message] + messages[middle_end:]

        # 🛡️ 摘要替换后确保 tool_use/tool_result 配对
        from core.llm.adaptor import ClaudeAdaptor

        result = ClaudeAdaptor.ensure_tool_pairs(result)

        logger.info(
            f"📦 应用已有摘要: {len(messages)} → {len(result)} 条消息 "
            f"(摘要覆盖 {covered} 条, range=[{middle_start},{middle_end}))"
        )

        return result, True

    except Exception as e:
        logger.warning(f"⚠️ 加载压缩摘要失败: {e}")
        return messages, False


# 导出
__all__ = [
    "QoSLevel",
    "QOS_TOKEN_BUDGETS",
    "ContextStrategy",
    "TrimStats",
    "get_context_strategy",
    "get_memory_guidance_prompt",
    "should_warn_backend",
    # 🆕 带摘要的智能压缩（双阈值机制）
    "CompressionPhase",
    "fast_prefilter_messages",  # 快速字符级预过滤
    "trim_by_token_budget",  # 纯 token 驱动裁剪
    "compress_with_summary",
    "load_with_existing_summary",
    # 🆕 摘要生成器
    "ConversationSummarizer",
    "generate_conversation_summary",
    # 🆕 工具结果压缩器（统一方案）
    "ToolResultCompressor",
    "compress_tool_result",
    "is_compressed",
    "extract_ref_id",
    "COMPRESSED_MARKER",
]

# 延迟导入摘要生成器（避免循环依赖）
from .summarizer import ConversationSummarizer, generate_conversation_summary

# 工具结果压缩器
from .tool_result import (
    COMPRESSED_MARKER,
    ToolResultCompressor,
    compress_tool_result,
    extract_ref_id,
    is_compressed,
)
