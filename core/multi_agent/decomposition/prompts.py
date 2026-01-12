"""
任务分解 Prompt

Few-shot 示例引导 LLM 进行任务分解

设计原则（Prompt-First）：
- 规则写在 Prompt 里，不写在代码里
- 使用 Few-shot 教会 LLM 分解模式
- 代码只做调用和解析
"""

# ==================== 任务分解 Few-shot ====================

DECOMPOSITION_FEW_SHOT = """
## 你的任务

将用户的复杂任务分解为可独立执行的子任务。每个子任务应该：
1. **独立性**：尽可能无依赖，最大化并行度
2. **原子性**：单个 Worker 可在上下文窗口内完成
3. **可聚合性**：输出格式统一，便于最终合并

## 输出格式

输出 JSON 格式：
```json
{
  "reasoning": "任务分解推理过程...",
  "sub_tasks": [
    {
      "id": "task-1",
      "action": "子任务描述",
      "specialization": "worker类型",
      "dependencies": [],
      "estimated_time": 300,
      "can_parallel": true
    }
  ],
  "parallelizable_groups": [["task-1", "task-2"], ["task-3"]]
}
```

## Worker 类型（specialization）

- `research`: 信息研究、竞品分析、市场调研
- `document`: 文档生成、PPT、报告撰写
- `data_analysis`: 数据分析、统计、可视化
- `code`: 代码编写、重构、测试
- `general`: 通用任务

## Few-shot 示例

### 示例 1：多维度研究

<example>
<user_task>研究全球 Top 5 云计算公司的 AI 战略</user_task>
<decomposition>
{
  "reasoning": "这是一个多实体、多维度的研究任务。5 家公司可以并行研究，每家公司的 AI 战略是独立的。最后需要汇总对比。",
  "sub_tasks": [
    {
      "id": "task-1",
      "action": "研究 AWS 的 AI 战略：产品线、投资并购、技术路线",
      "specialization": "research",
      "dependencies": [],
      "estimated_time": 600,
      "can_parallel": true
    },
    {
      "id": "task-2", 
      "action": "研究 Azure 的 AI 战略：产品线、投资并购、技术路线",
      "specialization": "research",
      "dependencies": [],
      "estimated_time": 600,
      "can_parallel": true
    },
    {
      "id": "task-3",
      "action": "研究 Google Cloud 的 AI 战略：产品线、投资并购、技术路线",
      "specialization": "research",
      "dependencies": [],
      "estimated_time": 600,
      "can_parallel": true
    },
    {
      "id": "task-4",
      "action": "研究阿里云的 AI 战略：产品线、投资并购、技术路线",
      "specialization": "research",
      "dependencies": [],
      "estimated_time": 600,
      "can_parallel": true
    },
    {
      "id": "task-5",
      "action": "研究腾讯云的 AI 战略：产品线、投资并购、技术路线",
      "specialization": "research",
      "dependencies": [],
      "estimated_time": 600,
      "can_parallel": true
    },
    {
      "id": "task-6",
      "action": "汇总 5 家公司 AI 战略对比分析报告",
      "specialization": "document",
      "dependencies": ["task-1", "task-2", "task-3", "task-4", "task-5"],
      "estimated_time": 900,
      "can_parallel": false
    }
  ],
  "parallelizable_groups": [
    ["task-1", "task-2", "task-3", "task-4", "task-5"],
    ["task-6"]
  ]
}
</decomposition>
</example>

### 示例 2：代码重构 + 测试

<example>
<user_task>重构用户认证模块，同时优化代码结构并补充单元测试</user_task>
<decomposition>
{
  "reasoning": "重构是核心任务，必须先完成。测试依赖重构后的代码。优化代码结构可以和重构并行。",
  "sub_tasks": [
    {
      "id": "task-1",
      "action": "分析现有认证模块代码，识别重构点和技术债务",
      "specialization": "code",
      "dependencies": [],
      "estimated_time": 300,
      "can_parallel": true
    },
    {
      "id": "task-2",
      "action": "重构认证模块核心逻辑：登录、注册、Token 管理",
      "specialization": "code",
      "dependencies": ["task-1"],
      "estimated_time": 600,
      "can_parallel": false
    },
    {
      "id": "task-3",
      "action": "优化代码结构：拆分模块、提取公共方法",
      "specialization": "code",
      "dependencies": ["task-1"],
      "estimated_time": 400,
      "can_parallel": true
    },
    {
      "id": "task-4",
      "action": "编写认证模块单元测试：覆盖核心场景",
      "specialization": "code",
      "dependencies": ["task-2"],
      "estimated_time": 500,
      "can_parallel": false
    }
  ],
  "parallelizable_groups": [
    ["task-1"],
    ["task-2", "task-3"],
    ["task-4"]
  ]
}
</decomposition>
</example>

### 示例 3：数据分析 + 报告

<example>
<user_task>分析上季度销售数据，生成周报 PPT 和详细分析报告</user_task>
<decomposition>
{
  "reasoning": "数据分析是基础，PPT 和详细报告可以基于分析结果并行生成。",
  "sub_tasks": [
    {
      "id": "task-1",
      "action": "从数据库提取上季度销售数据，进行清洗和预处理",
      "specialization": "data_analysis",
      "dependencies": [],
      "estimated_time": 300,
      "can_parallel": true
    },
    {
      "id": "task-2",
      "action": "销售数据统计分析：趋势、同比环比、TOP 产品",
      "specialization": "data_analysis",
      "dependencies": ["task-1"],
      "estimated_time": 400,
      "can_parallel": false
    },
    {
      "id": "task-3",
      "action": "生成销售周报 PPT：关键数据、图表、洞察",
      "specialization": "document",
      "dependencies": ["task-2"],
      "estimated_time": 600,
      "can_parallel": true
    },
    {
      "id": "task-4",
      "action": "撰写详细销售分析报告：数据解读、建议",
      "specialization": "document",
      "dependencies": ["task-2"],
      "estimated_time": 500,
      "can_parallel": true
    }
  ],
  "parallelizable_groups": [
    ["task-1"],
    ["task-2"],
    ["task-3", "task-4"]
  ]
}
</decomposition>
</example>

### 示例 4：简单任务（不需要分解）

<example>
<user_task>帮我查一下明天北京的天气</user_task>
<decomposition>
{
  "reasoning": "这是一个简单的单一查询任务，不需要分解为多个子任务。",
  "sub_tasks": [
    {
      "id": "task-1",
      "action": "查询明天北京的天气预报",
      "specialization": "general",
      "dependencies": [],
      "estimated_time": 30,
      "can_parallel": true
    }
  ],
  "parallelizable_groups": [["task-1"]]
}
</decomposition>
</example>

## 现在请分解以下任务

<user_task>{user_query}</user_task>

请输出 JSON 格式的分解结果：
"""


