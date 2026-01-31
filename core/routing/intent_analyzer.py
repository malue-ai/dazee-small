"""
V5.0 IntentAnalyzer - 意图分析器

🆕 V6.1: 新增上下文感知（追问识别）
🆕 V9.2: 新增 task_dependency_type 解析（任务依赖类型）
🆕 V9.3: 新增语义缓存支持（减少 LLM 调用，降低延迟和成本）

核心理念：
- 意图分析通过 LLM 语义理解完成
- 不使用关键词匹配规则
- 保守的 fallback（OTHER），不做关键词猜测
- 识别追问/新话题，避免上下文脱节
- 语义驱动的 Multi-Agent 和执行策略决策

设计原则：
- 运营无需配置任何关键词规则
- LLM 学习 Few-Shot 示例进行语义泛化推理
- 代码只做调用和解析，不做规则判断
- 运营配置提示词 + 高质量默认模板 → 场景化意图识别

🆕 V9.3 语义缓存策略：
- L1: 精确匹配（hash）< 0.1ms
- L2: 语义匹配（embedding）< 60ms
- 阈值 >= 0.92 时直接返回缓存结果
"""

# 1. 标准库
import asyncio
import logging
from typing import Dict, Any, Optional, List, TYPE_CHECKING

# 3. 本地模块
from utils.json_utils import extract_json
from core.agent.types import (
    IntentResult,
    TaskType,
    Complexity,
)

if TYPE_CHECKING:
    from core.routing.intent_cache import IntentSemanticCache

logger = logging.getLogger(__name__)


