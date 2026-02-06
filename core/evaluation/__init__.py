"""
Evaluation 评估模块

V8.0 新增

职责：
- RewardAttribution: 细粒度步骤级奖励归因
- 支持持续学习和策略优化

设计原则：
- 会话级评估 → 步骤级评估
- 自动化评估 + 人工审核
- 支持策略库更新
"""

from core.evaluation.reward_attribution import (
    RewardAttribution,
    SessionReward,
    StepReward,
    create_reward_attribution,
)

__all__ = [
    "RewardAttribution",
    "StepReward",
    "SessionReward",
    "create_reward_attribution",
]
