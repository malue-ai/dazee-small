"""
事件广播器 - EventBroadcaster

职责：
1. Agent 发送事件的统一入口
2. 事件增强（特殊工具的 message_delta）
3. 缓存 tool_id -> tool_name 映射
4. 内容累积（管理 ContentAccumulator）
5. 消息持久化（checkpoint + 最终保存）

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
from typing import Dict, Any, Optional, Set, TYPE_CHECKING
from uuid import uuid4
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
        conversation_id: str = None
    ):
        """
        初始化广播器
        
        Args:
            event_manager: EventManager 实例
            conversation_service: ConversationService 实例（用于持久化）
            output_format: 输出事件格式（zeno/zenflux），默认 zenflux
            conversation_id: 对话 ID（用于 ZenO 格式）
        """
        self.events = event_manager
        self.conversation_service = conversation_service
        
        # 输出格式配置（由 chat.py 传递）
        self.output_format = output_format
        self.output_conversation_id = conversation_id
        
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
        
        # tool_result 时额外发送特殊工具的 message_delta
        if content_block.get("type") == "tool_result":
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
        2. Checkpoint 到数据库（断点恢复）
        
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
        
        # Checkpoint 到数据库
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
        message_id: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        发送 message_delta 事件
        
        Args:
            session_id: Session ID
            delta: Delta 内容
            message_id: 消息 ID（可选）
            
        Returns:
            发送的事件，如果被过滤则返回 None
        """
        # 通过 EventManager 发送事件
        return await self.events.message.emit_message_delta(
            session_id=session_id,
            delta=delta,
            message_id=message_id,
            output_format=self.output_format,
            adapter=self._get_adapter()
        )
    
    async def emit_message_stop(
        self,
        session_id: str,
        message_id: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        发送 message_stop 事件
        
        自动：
        1. 最终保存完整消息到数据库
        2. 清理 session 状态
        
        Args:
            session_id: Session ID
            message_id: 消息 ID（可选）
            
        Returns:
            发送的事件，如果被过滤则返回 None
        """
        # 最终保存完整消息
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
    
    # ==================== Conversation 快捷方法 ====================
    
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
    
    # ==================== 内部事件发送方法 ====================
    
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
    
    # ==================== 特殊工具处理（内部方法）====================
    
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
            
            # 直接保存到数据库 metadata（增量合并）
            await self._save_delta_to_metadata(session_id, delta_type, result_content)
            
            # 发送 SSE 事件给前端（通过 EventManager）
            await self.events.message.emit_message_delta(
                session_id=session_id,
                delta={
                    "type": delta_type,
                    "content": result_content
                },
                output_format=self.output_format,
                adapter=self._get_adapter()
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
        发送单个 delta 事件
        
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
        
        # 保存到数据库
        await self._save_delta_to_metadata(session_id, delta_type, content)
        
        # 发送 SSE 事件（通过 EventManager）
        await self.events.message.emit_message_delta(
            session_id=session_id,
            delta={
                "type": delta_type,
                "content": content_str
            },
            output_format=self.output_format,
            adapter=self._get_adapter()
        )
    
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
        会先执行 checkpoint 保存当前累积的内容，然后更新状态为 completed。
        
        Args:
            session_id: Session ID
        """
        # 先保存当前累积的内容
        accumulator = self._accumulators.get(session_id)
        message_id = self._session_message_ids.get(session_id)
        
        if accumulator and message_id:
            await self._checkpoint_content(session_id, message_id, accumulator)
        
        # 然后完成消息
        await self._finalize_message(session_id)
    
    def _cleanup_session(self, session_id: str) -> None:
        """清理 session 状态"""
        self._accumulators.pop(session_id, None)
        self._session_message_ids.pop(session_id, None)
        logger.debug(f"🧹 清理 session 状态: {session_id}")
    
    # ==================== 多智能体事件 ====================
    
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
    
    # ==================== HITL 事件 ====================
    
    async def emit_confirmation_request(
        self,
        session_id: str,
        request_id: str,
        question: str,
        options: list = None,
        confirmation_type: str = "form",
        timeout: int = 120,
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
            confirmation_type: 输入类型（form, text_input）
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

