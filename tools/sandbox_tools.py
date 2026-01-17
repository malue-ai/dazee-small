"""
沙盒工具 - E2B 沙盒操作（精简版）

核心工具（4 个）：
- sandbox_write_file: 写文件
- sandbox_run_command: 执行命令（读/列/删 用 bash）
- sandbox_create_project: 创建项目骨架
- sandbox_run_project: 运行项目，获取预览 URL
"""

import re
from typing import Dict, Any, List, Optional

from logger import get_logger
from tools.base import BaseTool
from services.sandbox_service import (
    get_sandbox_service,
    SandboxServiceError,
    SandboxNotFoundError
)

logger = get_logger("sandbox_tools")

PROJECT_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


def _normalize_project_path(project_path: str) -> str:
    """
    标准化项目路径为沙盒绝对路径。

    Args:
        project_path: 项目路径（支持 /home/user/xxx 或 xxx）

    Returns:
        标准化后的绝对路径
    """
    if not project_path:
        return "/home/user"

    if project_path.startswith("/"):
        return project_path

    return f"/home/user/{project_path}".replace("//", "/")


def _validate_project_name(project_name: str) -> Optional[str]:
    """
    校验项目名称，防止路径穿越等问题。

    Args:
        project_name: 项目名称

    Returns:
        错误信息（合法则返回 None）
    """
    if not project_name:
        return "project_name 不能为空"

    if "/" in project_name or "\\" in project_name:
        return "project_name 不能包含路径分隔符"

    if ".." in project_name:
        return "project_name 不能包含 .."

    if not PROJECT_NAME_PATTERN.match(project_name):
        return "project_name 只允许字母数字、_、-，且长度 1-64"

    return None


