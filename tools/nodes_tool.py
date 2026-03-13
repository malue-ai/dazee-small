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
import os
import re
import shlex
from typing import Any, Dict, List, Optional

from core.nodes.manager import NodeConfig, NodeManager, get_node_manager
from core.tool.types import ToolContext
from tools.base import BaseTool

logger = logging.getLogger(__name__)


_INSTALL_COMMANDS: set[tuple[str, str]] = {
    ("pip", "install"),
    ("pip3", "install"),
    ("python", "-m"),  # python -m pip install ...
    ("python3", "-m"),
    ("npm", "install"),
    ("npm", "ci"),
    ("pnpm", "install"),
    ("yarn", "install"),
    ("yarn", "add"),
    ("brew", "install"),
    ("apt", "install"),
    ("apt-get", "install"),
}

_INSTALL_TIMEOUT_MS = 120_000  # 2 min for package install commands

_SHELL_OPERATOR_TOKENS: set[str] = {
    "|", "||", "&&", ";", "(", ")",
}
_SHELL_REDIRECT_PREFIXES: tuple[str, ...] = (
    ">", ">>", "<", "<<", "1>", "1>>", "2>", "2>>", "0>",
)
_HEREDOC_OPEN_RE = re.compile(
    r"(?m)^(?:.*?)(?<!['\"])<<-?\s*"
    r"(?P<quote>['\"]?)(?P<tag>[A-Za-z_][A-Za-z0-9_]*)(?P=quote)\s*$"
)


def _is_install_command(command: list[str]) -> bool:
    if len(command) < 2:
        return False
    return (command[0], command[1]) in _INSTALL_COMMANDS


def _is_shell_fragment(token: str) -> bool:
    if token in _SHELL_OPERATOR_TOKENS:
        return True
    return token.startswith(_SHELL_REDIRECT_PREFIXES)


def _contains_shell_syntax(command: list[str]) -> bool:
    return any(_is_shell_fragment(token) for token in command)


def _command_array_to_shell_string(command: list[str]) -> str:
    rendered: list[str] = []
    for token in command:
        if _is_shell_fragment(token):
            rendered.append(token)
        else:
            rendered.append(shlex.quote(token))
    return " ".join(rendered)


def _contains_shell_syntax_in_text(command_text: str) -> bool:
    shell_markers = ("|", "&", ";", "<", ">", "(", ")", "\n", "\r")
    return any(marker in command_text for marker in shell_markers)


def _normalize_legacy_string_command(command_text: str) -> tuple[list[str], str]:
    """Normalize legacy string command input.

    Returns:
        (command_array, command_string)
        - command_array: safe direct-exec tokens when no shell composition is needed
        - command_string: raw shell command for multiline / redirection / pipelines
    """
    if not command_text.strip():
        return [], ""

    if _contains_shell_syntax_in_text(command_text):
        return [], command_text

    try:
        parsed = shlex.split(command_text, posix=os.name != "nt")
    except ValueError:
        # Keep raw text intact for shell execution to avoid lossy split().
        return [], command_text

    return parsed, ""


def _find_unclosed_heredoc_tags(command_text: str) -> list[str]:
    """Find heredoc delimiters that are opened but not properly closed."""
    matches = list(_HEREDOC_OPEN_RE.finditer(command_text))
    if not matches:
        return []

    lines = command_text.splitlines()
    if len(lines) <= 1:
        return [match.group("tag") for match in matches]

    unclosed: list[str] = []
    for match in matches:
        tag = match.group("tag")
        opener_line = command_text.count("\n", 0, match.start())
        matched_line = None
        for index in range(opener_line + 1, len(lines)):
            if lines[index].strip() == tag:
                matched_line = index
                break

        if matched_line is None:
            unclosed.append(tag)

    return unclosed


def _validate_shell_command(command_text: str) -> tuple[bool, str]:
    """Validate shell command string for dangerous malformed heredoc patterns."""
    unclosed_tags = _find_unclosed_heredoc_tags(command_text)
    if not unclosed_tags:
        return True, ""

    preview = ", ".join(unclosed_tags[:3])
    if len(unclosed_tags) > 3:
        preview = f"{preview}, ..."
    return False, f"Detected unclosed heredoc delimiter(s): {preview}"


