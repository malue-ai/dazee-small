"""
ToolSystemRoleProvider - 工具定义提供器

职责：
1. 从 InjectionContext.available_tools 获取工具定义
2. 格式化为 LLM 可理解的工具描述
3. 追加 APIs 文档（如果有）

缓存策略：STABLE（1h 缓存）
注入位置：Phase 1 - System Message
优先级：80（在角色定义之后）
"""

from typing import Any, Dict, List

from logger import get_logger

from ..base import BaseInjector, CacheStrategy, InjectionPhase, InjectionResult
from ..context import InjectionContext

logger = get_logger("injectors.phase1.tool_provider")


class ToolSystemRoleProvider(BaseInjector):
    """
    工具定义提供器

    将可用工具格式化为 LLM 可理解的描述。

    输出示例：
    ```
    # 可用工具

    You have access to these tools:

    <tool name="search_skill">
    通过搜索类 Skill 或 api_calling 获取最新信息
    </tool>

    <tool name="code_execute">
    执行代码
    </tool>
    ```
    """

    @property
    def name(self) -> str:
        return "tool_provider"

    @property
    def phase(self) -> InjectionPhase:
        return InjectionPhase.SYSTEM

    @property
    def cache_strategy(self) -> CacheStrategy:
        return CacheStrategy.STABLE

    @property
    def priority(self) -> int:
        # 在角色定义之后
        return 80

    async def should_inject(self, context: InjectionContext) -> bool:
        """只有存在工具时才注入"""
        return context.has_tools

    async def inject(self, context: InjectionContext) -> InjectionResult:
        """
        注入工具定义

        1. 格式化可用工具为 XML 格式
        2. 追加 APIs 文档（如果有）
        """
        parts = []

        # 1. 格式化工具定义
        tools_text = self._format_tools(context.available_tools)
        if tools_text:
            parts.append(tools_text)

        # 2. 追加 APIs 文档
        apis_prompt = await self._get_apis_prompt(context)
        if apis_prompt:
            parts.append(apis_prompt)

        # 3. 追加 Skills 文档
        skills_prompt = await self._get_skills_prompt(context)
        if skills_prompt:
            parts.append(skills_prompt)

        if not parts:
            logger.debug("ToolSystemRoleProvider: 无工具可注入")
            return InjectionResult()

        content = "\n\n".join(parts)
        logger.info(
            f"ToolSystemRoleProvider: {len(context.available_tools)} 工具, " f"{len(content)} 字符"
        )

        return InjectionResult(content=content)

    def _format_tools(self, tools: List[Dict[str, Any]]) -> str:
        """
        格式化工具列表为 XML 格式

        输出示例：
        ```
        # 可用工具

        You have access to these tools:

        <tool name="search_skill">
        通过搜索类 Skill 或 api_calling 获取最新信息
        参数：
        - query (string, required): 搜索查询
        </tool>
        ```
        """
        if not tools:
            return ""

        lines = ["# 可用工具", "", "You have access to these tools:", ""]

        for tool in tools:
            name = tool.get("name", "unknown")
            description = tool.get("description", "")
            input_schema = tool.get("input_schema", {})

            # 构建工具描述
            tool_lines = [f'<tool name="{name}">']

            if description:
                tool_lines.append(description)

            # 添加参数描述
            if input_schema:
                properties = input_schema.get("properties", {})
                required = input_schema.get("required", [])

                if properties:
                    tool_lines.append("")
                    tool_lines.append("参数：")

                    for prop_name, prop_info in properties.items():
                        prop_type = prop_info.get("type", "any")
                        prop_desc = prop_info.get("description", "")
                        is_required = prop_name in required

                        req_str = "required" if is_required else "optional"

                        if prop_desc:
                            tool_lines.append(
                                f"- {prop_name} ({prop_type}, {req_str}): {prop_desc}"
                            )
                        else:
                            tool_lines.append(f"- {prop_name} ({prop_type}, {req_str})")

            tool_lines.append("</tool>")
            lines.extend(tool_lines)
            lines.append("")

        return "\n".join(lines)

    async def _get_apis_prompt(self, context: InjectionContext) -> str:
        """
        从 prompt_cache.runtime_context 获取 APIs 文档
        """
        if not context.has_prompt_cache:
            return ""

        prompt_cache = context.prompt_cache

        if not prompt_cache.runtime_context:
            return ""

        return prompt_cache.runtime_context.get("apis_prompt", "")

    async def _get_skills_prompt(self, context: InjectionContext) -> str:
        """
        从 prompt_cache.runtime_context 获取 Skills 文档
        """
        if not context.has_prompt_cache:
            return ""

        prompt_cache = context.prompt_cache

        if not prompt_cache.runtime_context:
            return ""

        return prompt_cache.runtime_context.get("skills_prompt", "")
