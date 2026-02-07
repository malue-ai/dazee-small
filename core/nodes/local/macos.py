# -*- coding: utf-8 -*-
"""
macOS 本地节点

实现 macOS 平台特定的本地操作能力：
- Shell 命令执行
- AppleScript 执行
- 系统通知
- 屏幕截图
- 剪贴板操作
"""

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

from core.nodes.local.base import LocalNodeBase

logger = logging.getLogger(__name__)


class MacOSLocalNode(LocalNodeBase):
    """
    macOS 本地节点

    对齐 clawdbot 的 MacNodeRuntime
    """

    # macOS 默认安全 bins（与 config.yaml 保持一致）
    DEFAULT_SAFE_BINS = [
        # 系统基础命令
        "osascript",
        "open",
        "screencapture",
        "pbcopy",
        "pbpaste",
        "say",
        "which",
        "ls",
        "cat",
        "echo",
        "pwd",
        "date",
        # 文件操作
        "mkdir",
        "mv",
        "cp",
        "rm",
        "rmdir",
        "touch",
        "chmod",
        "find",
        "xargs",
        "head",
        "tail",
        "grep",
        "sort",
        "uniq",
        "wc",
        # Shell 与开发工具
        "bash",
        "sh",
        "zsh",
        "python3",
        "sleep",
        # UI 自动化（Peekaboo）
        "peekaboo",
    ]

    # macOS 默认命令白名单（完整路径）
    DEFAULT_ALLOWLIST = [
        # 系统基础命令
        "/usr/bin/osascript",
        "/usr/bin/open",
        "/usr/sbin/screencapture",
        "/usr/bin/pbcopy",
        "/usr/bin/pbpaste",
        "/usr/bin/say",
        "/usr/bin/which",
        "/bin/ls",
        "/bin/cat",
        "/bin/echo",
        "/bin/pwd",
        "/bin/date",
        # 文件操作
        "/bin/mkdir",
        "/bin/mv",
        "/bin/cp",
        "/bin/rm",
        "/bin/rmdir",
        "/usr/bin/touch",
        "/bin/chmod",
        "/usr/bin/find",
        "/usr/bin/xargs",
        "/usr/bin/head",
        "/usr/bin/tail",
        "/usr/bin/grep",
        "/usr/bin/sort",
        "/usr/bin/uniq",
        "/usr/bin/wc",
        # Shell 与开发工具
        "/bin/bash",
        "/bin/sh",
        "/bin/zsh",
        "/usr/bin/python3",
        "/usr/local/bin/python3",
        "/opt/homebrew/bin/python3",
        "/bin/sleep",
        # UI 自动化（Peekaboo - Homebrew 安装路径）
        "/opt/homebrew/bin/peekaboo",
        "/usr/local/bin/peekaboo",
    ]

    def __init__(
        self,
        node_id: str = "local",
        display_name: str = "macOS 本地节点",
        allowlist: Optional[List[str]] = None,
        safe_bins: Optional[List[str]] = None,
    ):
        """
        初始化 macOS 本地节点

        Args:
            node_id: 节点 ID
            display_name: 显示名称
            allowlist: 命令白名单（None 则使用默认）
            safe_bins: 安全的可执行文件名（None 则使用默认）
        """
        super().__init__(
            node_id=node_id,
            display_name=display_name,
            allowlist=allowlist or self.DEFAULT_ALLOWLIST,
            safe_bins=safe_bins or self.DEFAULT_SAFE_BINS,
        )

    @property
    def platform(self) -> str:
        return "darwin"

    @property
    def capabilities(self) -> List[str]:
        return [
            "shell",
            "applescript",
            "notify",
            "screenshot",
            "clipboard",
            "open_app",
            "open_url",
        ]

    async def _do_initialize(self) -> None:
        """macOS 特定初始化"""
        # 检查 osascript 是否可用
        result = await self.shell_executor.which("osascript")
        if not result:
            logger.warning("osascript 不可用，AppleScript 功能将受限")

    async def _handle_system_notify(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        发送 macOS 系统通知

        使用 osascript 调用 AppleScript
        """
        title = params.get("title", "通知")
        message = params.get("message", "")
        subtitle = params.get("subtitle", "")
        sound = params.get("sound", True)

        # 构建 AppleScript
        script_parts = [f'display notification "{self._escape_applescript(message)}"']
        script_parts.append(f'with title "{self._escape_applescript(title)}"')
        if subtitle:
            script_parts.append(f'subtitle "{self._escape_applescript(subtitle)}"')
        if sound:
            script_parts.append('sound name "default"')

        script = " ".join(script_parts)

        result = await self.execute_applescript(script)
        return {
            "sent": result.get("success", False),
            "title": title,
            "message": message,
        }

    async def execute_applescript(self, script: str, timeout: float = 30.0) -> Dict[str, Any]:
        """
        执行 AppleScript

        Args:
            script: AppleScript 脚本
            timeout: 超时时间（秒）

        Returns:
            执行结果
        """
        result = await self.shell_executor.execute(
            command=["osascript", "-e", script],
            timeout=timeout,
        )

        return {
            "success": result.success,
            "output": result.stdout.strip() if result.stdout else "",
            "error": result.stderr.strip() if result.stderr else None,
        }

    async def open_app(
        self,
        app_name: str,
        url: Optional[str] = None,
        wait: bool = False,
    ) -> Dict[str, Any]:
        """
        打开应用程序

        Args:
            app_name: 应用名称
            url: 要打开的 URL（可选）
            wait: 是否等待应用启动
        """
        command = ["open"]
        if wait:
            command.append("-W")
        command.extend(["-a", app_name])
        if url:
            command.append(url)

        result = await self.shell_executor.execute(command)
        return {
            "success": result.success,
            "app": app_name,
            "url": url,
        }

    async def open_url(self, url: str) -> Dict[str, Any]:
        """
        打开 URL

        Args:
            url: 要打开的 URL
        """
        result = await self.shell_executor.execute(["open", url])
        return {
            "success": result.success,
            "url": url,
        }

    async def open_path(self, path: str) -> Dict[str, Any]:
        """
        在 Finder 中打开路径

        Args:
            path: 文件或文件夹路径
        """
        expanded_path = os.path.expanduser(path)
        result = await self.shell_executor.execute(["open", expanded_path])
        return {
            "success": result.success,
            "path": expanded_path,
        }

    async def screenshot(
        self,
        output_path: Optional[str] = None,
        region: Optional[Dict[str, int]] = None,
        window: bool = False,
        interactive: bool = False,
    ) -> Dict[str, Any]:
        """
        截取屏幕截图

        Args:
            output_path: 输出路径（可选，默认剪贴板）
            region: 区域 {x, y, width, height}（可选）
            window: 是否截取窗口
            interactive: 是否交互式选择
        """
        command = ["screencapture"]

        if not output_path:
            command.append("-c")  # 复制到剪贴板

        if window:
            command.append("-w")  # 截取窗口
        elif interactive:
            command.append("-i")  # 交互式选择

        if output_path:
            expanded_path = os.path.expanduser(output_path)
            command.append(expanded_path)

        result = await self.shell_executor.execute(command)
        return {
            "success": result.success,
            "output_path": output_path,
            "to_clipboard": not output_path,
        }

    async def clipboard_get(self) -> Dict[str, Any]:
        """获取剪贴板内容"""
        result = await self.shell_executor.execute(["pbpaste"])
        return {
            "success": result.success,
            "content": result.stdout if result.success else None,
        }

    async def clipboard_set(self, content: str) -> Dict[str, Any]:
        """设置剪贴板内容"""
        # 通过 echo 和管道设置剪贴板
        result = await self.shell_executor.execute(
            ["bash", "-c", f"echo -n {self._shell_escape(content)} | pbcopy"]
        )
        return {
            "success": result.success,
            "length": len(content),
        }

    async def say(self, text: str, voice: Optional[str] = None) -> Dict[str, Any]:
        """
        文字转语音

        Args:
            text: 要朗读的文字
            voice: 语音名称（可选）
        """
        command = ["say"]
        if voice:
            command.extend(["-v", voice])
        command.append(text)

        result = await self.shell_executor.execute(command)
        return {
            "success": result.success,
            "text": text,
            "voice": voice,
        }

    async def _handle_platform_command(
        self, command: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """处理 macOS 平台特定命令"""
        if command == "applescript":
            script = params.get("script", "")
            if not script:
                raise ValueError("缺少 script 参数")
            return await self.execute_applescript(script)

        elif command == "open_app":
            app_name = params.get("app_name", "")
            if not app_name:
                raise ValueError("缺少 app_name 参数")
            return await self.open_app(
                app_name=app_name,
                url=params.get("url"),
                wait=params.get("wait", False),
            )

        elif command == "open_url":
            url = params.get("url", "")
            if not url:
                raise ValueError("缺少 url 参数")
            return await self.open_url(url)

        elif command == "open_path":
            path = params.get("path", "")
            if not path:
                raise ValueError("缺少 path 参数")
            return await self.open_path(path)

        elif command == "screenshot":
            return await self.screenshot(
                output_path=params.get("output_path"),
                window=params.get("window", False),
                interactive=params.get("interactive", False),
            )

        elif command == "clipboard.get":
            return await self.clipboard_get()

        elif command == "clipboard.set":
            content = params.get("content", "")
            return await self.clipboard_set(content)

        elif command == "say":
            text = params.get("text", "")
            if not text:
                raise ValueError("缺少 text 参数")
            return await self.say(text, params.get("voice"))

        else:
            return await super()._handle_platform_command(command, params)

    @staticmethod
    def _escape_applescript(text: str) -> str:
        """转义 AppleScript 字符串"""
        return text.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _shell_escape(text: str) -> str:
        """转义 shell 字符串"""
        return "'" + text.replace("'", "'\"'\"'") + "'"
