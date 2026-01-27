# AWS NLB 空闲超时配置指南

## 问题描述

当通过 AWS Network Load Balancer (NLB) 访问 gRPC 流式服务时，即使客户端和服务端都配置了长超时（如 30 分钟），连接仍然在约 5-6 分钟后断开，报错：

```
"error": "rpc error: code = Canceled desc = context canceled"
```

## 根本原因

AWS NLB 默认的 **TCP 空闲超时是 350 秒（约 5.8 分钟）**。当 gRPC 流在这段时间内没有数据传输时，NLB 会主动断开连接。

## 解决方案

### 方案 1：增加 NLB 空闲超时（推荐）

#### 使用 AWS Console

1. 登录 AWS Console
2. 进入 EC2 > Load Balancers
3. 找到你的 NLB（`zen0-b-Publi-3WSjpP2omnbc`）
4. 点击 "Attributes" 标签
5. 编辑 "Idle timeout" 设置
6. 将超时时间改为 **1800 秒（30 分钟）**
7. 保存更改

#### 使用 AWS CLI

```bash
aws elbv2 modify-load-balancer-attributes \
  --load-balancer-arn arn:aws:elasticloadbalancing:ap-southeast-1:ACCOUNT_ID:loadbalancer/net/zen0-b-Publi-3WSjpP2omnbc/XXXXXXXX \
  --attributes \
    Key=idle_timeout.timeout_seconds,Value=1800
```

#### 使用 Terraform

```hcl
resource "aws_lb" "nlb" {
  name               = "zen0-backend-nlb"
  load_balancer_type = "network"
  
  # 其他配置...
  
  # 🔧 增加空闲超时到 30 分钟
  idle_timeout = 1800
}
```

#### 使用 CloudFormation

```yaml
Resources:
  NetworkLoadBalancer:
    Type: AWS::ElasticLoadBalancingV2::LoadBalancer
    Properties:
      Type: network
      LoadBalancerAttributes:
        - Key: idle_timeout.timeout_seconds
          Value: 1800  # 30 分钟
```

### 方案 2：实现心跳机制（已实现）

ZenFlux Agent 已经实现了心跳机制，每 30 秒发送一次 ping 事件，理论上可以保持连接活跃。

但需要确保：

1. **客户端正确处理 ping 事件**：
   ```go
   for {
       event, err := stream.Recv()
       if err != nil {
           return err
       }
       
       // 解析事件
       var eventData map[string]interface{}
       json.Unmarshal([]byte(event.Data), &eventData)
       
       // 🔧 跳过 ping 事件，不要关闭连接
       if eventData["type"] == "ping" {
           continue
       }
       
       // 处理其他事件...
   }
   ```

2. **确保 ping 事件能通过 NLB**：
   - ping 事件是数据包，应该能重置 NLB 的空闲计时器
   - 但如果 NLB 配置了特定的健康检查，可能需要额外配置

### 方案 3：客户端发送周期性请求（备用）

如果无法调整 NLB 配置，可以在客户端实现周期性的 keepalive：

```go
// 客户端代码示例
func consumeStreamWithKeepalive(stream ChatService_ChatStreamClient) error {
    // 启动一个 goroutine 定期发送 keepalive
    keepaliveDone := make(chan struct{})
    go func() {
        ticker := time.NewTicker(3 * time.Minute)  // 每 3 分钟
        defer ticker.Stop()
        
        for {
            select {
            case <-ticker.C:
                // 发送一个空的元数据帧，保持连接活跃
                stream.Header()
            case <-keepaliveDone:
                return
            }
        }
    }()
    defer close(keepaliveDone)
    
    // 接收事件
    for {
        event, err := stream.Recv()
        if err != nil {
            return err
        }
        // 处理事件...
    }
}
```

## 验证修复

### 1. 检查当前 NLB 配置

```bash
aws elbv2 describe-load-balancer-attributes \
  --load-balancer-arn arn:aws:elasticloadbalancing:ap-southeast-1:ACCOUNT_ID:loadbalancer/net/zen0-b-Publi-3WSjpP2omnbc/XXXXXXXX \
  | jq '.Attributes[] | select(.Key == "idle_timeout.timeout_seconds")'
```

预期输出：
```json
{
  "Key": "idle_timeout.timeout_seconds",
  "Value": "1800"
}
```

