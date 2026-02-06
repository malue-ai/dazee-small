# 本地开发环境：使用本地 Redis 模拟 MemoryDB Streams

## 快速回答

**问题**：本地 Redis 能模拟 MemoryDB Redis Streaming 吗？

**答案**：✅ **完全可以！** 本地 Redis >= 5.0 可以完全模拟 MemoryDB 的 Redis Streams 功能。

## 核心要点

1. **API 完全兼容**：MemoryDB 与开源 Redis 100% API 兼容
2. **代码无需修改**：部署时仅需修改连接字符串（通过环境变量）
3. **功能完全一致**：本地测试的功能在生产环境完全一致

## 快速开始

### 1. 启动本地 Redis

```bash
# 使用 Docker（推荐）
docker run -d --name local-redis -p 6379:6379 redis:7-alpine

# 或使用 Homebrew (macOS)
brew install redis
brew services start redis

# 验证 Redis 运行
redis-cli ping
# 应返回: PONG
```

### 2. 配置环境变量

```bash
# 本地开发环境（使用本地 Redis）
export DEPLOYMENT_ENV=local
export REDIS_URL=redis://localhost:6379/0
```

### 3. 运行兼容性验证

```bash
# 验证本地 Redis 完全兼容 MemoryDB Streams 功能
python tests/e2e_message_session/test_redis_streams_compatibility.py
```

如果所有测试通过，说明本地 Redis 完全可以模拟 MemoryDB 的功能。

### 4. 开发测试

在本地环境进行完整的功能开发和测试，代码可以直接部署到 AWS，无需修改。

### 5. 部署到 AWS

部署时仅需修改环境变量：

```bash
# AWS 生产环境（使用 MemoryDB）
export DEPLOYMENT_ENV=aws
export REDIS_URL=rediss://agentuser:****@clustercfg.zen0-backend-staging-memorydb.w9tdej.memorydb.ap-southeast-1.amazonaws.com:6379
```

## 使用的 Redis Streams 功能

系统使用的所有功能都是标准 Redis API，完全兼容：

| 功能 | 命令 | 兼容性 |
|------|------|--------|
| 添加消息 | XADD | ✅ 完全兼容 |
| 消费者组读取 | XREADGROUP | ✅ 完全兼容 |
| 创建消费者组 | XGROUP CREATE | ✅ 完全兼容 |
| 确认消息 | XACK | ✅ 完全兼容 |
| 查询待处理 | XPENDING | ✅ 完全兼容 |
| Stream 长度限制 | XTRIM (maxlen) | ✅ 完全兼容 |

## 版本要求

- **本地 Redis**：>= 5.0（Redis Streams 在 5.0 引入）
- **MemoryDB**：完全兼容 Redis 5.0+ API

## 验证清单

在部署到 AWS 前，确保以下测试通过：

- [x] Redis 版本 >= 5.0
- [x] XADD 功能正常
- [x] 消费者组机制正常
- [x] 消息 ACK 机制正常
- [x] 完整工作流程测试通过

运行验证脚本即可自动检查所有项目。

## 常见问题

### Q: 本地 Redis 和 MemoryDB 有什么差异？

**A**: 功能上完全一致，但存在以下非功能性差异：

| 特性 | 本地 Redis | MemoryDB |
|------|----------|---------|
| 持久化 | RDB/AOF 可选 | 多 AZ 事务日志（强制） |
| 写入性能 | 更高（无持久化开销） | 稍低（需写入事务日志） |
| 网络延迟 | < 1ms（本地） | 10-50ms（远程网络） |
| 高可用性 | 需自配置 | 内置多 AZ 故障转移 |
| TLS | 可选 | 强制（rediss://） |

这些差异**不影响功能兼容性**，仅影响性能和可用性。

### Q: 部署时需要修改代码吗？

**A**: **不需要！** 代码完全不需要修改，只需修改环境变量：

```python
# 代码中这样使用（无需修改）
from infra.cache.redis import get_redis_client
redis = await get_redis_client()  # 自动从环境变量读取 REDIS_URL
```

### Q: 如何确保兼容性？

**A**: 
1. 运行兼容性验证脚本：`test_redis_streams_compatibility.py`
2. 确保 Redis 版本 >= 5.0
3. 在本地完成所有功能测试

### Q: 如果验证失败怎么办？

**A**: 
1. 检查 Redis 版本（需要 >= 5.0）
2. 检查 Redis 是否正常运行
3. 检查连接配置是否正确
4. 查看测试脚本的错误输出

## 详细文档

- **兼容性详细分析**：[redis-streams-compatibility.md](./redis-streams-compatibility.md)
- **消息会话架构**：[22-MESSAGE-SESSION-MANAGEMENT.md](./22-MESSAGE-SESSION-MANAGEMENT.md)

## 总结

✅ **本地 Redis 完全可以模拟 MemoryDB 的 Redis Streams 功能**

- 使用标准 Redis API，无需 MemoryDB 特定功能
- 本地开发测试通过后，代码可以直接部署到 AWS
- 部署时仅需修改环境变量，无需修改代码
- 有效避免部署阶段的代码修改和 bug 修复
