"""
Agent 上下文与 Prompt 构建模块

这是 agent 内部的 Builder 层，负责：
- 组装 core/context 的 injector 能力
- 构建 LLM 调用所需的 system blocks
- 管理 runtime context 和 session 状态

目录结构：
- prompt_builder.py: build_system_blocks_with_injector 的归属地
- context_builder.py: runtime/context + variables/metadata 组装（可选）
- state.py: session 级状态（plan_cache/tool_calls 等）

注意：这不是"另一个层"，而是把 core/context 的通用能力
组合成 agent 需要的可执行行为。
"""

from core.agent.context.prompt_builder import (
    build_messages_with_injector,
    build_system_blocks_with_injector,
    build_user_context_with_injector,
    fetch_user_profile,
    get_task_complexity,
)

__all__ = [
    "build_system_blocks_with_injector",
    "build_user_context_with_injector",
    "build_messages_with_injector",
    "get_task_complexity",
    "fetch_user_profile",
]
