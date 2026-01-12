"""
AgentWorker - 内置 SimpleAgent Worker

将 SimpleAgent 包装为标准 Worker 接口
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from .base import BaseWorker, WorkerType, WorkerInput, WorkerOutput, WorkerStatus

logger = logging.getLogger(__name__)


class AgentWorker(BaseWorker):
    """
    Agent Worker - 使用内置 SimpleAgent 执行任务
    
    这是最基础的 Worker 类型，直接使用 ZenFlux 的 SimpleAgent。
    
    Example:
        worker = AgentWorker(
            name="refactor-worker",
            specialization="refactor",
            system_prompt="你是一个代码重构专家...",
            model="claude-sonnet-4-5-20250929"
        )
        
        result = await worker.execute(WorkerInput(
            task_id="task-1",
            action="重构用户认证模块"
        ))
    """
    
    def __init__(
        self,
        name: str,
        specialization: str = "general",
        system_prompt: str = "",
        model: str = "claude-sonnet-4-5-20250929",
        max_turns: int = 10,
        config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            name=name,
            worker_type=WorkerType.AGENT,
            specialization=specialization,
            config=config
        )
        
        self.system_prompt = system_prompt
        self.model = model
        self.max_turns = max_turns
        self._agent = None  # 延迟初始化
    
    def _get_or_create_agent(self):
        """获取或创建 Agent 实例"""
        if self._agent is None:
            # 延迟导入避免循环依赖
            from core.agent import SimpleAgent
            
            self._agent = SimpleAgent(
                model=self.model,
                max_turns=self.max_turns,
                system_prompt=self.system_prompt
            )
            logger.info(f"AgentWorker '{self.name}' 创建 SimpleAgent 实例")
        
        return self._agent
    
    async def execute(self, input: WorkerInput) -> WorkerOutput:
        """
        执行任务
        
        使用 SimpleAgent 执行任务，收集流式输出并返回最终结果
        """
        start_time = datetime.now()
        
        try:
            agent = self._get_or_create_agent()
            
            # 构建完整的任务上下文
            task_context = self._build_task_context(input)
            
            logger.info(f"AgentWorker '{self.name}' 开始执行任务: {input.action[:50]}...")
            
            # 执行 Agent
            final_response = ""
            artifacts = []
            
            async for event in agent.chat(
                user_input=task_context,
                session_id=f"worker-{self.name}-{input.task_id}"
            ):
                # 收集响应
                if event.get("type") == "content_delta":
                    delta = event.get("data", {}).get("delta", "")
                    if isinstance(delta, str):
                        final_response += delta
                
                # 收集产出物
                if event.get("type") == "artifact":
                    artifacts.append(event.get("data", {}))
            
            duration = (datetime.now() - start_time).total_seconds()
            
            logger.info(f"AgentWorker '{self.name}' 任务完成，耗时 {duration:.1f}s")
            
            return WorkerOutput(
                task_id=input.task_id,
                status=WorkerStatus.COMPLETED,
                result=final_response,
                artifacts=artifacts,
                duration=duration,
                metadata={
                    "model": self.model,
                    "worker_type": "agent"
                }
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"AgentWorker '{self.name}' 执行失败: {e}")
            
            return WorkerOutput(
                task_id=input.task_id,
                status=WorkerStatus.FAILED,
                error=str(e),
                duration=duration
            )
    
    def _build_task_context(self, input: WorkerInput) -> str:
        """构建任务上下文"""
        context_parts = [input.action]
        
        # 添加依赖任务的结果
        if input.dependencies_results:
            context_parts.append("\n\n## 前置任务结果\n")
            for task_id, result in input.dependencies_results.items():
                context_parts.append(f"### {task_id}\n{result}\n")
        
        # 添加额外上下文
        if input.context:
            context_parts.append("\n\n## 上下文信息\n")
            for key, value in input.context.items():
                context_parts.append(f"- {key}: {value}")
        
        return "\n".join(context_parts)
    
    async def health_check(self) -> bool:
        """健康检查"""
        # Agent Worker 始终可用
        return True
