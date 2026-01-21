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

# 流程图生成类 API（text2flowchart 等）
# 返回 mind 类型：Mermaid 图表（流程图/思维导图）
FLOWCHART_API_NAMES = {
    "dify_api",        # Dify text2flowchart 工作流
    "dify",            # 简写形式
}


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
        
        # 🆕 修复：处理 session_end 事件（支持列表中声明了但之前没有处理）
        if event_type == "session_end":
            return self._transform_session_end(event, message_id, timestamp)
        
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
        
        # elif delta_type == "confirmation_request":
        #     zeno_delta_type = "clue"
        #     # 转换 HITL 请求为 clue 格式
        #     zeno_content = self._convert_hitl_to_clue(content)
        
        # 🆕 问数平台智能分析场景：直接透传 delta 类型
        elif delta_type in (
            "sql", "data", "chart", "report",  # 智能分析三件套 + 报告
            "intent", "application",            # 意图和应用状态
            "preface", "files", "mind", "clue",  # 其他通用类型
            "billing"                           # 🆕 计费信息
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
    
    # ===========================================================================
    # 工具结果增强（将 tool_result 拆分为多个 delta）
    # ===========================================================================
    
    def enhance_tool_result(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        tool_result: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        增强 tool_result，返回额外的 delta 列表
        
        根据工具类型和 api_name 生成额外的 message_delta 事件：
        - wenshu_api → 拆分为 sql/data/chart/report/intent 等（智能分析）
        - coze_api → 转换为 interface（系统配置，Ontology Builder）
        - dify_api → 转换为 mind（Mermaid 流程图，text2flowchart）
        - 其他特殊工具 → 根据 TOOL_TO_DELTA_TYPE 映射
        
        Args:
            tool_name: 工具名称（如 "api_calling"）
            tool_input: 工具输入参数（包含 api_name 等）
            tool_result: 工具返回结果（content_block 格式）
            
        Returns:
            delta 列表，每个元素是 {"type": "xxx", "content": "..."}
        """
        is_error = tool_result.get("is_error", False)
        result_content = tool_result.get("content", "")
        
        # 错误结果不增强
        if is_error:
            return []
        
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
                return self._generate_ontology_deltas(result_content)
            
            # 3. 流程图生成类 API（Dify text2flowchart）→ mind
            if api_name in FLOWCHART_API_NAMES:
                logger.debug(f"🔍 识别到流程图生成类 API: api_name={api_name}")
                return self._generate_flowchart_deltas(result_content)
        
        # 向后兼容：专用工具 wenshu_analytics（将废弃）
        if tool_name == "wenshu_analytics":
            return self._generate_analytics_deltas(result_content)
        
        # 检查是否需要发送特殊 delta（简单工具）
        delta_type = TOOL_TO_DELTA_TYPE.get(tool_name)
        if delta_type:
            logger.debug(f"🔧 生成特殊工具 delta: type={delta_type}, tool={tool_name}")
            return [self._create_delta(delta_type, result_content)]
        
        return []
    
    def _generate_analytics_deltas(self, result_content: str) -> List[Dict[str, Any]]:
        """
        为分析类 API（如问数平台）生成多个 delta
        
        分析类 API 返回的结果包含多个字段，每个字段对应一个 delta：
        - sql: SQL 查询语句
        - data: 查询结果数据
        - chart: 图表配置
        - report: 分析报告 {title, content}
        - intent_name: 意图名称
        
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
        
        # 检查是否成功
        if not result.get("success", False):
            logger.warning(f"⚠️ 分析类 API 返回失败: {result.get('error')}")
            return deltas
        
        logger.info(f"📊 分析类 API 结果处理: intent={result.get('intent_name')}")
        
        # 生成 intent delta（智能分析场景）
        intent_name = result.get("intent_name")
        if intent_name:
            intent_data = {
                "intent_id": result.get("intent", 2),  # 默认 2 = 智能分析
                "intent_name": intent_name,
                "platform": "analytics"  # 分析类 API 都是 analytics 场景
            }
            deltas.append(self._create_delta("intent", intent_data))
        
        # 生成 sql delta
        sql = result.get("sql")
        if sql:
            deltas.append(self._create_delta("sql", sql))
        
        # 生成 data delta
        data = result.get("data")
        if data:
            deltas.append(self._create_delta("data", data))
        
        # 生成 chart delta
        chart = result.get("chart")
        if chart:
            deltas.append(self._create_delta("chart", chart))
        
        # 生成 report delta
        report = result.get("report")
        if report:
            deltas.append(self._create_delta("report", report))
        
        # 生成 application delta（可选，包含 dashboard_id 等）
        dashboard_id = result.get("dashboard_id")
        if dashboard_id:
            app_data = {
                "application_id": dashboard_id,
                "name": "数据分析",
                "status": "success"
            }
            deltas.append(self._create_delta("application", app_data))
        
        return deltas
    
    def _generate_ontology_deltas(self, result_content: str) -> List[Dict[str, Any]]:
        """
        为系统搭建类 API（Coze Ontology Builder）生成 delta
        
        Coze SSE 返回格式（解析后）：
        - 最终结果通常在最后一个 Message 事件的 content 中
        - 包含系统配置（实体、属性、关系）
        
        生成的 delta 类型：
        - intent: 意图识别
        - interface: 系统配置（实体、属性、关系）
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
        
        # 生成 intent delta（系统搭建场景）
        intent_data = {
            "intent_id": 1,  # 1 = 系统搭建
            "intent_name": "系统搭建",
            "platform": "ontology"
        }
        deltas.append(self._create_delta("intent", intent_data))
        
        # 生成 interface delta（系统配置）
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
        
        deltas.append(self._create_delta("interface", interface_data))
        
        # 生成 application delta（构建状态）
        # 注意：这里不再使用 session_id，因为我们是返回 delta 列表
        app_data = {
            "application_id": "ontology_build",
            "name": "系统配置",
            "status": "success"
        }
        deltas.append(self._create_delta("application", app_data))
        
        return deltas
    
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
        
        # 生成 intent delta（系统搭建场景，流程图是其一部分）
        intent_data = {
            "intent_id": 1,  # 1 = 系统搭建
            "intent_name": "系统搭建",
            "platform": "flowchart"
        }
        deltas.append(self._create_delta("intent", intent_data))
        
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
            content: 内容（对象或字符串）
            
        Returns:
            delta 字典 {"type": "xxx", "content": "..."}
        """
        # 转换为 JSON 字符串（如果是对象）
        if isinstance(content, (dict, list)):
            content_str = json.dumps(content, ensure_ascii=False)
        else:
            content_str = str(content)
        
        logger.debug(f"📤 创建 delta: type={delta_type}")
        
        return {
            "type": delta_type,
            "content": content_str
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
