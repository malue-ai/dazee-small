"""
云端协同模块

本地端管理与云端 Agent 的交互：
- models: 云端任务数据模型（本地 SQLite 存储）
- task_manager: 任务生命周期管理（创建/追踪/取消）
"""

from core.cloud.models import LocalCloudTask
from core.cloud.task_manager import CloudTaskManager

__all__ = ["LocalCloudTask", "CloudTaskManager"]
