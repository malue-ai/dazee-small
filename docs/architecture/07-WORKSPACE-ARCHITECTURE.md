# Workspace 与 Sandbox 架构设计

> 本文档定义 workspace 的设计理念、文件操作方式、以及与 E2B Sandbox 的协作关系

---

## 一、核心理念

### 1.1 两个独立的概念

| 概念 | 位置 | 特点 | 用途 |
|------|------|------|------|
| **Workspace** | 本地服务器 | 永久存储、用户可下载 | 存放文件（源码、文档、产物） |
| **Sandbox** | E2B 远程 | 临时环境、隔离安全 | 执行代码、运行服务 |

```
Workspace = 文件柜（永久保存）
Sandbox   = 临时工作台（用完即弃）
```

### 1.2 设计原则

1. **Workspace 完全自由**：不预设任何目录结构，Agent 想怎么组织就怎么组织
2. **Agent 使用相对路径**：Agent 不需要知道真实的文件系统路径
3. **Sandbox 按需创建**：只有需要执行代码时才创建
4. **前端可见**：提供 API 让前端展示 workspace 内容

---

## 二、目录结构

### 2.1 物理结构

```
workspace/
└── conversations/
    └── {conversation_id}/
        └── workspace/          ← Agent 的工作区（完全自由）
            ├── ...             ← Agent 创建的任何文件
            └── ...             ← Agent 创建的任何目录
```

### 2.2 Agent 视角

Agent 看到的是一个**空白的工作区**，它可以：
- 创建任意文件和目录
- 自由组织项目结构
- 不受任何预设限制

```python
# Agent 操作示例
write_file("main.py", code)           # 创建文件
write_file("src/utils.py", utils)     # 创建目录 + 文件
write_file("data/input.csv", csv)     # 另一个目录
list_dir(".")                         # 查看根目录
list_dir("src")                       # 查看子目录
```

### 2.3 路径映射

| Agent 看到的路径 | 实际路径 |
|------------------|----------|
| `main.py` | `workspace/conversations/{conv_id}/workspace/main.py` |
| `src/app.py` | `workspace/conversations/{conv_id}/workspace/src/app.py` |
| `.` | `workspace/conversations/{conv_id}/workspace/` |

---

## 三、File Tools 设计

### 3.1 工具列表

| 工具 | 功能 | 参数 |
|------|------|------|
| `read_file` | 读取文件内容 | `path: str` |
| `write_file` | 写入/创建文件 | `path: str, content: str` |
| `list_dir` | 列出目录内容 | `path: str = "."` |
| `delete_file` | 删除文件 | `path: str` |
| `file_exists` | 检查文件是否存在 | `path: str` |

### 3.2 实现要点

```python
class BaseFileTool:
    """文件工具基类"""
    
    def get_workspace_root(self, conversation_id: str) -> Path:
        """获取工作区根路径"""
        return Path(f"workspace/conversations/{conversation_id}/workspace")
    
    def resolve_path(self, conversation_id: str, relative_path: str) -> Path:
        """
        解析相对路径为绝对路径
        
        包含安全检查，防止路径穿越
        """
        workspace_root = self.get_workspace_root(conversation_id)
        full_path = (workspace_root / relative_path).resolve()
        
        # 安全检查：确保路径在 workspace 内
        if not full_path.is_relative_to(workspace_root.resolve()):
            raise SecurityError("非法路径：不能访问工作区外的文件")
        
        return full_path
```

### 3.3 安全边界

- ✅ 可以访问：workspace 内的任何文件和目录
- ❌ 不能访问：workspace 外的任何路径
- ❌ 不能穿越：`../../etc/passwd` 等路径会被拒绝

---

## 四、前端接口

### 4.1 获取文件列表

```
GET /api/workspace/{conversation_id}/files

Response:
{
    "conversation_id": "conv_abc123",
    "files": [
        {
            "path": "main.py",
            "type": "file",
            "size": 1024,
            "modified_at": "2025-01-01T12:00:00Z"
        },
        {
            "path": "src",
            "type": "directory",
            "children": [
                {
                    "path": "src/app.py",
                    "type": "file",
                    "size": 2048,
                    "modified_at": "2025-01-01T12:01:00Z"
                }
            ]
        }
    ]
}
```

