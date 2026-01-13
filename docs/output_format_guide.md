# 输出格式指南

## 概述

ZenFlux Agent 支持多种输出格式，并提供 JSON 格式的 Schema 校验功能。

## 支持的输出格式

| 格式 | 说明 | 使用场景 |
|------|------|---------|
| `text` | 纯文本 | 简单对话、日志输出 |
| `markdown` | Markdown 格式（默认） | 富文本展示、文档生成 |
| `json` | JSON 格式 | API 集成、结构化数据 |
| `html` | HTML 格式（待扩展） | 网页展示 |

---

## 配置方式

### 1. 全局配置（config.yaml）

```yaml
advanced:
  output_formatter:
    enabled: true
    default_format: "json"  # text/markdown/json/html
    
    # JSON 输出配置
    json_schema:
      type: "object"
      properties:
        status:
          type: "string"
          enum: ["success", "error"]
        data:
          type: "object"
        message:
          type: "string"
      required: ["status"]
    
    strict_json_validation: false  # true: 不通过抛出错误，false: 警告
    json_ensure_ascii: false       # 支持中文
    json_indent: 2                 # 缩进空格数
    
    # 其他配置
    code_highlighting: true
    max_output_length: 50000
```

### 2. 运行时指定（API 请求）

```python
# HTTP API 请求
{
  "message": "生成一个用户信息",
  "session_id": "test_session",
  "variables": {
    "output_format": "json"  # 覆盖默认配置
  }
}
```

```python
# 直接调用 Agent
async for event in agent.chat(
    messages=[{"role": "user", "content": "生成用户信息"}],
    session_id="test_session",
    variables={"output_format": "json"}
):
    print(event)
```

---

## JSON 格式输出

### 基本用法

#### 配置 JSON Schema

```yaml
advanced:
  output_formatter:
    default_format: "json"
    json_schema:
      type: "object"
      properties:
        name:
          type: "string"
          description: "用户姓名"
        age:
          type: "integer"
          minimum: 0
          maximum: 150
        email:
          type: "string"
          format: "email"
        tags:
          type: "array"
          items:
            type: "string"
      required: ["name", "email"]
```

#### System Prompt 引导

在 `prompt.md` 中添加输出格式说明：

```markdown
## 输出格式要求

请按照以下 JSON 格式返回结果：

```json
{
  "name": "张三",
  "age": 25,
  "email": "zhangsan@example.com",
  "tags": ["developer", "python"]
}
```

**重要**：
- 必须是有效的 JSON 格式
- 必须包含 `name` 和 `email` 字段
- `age` 必须是 0-150 之间的整数
```

### 智能 JSON 提取

OutputFormatter 会自动从 LLM 响应中提取 JSON：

**策略 1**：直接解析整个响应
```
{"name": "张三", "age": 25}
```

**策略 2**：从 Markdown 代码块提取
```markdown
这是用户信息：

```json
{"name": "张三", "age": 25}
```
```

**策略 3**：从文本中查找 JSON 对象
```
用户信息如下：{"name": "张三", "age": 25}，已生成完毕。
```

**策略 4**：包装为对象（兜底）
```
张三，25岁
```
→ 转换为：
```json
{"content": "张三，25岁", "format": "raw_text"}
```

### JSON Schema 校验

#### 严格模式（strict_json_validation: true）

```yaml
advanced:
  output_formatter:
    strict_json_validation: true
```

- 校验不通过 → 抛出 `JSONValidationError`
- Agent 流程中断
- 适用于：API 集成、严格的数据管道

#### 宽松模式（strict_json_validation: false，默认）

- 校验不通过 → 记录警告
- Agent 继续执行
- 适用于：对话场景、容错性要求高的场景

---

## 使用示例

### 示例 1：简单对话（默认 markdown）

**config.yaml**
```yaml
advanced:
  output_formatter:
    default_format: "markdown"
```

**用户请求**
```
介绍一下 Python
```

**Agent 输出**
```markdown
# Python 编程语言

Python 是一种**高级编程语言**，特点包括：
- 简洁易读
- 功能强大
- 生态丰富

## 示例代码
```python
print("Hello, World!")
```
```

---

### 示例 2：结构化数据（JSON 格式）

**config.yaml**
```yaml
advanced:
  output_formatter:
    default_format: "json"
    json_schema:
      type: "object"
      properties:
        users:
          type: "array"
          items:
            type: "object"
            properties:
              name: {type: "string"}
              role: {type: "string"}
      required: ["users"]
```

**System Prompt**
```markdown
你是一个用户管理助手。当用户请求生成用户列表时，返回 JSON 格式：

```json
{
  "users": [
    {"name": "张三", "role": "admin"},
    {"name": "李四", "role": "user"}
  ]
}
```
```

