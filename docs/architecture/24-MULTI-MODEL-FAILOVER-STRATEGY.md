# 多模型容灾与动态切换方案

> **文档版本**: V2.1  
> **创建日期**: 2026-01-23  
> **最后更新**: 2026-01-23  
> **适用架构**: V7.11+  
> **目标读者**: 后端开发者、运维工程师

## 目录

- [1. 方案概述](#1-方案概述)
- [2. 自动切换机制](#2-自动切换机制)
  - [2.0 切换优先级规则](#20-切换优先级规则)
  - [2.1 自动切换时机](#21-自动切换时机)
  - [2.2 切换原理与实现](#22-切换原理与实现)
  - [2.3 自顶向下调用关系](#23-自顶向下调用关系)
  - [2.4 主动恢复策略](#24-主动恢复策略priority-recovery)
  - [2.5 探针优化与用户体验](#25-探针优化与用户体验)
- [3. 手动配置方法](#3-手动配置方法)
  - [3.1 主备切换配置](#31-主备切换配置)
  - [3.2 Provider切换配置](#32-provider切换配置)
  - [3.3 全局一键切换](#33-全局一键切换)
  - [3.4 健康探测配置](#34-健康探测配置)
- [4. 核心组件详解](#4-核心组件详解)
- [5. 配置示例](#5-配置示例)
- [6. 监控与调试](#6-监控与调试)
- [7. 最佳实践](#7-最佳实践)
- [8. 附录](#8-附录)

---

## 1. 方案概述

### 1.1 业务背景

ZenFlux Agent 原本完全依赖 Claude API，存在以下问题：

| 问题类型 | 影响 | 优先级 |
|---------|------|--------|
| **单点故障** | Claude 服务中断 → 整个系统不可用 | P0 |
| **成本固化** | 无法根据任务复杂度动态选择模型 | P1 |
| **能力绑定** | Claude Skills 强绑定，切换后工具调用失败 | P0 |
| **迭代缓慢** | 模型升级需要改造所有代码 | P2 |

### 1.2 解决方案

通过引入 **多模型容灾架构**，实现：

```
┌─────────────────────────────────────────────────────────────┐
│                   多模型容灾架构（V7.6+）                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  用户请求                                                     │
│     ↓                                                        │
│  ChatService（服务层）                                        │
│     ↓                                                        │
│  Agent（SimpleAgent/MultiAgentOrchestrator）                 │
│     ↓                                                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  ModelRouter（模型路由器）🆕 核心组件                  │   │
│  │  - 主备切换逻辑                                        │   │
│  │  - 健康检测集成                                        │   │
│  │  - 熔断保护机制                                        │   │
│  └──────────────────────────────────────────────────────┘   │
│     ↓                    ↓                                   │
│  Claude (主)         Qwen (备)                               │
│  └─ Provider A      └─ Qwen API                              │
│  └─ Provider B                                               │
│     ↓                                                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  UnifiedToolCaller（统一工具调用器）🆕 核心组件        │   │
│  │  - Skills 热插拔（仅 Claude）                          │   │
│  │  - Fallback Tool（非 Claude）                          │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 核心特性

✅ **自动容灾**：主模型故障时自动切换到备选模型  
✅ **热插拔工具**：Skills 可动态启用/禁用，非 Claude 模型使用 Fallback Tool  
✅ **多 Provider 支持**：同一模型支持多个服务商来源（如 Claude 官方 + 第三方代理）  
✅ **配置驱动**：通过 YAML 配置文件或环境变量实现主备切换，无需修改代码  
✅ **健康监控**：实时采集模型指标，自动判定健康状态  

---

## 2. 自动切换机制

### 2.0 切换优先级规则

#### 2.0.1 Fallback 优先级顺序

根据 `profiles.yaml` 配置，切换优先级为：

```
┌────────────────────────────────────────────────────────────────────┐
│                     切换优先级（以 main_agent 为例）                 │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  primary:      Claude Sonnet（主 API，ANTHROPIC_API_KEY）           │
│                     ↓ 失败                                          │
│  fallback_0:   Claude Sonnet（Vendor A，CLAUDE_API_KEY_VENDOR_A）   │
│                     ↓ 失败                                          │
│  fallback_1:   Claude Sonnet（Vendor B，CLAUDE_API_KEY_VENDOR_B）   │
│                     ↓ 失败                                          │
│  fallback_2:   Qwen-Max（跨厂商，QWEN_API_KEY）                     │
│                     ↓ 失败                                          │
│  fallback_3:   DeepSeek-Chat（跨厂商，待接入）                      │
│                                                                     │
└────────────────────────────────────────────────────────────────────┘
```

#### 2.0.2 优先级设计原则

**原则：同模型多 Provider 优先，跨厂商兜底**

| 优先级 | 策略 | 说明 | 用户感知 |
|-------|------|------|---------|
| **1** | 同模型同 Provider（备用账号） | API Key 故障时快速切换 | ✅ 无感知 |
| **2** | 同模型不同 Provider（代理商） | Provider 故障时切换 | ✅ 无感知 |
| **3** | 跨厂商备选（Qwen） | Claude 完全不可用时兜底 | ⚠️ 效果可能有差异 |

**为什么同模型优先？**
- **效果一致**：同一模型，输出质量相同
- **无需适配**：工具调用格式兼容，无需 fallback_tool
- **用户无感知**：切换后体验完全一致

#### 2.0.3 配置示例

```yaml
# config/llm_config/profiles.yaml

profiles:
  main_agent:
    provider: "claude"
    model: "claude-sonnet-4-5-20250929"
    api_key_env: "ANTHROPIC_API_KEY"  # 主 API Key
    
    fallbacks:
      # 优先级 1：同模型，Provider A（备用账号/代理商）
      - provider: "claude"
        model: "claude-sonnet-4-5-20250929"
        api_key_env: "CLAUDE_API_KEY_VENDOR_A"
        base_url: "https://api.anthropic.com"
      
      # 优先级 2：同模型，Provider B（另一代理商）
      - provider: "claude"
        model: "claude-sonnet-4-5-20250929"
        api_key_env: "CLAUDE_API_KEY_VENDOR_B"
        base_url: "https://anthropic-proxy-b.example.com/v1"
      
      # 优先级 3：跨厂商（Qwen 兜底）
      - provider: "qwen"
        model: "qwen-max"
        api_key_env: "QWEN_API_KEY"
```

---

### 2.1 自动切换时机

自动切换在以下 **4 种场景** 下触发：

#### 场景 1：网络异常

```python
# 示例：Claude API 网络连接失败
APIConnectionError: Connection to api.anthropic.com timeout
↓
ModelRouter 捕获异常 → 记录失败 → 切换到 fallback_0（Qwen）
```

**触发条件**：
- `APIConnectionError`（连接超时）
- `APITimeoutError`（请求超时）
- `RemoteProtocolError`（协议错误）
- `ConnectError`（网络连接错误）

#### 场景 2：服务限流

```python
# 示例：Claude API 触发速率限制
RateLimitError: 429 Too Many Requests
↓
ModelRouter 捕获异常 → 记录失败 → 切换到 fallback_0（Qwen）
```

**触发条件**：
- `RateLimitError`（429 状态码）
- 连续失败次数达到 `policy.max_failures`（默认 2 次）

#### 场景 3：健康检测失败

```python
# 示例：健康监控器检测到模型不可用
HealthMonitor: 错误率 35% > 阈值 30%
↓
ModelRouter._target_available() → 返回 False
↓
自动跳过主模型，直接选择 fallback_0（Qwen）
```

**触发条件**：
- 错误率 > `error_rate_threshold`（默认 30%）
- 平均延迟 > `avg_latency_ms_threshold`（默认 15000ms）
- 样本数 >= `min_samples`（默认 5 个请求）

#### 场景 4：条件探测失败（V7.11 条件探测）

```python
# 示例：ChatService 条件探测（仅当后台探测显示不健康时执行）
await chat_service._probe_llm_service()
↓
检查后台探测服务：probe_service.is_healthy(profile_name)
↓
后台健康 → 跳过探测（零延迟）
后台不健康 → 执行请求级探测确认
↓
ModelRouter.probe(include_unhealthy=True)
↓
主模型探针失败 → 切换到 fallback_0（Qwen）
```

**触发条件**：
- 后台探测服务显示该 Profile 不健康
- 执行请求级探测进行"最后确认"
- 探针请求失败（网络、超时、服务不可用）

**条件探测优势**：
- 正常情况：零延迟（直接跳过）
- 异常情况：提供额外保护（≤5s）

---

### 2.2 切换原理与实现

#### 2.2.1 健康监控机制

**核心组件**：`LLMHealthMonitor`（`core/llm/health_monitor.py`）

```python
class LLMHealthMonitor:
    """
    LLM 健康监控器（滑动窗口统计）
    
    统计指标：
    - 错误率：失败请求 / 总请求
    - 平均延迟：请求耗时平均值
    - 样本数：统计窗口内的请求数量
    """
    
    def record_success(self, target_key: str, latency_ms: float):
        """记录成功调用"""
        
    def record_failure(self, target_key: str, latency_ms: float, error: Exception):
        """记录失败调用"""
        
    def is_healthy(self, target_key: str) -> bool:
        """判断目标是否健康"""
        stats = self.get_stats(target_key)
        if stats["error_rate"] > 0.3:  # 错误率 > 30%
            return False
        if stats["avg_latency_ms"] > 15000:  # 平均延迟 > 15s
            return False
        return True
```

**健康判定策略**：

```yaml
# 健康检测策略（可通过环境变量覆盖）
window_seconds: 300           # 统计窗口：5 分钟
min_samples: 5                # 最小样本数：5 个请求
error_rate_threshold: 0.3     # 错误率阈值：30%
avg_latency_ms_threshold: 15000.0  # 延迟阈值：15 秒
```

**状态转换图**：

```
┌─────────┐  错误率 < 30%   ┌─────────┐
│ Healthy │◄───────────────│ Degraded │  延迟 > 15s
│         │                 │          │  但错误率 < 30%
└─────────┘                 └─────────┘
     ▲                           │
     │                           │
     │  错误率降低                │ 错误率 > 30%
     │                           │
     │                           ▼
     │                      ┌──────────┐
     └──────────────────────┤ Unhealthy │
        错误率降低 < 30%     │           │
                            └──────────┘
```

#### 2.2.2 熔断保护机制

**核心组件**：`ModelRouter`（`core/llm/router.py`）

```python
class ModelRouter:
    """
    模型路由器（熔断保护）
    
    熔断策略：
    - 连续失败达到 max_failures 次 → 进入冷却期
    - 冷却期内不再尝试该模型（避免雪崩）
    - 冷却期结束后重新探测
    """
    
    def _target_available(self, target: RouteTarget) -> bool:
        """判断目标是否可用"""
        # 1. 健康监控器判定
        if not self.health_monitor.is_healthy(target.name):
            return False
        
        # 2. 熔断器判定
        failures = self._failure_counts.get(target.name, 0)
        if failures < self.policy.max_failures:
            return True  # 未达到熔断阈值
        
        # 3. 冷却期判定
        last_ts = self._last_failure_ts.get(target.name, 0.0)
        cooldown_passed = (time.time() - last_ts) >= self.policy.cooldown_seconds
        return cooldown_passed  # 冷却期结束后可恢复
```

**熔断流程图**：

```
┌──────────────────────────────────────────────────────────┐
│                   熔断保护流程                              │
├──────────────────────────────────────────────────────────┤
│                                                           │
│  模型调用失败                                              │
│     ↓                                                     │
│  failure_counts[target] += 1                              │
│     ↓                                                     │
│  ┌─────────────────────────┐                             │
│  │ failures >= max_failures? │  NO → 记录失败，继续使用   │
│  └─────────────────────────┘                             │
│     │ YES                                                 │
│     ↓                                                     │
│  进入冷却期（cooldown_seconds = 600s，10 分钟）              │
│     ↓                                                     │
│  后续请求自动跳过该模型                                     │
│     ↓                                                     │
│  冷却期结束后重新探测                                       │
│     ↓                                                     │
│  ┌──────────────┐                                        │
│  │ 探测成功？    │  YES → 恢复使用，重置计数器             │
│  └──────────────┘                                        │
│     │ NO                                                  │
│     ↓                                                     │
│  继续冷却，等待下次探测                                     │
│                                                           │
└──────────────────────────────────────────────────────────┘
```

#### 2.2.3 自动切换算法

**核心方法**：`ModelRouter._select_targets()`

```python
def _select_targets(self) -> List[RouteTarget]:
    """
    选择可用目标（优先级排序）
    
    返回顺序：
    1. 主模型（如果可用）
    2. fallback_0（如果可用）
    3. fallback_1（如果可用）
    ...
    
    如果全部不可用，返回 [primary]（强制尝试）
    """
    available = [t for t in self.targets if self._target_available(t)]
    return available if available else [self.primary]
```

**切换逻辑示例**：

```
请求 1：
  主模型（Claude）可用 → 选择 Claude
  ✅ 调用成功 → 记录成功

请求 2：
  主模型（Claude）可用 → 选择 Claude
  ❌ 调用失败（APIConnectionError）→ failure_counts["Claude"] = 1
  → 自动切换到 fallback_0（Qwen）
  ✅ 调用成功 → 记录成功

请求 3：
  主模型（Claude）可用 → 选择 Claude
  ❌ 调用失败（APITimeoutError）→ failure_counts["Claude"] = 2
  → 达到熔断阈值（max_failures=2）→ 进入冷却期
  → 自动切换到 fallback_0（Qwen）
  ✅ 调用成功 → 记录成功

请求 4-N：
  主模型（Claude）不可用（冷却期）→ 自动跳过
  → 直接选择 fallback_0（Qwen）
  ✅ 调用成功 → 记录成功

请求 N+1（冷却期结束后）：
  主模型（Claude）冷却期结束 → 重新探测
  ✅ 探测成功 → 恢复使用 Claude
  failure_counts["Claude"] = 0（重置计数器）
```

---

### 2.3 自顶向下调用关系

#### 2.3.1 完整调用链路

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        多模型切换完整调用链路                               │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  1️⃣ 用户请求入口                                                          │
│  POST /api/v1/conversations/{id}/messages                                 │
│     ↓                                                                     │
│  routers/chat_router.py: stream_chat() / send_message()                  │
│     ↓                                                                     │
│  ──────────────────────────────────────────────────────────────────────  │
│  2️⃣ 服务层（条件探测 V7.11）                                               │
│  services/chat_service.py: ChatService.chat()                            │
│     ↓                                                                     │
│  await self._probe_llm_service()  # 🆕 条件探测（后台不健康时才执行）      │
│     ↓                                                                     │
│  检查后台探测结果：probe_service.is_healthy(profile_name)                 │
│     ├─ 后台健康 → 跳过探测（零延迟）✅                                     │
│     └─ 后台不健康 → 执行请求级探测确认                                     │
│         ↓                                                                 │
│         ModelRouter.probe(include_unhealthy=True)                        │
│         ├─ 尝试 primary（Claude）→ 失败 → 标记不可用                       │
│         ├─ 尝试 fallback_0（Qwen）→ 成功 → 返回 Qwen 配置                  │
│         └─ 记录切换事件：switched=True                                     │
│     ↓                                                                     │
│  ──────────────────────────────────────────────────────────────────────  │
│  3️⃣ 路由层（意图分析）                                                     │
│  core/routing/router.py: AgentRouter.route()                             │
│     ↓                                                                     │
│  intent_llm = create_llm_service(**get_llm_profile("intent_analyzer"))   │
│     ↓                                                                     │
│  ModelRouter（intent_analyzer 配置）                                      │
│     ├─ primary: Claude Haiku                                              │
│     ├─ fallback_0: Qwen-Plus                                              │
│     └─ 自动选择可用模型                                                    │
│     ↓                                                                     │
│  intent_analyzer.analyze() → 返回复杂度评分                               │
│     ↓                                                                     │
│  ──────────────────────────────────────────────────────────────────────  │
│  4️⃣ Agent 层（任务执行）                                                   │
│  core/agent/simple/simple_agent.py: SimpleAgent.run()                    │
│     ↓                                                                     │
│  self.llm = ModelRouter（main_agent 配置）                                │
│     ├─ primary: Claude Sonnet                                             │
│     ├─ fallback_0: Claude Sonnet (Vendor A)                               │
│     ├─ fallback_1: Claude Sonnet (Vendor B)                               │
│     ├─ fallback_2: Qwen-Max                                               │
│     └─ 自动选择可用模型                                                    │
│     ↓                                                                     │
│  await self.llm.create_message_async(messages, tools=...)                │
│     ↓                                                                     │
│  ──────────────────────────────────────────────────────────────────────  │
│  5️⃣ 路由器层（主备切换）                                                   │
│  core/llm/router.py: ModelRouter.create_message_async()                  │
│     ↓                                                                     │
│  for target in self._select_targets():  # 按优先级遍历                    │
│     ├─ 尝试 primary（Claude Sonnet）                                      │
│     │   ├─ 检查健康状态：is_healthy()                                      │
│     │   ├─ 检查熔断器：failure_counts < max_failures                       │
│     │   └─ 调用 target.service.create_message_async()                     │
│     │       ↓                                                             │
│     │   ❌ 失败（APIConnectionError）                                      │
│     │       ├─ record_failure(target, error)                              │
│     │       ├─ health_monitor.record_failure(...)                         │
│     │       └─ 继续尝试下一个 target                                       │
│     │                                                                     │
│     ├─ 尝试 fallback_0（Qwen-Max）                                        │
│     │   ├─ 检查健康状态：is_healthy()                                      │
│     │   ├─ 检查熔断器：failure_counts < max_failures                       │
│     │   └─ 调用 target.service.create_message_async()                     │
│     │       ↓                                                             │
│     │   ✅ 成功                                                            │
│     │       ├─ record_success(target)                                     │
│     │       ├─ health_monitor.record_success(...)                         │
│     │       └─ 返回 LLMResponse                                            │
│     │                                                                     │
│     └─ self._last_selected = "fallback_0:qwen:qwen-max"                  │
│     ↓                                                                     │
│  ──────────────────────────────────────────────────────────────────────  │
│  6️⃣ Provider 层（实际调用）                                                │
│  core/llm/qwen.py: QwenLLMService.create_message_async()                 │
│     ↓                                                                     │
│  dashscope.Generation.call(model="qwen-max", messages=...)               │
│     ↓                                                                     │
│  DashScope API（阿里云通义千问）                                           │
│     ↓                                                                     │
│  返回 LLMResponse（content, thinking, tool_calls, usage）                 │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘
```

#### 2.3.2 关键调用点说明

| 调用点 | 位置 | 职责 | 切换触发 |
|-------|------|------|---------|
| **条件探测** | `ChatService._probe_llm_service()` | 后台不健康时执行请求级确认（V7.11） | ✅ 后台不健康 + 探针失败 → 切换 |
| **意图分析** | `AgentRouter.route()` | 分析用户意图，评估任务复杂度 | ✅ 调用失败 → 切换 |
| **任务执行** | `SimpleAgent.run()` / `WorkerAgent.execute()` | 执行具体任务，调用工具 | ✅ 调用失败 → 切换 |
| **模型路由** | `ModelRouter.create_message_async()` | 主备切换核心逻辑 | ✅ 失败 → 遍历 fallbacks |
| **后台探测** | `HealthProbeService.probe_all()` | 定期探测所有模型健康状态 | ⚠️ 更新健康状态，影响条件探测决策 |
| **健康监控** | `HealthMonitor.record_success/failure()` | 采集指标，判定健康状态 | ⚠️ 不直接切换，影响可用性判断 |

---

### 2.4 主动恢复策略（Priority Recovery）

#### 2.4.1 恢复问题分析

当高优先级服务（如 Claude 原生接口）从故障恢复后，需要解决以下问题：

| 问题 | 影响 | 当前机制 |
|-----|------|---------|
| **恢复延迟** | 冷却期 + 下一个请求等待 | 被动恢复，最长 10分钟+ |
| **用户感知** | 可能持续使用备选模型 | 无主动通知 |
| **资源浪费** | 备选模型可能成本更高或效果更差 | 无优先级回切 |

#### 2.4.2 主动恢复机制（V7.10+ 已实现）

**核心原理**：

```
┌─────────────────────────────────────────────────────────────────────┐
│                     主动恢复策略（Priority Recovery）                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1️⃣ 后台恢复探测（Background Recovery Probe）                         │
│     HealthProbeService 定期探测主模型                                 │
│        ↓                                                             │
│     probe(include_unhealthy=True)                                   │
│        ↓                                                             │
│     主模型探测成功 → _record_success() → 重置失败计数                 │
│        ↓                                                             │
│     下一个请求自动使用主模型                                          │
│                                                                      │
│  2️⃣ 冷却期结束自动恢复（Cooldown Recovery）                           │
│     冷却期结束 → _target_available() 返回 True                       │
│        ↓                                                             │
│     _select_targets() 将主模型放在第一位                             │
│        ↓                                                             │
│     下一个请求优先尝试主模型                                          │
│                                                                      │
│  3️⃣ 请求时渐进式恢复（Request-time Recovery Probe）🆕                │
│     当使用备选模型时，定期尝试探测主模型                               │
│        ↓                                                             │
│     探测成功 → 立即切回主模型                                         │
│        ↓                                                             │
│     用户完全无感知                                                    │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

**恢复时序图**：

```
时间 ──────────────────────────────────────────────────────────────────►

主模型故障                 后台探测恢复                用户请求
    │                           │                         │
    ▼                           ▼                         ▼
┌─────────┐              ┌─────────────┐            ┌─────────┐
│ 故障发生 │──冷却期───► │ 后台探测主模型 │───成功──►│ 使用主模型│
│         │  (10分钟)   │             │           │         │
│ 切换到   │              │ _record_    │           │ 用户无感知│
│ 备选模型 │              │ success()   │           │         │
└─────────┘              └─────────────┘            └─────────┘
                               │
                               ▼
                         重置失败计数
                         failures = 0
```

#### 2.4.3 恢复策略配置

```yaml
# config/llm_config/profiles.yaml

# 恢复策略配置
recovery:
  # 冷却期配置（越短恢复越快，但可能导致抖动）
  cooldown_seconds: 600          # 默认：10 分钟（可通过 LLM_ROUTER_COOLDOWN_SECONDS 覆盖）
  
  # 后台恢复探测
  background_recovery:
    enabled: true                 # 启用后台恢复探测
    interval_seconds: 120         # 探测间隔（默认：120s）
    include_unhealthy: true       # 探测不健康目标（恢复探测）
  
  # 请求时恢复探测（可选，适用于高可用场景）
  request_recovery:
    enabled: false                # 默认禁用（避免延迟）
    probe_interval_seconds: 300   # 每 5 分钟尝试一次主模型
    max_probe_latency_ms: 1000    # 探测超时限制

profiles:
  main_agent:
    # ... 主模型配置 ...
    policy:
      max_failures: 2
      cooldown_seconds: 600      # 默认：10 分钟（与 recovery.cooldown_seconds 一致）
```

#### 2.4.4 恢复效果对比

| 策略 | 恢复延迟 | 用户感知 | 资源消耗 | 推荐场景 |
|-----|---------|---------|---------|---------|
| **纯被动恢复** | 冷却期 + 请求等待 | ⚠️ 可能感知 | 低 | 低频场景 |
| **后台恢复探测** | ≤ 探测间隔（120s） | ✅ 无感知 | 中 | **生产推荐** |
| **请求时恢复探测** | 即时 | ✅ 无感知 | 高 | 高可用场景 |

#### 2.4.5 代码实现关键点

**后台恢复探测**（已实现）：

```python
# services/health_probe_service.py

async def _probe_profile(self, profile_name: str) -> Dict[str, Any]:
    # 关键：include_unhealthy=True 会探测主模型
    result = await llm.probe(max_retries=1, include_unhealthy=True)
    #                                       ^^^^^^^^^^^^^^^^^^^^^^
    #                                       即使主模型不健康也会探测
```

**探测成功自动恢复**：

```python
# core/llm/router.py

async def probe(self, ..., include_unhealthy: bool = False):
    # include_unhealthy=True 时遍历所有目标（包括不健康的主模型）
    targets = self.targets if include_unhealthy else self._select_targets()
    
    for target in targets:
        try:
            await target.service.create_message_async(...)
            # 探测成功 → 重置失败计数 → 恢复可用
            self._record_success(target)  # ✅ 关键：重置 failure_counts
            return {"selected": target, "switched": ...}
        except Exception as e:
            continue  # 继续尝试下一个
```

**请求时优先选择恢复的主模型**：

```python
# core/llm/router.py

def _select_targets(self) -> List[RouteTarget]:
    # self.targets = [primary, fallback_0, fallback_1, ...]
    # 主模型恢复后会在列表第一位，优先被选择
    available = [t for t in self.targets if self._target_available(t)]
    return available if available else [self.primary]
```

#### 2.4.6 用户透明性保证

**透明切换的关键**：

1. **后台探测**：与用户请求解耦，用户不感知探测过程
2. **状态预更新**：后台探测成功后立即更新状态，下一个请求直接使用主模型
3. **无中断切换**：当前请求继续使用备选模型，下一个请求使用主模型
4. **日志记录**：切换事件记录日志，便于运维排查

```python
# 用户视角的请求流程

请求 1（主模型故障期间）：
  ModelRouter → 主模型不可用 → 使用备选模型 → 用户收到响应
  
# 后台探测：主模型恢复 → _record_success() → 重置状态

请求 2（主模型恢复后）：
  ModelRouter → 主模型可用 → 使用主模型 → 用户收到响应
  ↑
  用户完全无感知切换过程
```

**日志示例**：

```bash
# 后台探测发现主模型恢复
🩺 后台探测: 主模型恢复 target=claude:claude-sonnet-4-5-20250929
✅ 模型恢复: target=claude:claude-sonnet-4-5-20250929, failures=0

# 下一个用户请求自动使用主模型
🔀 模型已切换: fallback_0:qwen:qwen-max → primary:claude:claude-sonnet-4-5-20250929
```

---

### 2.5 探针优化与用户体验

#### 2.5.1 优化目标

**核心目标**：
- ✅ 移除请求链路阻塞，提升用户体验
- ✅ 实现主备自动切换，保障服务可用性
- ✅ 后台持续健康监控，提前发现问题

**优化前的问题**：

| 问题 | 影响 | 延迟增加 | 用户感知 |
|-----|------|---------|---------|
| **探针在请求链路中同步执行** | 每次请求都探测 | +500ms~1s | ⚠️ 略有感知 |
| **主模型超时** | 需要等待超时后切换 | +30s~60s | 🔴 **严重影响** |
| **多级切换** | 依次尝试所有 fallback | +N × 超时时间 | 🔴 **严重影响** |
| **无后台健康检测** | 只有请求时才探测 | 无法提前发现问题 | ⚠️ 被动响应 |

#### 2.5.2 条件探测方案（V7.11 重构 ✅）

**设计思路**：

```
┌─────────────────────────────────────────────────────────────────────┐
│                        条件探测策略                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   用户请求到达                                                       │
│        ↓                                                            │
│   检查后台探测服务的健康状态                                          │
│        ↓                                                            │
│   ┌─────────────────┐     ┌─────────────────┐                       │
│   │ 后台健康 ✅      │     │ 后台不健康 ⚠️   │                       │
│   │                 │     │                 │                       │
│   │ 直接跳过探测     │     │ 执行请求级探测   │                       │
│   │ 零延迟 🚀       │     │ 最后确认 🛡️     │                       │
│   └────────┬────────┘     └────────┬────────┘                       │
│            ↓                       ↓                                │
│   依赖 ModelRouter            探测确认后执行                          │
│   自动切换                    （最多 5s 延迟）                        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**优化方案汇总**：

| 方案 | 状态 | 效果 | 说明 |
|-----|------|------|------|
| **条件探测** | ✅ V7.11 | 正常零延迟，异常有保护 | 后台健康则跳过，不健康则确认 |
| **后台健康检测** | ✅ V7.10 | 完全解耦，用户无感知 | 定期探测所有模型 |
| **ModelRouter 切换** | ✅ 已有 | 实时响应式切换 | 调用失败自动遍历 fallbacks |

---

##### 条件探测：智能跳过策略

**核心逻辑**：后台健康 → 跳过（0ms）| 后台不健康 → 执行确认（≤5s）

```python
# services/chat_service.py - 条件探测实现

async def _probe_llm_service(self, llm_service, session_id, role, ...):
    profile_name = self._ROLE_TO_PROFILE_MAP.get(role, role)
    probe_service = get_health_probe_service()
    
    if probe_service.is_healthy(profile_name):
        return None  # 后台健康，跳过探测
    
    # 后台不健康，执行请求级确认
    return await asyncio.wait_for(
        llm_service.probe(max_retries=1, include_unhealthy=True),
        timeout=5.0
    )
```

---

##### 后台异步健康检测服务

**核心功能**：定期探测所有模型（默认 120s），与用户请求完全解耦

```python
# main.py - 应用启动时自动集成

async def lifespan(app: FastAPI):
    await start_health_probe_service()  # 启动后台探测
    yield
    await stop_health_probe_service()   # 关闭服务
```

**效果对比**：

| 指标 | 优化后 |
|-----|-------|
| 首次响应延迟 | <100ms |
| 健康状态更新 | 后台持续更新（120s 间隔） |
| 用户感知 | 完全无感知 |

---

#### 2.5.4 用户体验透明性

**已实现的透明机制**：

```
用户请求 → ChatService
              ↓
         ModelRouter（自动切换）
              ├─ 尝试 primary → 失败 → 自动切换（用户无感知）
              ├─ 尝试 fallback_0 → 成功 → 返回结果
              └─ 切换事件记录日志（便于运维排查）
```

**用户视角**：
- ✅ 无需关心使用的是哪个模型
- ✅ 无需关心切换过程
- ✅ 首次响应快速（<100ms）
- ✅ 最终都能得到响应（只要有可用的 fallback）
- ✅ 后台持续监控，提前发现问题

---

## 3. 手动配置方法

### 3.1 主备切换配置

#### 3.1.1 配置文件位置

```bash
config/llm_config/profiles.yaml
```

#### 3.1.2 配置结构说明

```yaml
profiles:
  main_agent:  # Profile 名称（角色级配置）
    description: "主 Agent 对话处理"
    
    # 主模型配置
    provider: "claude"                       # 提供商：claude/qwen/openai
    model: "claude-sonnet-4-5-20250929"     # 模型名称
    api_key_env: "ANTHROPIC_API_KEY"        # API Key 环境变量
    base_url: "https://api.anthropic.com"   # 可选：自定义 Base URL
    max_tokens: 64000                        # 最大输出 token
    temperature: 1.0                         # 温度参数
    enable_thinking: true                    # 启用深度推理
    thinking_budget: 10000                   # 推理 token 预算
    enable_caching: true                     # 启用 Prompt Caching
    timeout: 120.0                           # 超时时间（秒）
    max_retries: 3                           # 最大重试次数
    
    # 备选模型列表（按优先级排序）
    fallbacks:
      # 备选 1：同模型多服务商（Provider A）
      - provider: "claude"
        model: "claude-sonnet-4-5-20250929"
        api_key_env: "CLAUDE_API_KEY_VENDOR_A"
        base_url: "https://api.anthropic.com"
        max_tokens: 64000
        temperature: 1.0
        enable_thinking: true
        thinking_budget: 10000
        enable_caching: true
        timeout: 120.0
        max_retries: 3
      
      # 备选 2：同模型多服务商（Provider B）
      - provider: "claude"
        model: "claude-sonnet-4-5-20250929"
        api_key_env: "CLAUDE_API_KEY_VENDOR_B"
        base_url: "https://anthropic-proxy-b.example.com/v1"
        max_tokens: 64000
        temperature: 1.0
        enable_thinking: true
        thinking_budget: 10000
        enable_caching: true
        timeout: 120.0
        max_retries: 3
      
      # 备选 3：跨厂商主备（Qwen）
      - provider: "qwen"
        model: "qwen-max"
        api_key_env: "QWEN_API_KEY"
        base_url: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        temperature: 0.8
        top_p: 0.9
        max_tokens: 32000
        result_format: "message"
        repetition_penalty: 1.05
      
      # 备选 4：跨厂商主备（DeepSeek，待接入）
      # - provider: "openai"
      #   model: "deepseek-chat"
      #   api_key_env: "DEEPSEEK_API_KEY"
      #   base_url: "https://api.deepseek.com/v1"
    
    # 路由策略配置
    policy:
      max_failures: 2           # 最大失败次数（超过进入冷却）
      cooldown_seconds: 600     # 冷却时间（默认 10 分钟）
```

#### 3.1.3 配置优先级

```
fallbacks[0] → fallbacks[1] → fallbacks[2] → ... → primary（强制尝试）
```

**说明**：
- 主模型故障时，按 `fallbacks` 列表顺序依次尝试
- 所有备选模型均故障时，强制尝试主模型（避免完全不可用）

#### 3.1.4 多 Provider 策略

**策略 1：同模型多服务商（推荐）**

```yaml
# 适用场景：提升同一模型的可用性
# 优点：效果一致，无需适配
# 缺点：需要多个 API Key

primary:
  provider: "claude"
  model: "claude-sonnet-4-5-20250929"
  api_key_env: "ANTHROPIC_API_KEY"
  base_url: "https://api.anthropic.com"

fallbacks:
  - provider: "claude"
    model: "claude-sonnet-4-5-20250929"
    api_key_env: "CLAUDE_API_KEY_VENDOR_A"  # 不同 API Key
    base_url: "https://api.anthropic.com"
  
  - provider: "claude"
    model: "claude-sonnet-4-5-20250929"
    api_key_env: "CLAUDE_API_KEY_VENDOR_B"  # 不同 API Key
    base_url: "https://anthropic-proxy-b.example.com/v1"  # 不同 Base URL
```

**策略 2：跨厂商主备（容灾）**

```yaml
# 适用场景：降低单一厂商依赖风险
# 优点：成本优化，国内网络更稳定
# 缺点：效果可能有差距，需要充分测试

primary:
  provider: "claude"
  model: "claude-sonnet-4-5-20250929"

fallbacks:
  - provider: "qwen"
    model: "qwen-max"        # Qwen 最强模型
  
      # DeepSeek 待接入
      # - provider: "openai"
      #   model: "deepseek-chat"
```

---

### 3.2 Provider 切换配置

#### 3.2.1 环境变量覆盖（Profile 级）

**使用场景**：临时切换某个 Profile 的配置，不影响其他 Profile

**命名规则**：

```bash
LLM_<PROFILE_NAME>_<PARAMETER>=<VALUE>
```

**示例**：

```bash
# 将 main_agent 的主模型临时切换为 Qwen
export LLM_MAIN_AGENT_PROVIDER=qwen
export LLM_MAIN_AGENT_MODEL=qwen-max
export LLM_MAIN_AGENT_API_KEY_ENV=QWEN_API_KEY
export LLM_MAIN_AGENT_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1

# 将 intent_analyzer 的超时时间调整为 30s
export LLM_INTENT_ANALYZER_TIMEOUT=30.0
export LLM_INTENT_ANALYZER_MAX_RETRIES=5
```

**支持的参数**：

| 环境变量 | 对应配置项 | 类型 | 示例 |
|---------|-----------|------|------|
| `LLM_<PROFILE>_PROVIDER` | `provider` | str | `claude`, `qwen`, `openai` |
| `LLM_<PROFILE>_MODEL` | `model` | str | `qwen-max`, `gpt-4o` |
| `LLM_<PROFILE>_MAX_TOKENS` | `max_tokens` | int | `8192` |
| `LLM_<PROFILE>_TEMPERATURE` | `temperature` | float | `0.7` |
| `LLM_<PROFILE>_ENABLE_THINKING` | `enable_thinking` | bool | `true`, `false` |
| `LLM_<PROFILE>_TIMEOUT` | `timeout` | float | `60.0` |
| `LLM_<PROFILE>_MAX_RETRIES` | `max_retries` | int | `3` |
| `LLM_<PROFILE>_BASE_URL` | `base_url` | str | `https://api.example.com` |
| `LLM_<PROFILE>_API_KEY_ENV` | `api_key_env` | str | `CUSTOM_API_KEY` |

#### 3.2.2 路由策略覆盖

```bash
# 调整 ModelRouter 熔断策略
export LLM_ROUTER_MAX_FAILURES=3         # 最大失败次数
export LLM_ROUTER_COOLDOWN_SECONDS=180   # 冷却时间（秒）
```

#### 3.2.3 健康监控策略覆盖

```bash
# 调整 HealthMonitor 健康检测策略
export LLM_HEALTH_WINDOW_SECONDS=600              # 统计窗口（秒）
export LLM_HEALTH_MIN_SAMPLES=10                  # 最小样本数
export LLM_HEALTH_ERROR_RATE_THRESHOLD=0.2        # 错误率阈值（20%）
export LLM_HEALTH_AVG_LATENCY_MS_THRESHOLD=10000  # 延迟阈值（10s）
```

---

### 3.3 全局一键切换

#### 3.3.1 方式一：环境变量全局切换

**使用场景**：紧急情况下快速切换所有 Profile 到同一 Provider

```bash
# 全局切换到 Qwen
export LLM_FORCE_PROVIDER=qwen
export LLM_FORCE_MODEL=qwen-max  # 可选：指定模型
export LLM_FORCE_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
export LLM_FORCE_API_KEY_ENV=QWEN_API_KEY
```

**效果**：

```python
# 所有 Profile 都会被覆盖
main_agent:       provider=qwen, model=qwen-max
intent_analyzer:  provider=qwen, model=qwen-max  # 自动映射为 qwen-plus
lead_agent:       provider=qwen, model=qwen-max
worker_agent:     provider=qwen, model=qwen-max
critic_agent:     provider=qwen, model=qwen-max
```

**模型自动映射规则**：

| Profile | 默认映射模型 | 说明 |
|---------|------------|------|
| `intent_analyzer` | `qwen-plus` | 轻量级模型，低延迟 |
| 其他 Profile | `qwen-max` | 最强模型，推理能力强 |

#### 3.3.2 方式二：配置文件全局切换

**使用场景**：持久化的全局切换配置，适合长期运行

**配置位置**：

```bash
instances/{instance_name}/config.yaml
```

**配置示例**：

```yaml
# instances/my_agent/config.yaml

llm_global:
  enabled: true             # 🔴 启用全局覆盖
  provider: "qwen"          # 全局 Provider
  base_url: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
  api_key_env: "QWEN_API_KEY"
  compat: "qwen"
  
  # 模型映射（按 Profile 自定义）
  model_map:
    intent_analyzer: "qwen-plus"     # 意图分析使用轻量模型
    main_agent: "qwen-max"           # 主 Agent 使用最强模型
    lead_agent: "qwen-max"           # Lead Agent 使用最强模型
    worker_agent: "qwen-max"         # Worker Agent 使用最强模型
    critic_agent: "qwen-max"         # Critic Agent 使用最强模型
    default: "qwen-max"              # 其他 Profile 默认模型
```

**激活方式**：

```bash
# 方式 1：环境变量指定实例
export ZENFLUX_INSTANCE=my_agent

# 方式 2：环境变量指定配置文件
export LLM_GLOBAL_CONFIG_PATH=/path/to/config.yaml

# 方式 3：环境变量指定实例配置路径
export INSTANCE_CONFIG_PATH=/path/to/instances/my_agent/config.yaml
```

#### 3.3.3 优先级规则

```
环境变量全局切换 > 配置文件全局切换 > Profile 级环境变量 > profiles.yaml
```

**示例**：

```bash
# profiles.yaml 中配置：
main_agent:
  provider: claude
  model: claude-sonnet-4-5-20250929

# 配置文件全局切换：
llm_global:
  enabled: true
  provider: qwen
  model_map:
    main_agent: qwen-max

# 环境变量全局切换：
export LLM_FORCE_PROVIDER=openai
export LLM_FORCE_MODEL=gpt-4o

# 最终生效：
main_agent:
  provider: openai         # 来自 LLM_FORCE_PROVIDER
  model: gpt-4o            # 来自 LLM_FORCE_MODEL
```

---

### 3.4 健康探测配置

#### 3.4.1 配置文件（`config/llm_config/profiles.yaml`）

```yaml
# 🆕 V7.11 健康探测配置
health_probe:
  # 条件探测配置（V7.11：后台不健康时自动触发请求级确认）
  request_probe:
    timeout_seconds: 5.0   # 探针超时时间
    max_retries: 1         # 最大重试次数
    # 注意：V7.11 已移除 enabled 开关，改为条件探测策略
    # 后台健康 → 自动跳过（零延迟）
    # 后台不健康 → 自动执行请求级确认（≤5s）
  
  # 后台健康探测（与用户请求解耦）
  background_probe:
    enabled: true          # 启用后台健康探测
    interval_seconds: 120  # 探测间隔（秒）
    timeout_seconds: 10    # 单次探测超时
    profiles:              # 要探测的 Profile 列表
      - main_agent
      - intent_analyzer
      - lead_agent
      - worker_agent
      - critic_agent
```

#### 3.4.2 环境变量覆盖

```bash
# 条件探测（V7.11：无需配置 enabled，自动根据后台健康状态决定）
LLM_PROBE_TIMEOUT=5.0            # 超时时间（秒）

# 后台健康探测
LLM_HEALTH_PROBE_ENABLED=true    # 启用后台探测
LLM_HEALTH_PROBE_INTERVAL=120    # 探测间隔（秒）
LLM_HEALTH_PROBE_TIMEOUT=10      # 单次探测超时
LLM_HEALTH_PROBE_PROFILES=main_agent,intent_analyzer,lead_agent
```

#### 3.4.3 配置优先级

```
环境变量 > profiles.yaml > 默认值
```

#### 3.4.4 代码调用

```python
# 获取健康探测配置
from config.llm_config import get_health_probe_config

config = get_health_probe_config()
# {
#     "request_probe": {
#         "timeout_seconds": 5.0,
#         "max_retries": 1
#         # 注意：V7.11 移除 enabled，改为条件探测策略
#     },
#     "background_probe": {
#         "enabled": True,
#         "interval_seconds": 120,
#         "timeout_seconds": 10,
#         "profiles": ["main_agent", "intent_analyzer", ...]
#     }
# }

# V7.11：条件探测使用方式
from services.health_probe_service import get_health_probe_service

probe_service = get_health_probe_service()
if probe_service.is_healthy("main_agent"):
    # 后台健康 → 跳过请求级探测
    pass
else:
    # 后台不健康 → 执行请求级探测确认
    result = await llm_service.probe(max_retries=1)
```

#### 3.4.5 查询健康状态

```python
from services.health_probe_service import get_health_probe_service

# 获取服务实例
service = get_health_probe_service()

# 获取健康状态汇总
status = service.get_health_status()
# {
#     "overall": "healthy",
#     "profiles": {
#         "main_agent": {"status": "healthy", "latency_ms": 100},
#         "intent_analyzer": {"status": "degraded", "latency_ms": 200}
#     },
#     "running": True
# }

# 判断指定 Profile 是否健康
is_healthy = service.is_healthy("main_agent")
```

---

## 4. 核心组件详解

### 4.1 ModelRouter（模型路由器）

**文件路径**：`core/llm/router.py`

**核心职责**：

| 职责 | 方法 | 说明 |
|-----|------|------|
| **目标选择** | `_select_targets()` | 根据健康状态和熔断器选择可用模型 |
| **主备切换** | `create_message_async()` | 遍历 targets，失败时自动切换 |
| **健康判定** | `_target_available()` | 集成 HealthMonitor 和熔断器判定 |
| **失败记录** | `_record_failure()` | 累积失败计数，触发熔断 |
| **成功记录** | `_record_success()` | 重置失败计数，恢复可用 |
| **探针检测** | `probe()` | 主动探测模型可用性，支持高优先级恢复 |
| **工具过滤** | `_filter_tools_for_provider()` | 针对不同 Provider 过滤工具列表 |

**关键数据结构**：

```python
@dataclass
class RouteTarget:
    """路由目标"""
    service: BaseLLMService   # LLM 服务实例
    provider: LLMProvider     # 提供商（claude/qwen/openai）
    model: str                # 模型名称
    name: str                 # 目标唯一标识（用于日志和状态跟踪）

@dataclass
class RouterPolicy:
    """路由策略"""
    max_failures: int = 2           # 最大失败次数
    cooldown_seconds: int = 600     # 冷却时间（默认 10 分钟）
```

### 4.2 HealthMonitor（健康监控器）

**文件路径**：`core/llm/health_monitor.py`

**核心职责**：

| 职责 | 方法 | 说明 |
|-----|------|------|
| **成功记录** | `record_success()` | 记录成功调用，更新延迟指标 |
| **失败记录** | `record_failure()` | 记录失败调用，更新错误率 |
| **健康判定** | `is_healthy()` | 根据错误率和延迟判定健康状态 |
| **状态查询** | `get_status()` | 返回 `healthy`/`degraded`/`unhealthy` |
| **指标统计** | `get_stats()` | 返回统计指标（样本数、错误率、延迟） |

**统计指标**：

```python
{
    "sample_count": 50.0,         # 样本数量
    "error_rate": 0.12,           # 错误率（12%）
    "avg_latency_ms": 3500.0,     # 平均延迟（3.5s）
    "last_error": "APIConnectionError: timeout"  # 最后错误
}
```

### 4.3 UnifiedToolCaller（统一工具调用器）

**文件路径**：`core/tool/unified_tool_caller.py`

**核心职责**：

| 职责 | 方法 | 说明 |
|-----|------|------|
| **Skills 判定** | `_supports_skills_for_all_targets()` | 判断 LLM 服务是否对所有目标都支持 Skills |
| **Fallback 映射** | `get_fallback_tool_for_skill()` | 获取 Skill 对应的 fallback_tool |
| **能力修正** | `ensure_skill_fallback()` | 非 Claude 环境自动添加 fallback_tool |

**配置示例**：

```yaml
# config/capabilities.yaml

capabilities:
  code_execution:
    capability_id: "code_execution"
    recommended_skill: "code_tool"         # Claude Skills 名称
    fallback_tool: "execute_e2b_sandbox"   # 非 Claude 使用的工具
    description: "执行 Python 代码"
```

**工作流程**：

```
1. Agent 请求执行代码
   ↓
2. UnifiedToolCaller.ensure_skill_fallback()
   ├─ 检查 LLM 服务是否支持 Skills
   │  ├─ 支持（Claude）→ 使用 code_tool（Skills）
   │  └─ 不支持（Qwen）→ 自动添加 execute_e2b_sandbox（Fallback）
   ↓
3. Agent 调用工具
   ├─ Claude: 使用 code_tool（原生 Skills）
   └─ Qwen: 使用 execute_e2b_sandbox（E2B Sandbox）
```

### 4.4 配置加载器（Loader）

**文件路径**：`config/llm_config/loader.py`

**核心职责**：

| 职责 | 方法 | 说明 |
|-----|------|------|
| **配置加载** | `_load_config()` | 加载 `profiles.yaml` 配置文件 |
| **环境变量覆盖** | `_apply_env_overrides()` | 应用 Profile 级环境变量覆盖 |
| **全局覆盖** | `_apply_global_overrides()` | 应用全局一键切换配置 |
| **Profile 获取** | `get_llm_profile()` | 获取指定 Profile 的配置字典 |
| **健康探测配置** | `get_health_probe_config()` | 获取健康探测配置（🆕 V7.10） |
| **配置重载** | `reload_config()` | 重新加载配置文件（热更新） |

**使用示例**：

```python
from config.llm_config import get_llm_profile, get_health_probe_config
from core.llm import create_llm_service

# 获取 main_agent 配置
profile = get_llm_profile("main_agent")

# 创建 LLM 服务（自动支持主备切换）
llm = create_llm_service(**profile)

# 获取健康探测配置
health_config = get_health_probe_config()
```

### 4.5 健康探测服务（HealthProbeService）🆕 V7.10

**文件路径**：`services/health_probe_service.py`

**核心职责**：

| 职责 | 方法 | 说明 |
|-----|------|------|
| **服务启动** | `start()` | 启动后台探测任务 |
| **服务停止** | `stop()` | 停止后台探测任务 |
| **探测所有模型** | `probe_all()` | 探测所有配置的 Profile |
| **探测单个模型** | `_probe_profile()` | 探测单个 Profile |
| **健康状态查询** | `get_health_status()` | 返回健康状态汇总 |
| **健康判定** | `is_healthy()` | 判断指定 Profile 是否健康 |

**工作流程**：

```
应用启动 → start() → _probe_loop()
                        ↓
                   定期探测（120s 间隔）
                        ↓
                   probe_all() → _probe_profile()
                        ↓
                   更新 _probe_results
                        ↓
                   用户可查询 get_health_status()
```

**使用示例**：

```python
from services.health_probe_service import get_health_probe_service

# 获取服务实例
service = get_health_probe_service()

# 查询健康状态
status = service.get_health_status()

# 判断是否健康
is_healthy = service.is_healthy("main_agent")
```

---

## 5. 配置示例

### 5.1 混合策略（推荐）

**切换优先级**：Claude 原生 → Qwen-Max → Claude 代理

```yaml
profiles:
  main_agent:
    provider: "claude"
    model: "claude-sonnet-4-5-20250929"
    api_key_env: "ANTHROPIC_API_KEY"
    enable_thinking: true
    enable_caching: true
    
    fallbacks:
      # 优先级 1：Qwen-Max（跨厂商，成本低）
      - provider: "qwen"
        model: "qwen-max"
        api_key_env: "QWEN_API_KEY"
        base_url: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
      
      # 优先级 2：Claude 代理（同模型，网络备份）
      - provider: "claude"
        model: "claude-sonnet-4-5-20250929"
        api_key_env: "CLAUDE_API_KEY_VENDOR_A"
        base_url: "https://anthropic-proxy-a.example.com/v1"
    
    policy:
      max_failures: 2
      cooldown_seconds: 600
```

**优先级说明**：`fallbacks` 数组顺序即切换优先级，可自由调整满足不同需求。

**环境变量配置**：

```bash
# Claude API Key
export ANTHROPIC_API_KEY=sk-ant-api03-xxx

# Qwen API Key
export QWEN_API_KEY=sk-xxx
export QWEN_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
```

### 5.3 场景三：全局紧急切换到 Qwen

**目标**：Claude 服务完全不可用时，快速切换到 Qwen

```bash
# 方式 1：环境变量（最快）
export LLM_FORCE_PROVIDER=qwen
export LLM_FORCE_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
export LLM_FORCE_API_KEY_ENV=QWEN_API_KEY

# 方式 2：配置文件（持久化）
# 编辑 instances/my_agent/config.yaml
llm_global:
  enabled: true
  provider: "qwen"
  base_url: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
  api_key_env: "QWEN_API_KEY"
  model_map:
    intent_analyzer: "qwen-plus"
    default: "qwen-max"
```

### 5.4 场景四：开发环境手动切换单个 Profile

**目标**：测试某个 Profile 使用 Qwen 的效果

```bash
# 仅切换 main_agent 到 Qwen，其他 Profile 不受影响
export LLM_MAIN_AGENT_PROVIDER=qwen
export LLM_MAIN_AGENT_MODEL=qwen-max
export LLM_MAIN_AGENT_API_KEY_ENV=QWEN_API_KEY
export LLM_MAIN_AGENT_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
export LLM_MAIN_AGENT_TEMPERATURE=0.8
```

---

## 6. 监控与调试

### 6.1 日志输出

#### 6.1.1 模型切换日志

```bash
# 主模型故障，切换到备选
⚠️ 模型调用失败: target=claude:claude-sonnet-4-5-20250929, failures=1, error=APIConnectionError: timeout
⚠️ 模型调用失败: target=claude:claude-sonnet-4-5-20250929, failures=2, error=APITimeoutError
🔀 模型已切换: primary=claude:claude-sonnet-4-5-20250929 → selected=fallback_0:qwen:qwen-max

# 主模型恢复
✅ 模型恢复: target=claude:claude-sonnet-4-5-20250929
```

#### 6.1.2 健康状态变化日志

```bash
# 健康状态变化
🩺 LLM 健康状态变化: claude:claude-sonnet-4-5-20250929 -> unhealthy
🩺 LLM 健康状态变化: fallback_0:qwen:qwen-max -> healthy
🩺 LLM 健康状态变化: claude:claude-sonnet-4-5-20250929 -> healthy
```

#### 6.1.3 全局覆盖日志

```bash
# 全局一键切换
🚨 Profile 'main_agent' 启用全局覆盖(env): ['provider', 'model', 'base_url', 'api_key_env']
🚨 Profile 'intent_analyzer' 启用全局覆盖(config.yaml): ['provider', 'model', 'base_url', 'api_key_env']
```

### 6.2 监控指标

#### 6.2.1 健康监控指标查询

```python
from core.llm.health_monitor import get_llm_health_monitor

monitor = get_llm_health_monitor()

# 查询 Claude 健康状态
stats = monitor.get_stats("claude:claude-sonnet-4-5-20250929")
print(stats)
# {
#     "sample_count": 50.0,
#     "error_rate": 0.12,
#     "avg_latency_ms": 3500.0,
#     "last_error": "APIConnectionError: timeout"
# }

# 判定健康状态
is_healthy = monitor.is_healthy("claude:claude-sonnet-4-5-20250929")
print(is_healthy)  # False（错误率 12% > 10%）
```

#### 6.2.2 ModelRouter 状态查询

```python
from core.llm import create_llm_service
from config.llm_config import get_llm_profile

# 创建 LLM 服务
profile = get_llm_profile("main_agent")
llm = create_llm_service(**profile)

# 查询失败计数
if hasattr(llm, "_failure_counts"):
    print(llm._failure_counts)
    # {
    #     'claude:claude-sonnet-4-5-20250929': 2,
    #     'fallback_0:qwen:qwen-max': 0
    # }

# 查询最后选择的模型
if hasattr(llm, "_last_selected"):
    print(llm._last_selected)
    # 'fallback_0:qwen:qwen-max'
```

### 6.3 探针诊断

#### 6.3.1 手动探针测试

```python
from core.llm import create_llm_service
from config.llm_config import get_llm_profile

# 创建 LLM 服务
profile = get_llm_profile("main_agent")
llm = create_llm_service(**profile)

# 执行探针（包含不健康目标）
result = await llm.probe(include_unhealthy=True)
print(result)
# {
#     "primary": {
#         "name": "claude:claude-sonnet-4-5-20250929",
#         "provider": "claude",
#         "model": "claude-sonnet-4-5-20250929",
#         "base_url": "https://api.anthropic.com"
#     },
#     "selected": {
#         "name": "fallback_0:qwen:qwen-max",
#         "provider": "qwen",
#         "model": "qwen-max",
#         "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
#     },
#     "switched": True,
#     "errors": [
#         {
#             "target": "claude:claude-sonnet-4-5-20250929",
#             "provider": "claude",
#             "model": "claude-sonnet-4-5-20250929",
#             "error": "APIConnectionError: timeout"
#         }
#     ]
# }
```

#### 6.3.2 ChatService 条件探测日志

```bash
# 正常情况：后台健康，跳过探测（V7.11 条件探测）
✅ 后台健康，跳过请求级探测: role=simple_agent, profile=main_agent

# 异常情况：后台不健康，执行请求级确认
⚠️ 后台探测显示不健康，执行请求级确认: role=simple_agent, profile=main_agent
✅ [ChatService] LLM 探针成功: selected=fallback_0:qwen:qwen-max, switched=True

# 后台服务不可用时：优雅降级
⏭️ 后台探测服务不可用，跳过请求级探测: role=simple_agent
```

### 6.4 故障排查

#### 6.4.1 问题：主模型一直不可用

**排查步骤**：

1. 检查 API Key 是否有效

```bash
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-sonnet-4-5-20250929","max_tokens":1,"messages":[{"role":"user","content":"ping"}]}'
```

2. 检查网络连接

```bash
ping api.anthropic.com
traceroute api.anthropic.com
```

3. 检查健康监控器状态

```python
from core.llm.health_monitor import get_llm_health_monitor

monitor = get_llm_health_monitor()
stats = monitor.get_stats("claude:claude-sonnet-4-5-20250929")
print(stats)
```

4. 检查熔断器状态

```python
# 查看失败计数
print(llm._failure_counts)
print(llm._last_failure_ts)

# 手动重置（谨慎使用）
llm._failure_counts["claude:claude-sonnet-4-5-20250929"] = 0
llm._last_failure_ts["claude:claude-sonnet-4-5-20250929"] = 0.0
```

#### 6.4.2 问题：备选模型效果不如主模型

**解决方案**：

1. 调整备选模型参数（温度、top_p）

```yaml
fallbacks:
  - provider: "qwen"
    model: "qwen-max"
    temperature: 0.7  # 降低温度，提升确定性
    top_p: 0.85       # 降低 top_p，减少随机性
    repetition_penalty: 1.1  # 提高惩罚，降低重复
```

2. 启用 Qwen 思考模式（Qwen3 系列支持）

```yaml
fallbacks:
  - provider: "qwen"
    model: "qwen3-max-preview"  # Qwen3 系列
    enable_thinking: true        # 启用思考模式
    thinking_budget: 8000        # 思考 token 预算
```

3. 添加更高质量的备选模型

```yaml
fallbacks:
  - provider: "openai"
    model: "gpt-4o"  # GPT-4 级别模型
    api_key_env: "OPENAI_API_KEY"
```

#### 6.4.3 问题：工具调用失败（非 Claude 模型）

**排查步骤**：

1. 检查 UnifiedToolCaller 是否正常工作

```python
from core.tool.capability import get_capability_registry
from core.tool.unified_tool_caller import create_unified_tool_caller

registry = get_capability_registry()
caller = create_unified_tool_caller(registry)

# 检查 fallback_tool 映射
fallback = caller.get_fallback_tool_for_skill("code_tool")
print(fallback)  # 应该输出: execute_e2b_sandbox
```

2. 检查 capabilities.yaml 配置

```yaml
# 确保每个 Skill 都配置了 fallback_tool
capabilities:
  code_execution:
    recommended_skill: "code_tool"
    fallback_tool: "execute_e2b_sandbox"  # ✅ 必须配置
```

3. 检查工具是否正确注入

```python
# 查看实际传给 LLM 的工具列表
print(tools)  # 应该包含 execute_e2b_sandbox，而不是 code_tool
```

---

## 7. 最佳实践

### 7.1 生产环境推荐配置

#### 7.1.1 LLM Profile 配置

```yaml
# config/llm_config/profiles.yaml

# 健康探测配置（生产推荐，V7.11）
health_probe:
  # 条件探测（V7.11：自动根据后台健康状态决定是否执行）
  request_probe:
    timeout_seconds: 5.0   # 探针超时时间
    max_retries: 1         # 最大重试次数
    # 无需配置 enabled，条件探测策略自动生效：
    # - 后台健康 → 跳过（零延迟）✅
    # - 后台不健康 → 执行确认（≤5s）🛡️
  
  background_probe:
    enabled: true          # ✅ 启用后台健康探测
    interval_seconds: 120  # 2 分钟探测一次
    timeout_seconds: 10
    profiles:
      - main_agent
      - intent_analyzer
      - lead_agent
      - worker_agent
      - critic_agent

profiles:
  main_agent:
    # 主模型：Claude Sonnet（最强推理能力）
    provider: "claude"
    model: "claude-sonnet-4-5-20250929"
    api_key_env: "ANTHROPIC_API_KEY"
    enable_thinking: true
    enable_caching: true
    
    fallbacks:
      # 备选 1：同模型多 Provider（国内网络优化）
      - provider: "claude"
        model: "claude-sonnet-4-5-20250929"
        api_key_env: "CLAUDE_API_KEY_VENDOR_A"
        base_url: "https://anthropic-proxy-a.example.com/v1"
        enable_thinking: true
        enable_caching: true
      
      # 备选 2：Qwen-Max（国产最强，成本低）
      - provider: "qwen"
        model: "qwen-max"
        api_key_env: "QWEN_API_KEY"
        temperature: 0.8
        repetition_penalty: 1.05
    
    policy:
      max_failures: 2
      cooldown_seconds: 600   # 冷却时间（默认 10 分钟）
```

#### 7.1.2 环境变量配置

```bash
# .env 文件

# 条件探测配置（V7.11：无需配置 enabled，自动根据后台状态决定）
LLM_PROBE_TIMEOUT=5.0          # 探针超时时间（秒）

# 后台健康探测（默认启用）
LLM_HEALTH_PROBE_ENABLED=true
LLM_HEALTH_PROBE_INTERVAL=120  # 2 分钟探测一次
LLM_HEALTH_PROBE_TIMEOUT=10    # 单次探测 10s 超时

# 主备 API Key 配置
ANTHROPIC_API_KEY=sk-ant-xxx              # 主 API
CLAUDE_API_KEY_VENDOR_A=sk-ant-xxx        # Vendor A
CLAUDE_API_KEY_VENDOR_B=sk-ant-xxx        # Vendor B
QWEN_API_KEY=sk-xxx                       # Qwen 兜底
```

### 7.2 测试环境推荐配置

```yaml
profiles:
  main_agent:
    # 主模型：Qwen-Max（测试国产模型效果）
    provider: "qwen"
    model: "qwen-max"
    api_key_env: "QWEN_API_KEY"
    temperature: 0.8
    
    fallbacks:
      # 备选 1：Claude（对比效果差距）
      - provider: "claude"
        model: "claude-sonnet-4-5-20250929"
        api_key_env: "ANTHROPIC_API_KEY"
        enable_thinking: true
    
    policy:
      max_failures: 3
      cooldown_seconds: 60  # 测试环境缩短冷却时间
```

### 7.3 成本优化建议

| 场景 | 主模型 | 备选模型 | 成本节省 |
|-----|--------|---------|---------|
| **简单任务** | Claude Haiku | Qwen-Plus | ~70% |
| **中等任务** | Claude Sonnet | Qwen-Max | ~50% |
| **复杂任务** | Claude Opus | Qwen-Max | ~40% |
| **紧急容灾** | Claude Sonnet | Qwen-Max | ~50% |

### 7.4 安全建议

1. **API Key 隔离**：不同 Provider 使用不同环境变量
2. **权限最小化**：备用账号仅授予必要权限
3. **监控告警**：配置切换告警，及时发现异常
4. **定期测试**：每周测试备选模型是否可用

---

## 8. 附录

### 8.1 相关文件清单

| 文件路径 | 说明 |
|---------|------|
| `core/llm/router.py` | ModelRouter 实现 |
| `core/llm/health_monitor.py` | HealthMonitor 实现 |
| `core/llm/qwen.py` | Qwen LLM 服务实现 |
| `core/llm/claude.py` | Claude LLM 服务实现 |
| `core/llm/__init__.py` | LLM 模块入口，工厂函数 |
| `core/tool/unified_tool_caller.py` | UnifiedToolCaller 实现 |
| `services/health_probe_service.py` | 🆕 后台健康探测服务 |
| `services/chat_service.py` | ChatService（包含探针优化） |
| `config/llm_config/profiles.yaml` | LLM Profile 配置文件（含健康探测配置） |
| `config/llm_config/loader.py` | 配置加载器（含健康探测配置加载） |
| `config/capabilities.yaml` | 工具能力配置（含 fallback_tool） |
| `main.py` | 应用入口（集成健康探测服务启动） |

### 8.2 环境变量参考

#### 8.2.1 API Key 配置

| 环境变量 | 说明 | 示例 |
|---------|------|------|
| `ANTHROPIC_API_KEY` | Claude 主 API Key | `sk-ant-api03-xxx` |
| `CLAUDE_API_KEY_VENDOR_A` | Claude 备用 Provider A | `sk-ant-api03-yyy` |
| `CLAUDE_API_KEY_VENDOR_B` | Claude 备用 Provider B | `sk-ant-api03-zzz` |
| `QWEN_API_KEY` | Qwen API Key | `sk-xxx` |
| `QWEN_BASE_URL` | Qwen Base URL | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` |

#### 8.2.2 路由策略配置

| 环境变量 | 说明 | 示例 |
|---------|------|------|
| `LLM_FORCE_PROVIDER` | 全局强制 Provider | `qwen` |
| `LLM_FORCE_MODEL` | 全局强制模型 | `qwen-max` |
| `LLM_ROUTER_MAX_FAILURES` | 路由器最大失败次数 | `3` |
| `LLM_ROUTER_COOLDOWN_SECONDS` | 冷却时间（秒） | `120` |

#### 8.2.3 健康监控配置

| 环境变量 | 说明 | 示例 |
|---------|------|------|
| `LLM_HEALTH_ERROR_RATE_THRESHOLD` | 健康检测错误率阈值 | `0.2` |
| `LLM_HEALTH_AVG_LATENCY_MS_THRESHOLD` | 平均延迟阈值（ms） | `10000` |
| `LLM_HEALTH_WINDOW_SECONDS` | 统计窗口（秒） | `600` |
| `LLM_HEALTH_MIN_SAMPLES` | 最小样本数 | `10` |

#### 8.2.4 健康探测配置（V7.11 条件探测）

| 环境变量 | 说明 | 默认值 |
|---------|------|-------|
| `LLM_PROBE_TIMEOUT` | 条件探测超时（秒） | `5.0` |
| `LLM_HEALTH_PROBE_ENABLED` | 后台健康探测开关 | `true` |
| `LLM_HEALTH_PROBE_INTERVAL` | 后台探测间隔（秒） | `120` |
| `LLM_HEALTH_PROBE_TIMEOUT` | 后台探测超时（秒） | `10` |
| `LLM_HEALTH_PROBE_PROFILES` | 要探测的 Profile 列表 | `main_agent,intent_analyzer,...` |

> **注意**：V7.11 移除了 `LLM_PROBE_ENABLED`，改为条件探测策略。后台健康则自动跳过，后台不健康则自动执行请求级确认。

### 8.3 测试验证脚本

| 脚本路径 | 说明 |
|---------|------|
| `scripts/verify_probe_optimization.py` | 探针优化逻辑验证（单元测试） |
| `scripts/e2e_probe_production_test.py` | 端到端生产环境验证 |

**运行方式**：

```bash
# 逻辑验证
/Users/liuyi/Documents/langchain/liuy/bin/python3 \
  scripts/verify_probe_optimization.py

# 端到端验证
/Users/liuyi/Documents/langchain/liuy/bin/python3 \
  scripts/e2e_probe_production_test.py
```

### 8.4 参考文档

- [00-ARCHITECTURE-OVERVIEW.md](./00-ARCHITECTURE-OVERVIEW.md) - 整体架构概览
- [02-CAPABILITY-ROUTING.md](./02-CAPABILITY-ROUTING.md) - 能力路由机制
- [13-INVOCATION_STRATEGY_V2.md](./13-INVOCATION_STRATEGY_V2.md) - 调用策略 V2
- [MULTI_MODEL_PRICING.md](./MULTI_MODEL_PRICING.md) - 多模型定价对比
- [项目环境配置](../../.cursor/rules/00-project-setup/RULE.mdc) - Python 虚拟环境配置

---

## 9. 变更记录

| 日期 | 版本 | 变更内容 |
|-----|------|---------|
| 2026-01-23 | V1.0 | 初始版本：多模型容灾与动态切换方案 |
| 2026-01-23 | V2.0 | 集成探针优化：三阶段优化方案、配置管理、端到端验证 |
| 2026-01-23 | V2.1 | 重构为条件探测策略：后台健康则跳过，不健康则确认 |

---

**文档维护者**: ZenFlux Agent Team  
**最后更新**: 2026-01-23  
**版本**: V2.1
