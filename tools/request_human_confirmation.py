"""
请求人类确认工具 (RequestHumanConfirmationTool)

HITL (Human-in-the-Loop) 核心工具，用于在 Agent 执行过程中请求用户确认。

核心机制：
1. LLM 调用此工具 → 创建 ConfirmationRequest
2. 通过 emit_event 回调发送 SSE 事件 → 前端显示确认框
3. 异步等待用户响应（阻塞当前工具，不阻塞事件循环）
4. 用户通过 HTTP POST 提交响应 → 唤醒等待的工具
5. 返回结果给 LLM → Agent 根据响应继续执行

使用场景：
- 删除文件/数据等危险操作
- 修改重要配置
- 执行不可逆操作
- 需要用户选择方案/参数

参考文档: docs/HITL-SSE-CONFIRMATION-DESIGN.md
"""

import logging
from typing import Dict, Any, Optional, List, Callable, Awaitable

from tools.base import BaseTool
from core.confirmation_manager import (
    get_confirmation_manager,
    ConfirmationType
)

logger = logging.getLogger(__name__)


class RequestHumanConfirmationTool(BaseTool):
    """
    请求人类确认工具
    
    当 LLM 需要用户确认时调用此工具，会：
    1. 创建确认请求
    2. 发送 SSE 事件到前端
    3. 异步等待用户响应
    4. 返回响应结果给 LLM
    
    工具参数：
    - question: 要询问用户的问题
    - options: 可选项列表，默认 ["confirm", "cancel"]
    - timeout: 超时时间（秒），默认 60
    - metadata: 额外信息（用于前端展示）
    
    返回结果：
    - success: 是否成功获取响应
    - response: 用户响应 ("confirm", "cancel", "timeout", 或自定义选项)
    - timed_out: 是否超时
    """
    
    @property
    def name(self) -> str:
        return "request_human_confirmation"
    
    @property
    def description(self) -> str:
        return """请求用户确认操作。适用于以下场景：
- 删除文件或数据等危险操作
- 修改重要配置
- 执行不可逆操作
- 需要用户选择方案或参数
- 任何需要人工干预的决策

调用此工具后，会暂停执行并等待用户响应。用户可以确认、取消或选择其他选项。"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "要询问用户的问题，应该清晰描述操作内容和影响"
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "可选项列表，默认 ['confirm', 'cancel']。可以自定义选项如 ['商务风格', '学术风格', '创意风格']",
                    "default": ["confirm", "cancel"]
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时时间（秒），默认 60 秒",
                    "default": 60
                },
                "confirmation_type": {
                    "type": "string",
                    "enum": ["yes_no", "single_choice", "multiple_choice", "text_input"],
                    "description": "确认类型，默认 yes_no",
                    "default": "yes_no"
                },
                "metadata": {
                    "type": "object",
                    "description": "额外信息，用于前端展示（如操作详情、影响范围等）"
                }
            },
            "required": ["question"]
        }
    
    async def execute(
        self,
        question: str,
        options: Optional[List[str]] = None,
        timeout: int = 60,
        confirmation_type: str = "yes_no",
        metadata: Optional[Dict[str, Any]] = None,
        # 🔥 关键：由 Agent 注入的回调
        emit_event: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        session_id: str = "",
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行确认请求
        
        Args:
            question: 要询问用户的问题
            options: 可选项列表
            timeout: 超时时间（秒）
            confirmation_type: 确认类型
            metadata: 额外信息
            emit_event: 🔥 事件发射回调（由 Agent 注入）
            session_id: 会话ID
            
        Returns:
            {
                "success": bool,
                "response": str,  # "confirm", "cancel", "timeout", 或自定义选项
                "timed_out": bool,
                "message": str  # 可选的消息
            }
        """
        logger.info(f"HITL 工具被调用: question={question[:50]}...")
        
        # 获取管理器
        manager = get_confirmation_manager()
        
        # 解析确认类型
        try:
            conf_type = ConfirmationType(confirmation_type)
        except ValueError:
            conf_type = ConfirmationType.YES_NO
        
        # 1. 创建确认请求
        request = manager.create_request(
            question=question,
            options=options,
            timeout=timeout,
            confirmation_type=conf_type,
            session_id=session_id,
            metadata=metadata or {}
        )
        
        logger.info(f"创建确认请求: request_id={request.request_id}")
        
        # 2. 🔥 发送 SSE 事件（通过 emit_event 回调）
        if emit_event:
            try:
                event_data = {
                    "type": "human_confirmation_request",
                    "data": request.to_dict()
                }
                await emit_event(event_data)
                logger.debug(f"SSE 事件已发送: {event_data}")
            except Exception as e:
                logger.error(f"发送 SSE 事件失败: {e}")
        else:
            logger.warning("emit_event 回调未注入，无法发送 SSE 事件")
        
        # 3. 🔥 异步等待用户响应（阻塞当前工具，但不阻塞事件循环）
        result = await manager.wait_for_response(request.request_id, timeout)
        
        logger.info(f"收到用户响应: request_id={request.request_id}, response={result.get('response')}")
        
        # 4. 返回结果给 LLM
        return result


# ==================== 便捷函数 ====================

def create_request_human_confirmation_tool() -> RequestHumanConfirmationTool:
    """创建 RequestHumanConfirmationTool 实例"""
    return RequestHumanConfirmationTool()

