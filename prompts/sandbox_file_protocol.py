"""
沙盒文件操作协议

为 LLM 提供沙盒文件操作的指导说明。
"""

SANDBOX_FILE_PROTOCOL = """
## 沙盒文件操作协议

当用户需要在沙盒环境中进行文件操作时，使用以下工具：

### 可用工具

1. **sandbox_list_dir** - 列出目录内容
   - 用途：查看沙盒中指定目录下的文件和文件夹
   - 参数：conversation_id, path（默认 /home/user）
   
2. **sandbox_read_file** - 读取文件内容
   - 用途：读取沙盒中文件的文本内容
   - 参数：conversation_id, path（完整路径）
   
3. **sandbox_write_file** - 写入文件
   - 用途：创建或更新沙盒中的文件
   - 参数：conversation_id, path, content
   - 注意：目录会自动创建
   
4. **sandbox_delete_file** - 删除文件
   - 用途：删除沙盒中的文件或目录
   - 参数：conversation_id, path
   - 警告：删除操作不可恢复
   
5. **sandbox_run_command** - 执行命令
   - 用途：在沙盒中执行 shell 命令
   - 参数：conversation_id, command, timeout
   - 常用命令：
     * `pip install <package>` - 安装 Python 包
     * `npm install` - 安装 Node.js 依赖
     * `ls -la` - 列出目录详情
     
6. **sandbox_create_project** - 创建项目
   - 用途：快速创建指定类型的项目框架
   - 参数：conversation_id, project_name, stack
   - 支持的技术栈：streamlit, gradio, flask, fastapi, python

7. **sandbox_run_project** - 运行项目
   - 用途：启动沙盒中的项目，获取预览 URL
   - 参数：conversation_id, project_path, stack
   - 返回：preview_url（E2B 公网可访问地址）
   - 代码结构要求：
     * streamlit/gradio/flask: 入口文件为 `app.py`
     * fastapi: 入口文件为 `main.py`（需要 `main:app`）
     * nodejs/react/vue: 需要 `package.json`

### 路径规范

- 所有路径从 `/home/user` 开始
- 项目通常放在 `/home/user/<project_name>/`
- 输入文件：`/home/user/input_data/`
- 输出文件：`/home/user/output_data/`

### 工作流程示例

#### 创建新项目

```
1. 调用 sandbox_create_project 创建项目框架
2. 调用 sandbox_write_file 修改代码
3. 调用 sandbox_run_command 安装依赖（如需额外依赖）
4. 调用 sandbox_run_project 启动项目，获取预览 URL
5. 将预览 URL 告诉用户
```

#### 修改现有文件

```
1. 调用 sandbox_read_file 读取当前内容
2. 修改内容
3. 调用 sandbox_write_file 保存修改
4. 如果项目已运行，Streamlit/Gradio 会自动热重载
5. 如果需要重启，再次调用 sandbox_run_project
```

#### 💡 启动项目最佳实践

**使用 sandbox_run_project 工具启动项目：**
- 会自动安装 requirements.txt 中的依赖
- 返回 E2B 公网可访问的 preview_url
- 不要使用 localhost 或 127.0.0.1 地址

### 注意事项

1. **conversation_id 必需**：所有操作都需要指定对话 ID
2. **路径要完整**：使用完整路径如 `/home/user/app.py`
3. **热重载**：Streamlit/Gradio 应用支持热重载，更新代码后自动刷新
4. **文件大小限制**：读取大文件时内容会被截断
5. **二进制文件**：二进制文件可能无法正确读取

### 与前端同步

当你修改沙盒中的文件时：
- 前端的文件浏览器会实时更新
- 用户可以看到你创建/修改的文件
- 用户可以直接在前端编辑文件
"""


def get_sandbox_file_protocol() -> str:
    """
    获取沙盒文件操作协议
    
    Returns:
        协议文本
    """
    return SANDBOX_FILE_PROTOCOL


# 用于 System Prompt 的简化版本
SANDBOX_FILE_PROTOCOL_BRIEF = """
## Sandbox File Tools

You have access to sandbox file tools for managing files in E2B sandbox:

| Tool | Purpose |
|------|---------|
| sandbox_list_dir | List directory contents |
| sandbox_read_file | Read file content |
| sandbox_write_file | Create/update files |
| sandbox_delete_file | Delete files/directories |
| sandbox_run_command | Execute shell commands |
| sandbox_create_project | Create project from template |
| sandbox_run_project | Run project and get preview URL |

All paths start from `/home/user`. Use full paths like `/home/user/my_project/app.py`.

💡 **Project Launch**: Use `sandbox_run_project` to start projects. It returns a public preview URL (https://xxx.e2b.dev), not localhost!
"""


def get_sandbox_file_protocol_brief() -> str:
    """
    获取沙盒文件操作协议（简化版）
    
    Returns:
        协议文本
    """
    return SANDBOX_FILE_PROTOCOL_BRIEF


