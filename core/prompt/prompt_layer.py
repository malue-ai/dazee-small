"""
提示词分层解耦模块 - Prompt Layer System

🆕 V4.6.1: LLM 驱动的语义分析

设计思路：
┌─────────────────────────────────────────────────────────────┐
│  运营写的系统提示词（任意格式：Markdown/XML/纯文本/混合）       │
│  "像写作文一样，没有严格标准"                                  │
│  instances/xxx/prompt.md                                     │
└───────────────────────────┬─────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│           🧠 LLM 语义分析器（核心改进）                        │
│                                                              │
│  ❌ 旧方案：正则匹配 XML 标签、Markdown 标题                   │
│     - 依赖特定格式，非常脆弱                                   │
│     - 运营写法多样，无法覆盖                                   │
│                                                              │
│  ✅ 新方案：LLM 深度语义理解                                   │
│     - 理解内容语义，不依赖格式                                 │
│     - 运营可以用任何方式写提示词                               │
│     - 智能识别逻辑模块                                        │
└───────────────────────────┬─────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│           智能按需组装（不是简单的分层裁剪）                    │
│                                                              │
│  原则：                                                       │
│  - 框架已处理 → 排除（如 IntentAnalyzer 处理意图识别）         │
│  - 任务不需要 → 排除（如简单问答不需要 ReAct 验证）             │
│  - 避免无谓的长提示词 → 节省 token                             │
└───────────────────────────┬─────────────────────────────────┘
                            ↓
     ┌──────────────────────┼──────────────────────┐
     ↓                      ↓                      ↓
┌────────────┐       ┌────────────┐        ┌────────────┐
│  Complex   │       │   Medium   │        │   Simple   │
│ 按需组装    │       │  按需组装   │        │  按需组装   │
│ 排除冗余    │       │  排除冗余   │        │  排除冗余   │
└────────────┘       └────────────┘        └────────────┘

核心原则：
1. 运营可以用任何方式写提示词（LLM 理解语义）
2. 框架组件已处理的模块 → 自动排除（避免重复）
3. 根据任务实际需要按需组装（不是复杂=全量）
4. 最小化系统提示词长度 → 节省 token
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from logger import get_logger

logger = get_logger("prompt_layer")


# ============================================================
# 任务复杂度枚举
# ============================================================


class TaskComplexity(Enum):
    """任务复杂度级别"""

    SIMPLE = "simple"  # 简单查询，1-2次工具调用
    MEDIUM = "medium"  # 中等任务，多步骤分析
    COMPLEX = "complex"  # 复杂任务，系统设计


# ============================================================
# 提示词模块定义
# ============================================================


class PromptModule(Enum):
    """
    提示词模块类型

    每个模块有对应的复杂度要求：
    - ALWAYS: 所有复杂度都需要
    - MEDIUM_UP: Medium 和 Complex 需要
    - COMPLEX_ONLY: 仅 Complex 需要
    """

    # 核心模块（所有复杂度都需要）
    ROLE_DEFINITION = "role_definition"  # 角色定义
    ABSOLUTE_PROHIBITIONS = "absolute_prohibitions"  # 最高禁令
    OUTPUT_FORMAT = "output_format"  # 输出格式（基础）

    # 中等模块（Medium/Complex 需要）
    INTENT_RECOGNITION = "intent_recognition"  # 意图识别
    TASK_COMPLEXITY = "task_complexity"  # 复杂度判断
    TOOL_SELECTION = "tool_selection"  # 工具选择策略
    PROGRESS_FEEDBACK = "progress_feedback"  # 进度反馈

    # 复杂模块（仅 Complex 需要）
    CONTEXT_PROTECTION = "context_protection"  # 上下文保护
    PLAN_OBJECT = "plan_object"  # Plan 对象构建
    DATA_CONTEXT = "data_context"  # Data_Context 管理
    REACT_VALIDATION = "react_validation"  # ReAct 验证循环
    QUALITY_GATES = "quality_gates"  # 质量门槛验证
    FINAL_DELIVERY = "final_delivery"  # 最终交付流程
    HITL = "hitl"  # Human-in-the-loop


# 模块到复杂度的映射（基础映射，会被框架组件排除修正）
MODULE_COMPLEXITY_MAP: Dict[PromptModule, Set[TaskComplexity]] = {
    # 核心模块（所有复杂度，不可排除）
    PromptModule.ROLE_DEFINITION: {
        TaskComplexity.SIMPLE,
        TaskComplexity.MEDIUM,
        TaskComplexity.COMPLEX,
    },
    PromptModule.ABSOLUTE_PROHIBITIONS: {
        TaskComplexity.SIMPLE,
        TaskComplexity.MEDIUM,
        TaskComplexity.COMPLEX,
    },
    PromptModule.OUTPUT_FORMAT: {
        TaskComplexity.SIMPLE,
        TaskComplexity.MEDIUM,
        TaskComplexity.COMPLEX,
    },
    # 中等模块（Medium/Complex，可被框架组件排除）
    PromptModule.INTENT_RECOGNITION: {TaskComplexity.MEDIUM, TaskComplexity.COMPLEX},
    PromptModule.TASK_COMPLEXITY: {TaskComplexity.MEDIUM, TaskComplexity.COMPLEX},
    PromptModule.TOOL_SELECTION: {TaskComplexity.MEDIUM, TaskComplexity.COMPLEX},
    PromptModule.PROGRESS_FEEDBACK: {TaskComplexity.MEDIUM, TaskComplexity.COMPLEX},
    # 复杂模块（仅 Complex，可被框架组件排除）
    PromptModule.CONTEXT_PROTECTION: {TaskComplexity.COMPLEX},
    PromptModule.PLAN_OBJECT: {TaskComplexity.COMPLEX},
    PromptModule.DATA_CONTEXT: {TaskComplexity.COMPLEX},
    PromptModule.REACT_VALIDATION: {TaskComplexity.COMPLEX},
    PromptModule.QUALITY_GATES: {TaskComplexity.COMPLEX},
    PromptModule.FINAL_DELIVERY: {TaskComplexity.COMPLEX},
    PromptModule.HITL: {TaskComplexity.COMPLEX},
}


# ============================================================
# 🆕 V4.6: 框架组件 → 模块排除映射
# ============================================================
# 当框架组件启用时，对应的提示词模块可以简化或排除
# 避免在提示词中重复定义已由框架处理的逻辑

FRAMEWORK_COMPONENT_EXCLUSIONS: Dict[str, List[PromptModule]] = {
    # IntentAnalyzer 组件启用 → 排除意图识别相关模块
    "intent_analyzer": [
        PromptModule.INTENT_RECOGNITION,
        PromptModule.TASK_COMPLEXITY,  # 复杂度判断由 ComplexityDetector 处理
    ],
    # PlanManager 组件启用 → 简化计划相关模块
    "plan_manager": [
        PromptModule.PLAN_OBJECT,  # Plan 结构由 plan 工具处理
        # 注意：保留 DATA_CONTEXT，因为这是 LLM 需要知道的数据管理规则
    ],
    # ToolSelector 组件启用 → 简化工具选择模块
    "tool_selector": [
        PromptModule.TOOL_SELECTION,  # 工具选择由 ToolSelector 处理
    ],
    # ConfirmationManager 组件启用 → 简化 HITL 模块
    "confirmation_manager": [
        PromptModule.HITL,  # HITL 触发条件由 ConfirmationManager 处理
    ],
}


# 不可排除的核心模块（无论框架组件如何配置）
CORE_MODULES_NEVER_EXCLUDE: Set[PromptModule] = {
    PromptModule.ROLE_DEFINITION,
    PromptModule.ABSOLUTE_PROHIBITIONS,
    PromptModule.OUTPUT_FORMAT,
}


# ============================================================
# 提示词模块内容
# ============================================================


@dataclass
class PromptModuleContent:
    """提示词模块内容"""

    module: PromptModule
    content: str
    priority: int = 50  # 优先级，用于排序

    # 简化版内容（用于 Simple 任务）
    simplified_content: Optional[str] = None


@dataclass
class PromptSchema:
    """
    提示词 Schema

    从运营写的完整提示词中解析出的结构化配置
    """

    # 基本信息
    agent_name: str = "GeneralAgent"
    agent_role: str = "AI 助手"

    # 模块内容
    modules: Dict[PromptModule, PromptModuleContent] = field(default_factory=dict)

    # 复杂度相关配置
    complexity_keywords: Dict[TaskComplexity, List[str]] = field(default_factory=dict)
    complexity_thresholds: Dict[TaskComplexity, Dict[str, Any]] = field(default_factory=dict)

    # 工具列表（从提示词中提取）
    tools: List[str] = field(default_factory=list)

    # 意图类型（从提示词中提取）
    intent_types: List[Dict[str, Any]] = field(default_factory=list)

    # 原始提示词（用于回退）
    raw_prompt: str = ""

    # 🆕 V4.6: 框架组件排除配置
    # 记录哪些模块已由框架组件处理，生成时应排除
    excluded_modules: Set[PromptModule] = field(default_factory=set)

    # 🆕 V4.6: 启用的框架组件列表
    # 用于计算应排除的模块
    enabled_components: List[str] = field(default_factory=list)

    def update_exclusions(self, agent_schema=None):
        """
        根据 AgentSchema 更新排除的模块

        Args:
            agent_schema: AgentSchema 配置（包含组件启用状态）
        """
        self.excluded_modules.clear()

        if agent_schema is None:
            return

        # 遍历框架组件排除映射
        for component, modules_to_exclude in FRAMEWORK_COMPONENT_EXCLUSIONS.items():
            # 检查组件是否启用
            component_config = getattr(agent_schema, component, None)
            if component_config and getattr(component_config, "enabled", False):
                for module in modules_to_exclude:
                    if module not in CORE_MODULES_NEVER_EXCLUDE:
                        self.excluded_modules.add(module)
                        logger.debug(f"   模块 {module.value} 已由 {component} 组件处理，排除")

        if self.excluded_modules:
            logger.info(f"✅ 框架组件处理的模块: {[m.value for m in self.excluded_modules]}")


# ============================================================
# 提示词解析器（🆕 V4.6.1 LLM 驱动）
# ============================================================


class PromptParser:
    """
    提示词解析器

    🆕 V4.6.1: 使用 LLM 语义理解分析提示词，而不是基于规则匹配

    核心理念：
    - 运营写提示词方式多样（像写作文），没有严格标准
    - 用 LLM 的深度语义理解能力分析内容
    - 不依赖特定格式或标签

    分析模式：
    - use_llm=True（默认）: 使用 LLM 语义分析（推荐）
    - use_llm=False: 使用传统正则匹配（回退方案）
    """

    # 🆕 V4.6.1: 模块重要性配置（LLM 分析时使用）
    MODULE_IMPORTANCE = {
        PromptModule.ROLE_DEFINITION: "high",
        PromptModule.ABSOLUTE_PROHIBITIONS: "high",
        PromptModule.OUTPUT_FORMAT: "high",
        PromptModule.INTENT_RECOGNITION: "medium",
        PromptModule.TASK_COMPLEXITY: "medium",
        PromptModule.TOOL_SELECTION: "medium",
        PromptModule.PROGRESS_FEEDBACK: "low",
        PromptModule.CONTEXT_PROTECTION: "medium",
        PromptModule.PLAN_OBJECT: "medium",
        PromptModule.DATA_CONTEXT: "medium",
        PromptModule.REACT_VALIDATION: "low",
        PromptModule.QUALITY_GATES: "low",
        PromptModule.FINAL_DELIVERY: "low",
        PromptModule.HITL: "low",
    }

    # 模块优先级（用于排序）
    MODULE_PRIORITY = {
        PromptModule.ROLE_DEFINITION: 10,
        PromptModule.ABSOLUTE_PROHIBITIONS: 20,
        PromptModule.OUTPUT_FORMAT: 30,
        PromptModule.INTENT_RECOGNITION: 40,
        PromptModule.TASK_COMPLEXITY: 50,
        PromptModule.TOOL_SELECTION: 60,
        PromptModule.PROGRESS_FEEDBACK: 70,
        PromptModule.CONTEXT_PROTECTION: 80,
        PromptModule.PLAN_OBJECT: 90,
        PromptModule.DATA_CONTEXT: 100,
        PromptModule.REACT_VALIDATION: 110,
        PromptModule.QUALITY_GATES: 120,
        PromptModule.HITL: 130,
        PromptModule.FINAL_DELIVERY: 140,
    }

    # 回退方案：传统正则匹配（当 LLM 不可用时）
    MODULE_PATTERNS = {
        PromptModule.ROLE_DEFINITION: [
            r"^# 角色.*?(?=^#|\Z|^---)",
            r"<role_definition>.*?</role_definition>",
        ],
        PromptModule.ABSOLUTE_PROHIBITIONS: [
            r"<absolute_prohibitions.*?>.*?</absolute_prohibitions>",
        ],
        PromptModule.CONTEXT_PROTECTION: [
            r"<context_self_protection.*?>.*?</context_self_protection>",
        ],
        PromptModule.INTENT_RECOGNITION: [
            r"<intent_recognition_flow>.*?</intent_recognition_flow>",
        ],
        PromptModule.TASK_COMPLEXITY: [
            r"<task_complexity_system>.*?</task_complexity_system>",
        ],
        PromptModule.OUTPUT_FORMAT: [
            r"## \d+\. 核心架构.*?(?=^## \d+\.|\Z)",
            r"## THINK 段规则.*?(?=^## |\Z)",
            r"## RESPONSE 段规则.*?(?=^## |\Z)",
            r"## JSON 段规则.*?(?=^## |\Z)",
        ],
        PromptModule.PLAN_OBJECT: [
            r"### `Plan` 对象定义.*?(?=^###|\Z)",
            r"<plan_schema>.*?</plan_schema>",
        ],
        PromptModule.DATA_CONTEXT: [
            r"### `Data_Context` 对象定义.*?(?=^###|\Z)",
            r"<data_context_schema>.*?</data_context_schema>",
        ],
        PromptModule.REACT_VALIDATION: [
            r"### `think` 阶段的 `ReAct` 验证循环.*?(?=^###|\Z)",
            r"<react_validation_loop>.*?</react_validation_loop>",
        ],
        PromptModule.QUALITY_GATES: [
            r"<final_validation_checklist>.*?</final_validation_checklist>",
        ],
        PromptModule.HITL: [
            r"## Human-in-the-Loop.*?(?=^## |\Z)",
            r"<hitl_trigger_conditions>.*?</hitl_trigger_conditions>",
        ],
        PromptModule.TOOL_SELECTION: [
            r"## 工具选择策略.*?(?=^## |\Z)",
            r"## 可用工具列表.*?(?=^## |\Z)",
        ],
        PromptModule.PROGRESS_FEEDBACK: [
            r"## 进度反馈.*?(?=^## |\Z)",
            r"<waiting_time_rule.*?>.*?</waiting_time_rule>",
        ],
        PromptModule.FINAL_DELIVERY: [
            r"## 交付流程设计.*?(?=^## |\Z)",
        ],
    }

    @classmethod
    async def parse_async(cls, raw_prompt: str, use_llm: bool = True) -> PromptSchema:
        """
        🆕 V5.2: 异步版本的解析方法

        在 async 上下文中调用时推荐使用此方法，
        确保 LLM 分析能正确执行（不会因 event loop 问题跳过）

        Args:
            raw_prompt: 运营写的完整提示词（任意格式）
            use_llm: 是否使用 LLM 语义分析（默认 True，推荐）

        Returns:
            PromptSchema 对象
        """
        if use_llm:
            return await cls._parse_with_llm_async(raw_prompt)
        else:
            return cls._parse_with_regex(raw_prompt)

    @classmethod
    async def _parse_with_llm_async(cls, raw_prompt: str) -> PromptSchema:
        """
        🆕 V5.2: 异步版本的 LLM 分析

        确保在 async 上下文中正确调用 LLM
        """
        try:
            from core.prompt.llm_analyzer import analyze_prompt_with_llm

            # 使用 async 版本调用 LLM 分析
            analysis = await analyze_prompt_with_llm(raw_prompt)

            # 转换为 PromptSchema（与同步版本逻辑相同）
            return cls._convert_analysis_to_schema(analysis, raw_prompt)

        except Exception as e:
            logger.warning(f"⚠️ LLM 分析失败，使用默认 Schema: {e}")
            # 🆕 V5.2: 失败时返回默认 Schema，不做正则回退
            return cls._create_default_schema(raw_prompt)

    @classmethod
    def _convert_analysis_to_schema(cls, analysis, raw_prompt: str) -> PromptSchema:
        """
        将 LLM 分析结果转换为 PromptSchema

        公共方法，供同步和异步版本共用
        """
        schema = PromptSchema(
            agent_name=analysis.agent_name,
            agent_role=analysis.agent_role,
            raw_prompt=raw_prompt,
            tools=analysis.tools,
        )

        # 转换模块
        for module_id, module_analysis in analysis.modules.items():
            if not module_analysis.found:
                continue

            try:
                module = PromptModule(module_id)
                schema.modules[module] = PromptModuleContent(
                    module=module,
                    content=module_analysis.content or module_analysis.summary,
                    priority=cls.MODULE_PRIORITY.get(module, 50),
                )
            except ValueError:
                # 未知的模块 ID，跳过
                logger.debug(f"   跳过未知模块: {module_id}")

        # 转换复杂度关键词
        for level, rule in analysis.complexity_rules.items():
            try:
                complexity = TaskComplexity(level)
                schema.complexity_keywords[complexity] = rule.keywords
            except ValueError:
                pass

        # 转换意图类型
        schema.intent_types = [
            {"name": intent.name, "keywords": intent.keywords} for intent in analysis.intent_types
        ]

        logger.info(f"✅ LLM 解析提示词完成: {len(schema.modules)} 个模块")

        return schema

    @classmethod
    def _create_default_schema(cls, raw_prompt: str) -> PromptSchema:
        """
        🆕 V5.2: 创建默认 Schema（当 LLM 失败时）

        不做任何假设，保留完整原始 prompt
        """
        logger.info("📜 使用默认 Schema（保留完整原始 prompt）")
        return PromptSchema(
            agent_name="GeneralAgent",
            agent_role="通用智能助手",
            raw_prompt=raw_prompt,
            modules={},  # 空 = 不做模块假设
            tools=[],
        )

    # 🆕 V10.3: _parse_with_llm 同步版本已删除，请使用 _parse_with_llm_async

    @classmethod
    def _parse_with_regex(cls, raw_prompt: str) -> PromptSchema:
        """
        🆕 V5.3: 已废弃的正则解析方法

        按照新架构（15-FRAMEWORK_PROMPT_CONTRACT.md）：
        - 不再使用正则匹配，因为运营可以用任何方式编写提示词
        - 直接返回默认 Schema，保留原始提示词
        - LLM 语义分析是唯一推荐的解析方式
        """
        logger.warning("⚠️ _parse_with_regex 已废弃，返回默认 Schema")
        return cls._create_default_schema(raw_prompt)

    @staticmethod
    def _extract_agent_name(raw_prompt: str) -> str:
        """提取 Agent 名称"""
        # 匹配 "名为 XXX 的" 或 "named XXX"
        patterns = [
            r'名为\s*["""]?([^"""\s]+)["""]?\s*的',
            r'named\s+["""]?([^"""\s]+)["""]?',
        ]
        for pattern in patterns:
            match = re.search(pattern, raw_prompt)
            if match:
                return match.group(1)
        return "GeneralAgent"

    @staticmethod
    def _extract_agent_role(raw_prompt: str) -> str:
        """提取 Agent 角色描述"""
        # 匹配第一段描述
        match = re.search(r"^#\s*角色.*?\n(.+?)(?=\n\n|\*\*)", raw_prompt, re.MULTILINE | re.DOTALL)
        if match:
            return match.group(1).strip()[:200]  # 限制长度
        return "AI 助手"

    @staticmethod
    def _extract_module(raw_prompt: str, patterns: List[str]) -> Optional[str]:
        """提取模块内容"""
        for pattern in patterns:
            match = re.search(pattern, raw_prompt, re.MULTILINE | re.DOTALL)
            if match:
                return match.group(0).strip()
        return None

    @staticmethod
    def _get_module_priority(module: PromptModule) -> int:
        """获取模块优先级（用于排序）"""
        priority_map = {
            PromptModule.ROLE_DEFINITION: 10,
            PromptModule.ABSOLUTE_PROHIBITIONS: 20,
            PromptModule.OUTPUT_FORMAT: 30,
            PromptModule.TASK_COMPLEXITY: 40,
            PromptModule.INTENT_RECOGNITION: 50,
            PromptModule.TOOL_SELECTION: 60,
            PromptModule.PLAN_OBJECT: 70,
            PromptModule.DATA_CONTEXT: 80,
            PromptModule.REACT_VALIDATION: 90,
            PromptModule.QUALITY_GATES: 100,
            PromptModule.PROGRESS_FEEDBACK: 110,
            PromptModule.FINAL_DELIVERY: 120,
            PromptModule.HITL: 130,
            PromptModule.CONTEXT_PROTECTION: 140,
        }
        return priority_map.get(module, 50)

    @staticmethod
    def _extract_complexity_keywords(raw_prompt: str) -> Dict[TaskComplexity, List[str]]:
        """提取复杂度关键词"""
        result = {
            TaskComplexity.SIMPLE: [],
            TaskComplexity.MEDIUM: [],
            TaskComplexity.COMPLEX: [],
        }

        # 从 task_complexity_system 中提取
        complexity_section = re.search(
            r"<task_complexity_system>.*?</task_complexity_system>", raw_prompt, re.DOTALL
        )

        if complexity_section:
            content = complexity_section.group(0)

            # 提取各级别的关键词
            for level, complexity in [
                (r'<level id="1".*?<keywords>(.*?)</keywords>', TaskComplexity.SIMPLE),
                (r'<level id="2".*?<keywords>(.*?)</keywords>', TaskComplexity.MEDIUM),
                (r'<level id="3".*?<keywords>(.*?)</keywords>', TaskComplexity.COMPLEX),
            ]:
                match = re.search(level, content, re.DOTALL)
                if match:
                    keywords = [k.strip() for k in match.group(1).split("、") if k.strip()]
                    keywords.extend([k.strip() for k in match.group(1).split(",") if k.strip()])
                    result[complexity] = list(set(keywords))

        return result

    @staticmethod
    def _extract_complexity_thresholds(raw_prompt: str) -> Dict[TaskComplexity, Dict[str, Any]]:
        """提取复杂度阈值配置"""
        result = {}

        complexity_section = re.search(
            r"<task_complexity_system>.*?</task_complexity_system>", raw_prompt, re.DOTALL
        )

        if complexity_section:
            content = complexity_section.group(0)

            for level_id, complexity in [
                ("1", TaskComplexity.SIMPLE),
                ("2", TaskComplexity.MEDIUM),
                ("3", TaskComplexity.COMPLEX),
            ]:
                level_match = re.search(rf'<level id="{level_id}".*?</level>', content, re.DOTALL)
                if level_match:
                    level_content = level_match.group(0)

                    # 提取 quality_threshold
                    threshold_match = re.search(
                        r"<quality_threshold>(.*?)</quality_threshold>", level_content
                    )

                    result[complexity] = {
                        "quality_threshold": threshold_match.group(1) if threshold_match else "无",
                    }

        return result

    @staticmethod
    def _extract_tools(raw_prompt: str) -> List[str]:
        """提取工具列表"""
        tools = []

        # 匹配 <tool id="N" name="xxx">
        tool_matches = re.findall(r'<tool\s+id="\d+"\s+name="([^"]+)"', raw_prompt)
        tools.extend(tool_matches)

        return list(set(tools))

    @staticmethod
    def _extract_intent_types(raw_prompt: str) -> List[Dict[str, Any]]:
        """提取意图类型"""
        intents = []

        intent_section = re.search(r"<intent_types>.*?</intent_types>", raw_prompt, re.DOTALL)

        if intent_section:
            content = intent_section.group(0)

            # 匹配每个意图
            intent_matches = re.findall(
                r'<intent\s+id="(\d+)"\s+name="([^"]+)".*?<keywords>(.*?)</keywords>',
                content,
                re.DOTALL,
            )

            for intent_id, name, keywords in intent_matches:
                intents.append(
                    {
                        "id": int(intent_id),
                        "name": name,
                        "keywords": [k.strip() for k in keywords.split(",") if k.strip()],
                    }
                )

        return intents


