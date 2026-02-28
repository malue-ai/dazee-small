"""
LLM 友好的工具描述增强

V8.0 新增

职责：
- 为工具生成面向 LLM 优化的描述
- 支持 use_when / not_use_when / examples / composition_hints
- 增强工具选择的准确性

设计原则：
- 描述应该告诉 LLM "什么时候用" 而不仅仅是 "能做什么"
- 提供正例和反例
- 说明与其他工具的组合关系
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
import yaml

from logger import get_logger

logger = get_logger(__name__)


@dataclass
class LLMToolDescription:
    """
    LLM 友好的工具描述

    相比传统的 tool description，增加了：
    - use_when: 何时应该使用
    - not_use_when: 何时不应该使用
    - examples: 输入输出示例
    - composition_hints: 与其他工具的组合建议
    - common_errors: 常见错误和解决方案
    """

    # 基础信息
    name: str
    description: str  # 基础描述

    # LLM 决策增强
    use_when: List[str] = field(default_factory=list)
    # [
    #   "需要搜索实时信息",
    #   "需要获取最新新闻",
    #   "用户问题涉及当前事件"
    # ]

    not_use_when: List[str] = field(default_factory=list)
    # [
    #   "查询用户个人数据（使用 memory 代替）",
    #   "静态知识问题（直接回答）",
    #   "需要用户上传的文档（使用 knowledge_search）"
    # ]

    # 示例
    examples: List[Dict[str, Any]] = field(default_factory=list)
    # [
    #   {
    #     "input": {"query": "2024年AI发展趋势"},
    #     "output": {"results": [...]},
    #     "explanation": "搜索最新AI趋势信息"
    #   }
    # ]

    # 组合建议
    composition_hints: List[Dict[str, Any]] = field(default_factory=list)
    # [
    #   {
    #     "pattern": "search_then_analyze",
    #     "sequence": ["web_search", "data_analysis"],
    #     "when": "需要先搜索信息再进行分析"
    #   }
    # ]

    # 常见错误
    common_errors: List[Dict[str, str]] = field(default_factory=list)
    # [
    #   {
    #     "error": "No results found",
    #     "cause": "查询太具体或太宽泛",
    #     "solution": "调整查询关键词"
    #   }
    # ]

    # 输出格式说明
    output_schema: Dict[str, Any] = field(default_factory=dict)
    # {
    #   "results": "list[{title, snippet, url}]",
    #   "total": "int"
    # }

    # 性能特征
    performance: Dict[str, Any] = field(default_factory=dict)
    # {
    #   "latency": "fast|medium|slow",
    #   "cost": "free|low|medium|high",
    #   "reliability": "high|medium|low"
    # }

    def to_llm_prompt(self) -> str:
        """
        生成 LLM 可读的工具描述

        Returns:
            格式化的描述文本
        """
        parts = [f"**{self.name}**", f"{self.description}"]

        if self.use_when:
            parts.append("\n**适用场景:**")
            for item in self.use_when:
                parts.append(f"  - {item}")

        if self.not_use_when:
            parts.append("\n**不适用场景:**")
            for item in self.not_use_when:
                parts.append(f"  - {item}")

        if self.examples:
            parts.append("\n**示例:**")
            for i, ex in enumerate(self.examples[:2], 1):
                parts.append(f"  {i}. 输入: {ex.get('input', {})}")
                if "explanation" in ex:
                    parts.append(f"     说明: {ex['explanation']}")

        if self.composition_hints:
            parts.append("\n**组合建议:**")
            for hint in self.composition_hints[:2]:
                parts.append(f"  - {hint.get('when', '')}: {' → '.join(hint.get('sequence', []))}")

        return "\n".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "description": self.description,
            "use_when": self.use_when,
            "not_use_when": self.not_use_when,
            "examples": self.examples,
            "composition_hints": self.composition_hints,
            "common_errors": self.common_errors,
            "output_schema": self.output_schema,
            "performance": self.performance,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LLMToolDescription":
        """从字典创建"""
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            use_when=data.get("use_when", []),
            not_use_when=data.get("not_use_when", []),
            examples=data.get("examples", []),
            composition_hints=data.get("composition_hints", []),
            common_errors=data.get("common_errors", []),
            output_schema=data.get("output_schema", {}),
            performance=data.get("performance", {}),
        )

    @classmethod
    def from_capability(cls, capability: Dict[str, Any]) -> "LLMToolDescription":
        """
        从 capabilities.yaml 的工具定义创建

        兼容现有格式，自动提取增强字段
        """
        name = capability.get("name", "")
        metadata = capability.get("metadata", {})

        # 基础描述
        description = metadata.get("description", capability.get("description", ""))

        # 从 metadata 提取增强信息
        use_when = []
        if "preferred_for" in metadata:
            use_when = metadata["preferred_for"]
        if "use_when" in capability:
            use_when.append(capability["use_when"])

        # 从 keywords 生成使用场景
        keywords = metadata.get("keywords", [])
        if keywords and not use_when:
            use_when = [f"涉及 {', '.join(keywords[:3])} 相关任务"]

        # 示例
        examples = []
        if "input_schema" in capability:
            schema = capability["input_schema"]
            example_input = {}
            for prop, prop_def in schema.get("properties", {}).items():
                if prop in schema.get("required", []):
                    if prop_def.get("type") == "string":
                        example_input[prop] = f"<{prop}>"
            if example_input:
                examples.append({"input": example_input})

        # 性能特征
        performance = {}
        if "cost" in capability:
            cost = capability["cost"]
            performance["latency"] = cost.get("time", "medium")
            performance["cost"] = cost.get("money", "low")

        return cls(
            name=name,
            description=description,
            use_when=use_when,
            not_use_when=[],
            examples=examples,
            composition_hints=[],
            common_errors=[],
            output_schema={},
            performance=performance,
        )


class ToolDescriptionEnhancer:
    """
    工具描述增强器

    职责：
    - 加载和管理 LLM 友好的工具描述
    - 为工具选择提供增强信息
    - 生成工具组合建议
    """

    def __init__(self):
        """初始化"""
        self._descriptions: Dict[str, LLMToolDescription] = {}
        self._loaded = False

    async def load(self, capabilities_path: str = None, llm_descriptions_path: str = None):
        """
        加载工具描述

        Args:
            capabilities_path: capabilities.yaml 路径
            llm_descriptions_path: LLM 描述文件路径（可选，覆盖/扩展）
        """
        # 从 capabilities.yaml 加载基础信息
        if capabilities_path:
            await self._load_from_capabilities(capabilities_path)

        # 从专用文件加载增强信息（覆盖）
        if llm_descriptions_path:
            await self._load_llm_descriptions(llm_descriptions_path)

        self._loaded = True
        logger.info(f"✅ ToolDescriptionEnhancer: {len(self._descriptions)} 个工具")

    async def _load_from_capabilities(self, path: str):
        """从 capabilities.yaml 加载"""
        try:
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                content = await f.read()
                data = yaml.safe_load(content)

            for cap in data.get("capabilities", []):
                name = cap.get("name", "")
                if name:
                    self._descriptions[name] = LLMToolDescription.from_capability(cap)

            logger.debug(f"从 capabilities.yaml 加载 {len(self._descriptions)} 个工具描述")
        except Exception as e:
            logger.warning(f"加载 capabilities.yaml 失败: {e}")

    async def _load_llm_descriptions(self, path: str):
        """从 LLM 描述文件加载（YAML 格式）"""
        try:
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                content = await f.read()
                data = yaml.safe_load(content)

            for tool_data in data.get("tools", []):
                name = tool_data.get("name", "")
                if name:
                    desc = LLMToolDescription.from_dict(tool_data)

                    # 合并而非覆盖
                    if name in self._descriptions:
                        existing = self._descriptions[name]
                        if not desc.description:
                            desc.description = existing.description
                        desc.use_when = desc.use_when or existing.use_when
                        desc.not_use_when = desc.not_use_when or existing.not_use_when

                    self._descriptions[name] = desc

            logger.debug(f"从 LLM 描述文件加载/更新 {len(data.get('tools', []))} 个工具")
        except Exception as e:
            logger.warning(f"加载 LLM 描述文件失败: {e}")

    def get(self, tool_name: str) -> Optional[LLMToolDescription]:
        """获取工具描述"""
        return self._descriptions.get(tool_name)

    def get_all(self) -> Dict[str, LLMToolDescription]:
        """获取所有工具描述"""
        return self._descriptions.copy()

    def generate_tool_context(
        self, tool_names: List[str], include_examples: bool = True, include_hints: bool = True
    ) -> str:
        """
        为指定工具生成上下文描述

        Args:
            tool_names: 工具名称列表
            include_examples: 是否包含示例
            include_hints: 是否包含组合建议

        Returns:
            格式化的上下文文本
        """
        parts = ["## 可用工具说明\n"]

        for name in tool_names:
            desc = self._descriptions.get(name)
            if desc:
                parts.append(desc.to_llm_prompt())
                parts.append("")

        return "\n".join(parts)

    def get_composition_hints(self, primary_tool: str) -> List[Dict[str, Any]]:
        """
        获取工具组合建议

        Args:
            primary_tool: 主工具名称

        Returns:
            组合建议列表
        """
        desc = self._descriptions.get(primary_tool)
        if not desc:
            return []

        return desc.composition_hints


# 预定义的 LLM 友好工具描述
DEFAULT_LLM_DESCRIPTIONS = """
tools:
  - name: web_search
    description: 搜索互联网获取实时信息
    use_when:
      - 需要获取最新/实时信息
      - 需要搜索公开网页内容
      - 需要查找特定网站或资源
      - 事实核查或信息验证
    not_use_when:
      - 查询用户个人数据（使用 memory 代替）
      - 静态知识问题（直接回答即可）
      - 需要用户上传的文档（使用 knowledge_search）
    examples:
      - input: {"query": "2024年AI发展趋势"}
        output: {"results": [{"title": "...", "snippet": "...", "url": "..."}]}
        explanation: 搜索最新AI趋势信息
    composition_hints:
      - pattern: search_then_summarize
        sequence: ["web_search", "内容总结"]
        when: 搜索信息后需要整理摘要
      - pattern: multi_source_research
        sequence: ["web_search", "api_calling", "综合分析"]
        when: 需要多源信息对比
    performance:
      latency: medium
      cost: low
      reliability: high

  - name: knowledge_search
    description: 从用户个人知识库检索信息
    use_when:
      - 用户提到"我的文档"、"我上传的"、"之前的资料"
      - 需要查找用户历史上传的内容
      - 个人知识回忆场景
    not_use_when:
      - 搜索公开互联网信息（使用 web_search）
      - 用户没有上传过相关文档
    examples:
      - input: {"query": "找一下我上传的产品文档"}
        output: {"results": [{"content": "...", "source": "产品文档.pdf"}]}
    performance:
      latency: fast
      cost: low
      reliability: high

  - name: data_analysis_skill
    description: 数据分析和可视化（通过 Skill + api_calling）
    use_when:
      - 需要分析 Excel/CSV 数据
      - 需要生成数据图表
      - 涉及销售、财务等数据分析
    not_use_when:
      - 简单的数学计算（直接计算）
      - 没有数据文件的分析请求
    composition_hints:
      - pattern: upload_then_analyze
        sequence: ["文件上传", "data_analysis_skill"]
        when: 用户有数据文件需要分析
    performance:
      latency: medium
      cost: low
      reliability: high

  - name: ppt_skill
    description: 生成专业 PPT 演示文稿（通过 PPT Skill + api_calling）
    use_when:
      - 需要创建 PPT/演示文稿
      - 需要专业设计的幻灯片
      - 包含图表、图片的演示
    not_use_when:
      - 简单的文字文档（使用文档 Skill）
      - 快速草稿（使用 PPT Skill）
    composition_hints:
      - pattern: research_then_ppt
        sequence: ["web_search", "内容规划", "ppt_skill"]
        when: 需要先搜索素材再生成PPT
    performance:
      latency: slow
      cost: low
      reliability: high
"""


async def create_tool_description_enhancer(
    capabilities_path: str = None, use_defaults: bool = True
) -> ToolDescriptionEnhancer:
    """
    创建工具描述增强器

    Args:
        capabilities_path: capabilities.yaml 路径
        use_defaults: 是否使用默认 LLM 描述

    Returns:
        ToolDescriptionEnhancer
    """
    enhancer = ToolDescriptionEnhancer()
    await enhancer.load(capabilities_path=capabilities_path)

    if use_defaults:
        # 加载默认描述
        import io

        data = yaml.safe_load(io.StringIO(DEFAULT_LLM_DESCRIPTIONS))
        for tool_data in data.get("tools", []):
            name = tool_data.get("name", "")
            if name:
                desc = LLMToolDescription.from_dict(tool_data)
                enhancer._descriptions[name] = desc

    return enhancer