**用户请求**
```
生成 2 个测试用户
```

**Agent 输出**
```json
{
  "users": [
    {"name": "测试用户1", "role": "admin"},
    {"name": "测试用户2", "role": "user"}
  ]
}
```

---

### 示例 3：API 集成（严格 JSON 校验）

**config.yaml**
```yaml
advanced:
  output_formatter:
    default_format: "json"
    strict_json_validation: true
    json_schema:
      type: "object"
      properties:
        status:
          type: "string"
          enum: ["success", "error", "pending"]
        data:
          type: "object"
        error_message:
          type: "string"
      required: ["status"]
```

**用户请求**
```
处理订单 12345
```

**Agent 输出（成功）**
```json
{
  "status": "success",
  "data": {
    "order_id": "12345",
    "processed_at": "2026-01-13T10:30:00Z"
  }
}
```

**Agent 输出（失败）**
```json
{
  "status": "error",
  "error_message": "订单 12345 不存在"
}
```

---

## 编程接口

### 直接使用 OutputFormatter

```python
from core.output import OutputFormatter

# 创建格式化器
formatter = OutputFormatter(
    default_format="json",
    json_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"}
        },
        "required": ["name"]
    },
    strict_json_validation=False
)

# 格式化输出
result = formatter.format(
    content='{"name": "张三", "age": 25}',
    format="json"
)
print(result)
# {"name": "张三", "age": 25}
```

### 在 Agent 中使用

```python
from core.agent import SimpleAgent

# Agent 初始化时会根据 Schema 配置自动创建 OutputFormatter
agent = SimpleAgent(
    schema=agent_schema,  # 包含 output_formatter 配置
    event_manager=event_manager
)

# Agent.chat() 会自动使用 OutputFormatter 格式化最终输出
async for event in agent.chat(
    messages=[{"role": "user", "content": "生成用户信息"}],
    session_id="test_session",
    variables={"output_format": "json"}
):
    print(event)
```

---

## 最佳实践

### 1. System Prompt 引导

在 `prompt.md` 中明确输出格式要求：

```markdown
## 输出格式规范

**重要**：所有响应必须是 JSON 格式，格式如下：

```json
{
  "status": "success",
  "data": {...},
  "message": "操作完成"
}
```

不要输出额外的文字说明，只输出 JSON 对象。
```

### 2. Few-shot 示例

提供输出示例：

```markdown
## 输出示例

用户：生成一个用户

助手：
```json
{"name": "张三", "age": 25, "email": "zhangsan@example.com"}
```

用户：生成两个用户

助手：
```json
{
  "users": [
    {"name": "张三", "age": 25},
    {"name": "李四", "age": 30}
  ]
}
```
```

### 3. 错误处理

```python
from core.output import OutputFormatter, JSONValidationError

formatter = OutputFormatter(
    json_schema={...},
    strict_json_validation=True
)

try:
    result = formatter.format(content=llm_output, format="json")
except JSONValidationError as e:
    logger.error(f"JSON 校验失败: {e}")
    # 降级处理
    result = formatter.format(content=llm_output, format="text")
```

### 4. 动态 Schema

根据用户请求动态设置 JSON Schema：

```python
# 用户请求生成用户列表
user_list_schema = {
    "type": "object",
    "properties": {
        "users": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string", "format": "email"}
                }
            }
        }
    }
}

formatter = OutputFormatter(json_schema=user_list_schema)
```

---

## 故障排除

### 问题 1：JSON 校验失败

**症状**：
```
❌ JSON 校验失败: 'name' is a required property
```

**解决方案**：
1. 检查 System Prompt 是否明确要求 JSON 格式
2. 检查 Few-shot 示例是否正确
3. 降低 `strict_json_validation` 为 `false`
4. 简化 JSON Schema

### 问题 2：无法提取 JSON

**症状**：
```
⚠️ 无法从文本提取 JSON，包装为对象
```

**解决方案**：
1. 在 System Prompt 中强调"**只输出 JSON 对象**"
2. 使用 Markdown 代码块包裹 JSON
3. 检查 LLM 输出是否被截断

### 问题 3：输出超长

**症状**：
```
⚠️ 输出超出最大长度 (60000 > 50000)，将被截断
```

**解决方案**：
```yaml
advanced:
  output_formatter:
    max_output_length: 100000  # 调大限制
```

---

## 参考

- [JSON Schema 官方文档](https://json-schema.org/)
- [Python jsonschema 库](https://python-jsonschema.readthedocs.io/)
- [架构文档](./architecture/00-ARCHITECTURE-OVERVIEW.md)
