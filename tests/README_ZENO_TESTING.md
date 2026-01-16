# ZenO 适配器测试指南

本文档说明如何测试 ZenO 适配器的功能，确保事件转换符合 **ZenO SSE 规范 v2.0.1**。

---

## 📋 测试清单

| 测试类型 | 脚本 | 说明 |
|---------|------|------|
| 单元测试 | `test_zeno_adapter.py` | 测试适配器的事件转换逻辑 |
| 模拟服务器 | `test_zeno_server.py` | 模拟 ZenO 服务器接收事件 |
| 集成测试 | `test_zeno_integration.py` | 端到端测试完整流程 |

---

## 🚀 快速开始

### 1. 启用 ZenO 适配器

编辑 `config/webhooks.yaml`，确保以下配置已启用：

```yaml
subscriptions:
  - name: "zeno_integration"
    adapter: "zeno"
    endpoint: "http://localhost:8080/api/sse/events"
    enabled: true  # 确保为 true
    events:
      - "message_start"
      - "message_stop"
      - "content_delta"
      - "message_delta"
      - "error"
```

### 2. 运行单元测试

测试适配器的事件转换功能：

```bash
cd /path/to/zenflux_agent
python tests/test_zeno_adapter.py
```

**预期输出**：
- ✅ 所有事件类型的转换测试
- ✅ 格式验证通过
- ✅ 完整事件流测试

---

## 🧪 完整测试流程

### 步骤 1: 启动模拟 ZenO 服务器

在 **终端 1** 运行：

```bash
python tests/test_zeno_server.py
```

**预期输出**：
```
🚀 启动 ZenO 模拟服务器
监听地址: http://localhost:8080
事件接收端点: http://localhost:8080/api/sse/events
```

服务器提供的接口：
- `GET /` - 服务状态
- `POST /api/sse/events` - 接收事件
- `GET /events` - 查看所有事件
- `GET /events/summary` - 事件摘要统计
- `DELETE /events` - 清空事件

### 步骤 2: 启动 Zenflux Agent

在 **终端 2** 运行：

```bash
uvicorn main:app --reload --port 8000
```

**检查配置**：
- ✅ Agent 已启动在 8000 端口
- ✅ `config/webhooks.yaml` 中 zeno_integration 已启用
- ✅ Redis 正在运行（如果使用 SSE）

### 步骤 3: 运行集成测试

在 **终端 3** 运行：

```bash
python tests/test_zeno_integration.py
```

**测试流程**：
1. 检查 ZenO 服务器和 Agent 是否运行
2. 清空旧事件
3. 发送测试消息到 Chat API
4. 等待事件处理
5. 验证接收到的事件格式
6. 显示详细摘要

**预期输出**：
```
🧪 ZenO 集成测试
步骤 1: 检查服务状态...
✅ ZenO Mock Server 正在运行
✅ Zenflux Agent 正在运行

步骤 2: 清空旧事件...
🗑️  已清空 0 个旧事件

步骤 3: 发送测试消息...
📤 发送消息: 你好，请介绍一下你自己
✅ 消息发送成功

步骤 4: 等待事件处理...

步骤 5: 查看事件摘要...
📊 事件摘要
总数: 5
按类型统计:
  message.assistant.start: 1
  message.assistant.delta: 3
  message.assistant.done: 1

按 Delta 类型统计:
  thinking: 1
  response: 2

验证结果:
  ✅ 有效: 5
  ❌ 无效: 0

✅ 集成测试完成！
成功接收并验证了 5 个事件
```

### 步骤 4: 查看详细事件

在浏览器访问或使用 curl：

```bash
# 查看所有事件
curl http://localhost:8080/events | jq

# 查看事件摘要
curl http://localhost:8080/events/summary | jq

# 清空事件
curl -X DELETE http://localhost:8080/events
```

---

## 📊 事件验证标准

### ZenO 事件格式要求

所有事件必须包含以下字段：

```json
{
  "type": "message.assistant.xxx",
  "message_id": "msg_xxx",
  "timestamp": 1704614400000
}
```

### 支持的事件类型

| 事件类型 | 说明 | 必填字段 |
|---------|------|----------|
| `message.assistant.start` | 消息开始 | `type`, `message_id`, `timestamp` |
| `message.assistant.delta` | 增量更新 | `type`, `message_id`, `timestamp`, `delta` |
| `message.assistant.done` | 消息完成 | `type`, `message_id`, `timestamp`, `data.content` |
| `message.assistant.error` | 错误事件 | `type`, `message_id`, `timestamp`, `error` |

### Delta 类型规范

`message.assistant.delta` 事件的 `delta` 字段必须包含：

```json
{
  "delta": {
    "type": "thinking|response|progress|clue|...",
    "content": "..."
  }
}
```

支持的 delta 类型：
- `intent` - 意图识别
- `preface` - 序言
- `thinking` - 思考过程
- `response` - 文本响应
- `progress` - 执行进度
- `clue` - 交互提示
- `files` - 文件列表
- `mind` - Mermaid 图表
- `sql` - SQL 查询
- `data` - 数据结果
- `chart` - 图表配置
- `recommended` - 推荐问题
- `application` - 应用状态

---

## 🐛 故障排查

### 问题 1: 未接收到事件

**症状**：集成测试显示 "未接收到任何事件"

**检查清单**：
1. ZenO Mock Server 是否在运行（端口 8080）
2. `config/webhooks.yaml` 中 `enabled: true`
3. endpoint 是否正确：`http://localhost:8080/api/sse/events`
4. Agent 日志中是否有错误（查看 `logs/app.log`）

**解决方法**：
```bash
# 检查端口占用
lsof -i :8080

# 查看 Agent 日志
tail -f logs/app.log | grep "zeno"

# 重启 Agent 使配置生效
# Ctrl+C 停止，然后重新运行 uvicorn
```

### 问题 2: 事件验证失败

**症状**：接收到事件但验证失败

**检查**：
- 查看 ZenO Mock Server 的日志输出
- 查看具体的验证错误信息

**常见错误**：
- 缺少必填字段（type, message_id, timestamp）
- delta 类型不符合规范
- 事件结构不完整

### 问题 3: 连接超时

**症状**：Agent 日志显示 "外部事件发送超时"

**原因**：
- ZenO Mock Server 未启动
- 网络问题
- 端口冲突

**解决**：
```bash
# 确认服务器正在运行
curl http://localhost:8080/

# 检查防火墙设置
# macOS: System Preferences > Security & Privacy > Firewall
```

---

## 📝 测试报告模板

```markdown
## ZenO 适配器测试报告

**测试日期**: 2025-01-07
**测试人员**: [你的名字]
**版本**: v2.0.1

### 测试结果

- ✅ 单元测试：通过
- ✅ 集成测试：通过
- ✅ 事件验证：100% 通过

### 事件统计

- 总事件数：15
- 事件类型：4 种
- Delta 类型：6 种
- 验证通过率：100%

### 问题记录

无

### 建议

建议将此适配器应用到生产环境。
```

---

## 🎯 下一步

完成测试后，你可以：

1. **生产部署**：将 endpoint 改为实际的 ZenO 服务器地址
2. **监控配置**：配置日志和监控，跟踪事件发送情况
3. **性能测试**：测试高并发场景下的事件发送性能
4. **错误处理**：配置重试策略和失败告警

---

## 📚 相关文档

- [ZenO SSE 规范 v2.0.1](../docs/AGENT_IO_SPECIFICATION.md)
- [事件协议文档](../docs/03-EVENT-PROTOCOL.md)
- [Webhook 配置指南](../config/webhooks.yaml)

---

**祝测试顺利！** 🎉

