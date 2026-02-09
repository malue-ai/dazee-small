"""
Skill 内容加载器

职责：
1. 渐进式加载 SKILL.md 内容（Level 2）
2. 加载资源文件（Level 3）
3. 获取脚本路径

⚠️ 注意：
- "Skill 发现"由 CapabilityRegistry 负责（Level 1）
- SkillLoader 只负责"内容加载"（Level 2/3）

设计原则：
- 渐进式加载：按需加载，减少启动时间
- 缓存机制：避免重复加载
- File is Everything：所有知识存储在文件中
"""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import aiofiles


@dataclass
class SkillInfo:
    """Skill 信息"""

    name: str
    skill_path: str

    # 缓存内容
    skill_md_content: Optional[str] = None
    resources: Optional[Dict[str, str]] = None

    # 加载状态
    content_loaded: bool = False
    resources_loaded: bool = False


class SkillLoader:
    """
    Skill 内容加载器

    核心价值：渐进式加载（按需加载内容）

    使用方式：
        loader = SkillLoader()

        # 从 Registry 获取 Skill 的路径
        skill_cap = registry.get("slidespeak-generator")
        skill_path = skill_cap.metadata.get('skill_path')

        # 加载内容
        content = loader.load_skill_content(skill_path)
        resources = loader.load_skill_resources(skill_path)
        scripts = loader.get_skill_scripts(skill_path)
    """

    def __init__(self):
        """初始化 Skill 加载器"""
        self._cache: Dict[str, SkillInfo] = {}

    async def load_skill_content(self, skill_path: str) -> Optional[str]:
        """
        异步加载 SKILL.md 完整内容（Level 2）

        Args:
            skill_path: Skill 目录路径（从 Capability.metadata 获取）

        Returns:
            SKILL.md 的完整内容
        """
        # 检查缓存
        if skill_path in self._cache:
            skill_info = self._cache[skill_path]
            if skill_info.content_loaded:
                return skill_info.skill_md_content

        # 加载内容
        skill_md = Path(skill_path) / "SKILL.md"
        if not skill_md.exists():
            print(f"⚠️ SKILL.md not found: {skill_md}")
            return None

        try:
            async with aiofiles.open(skill_md, "r", encoding="utf-8") as f:
                content = await f.read()

            # 缓存
            if skill_path not in self._cache:
                self._cache[skill_path] = SkillInfo(
                    name=Path(skill_path).name, skill_path=skill_path
                )

            self._cache[skill_path].skill_md_content = content
            self._cache[skill_path].content_loaded = True

            return content
        except Exception as e:
            print(f"⚠️ Failed to load {skill_md}: {e}")
            return None

    async def load_skill_resources(self, skill_path: str) -> Dict[str, str]:
        """
        异步加载 Skill 资源文件（Level 3）

        Args:
            skill_path: Skill 目录路径

        Returns:
            资源文件字典 {filename: content}
        """
        # 检查缓存
        if skill_path in self._cache:
            skill_info = self._cache[skill_path]
            if skill_info.resources_loaded:
                return skill_info.resources or {}

        # 加载资源
        resources = {}
        resources_dir = Path(skill_path) / "resources"

        if resources_dir.exists():
            # 使用 asyncio.to_thread 包装同步的目录遍历
            files = await asyncio.to_thread(list, resources_dir.iterdir())
            for file in files:
                if file.is_file():
                    try:
                        async with aiofiles.open(file, "r", encoding="utf-8") as f:
                            resources[file.name] = await f.read()
                    except Exception as e:
                        print(f"⚠️ Failed to read {file}: {e}")

        # 缓存
        if skill_path not in self._cache:
            self._cache[skill_path] = SkillInfo(name=Path(skill_path).name, skill_path=skill_path)

        self._cache[skill_path].resources = resources
        self._cache[skill_path].resources_loaded = True

        return resources

    async def get_skill_scripts(self, skill_path: str) -> Dict[str, str]:
        """
        异步获取 Skill 脚本文件路径

        Args:
            skill_path: Skill 目录路径

        Returns:
            脚本文件字典 {script_name: path}
        """
        scripts = {}
        scripts_dir = Path(skill_path) / "scripts"

        if scripts_dir.exists():
            # 使用 asyncio.to_thread 包装同步的目录遍历
            files = await asyncio.to_thread(list, scripts_dir.iterdir())
            for file in files:
                if file.is_file() and file.suffix == ".py":
                    scripts[file.stem] = str(file)

        return scripts

    def get_skill_info(self, skill_path: str) -> Optional[SkillInfo]:
        """
        获取 Skill 信息（包括缓存状态）

        Args:
            skill_path: Skill 目录路径

        Returns:
            SkillInfo 或 None
        """
        return self._cache.get(skill_path)

    async def preload_skill(self, skill_path: str) -> SkillInfo:
        """
        异步预加载 Skill 的所有内容

        Args:
            skill_path: Skill 目录路径

        Returns:
            完全加载的 SkillInfo
        """
        # 加载所有内容
        await self.load_skill_content(skill_path)
        await self.load_skill_resources(skill_path)

        return self._cache.get(skill_path)

    def clear_cache(self, skill_path: str = None):
        """
        清除缓存

        Args:
            skill_path: 指定 Skill 路径（None 则清除全部）
        """
        if skill_path:
            self._cache.pop(skill_path, None)
        else:
            self._cache.clear()

    def get_cache_stats(self) -> Dict[str, int]:
        """
        获取缓存统计

        Returns:
            统计信息
        """
        total = len(self._cache)
        content_loaded = sum(1 for s in self._cache.values() if s.content_loaded)
        resources_loaded = sum(1 for s in self._cache.values() if s.resources_loaded)

        return {
            "total_cached": total,
            "content_loaded": content_loaded,
            "resources_loaded": resources_loaded,
        }


# ==================== 便捷函数 ====================


def create_skill_loader() -> SkillLoader:
    """
    创建 Skill 加载器

    Returns:
        SkillLoader 实例
    """
    return SkillLoader()
