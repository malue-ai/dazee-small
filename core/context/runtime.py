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
    
    职责：
    1. 接收 content_start / content_delta / content_stop 事件
    2. 维护累积状态（支持多轮累积）
    3. 输出 content_blocks 数组（用于数据库 + 上下文传递）
    
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
        
        # 处理事件
        accumulator.on_content_start({"type": "thinking"})
        accumulator.on_content_delta({"type": "thinking_delta", "thinking": "让我思考..."})
        accumulator.on_content_stop()
        
        # 完成一轮
        turn_content = accumulator.finish_turn()
        
        # 获取完整内容（用于数据库）
        all_content = accumulator.build_for_db()
    """
    
    # === 所有轮次的累积（用于数据库持久化）===
    all_blocks: List[Dict[str, Any]] = field(default_factory=list)
    
    # === 当前轮的状态 ===
    current_thinking: Optional[Dict[str, Any]] = None    # 当前轮的 thinking block
    current_text: str = ""                                # 当前累积的 text
    current_blocks: List[Dict[str, Any]] = field(default_factory=list)  # 当前轮的其他 blocks
    
    # === 工具输入累积 ===
    _tool_input_buffer: str = ""
    
    # ==================== 事件处理方法 ====================
    
    def on_content_start(self, content_block: Dict[str, Any]) -> None:
        """
        处理 content_start 事件
        
        Args:
            content_block: {"type": "thinking|text|tool_use|tool_result", ...}
        """
        block_type = content_block.get("type")
        
        if block_type == "thinking":
            # thinking 通过 delta 累积
            self.current_thinking = {"type": "thinking", "thinking": ""}
        
        elif block_type == "text":
            # text 通过 delta 累积，这里不做处理
            pass
        
        elif block_type == "tool_use":
            # 先 flush 当前 text
            self._flush_text()
            # 添加 tool_use block
            self.current_blocks.append({
                "type": "tool_use",
                "id": content_block.get("id", ""),
                "name": content_block.get("name", ""),
                "input": content_block.get("input", {})
            })
            self._tool_input_buffer = ""  # 重置工具输入缓冲
        
        elif block_type == "tool_result":
            # 直接添加 tool_result block
            self.current_blocks.append({
                "type": "tool_result",
                "tool_use_id": content_block.get("tool_use_id", ""),
                "content": content_block.get("content", ""),
                "is_error": content_block.get("is_error", False)
            })
        
        elif block_type == "server_tool_use":
            # 服务端工具调用（web_search 等）
            self._flush_text()
            self.current_blocks.append({
                "type": "server_tool_use",
                "id": content_block.get("id", ""),
                "name": content_block.get("name", ""),
                "input": content_block.get("input", {})
            })
        
        elif block_type and block_type.endswith("_tool_result"):
            # 服务端工具结果（web_search_tool_result 等）
            self.current_blocks.append({
                "type": block_type,
                "tool_use_id": content_block.get("tool_use_id", ""),
                "content": content_block.get("content", [])
            })
    
    def on_content_delta(self, delta: Dict[str, Any]) -> None:
        """
        处理 content_delta 事件
        
        Args:
            delta: {"type": "text_delta|thinking_delta|input_json_delta", ...}
        """
        delta_type = delta.get("type")
        
        if delta_type == "text_delta" or delta_type == "text":
            # 累积 text
            self.current_text += delta.get("text", "")
        
        elif delta_type == "thinking_delta" or delta_type == "thinking":
            # 累积 thinking
            if self.current_thinking is not None:
                thinking_text = delta.get("thinking", delta.get("text", ""))
                self.current_thinking["thinking"] += thinking_text
        
        elif delta_type == "input_json_delta":
            # 累积工具输入 JSON
            self._tool_input_buffer += delta.get("partial_json", "")
            self._try_parse_tool_input()
    
    def on_content_stop(self, signature: Optional[str] = None) -> None:
        """
        处理 content_stop 事件
        
        Args:
            signature: thinking 的签名（如果有）
            
        TODO: 在这里可以添加 checkpoint 逻辑，将当前内容写入数据库
              实现断点恢复功能，防止中途崩溃丢失数据
        """
        # 如果有 signature，添加到 thinking block
        if signature and self.current_thinking:
            self.current_thinking["signature"] = signature
    
    # ==================== 轮次管理方法 ====================
    
    def finish_turn(self) -> List[Dict[str, Any]]:
        """
        完成当前轮（Agent 一轮 LLM 调用结束时调用）
        
        将当前轮的内容合并到 all_blocks，
        返回当前轮的 content（用于作为 assistant 消息传给下一轮）
        
        Returns:
            当前轮的 content_blocks
            
        TODO: 在这里可以添加 checkpoint 逻辑
              每轮结束时 UPDATE messages 表，保存当前进度
              这样即使后续轮次失败，也不会丢失之前的内容
        """
        # flush 当前 text
        self._flush_text()
        
        # 构建当前轮的 content
        turn_content = []
        if self.current_thinking and self.current_thinking.get("thinking"):
            turn_content.append(self.current_thinking)
        turn_content.extend(self.current_blocks)
        
        # 合并到 all_blocks（用于最终数据库存储）
        self.all_blocks.extend(turn_content)
        
        # 重置当前轮状态（为下一轮准备）
        self.current_thinking = None
        self.current_text = ""
        self.current_blocks = []
        self._tool_input_buffer = ""
        
        return turn_content
    
    def get_current_turn_content(self) -> List[Dict[str, Any]]:
        """
        获取当前轮的 content（用于传给下一轮 LLM 作为上下文）
        
        注意：不会 flush，只是读取当前状态
        
        Returns:
            当前轮的 content_blocks（不含未完成的 text）
        """
        result = []
        if self.current_thinking and self.current_thinking.get("thinking"):
            result.append(self.current_thinking.copy())
        result.extend([b.copy() for b in self.current_blocks])
        
        # 包含当前累积的 text
        if self.current_text:
            result.append({"type": "text", "text": self.current_text})
        
        return result
    
    # ==================== 输出方法 ====================
    
    def build_for_db(self) -> List[Dict[str, Any]]:
        """
        构建用于数据库存储的完整 content
        
        包含所有已完成轮次 + 当前轮未完成的内容
        
        Returns:
            完整的 content_blocks 数组
        """
        result = self.all_blocks.copy()
        
        # 加上当前轮未完成的内容
        if self.current_thinking and self.current_thinking.get("thinking"):
            result.append(self.current_thinking)
        
        # flush text 到 result（但不修改内部状态）
        if self.current_text:
            result.append({"type": "text", "text": self.current_text})
        
        result.extend(self.current_blocks)
        
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
            self.current_blocks or 
            self.current_text or 
            (self.current_thinking and self.current_thinking.get("thinking"))
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取累积统计信息"""
        return {
            "total_blocks": len(self.all_blocks),
            "current_blocks": len(self.current_blocks),
            "current_text_length": len(self.current_text),
            "has_thinking": self.current_thinking is not None,
            "thinking_length": len(self.current_thinking.get("thinking", "")) if self.current_thinking else 0
        }
    
    def reset(self) -> None:
        """
        完全重置（新的 message 开始时调用）
        """
        self.all_blocks = []
        self.current_thinking = None
        self.current_text = ""
        self.current_blocks = []
        self._tool_input_buffer = ""
    
    # ==================== 私有方法 ====================
    
    def _flush_text(self) -> None:
        """将累积的 text 转为 text block"""
        if self.current_text:
            self.current_blocks.append({"type": "text", "text": self.current_text})
            self.current_text = ""
    
    def _try_parse_tool_input(self) -> None:
        """尝试解析累积的工具输入 JSON"""
        if not self._tool_input_buffer:
            return
        
        # 找到最后一个 tool_use block
        for block in reversed(self.current_blocks):
            if block.get("type") == "tool_use":
                try:
                    block["input"] = json.loads(self._tool_input_buffer)
                    self._tool_input_buffer = ""
                except json.JSONDecodeError:
                    pass  # JSON 不完整，继续累积
                break


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
