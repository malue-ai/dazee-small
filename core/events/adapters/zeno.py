"""
ZenO 适配器

将 Zenflux 内部事件转换为 ZenO SSE 数据规范 v2.0.1 格式

ZenO 规范特点：
1. 生命周期事件：message.assistant.created/start/done/error
2. 业务事件统一用：message.assistant.delta + delta.type
3. delta.type 包括：intent, preface, thinking, response, progress, clue, files, mind, sql, data, chart, recommended, application, billing

参考文档：ZenO 会话详情页 SSE 数据规范 v2.0.1
"""

import json
import re
import time
from typing import Dict, Any, List, Optional
from core.events.adapters.base import EventAdapter
from logger import get_logger

logger = get_logger("zeno_adapter")


# ===========================================================================
# ZenO 特有常量配置
# ===========================================================================

# 工具 → Delta 类型映射
# 需要发送特殊 message_delta 的工具
# key: 工具名, value: delta.type（ZenO 前端根据这个渲染对应 UI）
TOOL_TO_DELTA_TYPE: Dict[str, str] = {
    # Plan 相关：plan_todo 需要特殊处理（转换为 progress 格式），不在此映射
    
    # 搜索类
    "web_search": "search",
    "knowledge_search": "knowledge",
    
    # PPT 生成
    "slidespeak_generate": "ppt",
    
    # 沙盒工具 - 获取公开 URL 时生成 sandbox delta
    "sandbox_get_public_url": "sandbox",
}

# 问数平台工具 → 多个 Delta 类型映射
# 返回结果的字段名直接映射为 delta.type
WENSHU_ANALYTICS_DELTA_FIELDS = {
    "sql": "sql",          # SQL 查询语句
    "data": "data",        # 查询结果数据
    "chart": "chart",      # 图表配置
    "report": "report",    # 分析报告
}

# 需要拆分响应的分析类 API（通过 api_name 识别）
# 当 api_calling 工具使用这些 api_name 时，自动拆分响应为多个 delta 事件
ANALYTICS_API_NAMES = {
    "wenshu_api",      # 问数平台 API
    "wenshu",          # 简写形式
}

# 系统搭建类 API（Ontology Builder 等）
# 返回 interface 类型：系统配置（实体、属性、关系）
ONTOLOGY_API_NAMES = {
    "coze_api",        # Coze Ontology Builder 工作流
    "coze",            # 简写形式
}

# 🆕 V7.8: 流程图生成已改用 MCP 工具，不再通过 api_calling
# FLOWCHART_API_NAMES 已废弃，保留注释说明历史
# 原配置：{"dify_api", "dify"}

# MCP 工具名模式：用于识别流程图生成类 MCP 工具
# 这些工具直接通过 MCP 调用，不经过 api_calling
# 命名格式：(mcp_)dify_Ontology_TextToChart_xxx
MCP_FLOWCHART_TOOL_PATTERNS = {
    "dify_Ontology_TextToChart",  # Dify 流程图生成工具
    "TextToChart",                # 简写模式
}


