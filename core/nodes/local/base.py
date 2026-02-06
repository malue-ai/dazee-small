# -*- coding: utf-8 -*-
"""
本地节点基类

定义本地节点的通用接口，各平台继承实现。
"""

import logging
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

logger = logging.getLogger(__name__)


class LocalNodeBase(ABC):
    """
    本地节点基类

    处理本地设备操作，对齐 clawdbot MacNodeRuntime
    """

    def __init__(
        self,
        node_id: str = "local",
        display_name: str = "本地节点",
        allowlist: Optional[List[str]] = None,
        safe_bins: Optional[List[str]] = None,
    ):
        """
        初始化本地节点

        Args:
            node_id: 节点 ID
            display_name: 显示名称
            allowlist: 命令白名单
            safe_bins: 安全的可执行文件名
        """
        self.node_id = node_id
        self.display_name = display_name
        self._initialized = False

        # Shell 执行器
        self.shell_executor = ShellExecutor(
            allowlist=allowlist,
            safe_bins=safe_bins,
        )

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

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(f"节点调用失败: {e}", exc_info=True)
            return NodeInvokeResponse.failure(request_id, str(e), elapsed_ms)

    async def _handle_system_run(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理 system.run 命令

        对齐 clawdbot 的 system.run
        """
        run_params = SystemRunParams.from_dict(params)

        result = await self.shell_executor.execute(
            command=run_params.command,
            cwd=run_params.cwd,
            env=run_params.env,
            timeout=run_params.timeout_ms / 1000.0,
        )

        return result.to_payload()

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

    async def shutdown(self) -> None:
        """关闭节点"""
        logger.info(f"关闭本地节点: {self.display_name}")
        await self.shell_executor.cleanup()
        self._initialized = False
