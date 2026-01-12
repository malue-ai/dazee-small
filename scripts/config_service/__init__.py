"""
Config Service - Control Plane 配置服务 (V6.0)

面向运营人员的异步配置管理服务，与 Data Plane（线上服务）分离。

核心组件:
- WorkerPromptGenerator: LLM 智能生成 Worker 系统提示词
- HITLConfirmation: Human-In-The-Loop 确认管理
- WorkerConfigManager: Worker 配置生命周期管理

使用场景:
- 运营人员创建/更新 Worker 专业提示词
- FDE 审核并确认 LLM 生成的配置
- 配置生效后同步到 instances/{instance}/workers/

架构分离:
- Control Plane (本模块): 异步配置管理，面向运营
- Data Plane (core/multi_agent): 实时执行，面向用户

Date: 2026-01-12
"""

from .worker_prompt_generator import WorkerPromptGenerator, GeneratedPrompt
from .hitl_confirmation import (
    HITLConfirmation,
    ConfirmationRequest,
    ConfirmationType,
    ConfirmationStatus
)
from .worker_config_manager import WorkerConfigManager

__all__ = [
    # 生成器
    "WorkerPromptGenerator",
    "GeneratedPrompt",
    # HITL
    "HITLConfirmation",
    "ConfirmationRequest",
    "ConfirmationType",
    "ConfirmationStatus",
    # 配置管理
    "WorkerConfigManager",
]
