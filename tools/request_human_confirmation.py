"""
请求人类确认工具 (RequestHumanConfirmationTool)

HITL (Human-in-the-Loop) 核心工具，用于在 Agent 执行过程中请求用户确认或收集偏好。

支持的表单类型（confirmation_type）：
┌─────────────────┬────────────────────────────────────────────┐
│ 类型            │ 说明                                        │
├─────────────────┼────────────────────────────────────────────┤
│ yes_no          │ 简单的是/否确认                             │
│ single_choice   │ 单选题                                      │
│ multiple_choice │ 多选题                                      │
│ text_input      │ 文本输入                                    │
│ form            │ 复杂表单（多个问题组合，支持单选+多选混合）  │
└─────────────────┴────────────────────────────────────────────┘

工作流程：
1. Agent 调用此工具 → 创建 ConfirmationRequest
2. 通过 emit_event 发送 SSE 事件 → 前端渲染表单
3. 异步等待用户响应（不阻塞事件循环）
4. 用户提交 → HTTP POST 唤醒等待
5. 返回结果给 Agent → 继续执行

参考文档: docs/HITL-SSE-CONFIRMATION-DESIGN.md
"""

import json
import logging
from typing import Dict, Any, Optional, List, Callable, Awaitable, Union

from tools.base import BaseTool
from core.confirmation_manager import (
    get_confirmation_manager,
    ConfirmationType
)

logger = logging.getLogger(__name__)


# ==================== 常量定义 ====================

# 默认选项
DEFAULT_YES_NO_OPTIONS = ["confirm", "cancel"]
DEFAULT_TIMEOUT = 60
FORM_TIMEOUT = 120  # 复杂表单给更多时间


# ==================== 问题类型定义 ====================

class QuestionType:
    """问题类型常量"""
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    TEXT_INPUT = "text_input"


# ==================== 工具类 ====================

