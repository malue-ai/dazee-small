"""
Skills Metadata Loader

自动扫描 skills/library/ 目录，提取 YAML frontmatter，
生成系统提示词中的 Skills 列表（Level 1: Metadata 预加载）

设计理念（对齐 clawdbot）：
- Skills 是模块化、自包含的知识包，扩展 Agent 能力
- 通过 SKILL.md 文件声明，frontmatter 定义元数据
- 系统提示词注入，Agent 按需读取 SKILL.md 内容

三级加载机制：
1. Metadata（name + description）- 始终在 context 中（~100 words）
2. SKILL.md body - 当 skill 被触发时加载（<5k words）
3. scripts/resources - 按需加载（无限制）
"""

import os
import yaml
from pathlib import Path
from typing import List, Dict, Any, Optional

# ======================================================================
# 缓存机制 - 避免重复扫描和打印
# ======================================================================
_SKILLS_CACHE: Dict[str, str] = {}
_SCAN_VERBOSE: bool = True  # 第一次扫描时显示详细信息


def extract_skill_metadata(skill_md_path: str) -> Dict[str, Any]:
    """
    从 SKILL.md 提取 YAML frontmatter
    
    Args:
        skill_md_path: SKILL.md 文件路径
        
    Returns:
        {
            "name": "skill-name",
            "description": "Skill description...",
            "metadata": {...}  # 可选的额外元数据
        }
    """
    with open(skill_md_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查是否有 YAML frontmatter
    if not content.startswith('---'):
        raise ValueError(f"SKILL.md must start with YAML frontmatter: {skill_md_path}")
    
    # 提取 YAML 部分
    yaml_end = content.find('---', 3)
    if yaml_end == -1:
        raise ValueError(f"Invalid YAML frontmatter in: {skill_md_path}")
    
    yaml_content = content[3:yaml_end].strip()
    frontmatter = yaml.safe_load(yaml_content)
    
    # 验证必需字段（对齐 clawdbot）
    if "name" not in frontmatter:
        raise ValueError(f"Missing 'name' in SKILL.md: {skill_md_path}")
    if "description" not in frontmatter:
        raise ValueError(f"Missing 'description' in SKILL.md: {skill_md_path}")
    
    return {
        "name": frontmatter["name"],
        "description": frontmatter["description"],
        "metadata": frontmatter.get("metadata", {})
    }


def scan_skills_directory(skills_dir: str, verbose: bool = True) -> List[Dict[str, Any]]:
    """
    扫描 skills 目录，收集所有 Skills 的 metadata
    
    Args:
        skills_dir: skills 目录路径（如 "/skills/library"）
        verbose: 是否打印详细信息
        
    Returns:
        [
            {
                "name": "planning-task",
                "description": "Generates structured task plans...",
                "location": "/path/to/skills/library/planning-task/SKILL.md"
            },
            ...
        ]
    """
    skills_path = Path(skills_dir)
    
    if not skills_path.exists():
        raise ValueError(f"Skills directory not found: {skills_dir}")
    
    skills_metadata = []
    
    # 扫描每个子目录
    for skill_dir in skills_path.iterdir():
        if not skill_dir.is_dir():
            continue
        
        # 跳过特殊目录
        if skill_dir.name.startswith('_') or skill_dir.name == '__pycache__':
            continue
        
        # 查找 SKILL.md
        skill_md_path = skill_dir / "SKILL.md"
        
        if not skill_md_path.exists():
            if verbose:
                print(f"Warning: No SKILL.md found in {skill_dir.name}, skipping...")
            continue
        
        try:
            metadata = extract_skill_metadata(str(skill_md_path))
            
            skills_metadata.append({
                "name": metadata["name"],
                "description": metadata["description"],
                "location": str(skill_md_path),
                "metadata": metadata.get("metadata", {})
            })
            
            if verbose:
                print(f"✅ Loaded Skill: {metadata['name']}")
            
        except Exception as e:
            if verbose:
                print(f"❌ Error loading {skill_dir.name}: {e}")
            continue
    
    return skills_metadata


def generate_skills_section(skills: List[Dict[str, Any]]) -> str:
    """
    生成系统提示词中的 Skills 列表部分（XML 格式，对齐 clawdbot）
    
    Args:
        skills: Skills 元数据列表
        
    Returns:
        系统提示词片段（XML 格式）
    """
    if not skills:
        return "<available_skills>\n  <!-- No skills currently loaded -->\n</available_skills>"
    
    lines = []
    lines.append("<available_skills>")
    
    for skill in skills:
        lines.append(f'  <skill name="{skill["name"]}" location="{skill["location"]}">')
        lines.append(f'    <description>{skill["description"]}</description>')
        lines.append(f'  </skill>')
    
    lines.append("</available_skills>")
    
    return "\n".join(lines)


def generate_skills_instructions() -> str:
    """
    生成 Skills 使用说明（对齐 clawdbot 风格）
    
    Returns:
        使用说明文本
    """
    return """## Skills (mandatory)

Before replying: scan <available_skills> <description> entries.

- If exactly one skill clearly applies: read its SKILL.md with Read tool, then follow it.
- If multiple could apply: choose the most specific one, then read/follow it.
- If none clearly apply: do not read any SKILL.md.

Constraints: never read more than one skill up front; only read after selecting."""


def load_skills_for_system_prompt(
    skills_dir: str,
    use_cache: bool = True,
    include_instructions: bool = True
) -> str:
    """
    便捷函数：扫描 skills 目录并生成系统提示词片段
    
    Args:
        skills_dir: skills 目录路径
        use_cache: 是否使用缓存（避免重复扫描）
        include_instructions: 是否包含使用说明
        
    Returns:
        完整的 Skills 部分，可直接注入系统提示词
        
    Example:
        >>> skills_section = load_skills_for_system_prompt("/skills/library")
        >>> full_system_prompt = BASE_PROMPT + "\\n\\n" + skills_section
    """
    global _SKILLS_CACHE, _SCAN_VERBOSE
    
    # 生成缓存键
    cache_key = f"{skills_dir}:{include_instructions}"
    
    # 检查缓存
    if use_cache and cache_key in _SKILLS_CACHE:
        return _SKILLS_CACHE[cache_key]
    
    # 第一次扫描时显示详细信息
    verbose = _SCAN_VERBOSE
    if verbose:
        print(f"📂 Scanning Skills directory: {skills_dir}")
        print()
    
    # 扫描 Skills
    skills = scan_skills_directory(skills_dir, verbose=verbose)
    
    if verbose:
        print()
        print(f"✅ Found {len(skills)} Skills")
        print()
    
    # 生成 Skills 部分
    parts = []
    
    if include_instructions:
        parts.append(generate_skills_instructions())
        parts.append("")
    
    parts.append(generate_skills_section(skills))
    
    skills_section = "\n".join(parts)
    
    if verbose:
        print(f"📝 Generated Skills section ({len(skills_section)} chars)")
    
    # 缓存结果
    _SKILLS_CACHE[cache_key] = skills_section
    
    # 后续调用不显示详细信息
    _SCAN_VERBOSE = False
    
    return skills_section


# 使用示例
if __name__ == "__main__":
    import sys
    
    # 获取项目根目录
    project_root = Path(__file__).parent.parent
    skills_dir = project_root / "skills" / "library"
    
    print("=" * 60)
    print("Skills Metadata Loader")
    print("=" * 60)
    print()
    
    try:
        skills_section = load_skills_for_system_prompt(str(skills_dir))
        
        print()
        print("=" * 60)
        print("Generated Skills Section Preview:")
        print("=" * 60)
        print()
        print(skills_section)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
