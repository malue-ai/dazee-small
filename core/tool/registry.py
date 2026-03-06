"""
统一注册表模块

合并自：
- core/tool/capability/registry.py (CapabilityRegistry)
- core/tool/instance_registry.py (InstanceToolRegistry)

提供两级注册表：
1. CapabilityRegistry - 全局能力注册表（单例，从 capabilities.yaml 加载）
2. InstanceRegistry - 实例级工具注册表（每个 Agent 实例独立）

设计原则：
- 配置驱动：所有能力从 YAML 配置加载
- 统一抽象：Skills/Tools/Code 统一为 Capability
- 分层管理：全局 vs 实例级分离
"""

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

import aiofiles
import yaml

from logger import get_logger

from .types import Capability, CapabilityType

logger = get_logger(__name__)


# ==================== 全局能力注册表 ====================


class CapabilityRegistry:
    """
    全局能力注册表（单例）

    管理所有能力（Skills/Tools/Code）
    从 capabilities.yaml 加载配置，同时扫描 skills/library/ 发现 Skills

    使用方式:
        registry = get_capability_registry()  # 获取单例
        await registry.initialize()  # 首次使用需要初始化

        # 查询能力
        cap = registry.get("api_calling")
        tools = registry.find_by_type(CapabilityType.TOOL)
    """

    def __init__(self, config_path: Optional[str] = None, skills_dir: Optional[str] = None):
        """
        初始化能力注册表

        Args:
            config_path: 配置文件路径，默认为 config/capabilities.yaml
            skills_dir: Skills 目录路径，默认为 skills/library/
        """
        self.capabilities: Dict[str, Capability] = {}
        self.categories: List[Dict[str, Any]] = []
        self._raw_capabilities: List[Dict[str, Any]] = []

        # 🆕 工具分类配置（合并自 tool_registry.yaml）
        self.tool_classification: Dict[str, Any] = {}

        self._config_path = config_path or self._default_config_path()
        self._skills_dir = skills_dir or self._default_skills_dir()
        self._initialized: bool = False

    async def initialize(self) -> None:
        """
        异步初始化：加载配置和扫描 Skills

        使用方式:
            registry = CapabilityRegistry()
            await registry.initialize()
        """
        if self._initialized:
            return

        # 加载 Tools 配置
        await self._load_config_async()

        # 扫描 Skills
        await self._scan_skills_async()

        self._initialized = True

    def _default_config_path(self) -> str:
        """获取默认配置文件路径"""
        from utils.app_paths import get_bundle_dir
        return str(get_bundle_dir() / "config" / "capabilities.yaml")

    def _default_skills_dir(self) -> str:
        """获取默认 Skills 目录"""
        from utils.app_paths import get_bundle_dir
        return str(get_bundle_dir() / "skills" / "library")

    async def _load_config_async(self) -> None:
        """异步从 YAML 配置文件加载能力"""
        config_path = Path(self._config_path)

        if not config_path.exists():
            logger.warning(f"⚠️ 配置文件不存在: {self._config_path}")
            return

        try:
            async with aiofiles.open(config_path, "r", encoding="utf-8") as f:
                content = await f.read()
                config = yaml.safe_load(content)
        except Exception as e:
            logger.error(f"❌ 加载配置失败: {e}")
            return

        # 加载能力分类定义
        self.categories = config.get("capability_categories", [])
        if self.categories:
            category_ids = [cat["id"] for cat in self.categories]
            logger.info(
                f"✅ 加载能力分类: {len(self.categories)} 个 ({', '.join(category_ids[:5])}...)"
            )

        # 🆕 加载工具分类配置（合并自 tool_registry.yaml）
        self.tool_classification = config.get("tool_classification", {})
        if self.tool_classification:
            logger.info(f"✅ 加载工具分类配置")

        # 加载每个能力
        for cap_data in config.get("capabilities", []):
            try:
                # 跳过显式禁用的能力
                if cap_data.get("enabled") is False:
                    logger.debug(f"⏭️ 跳过禁用能力: {cap_data.get('name', 'unknown')}")
                    continue

                capability = self._parse_capability(cap_data)
                self.capabilities[capability.name] = capability
                self._raw_capabilities.append(cap_data)
            except Exception as e:
                logger.warning(f"⚠️ 解析能力失败 {cap_data.get('name', 'unknown')}: {e}")

        # 打印加载结果
        if self.capabilities:
            logger.info(f"✅ 加载 {len(self.capabilities)} 个能力")

    def _parse_capability(self, data: Dict) -> Capability:
        """解析能力配置"""
        metadata = data.get("metadata", {})
        if "implementation" in data:
            metadata["implementation"] = data["implementation"]

        if "compaction" in data:
            metadata["compaction"] = data["compaction"]

        if "state_category" in data:
            metadata["state_category"] = data["state_category"]

        return Capability(
            name=data["name"],
            type=CapabilityType(data["type"]),
            subtype=data.get("subtype", "CUSTOM"),
            provider=data.get("provider", "unknown"),
            capabilities=data.get("capabilities", []),
            priority=data.get("priority", 50),
            cost=data.get("cost", {"time": "medium", "money": "free"}),
            constraints=data.get("constraints", {}),
            metadata=metadata,
            input_schema=data.get("input_schema"),
            fallback_tool=data.get("fallback_tool"),
            skill_path=data.get("skill_path"),
            level=data.get("level", 2),
            cache_stable=data.get("cache_stable", False),
        )

    async def _scan_skills_async(self) -> None:
        """
        异步扫描 Skills 目录

        将 Skills 注册为 Capability(type=SKILL)
        """
        skills_dir = Path(self._skills_dir)

        if not skills_dir.exists():
            logger.debug(f"Skills 目录不存在: {skills_dir}")
            return

        skill_dirs = await asyncio.to_thread(list, skills_dir.iterdir())

        skill_count = 0
        for skill_dir in skill_dirs:
            if not skill_dir.is_dir():
                continue

            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue

            # 异步解析 YAML frontmatter
            metadata = await self._parse_skill_frontmatter_async(skill_md)
            if not metadata:
                continue

            skill_name = metadata.get("name", skill_dir.name)

            # 跳过已在 capabilities.yaml 中定义的
            if skill_name in self.capabilities:
                continue

            self.capabilities[skill_name] = Capability(
                name=skill_name,
                type=CapabilityType.SKILL,
                subtype="CUSTOM",
                provider="local",
                capabilities=metadata.get("capabilities", []),
                priority=self._parse_priority(metadata.get("priority", "medium")),
                cost={"time": "medium", "money": "free"},
                constraints={},
                metadata={
                    "description": metadata.get("description", ""),
                    "keywords": metadata.get("keywords", []),
                    "preferred_for": metadata.get("preferred_for", []),
                    "skill_path": str(skill_dir),
                },
            )
            skill_count += 1

        if skill_count > 0:
            logger.info(f"✅ 扫描到 {skill_count} 个本地 Skills")

    async def _parse_skill_frontmatter_async(self, skill_md: Path) -> Optional[Dict]:
        """异步解析 SKILL.md 的 YAML frontmatter"""
        try:
            async with aiofiles.open(skill_md, "r", encoding="utf-8") as f:
                content = await f.read()
            if not content.startswith("---"):
                return None

            end_idx = content.index("---", 3)
            frontmatter = content[3:end_idx].strip()
            return yaml.safe_load(frontmatter)
        except Exception as e:
            logger.debug(f"解析 {skill_md} 失败: {e}")
            return None

    def _parse_priority(self, priority_str: str) -> int:
        """将优先级字符串转换为数字"""
        priority_map = {"low": 30, "medium": 50, "high": 80, "critical": 90}
        return priority_map.get(str(priority_str).lower(), 50)

    # ==================== 查询接口 ====================

    @staticmethod
    def normalize_tool_name(name: str) -> str:
        """Skill/Tool 名称归一化：连字符 → 下划线（capabilities.yaml 统一用下划线）"""
        return name.replace("-", "_")

    def get(self, name: str) -> Optional[Capability]:
        """获取指定名称的能力（自动归一化 hyphen/underscore）"""
        cap = self.capabilities.get(name)
        if cap is not None:
            return cap
        normalized = self.normalize_tool_name(name)
        if normalized != name:
            return self.capabilities.get(normalized)
        return None

    def find_by_type(self, cap_type: CapabilityType) -> List[Capability]:
        """按类型查找能力"""
        return [c for c in self.capabilities.values() if c.type == cap_type]

    def find_by_capability_tag(self, tag: str) -> List[Capability]:
        """按能力标签查找"""
        return [c for c in self.capabilities.values() if tag in c.capabilities]

    def find_by_level(self, level: int) -> List[Capability]:
        """按工具层级查找（1=核心，2=动态）"""
        return [c for c in self.capabilities.values() if c.level == level]

    def get_core_tools(self) -> List[Capability]:
        """获取核心工具（Level 1）"""
        return self.find_by_level(1)

    def get_dynamic_tools(self) -> List[Capability]:
        """获取动态工具（Level 2）"""
        return self.find_by_level(2)

    def get_cacheable_tools(self) -> List[str]:
        """获取可缓存工具名称列表"""
        return [c.name for c in self.capabilities.values() if c.cache_stable]

    def filter_by_enabled(self, enabled_map: Dict[str, bool]) -> "CapabilityRegistry":
        """
        根据启用配置过滤能力

        Args:
            enabled_map: 工具名 -> 是否启用

        Returns:
            过滤后的新 CapabilityRegistry 实例
        """
        filtered = CapabilityRegistry.__new__(CapabilityRegistry)
        filtered.capabilities = {}
        filtered._raw_capabilities = []
        filtered.categories = self.categories.copy()
        filtered.tool_classification = self.tool_classification.copy()
        filtered._config_path = self._config_path
        filtered._skills_dir = self._skills_dir
        filtered._initialized = True

        normalized_enabled = {
            self.normalize_tool_name(k): v for k, v in enabled_map.items()
        }

        for name, cap in self.capabilities.items():
            norm = self.normalize_tool_name(name)
            if normalized_enabled.get(name, False) or normalized_enabled.get(norm, False):
                filtered.capabilities[name] = cap

        for cap_data in self._raw_capabilities:
            cap_name = cap_data.get("name")
            if cap_name:
                norm = self.normalize_tool_name(cap_name)
                if normalized_enabled.get(cap_name, False) or normalized_enabled.get(norm, False):
                    filtered._raw_capabilities.append(cap_data)

        return filtered

    def find_candidates(
        self,
        context: Dict[str, Any] = None,
    ) -> List[Capability]:
        """
        查找满足上下文约束的候选能力（符合 LLM-First）。

        Args:
            context: 上下文（用于约束检查）

        Returns:
            候选能力列表（未排序）
        """
        candidates = []

        for cap in self.capabilities.values():
            if cap.constraints.get("internal_use_only"):
                if not context or not context.get("allow_internal_tools"):
                    continue
            if not cap.meets_constraints(context):
                continue

            candidates.append(cap)

        return candidates

    # ==================== 注册接口 ====================

    def register(self, capability: Capability):
        """动态注册新能力"""
        self.capabilities[capability.name] = capability

    def register_from_dict(self, data: Dict):
        """从字典注册新能力"""
        capability = self._parse_capability(data)
        self.register(capability)

    # ==================== 工具接口 ====================

    def get_tool_schemas(self) -> List[Dict]:
        """获取所有工具的 Schema（用于 Claude API）"""
        schemas = []
        for cap in self.find_by_type(CapabilityType.TOOL):
            schema = cap.to_tool_schema()
            if schema:
                schemas.append(schema)
        return schemas

    def get_skills_metadata(self) -> List[Dict]:
        """获取所有 Skills 的元数据（用于 System Prompt）"""
        skills = []
        for cap in self.find_by_type(CapabilityType.SKILL):
            skills.append(
                {
                    "name": cap.name,
                    "description": cap.metadata.get("description", ""),
                    "subtype": cap.subtype,
                    "provider": cap.provider,
                    "preferred_for": cap.metadata.get("preferred_for", []),
                    "keywords": cap.metadata.get("keywords", []),
                }
            )
        return skills

    def get_all_capabilities(self) -> List[Dict[str, Any]]:
        """获取所有原始能力配置数据"""
        return self._raw_capabilities

    # ==================== 分类接口 ====================

    def get_category_ids(self) -> List[str]:
        """获取所有分类 ID"""
        return [cat["id"] for cat in self.categories]

    def get_categories_for_prompt(self) -> str:
        """生成 System Prompt 中的能力分类说明"""
        if not self.categories:
            return ""

        lines = [
            "## 🏷️ Available Capability Categories",
            "",
            "| Category | Description | Use When |",
            "|----------|-------------|----------|",
        ]

        for cat in self.categories:
            cat_id = cat["id"]
            desc = cat["description"]
            use_when = cat["use_when"]
            lines.append(f"| `{cat_id}` | {desc} | {use_when} |")

        return "\n".join(lines)

    # ==================== 🆕 工具分类配置（合并自 tool_registry.yaml）====================

    def get_frequent_tools(self) -> List[str]:
        """获取常用工具列表（不延迟加载）"""
        return self.tool_classification.get("frequent_tools", []).copy()

    def get_tool_categories(self) -> Dict[str, List[str]]:
        """获取工具类别映射（简写展开）"""
        return self.tool_classification.get("categories", {}).copy()

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


