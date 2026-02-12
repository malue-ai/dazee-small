"""
Agent V3.6 - Prompt-Driven + Memory-First 架构

基于Claude 4.5系列LLM的智能体架构，核心特点：
- Extended Thinking - 深度推理
- Memory-First Protocol - Plan/Todo 存储到 Short Memory
- Skills-First - 本地工作流技能
- Code-First - 动态代码生成和验证
- Native Tool Use - 原生工具调用

术语说明：
- Skill: 本地工作流技能（skills/library/）

架构特点：
1. 无LangGraph依赖 - 直接使用Claude API
2. Prompt-Driven - 系统提示词为大脑，Agent 为骨架
3. Memory-First - Plan/Todo 存储到 WorkingMemory，避免多轮 token 浪费
4. plan_todo Tool - LLM 通过工具 CRUD Plan/Todo，存入 Short Memory

版本: 3.6
"""

__version__ = "3.6.0"

from core.agent import Agent, create_agent
from core.memory import (
    MemoryManager,
    WorkingMemory,
    EpisodicMemory,
    SkillMemory,
    create_memory_manager
)
from tools.plan_todo_tool import (
    PlanTodoTool,
    create_plan_todo_tool,
)

__all__ = [
    # Core Agent
    "Agent",
    "create_agent",
    
    # Memory Layer
    "MemoryManager",
    "WorkingMemory",
    "EpisodicMemory",
    "SkillMemory",  # 本地工作流技能缓存
    "create_memory_manager",
    
    # Plan/Todo Tool (替代 PlanningManager)
    "PlanTodoTool",
    "create_plan_todo_tool",
]

