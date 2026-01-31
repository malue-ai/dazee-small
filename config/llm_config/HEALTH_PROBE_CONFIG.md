# 健康探测配置快速参考

## 概述

本文档提供 LLM 健康探测配置的快速参考，包括配置项说明、环境变量、使用示例。

---

## 配置文件

### 位置

```
config/llm_config/profiles.yaml
```

### 配置结构

```yaml
# 🆕 V7.10 健康探测配置
health_probe:
  # 请求链路探针（短期优化：默认禁用）
  request_probe:
    enabled: false         # 生产环境推荐 false
    timeout_seconds: 5.0   # 探针超时时间
    max_retries: 1         # 最大重试次数
  
  # 后台健康探测（长期优化：与用户请求解耦）
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

---

## 环境变量

### 请求链路探针

| 环境变量 | 说明 | 默认值 | 推荐值（生产） |
|---------|------|-------|--------------|
| `LLM_PROBE_ENABLED` | 是否启用请求链路探针 | `false` | `false` |
| `LLM_PROBE_TIMEOUT` | 探针超时时间（秒） | `5.0` | `5.0` |

### 后台健康探测

| 环境变量 | 说明 | 默认值 | 推荐值（生产） |
|---------|------|-------|--------------|
| `LLM_HEALTH_PROBE_ENABLED` | 是否启用后台健康探测 | `true` | `true` |
| `LLM_HEALTH_PROBE_INTERVAL` | 探测间隔（秒） | `120` | `120` |
| `LLM_HEALTH_PROBE_TIMEOUT` | 单次探测超时（秒） | `10` | `10` |
| `LLM_HEALTH_PROBE_PROFILES` | 要探测的 Profile 列表（逗号分隔） | 所有主要 Profile | 根据需要配置 |

---

## 配置优先级

```
环境变量 > profiles.yaml > 默认值
```

**示例**：

```bash
# profiles.yaml 中配置
health_probe:
  request_probe:
    enabled: false
    timeout_seconds: 5.0

# 环境变量覆盖（优先级更高）
export LLM_PROBE_ENABLED=true
export LLM_PROBE_TIMEOUT=3.0

# 最终生效：
# enabled: true（来自环境变量）
# timeout_seconds: 3.0（来自环境变量）
```

---

## 使用示例

### 获取配置

```python
from config.llm_config import get_health_probe_config

config = get_health_probe_config()

# 输出示例：
# {
#     "request_probe": {
#         "enabled": False,
#         "timeout_seconds": 5.0,
#         "max_retries": 1
#     },
#     "background_probe": {
#         "enabled": True,
#         "interval_seconds": 120,
#         "timeout_seconds": 10,
#         "profiles": ["main_agent", "intent_analyzer", ...]
#     }
# }
```

### 查询健康状态

```python
from services.health_probe_service import get_health_probe_service

# 获取服务实例
service = get_health_probe_service()

# 获取健康状态汇总
status = service.get_health_status()
print(status)
# {
#     "overall": "healthy",
#     "profiles": {
#         "main_agent": {
#             "status": "healthy",
#             "latency_ms": 100,
#             "last_probe_seconds_ago": 30
#         },
#         "intent_analyzer": {
#             "status": "degraded",
#             "latency_ms": 200,
#             "last_probe_seconds_ago": 30
#         }
#     },
#     "enabled": True,
#     "interval_seconds": 120,
#     "running": True
# }

# 判断指定 Profile 是否健康
is_healthy = service.is_healthy("main_agent")
print(is_healthy)  # True
```

---

## 生产环境配置

### .env 文件

```bash
# 请求链路探针（默认禁用，不阻塞用户）
LLM_PROBE_ENABLED=false

# 后台健康探测（默认启用，提前发现问题）
LLM_HEALTH_PROBE_ENABLED=true
LLM_HEALTH_PROBE_INTERVAL=120  # 2 分钟探测一次
LLM_HEALTH_PROBE_TIMEOUT=10    # 单次探测 10s 超时
```

### 调试配置

```bash
# 启用请求链路探针（调试用）
LLM_PROBE_ENABLED=true
LLM_PROBE_TIMEOUT=5.0

# 缩短后台探测间隔（快速验证）
LLM_HEALTH_PROBE_INTERVAL=30  # 30 秒探测一次
```

---

## 常见问题

### Q1: 为什么请求链路探针默认禁用？

**A**: 请求链路探针会在用户请求时同步执行，导致首次响应延迟（500ms~60s）。禁用后依赖 ModelRouter 内部切换机制和后台健康探测，用户体验更好。

### Q2: 后台健康探测多久执行一次？

**A**: 默认 120 秒（2 分钟）探测一次。可通过 `LLM_HEALTH_PROBE_INTERVAL` 环境变量调整。

### Q3: 如何查看当前健康状态？

**A**: 使用 `get_health_probe_service().get_health_status()` 查询。

### Q4: 探测失败会影响用户请求吗？

**A**: 不会。后台探测与用户请求完全解耦，探测失败不影响用户体验。

### Q5: 如何临时启用请求链路探针？

**A**: 设置环境变量 `LLM_PROBE_ENABLED=true`，用于调试时主动探测。

---

## 相关文档

- [多模型容灾与动态切换方案](../../docs/architecture/24-MULTI-MODEL-FAILOVER-STRATEGY.md)
- [LLM 配置管理 README](./README.md)
- [项目环境配置](../../.cursor/rules/00-project-setup/RULE.mdc)

---

**最后更新**: 2026-01-23  
**版本**: V1.0