### 4.2 获取文件内容

```
GET /api/workspace/{conversation_id}/files/{path}

# 示例：GET /api/workspace/conv_abc123/files/src/app.py

Response:
- 文本文件：返回内容
- 二进制文件：返回下载流
```

### 4.3 上传文件

```
POST /api/workspace/{conversation_id}/files
Content-Type: multipart/form-data

Body:
- file: 文件内容
- path: 目标路径（可选，默认为文件名）
```

### 4.4 删除文件

```
DELETE /api/workspace/{conversation_id}/files/{path}
```

---

## 五、Sandbox 使用时机

### 5.1 什么时候需要 Sandbox？

| 场景 | 需要 Sandbox | 原因 |
|------|--------------|------|
| 执行 Python/Node.js 代码 | ✅ 是 | 安全隔离 |
| 启动 Web 服务（Gradio/Streamlit） | ✅ 是 | 需要公网 URL |
| 安装依赖并运行 | ✅ 是 | 避免污染主机 |
| 编译项目 | ✅ 是 | 需要构建环境 |

### 5.2 什么时候不需要 Sandbox？

| 场景 | 需要 Sandbox | 替代方案 |
|------|--------------|----------|
| 读写文本文件 | ❌ 否 | 本地 File Tools |
| 生成 HTML/Markdown/JSON | ❌ 否 | 直接写文件 |
| 修改 Office 文件 | ❌ 否 | python-pptx 等本地库 |
| 分析文件内容（不执行） | ❌ 否 | 本地读取 |

### 5.3 触发方式

**核心原则：前端触发，按需启动**

因为 Sandbox 不能一直运行（1小时自动销毁），所以：
- ✅ 前端提供「运行」按钮，用户随时可以点击启动
- ✅ Sandbox 过期后，用户再次点击可以重新启动
- ❌ 不能依赖 Sandbox 一直存在

**流程**：

```
用户操作：
    点击「运行」→ 创建 Sandbox → 返回预览 URL → 使用
    ↓
    1小时后 Sandbox 销毁
    ↓
    再次点击「运行」→ 重新创建 → 重新返回 URL → 继续使用
```

**实现**：

```javascript
// 前端示例
async function runProject(conversationId, projectPath) {
    const response = await fetch(
        `/api/workspace/${conversationId}/sandbox/run`,
        {
            method: 'POST',
            body: JSON.stringify({ project_path: projectPath })
        }
    );
    
    const { sandbox_id, preview_url, expires_at } = await response.json();
    
    // 打开预览窗口
    window.open(preview_url, '_blank');
    
    // 显示过期提示
    showExpiryNotice(expires_at);
}
```

---

## 六、Sandbox 运行机制

### 6.1 核心理念：按需上传，用完即弃

**不是"同步"，是"上传"**

```
Workspace（源码永久保存）
    ↓
    用户点击「运行」按钮
    ↓
    前端调用 API：POST /workspace/{conv_id}/sandbox/run
    ↓
    后端：创建 Sandbox + 上传项目文件
    ↓
    Sandbox 执行并返回预览 URL
    ↓
    用户预览/使用
    ↓
    1 小时后 Sandbox 自动销毁
    ↓
    用户再次点击「运行」→ 重新上传 + 重新启动
```

**关键点**：
- Agent 只操作 workspace（写源码）
- Agent 不感知 Sandbox 的存在
- 前端负责触发"上传+运行"
- 每次运行都是全新的 Sandbox

### 6.2 上传策略

```python
async def run_project_in_sandbox(conversation_id: str, project_path: str = "."):
    """
    把项目上传到 Sandbox 并运行
    
    Args:
        conversation_id: 对话ID
        project_path: 项目在 workspace 中的相对路径（默认根目录）
    """
    # 1. 打包项目文件
    workspace_path = get_workspace_path(conversation_id)
    project_full_path = workspace_path / project_path
    archive = create_tar_gz(project_full_path)
    
    # 2. 创建新的 Sandbox
    sandbox = Sandbox.create(
        timeout=3600,  # 1小时
        metadata={
            "conversation_id": conversation_id,
            "project_path": project_path
        }
    )
    
    # 3. 上传并解压
    sandbox.files.write("/home/user/project.tar.gz", archive)
    sandbox.commands.run("cd /home/user && tar -xzf project.tar.gz")
    
    # 4. 执行启动命令（根据项目类型）
    if has_file(project_full_path / "requirements.txt"):
        sandbox.commands.run("pip install -r requirements.txt")
    
    if has_file(project_full_path / "app.py"):
        sandbox.commands.run("python app.py &")
    
    # 5. 返回预览 URL
    preview_url = sandbox.get_host(7860)
    
    return {
        "sandbox_id": sandbox.id,
        "preview_url": preview_url,
        "expires_at": datetime.now() + timedelta(hours=1)
    }
```

