"""
动态意图识别提示词生成器 - IntentPromptGenerator

🆕 V4.6.2: 从 PromptSchema 动态生成意图识别提示词

设计原则：
1. 用户配置优先：运营在 prompt.md 中定义的意图规则
2. 高质量默认：未配置时使用精心设计的 few-shot 示例
3. 一次性生成：启动时生成，运行时直接使用

生成的提示词用于 IntentAnalyzer (Haiku 4.5):
- 任务类型分类
- 复杂度判断
- 是否需要规划
- 是否跳过记忆检索
"""

from typing import Optional, List, Dict, Any

from logger import get_logger

logger = get_logger("intent_prompt_generator")


# ============================================================
# 高质量默认提示词组件
# ============================================================

INTENT_PROMPT_HEADER = """You are a fast intent classifier. Your job is SIMPLE CLASSIFICATION ONLY.

## Task

Analyze the user query and classify it into one of these categories:

### Output Format (JSON)

```json
{
  "task_type": "information_query|content_generation|data_analysis|code_task|other",
  "complexity": "simple|medium|complex",
  "needs_plan": true|false,
  "skip_memory_retrieval": true|false
}
```

**ALL FOUR FIELDS ARE REQUIRED** — 不要省略任何字段。即使不确定也要给出最接近的分类。
"""

# 默认的任务类型定义
DEFAULT_TASK_TYPES = """
## Classification Rules

### Task Type
- **information_query**: Search, lookup, Q&A
  - Examples: "weather?", "search AI papers", "what is X?"
  
- **content_generation**: Create documents, presentations, reports
  - Examples: "generate PPT", "write report", "create slides"
  
- **data_analysis**: Process data, statistics, analysis
  - Examples: "analyze sales data", "chart from Excel", "calculate trends"
  
- **code_task**: Write, debug, or execute code
  - Examples: "write Python script", "debug this code", "refactor function"
  
- **other**: Everything else
"""

# 默认的复杂度规则
DEFAULT_COMPLEXITY_RULES = """
### Complexity
- **simple**: Single-step, direct answer
  - 1 action, immediate result
  - Examples: "weather?", "current time?", "what is Python?"
  
- **medium**: 2-4 steps, straightforward workflow
  - Examples: "search and summarize", "write function", "analyze data"
  
- **complex**: 5+ steps, requires planning
  - Examples: "create product PPT with research", "analyze market and write strategy"

### Needs Plan
- **true**: complexity is medium or complex
- **false**: complexity is simple
"""

# 默认的记忆检索规则（few-shot 示例驱动）
DEFAULT_MEMORY_RULES = """
### Skip Memory Retrieval (🆕 V4.6)

判断是否跳过用户记忆检索。根据以下示例的思路自行推理：

<examples>
<example>
<query>今天上海天气怎么样？</query>
<reasoning>纯粹的实时信息查询，与用户个人历史无关</reasoning>
<skip_memory_retrieval>true</skip_memory_retrieval>
</example>

<example>
<query>帮我生成一个产品介绍PPT</query>
<reasoning>用户可能有PPT风格偏好、常用配色等历史记录</reasoning>
<skip_memory_retrieval>false</skip_memory_retrieval>
</example>

<example>
<query>Python的列表推导式怎么用？</query>
<reasoning>通用技术问题，不涉及用户个人偏好</reasoning>
<skip_memory_retrieval>true</skip_memory_retrieval>
</example>

<example>
<query>帮我推荐一家餐厅</query>
<reasoning>推荐需要了解用户的口味偏好、饮食限制等</reasoning>
<skip_memory_retrieval>false</skip_memory_retrieval>
</example>

<example>
<query>把这段话翻译成英文</query>
<reasoning>简单翻译任务，无需个性化</reasoning>
<skip_memory_retrieval>true</skip_memory_retrieval>
</example>

<example>
<query>帮我写一段Python代码实现排序</query>
<reasoning>用户可能有编码风格偏好、常用框架等</reasoning>
<skip_memory_retrieval>false</skip_memory_retrieval>
</example>

<example>
<query>1美元等于多少人民币？</query>
<reasoning>汇率查询是客观事实，无需个性化</reasoning>
<skip_memory_retrieval>true</skip_memory_retrieval>
</example>

<example>
<query>按照我之前说的风格，帮我写个邮件</query>
<reasoning>明确引用了历史偏好</reasoning>
<skip_memory_retrieval>false</skip_memory_retrieval>
</example>

<example>
<query>帮我做一个数据分析报告</query>
<reasoning>用户可能有报告格式、图表风格等偏好</reasoning>
<skip_memory_retrieval>false</skip_memory_retrieval>
</example>

<example>
<query>什么是机器学习？</query>
<reasoning>百科知识问答，无需个性化</reasoning>
<skip_memory_retrieval>true</skip_memory_retrieval>
</example>
</examples>

**默认值**: false（不跳过，即默认检索记忆）
**原则**: 不确定时选择 false，宁可多检索也不漏掉个性化
"""

INTENT_PROMPT_FOOTER = """
## Important

- DO NOT analyze what tools/capabilities are needed (that's Sonnet's job)
- DO NOT create a plan (that's Sonnet's job)
- ONLY classify: task_type, complexity, needs_plan, skip_memory_retrieval

## Example

Input: "Create a professional product presentation with market data"

Output:
```json
{
  "task_type": "content_generation",
  "complexity": "complex",
  "needs_plan": true,
  "skip_memory_retrieval": false
}
```

Now classify the user's query. Output ONLY the JSON, nothing else."""


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
        
        # 3. 记忆检索规则
        memory_section = cls._generate_memory_rules(schema)
        parts.append(memory_section)
        
        # 4. 尾部
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
        from core.prompt import TaskComplexity
        
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
    def get_default(cls) -> str:
        """
        获取高质量默认提示词
        
        当运营没有配置意图规则时使用
        """
        return "\n".join([
            INTENT_PROMPT_HEADER,
            DEFAULT_TASK_TYPES,
            DEFAULT_COMPLEXITY_RULES,
            DEFAULT_MEMORY_RULES,
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
