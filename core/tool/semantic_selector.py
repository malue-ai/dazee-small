"""
LLM 语义驱动的工具选择器

V5.1 核心改进：
- 删除硬编码评分算法（type_weights, subtype_weights, keyword_match）
- 利用 LLM 的推理能力选择最合适的工具
- 运营只需定义工具的清晰描述和使用场景

设计原则（Prompt-First）：
- 规则写在 Prompt 里，不写在代码里
- 让 LLM 根据工具描述自主推理
- 代码只做调用和解析，不做规则判断

Date: 2026-01-12
"""

import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

from logger import get_logger

logger = get_logger("semantic_selector")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 数据结构
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class ToolDescription:
    """
    工具描述（运营配置）
    
    运营只需要定义以下字段：
    - name: 工具名称
    - description: 清晰的功能描述
    - use_cases: 适用场景列表
    - constraints: 使用限制（可选）
    """
    name: str
    description: str
    use_cases: List[str]
    constraints: Optional[List[str]] = None
    
    def to_prompt_text(self) -> str:
        """转换为 Prompt 文本（供 LLM 阅读）"""
        text = f"## {self.name}\n"
        text += f"**功能**: {self.description}\n"
        text += f"**适用场景**:\n"
        for case in self.use_cases:
            text += f"  - {case}\n"
        if self.constraints:
            text += f"**限制**:\n"
            for c in self.constraints:
                text += f"  - {c}\n"
        return text


