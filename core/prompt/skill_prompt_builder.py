"""
Skill Prompt 构建器

核心理念：
- 只在系统 Prompt 中注入 Skills 列表（name + description + location）
- Agent 根据任务选择相关 Skill 后，通过 Read 工具读取完整内容
- 避免一次性加载 50+ Skills 导致 Token 爆炸

收益：
- 系统 Prompt 大小从 ~50K tokens 降至 ~5K tokens
- 每次对话节省 Token 成本 90%
- 按需加载，提升响应速度
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from logger import get_logger

logger = get_logger(__name__)


@dataclass
class SkillSummary:
    """Skill 简要信息（用于 Prompt 注入）"""

    name: str
    description: str
    location: Path  # SKILL.md 的绝对路径
    emoji: str = ""  # 可选图标
    requires_bins: List[str] = field(default_factory=list)
    requires_env: List[str] = field(default_factory=list)


class SkillPromptBuilder:
    """
    Skill Prompt 构建器

    支持两种模式：
    1. Lazy Mode（延迟加载）：仅注入 name + description + location
    2. Eager Mode（全量加载）：注入完整 SKILL.md 内容
    """

    # ================================================================
    # Prompt 构建（无状态，staticmethod）
    # ================================================================

    @staticmethod
    def build_lazy_prompt(
        skills: List[SkillSummary],
        language: str = "zh",
    ) -> str:
        """
        构建延迟加载 Prompt（仅注入 Skills 列表）

        Args:
            skills: Skills 简要信息列表
            language: 语言（zh/en）

        Returns:
            XML 格式的 Skills 列表
        """
        if not skills:
            return ""

        lines = ["<available_skills>"]

        for skill in skills:
            emoji_prefix = f"{skill.emoji} " if skill.emoji else ""
            # 使用相对路径节省 token（绝对路径每个 skill 浪费 ~90 chars）
            location = skill.location
            try:
                location = Path(location).relative_to(Path.cwd())
            except (ValueError, TypeError):
                pass  # 无法转相对路径时保留原值
            lines.append(f'  <skill name="{skill.name}" location="{location}">')
            lines.append(f"    <description>{emoji_prefix}{skill.description}</description>")
            lines.append("  </skill>")

        lines.append("</available_skills>")

        prompt = "\n".join(lines)

        logger.debug(f"构建延迟加载 Skills Prompt: {len(skills)} 个技能, {len(prompt)} 字符")

        return prompt

    @staticmethod
    def build_lazy_instructions(language: str = "zh") -> str:
        """
        构建延迟加载的系统指令

        Args:
            language: 语言（zh/en）

        Returns:
            系统指令文本
        """
        if language == "zh":
            return """
## Skills（技能）

扫描 `<available_skills>` 的 `<description>` 条目。
- 恰好一个技能适用 → 读取其 SKILL.md 并遵循
- 多个可能适用 → 选择最具体的
- 没有适用的 → 不读取

**重要：** 
- 只在明确需要时才读取 SKILL.md
- 不要在选择前读取多个 Skills
- 使用 Read 工具读取 `location` 指定的路径
""".strip()
        else:
            return """
## Skills (mandatory)

Scan `<available_skills>` `<description>` entries.
- If exactly one skill clearly applies: read its SKILL.md with Read, then follow it.
- If multiple could apply: choose the most specific one, then read/follow it.
- If none clearly apply: do not read any SKILL.md.

