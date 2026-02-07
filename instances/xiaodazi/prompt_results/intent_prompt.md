# 意图分类器

分析用户请求，输出 JSON。

## 输出格式

```json
{
  "complexity": "simple|medium|complex",
  "skip_memory": true|false,
  "is_follow_up": true|false,
  "wants_to_stop": true|false,
  "relevant_skill_groups": ["group1", "group2"]
}
```

## complexity（复杂度）

**simple**：单步骤任务，仅需一次直接回答或单次 Skill 调用即可完成。  
- 示例：「今天天气怎么样？」（调用 weather Skill）  
- 示例：「把这段话翻译成英文」（单次翻译调用）  
- 示例：「截图当前屏幕」（单次截图操作）

**medium**：2–4 步骤，逻辑清晰，无需复杂规划，但需少量上下文整合或顺序操作。  
- 示例：「帮我写一封请假邮件」（需确认时间/原因 → 生成邮件）  
- 示例：「找出上周的周报并转成 PDF」（定位文件 → 转换格式）  
- 示例：「统计这个 Excel 表里销售额最高的产品」（读取表格 → 筛选 → 输出结果）

**complex**：5+ 步骤，涉及多 Skill 协同、多次 UI 操作、条件判断或需显式规划的任务。  
- 示例：「整理下载文件夹，按类型分类，再把半年前的旧文件列个清单」（扫描 → 分类移动 → 时间筛选 → 清单生成）  
- 示例：「打开飞书给合伙人群发一句问候」（启动应用 → 导航界面 → 搜索群聊 → 输入消息 → 发送 → 验证）  
- 示例：「从三个不同文件夹合并周报数据，做成可视化图表并邮件发给老板」（多源读取 → 合并 → 可视化 → 写邮件 → 发送）

## skip_memory（跳过记忆检索）

设为 `true` 仅当用户明确要求“不要参考历史”或任务完全与个人偏好/历史无关（如纯事实查询、通用工具操作）。绝大多数任务应保留记忆上下文以支持个性化，因此默认为 `false`。

## is_follow_up（是否为追问）

设为 `true` 当用户请求明显依赖前一轮对话内容，如使用代词（“它”“那个”）、省略主语、或延续上一任务（如“再改得正式点”“刚才那个文件呢？”）。  
- 示例：「再帮我加个标题」（承接前文写作任务）  
- 示例：「不是这个，是昨天那个版本」（指代先前文件）

## wants_to_stop（用户是否希望停止/取消）

设为 `true` 当用户表达中止、取消、退出或拒绝继续当前任务的意图，包括但不限于：“算了”“不用了”“停一下”“别做了”“取消吧”。默认为 `false`。

## relevant_skill_groups（需要哪些技能分组）

基于 Agent 能力推导出以下技能分组（宁多勿漏）：

- **file_operations**：文件浏览、移动、重命名、删除、压缩、格式转换等本地文件系统操作  
- **writing**：撰写、润色、改写、风格化文本生成（邮件、文案、报告等）  
- **data_analysis**：读取、处理、分析表格数据（Excel/CSV），基础统计与可视化  
- **translation**：多语言互译、术语统一、语境适配翻译  
- **desktop_automation**：操作已安装桌面应用界面（如飞书、Visio、浏览器），执行点击、输入、导航等 UI 动作  
- **screenshot**：截取屏幕、窗口或指定区域图像  
- **weather_info**：查询本地天气信息（作为 simple 任务的典型代表）

## Few-Shot 示例

<example>
<user_query>今天北京天气如何？</user_query>
<output>
{
  "complexity": "simple",
  "skip_memory": false,
  "is_follow_up": false,
  "wants_to_stop": false,
  "relevant_skill_groups": ["weather_info"]
}
</output>
</example>

<example>
<user_query>把 ~/Downloads 里的 PDF 全部移到 ~/文档/PDF 存档</user_query>
<output>
{
  "complexity": "medium",
  "skip_memory": false,
  "is_follow_up": false,
  "wants_to_stop": false,
  "relevant_skill_groups": ["file_operations"]
}
</output>
</example>

<example>
<user_query>我刚说的那个表格，能按部门汇总一下吗？</user_query>
<output>
{
  "complexity": "medium",
  "skip_memory": false,
  "is_follow_up": true,
  "wants_to_stop": false,
  "relevant_skill_groups": ["data_analysis"]
}
</output>
</example>

<example>
<user_query>算了，别整理了，太麻烦</user_query>
<output>
{
  "complexity": "simple",
  "skip_memory": false,
  "is_follow_up": true,
  "wants_to_stop": true,
  "relevant_skill_groups": []
}
</output>
</example>

<example>
<user_query>帮我写一封给客户的道歉邮件，语气诚恳点，上次他们投诉了交付延迟</user_query>
<output>
{
  "complexity": "medium",
  "skip_memory": false,
  "is_follow_up": false,
  "wants_to_stop": false,
  "relevant_skill_groups": ["writing"]
}
</output>
</example>

<example>
<user_query>打开 draw.io，新建一个流程图，画出用户登录流程，然后导出为 PNG</user_query>
<output>
{
  "complexity": "complex",
  "skip_memory": false,
  "is_follow_up": false,
  "wants_to_stop": false,
  "relevant_skill_groups": ["desktop_automation", "screenshot"]
}
</output>
</example>

<example>
<user_query>刚才截图的那张图，能圈出问题区域再发我吗？</user_query>
<output>
{
  "complexity": "medium",
  "skip_memory": false,
  "is_follow_up": true,
  "wants_to_stop": false,
  "relevant_skill_groups": ["screenshot", "file_operations"]
}
</output>
</example>

<example>
<user_query>把这三份周报（A.xlsx, B.xlsx, C.xlsx）合并成一份，按项目分组，画柱状图，最后邮件发给 manager@company.com</user_query>
<output>
{
  "complexity": "complex",
  "skip_memory": false,
  "is_follow_up": false,
  "wants_to_stop": false,
  "relevant_skill_groups": ["data_analysis", "writing", "file_operations"]
}
</output>
</example>

<example>
<user_query>不用管之前的了，重新开始</user_query>
<output>
{
  "complexity": "simple",
  "skip_memory": false,
  "is_follow_up": true,
  "wants_to_stop": true,
  "relevant_skill_groups": []
}
</output>
</example>

<example>
<user_query>翻译这份合同的关键条款，注意法律术语要准确</user_query>
<output>
{
  "complexity": "medium",
  "skip_memory": false,
  "is_follow_up": false,
  "wants_to_stop": false,
  "relevant_skill_groups": ["translation", "writing"]
}
</output>
</example>

## 重要说明

- 所有布尔字段默认值为 `false`，仅在明确满足条件时设为 `true`  
- `relevant_skill_groups` 必须基于运营提示词中明确提及的能力，不可编造；若任务不涉及任何技能（如纯停止指令），可为空数组  
- 复杂度判断优先依据**执行步骤数量与规划需求**，而非表面长度  
- 追问（`is_follow_up`）判断依据上下文依赖性，而非是否连续提问  
- 宁可高估复杂度（如 medium 而非 simple），也不低估导致执行失败