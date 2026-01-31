"""
Token Budget - 多智能体 Token 预算管理

职责：
- 根据用户等级和 Agent 类型分配 Token 预算
- 检查预算是否足够
- 实时监控 Token 使用
- 支持预算告警和降级策略

设计原则：
- 参考 Anthropic 实践：多智能体工作流消耗 ~15× token
- 适合高价值任务，不适合简单查询
- 提供成本 vs 价值分析
"""

from typing import Dict, Tuple, Optional
from enum import Enum
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)


class QoSTier(str, Enum):
    """用户等级（与 QoS 对齐）"""
    FREE = "FREE"
    BASIC = "BASIC"
    PRO = "PRO"
    ENTERPRISE = "ENTERPRISE"


class AgentType(str, Enum):
    """Agent 类型"""
    SINGLE = "single"    # 单智能体
    MULTI = "multi"      # 多智能体


class BudgetCheckResult(BaseModel):
    """预算检查结果"""
    allowed: bool
    reason: str
    budget_total: int
    budget_used: int
    budget_remaining: int
    estimated_tokens: int
    warning: Optional[str] = None  # 警告信息（接近预算时）


class MultiAgentTokenBudget:
    """
    多智能体 Token 预算管理器
    
    参考 Anthropic 实践：
    - 多智能体工作流消耗 ~15× token（vs 单智能体）
    - 需要根据任务复杂度和用户等级分配预算
    - 超出预算时降级到单智能体或拒绝请求
    
    使用示例：
        budget = MultiAgentTokenBudget()
        
        # 检查预算
        result = await budget.check_budget(
            user_tier="PRO",
            agent_type="multi",
            estimated_tokens=500_000
        )
        
        if not result.allowed:
            print(f"预算不足: {result.reason}")
        
        # 记录使用
        budget.record_usage("session-123", 50_000)
    """
    
    # Anthropic 启发：多智能体是单智能体的 15 倍
    MULTI_AGENT_MULTIPLIER = 15.0
    
    # 基础预算（单智能体，每次对话）
    BASE_BUDGET = {
        QoSTier.FREE: 50_000,        # 50K tokens
        QoSTier.BASIC: 100_000,      # 100K tokens
        QoSTier.PRO: 150_000,        # 150K tokens
        QoSTier.ENTERPRISE: 200_000, # 200K tokens
    }
    
    # 告警阈值（使用超过预算的百分比时告警）
    WARNING_THRESHOLD = 0.8  # 80%
    
    def __init__(self):
        """初始化 Token 预算管理器"""
        # session_id -> token 使用量
        self._session_usage: Dict[str, int] = {}
        
        # 自定义预算（如果设置了，覆盖默认值）
        self._custom_budgets: Dict[Tuple[str, str], int] = {}
    
    def set_custom_budget(
        self,
        user_tier: str,
        agent_type: str,
        budget: int
    ):
        """
        设置自定义预算（覆盖默认值）
        
        Args:
            user_tier: 用户等级
            agent_type: Agent 类型
            budget: 预算（tokens）
        """
        key = (user_tier.upper(), agent_type.lower())
        self._custom_budgets[key] = budget
        logger.info(f"✅ 自定义预算: {user_tier}/{agent_type} = {budget:,} tokens")
    
    def get_budget(
        self,
        user_tier: str,
        agent_type: str
    ) -> int:
        """
        获取 Token 预算
        
        Args:
            user_tier: 用户等级（FREE/BASIC/PRO/ENTERPRISE）
            agent_type: Agent 类型（single/multi）
            
        Returns:
            预算（tokens）
        """
        # 检查自定义预算
        key = (user_tier.upper(), agent_type.lower())
        if key in self._custom_budgets:
            return self._custom_budgets[key]
        
        # 使用默认预算
        try:
            tier = QoSTier(user_tier.upper())
        except ValueError:
            logger.warning(f"⚠️ 未知用户等级: {user_tier}，使用 FREE")
            tier = QoSTier.FREE
        
        base = self.BASE_BUDGET[tier]
        
        # 多智能体应用倍数
        if agent_type.lower() == AgentType.MULTI:
            return int(base * self.MULTI_AGENT_MULTIPLIER)
        
        return base
    
    def get_session_usage(self, session_id: str) -> int:
        """
        获取会话已使用的 tokens
        
        Args:
            session_id: 会话 ID
            
        Returns:
            已使用的 tokens
        """
        return self._session_usage.get(session_id, 0)
    
    def record_usage(self, session_id: str, tokens: int):
        """
        记录 token 使用
        
        Args:
            session_id: 会话 ID
            tokens: 使用的 tokens
        """
        if session_id not in self._session_usage:
            self._session_usage[session_id] = 0
        
        self._session_usage[session_id] += tokens
        
        logger.debug(
            f"📊 Token 使用: session={session_id}, "
            f"当前使用={tokens:,}, "
            f"总计={self._session_usage[session_id]:,}"
        )
    
    def reset_session(self, session_id: str):
        """
        重置会话预算（新对话开始时）
        
        Args:
            session_id: 会话 ID
        """
        if session_id in self._session_usage:
            del self._session_usage[session_id]
            logger.debug(f"🔄 会话预算已重置: {session_id}")
    
    async def check_budget(
        self,
        user_tier: str,
        agent_type: str,
        estimated_tokens: int,
        session_id: Optional[str] = None
    ) -> BudgetCheckResult:
        """
        检查预算是否足够
        
        Args:
            user_tier: 用户等级
            agent_type: Agent 类型
            estimated_tokens: 预估需要的 tokens
            session_id: 会话 ID（如果提供，检查会话级预算）
            
        Returns:
            BudgetCheckResult
        """
        # 获取预算
        budget_total = self.get_budget(user_tier, agent_type)
        
        # 获取已使用量
        budget_used = self.get_session_usage(session_id) if session_id else 0
        
        # 计算剩余预算
        budget_remaining = budget_total - budget_used
        
        # 检查是否足够
        if estimated_tokens > budget_remaining:
            return BudgetCheckResult(
                allowed=False,
                reason=f"预算不足：预估需要 {estimated_tokens:,} tokens，"
                       f"但剩余 {budget_remaining:,} tokens",
                budget_total=budget_total,
                budget_used=budget_used,
                budget_remaining=budget_remaining,
                estimated_tokens=estimated_tokens,
            )
        
        # 检查是否接近预算（告警）
        usage_rate = (budget_used + estimated_tokens) / budget_total
        warning = None
        
        if usage_rate >= self.WARNING_THRESHOLD:
            warning = (
                f"⚠️ 预算使用率 {usage_rate:.1%}，接近预算上限 "
                f"({budget_used + estimated_tokens:,}/{budget_total:,})"
            )
            logger.warning(warning)
        
        return BudgetCheckResult(
            allowed=True,
            reason="预算充足",
            budget_total=budget_total,
            budget_used=budget_used,
            budget_remaining=budget_remaining,
            estimated_tokens=estimated_tokens,
            warning=warning,
        )
    
    def estimate_tokens_for_multi_agent(
        self,
        base_tokens: int,
        num_workers: int = 3,
        orchestration_overhead: float = 1.2
    ) -> int:
        """
        估算多智能体任务的 token 消耗
        
        基于 Anthropic 实践：
        - 基础消耗 = 单智能体的 token 估算
        - Worker 并行度影响（num_workers）
        - Orchestration 开销（任务分解、结果聚合等）
        
        Args:
            base_tokens: 单智能体预估的 token 数
            num_workers: Worker 数量
            orchestration_overhead: 编排开销倍数（默认 1.2 = 20% 开销）
            
        Returns:
            多智能体预估的 token 数
        """
        # 简化公式：base × num_workers × orchestration_overhead
        estimated = int(base_tokens * num_workers * orchestration_overhead)
        
        logger.debug(
            f"📊 多智能体 Token 估算: "
            f"base={base_tokens:,}, "
            f"workers={num_workers}, "
            f"overhead={orchestration_overhead}, "
            f"estimated={estimated:,}"
        )
        
        return estimated
    
    def get_summary(self) -> Dict[str, any]:
        """
        获取预算使用摘要
        
        Returns:
            摘要字典
        """
        total_sessions = len(self._session_usage)
        total_tokens = sum(self._session_usage.values())
        
        return {
            "active_sessions": total_sessions,
            "total_tokens_used": total_tokens,
            "average_per_session": (
                total_tokens // total_sessions if total_sessions > 0 else 0
            ),
            "custom_budgets": len(self._custom_budgets),
        }


# ============================================================
# 工厂函数
# ============================================================

_global_token_budget: Optional[MultiAgentTokenBudget] = None


def create_token_budget() -> MultiAgentTokenBudget:
    """
    创建 Token 预算管理器（单例模式）
    
    Returns:
        MultiAgentTokenBudget 实例
    """
    global _global_token_budget
    
    if _global_token_budget is None:
        _global_token_budget = MultiAgentTokenBudget()
        logger.info("✅ Token 预算管理器已初始化")
    
    return _global_token_budget


def get_token_budget() -> MultiAgentTokenBudget:
    """
    获取全局 Token 预算管理器
    
    Returns:
        MultiAgentTokenBudget 实例
    """
    if _global_token_budget is None:
        return create_token_budget()
    
    return _global_token_budget
