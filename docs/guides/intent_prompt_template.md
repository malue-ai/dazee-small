# 实例层意图识别提示词模板

V10.0 版本的意图识别系统使用极简 JSON 输出。如果您需要为实例自定义意图识别提示词，请参考此模板。

## 必须输出的字段

```json
{
  "complexity": "simple|medium|complex",
  "agent_type": "rvr|rvr-b|multi",
  "skip_memory": true|false
}
```

## 字段说明

### complexity（复杂度）

| 值 | 含义 | 示例 |
|----|------|------|
| simple | 单步骤，直接回答 | 天气查询、翻译、概念问答 |
| medium | 2-4 步骤，需要少量规划 | 搜索+总结、写函数 |
| complex | 5+ 步骤，需要完整规划 | 系统设计、调研报告 |

### agent_type（执行引擎）

| 值 | 含义 | 示例 |
|----|------|------|
| rvr | 确定性任务，无需重试 | 问答、翻译、简单代码 |
| rvr-b | 可能失败需要重试 | 代码开发、调研、爬虫 |
| multi | 3+ 独立实体并行处理 | Top 5 公司分析、多城市天气 |

### skip_memory（跳过记忆检索）

| 值 | 含义 | 示例 |
|----|------|------|
| true | 客观事实查询 | 天气、汇率、百科知识 |
| false | 可能需要个性化 | 写邮件、推荐、PPT 生成 |

## 模板示例

将以下内容保存为 `instances/<your_agent>/prompt_results/intent_prompt.md`：

```markdown
# 意图分类器

分析用户请求，输出 JSON。

## 输出格式

```json
{
  "complexity": "simple|medium|complex",
  "agent_type": "rvr|rvr-b|multi",
  "skip_memory": true|false
}
```

## 业务场景规则

（在此添加您的业务特定规则）

### complexity 判断

- **simple**: （您的简单任务定义）
- **medium**: （您的中等任务定义）
- **complex**: （您的复杂任务定义）

### agent_type 判断

- **rvr**: （您的 rvr 场景）
- **rvr-b**: （您的 rvr-b 场景）
- **multi**: （您的 multi 场景）

### skip_memory 判断

- **true**: （不需要记忆的场景）
- **false**: （需要记忆的场景）

## Few-Shot 示例

<example>
<query>（您的业务场景 1）</query>
<output>{"complexity": "...", "agent_type": "...", "skip_memory": ...}</output>
</example>

<example>
<query>（您的业务场景 2）</query>
<output>{"complexity": "...", "agent_type": "...", "skip_memory": ...}</output>
</example>

现在分析用户的请求，只输出 JSON：
```

## 迁移指南

如果您有现有的 `intent_prompt.md` 文件，需要进行以下修改：

1. **删除旧字段**：移除 `task_type`, `intent_id`, `intent_name`, `complexity_score`, `needs_plan`, `needs_multi_agent`, `task_dependency_type`, `is_follow_up` 等字段

2. **添加新字段**：只保留 `complexity`, `agent_type`, `skip_memory` 三个字段

3. **更新示例**：将 Few-Shot 示例中的 JSON 输出更新为新格式

### 旧格式示例

```json
{
  "intent_id": 1,
  "intent_name": "系统搭建",
  "task_type": "task_execution",
  "complexity": "complex",
  "complexity_score": 7.5,
  "needs_plan": true,
  "needs_multi_agent": false
}
```

### 新格式示例

```json
{
  "complexity": "complex",
  "agent_type": "rvr-b",
  "skip_memory": false
}
```

## 注意事项

1. **字段必填**：三个字段都是必填的，LLM 必须输出完整的 JSON
2. **不确定时保守**：`agent_type` 不确定选 `rvr`，`skip_memory` 不确定选 `false`
3. **multi 条件**：只有 3+ 个独立实体需要并行处理时才选 `multi`
4. **needs_plan 推断**：代码会从 `complexity` 推断，simple → false，其他 → true
