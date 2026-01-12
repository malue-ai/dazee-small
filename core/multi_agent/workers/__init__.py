"""
Multi-Agent Workers 模块

支持 7 种 Worker 实现形态：
1. AgentWorker: 内置 SimpleAgent
2. SkillWorker: Claude Skills 专业能力
3. MCPWorker: MCP Server 远程服务
4. WorkflowWorker: Coze/Dify Workflow
5. SandboxWorker: E2B/代码执行沙箱
6. SubagentWorker: Claude 原生子智能体
7. HumanWorker: Human-In-The-Loop

使用示例：
    from core.multi_agent.workers import WorkerFactory, WorkerInput
    
    # 从配置创建 Skill Worker
    worker = WorkerFactory.create_from_config({
        "name": "pptx-generator",
        "type": "skill",
        "skill_id": "pptx-generator"
    })
    
    # 从配置创建 Workflow Worker
    worker = WorkerFactory.create_from_config({
        "name": "coze-research",
        "type": "workflow",
        "platform": "coze",
        "workflow_id": "7xxx"
    })
    
    # 执行任务
    result = await worker.execute(WorkerInput(
        task_id="task-1",
        action="创建 AI 趋势分析 PPT"
    ))
"""

from .base import (
    BaseWorker,
    WorkerType,
    WorkerStatus,
    WorkerInput,
    WorkerOutput,
)
from .agent_worker import AgentWorker
from .skill_worker import SkillWorker
from .mcp_worker import MCPWorker
from .workflow_worker import WorkflowWorker, WorkflowPlatform
from .sandbox_worker import SandboxWorker
from .subagent_worker import SubagentWorker
from .human_worker import HumanWorker, HumanTaskType
from .factory import WorkerFactory

__all__ = [
    # 工厂
    "WorkerFactory",
    # 基类
    "BaseWorker",
    "WorkerType",
    "WorkerStatus",
    "WorkerInput",
    "WorkerOutput",
    # Worker 实现
    "AgentWorker",
    "SkillWorker",
    "MCPWorker",
    "WorkflowWorker",
    "WorkflowPlatform",
    "SandboxWorker",
    "SubagentWorker",
    "HumanWorker",
    "HumanTaskType",
]
