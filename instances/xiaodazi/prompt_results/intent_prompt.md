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

**simple**：单步骤任务，仅需一次直接回答或单次工具调用即可完成。  
- 示例：「今天天气怎么样？」（调用 weather）  
- 示例：「把这份 PDF 转成 Word」（调用文档转换工具）  
- 示例：「截图当前屏幕」（调用截图工具）

**medium**：2–4 步骤，需少量规划或参数确认，但流程清晰、无需多轮 UI 操作。  
- 示例：「帮我写一封请假邮件，明天请一天假」（提取时间 → 生成邮件草稿）  
- 示例：「找出上周下载的 Excel 文件并统计销售额」（定位文件 → 读取 → 计算）  
- 示例：「翻译这段英文并保存为 notes.txt」（翻译 → 写入文件）

**complex**：5+ 步骤，涉及多工具协同、多次界面操作、条件分支或需完整执行计划。  
- 示例：「整理下载文件夹，按类型分类，再把半年前的旧文件列个清单」（扫描 → 分类移动 → 筛选 → 生成报告）  
- 示例：「打开飞书，找到合伙人群，发一句“项目进度更新了”」（启动应用 → 导航界面 → 搜索群 → 输入发送 → 验证）  
- 示例：「从会议录音中提取文字，整理成带重点标记的纪要」（OCR/语音转文字 → 结构化 → 标注 → 保存）

## skip_memory（跳过记忆检索）

设为 `true` 仅当用户明确要求忽略历史偏好（如「别用我之前的风格」「这次重新开始」）或任务完全与个人习惯无关（如临时查天气、一次性工具操作）。默认 `false`，因系统强调利用 `<user_memory>` 提供个性化服务。

## is_follow_up（是否为追问）

设为 `true` 当用户消息明显承接上一轮对话，如使用代词（「它」「那个」）、省略主语、或直接回应前文（如「再详细点」「换一种风格」）。  
- 示例：「刚才那个表格能加个图表吗？」  
- 示例：「不是这个，是上周的周报」  
- 示例：「改成毒舌风格」

## wants_to_stop（用户是否希望停止/取消）

设为 `true` 当用户使用明确中止词汇（如「算了」「取消」「别弄了」「恢复原样」「停一下」），或表达放弃意图（如「太麻烦了，不搞了」）。默认 `false`。

## relevant_skill_groups（需要哪些技能分组）

基于 Agent 能力推导出以下技能分组（宁多勿漏）：

- **file_operations**：文件读取、写入、移动、重命名、备份、批量处理（对应 `nodes` 工具）
- **document_processing**：PDF/Word/Excel 转换、表格分析、文本提取（含 OCR）
- **desktop_automation**：操作应用界面（如飞书、浏览器）、打开应用、模拟点击（需桌面操作协议）
- **writing_assistance**：写作、润色、邮件/文案生成、风格适配（依赖记忆中的写作风格）
- **knowledge_search**：查询用户本地知识库内容（调用 `knowledge_search`）
- **system_interaction**：系统设置调用（如 `open_system_preferences`）、权限处理、环境感知
- **plan_execution**：多步骤任务规划、替代方案生成（`plan-todo` 相关逻辑）

## Few-Shot 示例

<example>
<user_query>今天北京天气如何？</user_query>
<output>
{
  "complexity": "simple",
  "skip_memory": false,
  "is_follow_up": false,
  "wants_to_stop": false,
  "relevant_skill_groups": ["system_interaction"]
}
</output>
</example>

<example>
<user_query>把桌面上的 report.pdf 转成 Word 文档</user_query>
<output>
{
  "complexity": "simple",
  "skip_memory": false,
  "is_follow_up": false,
  "wants_to_stop": false,
  "relevant_skill_groups": ["file_operations", "document_processing"]
}
</output>
</example>

<example>
<user_query>帮我写一封给老板的周报，包含本周完成事项和下周计划</user_query>
<output>
{
  "complexity": "medium",
  "skip_memory": false,
  "is_follow_up": false,
  "wants_to_stop": false,
  "relevant_skill_groups": ["writing_assistance"]
}
</output>
</example>

<example>
<user_query>上次那个会议纪要能加个执行人列表吗？</user_query>
<output>
{
  "complexity": "medium",
  "skip_memory": false,
  "is_follow_up": true,
  "wants_to_stop": false,
  "relevant_skill_groups": ["writing_assistance", "file_operations"]
}
</output>
</example>

<example>
<user_query>整理下载文件夹，图片放 pictures，文档放 docs，然后告诉我哪些是超过100MB的大文件</user_query>
<output>
{
  "complexity": "complex",
  "skip_memory": false,
  "is_follow_up": false,
  "wants_to_stop": false,
  "relevant_skill_groups": ["file_operations", "plan_execution"]
}
</output>
</example>

<example>
<user_query>打开飞书，给“产品团队”群发“需求文档已更新，请查收”</user_query>
<output>
{
  "complexity": "complex",
  "skip_memory": false,
  "is_follow_up": false,
  "wants_to_stop": false,
  "relevant_skill_groups": ["desktop_automation", "plan_execution"]
}
</output>
</example>

<example>
<user_query>算了，别改那些文件了，恢复原样吧</user_query>
<output>
{
  "complexity": "simple",
  "skip_memory": false,
  "is_follow_up": true,
  "wants_to_stop": true,
  "relevant_skill_groups": ["file_operations"]
}
</output>
</example>

<example>
<user_query>这次别用我之前的毒舌风格，正经点写</user_query>
<output>
{
  "complexity": "simple",
  "skip_memory": true,
  "is_follow_up": true,
  "wants_to_stop": false,
  "relevant_skill_groups": ["writing_assistance"]
}
</output>
</example>

<example>
<user_query>从这个截图里提取文字并翻译成中文</user_query>
<output>
{
  "complexity": "medium",
  "skip_memory": false,
  "is_follow_up": false,
  "wants_to_stop": false,
  "relevant_skill_groups": ["document_processing", "writing_assistance"]
}
</output>
</example>

<example>
<user_query>查一下我去年写的项目总结在哪个文件夹</user_query>
<output>
{
  "complexity": "medium",
  "skip_memory": false,
  "is_follow_up": false,
  "wants_to_stop": false,
  "relevant_skill_groups": ["file_operations", "knowledge_search"]
}
</output>
</example>

<example>
<user_query>太麻烦了，不弄了</user_query>
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
<user_query>帮我看看系统设置里有没有开启屏幕录制权限</user_query>
<output>
{
  "complexity": "simple",
  "skip_memory": false,
  "is_follow_up": false,
  "wants_to_stop": false,
  "relevant_skill_groups": ["system_interaction"]
}
</output>
</example>

## 重要说明

- 所有布尔字段默认为 `false`，除非有明确证据支持设为 `true`。
- `relevant_skill_groups` 宁可多选，不可遗漏；若任务涉及多个能力，全部列出。
- 不依赖关键词匹配，而是基于任务语义和所需执行动作判断复杂度与技能分组。
- 即使用户未显式提及文件路径或应用名，只要任务隐含本地操作（如“整理下载文件夹”），即视为需要相应技能分组。