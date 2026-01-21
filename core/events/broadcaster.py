"""
事件广播器 - EventBroadcaster

职责：
1. Agent 发送事件的统一入口
2. 缓存 tool_id -> tool_name 映射
3. 内容累积（管理 ContentAccumulator）
4. 消息持久化（checkpoint + 最终保存）
5. 【仅 ZenO 格式】事件增强（特殊工具的 message_delta）

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
- Broadcaster 只负责内部逻辑（累积、增强、持久化）

输出格式差异：
- zenflux（默认）：保持原始事件结构，tool_result 不做拆分
- zeno：tool_result 会被拆分为多个 message_delta（sql/data/chart/intent 等）
        这是 ZenO 前端规范特有的业务语义增强

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


# ===========================================================================
# ZenO 特有配置（仅 output_format == "zeno" 时使用）
# ===========================================================================

# 工具 → Delta 类型映射
# 需要发送特殊 message_delta 的工具
# key: 工具名, value: delta.type（ZenO 前端根据这个渲染对应 UI）
TOOL_TO_DELTA_TYPE: Dict[str, str] = {
    # Plan 相关
    "plan_todo": "plan",
    
    # 搜索类
    "web_search": "search",
    "knowledge_search": "knowledge",
    
    # PPT 生成
    "slidespeak_generate": "ppt",
    
    # 代码执行（可选，看前端是否需要特殊 UI）
    # "bash": "code",
    # "e2b_python_sandbox": "code",
}

# 问数平台工具 → 多个 Delta 类型映射
# 返回结果的字段名直接映射为 delta.type
WENSHU_ANALYTICS_DELTA_FIELDS = {
    "sql": "sql",          # SQL 查询语句
    "data": "data",        # 查询结果数据
    "chart": "chart",      # 图表配置
    "report": "report",    # 分析报告
    "intent": "intent",    # 意图识别（可选）
}

# 🆕 需要拆分响应的分析类 API（通过 api_name 识别）
# 当 api_calling 工具使用这些 api_name 时，自动拆分响应为多个 delta 事件
ANALYTICS_API_NAMES = {
    "wenshu_api",      # 问数平台 API
    "wenshu",          # 简写形式
}

# 🆕 系统搭建类 API（Ontology Builder 等）
# 返回 interface 类型：系统配置（实体、属性、关系）
ONTOLOGY_API_NAMES = {
    "coze_api",        # Coze Ontology Builder 工作流
    "coze",            # 简写形式
}

# 🆕 流程图生成类 API（text2flowchart 等）
# 返回 mind 类型：Mermaid 图表（流程图/思维导图）
FLOWCHART_API_NAMES = {
    "dify_api",        # Dify text2flowchart 工作流
    "dify",            # 简写形式
}


class EventBroadcaster:
    """
    事件广播器
    
    将 Agent 产生的事件通过 EventManager 发送，同时管理内容累积和持久化
    
    核心职责：
    - 内容累积（ContentAccumulator）
    - 事件增强（特殊工具的 message_delta）
    - 消息持久化（checkpoint + 最终保存）
    
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
        - tool_result: 发送特殊工具的 message_delta
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
        
        # 🆕 仅 ZenO 格式：tool_result 时额外发送特殊工具的 message_delta
        # 这些 delta（sql/data/chart/intent 等）是 ZenO 规范特有的业务语义增强
        # Zenflux 原生格式保持 tool_result 的原始结构，不做拆分
        if self.output_format == "zeno" and content_block.get("type") == "tool_result":
            await self._emit_special_tool_delta(session_id, content_block)
        
        return result
    
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
    # 特殊工具处理（仅 ZenO 格式）
    # 
    # 这些方法将 tool_result 拆分为多个 message_delta 事件：
    # - sql/data/chart/report：智能分析场景（问数平台）
    # - intent：意图识别
    # - interface：系统配置（Ontology Builder）
    # - mind：Mermaid 图表（流程图）
    # 
    # 只有 output_format == "zeno" 时才会触发，
    # Zenflux 原生格式保持 tool_result 的原始结构。
    # ===========================================================================
    
    def _is_analytics_api(self, tool_use_id: str) -> bool:
        """
        判断是否是分析类 API（通过 api_name 识别）
        
        Args:
            tool_use_id: 工具调用 ID
            
        Returns:
            是否是分析类 API（如问数平台）
        """
        tool_input = self._tool_id_to_input.get(tool_use_id, {})
        api_name = tool_input.get("api_name", "")
        
        if api_name and api_name in ANALYTICS_API_NAMES:
            logger.debug(f"🔍 识别到分析类 API: api_name={api_name}")
            return True
    
    def _is_ontology_api(self, tool_use_id: str) -> bool:
        """
        判断是否是系统搭建类 API（Ontology Builder）
        
        Args:
            tool_use_id: 工具调用 ID
            
        Returns:
            是否是系统搭建类 API（返回 interface）
        """
        tool_input = self._tool_id_to_input.get(tool_use_id, {})
        api_name = tool_input.get("api_name", "")
        
        if api_name and api_name in ONTOLOGY_API_NAMES:
            logger.debug(f"🔍 识别到系统搭建类 API: api_name={api_name}")
            return True
        return False
    
    def _is_flowchart_api(self, tool_use_id: str) -> bool:
        """
        判断是否是流程图生成类 API（text2flowchart）
        
        Args:
            tool_use_id: 工具调用 ID
            
        Returns:
            是否是流程图生成类 API（返回 mind）
        """
        tool_input = self._tool_id_to_input.get(tool_use_id, {})
        api_name = tool_input.get("api_name", "")
        
        if api_name and api_name in FLOWCHART_API_NAMES:
            logger.debug(f"🔍 识别到流程图生成类 API: api_name={api_name}")
            return True
        return False
    
    async def _emit_special_tool_delta(
        self,
        session_id: str,
        tool_result_block: Dict[str, Any]
    ) -> None:
        """
        为特殊工具发送 message_delta（内部方法）
        
        根据 tool_use_id 查找工具名，检查是否需要发送特殊 delta
        
        支持的 api_calling 工具处理：
        1. wenshu_api → 拆分为 sql/data/chart/report/intent 等（智能分析）
        2. coze_api → 转换为 interface（系统配置，Ontology Builder）
        3. dify_api → 转换为 mind（Mermaid 流程图，text2flowchart）
        
        向后兼容：
        - tool_name == "wenshu_analytics"（专用工具，将废弃）
        """
        tool_use_id = tool_result_block.get("tool_use_id", "")
        is_error = tool_result_block.get("is_error", False)
        result_content = tool_result_block.get("content", "")
        
        # 查找工具名
        tool_name = self._tool_id_to_name.get(tool_use_id, "")
        
        # 🆕 api_calling 工具的特殊处理（通过 api_name 识别）
        if tool_name == "api_calling" and not is_error:
            # 1. 问数平台 API → 拆分为 sql/data/chart/report 等
            if self._is_analytics_api(tool_use_id):
                await self._emit_analytics_deltas(session_id, result_content)
                self._cleanup_tool_cache(tool_use_id)
                return
            
            # 2. 系统搭建类 API（Coze Ontology Builder）→ interface
            if self._is_ontology_api(tool_use_id):
                await self._emit_ontology_deltas(session_id, result_content)
                self._cleanup_tool_cache(tool_use_id)
                return
            
            # 3. 流程图生成类 API（Dify text2flowchart）→ mind
            if self._is_flowchart_api(tool_use_id):
                await self._emit_flowchart_deltas(session_id, result_content)
                self._cleanup_tool_cache(tool_use_id)
                return
        
        # 🆕 向后兼容：专用工具 wenshu_analytics（将废弃）
        if tool_name == "wenshu_analytics" and not is_error:
            await self._emit_analytics_deltas(session_id, result_content)
            self._cleanup_tool_cache(tool_use_id)
            return
        
        # 检查是否需要发送特殊 delta
        delta_type = TOOL_TO_DELTA_TYPE.get(tool_name)
        
        if delta_type and not is_error:
            logger.debug(f"🔧 发送特殊工具 delta: type={delta_type}, tool={tool_name}")
            
            # 统一使用 emit_message_delta（自动发送 + 保存到 metadata）
            await self.emit_message_delta(
                session_id=session_id,
                delta={
                    "type": delta_type,
                    "content": result_content
                }
            )
        
        # 清理缓存
        self._cleanup_tool_cache(tool_use_id)
    
    def _cleanup_tool_cache(self, tool_use_id: str) -> None:
        """清理工具相关的缓存"""
        self._tool_id_to_name.pop(tool_use_id, None)
        self._tool_id_to_input.pop(tool_use_id, None)
    
    async def _emit_analytics_deltas(
        self,
        session_id: str,
        result_content: str
    ) -> None:
        """
        为分析类 API（如问数平台）发送多个 delta 事件
        
        分析类 API 返回的结果包含多个字段，每个字段对应一个 delta 事件：
        - sql: SQL 查询语句
        - data: 查询结果数据
        - chart: 图表配置
        - report: 分析报告 {title, content}
        - intent_name: 意图名称
        
        Args:
            session_id: Session ID
            result_content: 工具返回的 JSON 字符串
        """
        # 解析结果
        try:
            if isinstance(result_content, str):
                result = json.loads(result_content)
            else:
                result = result_content
        except json.JSONDecodeError:
            logger.warning(f"⚠️ 分析类 API 结果解析失败: {str(result_content)[:100]}...")
            return
        
        # 检查是否成功
        if not result.get("success", False):
            logger.warning(f"⚠️ 分析类 API 返回失败: {result.get('error')}")
            return
        
        logger.info(f"📊 分析类 API 结果处理: intent={result.get('intent_name')}")
        
        # 发送 intent delta（智能分析场景）
        intent_name = result.get("intent_name")
        if intent_name:
            intent_data = {
                "intent_id": result.get("intent", 2),  # 默认 2 = 智能分析
                "intent_name": intent_name,
                "platform": "analytics"  # 分析类 API 都是 analytics 场景
            }
            await self._emit_single_delta(session_id, "intent", intent_data)
        
        # 发送 sql delta
        sql = result.get("sql")
        if sql:
            await self._emit_single_delta(session_id, "sql", sql)
        
        # 发送 data delta
        data = result.get("data")
        if data:
            await self._emit_single_delta(session_id, "data", data)
        
        # 发送 chart delta
        chart = result.get("chart")
        if chart:
            await self._emit_single_delta(session_id, "chart", chart)
        
        # 发送 report delta
        report = result.get("report")
        if report:
            await self._emit_single_delta(session_id, "report", report)
        
        # 发送 application delta（可选，包含 dashboard_id 等）
        dashboard_id = result.get("dashboard_id")
        if dashboard_id:
            app_data = {
                "application_id": dashboard_id,
                "name": "数据分析",
                "status": "success"
            }
            await self._emit_single_delta(session_id, "application", app_data)
    
    async def _emit_ontology_deltas(
        self,
        session_id: str,
        result_content: str
    ) -> None:
        """
        为系统搭建类 API（Coze Ontology Builder）发送 delta 事件
        
        Coze SSE 返回格式（解析后）：
        - 最终结果通常在最后一个 Message 事件的 content 中
        - 包含系统配置（实体、属性、关系）
        
        发送的 delta 类型：
        - interface: 系统配置（实体、属性、关系）
        - application: 应用状态（可选）
        
        Args:
            session_id: Session ID
            result_content: 工具返回的内容（可能是 JSON 或原始 SSE）
        """
        # 解析结果
        parsed_result = self._parse_coze_sse_result(result_content)
        
        if not parsed_result:
            logger.warning(f"⚠️ Coze API 结果解析失败: {str(result_content)[:200]}...")
            return
        
        logger.info(f"🏗️ Ontology Builder 结果处理")
        
        # 发送 intent delta（系统搭建场景）
        intent_data = {
            "intent_id": 1,  # 1 = 系统搭建
            "intent_name": "系统搭建",
            "platform": "ontology"
        }
        await self._emit_single_delta(session_id, "intent", intent_data)
        
        # 发送 interface delta（系统配置）
        # parsed_result 可能是配置对象或包含配置的结构
        interface_data = parsed_result
        
        # 如果结果嵌套在特定字段中，尝试提取
        if isinstance(parsed_result, dict):
            interface_data = (
                parsed_result.get("config") or
                parsed_result.get("ontology") or
                parsed_result.get("entities") or
                parsed_result.get("result") or
                parsed_result
            )
        
        await self._emit_single_delta(session_id, "interface", interface_data)
        
        # 发送 application delta（构建状态）
        app_data = {
            "application_id": f"ontology_{session_id}",
            "name": "系统配置",
            "status": "success"
        }
        await self._emit_single_delta(session_id, "application", app_data)
    
    async def _emit_flowchart_deltas(
        self,
        session_id: str,
        result_content: str
    ) -> None:
        """
        为流程图生成类 API（Dify text2flowchart）发送 delta 事件
        
        Dify 返回格式：
        {
            "workflow_run_id": "xxx",
            "data": {
                "outputs": {
                    "text": "```mermaid\\nflowchart TD\\n  ...\\n```"
                }
            }
        }
        
        发送的 delta 类型：
        - mind: Mermaid 图表（流程图/思维导图）
        
        Args:
            session_id: Session ID
            result_content: 工具返回的 JSON 字符串
        """
        # 解析结果
        try:
            if isinstance(result_content, str):
                result = json.loads(result_content)
            else:
                result = result_content
        except json.JSONDecodeError:
            logger.warning(f"⚠️ Dify API 结果解析失败: {str(result_content)[:200]}...")
            return
        
        logger.info(f"📊 text2flowchart 结果处理")
        
        # 提取 Mermaid 内容
        mermaid_content = None
        
        # 方式1: data.outputs.text
        if isinstance(result, dict):
            data = result.get("data", {})
            outputs = data.get("outputs", {})
            mermaid_content = outputs.get("text", "")
            
            # 方式2: 直接在 result 中
            if not mermaid_content:
                mermaid_content = result.get("text", "")
            
            # 方式3: raw_content（如果是 SSE 流式返回）
            if not mermaid_content:
                raw = result.get("raw_content", "")
                if raw:
                    mermaid_content = self._extract_mermaid_from_raw(raw)
        
        if not mermaid_content:
            logger.warning(f"⚠️ 未找到 Mermaid 内容")
            return
        
        # 清理 Mermaid 代码块标记
        mermaid_content = self._clean_mermaid_content(mermaid_content)
        
        # 发送 intent delta（系统搭建场景，流程图是其一部分）
        intent_data = {
            "intent_id": 1,  # 1 = 系统搭建
            "intent_name": "系统搭建",
            "platform": "flowchart"
        }
        await self._emit_single_delta(session_id, "intent", intent_data)
        
        # 发送 mind delta（Mermaid 图表）
        mind_data = {
            "mermaid_content": mermaid_content,
            "chart_type": "flowchart"
        }
        await self._emit_single_delta(session_id, "mind", mind_data)
    
    def _parse_coze_sse_result(self, result_content: str) -> Any:
        """
        解析 Coze SSE 返回结果
        
        Coze SSE 格式：
        event: Message
        data: {"content": "...", "node_is_finish": true, ...}
        
        event: Done
        data: {"debug_url": "..."}
        
        Args:
            result_content: 原始返回内容（可能是 JSON 或 SSE 流）
            
        Returns:
            解析后的结果对象
        """
        # 尝试直接解析 JSON
        try:
            if isinstance(result_content, str):
                result = json.loads(result_content)
                
                # 如果是 raw_content 格式，需要进一步解析 SSE
                if "raw_content" in result:
                    return self._parse_coze_sse_stream(result["raw_content"])
                
                return result
            return result_content
        except json.JSONDecodeError:
            pass
        
        # 尝试解析 SSE 流
        return self._parse_coze_sse_stream(result_content)
    
    def _parse_coze_sse_stream(self, raw_content: str) -> Any:
        """
        解析 Coze SSE 流内容，提取最终结果
        
        Args:
            raw_content: 原始 SSE 流内容
            
        Returns:
            最终结果（最后一个 Message 事件的 content）
        """
        final_content = ""
        
        for line in raw_content.split("\n"):
            line = line.strip()
            
            if line.startswith("data:"):
                data_str = line[5:].strip()
                try:
                    data = json.loads(data_str)
                    content = data.get("content", "")
                    if content:
                        final_content += content
                except json.JSONDecodeError:
                    continue
        
        # 尝试将累积的内容解析为 JSON
        if final_content:
            try:
                return json.loads(final_content)
            except json.JSONDecodeError:
                return final_content
        
        return None
    
    def _extract_mermaid_from_raw(self, raw_content: str) -> str:
        """
        从原始 SSE 流中提取 Mermaid 内容
        
        Args:
            raw_content: 原始 SSE 流内容
            
        Returns:
            Mermaid 内容
        """
        import re
        
        # 尝试匹配 ```mermaid ... ```
        pattern = r'```mermaid\s*([\s\S]*?)```'
        match = re.search(pattern, raw_content)
        if match:
            return match.group(1).strip()
        
        # 尝试匹配 flowchart 或 mindmap 开头的内容
        for prefix in ['flowchart', 'mindmap', 'graph', 'sequenceDiagram']:
            if prefix in raw_content:
                # 找到 Mermaid 内容的开始位置
                start = raw_content.find(prefix)
                if start != -1:
                    # 提取到下一个 ``` 或文件结束
                    end = raw_content.find('```', start)
                    if end != -1:
                        return raw_content[start:end].strip()
                    return raw_content[start:].strip()
        
        return ""
    
    def _clean_mermaid_content(self, content: str) -> str:
        """
        清理 Mermaid 代码块标记
        
        Args:
            content: 可能包含代码块标记的 Mermaid 内容
            
        Returns:
            清理后的 Mermaid 内容
        """
        content = content.strip()
        
        # 移除 ```mermaid 开头
        if content.startswith("```mermaid"):
            content = content[10:].strip()
        elif content.startswith("```"):
            content = content[3:].strip()
        
        # 移除 ``` 结尾
        if content.endswith("```"):
            content = content[:-3].strip()
        
        return content
    
    async def _emit_single_delta(
        self,
        session_id: str,
        delta_type: str,
        content: Any
    ) -> None:
        """
        发送单个 delta 事件（内部方法）
        
        Args:
            session_id: Session ID
            delta_type: delta 类型
            content: 内容（对象或字符串）
        """
        # 转换为 JSON 字符串（如果是对象）
        if isinstance(content, (dict, list)):
            content_str = json.dumps(content, ensure_ascii=False)
        else:
            content_str = str(content)
        
        logger.debug(f"📤 发送 delta: type={delta_type}")
        
        # 统一使用 emit_message_delta（自动发送 + 保存到 metadata）
        await self.emit_message_delta(
            session_id=session_id,
            delta={
                "type": delta_type,
                "content": content_str
            }
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
    
    # ===========================================================================
    # 配置管理
    # ===========================================================================
    
    @staticmethod
    def register_tool_delta_type(tool_name: str, delta_type: str) -> None:
        """
        注册工具的 delta 类型（动态添加）
        
        Args:
            tool_name: 工具名
            delta_type: delta.type（前端根据这个渲染 UI）
        """
        TOOL_TO_DELTA_TYPE[tool_name] = delta_type
        logger.info(f"✅ 注册工具 delta: {tool_name} -> {delta_type}")


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

