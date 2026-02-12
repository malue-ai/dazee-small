# -*- coding: utf-8 -*-
"""
Windows 本地节点

实现 Windows 平台特定的本地操作能力：
- Shell 命令执行（cmd / PowerShell）
- 系统通知（Toast Notification via PowerShell）
- 剪贴板操作（PowerShell Get-Clipboard / Set-Clipboard）
- 文件/URL 打开（start 命令）
- 屏幕截图（PowerShell + System.Drawing）
- TTS 文字转语音（PowerShell SAPI.SpVoice）
"""

import logging
import os
import tempfile
from typing import Any, Dict, List, Optional

from core.nodes.local.base import LocalNodeBase

logger = logging.getLogger(__name__)


class WindowsLocalNode(LocalNodeBase):
    """
    Windows 本地节点

    提供 Windows 平台的本地操作能力，对齐 macOS 节点的功能集。
    """

    # Windows 默认安全 bins
    DEFAULT_SAFE_BINS = [
        # 系统基础命令
        "cmd",
        "cmd.exe",
        "powershell",
        "powershell.exe",
        "pwsh",
        "pwsh.exe",
        "where",
        "where.exe",
        "dir",
        "echo",
        "type",
        "start",
        "whoami",
        "hostname",
        "systeminfo",
        "tasklist",
        "tasklist.exe",
        "wmic",
        "wmic.exe",
        # 文件操作
        "mkdir",
        "rmdir",
        "copy",
        "xcopy",
        "robocopy",
        "move",
        "del",
        "ren",
        "attrib",
        "findstr",
        "find",
        "sort",
        "more",
        "tree",
        # 网络
        "ping",
        "ipconfig",
        "nslookup",
        "netstat",
        "curl",
        "curl.exe",
        # 开发工具
        "python",
        "python3",
        "python.exe",
        "python3.exe",
        "node",
        "node.exe",
        "npm",
        "npm.cmd",
        "git",
        "git.exe",
        "pip",
        "pip.exe",
        "pip3",
        "pip3.exe",
        # 剪贴板 & 系统工具
        "clip",
        "clip.exe",
        "explorer",
        "explorer.exe",
        "notepad",
        "notepad.exe",
        # 文本处理 (Git Bash / WSL 提供)
        "cat",
        "head",
        "tail",
        "grep",
        "ls",
        "wc",
        "bash",
        "bash.exe",
        "sh",
        # 包管理
        "winget",
        "winget.exe",
    ]

    # Windows 默认命令白名单（完整路径）
    DEFAULT_ALLOWLIST = [
        # System32
        r"C:\Windows\System32\cmd.exe",
        r"C:\Windows\System32\where.exe",
        r"C:\Windows\System32\findstr.exe",
        r"C:\Windows\System32\ping.exe",
        r"C:\Windows\System32\ipconfig.exe",
        r"C:\Windows\System32\whoami.exe",
        r"C:\Windows\System32\hostname.exe",
        r"C:\Windows\System32\systeminfo.exe",
        r"C:\Windows\System32\curl.exe",
        r"C:\Windows\System32\xcopy.exe",
        r"C:\Windows\System32\robocopy.exe",
        r"C:\Windows\System32\attrib.exe",
        r"C:\Windows\System32\tree.com",
        r"C:\Windows\System32\sort.exe",
        r"C:\Windows\System32\more.com",
        r"C:\Windows\System32\tasklist.exe",
        r"C:\Windows\System32\wmic.exe",
        r"C:\Windows\System32\netstat.exe",
        r"C:\Windows\System32\nslookup.exe",
        r"C:\Windows\System32\clip.exe",
        r"C:\Windows\System32\notepad.exe",
        # Explorer
        r"C:\Windows\explorer.exe",
        # PowerShell
        r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        r"C:\Program Files\PowerShell\7\pwsh.exe",
    ]

    def __init__(
        self,
        node_id: str = "local",
        display_name: str = "Windows 本地节点",
        allowlist: Optional[List[str]] = None,
        safe_bins: Optional[List[str]] = None,
    ):
        """
        Initialize Windows local node.

        Args:
            node_id: Node ID
            display_name: Display name
            allowlist: Command allowlist (None uses defaults)
            safe_bins: Safe executable names (None uses defaults)
        """
        super().__init__(
            node_id=node_id,
            display_name=display_name,
            allowlist=allowlist or self.DEFAULT_ALLOWLIST,
            safe_bins=safe_bins or self.DEFAULT_SAFE_BINS,
        )
        self._has_powershell7 = False

    @property
    def platform(self) -> str:
        return "win32"

    @property
    def capabilities(self) -> List[str]:
        return [
            "shell",
            "powershell",
            "notify",
            "screenshot",
            "clipboard",
            "open_app",
            "open_url",
        ]

    async def _do_initialize(self) -> None:
        """Windows-specific initialization."""
        # Resolve PowerShell path: use %SystemRoot% path
        self._powershell_path = self._resolve_powershell_path()
        logger.info(f"PowerShell 路径: {self._powershell_path}")

        # Verify PowerShell is actually callable
        result = await self.shell_executor.which("powershell")
        if not result:
            logger.warning("PowerShell 不可用，部分功能将受限")

        # Check for PowerShell 7 (pwsh) for enhanced features
        pwsh_result = await self.shell_executor.which("pwsh")
        self._has_powershell7 = pwsh_result is not None
        if self._has_powershell7:
            logger.info("检测到 PowerShell 7 (pwsh)，启用增强功能")

    @staticmethod
    def _resolve_powershell_path() -> str:
        """
        Resolve PowerShell executable path from %SystemRoot%.

        Check SystemRoot/WINDIR environment variable
        to build the full path, falling back to bare 'powershell.exe'.
        """
        system_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR")
        if system_root:
            candidate = os.path.join(
                system_root,
                "System32",
                "WindowsPowerShell",
                "v1.0",
                "powershell.exe",
            )
            if os.path.isfile(candidate):
                return candidate
        return "powershell.exe"

    def _get_powershell_cmd(self) -> str:
        """Get the best available PowerShell executable."""
        if self._has_powershell7:
            return "pwsh"
        return getattr(self, "_powershell_path", "powershell")

    async def _handle_system_notify(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send Windows toast notification via PowerShell.
        """
        title = params.get("title", "通知")
        message = params.get("message", "")

        # Use PowerShell BurntToast module or fallback to basic notification
        ps_script = self._build_toast_script(title, message)

        result = await self.shell_executor.execute(
            command=[self._get_powershell_cmd(), "-NoProfile", "-Command", ps_script],
            timeout=10.0,
        )

        return {
            "sent": result.success,
            "title": title,
            "message": message,
            "error": result.stderr if not result.success else None,
        }

    async def execute_powershell(
        self, script: str, timeout: float = 30.0
    ) -> Dict[str, Any]:
        """
        Execute PowerShell script.

        Args:
            script: PowerShell script content
            timeout: Timeout in seconds

        Returns:
            Execution result
        """
        result = await self.shell_executor.execute(
            command=[self._get_powershell_cmd(), "-NoProfile", "-Command", script],
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
        Open an application on Windows.

        Args:
            app_name: Application name or path
            url: URL to open (optional)
            wait: Whether to wait for the app to start
        """
        if url:
            command = ["cmd", "/c", "start", "", app_name, url]
        elif wait:
            command = ["cmd", "/c", "start", "/wait", "", app_name]
        else:
            command = ["cmd", "/c", "start", "", app_name]

        result = await self.shell_executor.execute(command)
        return {
            "success": result.success,
            "app": app_name,
            "url": url,
        }

    async def open_url(self, url: str) -> Dict[str, Any]:
        """
        Open URL in default browser.

        Args:
            url: URL to open
        """
        result = await self.shell_executor.execute(["cmd", "/c", "start", "", url])
        return {
            "success": result.success,
            "url": url,
        }

    async def open_path(self, path: str) -> Dict[str, Any]:
        """
        Open path in Windows Explorer.

        Args:
            path: File or folder path
        """
        expanded_path = os.path.expanduser(path)
        result = await self.shell_executor.execute(
            ["explorer.exe", expanded_path]
        )
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
        Take a screenshot on Windows using PowerShell + System.Drawing.

        Args:
            output_path: Output file path (optional, defaults to temp)
            region: Capture region {x, y, width, height} (optional)
            window: Whether to capture active window only
            interactive: Not supported on Windows, ignored
        """
        if not output_path:
            output_path = os.path.join(tempfile.gettempdir(), "screenshot.png")

        expanded_path = os.path.expanduser(output_path)
        # Normalize to backslash for PowerShell
        ps_path = expanded_path.replace("/", "\\")

        if region:
            x = region.get("x", 0)
            y = region.get("y", 0)
            width = region.get("width", 1920)
            height = region.get("height", 1080)
            ps_script = self._build_region_screenshot_script(
                ps_path, x, y, width, height
            )
        elif window:
            ps_script = self._build_window_screenshot_script(ps_path)
        else:
            ps_script = self._build_fullscreen_screenshot_script(ps_path)

        result = await self.execute_powershell(ps_script, timeout=10.0)
        return {
            "success": result.get("success", False),
            "output_path": expanded_path,
            "to_clipboard": False,
            "error": result.get("error") if not result.get("success") else None,
        }

    async def clipboard_get(self) -> Dict[str, Any]:
        """Get clipboard content via PowerShell."""
        result = await self.execute_powershell("Get-Clipboard")
        return {
            "success": result.get("success", False),
            "content": result.get("output") if result.get("success") else None,
        }

    async def clipboard_set(self, content: str) -> Dict[str, Any]:
        """
        Set clipboard content with fallback chain.

        Attempts: clip.exe → PowerShell Set-Clipboard
        """
        # Attempt 1: clip.exe (fastest, works in WSL and native Windows)
        clip_result = await self.shell_executor.execute(
            ["cmd", "/c", f"echo {self._cmd_escape(content)}| clip"],
            timeout=5.0,
        )
        if clip_result.success:
            return {"success": True, "length": len(content), "method": "clip.exe"}

        # Attempt 2: PowerShell Set-Clipboard (fallback)
        escaped = content.replace("'", "''")
        ps_result = await self.execute_powershell(
            f"Set-Clipboard -Value '{escaped}'"
        )
        return {
            "success": ps_result.get("success", False),
            "length": len(content),
            "method": "powershell",
        }

    @staticmethod
    def _cmd_escape(text: str) -> str:
        """Escape text for cmd.exe echo command."""
        # Escape special cmd characters
        for ch in ("^", "&", "|", "<", ">", "(", ")", "%"):
            text = text.replace(ch, f"^{ch}")
        return text

    async def say(self, text: str, voice: Optional[str] = None) -> Dict[str, Any]:
        """
        Text-to-speech via PowerShell SAPI.SpVoice.

        Args:
            text: Text to speak
            voice: Voice name (optional)
        """
        escaped_text = text.replace("'", "''")

        if voice:
            escaped_voice = voice.replace("'", "''")
            ps_script = (
                "$sp = New-Object -ComObject SAPI.SpVoice; "
                "$voices = $sp.GetVoices(); "
                "foreach ($v in $voices) { "
                f"  if ($v.GetDescription() -like '*{escaped_voice}*') {{ "
                "    $sp.Voice = $v; break "
                "  } "
                "}; "
                f"$sp.Speak('{escaped_text}')"
            )
        else:
            ps_script = (
                "$sp = New-Object -ComObject SAPI.SpVoice; "
                f"$sp.Speak('{escaped_text}')"
            )

        result = await self.execute_powershell(ps_script, timeout=60.0)
        return {
            "success": result.get("success", False),
            "text": text,
            "voice": voice,
        }

    async def _handle_platform_command(
        self, command: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle Windows platform-specific commands."""
        if command == "powershell":
            script = params.get("script", "")
            if not script:
                raise ValueError("缺少 script 参数")
            return await self.execute_powershell(script)

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
                region=params.get("region"),
                window=params.get("window", False),
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

    # ==================== Screenshot Helpers ====================

    @staticmethod
    def _build_fullscreen_screenshot_script(output_path: str) -> str:
        """Build PowerShell script for full-screen screenshot."""
        return (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "Add-Type -AssemblyName System.Drawing; "
            "$screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds; "
            "$bmp = New-Object System.Drawing.Bitmap($screen.Width, $screen.Height); "
            "$g = [System.Drawing.Graphics]::FromImage($bmp); "
            "$g.CopyFromScreen($screen.Location, [System.Drawing.Point]::Empty, $screen.Size); "
            f"$bmp.Save('{output_path}'); "
            "$g.Dispose(); $bmp.Dispose()"
        )

    @staticmethod
    def _build_region_screenshot_script(
        output_path: str, x: int, y: int, width: int, height: int
    ) -> str:
        """Build PowerShell script for region screenshot."""
        return (
            "Add-Type -AssemblyName System.Drawing; "
            f"$bmp = New-Object System.Drawing.Bitmap({width}, {height}); "
            "$g = [System.Drawing.Graphics]::FromImage($bmp); "
            f"$g.CopyFromScreen({x}, {y}, 0, 0, $bmp.Size); "
            f"$bmp.Save('{output_path}'); "
            "$g.Dispose(); $bmp.Dispose()"
        )

    @staticmethod
    def _build_window_screenshot_script(output_path: str) -> str:
        """Build PowerShell script for foreground window screenshot."""
        # Use user32.dll to get the foreground window rect
        return (
            "Add-Type -AssemblyName System.Drawing; "
            "Add-Type -Name WinAPI -Namespace Screenshot -MemberDefinition '"
            "[DllImport(\"user32.dll\")] public static extern IntPtr GetForegroundWindow(); "
            "[DllImport(\"user32.dll\")] public static extern bool GetWindowRect("
            "IntPtr hWnd, out System.Drawing.Rectangle lpRect);'; "
            "$hwnd = [Screenshot.WinAPI]::GetForegroundWindow(); "
            "$rect = New-Object System.Drawing.Rectangle; "
            "[Screenshot.WinAPI]::GetWindowRect($hwnd, [ref]$rect) | Out-Null; "
            "$w = $rect.Width - $rect.X; $h = $rect.Height - $rect.Y; "
            "$bmp = New-Object System.Drawing.Bitmap($w, $h); "
            "$g = [System.Drawing.Graphics]::FromImage($bmp); "
            "$g.CopyFromScreen($rect.X, $rect.Y, 0, 0, "
            "(New-Object System.Drawing.Size($w, $h))); "
            f"$bmp.Save('{output_path}'); "
            "$g.Dispose(); $bmp.Dispose()"
        )

    # ==================== Toast Notification ====================

    @staticmethod
    def _build_toast_script(title: str, message: str) -> str:
        """
        Build PowerShell toast notification script.

        Uses Windows built-in .NET APIs (no third-party module required).
        """
        escaped_title = title.replace("'", "''")
        escaped_message = message.replace("'", "''")

        return (
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
            "ContentType = WindowsRuntime] > $null; "
            "$template = [Windows.UI.Notifications.ToastNotificationManager]::"
            "GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
            "$textNodes = $template.GetElementsByTagName('text'); "
            f"$textNodes.Item(0).AppendChild($template.CreateTextNode('{escaped_title}')) > $null; "
            f"$textNodes.Item(1).AppendChild($template.CreateTextNode('{escaped_message}')) > $null; "
            "$toast = [Windows.UI.Notifications.ToastNotification]::new($template); "
            "[Windows.UI.Notifications.ToastNotificationManager]::"
            "CreateToastNotifier('ZenFlux Agent').Show($toast)"
        )
