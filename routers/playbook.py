"""
Playbook 策略库路由层

职责：
- 策略列表查询
- 策略详情查询
- 策略审核（approve / reject / dismiss）
- WebSocket 推送的 playbook_suggestion 的用户响应
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.playbook import PlaybookManager, PlaybookStatus, create_playbook_manager
from logger import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/v1/playbook",
    tags=["playbook"],
)


# ==================== 请求/响应模型 ====================


class PlaybookEntryResponse(BaseModel):
    """策略条目响应"""

    id: str
    name: str
    description: str
    trigger: Dict[str, Any] = Field(default_factory=dict)
    strategy: Dict[str, Any] = Field(default_factory=dict)
    tool_sequence: List[Dict[str, Any]] = Field(default_factory=list)
    quality_metrics: Dict[str, float] = Field(default_factory=dict)
    status: str
    source: str
    usage_count: int = 0
    created_at: str
    updated_at: str
    reviewed_by: Optional[str] = None
    review_notes: Optional[str] = None
    last_used_at: Optional[str] = None
    is_stale: bool = False


class PlaybookListResponse(BaseModel):
    """策略列表响应"""

    success: bool = True
    entries: List[PlaybookEntryResponse]
    stats: Dict[str, Any] = Field(default_factory=dict)


class PlaybookActionRequest(BaseModel):
    """策略操作请求（approve / reject / dismiss / deprecate）"""

    action: str = Field(..., description="操作类型: approve / reject / dismiss / deprecate")
    reviewer: str = Field(default="user", description="审核人")
    notes: Optional[str] = Field(default=None, description="审核备注")


class PlaybookActionResponse(BaseModel):
    """策略操作响应"""

    success: bool
    message: str
    playbook_id: str


# ==================== 辅助函数 ====================


async def _get_manager() -> PlaybookManager:
    """获取并加载 PlaybookManager"""
    manager = create_playbook_manager()
    await manager.load_all_async()
    return manager


def _entry_to_response(entry) -> PlaybookEntryResponse:
    """PlaybookEntry → PlaybookEntryResponse"""
    data = entry.to_dict()
    data["is_stale"] = entry.is_stale()
    return PlaybookEntryResponse(**data)


# ==================== 路由 ====================


@router.get("", response_model=PlaybookListResponse)
async def list_playbooks(
    status: Optional[str] = None,
    source: Optional[str] = None,
):
    """
    列出所有策略

    Query Params:
        status: 按状态过滤 (draft / pending / approved / rejected / deprecated)
        source: 按来源过滤 (auto / manual / import)
    """
    manager = await _get_manager()

    filter_status = None
    if status:
        try:
            filter_status = PlaybookStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"无效的状态值: {status}，"
                f"支持: {', '.join(s.value for s in PlaybookStatus)}",
            )
    entries = manager.list_all(status=filter_status, source=source)

    return PlaybookListResponse(
        entries=[_entry_to_response(e) for e in entries],
        stats=manager.get_stats(),
    )


@router.get("/{playbook_id}", response_model=PlaybookEntryResponse)
async def get_playbook(playbook_id: str):
    """获取策略详情"""
    manager = await _get_manager()
    entry = manager.get(playbook_id)

    if not entry:
        raise HTTPException(status_code=404, detail=f"策略 {playbook_id} 不存在")

    return _entry_to_response(entry)


@router.post("/{playbook_id}/action", response_model=PlaybookActionResponse)
async def playbook_action(playbook_id: str, request: PlaybookActionRequest):
    """
    对策略执行操作

    支持的 action:
    - approve: 审核通过（PENDING_REVIEW → APPROVED）
    - reject: 审核拒绝（PENDING_REVIEW → REJECTED）
    - dismiss: 忽略/删除策略
    - deprecate: 废弃策略（APPROVED → DEPRECATED）
    """
    manager = await _get_manager()
    entry = manager.get(playbook_id)

    if not entry:
        raise HTTPException(status_code=404, detail=f"策略 {playbook_id} 不存在")

    action = request.action.lower()

    if action == "approve":
        # 先提交审核（如果还是 DRAFT）
        if entry.status == PlaybookStatus.DRAFT:
            await manager.submit_for_review(playbook_id)

        success = await manager.approve(
            playbook_id,
            reviewer=request.reviewer,
            notes=request.notes,
        )
        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"策略 {playbook_id} 当前状态 ({entry.status.value}) 无法审核通过",
            )
        return PlaybookActionResponse(
            success=True,
            message="策略已记住",
            playbook_id=playbook_id,
        )

    elif action == "reject":
        if entry.status == PlaybookStatus.DRAFT:
            await manager.submit_for_review(playbook_id)

        success = await manager.reject(
            playbook_id,
            reviewer=request.reviewer,
            reason=request.notes or "用户拒绝",
        )
        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"策略 {playbook_id} 当前状态 ({entry.status.value}) 无法拒绝",
            )
        return PlaybookActionResponse(
            success=True,
            message="策略已拒绝",
            playbook_id=playbook_id,
        )

    elif action == "dismiss":
        await manager.delete(playbook_id)
        return PlaybookActionResponse(
            success=True,
            message="策略已忽略",
            playbook_id=playbook_id,
        )

    elif action == "deprecate":
        success = await manager.deprecate(
            playbook_id,
            reason=request.notes or "用户废弃",
        )
        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"策略 {playbook_id} 当前状态 ({entry.status.value}) 无法废弃"
                f"（仅 APPROVED 状态可废弃）",
            )
        return PlaybookActionResponse(
            success=True,
            message="策略已废弃",
            playbook_id=playbook_id,
        )

    else:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的操作: {action}，支持: approve / reject / dismiss / deprecate",
        )


@router.delete("/{playbook_id}")
async def delete_playbook(playbook_id: str):
    """删除策略"""
    manager = await _get_manager()
    success = await manager.delete(playbook_id)

    if not success:
        raise HTTPException(status_code=404, detail=f"策略 {playbook_id} 不存在")

    return {"success": True, "message": f"策略 {playbook_id} 已删除"}