def _get_project_scaffold(stack: str, project_name: str) -> Dict[str, str]:
    """
    获取项目骨架文件集合（相对项目目录的路径 -> 内容）。

    Args:
        stack: 技术栈
        project_name: 项目名称

    Returns:
        文件映射

    Raises:
        ValueError: 不支持的技术栈
    """
    stack = (stack or "").lower()

    if stack == "streamlit":
        return {
            "requirements.txt": "streamlit>=1.33.0\n",
            "app.py": (
                "import streamlit as st\n\n\n"
                "def main() -> None:\n"
                "    \"\"\"Streamlit 入口\"\"\"\n"
                "    st.set_page_config(page_title='ZenFlux', page_icon='🧪')\n"
                "    st.title('Hello from Streamlit')\n"
                "    st.write('项目初始化完成，可以开始写代码了。')\n\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            ),
        }

    if stack == "gradio":
        return {
            "requirements.txt": "gradio>=4.0.0\n",
            "app.py": (
                "import gradio as gr\n\n\n"
                "def echo(text: str) -> str:\n"
                "    \"\"\"简单回声函数\"\"\"\n"
                "    return f'你输入了: {text}'\n\n\n"
                "def main() -> None:\n"
                "    \"\"\"Gradio 入口\"\"\"\n"
                "    demo = gr.Interface(fn=echo, inputs='text', outputs='text', title='ZenFlux')\n"
                "    demo.launch(server_name='0.0.0.0', server_port=7860)\n\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            ),
        }

    if stack == "flask":
        return {
            "requirements.txt": "flask>=3.0.0\n",
            "app.py": (
                "from flask import Flask\n\n"
                "app = Flask(__name__)\n\n\n"
                "@app.get('/')\n"
                "def index() -> str:\n"
                "    \"\"\"首页\"\"\"\n"
                "    return 'Hello from Flask'\n\n\n"
                "if __name__ == '__main__':\n"
                "    app.run(host='0.0.0.0', port=5000)\n"
            ),
        }

    if stack == "fastapi":
        return {
            "requirements.txt": "fastapi>=0.110.0\nuvicorn>=0.27.0\n",
            "main.py": (
                "from fastapi import FastAPI\n\n"
                "app = FastAPI(title='ZenFlux')\n\n\n"
                "@app.get('/')\n"
                "async def index() -> dict:\n"
                "    \"\"\"首页\"\"\"\n"
                "    return {'message': 'Hello from FastAPI'}\n"
            ),
        }

    if stack == "python":
        return {
            "requirements.txt": "",
            "main.py": (
                "def main() -> None:\n"
                "    \"\"\"主函数\"\"\"\n"
                "    print('Hello from Python')\n\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            ),
        }

    if stack == "vue":
        return {
            "package.json": (
                "{\n"
                f"  \"name\": \"{project_name}\",\n"
                "  \"private\": true,\n"
                "  \"type\": \"module\",\n"
                "  \"scripts\": {\n"
                "    \"dev\": \"vite --host 0.0.0.0 --port 5173 --strictPort\",\n"
                "    \"build\": \"vite build\",\n"
                "    \"preview\": \"vite preview --host 0.0.0.0 --port 5173 --strictPort\"\n"
                "  },\n"
                "  \"dependencies\": {\n"
                "    \"vue\": \"^3.4.0\"\n"
                "  },\n"
                "  \"devDependencies\": {\n"
                "    \"vite\": \"^5.0.0\",\n"
                "    \"@vitejs/plugin-vue\": \"^5.0.0\"\n"
                "  }\n"
                "}\n"
            ),
            "index.html": (
                "<!doctype html>\n"
                "<html lang=\"zh-CN\">\n"
                "  <head>\n"
                "    <meta charset=\"UTF-8\" />\n"
                "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />\n"
                f"    <title>{project_name}</title>\n"
                "  </head>\n"
                "  <body>\n"
                "    <div id=\"app\"></div>\n"
                "    <script type=\"module\" src=\"/src/main.js\"></script>\n"
                "  </body>\n"
                "</html>\n"
            ),
            "vite.config.js": (
                "import { defineConfig } from 'vite'\n"
                "import vue from '@vitejs/plugin-vue'\n\n"
                "export default defineConfig({\n"
                "  plugins: [vue()],\n"
                "  server: {\n"
                "    host: true,\n"
                "    allowedHosts: true,\n"
                "    port: 5173,\n"
                "    strictPort: true,\n"
                "  },\n"
                "})\n"
            ),
            "src/main.js": (
                "import { createApp } from 'vue'\n"
                "import App from './App.vue'\n\n"
                "createApp(App).mount('#app')\n"
            ),
            "src/App.vue": (
                "<template>\n"
                "  <main style=\"font-family: ui-sans-serif, system-ui; padding: 24px;\">\n"
                "    <h1>Vue 项目已初始化</h1>\n"
                "    <p>你可以开始 vibe coding 了。</p>\n"
                "  </main>\n"
                "</template>\n"
            ),
        }

    if stack == "react":
        return {
            "package.json": (
                "{\n"
                f"  \"name\": \"{project_name}\",\n"
                "  \"private\": true,\n"
                "  \"type\": \"module\",\n"
                "  \"scripts\": {\n"
                "    \"dev\": \"vite --host 0.0.0.0 --port 5173 --strictPort\",\n"
                "    \"build\": \"vite build\",\n"
                "    \"preview\": \"vite preview --host 0.0.0.0 --port 5173 --strictPort\"\n"
                "  },\n"
                "  \"dependencies\": {\n"
                "    \"react\": \"^18.2.0\",\n"
                "    \"react-dom\": \"^18.2.0\"\n"
                "  },\n"
                "  \"devDependencies\": {\n"
                "    \"vite\": \"^5.0.0\",\n"
                "    \"@vitejs/plugin-react\": \"^4.2.0\"\n"
                "  }\n"
                "}\n"
            ),
            "index.html": (
                "<!doctype html>\n"
                "<html lang=\"zh-CN\">\n"
                "  <head>\n"
                "    <meta charset=\"UTF-8\" />\n"
                "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />\n"
                f"    <title>{project_name}</title>\n"
                "  </head>\n"
                "  <body>\n"
                "    <div id=\"root\"></div>\n"
                "    <script type=\"module\" src=\"/src/main.jsx\"></script>\n"
                "  </body>\n"
                "</html>\n"
            ),
            "vite.config.js": (
                "import { defineConfig } from 'vite'\n"
                "import react from '@vitejs/plugin-react'\n\n"
                "export default defineConfig({\n"
                "  plugins: [react()],\n"
                "  server: {\n"
                "    host: true,\n"
                "    allowedHosts: true,\n"
                "    port: 5173,\n"
                "    strictPort: true,\n"
                "  },\n"
                "})\n"
            ),
            "src/main.jsx": (
                "import React from 'react'\n"
                "import ReactDOM from 'react-dom/client'\n"
                "import App from './App.jsx'\n\n"
                "ReactDOM.createRoot(document.getElementById('root')).render(\n"
                "  <React.StrictMode>\n"
                "    <App />\n"
                "  </React.StrictMode>\n"
                ")\n"
            ),
            "src/App.jsx": (
                "export default function App() {\n"
                "  return (\n"
                "    <main style={{ fontFamily: 'ui-sans-serif, system-ui', padding: 24 }}>\n"
                "      <h1>React 项目已初始化</h1>\n"
                "      <p>你可以开始 vibe coding 了。</p>\n"
                "    </main>\n"
                "  )\n"
                "}\n"
            ),
        }

    if stack == "nextjs":
        return {
            "package.json": (
                "{\n"
                f"  \"name\": \"{project_name}\",\n"
                "  \"private\": true,\n"
                "  \"scripts\": {\n"
                "    \"dev\": \"next dev -p 3000 -H 0.0.0.0\",\n"
                "    \"build\": \"next build\",\n"
                "    \"start\": \"next start -p 3000 -H 0.0.0.0\"\n"
                "  },\n"
                "  \"dependencies\": {\n"
                "    \"next\": \"^14.2.0\",\n"
                "    \"react\": \"^18.2.0\",\n"
                "    \"react-dom\": \"^18.2.0\"\n"
                "  }\n"
                "}\n"
            ),
            "pages/index.js": (
                "export default function Home() {\n"
                "  return (\n"
                "    <main style={{ fontFamily: 'ui-sans-serif, system-ui', padding: 24 }}>\n"
                "      <h1>Next.js 项目已初始化</h1>\n"
                "      <p>你可以开始 vibe coding 了。</p>\n"
                "    </main>\n"
                "  )\n"
                "}\n"
            ),
        }

    if stack == "nodejs":
        return {
            "package.json": (
                "{\n"
                f"  \"name\": \"{project_name}\",\n"
                "  \"private\": true,\n"
                "  \"type\": \"module\",\n"
                "  \"scripts\": {\n"
                "    \"start\": \"node server.js\"\n"
                "  },\n"
                "  \"dependencies\": {\n"
                "    \"express\": \"^4.19.2\"\n"
                "  }\n"
                "}\n"
            ),
            "server.js": (
                "import express from 'express'\n"
                "import { fileURLToPath } from 'url'\n"
                "import { dirname, join } from 'path'\n\n"
                "const __filename = fileURLToPath(import.meta.url)\n"
                "const __dirname = dirname(__filename)\n\n"
                "const app = express()\n"
                "const port = process.env.PORT ? Number(process.env.PORT) : 3000\n\n"
                "// 🔑 静态文件服务：提供 public 目录下的文件（HTML/CSS/JS/图片等）\n"
                "// 将静态资源放在 public/ 目录下，访问时直接使用文件名\n"
                "// 例如：public/index.html -> http://localhost:3000/index.html\n"
                "app.use(express.static(join(__dirname, 'public')))\n\n"
                "// 🔑 也支持根目录下的静态文件（如果你不想用 public 目录）\n"
                "// 优先级：public 目录 > 根目录\n"
                "app.use(express.static(__dirname))\n\n"
                "// API 路由示例\n"
                "app.get('/api/health', (_req, res) => {\n"
                "  res.json({ status: 'ok', message: 'Hello from Node.js' })\n"
                "})\n\n"
                "// 兜底路由：如果没有匹配的静态文件或 API，返回 index.html（适用于 SPA）\n"
                "app.get('*', (req, res) => {\n"
                "  const indexPath = join(__dirname, 'public', 'index.html')\n"
                "  const rootIndexPath = join(__dirname, 'index.html')\n"
                "  // 尝试 public/index.html，如果不存在则尝试根目录的 index.html\n"
                "  res.sendFile(indexPath, (err) => {\n"
                "    if (err) {\n"
                "      res.sendFile(rootIndexPath, (err2) => {\n"
                "        if (err2) {\n"
                "          res.status(404).send('Not Found - 请创建 index.html 或 public/index.html')\n"
                "        }\n"
                "      })\n"
                "    }\n"
                "  })\n"
                "})\n\n"
                "app.listen(port, '0.0.0.0', () => {\n"
                "  console.log(`🚀 Server running at http://localhost:${port}`)\n"
                "  console.log(`📁 Static files: ./public/ or ./`)\n"
                "})\n"
            ),
            # 创建 public 目录的占位文件
            "public/.gitkeep": "",
        }

    raise ValueError(f"不支持的 stack: {stack}")


async def ensure_sandbox(conversation_id: str, user_id: str = "default_user") -> bool:
    """确保沙盒存在"""
    service = get_sandbox_service()
    try:
        status = await service.get_sandbox_status(conversation_id)
        if status is None:
            await service.get_or_create_sandbox(conversation_id, user_id)
        elif status.status == "paused":
            await service.resume_sandbox(conversation_id)
        elif status.status not in ("running",):
            await service.get_or_create_sandbox(conversation_id, user_id)
        return True
    except SandboxNotFoundError:
        await service.get_or_create_sandbox(conversation_id, user_id)
        return True
    except Exception as e:
        logger.error(f"❌ 沙盒初始化失败: {e}", exc_info=True)
        raise


class SandboxWriteFile(BaseTool):
    """写文件到沙盒"""
    
    @property
    def name(self) -> str:
        return "sandbox_write_file"
    
    @property
    def description(self) -> str:
        return "在沙盒中写入文件。目录不存在会自动创建。"
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "conversation_id": {"type": "string", "description": "对话 ID"},
                "path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "文件内容"}
            },
            "required": ["conversation_id", "path", "content"]
        }
    
    async def execute(self, conversation_id: str, path: str, content: str, **kwargs) -> Dict[str, Any]:
        try:
            await ensure_sandbox(conversation_id, kwargs.get("user_id", "default_user"))
            service = get_sandbox_service()
            result = await service.write_file(conversation_id, path, content)
            return {"success": True, "path": path, "size": result["size"]}
        except Exception as e:
            return {"success": False, "error": str(e)}


class SandboxRunCommand(BaseTool):
    """在沙盒中执行命令"""
    
    @property
    def name(self) -> str:
        return "sandbox_run_command"
    
    @property
    def description(self) -> str:
        return """执行命令。常用：
- cat file.txt (读文件)
- ls -la (列目录)  
- pip install xxx
- npm install
- rm -rf path (删除)"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "conversation_id": {"type": "string", "description": "对话 ID"},
                "command": {"type": "string", "description": "命令"},
                "timeout": {"type": "integer", "description": "超时秒数", "default": 60}
            },
            "required": ["conversation_id", "command"]
        }
    
    async def execute(self, conversation_id: str, command: str, timeout: int = 60, **kwargs) -> Dict[str, Any]:
        try:
            await ensure_sandbox(conversation_id, kwargs.get("user_id", "default_user"))
            service = get_sandbox_service()
            return await service.run_command(conversation_id, command, timeout)
        except Exception as e:
            return {"success": False, "error": str(e)}


class SandboxCreateProject(BaseTool):
    """在沙盒中初始化项目骨架"""

    SUPPORTED_STACKS = [
        "streamlit",
        "gradio",
        "flask",
        "fastapi",
        "python",
        "vue",
        "react",
        "nextjs",
        "nodejs",
    ]

    @property
    def name(self) -> str:
        return "sandbox_create_project"

    @property
    def description(self) -> str:
        return (
            "在沙盒中初始化项目骨架（Initialize project）。\n"
            "项目将创建在 /home/user/<project_name>/ 下。\n"
            "注意：该工具只创建文件，不会自动安装依赖。\n\n"
            "【Node.js 静态文件说明】\n"
            "Node.js 项目默认配置了 express.static 中间件：\n"
            "- 静态文件放在 public/ 目录下（推荐）\n"
            "- 也支持直接放在项目根目录\n"
            "- 访问方式：http://host/index.html 或 http://host/game.js\n"
            "- 如果访问根路径 / 会自动寻找 index.html"
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "conversation_id": {"type": "string", "description": "对话 ID"},
                "project_name": {"type": "string", "description": "项目名称（目录名）"},
                "stack": {
                    "type": "string",
                    "description": "技术栈",
                    "enum": self.SUPPORTED_STACKS,
                },
                "overwrite": {"type": "boolean", "description": "是否覆盖写入（默认 false）"},
            },
            "required": ["conversation_id", "project_name", "stack"],
        }

    async def execute(
        self,
        conversation_id: str,
        project_name: str,
        stack: str,
        overwrite: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        try:
            err = _validate_project_name(project_name)
            if err:
                return {"success": False, "error": err}

            await ensure_sandbox(conversation_id, kwargs.get("user_id", "default_user"))
            service = get_sandbox_service()

            project_dir = _normalize_project_path(project_name)

            # 如果目录已存在，且不允许覆盖，则返回错误
            if await service.file_exists(conversation_id, project_dir) and not overwrite:
                return {
                    "success": False,
                    "error": f"项目目录已存在: {project_dir}（如需覆盖请传 overwrite=true）",
                }

            files = _get_project_scaffold(stack, project_name=project_name)
            written_files: List[str] = []

            for rel_path, content in files.items():
                full_path = f"{project_dir}/{rel_path}".replace("//", "/")
                await service.write_file(conversation_id, full_path, content)
                written_files.append(full_path)

            return {
                "success": True,
                "project_name": project_name,
                "project_path": project_dir,
                "stack": stack,
                "files_written": written_files,
            }
        except Exception as e:
            logger.error(f"❌ 创建项目失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}


class SandboxRunProject(BaseTool):
    """运行沙盒中的项目并返回预览 URL"""

    @property
    def name(self) -> str:
        return "sandbox_run_project"

    @property
    def description(self) -> str:
        return "运行项目并返回 E2B 预览 URL（推荐方式）。"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "conversation_id": {"type": "string", "description": "对话 ID"},
                "project_path": {"type": "string", "description": "项目路径（如 /home/user/my_app）"},
                "stack": {
                    "type": "string",
                    "description": "技术栈",
                    "enum": ["vue", "react", "nextjs", "nodejs", "streamlit", "gradio", "flask", "fastapi", "python"],
                },
            },
            "required": ["conversation_id", "project_path", "stack"],
        }

    async def execute(
        self,
        conversation_id: str,
        project_path: str,
        stack: str,
        **kwargs,
    ) -> Dict[str, Any]:
        try:
            await ensure_sandbox(conversation_id, kwargs.get("user_id", "default_user"))
            service = get_sandbox_service()

            normalized_path = _normalize_project_path(project_path)
            result = await service.run_project(conversation_id, normalized_path, stack)
            return {
                "success": result.success,
                "preview_url": result.preview_url,
                "message": result.message,
                "error": result.error,
            }
        except Exception as e:
            logger.error(f"❌ 运行项目失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}


# 工具注册（4 个核心工具）
SANDBOX_TOOLS = [
    SandboxWriteFile,
    SandboxRunCommand,
    SandboxCreateProject,
    SandboxRunProject,
]

def get_sandbox_tools() -> List[BaseTool]:
    return [t() for t in SANDBOX_TOOLS]
