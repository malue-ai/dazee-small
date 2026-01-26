"""
E2B 沙盒模板定义

包含：
- frontend_template: 前端开发模板（Node.js 20）
"""

from .frontend_template import (
    frontend_template,
    FRONTEND_TEMPLATE_ALIAS,
    FRONTEND_TEMPLATE_ALIAS_DEV,
)

__all__ = [
    "frontend_template",
    "FRONTEND_TEMPLATE_ALIAS",
    "FRONTEND_TEMPLATE_ALIAS_DEV",
]
