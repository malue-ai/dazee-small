"""
Skill Prompt 构建器

🆕 V6.2: 借鉴 clawdbot 的延迟加载机制

核心理念：
- 只在系统 Prompt 中注入 Skills 列表（name + description + location）
- Agent 根据任务选择相关 Skill 后，通过 Read 工具读取完整内容
- 避免一次性加载 50+ Skills 导致 Token 爆炸

收益：
- 系统 Prompt 大小从 ~50K tokens 降至 ~5K tokens
- 每次对话节省 Token 成本 90%
- 按需加载，提升响应速度
"""

from typing import List
from pathlib import Path
from dataclasses import dataclass

from logger import get_logger

logger = get_logger(__name__)


@dataclass
class SkillSummary:
    """Skill 简要信息（用于 Prompt 注入）"""
    name: str
    description: str
    location: Path  # SKILL.md 的绝对路径
    emoji: str = ""  # 可选图标


class SkillPromptBuilder:
    """
    Skill Prompt 构建器
    
    支持两种模式：
    1. Lazy Mode（延迟加载）：仅注入 name + description + location
    2. Eager Mode（全量加载）：注入完整 SKILL.md 内容
    """
    
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
            # 构建 skill 标签
            emoji_prefix = f"{skill.emoji} " if skill.emoji else ""
            lines.append(f'  <skill name="{skill.name}" location="{skill.location}">')
            lines.append(f'    <description>{emoji_prefix}{skill.description}</description>')
            lines.append('  </skill>')
        
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
        
        logger.debug(f"构建全量加载 Skills Prompt: {len(skills_content)} 个技能, {len(prompt)} 字符")
        
        return prompt
    
    @classmethod
    def build_from_skill_dir(
        cls,
        skills_dir: Path,
        mode: str = "lazy",
        language: str = "zh",
    ) -> str:
        """
        从 Skills 目录构建 Prompt
        
        Args:
            skills_dir: Skills 目录路径
            mode: 加载模式（lazy/eager）
            language: 语言（zh/en）
        
        Returns:
            构建的 Prompt
        """
        if not skills_dir.exists():
            logger.warning(f"Skills 目录不存在: {skills_dir}")
            return ""
        
        # 扫描 SKILL.md 文件
        skill_files = list(skills_dir.glob("*/SKILL.md"))
        
        if not skill_files:
            logger.info(f"未找到 Skills: {skills_dir}")
            return ""
        
        if mode == "lazy":
            # 延迟加载：只读取 frontmatter
            summaries = []
            for skill_file in skill_files:
                summary = cls._parse_skill_summary(skill_file)
                if summary:
                    summaries.append(summary)
            
            return cls.build_lazy_prompt(summaries, language)
        
        else:
            # 全量加载：读取完整内容
            skills_content = []
            for skill_file in skill_files:
                skill_name = skill_file.parent.name
                try:
                    content = skill_file.read_text(encoding="utf-8")
                    skills_content.append((skill_name, content))
                except Exception as e:
                    logger.warning(f"读取 {skill_file} 失败: {e}")
            
            return cls.build_eager_prompt(skills_content, language)
    
    @staticmethod
    def _parse_skill_summary(skill_file: Path) -> SkillSummary | None:
        """
        解析 SKILL.md frontmatter 提取简要信息
        
        Args:
            skill_file: SKILL.md 文件路径
        
        Returns:
            SkillSummary 或 None
        """
        try:
            content = skill_file.read_text(encoding="utf-8")
            
            # 简单的 frontmatter 解析
            if not content.startswith("---"):
                return None
            
            # 提取 frontmatter
            parts = content.split("---", 2)
            if len(parts) < 3:
                return None
            
            frontmatter_text = parts[1]
            
            # 解析 name 和 description
            name = skill_file.parent.name
            description = ""
            emoji = ""
            
            for line in frontmatter_text.split("\n"):
                line = line.strip()
                if line.startswith("name:"):
                    name = line.split(":", 1)[1].strip().strip('"')
                elif line.startswith("description:"):
                    description = line.split(":", 1)[1].strip().strip('"')
                elif '"emoji"' in line and '":"' in line:
                    # 解析 metadata.moltbot.emoji
                    emoji_part = line.split('"emoji":', 1)[1]
                    if '"' in emoji_part:
                        emoji = emoji_part.split('"')[1]
            
            if not description:
                logger.debug(f"Skill {name} 缺少 description")
                return None
            
            return SkillSummary(
                name=name,
                description=description,
                location=skill_file.absolute(),
                emoji=emoji,
            )
        
        except Exception as e:
            logger.warning(f"解析 {skill_file} 失败: {e}")
            return None


# 便捷函数

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
