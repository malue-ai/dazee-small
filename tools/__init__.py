"""
Tools 工具模块

此目录包含各类工具的具体实现：
- plan_todo_tool.py: Plan/Todo 工具
- slidespeak.py: SlideSpeek PPT 工具
- request_human_confirmation.py: HITL 工具
- e2b_python_sandbox.py: E2B 沙箱工具

注意：工具核心逻辑（Selector、Executor）已移至 core/tool/

向后兼容导出（推荐使用 core.tool）：
- ToolSelector, create_tool_selector
- ToolExecutor, create_tool_executor
"""

# 向后兼容：从 core.tool 重导出
from core.tool import (
    ToolSelector,
    ToolSelectionResult,
    create_tool_selector,
    ToolExecutor,
    create_tool_executor,
)

__all__ = [
    # 向后兼容（已废弃，推荐使用 core.tool）
    "ToolSelector",
    "ToolSelectionResult",
    "create_tool_selector",
    "ToolExecutor",
    "create_tool_executor",
]

