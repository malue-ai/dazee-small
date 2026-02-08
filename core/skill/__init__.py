"""
Skill 管理模块

职责：
- Skills-First 统一加载器（SkillsLoader）
- OS 维度的 Skill 合并与兼容性检查
- 动态依赖检查与加载（DynamicSkillLoader）
- 统一数据模型（SkillEntry、BackendType 等）

架构说明（V11 Skills-First）：
- SkillsLoader: 核心加载器，解析 config.yaml → SkillEntry 列表
- SkillEntry: Agent 看到的唯一能力单元
- BackendType: Skill 执行后端（local/tool/mcp/api），Agent 不感知

相关组件：
- core/tool/capability/skill_loader.py: Skill 内容加载器（SKILL.md 渐进式加载）
- Skills 提示词由 SkillsLoader.build_skills_prompt() 注入到 runtime_context["skills_prompt"]
"""

from core.skill.dynamic_loader import DynamicSkillLoader, SkillDependency, check_and_report_skills
from core.skill.group_registry import SkillGroupRegistry
from core.skill.loader import SkillsLoader, create_skills_loader
from core.skill.models import BackendType, DependencyLevel, SkillEntry, SkillStatus
from core.skill.os_compatibility import (
    CompatibilityResult,
    CompatibilityStatus,
    OSCompatibilityChecker,
)
__all__ = [
    # Skills-First 核心
    "SkillsLoader",
    "create_skills_loader",
    "SkillGroupRegistry",
    "SkillEntry",
    "BackendType",
    "DependencyLevel",
    "SkillStatus",
    # OS 兼容性
    "OSCompatibilityChecker",
    "CompatibilityResult",
    "CompatibilityStatus",
    # 动态加载
    "DynamicSkillLoader",
    "SkillDependency",
    "check_and_report_skills",
]
