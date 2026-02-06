"""
Slack 适配器

将内部事件转换为 Slack Block Kit 格式
参考: https://api.slack.com/block-kit
"""

import json
from typing import Any, Dict, List, Optional

from core.events.adapters.base import EventAdapter
from logger import get_logger

logger = get_logger("slack_adapter")


class SlackAdapter(EventAdapter):
    """
    Slack 事件适配器

    将内部事件转换为 Slack Block Kit 格式

    支持的事件类型：
    - confirmation_request → Interactive Message (Buttons)
    - session_end → Simple Message
    - error → Attachment (Red)
    """

    name = "slack"
    supported_events = ["message_delta:confirmation_request", "session_end", "error"]

    def __init__(self, channel: Optional[str] = None):
        """
        初始化 Slack 适配器

        Args:
            channel: 默认频道（可选，部分 Webhook 不需要）
        """
        self.channel = channel

    def transform(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        转换为 Slack 格式
        """
        event_type = event.get("type", "")

        # 处理 message_delta 中的特定类型
        if event_type == "message_delta":
            delta_type = self.extract_delta_type(event)
            if delta_type == "confirmation_request":
                return self._transform_confirmation_request(event)

        # 处理其他事件类型
        if event_type == "session_end":
            return self._transform_session_end(event)

        if event_type == "error":
            return self._transform_error(event)

        # 默认：简单消息
        return self._transform_default(event)

    def _transform_confirmation_request(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        转换 HITL 确认请求为 Slack Interactive Message
        """
        data = event.get("data", {})
        delta = data.get("delta", {})
        content = delta.get("content", "{}")

        try:
            hitl_data = json.loads(content) if isinstance(content, str) else content
        except json.JSONDecodeError:
            hitl_data = {}

        question = hitl_data.get("question", "确认请求")
        options = hitl_data.get("options", ["confirm", "cancel"])
        description = hitl_data.get("description", "")
        request_id = hitl_data.get("request_id", "")

        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*🤖 Agent 确认请求*\n\n{question}"},
            }
        ]

        # 添加描述（如果有）
        if description:
            blocks.append(
                {"type": "context", "elements": [{"type": "mrkdwn", "text": description}]}
            )

        # 添加按钮
        buttons = []
        for i, option in enumerate(options[:5]):  # Slack 限制最多 5 个按钮
            style = "primary" if i == 0 else "danger" if option in ["cancel", "取消"] else None
            button = {
                "type": "button",
                "text": {"type": "plain_text", "text": str(option), "emoji": True},
                "value": str(option),
                "action_id": f"hitl_{request_id}_{i}",
            }
            if style:
                button["style"] = style
            buttons.append(button)

        blocks.append({"type": "actions", "elements": buttons})

        result = {"blocks": blocks}
        if self.channel:
            result["channel"] = self.channel

        return result

    def _transform_session_end(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        转换 session_end 为 Slack 消息
        """
        data = event.get("data", {})
        session_id = data.get("session_id", "")
        status = data.get("status", "completed")
        duration_ms = data.get("duration_ms", 0)

        emoji = "✅" if status == "completed" else "❌"
        duration_s = duration_ms / 1000 if duration_ms else 0

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{emoji} *Session 结束*\n\n"
                    f"• Session: `{session_id}`\n"
                    f"• 状态: {status}\n"
                    f"• 耗时: {duration_s:.1f}s",
                },
            }
        ]

        result = {"blocks": blocks}
        if self.channel:
            result["channel"] = self.channel

        return result

    def _transform_error(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        转换 error 为 Slack 附件（红色边栏）
        """
        data = event.get("data", {})
        error = data.get("error", {})
        error_type = error.get("type", "unknown_error")
        error_message = error.get("message", "未知错误")

        return {
            "attachments": [
                {
                    "color": "#ff0000",
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"❌ *错误: {error_type}*\n\n{error_message}",
                            },
                        }
                    ],
                }
            ],
            "channel": self.channel,
        }

    def _transform_default(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        默认转换：简单文本消息
        """
        event_type = event.get("type", "unknown")
        session_id = event.get("session_id", "")

        return {"text": f"📨 事件: {event_type} (session: {session_id})", "channel": self.channel}
