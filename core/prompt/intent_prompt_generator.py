"""
动态意图识别提示词生成器 - IntentPromptGenerator

🆕 V4.6.2: 从 PromptSchema 动态生成意图识别提示词

设计原则：
1. 用户配置优先：运营在 prompt.md 中定义的意图规则
2. 高质量默认：未配置时使用精心设计的 few-shot 示例
3. 一次性生成：启动时生成，运行时直接使用

生成的提示词用于 IntentAnalyzer (Haiku 4.5):
- 任务类型分类
- 复杂度判断 + complexity_score
- 是否需要规划
- 是否跳过记忆检索
- 是否需要多智能体
- 是否为追问
"""

# 1. 标准库
from typing import Optional, List, Dict, Any

# 2. 第三方库（无）

# 3. 本地模块
from core.prompt.prompt_layer import TaskComplexity
from logger import get_logger
from prompts.intent_recognition_prompt import (
    INTENT_PROMPT_HEADER,
    INTENT_PROMPT_TASK_TYPES,
    INTENT_PROMPT_COMPLEXITY,
    INTENT_PROMPT_CONTEXT_AWARENESS,
    INTENT_PROMPT_MEMORY,
    INTENT_PROMPT_MULTI_AGENT,
    INTENT_PROMPT_FOOTER,
)

logger = get_logger("intent_prompt_generator")


# ============================================================
# 高质量默认提示词组件
# ============================================================

# 默认规则直接复用统一定义，避免版本不一致
DEFAULT_TASK_TYPES = INTENT_PROMPT_TASK_TYPES
DEFAULT_COMPLEXITY_RULES = INTENT_PROMPT_COMPLEXITY
DEFAULT_CONTEXT_RULES = INTENT_PROMPT_CONTEXT_AWARENESS
DEFAULT_MEMORY_RULES = INTENT_PROMPT_MEMORY
DEFAULT_MULTI_AGENT_RULES = INTENT_PROMPT_MULTI_AGENT


# ============================================================
# IntentPromptGenerator
# ============================================================

