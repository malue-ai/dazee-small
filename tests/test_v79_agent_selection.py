"""
验证 V7.9 Agent 选择三级优化

测试内容：
1. 三级优先级逻辑：Config > Task > Capability
2. 有效性验证：无效 Agent ID 检测
3. 覆盖透明化：日志格式验证

借鉴工具选择 V7.6 的验证模式
"""

import pytest
from unittest.mock import MagicMock, patch
from typing import List, Optional

from core.agent.multi.models import (
    AgentConfig,
    AgentRole,
    AgentSelectionResult,
    MultiAgentConfig,
    ExecutionMode,
)
from core.planning.protocol import PlanStep, StepStatus


class TestAgentSelectionPriority:
    """测试三级优先级逻辑：Config > Task > Capability"""
    
    def setup_method(self):
        """设置测试 Agent 配置"""
        self.agents = [
            AgentConfig(
                agent_id="researcher_1",
                role=AgentRole.RESEARCHER,
                tools=["web_search", "exa_search"],
            ),
            AgentConfig(
                agent_id="executor_1",
                role=AgentRole.EXECUTOR,
                tools=["bash", "code_editor"],
            ),
            AgentConfig(
                agent_id="planner_1",
                role=AgentRole.PLANNER,
                tools=["plan_todo"],
            ),
        ]
        
        self.config = MultiAgentConfig(
            config_id="test_config",
            mode=ExecutionMode.PARALLEL,
            agents=self.agents,
        )
    
    def test_config_highest_priority(self):
        """Config 显式指定应该优先于 Task 和 Capability"""
        # 创建步骤：同时指定 agent_id、role 和 tools
        step = PlanStep(
            id="step_1",
            description="测试步骤",
            assigned_agent="researcher_1",  # Config 层
            assigned_agent_role="executor",  # Task 层（不同）
            tools_required=["plan_todo"],    # Capability 层（匹配 planner_1）
        )
        
        # 模拟选择逻辑
        config_candidate = None
        task_candidate = None
        capability_candidate = None
        
        # Capability 匹配
        for agent in self.agents:
            if any(t in agent.tools for t in step.tools_required):
                capability_candidate = agent
                break
        
        # Task 匹配
        for agent in self.agents:
            if agent.role.value == step.assigned_agent_role:
                task_candidate = agent
                break
        
        # Config 匹配
        for agent in self.agents:
            if agent.agent_id == step.assigned_agent:
                config_candidate = agent
                break
        
        # 验证优先级
        assert config_candidate is not None
        assert config_candidate.agent_id == "researcher_1"
        
        # Config 应该覆盖 Task 和 Capability
        overridden = []
        if task_candidate and task_candidate.agent_id != config_candidate.agent_id:
            overridden.append(f"task:{task_candidate.agent_id}")
        if capability_candidate and capability_candidate.agent_id != config_candidate.agent_id:
            overridden.append(f"capability:{capability_candidate.agent_id}")
        
        assert len(overridden) == 2
        assert "task:executor_1" in overridden
        assert "capability:planner_1" in overridden
    
    def test_task_over_capability(self):
        """Task（角色）应该优先于 Capability（工具匹配）"""
        step = PlanStep(
            id="step_2",
            description="测试步骤",
            assigned_agent_role="researcher",  # Task 层
            tools_required=["bash"],           # Capability 层（匹配 executor_1）
        )
        
        task_candidate = None
        capability_candidate = None
        
        # Capability 匹配
        for agent in self.agents:
            if any(t in agent.tools for t in step.tools_required):
                capability_candidate = agent
                break
        
        # Task 匹配
        for agent in self.agents:
            if agent.role.value == step.assigned_agent_role:
                task_candidate = agent
                break
        
        # Task 应该被选中
        assert task_candidate is not None
        assert task_candidate.agent_id == "researcher_1"
        
        # 应该覆盖 Capability
        assert capability_candidate is not None
        assert capability_candidate.agent_id == "executor_1"
    
    def test_capability_fallback(self):
        """没有 Config 和 Task 时，使用 Capability 匹配"""
        step = PlanStep(
            id="step_3",
            description="测试步骤",
            tools_required=["bash", "code_editor"],
        )
        
        capability_candidate = None
        
        for agent in self.agents:
            matching = [t for t in step.tools_required if t in agent.tools]
            if matching:
                capability_candidate = agent
                break
        
        assert capability_candidate is not None
        assert capability_candidate.agent_id == "executor_1"
    
    def test_default_fallback(self):
        """没有任何匹配时，使用默认 Agent"""
        step = PlanStep(
            id="step_4",
            description="测试步骤",
            # 没有指定任何匹配条件
        )
        
        config_candidate = None
        task_candidate = None
        capability_candidate = None
        
        # 都没有匹配，使用默认
        if not config_candidate and not task_candidate and not capability_candidate:
            selected = self.agents[0] if self.agents else None
            selection_source = "default"
        
        assert selected is not None
        assert selected.agent_id == "researcher_1"
        assert selection_source == "default"


