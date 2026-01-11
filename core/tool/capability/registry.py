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
        self._raw_capabilities: List[Dict[str, Any]] = []  # 🆕 保存原始配置数据
        
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
                self._raw_capabilities.append(cap_data)  # 🆕 保存原始配置
            except Exception as e:
                print(f"⚠️ Warning: Failed to parse capability {cap_data.get('name', 'unknown')}: {e}")
    
    def _parse_capability(self, data: Dict) -> Capability:
        """解析能力配置"""
        metadata = data.get('metadata', {})
        if 'implementation' in data:
            metadata['implementation'] = data['implementation']
        
        # 保存 compaction 配置到 metadata（供 ResultCompactor 使用）
        if 'compaction' in data:
            metadata['compaction'] = data['compaction']
        
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
            input_schema=data.get('input_schema'),
            fallback_tool=data.get('fallback_tool'),
            skill_id=data.get('skill_id'),       # Claude 返回的 Skill ID
            skill_path=data.get('skill_path'),   # Skill 本地路径
            level=data.get('level', 2),          # 🆕 工具层级：1=核心，2=动态（默认2）
            cache_stable=data.get('cache_stable', False)  # 🆕 结果是否稳定可缓存
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
    
    def find_by_level(self, level: int) -> List[Capability]:
        """
        按工具层级查找
        
        Args:
            level: 工具层级（1=核心，2=动态）
            
        Returns:
            匹配的能力列表
        """
        return [c for c in self.capabilities.values() if c.level == level]
    
    def get_core_tools(self) -> List[Capability]:
        """
        获取核心工具（Level 1）
        
        核心工具始终加载，不受动态选择影响：
        - plan_todo（任务规划）
        - bash（基础命令）
        
        Returns:
            Level 1 核心工具列表
        """
        return self.find_by_level(1)
    
    def get_dynamic_tools(self) -> List[Capability]:
        """
        获取动态工具（Level 2）
        
        动态工具按需加载，根据意图/Schema 选择：
        - exa_search（搜索）
        - e2b_python_sandbox（代码执行）
        - ppt_generator（PPT 生成）
        - ...
        
        Returns:
            Level 2 动态工具列表
        """
        return self.find_by_level(2)
    
    def get_cacheable_tools(self) -> List[str]:
        """
        获取可缓存工具名称列表
        
        cache_stable=true 的工具，同输入产生同输出，
        可安全使用 prompt cache。
        
        Returns:
            可缓存工具名称列表
        """
        return [
            c.name for c in self.capabilities.values()
            if c.cache_stable
        ]
    
    def filter_by_enabled(
        self, 
        enabled_map: Dict[str, bool]
    ) -> "CapabilityRegistry":
        """
        根据启用配置过滤能力
        
        用于实例级工具过滤：只保留在 enabled_map 中明确标记为启用的工具。
        
        Args:
            enabled_map: 工具名 -> 是否启用的映射
                        例如: {"web_search": True, "ppt_generator": False}
            
        Returns:
            过滤后的新 CapabilityRegistry 实例
            
        示例:
            >>> registry = CapabilityRegistry()
            >>> enabled = {"web_search": True, "plan_todo": True}
            >>> filtered = registry.filter_by_enabled(enabled)
            >>> len(filtered.capabilities)  # 只包含 2 个工具
            2
        """
        # 创建新的 registry 实例（不加载配置，手动填充）
        filtered = CapabilityRegistry.__new__(CapabilityRegistry)
        filtered.capabilities = {}
        filtered._raw_capabilities = []
        
        # 保留原有的分类和映射
        filtered.task_type_mappings = self.task_type_mappings.copy()
        filtered.categories = self.categories.copy()
        filtered._config_path = self._config_path
        filtered._skills_dir = self._skills_dir
        
        # 过滤能力：只保留明确启用的工具
        for name, cap in self.capabilities.items():
            if enabled_map.get(name, False):  # 只有显式为 True 才启用
                filtered.capabilities[name] = cap
        
        # 同步原始配置
        for cap_data in self._raw_capabilities:
            cap_name = cap_data.get('name')
            if cap_name and enabled_map.get(cap_name, False):
                filtered._raw_capabilities.append(cap_data)
        
        return filtered
    
    def find_candidates(
        self,
        keywords: List[str],
        task_type: str = None,
        context: Dict[str, Any] = None
    ) -> List[Capability]:
        """
        根据关键词和任务类型查找候选能力
        
        🆕 V4.6 自动化匹配：
        1. 如果传入 task_type，自动通过 task_type_mappings 展开为能力列表
        2. 遍历所有 Capability，检查是否匹配展开后的能力 ID
        3. 同时支持关键词匹配作为补充
        
        Args:
            keywords: 关键词列表
            task_type: 任务类型（如 information_query, content_generation）
            context: 上下文（用于约束检查）
            
        Returns:
            候选能力列表（未排序）
        """
        candidates = []
        
        # 🆕 V4.6: 自动展开 task_type → 能力列表
        required_capabilities = set()
        if task_type:
            # 通过 task_type_mappings 获取需要的能力类别
            mapped_caps = self.get_capabilities_for_task_type(task_type)
            required_capabilities.update(mapped_caps)
        
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
            
            # 🆕 V4.6: 检查能力类别匹配（自动化）
            # cap.capabilities 是该工具声明的能力列表（如 ["data_analysis", "data_visualization"]）
            # required_capabilities 是 task_type 展开后需要的能力
            if required_capabilities and cap.capabilities:
                # 如果工具的任一能力在需求列表中，则匹配
                if any(c in required_capabilities for c in cap.capabilities):
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
    
    def get_registered_skills(self) -> List[Dict[str, Any]]:
        """
        获取所有已注册到 Claude 的 Skills（有 skill_id 的）
        
        用于 Agent 初始化时启用 Skills Container
        
        Returns:
            已注册的 Skills 列表，格式符合 Claude API 要求：
            [{"type": "custom", "skill_id": "skill_xxx", "version": "latest"}, ...]
        """
        registered = []
        
        for cap in self.find_by_type(CapabilityType.SKILL):
            if cap.skill_id:  # 只返回已注册的（有 skill_id）
                skill_config = {
                    "type": "custom",
                    "skill_id": cap.skill_id,
                    "version": "latest"
                }
                registered.append(skill_config)
                
        return registered
    
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
    
    def get_all_capabilities(self) -> List[Dict[str, Any]]:
        """
        获取所有原始能力配置数据
        
        用于：
        - ResultCompactor 加载 compaction 配置
        - 其他需要完整配置数据的组件
        
        Returns:
            原始配置数据列表（包含 compaction 等配置）
        """
        return self._raw_capabilities
    
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


