"""
V5.0 统一语义推理模块

核心理念：
- 所有推理都通过 LLM 语义理解完成
- 使用 Few-Shot 提示词教会 LLM 推理模式
- 代码只做调用和解析，不做规则判断
- 保守的 fallback（默认值），不做关键词猜测

设计原则：
- 运营无需配置任何推理规则
- 框架内置 Few-Shot 示例
- 对运营完全透明

┌────────────────────────────────────────────────────────┐
│  用户输入 → LLM 语义推理 → 结构化结果                    │
│                                                        │
│  Few-Shot 示例教会 LLM:                                 │
│  • "构造CRM系统" → Complex (build + 完整架构)           │
│  • "这个系统怎么用" → Simple (询问，非构建)             │
│  • "分析销售趋势" → Medium (分析，单一任务)             │
└────────────────────────────────────────────────────────┘
"""

import asyncio
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from logger import get_logger

logger = get_logger("semantic_inference")


# ============================================================
# 推理类型枚举
# ============================================================


class InferenceType(str, Enum):
    """推理类型"""

    COMPLEXITY = "complexity"  # 复杂度推理
    INTENT = "intent"  # 意图推理
    CAPABILITY = "capability"  # 能力推理
    SCHEMA = "schema"  # Schema 推理


# ============================================================
# 推理结果数据类
# ============================================================


@dataclass
class InferenceResult:
    """推理结果"""

    inference_type: InferenceType
    result: Dict[str, Any]
    confidence: float = 1.0
    reasoning: str = ""
    is_fallback: bool = False  # 是否使用了 fallback


# ============================================================
# Few-Shot 提示词（框架内置，运营无需配置）
# ============================================================

COMPLEXITY_FEW_SHOT = """你是一个任务复杂度分析专家。分析用户的请求，判断其复杂度级别。

## 复杂度定义

- **simple**: 单一问答、简单查询、打招呼、获取基本信息。无需多步骤处理。
- **medium**: 需要分析、对比、生成报告或文档、提供建议。需要 3-5 步处理。
- **complex**: 系统设计、架构规划、业务流程构建、多实体关系建模。需要完整规划和多轮迭代。

## 学习示例（理解语义，不是匹配关键词）

### 示例 1
用户: "今天天气怎么样？"
分析: 单一信息查询，直接获取即可
输出: {"complexity": "simple", "reasoning": "天气查询，单步完成"}

### 示例 2
用户: "构造CRM系统"
分析: "构造"是 build 动作，"系统"表示完整架构，需要多轮设计和建模
输出: {"complexity": "complex", "reasoning": "系统构建，需要需求分析、架构设计、实体建模等多个阶段"}

### 示例 3
用户: "这个系统怎么用？"
分析: 虽然提到"系统"，但这是询问使用方法，不是构建
输出: {"complexity": "simple", "reasoning": "询问使用方法，直接回答即可"}

### 示例 4
用户: "帮我分析一下销售数据趋势"
分析: 需要获取数据、分析趋势、总结洞察，但是单一分析任务
输出: {"complexity": "medium", "reasoning": "数据分析任务，需要获取数据和分析，但非系统级"}

### 示例 5
用户: "做个简单的自我介绍PPT"
分析: 虽然涉及 PPT 生成，但"简单"限定了范围，不需要深度规划
输出: {"complexity": "medium", "reasoning": "PPT 生成但范围简单，中等复杂度"}

### 示例 6
用户: "设计一个完整的电商平台"
分析: 完整平台设计，涉及多个子系统、多实体关系、业务流程
输出: {"complexity": "complex", "reasoning": "完整平台设计，需要全面规划和多轮迭代"}

### 示例 7
用户: "你好"
分析: 打招呼，闲聊
输出: {"complexity": "simple", "reasoning": "闲聊问候"}

### 示例 8
用户: "帮我写一份市场调研报告"
分析: 需要调研、收集信息、分析、撰写，但是单一任务
输出: {"complexity": "medium", "reasoning": "报告撰写，需要多步但非系统设计"}

## 现在分析

用户: "{query}"

请直接输出 JSON（不要其他内容）："""


