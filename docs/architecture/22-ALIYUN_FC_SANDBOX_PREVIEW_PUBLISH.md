# 阿里云 FC Sandbox：预览与发布方案

> 版本：0.3  
> 更新时间：2026-01-20  
> 参考来源：`AI+Chat+应用接入+FC+Sandbox+流程.pdf`

---

## 一、核心目标

1. **预览态**：用户新建聊天时，分配专属 Sandbox，Agent 产出的应用可通过 `preview_url` 即时预览
2. **发布态**：将应用发布成长期稳定的公开 URL

---

## 二、两阶段架构（对齐 PDF 文档）

参考 PDF 文档，整体架构分为**两个阶段**：

### 阶段一：预热与池化（Proactive Pooling）

> **离线/定时任务**，提前准备好函数池

```
┌────────────────────────────────────────────────────────────────────┐
│  后台定时任务                                                       │
│                                                                    │
│  createFunction ──► poll getFunction ──► createSession(预热)       │
│       │                  │                      │                  │
│       │            等待 state=Active            │                  │
│       │                  │                      │                  │
│       │                  ▼                      │                  │
│       │            getTrigger                   │                  │
│       │            (获取 trigger_host)          │                  │
│       │                  │                      │                  │
│       └──────────────────┴──────────────────────┘                  │
│                          │                                         │
│                          ▼                                         │
│                   存入数据库 (status=0 空闲)                         │
└────────────────────────────────────────────────────────────────────┘
```

**步骤说明**：
1. `createFunction`：批量创建 FC 函数（自定义容器镜像）
2. `getFunction`：轮询等待 `state=Active`
3. `getTrigger`：获取 `urlInternet`，提取 `trigger_host`
4. `createSession`：预热实例（不传业务 sessionId，仅触发实例拉起）
5. 存入数据库，标记 `status=0`（空闲可分配）

### 阶段二：分配与服务（Reactive Allocation & Serving）

> **用户请求触发**，从池中分配函数

```
┌────────────────────────────────────────────────────────────────────┐
│  用户新建聊天                                                       │
│       │                                                            │
│       ▼                                                            │
│  查询数据库 (status=0) ──► createSession(挂载&绑定)                  │
│       │                          │                                 │
│       │                   传入业务 sessionId                        │
│       │                   可选：动态挂载 NAS/OSS                     │
│       │                          │                                 │
│       │                          ▼                                 │
│       │                  (PreStop Hook 中)                         │
│       │                   updateFunction                           │
│       │                   持久化挂载配置                             │
│       │                          │                                 │
│       ▼                          │                                 │
│  更新数据库 (status=1 已分配)     │                                 │
│       │                          │                                 │
│       ▼                          ▼                                 │
│  返回 preview_url ◄──────────────┘                                 │
│       │                                                            │
│       ▼                                                            │
│  客户端使用 URL + SessionID 交互                                    │
└────────────────────────────────────────────────────────────────────┘
```

**步骤说明**：
1. 查询数据库，找 `status=0` 的空闲函数
2. `createSession`：传入业务 `sessionId`，可选动态挂载
3. 更新数据库 `status=1`（已分配）
4. 生成 `preview_url`，通过 SSE 返回给前端
5. （实例 PreStop Hook 中）`updateFunction` 持久化挂载配置

---

## 三、Sandbox 创建时机

### 触发点：新建 Conversation 时

```
用户点击"新建聊天" 
  → 后端 ChatService.chat() 
  → 检测到 conversation_id 为空（新对话）
  → 创建 conversation 
  → 【立即执行阶段二：从池中分配 Sandbox】
  → 发送 SSE 事件通知前端
```

**代码位置**：`services/chat_service.py` 的 `chat()` 方法中，`create_conversation` 之后。

---

## 四、SSE 事件定义（聊天过程中）

> SSE 事件仅用于**聊天过程中**的 Sandbox 状态通知

### 4.1 事件类型总览

| 事件场景 | `phase` | `status` | 说明 |
|---------|---------|----------|------|
| Sandbox 就绪 | `sandbox` | `running` | 分配完成，携带 `preview_url` |
| Sandbox 失败 | `sandbox` | `error` | 分配失败，携带错误信息 |
| **应用就绪** | `sandbox` | `app_ready` | **Agent 完成应用生成**，前端显示"预览"按钮 |

### 4.2 事件发送时机

| 事件 | 发送时机 | 前端行为 |
|------|---------|---------|
| `sandbox/allocating` | `create_conversation` 之后立即发送 | 显示 loading："正在准备开发环境..." |
| `sandbox/running` | Sandbox 分配成功 | 记录 `preview_url`，暂不显示预览入口 |
| `sandbox/app_ready` | **Agent 完成应用生成后** | 显示"预览"按钮 |
| `sandbox/error` | 分配失败时 | 显示错误提示 |

