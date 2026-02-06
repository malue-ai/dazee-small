"""
事件适配器基类

定义事件格式转换的抽象接口
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from logger import get_logger

logger = get_logger("event_adapter")


@dataclass
class AdapterConfig:
    """
    适配器配置

    Attributes:
        name: 配置名称（用于日志和识别）
        adapter: 适配器实例
        endpoint: 目标端点 URL
        events: 订阅的事件类型列表，None 或 ["*"] 表示全部
        enabled: 是否启用
        headers: 额外的 HTTP 请求头
        timeout: 请求超时时间（秒）
        retry_count: 失败重试次数
    """

    name: str
    adapter: "EventAdapter"
    endpoint: str
    events: Optional[List[str]] = None
    enabled: bool = True
    headers: Dict[str, str] = field(default_factory=dict)
    timeout: float = 5.0
    retry_count: int = 2


class EventAdapter(ABC):
    """
    事件适配器基类

    职责：将内部事件格式（Zenflux 5 层架构）转换为外部系统格式

    使用示例：
    ```python
    class MyAdapter(EventAdapter):
        name = "my_system"

        def transform(self, event):
            return {"custom_format": event}
    ```
    """

    # 适配器名称（子类覆盖）
    name: str = "base"

    # 默认支持的事件类型（None 表示全部）
    supported_events: Optional[List[str]] = None

    @abstractmethod
    def transform(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        转换事件格式

        Args:
            event: 内部事件（Zenflux 格式）
                {
                    "type": "message_delta",
                    "data": {...},
                    "session_id": "...",
                    "timestamp": "..."
                }

        Returns:
            外部格式（由具体适配器定义）
        """
        pass

    def get_headers(self) -> Dict[str, str]:
        """
        获取 HTTP 请求头

        Returns:
            默认返回 JSON Content-Type
        """
        return {"Content-Type": "application/json"}

    def should_handle(self, event_type: str) -> bool:
        """
        判断是否应该处理该事件类型

        Args:
            event_type: 事件类型

        Returns:
            是否处理
        """
        if self.supported_events is None:
            return True
        if "*" in self.supported_events:
            return True
        return event_type in self.supported_events

    def extract_delta_type(self, event: Dict[str, Any]) -> Optional[str]:
        """
        提取 message_delta 中的 delta.type

        Args:
            event: 事件

        Returns:
            delta.type 或 None
        """
        if event.get("type") == "message_delta":
            data = event.get("data", {})
            delta = data.get("delta", {})
            return delta.get("type")
        return None

    def should_handle_extended(self, event: Dict[str, Any]) -> bool:
        """
        扩展的事件过滤（支持 message_delta 中的 delta.type）

        可以配置订阅特定的 delta 类型，如：
        - "message_delta:confirmation_request"
        - "message_delta:recommended"

        Args:
            event: 完整事件

        Returns:
            是否处理
        """
        event_type = event.get("type", "")

        # 先检查基本类型
        if self.should_handle(event_type):
            return True

        # 检查扩展类型（message_delta:xxx）
        if event_type == "message_delta" and self.supported_events:
            delta_type = self.extract_delta_type(event)
            if delta_type:
                extended_type = f"message_delta:{delta_type}"
                return extended_type in self.supported_events

        return False

    async def enhance_tool_result(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        tool_result: Dict[str, Any],
        conversation_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        增强 tool_result，返回额外的 delta 列表（可选实现）

        子类可以覆盖此方法，根据工具类型生成额外的 message_delta 事件。

        Args:
            tool_name: 工具名称（如 "api_calling"）
            tool_input: 工具输入参数（包含 api_name 等）
            tool_result: 工具返回结果（content_block 格式）
                {
                    "type": "tool_result",
                    "tool_use_id": "...",
                    "content": "...",
                    "is_error": False
                }
            conversation_id: 实际的对话 ID

        Returns:
            delta 列表，每个元素是 {"type": "xxx", "content": "..."}
            默认返回空列表（不增强）
        """
        return []
