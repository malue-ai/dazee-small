"""
奖励归因模块

V8.0 新增
V9.4 增强：支持数据库持久化

职责：
- 细粒度步骤级奖励归因
- 识别成功/失败的关键步骤
- 为策略优化提供数据支持
- 🆕 V9.4: 持久化存储支持

设计原则：
- 从会话级评估到步骤级评估
- 支持多种归因策略
- 可与人工评审结合

持久化配置（V9.4）：
    export REWARD_PERSIST_ENABLED=true  # 启用持久化
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime

from logger import get_logger

logger = get_logger(__name__)


class RewardSignal(Enum):
    """奖励信号类型"""
    POSITIVE = "positive"      # 正向奖励
    NEGATIVE = "negative"      # 负向奖励
    NEUTRAL = "neutral"        # 中性


class AttributionMethod(Enum):
    """归因方法"""
    DIRECT = "direct"                    # 直接归因
    TEMPORAL_DIFFERENCE = "td"           # 时序差分
    MONTE_CARLO = "monte_carlo"          # 蒙特卡洛
    ADVANTAGE = "advantage"              # 优势函数


@dataclass
class StepReward:
    """步骤级奖励"""
    step_id: str
    step_index: int
    action_type: str                     # tool_call, plan_create, response
    action_name: str                     # 具体动作名称
    
    # 奖励信号
    signal: RewardSignal = RewardSignal.NEUTRAL
    reward_value: float = 0.0            # -1.0 到 1.0
    
    # 归因信息
    attribution_method: AttributionMethod = AttributionMethod.DIRECT
    confidence: float = 0.5              # 归因置信度
    
    # 执行信息
    success: bool = True
    execution_time_ms: int = 0
    error: Optional[str] = None
    
    # 上下文
    input_summary: Optional[str] = None
    output_summary: Optional[str] = None
    
    # 关键性评估
    is_critical: bool = False            # 是否是关键步骤
    impact_on_outcome: float = 0.0       # 对最终结果的影响 0-1
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "step_index": self.step_index,
            "action_type": self.action_type,
            "action_name": self.action_name,
            "signal": self.signal.value,
            "reward_value": self.reward_value,
            "attribution_method": self.attribution_method.value,
            "confidence": self.confidence,
            "success": self.success,
            "is_critical": self.is_critical,
            "impact_on_outcome": self.impact_on_outcome,
        }


@dataclass
class SessionReward:
    """会话级奖励"""
    session_id: str
    conversation_id: Optional[str] = None
    user_id: Optional[str] = None
    
    # 总体奖励
    total_reward: float = 0.0
    outcome_success: bool = True
    
    # 步骤奖励
    step_rewards: List[StepReward] = field(default_factory=list)
    
    # 统计信息
    total_steps: int = 0
    successful_steps: int = 0
    failed_steps: int = 0
    critical_steps: int = 0
    
    # 时间信息
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    total_duration_ms: int = 0
    
    # 评估来源
    evaluated_by: str = "auto"           # auto, human, hybrid
    evaluator_notes: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "conversation_id": self.conversation_id,
            "total_reward": self.total_reward,
            "outcome_success": self.outcome_success,
            "total_steps": self.total_steps,
            "successful_steps": self.successful_steps,
            "failed_steps": self.failed_steps,
            "critical_steps": self.critical_steps,
            "total_duration_ms": self.total_duration_ms,
            "evaluated_by": self.evaluated_by,
            "step_rewards": [s.to_dict() for s in self.step_rewards],
        }
    
    def get_critical_steps(self) -> List[StepReward]:
        """获取关键步骤"""
        return [s for s in self.step_rewards if s.is_critical]
    
    def get_failed_steps(self) -> List[StepReward]:
        """获取失败步骤"""
        return [s for s in self.step_rewards if not s.success]


class RewardAttribution:
    """
    奖励归因器
    
    功能：
    1. 收集执行步骤
    2. 计算步骤级奖励
    3. 识别关键步骤
    4. 支持多种归因方法
    
    使用方式：
        attribution = RewardAttribution()
        
        # 记录步骤
        attribution.record_step(
            session_id="...",
            step_id="step_1",
            action_type="tool_call",
            action_name="web_search",
            success=True,
            output="..."
        )
        
        # 完成会话评估
        session_reward = attribution.evaluate_session(
            session_id="...",
            outcome_success=True
        )
    """
    
    def __init__(
        self,
        llm_service: Any = None,
        default_method: AttributionMethod = AttributionMethod.DIRECT,
        persist_enabled: bool = None,  # 🆕 V9.4: 持久化开关
    ):
        """
        初始化奖励归因器
        
        Args:
            llm_service: LLM 服务（用于自动评估）
            default_method: 默认归因方法
            persist_enabled: 是否启用持久化（默认从环境变量读取）
        """
        import os
        
        self.llm_service = llm_service
        self.default_method = default_method
        
        # 🆕 V9.4: 持久化配置
        if persist_enabled is None:
            persist_enabled = os.getenv("REWARD_PERSIST_ENABLED", "false").lower() == "true"
        self.persist_enabled = persist_enabled
        
        # 会话数据
        self._sessions: Dict[str, SessionReward] = {}
        self._step_buffer: Dict[str, List[Dict[str, Any]]] = {}
        
        logger.info(
            f"✅ RewardAttribution 初始化: method={default_method.value}, "
            f"persist={persist_enabled}"
        )
    
    def start_session(
        self,
        session_id: str,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> SessionReward:
        """
        开始新会话
        
        Args:
            session_id: 会话 ID
            conversation_id: 对话 ID
            user_id: 用户 ID
            
        Returns:
            SessionReward: 会话奖励对象
        """
        session = SessionReward(
            session_id=session_id,
            conversation_id=conversation_id,
            user_id=user_id,
            start_time=datetime.now(),
        )
        
        self._sessions[session_id] = session
        self._step_buffer[session_id] = []
        
        logger.debug(f"📊 开始会话评估: {session_id}")
        return session
    
    def record_step(
        self,
        session_id: str,
        step_id: str,
        action_type: str,
        action_name: str,
        success: bool = True,
        execution_time_ms: int = 0,
        input_data: Any = None,
        output_data: Any = None,
        error: Optional[str] = None,
    ):
        """
        记录执行步骤
        
        Args:
            session_id: 会话 ID
            step_id: 步骤 ID
            action_type: 动作类型
            action_name: 动作名称
            success: 是否成功
            execution_time_ms: 执行时间
            input_data: 输入数据
            output_data: 输出数据
            error: 错误信息
        """
        if session_id not in self._step_buffer:
            self._step_buffer[session_id] = []
        
        step_index = len(self._step_buffer[session_id])
        
        step_data = {
            "step_id": step_id,
            "step_index": step_index,
            "action_type": action_type,
            "action_name": action_name,
            "success": success,
            "execution_time_ms": execution_time_ms,
            "input_summary": self._summarize(input_data),
            "output_summary": self._summarize(output_data),
            "error": error,
            "timestamp": datetime.now(),
        }
        
        self._step_buffer[session_id].append(step_data)
        
        logger.debug(
            f"📝 记录步骤: {session_id}/{step_id} - "
            f"{action_type}:{action_name} ({'✅' if success else '❌'})"
        )
    
    async def evaluate_session(
        self,
        session_id: str,
        outcome_success: bool,
        user_feedback: Optional[str] = None,
        use_llm: bool = True,
    ) -> SessionReward:
        """
        评估会话
        
        Args:
            session_id: 会话 ID
            outcome_success: 最终结果是否成功
            user_feedback: 用户反馈
            use_llm: 是否使用 LLM 辅助评估
            
        Returns:
            SessionReward: 会话奖励
        """
        session = self._sessions.get(session_id)
        if not session:
            session = SessionReward(session_id=session_id)
            self._sessions[session_id] = session
        
        session.end_time = datetime.now()
        session.outcome_success = outcome_success
        
        if session.start_time:
            session.total_duration_ms = int(
                (session.end_time - session.start_time).total_seconds() * 1000
            )
        
        # 获取步骤数据
        steps = self._step_buffer.get(session_id, [])
        session.total_steps = len(steps)
        
        # 计算步骤奖励
        step_rewards = await self._compute_step_rewards(
            steps=steps,
            outcome_success=outcome_success,
            user_feedback=user_feedback,
            use_llm=use_llm,
        )
        
        session.step_rewards = step_rewards
        session.successful_steps = sum(1 for s in step_rewards if s.success)
        session.failed_steps = sum(1 for s in step_rewards if not s.success)
        session.critical_steps = sum(1 for s in step_rewards if s.is_critical)
        
        # 计算总奖励
        session.total_reward = self._compute_total_reward(
            step_rewards=step_rewards,
            outcome_success=outcome_success,
        )
        
        session.evaluated_by = "auto" if use_llm else "rule"
        
        logger.info(
            f"✅ 会话评估完成: {session_id}, "
            f"reward={session.total_reward:.2f}, "
            f"success={outcome_success}, "
            f"steps={session.total_steps}"
        )
        
        # 🆕 V9.4: 持久化存储
        if self.persist_enabled:
            try:
                await self.persist_session(session)
            except Exception as e:
                logger.warning(f"⚠️ 会话奖励持久化失败: {e}")
        
        return session
    
    async def persist_session(self, session: SessionReward) -> bool:
        """
        🆕 V9.4: 持久化会话奖励到数据库
        
        Args:
            session: 会话奖励对象
            
        Returns:
            是否成功
        """
        try:
            from infra.database import AsyncSessionLocal
            from infra.database.crud.continuous_learning import (
                create_session_reward,
                create_step_rewards_batch,
            )
            from infra.database.models.continuous_learning import (
                AttributionMethod as DBAttributionMethod,
            )
            
            async with AsyncSessionLocal() as db_session:
                # 映射归因方法
                method_mapping = {
                    AttributionMethod.DIRECT: DBAttributionMethod.UNIFORM,
                    AttributionMethod.TEMPORAL_DIFFERENCE: DBAttributionMethod.DECAY,
                    AttributionMethod.MONTE_CARLO: DBAttributionMethod.LLM_JUDGE,
                    AttributionMethod.ADVANTAGE: DBAttributionMethod.ADVANTAGE,
                }
                db_method = method_mapping.get(
                    self.default_method, DBAttributionMethod.DECAY
                )
                
                # 创建会话奖励记录
                record = await create_session_reward(
                    session=db_session,
                    session_id=session.session_id,
                    total_reward=session.total_reward,
                    outcome_success=session.outcome_success,
                    attribution_method=db_method,
                    conversation_id=session.conversation_id,
                    user_id=session.user_id,
                    total_steps=session.total_steps,
                    successful_steps=session.successful_steps,
                    failed_steps=session.failed_steps,
                    critical_steps=session.critical_steps,
                    session_start=session.start_time,
                    session_end=session.end_time,
                    total_duration_ms=session.total_duration_ms,
                    evaluated_by=session.evaluated_by,
                    evaluator_notes=session.evaluator_notes,
                )
                
                # 创建步骤奖励记录
                if session.step_rewards:
                    steps_data = []
                    for step in session.step_rewards:
                        steps_data.append({
                            "step_index": step.step_index,
                            "action_type": step.action_type,
                            "action_name": step.action_name,
                            "reward_value": step.reward_value,
                            "success": step.success,
                            "execution_time_ms": step.execution_time_ms,
                            "error_message": step.error,
                            "is_critical": step.is_critical,
                            "impact_on_outcome": step.impact_on_outcome,
                            "input_summary": step.input_summary,
                            "output_summary": step.output_summary,
                            "contribution_weight": step.contribution_weight,
                            "confidence": step.confidence,
                        })
                    
                    await create_step_rewards_batch(
                        session=db_session,
                        session_reward_id=record.id,
                        steps=steps_data
                    )
                
                logger.info(f"💾 会话奖励已持久化: {session.session_id}")
                return True
                
        except ImportError as e:
            logger.warning(f"⚠️ 数据库模块未安装: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ 持久化失败: {e}", exc_info=True)
            return False
    
    async def _compute_step_rewards(
        self,
        steps: List[Dict[str, Any]],
        outcome_success: bool,
        user_feedback: Optional[str],
        use_llm: bool,
    ) -> List[StepReward]:
        """计算步骤奖励"""
        step_rewards = []
        
        for step_data in steps:
            # 基础奖励计算
            reward = self._compute_basic_reward(step_data, outcome_success)
            
            # 识别关键步骤
            is_critical = self._is_critical_step(step_data, steps)
            
            # 计算对结果的影响
            impact = self._compute_impact(step_data, steps, outcome_success)
            
            step_reward = StepReward(
                step_id=step_data["step_id"],
                step_index=step_data["step_index"],
                action_type=step_data["action_type"],
                action_name=step_data["action_name"],
                signal=RewardSignal.POSITIVE if reward > 0 else (
                    RewardSignal.NEGATIVE if reward < 0 else RewardSignal.NEUTRAL
                ),
                reward_value=reward,
                attribution_method=self.default_method,
                confidence=0.7 if use_llm else 0.5,
                success=step_data["success"],
                execution_time_ms=step_data["execution_time_ms"],
                error=step_data.get("error"),
                input_summary=step_data.get("input_summary"),
                output_summary=step_data.get("output_summary"),
                is_critical=is_critical,
                impact_on_outcome=impact,
            )
            
            step_rewards.append(step_reward)
        
        # 使用 LLM 增强评估
        if use_llm and self.llm_service and len(step_rewards) > 0:
            step_rewards = await self._enhance_with_llm(
                step_rewards, outcome_success, user_feedback
            )
        
        return step_rewards
    
    def _compute_basic_reward(
        self,
        step_data: Dict[str, Any],
        outcome_success: bool
    ) -> float:
        """计算基础奖励"""
        reward = 0.0
        
        # 成功/失败基础分
        if step_data["success"]:
            reward += 0.5
        else:
            reward -= 0.5
        
        # 根据动作类型调整
        action_type = step_data["action_type"]
        if action_type == "tool_call":
            # 工具调用权重
            reward *= 1.2
        elif action_type == "plan_create":
            # Plan 创建权重（影响较大）
            reward *= 1.5
        
        # 根据最终结果调整
        if outcome_success:
            reward *= 1.2 if reward > 0 else 0.8
        else:
            reward *= 0.8 if reward > 0 else 1.2
        
        # 限制在 [-1, 1] 范围
        return max(-1.0, min(1.0, reward))
    
    def _is_critical_step(
        self,
        step_data: Dict[str, Any],
        all_steps: List[Dict[str, Any]]
    ) -> bool:
        """判断是否是关键步骤"""
        # 规则 1：Plan 创建总是关键
        if step_data["action_type"] == "plan_create":
            return True
        
        # 规则 2：第一个和最后一个步骤
        if step_data["step_index"] == 0 or step_data["step_index"] == len(all_steps) - 1:
            return True
        
        # 规则 3：失败的步骤（可能导致问题）
        if not step_data["success"]:
            return True
        
        # 规则 4：某些关键工具
        critical_tools = {"plan_todo", "request_human_confirmation"}
        if step_data["action_name"] in critical_tools:
            return True
        
        return False
    
    def _compute_impact(
        self,
        step_data: Dict[str, Any],
        all_steps: List[Dict[str, Any]],
        outcome_success: bool
    ) -> float:
        """计算对最终结果的影响"""
        total_steps = len(all_steps)
        if total_steps == 0:
            return 0.0
        
        step_index = step_data["step_index"]
        
        # 基础影响（越靠后影响越大）
        position_weight = (step_index + 1) / total_steps
        
        # 关键步骤加权
        if self._is_critical_step(step_data, all_steps):
            position_weight *= 1.5
        
        # 失败步骤
        if not step_data["success"]:
            if not outcome_success:
                position_weight *= 2.0  # 失败的会话中，失败步骤影响更大
        
        return min(1.0, position_weight)
    
    def _compute_total_reward(
        self,
        step_rewards: List[StepReward],
        outcome_success: bool
    ) -> float:
        """计算总奖励"""
        if not step_rewards:
            return 1.0 if outcome_success else -1.0
        
        # 加权平均
        total = 0.0
        weight_sum = 0.0
        
        for step in step_rewards:
            weight = 1.0 + step.impact_on_outcome
            total += step.reward_value * weight
            weight_sum += weight
        
        avg_reward = total / weight_sum if weight_sum > 0 else 0.0
        
        # 结果加成
        if outcome_success:
            avg_reward = avg_reward * 0.7 + 0.3
        else:
            avg_reward = avg_reward * 0.7 - 0.3
        
        return max(-1.0, min(1.0, avg_reward))
    
    async def _enhance_with_llm(
        self,
        step_rewards: List[StepReward],
        outcome_success: bool,
        user_feedback: Optional[str],
    ) -> List[StepReward]:
        """使用 LLM 增强评估"""
        # 简化实现：暂不使用 LLM 增强
        # TODO: 实现 LLM 辅助评估
        return step_rewards
    
    def _summarize(self, data: Any) -> Optional[str]:
        """摘要数据"""
        if data is None:
            return None
        
        if isinstance(data, str):
            return data[:200] + "..." if len(data) > 200 else data
        
        try:
            import json
            s = json.dumps(data, ensure_ascii=False)
            return s[:200] + "..." if len(s) > 200 else s
        except Exception:
            return str(data)[:200]
    
    def get_session(self, session_id: str) -> Optional[SessionReward]:
        """获取会话奖励"""
        return self._sessions.get(session_id)
    
    def clear_session(self, session_id: str):
        """清除会话数据"""
        if session_id in self._sessions:
            del self._sessions[session_id]
        if session_id in self._step_buffer:
            del self._step_buffer[session_id]


def create_reward_attribution(
    llm_service: Any = None,
    default_method: AttributionMethod = AttributionMethod.DIRECT,
) -> RewardAttribution:
    """
    创建奖励归因器
    
    Args:
        llm_service: LLM 服务
        default_method: 默认归因方法
        
    Returns:
        RewardAttribution 实例
    """
    return RewardAttribution(
        llm_service=llm_service,
        default_method=default_method,
    )
