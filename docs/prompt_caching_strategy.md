# Prompt Caching 策略设计

## 概述

基于 [Claude Prompt Caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) 的多层缓存架构，优化 `prompt_results` 生成的系统提示词成本。

## 核心理念

```
缓存粒度 = 更新频率的倒数

更新越少 → 缓存时间越长 → 成本越低
```

## 缓存架构总览（最终修正版）

### ⚠️ 重要：Claude API 缓存限制

根据 [Claude 官方文档](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)：

```
Claude Prompt Caching 缓存时长：固定 5 分钟
- cache_control: {"type": "ephemeral"}  ✅ 正确格式
- cache_control: {"type": "ephemeral", }  ❌ 不支持自定义 TTL！
```

### 核心原则

```
原则 1：需要重启的内容 = 运行期稳定 → 启用缓存（5分钟内命中率高）
原则 2：基于语义检索的内容 = 每次 query 不同结果不同 → 不能缓存
原则 3：不同 LLM 调用有不同的缓存需求
```

### 两条缓存路径

系统有两个独立的 LLM 调用路径，各有自己的缓存策略：

```
路径 A：意图识别调用（Haiku 4.5）
  → 用于快速分类任务类型和复杂度
  → 缓存策略：意图识别提示词（缓存，5分钟 TTL）

路径 B：主对话调用（Sonnet 4.5）
  → 用于实际任务执行
  → 缓存策略：框架规则（缓存）→ 实例提示词（缓存）→ Skills+工具（缓存）→ 对话历史（不缓存）
```

### 修正历程

**第一次修正**：Layer 2（实例提示词）从不缓存改为缓存
- ❌ 错误假设：运营可以热更新提示词
- ✅ 实际情况：修改 prompt_results 后需要重启 Agent
- ✅ 正确策略：启用缓存（同运行周期内稳定）

**第二次修正**：Layer 4（Mem0 用户画像）明确**不缓存**
- ❌ 错误假设：用户画像短期内稳定
- ✅ 实际情况：Mem0 基于**语义向量匹配**检索，每次 query 不同 → 检索结果不同
- ✅ 正确策略：**不缓存**（缓存会导致使用错误的记忆）

**第三次修正**：意图识别提示词需要独立缓存
- ❌ 错误遗漏：忽略了意图识别有独立的系统提示词
- ✅ 实际情况：intent_prompt 在运行态只读，不会改变（除非重启）
- ✅ 正确策略：启用缓存（与其他运行期稳定内容一致）

**第四次修正**：修正 TTL 参数（根据 Claude 官方文档）
- ❌ 错误实现：使用了 ``（Claude API 不支持）
- ✅ 正确格式：`{"type": "ephemeral"}`（固定 5 分钟）
- ✅ 影响：缓存命中率仍然很高（短期重复请求场景）

```python
# ❌ 错误示例：缓存用户画像
# Query 1: "我喜欢什么运动？" → 检索到运动相关记忆
# Query 2: "我的工作是什么？" → 但使用了缓存的运动记忆！错误！

# ✅ 正确做法：不缓存
# 每次根据当前 query 语义检索相关记忆
```

### 路径 A：意图识别调用（Haiku 4.5，快速分类）

