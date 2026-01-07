"""
Skill Memory - 已加载的 Skills 缓存

职责：
- 存储 Skill 元数据（名称、描述、路径）
- 缓存 Skill 资源（SKILL.md 内容、scripts 路径）
- 🆕 缓存 Claude 服务器返回的 skill_id（V4.2.3）
- 支持 Skill 的注册和查询

设计原则：
- 系统级：全局共享，所有用户可用
- 缓存优先：减少重复加载
- 异步注册：启动时异步注册到 Claude 服务器
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
import json
from logger import get_logger

from ..base import BaseMemory, MemoryConfig, MemoryScope, StorageBackend

logger = get_logger("memory.system.skill")

# 持久化缓存文件路径
SKILL_CACHE_FILE = Path(__file__).parent.parent.parent.parent / "outputs" / "skill_id_cache.json"


class SkillMemory(BaseMemory):
    """
    Skill 记忆 - 已加载的 Skills 缓存
    
    存储内容：
    - Skill 元数据（名称、描述、路径）
    - Skill 资源（SKILL.md 内容、scripts 路径）
    - 🆕 skill_id 缓存（Claude 服务器返回）
    
    缓存机制：
    - skill_id 持久化到本地文件，避免重复注册
    - Agent 启动时自动加载缓存
    """
    
    def __init__(self):
        config = MemoryConfig(
            scope=MemoryScope.SYSTEM,
            backend=StorageBackend.MEMORY
        )
        super().__init__(config)
        
        self.skills: Dict[str, Dict[str, Any]] = {}
        # 🆕 skill_id 缓存 {skill_name: skill_id}
        self.skill_id_cache: Dict[str, str] = {}
        
        # 启动时加载持久化缓存
        self._load_skill_id_cache()
    
    def _load_skill_id_cache(self):
        """从文件加载 skill_id 缓存"""
        if SKILL_CACHE_FILE.exists():
            try:
                with open(SKILL_CACHE_FILE, 'r', encoding='utf-8') as f:
                    self.skill_id_cache = json.load(f)
                logger.info(f"[SkillMemory] 加载 skill_id 缓存: {len(self.skill_id_cache)} 个")
            except Exception as e:
                logger.warning(f"[SkillMemory] 加载缓存失败: {e}")
                self.skill_id_cache = {}
    
    def _save_skill_id_cache(self):
        """持久化 skill_id 缓存到文件"""
        try:
            SKILL_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(SKILL_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.skill_id_cache, f, ensure_ascii=False, indent=2)
            logger.debug(f"[SkillMemory] 保存 skill_id 缓存: {len(self.skill_id_cache)} 个")
        except Exception as e:
            logger.error(f"[SkillMemory] 保存缓存失败: {e}")
    
    def register_skill(
        self,
        skill_name: str,
        skill_path: str,
        description: str = "",
        skill_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        注册一个 Skill
        
        Args:
            skill_name: Skill 名称
            skill_path: Skill 文件路径
            description: Skill 描述
            skill_id: 🆕 Claude 服务器返回的 skill_id
            metadata: 额外元数据
        """
        self.skills[skill_name] = {
            "name": skill_name,
            "path": skill_path,
            "description": description,
            "skill_id": skill_id,
            "metadata": metadata or {},
            "loaded_at": datetime.now().isoformat()
        }
        
        # 🆕 缓存 skill_id
        if skill_id:
            self.skill_id_cache[skill_name] = skill_id
            self._save_skill_id_cache()
        
        logger.debug(f"[SkillMemory] 注册 Skill: {skill_name}, skill_id={skill_id}")
    
    def get_skill(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """获取 Skill 信息"""
        return self.skills.get(skill_name)
    
    def has_skill(self, skill_name: str) -> bool:
        """检查 Skill 是否已注册"""
        return skill_name in self.skills
    
    def list_skills(self) -> List[str]:
        """列出所有已注册的 Skills"""
        return list(self.skills.keys())
    
    def get_skill_path(self, skill_name: str) -> Optional[str]:
        """获取 Skill 的文件路径"""
        skill = self.get_skill(skill_name)
        return skill["path"] if skill else None
    
    # ==================== 🆕 skill_id 相关方法 ====================
    
    def get_skill_id(self, skill_name: str) -> Optional[str]:
        """
        获取已注册的 skill_id
        
        Args:
            skill_name: Skill 名称
            
        Returns:
            Claude 服务器返回的 skill_id，如果未注册则返回 None
        """
        return self.skill_id_cache.get(skill_name)
    
    def has_skill_id(self, skill_name: str) -> bool:
        """检查 Skill 是否已注册到 Claude 服务器"""
        return skill_name in self.skill_id_cache
    
    def set_skill_id(self, skill_name: str, skill_id: str):
        """
        设置 skill_id（异步注册后调用）
        
        Args:
            skill_name: Skill 名称
            skill_id: Claude 服务器返回的 skill_id
        """
        self.skill_id_cache[skill_name] = skill_id
        
        # 同步更新 skills 记录
        if skill_name in self.skills:
            self.skills[skill_name]["skill_id"] = skill_id
        
        # 持久化
        self._save_skill_id_cache()
        logger.info(f"[SkillMemory] 缓存 skill_id: {skill_name} → {skill_id}")
    
    def get_all_skill_ids(self) -> Dict[str, str]:
        """
        获取所有已注册的 {skill_name: skill_id} 映射
        
        Returns:
            skill_id 缓存的副本
        """
        return self.skill_id_cache.copy()
    
    def get_registered_skills_for_container(self) -> List[Dict[str, str]]:
        """
        获取可传给 Claude API container.skills 的格式
        
        Returns:
            [
                {"type": "custom", "skill_id": "skill_abc123", "version": "latest"},
                ...
            ]
        """
        return [
            {
                "type": "custom",
                "skill_id": skill_id,
                "version": "latest"
            }
            for skill_id in self.skill_id_cache.values()
        ]
    
    def remove_skill_id(self, skill_name: str):
        """移除 skill_id 缓存"""
        if skill_name in self.skill_id_cache:
            del self.skill_id_cache[skill_name]
            self._save_skill_id_cache()
            logger.info(f"[SkillMemory] 移除 skill_id: {skill_name}")
    
    # ==================== 原有方法 ====================
    
    def unregister_skill(self, skill_name: str):
        """注销 Skill"""
        if skill_name in self.skills:
            del self.skills[skill_name]
        # 🆕 同时移除 skill_id
        self.remove_skill_id(skill_name)
        logger.debug(f"[SkillMemory] 注销 Skill: {skill_name}")
    
    def clear(self):
        """清空所有 Skills"""
        self.skills.clear()
        self.skill_id_cache.clear()
        self._save_skill_id_cache()
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        base = super().to_dict()
        base.update({
            "skills_count": len(self.skills),
            "skills": list(self.skills.keys()),
            "registered_skill_ids": len(self.skill_id_cache),
            "skill_ids": list(self.skill_id_cache.keys())
        })
        return base


def create_skill_memory() -> SkillMemory:
    """创建 SkillMemory 实例"""
    return SkillMemory()

