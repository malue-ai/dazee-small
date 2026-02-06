"""
Gateway 网关层

负责：
- 消息预处理（去重、防抖、合并）
- 权限检查
- 路由分发
"""

from channels.gateway.preprocessor import (
    MessagePreprocessor,
    MessageDeduper,
    InboundDebouncer,
    TextFragmentBuffer,
    MediaGroupBuffer,
)
from channels.gateway.security import SecurityChecker

__all__ = [
    "MessagePreprocessor",
    "MessageDeduper",
    "InboundDebouncer",
    "TextFragmentBuffer",
    "MediaGroupBuffer",
    "SecurityChecker",
]