# ==================== 实例级工具注册表 ====================


class InstanceToolType(Enum):
    """实例级工具类型"""

    REST_API = "REST_API"  # REST API（通过 api_calling 调用）


@dataclass
class InstanceTool:
    """
    实例级工具定义

    表示 REST API，可转换为 Claude API 格式
    """

    name: str
    type: InstanceToolType
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)
    capability: Optional[str] = None

    # REST API 特有属性
    base_url: Optional[str] = None
    api_doc: Optional[str] = None

    # 调用处理器
    handler: Optional[Callable[..., Awaitable[Any]]] = None

    def to_claude_tool(self) -> Dict[str, Any]:
        """转换为 Claude API 工具格式"""
        schema = (
            self.input_schema
            if self.input_schema
            else {"type": "object", "properties": {}, "required": []}
        )
        return {"name": self.name, "description": self.description, "input_schema": schema}

    def to_capability_dict(self) -> Dict[str, Any]:
        """转换为 Capability 兼容格式"""
        return {
            "name": self.name,
            "type": "TOOL",
            "subtype": "REST",
            "provider": "instance",
            "capabilities": [self.capability] if self.capability else [],
            "priority": 80,
            "metadata": {
                "description": self.description,
                "instance_tool": True,
                "tool_type": self.type.value,
            },
            "input_schema": self.input_schema,
        }


