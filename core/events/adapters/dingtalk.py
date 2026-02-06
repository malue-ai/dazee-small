"""
钉钉适配器

将内部事件转换为钉钉机器人消息格式
参考: https://open.dingtalk.com/document/orgapp/custom-robots-send-group-messages
"""

import json
from typing import Any, Dict, List, Optional

from core.events.adapters.base import EventAdapter
from logger import get_logger

logger = get_logger("dingtalk_adapter")


class DingTalkAdapter(EventAdapter):
    """
    钉钉事件适配器

    将内部事件转换为钉钉机器人消息格式

    支持的消息类型：
    - text: 文本消息
    - markdown: Markdown 消息
    - actionCard: 卡片消息（支持按钮）
    """

    name = "dingtalk"
    supported_events = ["message_delta:confirmation_request", "session_end", "error"]

    def __init__(self, at_mobiles: Optional[List[str]] = None, at_all: bool = False):
        """
        初始化钉钉适配器

        Args:
            at_mobiles: 需要 @ 的手机号列表
            at_all: 是否 @ 所有人
        """
        self.at_mobiles = at_mobiles or []
        self.at_all = at_all

    def transform(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        转换为钉钉格式
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
        转换 HITL 确认请求为钉钉 ActionCard
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

        # 构建 Markdown 内容
        markdown_text = f"### 🤖 Agent 确认请求\n\n{question}"
        if description:
            markdown_text += f"\n\n> {description}"

        # 构建按钮
        btns = []
        for option in options[:5]:  # 钉钉限制按钮数量
            btns.append(
                {
                    "title": str(option),
                    "actionURL": f"dingtalk://dingtalkclient/page/link?url=callback://confirm&request_id={request_id}&option={option}",
                }
            )

        return {
            "msgtype": "actionCard",
            "actionCard": {
                "title": "Agent 确认请求",
                "text": markdown_text,
                "btnOrientation": "0",  # 0 垂直排列，1 水平排列
                "btns": btns,
            },
        }

    def _transform_session_end(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        转换 session_end 为钉钉 Markdown 消息
        """
        data = event.get("data", {})
        session_id = data.get("session_id", "")
        status = data.get("status", "completed")
        duration_ms = data.get("duration_ms", 0)

        emoji = "✅" if status == "completed" else "❌"
        duration_s = duration_ms / 1000 if duration_ms else 0

        return {
            "msgtype": "markdown",
            "markdown": {
                "title": "Session 结束",
                "text": f"### {emoji} Session 结束\n\n"
                f"- **Session**: {session_id}\n"
                f"- **状态**: {status}\n"
                f"- **耗时**: {duration_s:.1f}s",
            },
            "at": {"atMobiles": self.at_mobiles, "isAtAll": self.at_all},
        }

    def _transform_error(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        转换 error 为钉钉 Markdown 消息
        """
        data = event.get("data", {})
        error = data.get("error", {})
        error_type = error.get("type", "unknown_error")
        error_message = error.get("message", "未知错误")

        return {
            "msgtype": "markdown",
            "markdown": {
                "title": f"错误: {error_type}",
                "text": f"### ❌ 错误: {error_type}\n\n{error_message}",
            },
            "at": {"atMobiles": self.at_mobiles, "isAtAll": self.at_all},
        }

    def _transform_default(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        默认转换：文本消息
        """
        event_type = event.get("type", "unknown")
        session_id = event.get("session_id", "")

        return {
            "msgtype": "text",
            "text": {"content": f"📨 事件: {event_type} (session: {session_id})"},
            "at": {"atMobiles": self.at_mobiles, "isAtAll": self.at_all},
        }
