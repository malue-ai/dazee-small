"""
能力注册表 - 统一管理所有能力

职责：
1. 从capabilities.yaml加载能力配置
2. 提供能力查询接口
3. 支持动态注册新能力

设计原则：
- 配置驱动：所有能力从YAML配置加载
- 统一抽象：Skills/Tools/MCP/Code统一为Capability
- 易于扩展：支持动态注册

参考文档：
- docs/v3/02-CAPABILITY-ROUTING.md
- docs/v3/TOOL_CALLING_DECISION_FRAMEWORK.md
"""

from typing import Dict, List, Optional, Any
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
import yaml


class CapabilityType(Enum):
    """能力类型"""
    SKILL = "SKILL"    # 领域知识包（SKILL.md + scripts）
    TOOL = "TOOL"      # 预定义函数
    MCP = "MCP"        # MCP服务器
    CODE = "CODE"      # 动态代码执行


class CapabilitySubtype(Enum):
    """能力子类型"""
    PREBUILT = "PREBUILT"    # Anthropic预置
    CUSTOM = "CUSTOM"        # 用户自定义
    NATIVE = "NATIVE"        # 系统原生
    EXTERNAL = "EXTERNAL"    # 外部服务
    DYNAMIC = "DYNAMIC"      # 动态生成


@dataclass
class Capability:
    """
    能力定义
    
    统一抽象所有执行方式（Skills/Tools/MCP/Code）
    """
    name: str
    type: CapabilityType
    subtype: str
    provider: str
    capabilities: List[str]  # 能力标签（如 ppt_generation, data_analysis）
    priority: int            # 基础优先级 0-100
    cost: Dict[str, str]     # 成本 {time: fast/medium/slow, money: free/low/medium/high}
    constraints: Dict[str, Any]  # 约束条件
    metadata: Dict[str, Any]     # 扩展信息（description, keywords, preferred_for等）
    input_schema: Optional[Dict] = None  # 工具输入Schema（用于Claude API）
    
    def matches_keywords(self, keywords: List[str]) -> int:
        """
        计算关键词匹配度
        
        Args:
            keywords: 待匹配的关键词列表
            
        Returns:
            匹配分数（越高越匹配）
        """
        if not keywords:
            return 0
            
        score = 0
        cap_keywords = self.metadata.get('keywords', [])
        preferred_for = self.metadata.get('preferred_for', [])
        description = self.metadata.get('description', '')
        
        for kw in keywords:
            kw_lower = kw.lower()
            
            # 能力标签匹配（权重最高）
            if any(kw_lower in str(c).lower() for c in self.capabilities):
                score += 15
            
            # preferred_for匹配（权重高）
            if any(kw_lower in str(p).lower() for p in preferred_for):
                score += 10
            
            # keywords匹配（权重中）
            if any(kw_lower in str(k).lower() for k in cap_keywords):
                score += 5
            
            # description匹配（权重低）
            if kw_lower in description.lower():
                score += 2
            
            # 名称匹配（权重中）
            if kw_lower in self.name.lower():
                score += 8
        
        return score
    
    def meets_constraints(self, context: Dict[str, Any] = None) -> bool:
        """
        检查是否满足约束条件
        
        Args:
            context: 当前上下文（如可用的API、网络状态等）
            
        Returns:
            是否满足约束
        """
        if not context:
            return True
        
        # 检查API依赖
        if self.constraints.get('requires_api'):
            api_name = self.constraints.get('api_name')
            available_apis = context.get('available_apis', [])
            if api_name and api_name not in available_apis:
                return False
        
        # 检查网络依赖
        if self.constraints.get('requires_network'):
            if not context.get('network_available', True):
                return False
        
        # 检查认证依赖
        if self.constraints.get('requires_auth'):
            if not context.get('authenticated', False):
                return False
        
        return True
    
    def to_tool_schema(self) -> Optional[Dict]:
        """
        转换为Claude API的tool schema格式
        
        Returns:
            符合Claude API规范的tool schema，或None
        """
        if self.type != CapabilityType.TOOL:
            return None
        
        if not self.input_schema:
            return None
        
        return {
            "name": self.name,
            "description": self.metadata.get('description', self.name),
            "input_schema": self.input_schema
        }


