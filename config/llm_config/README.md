# LLM 超参数配置说明

## 概述

项目中所有 LLM 调用点的超参数（模型、温度、max_tokens 等）已统一配置化，开发人员可在 [`llm_profiles.yaml`](llm_profiles.yaml) 中集中管理。

## 配置文件结构

```yaml
profiles:
  profile_name:
    description: "Profile 用途说明"
    model: "claude-sonnet-4-5-20250929"
    max_tokens: 64000
    temperature: 1.0
    enable_thinking: true
    thinking_budget: 10000
    enable_caching: false
    timeout: 120.0
    max_retries: 3
```

## 已配置的 LLM 调用点

| Profile 名称 | 调用位置 | 用途 | 模型 |
|-------------|---------|------|------|
| `main_agent` | `core/agent/simple/simple_agent.py` | 主 Agent 对话 | Sonnet |
| `intent_analyzer` | `core/agent/intent_analyzer.py` | 意图分析 | Haiku |
| `semantic_inference` | `core/inference/semantic_inference.py` | 语义推理 | Haiku |
| `llm_analyzer` | `core/prompt/llm_analyzer.py` | 提示词分析 | Haiku |
| `schema_generator` | `core/agent/factory.py` | Schema 生成 | Haiku |
| `tool_capability_inference` | `core/tool/instance_registry.py` | 工具能力推断 | Haiku |
| `background_task` | `utils/background_tasks.py` | 后台任务 | Haiku |
| `plan_manager` | `tools/plan_todo_tool.py` | 计划管理 | Sonnet |

## 使用方法

### 1. 修改配置

直接编辑 [`profiles.yaml`](profiles.yaml)：

```yaml
profiles:
  semantic_inference:
    description: "语义推理任务"
    model: "claude-haiku-4-5-20251001"
    max_tokens: 500        # 修改为 1000
    temperature: 0         # 修改为 0.3
    enable_thinking: false
```

修改后**无需重启服务**，配置会在下次调用时自动加载（有缓存机制）。

### 2. 强制刷新配置

如果需要立即生效，可在代码中调用：

```python
from config.llm_config_loader import reload_config
reload_config()
```

### 3. 在代码中使用

```python
    from config.llm_config import get_llm_profile
    from core.llm import create_llm_service

    # 获取配置
    profile = get_llm_profile("semantic_inference")

# 创建 LLM 服务
llm = create_llm_service(**profile)

# 调用
response = await llm.create_message_async(messages=[...])
```

### 4. 覆盖部分参数

```python
# 使用配置 + 临时覆盖
profile = get_llm_profile("semantic_inference", max_tokens=1000)
llm = create_llm_service(**profile)
```

## 环境变量覆盖（可选）

支持通过环境变量覆盖配置（优先级高于 YAML）：

```bash
# 格式：LLM_<PROFILE_NAME>_<PARAMETER>=<VALUE>
export LLM_SEMANTIC_INFERENCE_MAX_TOKENS=1000
export LLM_SEMANTIC_INFERENCE_TEMPERATURE=0.3
```

在代码中使用：

```python
    from config.llm_config import get_llm_profile_from_env

    # 自动应用环境变量覆盖
    profile = get_llm_profile_from_env("semantic_inference")
llm = create_llm_service(**profile)
```

## 参数说明

### model
- **类型**: `string`
- **说明**: 模型名称
- **推荐值**:
  - `claude-sonnet-4-5-20250929`: 最强推理能力，适合复杂任务
  - `claude-haiku-4-5-20251001`: 轻量快速，适合简单任务

### max_tokens
- **类型**: `integer`
- **说明**: 最大输出 token 数
- **推荐值**:
  - 简单任务: 100-500
  - 中等任务: 500-2048
  - 复杂任务: 2048-64000

### temperature
- **类型**: `float` (0-1)
- **说明**: 温度参数，控制输出随机性
- **推荐值**:
  - `0`: 确定性输出，适合结构化任务
  - `0.7-1.0`: 创意输出，适合对话和内容生成

### enable_thinking
- **类型**: `boolean`
- **说明**: 是否启用 Extended Thinking（深度推理）
- **限制**: 仅 Sonnet 支持，Haiku 不支持
- **推荐值**:
  - `true`: 需要复杂推理的任务
  - `false`: 简单任务或使用 Haiku 模型

### thinking_budget
- **类型**: `integer`
- **说明**: Thinking token 预算
- **前提**: `enable_thinking=true` 时有效
- **推荐值**: 5000-10000

### enable_caching
- **类型**: `boolean`
- **说明**: 是否启用 Prompt Caching（减少重复 token 消耗）
- **推荐值**:
  - `true`: 系统提示词很长且不常变化
  - `false`: 系统提示词短或频繁变化

### timeout
- **类型**: `float`
- **说明**: 请求超时时间（秒）
- **推荐值**:
  - 简单任务: 30
  - 中等任务: 60
  - 复杂任务: 120

### max_retries
- **类型**: `integer`
- **说明**: 最大重试次数
- **推荐值**: 1-3

## 查看可用 Profile

```python
    from config.llm_config import list_profiles

    profiles = list_profiles()
    for name, desc in profiles.items():
        print(f"{name}: {desc}")
```

输出示例：
```
main_agent: 主 Agent 对话处理，需要最强推理能力
semantic_inference: 工具调用时机判断，需要确定性输出
...
```

## 按环境区分配置（高级）

如果需要按环境（dev/prod）使用不同配置，可以创建多个配置文件：

```bash
config/llm_config/
├── profiles.yaml           # 默认（开发环境）
├── profiles.prod.yaml      # 生产环境
└── profiles.test.yaml      # 测试环境
```

在启动时通过环境变量指定：

```bash
export LLM_CONFIG_FILE=profiles.prod.yaml
python main.py
```

## 故障排查

### 配置未生效

1. 检查 YAML 语法是否正确
2. 确认 Profile 名称拼写正确
3. 调用 `reload_config()` 刷新缓存

### Profile 不存在错误

```
KeyError: LLM Profile 'xxx' 不存在
可用的 Profile: main_agent, semantic_inference, ...
```

**解决方法**: 检查 Profile 名称是否正确，或在 `profiles.yaml` 中添加该 Profile。

### 参数类型错误

```
TypeError: max_tokens must be int, not str
```

**解决方法**: 检查 YAML 中参数值类型是否正确（数字不要加引号）。

## 最佳实践

1. **模型选择**
   - 复杂推理任务 → Sonnet + Extended Thinking
   - 简单快速任务 → Haiku
   - 成本敏感场景 → Haiku

2. **Temperature 设置**
   - 结构化输出（JSON/工具调用）→ 0
   - 创意内容生成 → 0.7-1.0

3. **max_tokens 设置**
   - 根据实际需要设置，不要过大（浪费资源）
   - 观察日志中的实际 token 使用量，适当调整

4. **Timeout 设置**
   - 考虑网络延迟 + 模型处理时间
   - 避免过短导致频繁超时

5. **配置版本管理**
   - 配置文件纳入 Git 版本控制
   - 重大调整前备份配置
   - 使用注释记录修改原因

## 相关文件

- [`profiles.yaml`](profiles.yaml) - LLM 配置文件
- [`loader.py`](loader.py) - 配置加载器
- [`__init__.py`](__init__.py) - 模块导出接口
- [`../core/llm/base.py`](../../core/llm/base.py) - LLM 服务基类