```
┌────────────────────────────────────────────────────────────┐
│            意图识别 LLM 调用的 Prompt 构成                  │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │ 意图识别提示词（缓存（5分钟 TTL））✅ 新增                    │ │
│  │ • 来源：prompt_results/intent_prompt.md              │ │
│  │ • 内容：任务类型定义、复杂度规则、示例               │ │
│  │ • 变更：运营优化后需重启                             │ │
│  │ • 策略：ephemeral cache (cache_control: {"type": "ephemeral"})            │ │
│  │ • 成本：写入 2x，命中 0.1x                           │ │
│  │ • 理由：运行态只读，不会热更新                       │ │
│  │ 📌 cache_control breakpoint                          │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │ 用户查询 + 对话历史（不缓存）                        │ │
│  │ • messages 参数                                      │ │
│  │ • 每次请求都变化                                     │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### 路径 B：主对话调用（Sonnet 4.5，任务执行）

```
┌─────────────────────────────────────────────────────────────────┐
│              主对话 LLM 调用的 System Prompt 构成                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Layer 1: 框架通用规则（缓存（5分钟 TTL））                         │ │
│  │ • 来源：prompts/MEMORY_PROTOCOL.md                         │ │
│  │ • 来源：prompts/fragments/e2b_rules.md                     │ │
│  │ • 变更：框架升级时需重启                                   │ │
│  │ • 策略：ephemeral cache (cache_control: {"type": "ephemeral"})                  │ │
│  │ • 成本：写入 2x，命中 0.1x                                 │ │
│  │ 📌 cache_control breakpoint #1                             │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Layer 2: 实例核心提示词（缓存（5分钟 TTL））                       │ │
│  │ • 来源：prompt_results/{simple|medium|complex}_prompt.md   │ │
│  │ • 内容：角色定义、工作规则、输出格式                       │ │
│  │ • 变更：运营优化后需重启                                   │ │
│  │ • 策略：ephemeral cache (cache_control: {"type": "ephemeral"})                  │ │
│  │ • 成本：写入 2x，命中 0.1x                                 │ │
│  │ 📌 cache_control breakpoint #2                             │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Layer 3: Skills + 工具定义（缓存（5分钟 TTL））                    │ │
│  │ • Skills 元数据                                            │ │
│  │ • 工具能力分类描述                                         │ │
│  │ • 变更：Skills/工具更新后需重启                            │ │
│  │ • 策略：ephemeral cache (cache_control: {"type": "ephemeral"})                  │ │
│  │ • 成本：写入 2x，命中 0.1x                                 │ │
│  │ 📌 cache_control breakpoint #3（最后一个）                │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Layer 4: Mem0 用户画像（不缓存）❌ 修正                    │ │
│  │ • Mem0 基于语义检索，每次 query 不同 → 结果不同           │ │
│  │ • 策略：不缓存（缓存会导致使用错误的记忆）                 │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Layer 5: 当前对话历史（不缓存）                            │ │
│  │ • messages 历史                                            │ │
│  │ • 当前用户输入                                             │ │
│  │ • 每次请求都变化                                           │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 成本对比（最终修正版）

### 场景：单次用户请求完整流程

**流程**：意图识别（Haiku）→ 主对话（Sonnet）

#### 路径 A：意图识别调用（Haiku 4.5）

| 内容 | Token | 缓存策略 | 首次成本 | 命中成本 | 节省 |
|------|-------|---------|---------|---------|------|
| 意图识别提示词 | 5K ✅ | 1h cache | $0.40/MTok × 5K = $0.002 | $0.04/MTok × 5K = $0.0002 | **90%** |
| 用户查询 | 1K | 不缓存 | $0.20/MTok × 1K = $0.0002 | $0.20/MTok × 1K = $0.0002 | 0% |

**小计**（Haiku，写入价 $0.40/MTok，命中价 $0.04/MTok）：
- **首次**：$0.0022 / 请求
- **命中**：$0.0004 / 请求
- **节省**：82% ✅

#### 路径 B：主对话调用（Sonnet 4.5）

| 层级 | 内容 | Token | 缓存策略 | 首次成本 | 命中成本 | 节省 |
|------|------|-------|---------|---------|---------|------|
| Layer 1 | 框架规则 | 30K | 1h cache | $6/MTok × 30K = $0.18 | $0.30/MTok × 30K = $0.009 | **95%** |
| Layer 2 | 实例提示词 | 50K | 1h cache | $6/MTok × 50K = $0.30 | $0.30/MTok × 50K = $0.015 | **95%** |
| Layer 3 | Skills+工具 | 15K | 1h cache | $6/MTok × 15K = $0.09 | $0.30/MTok × 15K = $0.0045 | **95%** |
| Layer 4 | Mem0 画像 | 5K | 不缓存 ❌ | $3/MTok × 5K = $0.015 | $3/MTok × 5K = $0.015 | 0% |
| Layer 5 | 对话历史 | 10K | 不缓存 | $3/MTok × 10K = $0.03 | $3/MTok × 10K = $0.03 | 0% |

**小计**（Sonnet，写入价 $6/MTok，命中价 $0.30/MTok，基础价 $3/MTok）：
- **首次**：$0.18 + $0.30 + $0.09 + $0.015 + $0.03 = **$0.615 / 请求**
- **命中**：$0.009 + $0.015 + $0.0045 + $0.015 + $0.03 = **$0.0735 / 请求**
- **节省**：88% ✅

#### 总成本（意图识别 + 主对话）

| 阶段 | 首次请求 | 完全命中 | 节省比例 |
|-----|---------|---------|---------|
| 意图识别（Haiku） | $0.0022 | $0.0004 | 82% |
| 主对话（Sonnet） | $0.615 | $0.0735 | 88% |
| **总计** | **$0.617** | **$0.074** | **88%** ✅ |

