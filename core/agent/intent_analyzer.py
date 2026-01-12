"""
V5.0 IntentAnalyzer - 意图分析器

核心理念：
- 意图分析通过 LLM 语义理解完成
- 不使用关键词匹配规则
- 保守的 fallback（OTHER），不做关键词猜测

设计原则：
- 运营无需配置任何关键词规则
- LLM 学习 Few-Shot 示例进行语义泛化推理
- 代码只做调用和解析，不做规则判断
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
            f"needs_multi_agent={result.needs_multi_agent}"
        )
        
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
            
            # 使用缓存的意图识别提示词
            intent_prompt = self._get_intent_prompt()
            
            # 调用 LLM
            response = await self.llm.create_message_async(
                messages=llm_messages,
                system=intent_prompt
            )
            
            # 解析响应内容（处理 Claude API 的 content blocks 格式）
            response_text = response.content
            if isinstance(response_text, list):
                # Claude API 格式: [{"type": "text", "text": "..."}]
                text_parts = []
                for block in response_text:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif hasattr(block, "text"):
                        text_parts.append(block.text)
                response_text = "".join(text_parts)
            
            last_user_text = self._extract_last_user_text(messages)
            return self._parse_llm_response(response_text, last_user_text)
            
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
        else:
            logger.warning(f"无法从 LLM 响应中提取 JSON: {content[:100]}...")
        
        return IntentResult(
            task_type=task_type,
            complexity=complexity,
            needs_plan=needs_plan,
            skip_memory_retrieval=skip_memory_retrieval,
            needs_multi_agent=needs_multi_agent,
            keywords=[],  # V5.0: 不再提取关键词
            raw_response=content
        )
    
    def _get_conservative_default(self) -> IntentResult:
        """
        获取保守默认值
        
        V5.0 策略：不做关键词猜测，使用安全默认值
        🆕 V6.0: 默认不需要 Multi-Agent
        
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
