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

from core.tool.base import BaseTool, ToolContext
from models.hitl import ConfirmationType
from services.confirmation_service import get_confirmation_manager

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
    HITL (Human-in-the-Loop) 工具（input_schema 由 capabilities.yaml 定义）
    
    支持两种输入类型：form（结构化表单）和 text_input（简单文本）。
    """
    
    name = "hitl"
    
    async def execute(
        self,
        params: Dict[str, Any],
        context: ToolContext
    ) -> Dict[str, Any]:
        """
        执行用户输入请求
        
        Args:
            params: 工具输入参数
                - title: 表单标题或提示信息
                - input_type: 输入类型（form 或 text_input）
                - questions: 问题列表（form 类型）
                - description: 表单描述
                - timeout: 超时时间（秒）
                - metadata: 额外元数据
            context: 工具执行上下文
            
        Returns:
            {
                "success": True,
                "response": "用户输入" | {"field1": "value1", ...},
                "timed_out": False
            }
        """
        # 从 params 提取参数
        title = params.get("title", "")
        if not title:
            return {"success": False, "error": "缺少必需参数: title"}
        
        input_type = params.get("input_type", "form")
        questions = params.get("questions")
        description = params.get("description", "")
        timeout = params.get("timeout")
        metadata = params.get("metadata")
        
        # 从 context 获取 session_id
        session_id = context.session_id or ""
        
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
