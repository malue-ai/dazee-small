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
   - 用途：启动项目并获取预览 URL
   - 参数：conversation_id, project_path, stack
   - 返回：preview_url

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
3. 调用 sandbox_run_command 安装依赖
4. 调用 sandbox_run_project 启动项目
5. 返回 preview_url 给用户
```

#### 修改现有文件

```
1. 调用 sandbox_read_file 读取当前内容
2. 修改内容
3. 调用 sandbox_write_file 保存修改
4. 如果是应用，调用 sandbox_run_project 重启（热重载）
```

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
| sandbox_run_project | Start project and get preview URL |

All paths start from `/home/user`. Use full paths like `/home/user/my_project/app.py`.
"""


def get_sandbox_file_protocol_brief() -> str:
    """
    获取沙盒文件操作协议（简化版）
    
    Returns:
        协议文本
    """
    return SANDBOX_FILE_PROTOCOL_BRIEF

