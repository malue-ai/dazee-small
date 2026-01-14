"""
多智能体编排器

负责协调多个 Agent 的执行，支持串行、并行、层级三种模式。

设计原则：
1. 与 SimpleAgent 完全独立
2. 通过 AgentRouter 被调用，而非互相嵌套
3. 每个子 Agent 是独立的 LLM 调用单元
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import uuid4

from core.agent.multi.models import (
    ExecutionMode,
    AgentConfig,
    MultiAgentConfig,
    TaskAssignment,
    AgentResult,
    OrchestratorState,
)
from core.routing import IntentResult

logger = logging.getLogger(__name__)


class MultiAgentOrchestrator:
    """
    多智能体编排器
    
    负责协调多个 Agent 的执行：
    - SEQUENTIAL: 依次执行，前一个输出作为后一个输入
    - PARALLEL: 同时执行，结果汇总
    - HIERARCHICAL: 主 Agent 分配任务给子 Agent
    
    使用方式：
        orchestrator = MultiAgentOrchestrator(config)
        async for event in orchestrator.execute(intent, messages, session_id):
            # 处理事件
            pass
    """
    
    def __init__(
        self,
        config: Optional[MultiAgentConfig] = None,
        mode: ExecutionMode = ExecutionMode.SEQUENTIAL,
        agents: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        初始化编排器
        
        Args:
            config: 完整的多智能体配置（优先使用）
            mode: 执行模式（当 config 为 None 时使用）
            agents: 智能体配置列表（当 config 为 None 时使用）
        """
        if config:
            self.config = config
        else:
            # 从参数构建配置
            agent_configs = []
            for i, agent_dict in enumerate(agents or []):
                agent_configs.append(AgentConfig(
                    agent_id=agent_dict.get("agent_id", f"agent_{i}"),
                    role=agent_dict.get("role", "executor"),
                    model=agent_dict.get("model", "claude-sonnet-4-5-20250929"),
                    system_prompt=agent_dict.get("system_prompt"),
                    tools=agent_dict.get("tools", []),
                ))
            
            self.config = MultiAgentConfig(
                config_id=f"config_{uuid4().hex[:8]}",
                mode=mode,
                agents=agent_configs,
            )
        
        self._state: Optional[OrchestratorState] = None
        logger.info(
            f"✅ MultiAgentOrchestrator 初始化: mode={self.config.mode.value}, "
            f"agents={len(self.config.agents)}"
        )
    
    async def execute(
        self,
        intent: Optional[IntentResult],
        messages: List[Dict[str, str]],
        session_id: str,
        message_id: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行多智能体协作
        
        Args:
            intent: 意图分析结果（来自路由层）
            messages: 消息历史
            session_id: 会话 ID
            message_id: 消息 ID
            
        Yields:
            事件字典
        """
        start_time = time.time()
        
        # 初始化状态
        self._state = OrchestratorState(
            state_id=f"orch_{uuid4().hex[:8]}",
            session_id=session_id,
            config_id=self.config.config_id,
            mode=self.config.mode,
            status="running",
            pending_agents=[agent.agent_id for agent in self.config.agents],
            started_at=datetime.now(),
        )
        
        # 发送开始事件
        yield {
            "type": "orchestrator_start",
            "session_id": session_id,
            "mode": self.config.mode.value,
            "agent_count": len(self.config.agents),
        }
        
        try:
            # 根据模式执行
            if self.config.mode == ExecutionMode.SEQUENTIAL:
                async for event in self._execute_sequential(messages, session_id, message_id):
                    yield event
            
            elif self.config.mode == ExecutionMode.PARALLEL:
                async for event in self._execute_parallel(messages, session_id, message_id):
                    yield event
            
            elif self.config.mode == ExecutionMode.HIERARCHICAL:
                async for event in self._execute_hierarchical(intent, messages, session_id, message_id):
                    yield event
            
            # 生成最终汇总
            if self.config.enable_final_summary:
                final_output = await self._generate_summary()
                self._state.final_output = final_output
                
                yield {
                    "type": "orchestrator_summary",
                    "session_id": session_id,
                    "content": final_output,
                }
            
            # 完成
            duration_ms = int((time.time() - start_time) * 1000)
            self._state.status = "completed"
            self._state.completed_at = datetime.now()
            self._state.total_duration_ms = duration_ms
            
            yield {
                "type": "orchestrator_end",
                "session_id": session_id,
                "status": "completed",
                "duration_ms": duration_ms,
                "agent_results": len(self._state.agent_results),
            }
            
        except Exception as e:
            logger.error(f"❌ 多智能体执行失败: {e}", exc_info=True)
            self._state.status = "failed"
            self._state.errors.append({
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            })
            
            yield {
                "type": "orchestrator_error",
                "session_id": session_id,
                "error": str(e),
            }
    
    async def _execute_sequential(
        self,
        messages: List[Dict[str, str]],
        session_id: str,
        message_id: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        串行执行模式
        
        每个 Agent 依次执行，前一个的输出作为后一个的输入
        """
        current_input = messages
        previous_output = None
        
        for agent_config in self.config.agents:
            agent_id = agent_config.agent_id
            self._state.current_agent = agent_id
            
            # 发送 Agent 开始事件
            yield {
                "type": "agent_start",
                "session_id": session_id,
                "agent_id": agent_id,
                "role": agent_config.role.value,
            }
            
            # 创建任务分配
            task = TaskAssignment(
                task_id=f"task_{uuid4().hex[:8]}",
                agent_id=agent_id,
                instruction=f"执行 {agent_config.role.value} 任务",
                source_agent=self._state.completed_agents[-1] if self._state.completed_agents else None,
                source_output=previous_output,
            )
            self._state.task_assignments.append(task)
            
            # 执行 Agent（这里是占位实现，实际需要调用独立的 LLM）
            result = await self._execute_single_agent(
                agent_config, 
                current_input, 
                previous_output,
                session_id
            )
            
            self._state.agent_results.append(result)
            self._state.completed_agents.append(agent_id)
            self._state.pending_agents.remove(agent_id)
            
            # 更新前一个输出
            previous_output = result.output
            
            # 发送 Agent 完成事件
            yield {
                "type": "agent_end",
                "session_id": session_id,
                "agent_id": agent_id,
                "success": result.success,
                "output_preview": result.output[:200] if result.output else "",
            }
            
            # 检查是否失败
            if not result.success and self.config.fail_fast:
                logger.warning(f"⚠️ Agent {agent_id} 失败，fail_fast=True，停止执行")
                break
        
        self._state.current_agent = None
    
    async def _execute_parallel(
        self,
        messages: List[Dict[str, str]],
        session_id: str,
        message_id: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        并行执行模式
        
        所有 Agent 同时执行，最后汇总结果
        """
        # 创建所有 Agent 的任务
        tasks = []
        for agent_config in self.config.agents:
            task = asyncio.create_task(
                self._execute_single_agent(agent_config, messages, None, session_id)
            )
            tasks.append((agent_config, task))
        
        # 发送并行开始事件
        yield {
            "type": "parallel_start",
            "session_id": session_id,
            "agent_count": len(tasks),
        }
        
        # 等待所有任务完成
        for agent_config, task in tasks:
            try:
                result = await asyncio.wait_for(
                    task, 
                    timeout=agent_config.timeout_seconds
                )
            except asyncio.TimeoutError:
                result = AgentResult(
                    result_id=f"result_{uuid4().hex[:8]}",
                    agent_id=agent_config.agent_id,
                    success=False,
                    error="执行超时",
                )
            
            self._state.agent_results.append(result)
            self._state.completed_agents.append(agent_config.agent_id)
            
            yield {
                "type": "agent_end",
                "session_id": session_id,
                "agent_id": agent_config.agent_id,
                "success": result.success,
            }
        
        self._state.pending_agents = []
    
    async def _execute_hierarchical(
        self,
        intent: Optional[IntentResult],
        messages: List[Dict[str, str]],
        session_id: str,
        message_id: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        层级执行模式
        
        主 Agent（Planner）分解任务，分配给子 Agent 执行
        """
        # 找到 Planner Agent
        planner = next(
            (a for a in self.config.agents if a.role.value == "planner"),
            self.config.agents[0] if self.config.agents else None
        )
        
        if not planner:
            yield {
                "type": "orchestrator_error",
                "session_id": session_id,
                "error": "层级模式需要至少一个 Planner Agent",
            }
            return
        
        # Step 1: Planner 分解任务
        yield {
            "type": "planner_start",
            "session_id": session_id,
            "agent_id": planner.agent_id,
        }
        
        # 这里是占位实现，实际需要 Planner 返回任务分解
        plan_result = await self._execute_single_agent(planner, messages, None, session_id)
        
        yield {
            "type": "planner_end",
            "session_id": session_id,
            "agent_id": planner.agent_id,
            "success": plan_result.success,
        }
        
        # Step 2: 分配任务给子 Agent（简化实现）
        sub_agents = [a for a in self.config.agents if a.agent_id != planner.agent_id]
        
        for sub_agent in sub_agents:
            yield {
                "type": "sub_agent_start",
                "session_id": session_id,
                "agent_id": sub_agent.agent_id,
            }
            
            result = await self._execute_single_agent(
                sub_agent, 
                messages, 
                plan_result.output,
                session_id
            )
            
            self._state.agent_results.append(result)
            self._state.completed_agents.append(sub_agent.agent_id)
            
            yield {
                "type": "sub_agent_end",
                "session_id": session_id,
                "agent_id": sub_agent.agent_id,
                "success": result.success,
            }
    
    async def _execute_single_agent(
        self,
        config: AgentConfig,
        messages: List[Dict[str, str]],
        previous_output: Optional[str],
        session_id: str,
    ) -> AgentResult:
        """
        执行单个 Agent
        
        这是占位实现，实际需要：
        1. 创建独立的 LLM 调用
        2. 注入角色专用 prompt
        3. 执行并收集结果
        
        Args:
            config: Agent 配置
            messages: 消息历史
            previous_output: 前一个 Agent 的输出（串行模式）
            session_id: 会话 ID
            
        Returns:
            AgentResult 执行结果
        """
        start_time = time.time()
        
        # 🎯 这里是 P1 待实现的核心逻辑
        # 实际实现需要：
        # 1. from core.llm import create_claude_service
        # 2. 构建角色专用 system_prompt
        # 3. 调用 LLM 并收集结果
        # 4. 处理工具调用（如果有）
        
        logger.info(
            f"🤖 执行 Agent: {config.agent_id} ({config.role.value}), "
            f"model={config.model}"
        )
        
        # 模拟执行（占位）
        await asyncio.sleep(0.1)  # 模拟网络延迟
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        return AgentResult(
            result_id=f"result_{uuid4().hex[:8]}",
            agent_id=config.agent_id,
            success=True,
            output=f"[{config.role.value}] 任务执行完成（占位输出）",
            turns_used=1,
            duration_ms=duration_ms,
            started_at=datetime.now(),
            completed_at=datetime.now(),
            metadata={
                "model": config.model,
                "previous_output_length": len(previous_output) if previous_output else 0,
            }
        )
    
    async def _generate_summary(self) -> str:
        """
        生成最终汇总
        
        将所有 Agent 的输出整合为最终结果
        """
        if not self._state or not self._state.agent_results:
            return "没有可汇总的结果"
        
        # 简单汇总（实际可以用专门的 Summarizer Agent）
        summary_parts = []
        for result in self._state.agent_results:
            if result.success and result.output:
                summary_parts.append(f"【{result.agent_id}】\n{result.output}")
        
        return "\n\n".join(summary_parts) if summary_parts else "所有 Agent 执行失败"
    
    def get_state(self) -> Optional[OrchestratorState]:
        """获取当前状态"""
        return self._state
