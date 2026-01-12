"""
Multi-Agent 模块单元测试

测试 V6.0 Multi-Agent 编排系统的核心功能
"""

import asyncio
import pytest
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestFSMStates:
    """FSM 状态测试"""
    
    def test_task_state_creation(self):
        """测试 TaskState 创建"""
        from core.multi_agent.fsm.states import TaskState, TaskStatus
        
        state = TaskState(
            task_id="test-1",
            session_id="sess-1",
            user_query="测试任务"
        )
        
        assert state.task_id == "test-1"
        assert state.status == TaskStatus.PENDING
        assert state.progress == 0.0
    
    def test_task_state_serialization(self):
        """测试 TaskState 序列化"""
        from core.multi_agent.fsm.states import TaskState, TaskStatus
        
        state = TaskState(
            task_id="test-1",
            session_id="sess-1",
            user_query="测试任务"
        )
        
        # 序列化
        data = state.to_dict()
        assert "task_id" in data
        assert "status" in data
        
        # 反序列化
        restored = TaskState.from_dict(data)
        assert restored.task_id == state.task_id
        assert restored.status == state.status
    
    def test_sub_task_state(self):
        """测试 SubTaskState"""
        from core.multi_agent.fsm.states import SubTaskState, SubTaskStatus
        
        sub_task = SubTaskState(
            id="sub-1",
            action="测试子任务",
            specialization="research",
            dependencies=["sub-0"]
        )
        
        assert sub_task.id == "sub-1"
        assert sub_task.status == SubTaskStatus.PENDING
        assert "sub-0" in sub_task.dependencies


class TestFSMTransitions:
    """FSM 状态转换测试"""
    
    def test_valid_transition(self):
        """测试合法状态转换"""
        from core.multi_agent.fsm.transitions import (
            is_valid_transition,
            get_next_status,
            TaskStatus
        )
        
        # PENDING -> DECOMPOSING
        assert is_valid_transition(TaskStatus.PENDING, "start")
        assert get_next_status(TaskStatus.PENDING, "start") == TaskStatus.DECOMPOSING
    
    def test_invalid_transition(self):
        """测试非法状态转换"""
        from core.multi_agent.fsm.transitions import is_valid_transition, TaskStatus
        
        # PENDING 不能直接到 COMPLETED
        assert not is_valid_transition(TaskStatus.PENDING, "complete")
    
    def test_terminal_status(self):
        """测试终态"""
        from core.multi_agent.fsm.transitions import is_terminal_status, TaskStatus
        
        assert is_terminal_status(TaskStatus.COMPLETED)
        assert is_terminal_status(TaskStatus.FAILED)
        assert not is_terminal_status(TaskStatus.EXECUTING)


class TestDependencyGraph:
    """依赖图测试"""
    
    def test_add_tasks(self):
        """测试添加任务"""
        from core.multi_agent.scheduling.dependency_graph import DependencyGraph
        from core.multi_agent.fsm.states import SubTaskState
        
        graph = DependencyGraph()
        
        task1 = SubTaskState(id="task-1", action="任务1", specialization="research")
        task2 = SubTaskState(id="task-2", action="任务2", specialization="document", dependencies=["task-1"])
        
        graph.add_tasks([task1, task2])
        
        assert graph.get_task("task-1") is not None
        assert graph.get_task("task-2") is not None
    
    def test_get_runnable_tasks(self):
        """测试获取可执行任务"""
        from core.multi_agent.scheduling.dependency_graph import DependencyGraph
        from core.multi_agent.fsm.states import SubTaskState
        
        graph = DependencyGraph()
        
        task1 = SubTaskState(id="task-1", action="任务1", specialization="research")
        task2 = SubTaskState(id="task-2", action="任务2", specialization="document", dependencies=["task-1"])
        
        graph.add_tasks([task1, task2])
        
        runnable = graph.get_runnable_tasks()
        
        # 只有 task-1 可执行
        assert len(runnable) == 1
        assert runnable[0].id == "task-1"
    
    def test_mark_completed(self):
        """测试标记完成"""
        from core.multi_agent.scheduling.dependency_graph import DependencyGraph
        from core.multi_agent.fsm.states import SubTaskState
        
        graph = DependencyGraph()
        
        task1 = SubTaskState(id="task-1", action="任务1", specialization="research")
        task2 = SubTaskState(id="task-2", action="任务2", specialization="document", dependencies=["task-1"])
        
        graph.add_tasks([task1, task2])
        graph.mark_completed("task-1")
        
        # task-2 现在可执行
        runnable = graph.get_runnable_tasks()
        assert len(runnable) == 1
        assert runnable[0].id == "task-2"
    
    def test_topological_sort(self):
        """测试拓扑排序"""
        from core.multi_agent.scheduling.dependency_graph import DependencyGraph
        from core.multi_agent.fsm.states import SubTaskState
        
        graph = DependencyGraph()
        
        task1 = SubTaskState(id="task-1", action="任务1", specialization="research")
        task2 = SubTaskState(id="task-2", action="任务2", specialization="document", dependencies=["task-1"])
        task3 = SubTaskState(id="task-3", action="任务3", specialization="code", dependencies=["task-2"])
        
        graph.add_tasks([task1, task2, task3])
        
        sorted_ids = graph.topological_sort()
        
        # task-1 应该在 task-2 之前，task-2 应该在 task-3 之前
        assert sorted_ids.index("task-1") < sorted_ids.index("task-2")
        assert sorted_ids.index("task-2") < sorted_ids.index("task-3")