class RequestHumanConfirmationTool(BaseTool):
    """
    请求人类确认工具
    
    支持多种表单类型，覆盖从简单确认到复杂表单的所有场景。
    
    使用示例：
    
    1. 简单确认（yes_no）
    ```python
    request_human_confirmation(
        question="是否删除文件 data.csv？",
        confirmation_type="yes_no"
    )
    # 返回: {"response": "confirm"} 或 {"response": "cancel"}
    ```
    
    2. 单选（single_choice）
    ```python
    request_human_confirmation(
        question="选择 PPT 风格",
        confirmation_type="single_choice",
        options=["商务专业", "科技未来感", "简约清新"]
    )
    # 返回: {"response": "商务专业"}
    ```
    
    3. 多选（multiple_choice）
    ```python
    request_human_confirmation(
        question="选择内容重点（可多选）",
        confirmation_type="multiple_choice",
        options=["政策法规", "产业动态", "技术突破", "投融资"]
    )
    # 返回: {"response": ["政策法规", "产业动态"]}
    ```
    
    4. 复杂表单（form）
    ```python
    request_human_confirmation(
        question="收集用户偏好",
        confirmation_type="form",
        description="请选择您的偏好以生成更符合需求的内容",
        questions=[
            {
                "id": "target_audience",
                "label": "目标受众",
                "type": "single_choice",
                "options": ["公司管理层", "技术团队", "行业公众"],
                "default": "公司管理层"
            },
            {
                "id": "content_focus",
                "label": "内容重点（可多选）",
                "type": "multiple_choice",
                "options": ["政策法规", "产业动态", "技术突破"],
                "default": ["政策法规"]
            }
        ]
    )
    # 返回: {"response": {"target_audience": "公司管理层", "content_focus": ["政策法规", "产业动态"]}}
    ```
    """
    
    @property
    def name(self) -> str:
        return "request_human_confirmation"
    
    @property
    def description(self) -> str:
        return """请求用户确认或收集用户偏好。

支持的表单类型：
- yes_no: 简单的是/否确认（如：删除文件、执行危险操作）
- single_choice: 单选题（如：选择风格、选择方案）
- multiple_choice: 多选题（如：选择多个重点内容）
- text_input: 文本输入（如：输入自定义名称）
- form: 复杂表单（如：同时收集目标受众、内容重点、结构偏好）

调用此工具后会暂停执行，等待用户在前端界面响应后继续。"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "问题内容或表单标题"
                },
                "confirmation_type": {
                    "type": "string",
                    "enum": ["yes_no", "single_choice", "multiple_choice", "text_input", "form"],
                    "description": "表单类型：yes_no（是否确认）、single_choice（单选）、multiple_choice（多选）、text_input（文本输入）、form（复杂表单）",
                    "default": "yes_no"
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "选项列表，用于 single_choice 和 multiple_choice 类型"
                },
                "default_value": {
                    "description": "默认值。single_choice 为字符串，multiple_choice 为数组"
                },
                "questions": {
                    "type": "array",
                    "description": "问题列表，仅用于 form 类型。每个问题包含 id、label、type、options 等字段",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "问题ID，作为返回结果的 key"},
                            "label": {"type": "string", "description": "问题标签，显示给用户"},
                            "type": {"type": "string", "enum": ["single_choice", "multiple_choice", "text_input"]},
                            "options": {"type": "array", "items": {"type": "string"}, "description": "选项列表"},
                            "default": {"description": "默认值"},
                            "hint": {"type": "string", "description": "提示文字"},
                            "required": {"type": "boolean", "description": "是否必填", "default": True}
                        },
                        "required": ["id", "label", "type"]
                    }
                },
                "description": {
                    "type": "string",
                    "description": "表单描述或补充说明"
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时时间（秒）。简单确认默认60秒，复杂表单默认120秒",
                    "default": 60
                }
            },
            "required": ["question"]
        }
    
    async def execute(
        self,
        question: str,
        confirmation_type: str = "yes_no",
        options: Optional[List[str]] = None,
        default_value: Optional[Union[str, List[str]]] = None,
        questions: Optional[List[Dict[str, Any]]] = None,
        description: str = "",
        timeout: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        emit_event: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        session_id: str = "",
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行确认请求
        
        Args:
            question: 问题内容或表单标题
            confirmation_type: 表单类型
            options: 选项列表
            default_value: 默认值
            questions: 问题列表（form 类型）
            description: 表单描述
            timeout: 超时时间（秒）
            metadata: 额外元数据
            emit_event: SSE 事件发射回调（由 Agent 注入）
            session_id: 会话ID
            
        Returns:
            {
                "success": True,
                "response": "confirm" | ["选项1", "选项2"] | {"field1": "value1", ...},
                "timed_out": False
            }
        """
        # 解析确认类型
        conf_type = self._parse_confirmation_type(confirmation_type)
        
        # 设置默认超时
        if timeout is None:
            timeout = FORM_TIMEOUT if conf_type == ConfirmationType.FORM else DEFAULT_TIMEOUT
        
        # 处理选项
        options = self._process_options(conf_type, options)
        
        # 构建请求元数据
        request_metadata = self._build_metadata(
            conf_type=conf_type,
            description=description,
            questions=questions,
            default_value=default_value,
            extra_metadata=metadata
        )
        
        logger.info(f"HITL 请求: type={confirmation_type}, question={question[:50]}...")
        
        # 获取确认管理器
        manager = get_confirmation_manager()
        
        # 1. 创建确认请求
        request = manager.create_request(
            question=question,
            options=options,
            timeout=timeout,
            confirmation_type=conf_type,
            session_id=session_id,
            metadata=request_metadata
        )
        
        logger.info(f"确认请求已创建: request_id={request.request_id}")
        
        # 2. 发送 SSE 事件到前端
        await self._emit_sse_event(
            emit_event=emit_event,
            request=request,
            description=description,
            questions=questions,
            conf_type=conf_type
        )
        
        # 3. 异步等待用户响应
        result = await manager.wait_for_response(request.request_id, timeout)
        
        # 4. 处理并返回结果
        return self._process_response(result, conf_type, timeout)
    
    # ==================== 私有方法 ====================
    
    def _parse_confirmation_type(self, type_str: str) -> ConfirmationType:
        """解析确认类型字符串"""
        try:
            return ConfirmationType(type_str)
        except ValueError:
            logger.warning(f"未知的确认类型: {type_str}，使用默认 yes_no")
            return ConfirmationType.YES_NO
    
    def _process_options(
        self, 
        conf_type: ConfirmationType, 
        options: Optional[List[str]]
    ) -> Optional[List[str]]:
        """处理选项列表"""
        # yes_no 类型使用默认选项
        if conf_type == ConfirmationType.YES_NO and not options:
            return DEFAULT_YES_NO_OPTIONS
        return options
    
    def _build_metadata(
        self,
        conf_type: ConfirmationType,
        description: str,
        questions: Optional[List[Dict[str, Any]]],
        default_value: Optional[Union[str, List[str]]],
        extra_metadata: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """构建请求元数据"""
        metadata = extra_metadata.copy() if extra_metadata else {}
        
        # 添加描述
        if description:
            metadata["description"] = description
        
        # 添加默认值
        if default_value is not None:
            metadata["default_value"] = default_value
        
        # form 类型添加问题列表
        if conf_type == ConfirmationType.FORM:
            metadata["form_type"] = "form"
            metadata["questions"] = questions or []
        
        return metadata
    
    async def _emit_sse_event(
        self,
        emit_event: Optional[Callable[[Dict[str, Any]], Awaitable[None]]],
        request,
        description: str,
        questions: Optional[List[Dict[str, Any]]],
        conf_type: ConfirmationType
    ) -> None:
        """发送 SSE 事件到前端（使用 message_delta 格式）"""
        if not emit_event:
            logger.warning("emit_event 回调未注入，无法发送 SSE 事件到前端")
            return
        
        try:
            # 构建 HITL 请求内容
            hitl_content = {
                **request.to_dict(),
                "description": description,
                "questions": questions if conf_type == ConfirmationType.FORM else None
            }
            
            # 使用 message_delta 格式，符合事件协议规范
            event_data = {
                "type": "message_delta",
                "data": {
                    "delta": {
                        "type": "confirmation_request",
                        "content": json.dumps(hitl_content, ensure_ascii=False)
                    }
                }
            }
            await emit_event(event_data)
            logger.debug("SSE 事件已发送到前端")
        except Exception as e:
            logger.error(f"发送 SSE 事件失败: {e}", exc_info=True)
    
    def _process_response(
        self, 
        result: Dict[str, Any], 
        conf_type: ConfirmationType,
        timeout: int
    ) -> Dict[str, Any]:
        """处理用户响应"""
        # 超时处理
        if result.get("timed_out"):
            logger.warning(f"用户响应超时 ({timeout}s)")
            return {
                "success": False,
                "timed_out": True,
                "response": "timeout",
                "message": f"用户未在 {timeout} 秒内响应"
            }
        
        response = result.get("response")
        
        # form 类型：尝试解析 JSON
        if conf_type == ConfirmationType.FORM and isinstance(response, str):
            try:
                response = json.loads(response)
            except json.JSONDecodeError:
                logger.warning(f"无法解析 form 响应为 JSON: {response[:100]}")
        
        logger.info(f"用户已响应: {type(response).__name__}")
        
        return {
            "success": True,
            "timed_out": False,
            "response": response,
            "metadata": result.get("metadata", {})
        }


# ==================== 便捷函数 ====================

def create_request_human_confirmation_tool() -> RequestHumanConfirmationTool:
    """
    创建 RequestHumanConfirmationTool 实例
    
    Returns:
        RequestHumanConfirmationTool 实例
    """
    return RequestHumanConfirmationTool()
