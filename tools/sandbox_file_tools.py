"""
沙盒文件工具 - 供 Agent 使用

提供 Agent 直接操作 E2B 沙盒文件系统的能力：
- sandbox_list_dir: 列出目录内容
- sandbox_read_file: 读取文件内容
- sandbox_write_file: 写入文件
- sandbox_delete_file: 删除文件
- sandbox_run_command: 执行命令
- sandbox_file_exists: 检查文件是否存在
"""

import os
from typing import Optional, Dict, Any, List

from logger import get_logger
from tools.base import BaseTool
from services.sandbox_service import (
    get_sandbox_service,
    SandboxServiceError,
    SandboxNotFoundError
)

logger = get_logger("sandbox_file_tools")


class SandboxListDir(BaseTool):
    """
    列出沙盒目录内容
    
    用于查看沙盒文件系统中指定目录的文件和子目录列表。
    """
    
    @property
    def name(self) -> str:
        return "sandbox_list_dir"
    
    @property
    def description(self) -> str:
        return """列出沙盒目录内容。

用途：查看沙盒中指定目录下的文件和文件夹。

参数：
- conversation_id: 对话 ID
- path: 目录路径（默认 /home/user）

返回：
- files: 文件列表，包含 name、path、type（file/directory）、size

示例：
```json
{
    "conversation_id": "conv_123",
    "path": "/home/user/my_project"
}
```
"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "对话 ID"
                },
                "path": {
                    "type": "string",
                    "description": "目录路径（默认 /home/user）",
                    "default": "/home/user"
                }
            },
            "required": ["conversation_id"]
        }
    
    async def execute(
        self,
        conversation_id: str = None,
        path: str = "/home/user",
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行列目录
        
        Args:
            conversation_id: 对话 ID
            path: 目录路径
            
        Returns:
            文件列表
        """
        try:
            service = get_sandbox_service()
            files = await service.list_files(conversation_id, path)
            
            return {
                "success": True,
                "path": path,
                "files": [
                    {
                        "name": f.name,
                        "path": f.path,
                        "type": f.type,
                        "size": f.size
                    }
                    for f in files
                ]
            }
        
        except SandboxNotFoundError as e:
            return {
                "success": False,
                "error": f"沙盒不存在: {e}"
            }
        except SandboxServiceError as e:
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"列目录失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"操作失败: {e}"
            }


class SandboxReadFile(BaseTool):
    """
    读取沙盒文件内容
    
    用于读取沙盒中文件的内容。
    """
    
    @property
    def name(self) -> str:
        return "sandbox_read_file"
    
    @property
    def description(self) -> str:
        return """读取沙盒文件内容。

用途：读取沙盒中指定文件的内容。

参数：
- conversation_id: 对话 ID
- path: 文件路径（完整路径，如 /home/user/app.py）

返回：
- content: 文件内容（文本）

示例：
```json
{
    "conversation_id": "conv_123",
    "path": "/home/user/my_project/app.py"
}
```

注意：
- 二进制文件可能无法正确读取
- 大文件可能会被截断
"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "对话 ID"
                },
                "path": {
                    "type": "string",
                    "description": "文件路径（完整路径）"
                }
            },
            "required": ["conversation_id", "path"]
        }
    
    async def execute(
        self,
        conversation_id: str = None,
        path: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行读取文件
        
        Args:
            conversation_id: 对话 ID
            path: 文件路径
            
        Returns:
            文件内容
        """
        try:
            service = get_sandbox_service()
            content = await service.read_file(conversation_id, path)
            
            # 限制返回内容大小
            max_size = 100000  # 100KB
            if len(content) > max_size:
                content = content[:max_size] + f"\n\n[... 内容已截断，共 {len(content)} 字节 ...]"
            
            return {
                "success": True,
                "path": path,
                "content": content,
                "size": len(content)
            }
        
        except SandboxNotFoundError as e:
            return {
                "success": False,
                "error": f"沙盒不存在: {e}"
            }
        except SandboxServiceError as e:
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"读取文件失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"操作失败: {e}"
            }