INTENT_FEW_SHOT = """你是一个用户意图分析专家。分析用户的请求，识别其任务类型。

## 任务类型定义

- **information_query**: 信息查询、搜索、获取知识
- **content_generation**: 生成文档、报告、PPT、代码等内容
- **data_analysis**: 数据分析、统计、可视化
- **system_design**: 系统设计、架构规划、业务建模
- **conversation**: 闲聊、问候、非任务对话
- **task_execution**: 执行具体操作、运行命令

## 学习示例

### 示例 1
用户: "北京今天天气怎么样？"
分析: 获取天气信息
输出: {"task_type": "information_query", "reasoning": "查询天气信息"}

### 示例 2
用户: "帮我写一份周报"
分析: 生成文档内容
输出: {"task_type": "content_generation", "reasoning": "生成周报文档"}

### 示例 3
用户: "分析这份 Excel 中的销售趋势"
分析: 数据分析任务
输出: {"task_type": "data_analysis", "reasoning": "分析销售数据"}

### 示例 4
用户: "设计一个库存管理系统"
分析: 系统设计任务
输出: {"task_type": "system_design", "reasoning": "设计管理系统"}

### 示例 5
用户: "你好，最近怎么样？"
分析: 闲聊问候
输出: {"task_type": "conversation", "reasoning": "日常问候"}

## 现在分析

用户: "{query}"

请直接输出 JSON（不要其他内容）："""


CAPABILITY_FEW_SHOT = """你是一个工具能力分析专家。根据工具的名称和描述，推断它能够满足的用户意图类别。

## 能力类别

- **document_creation**: 创建文档、图表、流程图
- **ppt_generation**: 生成演示文稿
- **web_search**: 网络搜索、信息检索
- **data_analysis**: 数据分析、统计计算
- **image_generation**: 生成图片
- **code_execution**: 执行代码、脚本
- **notification**: 发送通知、邮件
- **crm_integration**: CRM 系统集成

## 学习示例

### 示例 1
工具: {"name": "diagram_skill", "description": "将文本描述转换为流程图或图表"}
分析: 生成流程图是文档/图表创建能力
输出: {"capabilities": ["document_creation"], "reasoning": "生成流程图属于文档创建"}

### 示例 2
工具: {"name": "search_skill", "description": "通过搜索类 Skill 进行互联网信息检索"}
分析: 网络搜索能力
输出: {"capabilities": ["web_search"], "reasoning": "互联网搜索"}

### 示例 3
工具: {"name": "ppt_skill", "description": "根据配置生成 PPT 演示文稿"}
分析: PPT 生成能力
输出: {"capabilities": ["ppt_generation", "document_creation"], "reasoning": "生成 PPT 演示文稿"}

### 示例 4
工具: {"name": "python_executor", "description": "安全环境执行 Python 代码"}
分析: 代码执行能力，也可用于数据分析
输出: {"capabilities": ["code_execution", "data_analysis"], "reasoning": "执行代码，支持数据分析"}

## 现在分析

工具: {tool_info}

请直接输出 JSON（不要其他内容）："""


# ============================================================
# 语义推理核心类
# ============================================================


