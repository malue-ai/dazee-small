"""
Intent Recognition Prompt - V12.0 桌面端版

输出 5 个核心字段：
- complexity: 复杂度等级 (simple/medium/complex)
- skip_memory: 是否跳过记忆检索
- is_follow_up: 是否为追问
- wants_to_stop: 用户是否希望停止/取消
- relevant_skill_groups: 需要哪些技能分组（多选）

其他字段（needs_plan）由代码从 complexity 推断。

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
{{
  "complexity": "simple|medium|complex",
  "skip_memory": true|false,
  "is_follow_up": true|false,
  "wants_to_stop": true|false,
  "relevant_skill_groups": ["group1", "group2"]
}}
```

**所有字段必填**，不要省略。

---

## complexity（复杂度）

- **simple**: 单步骤，可直接回答或单次工具调用
  - 例: 天气查询、简单翻译、打开一个应用、概念问答、简单计算

- **medium**: 2-4 步骤，需少量规划或多次工具调用
  - 例: 写一篇文章、分析一个 Excel、搜索并总结、整理指定文件夹

- **complex**: 5+ 步骤，需完整规划，可能涉及多工具协作或 UI 操作链
  - 例: 调研竞品写对比报告、在应用中完成多步操作流程、整理文件夹并生成分类清单

---

## skip_memory（跳过记忆检索）

- **true**: 客观事实查询，无需个性化（如天气、翻译、计算）
- **false**: 可能需要用户偏好/历史（如写作风格、常用路径、称呼）

**默认: false**（不确定时检索记忆，安全保守）

---

## is_follow_up（是否为追问）

- **true**: 用户在已有对话基础上追问、补充、修改，依赖前序上下文
  - 例: "继续"、"然后呢"、"把第二段改短一点"、"用表格展示"
- **false**: 全新请求，不依赖前序对话

**默认: false**

---

## wants_to_stop（用户是否希望停止/取消）

- **true**: 用户明确表示停止、取消、不做了
- **false**: 正常任务请求或追问

**默认: false**

---

## relevant_skill_groups（需要哪些技能分组）

从以下分组中选择**所有可能相关的**（可多选，宁多勿漏）：
{skill_groups_description}

**原则**：
- 一个请求可能涉及多个分组（如"分析 Excel 写总结" → ["data_analysis", "writing"]）
- **重召回**：不确定是否需要时，选上（宁可多选，不要漏掉）
- 纯聊天/问答/计算等不需要任何技能时，填 []

---

## Few-Shot 示例

<example>
<query>今天上海天气怎么样？</query>
<output>{{"complexity": "simple", "skip_memory": true, "is_follow_up": false, "wants_to_stop": false, "relevant_skill_groups": []}}</output>
</example>

<example>
<query>帮我写一篇关于咖啡文化的文章</query>
<output>{{"complexity": "medium", "skip_memory": false, "is_follow_up": false, "wants_to_stop": false, "relevant_skill_groups": ["writing"]}}</output>
</example>

<example>
<query>分析这个 Excel 数据，找出销售趋势，写一段总结</query>
<output>{{"complexity": "complex", "skip_memory": false, "is_follow_up": false, "wants_to_stop": false, "relevant_skill_groups": ["data_analysis", "writing"]}}</output>
</example>

<example>
<query>打开飞书给合伙人群发一句问候</query>
<output>{{"complexity": "complex", "skip_memory": false, "is_follow_up": false, "wants_to_stop": false, "relevant_skill_groups": ["app_automation"]}}</output>
</example>

<example>
<query>帮我整理下载文件夹，按类型分类</query>
<output>{{"complexity": "medium", "skip_memory": false, "is_follow_up": false, "wants_to_stop": false, "relevant_skill_groups": ["file_operation"]}}</output>
</example>

<example>
<query>把这段话翻译成英文</query>
<output>{{"complexity": "simple", "skip_memory": true, "is_follow_up": false, "wants_to_stop": false, "relevant_skill_groups": ["translation"]}}</output>
</example>

<example>
<query>把第二段改短一点</query>
<output>{{"complexity": "simple", "skip_memory": false, "is_follow_up": true, "wants_to_stop": false, "relevant_skill_groups": ["writing"]}}</output>
</example>

<example>
<query>算了不做了</query>
<output>{{"complexity": "simple", "skip_memory": true, "is_follow_up": false, "wants_to_stop": true, "relevant_skill_groups": []}}</output>
</example>

<example>
<query>Python 是什么？</query>
<output>{{"complexity": "simple", "skip_memory": true, "is_follow_up": false, "wants_to_stop": false, "relevant_skill_groups": []}}</output>
</example>

<example>
<query>帮我搜一下最近的 transformer 论文</query>
<output>{{"complexity": "medium", "skip_memory": false, "is_follow_up": false, "wants_to_stop": false, "relevant_skill_groups": ["research"]}}</output>
</example>

<example>
<query>截个图给我看看桌面</query>
<output>{{"complexity": "simple", "skip_memory": true, "is_follow_up": false, "wants_to_stop": false, "relevant_skill_groups": ["app_automation"]}}</output>
</example>

<example>
<query>帮我分析这份会议记录，提取行动项</query>
<output>{{"complexity": "medium", "skip_memory": false, "is_follow_up": false, "wants_to_stop": false, "relevant_skill_groups": ["meeting"]}}</output>
</example>

<example>
<query>帮我头脑风暴一下，公众号怎么涨粉</query>
<output>{{"complexity": "medium", "skip_memory": false, "is_follow_up": false, "wants_to_stop": false, "relevant_skill_groups": ["creative"]}}</output>
</example>

<example>
<query>帮我画一个项目开发流程图</query>
<output>{{"complexity": "medium", "skip_memory": false, "is_follow_up": false, "wants_to_stop": false, "relevant_skill_groups": ["diagram"]}}</output>
</example>

<example>
<query>帮我分析这个职位描述，优化简历</query>
<output>{{"complexity": "medium", "skip_memory": false, "is_follow_up": false, "wants_to_stop": false, "relevant_skill_groups": ["career"]}}</output>
</example>

<example>
<query>教我学数据分析，从零开始</query>
<output>{{"complexity": "medium", "skip_memory": false, "is_follow_up": false, "wants_to_stop": false, "relevant_skill_groups": ["learning"]}}</output>
</example>

<example>
<query>帮我把这篇文章去掉 AI 味，然后生成一份 PDF 报告</query>
<output>{{"complexity": "complex", "skip_memory": false, "is_follow_up": false, "wants_to_stop": false, "relevant_skill_groups": ["writing"]}}</output>
</example>

---

## 重要说明

- 只输出 JSON，不要解释
- 不确定 skip_memory 时选 false（保守）
- 不确定 is_follow_up 时选 false（保守）
- relevant_skill_groups 宁多勿漏，不确定时多选

现在分析用户的请求，只输出 JSON："""


def get_intent_recognition_prompt(
    skill_groups_description: str,
    custom_rules: Optional[str] = None,
) -> str:
    """
    获取意图识别提示词

    Args:
        skill_groups_description: Skill 分组描述（必填，从 SkillGroupRegistry.build_groups_description() 获取）
        custom_rules: 自定义规则（可选，会追加到默认提示词之后）

    Returns:
        意图识别提示词
    """
    prompt = INTENT_RECOGNITION_PROMPT.replace("{skill_groups_description}", skill_groups_description)

    if custom_rules:
        return prompt + "\n\n" + custom_rules
    return prompt


__all__ = [
    "INTENT_RECOGNITION_PROMPT",
    "get_intent_recognition_prompt",
]
