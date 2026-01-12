"""
SubagentWorker - Claude 原生子智能体 Worker

利用 Claude 4.5 的原生子智能体编排能力

参考文档：
- https://platform.claude.com/docs/en/build-with-claude/agentic-capabilities/subagent-orchestration
- https://www.anthropic.com/engineering/multi-agent-research-system

Claude 原生子智能体特点：
1. 模型内部管理：无需外部编排
2. 上下文隔离：子智能体有独立的上下文窗口
3. 工具委托：可以将特定工具委托给子智能体
4. 低延迟：减少 API 往返
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseWorker, WorkerType, WorkerInput, WorkerOutput, WorkerStatus

logger = logging.getLogger(__name__)


class SubagentWorker(BaseWorker):
    """
    Subagent Worker - 使用 Claude 原生子智能体执行任务
    
    Claude 4.5 支持在单次 API 调用中委托任务给"子智能体"，
    子智能体有独立的上下文和工具集。
    
    适用场景：
    1. 需要隔离上下文的并行任务
    2. 工具密集型的专业任务
    3. 需要减少 API 调用延迟的场景
    
    实现方式：
    通过 system prompt 工程，让 Claude 扮演"子智能体"角色，
    或使用 Claude 4.5 的 tool_use 机制委托任务。
    
    Example:
        worker = SubagentWorker(
            name="research-subagent",
            specialization="research",
            subagent_prompt="你是一个研究助手...",
            delegated_tools=["web_search", "document_reader"]
        )
    
    配置示例 (worker_registry.yaml):
        workers:
          - name: research-subagent
            type: subagent
            specialization: research
            delegated_tools:
              - web_search
              - document_reader
            max_iterations: 5
    """
    
    def __init__(
        self,
        name: str,
        specialization: str = "general",
        subagent_prompt: str = None,
        delegated_tools: List[str] = None,
        max_iterations: int = 5,
        model: str = "claude-sonnet-4-5-20250929",
        config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            name=name,
            worker_type=WorkerType.AGENT,
            specialization=specialization,
            config=config
        )
        
        self.subagent_prompt = subagent_prompt or self._get_default_subagent_prompt()
        self.delegated_tools = delegated_tools or []
        self.max_iterations = max_iterations
        self.model = model
        
        self._agent = None
        
        logger.info(f"SubagentWorker 初始化: {name} (工具: {len(self.delegated_tools)} 个)")
    
    def _get_default_subagent_prompt(self) -> str:
        """获取默认的子智能体提示词"""
        return f"""你是一个专注于 {self.specialization} 的子智能体。

## 角色定位
你是主智能体的专业助手，负责处理特定领域的任务。
你有独立的上下文和工具集，专注于高质量完成分配的任务。

## 工作原则
1. 专注：只处理分配给你的任务，不要越界
2. 高效：使用最少的步骤完成任务
3. 清晰：输出结构化、易于理解的结果
4. 完整：确保任务完全完成后再返回结果

## 输出格式
完成任务后，请提供：
1. 任务摘要
2. 详细结果
3. 相关产出物（如果有）
"""
    
    def _get_or_create_agent(self):
        """获取或创建子智能体"""
        if self._agent is None:
            from core.agent import SimpleAgent
            
            # 构建子智能体专用的 system prompt
            system_prompt = self._build_subagent_system_prompt()
            
            self._agent = SimpleAgent(
                model=self.model,
                max_turns=self.max_iterations,
                system_prompt=system_prompt
            )
            
            logger.info(f"SubagentWorker '{self.name}' 创建子智能体")
        
        return self._agent
    
    def _build_subagent_system_prompt(self) -> str:
        """构建子智能体系统提示词"""
        parts = [self.subagent_prompt]
        
        # 添加可用工具说明
        if self.delegated_tools:
            tools_str = ", ".join(self.delegated_tools)
            parts.append(f"\n\n## 可用工具\n你可以使用以下工具：{tools_str}")
        
        return "\n".join(parts)
    
    async def execute(self, input: WorkerInput) -> WorkerOutput:
        """
        使用子智能体执行任务
        
        子智能体模式的特点：
        - 有限的迭代次数（max_iterations）
        - 上下文隔离
        - 专用工具集
        """
        start_time = datetime.now()
        
        try:
            agent = self._get_or_create_agent()
            
            # 构建子智能体任务
            task = self._build_subagent_task(input)
            
            logger.info(f"SubagentWorker '{self.name}' 开始任务: {input.action[:50]}...")
            
            # 执行子智能体
            final_response = ""
            artifacts = []
            iterations = 0
            
            async for event in agent.chat(
                user_input=task,
                session_id=f"subagent-{self.name}-{input.task_id}"
            ):
                if event.get("type") == "content_delta":
                    delta = event.get("data", {}).get("delta", "")
                    if isinstance(delta, str):
                        final_response += delta
                
                if event.get("type") == "artifact":
                    artifacts.append(event.get("data", {}))
                
                # 跟踪迭代
                if event.get("type") == "tool_use":
                    iterations += 1
            
            duration = (datetime.now() - start_time).total_seconds()
            
            logger.info(f"SubagentWorker '{self.name}' 完成 ({iterations} 次工具调用)，耗时 {duration:.1f}s")
            
            return WorkerOutput(
                task_id=input.task_id,
                status=WorkerStatus.COMPLETED,
                result=final_response,
                artifacts=artifacts,
                duration=duration,
                metadata={
                    "iterations": iterations,
                    "delegated_tools": self.delegated_tools,
                    "worker_type": "subagent"
                }
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"SubagentWorker '{self.name}' 执行失败: {e}")
            
            return WorkerOutput(
                task_id=input.task_id,
                status=WorkerStatus.FAILED,
                error=str(e),
                duration=duration
            )
    
    def _build_subagent_task(self, input: WorkerInput) -> str:
        """构建子智能体任务"""
        parts = [f"## 任务\n{input.action}"]
        
        if input.dependencies_results:
            parts.append("\n## 前置任务结果")
            for task_id, result in input.dependencies_results.items():
                parts.append(f"### {task_id}\n{result}")
        
        if input.context:
            parts.append("\n## 上下文")
            for key, value in input.context.items():
                parts.append(f"- {key}: {value}")
        
        parts.append(f"\n## 约束\n- 最多使用 {self.max_iterations} 次工具调用完成任务")
        
        return "\n".join(parts)
    
    async def health_check(self) -> bool:
        """健康检查"""
        return True
