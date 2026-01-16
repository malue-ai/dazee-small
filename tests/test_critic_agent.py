"""
Critic Agent 测试用例

V7.2 新增：测试 Critic Agent 的评估功能和人机协同

设计原则：
- Critic 是顾问，不是裁判
- 提供观察和建议，不做硬编码评分
- 测试 confidence 和 auto_execute 逻辑
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from core.agent.multi.critic import CriticAgent
from core.agent.multi.models import (
    CriticResult,
    CriticAction,
    CriticConfidence,
    CriticConfig,
    PlanAdjustmentHint,
)
from core.planning.protocol import PlanStep, StepStatus


class TestCriticAgent:
    """Critic Agent 测试类"""
    
    @pytest.fixture
    def critic_agent(self):
        """创建 CriticAgent 实例"""
        config = CriticConfig(
            enabled=True,
            model="claude-sonnet-4-5-20250929",
            enable_thinking=True,
            max_retries=2,
            auto_pass_on_high_confidence=True,
            require_human_on_low_confidence=True,
        )
        return CriticAgent(config=config)
    
    @pytest.fixture
    def plan_step(self):
        """创建 PlanStep 实例"""
        return PlanStep(
            id="step_1",
            description="分析竞品定价和功能",
            status=StepStatus.IN_PROGRESS,
            metadata={
                "success_criteria": [
                    "包含至少3个竞品",
                    "包含定价信息",
                    "包含功能对比"
                ]
            }
        )
    
    @pytest.mark.asyncio
    async def test_critique_pass_high_confidence(self, critic_agent, plan_step):
        """测试：高质量输出 -> Critic pass（高信心）"""
        mock_response = Mock()
        mock_response.content = """```json
{
  "observations": [
    "输出包含了3个竞品的定价信息",
    "每个竞品都有功能对比",
    "信息结构清晰"
  ],
  "gaps": [],
  "root_cause": null,
  "suggestions": [],
  "recommended_action": "pass",
  "reasoning": "输出完整覆盖了所有成功标准",
  "confidence": "high"
}
```"""
        
        with patch.object(critic_agent.llm, 'create_message_async', return_value=mock_response):
            result = await critic_agent.critique(
                executor_output="竞品A定价$99/月...(完整信息)",
                plan_step=plan_step,
            )
            
            assert result.recommended_action == CriticAction.PASS
            assert result.confidence == CriticConfidence.HIGH
            assert len(result.gaps) == 0
            assert critic_agent.should_auto_execute(result) is True
    
    @pytest.mark.asyncio
    async def test_critique_retry_medium_confidence(self, critic_agent, plan_step):
        """测试：有差距 -> Critic retry（中等信心）"""
        mock_response = Mock()
        mock_response.content = """```json
{
  "observations": [
    "输出包含了2个竞品的定价",
    "缺少第3个竞品"
  ],
  "gaps": [
    "缺少竞品C的信息",
    "功能对比不完整"
  ],
  "root_cause": "搜索范围可能不够广",
  "suggestions": [
    "搜索 '竞品C 定价'",
    "对比3个竞品的核心功能差异"
  ],
  "recommended_action": "retry",
  "reasoning": "核心信息已有，但缺少部分数据，值得重试补充",
  "confidence": "medium"
}
```"""
        
        with patch.object(critic_agent.llm, 'create_message_async', return_value=mock_response):
            result = await critic_agent.critique(
                executor_output="竞品A定价$99，竞品B定价$149",
                plan_step=plan_step,
            )
            
            assert result.recommended_action == CriticAction.RETRY
            assert result.confidence == CriticConfidence.MEDIUM
            assert len(result.gaps) > 0
            assert len(result.suggestions) > 0
            # 中等信心不应自动执行
            assert critic_agent.should_auto_execute(result) is False
    
    @pytest.mark.asyncio
    async def test_critique_ask_human_low_confidence(self, critic_agent, plan_step):
        """测试：无法判断 -> ask_human（低信心）"""
        mock_response = Mock()
        mock_response.content = """```json
{
  "observations": [
    "输出是一段代码实现",
    "无法从文本判断代码正确性"
  ],
  "gaps": [],
  "root_cause": "需要运行测试才能验证",
  "suggestions": [
    "运行单元测试验证功能",
    "人工 review 代码逻辑"
  ],
  "recommended_action": "ask_human",
  "reasoning": "代码的正确性需要人工或测试验证，Critic 无法仅从文本判断",
  "confidence": "low"
}
```"""
        
        with patch.object(critic_agent.llm, 'create_message_async', return_value=mock_response):
            result = await critic_agent.critique(
                executor_output="def calculate(x): return x * 2",
                plan_step=plan_step,
            )
            
            assert result.recommended_action == CriticAction.ASK_HUMAN
            assert result.confidence == CriticConfidence.LOW
            # 低信心必须人工介入
            assert critic_agent.should_auto_execute(result) is False
    
    @pytest.mark.asyncio
    async def test_critique_replan_direction_error(self, critic_agent, plan_step):
        """测试：方向错误 -> replan"""
        mock_response = Mock()
        mock_response.content = """```json
{
  "observations": [
    "输出只包含了价格数字",
    "缺少分析维度定义"
  ],
  "gaps": [
    "不清楚需要从哪些维度分析",
    "任务描述不够明确"
  ],
  "root_cause": "任务定义缺少分析维度",
  "suggestions": [],
  "recommended_action": "replan",
  "reasoning": "任务缺少明确的分析维度，需要先与用户确认",
  "confidence": "high",
  "plan_adjustment": {
    "action": "insert_before",
    "reason": "需要先确定分析维度",
    "new_step": "与用户确认分析维度（价格/功能/市场）",
    "context_for_replan": "当前任务缺少分析维度定义"
  }
}
```"""
        
        with patch.object(critic_agent.llm, 'create_message_async', return_value=mock_response):
            result = await critic_agent.critique(
                executor_output="竞品A: $99, 竞品B: $149",
                plan_step=plan_step,
            )
            
            assert result.recommended_action == CriticAction.REPLAN
            assert result.plan_adjustment is not None
            assert result.plan_adjustment.action == "insert_before"
    
    def test_should_auto_execute_high_confidence(self, critic_agent):
        """测试：高信心 + 配置允许 -> 自动执行"""
        result = CriticResult(
            observations=["完整"],
            gaps=[],
            suggestions=[],
            recommended_action=CriticAction.PASS,
            reasoning="完成",
            confidence=CriticConfidence.HIGH,
        )
        
        assert critic_agent.should_auto_execute(result) is True
    
    def test_should_auto_execute_low_confidence(self, critic_agent):
        """测试：低信心 -> 不自动执行"""
        result = CriticResult(
            observations=["无法判断"],
            gaps=[],
            suggestions=["人工检查"],
            recommended_action=CriticAction.RETRY,
            reasoning="信心不足",
            confidence=CriticConfidence.LOW,
        )
        
        assert critic_agent.should_auto_execute(result) is False
    
    def test_parse_critique_response_with_markdown(self, critic_agent):
        """测试：解析包含 markdown 代码块的响应"""
        response_text = """```json
{
  "observations": ["测试观察"],
  "gaps": [],
  "suggestions": [],
  "recommended_action": "pass",
  "reasoning": "测试",
  "confidence": "high"
}
```"""
        
        result = critic_agent._parse_critique_response(response_text)
        
        assert result.recommended_action == CriticAction.PASS
        assert result.confidence == CriticConfidence.HIGH
    
    def test_parse_critique_response_invalid_json(self, critic_agent):
        """测试：解析无效 JSON -> 返回 ask_human"""
        response_text = "这不是 JSON 格式"
        
        result = critic_agent._parse_critique_response(response_text)
        
        assert result.recommended_action == CriticAction.ASK_HUMAN
        assert result.confidence == CriticConfidence.LOW
        assert "无法解析" in result.reasoning


class TestCriticOrchestratorIntegration:
    """Critic 与 Orchestrator 集成测试"""
    
    @pytest.mark.asyncio
    async def test_execute_step_with_critique_pass(self):
        """测试：执行步骤 -> Critic pass -> 继续"""
        from core.agent.multi.orchestrator import MultiAgentOrchestrator
        from core.agent.multi.models import (
            MultiAgentConfig,
            AgentConfig,
            AgentRole,
            CriticConfig,
        )
        
        config = MultiAgentConfig(
            config_id="test_config",
            agents=[
                AgentConfig(
                    agent_id="agent_1",
                    role=AgentRole.EXECUTOR,
                )
            ],
            critic_config=CriticConfig(
                enabled=True,
                max_retries=2,
                auto_pass_on_high_confidence=True,
            ),
        )
        
        orchestrator = MultiAgentOrchestrator(config=config)
        
        # Mock Critic 返回 pass（高信心）
        mock_critic_result = CriticResult(
            observations=["输出完整"],
            gaps=[],
            suggestions=[],
            recommended_action=CriticAction.PASS,
            reasoning="满足需求",
            confidence=CriticConfidence.HIGH,
        )
        
        with patch.object(orchestrator.critic, 'critique', return_value=mock_critic_result):
            from core.agent.multi.models import AgentResult
            mock_result = AgentResult(
                result_id="result_1",
                agent_id="agent_1",
                success=True,
                output="完整输出",
            )
            
            with patch.object(orchestrator, '_execute_single_agent', return_value=mock_result):
                result = await orchestrator._execute_step_with_critique(
                    agent_config=config.agents[0],
                    subtask=None,
                    messages=[],
                    previous_output=None,
                    session_id="test_session",
                )
                
                assert result.success is True
                assert result.output == "完整输出"
    
    @pytest.mark.asyncio
    async def test_execute_step_with_critique_ask_human(self):
        """测试：执行步骤 -> Critic ask_human -> 标记需要人工审核"""
        from core.agent.multi.orchestrator import MultiAgentOrchestrator
        from core.agent.multi.models import (
            MultiAgentConfig,
            AgentConfig,
            AgentRole,
            CriticConfig,
        )
        
        config = MultiAgentConfig(
            config_id="test_config",
            agents=[
                AgentConfig(
                    agent_id="agent_1",
                    role=AgentRole.EXECUTOR,
                )
            ],
            critic_config=CriticConfig(enabled=True),
        )
        
        orchestrator = MultiAgentOrchestrator(config=config)
        
        # Mock Critic 返回 ask_human
        mock_critic_result = CriticResult(
            observations=["无法判断"],
            gaps=[],
            suggestions=["人工检查"],
            recommended_action=CriticAction.ASK_HUMAN,
            reasoning="需要人工验证",
            confidence=CriticConfidence.LOW,
        )
        
        with patch.object(orchestrator.critic, 'critique', return_value=mock_critic_result):
            from core.agent.multi.models import AgentResult
            mock_result = AgentResult(
                result_id="result_1",
                agent_id="agent_1",
                success=True,
                output="输出内容",
            )
            
            with patch.object(orchestrator, '_execute_single_agent', return_value=mock_result):
                result = await orchestrator._execute_step_with_critique(
                    agent_config=config.agents[0],
                    subtask=None,
                    messages=[],
                    previous_output=None,
                    session_id="test_session",
                )
                
                # 结果应该标记需要人工审核
                assert result.metadata.get("needs_human_review") is True
                assert "critic_result" in result.metadata


class TestCriticHumanInTheLoop:
    """人机协同测试"""
    
    def test_confidence_determines_auto_execute(self):
        """测试：信心程度决定是否自动执行"""
        config = CriticConfig(
            enabled=True,
            auto_pass_on_high_confidence=True,
            require_human_on_low_confidence=True,
        )
        critic = CriticAgent(config=config)
        
        # 高信心 -> 可自动执行
        high_conf_result = CriticResult(
            observations=["完整"],
            gaps=[],
            suggestions=[],
            recommended_action=CriticAction.PASS,
            reasoning="完成",
            confidence=CriticConfidence.HIGH,
        )
        assert critic.should_auto_execute(high_conf_result) is True
        
        # 中信心 -> 不自动执行（需要确认）
        medium_conf_result = CriticResult(
            observations=["部分"],
            gaps=["缺少"],
            suggestions=["补充"],
            recommended_action=CriticAction.RETRY,
            reasoning="建议重试",
            confidence=CriticConfidence.MEDIUM,
        )
        assert critic.should_auto_execute(medium_conf_result) is False
        
        # 低信心 -> 不自动执行（必须人工）
        low_conf_result = CriticResult(
            observations=["无法判断"],
            gaps=[],
            suggestions=["人工检查"],
            recommended_action=CriticAction.ASK_HUMAN,
            reasoning="需要人工",
            confidence=CriticConfidence.LOW,
        )
        assert critic.should_auto_execute(low_conf_result) is False
