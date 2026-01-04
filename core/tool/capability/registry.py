"""
能力注册表 - 统一管理所有能力

职责：
1. 从 capabilities.yaml 加载能力配置
2. 扫描 skills/library/ 发现 Skills
3. 提供能力查询接口
4. 支持动态注册新能力

设计原则：
- 配置驱动：所有能力从 YAML 配置加载
- 统一抽象：Skills/Tools/MCP/Code 统一为 Capability
- 易于扩展：支持动态注册
"""

from typing import Dict, List, Optional, Any
from pathlib import Path
import yaml

from .types import Capability, CapabilityType


class CapabilityRegistry:
    """
    统一能力注册表
    
    管理所有能力（Skills/Tools/MCP/Code）
    从 capabilities.yaml 加载配置，同时扫描 skills/library/ 发现 Skills
    """
    
    def __init__(
        self,
        config_path: Optional[str] = None,
        skills_dir: Optional[str] = None
    ):
        """
        初始化能力注册表
        
        Args:
            config_path: 配置文件路径，默认为 /config/capabilities.yaml
            skills_dir: Skills 目录路径，默认为 /skills/library/
        """
        self.capabilities: Dict[str, Capability] = {}
        self.categories: List[Dict[str, Any]] = []
        self.task_type_mappings: Dict[str, List[str]] = {}
        
        self._config_path = config_path or self._default_config_path()
        self._skills_dir = skills_dir or self._default_skills_dir()
        
        # 加载 Tools/MCP 配置
        self._load_config()
        
        # 扫描 Skills
        self._scan_skills()
    
    def _default_config_path(self) -> str:
        """获取默认配置文件路径"""
        return str(Path(__file__).parent.parent.parent.parent / "config" / "capabilities.yaml")
    
    def _default_skills_dir(self) -> str:
        """获取默认 Skills 目录"""
        return str(Path(__file__).parent.parent.parent.parent / "skills" / "library")
    
    def _load_config(self):
        """从 YAML 配置文件加载能力"""
        config_path = Path(self._config_path)
        
        if not config_path.exists():
            print(f"⚠️ Warning: Config file not found: {self._config_path}")
            return
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
        except Exception as e:
            print(f"⚠️ Warning: Failed to load config: {e}")
            return
        
        # 加载任务类型映射
        self.task_type_mappings = config.get('task_type_mappings', {})
        if self.task_type_mappings:
            print(f"✅ Loaded task type mappings for {len(self.task_type_mappings)} types")
        
        # 加载能力分类定义
        self.categories = config.get('capability_categories', [])
        if self.categories:
            category_ids = [cat['id'] for cat in self.categories]
            print(f"✅ Loaded {len(self.categories)} capability categories: {', '.join(category_ids)}")
        
        # 加载每个能力
        for cap_data in config.get('capabilities', []):
            try:
                capability = self._parse_capability(cap_data)
                self.capabilities[capability.name] = capability
            except Exception as e:
                print(f"⚠️ Warning: Failed to parse capability {cap_data.get('name', 'unknown')}: {e}")
    
    def _parse_capability(self, data: Dict) -> Capability:
        """解析能力配置"""
        metadata = data.get('metadata', {})
        if 'implementation' in data:
            metadata['implementation'] = data['implementation']
        
        return Capability(
            name=data['name'],
            type=CapabilityType(data['type']),
            subtype=data.get('subtype', 'CUSTOM'),
            provider=data.get('provider', 'unknown'),
            capabilities=data.get('capabilities', []),
            priority=data.get('priority', 50),
            cost=data.get('cost', {'time': 'medium', 'money': 'free'}),
            constraints=data.get('constraints', {}),
            metadata=metadata,
            input_schema=data.get('input_schema')
        )
    
    def _scan_skills(self):
        """
        扫描 Skills 目录
        
        将 Skills 注册为 Capability(type=SKILL)
        """
        skills_dir = Path(self._skills_dir)
        
        if not skills_dir.exists():
            print(f"⚠️ Skills directory not found: {skills_dir}")
            return
        
        skill_count = 0
        for skill_dir in skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            
            # 解析 YAML frontmatter
            metadata = self._parse_skill_frontmatter(skill_md)
            if not metadata:
                continue
            
            # 注册为 Capability
            skill_name = metadata.get('name', skill_dir.name)
            
            # 跳过已经在 capabilities.yaml 中定义的
            if skill_name in self.capabilities:
                continue
            
            self.capabilities[skill_name] = Capability(
                name=skill_name,
                type=CapabilityType.SKILL,
                subtype="CUSTOM",
                provider="local",
                capabilities=metadata.get('capabilities', []),
                priority=self._parse_priority(metadata.get('priority', 'medium')),
                cost={'time': 'medium', 'money': 'free'},
                constraints={},
                metadata={
                    'description': metadata.get('description', ''),
                    'keywords': metadata.get('keywords', []),
                    'preferred_for': metadata.get('preferred_for', []),
                    'skill_path': str(skill_dir)  # 保存路径供 SkillLoader 使用
                }
            )
            skill_count += 1
        
        if skill_count > 0:
            print(f"✅ Scanned {skill_count} skills from {skills_dir}")
    
    def _parse_skill_frontmatter(self, skill_md: Path) -> Optional[Dict]:
        """解析 SKILL.md 的 YAML frontmatter"""
        try:
            content = skill_md.read_text(encoding='utf-8')
            if not content.startswith('---'):
                return None
            
            end_idx = content.index('---', 3)
            frontmatter = content[3:end_idx].strip()
            return yaml.safe_load(frontmatter)
        except Exception as e:
            print(f"⚠️ Failed to parse {skill_md}: {e}")
            return None
    
    def _parse_priority(self, priority_str: str) -> int:
        """将优先级字符串转换为数字"""
        priority_map = {'low': 30, 'medium': 50, 'high': 80, 'critical': 90}
        return priority_map.get(str(priority_str).lower(), 50)
    
    # ==================== 查询接口 ====================
    
    def get(self, name: str) -> Optional[Capability]:
        """
        获取指定名称的能力
        
        Args:
            name: 能力名称
            
        Returns:
            Capability 或 None
        """
        return self.capabilities.get(name)
    
    def find_by_type(self, cap_type: CapabilityType) -> List[Capability]:
        """
        按类型查找能力
        
        Args:
            cap_type: 能力类型
            
        Returns:
            匹配的能力列表
        """
        return [c for c in self.capabilities.values() if c.type == cap_type]
    
    def find_by_capability_tag(self, tag: str) -> List[Capability]:
        """
        按能力标签查找
        
        Args:
            tag: 能力标签（如 ppt_generation）
            
        Returns:
            匹配的能力列表
        """
        return [
            c for c in self.capabilities.values()
            if tag in c.capabilities
        ]
    
    def find_candidates(
        self,
        keywords: List[str],
        task_type: str = None,
        context: Dict[str, Any] = None
    ) -> List[Capability]:
        """
        根据关键词和任务类型查找候选能力
        
        Args:
            keywords: 关键词列表
            task_type: 任务类型（如 ppt_generation）
            context: 上下文（用于约束检查）
            
        Returns:
            候选能力列表（未排序）
        """
        candidates = []
        
        for cap in self.capabilities.values():
            # 过滤内部工具（除非上下文明确允许）
            if cap.constraints.get('internal_use_only'):
                if not context or not context.get('allow_internal_tools'):
                    continue
            
            # 检查约束
            if not cap.meets_constraints(context):
                continue
            
            # 检查关键词匹配
            if keywords and cap.matches_keywords(keywords) > 0:
                candidates.append(cap)
                continue
            
            # 检查任务类型匹配
            if task_type and task_type in cap.capabilities:
                candidates.append(cap)
        
        return candidates
    
    # ==================== 注册接口 ====================
    
    def register(self, capability: Capability):
        """
        动态注册新能力
        
        Args:
            capability: 要注册的能力
        """
        self.capabilities[capability.name] = capability
    
    def register_from_dict(self, data: Dict):
        """
        从字典注册新能力
        
        Args:
            data: 能力配置字典
        """
        capability = self._parse_capability(data)
        self.register(capability)
    
    # ==================== 工具接口 ====================
    
    def get_tool_schemas(self) -> List[Dict]:
        """
        获取所有工具的 Schema（用于 Claude API）
        
        Returns:
            工具 schema 列表
        """
        schemas = []
        
        for cap in self.find_by_type(CapabilityType.TOOL):
            schema = cap.to_tool_schema()
            if schema:
                schemas.append(schema)
        
        return schemas
    
    def get_skills_metadata(self) -> List[Dict]:
        """
        获取所有 Skills 的元数据（用于 System Prompt）
        
        Returns:
            Skills 元数据列表
        """
        skills = []
        
        for cap in self.find_by_type(CapabilityType.SKILL):
            skills.append({
                'name': cap.name,
                'description': cap.metadata.get('description', ''),
                'subtype': cap.subtype,
                'provider': cap.provider,
                'preferred_for': cap.metadata.get('preferred_for', []),
                'keywords': cap.metadata.get('keywords', [])
            })
        
        return skills
    
    # ==================== 能力分类接口 ====================
    
    def get_category_ids(self) -> List[str]:
        """
        获取所有分类 ID
        
        Returns:
            分类 ID 列表
        """
        return [cat['id'] for cat in self.categories]
    
    def get_categories_for_prompt(self) -> str:
        """
        生成 System Prompt 中的能力分类说明（Markdown 格式）
        
        Returns:
            Markdown 格式的分类表格
        """
        if not self.categories:
            return ""
        
        lines = [
            "## 🏷️ Available Capability Categories",
            "",
            "When creating a plan, specify which capability each step needs:",
            "",
            "| Category | Description | Use When |",
            "|----------|-------------|----------|"
        ]
        
        for cat in self.categories:
            cat_id = cat['id']
            desc = cat['description']
            use_when = cat['use_when']
            lines.append(f"| `{cat_id}` | {desc} | {use_when} |")
        
        lines.extend([
            "",
            "### Examples",
            ""
        ])
        
        for cat in self.categories:
            if 'examples' in cat:
                lines.append(f"**{cat['id']}**: {', '.join(cat['examples'])}")
        
        lines.extend([
            "",
            "⚠️ **Important**: Only specify capability categories, NOT specific tool names.",
            "The Router will automatically select the best tools for each capability."
        ])
        
        return "\n".join(lines)
    
    def get_category_description(self, category_id: str) -> Optional[str]:
        """
        获取分类描述
        
        Args:
            category_id: 分类 ID
            
        Returns:
            分类描述，或 None
        """
        for cat in self.categories:
            if cat['id'] == category_id:
                return cat['description']
        return None
    
    # ==================== 任务类型映射接口 ====================
    
    def get_capabilities_for_task_type(self, task_type: str) -> List[str]:
        """
        根据任务类型获取推荐的能力列表
        
        Args:
            task_type: 任务类型（如 information_query, content_generation）
            
        Returns:
            能力列表（capability IDs）
        """
        mapping = self.task_type_mappings.get(task_type)
        
        if mapping:
            return mapping
        
        # 如果没有找到，返回默认映射
        default_mapping = self.task_type_mappings.get("other", [])
        
        if not default_mapping:
            return ["file_operations", "code_execution", "task_planning"]
        
        return default_mapping
    
    def get_all_task_types(self) -> List[str]:
        """
        获取所有已配置的任务类型
        
        Returns:
            任务类型列表
        """
        return list(self.task_type_mappings.keys())
    
    # ==================== 信息接口 ====================
    
    def list_all(self) -> List[str]:
        """列出所有能力名称"""
        return list(self.capabilities.keys())
    
    def count_by_type(self) -> Dict[str, int]:
        """按类型统计能力数量"""
        counts = {}
        for cap_type in CapabilityType:
            counts[cap_type.value] = len(self.find_by_type(cap_type))
        return counts
    
    def summary(self) -> str:
        """生成能力注册表摘要"""
        counts = self.count_by_type()
        lines = ["CapabilityRegistry Summary:"]
        for cap_type, count in counts.items():
            lines.append(f"  - {cap_type}: {count}")
        lines.append(f"  Total: {len(self.capabilities)}")
        if self.categories:
            lines.append(f"  Categories: {len(self.categories)}")
        return "\n".join(lines)


# ==================== 便捷函数 ====================

def create_capability_registry(
    config_path: str = None,
    skills_dir: str = None
) -> CapabilityRegistry:
    """
    创建能力注册表
    
    Args:
        config_path: 配置文件路径
        skills_dir: Skills 目录路径
        
    Returns:
        配置好的 CapabilityRegistry 实例
    """
    return CapabilityRegistry(config_path=config_path, skills_dir=skills_dir)

