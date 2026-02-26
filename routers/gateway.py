"""
Gateway health check, status, and configuration API

Provides endpoints to:
- Check gateway / channel connection status
- Read / update gateway configuration (gateway.yaml)
"""

import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/gateway", tags=["gateway"])

# Module-level reference to the ChannelManager (set during startup)
_channel_manager = None


def set_channel_manager(manager) -> None:
    """Set the ChannelManager instance for this router (called from main.py lifespan)."""
    global _channel_manager
    _channel_manager = manager


# ==================== Status Endpoints ====================


@router.get("/status")
async def get_gateway_status() -> Dict[str, Any]:
    """
    Get gateway status and all channel statuses.

    Returns:
        {
            "enabled": true,
            "channels": [
                {"id": "telegram", "display_name": "Telegram", "status": "connected"},
                {"id": "feishu", "display_name": "Feishu", "status": "disconnected"}
            ]
        }
    """
    if _channel_manager is None:
        return {
            "enabled": False,
            "channels": [],
        }

    return {
        "enabled": True,
        "channels": _channel_manager.list_channels(),
    }


@router.get("/channels")
async def list_channels() -> List[Dict[str, str]]:
    """
    List all registered channels with their status.

    Returns:
        List of channel info dicts
    """
    if _channel_manager is None:
        return []

    return _channel_manager.list_channels()


# ==================== Configuration Endpoints ====================

# Channel display metadata (shared between frontend and backend)
CHANNEL_META = {
    "telegram": {
        "display_name": "Telegram",
        "description": "Telegram Bot（长轮询，无需公网 IP）",
        "secret_fields": ["bot_token"],
        "fields": [
            {"key": "bot_token", "label": "Bot Token", "placeholder": "从 @BotFather 获取", "secret": True},
            {"key": "allowed_users", "label": "允许的用户 ID", "placeholder": "留空表示允许所有人", "type": "list"},
            {"key": "allowed_groups", "label": "允许的群组 ID", "placeholder": "留空表示允许所有群组", "type": "list"},
        ],
        "setup_steps": [
            {"title": "打开 Telegram，搜索 @BotFather", "detail": "这是 Telegram 官方的机器人管理工具，直接在聊天搜索框输入 @BotFather 即可找到。"},
            {"title": "发送 /newbot 创建机器人", "detail": "按提示依次输入机器人的显示名称（如「我的助手」）和用户名（必须以 bot 结尾，如 my_assistant_bot）。"},
            {"title": "复制 Bot Token 并测试", "detail": "创建成功后 BotFather 会返回一串形如 123456:ABC-DEF... 的 Token，粘贴到下方输入框，然后点击「测试连接」确认 Token 有效。"},
            {"title": "（可选）限制访问", "detail": "如果只想让特定用户使用，填写他们的 Telegram User ID。获取方式：给 @userinfobot 发送任意消息即可看到自己的 ID。"},
        ],
    },
    "feishu": {
        "display_name": "飞书",
        "description": "飞书机器人（WebSocket 长连接，无需公网 IP）",
        "secret_fields": ["app_secret"],
        "fields": [
            {"key": "app_id", "label": "App ID", "placeholder": "飞书开放平台 App ID", "secret": False},
            {"key": "app_secret", "label": "App Secret", "placeholder": "飞书开放平台 App Secret", "secret": True},
        ],
        "setup_steps": [
            {
                "title": "访问飞书开放平台，创建应用",
                "detail": "打开 open.feishu.cn → 开发者后台 → 创建企业自建应用。输入应用名称和描述。",
                "link": "https://open.feishu.cn/app",
            },
            {
                "title": "获取 App ID 和 App Secret",
                "detail": "在应用的「凭证与基础信息」页面，复制 App ID 和 App Secret 到下方输入框。",
            },
            {
                "title": "启用机器人能力",
                "detail": "在应用的「添加应用能力」中，添加「机器人」能力。添加后可以在「机器人」页面设置机器人的名称和头像。",
            },
            {
                "title": "配置权限",
                "detail": "在「权限管理」中搜索并开通以下权限：\n• im:message — 获取与发送消息\n• im:message.group_at_msg — 接收群聊中 @机器人的消息\n• im:chat:readonly — 获取群组信息\n开通后需要发布版本才能生效。",
            },
            {
                "title": "添加事件订阅",
                "detail": "在「事件与回调」→「事件配置」中，点击「添加事件」，搜索并添加 im.message.receive_v1（接收消息）事件。这一步必须先完成，否则无法选择长连接模式。\n\n「加密策略」和「回调配置」不需要配置 — 长连接模式下由 SDK 主动连接飞书服务器，不需要公网回调地址，也不需要加密。",
            },
            {
                "title": "选择长连接方式",
                "detail": "在同一页面的「订阅方式」中，选择「使用长连接接收事件」→ 点击「保存」。这样无需公网 IP，我们的服务会主动连接飞书服务器。",
            },
            {
                "title": "测试连接",
                "detail": "在下方填好 App ID 和 App Secret 后，点击「测试连接」。后端会真实验证凭证、检查机器人能力是否开启，全部通过才会显示成功。",
            },
            {
                "title": "发布并测试",
                "detail": "点击右上角「创建版本」→ 填写更新说明 → 提交发布。管理员审批通过后，在飞书中搜索你的机器人名称，发一条消息测试是否正常回复。\n\n如果是个人开发测试，可以先在「版本管理与发布」中使用「测试企业和人员」将自己添加为测试用户，无需管理员审批。",
            },
        ],
    },
}


