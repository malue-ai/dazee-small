# 云端协同架构方案 v2: Skill 模式

## 一、核心理念

**用户视角**：只有一个 Agent，打开本地应用就能用，不感知云端存在。

**架构视角**：云端 Agent 是本地 Agent 的一个 Skill，和 `excel-analyzer`、`web-scraper` 一样。LLM 按需选择，数据通过对话上下文自然流转。

```
用户 --> 本地 Agent (RVR-B 循环)
            |-- Turn 1 --> excel-analyzer (本地)
            |-- Turn 2 --> cloud-agent Skill --> 云端 Agent (黑盒)
            |-- Turn 3 --> ppt-generator (本地)
```

### 为什么放弃 Plan 驱动方案

之前设计了 13+ 端点的 Plan 驱动协议（Plan/Step 双层状态机、步骤间结构化数据流转、三层控制粒度）。经评估是过度设计：

| 问题 | Plan 驱动 | Skill 模式 |
| --- | --- | --- |
| 步骤间数据流转 | 显式 `input_data.from_steps` | LLM 上下文自然流转 |
| 混合本地/云端步骤 | Plan Orchestrator 编排 | RVR-B 多轮循环自然交替 |
| 重规划 | `PATCH /acp/plans` | LLM 自主重规划 (plan_todo rewrite) |
| 云端感知全局 | 共享 Plan 结构 | 不需要，云端只完成被交代的任务 |

**核心洞察**：编排逻辑在 LLM 大脑里（RVR-B），不在协议层。LLM-First。

---

## 二、两个代码库的关系

| | 本地端 | 云端 |
| --- | --- | --- |
| **代码库** | `xiaodazi/zenflux_agent` | `CoT_agent/mvp/zenflux_agent` |
| **新增** | 1 个 Skill 目录 | 1 个 Router + 1 个 Service |
| **耦合** | ACP 5 个端点 | ACP 5 个端点 |
| **独立演进** | 完全独立 | 完全独立 |

代码零共享，ACP 协议规范是唯一契约。

---

## 三、ACP 极简协议

### 3.1 端点总览

```
GET    /acp/capabilities                --> 能力声明
POST   /acp/execute                     --> 提交任务（SSE 流式返回）
DELETE /acp/tasks/{task_id}             --> 取消任务
GET    /acp/tasks/{task_id}             --> 查询任务状态（断线恢复用）
GET    /acp/tasks/{task_id}/stream      --> 断线后重接 SSE（last_seq 续传）
```

5 个端点，对比 Plan 驱动方案的 13+。

### 3.2 能力声明

```
GET /acp/capabilities
```

```json
{
  "agent_id": "cloud-xiaodazi-01",
  "acp_version": "1.0.0",
  "status": "ready",
  "description": "云端深度调研、代码执行、7x24 定时任务",
  "limits": {
    "max_concurrent_tasks": 3,
    "max_task_duration_s": 600
  }
}
```

不列举具体 Skills。云端是黑盒。

### 3.3 提交任务（核心）

```
POST /acp/execute
Authorization: Bearer {token}
```

请求：

```json
{
  "task_id": "task_xxx",
  "task": "调研 2026 年 AI Agent 赛道融资情况",
  "context": "竞品列表: Manus, Devin, OpenHands...\n用户偏好: 覆盖国内和海外",
  "expected_output": "结构化融资数据 JSON",
  "constraints": {"max_turns": 15, "timeout_s": 300}
}
```

直接返回 SSE 流：

```
id: 1
data: {"type":"acp_status","seq":1,"data":{"task_id":"xxx","status":"working"}}

id: 2
data: {"type":"content_delta","seq":2,"data":{"type":"text","text":"正在搜索..."}}

id: 3
data: {"type":"tool_use_start","seq":3,"data":{"name":"exa_search"}}

id: 4
data: {"type":"tool_result","seq":4,"data":{"tool_use_id":"tu_01","content":"..."}}

...

id: 20
data: {"type":"acp_result","seq":20,"data":{"result":{...融资数据...}}}

event: done
data: {}
```

