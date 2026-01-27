# gRPC Context Canceled 错误排查和解决

## 问题描述

```
"error": "rpc error: code = Canceled desc = context canceled",
"stacktrace": "zen0-backend/pkg/zenflux.(*client).consumeStream\n\tzen0-backend/pkg/zenflux/client.go:375"
```

## 根本原因

这个错误可能由以下几个原因导致：

### 原因 1：AWS NLB 空闲超时（最常见）⚠️

**AWS Network Load Balancer 默认的 TCP 空闲超时是 350 秒（约 5.8 分钟）**。

即使客户端和服务端都配置了 30 分钟超时，如果通过 NLB 访问服务，NLB 会在 350 秒后断开空闲连接，导致：

1. 客户端收到 `context canceled` 错误
2. 服务端检测到 `context.cancelled()` 并停止流式响应

> 💡 **关键点**：这是 **TCP 层面的超时**，应用层心跳可能无法完全解决问题。

### 原因 2：客户端超时配置过短

1. Go 客户端代码中硬编码了过短的超时（如 5 分钟）
2. Agent 处理长时间任务（如 PPT 生成、视频处理）超过配置的超时
3. 客户端 context 超时后主动取消连接

### 原因 3：中间网络设备超时

防火墙、NAT 网关等网络设备可能有自己的连接超时限制。

## 超时配置对比

### 生产环境配置（通过 AWS NLB）

#### 修复前（问题配置）

| 层级 | 配置项 | 超时时间 | 状态 |
|------|--------|----------|------|
| 客户端 | timeout | 30 分钟 | ✅ 正确 |
| 客户端 | keepalive_time | 30 秒 | ✅ 正确 |
| **AWS NLB** | **idle_timeout** | **350 秒 (5.8分钟)** | ⚠️ **瓶颈！** |
| gRPC 服务端 | max_connection_idle | 30 分钟 | ✅ 正确 |
| Redis 订阅 | subscribe_events timeout | 30 分钟 | ✅ 正确 |

#### 修复后（推荐配置）

| 层级 | 配置项 | 超时时间 | 状态 |
|------|--------|----------|------|
| 客户端 | timeout | 30 分钟 | ✅ 正确 |
| 客户端 | keepalive_time | **60 秒** | ✅ **更频繁** |
| **AWS NLB** | **idle_timeout** | **1800 秒 (30分钟)** | ✅ **已修复** |
| gRPC 服务端 | max_connection_idle | 30 分钟 | ✅ 正确 |
| Redis 订阅 | subscribe_events timeout | 30 分钟 | ✅ 正确 |

### 测试环境配置（直连，无 NLB）

#### 修复前

| 组件 | 配置项 | 超时时间 | 问题 |
|------|--------|----------|------|
| Go 客户端 | `context.WithTimeout` | 5 分钟 | ⚠️ **太短** |
| gRPC 服务端 | `max_connection_idle` | 5 分钟 | ⚠️ **太短** |
| Redis 订阅 | `subscribe_events timeout` | 30 分钟 | ✅ 合理 |

#### 修复后

| 组件 | 配置项 | 超时时间 | 状态 |
|------|--------|----------|------|
| Go 客户端 | `context.WithTimeout` | **30 分钟** | ✅ **已修复** |
| gRPC 服务端 | `max_connection_idle` | **30 分钟** | ✅ **已修复** |
| Redis 订阅 | `subscribe_events timeout` | 30 分钟 | ✅ 合理 |

## 修复方案

### 🎯 方案 1：调整 AWS NLB 空闲超时（生产环境 - 最重要）

如果你的服务通过 AWS NLB 暴露，**这是必须要做的修改**！

详细步骤请参考：[AWS NLB 超时配置指南](./aws-nlb-timeout-fix.md)

**快速修复（使用 AWS CLI）**：

```bash
# 1. 获取 NLB ARN
aws elbv2 describe-load-balancers \
  --names zen0-b-Publi-3WSjpP2omnbc \
  --query 'LoadBalancers[0].LoadBalancerArn' \
  --output text

# 2. 修改空闲超时为 30 分钟
aws elbv2 modify-load-balancer-attributes \
  --load-balancer-arn <YOUR_NLB_ARN> \
  --attributes Key=idle_timeout.timeout_seconds,Value=1800

# 3. 验证修改
aws elbv2 describe-load-balancer-attributes \
  --load-balancer-arn <YOUR_NLB_ARN> \
  | jq '.Attributes[] | select(.Key == "idle_timeout.timeout_seconds")'
```

**预期输出**：
```json
{
  "Key": "idle_timeout.timeout_seconds",
  "Value": "1800"
}
```

### 🔧 方案 2：调整测试客户端超时（已完成）

