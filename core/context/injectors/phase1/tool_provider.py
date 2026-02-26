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

    def __init__(self) -> None:
        super().__init__()
        # 缓存上一轮有效的 skill_groups，用于 is_follow_up 时继承
        # 避免用户追问"继续"时 LLM 返回空 groups 导致技能丢失
        self._last_skill_groups: List[str] | None = None

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
        动态生成 Skills 提示词（双信号源重召回注入）

        信号源（union 合并，宁多勿漏）：
        1. Step-Aware Intent: IntentAnalyzer 感知当前步骤语义，每轮推断
        2. Plan required_skills: 主模型在创建 plan 时声明，跨轮持久

        优先级链：
        1. intent.relevant_skill_groups 有值 -> 按分组过滤注入
        2. Plan.required_skills 存在 -> 反查分组，与 intent union 合并
        3. intent.relevant_skill_groups 为 None -> Fallback 全量注入（保守）
        4. 无 intent -> 使用缓存的静态 skills_prompt
        """
        # 尝试动态生成（需要 skills_loader 和 group_registry）
        if context.has_prompt_cache and context.prompt_cache.runtime_context:
            skills_loader = context.prompt_cache.runtime_context.get("_skills_loader")
            group_registry = context.prompt_cache.runtime_context.get(
                "_skill_group_registry"
            )

            if skills_loader and hasattr(skills_loader, "build_skills_prompt"):
                # 从 intent 获取 relevant_skill_groups
                relevant_groups = None  # None = Fallback 全量
                if context.intent and hasattr(context.intent, "relevant_skill_groups"):
                    groups = context.intent.relevant_skill_groups
                    if isinstance(groups, list) and len(groups) > 0:
                        relevant_groups = groups
                        self._last_skill_groups = groups
                    elif isinstance(groups, list) and len(groups) == 0:
                        is_follow_up = getattr(context.intent, "is_follow_up", False)
                        if is_follow_up and self._last_skill_groups:
                            relevant_groups = self._last_skill_groups
                            logger.info(
                                f"Skills follow-up 继承: {self._last_skill_groups}"
                            )
                        else:
                            relevant_groups = groups
                    # groups is None → relevant_groups stays None → 全量 Fallback

                # Plan required_skills 补偿（union 合并，重召回安全网）
                relevant_groups = self._merge_plan_skills(
                    relevant_groups, context, group_registry
                )

                try:
                    prompt = await skills_loader.build_skills_prompt(
                        language="zh",
                        relevant_skill_groups=relevant_groups,
                        group_registry=group_registry,
                    )
                    if prompt:
                        logger.info(
                            f"Skills 动态注入: groups={relevant_groups}, "
                            f"{len(prompt)} 字符"
                        )
                        return prompt
                except Exception as e:
                    logger.warning(f"Skills 动态生成失败，Fallback 到静态: {e}")

        # Fallback: 使用启动时缓存的静态 skills_prompt
        if context.has_prompt_cache and context.prompt_cache.runtime_context:
            return context.prompt_cache.runtime_context.get("skills_prompt", "")

        return ""

    @staticmethod
    def _merge_plan_skills(
        intent_groups, context: InjectionContext, group_registry
    ):
        """
        Plan required_skills union merge (recall safety net).

        Supplements intent-driven groups with plan-level required_skills.
        Both Step-Aware intent analysis and this mechanism operate
        independently — their union maximizes recall.

        Skip conditions:
        - intent_groups is None (full fallback, already maximal)
        - No plan or no required_skills in plan
        """
        if intent_groups is None:
            return None

        if not group_registry or not hasattr(group_registry, "get_groups_for_skill"):
            return intent_groups

        plan = context.get("plan")
        if not plan or not isinstance(plan, dict):
            return intent_groups

        plan_skills = plan.get("required_skills")
        if not plan_skills or not isinstance(plan_skills, list):
            return intent_groups

        plan_groups = set()
        for skill_name in plan_skills:
            if not isinstance(skill_name, str):
                continue
            groups_for_skill = group_registry.get_groups_for_skill(skill_name)
            plan_groups.update(groups_for_skill)

        plan_groups.discard("_always")

        if not plan_groups:
            return intent_groups

        intent_set = set(intent_groups)
        added = plan_groups - intent_set
        if added:
            merged = sorted(intent_set | plan_groups)
            logger.info(
                f"Plan required_skills 补偿: "
                f"intent={intent_groups}, +groups={sorted(added)}, "
                f"merged={merged}"
            )
            return merged

        return intent_groups

