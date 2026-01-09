"""
IntentAnalyzer - 意图分析器

职责：
1. 分析用户输入的意图
2. 判断任务类型和复杂度
3. 决定是否需要规划
4. 推荐合适的提示词级别

设计原则：
- 单一职责：只做意图分析
- 快速响应：使用轻量级 LLM（Haiku）
- 可配置：支持自定义分析规则
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
    意图分析器
    
    使用轻量级 LLM 快速分析用户意图
    
    🆕 V4.6.2: 支持从 InstancePromptCache 获取意图识别提示词
    
    使用方式：
        analyzer = IntentAnalyzer(llm_service)
        result = await analyzer.analyze("帮我写一个 Python 脚本")
        print(result.task_type)  # TaskType.CODE_DEVELOPMENT
        
        # 🆕 V4.6.2: 使用缓存的意图提示词
        analyzer = IntentAnalyzer(llm_service, prompt_cache=cache)
    """
    
    def __init__(
        self,
        llm_service=None,
        enable_llm: bool = True,
        prompt_cache=None  # 🆕 V4.6.2: InstancePromptCache
    ):
        """
        初始化意图分析器
        
        Args:
            llm_service: LLM 服务（用于复杂意图分析）
            enable_llm: 是否启用 LLM 分析（False 则使用规则）
            prompt_cache: 🆕 V4.6.2 InstancePromptCache（获取缓存的意图识别提示词）
        """
        self.llm = llm_service
        self.enable_llm = enable_llm and llm_service is not None
        
        # 🆕 V4.6.2: 实例级提示词缓存
        self._prompt_cache = prompt_cache
        
        # 关键词映射规则（用于快速匹配）
        self._keyword_rules = self._init_keyword_rules()
    
    def _init_keyword_rules(self) -> Dict[TaskType, List[str]]:
        """初始化关键词规则"""
        return {
            TaskType.INFORMATION_QUERY: [
                "查询", "搜索", "查找", "什么是", "怎么", "如何",
                "search", "query", "find", "what is", "how to"
            ],
            TaskType.CONTENT_GENERATION: [
                "生成", "创建", "写", "制作", "ppt", "文档", "报告",
                "generate", "create", "write", "make", "document"
            ],
            TaskType.CODE_DEVELOPMENT: [
                "代码", "程序", "脚本", "函数", "bug", "修复",
                "code", "script", "function", "debug", "fix"
            ],
            TaskType.DATA_ANALYSIS: [
                "分析", "统计", "图表", "excel", "数据",
                "analyze", "statistics", "chart", "data"
            ],
            TaskType.CONVERSATION: [
                "你好", "谢谢", "聊聊", "说说",
                "hello", "hi", "thanks", "chat"
            ],
            TaskType.TASK_EXECUTION: [
                "执行", "运行", "启动", "部署",
                "execute", "run", "start", "deploy"
            ]
        }
    
    async def analyze(
        self,
        messages: List[Dict[str, Any]]
    ) -> IntentResult:
        """
        分析用户意图
        
        Args:
            messages: 完整的消息列表（包含上下文）
            
        Returns:
            IntentResult 意图分析结果
        """
        if self.enable_llm:
            # 使用 LLM 进行分析（传入完整上下文）
            result = await self._analyze_with_llm(messages)
        else:
            # 使用规则进行分析（只取最后一条 user 消息）
            last_user_text = self._extract_last_user_text(messages)
            result = self._analyze_with_rules(last_user_text)
        
        # 🆕 自动计算是否需要持久化（框架自动处理，用户透明）
        result.needs_persistence = self._should_persist(result)
        
        logger.info(
            f"🎯 意图分析结果: "
            f"type={result.task_type.value}, "
            f"complexity={result.complexity.value}, "
            f"needs_plan={result.needs_plan}, "
            f"needs_persistence={result.needs_persistence}, "
            f"skip_memory={result.skip_memory_retrieval}"  # 🆕 V4.6
        )
        
        return result
    
    def _should_persist(self, result: IntentResult) -> bool:
        """
        判断是否需要跨 Session 持久化
        
        🆕 V4.3 新增：自动检测任务复杂度，决定是否启用持久化
        
        触发条件（满足任一）：
        1. 复杂度为 COMPLEX
        2. 需要规划（needs_plan=True）
        3. 关键词数量 > 3（表示多步骤任务）
        4. 任务类型为 CONTENT_GENERATION 或 CODE_DEVELOPMENT
        
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
        
        # 条件 3: 多步骤任务（关键词多）
        if len(result.keywords) > 3:
            return True
        
        # 条件 4: 内容生成或代码开发任务（通常较长）
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
        
        🆕 V4.6.2: 优先从 InstancePromptCache 获取（用户配置优先）
        
        Returns:
            意图识别提示词
        """
        # 优先使用缓存的提示词（启动时已生成）
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
        使用 LLM 分析意图（传入完整上下文）
        
        🆕 V4.6.2: 优先使用缓存的意图识别提示词
        
        Args:
            messages: 完整的消息列表
            
        Returns:
            IntentResult
        """
        from core.llm import Message
        
        try:
            # 截断消息，保留最近的（意图分析只需要最近的上下文）
            # 简单策略：保留最近 30 条消息或全部（如果不足 30 条）
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
            
            # 🆕 V4.6.2: 使用缓存的意图识别提示词
            intent_prompt = self._get_intent_prompt()
            
            # 调用 LLM（传入截断后的对话历史）
            response = await self.llm.create_message_async(
                messages=llm_messages,
                system=intent_prompt
            )
            
            # 解析响应
            last_user_text = self._extract_last_user_text(messages)
            return self._parse_llm_response(response.content, last_user_text)
            
        except Exception as e:
            logger.warning(f"LLM 意图分析失败: {e}，降级到规则分析")
            last_user_text = self._extract_last_user_text(messages)
            return self._analyze_with_rules(last_user_text)
    
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
        skip_memory_retrieval = False  # 🆕 V4.6: 默认不跳过记忆检索
        
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
            
            # 🆕 V4.6: 解析 skip_memory_retrieval
            skip_memory_retrieval = parsed.get("skip_memory_retrieval", False)
        else:
            logger.warning(f"无法从 LLM 响应中提取 JSON: {content[:100]}...")
        
        # 提取关键词
        keywords = self._extract_keywords(input_text)
        
        return IntentResult(
            task_type=task_type,
            complexity=complexity,
            needs_plan=needs_plan,
            skip_memory_retrieval=skip_memory_retrieval,  # 🆕 V4.6
            keywords=keywords,
            raw_response=content
        )
    
    def _analyze_with_rules(self, input_text: str) -> IntentResult:
        """
        使用规则分析意图（无 LLM 时的降级方案）
        
        Args:
            input_text: 用户输入文本
            
        Returns:
            IntentResult
        """
        input_lower = input_text.lower()
        
        # 匹配任务类型
        task_type = TaskType.OTHER
        max_matches = 0
        
        for t_type, keywords in self._keyword_rules.items():
            matches = sum(1 for kw in keywords if kw in input_lower)
            if matches > max_matches:
                max_matches = matches
                task_type = t_type
        
        # 判断复杂度（基于输入长度和关键词）
        complexity = self._estimate_complexity(input_text)
        
        # 判断是否需要规划
        needs_plan = complexity != Complexity.SIMPLE
        
        # 提取关键词
        keywords = self._extract_keywords(input_text)
        
        return IntentResult(
            task_type=task_type,
            complexity=complexity,
            needs_plan=needs_plan,
            keywords=keywords,
            confidence=0.7  # 规则分析置信度较低
        )
    
    def _estimate_complexity(self, input_text: str) -> Complexity:
        """
        估算任务复杂度
        
        Args:
            input_text: 用户输入
            
        Returns:
            Complexity
        """
        # 简单规则：
        # - 短输入（<50字）且无复杂关键词 → SIMPLE
        # - 中等输入 或 有一般关键词 → MEDIUM
        # - 长输入（>200字）或 有复杂关键词 → COMPLEX
        
        length = len(input_text)
        input_lower = input_text.lower()
        
        complex_keywords = ["ppt", "报告", "分析", "开发", "项目", "系统"]
        has_complex = any(kw in input_lower for kw in complex_keywords)
        
        if has_complex or length > 200:
            return Complexity.COMPLEX
        elif length < 50:
            return Complexity.SIMPLE
        else:
            return Complexity.MEDIUM
    
    def _extract_keywords(self, input_text: str) -> List[str]:
        """
        从输入中提取关键词
        
        Args:
            input_text: 用户输入
            
        Returns:
            关键词列表
        """
        keywords = []
        input_lower = input_text.lower()
        
        # 检查所有已知关键词
        all_keywords = []
        for kw_list in self._keyword_rules.values():
            all_keywords.extend(kw_list)
        
        for kw in all_keywords:
            if kw in input_lower:
                keywords.append(kw)
        
        return list(set(keywords))  # 去重


def create_intent_analyzer(
    llm_service=None,
    enable_llm: bool = True,
    prompt_cache=None  # 🆕 V4.6.2: InstancePromptCache
) -> IntentAnalyzer:
    """
    创建意图分析器
    
    🆕 V4.6.2: 支持 InstancePromptCache
    
    Args:
        llm_service: LLM 服务
        enable_llm: 是否启用 LLM 分析
        prompt_cache: 🆕 V4.6.2 InstancePromptCache（获取缓存的意图识别提示词）
        
    Returns:
        IntentAnalyzer 实例
    """
    return IntentAnalyzer(
        llm_service=llm_service,
        enable_llm=enable_llm,
        prompt_cache=prompt_cache
    )