def build_sandbox_context(conversation_id: str, user_id: str = None) -> str:
    """
    构建沙盒运行时上下文
    
    为 System Prompt 动态注入当前会话信息，让 Agent 能正确调用 sandbox_* 工具。
    
    Args:
        conversation_id: 对话 ID（必填，sandbox 工具需要）
        user_id: 用户 ID（可选）
        
    Returns:
        格式化的上下文字符串
    """
    context = f"""

---

# 🔒 沙盒运行环境（CRITICAL - 必读）

## 当前会话

- **conversation_id**: `{conversation_id}`
"""
    
    if user_id:
        context += f"- **user_id**: `{user_id}`\n"
    
    context += f"""
## ⚠️ 核心规则：所有操作都在云沙盒中执行

**你运行在一个隔离的 E2B 云沙盒环境中，不是本地机器！**

- ✅ 工作目录: `/home/user`
- ✅ 项目目录: `/home/user/<project_name>/`
- ❌ **禁止使用**: `/tmp`、`/var`、`./` 等本地路径

## 🛠️ 工具说明

### Claude 原生工具（自动路由到沙盒）

| 工具 | 说明 |
|------|------|
| `bash` | 在沙盒中执行 shell 命令 |
| `str_replace_based_edit_tool` | 在沙盒中创建/编辑文件 |

### 沙盒专用工具

| 工具 | 说明 |
|------|------|
| `sandbox_write_file` | 创建/更新沙盒文件 |
| `sandbox_read_file` | 读取沙盒文件 |
| `sandbox_run_command` | 执行命令（安装依赖等） |
| `sandbox_run_project` | 🚀 启动项目，返回 preview_url |

## 📁 路径规范

```
/home/user/                     ← 工作根目录
├── my_app/                     ← 项目目录
│   ├── app.py
│   ├── requirements.txt
│   └── templates/
├── input_data/                 ← 输入文件
└── output_data/                ← 输出文件
```

## 正确示例

### 使用 bash 工具

```json
{{
    "command": "cd /home/user/my_app && pip install -r requirements.txt"
}}
```

### 使用 text_editor (str_replace_based_edit_tool)

```json
{{
    "command": "create",
    "path": "/home/user/my_app/app.py",
    "file_text": "print('Hello from sandbox!')"
}}
```

### 使用 sandbox_write_file

```json
{{
    "conversation_id": "{conversation_id}",
    "path": "/home/user/my_app/app.py",
    "content": "print('Hello from sandbox!')"
}}
```

## ❌ 错误示例（禁止）

```json
// ❌ 不要使用 /tmp
{{"path": "/tmp/my_app/app.py"}}

// ❌ 不要使用相对路径
{{"path": "./app.py"}}

// ❌ 不要使用本地目录
{{"command": "cd /Users/xxx/projects && ls"}}
```

## 💡 最佳实践

1. **文件路径**: 始终使用 `/home/user/` 开头的绝对路径
2. **项目结构**: 将项目放在 `/home/user/<project_name>/` 下
3. **依赖安装**: 使用 `pip install -r requirements.txt`

## 🖥️ 实时终端与验证

**你的 shell 命令和输出会在前端终端实时显示给用户！**

### ✅ 必须进行验证
用户希望看到你验证你的工作。修改代码或启动服务后，请使用 `sandbox_run_command` 执行验证命令：

1. **验证服务状态**：
   ```json
   {{
       "command": "curl -I http://localhost:8000"
   }}
   ```

2. **验证页面内容**：
   ```json
   {{
       "command": "curl -s http://localhost:3000 | grep -o '<title>.*</title>'"
   }}
   ```

3. **验证文件内容**：
   ```json
   {{
       "command": "grep 'DEBUG' /home/user/my_app/config.py"
   }}
   ```

**展示给用户的效果**：
用户会看到一个真实的终端窗口，显示你执行的每一条命令及其输出。这能增加用户对你工作的信任感。

## 📦 依赖管理

**沙盒环境已预装数据分析包**（pandas, numpy, matplotlib）。

**Web 框架需要安装**（streamlit, flask, fastapi 等）。

### ✅ 正确做法

1. **创建代码文件**
2. **调用 `sandbox_run_project`** - 它会自动检查并安装依赖
3. **不要手动执行 `pip install`** - 让 `sandbox_run_project` 处理

## 🚀 启动项目规则

### ✅ 使用 sandbox_run_project 工具

当项目代码创建/修改完成后，**直接**调用 `sandbox_run_project` 启动项目（无需安装依赖）：

```json
{{
    "conversation_id": "{conversation_id}",
    "project_path": "/home/user/my_app",
    "stack": "streamlit"
}}
```

返回结果：
```json
{{
    "success": true,
    "preview_url": "https://xxx-8501.e2b.dev"
}}
```

### ⚠️ 不要使用 bash 启动

**禁止使用以下方式启动项目：**
- `python app.py` / `streamlit run app.py`
- `npm start` / `npm run dev`
- `nohup ... &`

原因：bash 启动无法获取正确的 preview_url，且不可靠。

### 响应示例

```
✅ 项目创建完成并已启动！

📁 项目结构：
- /home/user/my_app/app.py
- /home/user/my_app/requirements.txt

🌐 预览地址：https://xxx-8501.e2b.dev

点击链接即可查看应用效果。
```

### 代码结构要求

| 技术栈 | 入口文件 | 端口 |
|--------|----------|------|
| streamlit | app.py | 8501 |
| gradio | app.py | 7860 |
| flask | app.py | 5000 |
| fastapi | main.py | 8000 |
"""
    return context

