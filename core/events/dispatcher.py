"""
事件分发器 - 外部 Webhook 发送

职责：
- 将事件发送到外部系统（Webhook、Slack、钉钉、飞书等）
- 配置管理（从 YAML 加载）
- 重试和错误处理

注意：内部事件广播由 storage.buffer_event 统一处理
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
import httpx
import yaml

from core.events.adapters.base import AdapterConfig, EventAdapter
from core.events.adapters.dingtalk import DingTalkAdapter
from core.events.adapters.feishu import FeishuAdapter
from core.events.adapters.slack import SlackAdapter
from core.events.adapters.webhook import WebhookAdapter
from logger import get_logger

logger = get_logger("event_dispatcher")


# 适配器类型映射
ADAPTER_TYPES = {
    "webhook": WebhookAdapter,
    "slack": SlackAdapter,
    "dingtalk": DingTalkAdapter,
    "feishu": FeishuAdapter,
}


class EventDispatcher:
    """
    事件分发器（外部 Webhook）

    职责：
    - 将事件发送到外部系统（Webhook、Slack、钉钉、飞书等）
    - 配置管理（从 YAML 加载）
    - 重试和错误处理

    使用示例：
    ```python
    dispatcher = EventDispatcher()
    await dispatcher.load_config("config/webhooks.yaml")

    # 发送事件到外部
    await dispatcher.send(event)
    ```
    """

    def __init__(self):
        """初始化事件分发器"""
        self.adapters: List[AdapterConfig] = []
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """获取或创建 HTTP 客户端"""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=10.0)
        return self._http_client

    async def close(self):
        """关闭 HTTP 客户端"""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    async def load_config(self, config_path: str) -> None:
        """
        异步从 YAML 配置文件加载适配器配置

        Args:
            config_path: 配置文件路径
        """
        path = Path(config_path)
        if not path.exists():
            logger.warning(f"配置文件不存在: {config_path}")
            return

        try:
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                content = await f.read()
                config = yaml.safe_load(content)

            subscriptions = config.get("subscriptions", [])

            for sub in subscriptions:
                self._add_subscription(sub)

            logger.info(f"✅ 已加载 {len(self.adapters)} 个外部适配器配置")

        except Exception as e:
            logger.error(f"加载配置文件失败: {e}", exc_info=True)

    def _add_subscription(self, config: Dict[str, Any]) -> None:
        """
        添加一个订阅配置

        Args:
            config: 订阅配置字典
        """
        name = config.get("name", "unnamed")
        adapter_type = config.get("adapter", "webhook")
        endpoint = config.get("endpoint", "")
        events = config.get("events")
        enabled = config.get("enabled", True)
        timeout = config.get("timeout", 5.0)
        retry_count = config.get("retry_count", 2)
        headers = config.get("headers", {})

        if not enabled:
            logger.debug(f"跳过禁用的适配器: {name}")
            return

        if not endpoint:
            logger.warning(f"适配器 {name} 缺少 endpoint 配置")
            return

        # 创建适配器实例
        adapter_class = ADAPTER_TYPES.get(adapter_type, WebhookAdapter)

        if adapter_type == "webhook":
            template = config.get("template")
            adapter = adapter_class(template=template, supported_events=events)
        elif adapter_type == "slack":
            channel = config.get("channel")
            adapter = adapter_class(channel=channel)
            adapter.supported_events = events
        elif adapter_type == "dingtalk":
            at_mobiles = config.get("at_mobiles", [])
            at_all = config.get("at_all", False)
            adapter = adapter_class(at_mobiles=at_mobiles, at_all=at_all)
            adapter.supported_events = events
        elif adapter_type == "feishu":
            at_users = config.get("at_users", [])
            adapter = adapter_class(at_users=at_users)
            adapter.supported_events = events
        else:
            adapter = adapter_class()
            adapter.supported_events = events

        # 创建配置
        adapter_config = AdapterConfig(
            name=name,
            adapter=adapter,
            endpoint=endpoint,
            events=events,
            enabled=enabled,
            headers=headers,
            timeout=timeout,
            retry_count=retry_count,
        )

        self.adapters.append(adapter_config)
        logger.debug(f"添加适配器: {name} ({adapter_type}) -> {endpoint}")

    def add_adapter(self, config: AdapterConfig) -> None:
        """
        手动添加适配器配置

        Args:
            config: 适配器配置
        """
        self.adapters.append(config)
        logger.info(f"添加适配器: {config.name}")

    async def send(self, event: Dict[str, Any]) -> None:
        """
        发送事件到所有匹配的外部适配器

        Args:
            event: 事件数据
        """
        if not self.adapters:
            return

        for config in self.adapters:
            if config.enabled and config.adapter.should_handle_extended(event):
                # 异步发送，不阻塞主流程
                asyncio.create_task(self._send_to_external(config, event))

    async def _send_to_external(self, config: AdapterConfig, event: Dict[str, Any]) -> bool:
        """
        发送事件到外部系统

        Args:
            config: 适配器配置
            event: 事件数据

        Returns:
            是否成功
        """
        try:
            # 转换格式
            transformed = config.adapter.transform(event)

            # 合并请求头
            headers = {**config.adapter.get_headers(), **config.headers}

            # 获取 HTTP 客户端
            client = await self._get_http_client()

            # 带重试的发送
            last_error = None
            for attempt in range(config.retry_count + 1):
                try:
                    response = await client.post(
                        config.endpoint, json=transformed, headers=headers, timeout=config.timeout
                    )

                    if response.status_code < 400:
                        logger.debug(
                            f"✅ 外部事件发送成功: {config.name}, " f"status={response.status_code}"
                        )
                        return True
                    else:
                        logger.warning(
                            f"⚠️ 外部事件发送失败: {config.name}, "
                            f"status={response.status_code}, body={response.text[:200]}"
                        )
                        last_error = f"HTTP {response.status_code}"

                except httpx.TimeoutException:
                    last_error = "timeout"
                    logger.warning(f"⏱️ 外部事件发送超时: {config.name} (尝试 {attempt + 1})")

                except httpx.RequestError as e:
                    last_error = str(e)
                    logger.warning(f"🔌 外部事件发送错误: {config.name}, error={e}")

                # 重试前等待
                if attempt < config.retry_count:
                    await asyncio.sleep(0.5 * (attempt + 1))

            logger.error(f"❌ 外部事件发送最终失败: {config.name}, error={last_error}")
            return False

        except Exception as e:
            logger.error(f"❌ 外部事件发送异常: {config.name}, error={e}", exc_info=True)
            return False

    def get_adapters_summary(self) -> List[Dict[str, Any]]:
        """
        获取适配器摘要信息

        Returns:
            适配器配置摘要列表
        """
        return [
            {
                "name": config.name,
                "adapter": config.adapter.name,
                "endpoint": (
                    config.endpoint[:50] + "..." if len(config.endpoint) > 50 else config.endpoint
                ),
                "events": config.events,
                "enabled": config.enabled,
            }
            for config in self.adapters
        ]


# ==================== 工厂函数 ====================


async def create_event_dispatcher(config_path: Optional[str] = None) -> EventDispatcher:
    """
    创建事件分发器

    Args:
        config_path: 配置文件路径（可选）

    Returns:
        EventDispatcher 实例
    """
    dispatcher = EventDispatcher()

    if config_path:
        await dispatcher.load_config(config_path)
    else:
        # 默认配置路径
        default_path = Path("config/webhooks.yaml")
        if default_path.exists():
            await dispatcher.load_config(str(default_path))

    return dispatcher
