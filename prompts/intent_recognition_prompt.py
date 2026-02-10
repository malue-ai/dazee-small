"""
Intent Recognition Prompt - V12.1 桌面端版

输出 6 个核心字段：
- complexity: 复杂度等级 (simple/medium/complex)
- skip_memory: 是否跳过记忆检索
- is_follow_up: 是否为追问
- wants_to_stop: 用户是否希望停止/取消
- wants_rollback: 用户是否要求恢复/撤销
- relevant_skill_groups: 需要哪些技能分组（多选，重召回）

其他字段（needs_plan）由代码从 complexity 推断。

设计原则：
- 极简输出，减少 LLM 产生矛盾的可能
- Few-Shot 示例驱动决策（多选示例 ≥ 40%，消除单选偏见）
- LLM-First：语义理解，不做关键词匹配
- 重召回：relevant_skill_groups 宁多勿漏
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
  "wants_rollback": true|false,
  "relevant_skill_groups": ["group1", "group2"]
}}
```

**所有字段必填**，不要省略。

---

## complexity（复杂度）

- **simple**: 单步骤，可直接回答或单次工具调用
  - 例: 天气查询、简单翻译、打开一个应用、概念问答、简单计算、设置定时任务/提醒

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

## wants_rollback（用户是否要求恢复/撤销）

- **true**: 用户**当前这条消息**明确要求恢复、撤销、回退之前的文件操作
  - 例: "帮我恢复一下"、"撤销刚才的修改"、"把文件还原回去"
- **false**: 其他一切情况，包括：
  - 致谢/确认: "OK 感谢"、"好的"、"收到"、"谢谢"
  - 追问: "还有别的吗"、"继续"
  - 新请求: 任何不涉及恢复/撤销的新任务
  - 已完成的回滚后续: 用户说"好的"确认回滚结果

**关键判断**：只看**当前消息**是否包含恢复/撤销的动作请求。即使上文讨论过回滚，如果当前消息只是致谢或确认，也必须为 false。

**默认: false**

---

## relevant_skill_groups（需要哪些技能分组）⚠️ 最重要

**核心原则：宁多勿漏。漏选 = 该能力完全不可用；多选仅多加载少量提示词，代价极低。**

### 决策两步法
1. **拆动作**：这个请求包含几个动作？（如 "搜论文写综述" = 搜索 + 写作 = 2 个动作）
2. **逐个匹配**：每个动作独立匹配分组，**全部选上**，不要合并

最多选 **6** 个分组（0-6），纯聊天/问答填 []。

### 可选分组
{skill_groups_description}

### ⚠️ 常见需要多选的信号
- 提到**写/总结/报告/润色/改写** → 加上 writing
- 提到**文件/PDF/Word/格式转换/归档** → 加上 file_operation
- 提到**搜索/调研/论文/网页/爬取** → 加上 research
- 提到**数据/分析/Excel/表格/图表** → 加上 data_analysis
- 提到**应用操作/打开App/截图/UI自动化** → 加上 app_automation
- 提到**邮件/日历/笔记/提醒/消息/待办** → 加上 productivity
- 提到**翻译/多语言** → 加上 translation
- 提到**视频/音频/语音/TTS/转录** → 加上 media
- **纯聊天/闲聊/问答/计算/打招呼** → []（不需要任何 skill）

---

## Few-Shot 示例

<!-- 单动作 → 单分组 -->

<example>
<query>今天上海天气怎么样？</query>
<output>{{"complexity": "simple", "skip_memory": true, "is_follow_up": false, "wants_to_stop": false, "wants_rollback": false, "relevant_skill_groups": []}}</output>
</example>

<example>
<query>帮我写一篇关于咖啡文化的文章</query>
<output>{{"complexity": "medium", "skip_memory": false, "is_follow_up": false, "wants_to_stop": false, "wants_rollback": false, "relevant_skill_groups": ["writing"]}}</output>
</example>

<example>
<query>帮我整理下载文件夹，按类型分类</query>
<output>{{"complexity": "medium", "skip_memory": false, "is_follow_up": false, "wants_to_stop": false, "wants_rollback": false, "relevant_skill_groups": ["file_operation"]}}</output>
</example>

<example>
<query>把这段话翻译成英文</query>
<output>{{"complexity": "simple", "skip_memory": true, "is_follow_up": false, "wants_to_stop": false, "wants_rollback": false, "relevant_skill_groups": ["translation"]}}</output>
</example>

<example>
<query>把第二段改短一点</query>
<output>{{"complexity": "simple", "skip_memory": false, "is_follow_up": true, "wants_to_stop": false, "wants_rollback": false, "relevant_skill_groups": ["writing"]}}</output>
</example>

<example>
<query>算了不做了</query>
<output>{{"complexity": "simple", "skip_memory": true, "is_follow_up": false, "wants_to_stop": true, "wants_rollback": false, "relevant_skill_groups": []}}</output>
</example>

<example>
<query>帮我恢复一下刚才删的文件</query>
<output>{{"complexity": "simple", "skip_memory": true, "is_follow_up": true, "wants_to_stop": false, "wants_rollback": true, "relevant_skill_groups": ["file_operation"]}}</output>
</example>

<example>
<query>OK 感谢</query>
<output>{{"complexity": "simple", "skip_memory": true, "is_follow_up": true, "wants_to_stop": false, "wants_rollback": false, "relevant_skill_groups": []}}</output>
</example>

<example>
<query>Python 是什么？</query>
<output>{{"complexity": "simple", "skip_memory": true, "is_follow_up": false, "wants_to_stop": false, "wants_rollback": false, "relevant_skill_groups": []}}</output>
</example>

<example>
<query>截个图给我看看桌面</query>
<output>{{"complexity": "simple", "skip_memory": true, "is_follow_up": false, "wants_to_stop": false, "wants_rollback": false, "relevant_skill_groups": ["app_automation"]}}</output>
</example>

<example>
<query>5分钟后提醒我喝水</query>
<output>{{"complexity": "simple", "skip_memory": true, "is_follow_up": false, "wants_to_stop": false, "wants_rollback": false, "relevant_skill_groups": ["productivity"]}}</output>
</example>

<example>
<query>帮我头脑风暴一下，公众号怎么涨粉</query>
<output>{{"complexity": "medium", "skip_memory": false, "is_follow_up": false, "wants_to_stop": false, "wants_rollback": false, "relevant_skill_groups": ["creative"]}}</output>
</example>

<example>
<query>帮我画一个项目开发流程图</query>
<output>{{"complexity": "medium", "skip_memory": false, "is_follow_up": false, "wants_to_stop": false, "wants_rollback": false, "relevant_skill_groups": ["diagram"]}}</output>
</example>

<!-- 多动作 → 必须多选 ⚠️ -->

<example>
<query>分析这个 Excel 数据，找出销售趋势，写一段总结</query>
<output>{{"complexity": "complex", "skip_memory": false, "is_follow_up": false, "wants_to_stop": false, "wants_rollback": false, "relevant_skill_groups": ["data_analysis", "writing"]}}</output>
<note>分析数据 → data_analysis ＋ 写总结 → writing</note>
</example>

<example>
<query>帮我搜一下最近的 AI Agent 论文，写个综述</query>
<output>{{"complexity": "complex", "skip_memory": false, "is_follow_up": false, "wants_to_stop": false, "wants_rollback": false, "relevant_skill_groups": ["research", "writing"]}}</output>
<note>搜论文 → research ＋ 写综述 → writing</note>
</example>

<example>
<query>把这张图片上的英文 OCR 出来翻译成中文</query>
<output>{{"complexity": "medium", "skip_memory": true, "is_follow_up": false, "wants_to_stop": false, "wants_rollback": false, "relevant_skill_groups": ["file_operation", "translation"]}}</output>
<note>OCR 提取文字 → file_operation ＋ 翻译 → translation</note>
</example>

<example>
<query>帮我把这篇文章去掉 AI 味，然后生成一份 PDF 报告</query>
<output>{{"complexity": "complex", "skip_memory": false, "is_follow_up": false, "wants_to_stop": false, "wants_rollback": false, "relevant_skill_groups": ["writing", "file_operation"]}}</output>
<note>去 AI 味 → writing ＋ 生成 PDF → file_operation</note>
</example>

<example>
<query>调研一下竞品的最新动态，写一份对比分析报告</query>
<output>{{"complexity": "complex", "skip_memory": false, "is_follow_up": false, "wants_to_stop": false, "wants_rollback": false, "relevant_skill_groups": ["research", "writing"]}}</output>
<note>调研竞品 → research ＋ 写报告 → writing</note>
</example>

<example>
<query>整理这些发票，按月份归档到对应文件夹</query>
<output>{{"complexity": "medium", "skip_memory": false, "is_follow_up": false, "wants_to_stop": false, "wants_rollback": false, "relevant_skill_groups": ["data_analysis", "file_operation"]}}</output>
<note>整理发票数据 → data_analysis ＋ 归档到文件夹 → file_operation</note>
</example>

<example>
<query>读一下这个 PDF 合同，提取关键条款，整理成 Word 文档</query>
<output>{{"complexity": "complex", "skip_memory": false, "is_follow_up": false, "wants_to_stop": false, "wants_rollback": false, "relevant_skill_groups": ["research", "file_operation", "writing"]}}</output>
<note>读 PDF → research ＋ 整理内容 → writing ＋ 输出 Word → file_operation</note>
</example>

<example>
<query>帮我分析这份会议记录，提取行动项，发邮件给参会人</query>
<output>{{"complexity": "complex", "skip_memory": false, "is_follow_up": false, "wants_to_stop": false, "wants_rollback": false, "relevant_skill_groups": ["meeting", "productivity"]}}</output>
<note>分析会议 → meeting ＋ 发邮件 → productivity</note>
</example>

<example>
<query>帮我把这个视频转成文字，翻译成英文，写一篇博客发布</query>
<output>{{"complexity": "complex", "skip_memory": false, "is_follow_up": false, "wants_to_stop": false, "wants_rollback": false, "relevant_skill_groups": ["media", "translation", "writing", "content_creation"]}}</output>
<note>视频转文字 → media ＋ 翻译 → translation ＋ 写博客 → writing ＋ 内容发布 → content_creation</note>
</example>

---

## 重要说明

- 只输出 JSON，不要解释
- 不确定 skip_memory 时选 false（保守）
- 不确定 is_follow_up 时选 false（保守）
- 不确定 wants_rollback 时选 false（保守，只有明确恢复/撤销请求才为 true）
- **relevant_skill_groups 经常需要多选**（上面示例中近半数是多选）
- 拆分用户请求中的每个动作，分别匹配分组
- **不确定某个分组是否需要时 → 选上**（多选无害，漏选致命）

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
