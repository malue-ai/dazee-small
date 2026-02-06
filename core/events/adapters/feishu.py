"""
飞书适配器

将内部事件转换为飞书机器人消息格式
参考: https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot
"""

import json
from typing import Any, Dict, List, Optional

from core.events.adapters.base import EventAdapter
from logger import get_logger

logger = get_logger("feishu_adapter")


class FeishuAdapter(EventAdapter):
    """
    飞书事件适配器

    将内部事件转换为飞书机器人消息格式

    支持的消息类型：
    - text: 文本消息
    - post: 富文本消息
    - interactive: 卡片消息
    """

    name = "feishu"
    supported_events = ["message_delta:confirmation_request", "session_end", "error"]

    def __init__(self, at_users: Optional[List[str]] = None):
        """
        初始化飞书适配器

        Args:
            at_users: 需要 @ 的用户 ID 列表
        """
        self.at_users = at_users or []

    def transform(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        转换为飞书格式
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

        # 默认：文本消息
        return self._transform_default(event)

    def _transform_confirmation_request(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        转换 HITL 确认请求为飞书卡片消息
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

        # 构建卡片元素
        elements = [{"tag": "div", "text": {"tag": "lark_md", "content": question}}]

        # 添加描述
        if description:
            elements.append(
                {"tag": "note", "elements": [{"tag": "plain_text", "content": description}]}
            )

        # 添加按钮
        buttons = []
        for i, option in enumerate(options[:4]):  # 飞书一行最多 4 个按钮
            btn_type = (
                "primary" if i == 0 else "danger" if option in ["cancel", "取消"] else "default"
            )
            buttons.append(
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": str(option)},
                    "type": btn_type,
                    "value": {"request_id": request_id, "option": str(option)},
                }
            )

        elements.append({"tag": "action", "actions": buttons})

        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": "🤖 Agent 确认请求"},
                    "template": "blue",
                },
                "elements": elements,
            },
        }

    def _transform_session_end(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        转换 session_end 为飞书卡片消息
        """
        data = event.get("data", {})
        session_id = data.get("session_id", "")
        status = data.get("status", "completed")
        duration_ms = data.get("duration_ms", 0)

        duration_s = duration_ms / 1000 if duration_ms else 0
        template = "green" if status == "completed" else "red"
        emoji = "✅" if status == "completed" else "❌"

        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": f"{emoji} Session 结束"},
                    "template": template,
                },
                "elements": [
                    {
                        "tag": "div",
                        "fields": [
                            {
                                "is_short": True,
                                "text": {"tag": "lark_md", "content": f"**Session**\n{session_id}"},
                            },
                            {
                                "is_short": True,
                                "text": {"tag": "lark_md", "content": f"**状态**\n{status}"},
                            },
                            {
                                "is_short": True,
                                "text": {
                                    "tag": "lark_md",
                                    "content": f"**耗时**\n{duration_s:.1f}s",
                                },
                            },
                        ],
                    }
                ],
            },
        }

    def _transform_error(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        转换 error 为飞书卡片消息
        """
        data = event.get("data", {})
        error = data.get("error", {})
        error_type = error.get("type", "unknown_error")
        error_message = error.get("message", "未知错误")

        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": f"❌ 错误: {error_type}"},
                    "template": "red",
                },
                "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": error_message}}],
            },
        }

    def _transform_default(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        默认转换：文本消息
        """
        event_type = event.get("type", "unknown")
        session_id = event.get("session_id", "")

        return {
            "msg_type": "text",
            "content": {"text": f"📨 事件: {event_type} (session: {session_id})"},
        }
