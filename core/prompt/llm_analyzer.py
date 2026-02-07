"""
🆕 V4.6.1 LLM 驱动的提示词分析器

核心理念：
- 用 LLM 的深度语义理解能力分析提示词
- 不依赖特定格式或标签（运营写作文方式多样）
- 理解内容的语义，而不是匹配文本模式

设计哲学：
┌─────────────────────────────────────────────────────────────┐
│  运营写的提示词（任意格式：Markdown/XML/纯文本/混合）           │
│  "像写作文一样，没有严格标准"                                  │
└───────────────────────────┬─────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│               LLM 语义分析器                                   │
│  1. 理解提示词的整体结构和意图                                  │
│  2. 识别逻辑模块（不依赖格式，纯语义理解）                       │
│  3. 提取关键配置（复杂度规则、工具列表等）                       │
│  4. 输出结构化的 PromptSchema                                  │
└─────────────────────────────────────────────────────────────┘
"""

# 1. 标准库
import asyncio
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

# 3. 本地模块
from core.llm import Message
from logger import get_logger

# 2. 第三方库（无）


logger = get_logger("llm_prompt_analyzer")


# ============================================================
# LLM 分析提示词模板
# ============================================================

PROMPT_ANALYSIS_SYSTEM = """你是一个专业的系统提示词分析专家。

## 任务
分析运营人员编写的 AI Agent 系统提示词，识别其中的逻辑模块，并输出结构化的分析结果。

## 关键要求
1. **精确定位模块边界**：找到每个模块的开始和结束位置
2. **提取完整内容**：模块内容应该完整，不要截断
3. **识别所有模块**：尽可能识别提示词中的所有逻辑模块

## 模块类型定义（按优先级排序）

| 模块 ID | 含义 | 识别特征 |
|---------|------|----------|
| role_definition | 角色定义 | 开头的角色描述、"你是..."、"# 角色" |
| absolute_prohibitions | 绝对禁令 | "禁止"、"禁令"、"不能"、"<absolute_prohibitions>" |
| context_protection | 上下文保护 | "上下文保护"、"防止注入"、"<context_self_protection>" |
| intent_recognition | 意图识别 | "意图识别"、"intent"、"<intent_recognition_flow>" |
| task_complexity | 任务复杂度 | "复杂度"、"简单/中等/复杂"、"<task_complexity_system>" |
| output_format | 输出格式 | "输出格式"、"三段式"、"THINK/RESPONSE/JSON" |
| tool_selection | 工具选择 | "工具选择"、"可用工具"、"<tool" |
| plan_object | 计划构建 | "Plan 对象"、"执行计划"、"<plan_schema>" |
| data_context | 数据上下文 | "Data_Context"、"数据管理" |
| react_validation | 验证循环 | "ReAct"、"验证循环"、"<react_validation_loop>" |
| quality_gates | 质量检查 | "质量验证"、"最终验证"、"<final_validation_checklist>" |
| progress_feedback | 进度反馈 | "进度反馈"、"等待时间"、"<waiting_time_rule>" |
| hitl | 人工介入 | "Human-in-the-Loop"、"HITL"、"人工介入" |
| final_delivery | 最终交付 | "交付流程"、"最终输出" |

## 输出格式

```json
{
  "agent_name": "Agent 名称（从提示词中提取）",
  "agent_role": "角色描述（1-2句话）",
  "modules": {
    "role_definition": {
      "found": true,
      "summary": "50字内摘要",
      "start_marker": "模块开始的标志性文字（用于定位）",
      "importance": "high",
      "can_simplify": false
    },
    "absolute_prohibitions": {
      "found": true,
      "summary": "...",
      "start_marker": "<absolute_prohibitions",
      "importance": "high",
      "can_simplify": false
    }
    // ... 列出所有找到的模块
  },
  "complexity_rules": {
    "simple": {"keywords": ["你好", "什么", "查"], "description": "单一信息查询"},
    "medium": {"keywords": ["分析", "对比", "建议"], "description": "多步骤处理"},
    "complex": {"keywords": ["搭建", "设计", "构建"], "description": "系统性任务"}
  },
  "tools": ["search_skill", "diagram_skill", "..."],
  "intent_types": [
    {"name": "本体论系统搭建", "keywords": ["搭建系统", "设计系统"]}
  ]
}
```

## 重要提示
1. **必须识别所有存在的模块**，不要遗漏
2. **start_marker 必须是提示词中实际存在的文字**，用于精确定位
3. 如果模块使用 XML 标签（如 `<absolute_prohibitions>`），start_marker 应该是该标签
4. 优先识别高重要性模块（role_definition, absolute_prohibitions, output_format）"""