### 2. Go 测试客户端超时调整

**文件**: `grpc_client_go/cmd/main.go`

```go
// 修复前
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)

// 修复后
ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
```

### 3. gRPC 服务端空闲超时调整

**文件**: `grpc_server/server.py`

```python
# 修复前
max_connection_idle = int(os.getenv("GRPC_MAX_CONNECTION_IDLE_MS", "300000"))  # 5 分钟

# 修复后
max_connection_idle = int(os.getenv("GRPC_MAX_CONNECTION_IDLE_MS", "1800000"))  # 30 分钟
```

### 4. 服务端已有的保护机制

**文件**: `services/redis_manager.py`

- **心跳机制**: 每 30 秒无事件时发送 `ping` 心跳，保持连接活跃
- **客户端断开检测**: 服务端在循环中定期检查 `context.cancelled()`
- **优雅退出**: 检测到断开后立即停止流式响应，记录日志

```python
# 心跳机制（redis_manager.py:666-676）
idle_seconds = (datetime.now() - last_event_time).total_seconds()
if idle_seconds >= ping_interval:
    ping_event = {
        "type": "ping",
        "timestamp": int(datetime.now().timestamp() * 1000),
        "session_id": session_id
    }
    yield ping_event
    last_event_time = datetime.now()
```

```python
# 客户端断开检测（grpc_server/chat_servicer.py:222-227）
if context.cancelled():
    logger.warning(
        f"⚠️ gRPC 客户端已断开连接，停止流式响应: "
        f"user_id={request.user_id}, events_sent={event_count}"
    )
    return
```

## 环境变量配置

如果需要进一步调整，可以通过环境变量覆盖默认值：

```bash
# gRPC 服务器配置
export GRPC_KEEPALIVE_TIME_MS=30000              # Keepalive ping 间隔（30 秒）
export GRPC_KEEPALIVE_TIMEOUT_MS=10000           # Keepalive ping 超时（10 秒）
export GRPC_MAX_CONNECTION_IDLE_MS=1800000       # 连接空闲超时（30 分钟）
export GRPC_MAX_CONNECTION_AGE_MS=3600000        # 连接最大生命周期（1 小时）
export GRPC_MAX_CONNECTION_AGE_GRACE_MS=60000    # 连接优雅关闭时间（1 分钟）
```

### 🔍 方案 3：检查生产客户端配置

你的生产客户端配置看起来是正确的：

```yaml
zenflux:
  timeout: 30m          # ✅ 正确
  keepalive_time: 30s   # ✅ 正确
```

但需要确认 `zen0-backend` 代码是否正确读取并应用了这些配置。

检查 `zen0-backend/pkg/zenflux/client.go` 中的代码：

```go
// ✅ 正确：使用配置的超时
timeout := config.Timeout  // 应该是 30m
ctx, cancel := context.WithTimeout(context.Background(), timeout)

// ❌ 错误：硬编码超时
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
```

## 验证修复

### 1. 验证 NLB 配置（生产环境）

```bash
# 检查当前 NLB 空闲超时
aws elbv2 describe-load-balancer-attributes \
  --load-balancer-arn <YOUR_NLB_ARN> \
  | jq '.Attributes[] | select(.Key == "idle_timeout.timeout_seconds")'
```

### 2. 重新编译 Go 客户端（测试环境）

```bash
cd grpc_client_go
go build -o grpc_client ./cmd/main.go
```

### 3. 重启 gRPC 服务器（如果修改了服务端）

```bash
# 重启服务以应用新的超时配置
python main.py
```

### 4. 测试长时间任务

```bash
# 发送一个需要较长处理时间的任务
./grpc_client -addr "localhost:50051" -msg "生成一份 50 页的 PPT"
```

### 5. 监控日志

**正常情况**（修复后）：
```
✅ gRPC 流式聊天完成: events_sent=120
```

**异常情况**（如果还有问题）：
```
⚠️ gRPC 客户端已断开连接，停止流式响应: user_id=xxx, events_sent=50
```

## 进一步优化建议

### 1. Agent 定期发送进度事件

对于长时间运行的任务，Agent 应该定期发送进度事件，让客户端知道任务还在进行中。

**示例**：
```python
# 在工具执行过程中定期发送进度
await self.emit_event({
    "type": "tool_progress",
    "tool_name": "ppt_generator",
    "progress": 0.5,  # 50%
    "message": "正在生成第 25/50 页..."
})
```

### 2. 实现断点续传

对于超长任务，可以实现断点续传机制：

1. 客户端超时后不报错，而是记录最后收到的 `event_seq`
2. 使用 `ReconnectStream` 接口重连，传入 `after_seq`
3. 服务端从断点处继续推送事件

