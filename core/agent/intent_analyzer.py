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
import json
import logging
import re
from typing import Dict, Any, Optional, List

# 2. 第三方库（无）

# 3. 本地模块
from core.agent.types import (
    IntentResult,
    TaskType,
    Complexity,
    PromptLevel,
    ExecutionConfig
)

logger = logging.getLogger(__name__)


class IntentAnalyzer:
    """
    意图分析器
    
    使用轻量级 LLM 快速分析用户意图
    
    使用方式：
        analyzer = IntentAnalyzer(llm_service)
        result = await analyzer.analyze("帮我写一个 Python 脚本")
        print(result.task_type)  # TaskType.CODE_DEVELOPMENT
    """
    
    def __init__(
        self,
        llm_service=None,
        enable_llm: bool = True
    ):
        """
        初始化意图分析器
        
        Args:
            llm_service: LLM 服务（用于复杂意图分析）
            enable_llm: 是否启用 LLM 分析（False 则使用规则）
        """
        self.llm = llm_service
        self.enable_llm = enable_llm and llm_service is not None
        
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
        user_input: str,
        context: Optional[Dict[str, Any]] = None
    ) -> IntentResult:
        """
        分析用户意图
        
        Args:
            user_input: 用户输入
            context: 上下文信息（可选）
            
        Returns:
            IntentResult 意图分析结果
        """
        # 提取用户输入文本
        input_text = self._extract_text(user_input)
        
        if self.enable_llm:
            # 使用 LLM 进行分析
            result = await self._analyze_with_llm(input_text, context)
        else:
            # 使用规则进行分析
            result = self._analyze_with_rules(input_text)
        
        logger.info(
            f"🎯 意图分析结果: "
            f"type={result.task_type.value}, "
            f"complexity={result.complexity.value}, "
            f"needs_plan={result.needs_plan}"
        )
        
        return result
    
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
    
    async def _analyze_with_llm(
        self,
        input_text: str,
        context: Optional[Dict[str, Any]] = None
    ) -> IntentResult:
        """
        使用 LLM 分析意图
        
        Args:
            input_text: 用户输入文本
            context: 上下文
            
        Returns:
            IntentResult
        """
        from prompts.intent_recognition_prompt import get_intent_recognition_prompt
        from core.llm import Message
        
        try:
            # 调用 LLM
            response = await self.llm.create_message_async(
                messages=[Message(role="user", content=input_text)],
                system=get_intent_recognition_prompt()
            )
            
            # 解析响应
            return self._parse_llm_response(response.content, input_text)
            
        except Exception as e:
            logger.warning(f"LLM 意图分析失败: {e}，降级到规则分析")
            return self._analyze_with_rules(input_text)
    
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
        
        try:
            # 尝试提取 JSON
            json_match = re.search(r'\{[^}]+\}', content, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                
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
        
        except Exception as e:
            logger.warning(f"解析 LLM 响应失败: {e}")
        
        # 根据复杂度推导 prompt_level
        prompt_level = self._complexity_to_prompt_level(complexity)
        
        # 提取关键词
        keywords = self._extract_keywords(input_text)
        
        return IntentResult(
            task_type=task_type,
            complexity=complexity,
            needs_plan=needs_plan,
            prompt_level=prompt_level,
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
        
        # 推导 prompt_level
        prompt_level = self._complexity_to_prompt_level(complexity)
        
        # 提取关键词
        keywords = self._extract_keywords(input_text)
        
        return IntentResult(
            task_type=task_type,
            complexity=complexity,
            needs_plan=needs_plan,
            prompt_level=prompt_level,
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
    
    def _complexity_to_prompt_level(self, complexity: Complexity) -> PromptLevel:
        """
        复杂度转换为提示词级别
        
        Args:
            complexity: 复杂度
            
        Returns:
            PromptLevel
        """
        mapping = {
            Complexity.SIMPLE: PromptLevel.SIMPLE,
            Complexity.MEDIUM: PromptLevel.STANDARD,
            Complexity.COMPLEX: PromptLevel.FULL
        }
        return mapping.get(complexity, PromptLevel.STANDARD)
    
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
    
    def get_execution_config(
        self,
        intent: IntentResult
    ) -> ExecutionConfig:
        """
        根据意图生成执行配置
        
        Args:
            intent: 意图分析结果
            
        Returns:
            ExecutionConfig
        """
        from prompts.simple_prompt import get_simple_prompt
        from prompts.standard_prompt import get_standard_prompt
        from prompts.universal_agent_prompt import get_universal_agent_prompt
        
        if intent.prompt_level == PromptLevel.SIMPLE:
            return ExecutionConfig(
                system_prompt=get_simple_prompt(),
                prompt_name="simple_prompt",
                enable_thinking=False
            )
        elif intent.prompt_level == PromptLevel.STANDARD:
            return ExecutionConfig(
                system_prompt=get_standard_prompt(),
                prompt_name="standard_prompt",
                enable_thinking=True
            )
        else:  # FULL
            return ExecutionConfig(
                system_prompt=get_universal_agent_prompt(),
                prompt_name="full_prompt",
                enable_thinking=True
            )


def create_intent_analyzer(
    llm_service=None,
    enable_llm: bool = True
) -> IntentAnalyzer:
    """
    创建意图分析器
    
    Args:
        llm_service: LLM 服务
        enable_llm: 是否启用 LLM 分析
        
    Returns:
        IntentAnalyzer 实例
    """
    return IntentAnalyzer(
        llm_service=llm_service,
        enable_llm=enable_llm
    )

