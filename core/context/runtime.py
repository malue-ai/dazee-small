"""
RuntimeContext - Agent 运行时上下文管理

职责：
1. 管理 chat() 方法中的所有运行时状态
2. 统一 SSE 事件块（block）的状态管理
3. 累积 content blocks（thinking, text, tool_use, tool_result）
4. 简化 Agent 代码，提高可测试性

设计原则：
- 单一职责：只管理运行时状态，不包含业务逻辑
- 可追踪：所有状态变更可追踪和调试
- 可重置：支持多轮对话时重置部分状态

Content 数据结构（Claude API 标准）：
[
    {"type": "thinking", "thinking": "...", "signature": "..."},
    {"type": "text", "text": "..."},
    {"type": "tool_use", "id": "...", "name": "...", "input": {...}},
    {"type": "tool_result", "tool_use_id": "...", "content": "..."},
    ...
]
"""

# 1. 标准库
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

# 3. 本地模块
from core.llm import Message

# 2. 第三方库（无）


@dataclass
class BlockState:
    """
    SSE 事件块状态

    管理 content_start/delta/stop 事件的状态机
    """

    index: int = 0  # 全局递增的 block 索引
    current_type: Optional[str] = None  # 当前 block 类型 ("thinking" | "text")
    current_index: Optional[int] = None  # 当前正在处理的 block 索引

    def start_new_block(self, block_type: str) -> int:
        """
        开始新的 block，返回新 block 的索引

        Args:
            block_type: block 类型 ("thinking" | "text")

        Returns:
            新 block 的索引
        """
        self.current_type = block_type
        self.current_index = self.index
        self.index += 1
        return self.current_index

    def close_current_block(self) -> Optional[int]:
        """
        关闭当前 block，返回被关闭的 block 索引

        Returns:
            被关闭的 block 索引，如果没有打开的 block 则返回 None
        """
        if self.current_type is None:
            return None

        closed_index = self.current_index
        self.current_type = None
        self.current_index = None
        return closed_index

    def is_block_open(self) -> bool:
        """检查是否有打开的 block"""
        return self.current_type is not None

    def needs_transition(self, new_type: str) -> bool:
        """检查是否需要切换 block 类型"""
        return self.current_type != new_type


@dataclass
class BlockContext:
    """
    单个 block 的累积上下文

    支持并行累积多个 block（基于 index）

    优化：使用 List[str] + join 替代字符串拼接，减少内存分配
    """

    block_type: str
    index: int
    content_chunks: List[str] = field(
        default_factory=list
    )  # text/thinking 内容（优化：list 替代 str）
    tool_use: Optional[Dict[str, Any]] = None  # tool_use 数据
    tool_input_chunks: List[str] = field(
        default_factory=list
    )  # 工具输入 JSON 缓冲（优化：list 替代 str）
    tool_result: Optional[Dict[str, Any]] = None  # tool_result 数据
    tool_result_chunks: List[str] = field(
        default_factory=list
    )  # tool_result 内容缓冲（优化：list 替代 str）
    is_complete: bool = False  # 是否已完成（收到 content_stop）

    @property
    def content(self) -> str:
        """懒加载获取完整内容"""
        return "".join(self.content_chunks)

    @property
    def tool_input_buffer(self) -> str:
        """懒加载获取完整工具输入"""
        return "".join(self.tool_input_chunks)

    @property
    def tool_result_buffer(self) -> str:
        """懒加载获取完整工具结果"""
        return "".join(self.tool_result_chunks)

    def try_parse_tool_input(self) -> None:
        """尝试解析累积的工具输入 JSON"""
        if not self.tool_input_chunks or not self.tool_use:
            return

        try:
            full_buffer = "".join(self.tool_input_chunks)  # 只在解析时 join
            self.tool_use["input"] = json.loads(full_buffer)
            self.tool_input_chunks.clear()  # 解析成功后清空
        except json.JSONDecodeError:
            pass  # JSON 不完整，继续累积