**示例**：
```go
// 客户端自动重连逻辑
var lastSeq int64 = 0
for {
    stream, err := client.ChatStream(ctx, req)
    if err != nil {
        // 超时或断开，尝试重连
        reconnectReq := &ReconnectRequest{
            SessionId: sessionId,
            AfterSeq: lastSeq,
        }
        stream, err = client.ReconnectStream(ctx, reconnectReq)
    }
    
    // 接收事件
    for {
        event, err := stream.Recv()
        if err != nil {
            break
        }
        lastSeq = event.Seq
        // 处理事件...
    }
}
```

### 3. 监控和告警

添加指标监控：

- 平均任务处理时间
- 超时任务数量
- 客户端断开频率

**Prometheus 指标示例**：
```python
from prometheus_client import Histogram, Counter

task_duration = Histogram('agent_task_duration_seconds', 'Agent 任务处理时间')
context_cancelled_total = Counter('grpc_context_cancelled_total', 'gRPC context 取消次数')

# 在代码中记录
with task_duration.time():
    await agent.process_task()

if context.cancelled():
    context_cancelled_total.inc()
```

## 相关文件

- `grpc_client_go/cmd/main.go` - Go 客户端
- `grpc_server/server.py` - gRPC 服务器配置
- `grpc_server/chat_servicer.py` - Chat 服务实现
- `services/redis_manager.py` - Redis 事件订阅和心跳
- `services/chat_service.py` - Chat 业务逻辑

## 常见问题

### Q1: 如何确认是 NLB 导致的问题？

**A**: 观察错误发生的时间：

- 如果连接总是在 **5-6 分钟**左右断开 → 很可能是 NLB 的 350 秒超时
- 如果连接在其他时间断开 → 可能是客户端或服务端的配置问题

### Q2: 为什么应用层心跳没有解决 NLB 超时问题？

**A**: NLB 的空闲超时是 **TCP 层面**的：

- 应用层心跳（如 Redis ping）只是 gRPC 数据包
- 如果这些数据包能正常通过 NLB，理论上应该能重置空闲计时器
- 但实际可能受 NLB 的流量类型识别、健康检查等因素影响
- **最可靠的方法是直接增加 NLB 的 idle_timeout**

### Q3: 为什么选择 30 分钟超时？

**A**: 基于以下考虑：

- PPT 生成（50 页）：5-10 分钟
- 视频处理：10-20 分钟
- 复杂数据分析：5-15 分钟
- 留有安全余量：30 分钟

### Q4: 30 分钟会不会太长？

**A**: 不会，因为：

1. **只是超时上限**：正常任务完成后会立即结束
2. **有心跳机制**：确保连接活跃，不会占用资源
3. **可以提前取消**：客户端可以随时调用 `cancel()`

### Q5: 如果任务超过 30 分钟怎么办？

**A**: 有几个选项：

1. **继续增加超时**：修改配置
2. **拆分任务**：将大任务拆成多个小任务
3. **异步处理**：使用非流式模式，任务完成后通过回调通知
4. **断点续传**：实现重连机制

## 总结

### 🎯 核心问题

在生产环境中，**AWS NLB 的默认 350 秒空闲超时** 是导致 `context canceled` 错误的最可能原因。

### ✅ 解决步骤

1. **立即修复**：将 AWS NLB 的 `idle_timeout.timeout_seconds` 从 350 秒增加到 **1800 秒（30 分钟）**
2. **验证配置**：确认客户端 `timeout: 30m` 配置被正确读取和应用
3. **增强心跳**：可选地将客户端 `keepalive_time` 从 30s 调整为 60s
4. **监控日志**：观察修复后的效果，确认不再出现 5-6 分钟超时

### 📊 优先级

| 修复项 | 优先级 | 影响 | 工作量 |
|--------|--------|------|--------|
| 调整 NLB idle_timeout | 🔴 **P0** | 解决 90% 的问题 | 5 分钟 |
| 验证客户端配置读取 | 🟡 P1 | 确保配置生效 | 30 分钟 |
| 调整服务端超时 | 🟢 P2 | 防御性优化 | 已完成 |
| 实现断点续传 | 🔵 P3 | 超长任务支持 | 1-2 天 |

### 🔗 相关文档

- [AWS NLB 超时配置指南](./aws-nlb-timeout-fix.md) - 详细的 NLB 配置步骤
- [gRPC 服务端配置](../grpc_server/server.py) - 服务端超时配置
- [Redis 事件订阅](../services/redis_manager.py) - 心跳机制实现

### 💡 这个修复是向后兼容的

- ✅ 不影响现有的短任务
- ✅ 支持更长时间的任务执行
- ✅ 无需修改客户端代码（如果配置正确）
- ✅ 对终端用户透明