**关键收益**：
- ✅ 意图识别提示词缓存：节省 90%（Haiku）
- ✅ Layer 1-3 使用 1 小时缓存：节省 95%（Sonnet）
- ❌ Mem0 用户画像不能缓存：基于语义检索，每次不同
- ❌ 对话历史不能缓存：每次请求都变化

## 实现策略

### 0. 代码示例总览

#### 路径 A：意图识别调用（IntentAnalyzer）

```python
# core/agent/intent_analyzer.py

async def analyze(self, messages: List[ChatMessage]) -> IntentResult:
    """意图识别（Haiku 4.5 + 提示词缓存）"""
    
    # 获取缓存的意图识别提示词（运行态稳定）
    intent_prompt = self._get_intent_prompt()
    
    # 调用 Haiku，使用提示词缓存
    response = await self.llm.create_message_async(
        model="claude-haiku-4-5-20250929",
        max_tokens=512,
        system=[
            {
                "type": "text",
                "text": intent_prompt,  # 意图识别提示词（~5K tokens）
                "cache_control": {"type": "ephemeral"}  # ✅ 缓存（5分钟 TTL）
            }
        ],
        messages=[
            # 用户查询 + 对话历史（不缓存）
            {"role": "user", "content": "当前用户查询"}
        ]
    )
    
    return self._parse_llm_response(response.content)
```

#### 路径 B：主对话调用（SimpleAgent）

```python
# core/agent/simple_agent.py

def _build_cached_system_prompt(
    self, 
    complexity: TaskComplexity,
    user_profile: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    构建主对话的多层缓存 system prompt（Sonnet 4.5）
    
    关键原则：需要重启的内容 = 运行期稳定 = 缓存（5分钟 TTL）
    """
    system_blocks = []
    
    # Layer 1: 框架通用规则（缓存（5分钟 TTL））
    framework_rules = self._get_framework_rules()
    system_blocks.append({
        "type": "text",
        "text": framework_rules,
        "cache_control": {"type": "ephemeral"}
    })
    
    # Layer 2: 实例核心提示词（缓存（5分钟 TTL））
    instance_prompt = self._prompt_cache.get_system_prompt(complexity)
    system_blocks.append({
        "type": "text",
        "text": instance_prompt,
        "cache_control": {"type": "ephemeral"}
    })
    
    # Layer 3: Skills + 工具定义（缓存（5分钟 TTL））
    tools_context = self._build_tools_context()
    if tools_context:
        system_blocks.append({
            "type": "text",
            "text": tools_context,
            "cache_control": {"type": "ephemeral"}  # 最后一个缓存断点
        })
    
    # Layer 4: Mem0 用户画像（不缓存）❌
    # 原因：基于语义检索，每次 query 不同 → 结果不同
    if user_profile:
        system_blocks.append({
            "type": "text",
            "text": f"# 用户画像\n{user_profile}"
            # 不添加 cache_control
        })
    
    # Layer 5: 对话历史（不缓存，在 messages 参数中）
    
    return system_blocks
```

### 1. prompt_results 生成时标记

在 `PromptResultsWriter` 输出时添加缓存边界元数据：

```yaml
# prompt_results/_metadata.json
{
  "cache_strategy": {
    "layer1_framework": {
      ,
      "fragments": [
        "prompts/MEMORY_PROTOCOL.md",
        "prompts/fragments/e2b_rules.md"
      ]
    },
    "layer2_instance": {
      ,
      "files": [
        "simple_prompt.md",
        "medium_prompt.md",
        "complex_prompt.md"
      ]
    },
    "layer3_dynamic": {
      ,
      "includes": ["user_profile", "tools", "skills"]
    }
  }
}
```

### 2. SimpleAgent 运行时组装（修正版）