@dataclass
class ContentAccumulator:
    """
    Content 累积器 - 将流式事件累积成 content_blocks 数组

    基于 index 的并行累积：
    - 每个 index 对应一个独立的 BlockContext
    - 多个工具可以并行累积，互不干扰
    - content_stop 时根据 index 处理对应的 block

    输出格式（Claude API 标准）：
    [
        {"type": "thinking", "thinking": "...", "signature": "..."},
        {"type": "text", "text": "..."},
        {"type": "tool_use", "id": "...", "name": "...", "input": {...}},
        {"type": "tool_result", "tool_use_id": "...", "content": "...", "is_error": false},
        ...
    ]

    使用示例：
        accumulator = ContentAccumulator()

        # 并行处理多个 block
        accumulator.on_content_start({"type": "tool_use", "id": "t1", "name": "plan"}, index=0)
        accumulator.on_content_start({"type": "tool_use", "id": "t2", "name": "api_calling"}, index=1)
        accumulator.on_content_delta('{"query": "AI news"}', index=0)
        accumulator.on_content_delta('{"api_name": "weather"}', index=1)
        accumulator.on_content_stop(index=0)  # 保存第一个工具
        accumulator.on_content_stop(index=1)  # 保存第二个工具

        # 获取完整内容
        all_content = accumulator.build_for_db()
    """

    # === 所有已完成的 blocks（按 index 顺序）===
    all_blocks: List[Dict[str, Any]] = field(default_factory=list)

    # === 基于 index 的并行累积 ===
    _active_blocks: Dict[int, BlockContext] = field(default_factory=dict)

    # === Metadata 累积（用于 message_delta）===
    _metadata: Dict[str, Any] = field(default_factory=dict)

    # ==================== 事件处理方法 ====================

    def on_content_start(self, content_block: Dict[str, Any], index: int) -> None:
        """
        处理 content_start 事件

        Args:
            content_block: {"type": "thinking|text|tool_use|tool_result", ...}
            index: block 索引（必需）
        """
        block_type = content_block.get("type")
        ctx = BlockContext(block_type=block_type, index=index)

        if block_type == "thinking":
            ctx.content_chunks = []  # 初始化空 list

        elif block_type == "text":
            ctx.content_chunks = []  # 初始化空 list

        elif block_type in ("tool_use",):
            ctx.tool_use = {
                "type": block_type,
                "id": content_block.get("id", ""),
                "name": content_block.get("name", ""),
                "input": content_block.get("input", {}),
            }
            ctx.tool_input_chunks = []  # 初始化空 list

        elif block_type == "tool_result":
            initial_content = content_block.get("content", "")
            if initial_content:
                # 完整模式：直接保存到 all_blocks
                self.all_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": content_block.get("tool_use_id", ""),
                        "content": initial_content,
                        "is_error": content_block.get("is_error", False),
                        "index": index,
                    }
                )
                ctx.is_complete = True  # 标记已完成，不需要再处理 stop
            else:
                # 流式模式
                ctx.tool_result = {
                    "type": "tool_result",
                    "tool_use_id": content_block.get("tool_use_id", ""),
                    "is_error": content_block.get("is_error", False),
                }
                ctx.tool_result_chunks = []  # 初始化空 list

        elif block_type and block_type.endswith("_tool_result"):
            # 服务端工具结果，直接保存
            self.all_blocks.append(
                {
                    "type": block_type,
                    "tool_use_id": content_block.get("tool_use_id", ""),
                    "content": content_block.get("content", []),
                    "index": index,
                }
            )
            ctx.is_complete = True

        self._active_blocks[index] = ctx

    def on_content_delta(self, delta: str, index: int) -> None:
        """
        处理 content_delta 事件

        Args:
            delta: 字符串（增量内容）
            index: block 索引（必需）
        """
        ctx = self._active_blocks.get(index)
        if not ctx or ctx.is_complete:
            return

        if ctx.block_type == "text":
            ctx.content_chunks.append(delta)  # append 替代 +=（优化：减少内存分配）
        elif ctx.block_type == "thinking":
            ctx.content_chunks.append(delta)  # append 替代 +=（优化：减少内存分配）
        elif ctx.block_type in ("tool_use",):
            ctx.tool_input_chunks.append(delta)  # append 替代 +=（优化：减少内存分配）
            ctx.try_parse_tool_input()
        elif ctx.block_type == "tool_result":
            ctx.tool_result_chunks.append(delta)  # append 替代 +=（优化：减少内存分配）

    def on_content_stop(self, index: int, signature: Optional[str] = None) -> None:
        """
        处理 content_stop 事件

        Args:
            index: block 索引（必需）
            signature: thinking 的签名（如果有）
        """
        ctx = self._active_blocks.get(index)
        if not ctx or ctx.is_complete:
            return

        block = None

        if ctx.block_type == "thinking":
            if ctx.content:
                block = {"type": "thinking", "thinking": ctx.content, "index": index}
                if signature:
                    block["signature"] = signature

        elif ctx.block_type == "text":
            if ctx.content:
                block = {"type": "text", "text": ctx.content, "index": index}

        elif ctx.block_type in ("tool_use",):
            if ctx.tool_use:
                block = {**ctx.tool_use, "index": index}

        elif ctx.block_type == "tool_result":
            if ctx.tool_result:
                ctx.tool_result["content"] = ctx.tool_result_buffer
                block = {**ctx.tool_result, "index": index}

        if block:
            self.all_blocks.append(block)

        ctx.is_complete = True
        # 清理已完成的 block
        del self._active_blocks[index]

    # ==================== 轮次管理方法 ====================

    def finish_turn(self) -> List[Dict[str, Any]]:
        """
        完成当前轮，处理所有未完成的并行 blocks

        Returns:
            all_blocks 的拷贝（按 index 排序）
        """
        # 完成所有并行 blocks
        for index, ctx in list(self._active_blocks.items()):
            if ctx.is_complete:
                continue

            block = None
            if ctx.block_type == "thinking" and ctx.content:
                block = {"type": "thinking", "thinking": ctx.content, "index": index}
            elif ctx.block_type == "text" and ctx.content:
                block = {"type": "text", "text": ctx.content, "index": index}
            elif ctx.block_type in ("tool_use",) and ctx.tool_use:
                block = {**ctx.tool_use, "index": index}
            elif ctx.block_type == "tool_result" and ctx.tool_result:
                ctx.tool_result["content"] = ctx.tool_result_buffer
                block = {**ctx.tool_result, "index": index}

            if block:
                self.all_blocks.append(block)

        self._active_blocks.clear()

        # 按 index 排序
        self.all_blocks.sort(key=lambda b: b.get("index", float("inf")))

        return [b.copy() for b in self.all_blocks]

    def get_current_turn_content(self) -> List[Dict[str, Any]]:
        """
        获取当前所有已完成的 content blocks

        Returns:
            all_blocks 的拷贝
        """
        return [b.copy() for b in self.all_blocks]

    # ==================== 输出方法 ====================

    def build_for_db(self, include_index: bool = True) -> List[Dict[str, Any]]:
        """
        构建用于数据库存储的完整 content

        Args:
            include_index: 是否包含 index 字段（默认 True）

        Returns:
            完整的 content_blocks 数组，按 index 排序
        """
        # 深拷贝 all_blocks
        result = [block.copy() for block in self.all_blocks]

        # 收集正在进行的并行 blocks
        for index, ctx in self._active_blocks.items():
            if ctx.is_complete:
                continue

            block = None
            if ctx.block_type == "thinking" and ctx.content:
                block = {"type": "thinking", "thinking": ctx.content, "index": index}
            elif ctx.block_type == "text" and ctx.content:
                block = {"type": "text", "text": ctx.content, "index": index}
            elif ctx.block_type in ("tool_use",) and ctx.tool_use:
                block = {**ctx.tool_use, "index": index}
            elif ctx.block_type == "tool_result" and ctx.tool_result:
                ctx.tool_result["content"] = ctx.tool_result_buffer
                block = {**ctx.tool_result, "index": index}

            if block:
                result.append(block)

        # 按 index 排序
        result.sort(key=lambda b: b.get("index", float("inf")))

        # 重新分配 index（确保连续）
        if include_index:
            for i, block in enumerate(result):
                block["index"] = i
        else:
            # 移除 index 字段
            for block in result:
                block.pop("index", None)

        return result

    def build_for_db_json(self) -> str:
        """
        构建用于数据库存储的 JSON 字符串

        Returns:
            JSON 格式的 content_blocks
        """
        return json.dumps(self.build_for_db(), ensure_ascii=False)

    # ==================== 状态查询方法 ====================

    def has_content(self) -> bool:
        """检查是否有任何内容"""
        return bool(self.all_blocks or self._active_blocks)

    def get_stats(self) -> Dict[str, Any]:
        """获取累积统计信息"""
        return {
            "total_blocks": len(self.all_blocks),
            "active_blocks": len(self._active_blocks),
        }

    # ==================== Metadata 方法 ====================

    def add_metadata(self, key: str, value: Any) -> None:
        """
        添加 metadata（用于累积 message_delta）

        Args:
            key: metadata key（如 intent, recommended）
            value: metadata value（会直接替换已有值）
        """
        self._metadata[key] = value

    def get_metadata(self) -> Dict[str, Any]:
        """获取累积的 metadata"""
        return self._metadata.copy()

    # ==================== 内容提取便捷方法 ====================

    def get_text_content(self) -> str:
        """
        获取所有 text block 的内容（拼接）

        Returns:
            所有 text 内容的拼接字符串
        """
        return "".join(
            block.get("text", "") for block in self.all_blocks if block.get("type") == "text"
        )

    def get_thinking_content(self) -> str:
        """
        获取所有 thinking block 的内容（拼接）

        Returns:
            所有 thinking 内容的拼接字符串
        """
        return "".join(
            block.get("thinking", "")
            for block in self.all_blocks
            if block.get("type") == "thinking"
        )

    def reset(self) -> None:
        """完全重置（新的 message 开始时调用）"""
        self.all_blocks = []
        self._active_blocks = {}
        self._metadata = {}


