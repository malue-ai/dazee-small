# 容错机制使用指南

本文档介绍如何使用 ZenFlux Agent 的容错机制（超时、重试、熔断、降级）。

## 1. 超时控制

### 1.1 使用装饰器

```python
from core.resilience import with_timeout

@with_timeout(timeout=60, timeout_type="llm")
async def call_llm(prompt: str):
    # 自动在 60 秒后超时
    return await llm.generate(prompt)
```

### 1.2 使用上下文管理器

```python
from core.resilience.timeout import TimeoutContext

async with TimeoutContext(timeout=30):
    result = await long_running_task()
```

### 1.3 配置超时时间

在 `config/resilience.yaml` 中配置：

```yaml
timeout:
  llm_timeout: 60.0      # LLM 调用
  tool_timeout: 30.0     # 工具执行
  database_timeout: 5.0  # 数据库操作
  cache_timeout: 2.0     # 缓存操作
```

## 2. 重试机制

### 2.1 使用装饰器

```python
from core.resilience import with_retry

@with_retry(max_retries=3, base_delay=1.0)
async def call_external_api():
    # 失败后自动重试，使用指数退避
    return await api.call()
```

### 2.2 可重试的错误类型

默认可重试的错误：
- `ConnectionError`: 网络连接错误
- `TimeoutError`: 超时错误
- HTTP 状态码：429（限流）、502、503、504

### 2.3 配置重试策略

```yaml
retry:
  max_retries: 3           # 最大重试次数
  base_delay: 0.5          # 基础延迟（秒）
  max_delay: 60.0          # 最大延迟（秒）
  exponential_base: 2.0    # 指数基数
```

重试延迟计算：`delay = base_delay * (exponential_base ** attempt)`

示例：
- 第 1 次重试：0.5s
- 第 2 次重试：1.0s
- 第 3 次重试：2.0s

## 3. 熔断器

### 3.1 使用熔断器

```python
from core.resilience import CircuitBreaker, get_circuit_breaker

# 获取熔断器实例
breaker = get_circuit_breaker("llm_service")

# 方式 1: 使用上下文管理器
async with breaker:
    result = await call_llm()

# 方式 2: 使用 call 方法
result = await breaker.call(call_llm, prompt="...")
```

### 3.2 熔断器状态

熔断器有三种状态：

1. **CLOSED（关闭）**: 正常工作
2. **OPEN（打开）**: 熔断中，直接拒绝请求
3. **HALF_OPEN（半开）**: 尝试恢复，允许少量请求

状态转换：
```
CLOSED --[失败次数达阈值]--> OPEN
OPEN --[超时后]--> HALF_OPEN
HALF_OPEN --[成功次数达阈值]--> CLOSED
HALF_OPEN --[任意失败]--> OPEN
```

### 3.3 配置熔断器

```yaml
circuit_breakers:
  llm_service:
    failure_threshold: 5      # 失败 5 次触发熔断
    success_threshold: 2      # 成功 2 次恢复
    timeout: 60.0             # 熔断 60 秒
    window_size: 10           # 滑动窗口大小
    half_open_max_calls: 1    # 半开状态最大并发数
```

### 3.4 查看熔断器状态

```python
breaker = get_circuit_breaker("llm_service")
stats = breaker.get_stats()

print(f"状态: {stats['state']}")
print(f"成功率: {stats['success_rate']:.2%}")
print(f"失败次数: {stats['failure_count']}")
```

## 4. 降级策略

### 4.1 注册降级策略

```python
from core.resilience import register_fallback, FallbackType

def cached_response():
    return {"content": "使用缓存响应"}

register_fallback(
    "llm_service",
    cached_response,
    FallbackType.CACHED_RESPONSE
)
```

### 4.2 使用降级装饰器

```python
from core.resilience import get_fallback_strategy

strategy = get_fallback_strategy()

@strategy.with_fallback("llm_service")
async def call_llm():
    # 失败时自动降级
    return await llm.generate()
```

### 4.3 降级类型

```python
class FallbackType(Enum):
    CACHED_RESPONSE = "cached_response"      # 返回缓存
    DEFAULT_RESPONSE = "default_response"    # 返回默认值
    SKIP = "skip"                            # 跳过该步骤
    SIMPLIFIED = "simplified"                # 使用简化版本
```

## 5. 组合使用

### 5.1 完整的容错链

```python
from core.resilience import (
    with_timeout,
    with_retry,
    get_circuit_breaker,
    get_fallback_strategy
)

# 1. 获取熔断器和降级策略
breaker = get_circuit_breaker("llm_service")
strategy = get_fallback_strategy()

# 2. 组合装饰器
@strategy.with_fallback("llm_service")      # 最外层：降级
@with_retry(max_retries=3)                  # 中间层：重试
@with_timeout(timeout_type="llm")           # 最内层：超时
async def call_llm_safe(prompt: str):
    async with breaker:                      # 熔断保护
        return await llm.generate(prompt)
```

