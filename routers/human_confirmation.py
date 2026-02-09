"""
人类确认路由层

职责：
- HTTP 请求解析
- 调用 ConfirmationService 处理业务逻辑
- 异常转换为 HTTP 异常

工作流程：
1. Agent 调用 hitl 工具
2. 工具通过 SSE 发送确认请求到前端
3. 前端显示确认对话框
4. 用户点击确认/取消 → 调用此接口提交响应
5. 此接口调用 ConfirmationService 唤醒等待的工具
6. 工具获取响应后返回给 LLM

接口列表：
- POST /api/v1/human-confirmation/{request_id} - 提交确认响应
- GET /api/v1/human-confirmation/{request_id} - 获取请求详情
- GET /api/v1/human-confirmation/pending - 获取所有待处理请求

参考文档: docs/HITL-SSE-CONFIRMATION-DESIGN.md
"""

from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from logger import get_logger
from services.confirmation_service import (
    ConfirmationExpiredError,
    ConfirmationNotFoundError,
    ConfirmationResponseError,
    ConfirmationService,
    get_confirmation_service,
)

logger = get_logger("human_confirmation_router")

router = APIRouter(prefix="/api/v1/human-confirmation", tags=["HITL"])

# 获取服务实例
confirmation_service = get_confirmation_service()


# ==================== 请求/响应模型 ====================


class ConfirmationResponseBody(BaseModel):
    """确认响应请求体"""

    response: Union[str, List[str], Dict[str, Any]] = Field(
        ..., description="用户响应：字符串（text_input）或对象（form）"
    )
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="额外的元数据")


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
    description="获取所有待处理的确认请求列表",
)
async def get_pending_requests(session_id: Optional[str] = None):
    """
    获取待处理的确认请求

    Args:
        session_id: 可选，按会话ID过滤

    Returns:
        待处理请求列表
    """
    requests = confirmation_service.get_pending_requests(session_id)

    return PendingRequestsResponse(
        code=200, message="success", data=[r.to_dict() for r in requests]
    )


@router.get("/stats", summary="获取统计信息", description="获取确认请求的统计信息")
async def get_stats():
    """获取统计信息"""
    return {"code": 200, "message": "success", "data": confirmation_service.get_stats()}


# ==================== 动态路径接口（必须放在固定路径之后）====================


@router.post(
    "/{session_id}",
    response_model=ConfirmationSubmitResponse,
    summary="提交确认响应",
    description="用户提交对确认请求的响应，唤醒等待的工具",
)
async def submit_confirmation(session_id: str, body: ConfirmationResponseBody):
    """
    提交用户确认响应

    Args:
        session_id: 会话ID（前端已知，同时也是确认请求的唯一标识）
        body: 响应内容

    Returns:
        提交结果

    Raises:
        HTTPException 404: 请求不存在或已过期
        HTTPException 410: 请求已过期
        HTTPException 500: 设置响应失败
    """
    try:
        result = confirmation_service.submit_response(session_id, body.response, body.metadata)

        return ConfirmationSubmitResponse(code=200, message="响应已提交", data=result)

    except ConfirmationNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"确认请求（session_id={session_id}）不存在或已过期"
        )
    except ConfirmationExpiredError:
        raise HTTPException(
            status_code=410, detail=f"确认请求（session_id={session_id}）已过期"  # Gone
        )
    except ConfirmationResponseError:
        raise HTTPException(status_code=500, detail="设置响应失败")


@router.get(
    "/{request_id}",
    response_model=ConfirmationRequestResponse,
    summary="获取确认请求详情",
    description="获取指定确认请求的详细信息",
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
    try:
        request = confirmation_service.get_request(request_id)

        return ConfirmationRequestResponse(code=200, message="success", data=request.to_dict())

    except ConfirmationNotFoundError:
        raise HTTPException(status_code=404, detail=f"确认请求 {request_id} 不存在")


@router.delete("/{request_id}", summary="取消确认请求", description="取消指定的确认请求")
async def cancel_confirmation_request(request_id: str):
    """
    取消确认请求

    Args:
        request_id: 确认请求ID

    Returns:
        取消结果
    """
    try:
        confirmation_service.cancel_request(request_id)

        return {"code": 200, "message": "请求已取消", "data": {"request_id": request_id}}

    except ConfirmationNotFoundError:
        raise HTTPException(status_code=404, detail=f"确认请求 {request_id} 不存在")
