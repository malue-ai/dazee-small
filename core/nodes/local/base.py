# -*- coding: utf-8 -*-
"""
本地节点基类

定义本地节点的通用接口，各平台继承实现。
"""

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.nodes.executors.shell import ShellExecutor
from core.nodes.protocol import (
    NodeCommand,
    NodeInfo,
    NodeInvokeRequest,
    NodeInvokeResponse,
    NodeStatus,
    ShellResult,
    SystemRunParams,
)
from utils.app_paths import get_bundle_dir, is_frozen

logger = logging.getLogger(__name__)


class LocalNodeBase(ABC):
    """
    本地节点基类

    处理本地设备操作
    """

    def __init__(
        self,
        node_id: str = "local",
        display_name: str = "本地节点",
        **kwargs,
    ):
        self.node_id = node_id
        self.display_name = display_name
        self._initialized = False

        if is_frozen():
            default_cwd = os.path.expanduser("~")
        else:
            default_cwd = str(get_bundle_dir())

        self.shell_executor = ShellExecutor(default_cwd=default_cwd)

        self.python_info: Dict[str, object] = {
            "available": False, "version": "", "path": "", "has_safe_path": False,
        }
        self._python_detected = False

    async def detect_python(self) -> Dict[str, object]:
        """Detect system Python (lazy, runs once)."""
        if self._python_detected:
            return self.python_info

        from utils.subprocess_env import detect_python_info
        self.python_info = await detect_python_info(
            shell_execute=self.shell_executor.execute,
        )
        self._python_detected = True

        ver = self.python_info.get("version", "")
        if self.python_info.get("available"):
            logger.info(f"系统 Python 探测: {ver} ({self.python_info.get('path')})")
        else:
            logger.info("系统 Python 探测: 不可用")

        return self.python_info

    @property
    @abstractmethod
    def platform(self) -> str:
        """平台标识：darwin, win32, linux"""
        pass

    @property
    @abstractmethod
    def capabilities(self) -> List[str]:
        """节点能力列表"""
        pass

    async def initialize(self) -> None:
        """初始化节点"""
        if self._initialized:
            return

        logger.info(f"初始化本地节点: {self.display_name} (platform={self.platform})")
        await self._do_initialize()
        self._initialized = True

    async def _do_initialize(self) -> None:
        """子类实现的初始化逻辑"""
        pass

    def get_info(self) -> NodeInfo:
        """获取节点信息"""
        return NodeInfo(
            node_id=self.node_id,
            display_name=self.display_name,
            platform=self.platform,
            status=NodeStatus.ONLINE if self._initialized else NodeStatus.UNKNOWN,
            capabilities=self.capabilities,
            last_seen=datetime.now(),
        )

    async def handle_invoke(self, command: str, params: Dict[str, Any]) -> NodeInvokeResponse:
        """
        处理节点调用

        Args:
            command: 命令类型
            params: 命令参数

        Returns:
            NodeInvokeResponse 调用结果
        """
        import time
        import uuid

        request_id = str(uuid.uuid4())
        start_time = time.time()

        try:
            logger.debug(f"处理节点调用: command={command}, params={params}")

            # 路由到具体处理器
            if command == NodeCommand.SYSTEM_RUN.value:
                result = await self._handle_system_run(params)
            elif command == NodeCommand.SYSTEM_WHICH.value:
                result = await self._handle_system_which(params)
            elif command == NodeCommand.SYSTEM_NOTIFY.value:
                result = await self._handle_system_notify(params)
            else:
                result = await self._handle_platform_command(command, params)

            elapsed_ms = int((time.time() - start_time) * 1000)
            return NodeInvokeResponse.success(request_id, result, elapsed_ms)

        except asyncio.TimeoutError:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error("节点调用超时")
            return NodeInvokeResponse.failure(
                request_id, "执行超时", elapsed_ms, error_code="timeout",
            )
        except PermissionError as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(f"节点调用权限不足: {e}", exc_info=True)
            return NodeInvokeResponse.failure(
                request_id, str(e), elapsed_ms, error_code="permission_denied",
            )
        except FileNotFoundError as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(f"节点调用依赖缺失: {e}", exc_info=True)
            return NodeInvokeResponse.failure(
                request_id, str(e), elapsed_ms, error_code="dependency_missing",
            )
        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(f"节点调用失败: {e}", exc_info=True)
            return NodeInvokeResponse.failure(request_id, str(e), elapsed_ms)

    # Patterns that indicate a missing Python/system dependency.
    # When detected, we append an actionable hint so the LLM uses HITL
    # instead of silently falling back to alternatives.
    _DEPENDENCY_ERROR_PATTERNS = (
        "ModuleNotFoundError: No module named",
        "ImportError: No module named",
        "ImportError: cannot import name",
        "command not found",
        "not found in PATH",
        "is not recognized as an internal or external command",
    )

    async def _handle_system_run(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute system.run command with denylist security.

        Security tiers:
        - Hard deny (denylist): blocked, not executed, hint to find alternative
        - Risky (soft confirm): executed, but result includes hitl hint so
          Agent asks user BEFORE next risky command
        - Normal: executed, no hint
        """
        run_params = SystemRunParams.from_dict(params)

        verdict, risk_reason = self.shell_executor.check_security(run_params.command)
        if verdict == "confirm":
            full_cmd = " ".join(run_params.command)
            return {
                "success": False,
                "action": "run",
                "node": self.node_id,
                "error": f"Risky command needs user approval: {risk_reason}",
                "_hint": (
                    f"⚠️ 此命令存在安全风险：{risk_reason}\n"
                    f"完整命令: {full_cmd}\n"
                    f"潜在后果：可能导致数据丢失、系统状态变更或服务中断。\n"
                    f"你必须立即调用 hitl 工具，向用户展示完整命令和风险说明，"
                    f"询问是否同意执行。hitl 的 default_action 必须设为 'deny'，"
                    f"这样用户不在时自动拒绝。用户明确同意后重试原命令。"
                ),
            }

        result = await self.shell_executor.execute(
            command=run_params.command,
            cwd=run_params.cwd,
            env=run_params.env,
            timeout=run_params.timeout_ms / 1000.0,
        )

        payload = result.to_payload()

        elapsed_s = result.elapsed_ms / 1000.0
        cmd_str = " ".join(run_params.command)
        if result.success:
            payload["_status_line"] = f"[exit:0 | {elapsed_s:.1f}s]"
        else:
            combined = f"{result.stderr}\n{result.stdout}"

            if "blocked by security policy" in combined:
                payload["_hint"] = (
                    "⛔ 此命令被安全策略硬拦截（不可逆破坏性操作），禁止执行。"
                    "请寻找更安全的替代方案，不要尝试绕过。"
                )
            elif result.timed_out:
                payload["_hint"] = (
                    f"命令超时。Try: 增大 timeout_ms 或拆分为更小的步骤。"
                    f"也可以用 nodes which {run_params.command[0]} 确认命令可用。"
                )
            elif result.exit_code == 127:
                bin_name = run_params.command[0]
                payload["_hint"] = (
                    f"Command not found: {bin_name}. "
                    f"Use: nodes which {bin_name} 检查是否可用。"
                    f"如需安装，先用 hitl 征得用户同意。"
                )
            elif result.exit_code == 126:
                payload["_hint"] = (
                    f"Permission denied for: {cmd_str}. "
                    f"检查文件权限或是否需要 sudo。"
                )
            else:
                for pattern in self._DEPENDENCY_ERROR_PATTERNS:
                    if pattern in combined:
                        payload["_hint"] = (
                            "⚠️ 依赖缺失！你必须立即调用 hitl 工具，"
                            "告知用户缺少哪个依赖，并询问是否同意安装。"
                            "用户同意后用 nodes 执行安装命令（如 pip install xxx），"
                            "安装完成后重试。用户拒绝后再寻找替代方案。"
                            "禁止跳过 hitl 直接尝试其他方案。"
                        )
                        break

            exit_label = f"exit:{result.exit_code}"
            if result.timed_out:
                exit_label = "exit:timeout"
            stderr_brief = result.stderr.split("\n")[0][:80] if result.stderr else ""
            suffix = f" | {stderr_brief}" if stderr_brief else ""
            payload["_status_line"] = f"[{exit_label} | {elapsed_s:.1f}s{suffix}]"

        return payload

    async def _handle_system_which(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理 system.which 命令"""
        executable = params.get("executable", "")
        if not executable:
            raise ValueError("缺少 executable 参数")

        path = await self.shell_executor.which(executable)
        return {
            "executable": executable,
            "path": path,
            "exists": path is not None,
        }

    @abstractmethod
    async def _handle_system_notify(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理 system.notify 命令（平台特定）"""
        pass

    async def _handle_platform_command(
        self, command: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        处理平台特定命令

        子类可覆盖以支持更多命令
        """
        raise ValueError(f"不支持的命令: {command}")

    def add_to_allowlist(self, executables: List[str]) -> Dict[str, Any]:
        """
        Runtime extension of the command allowlist.

        Args:
            executables: Executable names or full paths to allow.

        Returns:
            Summary dict.
        """
        return self.shell_executor.add_to_allowlist(executables)

    def get_allowlist_info(self) -> Dict[str, Any]:
        """Return current allowlist state."""
        return self.shell_executor.get_allowlist_info()

    async def shutdown(self) -> None:
        """关闭节点"""
        logger.info(f"关闭本地节点: {self.display_name}")
        await self.shell_executor.cleanup()
        self._initialized = False