执行流程：
1. 检查熔断器状态
2. 设置超时控制
3. 失败时自动重试（指数退避）
4. 重试失败后触发降级

### 5.2 实际应用示例

```python
class ChatService:
    def __init__(self):
        self.llm_breaker = get_circuit_breaker("llm_service")
        self.fallback_strategy = get_fallback_strategy()
    
    async def chat(self, message: str):
        try:
            # 使用容错机制调用 LLM
            response = await self._call_llm_safe(message)
            return response
        except Exception as e:
            logger.error(f"聊天失败: {e}")
            raise
    
    @with_retry(max_retries=3)
    @with_timeout(timeout_type="llm")
    async def _call_llm_safe(self, message: str):
        async with self.llm_breaker:
            # 实际的 LLM 调用
            return await self.llm.generate(message)
```

## 6. 健康检查

### 6.1 存活探针

```bash
curl http://localhost:8000/health/live
```

返回：
```json
{
  "status": "alive",
  "timestamp": 1699999999.999
}
```

### 6.2 就绪探针

```bash
curl http://localhost:8000/health/ready
```

返回：
```json
{
  "status": "ready",
  "checks": {
    "redis": {"status": "healthy"},
    "database": {"status": "healthy"},
    "llm": {"status": "healthy"}
  },
  "timestamp": 1699999999.999
}
```

### 6.3 健康指标

```bash
curl http://localhost:8000/health/metrics
```

返回：
```json
{
  "status": "ok",
  "metrics": {
    "circuit_breakers": {
      "llm_service": {
        "state": "closed",
        "success_rate": 0.95,
        "failure_count": 0
      }
    },
    "system": {
      "cpu_percent": 15.2,
      "memory_mb": 256.5
    }
  }
}
```

## 7. 最佳实践

### 7.1 选择合适的超时时间

- **LLM 调用**: 60-120 秒（复杂任务需要更长）
- **工具执行**: 30-60 秒
- **数据库查询**: 3-5 秒
- **缓存操作**: 1-2 秒

### 7.2 重试策略

- **幂等操作**: 可以重试
- **非幂等操作**: 谨慎重试（如支付、创建订单）
- **用户可见操作**: 重试次数不宜过多

### 7.3 熔断阈值

- **高频服务**: failure_threshold = 5-10
- **低频服务**: failure_threshold = 3-5
- **关键服务**: 熔断时间短（30s），快速恢复

### 7.4 降级策略

- **优先级 1**: 返回缓存数据
- **优先级 2**: 返回默认数据
- **优先级 3**: 跳过可选功能
- **优先级 4**: 返回错误提示

## 8. 监控与告警

### 8.1 日志

容错模块会自动记录关键事件：

```
✅ 超时配置已更新: LLM=60s, Tool=30s, DB=5s
⚠️ call_llm 失败，0.50s 后重试 (尝试 1/3): TimeoutError
🔴 熔断器 llm_service 打开 (失败次数: 5, 超时: 30s)
🟡 熔断器 llm_service 转为半开状态（尝试恢复）
🟢 熔断器 llm_service 恢复正常（关闭状态）
```

### 8.2 指标收集

建议监控的指标：
- 熔断器状态（state）
- 成功率（success_rate）
- 平均响应时间
- 重试次数
- 降级触发次数

### 8.3 告警规则

- 熔断器打开 → 立即告警
- 成功率 < 90% → 警告
- 平均响应时间 > 阈值 → 警告
- 重试次数异常增加 → 警告

## 9. 故障排查

### 9.1 服务频繁超时

1. 检查超时配置是否合理
2. 检查 LLM API 响应时间
3. 检查网络连接质量
4. 考虑增加超时时间或优化请求

### 9.2 熔断器频繁打开

1. 查看熔断器统计信息
2. 检查上游服务健康状态
3. 调整熔断阈值
4. 实施降级策略

### 9.3 重试无效

1. 确认错误类型可重试
2. 检查重试延迟是否足够
3. 检查重试次数配置
4. 考虑添加自定义重试逻辑

## 10. 常见问题

**Q: 超时和重试的区别？**

A: 超时控制单次调用的最长时间；重试在失败后自动再次尝试。两者可以组合使用。

**Q: 熔断器打开后，请求立即失败吗？**

A: 是的。熔断器打开后会立即拒绝请求（抛出 `CircuitBreakerOpenError`），避免雪崩。

**Q: 降级策略何时触发？**

A: 当所有重试都失败后，会触发降级策略（如果已配置）。

**Q: 如何禁用某个服务的容错机制？**

A: 在配置文件中设置 `enabled: false`，或不添加装饰器。
