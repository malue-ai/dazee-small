# -*- coding: utf-8 -*-
"""
Shell 命令执行器

跨平台 Shell 命令执行：
- 环境变量过滤（安全）
- 超时控制 + 进程树终止
- 输出捕获（Windows 编码感知）
- PATHEXT 可执行文件解析（Windows）
- 白名单：大小写无关 + 扩展名无关匹配（Windows）
"""

import asyncio
import logging
import os
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Set

from core.nodes.executors.base import BaseExecutor
from core.nodes.protocol import ShellResult

logger = logging.getLogger(__name__)

# Windows platform flag (evaluated once at import)
_IS_WIN32 = sys.platform == "win32"

# npm-related commands that need .cmd extension on Windows
_WIN_CMD_COMMANDS: Set[str] = {"npm", "pnpm", "yarn", "npx"}


class ShellExecutor(BaseExecutor):
    """
    Shell 命令执行器

    安全特性：
    - 命令白名单（可选）
    - 环境变量过滤
    - 超时控制
    - 输出大小限制
    - Windows: PATHEXT 解析、进程树终止、大小写无关白名单
    """

    # 阻止的环境变量键（安全过滤）
    BLOCKED_ENV_KEYS: Set[str] = {
        "NODE_OPTIONS",
        "PYTHONHOME",
        "PYTHONPATH",
        "LD_PRELOAD",
    }

    # 阻止的环境变量前缀
    BLOCKED_ENV_PREFIXES: List[str] = [
        "DYLD_",  # macOS 动态链接器
        "LD_",  # Linux 动态链接器
    ]

    # Windows 额外阻止的环境变量键
    BLOCKED_ENV_KEYS_WIN32: Set[str] = {
        "PSModulePath",  # 防止注入恶意 PowerShell 模块
        "__PSLockdownPolicy",  # PowerShell Constrained Language Mode
    }

    # 默认超时时间（秒）
    DEFAULT_TIMEOUT: float = 30.0

    # 最大输出大小（字节）
    MAX_OUTPUT_BYTES: int = 200000

    def __init__(
        self,
        allowlist: Optional[List[str]] = None,
        safe_bins: Optional[List[str]] = None,
        default_cwd: Optional[str] = None,
    ):
        """
        初始化 Shell 执行器

        Args:
            allowlist: 命令白名单（完整路径）
            safe_bins: 安全的可执行文件名（无需审批）
            default_cwd: 默认工作目录
        """
        self.allowlist = set(allowlist) if allowlist else None
        self.safe_bins = set(safe_bins) if safe_bins else set()
        self.default_cwd = default_cwd or os.path.expanduser("~")

        # Windows: build lowercase sets for case-insensitive matching
        if _IS_WIN32:
            self._allowlist_lower: Optional[Set[str]] = (
                {self._normalize_win_path(p) for p in self.allowlist}
                if self.allowlist
                else None
            )
            self._safe_bins_lower: Set[str] = {
                self._strip_win_ext(b.lower()) for b in self.safe_bins
            }
        else:
            self._allowlist_lower = None
            self._safe_bins_lower = set()

    # ==================== Allowlist Management ====================

    def add_to_allowlist(self, executables: List[str]) -> Dict[str, Any]:
        """
        Runtime extension of the allowlist.

        Accepts both full paths (/opt/homebrew/bin/brew) and bare names (brew).
        Full paths are added to self.allowlist; bare names to self.safe_bins.

        Args:
            executables: List of executable names or full paths to allow.

        Returns:
            Summary dict with counts of added items.
        """
        if self.allowlist is None:
            # No allowlist configured → all commands are already allowed.
            return {"added_paths": 0, "added_bins": 0, "note": "allowlist disabled, no-op"}

        added_paths = 0
        added_bins = 0

        for exe in executables:
            exe = exe.strip()
            if not exe:
                continue

            if "/" in exe or "\\" in exe:
                # Full path
                if exe not in self.allowlist:
                    self.allowlist.add(exe)
                    added_paths += 1
                    logger.info(f"白名单新增路径: {exe}")
            else:
                # Bare executable name
                if exe not in self.safe_bins:
                    self.safe_bins.add(exe)
                    added_bins += 1
                    logger.info(f"白名单新增命令: {exe}")

        return {"added_paths": added_paths, "added_bins": added_bins}

    def get_allowlist_info(self) -> Dict[str, Any]:
        """
        Return current allowlist state for debugging / introspection.
        """
        return {
            "enabled": self.allowlist is not None,
            "allowlist_count": len(self.allowlist) if self.allowlist else 0,
            "safe_bins_count": len(self.safe_bins),
            "safe_bins": sorted(self.safe_bins) if self.safe_bins else [],
        }

    # ==================== Environment Sanitization ====================

    def _sanitize_env(self, env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """
        清理环境变量，移除危险项

        Args:
            env: 用户提供的环境变量

        Returns:
            清理后的环境变量
        """
        sanitized = dict(os.environ)

        blocked_keys = self.BLOCKED_ENV_KEYS
        if _IS_WIN32:
            blocked_keys = blocked_keys | self.BLOCKED_ENV_KEYS_WIN32

        for key in list(sanitized.keys()):
            if key in blocked_keys:
                del sanitized[key]
                continue
            for prefix in self.BLOCKED_ENV_PREFIXES:
                if key.startswith(prefix):
                    del sanitized[key]
                    break

        if env:
            for key, value in env.items():
                if key in blocked_keys:
                    logger.warning(f"跳过阻止的环境变量: {key}")
                    continue
                blocked = False
                for prefix in self.BLOCKED_ENV_PREFIXES:
                    if key.startswith(prefix):
                        logger.warning(f"跳过阻止的环境变量: {key}")
                        blocked = True
                        break
                if not blocked:
                    sanitized[key] = value

        return sanitized

    # ==================== Allowlist & Command Resolution ====================

    def _check_allowlist(self, command: List[str]) -> bool:
        """
        检查命令是否在白名单中

        Windows: 大小写无关 + 去掉 .exe/.cmd 扩展名后匹配
        安全白名单匹配逻辑

        Args:
            command: 命令列表

        Returns:
            是否允许执行
        """
        if not self.allowlist:
            return True

        if not command:
            return False

        executable = command[0]

        if _IS_WIN32:
            # Case-insensitive full-path check
            if (
                self._allowlist_lower
                and self._normalize_win_path(executable) in self._allowlist_lower
            ):
                return True

            # Case-insensitive safe_bin check (strip .exe/.cmd extension)
            bin_name = os.path.basename(executable)
            stripped = self._strip_win_ext(bin_name.lower())
            if stripped in self._safe_bins_lower:
                return True
        else:
            # Unix: exact match
            if executable in self.allowlist:
                return True

            bin_name = os.path.basename(executable)
            if bin_name in self.safe_bins:
                return True

        return False

    @staticmethod
    def _resolve_win_command(command: List[str]) -> List[str]:
        """
        Resolve Windows command: add .cmd extension for npm-related commands,
        and use shutil.which to resolve PATHEXT.

        npm/pnpm/yarn/npx need .cmd extension on Windows
        because they are installed as .cmd batch scripts.

        Args:
            command: Original command list

        Returns:
            Command list with resolved executable
        """
        if not command:
            return command

        exe = command[0]
        basename = os.path.basename(exe).lower()
        ext = os.path.splitext(basename)[1]

        # Already has extension — leave it
        if ext:
            return command

        # npm-related commands need .cmd on Windows
        if basename in _WIN_CMD_COMMANDS:
            resolved = shutil.which(f"{exe}.cmd") or shutil.which(exe)
            if resolved:
                return [resolved] + command[1:]
            return [f"{exe}.cmd"] + command[1:]

        # General resolution via shutil.which (respects PATHEXT)
        resolved = shutil.which(exe)
        if resolved:
            return [resolved] + command[1:]

        return command

    @staticmethod
    def _normalize_win_path(p: str) -> str:
        """
        Normalize Windows path for matching: lowercase + forward slashes.
        Strips UNC prefix (\\\\?\\ or \\\\.\\\\ ).
        """
        stripped = p
        if stripped.startswith("\\\\?\\") or stripped.startswith("\\\\.\\"):
            stripped = stripped[4:]
        return stripped.replace("\\", "/").lower()

    @staticmethod
    def _strip_win_ext(name: str) -> str:
        """Strip common Windows executable extensions for matching."""
        stem, ext = os.path.splitext(name)
        if ext in {".exe", ".cmd", ".bat", ".com"}:
            return stem
        return name

    # ==================== Output Decoding ====================

    @staticmethod
    def _decode_output(data: bytes) -> str:
        """
        Decode subprocess output with platform-aware encoding.

        On Windows, PowerShell / cmd may output in system codepage (e.g. CP936
        for Simplified Chinese). We try UTF-8 first, then fall back to the
        system preferred encoding.

        Args:
            data: Raw bytes from subprocess stdout/stderr

        Returns:
            Decoded string
        """
        if not data:
            return ""

        if _IS_WIN32:
            # Try UTF-8 first (works when chcp 65001 or PowerShell UTF-8 mode)
            try:
                text = data.decode("utf-8")
                if "\ufffd" not in text:
                    return text
            except UnicodeDecodeError:
                pass

            # Fall back to system default encoding (e.g. cp936 / gbk)
            try:
                import locale

                encoding = locale.getpreferredencoding(False)
                return data.decode(encoding, errors="replace")
            except (UnicodeDecodeError, LookupError):
                pass

        return data.decode("utf-8", errors="replace")

    # ==================== Process Management ====================

    @staticmethod
    def _kill_process_tree(pid: int) -> None:
        """
        Kill entire process tree (parent + children).

        Windows: taskkill /F /T /PID
        Unix: SIGKILL to the child's own process group.

        IMPORTANT: The child must have been started with process_group=0
        (or start_new_session=True) so that its process group ID differs
        from the parent's. Otherwise os.killpg() would kill the parent
        (FastAPI server) too.
        """
        if _IS_WIN32:
            try:
                subprocess.Popen(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.DETACHED_PROCESS
                    if _IS_WIN32
                    else 0,
                )
            except Exception:
                pass  # Best-effort
        else:
            try:
                child_pgid = os.getpgid(pid)
                parent_pgid = os.getpgid(os.getpid())

                if child_pgid == parent_pgid:
                    # Safety guard: child is in the same process group as the
                    # server. Sending SIGKILL to the group would crash the
                    # server. Fall back to killing only the child process.
                    logger.warning(
                        f"子进程 {pid} 与服务器在同一进程组 ({child_pgid})，"
                        f"仅终止子进程（不使用 killpg 以避免杀死服务器）"
                    )
                    os.kill(pid, 9)
                else:
                    # Child has its own process group (process_group=0).
                    # Safe to kill the entire group.
                    os.killpg(child_pgid, 9)
            except (ProcessLookupError, PermissionError, OSError):
                pass

    # ==================== Command Execution ====================

    async def execute(
        self,
        command: List[str],
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> ShellResult:
        """
        执行 shell 命令

        Windows: 自动解析 PATHEXT、.cmd 扩展名
        超时时: 使用 taskkill 终止整个进程树

        Args:
            command: 命令列表，如 ["ls", "-la"]
            cwd: 工作目录
            env: 额外环境变量
            timeout: 超时时间（秒）

        Returns:
            ShellResult 执行结果
        """
        if not command:
            return ShellResult(success=False, stderr="命令不能为空", exit_code=-1)

        # Windows: resolve .cmd / PATHEXT extensions
        if _IS_WIN32:
            command = self._resolve_win_command(command)

        # 白名单检查
        if not self._check_allowlist(command):
            bin_name = os.path.basename(command[0])
            return ShellResult(
                success=False,
                stderr=(
                    f"命令不在白名单中: {command[0]}。"
                    f"请先使用 hitl 工具询问用户是否同意将 {bin_name} 加入白名单，"
                    f"用户同意后使用 nodes whitelist_add --executables [\"{bin_name}\"] "
                    f"将其加入白名单，然后重试。"
                ),
                exit_code=-1,
            )

        # 准备参数
        work_dir = cwd or self.default_cwd
        sanitized_env = self._sanitize_env(env)
        timeout_s = timeout or self.DEFAULT_TIMEOUT

        logger.debug(f"执行命令: {' '.join(command)}, cwd={work_dir}")
        start_time = time.time()

        try:
            return await self._exec_async(
                command, work_dir, sanitized_env, timeout_s, start_time,
            )
        except (NotImplementedError, ValueError) as e:
            # NotImplementedError: Windows SelectorEventLoop does NOT
            #   support asyncio.create_subprocess_exec().
            # ValueError: uvloop rejects unknown kwargs like process_group
            #   (safety net in case _is_uvloop detection fails).
            # Fall back to running subprocess.run() in a thread-pool
            # which works with any event-loop implementation.
            logger.debug(f"asyncio subprocess 不可用 ({e})，回退到线程池执行")
            return await self._exec_thread_fallback(
                command, work_dir, sanitized_env, timeout_s, start_time,
            )
        except FileNotFoundError as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            return ShellResult(
                success=False,
                stderr=f"命令未找到: {e}",
                exit_code=-1,
                elapsed_ms=elapsed_ms,
            )
        except PermissionError as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            return ShellResult(
                success=False,
                stderr=f"权限不足: {e}",
                exit_code=-1,
                elapsed_ms=elapsed_ms,
            )
        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(f"执行命令失败: {e}", exc_info=True)
            return ShellResult(
                success=False,
                stderr=f"执行失败: {str(e)}",
                exit_code=-1,
                elapsed_ms=elapsed_ms,
            )

    # ---------- Primary path: asyncio subprocess ----------

    @staticmethod
    def _is_uvloop() -> bool:
        """Detect if the current event loop is uvloop.

        uvloop does NOT support the ``process_group`` kwarg in
        ``create_subprocess_exec``, so we must fall back to
        ``start_new_session=True`` which achieves similar process
        isolation (new session implies new process group).
        """
        try:
            loop = asyncio.get_running_loop()
            return type(loop).__module__.startswith("uvloop")
        except RuntimeError:
            return False

    async def _exec_async(
        self,
        command: List[str],
        cwd: str,
        env: Dict[str, str],
        timeout_s: float,
        start_time: float,
    ) -> ShellResult:
        """Execute via asyncio.create_subprocess_exec (preferred)."""
        # We need to isolate the child into its own process group so that
        # _kill_process_tree's os.killpg() does NOT kill the parent
        # (FastAPI server).
        #
        # - process_group=0 (os.setpgid): more targeted, only creates a
        #   new process group.  Preferred on stdlib asyncio.
        # - start_new_session=True (os.setsid): creates a new session
        #   AND process group.  Required when running under uvloop which
        #   does not support process_group.
        if self._is_uvloop():
            isolation_kwargs = {"start_new_session": True}
        else:
            isolation_kwargs = {"process_group": 0}

        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=cwd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **isolation_kwargs,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=timeout_s
            )

            elapsed_ms = int((time.time() - start_time) * 1000)
            stdout = self._decode_output(stdout_bytes)
            stderr = self._decode_output(stderr_bytes)

            if len(stdout) > self.MAX_OUTPUT_BYTES:
                stdout = stdout[: self.MAX_OUTPUT_BYTES] + "\n... (输出已截断)"
            if len(stderr) > self.MAX_OUTPUT_BYTES:
                stderr = stderr[: self.MAX_OUTPUT_BYTES] + "\n... (输出已截断)"

            return ShellResult(
                success=process.returncode == 0,
                stdout=stdout,
                stderr=stderr,
                exit_code=process.returncode or 0,
                elapsed_ms=elapsed_ms,
            )

        except asyncio.TimeoutError:
            if process.pid:
                self._kill_process_tree(process.pid)
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except (asyncio.TimeoutError, ProcessLookupError):
                try:
                    process.kill()
                except ProcessLookupError:
                    pass

            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.warning(f"命令超时: {' '.join(command)}, elapsed={elapsed_ms}ms")
            return ShellResult(
                success=False,
                stderr=f"命令执行超时 ({timeout_s}s)",
                exit_code=-1,
                timed_out=True,
                elapsed_ms=elapsed_ms,
            )

    # ---------- Fallback path: thread-pool subprocess ----------

    async def _exec_thread_fallback(
        self,
        command: List[str],
        cwd: str,
        env: Dict[str, str],
        timeout_s: float,
        start_time: float,
    ) -> ShellResult:
        """
        Fallback for Windows when the event loop does not support
        asyncio subprocess (SelectorEventLoop).

        Runs subprocess.run() in asyncio's default thread-pool executor
        so the event loop is never blocked.
        """
        import functools

        def _run() -> subprocess.CompletedProcess:
            # Isolate the child into its own process group, matching
            # _exec_async behaviour.  process_group requires Python 3.12+;
            # fall back to start_new_session on older runtimes.
            isolation: dict = {}
            if sys.version_info >= (3, 12):
                isolation["process_group"] = 0
            elif not _IS_WIN32:
                isolation["start_new_session"] = True

            return subprocess.run(
                command,
                cwd=cwd,
                env=env,
                capture_output=True,
                timeout=timeout_s,
                **isolation,
            )

        try:
            loop = asyncio.get_running_loop()
            completed = await loop.run_in_executor(None, _run)

            elapsed_ms = int((time.time() - start_time) * 1000)
            stdout = self._decode_output(completed.stdout)
            stderr = self._decode_output(completed.stderr)

            if len(stdout) > self.MAX_OUTPUT_BYTES:
                stdout = stdout[: self.MAX_OUTPUT_BYTES] + "\n... (输出已截断)"
            if len(stderr) > self.MAX_OUTPUT_BYTES:
                stderr = stderr[: self.MAX_OUTPUT_BYTES] + "\n... (输出已截断)"

            return ShellResult(
                success=completed.returncode == 0,
                stdout=stdout,
                stderr=stderr,
                exit_code=completed.returncode,
                elapsed_ms=elapsed_ms,
            )

        except subprocess.TimeoutExpired:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.warning(f"命令超时: {' '.join(command)}, elapsed={elapsed_ms}ms")
            return ShellResult(
                success=False,
                stderr=f"命令执行超时 ({timeout_s}s)",
                exit_code=-1,
                timed_out=True,
                elapsed_ms=elapsed_ms,
            )
        except FileNotFoundError as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            return ShellResult(
                success=False,
                stderr=f"命令未找到: {e}",
                exit_code=-1,
                elapsed_ms=elapsed_ms,
            )
        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(f"线程池执行命令失败: {e}", exc_info=True)
            return ShellResult(
                success=False,
                stderr=f"执行失败: {str(e)}",
                exit_code=-1,
                elapsed_ms=elapsed_ms,
            )

    # ==================== Utilities ====================

    async def which(self, executable: str) -> Optional[str]:
        """
        检查可执行文件是否存在（system.which）

        Windows 使用 where 命令，macOS/Linux 使用 which 命令。

        Args:
            executable: 可执行文件名

        Returns:
            可执行文件路径，如果不存在则返回 None
        """
        if _IS_WIN32:
            result = await self.execute(["where", executable], timeout=5.0)
        else:
            result = await self.execute(["which", executable], timeout=5.0)

        if result.success and result.stdout.strip():
            # where may return multiple lines; take the first match
            return result.stdout.strip().splitlines()[0]
        return None

    async def cleanup(self) -> None:
        """清理资源（当前无需清理）"""
        pass