class SemanticInference:
    """
    统一的 LLM 语义推理接口

    职责：
    1. 复杂度推理（替代关键词匹配）
    2. 意图推理（替代关键词规则）
    3. 能力推断（替代 keyword_map）

    设计原则：
    - 运营无需配置，框架内置 Few-Shot 示例
    - LLM 学习示例模式，进行语义泛化推理
    - 保守的 fallback（默认值），不做关键词猜测
    """

    # Few-Shot 提示词映射
    FEW_SHOT_PROMPTS = {
        InferenceType.COMPLEXITY: COMPLEXITY_FEW_SHOT,
        InferenceType.INTENT: INTENT_FEW_SHOT,
        InferenceType.CAPABILITY: CAPABILITY_FEW_SHOT,
    }

    # 保守的默认值（不做智能猜测）
    CONSERVATIVE_DEFAULTS = {
        InferenceType.COMPLEXITY: {
            "complexity": "medium",
            "reasoning": "LLM 推理失败，使用保守默认值",
        },
        InferenceType.INTENT: {"task_type": "other", "reasoning": "LLM 推理失败，使用保守默认值"},
        InferenceType.CAPABILITY: {"capabilities": [], "reasoning": "LLM 推理失败，使用保守默认值"},
    }

    def __init__(self, llm_service=None):
        """
        初始化语义推理器

        Args:
            llm_service: LLM 服务（可选，懒加载）
        """
        self._llm_service = llm_service
        self._cache: Dict[str, InferenceResult] = {}  # 简单内存缓存

    async def _get_llm_service(self):
        """获取 LLM 服务（懒加载）"""
        if self._llm_service is None:
            try:
                # 🆕 使用配置化的 LLM Profile
                # 🆕 V7.10: 使用 create_llm_service 支持多模型容灾
                from config.llm_config import get_llm_profile
                from core.llm import create_llm_service

                profile = await get_llm_profile("semantic_inference")
                self._llm_service = create_llm_service(**profile)
            except Exception as e:
                logger.warning(f"⚠️ LLM 服务初始化失败: {e}")
                return None
        return self._llm_service

    def _get_cache_key(self, inference_type: InferenceType, context: str) -> str:
        """生成缓存 key"""
        return f"{inference_type.value}:{hash(context)}"

    async def infer(
        self, inference_type: InferenceType, context: Dict[str, Any]
    ) -> InferenceResult:
        """
        执行语义推理

        Args:
            inference_type: 推理类型
            context: 推理上下文（如 {"query": "..."} 或 {"tool_info": {...}}）

        Returns:
            InferenceResult 推理结果
        """
        # 1. 构建上下文字符串
        context_str = self._build_context_string(inference_type, context)

        # 2. 检查缓存
        cache_key = self._get_cache_key(inference_type, context_str)
        if cache_key in self._cache:
            logger.debug(f"📦 缓存命中: {inference_type.value}")
            return self._cache[cache_key]

        # 3. 获取 LLM 服务
        llm = await self._get_llm_service()
        if llm is None:
            logger.warning(f"⚠️ LLM 服务不可用，使用保守默认值")
            return self._get_fallback_result(inference_type)

        # 4. 构建 Few-Shot 提示词
        prompt = self._build_prompt(inference_type, context)

        # 5. 调用 LLM
        try:
            # 🆕 使用配置化的 LLM Profile
            from config.llm_config import get_llm_profile
            from core.llm import Message

            profile = await get_llm_profile("semantic_inference")

            response = await llm.create_message_async(
                messages=[Message(role="user", content=prompt)], **profile
            )

            # 6. 解析响应
            result = self._parse_response(inference_type, response)

            # 7. 缓存结果
            self._cache[cache_key] = result

            logger.info(f"🧠 语义推理完成: {inference_type.value} → {result.result}")
            return result

        except Exception as e:
            logger.warning(f"⚠️ LLM 推理失败: {e}，使用保守默认值")
            return self._get_fallback_result(inference_type)

    def _build_context_string(self, inference_type: InferenceType, context: Dict[str, Any]) -> str:
        """构建上下文字符串（用于缓存 key）"""
        if inference_type == InferenceType.COMPLEXITY:
            return context.get("query", "")
        elif inference_type == InferenceType.INTENT:
            return context.get("query", "")
        elif inference_type == InferenceType.CAPABILITY:
            tool_info = context.get("tool_info", {})
            return f"{tool_info.get('name', '')}:{tool_info.get('description', '')}"
        return str(context)

    def _build_prompt(self, inference_type: InferenceType, context: Dict[str, Any]) -> str:
        """构建 Few-Shot 提示词"""
        template = self.FEW_SHOT_PROMPTS.get(inference_type, "")

        # 使用字符串替换而不是 .format()（避免 JSON 中的花括号被误解析）
        if inference_type == InferenceType.COMPLEXITY:
            return template.replace("{query}", context.get("query", ""))
        elif inference_type == InferenceType.INTENT:
            return template.replace("{query}", context.get("query", ""))
        elif inference_type == InferenceType.CAPABILITY:
            tool_info = context.get("tool_info", {})
            return template.replace("{tool_info}", json.dumps(tool_info, ensure_ascii=False))

        return template

    def _parse_response(self, inference_type: InferenceType, response) -> InferenceResult:
        """解析 LLM 响应"""
        try:
            # 提取文本（LLMResponse.content 是 str 类型）
            text = response.content.strip() if response.content else ""

            # 清理可能的 markdown 代码块
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            if text.endswith("```"):
                text = text[:-3]

            # 解析 JSON
            result_data = json.loads(text.strip())

            return InferenceResult(
                inference_type=inference_type,
                result=result_data,
                confidence=0.9,  # LLM 推理置信度高
                reasoning=result_data.get("reasoning", ""),
                is_fallback=False,
            )

        except (json.JSONDecodeError, IndexError, KeyError, AttributeError) as e:
            logger.warning(f"⚠️ 解析 LLM 响应失败: {e}")
            return self._get_fallback_result(inference_type)

    def _get_fallback_result(self, inference_type: InferenceType) -> InferenceResult:
        """获取保守的 fallback 结果（不做关键词猜测）"""
        default = self.CONSERVATIVE_DEFAULTS.get(inference_type, {})
        return InferenceResult(
            inference_type=inference_type,
            result=default,
            confidence=0.3,  # 低置信度，标记这是猜测
            reasoning="LLM 服务不可用，使用保守默认值",
            is_fallback=True,
        )

    # ============================================================
    # 便捷方法
    # ============================================================

    async def infer_complexity(self, query: str) -> InferenceResult:
        """推断任务复杂度"""
        return await self.infer(InferenceType.COMPLEXITY, {"query": query})

    async def infer_intent(self, query: str) -> InferenceResult:
        """推断用户意图"""
        return await self.infer(InferenceType.INTENT, {"query": query})

    async def infer_capability(self, tool_name: str, tool_description: str) -> InferenceResult:
        """推断工具能力"""
        return await self.infer(
            InferenceType.CAPABILITY,
            {"tool_info": {"name": tool_name, "description": tool_description}},
        )


