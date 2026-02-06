"""
事件适配器模块

负责将内部事件格式转换为外部系统格式（Slack、钉钉、飞书等）
"""

from core.events.adapters.base import AdapterConfig, EventAdapter
from core.events.adapters.dingtalk import DingTalkAdapter
from core.events.adapters.feishu import FeishuAdapter
from core.events.adapters.slack import SlackAdapter
from core.events.adapters.webhook import WebhookAdapter

__all__ = [
    "EventAdapter",
    "AdapterConfig",
    "WebhookAdapter",
    "SlackAdapter",
    "DingTalkAdapter",
    "FeishuAdapter",
]
