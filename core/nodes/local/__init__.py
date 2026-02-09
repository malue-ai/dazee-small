# -*- coding: utf-8 -*-
"""
本地节点模块

提供各平台的本地节点实现：
- MacOSLocalNode: macOS 平台
- WindowsLocalNode: Windows 平台（未来）
- LinuxLocalNode: Linux 平台（未来）
"""

from core.nodes.local.base import LocalNodeBase
from core.nodes.local.macos import MacOSLocalNode

__all__ = [
    "LocalNodeBase",
    "MacOSLocalNode",
]
