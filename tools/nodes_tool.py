# -*- coding: utf-8 -*-
"""
Nodes 工具 - 本地/远程节点操作

提供统一的节点操作接口：
- status: 列出所有节点状态
- describe: 获取节点详细信息
- run: 在节点上执行命令
- notify: 发送通知到节点
- which: 检查可执行文件是否存在
"""

import logging
from typing import Any, Dict, List, Optional

from core.nodes.manager import NodeConfig, NodeManager, get_node_manager
from core.tool.types import ToolContext
from tools.base import BaseTool

logger = logging.getLogger(__name__)


class NodesTool(BaseTool):
    """
    Nodes 工具 - 发现、管理和操作本地/远程节点

    统一的节点操作工具
    """

    def __init__(self, node_manager: Optional[NodeManager] = None):
        """
        初始化 Nodes 工具

        Args:
            node_manager: 节点管理器实例（可选，默认使用全局单例）
        """
        self._node_manager = node_manager
        self._initialized = False

    @property
    def node_manager(self) -> NodeManager:
        """获取节点管理器"""
        if self._node_manager is None:
            self._node_manager = get_node_manager()
        return self._node_manager

    @property
    def name(self) -> str:
        return "nodes"

    @property
    def description(self) -> str:
        return """发现和操作本地/远程节点。

Actions:
- status: 列出所有节点状态
- describe: 获取节点详细信息
- run: 在节点上执行 shell 命令
- notify: 发送系统通知到节点
- which: 检查可执行文件是否存在
- whitelist_add: 将命令加入白名单（需先通过 hitl 征得用户同意）
- whitelist_info: 查看当前白名单状态

示例:
- nodes status: 查看所有节点状态
- nodes run --command ["ls", "-la"]: 执行命令
- nodes notify --title "提醒" --message "任务完成"
- nodes which --executable "python3": 检查 python3 是否存在
- nodes whitelist_add --executables ["brew", "/opt/homebrew/bin/brew"]: 将 brew 加入白名单"""

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "status", "describe", "run", "notify", "which",
                        "whitelist_add", "whitelist_info",
                    ],
                    "description": "操作类型",
                },
                "node": {
                    "type": "string",
                    "description": "目标节点 ID（默认 'local'）",
                    "default": "local",
                },
                "command": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要执行的命令（run action）",
                },
                "cwd": {"type": "string", "description": "工作目录（run action）"},
                "env": {"type": "object", "description": "环境变量（run action）"},
                "timeout_ms": {"type": "integer", "description": "超时毫秒数", "default": 30000},
                "title": {"type": "string", "description": "通知标题（notify action）"},
                "message": {"type": "string", "description": "通知内容（notify action）"},
                "subtitle": {"type": "string", "description": "通知副标题（notify action）"},
                "executable": {"type": "string", "description": "可执行文件名（which action）"},
                "executables": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要加入白名单的命令名或完整路径列表（whitelist_add action）",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self, params: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> Dict[str, Any]:
        """
        执行节点操作

        Args:
            params: 工具参数
            context: 工具上下文（可选）
        """
        action = params.get("action", "")
        node = params.get("node", "local")

        # 确保节点管理器已启动
        if not self._initialized:
            await self.node_manager.start()
            self._initialized = True

        try:
            if action == "status":
                return await self._action_status()
            elif action == "describe":
                return await self._action_describe(node)
            elif action == "run":
                return await self._action_run(node, params)
            elif action == "notify":
                return await self._action_notify(node, params)
            elif action == "which":
                return await self._action_which(node, params)
            elif action == "whitelist_add":
                return self._action_whitelist_add(node, params)
            elif action == "whitelist_info":
                return self._action_whitelist_info(node)
            else:
                return {
                    "success": False,
                    "error": f"不支持的操作: {action}",
                    "supported_actions": [
                        "status", "describe", "run", "notify", "which",
                        "whitelist_add", "whitelist_info",
                    ],
                }
        except Exception as e:
            logger.error(f"节点操作失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _action_status(self) -> Dict[str, Any]:
        """获取所有节点状态"""
        status = self.node_manager.get_status()
        return {"success": True, "action": "status", **status}

    async def _action_describe(self, node_id: str) -> Dict[str, Any]:
        """获取节点详细信息"""
        nodes = self.node_manager.list_nodes()

        for node in nodes:
            if node.node_id == node_id:
                return {"success": True, "action": "describe", "node": node.to_dict()}

        return {"success": False, "error": f"节点不存在: {node_id}"}

    # Commands whose output is data the Agent needs to reason about (read operations).
    # Results of these commands skip immediate compression so the Agent sees the full content.
    _READ_COMMANDS = frozenset({
        "cat", "head", "tail", "less", "more",
        "grep", "find", "ls", "wc", "file", "stat",
    })

    async def _action_run(self, node_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """在节点上执行命令"""
        command = params.get("command", [])
        if not command:
            return {"success": False, "error": "缺少 command 参数"}

        if isinstance(command, str):
            # 支持字符串形式的命令
            command = command.split()

        response = await self.node_manager.run_command(
            command=command,
            cwd=params.get("cwd"),
            env=params.get("env"),
            timeout_ms=params.get("timeout_ms", 30000),
            node_id=node_id,
        )

        inner_payload = response.payload if response.ok else None
        result: Dict[str, Any] = {
            "success": response.ok,
            "action": "run",
            "node": node_id,
            "command": command,
            "result": inner_payload,
            "error": response.error if not response.ok else None,
            "elapsed_ms": response.elapsed_ms,
        }

        # Promote _hint from nested payload to top level so the LLM sees it
        # without having to parse deeply nested JSON.
        # Also mark success=False when the inner command failed (exit_code != 0),
        # so the LLM does not misread the outer success=True as "command succeeded".
        if inner_payload:
            inner_hint = inner_payload.get("_hint")
            if inner_hint:
                result["_hint"] = inner_hint
            inner_exit_code = inner_payload.get("exit_code")
            if inner_exit_code is not None and inner_exit_code != 0:
                result["success"] = False

        # Structured error classification for failed commands
        if not response.ok and response.error:
            err_lower = response.error.lower()
            if "超时" in response.error or "timeout" in err_lower:
                result["error_type"] = "timeout"
            elif "permission" in err_lower or "权限" in response.error:
                result["error_type"] = "permission_denied"
                result["recovery_hint"] = "open_system_preferences:accessibility"
            elif "not found" in err_lower or "command not found" in err_lower:
                result["error_type"] = "dependency_missing"

        # Set compression hint based on command type.
        # Read commands return data the Agent needs intact; skip compression.
        # Write/mutation commands return confirmations; normal compression is fine.
        base_cmd = command[0].split("/")[-1] if command else ""
        if base_cmd in self._READ_COMMANDS:
            result["_compression_hint"] = "skip"

        return result

    async def _action_notify(self, node_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """发送系统通知"""
        title = params.get("title", "")
        message = params.get("message", "")

        if not title or not message:
            return {"success": False, "error": "缺少 title 或 message 参数"}

        response = await self.node_manager.notify(
            title=title,
            message=message,
            subtitle=params.get("subtitle"),
            node_id=node_id,
        )

        return {
            "success": response.ok,
            "action": "notify",
            "node": node_id,
            "title": title,
            "message": message,
            "error": response.error if not response.ok else None,
        }

    async def _action_which(self, node_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """检查可执行文件是否存在"""
        executable = params.get("executable", "")
        if not executable:
            return {"success": False, "error": "缺少 executable 参数"}

        response = await self.node_manager.invoke(
            command="system.which",
            params={"executable": executable},
            node_id=node_id,
        )

        if response.ok:
            return {"success": True, "action": "which", "node": node_id, **response.payload}
        else:
            return {"success": False, "action": "which", "node": node_id, "error": response.error}

    def _action_whitelist_add(self, node_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """将命令加入白名单"""
        executables = params.get("executables", [])
        if not executables:
            return {"success": False, "error": "缺少 executables 参数"}

        if isinstance(executables, str):
            executables = [executables]

        result = self.node_manager.add_to_allowlist(executables, node_id=node_id)

        if "error" in result:
            return {"success": False, "action": "whitelist_add", "error": result["error"]}

        return {
            "success": True,
            "action": "whitelist_add",
            "node": node_id,
            "added": executables,
            **result,
        }

    def _action_whitelist_info(self, node_id: str) -> Dict[str, Any]:
        """查看当前白名单状态"""
        result = self.node_manager.get_allowlist_info(node_id=node_id)

        if "error" in result:
            return {"success": False, "action": "whitelist_info", "error": result["error"]}

        return {
            "success": True,
            "action": "whitelist_info",
            "node": node_id,
            **result,
        }


# 工厂函数：创建 Nodes 工具实例
def create_nodes_tool(config: Optional[Dict[str, Any]] = None) -> NodesTool:
    """
    创建 Nodes 工具实例

    Args:
        config: 节点配置（可选）

    Returns:
        NodesTool 实例
    """
    if config:
        node_config = NodeConfig.from_dict(config)
        node_manager = NodeManager(node_config)
        return NodesTool(node_manager)
    else:
        return NodesTool()