def _resolve_default_agent_id() -> Optional[str]:
    """
    Resolve default agent_id for gateway channel bindings.

    Priority:
    1. AGENT_INSTANCE environment variable
    2. Currently loaded single instance from AgentRegistry
    """
    env_instance = os.getenv("AGENT_INSTANCE")
    if env_instance:
        return env_instance

    try:
        from services.agent_registry import get_agent_registry

        registry = get_agent_registry()
        return registry.get_current_instance()
    except Exception as e:
        logger.warning(
            "Failed to resolve current instance for gateway binding",
            extra={"error": str(e)},
            exc_info=True,
        )
        return None


def _ensure_default_channel_bindings(raw_config: Dict[str, Any]) -> None:
    """
    Ensure each enabled channel has a channel-level binding.

    This keeps gateway routing stable when users enable a new channel
    (e.g. Feishu) from frontend settings without manually editing bindings.
    """
    channels_raw = raw_config.get("channels", {}) or {}
    bindings = raw_config.get("bindings", []) or []
    if not isinstance(bindings, list):
        bindings = []

    default_agent_id = _resolve_default_agent_id()
    if not default_agent_id:
        logger.warning("Skip auto-binding: cannot resolve default agent_id")
        raw_config["bindings"] = bindings
        return

    for channel_id, channel_data in channels_raw.items():
        if not isinstance(channel_data, dict):
            continue
        if not channel_data.get("enabled", False):
            continue

        # channel-level binding (without conversation_id) is enough
        exists = any(
            isinstance(b, dict)
            and b.get("channel") == channel_id
            and not b.get("conversation_id")
            for b in bindings
        )
        if exists:
            continue

        bindings.append(
            {
                "channel": channel_id,
                "agent_id": default_agent_id,
            }
        )
        logger.info(
            "Auto-added gateway binding",
            extra={"channel": channel_id, "agent_id": default_agent_id},
        )

    raw_config["bindings"] = bindings


def _build_channel_response(channel_id: str, channel_data: dict) -> Dict[str, Any]:
    """Build a channel config response with metadata. No masking — local project."""
    meta = CHANNEL_META.get(channel_id, {})

    enabled = channel_data.get("enabled", False)
    params: Dict[str, Any] = {
        k: v for k, v in channel_data.items() if k != "enabled"
    }

    return {
        "id": channel_id,
        "enabled": enabled,
        "display_name": meta.get("display_name", channel_id),
        "description": meta.get("description", ""),
        "fields": meta.get("fields", []),
        "setup_steps": meta.get("setup_steps", []),
        "params": params,
        "status": _get_channel_status(channel_id),
    }


def _get_channel_status(channel_id: str) -> str:
    """Get the live connection status for a channel."""
    if _channel_manager is None:
        return "disconnected"
    adapter = _channel_manager.get_adapter(channel_id)
    if adapter is None:
        return "disconnected"
    return adapter.get_status().value


# Default channel skeleton (used when gateway.yaml doesn't exist yet)
_DEFAULT_CHANNELS: Dict[str, Dict[str, Any]] = {
    "telegram": {"enabled": False, "bot_token": "", "allowed_users": [], "allowed_groups": []},
    "feishu": {"enabled": False, "app_id": "", "app_secret": ""},
}