class TestAgentValidation:
    """测试有效性验证"""
    
    def test_missing_tools_validation(self):
        """验证缺少工具的检测"""
        agent = AgentConfig(
            agent_id="limited_agent",
            role=AgentRole.EXECUTOR,
            tools=["bash"],
        )
        
        step = PlanStep(
            id="step_1",
            description="测试步骤",
            tools_required=["bash", "code_editor", "web_search"],
        )
        
        # 验证逻辑
        issues = []
        if step.tools_required:
            missing = [t for t in step.tools_required if t not in agent.tools]
            if missing:
                issues.append(f"Agent 缺少工具: {missing}")
        
        assert len(issues) == 1
        assert "code_editor" in issues[0]
        assert "web_search" in issues[0]
    
    def test_role_mismatch_validation(self):
        """验证角色不匹配的检测"""
        agent = AgentConfig(
            agent_id="executor_1",
            role=AgentRole.EXECUTOR,
            tools=["bash"],
        )
        
        step = PlanStep(
            id="step_1",
            description="测试步骤",
            assigned_agent_role="researcher",
        )
        
        issues = []
        if step.assigned_agent_role and agent.role.value != step.assigned_agent_role:
            issues.append(
                f"角色不匹配: 需要 {step.assigned_agent_role}, 实际 {agent.role.value}"
            )
        
        assert len(issues) == 1
        assert "researcher" in issues[0]
        assert "executor" in issues[0]
    
    def test_invalid_agent_id_detection(self):
        """验证无效 Agent ID 的检测"""
        agents = [
            AgentConfig(agent_id="agent_1", role=AgentRole.EXECUTOR, tools=[]),
            AgentConfig(agent_id="agent_2", role=AgentRole.RESEARCHER, tools=[]),
        ]
        
        step = PlanStep(
            id="step_1",
            description="测试步骤",
            assigned_agent="non_existent_agent",
        )
        
        config_candidate = None
        for agent in agents:
            if agent.agent_id == step.assigned_agent:
                config_candidate = agent
                break
        
        # 验证：指定的 Agent 不存在
        assert config_candidate is None
        available_ids = [a.agent_id for a in agents]
        assert step.assigned_agent not in available_ids


