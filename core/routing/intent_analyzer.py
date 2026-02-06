"""
V10.0 IntentAnalyzer - 意图分析器（简化版）

核心理念：
- 意图分析通过 LLM 语义理解完成
- 只输出 3 个核心字段：complexity, agent_type, skip_memory
- 其他字段（needs_plan, execution_strategy）由代码推断

设计原则：
- LLM-First：语义驱动决策
- 极简输出：减少 LLM 输出矛盾的可能
- 保守 fallback：不做关键词猜测
"""

# 1. 标准库
from typing import Any, Dict, List, Optional

from core.llm import Message

# 3. 本地模块
from core.routing.types import Complexity, IntentResult
from logger import get_logger
from prompts.intent_recognition_prompt import get_intent_recognition_prompt
from utils.json_utils import extract_json

# 2. 第三方库（无）


logger = get_logger(__name__)


class IntentAnalyzer:
    """
    V10.0 意图分析器（简化版）

    策略：LLM-First 语义推理
    - 只解析 3 个核心字段
    - 其他字段通过 property 推断

    使用方式：
        analyzer = IntentAnalyzer(llm_service)
        result = await analyzer.analyze([{"role": "user", "content": "..."}])
        print(result.complexity, result.agent_type)
    """

    def __init__(self, llm_service=None, enable_llm: bool = True, prompt_cache=None):
        """
        初始化意图分析器

        Args:
            llm_service: LLM 服务（用于意图分析）
            enable_llm: 是否启用 LLM 分析（False 则使用保守默认值）
            prompt_cache: InstancePromptCache（获取缓存的意图识别提示词）
        """
        self.llm = llm_service
        self.enable_llm = enable_llm and llm_service is not None
        self._prompt_cache = prompt_cache

    async def analyze(self, messages: List[Dict[str, Any]], tracker=None) -> IntentResult:
        """
        分析用户意图

        Args:
            messages: 完整的消息列表（包含上下文）
            tracker: UsageTracker 实例（可选）

        Returns:
            IntentResult 意图分析结果（3 个核心字段 + 推断属性）
        """
        if self.enable_llm:
            result = await self._analyze_with_llm(messages, tracker=tracker)
        else:
            result = self._get_conservative_default()

        logger.info(
            f"意图分析结果: "
            f"complexity={result.complexity.value}, "
            f"agent_type={result.agent_type}, "
            f"skip_memory={result.skip_memory}, "
            f"needs_plan={result.needs_plan}"
        )

        return result

    def _get_intent_prompt(self) -> str:
        """
        获取意图识别提示词

        优先从 InstancePromptCache 获取（用户配置优先）
        """
        if self._prompt_cache and self._prompt_cache.is_loaded:
            cached = self._prompt_cache.get_intent_prompt()
            if cached:
                logger.debug("使用缓存的意图识别提示词")
                return cached

        return get_intent_recognition_prompt()

    async def _analyze_with_llm(self, messages: List[Dict[str, Any]], tracker=None) -> IntentResult:
        """
        使用 LLM 分析意图

        Args:
            messages: 完整的消息列表
            tracker: UsageTracker 实例（可选）

        Returns:
            IntentResult
        """
        try:
            # 只保留最近 3 轮对话（6 条消息）
            max_messages = 6
            truncated = messages[-max_messages:] if len(messages) > max_messages else messages

            if len(truncated) < len(messages):
                logger.info(f"意图分析: 截断消息 {len(messages)} → {len(truncated)} 条")

            # 转换消息格式
            llm_messages = [Message(role=msg["role"], content=msg["content"]) for msg in truncated]

            # 获取 system prompt
            if self._prompt_cache and self._prompt_cache.is_loaded:
                if hasattr(self.llm, "config") and self.llm.config.enable_caching:
                    system_blocks = self._prompt_cache.get_cached_intent_blocks()
                    if not system_blocks:
                        system_blocks = self._get_intent_prompt()
                else:
                    system_blocks = self._get_intent_prompt()
            else:
                system_blocks = self._get_intent_prompt()

            # ========== 打印意图识别输入 ==========
            logger.info("=" * 60)
            logger.info("[意图识别] 输入消息:")
            for i, msg in enumerate(truncated):
                content = msg.get("content", "")
                # 截断过长内容便于查看
                content_preview = content[:200] + "..." if len(str(content)) > 200 else content
                logger.info(f"  [{i+1}] role={msg.get('role')}: {content_preview}")
            logger.info("=" * 60)

            # 调用 LLM
            response = await self.llm.create_message_async(
                messages=llm_messages, system=system_blocks
            )

            # 记录计费
            if tracker:
                tracker.record_call(
                    llm_response=response, model=response.model, purpose="intent_analysis"
                )

            # ========== 打印意图识别原始输出 ==========
            logger.info("=" * 60)
            logger.info(f"[意图识别] LLM 原始响应: {response.content}")
            logger.info("=" * 60)

            # 解析响应
            return self._parse_llm_response(response.content)

        except Exception as e:
            logger.warning(f"LLM 意图分析失败: {e}，使用保守默认值")
            return self._get_conservative_default()

    def _parse_llm_response(self, content: str) -> IntentResult:
        """
        解析 LLM 响应（只解析 3 个核心字段）

        Args:
            content: LLM 响应内容

        Returns:
            IntentResult
        """
        parsed = extract_json(content)

        if parsed and isinstance(parsed, dict):
            # 解析 complexity
            complexity_str = parsed.get("complexity", "medium")
            try:
                complexity = Complexity(complexity_str)
            except ValueError:
                complexity = Complexity.MEDIUM

            # 解析 agent_type
            agent_type = parsed.get("agent_type", "rvr")
            if agent_type not in ("rvr", "rvr-b", "multi"):
                agent_type = "rvr"

            # 解析 skip_memory
            skip_memory = parsed.get("skip_memory", False)
            if not isinstance(skip_memory, bool):
                skip_memory = False

            logger.debug(
                f"解析成功: complexity={complexity.value}, "
                f"agent_type={agent_type}, skip_memory={skip_memory}"
            )

            return IntentResult(
                complexity=complexity, agent_type=agent_type, skip_memory=skip_memory
            )
        else:
            logger.warning(f"无法解析 JSON: {content[:100]}...")
            return self._get_conservative_default()

    def _get_conservative_default(self) -> IntentResult:
        """
        获取保守默认值

        策略：中等复杂度，单智能体，不跳过记忆
        """
        logger.info("使用保守默认值")
        return IntentResult(
            complexity=Complexity.MEDIUM, agent_type="rvr", skip_memory=False, confidence=0.3
        )


def create_intent_analyzer(
    llm_service=None, enable_llm: bool = True, prompt_cache=None
) -> IntentAnalyzer:
    """
    创建意图分析器

    Args:
        llm_service: LLM 服务
        enable_llm: 是否启用 LLM 分析
        prompt_cache: InstancePromptCache

    Returns:
        IntentAnalyzer 实例
    """
    return IntentAnalyzer(llm_service=llm_service, enable_llm=enable_llm, prompt_cache=prompt_cache)
