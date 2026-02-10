"""
运行时上下文构建器 - RuntimeContextBuilder

🆕 V6.0: 自动检测环境信息，动态注入到系统提示词

设计原则：
1. 环境信息由框架自动检测，用户无需在 prompt.md 硬编码
2. 自动构建系统提示词中的环境上下文片段
3. 支持 macOS / Linux / Windows

使用方式（异步）：
```python
from core.prompt.runtime_context_builder import RuntimeContextBuilder, get_environment_async

# 异步检测环境并生成提示词片段
env = await get_environment_async()
env_prompt = RuntimeContextBuilder.build_environment_prompt(env)

# 注入到 runtime_context
prompt_cache.runtime_context["environment_prompt"] = env_prompt
```
"""

import asyncio
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

import aiofiles

from logger import get_logger

logger = get_logger("runtime_context")

# 环境信息缓存（懒加载）
_cached_environment: Optional["RuntimeEnvironment"] = None

# Windows platform flag
_IS_WIN32 = platform.system().lower() == "windows"


async def _safe_subprocess_exec(
    *args: str, timeout: float = 5.0
) -> subprocess.CompletedProcess:
    """
    Cross-platform async subprocess execution.

    On Windows, asyncio.create_subprocess_exec may raise NotImplementedError
    when the event loop is SelectorEventLoop (common under uvicorn).
    Falls back to subprocess.run() via thread-pool.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        return subprocess.CompletedProcess(
            args=list(args),
            returncode=proc.returncode or 0,
            stdout=stdout,
            stderr=stderr,
        )
    except NotImplementedError:
        # Windows SelectorEventLoop fallback
        def _run():
            return subprocess.run(
                list(args),
                capture_output=True,
                timeout=timeout,
            )

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _run)


@dataclass
class RuntimeEnvironment:
    """运行时环境信息"""

    # 系统信息
    platform: str  # darwin / linux / windows
    platform_version: str  # macOS 14.0, Ubuntu 22.04, etc.
    arch: str  # arm64 / x86_64
    hostname: str  # 主机名

    # 用户信息
    user_home: Path  # 用户主目录
    user_name: str  # 用户名

    # 常用目录
    common_dirs: Dict[str, Path] = field(default_factory=dict)

    # 已安装应用（可选）
    installed_apps: List[str] = field(default_factory=list)

    # 时区
    timezone: str = ""

    # 当前时间
    current_time: str = ""


class RuntimeContextBuilder:
    """
    运行时上下文构建器

    自动检测当前环境信息，生成可注入到提示词的上下文
    """

    @classmethod
    async def detect_environment_async(cls, detect_apps: bool = True) -> RuntimeEnvironment:
        """
        自动检测当前环境（异步）

        Args:
            detect_apps: 是否检测已安装应用（macOS 较慢）

        Returns:
            RuntimeEnvironment 数据对象
        """
        user_home = Path.home()
        system = platform.system().lower()

        # 获取平台版本（异步）
        platform_version = await cls._get_platform_version_async(system)

        # 获取时区
        timezone = cls._get_timezone()

        # 构建常用目录
        common_dirs = cls._build_common_dirs(user_home, system)

        # 检测已安装应用（异步）
        installed_apps = []
        if detect_apps:
            installed_apps = await cls._detect_installed_apps_async(system)

        return RuntimeEnvironment(
            platform=system,
            platform_version=platform_version,
            arch=platform.machine(),
            hostname=platform.node(),
            user_home=user_home,
            user_name=os.getenv("USER") or os.getenv("USERNAME") or "unknown",
            common_dirs=common_dirs,
            installed_apps=installed_apps,
            timezone=timezone,
            current_time=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )

    @classmethod
    async def _get_platform_version_async(cls, system: str) -> str:
        """获取平台版本（异步）"""
        try:
            if system == "darwin":
                result = await _safe_subprocess_exec(
                    "sw_vers", "-productVersion", timeout=2,
                )
                if result.returncode == 0:
                    return f"macOS {result.stdout.decode().strip()}"
            elif system == "windows":
                # Use PowerShell to get Windows version details
                result = await _safe_subprocess_exec(
                    "powershell", "-NoProfile", "-Command",
                    "(Get-CimInstance Win32_OperatingSystem).Caption + ' Build ' + "
                    "(Get-CimInstance Win32_OperatingSystem).BuildNumber",
                    timeout=5,
                )
                if result.returncode == 0:
                    version_str = result.stdout.decode("utf-8", errors="replace").strip()
                    if version_str:
                        return version_str
                # Fallback: platform.version()
                return f"Windows {platform.version()}"
            elif system == "linux":
                # 尝试读取 /etc/os-release（异步）
                os_release = Path("/etc/os-release")
                if os_release.exists():
                    try:
                        async with aiofiles.open(os_release, "r") as f:
                            async for line in f:
                                if line.startswith("PRETTY_NAME="):
                                    return line.split("=")[1].strip().strip('"')
                    except FileNotFoundError:
                        pass
            return platform.platform()
        except Exception:
            return platform.platform()

    @classmethod
    def _get_timezone(cls) -> str:
        """获取时区"""
        try:
            import time
            from datetime import timezone as tz

            # 获取本地时区名称
            return time.tzname[0]
        except Exception:
            return "Unknown"

    @classmethod
    def _build_common_dirs(cls, user_home: Path, system: str) -> Dict[str, Path]:
        """构建常用目录映射"""
        dirs = {
            "home": user_home,
            "desktop": user_home / "Desktop",
            "downloads": user_home / "Downloads",
            "documents": user_home / "Documents",
        }

        if system == "darwin":
            dirs["pictures"] = user_home / "Pictures"
            dirs["movies"] = user_home / "Movies"
            dirs["music"] = user_home / "Music"
        elif system == "windows":
            dirs["pictures"] = user_home / "Pictures"
            dirs["videos"] = user_home / "Videos"
            dirs["music"] = user_home / "Music"
            # Windows-specific directories
            appdata = os.environ.get("APPDATA")
            if appdata:
                dirs["appdata"] = Path(appdata)
            local_appdata = os.environ.get("LOCALAPPDATA")
            if local_appdata:
                dirs["local_appdata"] = Path(local_appdata)
        elif system == "linux":
            dirs["pictures"] = user_home / "Pictures"
            dirs["videos"] = user_home / "Videos"
            dirs["music"] = user_home / "Music"

        # 只返回存在的目录
        return {k: v for k, v in dirs.items() if v.exists()}

    # 应用中英文名映射，便于 Agent 识别（飞书=Lark 等）
    APP_DISPLAY_NAME_MAP = {
        "Lark": "Lark (飞书)",
        "WeChat": "微信 (WeChat)",
        "企业微信": "企业微信 (WeCom)",
        "Google Chrome": "Chrome",
        "Visual Studio Code": "VS Code",
        "Microsoft Edge": "Edge",
        "Netflix": "Netflix",
        "Slack": "Slack",
        "Zoom": "Zoom",
        "Telegram": "Telegram",
        "Notion": "Notion",
        "Figma": "Figma",
        "Spotify": "Spotify",
    }

    @classmethod
    async def _detect_installed_apps_async(cls, system: str) -> List[str]:
        """
        检测已安装的应用（异步）。

        macOS: 扫描 /Applications 与 /System/Applications 全量 .app，
        并合并 lsappinfo 检测到的运行中应用（如飞书），应用名称映射便于 Agent 识别。
        """
        apps: List[str] = []
        seen: Set[str] = set()
        max_apps = 80

        if system == "darwin":
            # 扫描 /Applications 与 /System/Applications 下所有 .app
            for base in [Path("/Applications"), Path("/System/Applications")]:
                if not base.exists():
                    continue
                try:
                    for entry in base.iterdir():
                        if len(apps) >= max_apps:
                            break
                        if entry.suffix != ".app" or not entry.is_dir():
                            continue
                        name = entry.stem
                        if name in seen:
                            continue
                        seen.add(name)
                        display = cls.APP_DISPLAY_NAME_MAP.get(name, name)
                        apps.append(display)
                except OSError:
                    pass

            # 通过 lsappinfo 检测运行中的应用（含未在 /Applications 的，如飞书）
            try:
                result = await _safe_subprocess_exec(
                    "lsappinfo", "list", timeout=3,
                )
                if result.returncode == 0:
                    output = result.stdout.decode()
                    if "com.electron.lark" in output and "Lark" not in seen:
                        apps.insert(0, "飞书 (Lark, 打开: `open -b com.electron.lark`)")
                        seen.add("Lark")
            except Exception:
                pass

            apps.sort(key=lambda x: x.lower())

        elif system == "windows":
            # Windows: scan registry + Start Menu via AppScanner
            try:
                from core.discovery.app_scanner import AppScanner

                scanner = AppScanner()
                scanned = scanner.scan()
                for app_info in scanned[:max_apps]:
                    name = app_info.get("name", "")
                    if name and name not in seen:
                        seen.add(name)
                        display = cls.APP_DISPLAY_NAME_MAP.get(name, name)
                        apps.append(display)
                apps.sort(key=lambda x: x.lower())
            except Exception as e:
                logger.debug(f"Windows app detection failed: {e}")

            # Supplement with common Windows commands
            if not apps:
                win_cmds = [
                    "powershell", "git", "python", "node", "code",
                    "winget", "wt",
                ]
                for cmd in win_cmds:
                    try:
                        result = await _safe_subprocess_exec(
                            "where", cmd, timeout=2,
                        )
                        if result.returncode == 0:
                            apps.append(cmd)
                    except Exception:
                        pass

        elif system == "linux":
            # Linux: 检查常用命令（异步）
            common_cmds = ["firefox", "chromium", "code", "gnome-terminal"]
            for cmd in common_cmds:
                try:
                    result = await _safe_subprocess_exec(
                        "which", cmd, timeout=1,
                    )
                    if result.returncode == 0:
                        apps.append(cmd)
                except Exception:
                    pass

        return apps

    # 多语言标签映射
    LABELS = {
        "zh": {
            "title": "## 本地环境（自动检测）",
            "platform": "**平台**",
            "host": "**主机**",
            "user": "**用户**",
            "home_dir": "**主目录**",
            "timezone": "**时区**",
            "current_time": "**当前时间**",
            "common_dirs": "**常用目录**:",
            "installed_apps": "**已安装应用**:",
            "dir_names": {
                "home": "主目录",
                "desktop": "桌面",
                "downloads": "下载",
                "documents": "文档",
                "pictures": "图片",
                "movies": "影片",
                "videos": "视频",
                "music": "音乐",
                "appdata": "应用数据",
                "local_appdata": "本地应用数据",
            },
        },
        "en": {
            "title": "## Local Environment (Auto-detected)",
            "platform": "**Platform**",
            "host": "**Host**",
            "user": "**User**",
            "home_dir": "**Home Directory**",
            "timezone": "**Timezone**",
            "current_time": "**Current Time**",
            "common_dirs": "**Common Directories**:",
            "installed_apps": "**Installed Apps**:",
            "dir_names": {
                "home": "Home",
                "desktop": "Desktop",
                "downloads": "Downloads",
                "documents": "Documents",
                "pictures": "Pictures",
                "movies": "Movies",
                "videos": "Videos",
                "music": "Music",
                "appdata": "AppData (Roaming)",
                "local_appdata": "AppData (Local)",
            },
        },
    }

    @classmethod
    def build_environment_prompt(
        cls,
        env: RuntimeEnvironment,
        include_apps: bool = True,
        include_time: bool = True,
        language: str = "zh",
    ) -> str:
        """
        生成环境信息提示词片段

        Args:
            env: RuntimeEnvironment 对象
            include_apps: 是否包含已安装应用列表
            include_time: 是否包含当前时间
            language: 语言代码（zh/en）

        Returns:
            可直接注入到提示词的 Markdown 文本
        """
        labels = cls.LABELS.get(language, cls.LABELS["zh"])
        dir_names = labels["dir_names"]

        lines = [
            labels["title"],
            "",
            f"{labels['platform']}: {env.platform_version} ({env.arch})",
            f"{labels['host']}: {env.hostname}",
            f"{labels['user']}: {env.user_name}",
            f"{labels['home_dir']}: `{env.user_home}`",
        ]

        if include_time:
            lines.append(f"{labels['timezone']}: {env.timezone}")
            lines.append(f"{labels['current_time']}: {env.current_time}")

        lines.append("")
        lines.append(labels["common_dirs"])
        for name, path in env.common_dirs.items():
            display_name = dir_names.get(name, name)
            lines.append(f"- {display_name}: `{path}`")

        if include_apps and env.installed_apps:
            lines.append("")
            lines.append(labels["installed_apps"])
            for app in env.installed_apps:
                lines.append(f"- {app}")

        lines.append("")

        return "\n".join(lines)

    @classmethod
    def build_capabilities_prompt(cls, env: RuntimeEnvironment, language: str = "zh") -> str:
        """
        根据平台生成能力提示词

        Args:
            env: RuntimeEnvironment 对象
            language: 语言代码（zh/en）

        Returns:
            能力描述的 Markdown 文本
        """
        if language == "en":
            lines = ["## Local Capabilities", ""]
            if env.platform == "darwin":
                if shutil.which("peekaboo"):
                    lines.extend(
                        [
                            "**macOS Capabilities**:",
                            "- **UI automation (`peekaboo`)**: the PRIMARY way to interact with app UI",
                            "- Shell command execution (`nodes run`)",
                            "- System notifications (`nodes notify`)",
                            "- App launch (`open -a` / `open -b`)",
                            "- Clipboard operations",
                            "",
                            "**UI workflow** (via `nodes run`):",
                            "- Observe: `peekaboo see --app <App> --annotate` → get element IDs",
                            "- Click: `peekaboo click --on <ID> --app <App>`",
                            '- Type: `peekaboo type "text" --app <App>` (ASCII only)',
                            '- Paste: `peekaboo paste "text" --app <App>` (CJK / any text)',
                            "- Scroll: `peekaboo scroll --direction down --app <App>`",
                            "",
                            "**Rules**:",
                            "- **ALL UI interaction MUST use peekaboo** (click/type/paste/scroll)",
                            "- **NEVER use raw `osascript keystroke/key code/click`** for UI interaction",
                            "- `osascript` is ONLY for process management (e.g. `activate`, `get name of`)",
                            "- **CJK input: MUST use `peekaboo paste`** (keystroke does NOT work for non-ASCII)",
                            '- Activate app: `open -a "AppName"` or `open -b "bundle.id"`',
                        ]
                    )
                else:
                    lines.extend(
                        [
                            "**macOS Capabilities**:",
                            "- Shell command execution (`nodes run`)",
                            "- AppleScript UI automation (`osascript`)",
                            "- System notifications (`nodes notify`)",
                            "- App launch (`open -a` / `open -b`)",
                            "- Clipboard operations",
                            "",
                            "**Tips**:",
                            '- Activate app: `open -a "AppName"` or `open -b "bundle.id"`',
                            "- AppleScript: `osascript -e 'tell application ...'`",
                        ]
                    )
            elif env.platform == "windows":
                lines.extend(
                    [
                        "**Windows Capabilities**:",
                        "- Shell command execution via PowerShell & cmd (`nodes run`)",
                        "- PowerShell script execution (full .NET access)",
                        "- System toast notifications (`nodes notify`)",
                        "- Screenshot capture (`screenshot` command)",
                        "- Clipboard operations (`Get-Clipboard` / `Set-Clipboard`)",
                        "- App launch (`Start-Process` / `start` command)",
                        "- URL/file opening (`start <url>` / `explorer.exe <path>`)",
                        "- Text-to-speech (`SAPI.SpVoice`)",
                        "",
                        "**Tips**:",
                        "- Run PowerShell: `powershell -NoProfile -Command \"<script>\"`",
                        "- Open app: `start <AppName>` or `Start-Process <path>`",
                        "- Open URL: `start https://example.com`",
                        "- Open folder: `explorer.exe <path>`",
                        "- List processes: `tasklist`",
                        "- System info: `systeminfo`",
                    ]
                )
            elif env.platform == "linux":
                lines.extend(
                    [
                        "**Linux Capabilities**:",
                        "- Shell command execution (`nodes run`)",
                        "- System notifications (`notify-send`)",
                        "- App launch",
                        "- Clipboard operations (`xclip` / `xsel`)",
                    ]
                )
        else:  # zh
            lines = ["## 本地能力", ""]
            if env.platform == "darwin":
                if shutil.which("peekaboo"):
                    lines.extend(
                        [
                            "**macOS 操作能力**:",
                            "- **UI 自动化 (`peekaboo`)**: 所有界面交互的唯一方式",
                            "- Shell 命令执行 (`nodes run`)",
                            "- 系统通知 (`nodes notify`)",
                            "- 应用启动 (`open -a` / `open -b`)",
                            "- 剪贴板操作",
                            "",
                            "**UI 操作流程**（通过 `nodes run` 调用）:",
                            "- 观察: `peekaboo see --app <应用名> --annotate` → 获取带 ID 的 UI 元素",
                            "- 点击: `peekaboo click --on <元素ID> --app <应用名>`",
                            '- 输入: `peekaboo type "文本" --app <应用名>`（仅 ASCII）',
                            '- 粘贴: `peekaboo paste "文本" --app <应用名>`（中文/任意文本）',
                            "- 滚动: `peekaboo scroll --direction down --app <应用名>`",
                            "",
                            "**强制规则**:",
                            "- **所有 UI 交互必须通过 peekaboo**（点击/输入/粘贴/滚动）",
                            "- **禁止 `osascript keystroke/key code/click`** 操作界面元素",
                            "- `osascript` 仅限进程管理（如 `activate`、`get name of`）",
                            "- **中文输入必须用 `peekaboo paste`**（keystroke 完全不支持非 ASCII）",
                            '- 激活应用: `open -a "AppName"` 或 `open -b "bundle.id"`',
                        ]
                    )
                else:
                    lines.extend(
                        [
                            "**macOS 操作能力**:",
                            "- Shell 命令执行 (`nodes run`)",
                            "- AppleScript UI 自动化 (`osascript`)",
                            "- 系统通知 (`nodes notify`)",
                            "- 应用启动 (`open -a` / `open -b`)",
                            "- 剪贴板操作",
                            "",
                            "**操作提示**:",
                            '- 激活应用: `open -a "AppName"` 或 `open -b "bundle.id"`',
                            "- AppleScript: `osascript -e 'tell application ...'`",
                        ]
                    )
            elif env.platform == "windows":
                lines.extend(
                    [
                        "**Windows 操作能力**:",
                        "- Shell 命令执行 - PowerShell 和 cmd (`nodes run`)",
                        "- PowerShell 脚本执行（可调用完整 .NET 框架）",
                        "- 系统 Toast 通知 (`nodes notify`)",
                        "- 屏幕截图 (`screenshot` 命令)",
                        "- 剪贴板操作 (`Get-Clipboard` / `Set-Clipboard`)",
                        "- 应用启动 (`Start-Process` / `start` 命令)",
                        "- URL/文件打开 (`start <url>` / `explorer.exe <路径>`)",
                        "- 文字转语音 (`SAPI.SpVoice`)",
                        "",
                        "**操作提示**:",
                        "- 执行 PowerShell: `powershell -NoProfile -Command \"<脚本>\"`",
                        "- 打开应用: `start <应用名>` 或 `Start-Process <路径>`",
                        "- 打开 URL: `start https://example.com`",
                        "- 打开文件夹: `explorer.exe <路径>`",
                        "- 查看进程: `tasklist`",
                        "- 系统信息: `systeminfo`",
                    ]
                )
            elif env.platform == "linux":
                lines.extend(
                    [
                        "**Linux 操作能力**:",
                        "- Shell 命令执行 (`nodes run`)",
                        "- 系统通知 (`notify-send`)",
                        "- 应用启动",
                        "- 剪贴板操作 (`xclip` / `xsel`)",
                    ]
                )

        lines.append("")
        return "\n".join(lines)

    @classmethod
    def build_skill_status_prompt(
        cls,
        enabled_skills: List[str],
        unavailable_skills: Optional[List[str]] = None,
        ineligible_skills: Optional[List[str]] = None,
        language: str = "zh",
    ) -> str:
        """
        V11: 构建 Skill 状态提示词片段

        将当前平台可用/不可用的 Skill 信息注入系统提示词，
        帮助 LLM 了解自己可以使用哪些能力。

        Args:
            enabled_skills: 当前已启用的 Skill 名称列表
            unavailable_skills: 因 OS 限制不可用的 Skill 列表
            ineligible_skills: 因依赖缺失不可用的 Skill 列表
            language: 语言代码（zh/en）

        Returns:
            可直接注入到提示词的 Markdown 文本
        """
        if language == "en":
            lines = ["## Available Skills", ""]
            if enabled_skills:
                lines.append("**Enabled**:")
                for name in enabled_skills:
                    lines.append(f"- {name}")
            else:
                lines.append("No skills currently enabled.")

            if ineligible_skills:
                lines.append("")
                lines.append("**Unavailable (missing dependencies)**:")
                for name in ineligible_skills:
                    lines.append(f"- {name} (dependency not met)")

            if unavailable_skills:
                lines.append("")
                lines.append("**Not supported on this OS**:")
                for name in unavailable_skills:
                    lines.append(f"- {name}")
        else:
            lines = ["## 可用 Skills", ""]
            if enabled_skills:
                lines.append("**已启用**:")
                for name in enabled_skills:
                    lines.append(f"- {name}")
            else:
                lines.append("当前无已启用的 Skills。")

            if ineligible_skills:
                lines.append("")
                lines.append("**不可用（依赖缺失）**:")
                for name in ineligible_skills:
                    lines.append(f"- {name}（依赖未满足）")

            if unavailable_skills:
                lines.append("")
                lines.append("**当前 OS 不支持**:")
                for name in unavailable_skills:
                    lines.append(f"- {name}")

        lines.append("")
        return "\n".join(lines)


# 异步获取环境信息（带缓存）
async def get_environment_async(
    detect_apps: bool = True, force_refresh: bool = False
) -> RuntimeEnvironment:
    """
    异步获取环境信息（带缓存）

    Args:
        detect_apps: 是否检测已安装应用
        force_refresh: 是否强制刷新缓存

    Returns:
        RuntimeEnvironment 数据对象
    """
    global _cached_environment

    if _cached_environment is None or force_refresh:
        _cached_environment = await RuntimeContextBuilder.detect_environment_async(
            detect_apps=detect_apps
        )

    return _cached_environment


# 便捷函数（异步）
async def detect_and_build_environment_context_async(
    detect_apps: bool = True,
    include_capabilities: bool = True,
    language: str = "zh",
) -> str:
    """
    一站式函数：检测环境并生成完整上下文（异步）

    Args:
        detect_apps: 是否检测已安装应用
        include_capabilities: 是否包含能力提示词
        language: 语言代码（zh/en）

    Returns:
        完整的环境上下文提示词
    """
    env = await get_environment_async(detect_apps=detect_apps)

    parts = [RuntimeContextBuilder.build_environment_prompt(env, language=language)]

    if include_capabilities:
        parts.append(RuntimeContextBuilder.build_capabilities_prompt(env, language=language))

    return "\n".join(parts)
