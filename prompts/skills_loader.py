"""
Skills Metadata Loader

自动扫描skills目录，提取YAML frontmatter，
生成系统提示词中的Skills列表（Level 1: Metadata预加载）

根据Claude官方文档：
https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview#how-skills-work

包含两类Skills：
1. Pre-built Skills（Claude官方提供）：pptx, xlsx, docx, pdf等
2. Custom Skills（用户定制）：从skills/library目录扫描
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


# ======================================================================
# Pre-built Skills（Anthropic官方提供）
# ======================================================================
# 参考：https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview#available-skills

PREBUILT_SKILLS = [
    {
        "name": "pptx",
        "description": "Create presentations, edit slides, analyze presentation content. Use when working with PowerPoint files or when the user mentions presentations, slides, or PPT files.",
        "provider": "Anthropic",
        "type": "pre-built"
    },
    {
        "name": "xlsx",
        "description": "Create spreadsheets, analyze data, generate reports with charts. Use when working with Excel files or when the user mentions spreadsheets, data analysis, or XLS files.",
        "provider": "Anthropic",
        "type": "pre-built"
    },
    {
        "name": "docx",
        "description": "Create documents, edit content, format text. Use when working with Word files or when the user mentions documents or DOC files.",
        "provider": "Anthropic",
        "type": "pre-built"
    },
    {
        "name": "pdf",
        "description": "Generate formatted PDF documents and reports. Use when the user needs PDF output.",
        "provider": "Anthropic",
        "type": "pre-built"
    }
]


def extract_skill_metadata(skill_md_path: str) -> Dict[str, str]:
    """
    从SKILL.md提取YAML frontmatter（包括priority和preferred_for）
    
    Args:
        skill_md_path: SKILL.md文件路径
        
    Returns:
        {
            "name": "skill-name",
            "description": "Skill description...",
            "priority": "high|medium|low",
            "preferred_for": ["keyword1", "keyword2", ...]
        }
    """
    with open(skill_md_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查是否有YAML frontmatter
    if not content.startswith('---'):
        raise ValueError(f"SKILL.md must start with YAML frontmatter: {skill_md_path}")
    
    # 提取YAML部分
    yaml_end = content.find('---', 3)
    if yaml_end == -1:
        raise ValueError(f"Invalid YAML frontmatter in: {skill_md_path}")
    
    yaml_content = content[3:yaml_end].strip()
    metadata = yaml.safe_load(yaml_content)
    
    # 验证必需字段
    if "name" not in metadata:
        raise ValueError(f"Missing 'name' in SKILL.md: {skill_md_path}")
    if "description" not in metadata:
        raise ValueError(f"Missing 'description' in SKILL.md: {skill_md_path}")
    
    return {
        "name": metadata["name"],
        "description": metadata["description"],
        "priority": metadata.get("priority", "medium"),
        "preferred_for": metadata.get("preferred_for", [])
    }


def scan_skills_directory(skills_dir: str, verbose: bool = True) -> List[Dict[str, Any]]:
    """
    扫描skills目录，收集所有Skills的metadata
    
    Args:
        skills_dir: skills目录路径（如 "agent_v3/skills/library"）
        verbose: 是否打印详细信息
        
    Returns:
        [
            {
                "name": "planning-task",
                "description": "Generates structured task plans...",
                "location": "skills/planning-task/"
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
        
        # 检查SKILL.md
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
                "location": f"agent_v3/skills/library/{skill_dir.name}/",
                "priority": metadata.get("priority", "medium"),
                "preferred_for": metadata.get("preferred_for", [])
            })
            
            if verbose:
                priority_emoji = {"high": "🥇", "medium": "🥈", "low": "🥉"}.get(metadata.get("priority", "medium"), "")
                print(f"✅ Loaded Skill: {metadata['name']} {priority_emoji}")
            
        except Exception as e:
            if verbose:
                print(f"❌ Error loading {skill_dir.name}: {e}")
            continue
    
    return skills_metadata


