"""
OS Skills 合并器 - OSSkillMerger

按实例配置的二维分类（common + 当前 OS）合并出当前应启用的 Skill 列表。

支持两种配置格式：
1. 旧格式（V10）：skills_classification: { common: ["name1"], darwin: ["name2"] }
2. 新格式（V11 Skills-First）：skills: { common: { builtin: [{name: ...}] } }

新格式由 SkillsLoader 处理，本模块仅处理旧格式的向后兼容。
"""

import platform
from typing import Any, Dict, List, Optional

from logger import get_logger

logger = get_logger(__name__)


def _current_os_key() -> str:
    """当前操作系统配置键"""
    s = platform.system().lower()
    if s == "darwin":
        return "darwin"
    if s == "windows":
        return "win32"
    return "linux"


class OSSkillMerger:
    """
    OS Skills 合并器

    根据 skills_classification 配置（common / darwin / win32 / linux）
    合并出当前平台启用的 Skill 列表。

    支持两种值格式：
    - 字符串列表：["skill-a", "skill-b"]（旧格式）
    - 字典列表：[{name: "skill-a", ...}]（新格式，自动提取名称）
    """

    def __init__(self, skills_classification: Optional[Dict[str, Any]] = None):
        """
        Args:
            skills_classification: 二维配置，键为 common / darwin / win32 / linux
        """
        self.skills_classification = skills_classification or {}
        self._os_key = _current_os_key()

    def get_enabled_skills(self) -> List[str]:
        """
        合并 common + 当前 OS 的 Skill 名称列表（去重、保持顺序）

        Returns:
            当前应启用的 Skill 名称列表
        """
        common = self._extract_names(self.skills_classification.get("common"))
        os_skills = self._extract_names(self.skills_classification.get(self._os_key))

        seen = set()
        result = []
        for name in common + os_skills:
            if name and name not in seen:
                seen.add(name)
                result.append(name)
        return result

    def get_unavailable_skills(self) -> List[str]:
        """
        返回仅属于其他 OS 的 Skill 名称（当前平台不启用）

        Returns:
            当前不可用的 Skill 名称列表
        """
        other_keys = {"darwin", "win32", "linux"} - {self._os_key}
        result = []
        seen = set()
        for key in other_keys:
            for name in self._extract_names(self.skills_classification.get(key)):
                if name and name not in seen:
                    seen.add(name)
                    result.append(name)
        return result

    @property
    def current_os(self) -> str:
        """当前 OS 键"""
        return self._os_key

    def _extract_names(self, value: Any) -> List[str]:
        """
        从配置值中提取 Skill 名称列表

        支持：
        - None → []
        - List[str] → 直接返回
        - List[Dict] → 提取每个 dict 的 name 字段
        - Dict（新二维格式 {builtin: [...], lightweight: [...]}）→ 展平所有值

        Args:
            value: 配置值

        Returns:
            名称列表
        """
        if value is None:
            return []

        if isinstance(value, list):
            names = []
            for item in value:
                if isinstance(item, str):
                    names.append(item)
                elif isinstance(item, dict):
                    name = item.get("name")
                    if name:
                        names.append(name)
            return names

        if isinstance(value, dict):
            # 新二维格式：{builtin: [...], lightweight: [...], ...}
            names = []
            for level_key, items in value.items():
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, str):
                            names.append(item)
                        elif isinstance(item, dict):
                            name = item.get("name")
                            if name:
                                names.append(name)
            return names

        return []
