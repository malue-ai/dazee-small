"""
事件广播器 - EventBroadcaster

职责：
1. Agent 发送事件的统一入口
2. 缓存 tool_id -> tool_name 映射
3. 内容累积（管理 ContentAccumulator）
4. 消息持久化（checkpoint + 最终保存）
5. 调用 Adapter 的增强方法（如果有）

架构（V7 重构后）：
    SimpleAgent → EventBroadcaster
                        │
                        └──→ EventManager（统一入口）
                              │
                              └──→ storage.buffer_event()
                                    │
                                    ├──→ 格式转换（如果需要）
                                    ├──→ Redis INCR 生成 seq
                                    └──→ 存入 Redis + Pub/Sub

设计说明：
- 所有事件通过 EventManager 发送（统一入口）
- seq 在 buffer_event 中统一生成（Redis INCR）
- 格式转换在 buffer_event 中完成
- Broadcaster 只负责内部逻辑（累积、持久化）
- 特殊工具的业务增强由 Adapter 实现（如 ZenOAdapter.enhance_tool_result）

使用示例：
    broadcaster = EventBroadcaster(event_manager, conversation_service)
    
    # 开始消息（关联 message_id）
    await broadcaster.start_message(session_id, message_id)
    
    # Content 事件（自动累积 + checkpoint）
    await broadcaster.emit_content_start(session_id, index, content_block)
    await broadcaster.emit_content_delta(session_id, index, delta)
    await broadcaster.emit_content_stop(session_id, index)  # ← 自动 checkpoint
    
    # 结束消息（自动最终保存）
    await broadcaster.emit_message_stop(session_id)  # ← 自动保存完整消息
"""

import json
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, Set, TYPE_CHECKING, Literal
from uuid import uuid4
from logger import get_logger

# 避免循环导入
if TYPE_CHECKING:
    from services.conversation_service import ConversationService

from core.context.runtime import ContentAccumulator

logger = get_logger("events.broadcaster")


# ===========================================================================
# 常量定义
# ===========================================================================

# 持久化策略枚举
class PersistenceStrategy(str, Enum):
    """
    消息持久化策略
    
    - REALTIME: 实时存储，每个 content_stop 都 checkpoint（断点恢复能力强）
    - DEFERRED: 延迟存储，只在 message_stop 时一次性保存（减少 DB 写入）
    """
    REALTIME = "realtime"
    DEFERRED = "deferred"


# 策略类型别名（方便使用字符串）
PersistenceStrategyType = Literal["realtime", "deferred"]


