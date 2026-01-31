"""
Skill 内容加载器

职责：
1. 渐进式加载 SKILL.md 内容（Level 2）
2. 加载资源文件（Level 3）
3. 获取脚本路径

术语说明：
- Skill: 本地工作流技能（对齐 clawdbot 机制）
- 目录：skills/library/
- 机制：系统提示词注入，Agent 按需读取 SKILL.md

设计原则（借鉴 clawdbot）：
- 渐进式加载：按需加载，减少启动时间
- 缓存机制：避免重复加载
- File is Everything：所有知识存储在文件中
- Progressive Disclosure：metadata → SKILL.md body → scripts/resources
"""

from typing import Dict, Optional, List
from pathlib import Path
from dataclasses import dataclass, field


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
    
    设计理念（对齐 clawdbot）：
    - Level 1: Metadata（name + description）- 始终在 context 中
    - Level 2: SKILL.md body - 当 skill 被触发时加载
    - Level 3: scripts/resources - 按需加载
    
    使用方式：
        loader = SkillLoader()
        
        # 从 Registry 获取 Skill 的路径
        skill_cap = registry.get("slidespeak-generator")
        skill_path = skill_cap.skill_path
        
        # 加载内容
        content = loader.load_skill_content(skill_path)
        resources = loader.load_skill_resources(skill_path)
        scripts = loader.get_skill_scripts(skill_path)
    """
    
    def __init__(self):
        """初始化 Skill 加载器"""
        self._cache: Dict[str, SkillInfo] = {}
    
    def load_skill_content(self, skill_path: str) -> Optional[str]:
        """
        加载 SKILL.md 完整内容（Level 2）
        
        Args:
            skill_path: Skill 目录路径（从 Capability.skill_path 获取）
            
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
            print(f"⚠️ SKILL.md not found: {skill_path}")
            return None
        
        try:
            content = skill_md.read_text(encoding='utf-8')
            
            # 缓存
            if skill_path not in self._cache:
                self._cache[skill_path] = SkillInfo(
                    name=Path(skill_path).name,
                    skill_path=skill_path
                )
            
            self._cache[skill_path].skill_md_content = content
            self._cache[skill_path].content_loaded = True
            
            return content
        except Exception as e:
            print(f"⚠️ Failed to load {skill_md}: {e}")
            return None
    
    def load_skill_resources(self, skill_path: str) -> Dict[str, str]:
        """
        加载 Skill 资源文件（Level 3）
        
        支持两个目录（对齐 clawdbot）：
        - resources/: 兼容现有资源目录
        - references/: clawdbot 风格的参考文档
        
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
        
        # 加载 resources/ 目录
        resources_dir = Path(skill_path) / "resources"
        if resources_dir.exists():
            for file in resources_dir.iterdir():
                if file.is_file():
                    try:
                        resources[file.name] = file.read_text(encoding='utf-8')
                    except Exception as e:
                        print(f"⚠️ Failed to read {file}: {e}")
        
        # 加载 references/ 目录（clawdbot 风格）
        references_dir = Path(skill_path) / "references"
        if references_dir.exists():
            for file in references_dir.iterdir():
                if file.is_file():
                    try:
                        resources[f"ref:{file.name}"] = file.read_text(encoding='utf-8')
                    except Exception as e:
                        print(f"⚠️ Failed to read {file}: {e}")
        
        # 缓存
        if skill_path not in self._cache:
            self._cache[skill_path] = SkillInfo(
                name=Path(skill_path).name,
                skill_path=skill_path
            )
        
        self._cache[skill_path].resources = resources
        self._cache[skill_path].resources_loaded = True
        
        return resources
    
    def get_skill_scripts(self, skill_path: str) -> Dict[str, str]:
        """
        获取 Skill 脚本文件路径
        
        Args:
            skill_path: Skill 目录路径
            
        Returns:
            脚本文件字典 {script_name: path}
        """
        scripts = {}
        scripts_dir = Path(skill_path) / "scripts"
        
        if scripts_dir.exists():
            for file in scripts_dir.iterdir():
                if file.is_file() and file.suffix in ('.py', '.sh'):
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
    
    def preload_skill(self, skill_path: str) -> SkillInfo:
        """
        预加载 Skill 的所有内容
        
        Args:
            skill_path: Skill 目录路径
            
        Returns:
            完全加载的 SkillInfo
        """
        # 加载所有内容
        self.load_skill_content(skill_path)
        self.load_skill_resources(skill_path)
        
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
            "resources_loaded": resources_loaded
        }


# ==================== 便捷函数 ====================

def create_skill_loader() -> SkillLoader:
    """
    创建 Skill 加载器
    
    Returns:
        SkillLoader 实例
    """
    return SkillLoader()
