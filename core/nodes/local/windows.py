# -*- coding: utf-8 -*-
"""
Windows 本地节点（全面升级版）

实现 Windows 平台特定的本地操作能力：
- Shell 命令执行（cmd / PowerShell）
- 动态执行审批策略（ExecApprovalPolicy，支持远程管理）
- 系统通知（Toast Notification + 通知分类系统）
- 剪贴板操作（stdin pipe 模式，支持多行 Unicode）
- 文件/URL 打开（start 命令）
- 屏幕截图（多显示器 + 格式/质量参数 + 修复 RECT）
- 屏幕列表（screen.list，多显示器枚举）
- 屏幕录制（screen.record，ffmpeg gdigrab）
- TTS 文字转语音（PowerShell SAPI.SpVoice）
- Canvas（canvas.present/hide/navigate/eval/snapshot/a2ui，Playwright 引擎）
- 摄像头（WinRT MediaCapture 优先，ffmpeg 备选）
- 摄像头视频录制（camera.clip）
- 位置信息（location.get，Windows Geolocation WinRT）
"""

import asyncio
import base64
import json
import logging
import os
import tempfile
import threading
from typing import Any, Dict, List, Optional

from core.nodes.local.base import LocalNodeBase
from core.nodes.local.exec_policy import ExecApprovalPolicy
from core.nodes.local.notify_categorizer import NotificationCategorizer

logger = logging.getLogger(__name__)

# 数据目录：%LOCALAPPDATA%\XiaoDazi 或 fallback 到 tempdir
_DATA_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", tempfile.gettempdir()),
    "XiaoDazi",
)

# ── Canvas URL 安全校验 ────────────────────────────────────────────────────────
_BLOCKED_SCHEMES = ("javascript:", "file://", "data:")
_BLOCKED_HOSTS = (
    "127.0.0.1", "localhost", "::1",
    "0.0.0.0",
)
_PRIVATE_PREFIXES = ("192.168.", "10.", "172.16.", "172.17.", "172.18.", "172.19.",
                     "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
                     "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.")


def _is_canvas_url_safe(url: str) -> bool:
    """检查 canvas URL 是否安全（防止 SSRF / 本地文件读取）"""
    lower = url.lower().strip()
    for scheme in _BLOCKED_SCHEMES:
        if lower.startswith(scheme):
            return False
    try:
        from urllib.parse import urlparse
        host = urlparse(url).hostname or ""
        if host in _BLOCKED_HOSTS:
            return False
        for prefix in _PRIVATE_PREFIXES:
            if host.startswith(prefix):
                return False
    except Exception:
        pass
    return True


