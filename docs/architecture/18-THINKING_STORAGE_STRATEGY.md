# Thinking 存储和 RVR 循环策略

> **更新日期**: 2025-01-01
>
> **重要变更**: 本文档已更新为新的存储策略。thinking 现在完整保存在 `content` 字段中，而非 `status.description`。

## 设计目标

在 Extended Thinking + Tool Use 场景下，既要保证 Claude API 的正确调用（需要 thinking + signature），又要让数据库存储完整、UI 展示友好。

## 核心原则

根据 [Claude 官方文档](https://docs.anthropic.com/en/docs/build-with-claude/extended-thinking)：

> **在使用 tools + extended thinking 时，需要把 thinking blocks（包含 signature）回传给 API**

因此，我们的新策略是：
- **数据库**：完整存储 thinking block（包含 thinking 文本 + signature）在 `content` 字段中
- **RVR 循环**：直接使用 content 中的 thinking block，无需额外处理
- **status**：纯状态字段，不再混入内容

## 数据库存储结构

### Message 表

```json
{
  "id": "msg_xxx",
  "conversation_id": "conv_xxx",
  "role": "assistant",
  
  // content 完整存储所有内容块（thinking 放在最前面）
  "content": [
    {
      "type": "thinking",
      "thinking": "让我分析一下这个需求:\n1. 用户想要生成一个关于 AI 的 PPT\n2. 需要确定 PPT 的结构...",
      "signature": "EqQBCgIYAhIM..."  // Claude 的加密签名
    },
    {"type": "text", "text": "好的，让我帮你生成一个 PPT..."},
    {"type": "tool_use", "id": "toolu_xxx", "name": "slidespeak_render", "input": {...}},
    {"type": "tool_result", "tool_use_id": "toolu_xxx", "content": "..."}
  ],
  
  // status 只存状态信息，不混入内容
  "status": {
    "action": "completed",     // 状态: completed/stopped/failed
    "has_thinking": true,      // 是否包含 thinking
    "blocks_count": 4          // 内容块数量
  },
  
  // metadata 存储其他元数据
  "metadata": {
    "session_id": "sess_xxx",
    "model": "claude-sonnet-4-5-20250929",
    "usage": {"input_tokens": 1500, "output_tokens": 250},
    "completed_at": "2025-01-01T12:00:00Z"
  }
}
```

## 新设计的优点

1. **完整性**：thinking 内容不再被截断，完整保存
2. **符合语义**：`status` 只表示状态，`content` 存储内容
3. **RVR 兼容**：signature 完整保存，后续调用 Claude API 无需额外处理
4. **前端友好**：从 content 中提取 thinking 和 text，逻辑清晰

## 前端处理

### 提取 thinking 内容

```javascript
// 从 content 中提取 thinking
function extractThinkingFromContent(content) {
  if (Array.isArray(content)) {
    const thinkingBlock = content.find(block => block.type === 'thinking')
    return thinkingBlock?.thinking || ''
  }
  return ''
}

// 从 content 中提取文本内容
function extractTextFromContent(content) {
  if (Array.isArray(content)) {
    const textBlocks = content.filter(block => block.type === 'text')
    return textBlocks.map(block => block.text).join('\n')
  }
  return String(content)
}
```

### 加载历史消息

```javascript
// 加载历史消息时
messages.value = result.messages.map(msg => ({
  id: msg.id,
  role: msg.role,
  content: extractTextFromContent(msg.content),
  thinking: extractThinkingFromContent(msg.content),  // 从 content 提取
  timestamp: new Date(msg.created_at)
}))
```

### 流式消息处理

```javascript
// 流式消息时，thinking 通过 content_delta 事件累积
if (deltaType === 'thinking' && deltaText) {
  assistantMessage.thinking += deltaText
} else if (deltaType === 'text' && deltaText) {
  assistantMessage.content += deltaText
}
```

## 后端处理

### ChatEventHandler.finalize()

```python
async def finalize(self, agent=None) -> None:
    """
    最终化：将所有累积的内容保存到数据库
    
    Content 结构：
    [
        {"type": "thinking", "thinking": "...", "signature": "..."},  # 完整保存
        {"type": "text", "text": "..."},
        {"type": "tool_use", ...},
        {"type": "tool_result", ...}
    ]
    
    Status 结构（纯状态）：
    {
        "action": "completed",
        "has_thinking": true,
        "blocks_count": 5
    }
    """
    # 构建完整的 content（thinking 放在最前面）
    final_blocks = []
    
    # 1. thinking block 放在最前面（完整保存，不截断）
    if self.thinking_block:
        final_blocks.append(self.thinking_block)
    
    # 2. 其他内容块
    final_blocks.extend(self.content_blocks)
    
    # status 只表示状态
    final_status = {
        "action": "completed",
        "has_thinking": self.thinking_block is not None,
        "blocks_count": len(final_blocks)
    }
```

## RVR 循环

### Context 加载

```python
# core/context/conversation.py

def _convert_to_agent_format(self, db_messages):
    """
    将数据库消息转换为 Agent 格式
    
    content 中包含所有 blocks：thinking/text/tool_use/tool_result
    RVR 循环中直接使用 content 中的 thinking + signature
    """
    agent_messages = []
    
    for msg in db_messages:
        content = msg.content
        
        if isinstance(content, str):
            try:
                content_array = json.loads(content)
                if isinstance(content_array, list):
                    # 直接使用 content 数组（已经是 Claude API 格式）
                    # thinking block 已经包含 signature
                    content = content_array
            except json.JSONDecodeError:
                pass
        
        agent_messages.append({
            "role": msg.role,
            "content": content
        })
    
    return agent_messages
```

## 迁移说明

如果有旧数据使用 `status.description` 存储 thinking，可以通过以下方式迁移：

```python
# 迁移脚本示例
async def migrate_thinking_to_content():
    """将 status.description 中的 thinking 迁移到 content"""
    messages = await message_repo.get_all()
    
    for msg in messages:
        status = json.loads(msg.status or '{}')
        content = json.loads(msg.content or '[]')
        
        # 如果 status 中有 thinking（旧格式）
        if status.get('action') == 'think' and status.get('description'):
            thinking_text = status['description']
            
            # 添加到 content 最前面（注意：旧数据可能没有 signature）
            content.insert(0, {
                "type": "thinking",
                "thinking": thinking_text,
                "signature": None  # 旧数据没有 signature，Extended Thinking 可能受影响
            })
            
            # 更新 status
            new_status = {
                "action": "completed",
                "has_thinking": True,
                "blocks_count": len(content)
  }
            
            await message_repo.update(
                message_id=msg.id,
                content=json.dumps(content, ensure_ascii=False),
                status=json.dumps(new_status, ensure_ascii=False)
            )
```

## 总结

| 字段 | 旧设计 | 新设计 |
|------|--------|--------|
| content | 不含 thinking | 完整存储 thinking（含 signature） |
| status | 混入 thinking 内容 | 纯状态信息 |
| 截断 | thinking 可能被截断 | 完整保存 |
| 前端读取 | `status.description` | `content` 中的 thinking block |
| RVR 循环 | 需要从 raw_content 获取 | 直接使用 content |
