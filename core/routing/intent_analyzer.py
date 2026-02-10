"""
V11.0 IntentAnalyzer - 意图分析器（小搭子简化版）

核心理念：
- 意图分析通过 LLM 语义理解完成
- 只输出 3 个核心字段：complexity, skip_memory, is_follow_up
- 其他字段（needs_plan）由代码推断
- 不需要 agent_type（固定 RVR-B）

设计原则：
- LLM-First：语义驱动决策
- 极简输出：减少 LLM 输出矛盾的可能
- 保守 fallback：不做关键词猜测
"""

# 1. 标准库
import asyncio
from typing import Any, Dict, List, Optional

from core.llm import Message

# 3. 本地模块
from core.routing.types import Complexity, IntentResult
from logger import get_logger
from prompts.intent_recognition_prompt import get_intent_recognition_prompt
from utils.json_utils import extract_json

# 2. 第三方库（无）


logger = get_logger(__name__)

# Tool definition for forced structured output via tool_choice.
# The model MUST call this tool, guaranteeing valid structured data
# instead of free-form text that may fail JSON parsing.
_INTENT_TOOL_NAME = "classify_intent"
_INTENT_TOOL = {
    "name": _INTENT_TOOL_NAME,
    "description": (
        "Output the intent classification result. "
        "Analyze the user's request and return structured classification."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "complexity": {
                "type": "string",
                "enum": ["simple", "medium", "complex"],
            },
            "skip_memory": {"type": "boolean"},
            "is_follow_up": {"type": "boolean"},
            "wants_to_stop": {"type": "boolean"},
            "wants_rollback": {"type": "boolean"},
            "relevant_skill_groups": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 6,
            },
        },
        "required": [
            "complexity",
            "skip_memory",
            "is_follow_up",
            "wants_to_stop",
            "wants_rollback",
            "relevant_skill_groups",
        ],
    },
}