# ==================== Worker 系统提示词生成 Few-shot ====================

WORKER_PROMPT_FEW_SHOT = """
## 你的任务

根据子任务描述，生成该 Worker 的系统提示词。提示词应该：
1. **专业化**：突出该 Worker 的专业领域
2. **具体化**：针对具体任务给出指导
3. **可操作**：包含明确的执行步骤或方法论

## 输出格式

输出 JSON 格式：
```json
{
  "reasoning": "生成提示词的推理过程...",
  "system_prompt": "生成的系统提示词..."
}
```

## Few-shot 示例

### 示例 1：Research Worker

<example>
<sub_task>
{
  "action": "研究 AWS 的 AI 战略：产品线、投资并购、技术路线",
  "specialization": "research"
}
</sub_task>
<generated_prompt>
{
  "reasoning": "这是一个竞品研究任务，需要系统性地收集和分析 AWS 的 AI 相关信息。Worker 需要关注三个维度：产品线、投资并购、技术路线。",
  "system_prompt": "你是一位资深的科技行业研究分析师，专注于云计算和 AI 领域的竞品研究。\\n\\n## 当前任务\\n研究 Amazon Web Services (AWS) 的 AI 战略布局。\\n\\n## 研究维度\\n1. **AI 产品线**：SageMaker、Bedrock、Rekognition 等核心 AI 服务\\n2. **投资并购**：近年 AI 领域的收购和战略投资\\n3. **技术路线**：自研芯片 (Trainium/Inferentia)、模型合作 (Anthropic) 等\\n\\n## 输出要求\\n- 信息来源要可靠（官方公告、财报、权威媒体）\\n- 数据要有时间标注\\n- 分析要有洞察，不只是罗列事实"
}
</generated_prompt>
</example>

### 示例 2：Document Worker

<example>
<sub_task>
{
  "action": "生成销售周报 PPT：关键数据、图表、洞察",
  "specialization": "document"
}
</sub_task>
<generated_prompt>
{
  "reasoning": "这是一个 PPT 生成任务，需要将数据分析结果转化为可视化的演示文稿。重点是数据可视化和商业洞察的表达。",
  "system_prompt": "你是一位专业的商业分析师，擅长将数据洞察转化为清晰、有说服力的演示文稿。\\n\\n## 当前任务\\n基于销售数据分析结果，生成销售周报 PPT。\\n\\n## PPT 结构建议\\n1. **Executive Summary**：关键指标一页纸\\n2. **销售趋势**：时间序列图表\\n3. **产品分析**：TOP 产品、增长最快产品\\n4. **区域分析**：各区域表现对比\\n5. **洞察与建议**：可执行的行动建议\\n\\n## 设计原则\\n- 每页一个核心观点\\n- 数据要有对比（同比、环比）\\n- 使用图表而非表格\\n- 洞察要可执行"
}
</generated_prompt>
</example>

### 示例 3：Code Worker

<example>
<sub_task>
{
  "action": "重构认证模块核心逻辑：登录、注册、Token 管理",
  "specialization": "code"
}
</sub_task>
<generated_prompt>
{
  "reasoning": "这是一个代码重构任务，需要关注代码质量、安全性和可维护性。认证模块是安全敏感的，需要特别注意。",
  "system_prompt": "你是一位资深后端工程师，专注于认证授权系统的设计和实现。\\n\\n## 当前任务\\n重构用户认证模块的核心逻辑。\\n\\n## 重构范围\\n1. **登录逻辑**：密码验证、多因素认证支持\\n2. **注册逻辑**：输入验证、密码强度检查\\n3. **Token 管理**：JWT 生成、刷新、撤销\\n\\n## 重构原则\\n- 遵循 SOLID 原则\\n- 敏感数据加密存储\\n- 防止常见安全漏洞（SQL 注入、XSS）\\n- 添加适当的日志和错误处理\\n\\n## 代码规范\\n- 使用类型注解\\n- 编写文档字符串\\n- 单一职责，小函数"
}
</generated_prompt>
</example>

## 现在请为以下子任务生成系统提示词

<sub_task>
{sub_task}
</sub_task>

请输出 JSON 格式的结果：
"""


# ==================== 结果聚合 Prompt ====================

AGGREGATION_PROMPT = """
## 你的任务

将多个 Worker 的执行结果聚合为最终输出。

## 输入

用户原始任务：{user_query}

各 Worker 执行结果：
{worker_results}

## 输出要求

1. 综合所有 Worker 的结果
2. 消除重复和冲突
3. 按逻辑顺序组织
4. 生成统一、连贯的最终输出

请生成聚合后的结果：
"""
