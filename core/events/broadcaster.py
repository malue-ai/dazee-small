"""
事件广播器 - EventBroadcaster

职责：
1. Agent 发送事件的统一入口
2. 事件增强（特殊工具的 message_delta）
3. 缓存 tool_id -> tool_name 映射
4. 🆕 内容累积（管理 ContentAccumulator）
5. 🆕 消息持久化（checkpoint + 最终保存）

架构：
    SimpleAgent → EventBroadcaster → EventManager → Redis
                  ↑ 累积/持久化      ↑ 纯发送
                  ↓
                  ConversationService → Database

为什么需要 Broadcaster？
=======================

EventManager 是纯粹的事件发送层，而 Broadcaster 提供：
1. 统一入口 - Agent 只需要知道 Broadcaster
2. 增强逻辑 - 特殊工具（plan_todo, web_search）自动发送额外的 message_delta
3. 状态缓存 - 缓存 tool_id -> tool_name，用于 tool_result 时查找工具名
4. 内容累积 - 每个 session 维护 ContentAccumulator，自动累积内容
5. 消息持久化 - content_stop 时 checkpoint，message_stop 时最终保存

使用示例：
    self.broadcaster = EventBroadcaster(event_manager, conversation_service)
    
    # 开始消息（关联 message_id）
    await self.broadcaster.start_message(session_id, message_id)
    
    # Content 事件（自动累积 + checkpoint）
    await self.broadcaster.emit_content_start(session_id, index, content_block)
    await self.broadcaster.emit_content_delta(session_id, index, delta)
    await self.broadcaster.emit_content_stop(session_id, index)  # ← 自动 checkpoint
    
    # 结束消息（自动最终保存）
    await self.broadcaster.emit_message_stop(session_id)  # ← 自动保存完整消息
"""

import json
from typing import Dict, Any, Optional, Set, TYPE_CHECKING
from logger import get_logger

# 避免循环导入
if TYPE_CHECKING:
    from services.conversation_service import ConversationService

from core.context.runtime import ContentAccumulator

logger = get_logger("events.broadcaster")


# ==================== 工具 → Delta 类型映射 ====================

# 需要发送特殊 message_delta 的工具
# key: 工具名, value: delta.type（前端根据这个渲染对应 UI）
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


