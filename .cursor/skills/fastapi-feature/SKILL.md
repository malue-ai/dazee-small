---
name: fastapi-feature
description: 按本仓库 FastAPI 三层架构实现功能增量（routers/services/models），遵守异步 I/O、Pydantic v2、统一日志与错误返回。用于新增/修改 API 端点、CRUD、业务流程、数据模型时。
---

# fastapi-feature

## 适用场景（触发词）

- 新增/修改 **FastAPI endpoint**、路由、接口协议（path/method/body/response）
- 新增/修改 **Service** 业务逻辑（只写一次，供 HTTP/gRPC 复用）
- 新增/修改 **Pydantic** 请求/响应模型（v2）
- 修复接口类 bug（校验、错误码、超时、并发、幂等）

## 强约束（必须遵守）

- **三层架构**：`routers/` 只做协议转换 → `services/` 写业务逻辑 → `models/` 放 Pydantic 模型
- **异步优先**：禁止阻塞 I/O（不要 `requests` / `time.sleep` / `with open()`）
  - HTTP 用 `httpx.AsyncClient`
  - 文件用 `aiofiles`
- **日志规范**：使用项目统一日志模块（`get_logger`），禁止 `print()`
- **敏感信息**：不要把 token/key 写进代码、提交或返回内容；不要改/创建 `config.yaml`（除非用户明确要求）
- **错误返回一致**：失败响应必须包含 `"error"` 字段（按项目既有约定）；参数校验优先用 Pydantic/HTTPException

## 输入信息（缺少就先补齐）

如果用户没说清楚，先用最少问题补齐这四类信息：

- **接口协议**：method + path + query/body + success response + error codes
- **业务规则**：关键约束、边界条件、权限/鉴权（如果有）
- **数据模型**：字段、类型、可空、默认值、约束、示例
- **影响面**：是否需要前端配合、配置项、迁移、文档更新

## 工作流（按顺序执行）

### 1) 选“落点”与命名

- 在 `routers/` 选择或新建对应路由文件（按现有模块划分）
- 在 `services/` 创建对应 service 函数（**RORO：接收对象，返回对象**）
- 在 `models/` 添加请求/响应模型（Pydantic v2，类型注解齐全）

### 2) 先写 models（协议先行）

- 建 `*Request` / `*Response`（必要时补 `ErrorResponse`）
- 字段用 `Field(..., description="...")` 写清含义与约束
- 响应结构遵循项目既有模式：
  - 成功：包含业务数据（必要时 `success: true`）
  - 失败：包含 `error`（必要时同时含 `code/message`）

### 3) 再写 services（业务逻辑只写一次）

- service 函数签名：**输入/输出用 Pydantic model 或 typed dict（优先 model）**
- 早返回（Guard Clauses），减少嵌套
- 外部调用（HTTP/DB/文件）全部异步 + 超时保护
- 记录关键路径日志（包含可追踪的 `session_id/user_id/request_id` 就用上下文注入，不要硬塞到函数参数里）

### 4) 最后写 routers（只做协议转换）

- 解析/校验请求（依赖 FastAPI/Pydantic）
- 调用 service，转换为 HTTP 响应
- 预期错误用 `HTTPException`（包含结构化 `detail`），非预期错误记录堆栈（`exc_info=True`）并返回统一错误结构

### 5) 回归与最小验证

- 只跑与改动相关的测试/脚本（若仓库已有同类测试，优先复用）
- 如果没有测试，至少给出“可复制”的手动验证步骤（curl 示例/页面操作路径）

## 输出要求（交付物清单）

每次使用本 Skill，最终输出必须包含：

- **变更文件列表**：新增/修改了哪些文件（路径）
- **接口说明**：method/path、请求/响应示例、错误码（简短）
- **验证方式**：测试命令或手动验证步骤（可复制）

## 代码模板（只在需要时使用）

### 统一错误 detail 模板（示意）

```python
raise HTTPException(
    status_code=400,
    detail={"code": "VALIDATION_ERROR", "message": "参数不合法"},
)
```

### Service RORO 模板（示意）

```python
from pydantic import BaseModel


class DoThingRequest(BaseModel):
    # ...
    pass


class DoThingResponse(BaseModel):
    # ...
    pass


async def do_thing(req: DoThingRequest) -> DoThingResponse:
    """业务逻辑：接收对象，返回对象"""
    # guard clauses...
    return DoThingResponse()
```