@router.get("/config")
async def get_gateway_config() -> Dict[str, Any]:
    """
    Get gateway configuration for the settings UI.

    Returns raw config with channel metadata attached.
    When gateway.yaml doesn't exist, returns default channel skeletons
    so the frontend can render the configuration form.
    """
    from core.gateway.loader import load_gateway_config_raw

    raw = await load_gateway_config_raw()

    # Gateway-level config
    gateway_section = raw.get("gateway", {})
    enabled = gateway_section.get("enabled", False)

    # Channels with metadata — fall back to defaults when config file is missing
    channels_raw = raw.get("channels", {})
    if not channels_raw:
        channels_raw = _DEFAULT_CHANNELS

    channels = []
    for channel_id, channel_data in channels_raw.items():
        if isinstance(channel_data, dict):
            channels.append(_build_channel_response(channel_id, channel_data))

    # Bindings
    bindings = raw.get("bindings", []) or []

    return {
        "success": True,
        "data": {
            "enabled": enabled,
            "channels": channels,
            "bindings": bindings,
        },
    }


class ChannelConfigUpdate(BaseModel):
    """Update payload for a single channel."""
    enabled: Optional[bool] = None
    params: Optional[Dict[str, Any]] = None


class GatewayConfigUpdate(BaseModel):
    """Update payload for gateway configuration."""
    enabled: Optional[bool] = None
    channels: Optional[Dict[str, ChannelConfigUpdate]] = None
    bindings: Optional[List[Dict[str, Any]]] = None


@router.put("/config")
async def update_gateway_config(body: GatewayConfigUpdate) -> Dict[str, Any]:
    """
    Update gateway configuration and save to gateway.yaml.

    Only provided fields are updated (partial update / merge).
    Requires server restart for changes to take effect on running channels.
    """
    from core.gateway.loader import load_gateway_config_raw, save_gateway_config

    raw = await load_gateway_config_raw()

    # Update gateway enabled
    if body.enabled is not None:
        raw.setdefault("gateway", {})["enabled"] = body.enabled

    # Update channels
    if body.channels:
        channels_raw = raw.setdefault("channels", {})
        for channel_id, update in body.channels.items():
            channel_data = channels_raw.setdefault(channel_id, {})

            if update.enabled is not None:
                channel_data["enabled"] = update.enabled

            if update.params:
                for key, value in update.params.items():
                    channel_data[key] = value

    # Update bindings
    if body.bindings is not None:
        raw["bindings"] = body.bindings

    # Auto-ensure enabled channels have explicit bindings (channel -> agent)
    _ensure_default_channel_bindings(raw)

    # Save to YAML
    await save_gateway_config(raw)

    logger.info("Gateway config updated via API")

    return {
        "success": True,
        "data": {
            "message": "配置已保存，需要重启服务后生效",
            "needs_restart": True,
        },
    }


# ==================== Connection Test Endpoints ====================


class ChannelTestRequest(BaseModel):
    """Request body for testing a channel connection."""
    channel: str = Field(..., description="Channel ID, e.g. 'telegram', 'feishu'")
    params: Dict[str, Any] = Field(..., description="Channel params to test")


@router.post("/test-connection")
async def test_channel_connection(body: ChannelTestRequest) -> Dict[str, Any]:
    """
    Test channel credentials without starting the full adapter.

    - Telegram: validates bot_token by calling getMe API
    - Feishu: validates app_id/app_secret by fetching tenant_access_token
    """
    import asyncio

    channel = body.channel
    params = body.params

    if channel == "telegram":
        return await _test_telegram(params)
    elif channel == "feishu":
        return await _test_feishu(params)
    else:
        return {
            "success": False,
            "data": {"valid": False, "message": f"不支持测试 {channel} 渠道"},
        }


async def _test_telegram(params: Dict[str, Any]) -> Dict[str, Any]:
    """Test Telegram bot token by calling getMe."""
    bot_token = params.get("bot_token", "")
    if not bot_token or bot_token.startswith("${"):
        return {
            "success": True,
            "data": {"valid": False, "message": "请先填写 Bot Token"},
        }

    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"https://api.telegram.org/bot{bot_token}/getMe")
            data = resp.json()

        if data.get("ok"):
            bot = data["result"]
            bot_name = bot.get("first_name", "")
            bot_username = bot.get("username", "")
            return {
                "success": True,
                "data": {
                    "valid": True,
                    "message": f"连接成功！机器人：{bot_name} (@{bot_username})",
                    "bot_info": {
                        "name": bot_name,
                        "username": bot_username,
                        "id": bot.get("id"),
                    },
                },
            }
        else:
            error_desc = data.get("description", "Token 无效")
            return {
                "success": True,
                "data": {"valid": False, "message": f"Token 验证失败：{error_desc}"},
            }
    except Exception as e:
        logger.error("Telegram connection test failed", extra={"error": str(e)}, exc_info=True)
        return {
            "success": True,
            "data": {"valid": False, "message": f"连接失败：{str(e)}"},
        }