# ============================================================
# 提示词生成器
# ============================================================


class PromptGenerator:
    """
    提示词生成器

    🆕 V4.6: 智能按需组装（不是简单的分层裁剪）
    🆕 V5.1: 增加模块内容大小限制，确保 Simple 版本足够精简

    核心原则：
    1. 框架组件已处理的模块 → 自动排除（避免重复）
    2. 根据任务实际需要按需组装（不是复杂=全量）
    3. 最小化系统提示词长度 → 节省 token
    4. 🆕 V5.1: Simple 版本严格控制在 15k 字符以内
    """

    # 🆕 V5.1: 各复杂度的模块内容大小限制（字符数）
    MODULE_SIZE_LIMITS = {
        TaskComplexity.SIMPLE: {
            PromptModule.ROLE_DEFINITION: 2000,  # 角色定义，保留核心描述
            PromptModule.ABSOLUTE_PROHIBITIONS: 3000,  # 禁令，完整保留
            PromptModule.OUTPUT_FORMAT: 5000,  # 输出格式，保留关键规则
        },
        TaskComplexity.MEDIUM: {
            PromptModule.ROLE_DEFINITION: 5000,
            PromptModule.ABSOLUTE_PROHIBITIONS: 5000,
            PromptModule.OUTPUT_FORMAT: 10000,
            PromptModule.INTENT_RECOGNITION: 3000,
            PromptModule.TASK_COMPLEXITY: 2000,
            PromptModule.TOOL_SELECTION: 5000,
            PromptModule.PROGRESS_FEEDBACK: 2000,
        },
        TaskComplexity.COMPLEX: {
            # Complex 不限制大小，但仍会排除冗余模块
        },
    }

    # 🆕 V5.1: 总提示词大小限制（字符数）
    TOTAL_SIZE_LIMITS = {
        TaskComplexity.SIMPLE: 15000,  # ~4k tokens
        TaskComplexity.MEDIUM: 40000,  # ~10k tokens
        TaskComplexity.COMPLEX: 80000,  # ~20k tokens
    }

    # 🆕 V7.6: 更细粒度的提示词精简规则
    SIMPLE_AGGRESSIVE_MODULES = {
        PromptModule.TOOL_SELECTION,
        PromptModule.PROGRESS_FEEDBACK,
        PromptModule.PLAN_OBJECT,
        PromptModule.REACT_VALIDATION,
        PromptModule.QUALITY_GATES,
        PromptModule.FINAL_DELIVERY,
        PromptModule.HITL,
        PromptModule.DATA_CONTEXT,
        PromptModule.CONTEXT_PROTECTION,
    }

    MEDIUM_STRIP_EXAMPLE_MODULES = {
        PromptModule.TOOL_SELECTION,
        PromptModule.PROGRESS_FEEDBACK,
        PromptModule.PLAN_OBJECT,
        PromptModule.REACT_VALIDATION,
        PromptModule.QUALITY_GATES,
        PromptModule.FINAL_DELIVERY,
        PromptModule.HITL,
    }

    @classmethod
    def generate(
        cls,
        schema: PromptSchema,
        complexity: TaskComplexity,
        agent_schema=None,  # 🆕 V4.6: AgentSchema（用于计算排除模块）
    ) -> str:
        """
        根据复杂度生成对应版本的提示词

        🆕 V4.6: 智能按需组装
        🆕 V5.1: 增加大小限制，确保各版本在合理范围内
        🆕 V5.2: 当模块为空时，使用原始提示词内容作为回退

        Args:
            schema: 提示词 Schema
            complexity: 任务复杂度
            agent_schema: AgentSchema 配置（可选，用于排除已处理模块）

        Returns:
            智能裁剪后的系统提示词
        """
        # 🆕 V4.6: 更新排除模块
        if agent_schema:
            schema.update_exclusions(agent_schema)

        # 1. 筛选需要的模块（排除框架已处理的）
        required_modules = cls._get_required_modules(complexity, schema.excluded_modules)

        # 2. 按优先级排序
        modules_to_include = [
            schema.modules[module] for module in required_modules if module in schema.modules
        ]
        modules_to_include.sort(key=lambda m: m.priority)

        # 🆕 V5.2: 当模块为空但有原始提示词时，使用原始内容作为回退
        if not modules_to_include and schema.raw_prompt:
            logger.warning(f"⚠️ 模块解析为空，使用原始提示词作为回退")
            return cls._generate_from_raw_prompt(schema, complexity)

        # 3. 组装提示词
        parts = []

        # 添加角色定义头部
        parts.append(f"# {schema.agent_name}")
        parts.append(f"\n{schema.agent_role}\n")

        # 添加复杂度说明
        parts.append(cls._generate_complexity_header(complexity, schema))

        # 🆕 V5.1: 获取模块大小限制
        size_limits = cls.MODULE_SIZE_LIMITS.get(complexity, {})

        # 添加各模块内容（🆕 V5.1: 应用大小限制）
        for module_content in modules_to_include:
            # Simple 任务使用简化版内容（如果有）
            if complexity == TaskComplexity.SIMPLE and module_content.simplified_content:
                content = module_content.simplified_content
            else:
                content = module_content.content

            # 🆕 V7.6: 细粒度精简（避免输出格式被过度裁剪）
            condensed = cls._condense_module_content(
                content=content, module=module_content.module, complexity=complexity
            )
            if condensed.strip():
                content = condensed

            # 🆕 V5.1: 应用模块大小限制
            max_size = size_limits.get(module_content.module)
            if max_size and len(content) > max_size:
                content = cls._truncate_content(content, max_size, module_content.module)
                logger.debug(
                    f"   模块 {module_content.module.value} 已截断: {len(module_content.content)} -> {len(content)} 字符"
                )

            parts.append(content)

        # 4. 添加工具列表（根据复杂度裁剪）
        if complexity in {TaskComplexity.MEDIUM, TaskComplexity.COMPLEX}:
            parts.append(cls._generate_tools_section(schema.tools, complexity))

        result = "\n\n---\n\n".join(parts)

        # 🆕 V5.1: 应用总大小限制
        total_limit = cls.TOTAL_SIZE_LIMITS.get(complexity)
        if total_limit and len(result) > total_limit:
            logger.warning(
                f"⚠️ {complexity.value} 版提示词超出限制: {len(result)} > {total_limit}，进行截断"
            )
            result = cls._truncate_total(result, total_limit)

        # 🆕 V4.6: 增强日志
        excluded_count = len(schema.excluded_modules)
        logger.info(
            f"✅ 生成 {complexity.value} 版提示词: {len(result)} 字符 (排除 {excluded_count} 个冗余模块)"
        )
        logger.debug(f"   包含模块: {[m.module.value for m in modules_to_include]}")
        if schema.excluded_modules:
            logger.debug(f"   排除模块: {[m.value for m in schema.excluded_modules]}")

        return result

    @classmethod
    def _condense_module_content(
        cls, content: str, module: PromptModule, complexity: TaskComplexity
    ) -> str:
        """
        🆕 V7.6: 按复杂度精简模块内容

        策略：
        - SIMPLE: 移除示例与代码块，仅保留核心规则
        - MEDIUM: 移除大段示例，保留关键规则与流程
        - COMPLEX: 不做额外精简
        """
        if complexity == TaskComplexity.COMPLEX:
            return content

        # 避免破坏输出格式模块的 JSON 模板
        if module == PromptModule.OUTPUT_FORMAT:
            return content

        condensed = content

        if complexity == TaskComplexity.SIMPLE and module in cls.SIMPLE_AGGRESSIVE_MODULES:
            condensed = cls._strip_examples(condensed)
            condensed = cls._strip_code_blocks(condensed)
            condensed = cls._keep_first_lines(condensed, max_lines=40)
            return condensed

        if complexity == TaskComplexity.MEDIUM and module in cls.MEDIUM_STRIP_EXAMPLE_MODULES:
            if module == PromptModule.TOOL_SELECTION:
                condensed = cls._strip_tools_catalog(condensed)
            condensed = cls._strip_examples(condensed)
            condensed = cls._strip_code_blocks(condensed)
            return condensed

        return condensed

    @staticmethod
    def _strip_code_blocks(content: str) -> str:
        """移除三引号代码块，避免示例过长"""
        return re.sub(r"```.*?```", "", content, flags=re.DOTALL)

    @staticmethod
    def _strip_tools_catalog(content: str) -> str:
        """移除工具清单块，保留选择策略与规则"""
        # XML 工具清单
        content = re.sub(r"<tools_catalog>.*?</tools_catalog>", "", content, flags=re.DOTALL)
        # Markdown 工具清单章节
        content = re.sub(r"(?:^|\n)##\s+可用工具列表.*?(?=\n##\s|\Z)", "", content, flags=re.DOTALL)
        return content

    @staticmethod
    def _strip_examples(content: str) -> str:
        """移除示例段落（标题或 XML 示例块）"""
        # 移除 Markdown 示例段
        content = re.sub(
            r"(?:^|\n)#{2,3}\s*(示例|Example).*?(?=\n#{2,3}\s|$)", "", content, flags=re.DOTALL
        )
        # 移除 XML 示例段
        content = re.sub(r"<example>.*?</example>", "", content, flags=re.DOTALL)
        return content

    @staticmethod
    def _keep_first_lines(content: str, max_lines: int) -> str:
        """保留前若干行，控制长度"""
        lines = [line for line in content.splitlines() if line.strip()]
        return "\n".join(lines[:max_lines])

    @classmethod
    def _generate_from_raw_prompt(
        cls,
        schema: PromptSchema,
        complexity: TaskComplexity,
    ) -> str:
        """
        🆕 V5.2: 当模块解析失败时，从原始提示词生成对应复杂度的版本

        策略：
        - Simple: 提取核心部分（角色定义 + 禁令 + 基本格式）
        - Medium: 核心 + 工具 + 部分流程
        - Complex: 完整内容（按大小限制截断）
        """
        raw_prompt = schema.raw_prompt
        total_limit = cls.TOTAL_SIZE_LIMITS.get(complexity, 80000)

        # 根据复杂度提取不同部分
        if complexity == TaskComplexity.SIMPLE:
            # Simple: 仅保留核心规则（角色定义 + 禁令）
            result = cls._extract_core_for_simple(raw_prompt, total_limit)
        elif complexity == TaskComplexity.MEDIUM:
            # Medium: 核心 + 工具 + 基本流程
            result = cls._extract_core_for_medium(raw_prompt, total_limit)
        else:
            # Complex: 尽可能完整，按大小限制截断
            if len(raw_prompt) > total_limit:
                result = cls._truncate_total(raw_prompt, total_limit)
            else:
                result = raw_prompt

        logger.info(
            f"✅ 从原始提示词生成 {complexity.value} 版: {len(result)} 字符 (原始: {len(raw_prompt)} 字符)"
        )
        return result

    @classmethod
    def _extract_core_for_simple(cls, raw_prompt: str, max_size: int) -> str:
        """
        🆕 V5.2: 为 Simple 任务提取核心内容

        提取内容：
        1. 角色定义（开头到第一个分隔符）
        2. 绝对禁令（<absolute_prohibitions> 标签）
        3. 输出格式基础（output_format 相关）
        """
        import re

        parts = []

        # 1. 提取角色定义（开头部分）
        role_match = re.search(
            r"^(#\s*角色.*?)(?=<absolute_prohibitions|## 绝对禁令|---\n\n#|\Z)",
            raw_prompt,
            re.MULTILINE | re.DOTALL,
        )
        if role_match:
            role_content = role_match.group(1).strip()
            if len(role_content) > 3000:
                role_content = role_content[:3000] + "\n\n<!-- 角色定义已精简 -->"
            parts.append(role_content)
        else:
            # 没有匹配到，取开头 3000 字符
            parts.append(raw_prompt[:3000] + "\n\n<!-- 开头部分 -->")

        # 2. 提取绝对禁令
        prohibitions_match = re.search(
            r"<absolute_prohibitions.*?>.*?</absolute_prohibitions>", raw_prompt, re.DOTALL
        )
        if prohibitions_match:
            prohibitions = prohibitions_match.group(0)
            if len(prohibitions) > 5000:
                prohibitions = prohibitions[:5000] + "\n</absolute_prohibitions>"
            parts.append(prohibitions)

        # 3. 提取输出格式基础
        output_match = re.search(
            r"(## 核心交互模型.*?)(?=## 工具|## THINK|## 可用工具|---\n\n##|\Z)",
            raw_prompt,
            re.MULTILINE | re.DOTALL,
        )
        if output_match:
            output_content = output_match.group(1).strip()
            if len(output_content) > 4000:
                output_content = output_content[:4000] + "\n\n<!-- 格式规则已精简 -->"
            parts.append(output_content)

        result = "\n\n---\n\n".join(parts)

        # 确保不超过限制
        if len(result) > max_size:
            result = cls._truncate_total(result, max_size)

        return result

    @classmethod
    def _extract_core_for_medium(cls, raw_prompt: str, max_size: int) -> str:
        """
        🆕 V5.2: 为 Medium 任务提取核心+扩展内容
        """
        import re

        # Medium 任务保留更多内容
        # 找到工具列表之后的部分可以截断
        tool_section_start = raw_prompt.find("## 可用工具列表")
        if tool_section_start == -1:
            tool_section_start = raw_prompt.find("<tool id=")

        if tool_section_start > 0:
            # 保留工具列表之前的全部内容 + 工具列表的一部分
            core_part = raw_prompt[:tool_section_start]

            # 提取工具列表（限制大小）
            tool_section = raw_prompt[tool_section_start:]
            if len(tool_section) > 15000:
                tool_section = tool_section[:15000] + "\n\n<!-- 工具列表已精简 -->"

            result = core_part + tool_section
        else:
            result = raw_prompt

        # 确保不超过限制
        if len(result) > max_size:
            result = cls._truncate_total(result, max_size)

        return result

    @staticmethod
    def _truncate_content(content: str, max_size: int, module: PromptModule) -> str:
        """
        🆕 V5.1: 智能截断模块内容

        截断策略：
        - 保留开头的核心规则
        - 在合适的分隔符处截断
        - 添加省略标记
        """
        if len(content) <= max_size:
            return content

        # 寻找合适的截断点（段落、列表项、标题等）
        truncate_at = max_size
        separators = ["\n\n", "\n- ", "\n## ", "\n### ", "\n"]

        for sep in separators:
            last_sep = content.rfind(sep, 0, max_size)
            if last_sep > max_size * 0.6:  # 至少保留 60% 的内容
                truncate_at = last_sep
                break

        truncated = content[:truncate_at].rstrip()

        # 添加省略标记
        truncated += f"\n\n<!-- {module.value}: 内容已精简，完整规则参见 Complex 版本 -->"

        return truncated

    @staticmethod
    def _truncate_total(content: str, max_size: int) -> str:
        """
        🆕 V5.1: 截断总提示词
        """
        if len(content) <= max_size:
            return content

        # 在分隔符处截断
        truncate_at = max_size
        separators = ["\n\n---\n\n", "\n\n", "\n"]

        for sep in separators:
            last_sep = content.rfind(sep, 0, max_size)
            if last_sep > max_size * 0.8:
                truncate_at = last_sep
                break

        return content[:truncate_at].rstrip() + "\n\n<!-- 提示词已精简 -->"

    @staticmethod
    def _get_required_modules(
        complexity: TaskComplexity, excluded_modules: Set[PromptModule] = None
    ) -> Set[PromptModule]:
        """
        获取指定复杂度需要的模块

        🆕 V4.6: 排除框架已处理的模块
        """
        excluded = excluded_modules or set()

        return {
            module
            for module, complexities in MODULE_COMPLEXITY_MAP.items()
            if complexity in complexities and module not in excluded
        }

    @staticmethod
    def _generate_complexity_header(complexity: TaskComplexity, schema: PromptSchema) -> str:
        """生成复杂度说明头部"""
        headers = {
            TaskComplexity.SIMPLE: """
## 当前任务模式：简单查询

这是一个简单的查询任务，请：
- 直接、简洁地回答
- 无需构建复杂的计划
- 无需输出 JSON 结构化数据
- 保持友好自然的对话风格
""",
            TaskComplexity.MEDIUM: """
## 当前任务模式：中等任务

这是一个需要多步处理的任务，请：
- 构建简化的 3-5 步计划
- 提供进度反馈
- 输出必要的 JSON 结构化数据
- 保持专业且友好的语气
""",
            TaskComplexity.COMPLEX: """
## 当前任务模式：复杂任务

这是一个需要系统性分析的复杂任务，请：
- 构建详细的执行计划
- 执行完整的质量验证流程
- 使用 ReAct 验证循环确保每步正确
- 输出完整的结构化交付物
""",
        }

        return headers.get(complexity, "")

    @staticmethod
    def _generate_tools_section(tools: List[str], complexity: TaskComplexity) -> str:
        """生成工具列表部分"""
        if not tools:
            return ""

        # 复杂任务列出所有工具
        if complexity == TaskComplexity.COMPLEX:
            tool_list = "\n".join([f"- {tool}" for tool in tools])
            return f"## 可用工具\n\n{tool_list}"

        # 中等任务只列出核心工具
        core_tools = tools[:5] if len(tools) > 5 else tools
        tool_list = "\n".join([f"- {tool}" for tool in core_tools])
        return f"## 核心工具\n\n{tool_list}"