PROMPT_ANALYSIS_USER = """请分析以下系统提示词：

---
{prompt}
---

请输出 JSON 格式的分析结果。只输出 JSON，不要其他内容。"""


# ============================================================
# LLM 分析结果数据类
# ============================================================


@dataclass
class ModuleAnalysis:
    """模块分析结果"""

    found: bool = False
    summary: str = ""
    start_marker: str = ""
    importance: str = "medium"  # high/medium/low
    can_simplify: bool = True
    content: str = ""  # 实际内容（后续提取）


@dataclass
class ComplexityRule:
    """复杂度规则"""

    keywords: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class IntentType:
    """意图类型"""

    name: str = ""
    keywords: List[str] = field(default_factory=list)


@dataclass
class LLMAnalysisResult:
    """LLM 分析结果"""

    agent_name: str = "GeneralAgent"
    agent_role: str = ""
    modules: Dict[str, ModuleAnalysis] = field(default_factory=dict)
    complexity_rules: Dict[str, ComplexityRule] = field(default_factory=dict)
    tools: List[str] = field(default_factory=list)
    intent_types: List[IntentType] = field(default_factory=list)
    raw_prompt: str = ""


# ============================================================
# LLM 提示词分析器
# ============================================================


class LLMPromptAnalyzer:
    """
    LLM 驱动的提示词分析器

    用 LLM 的语义理解能力分析提示词，而不是基于规则匹配
    """

    def __init__(self, llm_service=None):
        """
        初始化分析器

        Args:
            llm_service: LLM 服务（默认使用 Haiku）
        """
        self._llm_service = llm_service

    async def _get_llm_service(self):
        """懒加载 LLM 服务（使用配置文件中的 llm_analyzer profile）"""
        if self._llm_service is None:
            from config.llm_config import get_llm_profile
            from core.llm import create_llm_service

            # 🆕 V5.3: 从配置文件获取 LLM Profile（优先使用 Claude Sonnet 4.5）
            # 🆕 V7.10: 使用 create_llm_service 支持多模型容灾
            profile = await get_llm_profile("llm_analyzer")
            logger.info(f"📦 使用 LLM Profile: llm_analyzer, model={profile.get('model')}")

            self._llm_service = create_llm_service(**profile)
        return self._llm_service

    async def analyze(self, raw_prompt: str) -> LLMAnalysisResult:
        """
        分析系统提示词

        Args:
            raw_prompt: 运营写的原始提示词（任意格式）

        Returns:
            LLMAnalysisResult 结构化分析结果
        """
        logger.info(f"🧠 开始 LLM 语义分析，提示词长度: {len(raw_prompt)} 字符")

        llm = await self._get_llm_service()

        try:
            # 调用 LLM 分析（使用 create_message_async）
            from core.llm import Message

            response = await llm.create_message_async(
                messages=[
                    Message(role="user", content=PROMPT_ANALYSIS_USER.format(prompt=raw_prompt))
                ],
                system=PROMPT_ANALYSIS_SYSTEM,
            )

            # 解析 JSON 响应（LLMResponse.content 是 str 类型）
            response_text = response.content.strip() if response.content else ""

            # 清理可能的 markdown 代码块
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]

            analysis_data = json.loads(response_text.strip())

            # 转换为数据类
            result = self._parse_analysis_result(analysis_data, raw_prompt)

            # 提取模块实际内容
            result = self._extract_module_contents(result, raw_prompt)

            logger.info(
                f"✅ LLM 分析完成: {result.agent_name}, 识别 {sum(1 for m in result.modules.values() if m.found)} 个模块"
            )

            return result

        except json.JSONDecodeError as e:
            logger.error(f"❌ LLM 返回的 JSON 解析失败: {e}")
            return self._default_fallback(raw_prompt)
        except Exception as e:
            logger.error(f"❌ LLM 分析失败: {e}")
            return self._default_fallback(raw_prompt)

    def _parse_analysis_result(self, data: Dict[str, Any], raw_prompt: str) -> LLMAnalysisResult:
        """解析 LLM 返回的 JSON 数据"""
        result = LLMAnalysisResult(
            agent_name=data.get("agent_name", "GeneralAgent"),
            agent_role=data.get("agent_role", ""),
            raw_prompt=raw_prompt,
        )

        # 解析模块
        modules_data = data.get("modules", {})
        for module_id, module_info in modules_data.items():
            if isinstance(module_info, dict):
                result.modules[module_id] = ModuleAnalysis(
                    found=module_info.get("found", False),
                    summary=module_info.get("summary", ""),
                    start_marker=module_info.get("start_marker", ""),
                    importance=module_info.get("importance", "medium"),
                    can_simplify=module_info.get("can_simplify", True),
                )

        # 解析复杂度规则
        complexity_data = data.get("complexity_rules", {})
        for level, rule_info in complexity_data.items():
            if isinstance(rule_info, dict):
                result.complexity_rules[level] = ComplexityRule(
                    keywords=rule_info.get("keywords", []),
                    description=rule_info.get("description", ""),
                )

        # 解析工具列表
        result.tools = data.get("tools", [])

        # 解析意图类型
        intent_data = data.get("intent_types", [])
        for intent_info in intent_data:
            if isinstance(intent_info, dict):
                result.intent_types.append(
                    IntentType(
                        name=intent_info.get("name", ""),
                        keywords=intent_info.get("keywords", []),
                    )
                )

        return result

    def _extract_module_contents(
        self, result: LLMAnalysisResult, raw_prompt: str
    ) -> LLMAnalysisResult:
        """
        根据 LLM 识别的位置标记，提取模块实际内容

        这是一个启发式方法，用 start_marker 定位内容
        """
        for module_id, module in result.modules.items():
            if not module.found or not module.start_marker:
                continue

            # 尝试定位内容
            marker_pos = raw_prompt.find(module.start_marker)
            if marker_pos == -1:
                # 尝试模糊匹配
                marker_lower = module.start_marker.lower()
                prompt_lower = raw_prompt.lower()
                marker_pos = prompt_lower.find(marker_lower[:30])  # 只匹配前30字符

            if marker_pos != -1:
                # 提取从标记开始的一段内容（最多2000字符，或到下一个主要分隔符）
                start = marker_pos
                end = min(start + 2000, len(raw_prompt))

                # 查找可能的结束位置（下一个主要标题或分隔符）
                separators = ["\n# ", "\n## ", "\n---", "\n===", "</", "\n\n\n"]
                for sep in separators:
                    sep_pos = raw_prompt.find(sep, start + 100)  # 至少包含100字符
                    if sep_pos != -1 and sep_pos < end:
                        end = sep_pos

                module.content = raw_prompt[start:end].strip()

        return result

    def _default_fallback(self, raw_prompt: str) -> LLMAnalysisResult:
        """
        默认回退（当 LLM 调用失败时）

        🆕 V5.2 架构修复：
        - 不使用正则匹配（运营 prompt 格式任意，正则不可靠）
        - 返回默认配置 + 原始 prompt（保留完整内容）
        - 让 Agent 使用完整的原始 prompt 运行

        参考：15-FRAMEWORK_PROMPT_CONTRACT.md
        """
        logger.warning("⚠️ LLM 分析失败，使用默认配置（保留原始 prompt）")

        # 返回最小化的默认配置
        # modules 为空 = 不做任何假设，不做任何裁剪
        # raw_prompt 保留完整 = Agent 使用原始的运营 prompt
        result = LLMAnalysisResult(
            agent_name="GeneralAgent",
            agent_role="通用智能助手",
            modules={},  # 空 = 不做模块假设
            complexity_rules={},  # 空 = 使用默认复杂度规则
            tools=[],  # 空 = 由 config.yaml 配置
            intent_types=[],  # 空 = 使用默认意图识别
            raw_prompt=raw_prompt,  # 保留完整原始 prompt
        )

        logger.info("✅ 默认配置：空模块 + 完整原始 prompt")

        return result

    async def analyze_in_running_loop(self, raw_prompt: str) -> LLMAnalysisResult:
        """
        在已运行的事件循环中执行分析

        🆕 V5.2: 解决 async 上下文中调用的问题
        """
        return await self.analyze(raw_prompt)