class NodesTool(BaseTool):
    """
    Nodes 工具 - 发现、管理和操作本地/远程节点

    统一的节点操作工具
    """

    execution_timeout: int = 300

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
        return """Execute commands and manage local/remote nodes.

Actions:
  status        — List all node status
  run           — Execute shell command (output_handling: full|summary)
  write_file    — Write file (use this instead of run + echo/cat redirect)
  which         — Check if executable exists
  notify        — Send system notification
  describe      — Node details
  denylist_add  — Block dangerous commands
  security_info — View security policy

Call with only action to see detailed usage for that action."""

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "status", "describe", "run", "write_file",
                        "notify", "which", "denylist_add", "security_info",
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
                    "description": "Command as array (run action). Preferred for single commands.",
                },
                "command_string": {
                    "type": "string",
                    "description": (
                        "Command as shell string (run action). "
                        "Supports pipes and chains: cmd1 | cmd2, cmd1 && cmd2. "
                        "Use when you need pipe composition. "
                        "Mutually exclusive with command array."
                    ),
                },
                "output_handling": {
                    "type": "string",
                    "enum": ["full", "summary"],
                    "description": (
                        "输出处理方式（仅 run action）。"
                        "full = 你需要完整输出来分析/处理（如读文件、查日志、查看配置）；"
                        "summary = 你只需确认执行结果（如安装包、创建目录、写文件）。"
                        "默认 summary。"
                    ),
                    "default": "summary",
                },
                "cwd": {"type": "string", "description": "工作目录（run action）"},
                "env": {"type": "object", "description": "环境变量（run action）"},
                "timeout_ms": {"type": "integer", "description": "超时毫秒数（安装类命令自动提升至 120s）", "default": 60000},
                "title": {"type": "string", "description": "通知标题（notify action）"},
                "message": {"type": "string", "description": "通知内容（notify action）"},
                "subtitle": {"type": "string", "description": "通知副标题（notify action）"},
                "category": {
                    "type": "string",
                    "enum": ["health", "urgent", "reminder", "email", "calendar", "error", "build", "stock", "info"],
                    "description": "通知类别（notify action），影响图标和优先级",
                    "default": "info",
                },
                "file_path": {"type": "string", "description": "文件完整路径（write_file action）"},
                "file_content": {"type": "string", "description": "要写入的文件内容（write_file action）"},
                "executable": {"type": "string", "description": "可执行文件名（which action）"},
                "executables": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要加入黑名单的危险命令模式列表（denylist_add action）",
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
            elif action == "write_file":
                return await self._action_write_file(params)
            elif action == "notify":
                return await self._action_notify(node, params)
            elif action == "which":
                return await self._action_which(node, params)
            elif action == "denylist_add":
                return self._action_denylist_add(node, params)
            elif action == "security_info":
                return self._action_security_info(node)
            elif action in ("whitelist_add", "whitelist_info"):
                if action == "whitelist_add":
                    return self._action_denylist_add(node, params)
                return self._action_security_info(node)
            else:
                supported = [
                    "status", "describe", "run", "write_file",
                    "notify", "which", "denylist_add", "security_info",
                ]
                return {
                    "success": False,
                    "error": f"Unknown action: {action}",
                    "recovery_hint": f"Available actions: {', '.join(supported)}",
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

        return {
            "success": False,
            "error": f"Node not found: {node_id}",
            "recovery_hint": "Use: nodes status to list available nodes.",
        }

    async def _action_run(self, node_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute shell command on a node."""
        raw_command = params.get("command", [])
        raw_command_string = params.get("command_string", "")
        command: list[str] = []
        command_string = (
            raw_command_string if isinstance(raw_command_string, str) else ""
        )

        if isinstance(raw_command, list):
            command = [str(token) for token in raw_command]
        elif isinstance(raw_command, str):
            if command_string.strip():
                logger.info(
                    "Both command and command_string provided; prefer command_string"
                )
            else:
                command, command_string = _normalize_legacy_string_command(raw_command)
        elif raw_command:
            return {
                "success": False,
                "error": "Invalid command type, expected array or string",
                "recovery_hint": (
                    "Use command array for direct execution, or command_string for shell"
                ),
            }

        if command_string and not command:
            is_valid, validation_error = _validate_shell_command(command_string)
            if not is_valid:
                return {
                    "success": False,
                    "action": "run",
                    "node": node_id,
                    "error": validation_error,
                    "error_type": "invalid_shell_command",
                    "recovery_hint": (
                        "Close heredoc delimiter on its own line, or use "
                        "nodes write_file for multi-line file content."
                    ),
                }
            shell = "bash" if os.name != "nt" else "cmd"
            flag = "-c" if os.name != "nt" else "/c"
            command = [shell, flag, command_string]

        if not command:
            return {
                "success": False,
                "error": "Missing command or command_string parameter",
                "recovery_hint": (
                    "Usage:\n"
                    "  nodes run command=[\"ls\", \"-la\"]  (array, single command)\n"
                    "  nodes run command_string=\"cat log.txt | grep ERROR | wc -l\"  "
                    "(string, supports pipes)"
                ),
            }

        # Auto-upgrade array commands with shell operators to command_string mode.
        # This preserves user intent for pipe/redirection expressions like:
        #   find ... 2>/dev/null | head -20
        if command and not command_string and _contains_shell_syntax(command):
            command_string = _command_array_to_shell_string(command)
            is_valid, validation_error = _validate_shell_command(command_string)
            if not is_valid:
                return {
                    "success": False,
                    "action": "run",
                    "node": node_id,
                    "error": validation_error,
                    "error_type": "invalid_shell_command",
                    "recovery_hint": (
                        "Close heredoc delimiter on its own line, or use "
                        "nodes write_file for multi-line file content."
                    ),
                }
            shell = "bash" if os.name != "nt" else "cmd"
            flag = "-c" if os.name != "nt" else "/c"
            command = [shell, flag, command_string]
            logger.info("NodesTool auto-promoted command array with shell syntax")

        timeout_ms = params.get("timeout_ms", 60_000)
        if _is_install_command(command):
            timeout_ms = max(timeout_ms, _INSTALL_TIMEOUT_MS)

        response = await self.node_manager.run_command(
            command=command,
            cwd=params.get("cwd"),
            env=params.get("env"),
            timeout_ms=timeout_ms,
            node_id=node_id,
        )

        # Always include payload so stderr is visible even on failure
        inner_payload = response.payload
        result: Dict[str, Any] = {
            "success": response.ok,
            "action": "run",
            "node": node_id,
            "command": command,
            "result": inner_payload,
            "error": response.error if not response.ok else None,
            "elapsed_ms": response.elapsed_ms,
        }

        if inner_payload:
            inner_hint = inner_payload.get("_hint")
            if inner_hint:
                result["_hint"] = inner_hint
            status_line = inner_payload.get("_status_line")
            if status_line:
                result["_status_line"] = status_line
            inner_exit_code = inner_payload.get("exit_code")
            if inner_exit_code is not None and inner_exit_code != 0:
                result["success"] = False

        if not response.ok:
            error_code = getattr(response, "error_code", None)
            if error_code:
                result["error_type"] = error_code
                _RECOVERY_HINTS: Dict[str, str] = {
                    "permission_denied": (
                        "Permission denied. "
                        "Use: open_system_preferences to grant Accessibility access."
                    ),
                    "timeout": (
                        "Command timed out. "
                        "Try: increase timeout_ms or break into smaller steps."
                    ),
                    "dependency_missing": (
                        "Required dependency not found. "
                        "Use: nodes which <name> to check, "
                        "then install with user approval via hitl."
                    ),
                }
                result["recovery_hint"] = _RECOVERY_HINTS.get(
                    error_code,
                    f"Error type: {error_code}. Use: nodes status to check node health.",
                )

        output_handling = params.get("output_handling", "summary")
        if output_handling == "full":
            result["_compression_hint"] = "skip"

        return result

    async def _action_notify(self, node_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """发送系统通知"""
        title = params.get("title", "")
        message = params.get("message", "")

        if not title or not message:
            return {
                "success": False,
                "error": "Missing title or message parameter",
                "recovery_hint": "Usage: nodes notify title=\"...\" message=\"...\"",
            }

        response = await self.node_manager.notify(
            title=title,
            message=message,
            subtitle=params.get("subtitle"),
            category=params.get("category"),
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
            return {
                "success": False,
                "error": "Missing executable parameter",
                "recovery_hint": "Usage: nodes which executable=\"<name>\"",
            }

        response = await self.node_manager.invoke(
            command="system.which",
            params={"executable": executable},
            node_id=node_id,
        )

        if response.ok:
            return {"success": True, "action": "which", "node": node_id, **(response.payload or {})}
        else:
            return {"success": False, "action": "which", "node": node_id, "error": response.error}

    async def _action_write_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Write content to a file (create or overwrite)."""
        file_path = params.get("file_path", "")
        file_content = params.get("file_content", "")

        if not file_path:
            return {
                "success": False,
                "error": "Missing file_path parameter",
                "recovery_hint": (
                    "Usage: nodes write_file file_path=\"/path/to/file\" "
                    "file_content=\"...\""
                ),
            }

        file_path = os.path.expanduser(file_path)

        try:
            parent = os.path.dirname(file_path)
            if parent:
                os.makedirs(parent, exist_ok=True)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(file_content)

            size = os.path.getsize(file_path)
            return {
                "success": True,
                "action": "write_file",
                "file_path": file_path,
                "bytes_written": size,
            }
        except PermissionError:
            return {
                "success": False,
                "action": "write_file",
                "error": f"Permission denied: {file_path}",
                "recovery_hint": "Check directory permissions or choose a writable path.",
            }
        except Exception as e:
            return {"success": False, "action": "write_file", "error": str(e)}

    def _action_denylist_add(self, node_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Add dangerous patterns to denylist."""
        executables = params.get("executables", [])
        if not executables:
            return {
                "success": False,
                "error": "Missing executables parameter",
                "recovery_hint": (
                    "Usage: nodes denylist_add executables=[\"<pattern>\", ...]\n"
                    "Use: nodes security_info to view current policy."
                ),
            }

        if isinstance(executables, str):
            executables = [executables]

        result = self.node_manager.add_to_denylist(executables, node_id=node_id)
        if "error" in result:
            return {"success": False, "action": "denylist_add", "error": result["error"]}

        return {"success": True, "action": "denylist_add", "node": node_id, **result}

    def _action_security_info(self, node_id: str) -> Dict[str, Any]:
        """Return current security policy state."""
        result = self.node_manager.get_allowlist_info(node_id=node_id)
        if "error" in result:
            return {"success": False, "action": "security_info", "error": result["error"]}
        return {"success": True, "action": "security_info", "node": node_id, **result}


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
