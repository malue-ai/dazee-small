"""
V5.0 IntentAnalyzer - 意图分析器

🆕 V6.1: 新增上下文感知（追问识别）

核心理念：
- 意图分析通过 LLM 语义理解完成
- 不使用关键词匹配规则
- 保守的 fallback（OTHER），不做关键词猜测
- 识别追问/新话题，避免上下文脱节

设计原则：
- 运营无需配置任何关键词规则
- LLM 学习 Few-Shot 示例进行语义泛化推理
- 代码只做调用和解析，不做规则判断
- 运营配置提示词 + 高质量默认模板 → 场景化意图识别
"""

# 1. 标准库
import logging
from typing import Dict, Any, Optional, List

# 3. 本地模块
from utils.json_utils import extract_json
from core.agent.types import (
    IntentResult,
    TaskType,
    Complexity,
)

logger = logging.getLogger(__name__)


class IntentAnalyzer:
    """
    V5.0 意图分析器
    
    策略：LLM-First 语义推理
    - 直接使用 LLM 进行语义理解
    - 不使用关键词匹配
    - 保守的 fallback（OTHER）
    
    使用方式：
        analyzer = IntentAnalyzer(llm_service)
        result = await analyzer.analyze([{"role": "user", "content": "..."}])
        print(result.task_type)
    """
    
    def __init__(
        self,
        llm_service=None,
        enable_llm: bool = True,
        prompt_cache=None  # InstancePromptCache
    ):
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
    
    async def analyze(
        self,
        messages: List[Dict[str, Any]]
    ) -> IntentResult:
        """
        分析用户意图
        
        V5.0 策略：LLM-First，无关键词匹配
        
        Args:
            messages: 完整的消息列表（包含上下文）
            
        Returns:
            IntentResult 意图分析结果
        """
        if self.enable_llm:
            # 使用 LLM 进行分析
            result = await self._analyze_with_llm(messages)
        else:
            # 使用保守默认值（不做关键词匹配）
            result = self._get_conservative_default()
        
        # 自动计算是否需要持久化
        result.needs_persistence = self._should_persist(result)
        
        logger.info(
            f"🎯 意图分析结果: "
            f"type={result.task_type.value}, "
            f"complexity={result.complexity.value}, "
            f"needs_plan={result.needs_plan}, "
            f"needs_persistence={result.needs_persistence}, "
            f"skip_memory={result.skip_memory_retrieval}, "
            f"needs_multi_agent={result.needs_multi_agent}, "
            f"is_follow_up={result.is_follow_up}"
        )
        
        return result
    
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
            # 截断消息，保留最近的
            max_messages_for_intent = 30
            truncated_messages = messages[-max_messages_for_intent:] if len(messages) > max_messages_for_intent else messages
            
            if len(truncated_messages) < len(messages):
                logger.info(
                    f"📝 意图分析: 截断消息 {len(messages)} → {len(truncated_messages)} 条"
                )
            
            # 转换消息格式
            llm_messages = [
                Message(role=msg["role"], content=msg["content"])
                for msg in truncated_messages
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
                        "text": intent_prompt,
                        "cache_control": {"type": "ephemeral"}
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
        
        Args:
            content: LLM 响应内容
            input_text: 原始用户输入
            
        Returns:
            IntentResult
        """
        # 默认值
        task_type = TaskType.OTHER
        complexity = Complexity.MEDIUM
        needs_plan = True
        skip_memory_retrieval = False
        needs_multi_agent = False  # 🆕 V6.0: 默认不需要 Multi-Agent
        is_follow_up = False       # 🆕 V6.1: 默认不是追问（视为新话题）
        
        # 使用 JSON 提取器解析 LLM 响应
        parsed = extract_json(content)
        
        if parsed and isinstance(parsed, dict):
            # 解析 task_type
            task_type_str = parsed.get("task_type", "other")
            try:
                task_type = TaskType(task_type_str)
            except ValueError:
                task_type = TaskType.OTHER
            
            # 解析 complexity
            complexity_str = parsed.get("complexity", "medium")
            try:
                complexity = Complexity(complexity_str)
            except ValueError:
                complexity = Complexity.MEDIUM
            
            # 解析 needs_plan
            needs_plan = parsed.get("needs_plan", True)
            
            # 解析 skip_memory_retrieval
            skip_memory_retrieval = parsed.get("skip_memory_retrieval", False)
            
            # 🆕 V6.0: 解析 needs_multi_agent
            needs_multi_agent = parsed.get("needs_multi_agent", False)
            
            # 🆕 V6.1: 解析 is_follow_up（上下文追问识别）
            is_follow_up = parsed.get("is_follow_up", False)
        else:
            logger.warning(f"无法从 LLM 响应中提取 JSON: {content[:100]}...")
        
        return IntentResult(
            task_type=task_type,
            complexity=complexity,
            needs_plan=needs_plan,
            skip_memory_retrieval=skip_memory_retrieval,
            needs_multi_agent=needs_multi_agent,
            is_follow_up=is_follow_up,  # 🆕 V6.1
            keywords=[],  # V5.0: 不再提取关键词
            raw_response=content
        )
    
    def _get_conservative_default(self) -> IntentResult:
        """
        获取保守默认值
        
        V5.0 策略：不做关键词猜测，使用安全默认值
        🆕 V6.0: 默认不需要 Multi-Agent
        🆕 V6.1: 默认不是追问（视为新话题）
        
        Returns:
            IntentResult（保守默认值）
        """
        logger.info("⚠️ 使用保守默认值（LLM 不可用或禁用）")
        return IntentResult(
            task_type=TaskType.OTHER,
            complexity=Complexity.MEDIUM,
            needs_plan=True,
            skip_memory_retrieval=False,
            needs_multi_agent=False,  # 🆕 V6.0: 默认不需要
            is_follow_up=False,       # 🆕 V6.1: 默认不是追问
            keywords=[],
            confidence=0.3  # 低置信度，标记这是默认值
        )


def create_intent_analyzer(
    llm_service=None,
    enable_llm: bool = True,
    prompt_cache=None  # InstancePromptCache
) -> IntentAnalyzer:
    """
    创建意图分析器
    
    Args:
        llm_service: LLM 服务
        enable_llm: 是否启用 LLM 分析
        prompt_cache: InstancePromptCache（获取缓存的意图识别提示词）
        
    Returns:
        IntentAnalyzer 实例
    """
    return IntentAnalyzer(
        llm_service=llm_service,
        enable_llm=enable_llm,
        prompt_cache=prompt_cache
    )
