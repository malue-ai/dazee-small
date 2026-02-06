"""
渠道 API 路由

提供统一的渠道 Webhook 入口和管理接口
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel

from channels.config import load_config
from channels.feishu import feishu_plugin
from channels.feishu.handler import FeishuMessageHandler
from channels.manager import ChannelManager, get_channel_manager
from channels.registry import get_channel_registry
from logger import get_logger

logger = get_logger("routers.channels")


router = APIRouter(prefix="/api/v1/channels", tags=["channels"])


# ===========================================================================
# 依赖注入
# ===========================================================================


async def get_manager() -> ChannelManager:
    """获取渠道管理器"""
    return get_channel_manager()


# ===========================================================================
# Webhook 入口
# ===========================================================================


@router.post("/{channel_id}/webhook")
async def channel_webhook(
    channel_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    account_id: Optional[str] = None,
    manager: ChannelManager = Depends(get_manager),
):
    """
    统一渠道 Webhook 入口

    接收各渠道推送的事件，路由到对应的插件处理

    - 飞书: POST /api/v1/channels/feishu/webhook
    - 钉钉: POST /api/v1/channels/dingtalk/webhook
    - Slack: POST /api/v1/channels/slack/webhook
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    logger.info(f"📨 收到 {channel_id} Webhook: keys={list(body.keys())[:5]}")

    # 处理事件
    response = await manager.handle_event(channel_id=channel_id, event=body, account_id=account_id)

    return response.to_dict()


@router.post("/{channel_id}/webhook/{account_id}")
async def channel_webhook_with_account(
    channel_id: str,
    account_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    manager: ChannelManager = Depends(get_manager),
):
    """
    带账户 ID 的 Webhook 入口（多账户场景）

    - POST /api/v1/channels/feishu/webhook/bot1
    - POST /api/v1/channels/feishu/webhook/bot2
    """
    return await channel_webhook(
        channel_id=channel_id,
        request=request,
        background_tasks=background_tasks,
        account_id=account_id,
        manager=manager,
    )


# ===========================================================================
# 管理接口
# ===========================================================================


@router.get("")
async def list_channels(manager: ChannelManager = Depends(get_manager)):
    """
    列出所有注册的渠道
    """
    registry = get_channel_registry()
    return {"channels": registry.get_summary(), "active": manager.list_active_channels()}


@router.get("/{channel_id}")
async def get_channel(channel_id: str, manager: ChannelManager = Depends(get_manager)):
    """
    获取渠道详情
    """
    status = manager.get_channel_status(channel_id)
    if "error" in status:
        raise HTTPException(status_code=404, detail=status["error"])
    return status


@router.post("/{channel_id}/start")
async def start_channel(
    channel_id: str,
    account_id: Optional[str] = None,
    manager: ChannelManager = Depends(get_manager),
):
    """
    启动渠道
    """
    success = await manager.start_channel(channel_id, account_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to start channel")
    return {"status": "started", "channel_id": channel_id}


@router.post("/{channel_id}/stop")
async def stop_channel(
    channel_id: str,
    account_id: Optional[str] = None,
    manager: ChannelManager = Depends(get_manager),
):
    """
    停止渠道
    """
    success = await manager.stop_channel(channel_id, account_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to stop channel")
    return {"status": "stopped", "channel_id": channel_id}


# ===========================================================================
# 初始化
# ===========================================================================


async def init_channels(config_path: str = None):
    """
    初始化渠道系统

    在应用启动时调用

    Args:
        config_path: 配置文件路径
    """
    # 加载配置
    config = await load_config(config_path)

    # 注册插件
    registry = get_channel_registry()
    registry.register(feishu_plugin)

    # 初始化管理器
    from channels.manager import set_channel_manager

    manager = ChannelManager(config=config, registry=registry)
    set_channel_manager(manager)

    # 启动已启用的渠道
    await manager.start_all()

    logger.info("✅ 渠道系统初始化完成")


async def shutdown_channels():
    """
    关闭渠道系统

    在应用关闭时调用
    """
    manager = get_channel_manager()
    await manager.stop_all()
    logger.info("渠道系统已关闭")
