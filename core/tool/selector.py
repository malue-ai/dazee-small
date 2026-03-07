"""
ToolSelector - 工具选择器

合并自：
- core/tool/selector.py (原 ToolSelector)
- core/tool/capability/router.py (CapabilityRouter)
- core/tool/unified_tool_caller.py (UnifiedToolCaller)

职责：
1. 根据意图和能力需求选择合适的工具
2. 管理基础工具和动态工具的选择
3. 提供工具 Schema 转换（用于 LLM API）
4. 智能路由推荐（原 CapabilityRouter）
5. Skill fallback 处理（原 UnifiedToolCaller）

设计原则：
- 单一职责：工具选择和路由
- 配置驱动：工具配置从 capabilities.yaml 加载
- LLM-First：关键词匹配仅作为辅助排序
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from core.tool.types import Capability, CapabilityType
from logger import get_logger

logger = get_logger(__name__)


# 延迟导入，避免循环依赖
def _get_registry():
    from core.tool.registry import get_capability_registry

    return get_capability_registry()


async def _get_core_tools_async():
    """异步获取核心工具"""
    from core.tool.registry_config import get_core_tools

    return await get_core_tools()


@dataclass
class ToolSelectionResult:
    """
    工具选择结果

    包含选中的工具列表和选择原因
    """

    tools: List[Any]  # 选中的工具列表（Capability 对象）
    tool_names: List[str]  # 工具名称列表
    base_tools: List[str]  # 基础工具名称
    dynamic_tools: List[str]  # 动态选择的工具名称
    reason: str = ""  # 选择原因

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "tool_names": self.tool_names,
            "base_tools": self.base_tools,
            "dynamic_tools": self.dynamic_tools,
            "total_count": len(self.tools),
            "reason": self.reason,
        }


@dataclass
class RoutingResult:
    """
    路由结果（原 CapabilityRouter）

    包含推荐的能力和评分
    """

    capability: Capability
    score: float
    reason: str
    alternatives: List[Tuple[Capability, float]] = None  # 备选方案


class ToolSelector:
    """
    工具选择器（合并 CapabilityRouter + UnifiedToolCaller）

    根据任务需求智能选择合适的工具。

    工具分层设计：
    - Level 1（核心工具）：始终加载，如 plan_todo
    - Level 2（动态工具）：按需加载，如 Skill 关联工具

    使用方式:
        selector = ToolSelector(registry)

        # 方式1：根据能力需求选择
        result = selector.select(
            required_capabilities=["web_search", "ppt_generation"],
            context={"task_type": "content_generation"}
        )

        # 方式2：智能路由推荐（原 CapabilityRouter）
        routing = selector.route(keywords=["PPT", "演示"])

        # 方式3：Skill fallback（原 UnifiedToolCaller）
        caps = selector.ensure_skill_fallback(caps, skill, llm_service)
    """

    # 类型权重（路由评分用）
    TYPE_WEIGHTS = {
        CapabilityType.SKILL: 10,
        CapabilityType.TOOL: 8,
        CapabilityType.CODE: 4,
    }

    # 子类型权重
    SUBTYPE_WEIGHTS = {"CUSTOM": 15, "PREBUILT": 10, "NATIVE": 8, "EXTERNAL": 5, "DYNAMIC": 3}

    def __init__(self, registry=None):
        """
        初始化工具选择器

        Args:
            registry: CapabilityRegistry 实例（可选，默认使用单例）
        """
        self._registry = registry
        self._core_tools_cache: Optional[List[str]] = None

    @property
    def registry(self):
        """延迟获取 Registry（避免循环导入）"""
        if self._registry is None:
            self._registry = _get_registry()
        return self._registry

    def _extract_capability_tags(self, tool_names: List[str]) -> List[str]:
        """
        从工具名列表提取对应的能力标签（去重保序）

        解决「工具名 ≠ 能力标签」的概念映射问题。
        例如：工具名 "plan" → 能力标签 ["task_planning", "progress_tracking"]

        Args:
            tool_names: 工具名列表

        Returns:
            去重后的能力标签列表
        """
        seen: set = set()
        tags: List[str] = []
        missing: List[str] = []
        for name in tool_names:
            cap = self.registry.get(name)
            if cap and cap.capabilities:
                for tag in cap.capabilities:
                    if tag not in seen:
                        seen.add(tag)
                        tags.append(tag)
            else:
                missing.append(name)
        if missing:
            logger.debug(
                f"{len(missing)} 个工具无 capabilities 标签: "
                f"{', '.join(missing[:5])}{'...' if len(missing) > 5 else ''}"
            )
        return tags

    async def get_core_tools(self) -> List[str]:
        """
        获取核心工具名称列表（Level 1）（异步）

        核心工具始终加载，不受动态选择影响。
        优先从 capabilities.yaml 读取 level=1 的工具，
        如果没有则使用配置文件中的默认列表。

        Returns:
            核心工具名称列表
        """
        if self._core_tools_cache is not None:
            return self._core_tools_cache

        # 从 Registry 获取 Level 1 工具
        core_caps = self.registry.get_core_tools()

        if core_caps:
            self._core_tools_cache = [c.name for c in core_caps]
        else:
            # 备用：从配置文件读取（异步）
            self._core_tools_cache = await _get_core_tools_async()

        logger.debug(f"核心工具 (Level 1): {self._core_tools_cache}")
        return self._core_tools_cache

    def get_cacheable_tools(self) -> List[str]:
        """
        获取可缓存工具名称列表

        cache_stable=true 的工具，同输入产生同输出，
        可安全使用 prompt cache。

        Returns:
            可缓存工具名称列表
        """
        return self.registry.get_cacheable_tools()

    async def select(
        self,
        required_capabilities: List[str],
        context: Optional[Dict[str, Any]] = None,
        allowed_tools: Optional[List[str]] = None,
        core_tools_override: Optional[List[str]] = None,
    ) -> ToolSelectionResult:
        """
        选择工具（异步）

        分层选择逻辑：
        1. 加载核心工具（Level 1），可通过 core_tools_override 精简
        2. 根据能力需求从动态工具中选择
        3. 如果提供了 allowed_tools，则仅选择白名单内的工具

        Args:
            required_capabilities: 所需能力标签列表（如 ["task_planning", "knowledge_base"]）
            context: 上下文信息（包含 task_type, available_apis 等）
            allowed_tools: 允许使用的工具白名单（可选，工具名列表）
            core_tools_override: 覆盖核心工具列表（可选，工具名列表）。
                提供时仅加载指定的核心工具，用于 simple task 场景裁剪。

        Returns:
            ToolSelectionResult 选择结果
        """
        context = context or {}
        selected = []
        selected_skills_capabilities = set()

        # 1. 添加核心工具（Level 1）
        #    默认加载全部核心工具；提供 core_tools_override 时仅加载指定子集
        base_tools = []
        if core_tools_override is not None:
            core_tool_names = core_tools_override
        else:
            core_tool_names = await self.get_core_tools()
        for name in core_tool_names:
            cap = self.registry.get(name)
            if cap and cap not in selected:
                selected.append(cap)
                base_tools.append(name)

        # 2. 根据能力标签选择工具
        dynamic_tools = []
        fallback_tools_to_add = []

        for capability_tag in required_capabilities:
            matched = self.registry.find_by_capability_tag(capability_tag)

            if not matched:
                logger.warning(f"未找到匹配能力的工具: {capability_tag}")
                continue

            # 按优先级排序
            matched.sort(key=lambda c: c.priority, reverse=True)

            for tool in matched:
                # 0. 检查白名单过滤 (Schema 限制)
                if allowed_tools is not None and tool.name not in allowed_tools:
                    continue

                # 检查约束条件
                if not tool.meets_constraints(context):
                    continue

                if tool not in selected:
                    selected.append(tool)
                    dynamic_tools.append(tool.name)

                    # 如果是 Skill，收集其能力需求
                    if tool.type == CapabilityType.SKILL:
                        selected_skills_capabilities.update(tool.capabilities)

                        # 如果 SKILL 有 fallback_tool，添加到待处理列表
                        if tool.fallback_tool:
                            fallback_tools_to_add.append(tool.fallback_tool)
                            logger.debug(
                                f"SKILL '{tool.name}' 指定 fallback_tool: {tool.fallback_tool}"
                            )

        # 3. 优先添加 fallback 工具
        for fallback_name in fallback_tools_to_add:
            # 检查白名单
            if allowed_tools is not None and fallback_name not in allowed_tools:
                continue

            fallback_cap = self.registry.get(fallback_name)
            if fallback_cap and fallback_cap not in selected:
                if fallback_cap.meets_constraints(context):
                    selected.append(fallback_cap)
                    dynamic_tools.append(fallback_name)
                    logger.info(f"添加 fallback 工具: {fallback_name}")

        # 4. 自动包含 Skills 依赖的底层工具
        for skill_capability in selected_skills_capabilities:
            tools_for_capability = [
                c
                for c in self.registry.find_by_capability_tag(skill_capability)
                if c.type == CapabilityType.TOOL
            ]

            for tool in tools_for_capability:
                # 依赖工具是否受白名单限制？
                # 通常依赖工具应该是隐式允许的，但为了严格控制，我们也应用白名单
                # 除非 schema 配置者不知道底层依赖。
                # 策略：如果 allowed_tools 存在，严格检查。
                if allowed_tools is not None and tool.name not in allowed_tools:
                    continue

                if tool not in selected and tool.meets_constraints(context):
                    selected.append(tool)
                    dynamic_tools.append(tool.name)
                    logger.debug(f"自动包含工具 {tool.name} (Skills 依赖)")

        # 5. 按优先级排序
        selected.sort(key=lambda c: c.priority, reverse=True)

        # 6. 提取工具名称
        tool_names = [t.name for t in selected]

        logger.info(
            f"工具选择完成: 基础={len(base_tools)}, "
            f"动态={len(dynamic_tools)}, 总计={len(tool_names)}"
        )

        return ToolSelectionResult(
            tools=selected,
            tool_names=tool_names,
            base_tools=base_tools,
            dynamic_tools=dynamic_tools,
            reason=f"基于能力需求 {required_capabilities} 选择",
        )

    def get_tools_for_llm(self, selection: ToolSelectionResult, llm_service=None) -> List[Any]:
        """
        将选择结果转换为 LLM API 格式

        Args:
            selection: 工具选择结果
            llm_service: LLM 服务（用于 schema 转换）

        Returns:
            LLM API 格式的工具列表
        """
        tools_for_llm = []

        for tool_name in selection.tool_names:
            capability = self.registry.get(tool_name)
            if not capability:
                continue

            # 只有 TOOL 类型且有 input_schema 的才能作为 LLM API 工具
            if capability.type != CapabilityType.TOOL:
                continue

            if not capability.input_schema:
                continue

            # 转换为 LLM API 格式
            if llm_service and hasattr(llm_service, "convert_to_claude_tool"):
                capability_dict = {
                    "name": capability.name,
                    "type": capability.type.value,
                    "provider": capability.provider,
                    "metadata": capability.metadata,
                    "input_schema": capability.input_schema,
                }
                tool_schema = llm_service.convert_to_claude_tool(capability_dict)
                tools_for_llm.append(tool_schema)
            else:
                # 简化版：直接构建 schema
                tools_for_llm.append(
                    {
                        "name": capability.name,
                        "description": capability.metadata.get("description", capability.name),
                        "input_schema": capability.input_schema,
                    }
                )

        return tools_for_llm

    async def resolve_capabilities(
        self,
        schema_tools: Optional[List[str]] = None,
        plan: Optional[Dict[str, Any]] = None,
        intent_required_tools: Optional[List[str]] = None,
    ) -> Tuple[List[str], str, List[str], Optional[List[str]]]:
        """
        解析能力需求（Plan + Intent + Schema 三级优先级）

        优先级策略：
        1. Plan.required_skills：最高优先（Plan 在完整任务上下文中由 LLM 创建）
        2. Intent.required_tools：LLM 语义推断的动态工具需求
        3. Schema 配置：作为 Allowlist (白名单)
        4. 全量 fallback：加载所有注册工具

        Args:
            schema_tools: Schema 配置的工具名列表
            plan: 任务规划结果（包含 required_skills 字段）
            intent_required_tools: IntentAnalyzer LLM 推断的动态工具名列表

        Returns:
            (required_capabilities, selection_source, overridden_sources, allowed_tools) 四元组
            - required_capabilities: 最终选择的能力标签列表
            - selection_source: 选择来源（plan/intent/schema/default）
            - overridden_sources: 被覆盖的来源列表
            - allowed_tools: 允许使用的工具白名单（来自 Schema，工具名列表）
        """
        required_capabilities: List[str] = []
        selection_source = "default"
        overridden_sources: List[str] = []
        allowed_tools: Optional[List[str]] = None

        # 收集各级来源
        plan_caps: List[str] = []

        # 1. Schema 配置（白名单来源）
        if schema_tools:
            # 验证工具有效性：只保留 Registry 中存在的工具
            valid_tools = [t for t in schema_tools if self.registry.get(t)]
            invalid_tools = [t for t in schema_tools if not self.registry.get(t)]

            if invalid_tools:
                logger.debug(f"Schema 中的无效工具（已过滤）: {invalid_tools}")

            if valid_tools:
                allowed_tools = valid_tools  # 设置白名单
                logger.debug(f"Schema 白名单已设置: {len(allowed_tools)} 个工具")

        # 2. Plan 推荐
        if plan and plan.get("required_skills"):
            plan_caps = plan.get("required_skills", [])
            logger.debug(f"Plan 推荐能力: {plan_caps}")

        # 混合选择逻辑：优先使用 Plan 需求，受白名单限制

        if plan_caps:
            required_capabilities = plan_caps
            selection_source = "plan"

            if allowed_tools:
                logger.info(f"✅ 使用 Plan 推荐 (受 Schema 过滤): {required_capabilities}")
            else:
                logger.info(f"✅ 使用 Plan 推荐: {required_capabilities}")

        elif intent_required_tools:
            required_capabilities = self._extract_capability_tags(intent_required_tools)
            selection_source = "intent"
            logger.info(
                f"✅ 使用 Intent 推荐工具: "
                f"{intent_required_tools} → {required_capabilities}"
            )

        elif allowed_tools:
            required_capabilities = self._extract_capability_tags(allowed_tools)
            selection_source = "schema"
            logger.info(
                f"✅ 从 Schema 工具提取能力标签: "
                f"{len(allowed_tools)} 个工具 → {required_capabilities}"
            )

        else:
            all_tool_names = list(self.registry.capabilities.keys())
            required_capabilities = self._extract_capability_tags(all_tool_names)
            selection_source = "default"
            logger.info(
                f"全量 fallback: {len(all_tool_names)} 工具 → "
                f"{len(required_capabilities)} 个能力标签"
            )

        return required_capabilities, selection_source, overridden_sources, allowed_tools

    def get_available_apis(self, executor=None) -> List[str]:
        """
        自动发现可用的 API（从已加载的工具推断）

        Args:
            executor: ToolExecutor 实例

        Returns:
            可用 API 名称列表
        """
        available_apis = set()

        if executor is None:
            return list(available_apis)

        # 从 ToolExecutor 获取已加载的工具
        loaded_tools = getattr(executor, "_tool_instances", {})

        for tool_name, tool_instance in loaded_tools.items():
            if tool_instance is None:
                continue

            # 从 Registry 获取工具的约束配置
            capability = self.registry.get(tool_name)
            if capability and capability.constraints:
                api_name = capability.constraints.get("api_name")
                if api_name:
                    available_apis.add(api_name)

        logger.debug(f"自动发现可用 API: {list(available_apis)}")
        return list(available_apis)

    # ==================== 路由功能（原 CapabilityRouter）====================

    def route(
        self,
        keywords: List[str],
        quality_requirement: str = "medium",
        explicit_capability: str = None,
        context: Dict[str, Any] = None,
    ) -> Optional[RoutingResult]:
        """
        智能路由到最合适的能力（原 CapabilityRouter.route）

        Args:
            keywords: 用户请求中的关键词
            quality_requirement: 质量要求（low/medium/high）
            explicit_capability: 用户明确指定的能力名称
            context: 上下文

        Returns:
            RoutingResult 或 None
        """
        # 如果用户明确指定，直接返回
        if explicit_capability:
            cap = self.registry.get(explicit_capability)
            if cap:
                return RoutingResult(
                    capability=cap,
                    score=10000,
                    reason=f"Explicitly requested: {explicit_capability}",
                )

        # 查找候选能力（不传 keywords，符合 LLM-First）
        candidates = self.registry.find_candidates(context=context)

        if not candidates:
            return None

        # 计算评分
        scored: List[Tuple[Capability, float]] = []
        for cap in candidates:
            score = self._calculate_routing_score(cap, quality_requirement, context)
            scored.append((cap, score))

        # 排序
        scored.sort(key=lambda x: x[1], reverse=True)

        # 返回最佳结果
        best_cap, best_score = scored[0]

        return RoutingResult(
            capability=best_cap,
            score=best_score,
            reason=self._explain_routing_selection(best_cap, best_score),
            alternatives=scored[1:4] if len(scored) > 1 else None,
        )

    def route_multiple(
        self,
        keywords: List[str],
        top_k: int = 3,
        context: Dict[str, Any] = None,
    ) -> List[RoutingResult]:
        """
        返回前 K 个最佳能力

        Args:
            keywords: 关键词列表
            top_k: 返回数量
            context: 上下文

        Returns:
            RoutingResult 列表
        """
        candidates = self.registry.find_candidates(context=context)

        scored = []
        for cap in candidates:
            score = self._calculate_routing_score(cap, "medium", context)
            scored.append(
                RoutingResult(
                    capability=cap,
                    score=score,
                    reason=self._explain_routing_selection(cap, score),
                )
            )

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]

    def _calculate_routing_score(
        self,
        cap: Capability,
        quality_requirement: str,
        context: Dict[str, Any] = None,
    ) -> float:
        """
        计算能力评分（不依赖关键词，符合 LLM-First）。

        Score = base_priority + type_weight×5 + subtype_weight×5
              + quality_match×20 + context_bonus - cost_penalty
        """
        score = float(cap.priority)

        # 类型权重
        type_weight = self.TYPE_WEIGHTS.get(cap.type, 0)
        score += type_weight * 5

        # 子类型权重
        subtype_weight = self.SUBTYPE_WEIGHTS.get(cap.subtype, 0)
        score += subtype_weight * 5

        # 质量要求匹配
        score += self._quality_match_score(cap, quality_requirement)

        # 上下文加分
        if context:
            score += self._context_bonus(cap, context)

        # 成本惩罚
        score -= self._cost_penalty(cap)

        return max(score, 0)

    def _quality_match_score(self, cap: Capability, requirement: str) -> float:
        """计算质量匹配分数"""
        quality_levels = {"low": 1, "medium": 2, "high": 3}

        min_quality = cap.constraints.get("min_quality", "low")
        cap_quality = quality_levels.get(min_quality, 1)
        req_quality = quality_levels.get(requirement, 2)

        if cap_quality >= req_quality:
            return 20
        elif cap_quality == req_quality - 1:
            return 10
        else:
            return 0

    def _context_bonus(self, cap: Capability, context: Dict[str, Any]) -> float:
        """计算上下文加分"""
        bonus = 0

        if context.get("current_capability") == cap.name:
            bonus += 15

        recent_successes = context.get("recent_success_capabilities", [])
        if cap.name in recent_successes:
            bonus += 10

        return bonus

    def _cost_penalty(self, cap: Capability) -> float:
        """计算成本惩罚"""
        penalty = 0

        time_cost = cap.cost.get("time", "fast")
        time_penalties = {"fast": 0, "medium": 5, "slow": 15, "variable": 10}
        penalty += time_penalties.get(time_cost, 0)

        money_cost = cap.cost.get("money", "free")
        money_penalties = {"free": 0, "low": 5, "medium": 15, "high": 30}
        penalty += money_penalties.get(money_cost, 0)

        return penalty

    def _explain_routing_selection(self, cap: Capability, score: float) -> str:
        """解释为什么选择这个能力"""
        reasons = [
            f"Type: {cap.type.value}",
            f"Subtype: {cap.subtype}",
            f"Priority: {cap.priority}",
            f"Total Score: {score:.1f}",
        ]

        min_quality = cap.constraints.get("min_quality", "N/A")
        reasons.append(f"Quality: {min_quality}")

        return " | ".join(reasons)

    # ==================== Skill Fallback（原 UnifiedToolCaller）====================

    def get_fallback_tool_for_skill(self, recommended_skill: Any) -> Optional[str]:
        """
        获取 Skill 对应的 fallback_tool（原 UnifiedToolCaller）

        Args:
            recommended_skill: 推荐 Skill（dict 或 str）

        Returns:
            fallback_tool 名称
        """
        if not recommended_skill:
            return None

        if isinstance(recommended_skill, dict):
            skill_name = recommended_skill.get("name")
        else:
            skill_name = str(recommended_skill)

        if not skill_name:
            return None

        capability = self.registry.get(skill_name)
        if capability and capability.fallback_tool:
            return capability.fallback_tool
        return None

    def ensure_skill_fallback(
        self, required_capabilities: List[str], recommended_skill: Any, llm_service: Any
    ) -> List[str]:
        """
        当模型不支持 Skills 时，确保 fallback 工具被加入能力列表（原 UnifiedToolCaller）

        Args:
            required_capabilities: 原始能力列表
            recommended_skill: 推荐 Skill
            llm_service: LLM 服务实例

        Returns:
            修正后的能力列表
        """
        if not recommended_skill:
            return required_capabilities

        supports_skills = self._supports_skills_for_all_targets(llm_service)
        if supports_skills:
            return required_capabilities

        fallback_tool = self.get_fallback_tool_for_skill(recommended_skill)
        if fallback_tool and fallback_tool not in required_capabilities:
            required_capabilities = required_capabilities.copy()
            required_capabilities.append(fallback_tool)
            logger.info(f"🧩 Skill fallback 启用: {fallback_tool}")

        return required_capabilities

    def _supports_skills_for_all_targets(self, llm_service: Any) -> bool:
        """判断 LLM 服务是否对所有目标都支持 Skills"""
        targets = getattr(llm_service, "targets", None)
        if targets is not None:
            if not targets:
                return False
            for target in targets:
                service = getattr(target, "service", None)
                if not service or not hasattr(service, "supports_skills"):
                    return False
                if not service.supports_skills():
                    return False
            return True

        if hasattr(llm_service, "supports_skills"):
            return llm_service.supports_skills()
        return False


def create_tool_selector(registry=None) -> ToolSelector:
    """
    创建工具选择器

    Args:
        registry: CapabilityRegistry 实例（可选，默认使用单例）

    Returns:
        ToolSelector 实例
    """
    return ToolSelector(registry=registry)


# ==================== 导出 ====================

__all__ = [
    "ToolSelector",
    "ToolSelectionResult",
    "RoutingResult",
    "create_tool_selector",
]
