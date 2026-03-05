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

- **simple**：单步骤操作，无需跨阶段协调，直接调用单一技能或返回预设信息。  
  示例：  
  - “查看进度”  
  - “跳过代码生成”  
  - “重新生成 Section 4.2”

- **medium**：涉及 2–4 个步骤，需在已有上下文基础上执行局部流程（如重生成章节+重组装+重合规检查），或确认少量参数后启动子流程。  
  示例：  
  - “修改主要终点的统计方法”（需编辑章节 → 重跑 Skill-5/6）  
  - “只生成主要终点”（过滤章节生成 + 组装 + 合规）  
  - “继续”（检测断点 → 恢复部分流程）

- **complex**：触发完整端到端 DAG 流程（6 阶段），或从零开始解析 Protocol + 模板并生成全套交付物。  
  示例：  
  - “生成 SAP”  
  - “开始”  
  - 上传 Protocol 和模板后说“请帮我完成整个 SAP”

## skip_memory（跳过记忆检索）

设为 `true` 当且仅当请求完全不依赖历史会话或 scratchpad 状态（如首次上传文件、明确要求“重新开始”）。其他情况（包括“继续”“查看进度”“修改内容”）均需访问 scratchpad，应设为 `false`。

## is_follow_up（是否为追问）

设为 `true` 当用户请求明显依赖前一轮 AI 输出（如确认参数、回应进度报告、对占位符或高亮内容提出修改）。  
示例：  
- “开始”（在收到参数确认消息后）→ `true`  
- “使用 Phase III”（在 AI 询问试验阶段后）→ `true`  
- “好的，继续” → `true`

## wants_to_stop（用户是否希望停止/取消）

设为 `true` 当用户明确表达终止、取消、放弃当前任务（如“取消”“不用了”“停止生成”）。模糊表达（如“等等”“稍后”）不视为停止。

## relevant_skill_groups（需要哪些技能分组）

从 Agent 能力推导出以下技能分组：

- **document_parsing**：Protocol/SAP 模板解析、实体抽取、分段读取（对应 Skill-1 & Skill-2）  
- **sap_authoring**：SAP 章节内容生成、Estimand 框架写作、占位符处理（Skill-3）  
- **code_generation**：SAS/R 统计代码生成与映射（Skill-4）  
- **document_assembly**：Markdown → Word/PDF 组装、目录更新（Skill-5）  
- **compliance_checking**：CDISC 合规性审核、一致性检查（Skill-6）  
- **workflow_control**：进度查询、断点恢复、流程跳过/重启（跨阶段控制逻辑）

## Few-Shot 示例

<example>
<input>生成 SAP</input>
<output>
{
  "complexity": "complex",
  "skip_memory": true,
  "is_follow_up": false,
  "wants_to_stop": false,
  "relevant_skill_groups": ["document_parsing", "sap_authoring", "code_generation", "document_assembly", "compliance_checking"]
}
</output>
</example>

<example>
<input>开始</input>
<output>
{
  "complexity": "complex",
  "skip_memory": false,
  "is_follow_up": true,
  "wants_to_stop": false,
  "relevant_skill_groups": ["document_parsing", "sap_authoring", "code_generation", "document_assembly", "compliance_checking"]
}
</output>
</example>

<example>
<input>查看进度</input>
<output>
{
  "complexity": "simple",
  "skip_memory": false,
  "is_follow_up": false,
  "wants_to_stop": false,
  "relevant_skill_groups": ["workflow_control"]
}
</output>
</example>

<example>
<input>跳过代码生成</input>
<output>
{
  "complexity": "simple",
  "skip_memory": false,
  "is_follow_up": false,
  "wants_to_stop": false,
  "relevant_skill_groups": ["workflow_control"]
}
</output>
</example>

<example>
<input>只生成主要终点</input>
<output>
{
  "complexity": "medium",
  "skip_memory": false,
  "is_follow_up": false,
  "wants_to_stop": false,
  "relevant_skill_groups": ["sap_authoring", "document_assembly", "compliance_checking"]
}
</output>
</example>

<example>
<input>重新生成 Section 5.1</input>
<output>
{
  "complexity": "medium",
  "skip_memory": false,
  "is_follow_up": false,
  "wants_to_stop": false,
  "relevant_skill_groups": ["sap_authoring", "document_assembly", "compliance_checking"]
}
</output>
</example>

<example>
<input>继续</input>
<output>
{
  "complexity": "medium",
  "skip_memory": false,
  "is_follow_up": true,
  "wants_to_stop": false,
  "relevant_skill_groups": ["workflow_control", "sap_authoring", "document_assembly", "compliance_checking"]
}
</output>
</example>

<example>
<input>修改样本量计算部分，使用 Farrington-Manning 方法</input>
<output>
{
  "complexity": "medium",
  "skip_memory": false,
  "is_follow_up": true,
  "wants_to_stop": false,
  "relevant_skill_groups": ["sap_authoring", "document_assembly", "compliance_checking"]
}
</output>
</example>

<example>
<input>不用做了，取消吧</input>
<output>
{
  "complexity": "simple",
  "skip_memory": false,
  "is_follow_up": false,
  "wants_to_stop": true,
  "relevant_skill_groups": ["workflow_control"]
}
</output>
</example>

<example>
<input>Phase II</input>
<output>
{
  "complexity": "simple",
  "skip_memory": false,
  "is_follow_up": true,
  "wants_to_stop": false,
  "relevant_skill_groups": ["workflow_control"]
}
</output>
</example>

<example>
<input>重新开始</input>
<output>
{
  "complexity": "complex",
  "skip_memory": true,
  "is_follow_up": false,
  "wants_to_stop": false,
  "relevant_skill_groups": ["document_parsing", "sap_authoring", "code_generation", "document_assembly", "compliance_checking"]
}
</output>
</example>

<example>
<input>好的，用默认值开始</input>
<output>
{
  "complexity": "complex",
  "skip_memory": false,
  "is_follow_up": true,
  "wants_to_stop": false,
  "relevant_skill_groups": ["document_parsing", "sap_authoring", "code_generation", "document_assembly", "compliance_checking"]
}
</output>
</example>

## 重要说明

- 所有布尔字段默认为 `false`，除非有明确证据支持设为 `true`。  
- `relevant_skill_groups` 宁多勿漏，只要可能涉及即包含。  
- 复杂度判断以实际执行的 Skill 步骤数为准，而非用户语句长度。  
- “继续”“恢复”等指令因需检测多个 scratchpad 文件状态，视为 medium。  
- 任何涉及内容修改、重生成、重组装的操作，均需包含 `document_assembly` 和 `compliance_checking`。