**Constraints:** 
- Only read SKILL.md when clearly needed
- Never read more than one skill up front
- Use Read tool with the `location` path
""".strip()

    @staticmethod
    def build_eager_prompt(
        skills_content: List[tuple[str, str]],
        language: str = "zh",
    ) -> str:
        """
        构建全量加载 Prompt（注入完整 SKILL.md 内容）

        Args:
            skills_content: [(skill_name, skill_md_content), ...]
            language: 语言（zh/en）

        Returns:
            完整的 Skills 内容
        """
        if not skills_content:
            return ""

        lines = ["# 可用技能" if language == "zh" else "# Available Skills", ""]

        for skill_name, content in skills_content:
            lines.append(f"## {skill_name}")
            lines.append("")
            lines.append(content)
            lines.append("")
            lines.append("---")
            lines.append("")

        prompt = "\n".join(lines)

        logger.debug(
            f"构建全量加载 Skills Prompt: {len(skills_content)} 个技能, {len(prompt)} 字符"
        )

        return prompt

    # ================================================================
    # 目录扫描 + Prompt 构建
    # ================================================================

    @classmethod
    def build_from_skill_dir(
        cls,
        skills_dir: Path,
        mode: str = "lazy",
        language: str = "zh",
    ) -> str:
        """
        从单个 Skills 目录构建 Prompt

        Args:
            skills_dir: Skills 目录路径
            mode: 加载模式（lazy/eager）
            language: 语言（zh/en）

        Returns:
            构建的 Prompt
        """
        return cls.build_from_skill_dirs([skills_dir], mode=mode, language=language)

    @classmethod
    def build_from_skill_dirs(
        cls,
        skill_dirs: List[Path],
        mode: str = "lazy",
        language: str = "zh",
    ) -> str:
        """
        从多个 Skills 目录构建 Prompt，按优先级合并（列表中靠前的优先，同名不覆盖）

        典型顺序：workspace（./skills/）> instance（instances/{id}/skills/）> bundled（skills/library/）

        Args:
            skill_dirs: 目录列表，优先级从高到低
            mode: 加载模式（lazy/eager）
            language: 语言（zh/en）

        Returns:
            构建的 Prompt
        """
        if not skill_dirs:
            return ""

        # 按优先级合并：列表中靠前的目录优先，已存在的同名 skill 不再被覆盖
        merged: Dict[str, SkillSummary] = {}
        for skills_dir in skill_dirs:
            if not skills_dir or not Path(skills_dir).exists():
                continue
            skill_files = list(Path(skills_dir).glob("*/SKILL.md"))
            for skill_file in skill_files:
                summary = cls._parse_skill_summary(skill_file)
                if summary and summary.name not in merged:
                    merged[summary.name] = summary

        if not merged:
            logger.info(f"未在 {skill_dirs} 中发现 Skills")
            return ""

        summaries = list(merged.values())

        if mode == "lazy":
            return cls.build_lazy_prompt(summaries, language)

        # eager: 按 merged 顺序加载完整内容
        skills_content = []
        for summary in summaries:
            try:
                content = summary.location.read_text(encoding="utf-8")
                skills_content.append((summary.name, content))
            except Exception as e:
                logger.warning(f"读取 {summary.location} 失败: {e}")
        return cls.build_eager_prompt(skills_content, language)

    # ================================================================
    # Frontmatter 解析（单一入口，DRY）
    # ================================================================

    @classmethod
    def _parse_frontmatter(cls, content: str) -> Optional[dict]:
        """
        Parse YAML frontmatter from SKILL.md content.

        Args:
            content: SKILL.md 文件完整文本

        Returns:
            解析后的 dict，或 None
        """
        if not content.startswith("---"):
            return None

        parts = content.split("---", 2)
        if len(parts) < 3:
            return None

        try:
            meta = yaml.safe_load(parts[1])
            return meta if isinstance(meta, dict) else None
        except yaml.YAMLError as e:
            logger.debug(f"YAML frontmatter 解析失败: {e}")
            return None

    @classmethod
    def _parse_skill_summary(cls, skill_file: Path) -> Optional[SkillSummary]:
        """
        解析 SKILL.md frontmatter 提取简要信息

        Args:
            skill_file: SKILL.md 文件路径

        Returns:
            SkillSummary 或 None
        """
        try:
            content = skill_file.read_text(encoding="utf-8")
            meta = cls._parse_frontmatter(content)
            if not meta:
                return None

            # name: 优先 frontmatter，回退目录名
            name = meta.get("name")
            if not isinstance(name, str) or not name:
                name = skill_file.parent.name

            # description: 必填
            description = meta.get("description", "")
            if not description:
                logger.debug(f"Skill {name} 缺少 description")
                return None

            # emoji: 从 metadata.emoji 或顶层 emoji
            emoji = ""
            metadata_block = meta.get("metadata", {})
            if isinstance(metadata_block, dict):
                emoji = str(metadata_block.get("emoji", ""))[:2]
            if not emoji:
                emoji = str(meta.get("emoji", ""))[:2]

            # requires: bins / env
            requires = meta.get("requires") or {}
            if not isinstance(requires, dict):
                requires = {}

            requires_bins = _ensure_str_list(requires.get("bins"))
            requires_env = _ensure_str_list(requires.get("env"))

            return SkillSummary(
                name=name,
                description=str(description),
                location=skill_file.absolute(),
                emoji=emoji,
                requires_bins=requires_bins,
                requires_env=requires_env,
            )

        except Exception as e:
            logger.warning(f"解析 {skill_file} 失败: {e}")
            return None

    @classmethod
    def parse_requires(cls, skill_md_path: Path) -> Dict[str, List[str]]:
        """
        从 SKILL.md 的 frontmatter 解析 requires（bins、env），供 Loader 合并 gating。

        内部复用 _parse_skill_summary，不重复解析。

        Args:
            skill_md_path: SKILL.md 绝对路径

        Returns:
            {"bins": [...], "env": [...]}
        """
        result: Dict[str, List[str]] = {"bins": [], "env": []}
        try:
            summary = cls._parse_skill_summary(skill_md_path)
            if summary:
                result["bins"] = summary.requires_bins
                result["env"] = summary.requires_env
        except Exception as e:
            logger.debug(f"解析 requires 失败 {skill_md_path}: {e}")
        return result


# ================================================================
# 辅助函数
# ================================================================


def _ensure_str_list(value: object) -> List[str]:
    """Normalize YAML value to List[str]: handles str, list, None."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return []


# ================================================================
# 便捷函数
# ================================================================


def build_skills_prompt(
    skills_dir: Path,
    mode: str = "lazy",
    language: str = "zh",
) -> str:
    """
    构建 Skills Prompt（便捷函数）

    Args:
        skills_dir: Skills 目录路径
        mode: 加载模式（lazy/eager）
        language: 语言（zh/en）

    Returns:
        构建的 Prompt
    """
    return SkillPromptBuilder.build_from_skill_dir(skills_dir, mode, language)


def build_skills_instructions(language: str = "zh") -> str:
    """
    构建 Skills 使用指令（便捷函数）

    Args:
        language: 语言（zh/en）

    Returns:
        系统指令文本
    """
    return SkillPromptBuilder.build_lazy_instructions(language)
