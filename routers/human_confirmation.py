"""
人类确认 HTTP 接口

提供 HTTP 端点接收用户对 HITL 确认请求的响应。

工作流程：
1. Agent 调用 request_human_confirmation 工具
2. 工具通过 SSE 发送确认请求到前端
3. 前端显示确认对话框
4. 用户点击确认/取消 → 调用此接口提交响应
5. 此接口调用 ConfirmationManager.set_response() 唤醒等待的工具
6. 工具获取响应后返回给 LLM

接口列表：
- POST /api/v1/human-confirmation/{request_id} - 提交确认响应
- GET /api/v1/human-confirmation/{request_id} - 获取请求详情
- GET /api/v1/human-confirmation/pending - 获取所有待处理请求

参考文档: docs/HITL-SSE-CONFIRMATION-DESIGN.md
"""

import logging
from typing import Optional, Dict, Any, List, Union

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.confirmation_manager import (
    get_confirmation_manager,
    ConfirmationRequest
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/human-confirmation", tags=["HITL"])


# ==================== 请求/响应模型 ====================

class ConfirmationResponseBody(BaseModel):
    """确认响应请求体"""
    response: Union[str, List[str], Dict[str, Any]] = Field(
        ...,
        description="用户响应：字符串（yes_no/single_choice/text_input）、数组（multiple_choice）、或对象（form）"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="额外的元数据"
    )


class ConfirmationSubmitResponse(BaseModel):
    """提交响应的返回"""
    code: int = 200
    message: str = "响应已提交"
    data: Dict[str, Any]


class ConfirmationRequestResponse(BaseModel):
    """确认请求详情的返回"""
    code: int = 200
    message: str = "success"
    data: Optional[Dict[str, Any]]


class PendingRequestsResponse(BaseModel):
    """待处理请求列表的返回"""
    code: int = 200
    message: str = "success"
    data: List[Dict[str, Any]]


# ==================== 接口实现 ====================
# 注意：固定路径必须在动态路径 /{request_id} 之前定义！

@router.get(
    "/pending",
    response_model=PendingRequestsResponse,
    summary="获取待处理的确认请求",
    description="获取所有待处理的确认请求列表"
)
async def get_pending_requests(session_id: Optional[str] = None):
    """
    获取待处理的确认请求
    
    Args:
        session_id: 可选，按会话ID过滤
        
    Returns:
        待处理请求列表
    """
    manager = get_confirmation_manager()
    
    requests = manager.get_pending_requests(session_id)
    
    return PendingRequestsResponse(
        code=200,
        message="success",
        data=[r.to_dict() for r in requests]
    )


@router.get(
    "/stats",
    summary="获取统计信息",
    description="获取确认请求的统计信息"
)
async def get_stats():
    """获取统计信息"""
    manager = get_confirmation_manager()
    
    return {
        "code": 200,
        "message": "success",
        "data": manager.stats()
    }


# ==================== 动态路径接口（必须放在固定路径之后）====================

@router.post(
    "/{request_id}",
    response_model=ConfirmationSubmitResponse,
    summary="提交确认响应",
    description="用户提交对确认请求的响应，唤醒等待的工具"
)
async def submit_confirmation(
    request_id: str,
    body: ConfirmationResponseBody
):
    """
    提交用户确认响应
    
    Args:
        request_id: 确认请求ID（从 SSE 事件中获取）
        body: 响应内容
        
    Returns:
        提交结果
        
    Raises:
        HTTPException 404: 请求不存在或已过期
    """
    logger.info(f"收到确认响应: request_id={request_id}, response={body.response}")
    
    manager = get_confirmation_manager()
    
    # 检查请求是否存在
    request = manager.get_request(request_id)
    if not request:
        logger.warning(f"确认请求不存在: request_id={request_id}")
        raise HTTPException(
            status_code=404,
            detail=f"确认请求 {request_id} 不存在或已过期"
        )
    
    # 检查是否过期
    if request.is_expired():
        logger.warning(f"确认请求已过期: request_id={request_id}")
        raise HTTPException(
            status_code=410,  # Gone
            detail=f"确认请求 {request_id} 已过期"
        )
    
    # 🔥 设置响应，唤醒等待的工具
    success = manager.set_response(request_id, body.response, body.metadata)
    
    if not success:
        raise HTTPException(
            status_code=500,
            detail="设置响应失败"
        )
    
    return ConfirmationSubmitResponse(
        code=200,
        message="响应已提交",
        data={
            "request_id": request_id,
            "response": body.response
        }
    )


@router.get(
    "/{request_id}",
    response_model=ConfirmationRequestResponse,
    summary="获取确认请求详情",
    description="获取指定确认请求的详细信息"
)
async def get_confirmation_request(request_id: str):
    """
    获取确认请求详情
    
    Args:
        request_id: 确认请求ID
        
    Returns:
        请求详情
        
    Raises:
        HTTPException 404: 请求不存在
    """
    manager = get_confirmation_manager()
    
    request = manager.get_request(request_id)
    if not request:
        raise HTTPException(
            status_code=404,
            detail=f"确认请求 {request_id} 不存在"
        )
    
    return ConfirmationRequestResponse(
        code=200,
        message="success",
        data=request.to_dict()
    )


@router.delete(
    "/{request_id}",
    summary="取消确认请求",
    description="取消指定的确认请求"
)
async def cancel_confirmation_request(request_id: str):
    """
    取消确认请求
    
    Args:
        request_id: 确认请求ID
        
    Returns:
        取消结果
    """
    manager = get_confirmation_manager()
    
    success = manager.cancel_request(request_id)
    
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"确认请求 {request_id} 不存在"
        )
    
    return {
        "code": 200,
        "message": "请求已取消",
        "data": {"request_id": request_id}
    }