### 2. 测试长时间流式连接

```bash
# 发送一个需要长时间处理的任务
grpcurl -d '{
  "message": "生成一份包含 50 页的详细 PPT，主题是人工智能发展史",
  "user_id": "test-user"
}' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  zen0-b-Publi-3WSjpP2omnbc-7c8eacde8b1e6a3a.elb.ap-southeast-1.amazonaws.com:50051 \
  zenflux.ChatService/ChatStream
```

### 3. 监控日志

**预期正常日志**（修复后）：
```
✅ gRPC 流式聊天完成: events_sent=200
```

**异常日志**（如果还有问题）：
```
⚠️ gRPC 客户端已断开连接，停止流式响应: user_id=xxx, events_sent=50
```

## 常见问题

### Q1: 为什么心跳机制没有解决问题？

**A**: 可能的原因：

1. **NLB 的空闲超时是 TCP 层面的**，即使有应用层心跳，如果 TCP 连接空闲超过 350 秒，NLB 仍会断开
2. **心跳频率不够**：30 秒一次的 ping 应该足够，但如果网络延迟导致实际间隔超过 350 秒，仍会超时
3. **NLB 健康检查问题**：某些 NLB 配置可能对心跳数据包有特殊处理

### Q2: 为什么不在客户端配置中看到效果？

**A**: 客户端配置的 `timeout: 30m` 是指 **gRPC 调用的最大等待时间**，不影响底层 TCP 连接的空闲超时。NLB 会在 TCP 层面断开空闲连接，导致 gRPC 层收到 context canceled 错误。

### Q3: 能否通过修改 gRPC keepalive 配置解决？

**A**: 可以尝试，但效果有限：

```yaml
zenflux:
  keepalive_time: 1m       # 从 30s 改为 1 分钟
  keepalive_timeout: 10s
```

gRPC keepalive 会在 TCP 层发送 HTTP/2 PING 帧，理论上可以保持连接活跃。但需要确保：

1. NLB 允许 HTTP/2 PING 帧通过
2. keepalive_time 足够小（如 1-3 分钟）

### Q4: 如果无法修改 NLB 配置怎么办？

**A**: 可以考虑：

1. **使用 Application Load Balancer (ALB)**：ALB 对 gRPC 支持更好，空闲超时可以配置到 4000 秒
2. **直连 EC2/ECS**：绕过 ELB，直接连接到后端实例（需要配置安全组）
3. **实现断点续传**：使用 ReconnectStream 机制，定期重连

## 推荐配置对比

### 调整前（问题配置）

| 层级 | 配置项 | 超时时间 | 状态 |
|------|--------|----------|------|
| 客户端 | timeout | 30 分钟 | ✅ 正确 |
| 客户端 | keepalive_time | 30 秒 | ✅ 正确 |
| NLB | idle_timeout | **350 秒** | ⚠️ **瓶颈** |
| 服务端 | max_connection_idle | 30 分钟 | ✅ 正确 |
| Redis | subscribe_events timeout | 30 分钟 | ✅ 正确 |

### 调整后（推荐配置）

| 层级 | 配置项 | 超时时间 | 状态 |
|------|--------|----------|------|
| 客户端 | timeout | 30 分钟 | ✅ 正确 |
| 客户端 | keepalive_time | **60 秒** | ✅ **更频繁** |
| NLB | idle_timeout | **1800 秒** | ✅ **已修复** |
| 服务端 | max_connection_idle | 30 分钟 | ✅ 正确 |
| Redis | subscribe_events timeout | 30 分钟 | ✅ 正确 |

## 相关链接

- [AWS NLB Idle Timeout 文档](https://docs.aws.amazon.com/elasticloadbalancing/latest/network/network-load-balancers.html#connection-idle-timeout)
- [gRPC Keepalive 配置](https://grpc.io/docs/guides/keepalive/)
- [HTTP/2 连接管理](https://http2.github.io/http2-spec/#ConnectionManagement)

## 总结

**最直接有效的解决方案**：将 AWS NLB 的 `idle_timeout.timeout_seconds` 从默认的 350 秒增加到 **1800 秒（30 分钟）**。

这个修改：
- ✅ 无需修改代码
- ✅ 对现有客户端透明
- ✅ 完全解决空闲超时问题
- ✅ 支持长时间运行的任务
