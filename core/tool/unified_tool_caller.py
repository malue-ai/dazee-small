"""
UnifiedToolCaller - 统一工具调用协调器

用于在 Skills 与普通工具之间进行统一编排和降级处理。
"""

from typing import Any, Dict, List, Optional

from logger import get_logger
from core.tool.capability import CapabilityRegistry

logger = get_logger(__name__)


class UnifiedToolCaller:
    """
    统一工具调用协调器
    
    负责：
    - Skill 推荐在非 Claude 环境下的 fallback 处理
    - 工具选择前的能力列表修正
    """
    
    def __init__(self, registry: CapabilityRegistry):
        """
        初始化统一工具调用器
        
        Args:
            registry: 能力注册表
        """
        self.registry = registry
    
    def get_fallback_tool_for_skill(self, recommended_skill: Any) -> Optional[str]:
        """
        获取 Skill 对应的 fallback_tool
        
        Args:
            recommended_skill: 推荐 Skill（dict 或 str）
        
        Returns:
            fallback_tool 名称
        """
        if not recommended_skill:
            return None
        
        if isinstance(recommended_skill, dict):
            skill_name = recommended_skill.get("name") or recommended_skill.get("skill_id")
        else:
            skill_name = str(recommended_skill)
        
        if not skill_name:
            return None
        
        capability = self.registry.get(skill_name)
        if capability and capability.fallback_tool:
            return capability.fallback_tool
        return None

    def _supports_skills_for_all_targets(self, llm_service: Any) -> bool:
        """
        判断 LLM 服务是否对所有目标都支持 Skills
        """
        targets = getattr(llm_service, "targets", None)
        if targets is not None:
            if not targets:
                return False
            for target in targets:
                service = getattr(target, "service", None)
                if not service or not hasattr(service, "supports_skills"):
                    return False
                if not service.supports_skills():
                    return False
            return True
        
        if hasattr(llm_service, "supports_skills"):
            return llm_service.supports_skills()
        return False
    
    def ensure_skill_fallback(
        self,
        required_capabilities: List[str],
        recommended_skill: Any,
        llm_service: Any
    ) -> List[str]:
        """
        当模型不支持 Skills 时，确保 fallback 工具被加入能力列表
        
        Args:
            required_capabilities: 原始能力列表
            recommended_skill: 推荐 Skill
            llm_service: LLM 服务实例
        
        Returns:
            修正后的能力列表
        """
        if not recommended_skill:
            return required_capabilities
        
        supports_skills = self._supports_skills_for_all_targets(llm_service)
        if supports_skills:
            return required_capabilities
        
        fallback_tool = self.get_fallback_tool_for_skill(recommended_skill)
        if fallback_tool and fallback_tool not in required_capabilities:
            required_capabilities.append(fallback_tool)
            logger.info(f"🧩 Skill fallback 启用: {fallback_tool}")
        
        return required_capabilities


def create_unified_tool_caller(registry: CapabilityRegistry) -> UnifiedToolCaller:
    """
    创建统一工具调用器
    """
    return UnifiedToolCaller(registry)
