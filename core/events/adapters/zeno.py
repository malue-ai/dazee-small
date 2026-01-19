"""
ZenO 适配器

将 Zenflux 内部事件转换为 ZenO SSE 数据规范 v2.0.1 格式

ZenO 规范特点：
1. 生命周期事件：message.assistant.created/start/done/error
2. 业务事件统一用：message.assistant.delta + delta.type
3. delta.type 包括：intent, preface, thinking, response, progress, clue, files, mind, sql, data, chart, recommended, application

参考文档：ZenO 会话详情页 SSE 数据规范 v2.0.1
"""

import json
import time
from typing import Dict, Any, List, Optional
from core.events.adapters.base import EventAdapter
from logger import get_logger

logger = get_logger("zeno_adapter")


class ZenOAdapter(EventAdapter):
    """
    ZenO 事件适配器
    
    将 Zenflux 5 层事件架构转换为 ZenO SSE 规范
    
    映射关系：
    - message_start → message.assistant.created + message.assistant.start
    - content_delta (thinking) → message.assistant.delta (type: thinking)
    - content_delta (text) → message.assistant.delta (type: response)
    - message_delta:plan → message.assistant.delta (type: progress)
    - message_delta:recommended → message.assistant.delta (type: recommended)
    - message_delta:confirmation_request → message.assistant.delta (type: clue)
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
        message_id = data.get("message_id") or self._current_message_id or f"msg_{session_id}"
        timestamp = int(time.time() * 1000)  # 毫秒时间戳
        
        # 更新 message_id 缓存
        if data.get("message_id"):
            self._current_message_id = data.get("message_id")
        
        # 根据事件类型转换（不传 seq，由 EventDispatcher 统一添加）
        if event_type == "message_start":
            return self._transform_message_start(message_id, conversation_id, timestamp, session_id)
        
        # 处理 content_start：记录当前 block 类型
        if event_type == "content_start":
            content_block = data.get("content_block", {})
            self._current_block_type = content_block.get("type")
            return None  # content_start 不需要转换为 ZenO 事件
        
        if event_type == "content_delta":
            return self._transform_content_delta(event, message_id, timestamp, session_id)
        
        if event_type == "message_delta":
            return self._transform_message_delta(event, message_id, timestamp, session_id)
        
        if event_type == "message_stop":
            return self._transform_message_stop(message_id, timestamp, session_id)
        
        if event_type == "error":
            return self._transform_error(event, message_id, timestamp, session_id)
        
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
        
        return {
            "type": "message.assistant.start",
            "message_id": message_id,
            "conversation_id": conversation_id,
            "session_id": session_id,
            "timestamp": timestamp
            # seq 由 EventDispatcher 统一添加
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
        - text → delta.type: "response"
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
            return None
        
        # 🆕 使用 _current_block_type 判断 delta 类型
        zeno_delta_type = None
        block_type = self._current_block_type or ""
        
        if block_type == "thinking":
            zeno_delta_type = "thinking"
        elif block_type == "text":
            zeno_delta_type = "response"
            # 累积内容（用于 done 事件）
            self._accumulated_content += text
        elif block_type in ("tool_use", "server_tool_use"):
            # 工具参数增量不需要转换为 ZenO 事件
            return None
        else:
            # 未知类型，跳过
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
        - plan → progress
        - recommended → recommended
        - confirmation_request → clue
        - 问数平台类型（sql/data/chart/report/intent/application）→ 直接透传
        """
        data = event.get("data", {})
        # 兼容两种结构：
        # 1. 旧格式：data.delta = {"type": "...", "content": "..."}
        # 2. 新格式：data = {"type": "...", "content": "..."}（delta 直接作为 data）
        delta = data.get("delta") if "delta" in data else data
        delta_type = delta.get("type", "")
        content = delta.get("content", "")
        
        # 映射 delta 类型
        zeno_delta_type = None
        zeno_content = content
        
        if delta_type == "plan":
            zeno_delta_type = "progress"
            # 转换 plan 格式为 progress 格式
            zeno_content = self._convert_plan_to_progress(content)
        
        elif delta_type == "recommended":
            zeno_delta_type = "recommended"
            # recommended 格式兼容，直接使用
        
        elif delta_type == "confirmation_request":
            zeno_delta_type = "clue"
            # 转换 HITL 请求为 clue 格式
            zeno_content = self._convert_hitl_to_clue(content)
        
        # 🆕 问数平台智能分析场景：直接透传 delta 类型
        elif delta_type in (
            "sql", "data", "chart", "report",  # 智能分析三件套 + 报告
            "intent", "application",            # 意图和应用状态
            "preface", "files", "mind", "clue"  # 其他通用类型
        ):
            zeno_delta_type = delta_type
            # 格式已符合规范，直接透传
        
        if not zeno_delta_type:
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
    ) -> Dict[str, Any]:
        """
        转换 session_end → message.assistant.done
        """
        return {
            "type": "message.assistant.done",
            "message_id": message_id,
            "timestamp": timestamp,
            "data": {
                "content": self._accumulated_content
            }
        }
    
    def _convert_plan_to_progress(self, content: str) -> str:
        """
        将 Zenflux plan 格式转换为 ZenO progress 格式
        
        Zenflux Plan:
        {
            "goal": "生成PPT",
            "steps": [
                {"index": 0, "action": "分析需求", "status": "completed"},
                {"index": 1, "action": "调用API", "status": "in_progress"}
            ],
            "current_step": 1,
            "progress": 0.5
        }
        
        ZenO Progress:
        {
            "title": "生成PPT",
            "status": "running",
            "current": 1,
            "total": 2,
            "subtasks": [
                {"title": "分析需求", "status": "success"},
                {"title": "调用API", "status": "running"}
            ]
        }
        """
        try:
            plan = json.loads(content) if isinstance(content, str) else content
        except json.JSONDecodeError:
            return content
        
        # 转换步骤状态
        status_map = {
            "pending": "pending",
            "in_progress": "running",
            "completed": "success",
            "failed": "error"
        }
        
        steps = plan.get("steps", [])
        subtasks = []
        for step in steps:
            subtasks.append({
                "title": step.get("action", ""),
                "status": status_map.get(step.get("status", "pending"), "pending"),
                "desc": step.get("result", "")
            })
        
        # 计算完成数
        completed_count = sum(1 for s in steps if s.get("status") == "completed")
        total = len(steps)
        
        # 整体状态
        overall_status = "running"
        if plan.get("progress", 0) >= 1.0:
            overall_status = "completed"
        
        progress_data = {
            "title": plan.get("goal", "任务执行中"),
            "status": overall_status,
            "current": completed_count,
            "total": total,
            "subtasks": subtasks
        }
        
        return json.dumps(progress_data, ensure_ascii=False)
    
    def _convert_hitl_to_clue(self, content: str) -> str:
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
            return content
        
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
        
        clue_data = {"tasks": tasks}
        return json.dumps(clue_data, ensure_ascii=False)
    
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
                "content": json.dumps(intent_data, ensure_ascii=False)
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
                "content": json.dumps(mind_data, ensure_ascii=False)
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
                "content": json.dumps(files, ensure_ascii=False)
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
                "content": json.dumps(data, ensure_ascii=False)
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
                "content": json.dumps(chart_config, ensure_ascii=False)
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
                "content": json.dumps(app_data, ensure_ascii=False)
            }
        }

