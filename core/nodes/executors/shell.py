# -*- coding: utf-8 -*-
"""
Shell 命令执行器

借鉴 clawdbot 的 ShellExecutor.swift 实现：
- 通过 /usr/bin/env 执行命令
- 环境变量过滤（安全）
- 超时控制
- 输出捕获
"""

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional, Set

from core.nodes.executors.base import BaseExecutor
from core.nodes.protocol import ShellResult

logger = logging.getLogger(__name__)


class ShellExecutor(BaseExecutor):
    """
    Shell 命令执行器

    安全特性：
    - 命令白名单（可选）
    - 环境变量过滤
    - 超时控制
    - 输出大小限制
    """

    # 阻止的环境变量键（对齐 clawdbot）
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

    def _sanitize_env(self, env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """
        清理环境变量，移除危险项

        Args:
            env: 用户提供的环境变量

        Returns:
            清理后的环境变量
        """
        # 从当前环境开始
        sanitized = dict(os.environ)

        # 移除阻止的键
        for key in list(sanitized.keys()):
            if key in self.BLOCKED_ENV_KEYS:
                del sanitized[key]
                continue
            for prefix in self.BLOCKED_ENV_PREFIXES:
                if key.startswith(prefix):
                    del sanitized[key]
                    break

        # 合并用户提供的环境变量（同样需要过滤）
        if env:
            for key, value in env.items():
                if key in self.BLOCKED_ENV_KEYS:
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

    def _check_allowlist(self, command: List[str]) -> bool:
        """
        检查命令是否在白名单中

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

        # 检查完整路径
        if executable in self.allowlist:
            return True

        # 检查是否是安全的 bin
        bin_name = os.path.basename(executable)
        if bin_name in self.safe_bins:
            return True

        return False

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

        # 白名单检查
        if not self._check_allowlist(command):
            hint = f"可用命令: {', '.join(sorted(self.safe_bins))}" if self.safe_bins else ""
            return ShellResult(
                success=False,
                stderr=f"命令不在白名单中: {command[0]}。{hint}",
                exit_code=-1,
            )

        # 准备参数
        work_dir = cwd or self.default_cwd
        sanitized_env = self._sanitize_env(env)
        timeout_s = timeout or self.DEFAULT_TIMEOUT

        logger.debug(f"执行命令: {' '.join(command)}, cwd={work_dir}")
        start_time = time.time()

        try:
            # 直接执行命令（不使用 /usr/bin/env 前缀，确保 macOS 命令正常工作）
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=work_dir,
                env=sanitized_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(), timeout=timeout_s
                )

                elapsed_ms = int((time.time() - start_time) * 1000)

                # 截断过大的输出
                stdout = stdout_bytes.decode("utf-8", errors="replace")
                stderr = stderr_bytes.decode("utf-8", errors="replace")

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
                # 超时，终止进程
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    process.kill()

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

    async def which(self, executable: str) -> Optional[str]:
        """
        检查可执行文件是否存在（对齐 clawdbot system.which）

        Args:
            executable: 可执行文件名

        Returns:
            可执行文件路径，如果不存在则返回 None
        """
        result = await self.execute(["which", executable], timeout=5.0)
        if result.success and result.stdout.strip():
            return result.stdout.strip()
        return None

    async def cleanup(self) -> None:
        """清理资源（当前无需清理）"""
        pass