class IntentPromptGenerator:
    """
    从 PromptSchema 动态生成意图识别提示词
    
    原则：用户配置优先，缺失用高质量默认
    
    使用方式：
    ```python
    # 从 PromptSchema 生成（用户配置优先）
    intent_prompt = IntentPromptGenerator.generate(prompt_schema)
    
    # 获取高质量默认
    intent_prompt = IntentPromptGenerator.get_default()
    ```
    """
    
    @classmethod
    def generate(cls, schema) -> str:
        """
        根据 PromptSchema 生成意图识别提示词
        
        提取内容：
        1. 意图分类规则（如果运营定义了）
        2. 复杂度判断规则（如果运营定义了）
        3. 特殊关键词映射
        
        Args:
            schema: PromptSchema 对象
            
        Returns:
            动态生成的意图识别提示词
        """
        parts = [INTENT_PROMPT_HEADER]
        
        # 1. 任务类型定义
        task_types_section = cls._generate_task_types(schema)
        parts.append(task_types_section)
        
        # 2. 复杂度规则
        complexity_section = cls._generate_complexity_rules(schema)
        parts.append(complexity_section)
        
        # 3. 上下文感知规则
        context_section = cls._generate_context_rules(schema)
        parts.append(context_section)
        
        # 4. 记忆检索规则
        memory_section = cls._generate_memory_rules(schema)
        parts.append(memory_section)
        
        # 5. 多智能体判断规则
        multi_agent_section = cls._generate_multi_agent_rules(schema)
        parts.append(multi_agent_section)
        
        # 6. 尾部
        parts.append(INTENT_PROMPT_FOOTER)
        
        result = "\n".join(parts)
        logger.debug(f"生成意图识别提示词: {len(result)} 字符")
        
        return result
    
    @classmethod
    def _generate_task_types(cls, schema) -> str:
        """
        生成任务类型定义
        
        优先使用用户定义，否则使用默认
        """
        # 检查 schema 中是否有自定义意图类型
        if schema and schema.intent_types:
            logger.info(f"   使用用户定义的意图类型: {len(schema.intent_types)} 个")
            return cls._format_custom_task_types(schema.intent_types)
        
        # 使用默认
        return DEFAULT_TASK_TYPES
    
    @classmethod
    def _format_custom_task_types(cls, intent_types: List[Dict[str, Any]]) -> str:
        """格式化自定义任务类型"""
        lines = ["\n## Classification Rules\n\n### Task Type"]
        
        for intent in intent_types:
            name = intent.get("name", "unknown")
            keywords = intent.get("keywords", [])
            examples = intent.get("examples", keywords[:3])
            
            lines.append(f"- **{name}**: {', '.join(keywords[:5])}")
            if examples:
                lines.append(f"  - Examples: {', '.join(examples[:3])}")
        
        # 添加 other 类型
        lines.append("- **other**: Everything else")
        
        return "\n".join(lines)
    
    @classmethod
    def _generate_complexity_rules(cls, schema) -> str:
        """
        生成复杂度规则
        
        优先使用用户定义的复杂度关键词
        """
        if not schema or not schema.complexity_keywords:
            return DEFAULT_COMPLEXITY_RULES
        
        # 检查是否有足够的自定义配置
        has_custom = any(
            keywords for keywords in schema.complexity_keywords.values()
        )
        
        if not has_custom:
            return DEFAULT_COMPLEXITY_RULES
        
        logger.info("   使用用户定义的复杂度规则")
        
        # 生成自定义复杂度规则
        lines = ["\n### Complexity"]
        
        complexity_map = {
            TaskComplexity.SIMPLE: ("simple", "Single-step, direct answer"),
            TaskComplexity.MEDIUM: ("medium", "2-4 steps, straightforward workflow"),
            TaskComplexity.COMPLEX: ("complex", "5+ steps, requires planning"),
        }
        
        for complexity, (name, default_desc) in complexity_map.items():
            keywords = schema.complexity_keywords.get(complexity, [])
            if keywords:
                lines.append(f"- **{name}**: {', '.join(keywords[:5])}")
            else:
                lines.append(f"- **{name}**: {default_desc}")
        
        lines.append("""
### Needs Plan
- **true**: complexity is medium or complex
- **false**: complexity is simple""")
        
        return "\n".join(lines)
    
    @classmethod
    def _generate_memory_rules(cls, schema) -> str:
        """
        生成记忆检索规则
        
        使用 few-shot 示例驱动（而非硬编码规则）
        """
        # 目前使用默认的 few-shot 示例
        # 未来可以根据 schema 中的配置扩展
        return DEFAULT_MEMORY_RULES

    @classmethod
    def _generate_context_rules(cls, schema) -> str:
        """
        生成上下文感知规则（追问识别）
        
        目前使用默认规则，后续可由 schema 扩展
        """
        return DEFAULT_CONTEXT_RULES

    @classmethod
    def _generate_multi_agent_rules(cls, schema) -> str:
        """
        生成多智能体判断规则
        
        目前使用默认规则，后续可由 schema 扩展
        """
        return DEFAULT_MULTI_AGENT_RULES
    
    @classmethod
    def get_default(cls) -> str:
        """
        获取高质量默认提示词
        
        当运营没有配置意图规则时使用
        """
        return "\n".join([
            INTENT_PROMPT_HEADER,
            DEFAULT_TASK_TYPES,
            DEFAULT_COMPLEXITY_RULES,
            DEFAULT_CONTEXT_RULES,
            DEFAULT_MEMORY_RULES,
            DEFAULT_MULTI_AGENT_RULES,
            INTENT_PROMPT_FOOTER,
        ])


# ============================================================
# 便捷函数
# ============================================================

def generate_intent_prompt(schema=None) -> str:
    """
    生成意图识别提示词（便捷函数）
    
    Args:
        schema: PromptSchema 对象（可选）
        
    Returns:
        意图识别提示词
    """
    if schema:
        return IntentPromptGenerator.generate(schema)
    return IntentPromptGenerator.get_default()


def get_default_intent_prompt() -> str:
    """获取默认意图识别提示词"""
    return IntentPromptGenerator.get_default()