# ============================================================
# 便捷函数
# ============================================================


async def parse_prompt(raw_prompt: str, use_llm: bool = True) -> PromptSchema:
    """
    解析提示词（异步版本）

    🆕 V4.6.1: 支持 LLM 语义分析
    🆕 V10.3: 转为异步版本

    Args:
        raw_prompt: 运营写的原始提示词（任意格式）
        use_llm: 是否使用 LLM 语义分析（默认 True）
                 - True: 用 LLM 理解语义（推荐，支持任意格式）
                 - False: 用正则匹配（回退方案，依赖特定格式）

    Returns:
        PromptSchema 对象
    """
    return await PromptParser.parse_async(raw_prompt, use_llm=use_llm)


def generate_prompt(
    schema: PromptSchema,
    complexity: TaskComplexity,
    agent_schema=None,  # 🆕 V4.6: AgentSchema（用于排除已处理模块）
) -> str:
    """
    生成指定复杂度的提示词

    🆕 V4.6: 智能按需组装
    - 如果提供 agent_schema，会自动排除框架已处理的模块
    - 避免无谓的长提示词，节省 token

    Args:
        schema: 提示词 Schema
        complexity: 任务复杂度
        agent_schema: AgentSchema 配置（可选）

    Returns:
        智能裁剪后的提示词
    """
    return PromptGenerator.generate(schema, complexity, agent_schema)


async def get_prompt_for_complexity(
    raw_prompt: str,
    complexity: TaskComplexity,
    agent_schema=None,
    use_llm: bool = True,
) -> str:
    """
    一步到位：解析并生成指定复杂度的提示词（异步版本）

    🆕 V10.3: 转为异步版本

    Args:
        raw_prompt: 运营写的完整提示词
        complexity: 任务复杂度
        agent_schema: AgentSchema 配置（可选，用于排除已处理模块）
        use_llm: 是否使用 LLM 语义分析（默认 True）

    Returns:
        智能裁剪后的提示词
    """
    schema = await parse_prompt(raw_prompt, use_llm=use_llm)
    return generate_prompt(schema, complexity, agent_schema)