class EventBroadcaster:
    """
    事件广播器
    
    将 Agent 产生的事件转发到 EventManager，同时管理内容累积和持久化
    
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
    
    注意：Tool 事件统一通过 Content 级事件发送
    - tool_use → content_start (type: tool_use)
    - tool_result → content_start (type: tool_result)
    
    🆕 内容累积和持久化：
    - 每个 session 维护独立的 ContentAccumulator
    - content_stop 时自动 checkpoint 到数据库
    - message_stop 时自动保存完整消息
    """
    
    def __init__(
        self,
        event_manager,
        conversation_service: "ConversationService" = None,
        event_dispatcher=None
    ):
        """
        初始化广播器
        
        Args:
            event_manager: EventManager 实例
            conversation_service: ConversationService 实例（用于持久化）
            event_dispatcher: EventDispatcher 实例（用于外部适配器，可选）
        """
        self.events = event_manager
        self.conversation_service = conversation_service
        self.dispatcher = event_dispatcher  # 🆕 外部事件分发器
        
        # tool_id -> tool_name 缓存（用于 tool_result 时查找工具名）
        self._tool_id_to_name: Dict[str, str] = {}
        
        # 🆕 session_id -> ContentAccumulator 映射
        self._accumulators: Dict[str, ContentAccumulator] = {}
        
        # 🆕 session_id -> message_id 映射（用于持久化）
        self._session_message_ids: Dict[str, str] = {}
        
        # 需要广播的事件类型（可配置）
        self._broadcast_types: Set[str] = {
            # Content 级（核心 3 个，包括 tool_use/tool_result）
            "content_start",
            "content_delta", 
            "content_stop",
            # Message 级
            "message_start",
            "message_delta",
            "message_stop",
            # Conversation 级
            "conversation_start",
            "conversation_delta",
            "conversation_stop",
            # System
            "error",
        }
    
    async def broadcast(
        self,
        session_id: str,
        event: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        广播单个事件
        
        Args:
            session_id: Session ID
            event: 原始事件
            
        Returns:
            发送的事件（如果广播了），否则 None
        """
        # 路由到对应的 emit 方法
        try:
            result = await self._route_event(session_id, event)
            
            # 🆕 分发到外部适配器（异步，不阻塞）
            if result and self.dispatcher:
                await self.dispatcher.dispatch(
                    session_id,
                    result,
                    to_internal=False,  # 内部广播已由 _route_event 完成
                    to_external=True
                )
            
            return result
        except Exception as e:
            logger.error(f"❌ 广播事件失败: {event.get('type', 'unknown')}, error={str(e)}")
            return None
    
    async def _route_event(
        self,
        session_id: str,
        event: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        路由事件到对应的 EventManager 方法
        
        Args:
            session_id: Session ID
            event: 事件对象
            
        Returns:
            发送的事件或 None
        """
        event_type = event.get("type", "")
        data = event.get("data", {})
        
        # Content 级事件（使用统一的 emit 方法，会自动处理特殊工具）
        if event_type == "content_start":
            content_block = data.get("content_block", {})
            index = data.get("index", 0)
            return await self.emit_content_start(session_id, index, content_block)
        
        elif event_type == "content_delta":
            delta = data.get("delta", {})
            index = data.get("index", 0)
            return await self.emit_content_delta(session_id, index, delta)
        
        elif event_type == "content_stop":
            index = data.get("index", 0)
            return await self.emit_content_stop(session_id, index)
        
        # Message 级事件
        elif event_type == "message_start":
            message = data.get("message", {})
            return await self.events.message.emit_message_start(
                session_id=session_id,
                message_id=message.get("id", ""),
                model=message.get("model", "")
            )
        
        elif event_type == "message_delta":
            return await self.events.message.emit_message_delta(
                session_id=session_id,
                delta=data.get("delta", data),  # 兼容新旧格式
                message_id=data.get("message_id")
            )
        
        elif event_type == "message_stop":
            return await self.events.message.emit_message_stop(
                session_id=session_id
            )
        
        # Conversation 级事件
        elif event_type == "conversation_start":
            return await self.events.conversation.emit_conversation_start(
                session_id=session_id,
                conversation=data
            )
        
        elif event_type == "conversation_delta":
            conversation_id = data.get("conversation_id", "")
            delta = data.get("delta", {})
            return await self.events.conversation.emit_conversation_delta(
                session_id=session_id,
                conversation_id=conversation_id,
                delta=delta
            )
        
        # Error 事件
        elif event_type == "error":
            return await self.events.system.emit_error(
                session_id=session_id,
                error_type=data.get("error_type", "unknown"),
                error_message=data.get("error_message", "")
            )
        
        # 其他事件：使用通用方法
        else:
            logger.debug(f"📤 广播通用事件: {event_type}")
            return await self.events.emit_custom(
                session_id=session_id,
                event_type=event_type,
                event_data=data
            )
    
    
    # ==================== 消息生命周期管理 ====================
    
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
    
    # ==================== 便捷发送方法（SimpleAgent 直接调用）====================
    
    async def emit_content_start(
        self,
        session_id: str,
        index: int,
        content_block: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        发送 content_start 事件（统一入口）
        
        会自动处理：
        - tool_use: 记录 tool_id -> tool_name 映射
        - tool_result: 发送特殊工具的 message_delta
        - 🆕 自动累积到 ContentAccumulator
        """
        # 记录 tool_use 的工具名
        if content_block.get("type") == "tool_use":
            tool_id = content_block.get("id", "")
            tool_name = content_block.get("name", "")
            if tool_id and tool_name:
                self._tool_id_to_name[tool_id] = tool_name
        
        # 🆕 累积内容
        accumulator = self._accumulators.get(session_id)
        if accumulator:
            accumulator.on_content_start(content_block)
        
        # 发送 content_start
        result = await self.events.content.emit_content_start(
            session_id=session_id,
            index=index,
            content_block=content_block
        )
        
        # tool_result 时额外发送特殊工具的 message_delta
        if content_block.get("type") == "tool_result":
            await self._emit_special_tool_delta(session_id, content_block)
        
        return result
    
    async def emit_content_delta(
        self,
        session_id: str,
        index: int,
        delta: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        发送 content_delta 事件
        
        🆕 自动累积到 ContentAccumulator
        """
        # 🆕 累积内容
        accumulator = self._accumulators.get(session_id)
        if accumulator:
            accumulator.on_content_delta(delta)
        
        return await self.events.content.emit_content_delta(
            session_id=session_id,
            index=index,
            delta=delta
        )
    
    async def emit_content_stop(
        self,
        session_id: str,
        index: int,
        signature: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        发送 content_stop 事件
        
        🆕 自动：
        1. 累积到 ContentAccumulator
        2. Checkpoint 到数据库（断点恢复）
        """
        # 🆕 累积内容（完成当前 block）
        accumulator = self._accumulators.get(session_id)
        if accumulator:
            accumulator.on_content_stop(signature)
        
        # 发送事件
        result = await self.events.content.emit_content_stop(
            session_id=session_id,
            index=index
        )
        
        # 🆕 Checkpoint 到数据库
        await self._checkpoint_message(session_id)
        
        return result
    
    async def emit_message_start(
        self,
        session_id: str,
        message_id: str,
        model: str
    ) -> Dict[str, Any]:
        """发送 message_start 事件"""
        return await self.events.message.emit_message_start(
            session_id=session_id,
            message_id=message_id,
            model=model
        )
    
    async def emit_message_delta(
        self,
        session_id: str,
        delta: Dict[str, Any],
        message_id: str = None
    ) -> Dict[str, Any]:
        """发送 message_delta 事件"""
        return await self.events.message.emit_message_delta(
            session_id=session_id,
            delta=delta,
            message_id=message_id
        )
    
    async def emit_message_stop(
        self,
        session_id: str,
        message_id: str = None
    ) -> Dict[str, Any]:
        """
        发送 message_stop 事件
        
        🆕 自动：
        1. 最终保存完整消息到数据库
        2. 清理 session 状态
        """
        # 🆕 最终保存完整消息
        await self._finalize_message(session_id)
        
        # 发送事件
        result = await self.events.message.emit_message_stop(
            session_id=session_id,
            message_id=message_id
        )
        
        # 🆕 清理 session 状态
        self._cleanup_session(session_id)
        
        return result
    
    # ==================== Conversation 快捷方法 ====================
    
    async def emit_conversation_title(
        self,
        session_id: str,
        conversation_id: str,
        title: str
    ) -> Dict[str, Any]:
        """发送标题更新（后台生成标题时使用）"""
        return await self.events.conversation.emit_conversation_delta(
            session_id=session_id,
            conversation_id=conversation_id,
            delta={"title": title}
        )
    
    # ==================== 内部方法 ====================
    
    async def _emit_special_tool_delta(
        self,
        session_id: str,
        tool_result_block: Dict[str, Any]
    ) -> None:
        """
        为特殊工具发送 message_delta（内部方法）
        
        根据 tool_use_id 查找工具名，检查是否需要发送特殊 delta
        """
        tool_use_id = tool_result_block.get("tool_use_id", "")
        is_error = tool_result_block.get("is_error", False)
        result_content = tool_result_block.get("content", "")
        
        # 查找工具名
        tool_name = self._tool_id_to_name.get(tool_use_id, "")
        
        # 检查是否需要发送特殊 delta
        delta_type = TOOL_TO_DELTA_TYPE.get(tool_name)
        
        if delta_type and not is_error:
            logger.debug(f"🔧 发送特殊工具 delta: type={delta_type}, tool={tool_name}")
            
            # 🆕 直接保存到数据库 metadata（增量合并）
            await self._save_delta_to_metadata(session_id, delta_type, result_content)
            
            # 发送 SSE 事件给前端
            await self.events.message.emit_message_delta(
                session_id=session_id,
                delta={
                    "type": delta_type,
                    "content": result_content
                }
            )
        
        # 清理缓存
        self._tool_id_to_name.pop(tool_use_id, None)
    
    async def _save_delta_to_metadata(
        self,
        session_id: str,
        delta_type: str,
        content: Any
    ) -> None:
        """
        直接保存 delta 到数据库 metadata（增量合并）
        
        Args:
            session_id: Session ID
            delta_type: delta 类型（plan/search/knowledge/ppt 等）
            content: delta 内容
        """
        if not self.conversation_service:
            return
        
        message_id = self._session_message_ids.get(session_id)
        if not message_id:
            return
        
        # 解析 content（可能是 JSON 字符串）
        parsed_content = content
        if isinstance(content, str):
            try:
                parsed_content = json.loads(content)
            except json.JSONDecodeError:
                pass
        
        try:
            # 直接更新数据库（update_message 会增量合并 metadata）
            await self.conversation_service.update_message(
                message_id=message_id,
                metadata={delta_type: parsed_content}
            )
            logger.debug(f"📦 保存 metadata: message_id={message_id}, type={delta_type}")
        except Exception as e:
            logger.warning(f"⚠️ 保存 metadata 失败: {str(e)}")
    
    # ==================== 消息持久化（内部方法）====================
    
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
        最终完成消息
        
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
    
    def _cleanup_session(self, session_id: str) -> None:
        """清理 session 状态"""
        self._accumulators.pop(session_id, None)
        self._session_message_ids.pop(session_id, None)
        logger.debug(f"🧹 清理 session 状态: {session_id}")
    
    # ==================== HITL 事件 ====================
    
    async def emit_confirmation_request(
        self,
        session_id: str,
        request_id: str,
        question: str,
        options: list = None,
        confirmation_type: str = "yes_no",
        timeout: int = 60,
        description: str = "",
        questions: list = None,
        metadata: dict = None
    ) -> Dict[str, Any]:
        """
        发送人类确认请求事件（HITL）
        
        通过 message_delta 发送，delta.type = "confirmation_request"
        前端收到此事件后应显示确认对话框，用户响应后通过 HTTP POST 提交。
        
        Args:
            session_id: 会话ID
            request_id: 确认请求ID（用于匹配响应）
            question: 问题内容
            options: 选项列表
            confirmation_type: 确认类型（yes_no, single_choice, multiple_choice, text_input, form）
            timeout: 超时时间（秒）
            description: 补充描述
            questions: 问题列表（form 类型）
            metadata: 额外元数据
            
        Returns:
            发送的事件
        """
        import json
        
        # 构建 HITL 请求内容
        hitl_content = {
            "request_id": request_id,
            "question": question,
            "options": options or ["confirm", "cancel"],
            "confirmation_type": confirmation_type,
            "timeout": timeout,
            "description": description,
            "questions": questions,
            "metadata": metadata or {}
        }
        
        # 通过 message_delta 发送，符合事件协议规范
        delta = {
            "type": "confirmation_request",
            "content": json.dumps(hitl_content, ensure_ascii=False)
        }
        
        event = await self.emit_message_delta(session_id, delta)
        logger.info(f"🤝 发送 HITL 请求: request_id={request_id}, type={confirmation_type}")
        
        return event
    
    # ==================== 配置管理 ====================
    
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
    event_dispatcher=None
) -> EventBroadcaster:
    """
    创建事件广播器
    
    Args:
        event_manager: EventManager 实例
        conversation_service: ConversationService 实例（用于持久化）
        event_dispatcher: EventDispatcher 实例（用于外部适配器，可选）
        
    Returns:
        EventBroadcaster 实例
    """
    return EventBroadcaster(event_manager, conversation_service, event_dispatcher)

