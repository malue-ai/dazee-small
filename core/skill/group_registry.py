"""
SkillGroupRegistry — Skill 分组的单一数据源

职责：
1. 从 config dict 加载分组（兼容新旧格式）
2. 提供 CRUD 方法管理分组和成员
3. 自动生成 intent prompt 用的分组描述
4. 反向查询（skill → groups）
5. 一致性校验（检测孤儿 skill）

数据流：
    config/skills.yaml (唯一数据源)
           ↓ 加载
    SkillGroupRegistry
           ↓ 派生
      ├── build_groups_description() → IntentAnalyzer
      ├── get_skills_for_groups()   → loader.py (过滤 available + unavailable)
      └── validate()                → 启动时检测孤儿 skill
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from logger import get_logger

logger = get_logger("skill_group_registry")

# _always 组的特殊键名，始终注入
ALWAYS_GROUP = "_always"


@dataclass
class SkillGroup:
    """Single skill group entry."""

    name: str
    description: str
    skills: List[str] = field(default_factory=list)


class SkillGroupRegistry:
    """
    Skill 分组注册表 — 单一数据源。

    Usage:
        registry = SkillGroupRegistry(config["skill_groups"])
        desc = registry.build_groups_description()
        names = registry.get_skills_for_groups(["writing", "meeting"])
    """

    def __init__(self, config: dict):
        """
        Load from config dict. Supports both formats:

        New (rich):
            {"writing": {"description": "...", "skills": [...]}}
        Old (flat):
            {"writing": ["skill-a", "skill-b"]}

        Args:
            config: skill_groups section from config/skills.yaml
        """
        self._groups: Dict[str, SkillGroup] = {}
        self._load(config or {})

        # Runtime caches (registry is immutable after init)
        self._desc_cache: Optional[str] = None
        self._groups_cache: Dict[frozenset, Set[str]] = {}

    # ================================================================
    # Read
    # ================================================================

    def get_group(self, name: str) -> Optional[SkillGroup]:
        """Get a single group by name."""
        return self._groups.get(name)

    def list_groups(self) -> List[str]:
        """List all group names (excluding _always)."""
        return [k for k in self._groups if k != ALWAYS_GROUP]

    def get_all_group_names(self) -> List[str]:
        """List all group names (including _always)."""
        return list(self._groups.keys())

    def get_skills_in_group(self, name: str) -> List[str]:
        """Get skill names in a specific group."""
        group = self._groups.get(name)
        return list(group.skills) if group else []

    def get_skills_for_groups(self, groups: List[str]) -> Set[str]:
        """
        Given a list of group names, return all skill names
        (union of selected groups + _always group).

        Results are cached by input (registry is immutable at runtime).

        Args:
            groups: list of group names from intent analysis

        Returns:
            set of skill names
        """
        cache_key = frozenset(groups)
        if cache_key in self._groups_cache:
            return self._groups_cache[cache_key]

        result: Set[str] = set()

        # Always include _always group
        always = self._groups.get(ALWAYS_GROUP)
        if always:
            result.update(always.skills)

        for group_name in groups:
            group = self._groups.get(group_name)
            if group:
                result.update(group.skills)

        self._groups_cache[cache_key] = result
        return result

    def get_groups_for_skill(self, skill_name: str) -> List[str]:
        """Reverse lookup: which groups contain this skill?"""
        return [
            name
            for name, group in self._groups.items()
            if skill_name in group.skills
        ]

    def supplement_groups_from_query(
        self, query: str, existing_groups: List[str]
    ) -> List[str]:
        """
        Deterministic post-check: if user query contains a known skill name,
        ensure that skill's group is included.

        This is NOT semantic inference — it's an exact string match safety net
        after LLM analysis. Per LLM-First principle, this is equivalent to
        format validation (deterministic, O(n), < 1ms).

        Args:
            query: user query text
            existing_groups: groups already selected by LLM

        Returns:
            existing_groups + any additional groups found by name matching
        """
        if not query:
            return existing_groups

        query_lower = query.lower()
        existing_set = set(existing_groups)
        added: List[str] = []

        for name, group in self._groups.items():
            if name == ALWAYS_GROUP or name in existing_set:
                continue
            for skill_name in group.skills:
                sn_lower = skill_name.lower()
                # Match both hyphenated ("trend-spotter") and spaced ("trend spotter")
                if sn_lower in query_lower or sn_lower.replace("-", " ") in query_lower:
                    added.append(name)
                    logger.info(
                        f"Skill 名称直匹配: '{skill_name}' → group '{name}'"
                    )
                    break  # one match per group is enough

        if added:
            return existing_groups + added
        return existing_groups

    # ================================================================
    # Create / Update / Delete
    # ================================================================

    def add_group(self, name: str, description: str, skills: Optional[List[str]] = None) -> None:
        """Add a new group or overwrite existing."""
        self._groups[name] = SkillGroup(
            name=name,
            description=description,
            skills=list(skills) if skills else [],
        )
        self._invalidate_cache()

    def add_skill(self, group_name: str, skill_name: str) -> bool:
        """
        Add a skill to a group.

        Returns:
            True if added, False if group not found
        """
        group = self._groups.get(group_name)
        if not group:
            return False
        if skill_name not in group.skills:
            group.skills.append(skill_name)
            self._invalidate_cache()
        return True

    def remove_skill(self, group_name: str, skill_name: str) -> bool:
        """
        Remove a skill from a group.

        Returns:
            True if removed, False if not found
        """
        group = self._groups.get(group_name)
        if not group or skill_name not in group.skills:
            return False
        group.skills.remove(skill_name)
        self._invalidate_cache()
        return True

    def remove_group(self, name: str) -> bool:
        """
        Remove an entire group.

        Returns:
            True if removed, False if not found
        """
        if name in self._groups:
            del self._groups[name]
            self._invalidate_cache()
            return True
        return False

    # ================================================================
    # Derivation: intent prompt description
    # ================================================================

    def build_groups_description(self) -> str:
        """
        Auto-generate the skill groups description for the intent prompt.

        Returns a markdown-formatted string like:
            - **writing**: 写作、润色... (writing-assistant, style-learner, ...)
            - **data_analysis**: Excel/CSV ... (excel-analyzer, ...)

        Includes skill names so the LLM can match user queries that reference
        skills by their English names (e.g. "trend-spotter" → research group).

        Only includes user-facing groups (excludes _always).
        Result is cached (registry is immutable at runtime).

        V12.1: 展示更多 skill 名称（8→10），提升小模型匹配命中率。
        """
        if self._desc_cache is not None:
            return self._desc_cache

        max_skills_shown = 10
        lines = []
        for name, group in self._groups.items():
            if name == ALWAYS_GROUP:
                continue
            # Include skill names for better LLM matching
            skill_names = ", ".join(group.skills[:max_skills_shown])
            if len(group.skills) > max_skills_shown:
                skill_names += f" 等{len(group.skills)}个"
            lines.append(f"- **{name}**: {group.description} ({skill_names})")
        self._desc_cache = "\n".join(lines)
        return self._desc_cache

    # ================================================================
    # Validation
    # ================================================================

    def validate(self, all_skill_names: Set[str]) -> List[str]:
        """
        Check which skills are not in any group (orphan detection).

        Args:
            all_skill_names: set of all known skill names
                             (from SkillsLoader entries)

        Returns:
            list of orphan skill names
        """
        grouped: Set[str] = set()
        for group in self._groups.values():
            grouped.update(group.skills)

        orphans = sorted(all_skill_names - grouped)
        return orphans

    def validate_and_warn(self, all_skill_names: Set[str]) -> None:
        """Run validate() and log warnings for orphan skills."""
        orphans = self.validate(all_skill_names)
        if orphans:
            logger.warning(
                f"Skill 分组覆盖检查: {len(orphans)} 个 skill 未归入任何分组 "
                f"(意图过滤时不可见): {orphans}"
            )

    # ================================================================
    # Serialization (for config export)
    # ================================================================

    def to_config_dict(self) -> dict:
        """Export to config/skills.yaml format (rich format)."""
        result = {}
        for name, group in self._groups.items():
            result[name] = {
                "description": group.description,
                "skills": list(group.skills),
            }
        return result

    # ================================================================
    # Internal: cache management
    # ================================================================

    def _invalidate_cache(self) -> None:
        """Clear all runtime caches (called after any write operation)."""
        self._desc_cache = None
        self._groups_cache.clear()

    # ================================================================
    # Internal: loading
    # ================================================================

    def _load(self, config: dict) -> None:
        """Parse config dict, auto-detect old vs new format."""
        for key, value in config.items():
            if isinstance(value, dict):
                # New rich format: {"description": "...", "skills": [...]}
                self._groups[key] = SkillGroup(
                    name=key,
                    description=value.get("description", ""),
                    skills=list(value.get("skills", [])),
                )
            elif isinstance(value, list):
                # Old flat format: ["skill-a", "skill-b"]
                self._groups[key] = SkillGroup(
                    name=key,
                    description="",
                    skills=list(value),
                )
            else:
                logger.warning(f"跳过无法识别的 skill_groups 条目: {key}={value}")

        logger.info(
            f"SkillGroupRegistry 加载完成: "
            f"{len(self._groups)} 个分组, "
            f"{sum(len(g.skills) for g in self._groups.values())} 个 skill 归组"
        )

    def __repr__(self) -> str:
        return (
            f"SkillGroupRegistry("
            f"groups={len(self._groups)}, "
            f"skills={sum(len(g.skills) for g in self._groups.values())})"
        )