# ============================================================
# 便捷函数
# ============================================================

# 全局单例（懒加载）
_global_inference: Optional[SemanticInference] = None


def get_semantic_inference() -> SemanticInference:
    """获取全局语义推理实例"""
    global _global_inference
    if _global_inference is None:
        _global_inference = SemanticInference()
    return _global_inference


async def infer_complexity(query: str) -> str:
    """
    便捷函数：推断任务复杂度

    Args:
        query: 用户输入

    Returns:
        "simple" | "medium" | "complex"
    """
    inference = get_semantic_inference()
    result = await inference.infer_complexity(query)
    return result.result.get("complexity", "medium")


async def infer_intent(query: str) -> str:
    """
    便捷函数：推断用户意图

    Args:
        query: 用户输入

    Returns:
        任务类型字符串
    """
    inference = get_semantic_inference()
    result = await inference.infer_intent(query)
    return result.result.get("task_type", "other")


async def infer_capability(tool_name: str, tool_description: str) -> List[str]:
    """
    便捷函数：推断工具能力

    Args:
        tool_name: 工具名称
        tool_description: 工具描述

    Returns:
        能力列表
    """
    inference = get_semantic_inference()
    result = await inference.infer_capability(tool_name, tool_description)
    return result.result.get("capabilities", [])
