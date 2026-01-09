# gRPC 混合架构集成指南

## 📋 概述

Zenflux Agent 现在支持 **FastAPI + gRPC 混合架构**，同时提供：

- **HTTP REST API**：对外提供 Web 接口（端口 8000）
- **gRPC 服务**：内部微服务高性能通信（端口 50051）

这种架构让你能够：
- ✅ 前端继续使用 HTTP/SSE
- ✅ 内部微服务使用 gRPC 高性能通信
- ✅ 性能提升 2-5 倍（相比 HTTP）
- ✅ 强类型接口定义（protobuf）
- ✅ 双向流式通信

---

## 🚀 快速开始

### 1. 安装依赖

```bash
# 安装 gRPC 相关包
pip install grpcio>=1.60.0 grpcio-tools>=1.60.0 protobuf>=4.25.0

# 或直接安装所有依赖
pip install -r requirements.txt
```

### 2. 生成 gRPC 代码

```bash
# 运行代码生成脚本
bash scripts/generate_grpc.sh
```

这会生成：
- `services/grpc/generated/tool_service_pb2.py` - 消息定义
- `services/grpc/generated/tool_service_pb2_grpc.py` - 服务定义
- `services/grpc/generated/tool_service_pb2.pyi` - 类型提示

### 3. 启动服务

#### 方式1：主服务（HTTP + gRPC 同时运行）

```bash
# 设置环境变量启用 gRPC
export ENABLE_GRPC=true
export GRPC_PORT=50051

# 启动服务
python main.py
```

访问：
- HTTP API: `http://localhost:8000`
- gRPC 服务: `localhost:50051`

#### 方式2：独立运行 gRPC 服务器

```bash
# 只运行 gRPC 服务器（不启动 HTTP）
python services/grpc/server.py
```

---

## 📡 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                        用户/前端                              │
│                     (HTTP/SSE 客户端)                        │
└───────────────────────┬─────────────────────────────────────┘
                        │ HTTP/REST
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                   FastAPI 服务 (端口 8000)                   │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│  │ Chat 路由  │  │Session路由 │  │ Tool 路由  │            │
│  └────────────┘  └────────────┘  └────────────┘            │
│                                                              │
│                    调用 Service 层                           │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  ChatService / SessionService / ToolService         │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                        ↕ 内部调用
┌─────────────────────────────────────────────────────────────┐
│                   gRPC 服务 (端口 50051)                     │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│  │ChatService │  │SessionSvc  │  │ ToolService│            │
│  │  (gRPC)    │  │  (gRPC)    │  │  (gRPC)    │            │
│  └────────────┘  └────────────┘  └────────────┘            │
│                                                              │
│           复用相同的 Service 层业务逻辑                      │
└─────────────────────────────────────────────────────────────┘
                        ↑ gRPC 调用
            ┌──────────┴──────────┬──────────┐
            │                     │          │
┌───────────▼──────┐  ┌───────────▼──┐  ┌───▼───────┐
│  微服务 A        │  │  微服务 B    │  │ 微服务 C  │
│ (数据分析服务)   │  │ (报告服务)   │  │(通知服务) │
└──────────────────┘  └──────────────┘  └───────────┘
```

---

## 🔧 可用服务

### ChatService (聊天服务)

```protobuf
service ChatService {
  rpc Chat(ChatRequest) returns (ChatResponse);
  rpc ChatStream(ChatRequest) returns (stream ChatEvent);
  rpc ReconnectStream(ReconnectRequest) returns (stream ChatEvent);
}
```

**功能**：
- `Chat`: 同步聊天（返回 task_id）
- `ChatStream`: 流式聊天（实时事件）
- `ReconnectStream`: 断线重连

### SessionService (会话管理)

```protobuf
service SessionService {
  rpc GetSessionStatus(SessionStatusRequest) returns (SessionStatusResponse);
  rpc GetSessionEvents(SessionEventsRequest) returns (SessionEventsResponse);
  rpc GetUserSessions(UserSessionsRequest) returns (UserSessionsResponse);
  rpc StopSession(StopSessionRequest) returns (StopSessionResponse);
  rpc EndSession(EndSessionRequest) returns (EndSessionResponse);
  rpc ListSessions(ListSessionsRequest) returns (ListSessionsResponse);
}
```

**功能**：
- 查询会话状态
- 获取会话事件
- 会话控制（停止/结束）

---

## 💻 客户端使用示例

### Python 客户端

```python
from services.grpc.client import ZenfluxGRPCClient

async def example():
    # 使用上下文管理器自动连接/关闭
    async with ZenfluxGRPCClient("localhost:50051") as client:
        # 同步聊天
        response = await client.chat(
            message="帮我生成PPT",
            user_id="user_001"
        )
        
        print(f"Task ID: {response['task_id']}")
        
        # 流式聊天
        async for event in client.chat_stream(
            message="分析数据",
            user_id="user_001"
        ):
            print(event['type'], event['data'])
```

### Go 客户端（示例）

```go
package main

import (
    "context"
    "log"
    pb "your_repo/generated/protos"
    "google.golang.org/grpc"
)