```python
# core/agent/simple_agent.py

def _build_cached_system_prompt(
    self, 
    complexity: TaskComplexity,
    user_profile: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    构建五层缓存的 system prompt（修正版）
    
    关键原则：需要重启的内容 = 运行期稳定 = 缓存（5分钟 TTL）
    
    Returns:
        List[Dict] - Claude API 的 system blocks 格式
    """
    system_blocks = []
    
    # Layer 1: 框架通用规则（缓存（5分钟 TTL））
    # 框架升级 → 重启 → 运行期稳定
    framework_rules = self._get_framework_rules()
    system_blocks.append({
        "type": "text",
        "text": framework_rules,
        "cache_control": {"type": "ephemeral"}
    })
    
    # Layer 2: 实例核心提示词（缓存（5分钟 TTL））✅ 修正
    # 运营优化 → 重启 → 运行期稳定
    instance_prompt = self._prompt_cache.get_system_prompt(complexity)
    system_blocks.append({
        "type": "text",
        "text": instance_prompt,
        "cache_control": {"type": "ephemeral"}  # 改为 1 小时
    })
    
    # Layer 3: Skills + 工具定义（缓存（5分钟 TTL））✅ 修正
    # Skills/工具更新 → 重启 → 运行期稳定
    tools_context = self._build_tools_context()
    if tools_context:
        system_blocks.append({
            "type": "text",
            "text": tools_context,
            "cache_control": {"type": "ephemeral"}  # 1 小时缓存
        })
    
    # Layer 4: Mem0 用户画像（5分钟缓存）
    # 会话内可能更新 → 无需重启 → 短期缓存
    if user_profile:
        system_blocks.append({
            "type": "text",
            "text": f"# 用户画像\n{user_profile}",
            "cache_control": {"type": "ephemeral"}  # 5 分钟缓存
        })
    
    # Layer 5: 对话历史（不缓存，在 messages 参数中）
    # 每次请求都变 → 不缓存
    
    return system_blocks
```

### 3. ClaudeLLMService 支持多层缓存

```python
# core/llm/claude.py

async def create_message_async(
    self,
    messages: List[Message],
    system: Optional[Union[str, List[Dict]]] = None,  # 支持 List[Dict] 格式
    **kwargs
) -> LLMResponse:
    """
    创建消息（支持多层缓存）
    
    Args:
        system: 系统提示词
            - str: 单层缓存（旧格式，向后兼容）
            - List[Dict]: 多层缓存（新格式）
    """
    request_params = {
        "model": self.config.model,
        "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
        "messages": self._format_messages(messages)
    }
    
    # System prompt（支持多层缓存）
    if system:
        if isinstance(system, str):
            # 单层缓存（向后兼容）
            if self.config.enable_caching:
                request_params["system"] = [{
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"}
                }]
            else:
                request_params["system"] = system
        elif isinstance(system, list):
            # 多层缓存（新格式）
            request_params["system"] = system
    
    # ... 其他代码
```

## 使用示例

### 示例 1：SimpleAgent 使用多层缓存

```python
# 构建多层缓存的 system prompt
system_blocks = agent._build_cached_system_prompt(
    complexity=TaskComplexity.COMPLEX,
    user_profile=mem0_profile
)

# 调用 LLM（自动应用缓存策略）
response = await agent.llm.create_message_async(
    messages=history_messages,
    system=system_blocks  # List[Dict] 格式
)

# 查看缓存效果
print(response.usage)
# {
#   "cache_creation_input_tokens": 100000,  # 首次：写入缓存
#   "cache_read_input_tokens": 0,
#   "input_tokens": 10000
# }

# 第二次请求（缓存命中）
response2 = await agent.llm.create_message_async(...)
print(response2.usage)
# {
#   "cache_creation_input_tokens": 0,
#   "cache_read_input_tokens": 100000,  # 命中：从缓存读取
#   "input_tokens": 10000
# }
```

### 示例 2：向后兼容单层缓存

```python
# 旧格式（单层缓存，仍然有效）
response = await agent.llm.create_message_async(
    messages=messages,
    system="You are a helpful assistant"  # str 格式
)
```

## 最佳实践（最终修正版）

### 核心原则（3 条铁律）

```
铁律 1：需要重启的内容 = 运行期稳定 → 1 小时缓存（90-95% 节省）
铁律 2：基于语义检索的内容 = 每次 query 不同结果不同 → 不能缓存
铁律 3：每次请求都变的内容 = 缓存无意义 → 不缓存
```

### 1. 意图识别提示词：1 小时缓存（运行期只读）

**路径 A：IntentAnalyzer（Haiku 4.5）**

```python
# ✅ 正确做法
system=[{
    "type": "text",
    "text": intent_prompt,  # 来自 prompt_results/intent_prompt.md
    "cache_control": {"type": "ephemeral"}
}]
```

**为什么是 1 小时**：
- ✅ 运营优化后需要重启 Agent
- ✅ 同一运行周期内完全稳定（只读）
- ✅ 1 小时缓存充分覆盖运行周期