# ── Canvas 管理器（Playwright 引擎）──────────────────────────────────────────
class _CanvasManager:
    """
    Canvas 生命周期管理器。

    使用 Playwright（headed Chromium）作为画布引擎，支持：
    - present / hide / navigate
    - eval（执行 JS）
    - snapshot（截图返回 base64）
    - a2ui.push / a2ui.reset（A2UI JSONL 渲染）

    如果 Playwright 不可用，降级为 Edge/Chrome app mode 子进程
    （仅支持 present/hide/navigate，不支持 eval/snapshot）。
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._playwright = None
        self._browser = None
        self._page = None
        self._proc: Optional[asyncio.subprocess.Process] = None  # fallback 子进程
        self._mode: str = "none"  # "playwright" | "subprocess" | "none"
        self._initialized = False
        self._a2ui_html: Optional[str] = None

    async def _ensure_playwright(self) -> bool:
        """尝试初始化 Playwright，返回是否成功"""
        if self._mode == "playwright":
            return True
        try:
            from playwright.async_api import async_playwright  # type: ignore[import]
            self._pw_context = await async_playwright().__aenter__()
            self._browser = await self._pw_context.chromium.launch(
                headless=False,
                args=["--disable-extensions", "--no-first-run"],
            )
            self._mode = "playwright"
            logger.info("[CANVAS] Playwright Chromium 引擎就绪")
            return True
        except ImportError:
            logger.warning("[CANVAS] Playwright 未安装，降级为 Edge app mode 子进程")
            self._mode = "subprocess"
            return False
        except Exception as e:
            logger.warning(f"[CANVAS] Playwright 初始化失败（{e}），降级为 Edge app mode 子进程")
            self._mode = "subprocess"
            return False

    async def present(
        self,
        url: Optional[str],
        html: Optional[str],
        width: int,
        height: int,
        x: int,
        y: int,
        title: str,
        always_on_top: bool,
    ) -> Dict[str, Any]:
        async with self._lock:
            await self._close_existing()

            if html:
                # 将 HTML 写入临时文件
                tmp = tempfile.NamedTemporaryFile(
                    mode="w", suffix=".html", delete=False, encoding="utf-8"
                )
                tmp.write(html)
                tmp.close()
                target_url = f"file:///{tmp.name.replace(os.sep, '/')}"
            elif url:
                target_url = url
            else:
                return {"success": False, "error": "必须提供 url 或 html"}

            playwright_ok = await self._ensure_playwright()

            if playwright_ok:
                try:
                    self._page = await self._browser.new_page()  # type: ignore[union-attr]
                    await self._page.set_viewport_size({"width": width, "height": height})
                    await self._page.goto(target_url, timeout=15000)
                    logger.info(f"[CANVAS] Playwright present: {target_url}")
                    return {"success": True, "mode": "playwright", "url": target_url}
                except Exception as e:
                    logger.error(f"[CANVAS] Playwright present 失败: {e}")
                    return {"success": False, "error": str(e)}
            else:
                return await self._subprocess_present(target_url, width, height)

    async def hide(self) -> Dict[str, Any]:
        async with self._lock:
            await self._close_existing()
        return {"success": True, "hidden": True}

    async def navigate(self, url: str) -> Dict[str, Any]:
        async with self._lock:
            if self._mode == "playwright" and self._page:
                try:
                    await self._page.goto(url, timeout=15000)
                    return {"success": True, "url": url}
                except Exception as e:
                    return {"success": False, "error": str(e)}
            elif self._mode == "subprocess" and self._proc:
                # subprocess 模式：关闭旧进程，启动新的
                await self._close_existing()
                return await self._subprocess_present(url, 800, 600)
            return {"success": False, "error": "Canvas 未打开"}

    async def eval_js(self, script: str) -> Dict[str, Any]:
        if self._mode == "playwright" and self._page:
            try:
                result = await self._page.evaluate(script)
                return {"success": True, "result": result}
            except Exception as e:
                return {"success": False, "error": str(e)}
        return {"success": False, "error": "canvas.eval 仅支持 Playwright 模式"}

    async def snapshot(
        self, fmt: str = "png", max_width: int = 1200, quality: int = 80
    ) -> Dict[str, Any]:
        if self._mode == "playwright" and self._page:
            try:
                kwargs: Dict[str, Any] = {}
                if fmt.lower() == "jpeg":
                    kwargs["type"] = "jpeg"
                    kwargs["quality"] = quality
                else:
                    kwargs["type"] = "png"

                raw = await self._page.screenshot(**kwargs)
                # 如果需要缩放
                if max_width < 9999:
                    try:
                        from PIL import Image
                        import io
                        img = Image.open(io.BytesIO(raw))
                        if img.width > max_width:
                            ratio = max_width / img.width
                            new_h = int(img.height * ratio)
                            resample = getattr(Image, "Resampling", Image).LANCZOS
                            img = img.resize((max_width, new_h), resample)
                            buf = io.BytesIO()
                            img.save(buf, format=fmt.upper() if fmt.upper() != "JPEG" else "JPEG",
                                     quality=quality)
                            raw = buf.getvalue()
                    except ImportError:
                        pass  # Pillow 不可用，使用原始大小

                b64 = base64.b64encode(raw).decode()
                return {"success": True, "format": fmt, "base64": b64}
            except Exception as e:
                return {"success": False, "error": str(e)}
        return {"success": False, "error": "canvas.snapshot 仅支持 Playwright 模式"}

    async def a2ui_push(self, jsonl: str, props: Optional[str] = None) -> Dict[str, Any]:
        """将 A2UI JSONL 渲染为 HTML 后显示在 Canvas"""
        html = _a2ui_jsonl_to_html(jsonl, props)
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        )
        tmp.write(html)
        tmp.close()
        self._a2ui_html = tmp.name
        target_url = f"file:///{tmp.name.replace(os.sep, '/')}"

        if self._mode == "playwright" and self._page:
            try:
                await self._page.goto(target_url, timeout=10000)
                return {"success": True, "pushed": True}
            except Exception as e:
                return {"success": False, "error": str(e)}
        # 未开启 canvas，自动 present
        return await self.present(target_url, None, 900, 600, -1, -1, "A2UI Canvas", False)

    async def a2ui_reset(self) -> Dict[str, Any]:
        """重置 A2UI Canvas（导航到空白页）"""
        if self._a2ui_html and os.path.isfile(self._a2ui_html):
            try:
                os.unlink(self._a2ui_html)
            except OSError:
                pass
            self._a2ui_html = None

        if self._mode == "playwright" and self._page:
            try:
                await self._page.goto("about:blank")
                return {"success": True, "reset": True}
            except Exception as e:
                return {"success": False, "error": str(e)}
        return {"success": True, "reset": True}

    async def _close_existing(self) -> None:
        if self._mode == "playwright" and self._page:
            try:
                await self._page.close()  # type: ignore[union-attr]
            except Exception:
                pass
            self._page = None
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=3.0)
            except Exception:
                pass
            self._proc = None

    async def _subprocess_present(
        self, url: str, width: int, height: int
    ) -> Dict[str, Any]:
        """使用 Edge/msedge app mode 子进程打开 URL（降级方案）"""
        edge_paths = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
        edge_exe = next((p for p in edge_paths if os.path.isfile(p)), "msedge.exe")
        try:
            self._proc = await asyncio.create_subprocess_exec(
                edge_exe,
                f"--app={url}",
                f"--window-size={width},{height}",
                "--disable-extensions",
                "--no-first-run",
                "--no-default-browser-check",
            )
            logger.info(f"[CANVAS] Edge app mode present: {url} (pid={self._proc.pid})")
            return {"success": True, "mode": "edge_subprocess", "url": url}
        except FileNotFoundError:
            return {
                "success": False,
                "error": "找不到 msedge.exe，请安装 Microsoft Edge 或 Playwright",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def cleanup(self) -> None:
        await self._close_existing()
        if self._mode == "playwright":
            try:
                await self._browser.close()
                await self._pw_context.__aexit__(None, None, None)
            except Exception:
                pass


def _a2ui_jsonl_to_html(jsonl: str, props_json: Optional[str]) -> str:
    """将 A2UI JSONL 转换为简单的 HTML 展示（轻量实现）"""
    items = []
    for line in jsonl.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            items.append({"type": "text", "content": line})

    body_parts = []
    for item in items:
        t = item.get("type", "text")
        if t == "text":
            body_parts.append(f"<p>{item.get('content', '')}</p>")
        elif t == "heading":
            level = item.get("level", 2)
            body_parts.append(f"<h{level}>{item.get('content', '')}</h{level}>")
        elif t == "image":
            src = item.get("src", "")
            body_parts.append(f'<img src="{src}" style="max-width:100%">')
        elif t == "code":
            body_parts.append(
                f"<pre><code>{item.get('content', '')}</code></pre>"
            )
        elif t == "list":
            rows = "".join(f"<li>{i}</li>" for i in item.get("items", []))
            body_parts.append(f"<ul>{rows}</ul>")
        else:
            body_parts.append(f"<div>{json.dumps(item, ensure_ascii=False)}</div>")

    body = "\n".join(body_parts)
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: system-ui, sans-serif; padding: 24px; max-width: 900px;
         margin: 0 auto; background: #fff; color: #1a1a1a; line-height: 1.6; }}
  pre {{ background: #f5f5f5; padding: 12px; border-radius: 4px; overflow-x: auto; }}
  img {{ border-radius: 4px; }}
</style>
</head>
<body>{body}</body>
</html>"""


# ── 主节点类 ──────────────────────────────────────────────────────────────────