class CapabilityRegistry:
    """
    能力注册表
    
    统一管理所有能力（Skills/Tools/MCP/Code）
    从capabilities.yaml加载配置
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化能力注册表
        
        Args:
            config_path: 配置文件路径，默认为/config/capabilities.yaml
        """
        self.capabilities: Dict[str, Capability] = {}
        self.categories: List[Dict[str, Any]] = []  # 🆕 能力分类定义
        self.task_type_mappings: Dict[str, List[str]] = {}  # 🆕 任务类型 → 能力映射
        self._config_path = config_path or self._default_config_path()
        self._load_config()
    
    def _default_config_path(self) -> str:
        """获取默认配置文件路径"""
        return str(Path(__file__).parent.parent / "config" / "capabilities.yaml")
    
    def _load_config(self):
        """从YAML配置文件加载能力"""
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
        
        # 🆕 加载任务类型映射
        self.task_type_mappings = config.get('task_type_mappings', {})
        if self.task_type_mappings:
            print(f"✅ Loaded task type mappings for {len(self.task_type_mappings)} types: {', '.join(self.task_type_mappings.keys())}")
        
        # 🆕 加载能力分类定义
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
        # 提取metadata，并将顶层的implementation字段合并进去（如果存在）
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
    
    # ==================== 查询接口 ====================
    
    def get(self, name: str) -> Optional[Capability]:
        """
        获取指定名称的能力
        
        Args:
            name: 能力名称
            
        Returns:
            Capability或None
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
            # 🚫 过滤内部工具（除非上下文明确允许）
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
        获取所有工具的Schema（用于Claude API）
        
        Returns:
            工具schema列表
        """
        schemas = []
        
        for cap in self.find_by_type(CapabilityType.TOOL):
            schema = cap.to_tool_schema()
            if schema:
                schemas.append(schema)
        
        return schemas
    
    def get_skills_metadata(self) -> List[Dict]:
        """
        获取所有Skills的元数据（用于System Prompt）
        
        Returns:
            Skills元数据列表
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
        lines = ["Capability Registry Summary:"]
        for cap_type, count in counts.items():
            lines.append(f"  - {cap_type}: {count}")
        lines.append(f"  Total: {len(self.capabilities)}")
        if self.categories:
            lines.append(f"  Categories: {len(self.categories)}")
        return "\n".join(lines)
    
    # ==================== 🆕 能力分类接口 ====================
    
    def get_category_ids(self) -> List[str]:
        """
        获取所有分类 ID
        
        用途：用于 plan_todo Schema 的 enum 定义
        
        Returns:
            分类 ID 列表，如 ["web_search", "ppt_generation", ...]
        """
        return [cat['id'] for cat in self.categories]
    
    def get_categories_for_prompt(self) -> str:
        """
        生成 System Prompt 中的能力分类说明（Markdown 格式）
        
        用途：动态注入到 System Prompt 中，告诉 LLM 可用的能力分类
        
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
        
        # 添加示例
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
    
    # ==================== 🆕 任务类型映射接口 ====================
    
    def get_capabilities_for_task_type(self, task_type: str) -> List[str]:
        """
        🆕 根据任务类型获取推荐的能力列表（通用能力推断）
        
        用途：
        - 作为能力推断的「初始值」，适用于所有任务
        - 优先级：有 Plan 时用 Plan 的 > 无 Plan 时用这个推断
        - 从配置文件动态加载，避免硬编码
        
        场景：
        - 简单任务：直接使用推断结果
        - 复杂任务首轮：作为初始能力集，后续轮次从 Plan 提取更精确的
        
        Args:
            task_type: 任务类型（如 information_query, content_generation）
            
        Returns:
            能力列表（capability IDs），如 ["web_search", "file_operations"]
            
        Example:
            >>> registry.get_capabilities_for_task_type("information_query")
            ["web_search", "file_operations", "task_planning"]
        """
        # 从配置文件读取映射
        mapping = self.task_type_mappings.get(task_type)
        
        if mapping:
            return mapping
        
        # 如果没有找到，返回默认映射（other）
        default_mapping = self.task_type_mappings.get("other", [])
        
        if not default_mapping:
            # 兜底：如果配置文件完全没有定义，使用最基础的能力
            return ["file_operations", "code_execution", "task_planning"]
        
        return default_mapping
    
    def get_all_task_types(self) -> List[str]:
        """
        获取所有已配置的任务类型
        
        Returns:
            任务类型列表
        """
        return list(self.task_type_mappings.keys())


# ==================== 便捷函数 ====================

def create_capability_registry(config_path: str = None) -> CapabilityRegistry:
    """
    创建能力注册表
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        配置好的CapabilityRegistry实例
    """
    return CapabilityRegistry(config_path=config_path)