@dataclass
class SelectionResult:
    """工具选择结果"""
    selected_tool: str
    reasoning: str
    confidence: str  # high/medium/low
    alternatives: Optional[List[str]] = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Few-Shot 示例（核心：教会 LLM 如何选择工具）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TOOL_SELECTION_EXAMPLES = """
<example>
<user_query>帮我生成一个产品介绍的PPT</user_query>
<available_tools>
- pptx: 生成 PowerPoint 演示文稿，支持模板和自定义样式
- docx: 生成 Word 文档，适合长文本报告
- xlsx: 生成 Excel 表格，适合数据分析
</available_tools>
<reasoning>
用户明确要求生成 PPT，这是演示文稿任务。
pptx 工具专门用于生成 PowerPoint，完全匹配需求。
</reasoning>
<selected_tool>pptx</selected_tool>
<confidence>high</confidence>
</example>

<example>
<user_query>分析销售数据，找出趋势</user_query>
<available_tools>
- sandbox_run_code: 在沙箱中执行 Python 代码，适合数据处理和分析
- xlsx: 生成 Excel 表格
- exa_search: 网络搜索
</available_tools>
<reasoning>
用户需要分析数据、找趋势，这是数据分析任务。
sandbox_run_code 可以运行 Python（pandas/matplotlib），最适合数据分析。
xlsx 只能生成表格，不能分析。
</reasoning>
<selected_tool>sandbox_run_code</selected_tool>
<confidence>high</confidence>
</example>

<example>
<user_query>查一下最近AI领域的新闻</user_query>
<available_tools>
- exa_search: 搜索网络内容，获取最新信息
- knowledge_search: 搜索本地知识库
- sandbox_run_code: 执行代码
</available_tools>
<reasoning>
用户要查"最近"的新闻，需要实时网络信息。
exa_search 专门用于网络搜索，可获取最新内容。
knowledge_search 只能搜索本地已有知识，无法获取最新新闻。
</reasoning>
<selected_tool>exa_search</selected_tool>
<confidence>high</confidence>
</example>

<example>
<user_query>帮我整理一下这个会议的要点</user_query>
<available_tools>
- docx: 生成 Word 文档
- pptx: 生成 PPT
- text_response: 直接文本回复
</available_tools>
<reasoning>
用户说"整理要点"，没有明确要求生成文档格式。
会议要点的整理通常是文字列表形式。
text_response 直接回复最简洁，除非用户明确要求文档。
</reasoning>
<selected_tool>text_response</selected_tool>
<confidence>medium</confidence>
<alternatives>docx（如果用户需要正式文档）</alternatives>
</example>
"""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 工具选择提示词模板
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TOOL_SELECTION_PROMPT = """你是一个工具选择专家，负责根据用户需求选择最合适的工具。

## 选择原则

1. **精准匹配**: 选择最直接满足用户需求的工具
2. **最小原则**: 能用简单工具解决的，不用复杂工具
3. **明确优先**: 用户明确指定的工具类型优先
4. **场景理解**: 理解用户真正的意图，而不仅是字面意思

## 可用工具列表

{tool_descriptions}

## Few-Shot 示例

{examples}

## 输出格式

请用 JSON 格式输出：
```json
{{
  "selected_tool": "工具名称",
  "reasoning": "选择理由（一句话）",
  "confidence": "high/medium/low",
  "alternatives": ["备选工具1", "备选工具2"]  // 可选
}}
```

---

## 当前任务

<user_query>{user_query}</user_query>

请选择最合适的工具："""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 语义工具选择器
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SemanticToolSelector:
    """
    LLM 语义驱动的工具选择器
    
    核心理念：
    - 不使用硬编码评分规则
    - 让 LLM 根据工具描述自主推理选择
    - 运营只需配置清晰的工具描述
    
    Example:
        selector = SemanticToolSelector(llm_service)
        
        # 注册工具描述（运营配置）
        selector.register_tool(ToolDescription(
            name="pptx",
            description="生成 PowerPoint 演示文稿",
            use_cases=["制作产品介绍", "生成汇报材料", "创建培训课件"]
        ))
        
        # LLM 自动选择最佳工具
        result = await selector.select("帮我做一个季度汇报的 PPT")
        print(result.selected_tool)  # "pptx"
    """
    
    def __init__(self, llm_service=None):
        """
        初始化选择器
        
        Args:
            llm_service: LLM 服务（用于推理）
        """
        self.llm_service = llm_service
        self.tools: Dict[str, ToolDescription] = {}
        
        # 使用配置的 profile（或默认 Haiku）
        self._llm_profile = "tool_selector"
    
    def register_tool(self, tool: ToolDescription):
        """
        注册工具描述
        
        Args:
            tool: 工具描述
        """
        self.tools[tool.name] = tool
        logger.debug(f"注册工具: {tool.name}")
    
    def register_tools_from_config(self, config: Dict[str, Any]):
        """
        从配置文件批量注册工具
        
        配置格式（运营友好）：
        ```yaml
        tools:
          pptx:
            description: "生成 PowerPoint 演示文稿"
            use_cases:
              - "制作产品介绍"
              - "生成汇报材料"
          xlsx:
            description: "生成 Excel 表格"
            use_cases:
              - "数据汇总"
              - "报表生成"
        ```
        """
        tools_config = config.get('tools', {})
        
        for name, tool_config in tools_config.items():
            tool = ToolDescription(
                name=name,
                description=tool_config.get('description', name),
                use_cases=tool_config.get('use_cases', []),
                constraints=tool_config.get('constraints')
            )
            self.register_tool(tool)
        
        logger.info(f"从配置注册 {len(tools_config)} 个工具")
    
    def _build_tool_descriptions_text(self) -> str:
        """构建工具描述文本（供 LLM 阅读）"""
        if not self.tools:
            return "（无可用工具）"
        
        texts = []
        for tool in self.tools.values():
            texts.append(tool.to_prompt_text())
        
        return "\n".join(texts)
    
    async def select(
        self,
        user_query: str,
        context: Optional[Dict[str, Any]] = None
    ) -> SelectionResult:
        """
        选择最合适的工具
        
        Args:
            user_query: 用户查询
            context: 上下文信息（可选）
            
        Returns:
            SelectionResult
        """
        if not self.tools:
            logger.warning("没有可用工具，返回默认 text_response")
            return SelectionResult(
                selected_tool="text_response",
                reasoning="没有可用工具，使用文本回复",
                confidence="low"
            )
        
        # 构建提示词
        prompt = TOOL_SELECTION_PROMPT.format(
            tool_descriptions=self._build_tool_descriptions_text(),
            examples=TOOL_SELECTION_EXAMPLES,
            user_query=user_query
        )
        
        # 调用 LLM 推理
        try:
            response = await self._call_llm(prompt)
            result = self._parse_response(response)
            
            logger.info(
                f"工具选择: {result.selected_tool} "
                f"(confidence={result.confidence}, reason={result.reasoning})"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"工具选择失败: {e}")
            # Fallback: 返回第一个工具
            first_tool = next(iter(self.tools.keys()))
            return SelectionResult(
                selected_tool=first_tool,
                reasoning=f"LLM 推理失败，使用默认工具: {e}",
                confidence="low"
            )
    
    async def _call_llm(self, prompt: str) -> str:
        """调用 LLM"""
        if self.llm_service is None:
            # 懒加载 LLM 服务
            from config.llm_config import get_llm_profile
            from core.llm import create_llm_service
            
            profile = get_llm_profile(self._llm_profile)
            self.llm_service = create_llm_service(**profile)
        
        response = await self.llm_service.create_message(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0  # 工具选择需要确定性
        )
        
        # 提取文本内容
        if hasattr(response, 'content') and response.content:
            for block in response.content:
                if hasattr(block, 'text'):
                    return block.text
        
        return str(response)
    
    def _parse_response(self, response: str) -> SelectionResult:
        """解析 LLM 响应"""
        try:
            # 提取 JSON 部分
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                data = json.loads(json_str)
                
                return SelectionResult(
                    selected_tool=data.get('selected_tool', ''),
                    reasoning=data.get('reasoning', ''),
                    confidence=data.get('confidence', 'medium'),
                    alternatives=data.get('alternatives')
                )
        except json.JSONDecodeError as e:
            logger.warning(f"JSON 解析失败: {e}")
        
        # Fallback: 简单文本解析
        return SelectionResult(
            selected_tool=response.strip().split('\n')[0],
            reasoning="无法解析 LLM 响应",
            confidence="low"
        )
    
    def select_sync(
        self,
        user_query: str,
        tools: List[ToolDescription]
    ) -> str:
        """
        同步选择（不使用 LLM，基于简单规则）
        
        用于：
        - LLM 不可用时的 fallback
        - 明显简单的场景
        
        Args:
            user_query: 用户查询
            tools: 工具列表
            
        Returns:
            工具名称
        """
        query_lower = user_query.lower()
        
        # 简单关键词匹配（仅作为 fallback）
        for tool in tools:
            # 检查工具名称是否在查询中
            if tool.name.lower() in query_lower:
                return tool.name
            
            # 检查使用场景关键词
            for case in tool.use_cases:
                if any(word in query_lower for word in case.lower().split()):
                    return tool.name
        
        # 默认返回第一个
        return tools[0].name if tools else "text_response"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 工厂函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def create_semantic_selector(
    llm_service=None,
    tools_config: Optional[Dict[str, Any]] = None
) -> SemanticToolSelector:
    """
    创建语义工具选择器
    
    Args:
        llm_service: LLM 服务（可选，懒加载）
        tools_config: 工具配置（可选）
        
    Returns:
        SemanticToolSelector 实例
    """
    selector = SemanticToolSelector(llm_service)
    
    if tools_config:
        selector.register_tools_from_config(tools_config)
    
    return selector


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 与现有系统集成
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def convert_capability_to_tool_description(capability) -> ToolDescription:
    """
    将现有 Capability 转换为 ToolDescription
    
    兼容现有系统，逐步迁移
    """
    return ToolDescription(
        name=capability.name,
        description=capability.metadata.get('description', capability.name),
        use_cases=capability.metadata.get('preferred_for', []),
        constraints=list(capability.constraints.keys()) if capability.constraints else None
    )