**成本**：节省 **90%**（Haiku：$0.40/MTok → $0.04/MTok）

### 2. 主对话 Layer 1-3：1 小时缓存（重启才变）

**路径 B：SimpleAgent（Sonnet 4.5）**

**包含内容**：
- Layer 1: 框架规则（prompts/MEMORY_PROTOCOL.md 等）
- Layer 2: 实例提示词（prompt_results/{complexity}_prompt.md）
- Layer 3: Skills + 工具定义

**为什么是 1 小时**：
- ✅ 修改后都需要重启 Agent
- ✅ 同一运行周期内完全稳定
- ✅ 最大化成本节省

**成本**：节省 **95%**（Sonnet：$6/MTok → $0.30/MTok）

```python
# ✅ 正确做法：所有需要重启才生效的内容
system_blocks = [
    {
        "type": "text",
        "text": framework_rules,
        "cache_control": {"type": "ephemeral"}
    },
    {
        "type": "text",
        "text": instance_prompt,
        "cache_control": {"type": "ephemeral"}
    },
    {
        "type": "text",
        "text": tools_context,
        "cache_control": {"type": "ephemeral"}  # 最后一个缓存断点
    }
]
```

### 3. Mem0 用户画像：不缓存（语义检索，每次不同）❌

**为什么不能缓存**：
- ❌ Mem0 基于**语义向量匹配**检索
- ❌ 每次用户 query 不同 → embedding 不同 → 检索结果不同
- ❌ 缓存会导致使用错误的记忆！

```python
# ❌ 错误示例
# Query 1: "我喜欢什么运动？" → 检索到运动相关记忆（命中缓存）
# Query 2: "我的工作是什么？" → 但使用了缓存的运动记忆！错误！

# ✅ 正确做法：不缓存
if user_profile:
    system_blocks.append({
        "type": "text",
        "text": f"# 用户画像\n{user_profile}"
        # 不添加 cache_control
    })
```

### 4. 对话历史：不缓存（每次请求都变）

**为什么不缓存**：
- ❌ 每次请求都不同
- ❌ 缓存命中率接近 0
- ❌ 写入成本大于收益

```python
# ✅ 正确做法：messages 参数直接传入，不添加 cache_control
response = await llm.create_message_async(
    model="claude-sonnet-4-5-20250929",
    messages=history_messages,  # 不缓存
    system=system_blocks  # 多层缓存
)
```

## 监控与优化

### 查看缓存效果

```python
# 在 SimpleAgent 中记录缓存统计
logger.info(f"💾 缓存统计:")
logger.info(f"   写入: {usage.cache_creation_input_tokens} tokens")
logger.info(f"   命中: {usage.cache_read_input_tokens} tokens")
logger.info(f"   未缓存: {usage.input_tokens} tokens")

# 计算节省
if usage.cache_read_input_tokens > 0:
    savings = (usage.cache_read_input_tokens * 0.9) / (
        usage.cache_read_input_tokens + usage.input_tokens
    )
    logger.info(f"   成本节省: {savings:.1%}")
```

### 优化建议

1. **监控缓存命中率**：
   - 目标：Layer 1 > 80%，Layer 2 > 60%
   - 命中率低 → 考虑减少缓存层或延长 TTL

2. **调整缓存边界**：
   - 频繁变化的内容不要缓存
   - 稳定内容考虑 1 小时缓存

3. **成本对比**：
   - 每周统计缓存前后成本
   - 计算 ROI = 节省成本 / 缓存写入成本

## 迁移路径

### Phase 1: 启用基础缓存（已完成）

```python
# 当前代码已支持单层缓存
if self.config.enable_caching:
    system = [{"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}]
```

### Phase 2: 支持多层缓存（本次实现）

1. `ClaudeLLMService` 支持 `system: List[Dict]`
2. `SimpleAgent` 实现 `_build_cached_system_prompt()`
3. `PromptResultsWriter` 添加缓存策略元数据

### Phase 3: 成本监控仪表板（未来）

- 实时显示缓存命中率
- 对比缓存前后成本
- 自动优化缓存策略

## 参考资料

- [Claude Prompt Caching 官方文档](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [Pricing Calculator](https://platform.claude.com/docs/en/about-claude/pricing)
- [Cache Breakpoint Best Practices](https://platform.claude.com/docs/en/build-with-claude/prompt-caching#cache-breakpoints)

---

**版本**: V6.3  
**最后更新**: 2026-01-13  
**状态**: 设计完成，待实施