def generate_skills_section(
    custom_skills: List[Dict[str, Any]],
    include_prebuilt: bool = True
) -> str:
    """
    生成系统提示词中的Skills列表部分（Pre-built + Custom）
    
    根据Claude官方文档，这是Level 1: Metadata（总是加载）
    
    Args:
        custom_skills: 用户自定义Skills列表
        include_prebuilt: 是否包含官方Pre-built Skills
        
    Returns:
        系统提示词片段（Markdown格式）
    """
    lines = []
    lines.append("# Available Skills")
    lines.append("")
    
    total = len(PREBUILT_SKILLS) + len(custom_skills) if include_prebuilt else len(custom_skills)
    
    if total == 0:
        return "# Available Skills\n\nNo Skills currently loaded.\n"
    
    lines.append(f"You have access to {total} specialized Skills. "
                 "Use them when relevant to the user's request:")
    lines.append("")
    
    # ==================== Pre-built Skills ====================
    if include_prebuilt:
        lines.append("## Pre-built Skills (Anthropic Official)")
        lines.append("")
        lines.append("These Skills are provided by Anthropic and work automatically:")
        lines.append("")
        
        for skill in PREBUILT_SKILLS:
            lines.append(f"### Skill: {skill['name']}")
            lines.append(f"**Description**: {skill['description']}")
            lines.append(f"**Provider**: {skill['provider']}")
            lines.append(f"**Type**: Pre-built (no SKILL.md needed, use directly)")
            lines.append("")
        
        lines.append("---")
        lines.append("")
    
    # ==================== Custom Skills ====================
    if custom_skills:
        lines.append("## Custom Skills (User Defined)")
        lines.append("")
        lines.append("These Skills are custom-built for specific workflows:")
        lines.append("")
        
        # 按priority排序：high → medium → low
        priority_order = {"high": 0, "medium": 1, "low": 2}
        custom_skills_sorted = sorted(
            custom_skills,
            key=lambda s: priority_order.get(s.get("priority", "medium"), 1)
        )
        
        for skill in custom_skills_sorted:
            # 优先级标识
            priority_emoji = {
                "high": "🥇",
                "medium": "🥈",
                "low": "🥉"
            }.get(skill.get("priority", "medium"), "🥈")
            
            priority_label = skill.get("priority", "medium").capitalize()
            
            lines.append(f"### Skill: {skill['name']} {priority_emoji}")
            lines.append(f"**Description**: {skill['description']}")
            lines.append(f"**Priority**: {priority_label}")
            
            # 显示preferred_for（优先使用场景）
            if skill.get("preferred_for"):
                preferred_text = ", ".join(skill["preferred_for"])
                lines.append(f"**Preferred for**: {preferred_text}")
            
            lines.append(f"**Location**: {skill['location']}")
            lines.append(f"**Type**: Custom (read SKILL.md for instructions)")
            lines.append("")
            lines.append("```bash")
            lines.append(f"# Load this Skill's instructions")
            lines.append(f"cat {skill['location']}SKILL.md")
            lines.append("```")
            lines.append("")
    
    # ==================== Usage Guidelines ====================
    lines.append("---")
    lines.append("")
    lines.append("# Skills Usage Guidelines")
    lines.append("")
    
    if include_prebuilt:
        lines.append("## For Pre-built Skills (pptx, xlsx, docx, pdf)")
        lines.append("")
        lines.append("These Skills work automatically without needing to read SKILL.md:")
        lines.append("- They have standard workflows built-in")
        lines.append("- Just use them naturally in your tasks")
        lines.append("- Example: 'Create a presentation about AI' will automatically use the pptx Skill")
        lines.append("")
    
    if custom_skills:
        lines.append("## For Custom Skills (planning-task, slidespeak-generator, etc.)")
        lines.append("")
        lines.append("These require loading their SKILL.md for detailed instructions:")
        lines.append("")
        lines.append("1. **Identify**: Check the Skills list above")
        lines.append("2. **Load**: Use `bash: cat agent_v3/skills/library/<skill-name>/SKILL.md`")
        lines.append("3. **Follow**: Execute the workflow in SKILL.md")
        lines.append("4. **Access resources**: Load scripts/ and resources/ as directed")
        lines.append("")
        lines.append("**Example workflow**:")
        lines.append("```bash")
        lines.append("# 1. Load Skill instructions")
        lines.append("cat agent_v3/skills/library/slidespeak-generator/SKILL.md")
        lines.append("")
        lines.append("# 2. Load API schema (if needed)")
        lines.append("cat agent_v3/skills/library/slidespeak-generator/resources/api_schema.json")
        lines.append("")
        lines.append("# 3. Execute helper script")
        lines.append("cd agent_v3/skills/library/slidespeak-generator && python -c \"")
        lines.append("exec(open('scripts/config_builder.py').read())")
        lines.append("config = build_slidespeak_config(topic='AI Product', pages=5)")
        lines.append("print(config)")
        lines.append("\"")
        lines.append("```")
        lines.append("")
    
    lines.append("## Runtime Environments vs Skills")
    lines.append("")
    lines.append("**Important**: Bash, Python, Nodejs are NOT Skills.")
    lines.append("- They are runtime environments in the VM")
    lines.append("- Access them via code_execution tool")
    lines.append("- No discovery or loading needed")
    lines.append("")
    
    # 添加优先级路由规则
    lines.append("## Priority and Routing Rules")
    lines.append("")
    lines.append("When multiple Skills can accomplish the same task:")
    lines.append("")
    lines.append("1. **Check explicit mentions**: If user mentions a specific Skill/Tool name, use it")
    lines.append("2. **Apply keyword matching**: Match user keywords with Skill's 'preferred_for' list")
    lines.append("3. **Follow priority order**: High (🥇) > Medium (🥈) > Low (🥉)")
    lines.append("4. **Consider context**: Continue with same Skill for iterations/refinements")
    lines.append("")
    lines.append("**Example: PPT Generation**")
    lines.append("```")
    lines.append('User: "创建产品介绍PPT"')
    lines.append("→ Keywords: 产品介绍 (implies professional/business)")
    lines.append("→ Available: slidespeak-generator (High, preferred_for: 'professional PPT')")
    lines.append("→ Decision: Use slidespeak-generator (priority + keyword match)")
    lines.append("")
    lines.append('User: "快速生成PPT草稿"')
    lines.append("→ Keywords: 快速, 草稿 (implies quick/simple)")
    lines.append("→ Available: pptx (Pre-built, faster and simpler)")
    lines.append("→ Decision: Use pptx (better fit for quick draft)")
    lines.append("```")
    lines.append("")
    lines.append("**Decision Protocol**:")
    lines.append("Use Extended Thinking to evaluate options when multiple Skills are available.")
    lines.append("")
    lines.append("**Remember**: Skills provide expertise, Tools provide execution. Use them together.")
    lines.append("")
    
    return "\n".join(lines)