### 6.3 Sandbox 生命周期

```
┌─────────────────────────────────────────────────────────┐
│  前端展示 Workspace 文件/项目                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ project-a│  │ project-b│  │ project-c│              │
│  │ [运行]   │  │ [运行]   │  │ [运行]   │              │
│  └──────────┘  └──────────┘  └──────────┘              │
└─────────────────────────────────────────────────────────┘
       │
       ├─ 用户点击 [运行]
       ↓
┌─────────────────────────────────────────────────────────┐
│  创建 Sandbox                                            │
│  - 上传项目文件                                          │
│  - 安装依赖                                              │
│  - 启动服务                                              │
│  ✅ 返回预览 URL                                         │
└─────────────────────────────────────────────────────────┘
       │
       ├─ 1 小时内正常使用
       ↓
┌─────────────────────────────────────────────────────────┐
│  Sandbox 超时自动销毁                                    │
│  ❌ 预览 URL 失效                                        │
└─────────────────────────────────────────────────────────┘
       │
       ├─ 用户再次点击 [运行]
       ↓
       重复上面的流程（重新创建）
```

### 6.4 为什么不需要"同步"？

| 错误理解 | 正确理解 |
|---------|---------|
| Agent 修改代码 → 自动同步到 Sandbox | Agent 修改代码 → 存到 workspace，Sandbox 不管 |
| 保持 Workspace 和 Sandbox 一致 | Sandbox 是临时的，不需要一致 |
| Agent 感知 Sandbox 状态 | Agent 只管 workspace，不知道 Sandbox |

**Agent 的职责**：写源码到 workspace
**Sandbox 的职责**：执行源码（一次性）
**前端的职责**：触发"上传+运行"

---

## 七、两种 Sandbox 使用场景

### 7.1 场景区分

| 场景 | 工具 | 特点 | 示例 |
|------|------|------|------|
| **简单代码执行** | `execute_code` | 一次性任务，自动保存产物 | 生成表格、数据处理、图表生成 |
| **Web 应用** | `vibe_coding` | 持续运行，返回预览 URL | Gradio 应用、Streamlit 仪表板 |

---

### 7.2 场景一：简单代码执行（execute_code）

**适用场景**：
- 数据处理（生成 Excel/CSV）
- 图表生成（PNG/PDF）
- 文件格式转换
- 简单计算

**Agent 调用**：

```python
execute_code({
    "code": """
import pandas as pd
data = {'产品': ['A', 'B', 'C'], '销量': [100, 200, 150]}
df = pd.DataFrame(data)
df.to_excel('/home/user/sales.xlsx', index=False)
    """,
    "conversation_id": "conv_123",
    "return_files": ["/home/user/sales.xlsx"]  # 关键：自动下载
})
```

**系统流程**：

```
1. 创建临时 Sandbox
2. 执行 Python 代码
3. 自动下载 sales.xlsx 到 workspace/conversations/{conv_id}/workspace/
4. 销毁 Sandbox
5. 返回结果给 Agent
```

**返回结果**：

```json
{
    "success": true,
    "stdout": "...",
    "files": {
        "/home/user/sales.xlsx": {
            "local_path": "sales.xlsx",
            "size": 5120
        }
    },
    "execution_time": 2.3
}
```

**关键点**：
- ✅ Agent 不需要关心 Sandbox 的创建和销毁
- ✅ 产物自动保存到 workspace
- ✅ 一次性任务，不需要持续运行
- ✅ 不需要前端触发

---

### 7.3 场景二：Web 应用（vibe_coding）