设计要点：
- POST 直接返回 SSE（减少 roundtrip）
- `task` 和 `context` 是自然语言，LLM 上一轮结果直接写在 context 里
- 事件格式复用现有 SSE 信封，前端可直接展示进度

### 3.4 Task 状态机

```
working --> completed | failed | canceled
```

3 个终态。暂停/恢复 Phase 2 按需扩展。

### 3.5 取消任务

```
DELETE /acp/tasks/{task_id}
```

云端 Turn 边界停止。

### 3.6 断线恢复

```
GET /acp/tasks/{task_id}         --> 查状态快照
GET /acp/tasks/{task_id}/stream?last_seq=15  --> 从 seq 15 续传
```

云端 Redis Streams 缓冲事件。保留至终态 + 1 小时 TTL。

### 3.7 认证

Bearer Token（共享密钥），HTTPS 强制。

---

## 四、本地端实现

### 4.1 cloud-agent Skill

```
skills/library/cloud-agent/
  SKILL.md           # LLM 读这个决定何时调用
  scripts/
    execute.py       # 调用云端 ACP 端点
```

### 4.2 SKILL.md

告诉 LLM 何时使用 cloud-agent（深度调研、沙箱执行、长任务），何时不使用（本地文件、隐私数据、简单搜索）。

### 4.3 execute.py

通过 `nodes run` 被调用，接收 `--task` `--context` 参数，POST /acp/execute，消费 SSE 流，返回 JSON 结果。

### 4.4 多轮协作工作流

```
用户: "根据桌面竞品表格做调研并生成PPT"

Turn 1: LLM 选 excel-analyzer
        --> 提取竞品数据 --> 结果进入上下文

Turn 2: LLM 看到 Turn 1 结果，选 cloud-agent
        --> task="调研融资" context="竞品:Manus,Devin..."
        --> 云端执行 --> 返回融资数据

Turn 3: LLM 看到 Turn 2 结果，选 ppt-generator
        --> 用融资数据生成 PPT --> 保存桌面

Turn 4: LLM 生成回复: "PPT已保存到桌面/竞品分析.pptx"
```

数据流转靠 LLM 上下文，不靠协议。这是 RVR-B 多轮循环的设计初衷。

---

## 五、云端实现

### 5.1 ACP Router

`routers/acp.py`：5 个端点。`execute` 内部调用现有 ChatService。对云端 Agent 零侵入。

### 5.2 TaskManager

`services/acp_task_manager.py`：Redis Streams 事件缓冲 + 状态管理。

---

## 六、实现分期

### Phase 1: MVP（约 1 周）

**本地端**：
- 新增 `skills/library/cloud-agent/SKILL.md`
- 新增 `skills/library/cloud-agent/scripts/execute.py`
- 修改 `instances/xiaodazi/config/skills.yaml` 注册
- 修改 `.env` 增加 ACP_ENDPOINT + ACP_SECRET_KEY

**云端**：
- 新增 `routers/acp.py`（5 端点）
- 新增 `services/acp_task_manager.py`
- 修改 `main.py` 挂载 Router

### Phase 2: 状态控制 + 断线恢复（约 1 周）

Redis Streams 缓冲，last_seq 续传，取消任务，进度转发前端。

### Phase 3: 异步推送（约 1 周）

/acp/ws WebSocket，定时调度，推送通知。

---

## 七、对比总结

| 维度 | Plan 驱动 | Skill 模式 |
| --- | --- | --- |
| 端点 | 13+ | 5 |
| 本地新增 | 5+ 文件 | 1 个 Skill 目录 |
| 云端新增 | 3+ 文件 | 2 个文件 |
| 数据流转 | 显式协议 | LLM 上下文 |
| 编排逻辑 | 协议层 | LLM 大脑 |
| 实现周期 | 3-4 周 | 1 周 |

**核心哲学：把智能交给 LLM，把管道做简单。**
