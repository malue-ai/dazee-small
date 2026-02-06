# 输出格式指南

## 概述

**重要说明**：
- **Agent 层**：只负责流式输出 next token，不做格式化/校验
- **API/Service 层**：使用 `OutputFormatter` 工具类进行格式化（按需）
- **JSON 校验**：使用 Pydantic 模型（Python 主流方案）

`OutputFormatter` 是一个独立的工具类，供 API 层、Service 层使用，用于：
- 格式化 Agent 的原始输出（text/markdown/json/html）
- JSON 格式的 Pydantic 校验
- 输出长度限制

## 调用路径

```
用户请求
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  API 层（routers/chat.py 或 grpc_server/chat_servicer.py）│
│  • 接收用户请求                                          │
│  • 解析 output_format 参数（可选）                      │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  Service 层（services/chat_service.py）                 │
│  • 调用 Agent.chat() 获取流式输出                        │
│  • 累积最终内容                                          │
│  • 【可选】使用 OutputFormatter 格式化                  │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  Agent 层（core/agent/simple/simple_agent.py）                  │
│  • 流式输出 next token                                   │
│  • 不做格式化/校验                                       │
│  • 保持职责单一                                          │
└─────────────────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  Service 层（后处理）                                    │
│  • 如果 output_format="json"，使用 OutputFormatter      │
│  • 校验 JSON 格式（Pydantic）                           │
│  • 返回格式化后的内容                                    │
└─────────────────────────────────────────────────────────┘
```

**关键点**：
- Agent 只负责生成内容，不做后处理
- 格式化在 Service 层按需进行
- `OutputFormatter` 是可选工具，不是 Agent 的依赖

## 支持的输出格式

| 格式 | 说明 | 使用场景 |
|------|------|---------|
| `text` | 纯文本 | 简单对话、日志输出 |
| `markdown` | Markdown 格式（默认） | 富文本展示、文档生成 |
| `json` | JSON 格式 | API 集成、结构化数据 |
| `html` | HTML 格式（待扩展） | 网页展示 |

---

## 配置方式

### 1. config.yaml 配置（推荐，供 Service 层使用）

**配置作用**：
- ✅ Agent Schema 会读取这些配置
- ✅ Service 层通过 `agent.schema.output_formatter` 访问配置
- ✅ 按需创建 OutputFormatter 进行格式化
- ❌ Agent 本身不使用这些配置（保持单一职责）

**使用方式**：
```python
# Service 层读取配置
formatter_config = agent.schema.output_formatter
if formatter_config.enabled:
    formatter = OutputFormatter(config=formatter_config)
    formatted = formatter.format(content, format="json")
```

```yaml
advanced:
  output_formatter:
    enabled: true
    default_format: "text"           # 默认文本格式（最简单）
    code_highlighting: true
    
    # JSON 输出配置（仅当 API 层需要 JSON 时使用）
    # json_model_name: "SimpleResponse"  # 使用内置 Pydantic 模型
    # json_schema:                        # 或使用动态 Schema 定义
    #   status: {type: "str", required: true}
    #   message: {type: "str", default: ""}
    #   data: {type: "any", default: null}
    # strict_json_validation: false     # true=校验不通过则报错
    json_ensure_ascii: false
    json_indent: 2
```

**设计原则**：
- Agent = 流式输出，不做后处理
- API 层 = 按需使用 `OutputFormatter` 格式化
- 配置保留在 Schema 中，但 Agent 不读取

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

### 在 API/Service 层使用（推荐）

**重要**：Agent 只负责流式输出 next token，不做格式化/校验。格式化应在 API 层处理。

```python
from core.output import OutputFormatter
from core.agent import SimpleAgent

# 1. Agent 初始化（不包含格式化逻辑）
agent = SimpleAgent(
    schema=agent_schema,
    event_manager=event_manager
)

# 2. Agent 流式输出（原始内容）
final_content = ""
async for event in agent.chat(
    messages=[{"role": "user", "content": "生成用户信息"}],
    session_id="test_session"
):
    if event.get("type") == "message_delta":
        final_content += event.get("delta", "")

# 3. API 层格式化（按需使用 OutputFormatter）
formatter = OutputFormatter(
    default_format="json",
    model_name="SimpleResponse",  # 使用内置 Pydantic 模型
    strict_json_validation=True
)

formatted_output = formatter.format(
    content=final_content,
    format="json"
)

print(formatted_output)
# {"status": "success", "message": "...", "data": {...}}
```

### 在 Service 层使用 Agent Schema 配置（推荐）

```python
# services/chat_service.py
from core.output import OutputFormatter

class ChatService:
    def get_output_formatter(self, agent: SimpleAgent) -> Optional[OutputFormatter]:
        """
        从 Agent Schema 获取 OutputFormatter
        
        这样运营人员可以通过 config.yaml 控制输出格式：
        - output_formatter.enabled: true/false
        - output_formatter.default_format: text/markdown/json
        - output_formatter.json_model_name: SimpleResponse
        """
        if not agent.schema or not agent.schema.output_formatter.enabled:
            return None
        
        # 从 Agent Schema 读取配置
        formatter_config = agent.schema.output_formatter
        return OutputFormatter(config=formatter_config)
    
    async def send_message_with_format(
        self, 
        message: str, 
        agent: SimpleAgent,
        output_format: Optional[str] = None
    ) -> str:
        """发送消息并根据配置格式化输出"""
        # 1. Agent 执行（流式输出）
        final_content = ""
        async for event in agent.chat(...):
            if event.get("type") == "message_delta":
                final_content += event.get("delta", "")
        
        # 2. 获取 Agent 的 OutputFormatter（从 config.yaml 配置）
        formatter = self.get_output_formatter(agent)
        
        # 3. 如果配置了格式化器，使用它格式化输出
        if formatter:
            format_type = output_format or formatter.default_format
            return formatter.format(final_content, format=format_type)
        
        # 4. 否则直接返回原始内容
        return final_content
```

**设计优势**：
- ✅ 配置驱动：运营人员通过 `config.yaml` 控制格式
- ✅ 按需格式化：只在需要时创建和使用 OutputFormatter
- ✅ Agent 解耦：Agent 只负责生成内容，不做格式化
- ✅ 灵活性：支持运行时覆盖格式（`output_format` 参数）

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