**适用场景**：
- Gradio 机器学习界面
- Streamlit 数据分析应用
- Next.js 全栈应用

**前端触发**：

```javascript
// 用户点击「运行」按钮
POST /workspace/{conv_id}/sandbox/run
Body: {
    "project_path": "asr-app",
    "stack": "gradio"
}
```

**系统流程**：

```
1. 上传项目代码到 Sandbox
2. 安装依赖
3. 启动服务（持续运行）
4. 返回预览 URL
5. 1小时后自动销毁
```

**返回结果**：

```json
{
    "success": true,
    "app_id": "app_20250101_120000",
    "preview_url": "https://xxx.e2b.dev",
    "sandbox_id": "sbx_123",
    "expires_in": "3600秒"
}
```

**关键点**：
- ✅ 持续运行，不是一次性
- ✅ 用户通过 URL 访问
- ✅ 前端负责触发
- ✅ 支持热重载（修改代码后自动更新）

---

### 7.4 两者对比

| 维度 | execute_code | vibe_coding |
|------|-------------|-------------|
| **触发方式** | Agent 调用工具 | 前端点击按钮 |
| **运行时长** | 执行完即销毁 | 持续运行 1 小时 |
| **产物处理** | 自动下载到 workspace | 不下载，只提供 URL |
| **用户交互** | 无 | 有（通过 Web UI） |
| **典型场景** | 生成表格、图表 | Gradio、Streamlit 应用 |
| **Agent 感知** | 需要（主动调用） | 不需要（前端处理） |

---

## 八、整体架构图

```
┌────────────────────────────────────────────────────────────────┐
│                           前端                                 │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌──────────────────┐          ┌──────────────────────────┐   │
│  │  聊天界面        │          │  Workspace 文件管理       │   │
│  │                  │          │                          │   │
│  │  - 发消息        │          │  - 文件树展示            │   │
│  │  - Agent 回复    │          │  - 项目卡片              │   │
│  │  - SSE 事件      │          │  - [运行] 按钮 ← 关键！  │   │
│  └──────────────────┘          └──────────────────────────┘   │
│         │                                │                     │
└─────────┼────────────────────────────────┼─────────────────────┘
          │                                │
          ▼                                ▼
┌────────────────────────────────────────────────────────────────┐
│                        后端 API                                │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  /chat/stream                  /workspace/{conv_id}/          │
│  - 处理用户消息                 - GET  /files      文件列表    │
│  - Agent 执行                   - GET  /projects   项目列表    │
│  - SSE 推送                     - POST /files      上传文件    │
│                                 - POST /sandbox/run 启动项目   │
│                                                                │
└───────────┬──────────────────────────────────┬─────────────────┘
            │                                  │
            ▼                                  ▼
┌───────────────────────────┐    ┌────────────────────────────┐
│      Agent Layer          │    │    SandboxManager          │
├───────────────────────────┤    ├────────────────────────────┤
│                           │    │                            │
│  File Tools:              │    │  - 创建 Sandbox            │
│  - read_file              │    │  - 上传项目文件            │
│  - write_file             │    │  - 执行启动命令            │
│  - list_dir               │    │  - 返回预览 URL            │
│  - delete_file            │    │  - 管理生命周期            │
│                           │    │                            │
│  只操作 Workspace         │    │  按需创建，用完即弃        │
│  不感知 Sandbox           │    │                            │
└───────────┬───────────────┘    └────────────┬───────────────┘
            │                                  │
            ▼                                  ▼
┌───────────────────────────┐    ┌────────────────────────────┐
│   本地 Workspace          │    │     E2B Sandbox            │
│   (永久存储)              │    │     (临时执行)             │
├───────────────────────────┤    ├────────────────────────────┤
│  workspace/               │    │  创建时：                  │
│    conversations/         │    │    ← 从 workspace 上传     │
│      {conv_id}/           │    │                            │
│        workspace/         │    │  运行中：                  │
│          project-a/       │    │    - 执行代码              │
│          project-b/       │    │    - 启动服务              │
│          ...              │    │    - 返回 URL              │
│                           │    │                            │
│  Agent 自由组织           │    │  1小时后自动销毁           │
│  不预设目录结构           │    │  需要时重新创建            │
└───────────────────────────┘    └────────────────────────────┘

关键流程：
1. Agent 写文件到 Workspace（左侧）
2. 前端展示文件和项目
3. 用户点击「运行」→ 触发上传到 Sandbox（右侧）
4. Sandbox 执行并返回 URL
5. 过期后重复步骤 3-4
```

