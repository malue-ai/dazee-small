# -*- coding: utf-8 -*-
"""
Nodes 模块 - 本地/远程节点操作

Nodes 架构，支持本地设备操作和未来远程节点扩展。

核心组件：
- NodeManager: 节点生命周期管理
- NodeProtocol: 通信协议定义
- LocalNode: 本地节点实现（macOS/Windows/Linux）
- ShellExecutor: Shell 命令执行器
"""

from core.nodes.manager import NodeManager
from core.nodes.protocol import (
    NodeCommand,
    NodeInvokeRequest,
    NodeInvokeResponse,
    ShellResult,
)

__all__ = [
    "NodeCommand",
    "NodeInvokeRequest",
    "NodeInvokeResponse",
    "ShellResult",
    "NodeManager",
]
