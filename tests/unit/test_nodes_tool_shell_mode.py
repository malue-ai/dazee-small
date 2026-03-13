"""Unit tests for nodes tool shell-syntax handling."""

from __future__ import annotations

import os

import pytest

from core.nodes.protocol import NodeInvokeResponse
from tools.nodes_tool import NodesTool


class _FakeNodeManager:
    def __init__(self) -> None:
        self.started = False
        self.last_command: list[str] | None = None

    async def start(self) -> None:
        self.started = True

    async def run_command(
        self,
        command: list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_ms: int = 60_000,
        node_id: str = "local",
    ) -> NodeInvokeResponse:
        self.last_command = command
        return NodeInvokeResponse.success(
            request_id="req-1",
            payload={
                "stdout": "ok",
                "stderr": "",
                "exit_code": 0,
                "timed_out": False,
            },
            elapsed_ms=1,
        )


@pytest.mark.asyncio
async def test_run_auto_promotes_array_with_pipe_to_shell_string() -> None:
    manager = _FakeNodeManager()
    tool = NodesTool(node_manager=manager)

    result = await tool.execute(
        {
            "action": "run",
            "command": [
                "find",
                "/Users/liuyi/Documents",
                "-name",
                "*sales*",
                "2>/dev/null",
                "|",
                "head",
                "-20",
            ],
        }
    )

    assert result["success"] is True
    assert manager.last_command is not None
    if os.name == "nt":
        assert manager.last_command[0] == "cmd"
        assert manager.last_command[1] == "/c"
    else:
        assert manager.last_command[0] == "bash"
        assert manager.last_command[1] == "-c"
    shell_cmd = manager.last_command[2]
    assert "2>/dev/null" in shell_cmd
    assert "|" in shell_cmd
    assert "'*sales*'" in shell_cmd


@pytest.mark.asyncio
async def test_run_keeps_plain_array_without_shell_syntax() -> None:
    manager = _FakeNodeManager()
    tool = NodesTool(node_manager=manager)

    result = await tool.execute(
        {
            "action": "run",
            "command": ["ls", "-la"],
        }
    )

    assert result["success"] is True
    assert manager.last_command == ["ls", "-la"]


@pytest.mark.asyncio
async def test_run_legacy_plain_string_command_keeps_direct_execution() -> None:
    manager = _FakeNodeManager()
    tool = NodesTool(node_manager=manager)

    result = await tool.execute(
        {
            "action": "run",
            "command": "ls -la /tmp",
        }
    )

    assert result["success"] is True
    assert manager.last_command == ["ls", "-la", "/tmp"]


@pytest.mark.asyncio
async def test_run_multiline_string_command_uses_shell_mode_without_split() -> None:
    manager = _FakeNodeManager()
    tool = NodesTool(node_manager=manager)

    script = "cat > /tmp/demo.txt <<'EOF'\nhello\nEOF"
    result = await tool.execute(
        {
            "action": "run",
            "command": script,
        }
    )

    assert result["success"] is True
    assert manager.last_command is not None
    if os.name == "nt":
        assert manager.last_command[0] == "cmd"
        assert manager.last_command[1] == "/c"
    else:
        assert manager.last_command[0] == "bash"
        assert manager.last_command[1] == "-c"
    assert manager.last_command[2] == script