---

## 九、代码上下文传递

### 9.1 Agent 如何知道 conversation_id？

通过 Tool Context 传递：

```python
class ToolContext:
    """工具执行上下文"""
    conversation_id: str
    message_id: str
    user_id: str


class ReadFileTool(BaseTool):
    async def _run(self, path: str, context: ToolContext) -> ToolResult:
        # 从 context 获取 conversation_id
        workspace_root = get_workspace_root(context.conversation_id)
        # ...
```

### 9.2 Sandbox 如何关联 conversation？

通过 metadata 标记：

```python
sandbox = Sandbox.create(
    timeout=3600,
    metadata={
        "conversation_id": conversation_id,
        "user_id": user_id,
        "project_path": project_path
    }
)

# 后续可以通过 metadata 查询
query = SandboxQuery(metadata={"conversation_id": conversation_id})
existing = Sandbox.list(query=query)
```

---

## 十、安全考虑

### 10.1 路径安全

```python
# 防止路径穿越
def is_safe_path(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False
```

### 10.2 conversation 隔离

- 每个 conversation 有独立的 workspace
- Agent 不能访问其他 conversation 的文件
- Sandbox 通过 metadata 隔离

### 10.3 文件大小限制

- 单文件上传限制：100MB
- workspace 总大小限制：1GB
- 上传到 Sandbox 时排除大文件（可配置）

---

## 十一、实现清单

### 11.1 需要实现的组件

| 组件 | 职责 | 优先级 |
|------|------|--------|
| `WorkspaceManager` | 管理本地 workspace 文件 | P0 |
| `File Tools` | Agent 文件操作工具 | P0 |
| `WorkspaceRouter` | 前端 API 接口 | P0 |
| `SandboxManager` | Sandbox 生命周期管理 | P1 |
| `SyncManager` | workspace ↔ sandbox 同步 | P1 |

### 11.2 Agent Tools 列表

**Workspace 操作工具（Agent 使用）**

| 工具 | 状态 | 说明 |
|------|------|------|
| `read_file` | 待实现 | 读取 workspace 文件 |
| `write_file` | 待实现 | 写入 workspace 文件 |
| `list_dir` | 待实现 | 列出目录内容 |
| `delete_file` | 待实现 | 删除文件 |
| `file_exists` | 待实现 | 检查文件是否存在 |

**重要说明**：
- ✅ Agent 只能操作 workspace 文件
- ❌ Agent 不应该有操作 Sandbox 的工具
- ❌ 不提供 `execute_code` 等直接执行工具给 Agent
- 原因：Sandbox 由前端触发，Agent 只负责写源码

### 11.3 API 接口

**Workspace 文件管理**

| 接口 | 方法 | 说明 |
|------|------|------|
| `/workspace/{conv_id}/files` | GET | 获取文件树 |
| `/workspace/{conv_id}/files/{path}` | GET | 获取/下载文件 |
| `/workspace/{conv_id}/files` | POST | 上传文件 |
| `/workspace/{conv_id}/files/{path}` | DELETE | 删除文件 |

**项目管理**

| 接口 | 方法 | 说明 |
|------|------|------|
| `/workspace/{conv_id}/projects` | GET | 获取所有项目列表 |

**Sandbox 管理**

| 接口 | 方法 | 说明 |
|------|------|------|
| `/workspace/{conv_id}/sandbox/run` | POST | 启动项目到 Sandbox |
| `/workspace/{conv_id}/sandbox/{sandbox_id}` | GET | 获取 Sandbox 状态 |
| `/workspace/{conv_id}/sandbox/{sandbox_id}` | DELETE | 停止 Sandbox |
| `/workspace/{conv_id}/sandbox/{sandbox_id}/download` | POST | 从 Sandbox 下载产物 |

---

## 十二、产品特色：多项目支持

### 12.1 设计理念

