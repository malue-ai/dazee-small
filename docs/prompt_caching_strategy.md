# Prompt Caching 策略设计

## 概述

基于 [Claude Prompt Caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) 的多层缓存架构，优化 `prompt_results` 生成的系统提示词成本。

## 核心理念

```
缓存粒度 = 更新频率的倒数

更新越少 → 缓存时间越长 → 成本越低
```

## 四层缓存架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    System Prompt 构成                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Layer 1: 框架通用规则（1小时缓存）                         │ │
│  │ • 来源：prompts/MEMORY_PROTOCOL.md                         │ │
│  │ • 来源：prompts/fragments/e2b_rules.md                     │ │
│  │ • 频率：几乎不变（框架升级）                               │ │
│  │ • 策略：1-hour cache (cache_control: 1h)                  │ │
│  │ • 成本：写入 2x，命中 0.1x                                 │ │
│  │ 📌 cache_control breakpoint #1                             │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Layer 2: 实例核心提示词（5分钟缓存）                       │ │
│  │ • 来源：prompt_results/{simple|medium|complex}_prompt.md   │ │
│  │ • 内容：角色定义、工作规则、输出格式                       │ │
│  │ • 频率：偶尔修改（运营优化）                               │ │
│  │ • 策略：5-minute cache (cache_control: ephemeral)         │ │
│  │ • 成本：写入 1.25x，命中 0.1x                              │ │
│  │ 📌 cache_control breakpoint #2                             │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Layer 3: 用户画像 + 工具定义（5分钟缓存）                  │ │
│  │ • Mem0 用户画像                                            │ │
│  │ • Skills 元数据                                            │ │
│  │ • 能力分类描述                                             │ │
│  │ • 频率：用户偏好变化 / 工具更新                            │ │
│  │ • 策略：5-minute cache (cache_control: ephemeral)         │ │
│  │ 📌 cache_control breakpoint #3                             │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Layer 4: 当前对话历史（不缓存）                            │ │
│  │ • messages 历史                                            │ │
│  │ • 当前用户输入                                             │ │
│  │ • 频率：每次请求都变化                                     │ │
│  │ • 策略：不缓存                                             │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 成本对比

### 场景：100K token 系统提示词 + 10K token 用户输入

| 层级 | 内容 | Token | 缓存策略 | 首次成本 | 命中成本 | 节省 |
|------|------|-------|---------|---------|---------|------|
| Layer 1 | 框架规则 | 30K | 1h cache | $60 / MTok | $3 / MTok | **95%** |
| Layer 2 | 实例提示词 | 50K | 5m cache | $62.5 / MTok | $3 / MTok | **95.2%** |
| Layer 3 | 用户画像+工具 | 20K | 5m cache | $62.5 / MTok | $3 / MTok | **95.2%** |
| Layer 4 | 对话历史 | 10K | 不缓存 | $50 / MTok | $50 / MTok | 0% |

**总成本**（Sonnet 4.5）：
- 首次：$6.05 / 请求
- 命中：$0.59 / 请求（**节省 90.2%**）

## 实现策略

### 1. prompt_results 生成时标记

在 `PromptResultsWriter` 输出时添加缓存边界元数据：

```yaml
# prompt_results/_metadata.json
{
  "cache_strategy": {
    "layer1_framework": {
      "ttl": "1h",
      "fragments": [
        "prompts/MEMORY_PROTOCOL.md",
        "prompts/fragments/e2b_rules.md"
      ]
    },
    "layer2_instance": {
      "ttl": "5m",
      "files": [
        "simple_prompt.md",
        "medium_prompt.md",
        "complex_prompt.md"
      ]
    },
    "layer3_dynamic": {
      "ttl": "5m",
      "includes": ["user_profile", "tools", "skills"]
    }
  }
}
```

### 2. SimpleAgent 运行时组装

```python
# core/agent/simple_agent.py

def _build_cached_system_prompt(
    self, 
    complexity: TaskComplexity,
    user_profile: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    构建多层缓存的 system prompt
    
    Returns:
        List[Dict] - Claude API 的 system blocks 格式
    """
    system_blocks = []
    
    # Layer 1: 框架通用规则（1小时缓存）
    framework_rules = self._get_framework_rules()
    system_blocks.append({
        "type": "text",
        "text": framework_rules,
        "cache_control": {"type": "ephemeral", "ttl": "1h"}  # 🆕 1小时缓存
    })
    
    # Layer 2: 实例核心提示词（5分钟缓存）
    instance_prompt = self._prompt_cache.get_system_prompt(complexity)
    system_blocks.append({
        "type": "text",
        "text": instance_prompt,
        "cache_control": {"type": "ephemeral"}  # 5分钟缓存
    })
    
    # Layer 3: 用户画像 + 工具（5分钟缓存）
    dynamic_context = self._build_dynamic_context(user_profile)
    if dynamic_context:
        system_blocks.append({
            "type": "text",
            "text": dynamic_context,
            "cache_control": {"type": "ephemeral"}  # 5分钟缓存
        })
    
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

## 最佳实践

### 1. 框架规则使用 1 小时缓存

框架规则几乎不变，使用 1 小时缓存可以最大化节省：

```python
# prompts/fragments/ 中的内容
FRAMEWORK_FRAGMENTS = [
    "MEMORY_PROTOCOL.md",
    "e2b_rules.md",
    "output_format_basic.md"
]
```

**成本**：
- 写入：$6 / MTok（2x）
- 命中：$0.30 / MTok（0.1x）
- 节省：**95%**

### 2. 实例提示词使用 5 分钟缓存

运营可能调整，5 分钟是平衡点：

```python
# prompt_results/{complexity}_prompt.md
# 包含：角色定义、工作规则、输出格式
```

### 3. 用户画像使用 5 分钟缓存

用户偏好短期内稳定，可以缓存：

```python
dynamic_context = f"""
# 用户画像
{mem0_profile}

# 可用工具
{tools_description}

# Skills
{skills_metadata}
"""
```

### 4. 对话历史不缓存

每次请求都变化，不值得缓存：

```python
# messages 参数传入的历史对话
# 不添加 cache_control
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
