"""
Gateway configuration loader and factory

Loads gateway.yaml, resolves environment variables,
creates channel adapters, and wires up the gateway bridge.
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiofiles
import yaml

from logger import get_logger

from core.gateway.bridge import GatewayBridge
from core.gateway.manager import ChannelManager
from core.gateway.types import ChannelConfig, GatewayBinding, GatewayConfig

logger = get_logger("gateway.loader")

# Default config path
from utils.app_paths import get_bundle_dir

GATEWAY_CONFIG_PATH = get_bundle_dir() / "config" / "gateway.yaml"

# Regex for ${VAR_NAME} environment variable references
_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


def _resolve_env_vars(value: Any) -> Any:
    """
    Recursively resolve ${VAR_NAME} references in config values.

    Args:
        value: config value (str, dict, list, or primitive)

    Returns:
        value with env vars resolved
    """
    if isinstance(value, str):
        def _replace(match):
            var_name = match.group(1)
            env_value = os.environ.get(var_name, "")
            if not env_value:
                logger.debug(f"Environment variable {var_name} not set")
            return env_value
        return _ENV_VAR_PATTERN.sub(_replace, value)

    if isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}

    if isinstance(value, list):
        return [_resolve_env_vars(item) for item in value]

    return value


async def load_gateway_config(
    config_path: Optional[Path] = None,
) -> GatewayConfig:
    """
    Load and parse gateway configuration from YAML.

    Args:
        config_path: path to gateway.yaml (defaults to config/gateway.yaml)

    Returns:
        Parsed GatewayConfig
    """
    path = config_path or GATEWAY_CONFIG_PATH

    if not path.exists():
        logger.info("Gateway config not found, gateway disabled", extra={"path": str(path)})
        return GatewayConfig(enabled=False)

    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            content = await f.read()
            raw = yaml.safe_load(content) or {}
    except Exception as e:
        logger.warning(f"Failed to load gateway config: {e}")
        return GatewayConfig(enabled=False)

    # Resolve environment variables
    raw = _resolve_env_vars(raw)

    # Parse gateway section
    gateway_section = raw.get("gateway", {})
    enabled = gateway_section.get("enabled", False)

    # Parse channels
    channels_raw = raw.get("channels", {})
    channels: Dict[str, ChannelConfig] = {}
    for channel_id, channel_data in channels_raw.items():
        if isinstance(channel_data, dict):
            channel_enabled = channel_data.get("enabled", False)
            params = {k: v for k, v in channel_data.items() if k != "enabled"}
            channels[channel_id] = ChannelConfig(
                enabled=channel_enabled,
                params=params,
            )

    # Parse bindings
    bindings_raw = raw.get("bindings", [])
    bindings: List[GatewayBinding] = []
    for binding_data in bindings_raw:
        if isinstance(binding_data, dict):
            bindings.append(GatewayBinding(**binding_data))

    config = GatewayConfig(
        enabled=enabled,
        channels=channels,
        bindings=bindings,
    )

    logger.info(
        "Gateway config loaded",
        extra={
            "enabled": config.enabled,
            "channels": {k: v.enabled for k, v in config.channels.items()},
            "bindings_count": len(config.bindings),
        },
    )

    return config


async def load_gateway_config_raw(
    config_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Load raw gateway YAML config without resolving env vars.

    Used by the settings API so users see ${VAR_NAME} placeholders
    instead of resolved (empty) values.

    Returns:
        Raw config dict
    """
    path = config_path or GATEWAY_CONFIG_PATH
    if not path.exists():
        return {
            "gateway": {"enabled": False},
            "channels": {},
            "bindings": [],
        }

    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            content = await f.read()
            return yaml.safe_load(content) or {}
    except Exception as e:
        logger.warning(f"Failed to load raw gateway config: {e}")
        return {"gateway": {"enabled": False}, "channels": {}, "bindings": []}


async def save_gateway_config(
    raw_config: Dict[str, Any],
    config_path: Optional[Path] = None,
) -> None:
    """
    Save gateway configuration back to YAML.

    Args:
        raw_config: full config dict (with ${VAR_NAME} placeholders intact)
        config_path: path to gateway.yaml (defaults to config/gateway.yaml)
    """
    path = config_path or GATEWAY_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    content = yaml.dump(
        raw_config,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )

    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(content)

    logger.info("Gateway config saved", extra={"path": str(path)})


def _create_channel_adapter(channel_id: str, config: ChannelConfig):
    """
    Create a channel adapter instance based on channel ID.

    Args:
        channel_id: channel identifier (e.g. "telegram", "feishu")
        config: channel configuration

    Returns:
        ChannelAdapter instance or None if channel type unknown or dependency missing
    """
    try:
        if channel_id == "telegram":
            from core.gateway.channels.telegram import TelegramChannel
            return TelegramChannel(config.params)

        elif channel_id == "feishu":
            from core.gateway.channels.feishu import FeishuChannel
            return FeishuChannel(config.params)

        else:
            logger.warning(f"Unknown channel type: {channel_id}")
            return None

    except ImportError as e:
        logger.warning(
            f"Channel '{channel_id}' skipped: missing dependency",
            extra={"channel": channel_id, "error": str(e)},
        )
        return None


async def create_gateway(
    config: Optional[GatewayConfig] = None,
) -> Optional[Tuple[ChannelManager, GatewayBridge]]:
    """
    Create and configure the gateway from config.

    Returns:
        Tuple of (ChannelManager, GatewayBridge) if enabled, None if disabled.
    """
    if config is None:
        config = await load_gateway_config()

    if not config.enabled:
        logger.info("Gateway is disabled")
        return None

    # Create manager and bridge
    manager = ChannelManager()
    bridge = GatewayBridge(
        channel_manager=manager,
        bindings=config.bindings,
    )

    # Register enabled channels
    registered = []
    for channel_id, channel_config in config.channels.items():
        if not channel_config.enabled:
            continue

        adapter = _create_channel_adapter(channel_id, channel_config)
        if adapter:
            manager.register(adapter)
            registered.append(channel_id)

    if not registered:
        logger.warning("Gateway enabled but no channels are configured/enabled")
        return None

    # Wire up the message handler
    manager.set_message_handler(bridge.handle_inbound)

    logger.info(
        "Gateway created",
        extra={"channels": registered, "bindings": len(config.bindings)},
    )

    return manager, bridge
