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
from typing import Dict, Any, List, Optional

# 2. 第三方库（无）

# 3. 本地模块（延迟导入，避免循环依赖）


@dataclass
class BlockState:
    """
    SSE 事件块状态
    
    管理 content_start/delta/stop 事件的状态机
    """
    index: int = 0                           # 全局递增的 block 索引
    current_type: Optional[str] = None       # 当前 block 类型 ("thinking" | "text")
    current_index: Optional[int] = None      # 当前正在处理的 block 索引
    
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
class ContentAccumulator:
    """
    Content 累积器 - 将流式事件累积成 content_blocks 数组
    
    核心设计：
    - 每次 content_stop 时立即将 block 保存到 all_blocks
    - 保证 blocks 按照实际事件顺序排列
    - 支持断点恢复（每个 block 完成就保存）
    
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
        
        # 处理事件（顺序自动保持正确）
        accumulator.on_content_start({"type": "thinking"})
        accumulator.on_content_delta({"type": "thinking_delta", "thinking": "让我思考..."})
        accumulator.on_content_stop()  # ← 立即保存到 all_blocks
        
        # 获取完整内容（用于数据库）
        all_content = accumulator.build_for_db()
    """
    
    # === 所有已完成的 blocks（按顺序）===
    all_blocks: List[Dict[str, Any]] = field(default_factory=list)
    
    # === 当前正在处理的 block 状态 ===
    _current_block_type: Optional[str] = None           # 当前 block 类型
    _current_thinking: str = ""                         # 当前 thinking 内容
    _current_text: str = ""                             # 当前 text 内容
    _current_tool_use: Optional[Dict[str, Any]] = None  # 当前 tool_use
    _tool_input_buffer: str = ""                        # 工具输入 JSON 缓冲
    _current_tool_result: Optional[Dict[str, Any]] = None  # 当前 tool_result（支持流式）
    _tool_result_content_buffer: str = ""               # tool_result 内容缓冲（流式累积）
    
    # === 向后兼容（保留旧字段名，但不再使用）===
    current_thinking: Optional[Dict[str, Any]] = None
    current_text: str = ""
    current_blocks: List[Dict[str, Any]] = field(default_factory=list)
    
    # === Metadata 累积（用于 message_delta）===
    _metadata: Dict[str, Any] = field(default_factory=dict)
    
    # ==================== 事件处理方法 ====================
    
    def on_content_start(self, content_block: Dict[str, Any]) -> None:
        """
        处理 content_start 事件
        
        开始一个新的 content block，记录类型并初始化状态
        
        Args:
            content_block: {"type": "thinking|text|tool_use|tool_result", ...}
        """
        block_type = content_block.get("type")
        self._current_block_type = block_type
        
        if block_type == "thinking":
            # thinking 通过 delta 累积
            self._current_thinking = ""
        
        elif block_type == "text":
            # text 通过 delta 累积
            self._current_text = ""
        
        elif block_type == "tool_use":
            # tool_use 需要等待 input_json_delta 累积完成
            self._current_tool_use = {
                "type": "tool_use",
                "id": content_block.get("id", ""),
                "name": content_block.get("name", ""),
                "input": content_block.get("input", {})
            }
            self._tool_input_buffer = ""
        
        elif block_type == "tool_result":
            # tool_result 支持两种模式：
            # 1. 完整模式：content 有值，直接保存
            # 2. 流式模式：content 为空，通过 delta 累积
            initial_content = content_block.get("content", "")
            if initial_content:
                # 完整模式：直接保存到 all_blocks
                self.all_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": content_block.get("tool_use_id", ""),
                    "content": initial_content,
                    "is_error": content_block.get("is_error", False)
                })
            else:
                # 流式模式：初始化累积状态，等待 delta 和 stop
                self._current_tool_result = {
                    "type": "tool_result",
                    "tool_use_id": content_block.get("tool_use_id", ""),
                    "is_error": content_block.get("is_error", False)
                }
                self._tool_result_content_buffer = ""
        
        elif block_type == "server_tool_use":
            # 服务端工具调用（web_search 等）
            self._current_tool_use = {
                "type": "server_tool_use",
                "id": content_block.get("id", ""),
                "name": content_block.get("name", ""),
                "input": content_block.get("input", {})
            }
        
        elif block_type and block_type.endswith("_tool_result"):
            # 服务端工具结果，直接保存
            self.all_blocks.append({
                "type": block_type,
                "tool_use_id": content_block.get("tool_use_id", ""),
                "content": content_block.get("content", [])
            })
    
    def on_content_delta(self, delta: str) -> None:
        """
        处理 content_delta 事件
        
        累积流式内容到当前 block
        
        简化格式：delta 直接是字符串，类型由 _current_block_type 决定
        - text block: delta = "我"
        - thinking block: delta = "Let me think..."
        - tool_use block: delta = '{"code": "print('
        - tool_result block: delta = '{"success": true...'（流式模式）
        
        Args:
            delta: 字符串（增量内容）
        """
        if self._current_block_type == "text":
            self._current_text += delta
        elif self._current_block_type == "thinking":
            self._current_thinking += delta
        elif self._current_block_type in ("tool_use", "server_tool_use"):
            self._tool_input_buffer += delta
            self._try_parse_tool_input()
        elif self._current_block_type == "tool_result":
            # 流式模式：累积 tool_result 内容
            self._tool_result_content_buffer += delta
    
    def on_content_stop(self, signature: Optional[str] = None) -> None:
        """
        处理 content_stop 事件
        
        核心逻辑：立即将当前 block 保存到 all_blocks
        这样可以保证 blocks 的顺序与实际事件顺序一致
        
        Args:
            signature: thinking 的签名（如果有）
        """
        if self._current_block_type == "thinking":
            # 保存 thinking block
            if self._current_thinking:
                block = {"type": "thinking", "thinking": self._current_thinking}
                if signature:
                    block["signature"] = signature
                self.all_blocks.append(block)
            self._current_thinking = ""
        
        elif self._current_block_type == "text":
            # 保存 text block
            if self._current_text:
                self.all_blocks.append({"type": "text", "text": self._current_text})
            self._current_text = ""
        
        elif self._current_block_type in ("tool_use", "server_tool_use"):
            # 保存 tool_use block
            if self._current_tool_use:
                self.all_blocks.append(self._current_tool_use)
            self._current_tool_use = None
        
        elif self._current_block_type == "tool_result":
            # 流式模式：保存累积的 tool_result
            if self._current_tool_result:
                self._current_tool_result["content"] = self._tool_result_content_buffer
                self.all_blocks.append(self._current_tool_result)
                self._current_tool_result = None
                self._tool_result_content_buffer = ""
        
        # 注意：完整模式的 tool_result 和 *_tool_result 已在 on_content_start 时保存
        
        # 重置当前 block 类型
        self._current_block_type = None
    
    # ==================== 轮次管理方法 ====================
    
    def finish_turn(self) -> List[Dict[str, Any]]:
        """
        完成当前轮（向后兼容，新设计中可能不需要调用）
        
        由于每个 block 在 content_stop 时已保存到 all_blocks，
        这个方法现在只是确保任何未完成的内容被保存
        
        Returns:
            all_blocks 的拷贝
        """
        # 如果有未完成的内容，强制保存
        if self._current_thinking:
            self.all_blocks.append({"type": "thinking", "thinking": self._current_thinking})
            self._current_thinking = ""
        
        if self._current_text:
            self.all_blocks.append({"type": "text", "text": self._current_text})
            self._current_text = ""
        
        if self._current_tool_use:
            self.all_blocks.append(self._current_tool_use)
            self._current_tool_use = None
        
        self._current_block_type = None
        self._tool_input_buffer = ""
        
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
        
        由于每个 block 在 content_stop 时已按顺序保存到 all_blocks，
        这里直接返回 all_blocks（加上可选的 index）
        
        Args:
            include_index: 是否包含 index 字段（默认 True）
        
        Returns:
            完整的 content_blocks 数组，格式如：
            [
                {"index": 0, "type": "thinking", "thinking": "..."},
                {"index": 1, "type": "text", "text": "..."},
                {"index": 2, "type": "tool_use", ...},
                {"index": 3, "type": "tool_result", ...}
            ]
        """
        # 深拷贝 all_blocks
        result = [block.copy() for block in self.all_blocks]
        
        # 如果有正在进行的内容（未收到 content_stop），也包含进去
        if self._current_thinking:
            result.append({"type": "thinking", "thinking": self._current_thinking})
        
        if self._current_text:
            result.append({"type": "text", "text": self._current_text})
        
        if self._current_tool_use:
            result.append(self._current_tool_use.copy())
        
        # 给每个 block 加上 index
        if include_index:
            for i, block in enumerate(result):
                block["index"] = i
        
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
        return bool(
            self.all_blocks or 
            self._current_thinking or 
            self._current_text or
            self._current_tool_use
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取累积统计信息"""
        return {
            "total_blocks": len(self.all_blocks),
            "current_block_type": self._current_block_type,
            "current_thinking_length": len(self._current_thinking),
            "current_text_length": len(self._current_text),
            "has_pending_tool_use": self._current_tool_use is not None
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
    
    def reset(self) -> None:
        """
        完全重置（新的 message 开始时调用）
        """
        self.all_blocks = []
        self._current_block_type = None
        self._current_thinking = ""
        self._current_text = ""
        self._current_tool_use = None
        self._tool_input_buffer = ""
        self._metadata = {}
        # 向后兼容字段
        self.current_thinking = None
        self.current_text = ""
        self.current_blocks = []
    
    # ==================== 私有方法 ====================
    
    def _flush_text(self) -> None:
        """将累积的 text 保存到 all_blocks（向后兼容）"""
        if self._current_text:
            self.all_blocks.append({"type": "text", "text": self._current_text})
            self._current_text = ""
    
    def _try_parse_tool_input(self) -> None:
        """尝试解析累积的工具输入 JSON"""
        if not self._tool_input_buffer:
            return
        
        # 更新当前 tool_use 的 input
        if self._current_tool_use:
            try:
                self._current_tool_use["input"] = json.loads(self._tool_input_buffer)
                self._tool_input_buffer = ""
            except json.JSONDecodeError:
                pass  # JSON 不完整，继续累积


# ==================== 向后兼容：保留 StreamAccumulator ====================

@dataclass
class StreamAccumulator:
    """
    流式响应累积器（向后兼容）
    
    ⚠️ 已废弃：新代码请使用 ContentAccumulator
    
    只累积 thinking 和 text，不支持 tool_use/tool_result
    """
    thinking: str = ""          # 累积的 thinking 内容
    content: str = ""           # 累积的 text 内容
    
    def append_thinking(self, text: str):
        """追加 thinking 内容"""
        self.thinking += text
    
    def append_content(self, text: str):
        """追加 text 内容"""
        self.content += text
    
    def reset(self):
        """重置累积器（用于新的 turn）"""
        self.thinking = ""
        self.content = ""


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
    
    # === 消息管理 ===
    messages: List[Any] = field(default_factory=list)
    
    # === 流式块状态（用于 SSE 事件）===
    block: BlockState = field(default_factory=BlockState)
    
    # === Content 累积器（新版，推荐使用）===
    accumulator: ContentAccumulator = field(default_factory=ContentAccumulator)
    
    # === 向后兼容：保留 stream ===
    stream: StreamAccumulator = field(default_factory=StreamAccumulator)
    
    # === 执行进度 ===
    step_index: int = 0                      # 步骤索引（用于 status 事件）
    current_turn: int = 0                    # 当前 turn
    max_turns: int = 20                      # 最大 turn 数
    
    # === 结果状态 ===
    final_result: Optional[str] = None       # 最终结果
    stop_reason: Optional[str] = None        # 停止原因
    last_llm_response: Optional[Any] = None  # 最后一次 LLM 响应（用于 RVR 循环判断工具调用）
    
    # === 时间戳 ===
    start_time: Optional[datetime] = None    # 开始时间
    
    def __post_init__(self):
        """初始化后处理"""
        if self.start_time is None:
            self.start_time = datetime.now()
    
    # === 消息管理方法 ===
    
    def add_history_messages(self, history: List[Dict[str, str]]):
        """
        添加历史消息
        
        Args:
            history: 历史消息列表 [{"role": "user", "content": "..."}, ...]
        """
        from core.llm import Message
        for msg in history:
            self.messages.append(Message(
                role=msg["role"],
                content=msg["content"]
            ))
    
    def add_user_message(self, content: Any):
        """
        添加用户消息
        
        Args:
            content: 消息内容（字符串或 Claude API 格式）
        """
        from core.llm import Message
        self.messages.append(Message(role="user", content=content))
    
    def add_assistant_message(self, content: Any):
        """
        添加 assistant 消息
        
        Args:
            content: 消息内容（content_blocks 数组）
        """
        from core.llm import Message
        self.messages.append(Message(role="assistant", content=content))
    
    def add_tool_result(self, tool_results: List[Dict]):
        """
        添加工具结果（作为 user 消息）
        
        Args:
            tool_results: 工具执行结果列表
        """
        from core.llm import Message
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
    
    # === 状态重置方法 ===
    
    def reset_for_turn(self):
        """
        重置用于新的 turn
        
        注意：
        - block 状态不重置（需要跨 turn 保持 block 索引连续）
        - accumulator 不重置（多轮内容需要累积）
        """
        self.stream.reset()  # 向后兼容
    
    def reset_stream_for_turn(self):
        """
        重置流式累积器（向后兼容）
        """
        self.stream.reset()
    
    def reset_for_new_chat(self):
        """
        完全重置（新的 chat 调用）
        """
        self.messages = []
        self.block = BlockState()
        self.accumulator = ContentAccumulator()
        self.stream = StreamAccumulator()
        self.step_index = 0
        self.current_turn = 0
        self.final_result = None
        self.stop_reason = None
        self.start_time = datetime.now()
    
    # === 完成状态方法 ===
    
    def set_completed(self, result: str, reason: str = "end_turn"):
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
            # 新版累积器统计
            "accumulator_stats": self.accumulator.get_stats(),
            # 向后兼容
            "accumulated_thinking_length": len(self.stream.thinking),
            "accumulated_content_length": len(self.stream.content),
            "is_completed": self.is_completed(),
            "stop_reason": self.stop_reason
        }


def create_runtime_context(
    session_id: str,
    max_turns: int = 20
) -> RuntimeContext:
    """
    创建运行时上下文
    
    Args:
        session_id: 会话 ID
        max_turns: 最大 turn 数
        
    Returns:
        RuntimeContext 实例
    """
    return RuntimeContext(
        session_id=session_id,
        max_turns=max_turns
    )