async def _test_feishu(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Multi-step Feishu connection test:
    1. Validate credentials (get tenant_access_token)
    2. Check bot capability (get bot info via API)
    3. Real WebSocket connection via official lark SDK
    """
    app_id = params.get("app_id", "")
    app_secret = params.get("app_secret", "")

    if not app_id or app_id.startswith("${"):
        return {
            "success": True,
            "data": {"valid": False, "message": "请先填写 App ID"},
        }
    if not app_secret or app_secret.startswith("${"):
        return {
            "success": True,
            "data": {"valid": False, "message": "请先填写 App Secret"},
        }

    steps_passed: List[str] = []

    try:
        import httpx

        # ── Step 1: Validate credentials ──
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": app_id, "app_secret": app_secret},
            )
            token_data = resp.json()

        if token_data.get("code") != 0:
            error_msg = token_data.get("msg", "凭证无效")
            return {
                "success": True,
                "data": {"valid": False, "message": f"凭证验证失败：{error_msg}"},
            }

        tenant_token = token_data.get("tenant_access_token", "")
        steps_passed.append("凭证有效")

        # ── Step 2: Check bot capability ──
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://open.feishu.cn/open-apis/bot/v3/info/",
                headers={"Authorization": f"Bearer {tenant_token}"},
            )
            bot_data = resp.json()

        if bot_data.get("code") != 0:
            error_msg = bot_data.get("msg", "未知错误")
            # code 10003 = bot not enabled
            if bot_data.get("code") in (10003, 10014):
                return {
                    "success": True,
                    "data": {
                        "valid": False,
                        "message": "凭证有效，但机器人能力未启用。请在飞书开放平台「添加应用能力」中添加「机器人」。",
                    },
                }
            return {
                "success": True,
                "data": {"valid": False, "message": f"凭证有效，但获取机器人信息失败：{error_msg}"},
            }

        bot_info = bot_data.get("bot", {})
        bot_name = bot_info.get("app_name", "未命名")
        steps_passed.append(f"机器人「{bot_name}」")

        # ── Step 3: Real WebSocket connection test via official SDK ──
        # lark SDK captures event loop at module-import time. When imported
        # inside FastAPI, it grabs the RUNNING loop, then start() calls
        # loop.run_until_complete() → "already running".
        # Fix: run in a daemon thread with its own loop + patch SDK reference.
        import asyncio as _asyncio
        import threading

        ws_ok = False
        ws_error = ""
        try:
            import lark_oapi as lark
            from lark_oapi.ws import client as ws_module

            event_handler = lark.EventDispatcherHandler.builder("", "").build()
            ws_client = lark.ws.Client(
                app_id, app_secret,
                event_handler=event_handler,
                log_level=lark.LogLevel.ERROR,
                auto_reconnect=False,
            )

            ws_exc: List[Exception] = []
            test_loop: List[_asyncio.AbstractEventLoop] = []

            def _ws_probe() -> None:
                probe_loop = _asyncio.new_event_loop()
                _asyncio.set_event_loop(probe_loop)
                ws_module.loop = probe_loop
                test_loop.append(probe_loop)
                try:
                    ws_client.start()
                except Exception as e:
                    ws_exc.append(e)

            t = threading.Thread(target=_ws_probe, daemon=True)
            t.start()
            t.join(timeout=6)

            if ws_exc:
                ws_error = str(ws_exc[0])
            elif not t.is_alive():
                ws_error = "WebSocket 连接意外断开"
            else:
                ws_ok = True
                # Clean up: stop the test loop so the WS connection closes
                if test_loop:
                    test_loop[0].call_soon_threadsafe(test_loop[0].stop)

        except ImportError:
            ws_error = "lark-oapi 未安装，请运行 pip install lark-oapi>=1.3.0"
        except Exception as e:
            ws_error = str(e)

        if ws_ok:
            steps_passed.append("长连接正常")
            return {
                "success": True,
                "data": {
                    "valid": True,
                    "message": f"全部通过！{' → '.join(steps_passed)}",
                    "bot_info": {"name": bot_name},
                },
            }
        else:
            return {
                "success": True,
                "data": {
                    "valid": False,
                    "message": f"{' → '.join(steps_passed)} → 长连接失败：{ws_error}。请确认已在飞书平台选择「使用长连接接收事件」并保存。",
                },
            }

    except Exception as e:
        logger.error("Feishu connection test failed", extra={"error": str(e)}, exc_info=True)
        detail = f"（已通过：{' → '.join(steps_passed)}）" if steps_passed else ""
        return {
            "success": True,
            "data": {"valid": False, "message": f"测试失败：{str(e)}{detail}"},
        }
