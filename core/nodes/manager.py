# -*- coding: utf-8 -*-
"""
节点管理器

管理所有本地和远程节点的生命周期和调用。
当前版本：内部直接调用模式（后续扩展 WebSocket 通信）
"""

import logging
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.nodes.local.base import LocalNodeBase
from core.nodes.protocol import (
    NodeInfo,
    NodeInvokeRequest,
    NodeInvokeResponse,
    NodeStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class NodeConfig:
    """节点配置"""

    enabled: bool = True
    platform: str = "auto"  # auto, darwin, win32, linux

    # 安全配置
    security_mode: str = "allowlist"  # deny, allowlist, full
    ask_on_miss: bool = True

    # 命令白名单
    allowlist: List[str] = field(default_factory=list)
    safe_bins: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NodeConfig":
        """从字典创建配置"""
        local_config = data.get("local", {})
        security_config = local_config.get("security", {})

        return cls(
            enabled=data.get("enabled", True),
            platform=local_config.get("platform", "auto"),
            security_mode=security_config.get("mode", "allowlist"),
            ask_on_miss=security_config.get("ask", "on-miss") == "on-miss",
            allowlist=local_config.get("allowlist", []),
            safe_bins=local_config.get("safe_bins", []),
        )


class NodeManager:
    """
    节点管理器

    职责：
    1. 节点注册/注销
    2. 节点发现（本地/远程）
    3. 命令路由
    4. 健康检查

    当前版本：仅支持本地节点（内部直接调用）
    后续扩展：WebSocket 远程节点
    """

    def __init__(self, config: Optional[NodeConfig] = None):
        """
        初始化节点管理器

        Args:
            config: 节点配置
        """
        self.config = config or NodeConfig()
        self.local_node: Optional[LocalNodeBase] = None
        self.remote_clients: Dict[str, Any] = {}  # 预留远程节点
        self._started = False

    async def start(self) -> None:
        """启动节点管理器"""
        if self._started:
            return

        logger.info("启动节点管理器")

        # 检测平台并创建本地节点
        if self.config.enabled:
            await self._init_local_node()

        self._started = True
        logger.info(f"节点管理器已启动, local_node={self.local_node is not None}")

    async def _init_local_node(self) -> None:
        """初始化本地节点"""
        platform = self.config.platform

        # 自动检测平台
        if platform == "auto":
            platform = sys.platform

        logger.info(f"初始化本地节点, platform={platform}")

        if platform == "darwin":
            from core.nodes.local.macos import MacOSLocalNode

            self.local_node = MacOSLocalNode(
                allowlist=self.config.allowlist if self.config.allowlist else None,
                safe_bins=self.config.safe_bins if self.config.safe_bins else None,
            )
        elif platform == "win32":
            # TODO: WindowsLocalNode
            logger.warning("Windows 本地节点尚未实现")
            return
        elif platform == "linux":
            # TODO: LinuxLocalNode
            logger.warning("Linux 本地节点尚未实现")
            return
        else:
            logger.warning(f"不支持的平台: {platform}")
            return

        await self.local_node.initialize()

    async def stop(self) -> None:
        """停止节点管理器"""
        if not self._started:
            return

        logger.info("停止节点管理器")

        if self.local_node:
            await self.local_node.shutdown()
            self.local_node = None

        # 关闭远程连接
        for client in self.remote_clients.values():
            if hasattr(client, "close"):
                await client.close()
        self.remote_clients.clear()

        self._started = False

    def get_status(self) -> Dict[str, Any]:
        """获取所有节点状态"""
        nodes = []

        if self.local_node:
            nodes.append(self.local_node.get_info().to_dict())

        for node_id, client in self.remote_clients.items():
            nodes.append(
                {
                    "node_id": node_id,
                    "type": "remote",
                    "status": (
                        "connected"
                        if hasattr(client, "is_connected") and client.is_connected
                        else "unknown"
                    ),
                }
            )

        return {
            "started": self._started,
            "local_node": self.local_node is not None,
            "remote_nodes": len(self.remote_clients),
            "nodes": nodes,
        }

    def list_nodes(self) -> List[NodeInfo]:
        """列出所有节点"""
        nodes = []

        if self.local_node:
            nodes.append(self.local_node.get_info())

        return nodes

    async def invoke(
        self,
        command: str,
        params: Dict[str, Any],
        node_id: str = "local",
        timeout_ms: int = 30000,
    ) -> NodeInvokeResponse:
        """
        向指定节点发送命令

        Args:
            command: 命令类型
            params: 命令参数
            node_id: 目标节点 ID
            timeout_ms: 超时时间（毫秒）

        Returns:
            NodeInvokeResponse 调用结果
        """
        if not self._started:
            return NodeInvokeResponse.failure("", "节点管理器未启动")

        # 本地节点
        if node_id == "local":
            if not self.local_node:
                return NodeInvokeResponse.failure("", "本地节点不可用")
            return await self.local_node.handle_invoke(command, params)

        # 远程节点
        if node_id in self.remote_clients:
            # TODO: 实现远程调用
            return NodeInvokeResponse.failure("", "远程节点调用尚未实现")

        return NodeInvokeResponse.failure("", f"节点不存在: {node_id}")

    async def run_command(
        self,
        command: List[str],
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout_ms: int = 30000,
        node_id: str = "local",
    ) -> NodeInvokeResponse:
        """
        在节点上执行 shell 命令（便捷方法）

        Args:
            command: 命令列表
            cwd: 工作目录
            env: 环境变量
            timeout_ms: 超时时间
            node_id: 目标节点
        """
        return await self.invoke(
            command="system.run",
            params={
                "command": command,
                "cwd": cwd,
                "env": env,
                "timeout_ms": timeout_ms,
            },
            node_id=node_id,
            timeout_ms=timeout_ms,
        )

    async def notify(
        self,
        title: str,
        message: str,
        subtitle: Optional[str] = None,
        node_id: str = "local",
    ) -> NodeInvokeResponse:
        """
        发送系统通知（便捷方法）

        Args:
            title: 通知标题
            message: 通知内容
            subtitle: 副标题
            node_id: 目标节点
        """
        return await self.invoke(
            command="system.notify",
            params={
                "title": title,
                "message": message,
                "subtitle": subtitle,
            },
            node_id=node_id,
        )


# 全局单例（可选使用）
_node_manager: Optional[NodeManager] = None


def get_node_manager() -> NodeManager:
    """获取节点管理器单例"""
    global _node_manager
    if _node_manager is None:
        _node_manager = NodeManager()
    return _node_manager


async def init_node_manager(config: Optional[NodeConfig] = None) -> NodeManager:
    """初始化并启动节点管理器"""
    global _node_manager
    if _node_manager is None:
        _node_manager = NodeManager(config)
    await _node_manager.start()
    return _node_manager