# ============================================================
# 便捷函数
# ============================================================


async def analyze_prompt_with_llm(raw_prompt: str) -> LLMAnalysisResult:
    """
    使用 LLM 分析系统提示词

    Args:
        raw_prompt: 运营写的原始提示词（任意格式）

    Returns:
        LLMAnalysisResult 结构化分析结果
    """
    analyzer = LLMPromptAnalyzer()
    return await analyzer.analyze(raw_prompt)


# ============================================================
# 🆕 V5.3: LLM 智能合并 - 框架规则 + 运营 prompt
# ============================================================


async def merge_with_framework_rules(user_prompt: str) -> str:
    """
    🆕 V5.3: 使用 LLM 智能合并框架规则和运营 prompt

    设计哲学（基于 15-FRAMEWORK_PROMPT_CONTRACT.md）：
    - 框架规则是泛化的通用能力，不包含特定场景
    - 运营配置是具体的业务规则，完整保留
    - LLM 进行语义级融合，不是简单拼接

    Args:
        user_prompt: 运营配置的系统提示词（任意格式、任何场景）

    Returns:
        合并后的最终系统提示词
    """
    from config.llm_config import get_llm_profile
    from core.llm import create_llm_service
    from core.prompt.framework_rules import get_merge_prompts

    # 🆕 V5.3: 从配置文件获取 LLM Profile（优先使用 Claude Sonnet 4.5）
    # 🆕 V7.10: 使用 create_llm_service 支持多模型容灾
    profile = await get_llm_profile("prompt_merger")
    logger.info(f"📦 使用 LLM Profile: prompt_merger, model={profile.get('model')}")

    # 获取合并提示词
    system_prompt, user_message = get_merge_prompts(user_prompt)

    try:
        # 使用 create_llm_service（支持多模型容灾）
        llm_service = create_llm_service(**profile)

        response = await llm_service.create_message_async(
            system=system_prompt,
            messages=[Message(role="user", content=user_message)],
            max_tokens=profile.get("max_tokens", 32000),
        )

        # LLMResponse.content 是字符串，不是列表
        merged_prompt = response.content.strip()

        # 计算压缩比
        original_len = len(user_prompt)
        merged_len = len(merged_prompt)
        ratio = merged_len / original_len if original_len > 0 else 1.0

        logger.info(f"✅ LLM 智能合并完成: {original_len} → {merged_len} 字符 (ratio={ratio:.2f})")

        return merged_prompt

    except Exception as e:
        logger.warning(f"⚠️ LLM 合并失败: {e}，直接使用运营配置")
        # 回退：直接使用运营配置（框架能力在默认 Schema 中体现）
        # 不做拼接，避免格式混乱
        return user_prompt