**差异化优势**：其他产品一个 conversation 只能做一个项目，我们支持**一个 conversation 多个项目**。

### 12.2 用户体验

**前端展示**：

```
┌────────────────────────────────────────────────┐
│  Conversation: 帮我做几个应用                  │
├────────────────────────────────────────────────┤
│  Workspace 项目列表：                          │
│                                                │
│  ┌──────────────────┐  ┌──────────────────┐   │
│  │  ASR 语音识别    │  │  图像分类器      │   │
│  │  📁 asr-app/     │  │  📁 image-clf/   │   │
│  │  ⚡ Gradio       │  │  ⚡ Streamlit    │   │
│  │  [运行] [下载]   │  │  [运行] [下载]   │   │
│  └──────────────────┘  └──────────────────┘   │
│                                                │
│  ┌──────────────────┐  ┌──────────────────┐   │
│  │  数据分析仪表板  │  │  聊天机器人      │   │
│  │  📁 dashboard/   │  │  📁 chatbot/     │   │
│  │  ⚡ Plotly Dash  │  │  ⚡ Next.js      │   │
│  │  [运行] [下载]   │  │  [运行] [下载]   │   │
│  └──────────────────┘  └──────────────────┘   │
└────────────────────────────────────────────────┘
```

**交互流程**：

```
用户：「帮我做一个语音识别应用」
    ↓
Agent 创建 workspace/asr-app/
    └── main.py
    └── requirements.txt
    └── README.md
    ↓
前端显示卡片：ASR 语音识别 [运行]
    ↓
用户点击 [运行] → 上传到 Sandbox → 返回预览 URL
    ↓
用户：「再帮我做一个图像分类器」
    ↓
Agent 创建 workspace/image-clf/
    └── app.py
    └── model.py
    └── ...
    ↓
前端新增卡片：图像分类器 [运行]
    ↓
用户可以同时管理多个项目
```

### 12.3 技术实现

**项目检测**：

```python
async def detect_projects(workspace_path: Path) -> List[ProjectInfo]:
    """
    检测 workspace 中的项目
    
    识别规则：
    - 包含 requirements.txt / package.json / pyproject.toml
    - 包含 app.py / main.py / index.html 等入口文件
    - 包含 README.md
    """
    projects = []
    
    for item in workspace_path.iterdir():
        if item.is_dir():
            project_info = analyze_project(item)
            if project_info:
                projects.append(project_info)
    
    return projects


class ProjectInfo:
    name: str              # 项目名称（目录名）
    path: str              # 相对路径
    type: str              # gradio / streamlit / nextjs / static
    entry_file: str        # 入口文件
    description: str       # 项目描述（从 README 提取）
    preview_url: str       # 如果 Sandbox 正在运行
    sandbox_id: str        # 关联的 Sandbox ID
    expires_at: datetime   # Sandbox 过期时间
```

**API 接口**：

```python
# GET /workspace/{conv_id}/projects
# 返回所有项目信息

# POST /workspace/{conv_id}/sandbox/run
# Body: { "project_path": "asr-app" }
# 启动特定项目到 Sandbox

# DELETE /workspace/{conv_id}/sandbox/{sandbox_id}
# 停止 Sandbox
```

### 12.4 项目目录结构示例

```
workspace/conversations/{conv_id}/workspace/
├── asr-app/                    # 项目 1：语音识别
│   ├── app.py
│   ├── requirements.txt
│   ├── README.md
│   └── models/
│       └── ...
│
├── image-classifier/           # 项目 2：图像分类
│   ├── main.py
│   ├── model.py
│   ├── requirements.txt
│   └── assets/
│       └── ...
│
├── data-analysis/              # 项目 3：数据分析
│   ├── dashboard.py
│   ├── data.csv
│   └── requirements.txt
│
└── shared-utils/               # 共享工具（可选）
    ├── __init__.py
    └── helpers.py
```

---

## 十三、其他扩展 Ideas

### 13.1 版本快照

支持对 workspace 创建快照，用户可以回溯到之前的版本。

### 13.2 跨 conversation 共享

允许用户把某个项目"导出"到共享区，供其他 conversation 使用。

### 13.3 项目模板

提供常用项目模板（Gradio、Streamlit、Next.js），Agent 可以快速初始化项目。