class ZenOAdapter(EventAdapter):
    """
    ZenO 事件适配器
    
    将 Zenflux 5 层事件架构转换为 ZenO SSE 规范
    
    映射关系：
    - message_start → message.assistant.created + message.assistant.start
    - content_delta (thinking) → message.assistant.delta (type: thinking)
    - content_delta (text) → message.assistant.delta (type: response)
    - message_delta (preface) → message.assistant.delta (type: preface)  # V7.8: 由 chat_service 独立发送
    - tool_result:plan_todo → message.assistant.delta (type: progress)  # 通过 enhance_tool_result 处理
    - tool_result:hitl → message.assistant.delta (type: hitl_data)  # 支持 pending/completed/timeout/failed 状态
    - tool_result:clue_generation → message.assistant.delta (type: clue)
    - message_delta:recommended → message.assistant.delta (type: recommended)
    - message_stop → message.assistant.done
    - error → message.assistant.error
    """
    
    name = "zeno"
    
    # 支持转换的事件类型
    supported_events = [
        "message_start",
        "message_stop",
        "content_start",
        "content_delta",
        "content_stop",
        "message_delta",
        "error",
        "session_end",
        "session_stopped",
    ]
    
    def __init__(self, conversation_id: Optional[str] = None):
        """
        初始化 ZenO 适配器
        
        Args:
            conversation_id: 对话 ID（可选，用于填充字段）
        """
        self.conversation_id = conversation_id
        # 缓存 message_id，用于后续事件
        self._current_message_id: Optional[str] = None
        # 缓存累积的内容
        self._accumulated_content: str = ""
        # 缓存当前 content block 类型（用于简化 delta 格式适配）
        self._current_block_type: Optional[str] = None
        # 标记是否已经有过 text 块（用于判断是否需要添加换行分隔符）
        self._has_text_started: bool = False
    
    def transform(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        转换为 ZenO 格式
        
        注意：seq 由 EventDispatcher 统一管理，这里不处理 seq
        
        Returns:
            ZenO 格式事件，或 None（如果不需要发送）
        """
        event_type = event.get("type", "")
        data = event.get("data", {})
        session_id = event.get("session_id", "")
        conversation_id = event.get("conversation_id") or self.conversation_id or ""
        
        # 获取 message_id：优先从事件顶层，其次从 data，再从 message.id（message_start 事件），最后用缓存
        message_id = event.get("message_id")
        timestamp = int(time.time() * 1000)  # 毫秒时间戳
        
        # 🆕 入口日志：记录收到的事件类型
        logger.debug(
            f"[transform] 收到事件: type={event_type}, "
            f"session={session_id[:8] if session_id else 'N/A'}, "
            f"current_block_type={self._current_block_type}"
        )
        
        # 更新 message_id 缓存
        if message_id:
            self._current_message_id = message_id
        
        # 根据事件类型转换（不传 seq，由 EventDispatcher 统一添加）
        if event_type == "message_start":
            return self._transform_message_start(message_id, conversation_id, timestamp, session_id)
        
        # 处理 content_start：记录当前 block 类型
        if event_type == "content_start":
            content_block = data.get("content_block", {})
            block_type = content_block.get("type")
            
            # 🆕 详细日志：记录 content_block 的类型和结构
            logger.debug(
                f"[content_start] block_type={block_type}, "
                f"content_block_keys={list(content_block.keys())}, "
                f"index={data.get('index')}"
            )
            
            # 用于标记是否需要发送换行符事件
            should_send_newline = False
            
            # 🆕 简化逻辑：只要收到 content_start 且 type=text 且不是第一个 text 块，就加换行
            # 这样多轮 text 内容（比如工具调用后的回复）之间会有清晰的分隔
            # 🆕 V7.8: Preface 已移至 chat_service 独立阶段，此处所有 text 块统一使用 response 类型
            if block_type == "text":
                if self._has_text_started:
                    self._accumulated_content += "\n\n"
                    # 🔧 标记需要发送换行符事件
                    should_send_newline = True
                    logger.debug(
                        f"[content_start] 新 text 块，添加换行分隔符，"
                        f"accumulated_len={len(self._accumulated_content)}"
                    )
                else:
                    self._has_text_started = True
                    logger.debug("[content_start] 首个 text 块开始")
            
            self._current_block_type = block_type
            
            # 🔧 如果需要发送换行符，返回一个 delta 事件
            if should_send_newline:
                logger.debug("[content_start] 发送换行符 delta 事件")
                return {
                    "type": "message.assistant.delta",
                    "message_id": message_id,
                    "session_id": session_id,
                    "timestamp": timestamp,
                    "delta": {
                        "type": "response",
                        "content": "\n\n"
                    }
                    # seq 由 EventDispatcher 统一添加
                }
            
            return None  # 其他情况 content_start 不需要转换为 ZenO 事件
        
        if event_type == "content_delta":
            # 🆕 日志：记录当前 block 类型和 delta 预览
            delta_preview = str(data.get("delta", ""))[:50]
            logger.debug(
                f"[content_delta] _current_block_type={self._current_block_type}, "
                f"index={data.get('index')}, "
                f"delta_preview={delta_preview}"
            )
            return self._transform_content_delta(event, message_id, timestamp, session_id)
        
        if event_type == "message_delta":
            return self._transform_message_delta(event, message_id, timestamp, session_id)
        
        if event_type == "message_stop":
            return self._transform_message_stop(message_id, timestamp, session_id)
        
        if event_type == "error":
            return self._transform_error(event, message_id, timestamp, session_id)
        
        # 🆕 修复：处理 session_end 事件（支持列表中声明了但之前没有处理）
        if event_type == "session_end":
            return self._transform_session_end(event, message_id, timestamp)
        
        # 🆕 用户主动停止事件
        if event_type == "session_stopped":
            return self._transform_session_stopped(event, session_id, timestamp)
        
        # 🆕 心跳事件：直接透传，保持连接活跃
        if event_type == "ping":
            return {
                "type": "ping",
                "timestamp": event.get("timestamp", int(time.time() * 1000)),
                "session_id": session_id
            }
        
        # 其他事件暂不转换
        return None
    
    def _transform_message_start(
        self,
        message_id: str,
        conversation_id: str,
        timestamp: int,
        session_id: str = ""
    ) -> Dict[str, Any]:
        """
        转换 message_start → message.assistant.start
        
        注意：ZenO 有 created 和 start 两个事件，这里合并为 start
        seq 由 EventDispatcher 统一添加
        """
        # 重置状态
        self._accumulated_content = ""
        self._current_block_type = None
        self._has_text_started = False
        
        return {
            "type": "message.assistant.start",
            "message_id": message_id,
            "conversation_id": conversation_id,
            "session_id": session_id,
            "timestamp": timestamp
        }
    
    def _transform_content_delta(
        self,
        event: Dict[str, Any],
        message_id: str,
        timestamp: int,
        session_id: str = ""
    ) -> Optional[Dict[str, Any]]:
        """
        转换 content_delta → message.assistant.delta
        
        🆕 简化格式适配：
        - delta 直接是字符串，类型由 content_start 的 content_block.type 决定
        - 使用 _current_block_type 来判断 delta 类型
        
        映射规则：
        - thinking → delta.type: "thinking"
        - text → delta.type: "response"（🆕 V7.8: Preface 已移至 chat_service 独立阶段）
        - tool_use → 忽略（工具参数不需要转换）
        """
        data = event.get("data", {})
        delta = data.get("delta", "")
        
        # 🆕 简化格式：delta 直接是字符串
        if isinstance(delta, str):
            text = delta
        else:
            # 兼容旧格式（字典形式）
            text = delta.get("text") or delta.get("thinking") or ""
        
        if not text:
            logger.debug(f"[_transform_content_delta] delta 为空，跳过")
            return None
        
        # 🆕 使用 _current_block_type 判断 delta 类型
        zeno_delta_type = None
        block_type = self._current_block_type or ""
        
        if block_type == "thinking":
            zeno_delta_type = "thinking"
            logger.debug(f"[_transform_content_delta] 思考内容: len={len(text)}")
        elif block_type == "text":
            # 🆕 V7.8: 所有 text 块统一使用 response 类型
            # Preface 已移至 chat_service 独立阶段，通过 emit_message_delta 直接发送
            zeno_delta_type = "response"
            logger.debug(f"[_transform_content_delta] 文本内容(response): len={len(text)}, accumulated_len={len(self._accumulated_content)}")
            # 累积内容（用于 done 事件）
            self._accumulated_content += text
        elif block_type in ("tool_use", "server_tool_use", "tool_result"):
            # 工具参数增量和工具结果不需要转换为 ZenO 事件
            # tool_result 的处理由 enhance_tool_result 负责
            logger.debug(f"[_transform_content_delta] 工具相关增量，跳过转换: block_type={block_type}")
            return None
        else:
            # 未知类型，跳过
            logger.warning(f"[_transform_content_delta] 未知 block_type: '{block_type}'，跳过转换")
            return None
        
        return {
            "type": "message.assistant.delta",
            "message_id": message_id,
            "session_id": session_id,
            "timestamp": timestamp,
            "delta": {
                "type": zeno_delta_type,
                "content": text
            }
            # seq 由 EventDispatcher 统一添加
        }
    
    def _transform_message_delta(
        self,
        event: Dict[str, Any],
        message_id: str,
        timestamp: int,
        session_id: str = ""
    ) -> Optional[Dict[str, Any]]:
        """
        转换 message_delta → message.assistant.delta
        
        根据内部 delta.type 映射：
        - recommended → recommended
        - 问数平台类型（sql/data/chart/report/intent/application）→ 直接透传
        
        注意：plan 类型已移至 enhance_tool_result 中处理（plan_todo 工具结果直接转换为 progress）
        """
        data = event.get("data", {})
        # 兼容两种结构：
        # 1. 旧格式：data.delta = {"type": "...", "content": "..."}
        # 2. 新格式：data = {"type": "...", "content": "..."}（delta 直接作为 data）
        delta = data.get("delta") if "delta" in data else data
        delta_type = delta.get("type", "")
        content = delta.get("content", "")
        
        # 🔧 确保 content 是正确的格式（对象而非 JSON 字符串）
        # 如果 content 是字符串且看起来像 JSON，尝试解析它
        if isinstance(content, str) and content.startswith(("{", "[")):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                pass  # 保持原字符串
        
        # 映射 delta 类型
        zeno_delta_type = None
        zeno_content = content
        
        # plan 类型已移至 enhance_tool_result 处理，此处不再处理
        
        if delta_type == "recommended":
            zeno_delta_type = "recommended"
            # recommended 格式兼容，直接使用
        
        # elif delta_type == "confirmation_request":
        #     zeno_delta_type = "clue"
        #     # 转换 HITL 请求为 clue 格式
        #     zeno_content = self._convert_hitl_to_clue(content)
        
        # 直接通过 message_delta 发送的类型
        elif delta_type in (
            "intent", "billing", "progress", "preface",  # 基础类型（V7.8: 添加 preface）
            "sql", "data", "chart", "report", "dashboard", "application", # 问数平台类型
            "mind", "interface", "sandbox", "files",  # 系统搭建/流程图/沙箱/文件类型
            "hitl", "hitl_data", "clue",  # 人机交互类型（hitl: 表单请求, hitl_data: 用户响应, clue: 操作线索）
        ):
            zeno_delta_type = delta_type
            # 格式已符合 ZenO 规范，直接透传
        
        if not zeno_delta_type:
            logger.debug(f"[_transform_message_delta] 未知 delta_type: '{delta_type}'，跳过转换")
            return None
        
        return {
            "type": "message.assistant.delta",
            "message_id": message_id,
            "session_id": session_id,
            "timestamp": timestamp,
            "delta": {
                "type": zeno_delta_type,
                "content": zeno_content
            }
            # seq 由 EventDispatcher 统一添加
        }
    
    def _transform_message_stop(
        self,
        message_id: str,
        timestamp: int,
        session_id: str = ""
    ) -> Dict[str, Any]:
        """
        转换 message_stop → message.assistant.done
        seq 由 EventDispatcher 统一添加
        """
        return {
            "type": "message.assistant.done",
            "message_id": message_id,
            "session_id": session_id,
            "timestamp": timestamp,
            "data": {
                "content": self._accumulated_content
            }
            # seq 由 EventDispatcher 统一添加
        }
    
    def _transform_error(
        self,
        event: Dict[str, Any],
        message_id: str,
        timestamp: int,
        session_id: str = ""
    ) -> Dict[str, Any]:
        """
        转换 error → message.assistant.error
        seq 由 EventDispatcher 统一添加
        """
        data = event.get("data", {})
        error = data.get("error", {})
        
        error_type = error.get("type", "unknown")
        error_message = error.get("message", "未知错误")
        
        # 映射错误类型
        zeno_error_type = "unknown"
        retryable = False
        
        if error_type in ["network_error", "timeout_error"]:
            zeno_error_type = "network"
            retryable = True
        elif error_type == "overloaded_error":
            zeno_error_type = "business"
            retryable = True
        elif error_type == "validation_error":
            zeno_error_type = "business"
            retryable = False
        elif error_type == "internal_error":
            zeno_error_type = "unknown"
            retryable = False
        
        return {
            "type": "message.assistant.error",
            "message_id": message_id,
            "session_id": session_id,
            "timestamp": timestamp,
            "error": {
                "type": zeno_error_type,
                "code": error_type.upper(),
                "message": error_message,
                "retryable": retryable,
                "userAction": "请稍后重试" if retryable else "请联系管理员"
            }
            # seq 由 EventDispatcher 统一添加
        }
    
    def _transform_session_end(
        self,
        event: Dict[str, Any],
        message_id: str,
        timestamp: int
    ) -> Optional[Dict[str, Any]]:
        """
        转换 session_end 事件
        
        🆕 修复：session_end 不再生成 message.assistant.done，
        因为 message_stop 已经发送了 done 事件。
        session_end 是会话级别的结束，不是消息级别的。
        """
        # session_end 不需要转换为 ZenO 事件，避免重复的 done
        logger.debug(f"[session_end] 会话结束，不生成 done 事件（已由 message_stop 处理）")
        return None
    
    def _transform_session_stopped(
        self,
        event: Dict[str, Any],
        session_id: str,
        timestamp: int
    ) -> Dict[str, Any]:
        """
        转换 session_stopped → session.stopped
        
        🆕 用户主动停止时发送，让前端知道是用户中断而非正常结束
        """
        data = event.get("data", {})
        reason = data.get("reason", "user_requested")
        stopped_at = data.get("stopped_at", "")
        
        logger.debug(f"[session_stopped] 用户主动停止: session={session_id[:8] if session_id else 'N/A'}, reason={reason}")
        
        return {
            "type": "session.stopped",
            "session_id": session_id,
            "timestamp": timestamp,
            "data": {
                "reason": reason,
                "stopped_at": stopped_at
            }
        }
    
    def _convert_plan_to_progress(self, content: Any) -> Dict[str, Any]:
        """
        将 plan_todo 格式转换为 ZenO progress 格式
        
        plan_todo 输入格式:
        {
            "name": "制作 AI PPT",
            "overview": "为用户生成一份 AI 技术分享 PPT",
            "todos": [
                {"id": "step-0", "content": "搜索资料", "status": "completed", "result": "找到5篇"},
                {"id": "step-1", "content": "整理大纲", "status": "in_progress"}
            ]
        }
        
        ZenO Progress 输出:
        {
            "title": "制作 AI PPT",
            "status": "running",
            "current": 1,
            "total": 2,
            "subtasks": [
                {"title": "搜索资料", "status": "success", "desc": "找到5篇"},
                {"title": "整理大纲", "status": "running"}
            ]
        }
        
        Args:
            content: plan 数据（str 或 dict）
            
        Returns:
            ZenO progress 格式的字典对象
        """
        try:
            if isinstance(content, str):
                plan = json.loads(content)
            else:
                plan = content
        except json.JSONDecodeError:
            return {"title": "任务执行中", "status": "running", "current": 0, "total": 0, "subtasks": []}
        
        # 状态映射：plan_todo → ZenO
        status_map = {
            "pending": "pending",
            "in_progress": "running",
            "completed": "success",
            "failed": "error"
        }
        
        # 转换 todos → subtasks
        todos = plan.get("todos", [])
        subtasks = []
        for todo in todos:
            subtasks.append({
                "title": todo.get("content", ""),
                "status": status_map.get(todo.get("status", "pending"), "pending"),
                "desc": todo.get("result", "")
            })
        
        # 计算进度
        completed_count = sum(1 for t in todos if t.get("status") == "completed")
        total = len(todos)
        
        # 整体状态
        overall_status = "completed" if (total > 0 and completed_count == total) else "running"
        
        return {
            "title": plan.get("name", "任务执行中"),
            "status": overall_status,
            "current": completed_count,
            "total": total,
            "subtasks": subtasks
        }
    
    def _convert_hitl_to_clue(self, content: str) -> Dict[str, Any]:
        """
        将 Zenflux HITL 请求转换为 ZenO clue 格式
        
        Zenflux HITL:
        {
            "request_id": "req_123",
            "question": "操作确认",
            "confirmation_type": "form",
            "questions": [{"id": "confirm", "label": "是否继续执行？", "type": "single_choice", "options": ["确认", "取消"]}]
        }
        
        ZenO Clue:
        {
            "tasks": [
                {"id": "clue_1", "text": "确认：是否继续执行？", "act": "confirm"},
                {"id": "clue_2", "text": "取消操作", "act": "reply"}
            ]
        }
        """
        try:
            hitl = json.loads(content) if isinstance(content, str) else content
        except json.JSONDecodeError:
            return {"tasks": []}
        
        request_id = hitl.get("request_id", "")
        question = hitl.get("question", "请确认")
        options = hitl.get("options", ["confirm", "cancel"])
        
        tasks = []
        for i, option in enumerate(options):
            # 第一个选项通常是确认
            act = "confirm" if i == 0 else "reply"
            
            # 生成友好的文本
            if option in ["confirm", "确认", "是", "yes"]:
                text = f"确认：{question}"
                act = "confirm"
            elif option in ["cancel", "取消", "否", "no"]:
                text = "取消操作"
                act = "reply"
            else:
                text = str(option)
                act = "reply"
            
            tasks.append({
                "id": f"clue_{request_id}_{i}",
                "text": text,
                "act": act,
                "status": "pending",
                "payload": {
                    "request_id": request_id,
                    "option": option
                }
            })
        
        return {"tasks": tasks}
    
    # ==================== 扩展方法：发送 ZenO 特有事件 ====================
    
    def create_intent_delta(
        self,
        message_id: str,
        intent_id: int,
        intent_name: str,
        platform: str = None
    ) -> Dict[str, Any]:
        """
        创建 intent 类型的 delta 事件
        
        Args:
            message_id: 消息 ID
            intent_id: 意图 ID（1: 系统搭建, 2: 智能分析）
            intent_name: 意图名称
            platform: 平台信息（可选）
        """
        intent_data = {
            "intent_id": intent_id,
            "intent_name": intent_name
        }
        if platform:
            intent_data["platform"] = platform
        
        return {
            "type": "message.assistant.delta",
            "message_id": message_id,
            "timestamp": int(time.time() * 1000),
            "delta": {
                "type": "intent",
                "content": intent_data
            }
        }
    
    def create_preface_delta(
        self,
        message_id: str,
        preface_text: str
    ) -> Dict[str, Any]:
        """
        创建 preface（序言）类型的 delta 事件
        """
        return {
            "type": "message.assistant.delta",
            "message_id": message_id,
            "timestamp": int(time.time() * 1000),
            "delta": {
                "type": "preface",
                "content": preface_text
            }
        }
    
    def create_mind_delta(
        self,
        message_id: str,
        mermaid_content: str,
        chart_type: str = None
    ) -> Dict[str, Any]:
        """
        创建 mind（Mermaid 图表）类型的 delta 事件
        """
        mind_data = {"mermaid_content": mermaid_content}
        if chart_type:
            mind_data["chart_type"] = chart_type
        
        return {
            "type": "message.assistant.delta",
            "message_id": message_id,
            "timestamp": int(time.time() * 1000),
            "delta": {
                "type": "mind",
                "content": mind_data
            }
        }
    
    def create_files_delta(
        self,
        message_id: str,
        files: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        创建 files 类型的 delta 事件
        
        Args:
            files: 文件列表 [{"name": "...", "type": "...", "url": "..."}]
        """
        return {
            "type": "message.assistant.delta",
            "message_id": message_id,
            "timestamp": int(time.time() * 1000),
            "delta": {
                "type": "files",
                "content": files
            }
        }
    
    def create_sql_delta(
        self,
        message_id: str,
        sql_query: str
    ) -> Dict[str, Any]:
        """
        创建 sql 类型的 delta 事件（智能分析场景）
        """
        return {
            "type": "message.assistant.delta",
            "message_id": message_id,
            "timestamp": int(time.time() * 1000),
            "delta": {
                "type": "sql",
                "content": sql_query
            }
        }
    
    def create_data_delta(
        self,
        message_id: str,
        data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        创建 data 类型的 delta 事件（智能分析场景）
        """
        return {
            "type": "message.assistant.delta",
            "message_id": message_id,
            "timestamp": int(time.time() * 1000),
            "delta": {
                "type": "data",
                "content": data
            }
        }
    
    def create_chart_delta(
        self,
        message_id: str,
        chart_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        创建 chart 类型的 delta 事件（智能分析场景）
        
        Args:
            chart_config: ECharts 配置对象
        """
        return {
            "type": "message.assistant.delta",
            "message_id": message_id,
            "timestamp": int(time.time() * 1000),
            "delta": {
                "type": "chart",
                "content": chart_config
            }
        }
    
    def create_application_delta(
        self,
        message_id: str,
        application_id: str,
        status: str,
        name: str = None,
        build_progress: int = None
    ) -> Dict[str, Any]:
        """
        创建 application 类型的 delta 事件（智能分析场景）
        """
        app_data = {
            "application_id": application_id,
            "status": status  # pending, building, success, failed
        }
        if name:
            app_data["name"] = name
        if build_progress is not None:
            app_data["build_progress"] = build_progress
        
        return {
            "type": "message.assistant.delta",
            "message_id": message_id,
            "timestamp": int(time.time() * 1000),
            "delta": {
                "type": "application",
                "content": app_data
            }
        }
    
    def create_sandbox_delta(
        self,
        message_id: str,
        sandbox_id: str,
        status: str,
        preview_url: str = None,
        project_path: str = None,
        stack: str = None,
        error: str = None,
        expires_at: int = None,
        timeout_seconds: int = None
    ) -> Dict[str, Any]:
        """
        创建 sandbox 类型的 delta 事件（沙盒项目启动）
        
        Args:
            message_id: 消息 ID
            sandbox_id: 沙盒/对话 ID
            status: 状态 (pending, building, running, success, failed)
            preview_url: E2B 预览 URL（成功时返回）
            project_path: 项目路径
            stack: 技术栈 (streamlit, flask, vue 等)
            error: 错误信息（失败时返回）
            expires_at: 沙盒过期时间（毫秒时间戳），前端可用于显示倒计时
            timeout_seconds: 沙盒超时时间（秒），剩余存活时间
            
        Returns:
            Zeno 格式的 delta 事件
        """
        sandbox_data = {
            "sandbox_id": sandbox_id,
            "status": status  # pending, building, running, success, failed
        }
        
        if preview_url:
            sandbox_data["preview_url"] = preview_url
        if project_path:
            sandbox_data["project_path"] = project_path
        if stack:
            sandbox_data["stack"] = stack
        if error:
            sandbox_data["error"] = error
        if expires_at is not None:
            sandbox_data["expires_at"] = expires_at
        if timeout_seconds is not None:
            sandbox_data["timeout_seconds"] = timeout_seconds
        
        return {
            "type": "message.assistant.delta",
            "message_id": message_id,
            "timestamp": int(time.time() * 1000),
            "delta": {
                "type": "sandbox",
                "content": sandbox_data
            }
        }
    
    # ===========================================================================
    # 工具结果增强（将 tool_result 拆分为多个 delta）
    # ===========================================================================
    
    async def enhance_tool_result(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        tool_result: Dict[str, Any],
        conversation_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        增强 tool_result，返回额外的 delta 列表
        
        根据工具类型和 api_name 生成额外的 message_delta 事件：
        - wenshu_api → 拆分为 sql/data/chart/report/intent 等（智能分析）
        - coze_api → 转换为 interface（系统配置，Ontology Builder）
        - dify_api → 转换为 mind（Mermaid 流程图，text2flowchart）
        - MCP 流程图工具（如 dify_Ontology_TextToChart）→ 下载 str_url 内容，转换为 mind
        - 其他特殊工具 → 根据 TOOL_TO_DELTA_TYPE 映射
        
        Args:
            tool_name: 工具名称（如 "api_calling"、"dify_Ontology_TextToChart_zen0"）
            tool_input: 工具输入参数（包含 api_name 等）
            tool_result: 工具返回结果（content_block 格式）
            conversation_id: 实际的对话 ID（用于 sandbox 等工具的 delta 生成，
                            避免使用 AI 可能传入的占位符如 "$CONVERSATION_ID"）
            
        Returns:
            delta 列表，每个元素是 {"type": "xxx", "content": "..."}
        """
        is_error = tool_result.get("is_error", False)
        result_content = tool_result.get("content", "")
        
        logger.info(f"🔧 [enhance_tool_result] tool_name={tool_name}, is_error={is_error}, content_len={len(result_content) if result_content else 0}")
        
        # 错误结果不增强
        if is_error:
            logger.info(f"🔧 [enhance_tool_result] 错误结果，跳过增强")
            return []
        
        # 🆕 V7.8: MCP 流程图工具的特殊处理
        # 识别 MCP 工具名模式（如 dify_Ontology_TextToChart_zen0、mcp_dify_Ontology_TextToChart_xxx）
        if self._is_mcp_flowchart_tool(tool_name):
            logger.info(f"🔍 识别到 MCP 流程图工具: tool_name={tool_name}")
            return await self._generate_mcp_flowchart_deltas(result_content)
        
        # api_calling 工具的特殊处理（通过 api_name 识别）
        if tool_name == "api_calling":
            api_name = tool_input.get("api_name", "")
            
            # 1. 问数平台 API → 拆分为 sql/data/chart/report 等
            if api_name in ANALYTICS_API_NAMES:
                logger.debug(f"🔍 识别到分析类 API: api_name={api_name}")
                return self._generate_analytics_deltas(result_content)
            
            # 2. 系统搭建类 API（Coze Ontology Builder）→ interface
            if api_name in ONTOLOGY_API_NAMES:
                logger.debug(f"🔍 识别到系统搭建类 API: api_name={api_name}")
                return await self._generate_ontology_deltas(result_content)
            
        
        # plan_todo 工具的特殊处理（直接转换为 progress 格式）
        if tool_name == "plan_todo":
            logger.info(f"🔧 [enhance_tool_result] 识别到 plan_todo，生成 progress delta")
            deltas = self._generate_plan_progress_deltas(result_content)
            logger.info(f"🔧 [enhance_tool_result] plan_todo 生成了 {len(deltas)} 个 delta")
            return deltas
        
        # clue_generation 工具的特殊处理（转换为 clue 格式）
        if tool_name == "clue_generation":
            logger.info(f"🔧 [enhance_tool_result] 识别到 clue_generation，生成 clue delta")
            deltas = self._generate_clue_deltas(result_content)
            logger.info(f"🔧 [enhance_tool_result] clue_generation 生成了 {len(deltas)} 个 delta")
            return deltas
        
        # hitl 工具的特殊处理（转换为 hitl_data 格式）
        if tool_name == "hitl":
            logger.info(f"🔧 [enhance_tool_result] 识别到 hitl，生成 hitl_data delta")
            deltas = self._generate_hitl_data_deltas(tool_input, result_content)
            logger.info(f"🔧 [enhance_tool_result] hitl 生成了 {len(deltas)} 个 hitl_data delta")
            return deltas
        
        # 沙盒工具：sandbox_get_public_url 的特殊处理（提取 url）
        if tool_name == "sandbox_get_public_url":
            logger.debug(f"🔧 处理 sandbox_get_public_url 工具结果")
            return self._generate_sandbox_deltas(result_content, tool_input, conversation_id)
        
        # 沙盒工具：sandbox_run_command 返回 URL 时生成 sandbox delta
        # 支持两种模式：
        # 1. 单命令模式：返回 {"url": "..."}
        # 2. 多命令模式：返回 {"urls": {"frontend": "...", "backend": "..."}, "services": [...]}
        if tool_name == "sandbox_run_command":
            try:
                result = json.loads(result_content) if isinstance(result_content, str) else result_content
                
                # 单命令模式：直接有 url 字段
                if result.get("url"):
                    logger.debug(f"🔧 处理 sandbox_run_command 返回的 URL: {result.get('url')}")
                    return self._generate_sandbox_deltas(result_content, tool_input, conversation_id)
                
                # 多命令模式：优先取前端服务（5173 端口）的 URL
                if result.get("mode") == "multiple" and result.get("services"):
                    # 前端常用端口（优先级从高到低）
                    frontend_ports = {5173, 3000, 8080, 4200, 5000}
                    
                    # 优先找前端端口的服务
                    target_service = None
                    for service in result["services"]:
                        if service.get("url") and service.get("port") in frontend_ports:
                            target_service = service
                            break
                    
                    # 如果没找到前端端口，取第一个有 URL 的服务
                    if not target_service:
                        for service in result["services"]:
                            if service.get("url"):
                                target_service = service
                                break
                    
                    if target_service:
                        # 构造单命令格式的结果，复用 _generate_sandbox_deltas
                        single_result = {
                            "success": target_service.get("success", True),
                            "url": target_service["url"],
                            "port": target_service.get("port"),
                            "sandbox_id": result.get("sandbox_id", ""),
                            "expires_at": result.get("expires_at"),
                            "timeout_seconds": result.get("timeout_seconds"),
                        }
                        logger.debug(f"🔧 处理 sandbox_run_command 多命令模式，取服务 [{target_service.get('name')}] 的 URL: {target_service['url']}")
                        return self._generate_sandbox_deltas(
                            json.dumps(single_result), 
                            tool_input, 
                            conversation_id
                        )
            except (json.JSONDecodeError, TypeError):
                pass
        
        # 🆕 V7.7: send_files 工具的特殊处理（生成 files delta）
        if tool_name == "send_files":
            logger.info(f"🔧 [enhance_tool_result] 识别到 send_files，生成 files delta")
            deltas = self._generate_files_deltas(result_content)
            logger.info(f"🔧 [enhance_tool_result] send_files 生成了 {len(deltas)} 个 delta")
            return deltas
        
        # 检查是否需要发送特殊 delta（简单工具）
        delta_type = TOOL_TO_DELTA_TYPE.get(tool_name)
        if delta_type:
            logger.debug(f"🔧 生成特殊工具 delta: type={delta_type}, tool={tool_name}")
            return [self._create_delta(delta_type, result_content)]
        
        return []
    
    def _is_mcp_flowchart_tool(self, tool_name: str) -> bool:
        """
        检查是否是 MCP 流程图工具
        
        MCP 工具名格式：
        - dify_Ontology_TextToChart_zen0
        - mcp_dify_Ontology_TextToChart_xxx
        - TextToChart_xxx
        
        Args:
            tool_name: 工具名称
            
        Returns:
            是否是 MCP 流程图工具
        """
        # 移除可能的前缀（mcp_）
        normalized_name = tool_name
        if normalized_name.startswith("mcp_"):
            normalized_name = normalized_name[4:]
        
        # 检查是否匹配流程图工具模式
        for pattern in MCP_FLOWCHART_TOOL_PATTERNS:
            if pattern in normalized_name:
                return True
        
        return False
    
    async def _generate_mcp_flowchart_deltas(self, result_content: str) -> List[Dict[str, Any]]:
        """
        🆕 V7.8: 为 MCP 流程图工具生成 mind delta
        
        MCP 流程图工具（如 dify_Ontology_TextToChart_zen0）返回格式：
        {
            "success": true,
            "data": "{\"str_url\": \"https://xxx.txt\"}"
        }
        
        处理流程：
        1. 解析返回结果，提取 str_url
        2. 下载 txt 文件内容（包含 Mermaid 图表）
        3. 生成 mind delta
        
        注意：不再生成 intent delta，避免重复
        
        Args:
            result_content: 工具返回的 JSON 字符串
            
        Returns:
            delta 列表（只包含 mind 类型的 delta）
        """
        import httpx
        
        deltas = []
        
        # 解析结果
        try:
            if isinstance(result_content, str):
                result = json.loads(result_content)
            else:
                result = result_content
        except json.JSONDecodeError:
            logger.warning(f"⚠️ MCP 流程图工具结果解析失败: {str(result_content)[:200]}...")
            return deltas
        
        # 检查是否成功
        if not result.get("success", False):
            logger.warning(f"⚠️ MCP 流程图工具返回失败: {result.get('error')}")
            return deltas
        
        logger.info(f"📊 MCP 流程图工具结果处理")
        
        # 提取 str_url（可能嵌套在 data 字段中）
        str_url = None
        
        # 尝试从 data 字段提取
        data = result.get("data")
        if data:
            # data 可能是 JSON 字符串
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except json.JSONDecodeError:
                    pass
            
            if isinstance(data, dict):
                str_url = data.get("str_url")
        
        # 直接从 result 提取
        if not str_url:
            str_url = result.get("str_url")
        
        if not str_url:
            logger.warning(f"⚠️ MCP 流程图工具结果中没有 str_url 字段: {str(result)[:200]}")
            return deltas
        
        logger.info(f"📥 开始下载流程图内容: {str_url}")
        
        # 下载 txt 文件内容
        mermaid_content = await self._fetch_flowchart_content(str_url)
        
        if not mermaid_content:
            logger.warning(f"⚠️ 流程图内容下载失败或为空")
            return deltas
        
        # 清理 Mermaid 代码块标记
        mermaid_content = self._clean_mermaid_content(mermaid_content)
        
        # 生成 mind delta（不生成 intent，避免重复）
        mind_data = {
            "flowchart_content": mermaid_content
        }
        deltas.append(self._create_delta("mind", mind_data))
        
        logger.info(f"✅ MCP 流程图 mind delta 生成完成，内容长度: {len(mermaid_content)}")
        
        return deltas
    
    async def _fetch_flowchart_content(self, url: str) -> Optional[str]:
        """
        下载流程图内容（txt 文件）
        
        Args:
            url: txt 文件 URL
            
        Returns:
            文件内容，失败返回 None
        """
        import httpx
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                content = response.text
                logger.debug(f"📥 流程图内容下载成功，长度: {len(content)}")
                return content
        except httpx.TimeoutException:
            logger.error(f"❌ 下载流程图内容超时: {url}")
            return None
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ 下载流程图内容 HTTP 错误: {e.response.status_code}, url={url}")
            return None
        except Exception as e:
            logger.error(f"❌ 下载流程图内容失败: {str(e)}", exc_info=True)
            return None
    
    def _generate_plan_progress_deltas(self, result_content: str) -> List[Dict[str, Any]]:
        """
        为 plan_todo 工具生成 progress delta
        
        提取 plan_todo 返回结果中的 plan 字段，转换为 ZenO progress 格式
        
        plan_todo 返回格式：
        {
            "status": "success",
            "message": "Plan created: xxx",
            "plan": {
                "goal": "xxx",
                "steps": [...],
                "current_step": 0,
                "progress": 0.0,
                ...
            }
        }
        
        Args:
            result_content: plan_todo 工具返回的 JSON 字符串
            
        Returns:
            delta 列表（包含一个 progress 类型的 delta）
        """
        try:
            if isinstance(result_content, str):
                result = json.loads(result_content)
            else:
                result = result_content
        except json.JSONDecodeError:
            logger.warning(f"⚠️ plan_todo 结果解析失败: {str(result_content)[:100]}...")
            return []
        
        # 提取 plan 字段
        plan = result.get("plan")
        if not plan:
            logger.debug("plan_todo 结果中没有 plan 字段，跳过 progress delta 生成")
            return []
        
        # 转换为 progress 格式
        progress_content = self._convert_plan_to_progress(plan)
        
        logger.debug(f"📋 生成 plan_todo progress delta")
        return [self._create_delta("progress", progress_content)]
    
    def _generate_clue_deltas(self, result_content: str) -> List[Dict[str, Any]]:
        """
        为 clue_generation 工具生成 clue delta
        
        clue_generation 返回格式：
        {
            "success": true,
            "message": "成功生成 X 个操作建议",
            "tasks": [
                {"id": "clue_1", "text": "线索描述", "act": "reply", "payload": {...}}
            ]
        }
        
        生成的 delta 类型：
        - clue: 操作线索列表，供前端渲染
        
        Args:
            result_content: clue_generation 工具返回的 JSON 字符串
            
        Returns:
            delta 列表（包含一个 clue 类型的 delta）
        """
        deltas = []
        
        # 解析结果
        try:
            if isinstance(result_content, str):
                result = json.loads(result_content)
            else:
                result = result_content
        except json.JSONDecodeError:
            logger.warning(f"⚠️ clue_generation 结果解析失败: {str(result_content)[:100]}...")
            return deltas
        
        # 检查是否成功
        if not result.get("success", False):
            logger.warning(f"⚠️ clue_generation 返回失败: {result.get('error')}")
            return deltas
        
        # 提取 tasks 字段
        tasks = result.get("tasks", [])
        if not tasks:
            logger.debug("clue_generation 结果中没有 tasks 或 tasks 为空，跳过 clue delta 生成")
            return deltas
        
        # 构建 clue delta 数据（直接使用 tasks 数组，包装为 {"tasks": [...]} 格式）
        clue_data = {"tasks": tasks}
        
        logger.info(f"🔍 生成 clue delta: 包含 {len(tasks)} 个操作建议")
        deltas.append(self._create_delta("clue", clue_data))
        
        return deltas
    
    def _generate_hitl_data_deltas(
        self,
        tool_input: Dict[str, Any],
        result_content: str
    ) -> List[Dict[str, Any]]:
        """
        为 hitl 工具生成 hitl_data delta（用户响应数据）
        
        注意：
        - hitl（tool_use 阶段）：表单请求，由 broadcaster._emit_hitl_request_event 发送
        - hitl_data（tool_result 阶段）：用户响应数据，由本方法生成
        
        hitl 工具输入格式：
        {
            "title": "确认操作",
            "description": "请确认以下操作",
            "questions": [
                {
                    "id": "confirm",
                    "label": "确定要删除这些文件吗？",
                    "type": "single_choice",
                    "options": ["是的，删除", "不，取消"]
                }
            ],
            "timeout": 120
        }
        
        hitl 工具返回格式：
        {
            "success": true,
            "timed_out": false,
            "response": {"question_id": "用户选择/输入", ...},
            "metadata": {}
        }
        
        生成的 delta 类型：
        - hitl_data: 人机交互响应数据，供前端更新表单状态
        
        Args:
            tool_input: hitl 工具的输入参数（包含表单定义）
            result_content: hitl 工具返回的 JSON 字符串（用户响应）
            
        Returns:
            delta 列表（包含一个 hitl_data 类型的 delta）
        """
        deltas = []
        
        # 解析结果
        try:
            if isinstance(result_content, str):
                result = json.loads(result_content)
            else:
                result = result_content
        except json.JSONDecodeError:
            logger.warning(f"⚠️ hitl_data 结果解析失败: {str(result_content)[:100]}...")
            return deltas
        
        success = bool(result.get("success", False))
        timed_out = bool(result.get("timed_out", False))
        error_message = result.get("error") or result.get("message")
        
        # 🆕 支持 pending 状态（HITL 异步模式）
        result_status = result.get("status", "")
        if result_status == "pending_user_input":
            status = "pending"
        else:
            status = "completed" if success else "timeout" if timed_out else "failed"
        
        # 🔑 重要：pending 状态不生成 hitl_data delta
        # 原因：前端需要通过是否收到 hitl_data 来区分用户行为：
        # - 收到 hitl_data (completed) → 用户提交了表单
        # - 没有收到 hitl_data → 用户点击"忽略"，直接输入
        # 前端通过 tool_use 事件中的 tool_input 来渲染表单，不需要 pending 状态的 hitl_data
        if status == "pending":
            logger.info(f"⏸️ HITL pending 状态: 不生成 hitl_data delta，等待用户操作")
            return deltas  # 返回空列表
        
        # 构建 hitl_data delta 数据（仅 completed/timeout/failed 状态）
        hitl_data = {
            # 🆕 类型标识（前端用于区分不同的 HITL 交互类型）
            "type": "form",
            # 响应状态（pending / completed / timeout / failed）
            "status": status,
            # 表单定义（来自工具输入）
            "title": tool_input.get("title", ""),
            "description": tool_input.get("description", ""),
            "questions": tool_input.get("questions", []),
            # 用户响应（来自工具输出）
            "success": success,
            "timed_out": timed_out,
            "used_default": bool(result.get("used_default", False)),
            "response": result.get("response"),
        }
        
        # 添加可选字段
        if error_message:
            hitl_data["message"] = error_message
        
        # 添加可选的 metadata
        if result.get("metadata"):
            hitl_data["metadata"] = result["metadata"]
        
        # 根据状态记录日志
        if status == "pending":
            logger.info(f"⏳ 生成 hitl_data delta: 等待用户响应, title={tool_input.get('title', '')[:30]}")
        elif result.get("timed_out"):
            logger.info(f"⏱️ 生成 hitl_data delta: 用户响应超时")
        elif result.get("success"):
            logger.info(f"✅ 生成 hitl_data delta: 用户已响应, title={tool_input.get('title', '')[:30]}")
        else:
            logger.warning(f"⚠️ 生成 hitl_data delta: 请求失败, error={result.get('error')}")
        
        deltas.append(self._create_delta("hitl_data", hitl_data))
        
        return deltas
    
    def _generate_analytics_deltas(self, result_content: str) -> List[Dict[str, Any]]:
        """
        为分析类 API（如问数平台）生成多个 delta
        
        分析类 API 返回的结果包含多个字段，每个字段对应一个 delta：
        - sql: SQL 查询语句
        - data: 查询结果数据
        - chart: 图表配置
        - report: 分析报告 {title, content}
        - dashboard: 仪表盘数据 {dashboard_id, name, status}（可选）
        
        Args:
            result_content: 工具返回的 JSON 字符串
            
        Returns:
            delta 列表
        """
        deltas = []
        
        # 解析结果
        try:
            if isinstance(result_content, str):
                result = json.loads(result_content)
            else:
                result = result_content
        except json.JSONDecodeError:
            logger.warning(f"⚠️ 分析类 API 结果解析失败: {str(result_content)[:100]}...")
            return deltas
        
        # 🔧 V7.9: 支持嵌套数据结构
        # 问数平台返回格式：{"code":0, "data": {"success":true, "report":..., "chart":..., "data":...}}
        # 需要从 data 字段中提取实际内容
        actual_data = result
        if "data" in result and isinstance(result.get("data"), dict):
            # 检查外层 code 是否成功
            if result.get("code") not in (0, None):
                logger.warning(f"⚠️ 分析类 API 返回错误码: code={result.get('code')}, msg={result.get('msg')}")
                return deltas
            actual_data = result["data"]
            logger.debug(f"📊 检测到嵌套数据结构，提取 data 字段")
        
        # 检查是否成功
        if not actual_data.get("success", False):
            error_msg = actual_data.get("error") or result.get("msg") or result.get("error")
            logger.warning(f"⚠️ 分析类 API 返回失败: {error_msg}")
            return deltas
        
        logger.info(f"📊 分析类 API 结果处理")
        
        # 注意：intent 不在此处理，由其他机制发送
        
        # 生成 sql delta
        sql = actual_data.get("sql")
        if sql:
            deltas.append(self._create_delta("sql", sql))
        
        # 生成 data delta（注意：这里的 data 是查询结果数据，不是外层的 data 字段）
        data_result = actual_data.get("data")
        if data_result:
            deltas.append(self._create_delta("data", data_result))
        
        # 生成 chart delta
        chart = actual_data.get("chart")
        if chart:
            deltas.append(self._create_delta("chart", chart))
        
        # 生成 report delta
        report = actual_data.get("report")
        if report:
            deltas.append(self._create_delta("report", report))
        
        # 生成 dashboard delta（可选，包含 dashboard_id 等）
        dashboard_id = actual_data.get("dashboard_id")
        if dashboard_id:
            # 从 report.title 获取名称，从 success 字段获取状态
            report_title = report.get("title", "数据分析") if report else "数据分析"
            app_status = "success" if actual_data.get("success") else "failed"
            app_data = {
                "dashboard_id": dashboard_id,
                "name": report_title,
                "status": app_status
            }
            deltas.append(self._create_delta("dashboard", app_data))
        
        return deltas
    
    def _generate_sandbox_deltas(
        self,
        result_content: str,
        tool_input: Dict[str, Any],
        actual_conversation_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        为 sandbox_get_public_url 工具生成 sandbox delta
        
        sandbox_get_public_url 返回格式：
        {
            "success": true,
            "url": "https://3000-xxx.e2b.app",
            "port": 3000,
            "expires_at": 1737900000000,  // 可选：毫秒时间戳
            "timeout_seconds": 3600       // 可选：剩余秒数
        }
        
        生成的 delta 类型：
        - sandbox: 包含 url、status、过期时间等信息
        
        Args:
            result_content: 工具返回的 JSON 字符串
            tool_input: 工具输入参数（包含 conversation_id、port 等）
            actual_conversation_id: 实际的对话 ID
            
        Returns:
            delta 列表（包含一个 sandbox 类型的 delta）
        """
        deltas = []
        
        # 解析结果
        try:
            if isinstance(result_content, str):
                result = json.loads(result_content)
            else:
                result = result_content
        except json.JSONDecodeError:
            logger.warning(f"⚠️ sandbox_get_public_url 结果解析失败: {str(result_content)[:100]}...")
            return deltas
        
        # 提取信息
        success = result.get("success", False)
        # 兼容 url 和 preview_url 两种字段名
        public_url = result.get("url") or result.get("preview_url")
        port = result.get("port")
        error = result.get("error")
        # 从工具结果中获取 E2B 实际沙箱 ID
        sandbox_id = result.get("sandbox_id", "")
        
        # 🆕 提取过期时间信息
        expires_at = result.get("expires_at")  # 毫秒时间戳
        timeout_seconds = result.get("timeout_seconds")  # 剩余秒数
        
        # 构建 sandbox delta 数据（符合前端 SandboxData 接口）
        # status: 'success' | 'error' | 'running' | 'pending'
        sandbox_data = {
            "sandbox_id": sandbox_id,  # E2B 实际沙箱 ID
            "status": "success" if success else "error",
            "project_path": "/home/user/project",  # 默认项目路径
            "stack": "nodejs",  # 默认技术栈
        }
        
        if public_url:
            sandbox_data["preview_url"] = public_url
        if port:
            sandbox_data["port"] = port
        if error:
            sandbox_data["error"] = error
        
        # 🆕 添加过期时间字段
        if expires_at is not None:
            sandbox_data["expires_at"] = expires_at
        if timeout_seconds is not None:
            sandbox_data["timeout_seconds"] = timeout_seconds
        
        logger.info(
            f"🚀 生成 sandbox delta: sandbox_id={sandbox_id}, url={public_url}, "
            f"status={'success' if success else 'error'}, "
            f"expires_at={expires_at}, timeout_seconds={timeout_seconds}"
        )
        deltas.append(self._create_delta("sandbox", sandbox_data))
        
        return deltas
    
    def _generate_files_deltas(self, result_content: str) -> List[Dict[str, Any]]:
        """
        🆕 V7.7: 为 send_files 工具生成 files delta
        
        send_files 返回格式（系统工具会直接返回 tool_input）：
        {
            "success": true,
            "files": [
                {
                    "name": "报告.pptx",
                    "type": "pptx",
                    "url": "https://...",
                    "size": 1024000,        // 可选
                    "thumbnail": "https://...",  // 可选
                    "description": "AI技术分享"  // 可选
                }
            ]
        }
        
        生成的 delta 类型：
        - files: 文件列表，供前端渲染
        
        Args:
            result_content: 工具返回的 JSON 字符串
            
        Returns:
            delta 列表（包含一个 files 类型的 delta）
        """
        deltas = []
        
        # 解析结果
        try:
            if isinstance(result_content, str):
                result = json.loads(result_content)
            else:
                result = result_content
        except json.JSONDecodeError:
            logger.warning(f"⚠️ send_files 结果解析失败: {str(result_content)[:100]}...")
            return deltas
        
        # 检查是否成功
        if not result.get("success", False):
            logger.warning(f"⚠️ send_files 返回失败: {result.get('error')}")
            return deltas
        
        # 提取 files 字段
        files = result.get("files", [])
        if not files:
            logger.warning("⚠️ send_files 结果中没有 files 字段")
            return deltas
        
        # 构建 files delta 数据（直接使用 files 数组，不要再包一层）
        logger.info(f"📁 生成 files delta: 包含 {len(files)} 个文件")
        deltas.append(self._create_delta("files", files))
        
        return deltas
    
    async def _generate_ontology_deltas(self, result_content: str) -> List[Dict[str, Any]]:
        """
        为系统搭建类 API（Coze Ontology Builder）生成 delta
        
        Coze SSE 返回格式（解析后）：
        - 最终结果通常在最后一个 Message 事件的 content 中
        - content 可能是 JSON 对象，也可能是指向 JSON 文件的 URL
        - 包含系统配置（实体、属性、关系）
        
        生成的 delta 类型：
        - intent: 意图识别
        - interface: 系统配置（实体、属性、关系）—— content 为 JSON 字符串
        - application: 应用状态
        
        Args:
            result_content: 工具返回的内容（可能是 JSON 或原始 SSE）
            
        Returns:
            delta 列表
        """
        deltas = []
        
        # 解析结果
        parsed_result = self._parse_coze_sse_result(result_content)
        
        if not parsed_result:
            logger.warning(f"⚠️ Coze API 结果解析失败: {str(result_content)[:200]}...")
            return deltas
        
        logger.info(f"🏗️ Ontology Builder 结果处理")
        
        # 🆕 V7.10: 检测 parsed_result 是否是 URL，如果是则下载内容
        # Coze 有时会返回指向 S3/OSS 的 JSON 文件 URL 而不是直接返回内容
        if isinstance(parsed_result, str) and self._is_json_url(parsed_result):
            logger.info(f"📥 检测到 Ontology 结果是 URL，开始下载: {parsed_result[:100]}...")
            downloaded_content = await self._fetch_json_content(parsed_result)
            if downloaded_content:
                parsed_result = downloaded_content
                logger.info(f"✅ Ontology 内容下载成功，内容类型: {type(parsed_result).__name__}")
            else:
                logger.warning(f"⚠️ Ontology 内容下载失败，使用原始 URL 作为内容")
        
        # 🆕 V7.10.2: 只生成 interface delta，移除 intent 和 application delta
        # 前端已通过路由层的 intent delta 获知意图，不需要重复发送
        
        # 生成 interface delta（系统配置）
        # 🆕 V7.10.3: 直接使用完整的 parsed_result，不做任何字段提取
        # 前端需要完整的 JSON 结构来处理
        interface_data = parsed_result
        
        # 🆕 将 interface_data 序列化为 JSON 字符串
        # 前端期望 content 是 JSON 字符串，如：
        # {"type": "interface", "content": "{\"ontology\":{...},\"config\":{...}}"}
        if isinstance(interface_data, (dict, list)):
            interface_content = json.dumps(interface_data, ensure_ascii=False)
        else:
            interface_content = str(interface_data)
        
        deltas.append(self._create_delta("interface", interface_content))
        
        return deltas
    
    def _is_json_url(self, value: str) -> bool:
        """
        检测字符串是否是指向 JSON 文件的 URL
        
        Args:
            value: 待检测的字符串
            
        Returns:
            是否是 JSON URL
        """
        if not isinstance(value, str):
            return False
        
        value = value.strip()
        
        # 检查是否是 HTTP/HTTPS URL
        if not (value.startswith("http://") or value.startswith("https://")):
            return False
        
        # 检查是否是 JSON 文件 URL（常见的云存储路径）
        # 支持 .json 后缀或常见的云存储域名
        json_indicators = [
            ".json",
            "s3.amazonaws.com",
            "s3.ap-southeast",
            "oss-cn-",
            "aliyuncs.com",
            "blob.core.windows.net",
        ]
        
        return any(indicator in value.lower() for indicator in json_indicators)
    
    async def _fetch_json_content(self, url: str) -> Any:
        """
        下载 JSON 文件内容
        
        Args:
            url: JSON 文件 URL
            
        Returns:
            解析后的 JSON 对象，失败返回 None
        """
        import httpx
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                content = response.text
                logger.debug(f"📥 JSON 内容下载成功，长度: {len(content)}")
                
                # 尝试解析 JSON
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    logger.warning(f"⚠️ 下载的内容不是有效 JSON: {content[:200]}...")
                    return content
                    
        except httpx.TimeoutException:
            logger.error(f"❌ 下载 JSON 内容超时: {url}")
            return None
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ 下载 JSON 内容 HTTP 错误: {e.response.status_code}, url={url}")
            return None
        except Exception as e:
            logger.error(f"❌ 下载 JSON 内容失败: {str(e)}", exc_info=True)
            return None
    
    def _generate_flowchart_deltas(self, result_content: str) -> List[Dict[str, Any]]:
        """
        为流程图生成类 API（Dify text2flowchart）生成 delta
        
        Dify 返回格式：
        {
            "workflow_run_id": "xxx",
            "data": {
                "outputs": {
                    "text": "```mermaid\\nflowchart TD\\n  ...\\n```"
                }
            }
        }
        
        生成的 delta 类型：
        - intent: 意图识别
        - mind: Mermaid 图表（流程图/思维导图）
        
        Args:
            result_content: 工具返回的 JSON 字符串
            
        Returns:
            delta 列表
        """
        deltas = []
        
        # 解析结果
        try:
            if isinstance(result_content, str):
                result = json.loads(result_content)
            else:
                result = result_content
        except json.JSONDecodeError:
            logger.warning(f"⚠️ Dify API 结果解析失败: {str(result_content)[:200]}...")
            return deltas
        
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
            return deltas
        
        # 清理 Mermaid 代码块标记
        mermaid_content = self._clean_mermaid_content(mermaid_content)
                
        # 生成 mind delta（Mermaid 图表）
        mind_data = {
            "mermaid_content": mermaid_content,
            "chart_type": "flowchart"
        }
        deltas.append(self._create_delta("mind", mind_data))
        
        return deltas
    
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
            # 如果是字符串，先解析为 JSON
            if isinstance(result_content, str):
                result = json.loads(result_content)
            else:
                result = result_content
            
            # 如果是 raw_content 格式，需要进一步解析 SSE
            if isinstance(result, dict) and "raw_content" in result:
                return self._parse_coze_sse_stream(result["raw_content"])
            
            # 处理轮询响应格式：{code: 0, data: [{output: "..."}]}
            if isinstance(result, dict) and "data" in result and isinstance(result.get("data"), list):
                data_list = result["data"]
                if data_list and isinstance(data_list[0], dict) and "output" in data_list[0]:
                    output = data_list[0]["output"]
                    logger.info(f"🔄 提取轮询响应 data[0].output")
                    # output 是 JSON 字符串：{"Output": "{\"data\":\"url\"}", "node_status": "{}"}
                    if isinstance(output, str):
                        try:
                            parsed = json.loads(output)
                            # 提取 Output 字段
                            if isinstance(parsed, dict) and "Output" in parsed:
                                output_str = parsed["Output"]
                                if output_str:
                                    try:
                                        output_obj = json.loads(output_str)
                                        # Output 结构：{content_type, data, original_result, type_for_model}
                                        # 实际数据在 data 字段中
                                        if isinstance(output_obj, dict) and "data" in output_obj:
                                            logger.info(f"🔄 提取 Output.data")
                                            return output_obj["data"]
                                        return output_obj
                                    except (json.JSONDecodeError, TypeError):
                                        return output_str
                            return parsed
                        except json.JSONDecodeError:
                            return output
                    return output
            
            return result
        except json.JSONDecodeError:
            pass
        
        # 尝试解析 SSE 流
        return self._parse_coze_sse_stream(result_content)
    
    def _parse_coze_sse_stream(self, raw_content: str) -> Any:
        """
        解析 Coze SSE 流内容，提取最终结果
        
        🆕 V7.10.1: 修复累积空 {} 的问题
        - 只取最后一个非空、有意义的 content
        - 如果 content 是 URL，直接返回 URL
        - 如果 content 是 JSON 对象，累积后解析
        
        Args:
            raw_content: 原始 SSE 流内容
            
        Returns:
            最终结果（最后一个 Message 事件的 content）
        """
        contents = []  # 收集所有非空 content
        
        for line in raw_content.split("\n"):
            line = line.strip()
            
            if line.startswith("data:"):
                data_str = line[5:].strip()
                try:
                    data = json.loads(data_str)
                    content = data.get("content", "")
                    if content and content.strip() and content.strip() != "{}":
                        contents.append(content)
                except json.JSONDecodeError:
                    continue
        
        if not contents:
            return None
        
        # 🆕 检查最后一个 content 是否是 URL
        last_content = contents[-1].strip()
        if last_content.startswith("http://") or last_content.startswith("https://"):
            logger.info(f"🔗 检测到 Coze 返回 URL: {last_content[:100]}...")
            return last_content
        
        # 尝试将所有内容累积后解析为 JSON
        final_content = "".join(contents)
        if final_content:
            try:
                return json.loads(final_content)
            except json.JSONDecodeError:
                # 如果解析失败，尝试只用最后一个 content
                try:
                    return json.loads(last_content)
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
    
    def _create_delta(self, delta_type: str, content: Any) -> Dict[str, Any]:
        """
        创建单个 delta 结构
        
        Args:
            delta_type: delta 类型
            content: 内容（对象、数组或字符串）
            
        Returns:
            delta 字典 {"type": "xxx", "content": ...}（content 为对象，非 JSON 字符串）
        """
        logger.debug(f"📤 创建 delta: type={delta_type}")
        
        return {
            "type": delta_type,
            "content": content
        }
    
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