class IntentAnalyzer:
    """
    V5.0 意图分析器
    
    策略：LLM-First 语义推理
    - 直接使用 LLM 进行语义理解
    - 不使用关键词匹配
    - 保守的 fallback（OTHER）
    
    🆕 V9.0: 用户问题聚焦型过滤
    - 意图识别只关注用户 query，过滤智能体回复和工具调用
    - 时延约束 < 200ms，过滤逻辑 < 0.1ms（纯 CPU）
    
    使用方式：
        analyzer = IntentAnalyzer(llm_service)
        result = await analyzer.analyze([{"role": "user", "content": "..."}])
        print(result.task_type)
    """
    
    # 🆕 V9.0: 意图识别上下文过滤配置
    MAX_USER_MESSAGES_FOR_INTENT = 5   # 最多保留 5 条用户消息
    LAST_ASSISTANT_TRUNCATE = 100      # 最后一条 assistant 截断长度
    
    def __init__(
        self,
        llm_service=None,
        enable_llm: bool = True,
        prompt_cache=None,  # InstancePromptCache
        semantic_cache: Optional["IntentSemanticCache"] = None,  # 🆕 V9.3
        enable_semantic_cache: bool = True  # 🆕 V9.3
    ):
        """
        初始化意图分析器
        
        Args:
            llm_service: LLM 服务（用于意图分析）
            enable_llm: 是否启用 LLM 分析（False 则使用保守默认值）
            prompt_cache: InstancePromptCache（获取缓存的意图识别提示词）
            semantic_cache: 语义缓存实例（可选，不提供则自动获取单例）
            enable_semantic_cache: 是否启用语义缓存（默认 True）
        """
        self.llm = llm_service
        self.enable_llm = enable_llm and llm_service is not None
        self._prompt_cache = prompt_cache
        
        # 🆕 V9.3: 语义缓存
        self._enable_semantic_cache = enable_semantic_cache
        self._semantic_cache = semantic_cache  # 延迟初始化
    
    def _get_semantic_cache(self) -> Optional["IntentSemanticCache"]:
        """
        获取语义缓存实例（延迟初始化）
        
        Returns:
            IntentSemanticCache 实例，禁用时返回 None
        """
        if not self._enable_semantic_cache:
            return None
        
        if self._semantic_cache is None:
            try:
                from core.routing.intent_cache import get_intent_cache
                self._semantic_cache = get_intent_cache()
            except Exception as e:
                logger.warning(f"⚠️ 语义缓存初始化失败: {e}")
                self._enable_semantic_cache = False
                return None
        
        return self._semantic_cache
    
    async def analyze(
        self,
        messages: List[Dict[str, Any]]
    ) -> IntentResult:
        """
        分析用户意图
        
        V5.0 策略：LLM-First，无关键词匹配
        🆕 V9.3: 语义缓存优先，减少 LLM 调用
        
        Args:
            messages: 完整的消息列表（包含上下文）
            
        Returns:
            IntentResult 意图分析结果
        """
        # 🆕 V9.3: 提取查询文本（用于缓存 key）
        query_text = self._extract_query_for_cache(messages)
        cache_hit = False
        cache_score = 0.0
        
        # 🆕 V9.3: 先查询语义缓存
        semantic_cache = self._get_semantic_cache()
        if semantic_cache and query_text:
            try:
                cached_result, cache_score = await semantic_cache.lookup(query_text)
                if cached_result and cache_score >= semantic_cache.config.threshold:
                    cache_hit = True
                    result = cached_result
                    logger.info(
                        f"✅ 语义缓存命中: score={cache_score:.4f}, "
                        f"type={result.task_type.value}"
                    )
            except Exception as e:
                logger.warning(f"⚠️ 语义缓存查询失败: {e}")
        
        # 缓存未命中，使用 LLM 分析
        if not cache_hit:
            if self.enable_llm:
                result = await self._analyze_with_llm(messages)
            else:
                result = self._get_conservative_default()
            
            # 🆕 V9.3: 异步写入缓存（不阻塞主流程）
            if semantic_cache and query_text:
                asyncio.create_task(self._store_to_cache(semantic_cache, query_text, result))
        
        # 自动计算是否需要持久化
        result.needs_persistence = self._should_persist(result)
        
        logger.info(
            f"🎯 意图分析结果: "
            f"type={result.task_type.value}, "
            f"complexity={result.complexity.value}, "
            f"score={result.complexity_score:.1f}, "
            f"needs_plan={result.needs_plan}, "
            f"needs_persistence={result.needs_persistence}, "
            f"skip_memory={result.skip_memory_retrieval}, "
            f"needs_multi_agent={result.needs_multi_agent}, "
            f"dependency_type={result.task_dependency_type}, "
            f"is_follow_up={result.is_follow_up}, "
            f"cache_hit={cache_hit}"  # 🆕 V9.3
        )
        
        return result
    
    def _extract_query_for_cache(self, messages: List[Dict[str, Any]]) -> str:
        """
        🆕 V9.3: 提取用于缓存的查询文本
        
        策略：使用最后一条用户消息作为缓存 key
        
        Args:
            messages: 消息列表
            
        Returns:
            查询文本
        """
        return self._extract_last_user_text(messages)
    
    async def _store_to_cache(
        self,
        cache: "IntentSemanticCache",
        query: str,
        result: IntentResult
    ) -> None:
        """
        🆕 V9.3: 异步存储到语义缓存
        
        Args:
            cache: 语义缓存实例
            query: 查询文本
            result: 意图分析结果
        """
        try:
            await cache.store(query, result)
        except Exception as e:
            logger.warning(f"⚠️ 语义缓存存储失败: {e}")
    
    async def analyze_with_context(
        self,
        messages: List[Dict[str, Any]],
        previous_result: Optional[IntentResult] = None
    ) -> IntentResult:
        """
        🆕 V6.1 带上下文的意图分析（追问场景优化）
        
        如果检测到追问（is_follow_up=True）且有上轮结果，复用上轮的 task_type，
        避免重复完整分析，提升性能。
        
        Args:
            messages: 完整的消息列表（包含上下文）
            previous_result: 上一轮的意图分析结果（用于追问场景复用）
            
        Returns:
            IntentResult 意图分析结果
            
        使用示例：
            # 存储上轮意图结果（session 级别）
            if hasattr(agent, '_last_intent_result'):
                previous = agent._last_intent_result
            else:
                previous = None
            
            intent_result = await analyzer.analyze_with_context(messages, previous)
            agent._last_intent_result = intent_result
        """
        # 1. 执行正常分析
        result = await self.analyze(messages)
        
        # 2. 如果是追问且有上轮结果，继承 task_type
        if result.is_follow_up and previous_result:
            inherited_task_type = previous_result.task_type
            logger.info(
                f"🔄 追问场景优化: 继承上轮 task_type={inherited_task_type.value} "
                f"(当前分析: {result.task_type.value})"
            )
            result.task_type = inherited_task_type
            # complexity 可能变化（追问可能变简单），保留新分析结果
            # needs_plan 也可能变化，保留新分析结果
        
        return result
    
    def _should_persist(self, result: IntentResult) -> bool:
        """
        判断是否需要跨 Session 持久化
        
        触发条件（满足任一）：
        1. 复杂度为 COMPLEX
        2. 需要规划（needs_plan=True）
        3. 任务类型为 CONTENT_GENERATION 或 CODE_DEVELOPMENT
        
        Args:
            result: 意图分析结果
            
        Returns:
            是否需要持久化
        """
        # 条件 1: 复杂任务
        if result.complexity == Complexity.COMPLEX:
            return True
        
        # 条件 2: 需要规划的任务
        if result.needs_plan:
            return True
        
        # 条件 3: 内容生成或代码开发任务
        if result.task_type in [TaskType.CONTENT_GENERATION, TaskType.CODE_DEVELOPMENT]:
            return True
        
        return False
    
    def _filter_for_intent(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        🆕 V9.1: 为意图识别过滤消息（保留对话顺序，支持追问识别）
        
        规则：
        1. 保留最近 N 轮对话（user + assistant 为一轮）
        2. assistant 消息截断为摘要（避免过长）
        3. 直接丢弃 tool_use/tool_result 内容
        4. **保持对话的自然顺序**（关键！追问识别依赖此顺序）
        
        设计原则：
        - 追问识别需要完整的上下文顺序
        - 工具调用结果会污染上下文，影响意图准确率
        - 时延约束 < 200ms，过滤逻辑必须轻量
        
        Args:
            messages: 完整的消息列表
            
        Returns:
            过滤后的消息列表（用于意图分析）
        """
        result = []
        user_count = 0
        
        # 正向遍历，保持原始顺序
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            
            # 跳过工具调用相关消息
            if isinstance(content, list):
                # 检查是否包含 tool_use 或 tool_result
                has_tool = any(
                    isinstance(block, dict) and block.get("type") in ("tool_use", "tool_result")
                    for block in content
                )
                if has_tool:
                    continue
            
            if role == "user":
                user_count += 1
                # 提取用户消息文本（处理 Claude API 格式）
                text = self._extract_text(content)
                if text:
                    result.append({"role": "user", "content": text})
                        
            elif role == "assistant":
                # 截断 assistant 消息
                text = self._extract_text(content)
                if text:
                    truncated = text[:self.LAST_ASSISTANT_TRUNCATE]
                    if len(text) > self.LAST_ASSISTANT_TRUNCATE:
                        truncated += "..."
                    result.append({"role": "assistant", "content": truncated})
        
        # 如果消息过多，只保留最近的 N 条用户消息相关的上下文
        if user_count > self.MAX_USER_MESSAGES_FOR_INTENT:
            # 从后往前保留，确保包含最近的对话轮次
            kept_user_count = 0
            filtered_result = []
            for msg in reversed(result):
                if msg["role"] == "user":
                    kept_user_count += 1
                if kept_user_count <= self.MAX_USER_MESSAGES_FOR_INTENT:
                    filtered_result.insert(0, msg)
                elif msg["role"] == "assistant" and kept_user_count == self.MAX_USER_MESSAGES_FOR_INTENT + 1:
                    # 保留上一轮的 assistant（作为上下文）
                    filtered_result.insert(0, msg)
            result = filtered_result
        
        return result
    
    def _extract_last_user_text(self, messages: List[Dict[str, Any]]) -> str:
        """从消息列表中提取最后一条 user 消息的文本"""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                return self._extract_text(msg.get("content", ""))
        return ""
    
    def _extract_text(self, user_input) -> str:
        """
        从用户输入中提取文本
        
        Args:
            user_input: 用户输入（字符串或 Claude API 格式）
            
        Returns:
            提取的文本
        """
        if isinstance(user_input, str):
            return user_input
        
        if isinstance(user_input, list):
            # Claude API 格式: [{"type": "text", "text": "..."}]
            texts = []
            for block in user_input:
                if isinstance(block, dict) and block.get("type") == "text":
                    texts.append(block.get("text", ""))
            return " ".join(texts)
        
        return str(user_input)
    
    def _get_intent_prompt(self) -> str:
        """
        获取意图识别提示词
        
        优先从 InstancePromptCache 获取（用户配置优先）
        
        Returns:
            意图识别提示词
        """
        # 优先使用缓存的提示词
        if self._prompt_cache and self._prompt_cache.is_loaded:
            cached = self._prompt_cache.get_intent_prompt()
            if cached:
                logger.debug("📝 使用缓存的意图识别提示词")
                return cached
        
        # Fallback: 使用默认提示词
        from prompts.intent_recognition_prompt import get_intent_recognition_prompt
        return get_intent_recognition_prompt()
    
    async def _analyze_with_llm(
        self,
        messages: List[Dict[str, Any]]
    ) -> IntentResult:
        """
        使用 LLM 分析意图
        
        🆕 V6.3: 支持多层缓存（意图识别提示词 1h 缓存）
        
        Args:
            messages: 完整的消息列表
            
        Returns:
            IntentResult
        """
        from core.llm import Message
        
        try:
            # 🆕 V9.0: 用户问题聚焦型过滤（替代简单截断）
            # 规则：只保留用户消息 + 最后一条 assistant 摘要
            # 时延：< 0.1ms（纯 CPU）
            intent_messages = self._filter_for_intent(messages)
            
            if len(intent_messages) < len(messages):
                logger.info(
                    f"📝 意图分析: 过滤 {len(messages)} → {len(intent_messages)} 条 "
                    f"(user={sum(1 for m in intent_messages if m['role']=='user')})"
                )
            
            # 转换消息格式
            llm_messages = [
                Message(role=msg["role"], content=msg["content"])
                for msg in intent_messages
            ]
            
            # 🆕 V6.3: 使用多层缓存格式（意图识别提示词缓存，Claude 固定 5 分钟）
            # 意图识别提示词在运行期只读，启用缓存
            if self._prompt_cache and self._prompt_cache.is_loaded and self.llm.config.enable_caching:
                # 使用 InstancePromptCache 的缓存构建方法
                system_blocks = self._prompt_cache.get_cached_intent_blocks()
                if system_blocks:
                    logger.debug(f"🗂️ 意图识别使用缓存: 1 层 [5min TTL]")
                else:
                    # Fallback: 手动构建缓存格式
                    intent_prompt = self._get_intent_prompt()
                    system_blocks = [{
                        "type": "text",
                        "text": intent_prompt
                        # 🔧 不在这里添加 cache_control，由 claude.py 统一处理
                    }]
            else:
                # 未启用缓存或无 prompt_cache：使用字符串格式（向后兼容）
                intent_prompt = self._get_intent_prompt()
                system_blocks = intent_prompt  # 字符串格式，由 ClaudeLLMService 处理
            
            # 调用 LLM
            response = await self.llm.create_message_async(
                messages=llm_messages,
                system=system_blocks
            )
            
            # 解析响应
            last_user_text = self._extract_last_user_text(messages)
            return self._parse_llm_response(response.content, last_user_text)
            
        except Exception as e:
            logger.warning(f"LLM 意图分析失败: {e}，使用保守默认值")
            return self._get_conservative_default()
    
    def _parse_llm_response(
        self,
        content: str,
        input_text: str
    ) -> IntentResult:
        """
        解析 LLM 响应
        
        🆕 V7.8: 新增 LLM 语义建议字段解析
        
        Args:
            content: LLM 响应内容
            input_text: 原始用户输入
            
        Returns:
            IntentResult
        """
        # 默认值
        task_type = TaskType.OTHER
        complexity = Complexity.MEDIUM
        complexity_score = 5.0     # 🆕 V7.0: 默认复杂度评分
        needs_plan = True
        skip_memory_retrieval = False
        needs_multi_agent = False  # 🆕 V6.0: 默认不需要 Multi-Agent
        task_dependency_type = "sequential"  # 🆕 V9.2: 默认串行依赖
        is_follow_up = False       # 🆕 V6.1: 默认不是追问（视为新话题）
        
        # 🆕 V7.8: LLM 语义建议字段
        suggested_planning_depth = None
        requires_deep_reasoning = False
        tool_usage_hint = None
        
        # 🆕 V8.0: 执行策略
        execution_strategy = "rvr"  # 默认标准执行循环
        
        # 使用 JSON 提取器解析 LLM 响应
        parsed = extract_json(content)
        
        if parsed and isinstance(parsed, dict):
            # 解析 task_type
            task_type_str = parsed.get("task_type", "other")
            try:
                task_type = TaskType(task_type_str)
            except ValueError:
                task_type = TaskType.OTHER
            
            # 解析 complexity（等级）
            complexity_str = parsed.get("complexity", "medium")
            try:
                complexity = Complexity(complexity_str)
            except ValueError:
                complexity = Complexity.MEDIUM
            
            # 🆕 V7.0: 解析 complexity_score（0-10 评分）
            raw_score = parsed.get("complexity_score")
            if raw_score is not None:
                try:
                    complexity_score = float(raw_score)
                    # 限制在 0-10 范围内
                    complexity_score = max(0.0, min(10.0, complexity_score))
                except (ValueError, TypeError):
                    # 如果解析失败，根据 complexity 等级推断
                    complexity_score = self._infer_score_from_complexity(complexity)
            else:
                # LLM 未返回 score，根据 complexity 等级推断
                complexity_score = self._infer_score_from_complexity(complexity)
            
            # 解析 needs_plan
            needs_plan = parsed.get("needs_plan", True)
            
            # 解析 skip_memory_retrieval
            skip_memory_retrieval = parsed.get("skip_memory_retrieval", False)
            
            # 🆕 V6.0: 解析 needs_multi_agent
            needs_multi_agent = parsed.get("needs_multi_agent", False)
            
            # 🆕 V9.2: 解析 task_dependency_type（任务依赖类型）
            raw_dependency_type = parsed.get("task_dependency_type", "sequential")
            if raw_dependency_type in ("independent", "sequential", "mixed"):
                task_dependency_type = raw_dependency_type
            else:
                task_dependency_type = "sequential"  # 保守默认值
            
            # 🆕 V6.1: 解析 is_follow_up（上下文追问识别）
            is_follow_up = parsed.get("is_follow_up", False)
            
            # ==================== V7.8: LLM 语义建议 ====================
            # 这些字段供 AgentFactory 参数映射时优先使用
            
            # suggested_planning_depth（可选）
            raw_planning = parsed.get("suggested_planning_depth")
            if raw_planning in ("none", "minimal", "full"):
                suggested_planning_depth = raw_planning
            
            # requires_deep_reasoning
            requires_deep_reasoning = parsed.get("requires_deep_reasoning", False)
            
            # tool_usage_hint（可选）
            raw_tool_hint = parsed.get("tool_usage_hint")
            if raw_tool_hint in ("single", "sequential", "parallel"):
                tool_usage_hint = raw_tool_hint
            
            # 🆕 V8.0: execution_strategy（必填）
            raw_strategy = parsed.get("execution_strategy", "rvr")
            if raw_strategy in ("rvr", "rvr-b"):
                execution_strategy = raw_strategy
            else:
                execution_strategy = "rvr"  # 默认值
            
            logger.debug(
                f"   V7.8 语义建议: planning={suggested_planning_depth}, "
                f"deep_reasoning={requires_deep_reasoning}, "
                f"tools={tool_usage_hint}, "
                f"strategy={execution_strategy}"
            )
        else:
            logger.warning(f"无法从 LLM 响应中提取 JSON: {content[:100]}...")
        
        return IntentResult(
            task_type=task_type,
            complexity=complexity,
            complexity_score=complexity_score,
            needs_plan=needs_plan,
            skip_memory_retrieval=skip_memory_retrieval,
            needs_multi_agent=needs_multi_agent,
            task_dependency_type=task_dependency_type,  # 🆕 V9.2
            is_follow_up=is_follow_up,
            # 🆕 V7.8: LLM 语义建议
            suggested_planning_depth=suggested_planning_depth,
            requires_deep_reasoning=requires_deep_reasoning,
            tool_usage_hint=tool_usage_hint,
            # 🆕 V8.0: 执行策略
            execution_strategy=execution_strategy,
        )
    
    def _infer_score_from_complexity(self, complexity: Complexity) -> float:
        """
        🆕 V7.0: 根据复杂度等级推断评分（兼容旧 Prompt）
        
        Args:
            complexity: 复杂度等级
            
        Returns:
            float: 推断的复杂度评分
        """
        score_map = {
            Complexity.SIMPLE: 2.0,
            Complexity.MEDIUM: 5.0,
            Complexity.COMPLEX: 7.5,
        }
        return score_map.get(complexity, 5.0)
    
    def _get_conservative_default(self) -> IntentResult:
        """
        获取保守默认值
        
        V5.0 策略：不做关键词猜测，使用安全默认值
        🆕 V6.0: 默认不需要 Multi-Agent
        🆕 V6.1: 默认不是追问（视为新话题）
        🆕 V7.0: 默认复杂度评分 5.0
        🆕 V9.2: 默认任务依赖类型为 sequential
        
        Returns:
            IntentResult（保守默认值）
        """
        logger.info("⚠️ 使用保守默认值（LLM 不可用或禁用）")
        return IntentResult(
            task_type=TaskType.OTHER,
            complexity=Complexity.MEDIUM,
            complexity_score=5.0,     # 🆕 V7.0: 默认评分
            needs_plan=True,
            skip_memory_retrieval=False,
            needs_multi_agent=False,  # 🆕 V6.0: 默认不需要
            task_dependency_type="sequential",  # 🆕 V9.2: 默认串行
            is_follow_up=False,       # 🆕 V6.1: 默认不是追问
            keywords=[],
            confidence=0.3  # 低置信度，标记这是默认值
        )


def create_intent_analyzer(
    llm_service=None,
    enable_llm: bool = True,
    prompt_cache=None,  # InstancePromptCache
    semantic_cache=None,  # IntentSemanticCache
    enable_semantic_cache: bool = True  # 🆕 V9.3
) -> IntentAnalyzer:
    """
    创建意图分析器
    
    Args:
        llm_service: LLM 服务
        enable_llm: 是否启用 LLM 分析
        prompt_cache: InstancePromptCache（获取缓存的意图识别提示词）
        semantic_cache: IntentSemanticCache（语义缓存，可选）
        enable_semantic_cache: 是否启用语义缓存（默认 True）
        
    Returns:
        IntentAnalyzer 实例
    """
    return IntentAnalyzer(
        llm_service=llm_service,
        enable_llm=enable_llm,
        prompt_cache=prompt_cache,
        semantic_cache=semantic_cache,
        enable_semantic_cache=enable_semantic_cache
    )