class InstanceRegistry:
    """
    实例级工具注册表

    管理一个 Agent 实例的所有动态工具（REST API）
    与全局 CapabilityRegistry 协同工作

    使用方式:
        instance_registry = InstanceRegistry(global_registry)

        # 获取所有工具（全局 + 实例）
        all_tools = instance_registry.get_all_tools_unified()
    """

    def __init__(self, global_registry: Optional[CapabilityRegistry] = None):
        """
        初始化实例工具注册表

        Args:
            global_registry: 全局 CapabilityRegistry（可选）
        """
        self._tools: Dict[str, InstanceTool] = {}
        self._global_registry = global_registry
        self._inference_cache: Dict[str, List[str]] = {}

    # ==================== 注册接口 ====================

    def register(self, tool: InstanceTool):
        """注册实例级工具"""
        self._tools[tool.name] = tool
        logger.info(f"📦 注册实例工具: {tool.name} ({tool.type.value})")

    def register_rest_api(
        self,
        name: str,
        base_url: str,
        description: str,
        api_doc: str,
        capability: Optional[str] = None,
    ):
        """
        注册 REST API

        Args:
            name: API 名称
            base_url: 基础 URL
            description: 描述
            api_doc: API 文档内容
            capability: 能力类别
        """
        tool_name = f"api_{name}"

        tool = InstanceTool(
            name=tool_name,
            type=InstanceToolType.REST_API,
            description=description,
            capability=capability,
            base_url=base_url,
            api_doc=api_doc,
            input_schema={
                "type": "object",
                "properties": {
                    "endpoint": {"type": "string", "description": "API 端点"},
                    "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"]},
                    "body": {"type": "object", "description": "请求体"},
                },
                "required": ["endpoint"],
            },
        )
        self.register(tool)

    # ==================== 查询接口 ====================

    def get(self, name: str) -> Optional[InstanceTool]:
        """获取工具"""
        return self._tools.get(name)

    def get_all(self) -> List[InstanceTool]:
        """获取所有实例工具"""
        return list(self._tools.values())

    def get_by_type(self, tool_type: InstanceToolType) -> List[InstanceTool]:
        """按类型获取工具"""
        return [t for t in self._tools.values() if t.type == tool_type]

    def get_by_capability(self, capability: str) -> List[InstanceTool]:
        """按能力类别获取工具"""
        return [t for t in self._tools.values() if t.capability == capability]

    # ==================== 工具发现接口 ====================

    def get_tools_for_claude(self) -> List[Dict[str, Any]]:
        """获取 Claude API 格式的工具列表"""
        return [t.to_claude_tool() for t in self._tools.values()]

    def get_tools_for_discovery(self) -> List[Dict[str, Any]]:
        """获取用于工具发现的列表（与 capabilities.yaml 格式兼容）"""
        return [t.to_capability_dict() for t in self._tools.values()]

    def get_all_tools_unified(self) -> List[Dict[str, Any]]:
        """
        获取统一格式的所有工具（全局 + 实例）

        Returns:
            合并后的工具列表，用于 Plan 阶段工具发现
        """
        tools = []

        # 添加全局工具
        if self._global_registry:
            for cap in self._global_registry.capabilities.values():
                if cap.type == CapabilityType.TOOL:
                    tools.append(
                        {
                            "name": cap.name,
                            "type": "TOOL",
                            "subtype": cap.subtype,
                            "provider": cap.provider,
                            "description": cap.metadata.get("description", ""),
                            "capabilities": cap.capabilities,
                            "priority": cap.priority,
                            "source": "global",
                        }
                    )

        # 添加实例工具
        for tool in self._tools.values():
            tools.append(
                {
                    "name": tool.name,
                    "type": "TOOL",
                    "subtype": tool.type.value,
                    "provider": "instance",
                    "description": tool.description,
                    "capabilities": [tool.capability] if tool.capability else [],
                    "priority": 80,
                    "source": "instance",
                }
            )

        return tools

    # ==================== 调用接口 ====================

    async def invoke(self, tool_name: str, **kwargs) -> Any:
        """
        调用工具

        Args:
            tool_name: 工具名称
            **kwargs: 工具参数

        Returns:
            工具执行结果
        """
        tool = self.get(tool_name)
        if not tool:
            raise ValueError(f"工具不存在: {tool_name}")

        if not tool.handler:
            raise ValueError(f"工具没有配置处理器: {tool_name}")

        return await tool.handler(**kwargs)

    # ==================== 缓存管理 ====================

    async def load_inference_cache(self, cache_path) -> bool:
        """异步加载工具推断缓存"""
        cache_file = Path(cache_path)
        if not cache_file.exists():
            return False

        try:
            async with aiofiles.open(cache_file, "r", encoding="utf-8") as f:
                content = await f.read()
                self._inference_cache = json.loads(content)
            logger.info(f"✅ 加载工具推断缓存: {len(self._inference_cache)} 个工具")
            return True
        except Exception as e:
            logger.error(f"加载工具推断缓存失败: {e}")
            return False

    async def save_inference_cache(self, cache_path) -> bool:
        """异步保存工具推断缓存"""
        cache_file = Path(cache_path)
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            async with aiofiles.open(cache_file, "w", encoding="utf-8") as f:
                await f.write(json.dumps(self._inference_cache, indent=2, ensure_ascii=False))
            logger.info(f"✅ 保存工具推断缓存: {len(self._inference_cache)} 个工具")
            return True
        except Exception as e:
            logger.error(f"保存工具推断缓存失败: {e}")
            return False

    # ==================== 信息接口 ====================

    def summary(self) -> str:
        """生成摘要"""
        api_count = len(self.get_by_type(InstanceToolType.REST_API))
        return f"InstanceRegistry: {api_count} REST APIs"

    def list_tool_names(self) -> List[str]:
        """列出所有工具名称"""
        return list(self._tools.keys())


# ==================== 单例管理 ====================

_registry_instance: Optional[CapabilityRegistry] = None


def get_capability_registry(
    config_path: str = None, skills_dir: str = None, force_reload: bool = False
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
        _registry_instance = CapabilityRegistry(config_path=config_path, skills_dir=skills_dir)

    return _registry_instance


def create_capability_registry(
    config_path: str = None, skills_dir: str = None
) -> CapabilityRegistry:
    """
    创建能力注册表（向后兼容，实际返回单例）

    建议使用 get_capability_registry() 明确获取单例
    """
    return get_capability_registry(config_path=config_path, skills_dir=skills_dir)


def create_instance_registry(
    global_registry: Optional[CapabilityRegistry] = None,
) -> InstanceRegistry:
    """
    创建实例工具注册表

    Args:
        global_registry: 全局 CapabilityRegistry

    Returns:
        InstanceRegistry 实例
    """
    return InstanceRegistry(global_registry=global_registry)


# ==================== 导出 ====================

__all__ = [
    # 全局注册表
    "CapabilityRegistry",
    "get_capability_registry",
    "create_capability_registry",
    # 实例注册表
    "InstanceRegistry",
    "InstanceTool",
    "InstanceToolType",
    "create_instance_registry",
]
