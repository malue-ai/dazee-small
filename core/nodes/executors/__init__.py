# -*- coding: utf-8 -*-
"""
Nodes 执行器模块

提供各种命令执行器：
- ShellExecutor: Shell 命令执行
- AppleScriptExecutor: macOS AppleScript 执行（未来）
- BrowserProxyExecutor: 浏览器代理（未来）
"""

from core.nodes.executors.base import BaseExecutor
from core.nodes.executors.shell import ShellExecutor

__all__ = [
    "BaseExecutor",
    "ShellExecutor",
]