class SandboxWriteFile(BaseTool):
    """
    写入沙盒文件
    
    用于在沙盒中创建或更新文件。
    """
    
    @property
    def name(self) -> str:
        return "sandbox_write_file"
    
    @property
    def description(self) -> str:
        return """写入沙盒文件。

用途：在沙盒中创建或更新文件内容。

参数：
- conversation_id: 对话 ID
- path: 文件路径（完整路径，如 /home/user/app.py）
- content: 文件内容

返回：
- success: 是否成功
- path: 文件路径
- size: 写入字节数

示例：
```json
{
    "conversation_id": "conv_123",
    "path": "/home/user/my_project/app.py",
    "content": "import streamlit as st\\n\\nst.title('Hello World')"
}
```

注意：
- 如果目录不存在会自动创建
- 如果文件已存在会被覆盖
"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "对话 ID"
                },
                "path": {
                    "type": "string",
                    "description": "文件路径（完整路径）"
                },
                "content": {
                    "type": "string",
                    "description": "文件内容"
                }
            },
            "required": ["conversation_id", "path", "content"]
        }
    
    async def execute(
        self,
        conversation_id: str = None,
        path: str = None,
        content: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行写入文件
        
        Args:
            conversation_id: 对话 ID
            path: 文件路径
            content: 文件内容
            
        Returns:
            写入结果
        """
        try:
            service = get_sandbox_service()
            result = await service.write_file(conversation_id, path, content)
            
            logger.info(f"✅ Agent 写入文件: {path}")
            
            return {
                "success": True,
                "path": path,
                "size": result["size"]
            }
        
        except SandboxNotFoundError as e:
            return {
                "success": False,
                "error": f"沙盒不存在: {e}"
            }
        except SandboxServiceError as e:
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"写入文件失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"操作失败: {e}"
            }


class SandboxDeleteFile(BaseTool):
    """
    删除沙盒文件
    
    用于删除沙盒中的文件或目录。
    """
    
    @property
    def name(self) -> str:
        return "sandbox_delete_file"
    
    @property
    def description(self) -> str:
        return """删除沙盒文件或目录。

用途：删除沙盒中指定的文件或目录。

参数：
- conversation_id: 对话 ID
- path: 文件或目录路径

返回：
- success: 是否成功

示例：
```json
{
    "conversation_id": "conv_123",
    "path": "/home/user/my_project/temp.txt"
}
```

注意：
- 删除目录会递归删除所有内容
- 操作不可恢复
"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "对话 ID"
                },
                "path": {
                    "type": "string",
                    "description": "文件或目录路径"
                }
            },
            "required": ["conversation_id", "path"]
        }
    
    async def execute(
        self,
        conversation_id: str = None,
        path: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行删除文件
        
        Args:
            conversation_id: 对话 ID
            path: 文件路径
            
        Returns:
            删除结果
        """
        try:
            service = get_sandbox_service()
            success = await service.delete_file(conversation_id, path)
            
            if success:
                logger.info(f"🗑️ Agent 删除文件: {path}")
            
            return {
                "success": success,
                "path": path
            }
        
        except SandboxNotFoundError as e:
            return {
                "success": False,
                "error": f"沙盒不存在: {e}"
            }
        except SandboxServiceError as e:
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"删除文件失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"操作失败: {e}"
            }


class SandboxRunCommand(BaseTool):
    """
    在沙盒中执行命令
    
    用于在沙盒中执行 shell 命令。
    """
    
    @property
    def name(self) -> str:
        return "sandbox_run_command"
    
    @property
    def description(self) -> str:
        return """在沙盒中执行命令。

用途：在沙盒中执行 shell 命令，如安装依赖、运行脚本等。

参数：
- conversation_id: 对话 ID
- command: 要执行的命令
- timeout: 超时时间（秒，默认 60）

返回：
- success: 是否成功（exit_code == 0）
- exit_code: 退出码
- stdout: 标准输出
- stderr: 标准错误

示例：
```json
{
    "conversation_id": "conv_123",
    "command": "pip install pandas numpy",
    "timeout": 120
}
```

常用命令：
- `pip install <package>` - 安装 Python 包
- `pip install -r requirements.txt` - 安装依赖
- `python script.py` - 运行 Python 脚本
- `npm install` - 安装 Node.js 依赖
- `ls -la` - 列出目录
- `cat file.txt` - 查看文件
"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "对话 ID"
                },
                "command": {
                    "type": "string",
                    "description": "要执行的命令"
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时时间（秒，默认 60）",
                    "default": 60
                }
            },
            "required": ["conversation_id", "command"]
        }
    
    async def execute(
        self,
        conversation_id: str = None,
        command: str = None,
        timeout: int = 60,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行命令
        
        Args:
            conversation_id: 对话 ID
            command: 命令
            timeout: 超时时间
            
        Returns:
            执行结果
        """
        try:
            service = get_sandbox_service()
            result = await service.run_command(conversation_id, command, timeout)
            
            logger.info(f"🖥️ Agent 执行命令: {command[:50]}...")
            
            return result
        
        except SandboxNotFoundError as e:
            return {
                "success": False,
                "error": f"沙盒不存在: {e}"
            }
        except SandboxServiceError as e:
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"执行命令失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"操作失败: {e}"
            }