class EventBroadcaster:
    """
    事件广播器
    
    将 Agent 产生的事件通过 EventManager 发送，同时管理内容累积和持久化
    
    核心职责：
    - 内容累积（ContentAccumulator）
    - 消息持久化（checkpoint + 最终保存）
    - 调用 Adapter 的增强方法（如 ZenOAdapter.enhance_tool_result）
    
    支持的事件类型：
    - content_start: 开始一个内容块（text/thinking/tool_use/tool_result）
    - content_delta: 内容增量
    - content_stop: 结束一个内容块
    - message_start: 消息开始
    - message_delta: 消息增量（usage 统计）
    - message_stop: 消息结束
    - conversation_start: 对话开始
    - conversation_delta: 对话增量更新
    - error: 错误事件
    
    注意：
    - 所有事件通过 EventManager 发送（统一入口）
    - seq 在 storage.buffer_event 中统一生成（Redis INCR）
    - 特殊工具的业务增强由 Adapter 实现（如 ZenOAdapter）
    """
    
    def __init__(
        self,
        event_manager,
        conversation_service: "ConversationService" = None,
        output_format: str = "zenflux",
        conversation_id: str = None,
        persistence_strategy: PersistenceStrategyType = "realtime"
    ):
        """
        初始化广播器
        
        Args:
            event_manager: EventManager 实例
            conversation_service: ConversationService 实例（用于持久化）
            output_format: 输出事件格式（zeno/zenflux），默认 zenflux
            conversation_id: 对话 ID（用于 ZenO 格式）
            persistence_strategy: 持久化策略
                - "realtime": 实时存储，每个 content_stop 都 checkpoint（默认，断点恢复能力强）
                - "deferred": 延迟存储，只在 message_stop 时保存（减少 DB 写入）
        """
        self.events = event_manager
        self.conversation_service = conversation_service
        
        # 输出格式配置（由 chat.py 传递）
        self.output_format = output_format
        self.output_conversation_id = conversation_id
        
        # 🆕 持久化策略
        self.persistence_strategy = PersistenceStrategy(persistence_strategy)
        
        # ZenO 适配器（延迟初始化）
        self._zeno_adapter = None
        
        # tool_id -> tool_name 缓存（用于 tool_result 时查找工具名）
        self._tool_id_to_name: Dict[str, str] = {}
        
        # tool_id -> tool_input 缓存（用于 api_calling 判断 api_name）
        self._tool_id_to_input: Dict[str, Dict[str, Any]] = {}
        
        # session_id -> ContentAccumulator 映射
        self._accumulators: Dict[str, ContentAccumulator] = {}
        
        # session_id -> message_id 映射（用于持久化）
        self._session_message_ids: Dict[str, str] = {}
        
        # 🆕 session_id -> pending_metadata 映射（DEFERRED 策略用，累积 message_delta 的 metadata）
        self._pending_metadata: Dict[str, Dict[str, Any]] = {}
        
        logger.debug(f"EventBroadcaster 初始化: persistence_strategy={persistence_strategy}")
    
    def _get_adapter(self):
        """
        获取格式转换适配器（延迟初始化）
        
        Returns:
            适配器实例，如果不需要转换则返回 None
        """
        if self.output_format != "zeno":
            return None
        
        if self._zeno_adapter is None:
            from core.events.adapters.zeno import ZenOAdapter
            self._zeno_adapter = ZenOAdapter(conversation_id=self.output_conversation_id)
        return self._zeno_adapter
    
    def set_output_format(self, format: str, conversation_id: str = None) -> None:
        """
        设置输出格式（运行时动态配置）
        
        Args:
            format: 输出事件格式（zeno/zenflux）
            conversation_id: 对话 ID（用于 ZenO 格式）
        """
        self.output_format = format
        if conversation_id:
            self.output_conversation_id = conversation_id
            # 重置适配器以使用新的 conversation_id
            self._zeno_adapter = None
    
    def set_persistence_strategy(self, strategy: PersistenceStrategyType) -> None:
        """
        设置持久化策略（运行时动态配置）
        
        Args:
            strategy: 持久化策略
                - "realtime": 实时存储，每个 content_stop 都 checkpoint
                - "deferred": 延迟存储，只在 message_stop 时保存
        """
        self.persistence_strategy = PersistenceStrategy(strategy)
        logger.debug(f"持久化策略已切换: {strategy}")
    
    
    # ===========================================================================
    # 消息生命周期管理
    # ===========================================================================
    
    def start_message(
        self,
        session_id: str,
        message_id: str
    ) -> None:
        """
        开始一条新消息（初始化累积器）
        
        在 Agent 开始处理消息前调用
        
        Args:
            session_id: Session ID
            message_id: 消息 ID（用于持久化）
        """
        self._accumulators[session_id] = ContentAccumulator()
        self._session_message_ids[session_id] = message_id
        self._pending_metadata[session_id] = {}  # 🆕 初始化 pending metadata
        logger.debug(f"📝 开始消息累积: session={session_id}, message_id={message_id}")
    
    async def accumulate_usage(
        self,
        session_id: str,
        usage: Dict[str, int]
    ) -> None:
        """
        保存 token 使用量到数据库（增量合并）
        
        Args:
            session_id: Session ID
            usage: 使用量字典
        """
        if not self.conversation_service:
            return
        
        message_id = self._session_message_ids.get(session_id)
        if not message_id:
            return
        
        try:
            await self.conversation_service.update_message(
                message_id=message_id,
                metadata={"usage": usage}
            )
            logger.debug(f"📊 保存 usage: message_id={message_id}, tokens={usage}")
        except Exception as e:
            logger.warning(f"⚠️ 保存 usage 失败: {str(e)}")
    
    def get_accumulator(self, session_id: str) -> Optional[ContentAccumulator]:
        """获取 session 的累积器（供外部查询）"""
        return self._accumulators.get(session_id)
    
    # ===========================================================================
    # 核心事件发送方法
    # ===========================================================================
    
    async def emit_content_start(
        self,
        session_id: str,
        index: int,
        content_block: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        发送 content_start 事件
        
        会自动处理：
        - tool_use: 记录 tool_id -> tool_name 映射
        - tool_result: 调用 adapter 的增强方法生成额外 delta
        - 自动累积到 ContentAccumulator
        
        Args:
            session_id: Session ID
            index: 内容块索引
            content_block: 内容块
            
        Returns:
            发送的事件，如果被过滤则返回 None
        """
        # 记录 tool_use 的工具名和输入参数
        if content_block.get("type") == "tool_use":
            tool_id = content_block.get("id", "")
            tool_name = content_block.get("name", "")
            tool_input = content_block.get("input", {})
            if tool_id and tool_name:
                self._tool_id_to_name[tool_id] = tool_name
                if tool_input:
                    self._tool_id_to_input[tool_id] = tool_input
        
        # 累积内容
        accumulator = self._accumulators.get(session_id)
        if accumulator:
            accumulator.on_content_start(content_block, index=index)
        
        # 通过 EventManager 发送事件
        result = await self.events.content.emit_content_start(
            session_id=session_id,
            index=index,
            content_block=content_block,
            output_format=self.output_format,
            adapter=self._get_adapter()
        )
        
        # tool_result 时调用 adapter 的增强方法生成额外 delta
        # 具体的业务增强逻辑由 Adapter 实现（如 ZenOAdapter 会拆分为 sql/data/chart 等）
        if content_block.get("type") == "tool_result":
            await self._emit_adapter_enhanced_deltas(session_id, content_block)
        
        return result
    
    async def _emit_adapter_enhanced_deltas(
        self,
        session_id: str,
        tool_result_block: Dict[str, Any]
    ) -> None:
        """
        调用 adapter 的增强方法，发送额外的 delta 事件
        
        Args:
            session_id: Session ID
            tool_result_block: tool_result 内容块
        """
        adapter = self._get_adapter()
        if not adapter:
            return
        
        tool_use_id = tool_result_block.get("tool_use_id", "")
        tool_name = self._tool_id_to_name.get(tool_use_id, "")
        tool_input = self._tool_id_to_input.get(tool_use_id, {})
        
        # 调用 adapter 的增强方法
        deltas = adapter.enhance_tool_result(
            tool_name=tool_name,
            tool_input=tool_input,
            tool_result=tool_result_block
        )
        
        # 发送生成的 delta 事件
        for delta in deltas:
            await self.emit_message_delta(
                session_id=session_id,
                delta=delta
            )
        
        # 清理工具缓存
        self._tool_id_to_name.pop(tool_use_id, None)
        self._tool_id_to_input.pop(tool_use_id, None)
    
    async def emit_content_delta(
        self,
        session_id: str,
        index: int,
        delta: str
    ) -> Optional[Dict[str, Any]]:
        """
        发送 content_delta 事件
        
        简化格式：delta 直接是字符串，类型由 content_start 的 content_block.type 决定
        自动累积到 ContentAccumulator
        
        Args:
            session_id: Session ID
            index: 内容块索引
            delta: 内容增量
            
        Returns:
            发送的事件，如果被过滤则返回 None
        """
        # 累积内容
        accumulator = self._accumulators.get(session_id)
        if accumulator:
            accumulator.on_content_delta(delta, index=index)
        
        # 通过 EventManager 发送事件
        return await self.events.content.emit_content_delta(
            session_id=session_id,
            index=index,
            delta=delta,
            output_format=self.output_format,
            adapter=self._get_adapter()
        )
    
    async def emit_content_stop(
        self,
        session_id: str,
        index: int,
        signature: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        发送 content_stop 事件
        
        自动：
        1. 累积到 ContentAccumulator
        2. Checkpoint 到数据库（仅 REALTIME 策略）
        
        Args:
            session_id: Session ID
            index: 内容块索引
            signature: 签名（Extended Thinking 用）
            
        Returns:
            发送的事件，如果被过滤则返回 None
        """
        # 累积内容
        accumulator = self._accumulators.get(session_id)
        if accumulator:
            accumulator.on_content_stop(index=index, signature=signature)
        
        # 通过 EventManager 发送事件
        result = await self.events.content.emit_content_stop(
            session_id=session_id,
            index=index,
            output_format=self.output_format,
            adapter=self._get_adapter()
        )
        
        # 🆕 根据策略决定是否 checkpoint
        # REALTIME: 每个 content_stop 都保存（断点恢复能力强）
        # DEFERRED: 跳过，等 message_stop 时一次性保存
        if self.persistence_strategy == PersistenceStrategy.REALTIME:
            await self._checkpoint_message(session_id)
        
        return result
    
    async def emit_message_start(
        self,
        session_id: str,
        message_id: str,
        model: str
    ) -> Optional[Dict[str, Any]]:
        """
        发送 message_start 事件
        
        Args:
            session_id: Session ID
            message_id: 消息 ID
            model: 模型名称
            
        Returns:
            发送的事件，如果被过滤则返回 None
        """
        # 通过 EventManager 发送事件
        return await self.events.message.emit_message_start(
            session_id=session_id,
            message_id=message_id,
            model=model,
            output_format=self.output_format,
            adapter=self._get_adapter()
        )
    
    async def emit_message_delta(
        self,
        session_id: str,
        delta: Dict[str, Any],
        message_id: str = None,
        persist: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        发送 message_delta 事件
        
        自动：
        1. 发送 SSE 事件
        2. 保存到数据库 metadata（增量合并/替换）
        
        Args:
            session_id: Session ID
            delta: Delta 内容，支持两种格式：
                - {"type": "xxx", "content": "..."}: 用 type 作为 key 保存 content
                - {"usage": {...}, ...}: 直接合并到 metadata
            message_id: 消息 ID（可选）
            persist: 是否保存到数据库（默认 True）
            
        Returns:
            发送的事件，如果被过滤则返回 None
        """
        # 1. 先发送 SSE 事件
        result = await self.events.message.emit_message_delta(
            session_id=session_id,
            delta=delta,
            message_id=message_id,
            output_format=self.output_format,
            adapter=self._get_adapter()
        )
        
        # 2. 保存到数据库 metadata（增量合并/替换）
        if persist:
            await self._persist_message_delta(session_id, delta)
        
        return result
    
    async def _persist_message_delta(
        self,
        session_id: str,
        delta: Dict[str, Any]
    ) -> None:
        """
        持久化 message_delta 到数据库 metadata
        
        根据持久化策略：
        - REALTIME：立即保存到数据库
        - DEFERRED：累积到 _pending_metadata，等 message_stop 时一起保存
        
        规则：
        - delta 有 type 字段：用 type 作为 key，content 作为 value
        - delta 无 type 字段：直接合并整个 delta 到 metadata
        - metadata 中已存在的字段会被替换，不存在的字段会增量添加
        
        Args:
            session_id: Session ID
            delta: Delta 内容
        """
        if not self.conversation_service:
            return
        
        msg_id = self._session_message_ids.get(session_id)
        if not msg_id:
            return
        
        # 解析 delta 格式
        if "type" in delta and "content" in delta:
            # 格式1：{"type": "xxx", "content": "..."}
            delta_type = delta["type"]
            content = delta["content"]
            
            # 解析 content（可能是 JSON 字符串）
            parsed_content = content
            if isinstance(content, str):
                try:
                    parsed_content = json.loads(content)
                except json.JSONDecodeError:
                    pass
            
            metadata_update = {delta_type: parsed_content}
        else:
            # 格式2：直接是 metadata 字段，如 {"usage": {...}}
            metadata_update = delta
        
        # 🆕 根据策略决定是立即保存还是累积
        if self.persistence_strategy == PersistenceStrategy.REALTIME:
            # REALTIME：立即保存到数据库
            try:
                await self.conversation_service.update_message(
                    message_id=msg_id,
                    metadata=metadata_update
                )
                logger.debug(f"📦 message_delta 已保存: message_id={msg_id}, keys={list(metadata_update.keys())}")
            except Exception as e:
                logger.warning(f"⚠️ message_delta 保存失败: {str(e)}")
        else:
            # DEFERRED：累积到 pending_metadata，等 message_stop 时一起保存
            if session_id not in self._pending_metadata:
                self._pending_metadata[session_id] = {}
            self._pending_metadata[session_id].update(metadata_update)
            logger.debug(f"📦 message_delta 已累积: session={session_id}, keys={list(metadata_update.keys())}")
    
    async def emit_message_stop(
        self,
        session_id: str,
        message_id: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        发送 message_stop 事件
        
        自动（无论哪种持久化策略都会执行）：
        1. 保存累积的 metadata（DEFERRED 策略）
        2. Checkpoint 当前累积内容（确保最后的内容不丢失）
        3. 更新消息状态为 completed
        4. 清理 session 状态
        
        Args:
            session_id: Session ID
            message_id: 消息 ID（可选）
            
        Returns:
            发送的事件，如果被过滤则返回 None
        """
        # 🆕 DEFERRED 策略：先保存累积的 metadata
        await self._flush_pending_metadata(session_id)
        
        # Checkpoint 当前累积的内容（防止最后一段 delta 丢失）
        # 无论 REALTIME 还是 DEFERRED 策略，message_stop 时都必须保存 content
        await self._checkpoint_message(session_id)
        
        # 更新状态为 completed
        await self._finalize_message(session_id)
        
        # 通过 EventManager 发送事件
        result = await self.events.message.emit_message_stop(
            session_id=session_id,
            message_id=message_id,
            output_format=self.output_format,
            adapter=self._get_adapter()
        )
        
        # 清理 session 状态
        self._cleanup_session(session_id)
        
        return result
    
    async def _flush_pending_metadata(self, session_id: str) -> None:
        """
        刷新累积的 metadata 到数据库（DEFERRED 策略用）
        
        Args:
            session_id: Session ID
        """
        if not self.conversation_service:
            return
        
        msg_id = self._session_message_ids.get(session_id)
        pending = self._pending_metadata.get(session_id)
        
        if not msg_id or not pending:
            return
        
        try:
            await self.conversation_service.update_message(
                message_id=msg_id,
                metadata=pending
            )
            logger.debug(f"📦 累积 metadata 已保存: message_id={msg_id}, keys={list(pending.keys())}")
        except Exception as e:
            logger.warning(f"⚠️ 累积 metadata 保存失败: {str(e)}")
    
    # ===========================================================================
    # Conversation 事件
    # ===========================================================================
    
    async def emit_conversation_title(
        self,
        session_id: str,
        conversation_id: str,
        title: str
    ) -> Dict[str, Any]:
        """发送标题更新（后台生成标题时使用）"""
        return await self._emit_conversation_delta(
            session_id=session_id,
            conversation_id=conversation_id,
            delta={"title": title}
        )
    
    # 内部事件发送方法
    
    async def _emit_conversation_start(
        self,
        session_id: str,
        conversation: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """发送 conversation_start 事件（内部方法）"""
        return await self.events.conversation.emit_conversation_start(
            session_id=session_id,
            conversation=conversation,
            output_format=self.output_format,
            adapter=self._get_adapter()
        )
    
    async def _emit_conversation_delta(
        self,
        session_id: str,
        conversation_id: str,
        delta: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """发送 conversation_delta 事件（内部方法）"""
        return await self.events.conversation.emit_conversation_delta(
            session_id=session_id,
            conversation_id=conversation_id,
            delta=delta,
            output_format=self.output_format,
            adapter=self._get_adapter()
        )
    
    async def _emit_error(
        self,
        session_id: str,
        error_type: str,
        error_message: str
    ) -> Optional[Dict[str, Any]]:
        """发送 error 事件（内部方法）"""
        return await self.events.system.emit_error(
            session_id=session_id,
            error_type=error_type,
            error_message=error_message,
            output_format=self.output_format,
            adapter=self._get_adapter()
        )
    
    async def _emit_custom(
        self,
        session_id: str,
        event_type: str,
        event_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """发送自定义事件（内部方法）"""
        return await self.events.system.emit_custom(
            session_id=session_id,
            event_type=event_type,
            event_data=event_data,
            output_format=self.output_format,
            adapter=self._get_adapter()
        )
    
    # ===========================================================================
    # 消息持久化
    # ===========================================================================
    
    async def _checkpoint_message(self, session_id: str) -> None:
        """
        Checkpoint 消息到数据库（断点恢复用）
        
        每次 content_stop 后调用，保存当前累积的内容
        状态设为 "processing"
        """
        if not self.conversation_service:
            return
        
        accumulator = self._accumulators.get(session_id)
        message_id = self._session_message_ids.get(session_id)
        
        if not accumulator or not message_id:
            return
        
        try:
            content_blocks = accumulator.build_for_db()
            if not content_blocks:
                return
            
            content_json = json.dumps(content_blocks, ensure_ascii=False)
            await self.conversation_service.update_message(
                message_id=message_id,
                content=content_json,
                status="processing"
            )
            logger.debug(f"📍 Checkpoint: message_id={message_id}, blocks={len(content_blocks)}")
        except Exception as e:
            logger.warning(f"⚠️ Checkpoint 保存失败: {str(e)}")
    
    async def _finalize_message(self, session_id: str) -> None:
        """
        最终完成消息（内部方法）
        
        在 message_stop 时调用：只更新状态为 "completed"
        
        注意：content 已在 checkpoint 保存，plan/usage 等已在 message_delta 时保存
        """
        if not self.conversation_service:
            return
        
        message_id = self._session_message_ids.get(session_id)
        if not message_id:
            return
        
        try:
            await self.conversation_service.update_message(
                message_id=message_id,
                status="completed"
            )
            logger.info(f"✅ 消息完成: message_id={message_id}")
        except Exception as e:
            logger.error(f"❌ 消息完成失败: {str(e)}", exc_info=True)
    
    async def finalize_message(self, session_id: str) -> None:
        """
        强制完成消息（公开方法）
        
        用于在 Session 被停止时强制保存当前内容。
        流程：
        1. 保存累积的 metadata（DEFERRED 策略）
        2. Checkpoint 当前累积的 content
        3. 更新状态为 completed
        
        Args:
            session_id: Session ID
        """
        # 🆕 先保存累积的 metadata（DEFERRED 策略）
        await self._flush_pending_metadata(session_id)
        
        # 保存当前累积的 content
        accumulator = self._accumulators.get(session_id)
        message_id = self._session_message_ids.get(session_id)
        
        if accumulator and message_id:
            await self._checkpoint_message(session_id)
        
        # 更新状态为 completed
        await self._finalize_message(session_id)
    
    def _cleanup_session(self, session_id: str) -> None:
        """清理 session 状态"""
        self._accumulators.pop(session_id, None)
        self._session_message_ids.pop(session_id, None)
        self._pending_metadata.pop(session_id, None)  # 🆕 清理累积的 metadata
        logger.debug(f"🧹 清理 session 状态: {session_id}")
    
    # ===========================================================================
    # 多智能体事件
    # ===========================================================================
    
    async def emit_raw_event(
        self,
        session_id: str,
        event: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        发送原始事件（多智能体场景）
        
        用于 MultiAgentOrchestrator 产生的特殊事件类型：
        - orchestrator_start: 协调器开始
        - task_decomposition: 任务分解
        - agent_start: 子 Agent 开始
        - agent_end: 子 Agent 结束
        - orchestrator_summary: 协调器总结
        - orchestrator_end: 协调器结束
        
        Args:
            session_id: Session ID
            event: 原始事件字典
            
        Returns:
            发送的事件（如果成功），否则 None
        """
        event_type = event.get("type", "unknown")
        event_data = event.get("data", {})
        
        # 通过 EventManager 发送自定义事件
        return await self.events.system.emit_custom(
            session_id=session_id,
            event_type=event_type,
            event_data=event_data,
            output_format=self.output_format,
            adapter=self._get_adapter()
        )
    


def create_broadcaster(
    event_manager,
    conversation_service: "ConversationService" = None,
    output_format: str = "zenflux",
    conversation_id: str = None
) -> EventBroadcaster:
    """
    创建事件广播器
    
    Args:
        event_manager: EventManager 实例
        conversation_service: ConversationService 实例（用于持久化）
        output_format: 输出格式（zenflux/zeno），默认 zenflux
        conversation_id: 对话 ID（用于 ZenO 格式）
        
    Returns:
        EventBroadcaster 实例
    """
    return EventBroadcaster(
        event_manager=event_manager,
        conversation_service=conversation_service,
        output_format=output_format,
        conversation_id=conversation_id
    )

