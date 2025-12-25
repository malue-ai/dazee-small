"""
Skills管理器 - 管理Skills的发现、加载和元数据

职责：
1. 扫描和发现本地Skills
2. 加载Skill内容（渐进式）
3. 生成Skills metadata供System Prompt使用

设计原则：
- 渐进式加载：Level 1 (metadata) → Level 2 (SKILL.md) → Level 3 (resources)
- File is Everything：所有知识存储在文件中
- 与CapabilityRegistry配合使用

参考文档：
- docs/v3/03-SKILLS-DISCOVERY.md
- claude-cookbook/skills/skill_utils.py
"""

from typing import Dict, List, Optional, Any
from pathlib import Path
from dataclasses import dataclass
import yaml


@dataclass
class SkillInfo:
    """Skill信息"""
    name: str
    description: str
    path: str
    priority: str
    preferred_for: List[str]
    keywords: List[str]
    
    # 加载状态
    metadata_loaded: bool = True
    content_loaded: bool = False
    resources_loaded: bool = False
    
    # 缓存内容
    skill_md_content: Optional[str] = None
    resources: Dict[str, str] = None


class SkillsManager:
    """
    Skills管理器
    
    管理Skills的发现、加载和元数据
    """
    
    def __init__(self, skills_dir: str = None, verbose: bool = False):
        """
        初始化Skills管理器
        
        Args:
            skills_dir: Skills目录路径
            verbose: 是否输出详细日志
        """
        self.verbose = verbose
        self.skills_dir = Path(skills_dir) if skills_dir else self._default_skills_dir()
        self.skills: Dict[str, SkillInfo] = {}
        self._scan_skills()
    
    def _default_skills_dir(self) -> Path:
        """获取默认Skills目录（使用绝对路径确保可靠性）"""
        # 获取项目根目录（main.py 所在目录）
        project_root = Path(__file__).parent.parent
        skills_dir = project_root / "skills" / "library"
        
        if self.verbose:
            print(f"📂 Scanning Custom Skills directory: {skills_dir.absolute()}")
        
        return skills_dir
    
    def _scan_skills(self):
        """扫描Skills目录，加载Level 1 metadata"""
        if not self.skills_dir.exists():
            print(f"⚠️ Skills加载失败: Skills directory not found: {self.skills_dir.absolute()}")
            return
        
        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            
            # 解析SKILL.md的YAML frontmatter
            metadata = self._parse_skill_metadata(skill_md)
            if metadata:
                skill_name = metadata.get('name', skill_dir.name)
                self.skills[skill_name] = SkillInfo(
                    name=skill_name,
                    description=metadata.get('description', ''),
                    path=str(skill_dir),
                    priority=metadata.get('priority', 'medium'),
                    preferred_for=metadata.get('preferred_for', []),
                    keywords=metadata.get('keywords', [])
                )
    
    def _parse_skill_metadata(self, skill_md: Path) -> Optional[Dict]:
        """解析SKILL.md的YAML frontmatter"""
        try:
            content = skill_md.read_text(encoding='utf-8')
        except Exception as e:
            print(f"⚠️ Warning: Failed to read {skill_md}: {e}")
            return None
        
        if not content.startswith('---'):
            return None
        
        try:
            # 查找第二个 ---
            end_idx = content.index('---', 3)
            frontmatter = content[3:end_idx].strip()
            return yaml.safe_load(frontmatter)
        except Exception as e:
            print(f"⚠️ Warning: Failed to parse YAML from {skill_md}: {e}")
            return None
    
    # ==================== 查询接口 ====================
    
    def get_skill(self, name: str) -> Optional[SkillInfo]:
        """
        获取Skill信息
        
        Args:
            name: Skill名称
            
        Returns:
            SkillInfo或None
        """
        return self.skills.get(name)
    
    def list_skills(self) -> List[str]:
        """列出所有可用Skills"""
        return list(self.skills.keys())
    
    def find_by_keyword(self, keyword: str) -> List[SkillInfo]:
        """
        按关键词查找Skills
        
        Args:
            keyword: 关键词
            
        Returns:
            匹配的Skills列表
        """
        keyword_lower = keyword.lower()
        results = []
        
        for skill in self.skills.values():
            # 检查keywords
            if any(keyword_lower in kw.lower() for kw in skill.keywords):
                results.append(skill)
                continue
            
            # 检查preferred_for
            if any(keyword_lower in pf.lower() for pf in skill.preferred_for):
                results.append(skill)
                continue
            
            # 检查description
            if keyword_lower in skill.description.lower():
                results.append(skill)
        
        return results
    
    # ==================== 加载接口 ====================
    
    def load_skill_content(self, name: str) -> Optional[str]:
        """
        加载Skill的完整内容（Level 2）
        
        Args:
            name: Skill名称
            
        Returns:
            SKILL.md的完整内容
        """
        skill = self.skills.get(name)
        if not skill:
            return None
        
        # 检查缓存
        if skill.content_loaded and skill.skill_md_content:
            return skill.skill_md_content
        
        # 加载内容
        skill_md = Path(skill.path) / "SKILL.md"
        try:
            content = skill_md.read_text(encoding='utf-8')
            skill.skill_md_content = content
            skill.content_loaded = True
            return content
        except Exception as e:
            print(f"⚠️ Warning: Failed to load {skill_md}: {e}")
            return None
    
    def load_skill_resources(self, name: str) -> Dict[str, str]:
        """
        加载Skill的资源文件（Level 3）
        
        Args:
            name: Skill名称
            
        Returns:
            资源文件字典 {filename: content}
        """
        skill = self.skills.get(name)
        if not skill:
            return {}
        
        # 检查缓存
        if skill.resources_loaded and skill.resources:
            return skill.resources
        
        # 加载资源
        resources = {}
        resources_dir = Path(skill.path) / "resources"
        
        if resources_dir.exists():
            for file in resources_dir.iterdir():
                if file.is_file():
                    try:
                        resources[file.name] = file.read_text(encoding='utf-8')
                    except Exception as e:
                        print(f"⚠️ Warning: Failed to read {file}: {e}")
        
        skill.resources = resources
        skill.resources_loaded = True
        return resources
    
    def get_skill_scripts(self, name: str) -> Dict[str, str]:
        """
        获取Skill的脚本文件路径
        
        Args:
            name: Skill名称
            
        Returns:
            脚本文件字典 {script_name: path}
        """
        skill = self.skills.get(name)
        if not skill:
            return {}
        
        scripts = {}
        scripts_dir = Path(skill.path) / "scripts"
        
        if scripts_dir.exists():
            for file in scripts_dir.iterdir():
                if file.is_file() and file.suffix == '.py':
                    scripts[file.stem] = str(file)
        
        return scripts
    
    # ==================== 元数据生成 ====================
    
    def generate_skills_metadata_for_prompt(self) -> str:
        """
        生成Skills元数据用于System Prompt（Level 1）
        
        Returns:
            Markdown格式的Skills列表
        """
        if not self.skills:
            return "No custom skills available."
        
        lines = ["## 🎯 Available Custom Skills\n"]
        
        for name, skill in sorted(self.skills.items()):
            lines.append(f"### {name}")
            lines.append(f"- **Description**: {skill.description}")
            lines.append(f"- **Location**: `{skill.path}/`")
            lines.append(f"- **Priority**: {skill.priority}")
            
            if skill.preferred_for:
                lines.append(f"- **Use when**: {', '.join(skill.preferred_for)}")
            
            if skill.keywords:
                lines.append(f"- **Keywords**: {', '.join(skill.keywords)}")
            
            lines.append("")
        
        lines.append("---")
        lines.append("To use a skill, first load its SKILL.md with `bash cat <location>/SKILL.md`")
        
        return "\n".join(lines)
    
    def get_skills_summary(self) -> Dict[str, Any]:
        """
        获取Skills摘要信息
        
        Returns:
            摘要字典
        """
        return {
            'total_skills': len(self.skills),
            'skills': [
                {
                    'name': s.name,
                    'description': s.description[:100] + '...' if len(s.description) > 100 else s.description,
                    'priority': s.priority
                }
                for s in self.skills.values()
            ]
        }


# ==================== 便捷函数 ====================

def create_skills_manager(skills_dir: str = None) -> SkillsManager:
    """
    创建Skills管理器
    
    Args:
        skills_dir: Skills目录路径
        
    Returns:
        配置好的SkillsManager实例
    """
    return SkillsManager(skills_dir=skills_dir)