func main() {
    // 连接到 gRPC 服务器
    conn, err := grpc.Dial("localhost:50051", grpc.WithInsecure())
    if err != nil {
        log.Fatal(err)
    }
    defer conn.Close()
    
    // 创建客户端
    client := pb.NewChatServiceClient(conn)
    
    // 调用服务
    resp, err := client.Chat(context.Background(), &pb.ChatRequest{
        Message: "帮我生成PPT",
        UserId:  "user_001",
    })
    if err != nil {
        log.Fatal(err)
    }
    
    log.Printf("Task ID: %s", resp.TaskId)
}
```

---

## 🔥 性能对比

| 维度 | HTTP REST | gRPC | 提升 |
|-----|----------|------|------|
| **序列化** | JSON (文本) | Protobuf (二进制) | 3-5x |
| **传输** | HTTP/1.1 | HTTP/2 | 2-3x |
| **请求延迟** | ~50ms | ~20ms | 2.5x |
| **并发连接** | 每连接一请求 | 多路复用 | 10x+ |
| **代码生成** | 手动 | 自动 | ✅ |
| **类型安全** | 弱类型 | 强类型 | ✅ |

---

## 🛠️ 开发指南

### 添加新的 gRPC 服务

#### 1. 更新 proto 文件

编辑 `protos/tool_service.proto`：

```protobuf
service YourService {
  rpc YourMethod(YourRequest) returns (YourResponse);
}

message YourRequest {
  string field1 = 1;
  int32 field2 = 2;
}

message YourResponse {
  bool success = 1;
  string result = 2;
}
```

#### 2. 重新生成代码

```bash
bash scripts/generate_grpc.sh
```

#### 3. 实现服务端

创建 `services/grpc/your_server.py`：

```python
from services.grpc.generated import tool_service_pb2_grpc

class YourServicer(tool_service_pb2_grpc.YourServiceServicer):
    async def YourMethod(self, request, context):
        # 实现业务逻辑
        return tool_service_pb2.YourResponse(
            success=True,
            result="处理完成"
        )
```

#### 4. 注册服务

在 `services/grpc/server.py` 中注册：

```python
tool_service_pb2_grpc.add_YourServiceServicer_to_server(
    YourServicer(), self.server
)
```

---

## 🔒 安全建议

### 1. 使用 TLS 加密

```python
# 服务端
credentials = grpc.ssl_server_credentials([
    (private_key, certificate_chain)
])
server.add_secure_port(address, credentials)

# 客户端
credentials = grpc.ssl_channel_credentials(root_certificates)
channel = grpc.secure_channel(address, credentials)
```

### 2. 认证和授权

```python
# 添加认证拦截器
class AuthInterceptor(grpc.aio.ServerInterceptor):
    async def intercept_service(self, continuation, handler_call_details):
        # 验证 token
        metadata = dict(handler_call_details.invocation_metadata)
        token = metadata.get("authorization", "")
        
        if not validate_token(token):
            raise grpc.RpcError(grpc.StatusCode.UNAUTHENTICATED)
        
        return await continuation(handler_call_details)
```

### 3. 网络隔离

- gRPC 服务只监听内网地址
- 使用防火墙限制访问
- 生产环境使用服务网格（如 Istio）

---

## 📊 监控和调试

### 启用 gRPC 日志

```bash
export GRPC_VERBOSITY=debug
export GRPC_TRACE=all
python main.py
```

### 使用 grpcurl 调试

```bash
# 安装 grpcurl
brew install grpcurl

# 列出服务
grpcurl -plaintext localhost:50051 list

# 调用方法
grpcurl -plaintext -d '{"message":"测试","user_id":"test"}' \
    localhost:50051 zenflux.ChatService/Chat
```

### 性能监控

```python
# 添加性能拦截器
class MetricsInterceptor(grpc.aio.ServerInterceptor):
    async def intercept_service(self, continuation, handler_call_details):
        start = time.time()
        response = await continuation(handler_call_details)
        duration = time.time() - start
        
        logger.info(f"gRPC 调用: {handler_call_details.method}, 耗时: {duration:.3f}s")
        return response
```

---

## 🐛 常见问题

### Q: 生成代码失败

```bash
# 确保安装了 grpcio-tools
pip install grpcio-tools

# 手动生成
python -m grpc_tools.protoc \
    -I./protos \
    --python_out=./services/grpc/generated \
    --grpc_python_out=./services/grpc/generated \
    ./protos/tool_service.proto
```

### Q: 连接被拒绝

检查：
1. gRPC 服务器是否已启动
2. 端口是否正确（默认 50051）
3. 防火墙是否阻止

### Q: 性能不如预期

优化建议：
1. 启用 HTTP/2
2. 增加连接池大小
3. 使用连接复用
4. 检查网络延迟

---

## 📚 参考资料

- [gRPC 官方文档](https://grpc.io/)
- [Protocol Buffers 指南](https://protobuf.dev/)
- [gRPC Python 教程](https://grpc.io/docs/languages/python/)
- 项目 proto 文件: `protos/tool_service.proto`
- 使用示例: `examples/grpc_client_example.py`

---

## 🎯 最佳实践

1. **接口设计**：使用 protobuf 定义清晰的接口
2. **版本管理**：proto 文件添加版本号
3. **错误处理**：使用 gRPC 状态码
4. **超时设置**：为每个调用设置合理超时
5. **重试策略**：实现指数退避重试
6. **监控告警**：监控 gRPC 调用指标

---

完成！你的项目现在支持 **FastAPI + gRPC 混合架构**了！🎉

