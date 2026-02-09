"""
Playbook 策略库模块

V8.0 新增
V10.0 重构：统一存储后端，修复实例隔离

职责：
- 自动生成成功执行策略
- 人工审核和确认
- 策略检索和应用

架构：
- PlaybookManager: 策略库管理器
- PlaybookEntry: 策略条目
- FileStorage: 文件存储后端

工作流：
1. RewardAttribution 评估会话 → 高分会话
2. PlaybookManager 提取策略模式
3. 人工审核确认（可选）
4. 存储为可复用策略
5. 新会话匹配相似场景 → 应用策略
"""

from core.playbook.manager import (
    PlaybookEntry,
    PlaybookManager,
    PlaybookStatus,
    create_playbook_manager,
)

__all__ = [
    "PlaybookManager",
    "PlaybookEntry",
    "PlaybookStatus",
    "create_playbook_manager",
]
