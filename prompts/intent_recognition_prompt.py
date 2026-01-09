"""
Intent Recognition Prompt - 模块化版本

🆕 V4.6.2: 重构为模块化结构，支持动态组装

职责：
- 快速分类任务类型和复杂度
- 决定系统提示词级别
- 判断是否需要 Mem0 记忆检索（基于 few-shot 示例）
- 不分析所需能力（由 Sonnet 在 Plan 阶段完成）

设计原则：
- Haiku 做简单分类（快+便宜）
- Sonnet 做深度推理（强+准确）
- 使用 few-shot 示例引导记忆检索决策，而非硬编码规则

模块化设计：
- INTENT_PROMPT_HEADER: 固定头部
- INTENT_PROMPT_TASK_TYPES: 任务类型定义（可被用户配置覆盖）
- INTENT_PROMPT_COMPLEXITY: 复杂度规则（可被用户配置覆盖）
- INTENT_PROMPT_MEMORY: 记忆检索规则（few-shot 示例）
- INTENT_PROMPT_FOOTER: 固定尾部
"""

from typing import Optional

# ============================================================
# 模块化组件
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

INTENT_PROMPT_TASK_TYPES = """
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

INTENT_PROMPT_COMPLEXITY = """
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

INTENT_PROMPT_MEMORY = """
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
# 组装后的完整提示词（向后兼容）
# ============================================================

INTENT_RECOGNITION_PROMPT = (
    INTENT_PROMPT_HEADER +
    INTENT_PROMPT_TASK_TYPES +
    INTENT_PROMPT_COMPLEXITY +
    INTENT_PROMPT_MEMORY +
    INTENT_PROMPT_FOOTER
)


# ============================================================
# 公开函数
# ============================================================

def get_intent_recognition_prompt(
    custom_task_types: Optional[str] = None,
    custom_complexity_rules: Optional[str] = None,
    custom_memory_rules: Optional[str] = None,
) -> str:
    """
    获取意图识别提示词（支持自定义覆盖）
    
    🆕 V4.6.2: 模块化组装
    
    Args:
        custom_task_types: 自定义任务类型定义（覆盖默认）
        custom_complexity_rules: 自定义复杂度规则（覆盖默认）
        custom_memory_rules: 自定义记忆检索规则（覆盖默认）
        
    Returns:
        组装后的意图识别提示词
    """
    parts = [
        INTENT_PROMPT_HEADER,
        custom_task_types or INTENT_PROMPT_TASK_TYPES,
        custom_complexity_rules or INTENT_PROMPT_COMPLEXITY,
        custom_memory_rules or INTENT_PROMPT_MEMORY,
        INTENT_PROMPT_FOOTER,
    ]
    
    return "".join(parts)


def get_default_intent_prompt() -> str:
    """获取默认意图识别提示词（无任何覆盖）"""
    return INTENT_RECOGNITION_PROMPT


# 导出模块化组件（供 IntentPromptGenerator 使用）
__all__ = [
    "INTENT_RECOGNITION_PROMPT",
    "INTENT_PROMPT_HEADER",
    "INTENT_PROMPT_TASK_TYPES",
    "INTENT_PROMPT_COMPLEXITY",
    "INTENT_PROMPT_MEMORY",
    "INTENT_PROMPT_FOOTER",
    "get_intent_recognition_prompt",
    "get_default_intent_prompt",
]
