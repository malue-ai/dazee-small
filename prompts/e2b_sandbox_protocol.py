"""
E2B Sandbox Protocol - 沙盒文件操作协议
面向 LLM，简洁直接

⚠️ 重要：所有文件操作必须在 E2B 沙盒中进行，不要使用本地文件系统！
"""

E2B_SANDBOX_PROTOCOL = """
## ⚠️ 核心规则：文件操作必须使用沙盒工具

**禁止使用本地文件系统！** 所有代码和文件都应该在 E2B 沙盒中创建和管理。

### 可用的沙盒工具

| 工具 | 用途 | 示例 |
|------|------|------|
| `sandbox_list_dir` | 列出目录内容 | 查看 `/home/user` 下的文件 |
| `sandbox_read_file` | 读取文件内容 | 读取代码或配置文件 |
| `sandbox_write_file` | 创建/更新文件 | 创建 `app.py`、`index.html` 等 |
| `sandbox_delete_file` | 删除文件 | 清理不需要的文件 |
| `sandbox_file_exists` | 检查文件是否存在 | 判断文件是否已创建 |
| `sandbox_run_command` | 执行 shell 命令 | `pip install`、`npm install` 等 |
| `sandbox_run_code` | 执行 Python 代码 | 数据分析、API 调用等 |
| `sandbox_create_project` | 创建项目框架 | 快速创建 Streamlit/Gradio 项目 |
| `sandbox_run_project` | 运行项目 | 启动应用并获取预览 URL |

### 🚨 路径规范

所有路径都从 `/home/user` 开始：

```
/home/user/                    # 工作目录
  ├── my_project/              # 项目目录
  │   ├── app.py              # 应用入口
  │   └── requirements.txt    # 依赖文件
  ├── input_data/             # 输入数据
  └── output_data/            # 输出结果
```

**正确的路径示例**：
- `/home/user/app.py`
- `/home/user/my_project/index.html`
- `/home/user/output_data/result.csv`

**❌ 禁止使用本地路径**：
- ❌ `workspace/conversations/conv_xxx/...`
- ❌ `/Users/xxx/projects/...`
- ❌ 任何本地文件系统路径

### 工作流程

#### 创建新项目

```
1. sandbox_create_project: 创建项目框架
   → project_name: "my_app"
   → stack: "streamlit"
   
2. sandbox_write_file: 编写代码
   → path: "/home/user/my_app/app.py"
   → content: "import streamlit as st..."
   
3. sandbox_run_command: 安装依赖（如需要）
   → command: "pip install extra-package"
   
4. sandbox_run_project: 启动项目
   → 返回 preview_url
```

#### 执行数据分析

```
1. sandbox_run_code: 执行 Python 代码
   → code: '''
   import pandas as pd
   df = pd.read_csv('/home/user/input_data/data.csv')
   result = df.describe()
   print(result)
   '''
```

### 技术栈支持

| 技术栈 | 入口文件 | 启动命令 |
|--------|----------|----------|
| streamlit | app.py | `streamlit run app.py` |
| gradio | app.py | `python app.py` |
| flask | app.py | `flask run` |
| fastapi | main.py | `uvicorn main:app` |
| python | main.py | `python main.py` |

### 示例：创建 Streamlit 应用

```json
// Step 1: 创建项目
sandbox_create_project({
  "conversation_id": "conv_xxx",
  "project_name": "my_dashboard",
  "stack": "streamlit"
})

// Step 2: 更新代码
sandbox_write_file({
  "conversation_id": "conv_xxx",
  "path": "/home/user/my_dashboard/app.py",
  "content": "import streamlit as st\\nst.title('Hello World')\\nst.write('Welcome!')"
})

// Step 3: 运行项目
sandbox_run_project({
  "conversation_id": "conv_xxx",
  "project_path": "/home/user/my_dashboard",
  "stack": "streamlit"
})
// 返回: { "preview_url": "https://xxx.e2b.dev" }
```

### 与前端同步

当你在沙盒中创建/修改文件时：
- 前端文件浏览器会实时显示沙盒中的文件
- 用户可以直接在前端编辑这些文件
- 运行项目后，用户可以在前端预览应用

### ⚠️ 注意事项

1. **conversation_id 必需**：所有沙盒操作都需要 `conversation_id` 参数
2. **路径要完整**：使用完整路径如 `/home/user/app.py`
3. **热重载**：Streamlit/Gradio 支持热重载，更新代码后自动刷新
4. **沙盒生命周期**：沙盒会在用户离开时自动暂停，回来时自动恢复

### 🚨 预览 URL 规范

**禁止使用本地地址！** 如 `http://127.0.0.1:5000` 或 `http://localhost:8501`

正确做法：
1. 调用 `sandbox_run_project` 启动项目
2. 从返回结果获取 `preview_url`
3. 使用 E2B 提供的 URL（格式：`https://5000-xxxxx.e2b.app`）

示例：
```json
sandbox_run_project({
  "conversation_id": "conv_xxx",
  "project_path": "my_app",
  "stack": "flask"
})
// 返回: { "success": true, "preview_url": "https://5000-abc123.e2b.app" }
```

**在向用户说明时，必须使用返回的 preview_url，不要写 localhost 或 127.0.0.1！**
"""


def get_e2b_sandbox_protocol() -> str:
    """获取 E2B Sandbox 协议"""
    return E2B_SANDBOX_PROTOCOL


# 简化版本（用于 capabilities.yaml）
E2B_SANDBOX_BRIEF = """
## 沙盒文件工具

⚠️ **所有文件操作必须使用沙盒工具，不要使用本地文件系统！**

| 工具 | 用途 |
|------|------|
| sandbox_list_dir | 列出目录内容 |
| sandbox_read_file | 读取文件 |
| sandbox_write_file | 创建/更新文件 |
| sandbox_delete_file | 删除文件 |
| sandbox_run_command | 执行命令 |
| sandbox_run_code | 执行 Python |
| sandbox_create_project | 创建项目 |
| sandbox_run_project | 运行项目 |

路径从 `/home/user` 开始，如 `/home/user/my_app/app.py`
"""


def get_e2b_sandbox_brief() -> str:
    """获取 E2B Sandbox 简化协议"""
    return E2B_SANDBOX_BRIEF
