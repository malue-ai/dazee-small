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
from typing import Dict, Any, Optional, List

# 2. 第三方库（无）

# 3. 本地模块
from core.agent.types import (
    IntentResult,
    TaskType,
    Complexity,
)
from core.llm import Message
from prompts.intent_recognition_prompt import get_intent_recognition_prompt
from utils.json_utils import extract_json
from logger import get_logger

logger = get_logger(__name__)


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
        messages: List[Dict[str, Any]],
        tracker=None  # 🆕 共享 Tracker（可选，用于记录 LLM 消耗）
    ) -> IntentResult:
        """
        分析用户意图
        
        V5.0 策略：LLM-First，无关键词匹配
        
        Args:
            messages: 完整的消息列表（包含上下文）
            tracker: EnhancedUsageTracker 实例（可选，用于计费追踪）
            
        Returns:
            IntentResult 意图分析结果
        """
        if self.enable_llm:
            # 使用 LLM 进行分析（传递 tracker）
            result = await self._analyze_with_llm(messages, tracker=tracker)
        else:
            # 使用保守默认值（不做关键词匹配）
            result = self._get_conservative_default()
        
        # 自动计算是否需要持久化
        result.needs_persistence = self._should_persist(result)
        
        logger.info(
            f"🎯 意图分析结果: "
            f"type={result.task_type.value}, "
            f"complexity={result.complexity.value}, "
            f"score={result.complexity_score:.1f}, "  # 🆕 V7.0
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
        previous_result: Optional[IntentResult] = None,
        tracker=None  # 🆕 共享 Tracker（可选）
    ) -> IntentResult:
        """
        🆕 V6.1 带上下文的意图分析（追问场景优化）
        
        如果检测到追问（is_follow_up=True）且有上轮结果，复用上轮的 task_type，
        避免重复完整分析，提升性能。
        
        Args:
            messages: 完整的消息列表（包含上下文）
            previous_result: 上一轮的意图分析结果（用于追问场景复用）
            tracker: EnhancedUsageTracker 实例（可选，用于计费追踪）
            
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
        # 1. 执行正常分析（传递 tracker）
        result = await self.analyze(messages, tracker=tracker)
        
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
        return get_intent_recognition_prompt()
    
    async def _analyze_with_llm(
        self,
        messages: List[Dict[str, Any]],
        tracker=None  # 🆕 共享 Tracker（可选）
    ) -> IntentResult:
        """
        使用 LLM 分析意图
        
        🆕 V6.3: 支持多层缓存（意图识别提示词 1h 缓存）
        
        Args:
            messages: 完整的消息列表
            tracker: EnhancedUsageTracker 实例（可选，用于计费追踪）
            
        Returns:
            IntentResult
        """
        try:
            # 🔧 V7.6.2: 只保留最近 3 轮对话（6 条消息），避免 LLM 进入对话模式
            # 太长的历史会导致 LLM 忽略 system prompt 继续对话
            max_messages_for_intent = 6  # 3 轮对话 = 6 条消息
            truncated_messages = messages[-max_messages_for_intent:] if len(messages) > max_messages_for_intent else messages
            
            if len(truncated_messages) < len(messages):
                logger.info(
                    f"📝 意图分析: 截断消息 {len(messages)} → {len(truncated_messages)} 条（最近3轮）"
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
                        "text": intent_prompt
                        # 🔧 不在这里添加 cache_control，由 claude.py 统一处理
                    }]
            else:
                # 未启用缓存或无 prompt_cache：使用字符串格式（向后兼容）
                intent_prompt = self._get_intent_prompt()
                system_blocks = intent_prompt  # 字符串格式，由 ClaudeLLMService 处理
            
            # 🔧 DEBUG: 打印意图识别的输入
            logger.info(f"📤 [Intent LLM] 输入消息数: {len(llm_messages)}")
            for i, msg in enumerate(llm_messages[-3:]):  # 只打印最后3条
                content_preview = str(msg.content)[:200] if msg.content else ""
                logger.info(f"📤 [Intent LLM] 消息[{i}] role={msg.role}: {content_preview}...")
            
            # 打印 system prompt 信息（包含内容预览）
            if isinstance(system_blocks, str):
                logger.info(f"📤 [Intent LLM] System Prompt 长度: {len(system_blocks)} 字符")
                logger.info(f"📤 [Intent LLM] System Prompt 预览: {system_blocks[:500]}...")
            elif isinstance(system_blocks, list) and system_blocks:
                total_len = sum(len(b.get("text", "")) for b in system_blocks if isinstance(b, dict))
                logger.info(f"📤 [Intent LLM] System Blocks 数量: {len(system_blocks)}, 总长度: {total_len} 字符")
                if system_blocks and isinstance(system_blocks[0], dict):
                    first_text = system_blocks[0].get("text", "")[:500]
                    logger.info(f"📤 [Intent LLM] System Block[0] 预览: {first_text}...")
            else:
                logger.warning(f"⚠️ [Intent LLM] System Prompt 为空或无效: {type(system_blocks)}, 值: {system_blocks}")
            
            # 调用 LLM
            response = await self.llm.create_message_async(
                messages=llm_messages,
                system=system_blocks
            )
            
            # 🆕 共享 Tracker 方案：记录意图识别的 LLM 消耗
            if tracker:
                tracker.record_call(
                    llm_response=response,
                    model=self.llm.config.model,  # 🔧 修复：使用 config.model 而不是 llm.model
                    purpose="intent_analysis"
                )
                logger.debug(f"💰 意图识别计费已记录到共享 Tracker: tracker_id={id(tracker)}")
            
            # 🔧 DEBUG: 打印 LLM 原始返回
            logger.info(f"📥 [Intent LLM] 原始返回内容:\n{response.content}")
            
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
        
        🆕 V7.5: 优先解析 intent_id/intent_name，并映射到 TaskType
        
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
        is_follow_up = False       # 🆕 V6.1: 默认不是追问（视为新话题）
        # 🆕 V7.5: 新增字段
        intent_id = None
        intent_name = None
        platform = None
        
        # 使用 JSON 提取器解析 LLM 响应
        parsed = extract_json(content)
        
        # 🔧 DEBUG: 打印 LLM 原始响应和解析结果
        logger.info(f"📝 LLM 意图响应原文: {content[:500]}")
        logger.info(f"📝 JSON 解析结果: {parsed}")
        logger.info(f"📝 parsed 类型: {type(parsed)}, 是否为 dict: {isinstance(parsed, dict)}")
        
        if parsed and isinstance(parsed, dict):
            # 🆕 V7.5: 优先解析 intent_id 和 intent_name
            intent_id = parsed.get("intent_id")
            intent_name = parsed.get("intent_name")
            platform = parsed.get("platform")  # 可选字段
            
            logger.info(f"📝 解析到: intent_id={intent_id}, intent_name={intent_name}, platform={platform}")
            
            # 🆕 V7.5: 根据 intent_id 映射到 TaskType（兼容现有逻辑）
            if intent_id is not None:
                task_type = self._map_intent_id_to_task_type(intent_id)
                logger.info(f"📝 intent_id={intent_id} 映射到 task_type={task_type.value}")
                # 🔧 V7.6.2: 如果 LLM 返回了 intent_id 但没返回 intent_name，根据 intent_id 生成
                if intent_name is None:
                    intent_name = self._get_intent_name_by_id(intent_id)
                    logger.info(f"📝 intent_name 为空，根据 intent_id 生成: {intent_name}")
            else:
                # 兼容旧格式：直接解析 task_type
                task_type_str = parsed.get("task_type", "other")
                logger.info(f"📝 未找到 intent_id，使用旧格式: task_type_str={task_type_str}")
                
                # 🆕 V7.6: 兼容 LLM 返回的 "code_task" → 枚举中的 "code_development"
                task_type_mapping = {
                    "code_task": "code_development",  # prompt 用 code_task，枚举是 code_development
                }
                task_type_str = task_type_mapping.get(task_type_str, task_type_str)
                
                try:
                    task_type = TaskType(task_type_str)
                except ValueError:
                    task_type = TaskType.OTHER
                
                logger.info(f"📝 task_type_str={task_type_str} 转换为 task_type={task_type.value}")
                
                # 🆕 V7.6: 当没有 intent_id 时，根据 task_type 生成默认值
                intent_id, intent_name = self._map_task_type_to_intent(task_type)
                logger.info(f"📝 反向映射: task_type={task_type.value} -> intent_id={intent_id}, intent_name={intent_name}")
            
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
            
            # 🆕 V6.1: 解析 is_follow_up（上下文追问识别）
            is_follow_up = parsed.get("is_follow_up", False)
        else:
            logger.warning(f"无法从 LLM 响应中提取 JSON: {content[:100]}...")
            # 🔧 V7.6.2: JSON 解析失败时设置默认 intent_id/intent_name，避免返回 null
            intent_id = 3              # 默认综合咨询
            intent_name = "综合咨询"
        
        return IntentResult(
            task_type=task_type,
            complexity=complexity,
            complexity_score=complexity_score,  # 🆕 V7.0
            needs_plan=needs_plan,
            intent_id=intent_id,        # 🆕 V7.5
            intent_name=intent_name,    # 🆕 V7.5
            platform=platform,          # 🆕 V7.5
            skip_memory_retrieval=skip_memory_retrieval,
            needs_multi_agent=needs_multi_agent,
            is_follow_up=is_follow_up,  # 🆕 V6.1
            keywords=[],  # V5.0: 不再提取关键词
            raw_response=content
        )
    
    def _map_intent_id_to_task_type(self, intent_id: int) -> TaskType:
        """
        🆕 V7.5: 将 intent_id 映射到 TaskType（兼容现有逻辑）
        
        映射规则：
        - intent_id=1 (系统搭建) -> TaskType.TASK_EXECUTION
        - intent_id=2 (BI智能问数) -> TaskType.DATA_ANALYSIS
        - intent_id=3 (综合咨询) -> TaskType.OTHER
        
        Args:
            intent_id: 意图 ID
            
        Returns:
            TaskType 枚举值
        """
        mapping = {
            1: TaskType.TASK_EXECUTION,   # 系统搭建
            2: TaskType.DATA_ANALYSIS,    # BI智能问数
            3: TaskType.OTHER,            # 综合咨询
        }
        return mapping.get(intent_id, TaskType.OTHER)
    
    def _map_task_type_to_intent(self, task_type: TaskType) -> tuple[int, str]:
        """
        🆕 V7.6: 根据 TaskType 生成默认的 intent_id 和 intent_name
        
        当 LLM 返回的是旧格式（task_type）而不是新格式（intent_id）时，
        根据 task_type 生成对应的 intent_id 和 intent_name，保持前端显示一致。
        
        Args:
            task_type: 任务类型枚举
            
        Returns:
            tuple[int, str]: (intent_id, intent_name)
        """
        mapping = {
            TaskType.TASK_EXECUTION: (1, "系统搭建"),
            TaskType.DATA_ANALYSIS: (2, "数据分析"),
            TaskType.INFORMATION_QUERY: (4, "信息查询"),
            TaskType.CONTENT_GENERATION: (5, "内容生成"),
            TaskType.CODE_DEVELOPMENT: (6, "代码任务"),  # 🆕 V7.6: 修正为 CODE_DEVELOPMENT
            TaskType.OTHER: (3, "综合咨询"),
        }
        return mapping.get(task_type, (3, "综合咨询"))
    
    def _get_intent_name_by_id(self, intent_id: int) -> str:
        """
        🆕 V7.6.2: 根据 intent_id 获取 intent_name
        
        当 LLM 返回了 intent_id 但没有返回 intent_name 时使用
        
        Args:
            intent_id: 意图 ID
            
        Returns:
            str: 意图名称
        """
        mapping = {
            1: "系统搭建",
            2: "BI智能问数",
            3: "综合咨询",
            4: "信息查询",
            5: "内容生成",
            6: "代码任务",
        }
        return mapping.get(intent_id, "综合咨询")
    
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
        🆕 V7.5: 默认 intent_id=3（综合咨询）
        
        Returns:
            IntentResult（保守默认值）
        """
        logger.info("⚠️ 使用保守默认值（LLM 不可用或禁用）")
        return IntentResult(
            task_type=TaskType.OTHER,
            complexity=Complexity.MEDIUM,
            complexity_score=5.0,     # 🆕 V7.0: 默认评分
            needs_plan=True,
            intent_id=3,              # 🆕 V7.5: 默认综合咨询
            intent_name="综合咨询",    # 🆕 V7.5
            platform=None,            # 🆕 V7.5
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
