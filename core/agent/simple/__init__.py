"""
Simple Agent 模块

职责：
- SimpleAgent: 单智能体执行引擎
- 支持 RVR (Read-Reason-Act-Observe-Validate-Write-Repeat) 循环
- 工具执行、上下文管理、Prompt 构建

使用方式：
    from core.agent.simple import SimpleAgent, create_simple_agent
    
    agent = create_simple_agent(
        model="claude-sonnet-4-5-20250929",
        event_manager=event_manager
    )
    
    async for event in agent.chat(messages, session_id):
        print(event)
"""

from core.agent.simple.simple_agent import (
    SimpleAgent,
    create_simple_agent
)

__all__ = [
    "SimpleAgent",
    "create_simple_agent",
]
