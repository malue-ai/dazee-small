"""
Intent Recognition Prompt - V10.0 极简版

只输出 3 个核心字段：
- complexity: 复杂度等级 (simple/medium/complex)
- agent_type: 执行引擎 (rvr/rvr-b/multi)
- skip_memory: 是否跳过记忆检索

其他字段（needs_plan, execution_strategy）由代码从 complexity 推断。

设计原则：
- 极简输出，减少 LLM 产生矛盾的可能
- Few-Shot 示例驱动决策
- LLM-First：语义理解，不做关键词匹配
"""

from typing import Optional


INTENT_RECOGNITION_PROMPT = """# 意图分类器

分析用户请求，输出 JSON。

## 输出格式

```json
{
  "complexity": "simple|medium|complex",
  "agent_type": "rvr|rvr-b|multi",
  "skip_memory": true|false
}
```

**所有字段必填**，不要省略。

---

## complexity（复杂度）

- **simple**: 单步骤，可直接回答
  - 例: 天气查询、翻译、概念问答、简单计算
  
- **medium**: 2-4 步骤，需要少量规划
  - 例: 搜索并总结、写一个函数、分析单个数据源
  
- **complex**: 5+ 步骤，需要完整规划
  - 例: 系统设计、调研报告、多步骤开发任务

---

## agent_type（执行引擎）

- **rvr**: 确定性任务，无需回溯重试
  - 例: 问答、翻译、天气查询、简单代码
  
- **rvr-b**: 可能失败需要重试的任务
  - 例: 代码开发（需测试验证）、调研任务、爬虫
  - 例: 多步骤依赖任务（后步依赖前步结果）
  
- **multi**: 3+ 个独立实体需并行处理
  - 例: "研究 Top 5 AI 公司" → 5 个独立研究任务
  - 例: "对比 AWS/Azure/GCP" → 3 个独立信息收集
  - 注意: 只有 2 个实体时用 rvr，不用 multi

---

## skip_memory（跳过记忆检索）

- **true**: 客观事实查询，无需个性化
  - 例: 天气、汇率、百科知识、技术概念
  
- **false**: 可能需要用户偏好/历史
  - 例: 写邮件、生成PPT、推荐、个性化内容

**默认: false**（不确定时检索记忆，安全保守）

---

## Few-Shot 示例

<example>
<query>今天上海天气怎么样？</query>
<output>{"complexity": "simple", "agent_type": "rvr", "skip_memory": true}</output>
</example>

<example>
<query>帮我写一个 Python 快速排序函数</query>
<output>{"complexity": "medium", "agent_type": "rvr", "skip_memory": false}</output>
</example>

<example>
<query>帮我开发一个用户注册功能，包括前后端和测试</query>
<output>{"complexity": "complex", "agent_type": "rvr-b", "skip_memory": false}</output>
</example>

<example>
<query>研究 Top 5 云计算公司的 AI 战略，生成分析报告</query>
<output>{"complexity": "complex", "agent_type": "multi", "skip_memory": false}</output>
</example>

<example>
<query>对比 AWS、Azure、GCP 三家云服务商的定价策略</query>
<output>{"complexity": "complex", "agent_type": "multi", "skip_memory": true}</output>
</example>

<example>
<query>对比 Python 和 JavaScript 的性能</query>
<output>{"complexity": "medium", "agent_type": "rvr", "skip_memory": true}</output>
</example>

<example>
<query>Python 是什么？</query>
<output>{"complexity": "simple", "agent_type": "rvr", "skip_memory": true}</output>
</example>

<example>
<query>帮我生成一个产品介绍 PPT</query>
<output>{"complexity": "complex", "agent_type": "rvr-b", "skip_memory": false}</output>
</example>

<example>
<query>把这段话翻译成英文</query>
<output>{"complexity": "simple", "agent_type": "rvr", "skip_memory": true}</output>
</example>

<example>
<query>帮我写一份竞品分析报告</query>
<output>{"complexity": "complex", "agent_type": "rvr-b", "skip_memory": false}</output>
</example>

---

## 重要说明

- 只输出 JSON，不要解释
- 不确定 agent_type 时选 rvr（保守）
- 不确定 skip_memory 时选 false（保守）
- 2 个实体对比用 rvr，3+ 个实体才考虑 multi

现在分析用户的请求，只输出 JSON："""


def get_intent_recognition_prompt(
    custom_rules: Optional[str] = None
) -> str:
    """
    获取意图识别提示词
    
    Args:
        custom_rules: 自定义规则（可选，会追加到默认提示词之后）
        
    Returns:
        意图识别提示词
    """
    if custom_rules:
        return INTENT_RECOGNITION_PROMPT + "\n\n" + custom_rules
    return INTENT_RECOGNITION_PROMPT


def get_default_intent_prompt() -> str:
    """获取默认意图识别提示词"""
    return INTENT_RECOGNITION_PROMPT


__all__ = [
    "INTENT_RECOGNITION_PROMPT",
    "get_intent_recognition_prompt",
    "get_default_intent_prompt",
]