@dataclass
class RuntimeContext:
    """
    Agent 运行时上下文

    管理 chat() 方法执行期间的所有状态

    使用方式：
        ctx = RuntimeContext(session_id="sess_123")

        # 处理 content 事件
        ctx.accumulator.on_content_start({"type": "thinking"})
        ctx.accumulator.on_content_delta({"type": "thinking_delta", "thinking": "..."})
        ctx.accumulator.on_content_stop()

        # 完成一轮
        turn_content = ctx.accumulator.finish_turn()

        # 添加为 assistant 消息（用于下一轮上下文）
        ctx.add_assistant_message(turn_content)

        # 获取用于数据库的 content
        db_content = ctx.accumulator.build_for_db_json()
    """

    # === 会话标识 ===
    session_id: str = ""
    instance_id: str = ""  # Instance name for storage isolation

    # === 消息管理 ===
    messages: List[Any] = field(default_factory=list)

    # === 流式块状态（用于 SSE 事件）===
    block: BlockState = field(default_factory=BlockState)

    # === Content 累积器 ===
    accumulator: ContentAccumulator = field(default_factory=ContentAccumulator)

    # === 执行进度 ===
    step_index: int = 0  # 步骤索引（用于 status 事件）
    current_turn: int = 0  # 当前 turn
    # max_turns 已废弃：终止完全由 AdaptiveTerminator 信号驱动
    # 保留字段仅为向后兼容（回溯上下文等仍读取此值作为参考信息）
    max_turns: int = 999

    # === 自适应终止（V11）===
    consecutive_failures: int = 0  # 连续失败次数（工具错误/超时等）

    # === 工具调用轨迹（去重检测）===
    _tool_call_signatures: List[str] = field(default_factory=list)
    _consecutive_duplicate_count: int = 0

    # === 回溯状态（V12 回溯↔终止联动）===
    total_backtracks: int = 0  # 累计回溯次数
    backtracks_exhausted: bool = False  # 回溯是否已耗尽
    backtrack_escalation: Optional[str] = None  # 升级请求 ("intent_clarify"/"escalate")
    total_backtrack_tokens: int = 0  # 回溯累计消耗的 token

    # === 结果状态 ===
    final_result: Optional[str] = None  # 最终结果
    stop_reason: Optional[str] = None  # 停止原因
    finish_reason: Optional[str] = None  # 结构化终止原因（FinishReason 枚举值）
    last_llm_response: Optional[Any] = None  # 最后一次 LLM 响应（用于 RVR 循环判断工具调用）

    # === 时间戳 ===
    start_time: Optional[datetime] = None  # 开始时间
    last_activity_time: Optional[datetime] = None  # 最后活动时间（用于 idle 检测）

    def __post_init__(self) -> None:
        """初始化后处理"""
        if self.start_time is None:
            self.start_time = datetime.now()
        if self.last_activity_time is None:
            self.last_activity_time = self.start_time

    # === 消息管理方法 ===

    def add_history_messages(self, history: List[Dict[str, str]]) -> None:
        """
        添加历史消息

        Args:
            history: 历史消息列表 [{"role": "user", "content": "..."}, ...]
        """
        for msg in history:
            self.messages.append(Message(role=msg["role"], content=msg["content"]))

    def add_user_message(self, content: Any) -> None:
        """
        添加用户消息

        Args:
            content: 消息内容（字符串或 Claude API 格式）
        """
        self.messages.append(Message(role="user", content=content))

    def add_assistant_message(self, content: Any) -> None:
        """
        添加 assistant 消息

        Args:
            content: 消息内容（content_blocks 数组）
        """
        self.messages.append(Message(role="assistant", content=content))

    def add_tool_result(self, tool_results: List[Dict]) -> None:
        """
        添加工具结果（作为 user 消息）

        Args:
            tool_results: 工具执行结果列表
        """
        self.messages.append(Message(role="user", content=tool_results))

    def get_messages(self) -> List[Any]:
        """获取所有消息"""
        return self.messages

    # === 进度管理方法 ===

    def next_step(self) -> int:
        """
        递增步骤索引，返回当前索引

        Returns:
            当前步骤索引
        """
        current = self.step_index
        self.step_index += 1
        return current

    def next_turn(self) -> int:
        """
        递增 turn，返回当前 turn

        Returns:
            当前 turn（从 1 开始）
        """
        self.current_turn += 1
        return self.current_turn

    def is_max_turns_reached(self) -> bool:
        """检查是否达到最大 turn 数"""
        return self.current_turn >= self.max_turns

    @property
    def duration_seconds(self) -> float:
        """已执行时长（秒）"""
        if not self.start_time:
            return 0.0
        return (datetime.now() - self.start_time).total_seconds()

    @property
    def idle_seconds(self) -> float:
        """距上次活动的空闲时长（秒）"""
        if not self.last_activity_time:
            return 0.0
        return (datetime.now() - self.last_activity_time).total_seconds()

    def touch_activity(self) -> None:
        """更新最后活动时间（每次 LLM 响应或工具调用时调用）"""
        self.last_activity_time = datetime.now()

    # === 工具调用轨迹（去重检测）===

    def record_tool_call(self, tool_name: str, tool_input: dict) -> None:
        """Record a tool call signature for deduplication."""
        import hashlib
        import json as _json

        sig = hashlib.md5(
            f"{tool_name}:{_json.dumps(tool_input, sort_keys=True, ensure_ascii=False)}".encode()
        ).hexdigest()

        if self._tool_call_signatures and self._tool_call_signatures[-1] == sig:
            self._consecutive_duplicate_count += 1
        else:
            self._consecutive_duplicate_count = 0

        self._tool_call_signatures.append(sig)
        if len(self._tool_call_signatures) > 50:
            self._tool_call_signatures = self._tool_call_signatures[-20:]

    def detect_repeated_call(self, threshold: int = 3) -> bool:
        """
        Check if the same (tool_name, params) was called consecutively >= threshold times.
        """
        return self._consecutive_duplicate_count >= threshold - 1

    # === 状态重置方法 ===

    def reset_for_turn(self) -> None:
        """
        重置用于新的 turn

        注意：
        - block 状态不重置（需要跨 turn 保持 block 索引连续）
        - accumulator 不重置（多轮内容需要累积）
        """
        pass  # 目前不需要额外操作

    def reset_for_new_chat(self) -> None:
        """
        完全重置（新的 chat 调用）
        """
        self.messages = []
        self.block = BlockState()
        self.accumulator = ContentAccumulator()
        self.step_index = 0
        self.current_turn = 0
        self.consecutive_failures = 0
        # 工具轨迹重置
        self._tool_call_signatures = []
        self._consecutive_duplicate_count = 0
        # V12 回溯状态重置
        self.total_backtracks = 0
        self.backtracks_exhausted = False
        self.backtrack_escalation = None
        self.total_backtrack_tokens = 0
        self.final_result = None
        self.stop_reason = None
        self.finish_reason = None
        now = datetime.now()
        self.start_time = now
        self.last_activity_time = now

    # === 完成状态方法 ===

    def set_completed(self, result: str, reason: str = "end_turn") -> None:
        """
        设置完成状态

        Args:
            result: 最终结果
            reason: 停止原因
        """
        self.final_result = result
        self.stop_reason = reason

    def is_completed(self) -> bool:
        """检查是否已完成"""
        return self.final_result is not None

    # === 调试方法 ===

    def summary(self) -> Dict[str, Any]:
        """
        生成状态摘要（用于调试）

        Returns:
            状态字典
        """
        return {
            "session_id": self.session_id,
            "messages_count": len(self.messages),
            "current_turn": self.current_turn,
            "max_turns": self.max_turns,
            "step_index": self.step_index,
            "block_index": self.block.index,
            "current_block_type": self.block.current_type,
            "accumulator_stats": self.accumulator.get_stats(),
            "accumulated_text_length": len(self.accumulator.get_text_content()),
            "accumulated_thinking_length": len(self.accumulator.get_thinking_content()),
            "is_completed": self.is_completed(),
            "stop_reason": self.stop_reason,
            "finish_reason": self.finish_reason,
        }


def create_runtime_context(session_id: str, max_turns: int = 999) -> RuntimeContext:
    """
    创建运行时上下文

    终止完全由 AdaptiveTerminator 信号驱动，max_turns 仅为安全兜底。

    Args:
        session_id: 会话 ID
        max_turns: 已废弃，保留仅为兼容，默认 999（不生效）

    Returns:
        RuntimeContext 实例
    """
    return RuntimeContext(session_id=session_id, max_turns=max_turns)