def load_skills_for_system_prompt(
    skills_dir: str,
    include_prebuilt: bool = True,
    use_cache: bool = True
) -> str:
    """
    便捷函数：扫描skills目录并生成系统提示词片段（包含Pre-built + Custom）
    
    Args:
        skills_dir: skills目录路径
        include_prebuilt: 是否包含官方Pre-built Skills
        use_cache: 是否使用缓存（避免重复扫描）
        
    Returns:
        完整的Skills部分，可直接注入系统提示词
        
    Example:
        >>> skills_section = load_skills_for_system_prompt("agent_v3/skills/library")
        >>> full_system_prompt = BASE_PROMPT + "\n\n" + skills_section
    """
    global _SKILLS_CACHE, _SCAN_VERBOSE
    
    # 生成缓存键
    cache_key = f"{skills_dir}:{include_prebuilt}"
    
    # 检查缓存
    if use_cache and cache_key in _SKILLS_CACHE:
        return _SKILLS_CACHE[cache_key]
    
    # 第一次扫描时显示详细信息
    verbose = _SCAN_VERBOSE
    if verbose:
        print(f"📂 Scanning Custom Skills directory: {skills_dir}")
        print()
    
    # 扫描Custom Skills
    custom_skills = scan_skills_directory(skills_dir, verbose=verbose)
    
    if verbose:
        print()
        if include_prebuilt:
            print(f"✅ Found {len(PREBUILT_SKILLS)} Pre-built Skills + {len(custom_skills)} Custom Skills")
        else:
            print(f"✅ Found {len(custom_skills)} Custom Skills")
        print()
    
    # 生成完整列表
    skills_section = generate_skills_section(custom_skills, include_prebuilt)
    
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
    project_root = Path(__file__).parent.parent.parent
    skills_dir = project_root / "agent_v3" / "skills" / "library"
    
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
        print(skills_section[:1000] + "...")
        
        # 保存到文件（可选）
        output_file = project_root / "agent_v3" / "prompts" / "skills_metadata.txt"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(skills_section)
        
        print()
        print(f"✅ Full output saved to: {output_file}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