# ==================== 单例管理 ====================

# 全局单例实例
_registry_instance: Optional[CapabilityRegistry] = None


def get_capability_registry(
    config_path: str = None,
    skills_dir: str = None,
    force_reload: bool = False
) -> CapabilityRegistry:
    """
    获取能力注册表单例（推荐使用）
    
    capabilities.yaml 只在首次调用或 force_reload=True 时加载。
    后续调用直接返回缓存的实例。
    
    Args:
        config_path: 配置文件路径（仅首次加载时生效）
        skills_dir: Skills 目录路径（仅首次加载时生效）
        force_reload: 是否强制重新加载
        
    Returns:
        CapabilityRegistry 单例实例
    """
    global _registry_instance
    
    if _registry_instance is None or force_reload:
        _registry_instance = CapabilityRegistry(
            config_path=config_path,
            skills_dir=skills_dir
        )
    
    return _registry_instance


def create_capability_registry(
    config_path: str = None,
    skills_dir: str = None
) -> CapabilityRegistry:
    """
    创建能力注册表（向后兼容，实际返回单例）
    
    ⚠️ 建议使用 get_capability_registry() 明确获取单例
    
    Args:
        config_path: 配置文件路径
        skills_dir: Skills 目录路径
        
    Returns:
        CapabilityRegistry 单例实例
    """
    return get_capability_registry(config_path=config_path, skills_dir=skills_dir)

