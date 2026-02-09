"""
通用 Webhook 适配器

支持自定义模板，可以将内部事件映射为任意外部格式
"""

import json
import re
from typing import Any, Dict, Optional

from core.events.adapters.base import EventAdapter
from logger import get_logger

logger = get_logger("webhook_adapter")


class WebhookAdapter(EventAdapter):
    """
    通用 Webhook 适配器

    支持自定义模板映射，使用简单的占位符语法：
    - {{ type }} - 事件类型
    - {{ data }} - 事件数据
    - {{ session_id }} - Session ID
    - {{ timestamp }} - 时间戳
    - {{ data.xxx }} - 嵌套字段访问

    使用示例：
    ```python
    adapter = WebhookAdapter(template={
        "event_type": "{{ type }}",
        "payload": "{{ data }}",
        "source": "zenflux",
        "ts": "{{ timestamp }}"
    })
    ```
    """

    name = "webhook"

    def __init__(
        self, template: Optional[Dict[str, Any]] = None, supported_events: Optional[list] = None
    ):
        """
        初始化 Webhook 适配器

        Args:
            template: 输出格式模板，None 则原样返回
            supported_events: 支持的事件类型列表
        """
        self.template = template
        self.supported_events = supported_events

    def transform(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        转换事件格式

        如果没有配置模板，则原样返回事件
        """
        if not self.template:
            return event

        return self._apply_template(self.template, event)

    def _apply_template(self, template: Any, event: Dict[str, Any]) -> Any:
        """
        递归应用模板

        Args:
            template: 模板（可以是 dict, list, str）
            event: 事件数据

        Returns:
            转换后的结果
        """
        if isinstance(template, dict):
            return {key: self._apply_template(value, event) for key, value in template.items()}
        elif isinstance(template, list):
            return [self._apply_template(item, event) for item in template]
        elif isinstance(template, str):
            return self._render_string(template, event)
        else:
            return template

    def _render_string(self, template_str: str, event: Dict[str, Any]) -> Any:
        """
        渲染字符串模板

        支持：
        - {{ type }} - 简单字段
        - {{ data.delta.type }} - 嵌套字段
        - {{ data | json }} - JSON 序列化

        Args:
            template_str: 模板字符串
            event: 事件数据

        Returns:
            渲染结果（可能是字符串或原始值）
        """
        # 检查是否是纯占位符（整个字符串就是一个占位符）
        pure_placeholder = re.match(r"^\{\{\s*(.+?)\s*\}\}$", template_str.strip())

        if pure_placeholder:
            # 纯占位符，返回原始值（不强制转为字符串）
            expr = pure_placeholder.group(1)
            return self._resolve_expression(expr, event)

        # 混合模板，替换所有占位符
        def replacer(match):
            expr = match.group(1).strip()
            value = self._resolve_expression(expr, event)
            if isinstance(value, (dict, list)):
                return json.dumps(value, ensure_ascii=False)
            return str(value) if value is not None else ""

        return re.sub(r"\{\{\s*(.+?)\s*\}\}", replacer, template_str)

    def _resolve_expression(self, expr: str, event: Dict[str, Any]) -> Any:
        """
        解析表达式

        支持：
        - type - 简单字段
        - data.delta.type - 嵌套字段
        - data | json - JSON 序列化

        Args:
            expr: 表达式
            event: 事件数据

        Returns:
            解析结果
        """
        # 检查是否有管道操作符
        if "|" in expr:
            parts = expr.split("|", 1)
            field_path = parts[0].strip()
            filter_name = parts[1].strip()

            value = self._get_nested_value(event, field_path)

            # 应用过滤器
            if filter_name == "json":
                return json.dumps(value, ensure_ascii=False) if value else ""

            return value

        # 简单字段访问
        return self._get_nested_value(event, expr)

    def _get_nested_value(self, obj: Dict[str, Any], path: str) -> Any:
        """
        获取嵌套字段值

        Args:
            obj: 对象
            path: 字段路径，如 "data.delta.type"

        Returns:
            字段值，不存在则返回 None
        """
        parts = path.split(".")
        current = obj

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None

        return current