class IntentAnalyzer:
    """
    V11.0 意图分析器（小搭子简化版）

    策略：LLM-First 语义推理
    - 只解析 complexity、skip_memory、is_follow_up
    - 固定使用 RVR-B 执行策略，不需要 agent_type

    使用方式：
        analyzer = IntentAnalyzer(llm_service)
        result = await analyzer.analyze([{"role": "user", "content": "..."}])
        print(result.complexity, result.skip_memory)
    """

    def __init__(
        self,
        llm_service=None,
        enable_llm: bool = True,
        prompt_cache=None,
        fast_mode: bool = False,
        semantic_cache_threshold: Optional[float] = None,
        simplified_output: bool = True,
    ):
        """
        初始化意图分析器

        Args:
            llm_service: LLM 服务（用于意图分析）
            enable_llm: 是否启用 LLM 分析（False 则使用保守默认值）
            prompt_cache: InstancePromptCache（获取缓存的意图识别提示词）
            fast_mode: 快速模式（可使用更快模型，由调用方选模型）
            semantic_cache_threshold: 语义缓存命中阈值（0-1），None 则用缓存默认
            simplified_output: 仅输出简化字段
        """
        self.llm = llm_service
        self.enable_llm = enable_llm and llm_service is not None
        self._prompt_cache = prompt_cache
        self.fast_mode = fast_mode
        self.semantic_cache_threshold = semantic_cache_threshold
        self.simplified_output = simplified_output

    async def analyze(self, messages: List[Dict[str, Any]], tracker=None) -> IntentResult:
        """
        Three-tier intent analysis: L1 Hash → L2 Semantic → L3 LLM

        精准优先：缓存命中要求高置信度，未命中走 LLM 语义分析。
        Embedding 模型不可用时静默降级为 hash-only（精准 100%，召回低可接受）。

        时延预算:
        - L1 Hash 命中: < 0.1ms
        - L2 Semantic 命中: < 60ms (embed ~50ms + cosine ~5ms)
        - L3 LLM: 100-500ms (模型/网络依赖)
        """
        # 提取最后一条用户消息作为缓存 key
        query_text = self._extract_query_text(messages)

        # === L1 Hash + L2 Semantic: 缓存查询 ===
        cache = self._get_cache()
        if cache and query_text:
            cached_result, score = await cache.lookup(query_text)
            if cached_result:
                logger.info(
                    f"意图分析结果 [缓存命中 score={score:.4f}]: "
                    f"complexity={cached_result.complexity.value}, "
                    f"skip_memory={cached_result.skip_memory}, "
                    f"is_follow_up={cached_result.is_follow_up}, "
                    f"needs_plan={cached_result.needs_plan}"
                )
                return cached_result

        # === L3: LLM 意图分析（兜底，ground truth）===
        if self.enable_llm:
            result = await self._analyze_with_llm(messages, tracker=tracker)
        else:
            result = self._get_conservative_default()

        # === L4: Skill 名称直匹配补偿 ===
        # 确定性安全网：用户 query 包含已知 skill 名时，补充对应 group
        result = self._supplement_skill_groups(result, query_text)

        # 异步存储到缓存（仅高置信度 LLM 结果，不阻塞主流程）
        if cache and query_text and result.confidence > 0.5:
            asyncio.create_task(self._safe_cache_store(cache, query_text, result))

        logger.info(
            f"意图分析结果: "
            f"complexity={result.complexity.value}, "
            f"skip_memory={result.skip_memory}, "
            f"is_follow_up={result.is_follow_up}, "
            f"needs_plan={result.needs_plan}"
        )

        return result

    def _get_cache(self):
        """
        Get intent cache instance (lazy init, None if disabled).

        首次调用时初始化，后续复用。缓存未启用时返回 None。
        """
        if not hasattr(self, "_cache_instance"):
            try:
                from core.routing.intent_cache import IntentSemanticCache

                cache = IntentSemanticCache.get_instance()
                self._cache_instance = cache if cache.config.enabled else None
            except Exception:
                self._cache_instance = None
        return self._cache_instance

    @staticmethod
    def _extract_query_text(messages: List[Dict[str, Any]]) -> Optional[str]:
        """
        Extract the last user message text as cache lookup key.

        仅提取最后一条 user 消息的文本内容，用于缓存 key。
        多模态内容（图片等）被忽略，只取文本部分。
        """
        for msg in reversed(messages):
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if isinstance(content, list):
                texts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        texts.append(block.get("text", ""))
                    elif isinstance(block, str):
                        texts.append(block)
                text = "\n".join(texts)
            elif isinstance(content, str):
                text = content
            else:
                continue
            return text.strip() if text.strip() else None
        return None

    @staticmethod
    async def _safe_cache_store(cache, query: str, result: "IntentResult") -> None:
        """Fire-and-forget cache store (store() has its own error handling)."""
        try:
            await cache.store(query, result)
        except Exception as e:
            logger.debug(f"Intent cache store failed (non-critical): {e}")

    def _get_intent_prompt(self) -> str:
        """
        获取意图识别提示词

        优先从 InstancePromptCache 获取（用户配置优先），
        Fallback 时从 SkillGroupRegistry 动态生成分组描述。
        """
        if self._prompt_cache and self._prompt_cache.is_loaded:
            cached = self._prompt_cache.get_intent_prompt()
            if cached:
                logger.debug("使用缓存的意图识别提示词")
                return cached

        # Fallback: 从 registry 生成分组描述
        groups_desc = ""
        if (
            self._prompt_cache
            and hasattr(self._prompt_cache, "runtime_context")
            and self._prompt_cache.runtime_context
        ):
            registry = self._prompt_cache.runtime_context.get("_skill_group_registry")
            if registry and hasattr(registry, "build_groups_description"):
                groups_desc = registry.build_groups_description()

        if not groups_desc:
            logger.warning("SkillGroupRegistry 不可用，意图识别使用空分组描述")
            groups_desc = "(无可用分组)"

        return get_intent_recognition_prompt(skill_groups_description=groups_desc)

    @staticmethod
    def _filter_for_intent(messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """
        Filter and flatten messages for intent analysis.

        Intent analysis only needs plain text — images, tool_use, tool_result
        blocks are stripped. This ensures compatibility with any LLM provider
        (Claude, Qwen, DeepSeek, OpenAI).

        Rules (O(n), < 0.1ms):
        - Keep last 5 user messages + last 1 assistant (truncated to 100 chars)
        - Discard tool_use / tool_result messages entirely
        - Extract text from multimodal content blocks
        - Return plain {role, content: str} dicts
        """
        filtered: List[Dict[str, str]] = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            # Skip tool_result messages (role=user but content is tool results)
            if isinstance(content, list) and any(
                isinstance(b, dict) and b.get("type") in ("tool_use", "tool_result")
                for b in content
            ):
                continue

            # Extract plain text from content
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        # Skip image, tool_use, tool_result, thinking blocks
                    elif isinstance(block, str):
                        text_parts.append(block)
                text = "\n".join(text_parts)
            elif isinstance(content, str):
                text = content
            else:
                text = str(content)

            if not text.strip():
                continue

            filtered.append({"role": role, "content": text})

        # Keep last 5 user messages + last 1 assistant (truncated)
        user_msgs = [m for m in filtered if m["role"] == "user"][-5:]
        assistant_msgs = [m for m in filtered if m["role"] == "assistant"][-1:]
        for m in assistant_msgs:
            m["content"] = m["content"][:100]

        # Rebuild in original order
        result = []
        u_idx, a_idx = 0, 0
        for m in filtered:
            if m["role"] == "user" and m in user_msgs:
                result.append(m)
            elif m["role"] == "assistant" and m in assistant_msgs:
                result.append(m)

        return result if result else filtered[-1:]  # at least 1 message

    async def _analyze_with_llm(self, messages: List[Dict[str, Any]], tracker=None) -> IntentResult:
        """
        Use LLM for intent analysis with forced structured output.

        Uses tool_choice to force the model to call classify_intent,
        guaranteeing structured output. Falls back to text parsing
        if tool call is unavailable.

        Args:
            messages: Raw message list (may contain multimodal content).
            tracker: UsageTracker (optional).

        Returns:
            IntentResult
        """
        try:
            # Filter: extract text, drop tool blocks, limit message count
            filtered = self._filter_for_intent(messages)

            if len(filtered) < len(messages):
                logger.info(f"意图分析: 过滤消息 {len(messages)} → {len(filtered)} 条")

            # Convert to Message objects (content is always str after filtering)
            llm_messages = [Message(role=msg["role"], content=msg["content"]) for msg in filtered]

            # Get system prompt
            if self._prompt_cache and self._prompt_cache.is_loaded:
                if hasattr(self.llm, "config") and self.llm.config.enable_caching:
                    system_blocks = self._prompt_cache.get_cached_intent_blocks()
                    if not system_blocks:
                        system_blocks = self._get_intent_prompt()
                else:
                    system_blocks = self._get_intent_prompt()
            else:
                system_blocks = self._get_intent_prompt()

            # Log input (debug level; content is already plain text)
            if logger.isEnabledFor(20):  # INFO
                logger.info("[意图识别] 输入消息:")
                for i, msg in enumerate(filtered):
                    preview = msg["content"][:200] + "..." if len(msg["content"]) > 200 else msg["content"]
                    logger.info(f"  [{i+1}] {msg['role']}: {preview}")

            # Call LLM with tool_choice to force structured output
            response = await self.llm.create_message_async(
                messages=llm_messages,
                system=system_blocks,
                tools=[_INTENT_TOOL],
                tool_choice={"type": "tool", "name": _INTENT_TOOL_NAME},
            )

            # 记录计费
            if tracker:
                tracker.record_call(
                    llm_response=response, model=response.model, purpose="intent_analysis"
                )

            # Parse from tool call (primary path: structured output)
            if response.tool_calls:
                parsed = response.tool_calls[0].get("input", {})
                logger.info("=" * 60)
                logger.info(f"[意图识别] tool_choice 结构化输出: {parsed}")
                logger.info("=" * 60)
                return self._parse_intent_dict(parsed)

            # Fallback: parse text content (should rarely happen)
            logger.info("=" * 60)
            logger.info(f"[意图识别] LLM 原始响应 (text fallback): {response.content}")
            logger.info("=" * 60)
            return self._parse_llm_response(response.content or "")

        except Exception as e:
            logger.warning(f"LLM 意图分析失败: {e}，使用保守默认值")
            return self._get_conservative_default()

    def _parse_intent_dict(self, parsed: Dict[str, Any]) -> IntentResult:
        """
        Parse a dict (from tool_call input or extracted JSON) into IntentResult.

        Each field is validated with safe defaults.

        Args:
            parsed: Dict with intent classification fields.

        Returns:
            IntentResult
        """
        complexity_str = parsed.get("complexity", "medium")
        try:
            complexity = Complexity(complexity_str)
        except ValueError:
            complexity = Complexity.MEDIUM

        skip_memory = parsed.get("skip_memory", False)
        if not isinstance(skip_memory, bool):
            skip_memory = False

        is_follow_up = parsed.get("is_follow_up", False)
        if not isinstance(is_follow_up, bool):
            is_follow_up = False

        wants_to_stop = parsed.get("wants_to_stop", False)
        if not isinstance(wants_to_stop, bool):
            wants_to_stop = False

        wants_rollback = parsed.get("wants_rollback", False)
        if not isinstance(wants_rollback, bool):
            wants_rollback = False

        relevant_skill_groups = parsed.get("relevant_skill_groups", [])
        if not isinstance(relevant_skill_groups, list):
            relevant_skill_groups = []
        relevant_skill_groups = [str(g) for g in relevant_skill_groups if g]

        logger.debug(
            f"解析成功: complexity={complexity.value}, "
            f"skip_memory={skip_memory}, is_follow_up={is_follow_up}, "
            f"wants_to_stop={wants_to_stop}, "
            f"relevant_skill_groups={relevant_skill_groups}"
        )

        return IntentResult(
            complexity=complexity,
            skip_memory=skip_memory,
            is_follow_up=is_follow_up,
            wants_to_stop=wants_to_stop,
            wants_rollback=wants_rollback,
            relevant_skill_groups=relevant_skill_groups,
        )

    def _parse_llm_response(self, content: str) -> IntentResult:
        """
        Parse LLM text response (fallback when tool_choice is unavailable).

        Extracts JSON from free-form text, then delegates to _parse_intent_dict.

        Args:
            content: LLM text response.

        Returns:
            IntentResult
        """
        parsed = extract_json(content)

        if parsed and isinstance(parsed, dict):
            return self._parse_intent_dict(parsed)
        else:
            logger.warning(f"无法解析 JSON: {content[:100]}...")
            return self._get_conservative_default()

    def _supplement_skill_groups(
        self, result: IntentResult, query_text: Optional[str]
    ) -> IntentResult:
        """
        Deterministic post-check after LLM analysis.

        If user query contains a known skill name (exact match), ensure that
        skill's group is included in relevant_skill_groups. This catches cases
        where the LLM fails to map English skill names to Chinese group
        descriptions (e.g. "trend-spotter" → research group's "趋势发现").

        This is a safety net, not a replacement for LLM judgment.
        When relevant_skill_groups is None (full fallback), skip supplementation
        since all skills will be injected anyway.

        Args:
            result: IntentResult from LLM analysis
            query_text: extracted user query text

        Returns:
            IntentResult with supplemented groups (if any)
        """
        if not query_text:
            return result

        # None = full fallback (all skills injected), no supplementation needed
        if result.relevant_skill_groups is None:
            return result

        registry = self._get_skill_group_registry()
        if not registry:
            return result

        supplemented = registry.supplement_groups_from_query(
            query_text, result.relevant_skill_groups
        )

        if supplemented != result.relevant_skill_groups:
            added = set(supplemented) - set(result.relevant_skill_groups)
            logger.info(
                f"[意图识别] Skill 名称直匹配补充分组: {sorted(added)}"
            )
            result.relevant_skill_groups = supplemented

        return result

    def _get_skill_group_registry(self):
        """Get SkillGroupRegistry from prompt cache runtime context."""
        if (
            self._prompt_cache
            and hasattr(self._prompt_cache, "runtime_context")
            and self._prompt_cache.runtime_context
        ):
            return self._prompt_cache.runtime_context.get("_skill_group_registry")
        return None

    def _get_conservative_default(self) -> IntentResult:
        """
        获取保守默认值

        策略：中等复杂度，不跳过记忆，非追问，全量注入 Skills（保守）
        relevant_skill_groups=None 表示"不确定需要什么"，触发全量 Skills 注入，
        确保 Agent 不会因为解析失败而丧失能力。
        """
        logger.info("使用保守默认值")
        return IntentResult(
            complexity=Complexity.MEDIUM,
            skip_memory=False,
            is_follow_up=False,
            wants_to_stop=False,
            confidence=0.3,
            relevant_skill_groups=None,  # None = 全量注入，保守策略
        )


def create_intent_analyzer(
    llm_service=None,
    enable_llm: bool = True,
    prompt_cache=None,
    fast_mode: bool = False,
    semantic_cache_threshold: Optional[float] = None,
    simplified_output: bool = True,
) -> IntentAnalyzer:
    """
    创建意图分析器

    Args:
        llm_service: LLM 服务
        enable_llm: 是否启用 LLM 分析
        prompt_cache: InstancePromptCache
        fast_mode: 快速模式
        semantic_cache_threshold: 语义缓存命中阈值
        simplified_output: 仅输出简化字段

    Returns:
        IntentAnalyzer 实例
    """
    return IntentAnalyzer(
        llm_service=llm_service,
        enable_llm=enable_llm,
        prompt_cache=prompt_cache,
        fast_mode=fast_mode,
        semantic_cache_threshold=semantic_cache_threshold,
        simplified_output=simplified_output,
    )