class SandboxFileExists(BaseTool):
    """
    检查沙盒文件是否存在
    
    用于检查沙盒中指定路径的文件或目录是否存在。
    """
    
    @property
    def name(self) -> str:
        return "sandbox_file_exists"
    
    @property
    def description(self) -> str:
        return """检查沙盒文件是否存在。

用途：检查沙盒中指定路径是否存在文件或目录。

参数：
- conversation_id: 对话 ID
- path: 文件或目录路径

返回：
- exists: 是否存在

示例：
```json
{
    "conversation_id": "conv_123",
    "path": "/home/user/my_project/app.py"
}
```
"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "对话 ID"
                },
                "path": {
                    "type": "string",
                    "description": "文件或目录路径"
                }
            },
            "required": ["conversation_id", "path"]
        }
    
    async def execute(
        self,
        conversation_id: str = None,
        path: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        检查文件是否存在
        
        Args:
            conversation_id: 对话 ID
            path: 文件路径
            
        Returns:
            检查结果
        """
        try:
            service = get_sandbox_service()
            exists = await service.file_exists(conversation_id, path)
            
            return {
                "success": True,
                "path": path,
                "exists": exists
            }
        
        except SandboxNotFoundError as e:
            return {
                "success": False,
                "error": f"沙盒不存在: {e}"
            }
        except SandboxServiceError as e:
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"检查文件失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"操作失败: {e}"
            }


class SandboxCreateProject(BaseTool):
    """
    在沙盒中创建项目
    
    快速创建指定类型的项目框架。
    """
    
    # 项目模板
    TEMPLATES = {
        "streamlit": {
            "app.py": '''"""
Streamlit 应用

运行: streamlit run app.py
"""
import streamlit as st

st.set_page_config(
    page_title="My Streamlit App",
    page_icon="🚀",
    layout="wide"
)

st.title("🚀 My Streamlit App")
st.write("欢迎使用 Streamlit！")

# 示例：输入框
name = st.text_input("请输入你的名字")
if name:
    st.write(f"你好，{name}！")

# 示例：按钮
if st.button("点击我"):
    st.balloons()
    st.success("你点击了按钮！")
''',
            "requirements.txt": "streamlit>=1.28.0\n"
        },
        "gradio": {
            "app.py": '''"""
Gradio 应用

运行: python app.py
"""
import gradio as gr

def greet(name, intensity):
    return "Hello, " + name + "!" * int(intensity)

demo = gr.Interface(
    fn=greet,
    inputs=["text", gr.Slider(value=1, minimum=1, maximum=10, step=1)],
    outputs=["text"],
    title="My Gradio App",
    description="一个简单的 Gradio 应用"
)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
''',
            "requirements.txt": "gradio>=4.0.0\n"
        },
        "flask": {
            "app.py": '''"""
Flask 应用

运行: python app.py
"""
from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({
        "message": "欢迎使用 Flask！",
        "status": "running"
    })

@app.route("/api/hello/<name>")
def hello(name):
    return jsonify({
        "message": f"你好，{name}！"
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
''',
            "requirements.txt": "flask>=3.0.0\n"
        },
        "fastapi": {
            "main.py": '''"""
FastAPI 应用

运行: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(
    title="My FastAPI App",
    description="一个简单的 FastAPI 应用",
    version="1.0.0"
)

class Item(BaseModel):
    name: str
    description: str = None

@app.get("/")
async def root():
    return {"message": "欢迎使用 FastAPI！"}

@app.get("/api/hello/{name}")
async def hello(name: str):
    return {"message": f"你好，{name}！"}

@app.post("/api/items")
async def create_item(item: Item):
    return {"item": item, "status": "created"}
''',
            "requirements.txt": "fastapi>=0.104.0\nuvicorn>=0.24.0\n"
        },
        "python": {
            "main.py": '''"""
Python 项目

运行: python main.py
"""

def main():
    print("Hello, World!")
    print("这是一个 Python 项目")

if __name__ == "__main__":
    main()
''',
            "requirements.txt": "# 在这里添加依赖\n"
        }
    }
    
    @property
    def name(self) -> str:
        return "sandbox_create_project"
    
    @property
    def description(self) -> str:
        return """在沙盒中创建项目。

用途：快速创建指定类型的项目框架，包含基础文件结构。

参数：
- conversation_id: 对话 ID
- project_name: 项目名称
- stack: 技术栈类型（streamlit/gradio/flask/fastapi/python）

返回：
- success: 是否成功
- project_path: 项目路径
- files_created: 创建的文件列表

示例：
```json
{
    "conversation_id": "conv_123",
    "project_name": "my_app",
    "stack": "streamlit"
}
```

支持的技术栈：
- streamlit: Streamlit Web 应用
- gradio: Gradio ML 界面
- flask: Flask Web 服务
- fastapi: FastAPI REST API
- python: 普通 Python 项目
"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "对话 ID"
                },
                "project_name": {
                    "type": "string",
                    "description": "项目名称"
                },
                "stack": {
                    "type": "string",
                    "enum": ["streamlit", "gradio", "flask", "fastapi", "python"],
                    "description": "技术栈类型",
                    "default": "python"
                }
            },
            "required": ["conversation_id", "project_name"]
        }
    
    async def execute(
        self,
        conversation_id: str = None,
        project_name: str = None,
        stack: str = "python",
        **kwargs
    ) -> Dict[str, Any]:
        """
        创建项目
        
        Args:
            conversation_id: 对话 ID
            project_name: 项目名称
            stack: 技术栈
            
        Returns:
            创建结果
        """
        try:
            if stack not in self.TEMPLATES:
                return {
                    "success": False,
                    "error": f"不支持的技术栈: {stack}。支持: {', '.join(self.TEMPLATES.keys())}"
                }
            
            service = get_sandbox_service()
            project_path = f"/home/user/{project_name}"
            
            # 创建项目目录
            await service.run_command(conversation_id, f"mkdir -p {project_path}")
            
            # 写入模板文件
            template = self.TEMPLATES[stack]
            files_created = []
            
            for filename, content in template.items():
                file_path = f"{project_path}/{filename}"
                await service.write_file(conversation_id, file_path, content)
                files_created.append(filename)
            
            # 创建 README
            readme_content = f"""# {project_name}

