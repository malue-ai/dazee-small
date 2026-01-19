"""
HITL 工具 (Human-in-the-Loop)

用于在 Agent 执行过程中请求用户输入或收集偏好。

支持的输入类型（input_type）：
┌─────────────┬────────────────────────────────────────────────────────┐
│ 类型        │ 说明                                                    │
├─────────────┼────────────────────────────────────────────────────────┤
│ form        │ 结构化表单（支持单选/多选/文本问题组合）                │
│ text_input  │ 简单文本输入                                            │
└─────────────┴────────────────────────────────────────────────────────┘

form 中的问题类型（question.type）：
- single_choice: 单选题（包含 yes/no 确认）
- multiple_choice: 多选题
- text_input: 文本输入

工作流程：
1. Agent 调用此工具 → 创建 ConfirmationRequest
2. 通过 emit_event 发送 SSE 事件 → 前端渲染表单
3. 异步等待用户响应（不阻塞事件循环）
4. 用户提交 → HTTP POST 唤醒等待
5. 返回结果给 Agent → 继续执行

参考文档: docs/HITL-SSE-CONFIRMATION-DESIGN.md
"""

import json
from logger import get_logger
from typing import Dict, Any, Optional, List, Callable, Awaitable, Union

from tools.base import BaseTool
from core.confirmation_manager import (
    get_confirmation_manager,
    ConfirmationType
)

logger = get_logger(__name__)


# ==================== 常量定义 ====================

DEFAULT_TIMEOUT = 60        # 默认超时时间
FORM_TIMEOUT = 120          # 表单默认超时（给更多时间）


# ==================== 问题类型定义 ====================

class QuestionType:
    """
    form 中的问题类型常量
    
    - SINGLE_CHOICE: 单选题（包含 yes/no 确认场景）
    - MULTIPLE_CHOICE: 多选题
    - TEXT_INPUT: 文本输入
    """
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    TEXT_INPUT = "text_input"


# ==================== 工具类 ====================