### 4.3 时序图

```
用户                前端                    后端                     FC
 │                   │                      │                        │
 │──新建聊天─────────▶│                      │                        │
 │                   │──POST /chat─────────▶│                        │
 │                   │                      │──创建conversation───────│
 │                   │                      │                        │
 │                   │◀─SSE: sandbox/allocating─│                    │
 │                   │  (显示"正在准备环境...")   │                    │
 │                   │                      │                        │
 │                   │                      │──查询函数池(status=0)───│
 │                   │                      │──createSession(绑定)──▶│
 │                   │                      │◀─────────────────────── │
 │                   │                      │──更新数据库(status=1)───│
 │                   │                      │                        │
 │                   │◀─SSE: sandbox/running, preview_url─│          │
 │                   │  (环境就绪，暂不显示预览)            │          │
 │                   │                      │                        │
 │     ... Agent 执行中，生成代码/应用 ...    │                        │
 │                   │                      │                        │
 │                   │◀─SSE: sandbox/app_ready─│                     │
 │                   │  (显示"预览"按钮)                              │
 │                   │                      │                        │
```

---

## 五、事件格式

### 5.1 ZenFlux 内部格式（`message_delta`）

```json
{
  "type": "message_delta",
  "data": {
    "type": "application",
    "content": {
      "phase": "sandbox",
      "status": "app_ready",
      "preview_url": "https://api.example.com/preview/conv_xxx/",
      "app_name": "我的应用",
      "message": "应用已生成，点击预览"
    }
  },
  "conversation_id": "conv_xxx",
  "session_id": "sess_xxx",
  "timestamp": "2026-01-20T12:00:00+08:00"
}
```

### 5.2 ZenO SSE 格式（经过 ZenOAdapter 转换后）

```json
{
  "type": "message.assistant.delta",
  "message_id": "msg_xxx",
  "timestamp": 1737360000000,
  "delta": {
    "type": "application",
    "content": "{\"phase\":\"sandbox\",\"status\":\"app_ready\",\"preview_url\":\"https://api.example.com/preview/conv_xxx/\",\"app_name\":\"我的应用\",\"message\":\"应用已生成，点击预览\"}"
  }
}
```

> **注意**：ZenO 格式中 `delta.content` 是 JSON 字符串，前端需要 `JSON.parse()` 解析。

### 5.3 各状态事件示例

#### sandbox/allocating（分配中）

**ZenFlux 内部**:
```json
{
  "type": "message_delta",
  "data": {
    "type": "application",
    "content": {
      "phase": "sandbox",
      "status": "allocating",
      "message": "正在准备开发环境..."
    }
  }
}
```

**ZenO 格式**:
```json
{
  "type": "message.assistant.delta",
  "message_id": "msg_xxx",
  "timestamp": 1737360000000,
  "delta": {
    "type": "application",
    "content": "{\"phase\":\"sandbox\",\"status\":\"allocating\",\"message\":\"正在准备开发环境...\"}"
  }
}
```

#### sandbox/running（就绪）

**ZenFlux 内部**:
```json
{
  "type": "message_delta",
  "data": {
    "type": "application",
    "content": {
      "phase": "sandbox",
      "status": "running",
      "preview_url": "https://api.example.com/preview/conv_xxx/",
      "message": "开发环境已就绪"
    }
  }
}
```

**ZenO 格式**:
```json
{
  "type": "message.assistant.delta",
  "message_id": "msg_xxx",
  "timestamp": 1737360000000,
  "delta": {
    "type": "application",
    "content": "{\"phase\":\"sandbox\",\"status\":\"running\",\"preview_url\":\"https://api.example.com/preview/conv_xxx/\",\"message\":\"开发环境已就绪\"}"
  }
}
```

#### sandbox/app_ready（应用就绪）

**ZenFlux 内部**:
```json
{
  "type": "message_delta",
  "data": {
    "type": "application",
    "content": {
      "phase": "sandbox",
      "status": "app_ready",
      "preview_url": "https://api.example.com/preview/conv_xxx/",
      "app_name": "我的应用",
      "message": "应用已生成，点击预览"
    }
  }
}
```

**ZenO 格式**:
```json
{
  "type": "message.assistant.delta",
  "message_id": "msg_xxx",
  "timestamp": 1737360000000,
  "delta": {
    "type": "application",
    "content": "{\"phase\":\"sandbox\",\"status\":\"app_ready\",\"preview_url\":\"https://api.example.com/preview/conv_xxx/\",\"app_name\":\"我的应用\",\"message\":\"应用已生成，点击预览\"}"
  }
}
```

---

## 六、Preview Proxy（预览代理）

### 6.1 为什么需要

浏览器直接打开 URL **无法携带自定义 Header**，但 FC 路由需要：
- `fc_host`：网关动态路由到目标函数
- `x-fc-session-id`：会话亲和