class WindowsLocalNode(LocalNodeBase):
    """
    Windows 本地节点（全面升级版）

    相比旧版新增/改进：
    - Canvas 完整实现（Playwright 引擎 + Edge 降级）
    - 动态 Exec 审批策略引擎（exec-policy.json）
    - system.execApprovals.get/set 远程管理命令
    - 多显示器支持：screen.list + screenIndex/format/quality 参数
    - 屏幕录制：screen.record（ffmpeg gdigrab）
    - 通知分类系统（NotificationCategorizer）
    - Toast AppID 自动注册
    - clipboard_set 改用 stdin pipe（支持多行 Unicode）
    - 窗口截图 RECT 结构修正（Left/Top/Right/Bottom）
    - 摄像头：WinRT 优先，ffmpeg 备选；新增 camera.clip 视频录制
    - 位置信息：location.get（Windows Geolocation WinRT）
    """

    DEFAULT_SAFE_BINS = [
        "cmd", "cmd.exe",
        "powershell", "powershell.exe",
        "pwsh", "pwsh.exe",
        "where", "where.exe",
        "dir", "echo", "type", "start",
        "whoami", "hostname", "systeminfo",
        "tasklist", "tasklist.exe",
        "wmic", "wmic.exe",
        "mkdir", "rmdir", "copy", "xcopy", "robocopy",
        "move", "del", "ren", "attrib",
        "findstr", "find", "sort", "more", "tree",
        "ping", "ipconfig", "nslookup", "netstat",
        "curl", "curl.exe",
        "python", "python3", "python.exe", "python3.exe",
        "node", "node.exe",
        "npm", "npm.cmd",
        "git", "git.exe",
        "pip", "pip.exe", "pip3", "pip3.exe",
        "clip", "clip.exe",
        "explorer", "explorer.exe",
        "notepad", "notepad.exe",
        "ffmpeg", "ffmpeg.exe",
        "cat", "head", "tail", "grep", "ls", "wc",
        "bash", "bash.exe", "sh",
        "winget", "winget.exe",
    ]

    DEFAULT_ALLOWLIST = [
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
        r"C:\Windows\explorer.exe",
        r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        r"C:\Program Files\PowerShell\7\pwsh.exe",
    ]

    def __init__(
        self,
        node_id: str = "local",
        display_name: str = "Windows 本地节点",
        allowlist: Optional[List[str]] = None,
        safe_bins: Optional[List[str]] = None,
        data_dir: Optional[str] = None,
    ):
        super().__init__(
            node_id=node_id,
            display_name=display_name,
            allowlist=allowlist or self.DEFAULT_ALLOWLIST,
            safe_bins=safe_bins or self.DEFAULT_SAFE_BINS,
        )
        self._data_dir = data_dir or _DATA_DIR
        os.makedirs(self._data_dir, exist_ok=True)

        self._powershell_path: str = "powershell.exe"
        self._has_powershell7: bool = False
        self._has_ffmpeg: bool = False
        self._exec_policy = ExecApprovalPolicy(self._data_dir)
        self._notifier = NotificationCategorizer(self._data_dir)
        self._canvas = _CanvasManager()
        self._toast_app_id = "XiaoDazi.Agent"

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
            "screen_list",
            "screen_record",
            "clipboard",
            "open_app",
            "open_url",
            "camera",
            "canvas",
            "location",
            "tts",
        ]

    # ── system.run（集成 Exec 审批策略）─────────────────────────────────────

    async def _handle_system_run(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        覆盖基类方法，在执行前先通过 ExecApprovalPolicy 审批。

        策略检查 command[0]（可执行文件名），以及完整命令字符串。
        """
        from core.nodes.protocol import SystemRunParams
        run_params = SystemRunParams.from_dict(params)

        command_list = run_params.command
        if not command_list:
            raise ValueError("缺少 command 参数")

        # 提取可执行文件名（basename，去掉路径）
        executable = os.path.basename(command_list[0]) if command_list else ""
        # 完整命令字符串（用于更细粒度的模式匹配）
        full_cmd = " ".join(str(c) for c in command_list)
        shell = params.get("shell", "powershell")

        # 先用可执行文件名评估，再用完整命令
        eval_result = self._exec_policy.evaluate(executable, shell)
        if not eval_result.allowed:
            eval_result = self._exec_policy.evaluate(full_cmd, shell)

        if not eval_result.allowed:
            logger.warning(
                f"[EXEC-POLICY] 拒绝执行: '{full_cmd}' "
                f"(pattern={eval_result.matched_pattern}, reason={eval_result.reason})"
            )
            return {
                "stdout": "",
                "stderr": (
                    f"[EXEC-POLICY] 命令被策略拒绝: {eval_result.reason or '无匹配规则，默认 deny'}\n"
                    f"命令: {full_cmd}\n"
                    "可通过 system.execApprovals.set 更新策略，或联系管理员。"
                ),
                "exit_code": 1,
                "timed_out": False,
                "_hint": (
                    "⚠️ 命令被 Exec 审批策略拒绝！你可以调用 hitl 工具询问用户，"
                    "或通过 nodes（command=system.execApprovals.set）更新策略后重试。"
                ),
            }

        logger.debug(
            f"[EXEC-POLICY] 允许执行: '{executable}' "
            f"(pattern={eval_result.matched_pattern})"
        )
        return await super()._handle_system_run(params)

    # ── 初始化 ────────────────────────────────────────────────────────────────

    async def _do_initialize(self) -> None:
        self._powershell_path = self._resolve_powershell_path()
        logger.info(f"PowerShell 路径: {self._powershell_path}")

        ps_check = await self.shell_executor.which("powershell")
        if not ps_check:
            logger.warning("PowerShell 不可用，部分功能将受限")

        pwsh_check = await self.shell_executor.which("pwsh")
        self._has_powershell7 = pwsh_check is not None
        if self._has_powershell7:
            logger.info("检测到 PowerShell 7 (pwsh)，启用增强功能")

        ffmpeg_check = await self.shell_executor.which("ffmpeg")
        self._has_ffmpeg = ffmpeg_check is not None
        if self._has_ffmpeg:
            logger.info("检测到 ffmpeg，启用屏幕录制 / 摄像头视频录制")

        await self._register_toast_app_id()

    @staticmethod
    def _resolve_powershell_path() -> str:
        system_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR")
        if system_root:
            candidate = os.path.join(
                system_root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe"
            )
            if os.path.isfile(candidate):
                return candidate
        return "powershell.exe"

    def _get_powershell_cmd(self) -> str:
        return "pwsh" if self._has_powershell7 else self._powershell_path

    async def _register_toast_app_id(self) -> None:
        """在注册表注册 Toast AppID，确保 Windows 10+ 能正常显示通知"""
        ps_script = (
            f"$appId = '{self._toast_app_id}'; "
            "$regPath = \"HKCU:\\SOFTWARE\\Classes\\AppUserModelId\\$appId\"; "
            "if (-not (Test-Path $regPath)) { "
            "  New-Item -Path $regPath -Force | Out-Null; "
            "  New-ItemProperty -Path $regPath -Name 'DisplayName' "
            "    -Value '小打字 Agent' -PropertyType String -Force | Out-Null "
            "}"
        )
        try:
            await self.execute_powershell(ps_script, timeout=5.0)
            logger.debug(f"[TOAST] AppID '{self._toast_app_id}' 注册完成")
        except Exception as e:
            logger.warning(f"[TOAST] AppID 注册失败（通知可能静默失败）: {e}")

    # ── PowerShell 执行 ───────────────────────────────────────────────────────

    async def execute_powershell(
        self, script: str, timeout: float = 30.0
    ) -> Dict[str, Any]:
        result = await self.shell_executor.execute(
            command=[self._get_powershell_cmd(), "-NoProfile", "-Command", script],
            timeout=timeout,
        )
        return {
            "success": result.success,
            "output": result.stdout.strip() if result.stdout else "",
            "error": result.stderr.strip() if result.stderr else None,
        }

    # ── 通知（含分类系统）────────────────────────────────────────────────────

    async def _handle_system_notify(self, params: Dict[str, Any]) -> Dict[str, Any]:
        title = params.get("title", "通知")
        message = params.get("message", "")
        category_hint = params.get("category")

        cat = self._notifier.categorize(title, message, category=category_hint)
        if not self._notifier.should_show(cat.category):
            return {
                "sent": False,
                "suppressed": True,
                "category": cat.category,
                "reason": f"通知类别 '{cat.category}' 已被用户设置过滤",
            }

        icon_title = f"{cat.icon} {title}" if cat.icon else title
        ps_script = self._build_toast_script(icon_title, message)
        result = await self.shell_executor.execute(
            command=[self._get_powershell_cmd(), "-NoProfile", "-Command", ps_script],
            timeout=10.0,
        )
        return {
            "sent": result.success,
            "title": title,
            "message": message,
            "category": cat.category,
            "icon": cat.icon,
            "priority": cat.priority,
            "error": result.stderr if not result.success else None,
        }

    # ── 系统 open / path ──────────────────────────────────────────────────────

    async def open_app(
        self, app_name: str, url: Optional[str] = None, wait: bool = False
    ) -> Dict[str, Any]:
        if url:
            command = ["cmd", "/c", "start", "", app_name, url]
        elif wait:
            command = ["cmd", "/c", "start", "/wait", "", app_name]
        else:
            command = ["cmd", "/c", "start", "", app_name]
        result = await self.shell_executor.execute(command)
        return {"success": result.success, "app": app_name, "url": url}

    async def open_url(self, url: str) -> Dict[str, Any]:
        result = await self.shell_executor.execute(["cmd", "/c", "start", "", url])
        return {"success": result.success, "url": url}

    async def open_path(self, path: str) -> Dict[str, Any]:
        expanded = os.path.expanduser(path)
        result = await self.shell_executor.execute(["explorer.exe", expanded])
        return {"success": result.success, "path": expanded}

    # ── 剪贴板（stdin pipe 模式，支持多行 Unicode）────────────────────────────

    async def clipboard_get(self) -> Dict[str, Any]:
        result = await self.execute_powershell("Get-Clipboard")
        return {
            "success": result.get("success", False),
            "content": result.get("output") if result.get("success") else None,
        }

    async def clipboard_set(self, content: str) -> Dict[str, Any]:
        """
        通过 stdin pipe 写入剪贴板（UTF-16 LE，支持多行/特殊字符）。
        clip.exe 接受 UTF-16 LE，完全绕过命令行转义问题。
        """
        try:
            clip_path = r"C:\Windows\System32\clip.exe"
            if not os.path.isfile(clip_path):
                clip_path = "clip.exe"
            proc = await asyncio.create_subprocess_exec(
                clip_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            # clip.exe 读取 UTF-16 LE with BOM
            encoded = content.encode("utf-16-le")
            await proc.communicate(input=b"\xff\xfe" + encoded)
            if proc.returncode == 0:
                return {"success": True, "length": len(content), "method": "clip_stdin"}
        except Exception as e:
            logger.debug(f"clip.exe stdin 失败: {e}，尝试 PowerShell")

        # Fallback: PowerShell Set-Clipboard
        escaped = content.replace("'", "''")
        result = await self.execute_powershell(f"Set-Clipboard -Value '{escaped}'")
        return {
            "success": result.get("success", False),
            "length": len(content),
            "method": "powershell",
        }

    # ── 截图（多显示器 + 格式/质量）──────────────────────────────────────────

    async def screen_list(self) -> Dict[str, Any]:
        """
        枚举所有显示器信息。

        返回：index, name, primary, bounds, working_area
        """
        ps_script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$screens = [System.Windows.Forms.Screen]::AllScreens; "
            "$out = @(); "
            "$i = 0; "
            "foreach ($s in $screens) { "
            "  $out += @{ "
            "    index = $i; "
            "    name = $s.DeviceName; "
            "    primary = $s.Primary; "
            "    bounds = @{ x=$s.Bounds.X; y=$s.Bounds.Y; "
            "                width=$s.Bounds.Width; height=$s.Bounds.Height }; "
            "    workingArea = @{ x=$s.WorkingArea.X; y=$s.WorkingArea.Y; "
            "                    width=$s.WorkingArea.Width; "
            "                    height=$s.WorkingArea.Height } "
            "  }; $i++ "
            "}; "
            "$out | ConvertTo-Json -Depth 4 -Compress"
        )
        result = await self.execute_powershell(ps_script, timeout=10.0)
        if not result.get("success"):
            return {"success": False, "screens": [], "error": result.get("error")}
        try:
            raw = json.loads(result.get("output", "[]"))
            if isinstance(raw, dict):
                raw = [raw]
            return {"success": True, "screens": raw, "count": len(raw)}
        except json.JSONDecodeError:
            return {"success": False, "screens": [], "error": "解析显示器列表失败"}

    async def screenshot(
        self,
        output_path: Optional[str] = None,
        region: Optional[Dict[str, int]] = None,
        window: bool = False,
        screen_index: int = 0,
        fmt: str = "png",
        max_width: int = 0,
        quality: int = 90,
    ) -> Dict[str, Any]:
        """
        屏幕截图（支持多显示器、格式、质量、区域、活动窗口）。

        Args:
            output_path: 输出路径（默认 temp）
            region: 自定义区域 {x, y, width, height}
            window: 是否仅截取前台窗口
            screen_index: 显示器索引（0=主显示器）
            fmt: 格式 png / jpeg
            max_width: 最大宽度，0 表示不缩放
            quality: JPEG 质量（1-100）
        """
        if not output_path:
            ext = "jpg" if fmt.lower() == "jpeg" else "png"
            output_path = os.path.join(tempfile.gettempdir(), f"screenshot.{ext}")

        ps_path = output_path.replace("/", "\\")
        fmt_lower = fmt.lower()

        if region:
            ps_script = self._build_region_screenshot_script(
                ps_path, region["x"], region["y"], region["width"], region["height"], fmt_lower
            )
        elif window:
            ps_script = self._build_window_screenshot_script(ps_path, fmt_lower)
        else:
            ps_script = self._build_screen_screenshot_script(ps_path, screen_index, fmt_lower)

        result = await self.execute_powershell(ps_script, timeout=15.0)

        payload: Dict[str, Any] = {
            "success": result.get("success", False),
            "output_path": output_path,
            "format": fmt_lower,
            "screen_index": screen_index,
            "error": result.get("error") if not result.get("success") else None,
        }

        # 返回 base64（方便 AI 直接读取图像内容）
        if result.get("success") and os.path.isfile(output_path):
            try:
                with open(output_path, "rb") as f:
                    raw = f.read()
                if max_width > 0:
                    raw = _resize_image(raw, max_width, quality, fmt_lower)
                payload["base64"] = base64.b64encode(raw).decode()
                payload["image"] = f"data:image/{fmt_lower};base64,{payload['base64']}"
            except Exception as e:
                logger.warning(f"截图 base64 编码失败: {e}")

        return payload

    async def screen_record(
        self,
        output_path: Optional[str] = None,
        duration: int = 10,
        screen_index: int = 0,
        fps: int = 15,
    ) -> Dict[str, Any]:
        """
        屏幕录制（ffmpeg gdigrab）。

        Args:
            output_path: 输出路径（默认 temp .mp4）
            duration: 录制时长（秒）
            screen_index: 显示器索引（0=主显示器）
            fps: 帧率（默认 15）
        """
        if not self._has_ffmpeg:
            return {
                "success": False,
                "error": "screen.record 需要 ffmpeg，请先安装：https://ffmpeg.org",
            }

        if not output_path:
            output_path = os.path.join(tempfile.gettempdir(), "screen_record.mp4")

        # gdigrab 的 offset 需要获取目标显示器坐标
        offset_x, offset_y = 0, 0
        if screen_index > 0:
            screens_info = await self.screen_list()
            screens = screens_info.get("screens", [])
            if screen_index < len(screens):
                bounds = screens[screen_index].get("bounds", {})
                offset_x = bounds.get("x", 0)
                offset_y = bounds.get("y", 0)

        cmd = [
            "ffmpeg",
            "-f", "gdigrab",
            "-framerate", str(fps),
            "-offset_x", str(offset_x),
            "-offset_y", str(offset_y),
            "-i", "desktop",
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            "-pix_fmt", "yuv420p",
            "-y",
            output_path,
        ]

        result = await self.shell_executor.execute(cmd, timeout=float(duration + 15))
        return {
            "success": result.success and os.path.isfile(output_path),
            "output_path": output_path,
            "duration": duration,
            "fps": fps,
            "screen_index": screen_index,
            "error": result.stderr if not result.success else None,
        }

    # ── TTS ──────────────────────────────────────────────────────────────────

    async def say(self, text: str, voice: Optional[str] = None) -> Dict[str, Any]:
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
        return {"success": result.get("success", False), "text": text, "voice": voice}

    # ── 摄像头（WinRT 优先，ffmpeg 备选）────────────────────────────────────

    async def camera_list(self) -> Dict[str, Any]:
        """使用 WinRT DeviceInformation 枚举摄像头（比 PnpDevice 更可靠）"""
        ps_script = self._build_camera_list_winrt_script()
        result = await self.execute_powershell(ps_script, timeout=15.0)
        if not result.get("success"):
            # fallback 到 PnpDevice
            ps_script = self._build_camera_list_pnp_script()
            result = await self.execute_powershell(ps_script, timeout=10.0)

        output = result.get("output", "").strip()
        try:
            cameras = json.loads(output) if output else []
            if isinstance(cameras, dict):
                cameras = [cameras]
        except json.JSONDecodeError:
            cameras = []
        return {"success": True, "cameras": cameras, "count": len(cameras)}

    async def camera_snap(
        self,
        output_path: Optional[str] = None,
        device_id: Optional[str] = None,
        width: int = 1280,
        height: int = 720,
    ) -> Dict[str, Any]:
        """
        摄像头拍照：WinRT MediaCapture → ffmpeg → 失败报错

        Args:
            output_path: 输出路径（默认 temp .jpg）
            device_id: 摄像头设备 ID 或名称（None=默认摄像头）
            width: 宽度
            height: 高度
        """
        if not output_path:
            output_path = os.path.join(tempfile.gettempdir(), "camera_snap.jpg")
        expanded = os.path.expanduser(output_path)

        # 优先 WinRT
        result = await self._camera_snap_winrt(expanded, device_id)
        if result.get("success"):
            return result

        logger.warning(f"[CAMERA] WinRT 拍照失败: {result.get('error')}，尝试 ffmpeg")

        if self._has_ffmpeg:
            result = await self._camera_snap_ffmpeg(expanded, device_id, width, height)
            if result.get("success"):
                return result

        return {
            "success": False,
            "error": "摄像头拍照失败：WinRT 和 ffmpeg 均不可用或未授权",
        }

    async def camera_clip(
        self,
        output_path: Optional[str] = None,
        device_id: Optional[str] = None,
        duration: int = 5,
        width: int = 1280,
        height: int = 720,
    ) -> Dict[str, Any]:
        """
        摄像头录制短视频（ffmpeg DirectShow）。

        Args:
            output_path: 输出路径（默认 temp .mp4）
            device_id: 摄像头设备名称（None=自动选择第一个）
            duration: 录制时长（秒）
            width / height: 分辨率
        """
        if not self._has_ffmpeg:
            return {
                "success": False,
                "error": "camera.clip 需要 ffmpeg（DirectShow），请先安装",
            }

        if not output_path:
            output_path = os.path.join(tempfile.gettempdir(), "camera_clip.mp4")

        device_name = device_id
        if not device_name:
            cameras = (await self.camera_list()).get("cameras", [])
            device_name = cameras[0].get("name", "") if cameras else ""

        if not device_name:
            return {"success": False, "error": "未找到可用摄像头"}

        cmd = [
            "ffmpeg",
            "-f", "dshow",
            "-video_size", f"{width}x{height}",
            "-i", f"video={device_name}",
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            "-pix_fmt", "yuv420p",
            "-y",
            output_path,
        ]
        result = await self.shell_executor.execute(cmd, timeout=float(duration + 15))
        return {
            "success": result.success and os.path.isfile(output_path),
            "output_path": output_path,
            "duration": duration,
            "device": device_name,
            "error": result.stderr if not result.success else None,
        }

    # ── 位置信息 ──────────────────────────────────────────────────────────────

    async def location_get(self) -> Dict[str, Any]:
        """
        获取设备位置（Windows Geolocation WinRT）。

        台式机依赖 IP 定位（精度低），笔记本 WiFi 精度较好。
        返回：latitude, longitude, accuracy_meters
        """
        ps_script = self._build_location_script()
        result = await self.execute_powershell(ps_script, timeout=30.0)
        if not result.get("success"):
            return {
                "success": False,
                "error": result.get("error") or "位置获取失败",
            }
        try:
            data = json.loads(result.get("output", "{}"))
            return {
                "success": True,
                "latitude": data.get("latitude"),
                "longitude": data.get("longitude"),
                "accuracy_meters": data.get("accuracy"),
                "altitude": data.get("altitude"),
                "source": "windows_geolocation",
                "note": "台式机精度较低（IP定位），笔记本WiFi精度较好",
            }
        except json.JSONDecodeError:
            return {"success": False, "error": "位置信息解析失败"}

    # ── Exec 审批策略 ─────────────────────────────────────────────────────────

    async def exec_approvals_get(self) -> Dict[str, Any]:
        return {"success": True, **self._exec_policy.get_policy_dict()}

    async def exec_approvals_set(self, params: Dict[str, Any]) -> Dict[str, Any]:
        rules = params.get("rules", [])
        default_action = params.get("defaultAction")
        self._exec_policy.set_policy(rules, default_action)
        return {
            "success": True,
            "ruleCount": len(rules),
            "defaultAction": default_action or self._exec_policy.default_action.value,
        }

    # ── Canvas ────────────────────────────────────────────────────────────────

    async def canvas_present(self, params: Dict[str, Any]) -> Dict[str, Any]:
        url = params.get("url")
        html = params.get("html")
        if url and not _is_canvas_url_safe(url):
            return {
                "success": False,
                "error": f"URL 被安全策略拒绝（禁止 file://, javascript:, localhost, 私有 IP）: {url}",
            }
        return await self._canvas.present(
            url=url,
            html=html,
            width=params.get("width", 900),
            height=params.get("height", 600),
            x=params.get("x", -1),
            y=params.get("y", -1),
            title=params.get("title", "Canvas"),
            always_on_top=params.get("alwaysOnTop", False),
        )

    async def canvas_hide(self) -> Dict[str, Any]:
        return await self._canvas.hide()

    async def canvas_navigate(self, url: str) -> Dict[str, Any]:
        if not _is_canvas_url_safe(url):
            return {"success": False, "error": f"URL 安全校验失败: {url}"}
        return await self._canvas.navigate(url)

    async def canvas_eval(self, script: str) -> Dict[str, Any]:
        return await self._canvas.eval_js(script)

    async def canvas_snapshot(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return await self._canvas.snapshot(
            fmt=params.get("format", "png"),
            max_width=params.get("maxWidth", 1200),
            quality=params.get("quality", 80),
        )

    async def canvas_a2ui_push(self, params: Dict[str, Any]) -> Dict[str, Any]:
        jsonl = params.get("jsonl", "")
        jsonl_path = params.get("jsonlPath")
        if not jsonl and jsonl_path:
            try:
                with open(jsonl_path, encoding="utf-8") as f:
                    jsonl = f.read()
            except Exception as e:
                return {"success": False, "error": f"读取 jsonlPath 失败: {e}"}
        if not jsonl:
            return {"success": False, "error": "缺少 jsonl 或 jsonlPath 参数"}
        return await self._canvas.a2ui_push(jsonl, params.get("props"))

    async def canvas_a2ui_reset(self) -> Dict[str, Any]:
        return await self._canvas.a2ui_reset()

    # ── 平台命令路由 ──────────────────────────────────────────────────────────

    async def _handle_platform_command(
        self, command: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:

        # ── PowerShell ──
        if command == "powershell":
            script = params.get("script", "")
            if not script:
                raise ValueError("缺少 script 参数")
            return await self.execute_powershell(script)

        # ── 系统文件/URL 打开 ──
        elif command == "open_app":
            app_name = params.get("app_name", "")
            if not app_name:
                raise ValueError("缺少 app_name 参数")
            return await self.open_app(app_name, params.get("url"), params.get("wait", False))

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

        # ── 剪贴板 ──
        elif command == "clipboard.get":
            return await self.clipboard_get()

        elif command == "clipboard.set":
            return await self.clipboard_set(params.get("content", ""))

        # ── 截图 ──
        elif command in ("screenshot", "screen.capture"):
            return await self.screenshot(
                output_path=params.get("output_path"),
                region=params.get("region"),
                window=params.get("window", False),
                screen_index=params.get("screenIndex", params.get("screen_index", 0)),
                fmt=params.get("format", "png"),
                max_width=params.get("maxWidth", params.get("max_width", 0)),
                quality=params.get("quality", 90),
            )

        # ── 显示器列表 ──
        elif command == "screen.list":
            return await self.screen_list()

        # ── 屏幕录制 ──
        elif command == "screen.record":
            return await self.screen_record(
                output_path=params.get("output_path"),
                duration=params.get("duration", 10),
                screen_index=params.get("screenIndex", 0),
                fps=params.get("fps", 15),
            )

        # ── TTS ──
        elif command == "say":
            text = params.get("text", "")
            if not text:
                raise ValueError("缺少 text 参数")
            return await self.say(text, params.get("voice"))

        # ── 摄像头 ──
        elif command == "camera.list":
            return await self.camera_list()

        elif command == "camera.snap":
            return await self.camera_snap(
                output_path=params.get("output_path"),
                device_id=params.get("device_id") or params.get("deviceId"),
                width=params.get("width", 1280),
                height=params.get("height", 720),
            )

        elif command == "camera.clip":
            return await self.camera_clip(
                output_path=params.get("output_path"),
                device_id=params.get("device_id") or params.get("deviceId"),
                duration=params.get("duration", 5),
                width=params.get("width", 1280),
                height=params.get("height", 720),
            )

        # ── 位置信息 ──
        elif command == "location.get":
            return await self.location_get()

        # ── Canvas ──
        elif command == "canvas.present":
            return await self.canvas_present(params)

        elif command == "canvas.hide":
            return await self.canvas_hide()

        elif command == "canvas.navigate":
            url = params.get("url", "")
            if not url:
                raise ValueError("缺少 url 参数")
            return await self.canvas_navigate(url)

        elif command == "canvas.eval":
            script = params.get("script") or params.get("javaScript") or params.get("javascript", "")
            if not script:
                raise ValueError("缺少 script 参数")
            return await self.canvas_eval(script)

        elif command == "canvas.snapshot":
            return await self.canvas_snapshot(params)

        elif command == "canvas.a2ui.push":
            return await self.canvas_a2ui_push(params)

        elif command == "canvas.a2ui.reset":
            return await self.canvas_a2ui_reset()

        # ── Exec 审批策略 ──
        elif command == "system.execApprovals.get":
            return await self.exec_approvals_get()

        elif command == "system.execApprovals.set":
            return await self.exec_approvals_set(params)

        else:
            return await super()._handle_platform_command(command, params)

    async def shutdown(self) -> None:
        await self._canvas.cleanup()
        await super().shutdown()

    # ══════════════════════════════════════════════════════════════════════════
    # PowerShell 脚本构建器
    # ══════════════════════════════════════════════════════════════════════════

    # ── 截图 ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_screen_screenshot_script(output_path: str, screen_index: int, fmt: str) -> str:
        """构建指定显示器截图脚本（正确处理多显示器坐标）"""
        codec = "Jpeg" if fmt == "jpeg" else "Png"
        return (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "Add-Type -AssemblyName System.Drawing; "
            "$screens = [System.Windows.Forms.Screen]::AllScreens; "
            f"$idx = {screen_index}; "
            "if ($idx -ge $screens.Count) { $idx = 0 }; "
            "$scr = $screens[$idx]; "
            "$b = $scr.Bounds; "
            "$bmp = New-Object System.Drawing.Bitmap($b.Width, $b.Height); "
            "$g = [System.Drawing.Graphics]::FromImage($bmp); "
            "$g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size); "
            f"$bmp.Save('{output_path}', "
            f"[System.Drawing.Imaging.ImageFormat]::{codec}); "
            "$g.Dispose(); $bmp.Dispose()"
        )

    @staticmethod
    def _build_region_screenshot_script(
        output_path: str, x: int, y: int, width: int, height: int, fmt: str
    ) -> str:
        codec = "Jpeg" if fmt == "jpeg" else "Png"
        return (
            "Add-Type -AssemblyName System.Drawing; "
            f"$bmp = New-Object System.Drawing.Bitmap({width}, {height}); "
            "$g = [System.Drawing.Graphics]::FromImage($bmp); "
            f"$g.CopyFromScreen({x}, {y}, 0, 0, $bmp.Size); "
            f"$bmp.Save('{output_path}', "
            f"[System.Drawing.Imaging.ImageFormat]::{codec}); "
            "$g.Dispose(); $bmp.Dispose()"
        )

    @staticmethod
    def _build_window_screenshot_script(output_path: str, fmt: str) -> str:
        """
        截取前台窗口截图。

        使用正确的 RECT 结构（Left/Top/Right/Bottom）替代 System.Drawing.Rectangle，
        避免语义混淆导致的坐标计算错误。
        """
        codec = "Jpeg" if fmt == "jpeg" else "Png"
        return (
            "Add-Type -AssemblyName System.Drawing; "
            "Add-Type -TypeDefinition @'\n"
            "using System;\n"
            "using System.Runtime.InteropServices;\n"
            "public struct RECT { public int Left, Top, Right, Bottom; }\n"
            "public class WinAPI {\n"
            "  [DllImport(\"user32.dll\")] public static extern IntPtr GetForegroundWindow();\n"
            "  [DllImport(\"user32.dll\")] public static extern bool GetWindowRect(IntPtr h, out RECT r);\n"
            "}\n"
            "'@ -Language CSharp; "
            "$hwnd = [WinAPI]::GetForegroundWindow(); "
            "$rect = New-Object RECT; "
            "[WinAPI]::GetWindowRect($hwnd, [ref]$rect) | Out-Null; "
            "$w = $rect.Right - $rect.Left; "
            "$h = $rect.Bottom - $rect.Top; "
            "if ($w -le 0 -or $h -le 0) { Write-Error 'Invalid window rect'; exit 1 }; "
            "$bmp = New-Object System.Drawing.Bitmap($w, $h); "
            "$g = [System.Drawing.Graphics]::FromImage($bmp); "
            "$g.CopyFromScreen($rect.Left, $rect.Top, 0, 0, "
            "(New-Object System.Drawing.Size($w, $h))); "
            f"$bmp.Save('{output_path}', "
            f"[System.Drawing.Imaging.ImageFormat]::{codec}); "
            "$g.Dispose(); $bmp.Dispose()"
        )

    # ── 摄像头 ────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_camera_list_winrt_script() -> str:
        """WinRT DeviceInformation 枚举摄像头（比 PnpDevice 更可靠）"""
        return (
            "$ErrorActionPreference = 'Stop'; "
            "Add-Type -AssemblyName System.Runtime.WindowsRuntime; "
            "[Windows.Devices.Enumeration.DeviceInformation, "
            "Windows.Devices.Enumeration, ContentType=WindowsRuntime] | Out-Null; "
            "$rtx = [System.WindowsRuntimeSystemExtensions]; "
            "$opM = ($rtx.GetMethods() | Where-Object { "
            "  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and "
            "  $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation``1' "
            "})[0]; "
            "$class = [Windows.Devices.Enumeration.DeviceClass]; "
            "$op = [Windows.Devices.Enumeration.DeviceInformation]"
            "::FindAllAsync($class::VideoCapture); "
            "$task = $opM.MakeGenericMethod("
            "[Windows.Devices.Enumeration.DeviceInformationCollection]"
            ").Invoke($null, @($op)); "
            "$task.Wait(-1) | Out-Null; "
            "$devs = $task.Result; "
            "$cams = @(); "
            "foreach ($d in $devs) { "
            "  $cams += @{ id = $d.Id; name = $d.Name; "
            "              isDefault = $d.IsDefault; isEnabled = $d.IsEnabled } "
            "}; "
            "if ($cams.Count -eq 0) { '[]' } "
            "elseif ($cams.Count -eq 1) { '[' + ($cams[0] | ConvertTo-Json -Compress) + ']' } "
            "else { $cams | ConvertTo-Json -Compress }"
        )

    @staticmethod
    def _build_camera_list_pnp_script() -> str:
        """PnpDevice 备选枚举方案"""
        return (
            "$cams = @(); "
            "try { "
            "  $devs = Get-PnpDevice -Class 'Camera','Image' -Status OK -ErrorAction Stop; "
            "  foreach ($d in $devs) { "
            "    $cams += @{ name=$d.FriendlyName; id=$d.InstanceId; status=[string]$d.Status } "
            "  } "
            "} catch { "
            "  $devs = Get-CimInstance Win32_PnPEntity | Where-Object { "
            "    $_.PNPClass -eq 'Camera' -or $_.PNPClass -eq 'Image' }; "
            "  foreach ($d in $devs) { "
            "    $cams += @{ name=$d.Name; id=$d.DeviceID; status=[string]$d.Status } "
            "  } "
            "}; "
            "if ($cams.Count -eq 0) { '[]' } "
            "elseif ($cams.Count -eq 1) { '[' + ($cams[0] | ConvertTo-Json -Compress) + ']' } "
            "else { $cams | ConvertTo-Json -Compress }"
        )

    async def _camera_snap_winrt(
        self, output_path: str, device_id: Optional[str]
    ) -> Dict[str, Any]:
        """WinRT MediaCapture 拍照"""
        ps_path = output_path.replace("/", "\\").replace("'", "''")
        ps_script = self._build_camera_capture_script(ps_path, device_id)
        result = await self.execute_powershell(ps_script, timeout=30.0)

        if result.get("success") and os.path.isfile(output_path):
            return {"success": True, "output_path": output_path, "method": "winrt"}
        return {
            "success": False,
            "error": result.get("error") or result.get("output") or "WinRT 拍照失败",
            "method": "winrt",
        }

    async def _camera_snap_ffmpeg(
        self, output_path: str, device_name: Optional[str], width: int, height: int
    ) -> Dict[str, Any]:
        """ffmpeg DirectShow 拍照"""
        if not device_name:
            cameras = (await self.camera_list()).get("cameras", [])
            device_name = cameras[0].get("name", "") if cameras else ""
        if not device_name:
            return {"success": False, "error": "找不到可用摄像头", "method": "ffmpeg"}

        result = await self.shell_executor.execute(
            command=[
                "ffmpeg", "-f", "dshow",
                "-video_size", f"{width}x{height}",
                "-i", f"video={device_name}",
                "-frames:v", "1",
                "-y", output_path,
            ],
            timeout=15.0,
        )
        if result.success and os.path.isfile(output_path):
            return {"success": True, "output_path": output_path, "method": "ffmpeg"}
        return {
            "success": False,
            "error": result.stderr or "ffmpeg 拍照失败",
            "method": "ffmpeg",
        }

    @staticmethod
    def _build_camera_capture_script(
        output_path: str, device_id: Optional[str] = None
    ) -> str:
        """WinRT MediaCapture 拍照 PowerShell 脚本"""
        escaped_path = output_path.replace("'", "''")
        if device_id:
            escaped_id = device_id.replace("'", "''")
            init_section = (
                "$settings = New-Object Windows.Media.Capture.MediaCaptureInitializationSettings; "
                f"$settings.VideoDeviceId = '{escaped_id}'; "
                "$task = $actM.Invoke($null, @($mc.InitializeAsync($settings))); "
                "$task.Wait(-1) | Out-Null; "
            )
        else:
            init_section = (
                "$task = $actM.Invoke($null, @($mc.InitializeAsync())); "
                "$task.Wait(-1) | Out-Null; "
            )

        return (
            "$ErrorActionPreference = 'Stop'; "
            "Add-Type -AssemblyName System.Runtime.WindowsRuntime; "
            "$rtx = [System.WindowsRuntimeSystemExtensions]; "
            "$actM = ($rtx.GetMethods() | Where-Object { "
            "  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and "
            "  $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction' "
            "})[0]; "
            "$opM = ($rtx.GetMethods() | Where-Object { "
            "  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and "
            "  $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation``1' "
            "})[0]; "
            "[Windows.Media.Capture.MediaCapture,"
            "Windows.Media.Capture,ContentType=WindowsRuntime] | Out-Null; "
            "[Windows.Media.MediaProperties.ImageEncodingProperties,"
            "Windows.Media.MediaProperties,ContentType=WindowsRuntime] | Out-Null; "
            "[Windows.Storage.Streams.InMemoryRandomAccessStream,"
            "Windows.Storage.Streams,ContentType=WindowsRuntime] | Out-Null; "
            "[Windows.Storage.Streams.DataReader,"
            "Windows.Storage.Streams,ContentType=WindowsRuntime] | Out-Null; "
            "$mc = New-Object Windows.Media.Capture.MediaCapture; "
            f"{init_section}"
            "$props = [Windows.Media.MediaProperties.ImageEncodingProperties]::CreateJpeg(); "
            "$stream = New-Object Windows.Storage.Streams.InMemoryRandomAccessStream; "
            "$task = $actM.Invoke($null, @($mc.CapturePhotoToStreamAsync($props, $stream))); "
            "$task.Wait(-1) | Out-Null; "
            "$stream.Seek(0); "
            "$reader = New-Object Windows.Storage.Streams.DataReader($stream); "
            "$task = $opM.MakeGenericMethod([uint32]).Invoke("
            "$null, @($reader.LoadAsync([uint32]$stream.Size))); "
            "$task.Wait(-1) | Out-Null; "
            "$buf = New-Object byte[] $stream.Size; "
            "$reader.ReadBytes($buf); "
            f"[System.IO.File]::WriteAllBytes('{escaped_path}', $buf); "
            "$reader.Dispose(); $stream.Dispose(); $mc.Dispose(); "
            "Write-Output 'OK'"
        )

    # ── Toast 通知 ────────────────────────────────────────────────────────────

    def _build_toast_script(self, title: str, message: str) -> str:
        escaped_title = title.replace("'", "''")
        escaped_message = message.replace("'", "''")
        app_id = self._toast_app_id.replace("'", "''")
        return (
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
            "ContentType=WindowsRuntime] > $null; "
            "$template = [Windows.UI.Notifications.ToastNotificationManager]::"
            "GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
            "$textNodes = $template.GetElementsByTagName('text'); "
            f"$textNodes.Item(0).AppendChild($template.CreateTextNode('{escaped_title}')) > $null; "
            f"$textNodes.Item(1).AppendChild($template.CreateTextNode('{escaped_message}')) > $null; "
            "$toast = [Windows.UI.Notifications.ToastNotification]::new($template); "
            "[Windows.UI.Notifications.ToastNotificationManager]::"
            f"CreateToastNotifier('{app_id}').Show($toast)"
        )

    # ── 位置信息 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _build_location_script() -> str:
        """Windows Geolocation WinRT 脚本"""
        return (
            "$ErrorActionPreference = 'Stop'; "
            "Add-Type -AssemblyName System.Runtime.WindowsRuntime; "
            "[Windows.Devices.Geolocation.Geolocator, "
            "Windows.Devices.Geolocation, ContentType=WindowsRuntime] | Out-Null; "
            "$rtx = [System.WindowsRuntimeSystemExtensions]; "
            "$opM = ($rtx.GetMethods() | Where-Object { "
            "  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and "
            "  $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation``1' "
            "})[0]; "
            "$geo = New-Object Windows.Devices.Geolocation.Geolocator; "
            "$geo.DesiredAccuracy = [Windows.Devices.Geolocation.PositionAccuracy]::High; "
            "$op = $geo.GetGeopositionAsync(); "
            "$task = $opM.MakeGenericMethod("
            "[Windows.Devices.Geolocation.Geoposition]).Invoke($null, @($op)); "
            "$task.Wait(20000) | Out-Null; "
            "$pos = $task.Result; "
            "$coord = $pos.Coordinate; "
            "@{ "
            "  latitude  = $coord.Point.Position.Latitude; "
            "  longitude = $coord.Point.Position.Longitude; "
            "  accuracy  = $coord.Accuracy; "
            "  altitude  = $coord.Point.Position.Altitude "
            "} | ConvertTo-Json -Compress"
        )


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _resize_image(raw: bytes, max_width: int, quality: int, fmt: str) -> bytes:
    """使用 Pillow 缩放图像（可选，Pillow 不可用时原样返回）"""
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(raw))
        if img.width <= max_width:
            return raw
        ratio = max_width / img.width
        new_h = int(img.height * ratio)
        resample = getattr(Image, "Resampling", Image).LANCZOS
        img = img.resize((max_width, new_h), resample)
        buf = io.BytesIO()
        pil_fmt = "JPEG" if fmt == "jpeg" else "PNG"
        img.save(buf, format=pil_fmt, quality=quality)
        return buf.getvalue()
    except ImportError:
        return raw
    except Exception:
        return raw
