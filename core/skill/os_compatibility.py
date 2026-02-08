"""
OS 兼容性检查器 - OSCompatibilityChecker

检查 Skill 在当前操作系统下的兼容性与可用状态。
四状态：ready / need_auth / need_setup / unavailable
"""

import platform
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from logger import get_logger

logger = get_logger(__name__)


class CompatibilityStatus(str, Enum):
    """兼容性状态"""

    READY = "ready"
    NEED_AUTH = "need_auth"
    NEED_SETUP = "need_setup"
    UNAVAILABLE = "unavailable"


@dataclass
class CompatibilityResult:
    """
    Skill 兼容性检查结果

    Attributes:
        status: ready | need_auth | need_setup | unavailable
        message: 人类可读说明
        alternatives: 可替代的 Skill 名称列表
    """

    status: str  # CompatibilityStatus 取值
    message: str = ""
    alternatives: List[str] = field(default_factory=list)


def _current_os_key() -> str:
    """当前操作系统配置键（与 config/skills.yaml OS 分类对齐）"""
    s = platform.system().lower()
    if s == "darwin":
        return "darwin"
    if s == "windows":
        return "win32"
    return "linux"


class OSCompatibilityChecker:
    """
    OS 兼容性检查器

    根据 Skill 元数据与当前 OS 判断状态，并可选查找替代 Skill。
    """

    def __init__(self, skills_dir: Optional[Path] = None):
        self.skills_dir = Path(skills_dir) if skills_dir else None
        self._os_key = _current_os_key()

    def check_skill(self, skill_metadata: Dict[str, Any]) -> CompatibilityResult:
        """
        检查 Skill 兼容性

        Args:
            skill_metadata: Skill 元数据（含 supported_os、requires 等）

        Returns:
            CompatibilityResult
        """
        supported_os = skill_metadata.get("supported_os") or skill_metadata.get("os") or []
        if not supported_os:
            return CompatibilityResult(
                status=CompatibilityStatus.READY.value,
                message="无 OS 限制",
            )

        # 归一化：macos -> darwin
        normalized = []
        for o in supported_os:
            o = str(o).lower()
            if o == "macos":
                normalized.append("darwin")
            else:
                normalized.append(o)

        if self._os_key in normalized:
            return CompatibilityResult(
                status=CompatibilityStatus.READY.value,
                message=f"支持当前系统 {self._os_key}",
            )

        return CompatibilityResult(
            status=CompatibilityStatus.UNAVAILABLE.value,
            message=f"当前系统 {self._os_key} 不在支持列表 {normalized}",
            alternatives=self._find_alternatives(skill_metadata),
        )

    def _find_alternatives(self, skill_metadata: Dict[str, Any]) -> List[str]:
        """
        查找可替代的 Skill（同能力、支持当前 OS）

        简化实现：返回空列表，后续可扩展为从注册表按能力匹配。
        """
        return []
