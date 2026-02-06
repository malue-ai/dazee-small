"""
Skill Memory - 已加载的 Skills 缓存

职责：
- 存储 Skill 元数据（名称、描述、路径）
- 缓存 Skill 资源（SKILL.md 内容、scripts 路径）
- 支持 Skill 的注册和查询

设计原则：
- 系统级：全局共享，所有用户可用
- 缓存优先：减少重复加载
- 本地文件系统：Skills 存储在 skills/library/ 目录
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from logger import get_logger

from ..base import BaseMemory, MemoryConfig, MemoryScope, StorageBackend

logger = get_logger("memory.system.skill")


class SkillMemory(BaseMemory):
    """
    Skill 记忆 - 已加载的 Skills 缓存

    存储内容：
    - Skill 元数据（名称、描述、路径）
    - Skill 资源（SKILL.md 内容、scripts 路径）

    使用方式：
        memory = SkillMemory()
        await memory.initialize()
    """

    def __init__(self) -> None:
        config = MemoryConfig(scope=MemoryScope.SYSTEM, backend=StorageBackend.MEMORY)
        super().__init__(config)

        self.skills: Dict[str, Dict[str, Any]] = {}
        self._initialized: bool = False

    async def initialize(self) -> None:
        """
        异步初始化

        使用方式：
            memory = SkillMemory()
            await memory.initialize()
        """
        if self._initialized:
            return

        self._initialized = True
        logger.debug("[SkillMemory] 初始化完成")

    async def register_skill(
        self,
        skill_name: str,
        skill_path: str,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        注册一个 Skill

        Args:
            skill_name: Skill 名称
            skill_path: Skill 文件路径
            description: Skill 描述
            metadata: 额外元数据
        """
        self.skills[skill_name] = {
            "name": skill_name,
            "path": skill_path,
            "description": description,
            "metadata": metadata or {},
            "loaded_at": datetime.now().isoformat(),
        }

        logger.debug(f"[SkillMemory] 注册 Skill: {skill_name}")

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

    async def unregister_skill(self, skill_name: str) -> None:
        """注销 Skill"""
        if skill_name in self.skills:
            del self.skills[skill_name]
        logger.debug(f"[SkillMemory] 注销 Skill: {skill_name}")

    async def clear(self) -> None:
        """清空所有 Skills"""
        self.skills.clear()

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        base = super().to_dict()
        base.update({"skills_count": len(self.skills), "skills": list(self.skills.keys())})
        return base


def create_skill_memory() -> SkillMemory:
    """
    创建 SkillMemory 实例

    注意：创建后需要调用 await memory.initialize() 完成异步初始化

    Returns:
        SkillMemory 实例
    """
    return SkillMemory()


async def create_skill_memory_async() -> SkillMemory:
    """
    创建并初始化 SkillMemory 实例（异步版本）

    Returns:
        已初始化的 SkillMemory 实例
    """
    memory = create_skill_memory()
    await memory.initialize()
    return memory