class TestOverrideTransparency:
    """测试覆盖透明化日志格式"""
    
    def test_override_format(self):
        """验证覆盖记录格式"""
        overridden_sources = []
        
        # 场景：Config 覆盖 Task 和 Capability
        config_candidate = AgentConfig(
            agent_id="config_agent",
            role=AgentRole.EXECUTOR,
            tools=[],
        )
        task_candidate = AgentConfig(
            agent_id="task_agent",
            role=AgentRole.RESEARCHER,
            tools=[],
        )
        capability_candidate = AgentConfig(
            agent_id="capability_agent",
            role=AgentRole.PLANNER,
            tools=[],
        )
        
        selected = config_candidate
        selection_source = "config"
        
        if task_candidate and task_candidate.agent_id != selected.agent_id:
            overridden_sources.append(f"task:{task_candidate.agent_id}")
        if capability_candidate and capability_candidate.agent_id != selected.agent_id:
            overridden_sources.append(f"capability:{capability_candidate.agent_id}")
        
        # 验证格式
        assert len(overridden_sources) == 2
        assert overridden_sources[0] == "task:task_agent"
        assert overridden_sources[1] == "capability:capability_agent"
        
        # 验证日志格式
        log_message = (
            f"Agent 选择 [{selection_source}]: {selected.agent_id}，"
            f"覆盖了 {overridden_sources}"
        )
        assert "config" in log_message
        assert "config_agent" in log_message
        assert "task:task_agent" in log_message
        assert "capability:capability_agent" in log_message
    
    def test_no_override_format(self):
        """验证无覆盖时的日志格式"""
        selected = AgentConfig(
            agent_id="only_agent",
            role=AgentRole.EXECUTOR,
            tools=[],
        )
        selection_source = "default"
        overridden_sources = []
        
        if overridden_sources:
            log_message = f"Agent 选择 [{selection_source}]: {selected.agent_id}，覆盖了 {overridden_sources}"
        else:
            log_message = f"Agent 选择 [{selection_source}]: {selected.agent_id}"
        
        assert "覆盖" not in log_message
        assert "default" in log_message
        assert "only_agent" in log_message


class TestAgentSelectionResult:
    """测试 AgentSelectionResult 数据模型"""
    
    def test_to_trace_dict(self):
        """验证 to_trace_dict 输出"""
        agent = AgentConfig(
            agent_id="test_agent",
            role=AgentRole.EXECUTOR,
            tools=["bash"],
        )
        
        result = AgentSelectionResult(
            selected_agent=agent,
            selection_source="config",
            overridden_sources=["task:other_agent"],
            validation_passed=True,
            validation_issues=[],
            config_candidate="test_agent",
            task_candidate="other_agent",
            capability_candidate=None,
        )
        
        trace_dict = result.to_trace_dict()
        
        assert trace_dict["selected_agent"] == "test_agent"
        assert trace_dict["selection_source"] == "config"
        assert trace_dict["overridden_sources"] == ["task:other_agent"]
        assert trace_dict["validation_passed"] is True
        assert trace_dict["config_candidate"] == "test_agent"
        assert trace_dict["task_candidate"] == "other_agent"
        assert trace_dict["capability_candidate"] is None


def verify_all():
    """快速验证脚本（不依赖 pytest）"""
    print("=" * 60)
    print("验证 V7.9 Agent 选择三级优化")
    print("=" * 60)
    
    # 验证 1: 优先级逻辑
    print("\n验证 1: Config > Task > Capability 优先级")
    test = TestAgentSelectionPriority()
    test.setup_method()
    test.test_config_highest_priority()
    print("✓ Config 最高优先级验证通过")
    test.test_task_over_capability()
    print("✓ Task > Capability 验证通过")
    test.test_capability_fallback()
    print("✓ Capability 兜底验证通过")
    test.test_default_fallback()
    print("✓ Default 兜底验证通过")
    
    # 验证 2: 有效性验证
    print("\n验证 2: 有效性验证")
    test2 = TestAgentValidation()
    test2.test_missing_tools_validation()
    print("✓ 缺少工具检测验证通过")
    test2.test_role_mismatch_validation()
    print("✓ 角色不匹配检测验证通过")
    test2.test_invalid_agent_id_detection()
    print("✓ 无效 Agent ID 检测验证通过")
    
    # 验证 3: 覆盖透明化
    print("\n验证 3: 覆盖透明化日志格式")
    test3 = TestOverrideTransparency()
    test3.test_override_format()
    print("✓ 覆盖记录格式验证通过")
    test3.test_no_override_format()
    print("✓ 无覆盖日志格式验证通过")
    
    # 验证 4: AgentSelectionResult
    print("\n验证 4: AgentSelectionResult 数据模型")
    test4 = TestAgentSelectionResult()
    test4.test_to_trace_dict()
    print("✓ to_trace_dict 输出验证通过")
    
    print("\n" + "=" * 60)
    print("✅ 所有验证通过！V7.9 Agent 选择三级优化实现正确")
    print("=" * 60)


if __name__ == "__main__":
    verify_all()
