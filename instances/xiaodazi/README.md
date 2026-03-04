# 小搭子 (xiaodazi) 实例

本地 AI 搭子实例，支持云端协同（委托云端 Agent 执行长任务、沙箱等）。

## 客户端如何配置云端协同

在**桌面/Web 客户端**里：

1. 打开 **设置** 页（侧栏或导航里的「设置」）。
2. 找到 **「云端协同」** 区块。
3. 填写：
   - **云端 URL**：默认 `https://agent.dazee.ai`，也可改为自建云端地址。
   - **用户名** / **密码**：可选；不填则依赖服务端环境变量或 JWT 透传。
4. 点击 **「测试连接」** 可检查当前填写的 URL 是否可达。

**说明**：当前云端请求由**服务端**发起，服务端在启动时从环境变量 `CLOUD_URL`、`CLOUD_USERNAME`、`CLOUD_PASSWORD` 读取配置。若在客户端修改了 URL/凭据，需在**服务端**的 `.env` 中同步配置并**重启服务**后才会生效；客户端设置页主要便于在界面上测试连接和后续扩展持久化。

API 文档：[Zenflux Agent API - Swagger UI](https://agent.dazee.ai/docs#/chat/chat_api_v1_chat_post)。

---

## 服务端：先实例化云端客户端

使用云端能力前，需在**本实例**下让云端客户端完成实例化：

1. **配置环境变量**（在项目根目录或本实例使用的 `.env` 中）：
   ```bash
   CLOUD_URL=https://agent.dazee.ai
   # 可选：用户名/密码（不填则依赖前端传入的 JWT 等）
   # CLOUD_USERNAME=your_username
   # CLOUD_PASSWORD=your_password
   ```

2. **启动服务**（会读取 `CLOUD_URL` 并初始化云端客户端）：
   ```bash
   AGENT_INSTANCE=xiaodazi python main.py
   ```
   启动日志出现 `☁️ 云端客户端已配置: https://agent.dazee.ai` 即表示实例化成功。

3. **API 文档**：云端 Chat 等接口见 [Zenflux Agent API - Swagger UI](https://agent.dazee.ai/docs#/chat/chat_api_v1_chat_post)。

未设置 `CLOUD_URL` 时不会初始化云端客户端，云端 Skill（如 cloud-agent）不可用。