class HITLTool(BaseTool):
    """
    HITL (Human-in-the-Loop) 工具
    
    只有两种输入类型：form（结构化表单）和 text_input（简单文本）。
    
    使用示例：
    
    1. 简单文本输入（text_input）
    ```python
    hitl(
        title="请输入项目名称",
        input_type="text_input",
        description="用于生成报告的标题"
    )
    # 返回: {"response": "2024年Q1季度报告"}
    ```
    
    2. 是/否确认（form + single_choice）
    ```python
    hitl(
        title="操作确认",
        input_type="form",
        questions=[{
            "id": "confirm",
            "label": "是否删除文件 data.csv？",
            "type": "single_choice",
            "options": ["确认", "取消"]
        }]
    )
    # 返回: {"response": {"confirm": "确认"}}
    ```
    
    3. 单选题（form + single_choice）
    ```python
    hitl(
        title="选择 PPT 风格",
        input_type="form",
        questions=[{
            "id": "style",
            "label": "请选择风格",
            "type": "single_choice",
            "options": ["商务专业", "科技未来感", "简约清新"],
            "default": "商务专业"
        }]
    )
    # 返回: {"response": {"style": "商务专业"}}
    ```
    
    4. 多问题表单（form）
    ```python
    hitl(
        title="收集用户偏好",
        input_type="form",
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
            },
            {
                "id": "additional_notes",
                "label": "补充说明",
                "type": "text_input",
                "hint": "可选，填写其他需求",
                "required": False
            }
        ]
    )
    # 返回: {"response": {"target_audience": "公司管理层", "content_focus": ["政策法规"], "additional_notes": ""}}
    ```
    """
    
    @property
    def name(self) -> str:
        return "hitl"
    
    @property
    def description(self) -> str:
        return """HITL (Human-in-the-Loop) 工具，请求用户输入或收集用户偏好。

支持的输入类型：
- form: 结构化表单（支持单选/多选/文本问题组合，可用于确认、选择、多问题表单等场景）
- text_input: 简单文本输入（用户输入自定义内容）

调用此工具后会暂停执行，等待用户在前端界面响应后继续。"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "表单标题或提示信息"
                },
                "input_type": {
                    "type": "string",
                    "enum": ["form", "text_input"],
                    "description": "输入类型：form（结构化表单）、text_input（简单文本输入）",
                    "default": "form"
                },
                "questions": {
                    "type": "array",
                    "description": "问题列表，用于 form 类型。每个问题包含 id、label、type、options 等字段",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "问题ID，作为返回结果的 key"},
                            "label": {"type": "string", "description": "问题标签，显示给用户"},
                            "type": {
                                "type": "string", 
                                "enum": ["single_choice", "multiple_choice", "text_input"],
                                "description": "问题类型：single_choice（单选，包括是/否确认）、multiple_choice（多选）、text_input（文本）"
                            },
                            "options": {"type": "array", "items": {"type": "string"}, "description": "选项列表，用于 single_choice 和 multiple_choice"},
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
                    "description": "超时时间（秒）。默认 120 秒",
                    "default": 120
                }
            },
            "required": ["title"]
        }
    
    async def execute(
        self,
        title: str,
        input_type: str = "form",
        questions: Optional[List[Dict[str, Any]]] = None,
        description: str = "",
        timeout: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        session_id: str = "",
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行用户输入请求
        
        Args:
            title: 表单标题或提示信息
            input_type: 输入类型（form 或 text_input）
            questions: 问题列表（form 类型）
            description: 表单描述
            timeout: 超时时间（秒）
            metadata: 额外元数据
            session_id: 会话ID
            
        Returns:
            {
                "success": True,
                "response": "用户输入" | {"field1": "value1", ...},
                "timed_out": False
            }
        """
        # 解析输入类型
        conf_type = self._parse_input_type(input_type)
        
        # 设置默认超时
        if timeout is None:
            timeout = FORM_TIMEOUT
        
        # 构建请求元数据
        request_metadata = self._build_metadata(
            conf_type=conf_type,
            description=description,
            questions=questions,
            extra_metadata=metadata
        )
        
        logger.info(f"HITL 请求: type={input_type}, title={title[:50]}...")
        
        # 获取确认管理器
        manager = get_confirmation_manager()
        
        # 1. 创建确认请求
        request = manager.create_request(
            question=title,
            options=None,
            timeout=timeout,
            confirmation_type=conf_type,
            session_id=session_id,
            metadata=request_metadata
        )
        
        logger.info(f"输入请求已创建: request_id={request.request_id}")
        
        # 2. 前端会通过 tool_use 事件自动显示表单，无需发送额外的 SSE 事件
        logger.debug("等待用户通过前端界面响应...")
        
        # 3. 异步等待用户响应
        result = await manager.wait_for_response(request.request_id, timeout)
        
        # 4. 处理并返回结果
        return self._process_response(result, conf_type, timeout)
    
    # ==================== 私有方法 ====================
    
    def _parse_input_type(self, type_str: str) -> ConfirmationType:
        """解析输入类型字符串"""
        try:
            return ConfirmationType(type_str)
        except ValueError:
            logger.warning(f"未知的输入类型: {type_str}，使用默认 form")
            return ConfirmationType.FORM
    
    def _build_metadata(
        self,
        conf_type: ConfirmationType,
        description: str,
        questions: Optional[List[Dict[str, Any]]],
        extra_metadata: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """构建请求元数据"""
        metadata = extra_metadata.copy() if extra_metadata else {}
        
        # 添加描述
        if description:
            metadata["description"] = description
        
        # form 类型添加问题列表
        if conf_type == ConfirmationType.FORM:
            metadata["questions"] = questions or []
        
        return metadata
    
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

def create_hitl_tool() -> HITLTool:
    """
    创建 HITLTool 实例
    
    Returns:
        HITLTool 实例
    """
    return HITLTool()