### 6.2 请求流程

```
浏览器打开: https://api.example.com/preview/{conversation_id}/{path}
           ↓
       PreviewProxy（后端）
           ↓ 查询 sandbox_allocation 表
           ↓ 注入 fc_host + x-fc-session-id
       API Gateway
           ↓
       FC Function
```

### 6.3 实现要点

```python
# routers/preview.py
@router.get("/preview/{conversation_id}/{path:path}")
async def preview_proxy(conversation_id: str, path: str, request: Request):
    # 1. 查询分配映射
    allocation = await get_allocation(conversation_id)
    
    # 2. 构造请求头
    headers = {
        "fc_host": allocation.trigger_host,
        "x-fc-session-id": allocation.biz_session_id,
    }
    
    # 3. 转发到 API 网关
    return await forward_to_gateway(path, headers, request)
```

---

## 七、数据模型

### fc_function_pool（函数池）

```sql
CREATE TABLE fc_function_pool (
    id VARCHAR(64) PRIMARY KEY,
    function_name VARCHAR(128) NOT NULL,
    trigger_host VARCHAR(256) NOT NULL,  -- getTrigger 返回的 urlInternet
    status INT DEFAULT 0,                 -- 0=空闲, 1=已分配, 2=不可用
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### sandbox_allocation（分配映射）

```sql
CREATE TABLE sandbox_allocation (
    conversation_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    function_name VARCHAR(128) NOT NULL,
    trigger_host VARCHAR(256) NOT NULL,
    biz_session_id VARCHAR(256) NOT NULL,   -- 业务 sessionId
    preview_url VARCHAR(512),
    nas_config JSON,                         -- 可选：动态挂载配置
    status VARCHAR(32) DEFAULT 'allocating', -- allocating/running/app_ready/error
    assigned_at TIMESTAMP
);
```

### published_apps（发布记录）

```sql
CREATE TABLE published_apps (
    id VARCHAR(64) PRIMARY KEY,
    conversation_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    app_name VARCHAR(256),
    function_name VARCHAR(128) NOT NULL,
    public_url VARCHAR(512) NOT NULL,
    status VARCHAR(32) DEFAULT 'deploying',  -- building/deploying/ready/failed
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

---

## 八、发布功能（HTTP 接口）

> 发布是用户主动触发的 HTTP 接口，**不是 SSE 事件**

### 8.1 接口定义

```
POST /api/v1/publish
```

**请求体**：
```json
{
  "conversation_id": "conv_xxx",
  "app_name": "我的应用"
}
```

**响应**（同步返回，或返回 task_id 后轮询）：
```json
{
  "success": true,
  "data": {
    "publish_id": "pub_xxx",
    "public_url": "https://app.example.com/published/pub_xxx/",
    "status": "ready"
  }
}
```

### 8.2 发布流程

```
用户点击"发布" 
  → 前端调用 POST /api/v1/publish
  → 后端执行：
      1. 打包应用（从 Sandbox 导出产物）
      2. createFunction（部署到 FC，不需要会话亲和）
      3. getFunction 轮询 Active
      4. getTrigger 获取访问地址
      5. 绑定 API 网关，生成 public_url
      6. 写入 published_apps 表
  → 返回 public_url
```

### 8.3 发布进度（可选）

如果发布耗时较长，可以：
1. 先返回 `task_id`
2. 前端轮询 `GET /api/v1/publish/{task_id}/status`
3. 或通过 WebSocket 推送进度

```json
// 轮询响应
{
  "task_id": "task_xxx",
  "status": "deploying",  // building / deploying / ready / failed
  "progress": 60,
  "message": "正在部署到 FC..."
}
```

---

## 九、实现任务清单

| 序号 | 任务 | 说明 |
|------|------|------|
| 1 | 数据模型 | 新增 `fc_function_pool`、`sandbox_allocation`、`published_apps` 表 |
| 2 | FC API 客户端 | 封装 createFunction/getFunction/getTrigger/createSession/updateFunction |
| 3 | 阶段一：函数池预热 | 后台定时任务，保持池内有足够空闲函数 |
| 4 | 阶段二：Sandbox 分配 | 在 `chat_service.py` 新建 conversation 后调用 |
| 5 | SSE 事件发送 | 发送 allocating → running → app_ready 事件 |
| 6 | Preview Proxy | 实现 `/preview/{conversation_id}/{path}` 路由 |
| 7 | 发布 HTTP 接口 | 实现 `POST /api/v1/publish`，打包、部署、返回 public_url |

---

## 十、与现有系统兼容

当前系统使用 E2B Sandbox，建议以 Provider 模式并存：

```python
# 环境变量控制
SANDBOX_PROVIDER=e2b        # 现有方案
SANDBOX_PROVIDER=aliyun_fc  # 新方案
```

事件格式统一，前端无需针对不同 Provider 做特殊处理。
