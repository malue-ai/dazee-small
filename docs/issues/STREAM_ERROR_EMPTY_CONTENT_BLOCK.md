# gRPC/HTTP 流式连接中断问题分析

**日期**: 2026-01-24  
**环境**: Staging  
**错误码**: STREAM_ERROR  
**错误信息**: `connection reset by peer`

---

## 问题描述

Zenflux Agent 在流式调用 Claude API 或 gRPC 通信时，偶发性出现连接被重置：

```
error reading from server: read tcp 10.0.3.192:50166->18.142.217.2:50051: read: connection reset by peer
```

---

## 日志分析

### 根本原因 1：Envoy Sidecar Draining（主要原因）

**日志证据**：

```
2026-01-23 01:49:31.671 | [AppNet Agent] Draining Envoy listeners...
2026-01-23 01:49:31.672 | [AppNet Agent] Waiting 20s for Envoy to drain listeners.
2026-01-23 02:07:02.534 | [AppNet Agent] Draining Envoy listeners...
2026-01-23 02:13:26.885 | [AppNet Agent] Draining Envoy listeners...
```

**分析**：
- AWS App Mesh 的 Envoy Sidecar 在部署或配置更新时会进入 Drain 状态
- Drain 期间，现有连接会被强制关闭
- 默认等待时间 20 秒，如果请求处理时间超过此值，连接会被中断

**责任方**：运维/基础设施团队

---

### 根本原因 2：gRPC 服务器停止

**日志证据**：

```
2026-01-23 02:13:15.679 | Aborting method [/zenflux.ChatService/ChatStream] due to server stop.
2026-01-23 02:13:15.700 | stopped: backend (terminated by SIGTERM)
```

**分析**：
- 服务器收到 SIGTERM 信号后停止
- 正在进行的 gRPC 流被强制中断

**责任方**：运维团队（部署流程）

---

### 根本原因 3：HTTP 流式传输网络读取错误

**日志证据**：

```
2026-01-23 01:16:22.173 | ❌ 流式传输中断:
2026-01-23 01:16:22.173 |    已接收事件数: 1040
2026-01-23 01:16:22.173 |    已累积 thinking: 0 chars
2026-01-23 01:16:22.173 |    已累积 content: 0 chars
...
httpcore.ReadError
httpx.ReadError
```

**分析**：
- 收到 1040 个事件但累积内容为 0（可能都是 thinking_delta 或 ping 事件）
- 底层 `httpcore.ReadError` 表示网络层读取失败
- 可能原因：
  - Claude API 服务端异常（包括输出空字符串导致崩溃）
  - 网络中间层（Envoy、负载均衡器）超时或重置连接
  - 上游代理（wanjiedata.com）连接问题

**责任方**：后端团队 + 需进一步定位

---

### 根本原因 4：Envoy gRPC 配置流关闭

**日志证据**：

```
2026-01-23 01:09:54.473 | StreamAggregatedResources gRPC config stream to unix:///var/run/ecs/appnet/relay/appnet_relay_listener.sock closed: 13, Received RST_STREAM with error code 0
```

**分析**：
- Envoy 与 App Mesh 控制平面的配置同步流被关闭
- `RST_STREAM error code 0` 表示正常关闭（非错误）
- 这是 Envoy 配置更新的正常行为，但可能导致连接重新建立期间的短暂中断

**责任方**：运维/基础设施团队

---

### 根本原因 5：API 凭证错误

**日志证据**：

```
2026-01-23 02:37:06.618 | HTTP Request: POST https://maas-openapi.wanjiedata.com/api/anthropic/v1/messages "HTTP/1.1 400 Bad Request"
2026-01-23 02:37:06.618 | ❌ 流式传输中断: Error code: 400 - {'error': {...'message': 'This credential is only authorized for use with Claude Code and cannot be used for other API requests.'...}}
```

**分析**：
- 使用了仅限 Claude Code 的凭证
- 返回 400 错误，不是连接问题

**责任方**：后端团队（配置问题）

---

## 根本原因汇总

| 优先级 | 原因 | 责任方 | 解决方案 |
|--------|------|--------|----------|
| P1 | Envoy Sidecar Draining | 运维团队 | 延长 Drain 时间 / 优化部署流程 |
| P1 | gRPC 服务器停止 | 运维团队 | 优雅停机 / 滚动部署 |
| P2 | HTTP 流式传输读取错误 | 后端团队 | 添加重试机制 |
| P3 | Envoy 配置流关闭 | 运维团队 | 正常行为，可忽略 |
| P3 | API 凭证错误 | 后端团队 | 更换正确凭证 |

---

## 已实施的修复

### 1. 流式重试机制

**修改文件**：`core/llm/claude.py`

当 `connection reset` 发生且无累积内容时，自动重试（最多 2 次，指数退避）。

### 2. Input 端空字符串过滤

**修改文件**：
- `utils/message_utils.py` - `_filter_empty_text_blocks()`
- `core/context/conversation.py` - `_clean_content_blocks()`, `_ensure_tool_pairs()`

过滤发送给 Claude API 的空 text block，降低触发服务端异常的概率。

---

## 待办事项

| 项目 | 责任方 | 状态 |
|------|--------|------|
| 延长 Envoy Drain 时间 | 运维团队 | 待处理 |
| 优化滚动部署流程 | 运维团队 | 待处理 |
| 更换 API 凭证 | 后端团队 | 待确认 |
| 监控流式中断率 | 后端团队 | 待实施 |

---

## 参考文档

- [Claude API Error Handling](https://platform.claude.com/docs/en/api/errors)
- [Claude Streaming Messages](https://docs.claude.com/en/api/streaming)
- [AWS App Mesh Envoy Draining](https://docs.aws.amazon.com/app-mesh/latest/userguide/envoy.html)