class TestCircuitBreaker:
    """断路器测试"""
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_normal(self):
        """测试断路器正常情况"""
        from core.multi_agent.fault_tolerance.circuit_breaker import CircuitBreaker, CircuitState
        
        breaker = CircuitBreaker(name="test")
        
        async def success_func():
            return "success"
        
        result = await breaker.call(success_func)
        
        assert result == "success"
        assert breaker.state == CircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_open(self):
        """测试断路器打开"""
        from core.multi_agent.fault_tolerance.circuit_breaker import (
            CircuitBreaker,
            CircuitBreakerConfig,
            CircuitState,
            CircuitOpenError
        )
        
        breaker = CircuitBreaker(
            name="test",
            config=CircuitBreakerConfig(failure_threshold=2)
        )
        
        async def fail_func():
            raise Exception("fail")
        
        # 连续失败
        for _ in range(2):
            try:
                await breaker.call(fail_func)
            except Exception:
                pass
        
        # 断路器应该打开
        assert breaker.state == CircuitState.OPEN
        
        # 后续调用应该被拒绝
        with pytest.raises(CircuitOpenError):
            await breaker.call(fail_func)


class TestRetryPolicy:
    """重试策略测试"""
    
    @pytest.mark.asyncio
    async def test_retry_success(self):
        """测试重试成功"""
        from core.multi_agent.fault_tolerance.retry_policy import ExponentialBackoffRetry, ExponentialBackoffConfig
        
        retry = ExponentialBackoffRetry(
            config=ExponentialBackoffConfig(max_retries=3, base_delay=0.1)
        )
        
        call_count = 0
        
        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("transient error")
            return "success"
        
        result = await retry.execute(flaky_func)
        
        assert result == "success"
        assert call_count == 3
    
    @pytest.mark.asyncio
    async def test_retry_exhausted(self):
        """测试重试耗尽"""
        from core.multi_agent.fault_tolerance.retry_policy import (
            ExponentialBackoffRetry,
            ExponentialBackoffConfig,
            MaxRetriesExceededError
        )
        
        retry = ExponentialBackoffRetry(
            config=ExponentialBackoffConfig(max_retries=2, base_delay=0.1)
        )
        
        async def always_fail():
            raise Exception("permanent error")
        
        with pytest.raises(MaxRetriesExceededError):
            await retry.execute(always_fail)


class TestTaskDecomposer:
    """任务分解器测试"""
    
    @pytest.mark.asyncio
    async def test_fallback_decompose(self):
        """测试 Fallback 分解"""
        from core.multi_agent.decomposition.task_decomposer import TaskDecomposer
        
        decomposer = TaskDecomposer(llm_service=None)
        
        result = await decomposer.decompose("研究竞品的 AI 战略，生成分析报告")
        
        assert result.success
        assert len(result.sub_tasks) > 0


class TestMultiAgentConfig:
    """Multi-Agent 配置测试"""
    
    def test_default_config(self):
        """测试默认配置"""
        from core.multi_agent.config import MultiAgentConfig, MultiAgentMode
        
        config = MultiAgentConfig()
        
        assert config.mode == MultiAgentMode.AUTO
        assert config.max_parallel_workers == 5
    
    def test_config_from_dict(self):
        """测试从字典创建配置"""
        from core.multi_agent.config import MultiAgentConfig, MultiAgentMode
        
        data = {
            "mode": "enabled",
            "max_parallel_workers": 10,
            "workers": {
                "research": {"enabled": True, "max_instances": 5}
            }
        }
        
        config = MultiAgentConfig.from_dict(data)
        
        assert config.mode == MultiAgentMode.ENABLED
        assert config.max_parallel_workers == 10
        assert "research" in config.workers
        assert config.workers["research"].max_instances == 5
    
    def test_should_use_multi_agent(self):
        """测试自动判断"""
        from core.multi_agent.config import MultiAgentConfig, MultiAgentMode
        
        # AUTO 模式
        config = MultiAgentConfig(mode=MultiAgentMode.AUTO)
        
        # 包含关键词 + complex
        assert config.should_use_multi_agent("研究竞品战略", "complex")
        
        # 不包含关键词
        assert not config.should_use_multi_agent("你好", "simple")
        
        # DISABLED 模式
        config_disabled = MultiAgentConfig(mode=MultiAgentMode.DISABLED)
        assert not config_disabled.should_use_multi_agent("研究竞品战略", "complex")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