技术栈：{stack}

## 运行方式

"""
            if stack == "streamlit":
                readme_content += "```bash\nstreamlit run app.py\n```"
            elif stack == "gradio":
                readme_content += "```bash\npython app.py\n```"
            elif stack == "flask":
                readme_content += "```bash\npython app.py\n```"
            elif stack == "fastapi":
                readme_content += "```bash\nuvicorn main:app --host 0.0.0.0 --port 8000\n```"
            else:
                readme_content += "```bash\npython main.py\n```"
            
            await service.write_file(conversation_id, f"{project_path}/README.md", readme_content)
            files_created.append("README.md")
            
            logger.info(f"📁 Agent 创建项目: {project_name} ({stack})")
            
            return {
                "success": True,
                "project_path": project_path,
                "stack": stack,
                "files_created": files_created
            }
        
        except SandboxNotFoundError as e:
            return {
                "success": False,
                "error": f"沙盒不存在: {e}"
            }
        except SandboxServiceError as e:
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"创建项目失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"操作失败: {e}"
            }


class SandboxRunProject(BaseTool):
    """
    运行沙盒中的项目
    
    启动项目并返回预览 URL。
    """
    
    @property
    def name(self) -> str:
        return "sandbox_run_project"
    
    @property
    def description(self) -> str:
        return """运行沙盒中的项目。

用途：启动沙盒中的项目，获取预览 URL。

参数：
- conversation_id: 对话 ID
- project_path: 项目路径（相对于 /home/user）
- stack: 技术栈类型（streamlit/gradio/flask/fastapi/python）

返回：
- success: 是否成功
- preview_url: 预览 URL
- message: 状态消息

示例：
```json
{
    "conversation_id": "conv_123",
    "project_path": "my_app",
    "stack": "streamlit"
}
```
"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "对话 ID"
                },
                "project_path": {
                    "type": "string",
                    "description": "项目路径（相对于 /home/user）"
                },
                "stack": {
                    "type": "string",
                    "enum": ["streamlit", "gradio", "flask", "fastapi", "python"],
                    "description": "技术栈类型"
                }
            },
            "required": ["conversation_id", "project_path", "stack"]
        }
    
    async def execute(
        self,
        conversation_id: str = None,
        project_path: str = None,
        stack: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        运行项目
        
        Args:
            conversation_id: 对话 ID
            project_path: 项目路径
            stack: 技术栈
            
        Returns:
            运行结果
        """
        try:
            service = get_sandbox_service()
            result = await service.run_project(conversation_id, project_path, stack)
            
            if result.success:
                logger.info(f"🚀 Agent 启动项目: {project_path} -> {result.preview_url}")
            
            return {
                "success": result.success,
                "preview_url": result.preview_url,
                "message": result.message,
                "error": result.error
            }
        
        except SandboxNotFoundError as e:
            return {
                "success": False,
                "error": f"沙盒不存在: {e}"
            }
        except SandboxServiceError as e:
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"运行项目失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"操作失败: {e}"
            }


# ==================== 工具注册 ====================

# 所有沙盒文件工具
SANDBOX_FILE_TOOLS = [
    SandboxListDir,
    SandboxReadFile,
    SandboxWriteFile,
    SandboxDeleteFile,
    SandboxRunCommand,
    SandboxFileExists,
    SandboxCreateProject,
    SandboxRunProject,
]


def get_sandbox_file_tools() -> List[BaseTool]:
    """
    获取所有沙盒文件工具实例
    
    Returns:
        工具实例列表
    """
    return [tool() for tool in SANDBOX_FILE_TOOLS]
