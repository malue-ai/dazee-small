"""
E2B Python Sandbox Tool - V2.0

职责：
1. 创建和管理E2B沙箱
2. 执行Python代码（支持流式输出）
3. 自动安装第三方包
4. 文件系统同步（workspace <-> sandbox）
5. 产物自动保存到 conversation workspace

设计原则：
✅ 基于 conversation_id 隔离 workspace
✅ 产物自动下载到 workspace/{conv_id}/workspace/
✅ Agent 使用相对路径，不感知真实路径
✅ 支持沙箱复用（同一 conversation 多次调用）
✅ 流式输出（集成EventManager）

参考文档：
- https://e2b.dev/docs/sandbox
- https://e2b.dev/docs/quickstart/install-custom-packages
- https://e2b.dev/docs/code-interpreting/streaming
"""

import os
import re
import time
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path

from logger import get_logger

logger = get_logger("e2b_sandbox")

# 说明：E2B SDK 的 list/query 依赖这些类型
try:
    from e2b.sandbox.sandbox_api import SandboxQuery
    from e2b.api.client.models.sandbox_state import SandboxState
except Exception:
    SandboxQuery = None
    SandboxState = None

# E2B SDK
try:
    from e2b_code_interpreter import Sandbox as CodeInterpreter
    E2B_AVAILABLE = True
    logger.debug("使用 E2B Code Interpreter SDK")
except ImportError:
    try:
        # 降级到普通 e2b SDK
        from e2b import Sandbox as CodeInterpreter
        E2B_AVAILABLE = True
        logger.debug("使用 E2B Standard SDK")
    except ImportError:
        logger.warning("⚠️ E2B SDK 未安装，请运行: pip install e2b e2b-code-interpreter")
        E2B_AVAILABLE = False
        CodeInterpreter = None


class E2BPythonSandbox:
    """
    E2B Python沙箱工具
    
    核心功能：
    - execute_code(): 执行Python代码（支持流式输出）
    - install_packages(): 安装第三方包
    - upload_file(): 上传文件到沙箱
    - download_file(): 从沙箱下载文件到 workspace
    - terminate(): 终止沙箱
    
    重要变更（V2.0）：
    - 使用 WorkspaceManager 管理文件
    - 产物保存到 workspace/conversations/{conv_id}/workspace/
    - Agent 使用相对路径
    """
    
    def __init__(
        self, 
        api_key: str = None,
        event_manager = None,
        workspace_base_dir: str = "./workspace"
    ):
        """
        初始化E2B沙箱工具
        
        Args:
            api_key: E2B API密钥（默认从环境变量读取）
            event_manager: EventManager实例（用于流式输出）
            workspace_base_dir: workspace 根目录
        """
        if not E2B_AVAILABLE:
            raise RuntimeError("E2B SDK 未安装")
        
        self.api_key = api_key or os.getenv("E2B_API_KEY")
        self.event_manager = event_manager
        self.workspace_base_dir = Path(workspace_base_dir)
        
        if not self.api_key:
            raise ValueError("E2B_API_KEY 未设置")
        
        # 导入 WorkspaceManager
        from core.workspace_manager import get_workspace_manager
        self.workspace_manager = get_workspace_manager(str(self.workspace_base_dir))
        
        # 内部状态管理（按 conversation_id 隔离）
        self._conversation_data: Dict[str, Dict[str, Any]] = {}  # conv_id -> session_data
        self._execution_history: Dict[str, List[Dict[str, Any]]] = {}  # conv_id -> history
        
        # 沙箱对象缓存（按 conversation_id）
        self._sandbox_cache: Dict[str, Any] = {}  # conv_id -> sandbox
        
        logger.info("✅ E2BPythonSandbox 已初始化（V2.0，支持 conversation 隔离）")
    
    def _get_session_data(self, conversation_id: str) -> Dict[str, Any]:
        """获取 conversation 的会话数据"""
        if conversation_id not in self._conversation_data:
            self._conversation_data[conversation_id] = {
                "sandbox_id": None,
                "template": None,
                "installed_packages": [],
                "status": "inactive",
                "created_at": None
            }
        return self._conversation_data[conversation_id]
    
    def _get_execution_history(self, conversation_id: str) -> List[Dict[str, Any]]:
        """获取 conversation 的执行历史"""
        if conversation_id not in self._execution_history:
            self._execution_history[conversation_id] = []
        return self._execution_history[conversation_id]
    
    async def execute(self, session_id: str = None, **params) -> Dict[str, Any]:
        """
        工具执行入口（Claude调用此方法）
        
        参数（来自input_schema）：
            code: Python代码
            conversation_id: 对话ID（必须）
            template: 沙箱模板（可选）
            enable_stream: 是否启用流式输出
            auto_install: 是否自动安装包
            timeout: 超时时间
            return_files: 要返回的文件列表（沙箱中的绝对路径）
            save_to: 产物保存的相对路径（相对于 workspace，默认直接保存到根目录）
        """
        code = params.get("code")
        template = params.get("template", "base")
        user_id = params.get("user_id")
        conversation_id = params.get("conversation_id")
        enable_stream = params.get("enable_stream", True)
        auto_install = params.get("auto_install", True)
        timeout = params.get("timeout", 300)
        return_files = params.get("return_files", [])
        save_to = params.get("save_to", "")  # 相对于 workspace 的保存路径
        
        if not code:
            return {
                "success": False,
                "error": "代码不能为空"
            }
        
        if not conversation_id:
            return {
                "success": False,
                "error": "conversation_id 不能为空"
            }
        
        start_time = time.time()
        session_data = self._get_session_data(conversation_id)
        
        try:
            # 1. 获取或创建沙箱
            sandbox = await self._get_or_create_sandbox(
                template=template,
                session_id=session_id,
                user_id=user_id,
                conversation_id=conversation_id,
            )
            
            # 2. 自动安装依赖包（如果启用）
            if auto_install:
                await self._auto_install_packages(sandbox, code, conversation_id)
            
            # 3. 执行代码
            if enable_stream and self.event_manager and session_id:
                # 流式执行
                result = await self._execute_code_stream(
                    sandbox=sandbox,
                    code=code,
                    session_id=session_id,
                    timeout=timeout
                )
            else:
                # 非流式执行
                result = await self._execute_code(
                    sandbox=sandbox,
                    code=code,
                    timeout=timeout
                )
            
            # 4. 下载返回文件到 workspace（如果指定）
            files_data = {}
            if return_files:
                files_data = await self._download_files_to_workspace(
                    sandbox=sandbox,
                    conversation_id=conversation_id,
                    remote_paths=return_files,
                    save_to=save_to
                )
            
            # 5. 记录执行历史
            execution_time = time.time() - start_time
            execution_result = {
                "success": result.get("success", False),
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
                "error": result.get("error"),
                "files": files_data,
                "execution_time": execution_time
            }
            
            # 添加到执行历史（按 conversation 隔离）
            history = self._get_execution_history(conversation_id)
            history.append({
                "code": code,
                "result": execution_result,
                "timestamp": time.time()
            })
            
            return execution_result
            
        except Exception as e:
            logger.error(f"❌ E2B执行失败: {e}", exc_info=True)
            error_result = {
                "success": False,
                "error": str(e),
                "stdout": "",
                "stderr": str(e),
                "execution_time": time.time() - start_time
            }
            
            # 添加到执行历史
            history = self._get_execution_history(conversation_id)
            history.append({
                "code": code,
                "result": error_result,
                "timestamp": time.time()
            })
            
            return error_result
    
    async def _get_or_create_sandbox(
        self,
        template: str = "base",
        session_id: str | None = None,
        user_id: str | None = None,
        conversation_id: str | None = None,
    ):
        """
        获取或创建沙箱（基于 conversation_id 隔离）

        说明：
        - 每个 conversation 有独立的 sandbox
        - 可以通过 metadata 找回仍存活的沙盒

        Args:
            template: 沙箱模板
            session_id: 会话 ID
            user_id: 用户 ID
            conversation_id: 对话 ID（必须）

        Returns:
            E2B Sandbox 实例
        """
        if not conversation_id:
            raise ValueError("conversation_id 不能为空")
        
        session_data = self._get_session_data(conversation_id)

        # 构造 metadata（E2B 要求 Dict[str, str]）
        metadata: Dict[str, str] = {"zenflux_tool": "e2b_python_sandbox"}
        if session_id:
            metadata["session_id"] = str(session_id)
        if user_id:
            metadata["user_id"] = str(user_id)
        metadata["conversation_id"] = str(conversation_id)

        # 1. 检查缓存中是否有该 conversation 的沙箱
        if conversation_id in self._sandbox_cache:
            sandbox = self._sandbox_cache[conversation_id]
            try:
                # 验证沙箱是否还活着
                test_result = await asyncio.to_thread(
                    sandbox.commands.run,
                    "echo 'ping'",
                    timeout=10
                )
                if test_result.exit_code == 0:
                    logger.info(f"♻️ 复用缓存沙箱: {sandbox.sandbox_id} (conversation: {conversation_id})")
                    return sandbox
                else:
                    raise Exception("沙箱无响应")
            except Exception as e:
                logger.warning(f"⚠️ 缓存沙箱已失效: {e}")
                del self._sandbox_cache[conversation_id]
                session_data["sandbox_id"] = None
                session_data["status"] = "inactive"
        
        # 2. 检查内部状态中是否有 sandbox_id（可能缓存丢失但沙箱仍存活）
        if session_data.get("sandbox_id") and session_data.get("status") == "active":
            sandbox_id = session_data["sandbox_id"]
            try:
                if self.api_key and self.api_key != os.getenv("E2B_API_KEY"):
                    os.environ["E2B_API_KEY"] = self.api_key
                
                sandbox = await asyncio.to_thread(
                    getattr(CodeInterpreter, "_cls_connect"),
                    sandbox_id
                )
                
                # 验证连接
                test_result = await asyncio.to_thread(
                    sandbox.commands.run,
                    "echo 'connected'",
                    timeout=10
                )
                if test_result.exit_code == 0:
                    self._sandbox_cache[conversation_id] = sandbox
                    logger.info(f"🔗 重新连接沙箱: {sandbox_id}")
                    return sandbox
            except Exception as e:
                logger.warning(f"⚠️ 沙箱连接失败: {e}")
                session_data["sandbox_id"] = None
                session_data["status"] = "inactive"
                session_data["installed_packages"] = []
        
        # 3. 尝试通过 metadata 找回仍存活的沙箱
        if SandboxQuery and SandboxState:
            try:
                query = SandboxQuery(
                    metadata={"conversation_id": conversation_id}, 
                    state=[SandboxState.RUNNING, SandboxState.PAUSED]
                )
                paginator = CodeInterpreter.list(query=query, limit=1)
                items = paginator.next_items()
                if items:
                    found = items[0]
                    found_id = getattr(found, "sandbox_id", None) or getattr(found, "id", None)
                    if found_id:
                        logger.info(f"🔎 通过 metadata 找到沙箱: {found_id}")
                        sandbox = await asyncio.to_thread(
                            getattr(CodeInterpreter, "_cls_connect"),
                            found_id
                        )
                        session_data.update({
                            "sandbox_id": sandbox.sandbox_id,
                            "template": template,
                            "status": "active",
                            "created_at": datetime.now().isoformat()
                        })
                        self._sandbox_cache[conversation_id] = sandbox
                        return sandbox
            except Exception as e:
                logger.warning(f"⚠️ metadata 找回沙箱失败: {e}")
        
        # 4. 创建新沙箱
        logger.info(f"🆕 创建新沙箱 (conversation: {conversation_id}, template={template})...")
        
        try:
            if self.api_key and self.api_key != os.getenv("E2B_API_KEY"):
                os.environ["E2B_API_KEY"] = self.api_key
            
            sandbox = await asyncio.to_thread(
                CodeInterpreter.create,
                timeout=120,
                metadata=metadata,
            )
            
            logger.info("⏳ 等待沙箱就绪...")
            await asyncio.sleep(5)
            
            # 验证沙箱状态
            try:
                test_result = await asyncio.to_thread(
                    sandbox.run_code,
                    "print('sandbox ready')",
                    timeout=30
                )
                logger.info("✅ 沙箱验证成功")
            except Exception as e:
                logger.warning(f"⚠️ 沙箱验证警告: {e}")
            
        except Exception as e:
            logger.error(f"❌ 沙箱创建失败: {e}")
            raise RuntimeError(f"E2B沙箱创建失败: {e}")
        
        # 5. 保存状态
        session_data.update({
            "sandbox_id": sandbox.sandbox_id,
            "template": template,
            "status": "active",
            "created_at": datetime.now().isoformat()
        })
        self._sandbox_cache[conversation_id] = sandbox
        
        # 6. 自动同步 workspace 文件到沙箱
        await self._auto_sync_workspace(sandbox, conversation_id)
        
        logger.info(f"✅ 新沙箱已创建: {sandbox.sandbox_id}")
        return sandbox
    
    async def _execute_code_stream(
        self,
        sandbox,
        code: str,
        session_id: str,
        timeout: int = 300
    ) -> Dict[str, Any]:
        """
        流式执行代码（E2B + EventManager 集成）
        
        工作原理：
        1. E2B 通过 on_stdout/on_stderr 实时回调
        2. 回调函数发送 SSE 事件到前端
        3. 前端实时显示输出
        
        参考：https://e2b.dev/docs/code-interpreting/streaming
        """
        stdout_lines = []
        stderr_lines = []
        
        # 定义回调函数
        def on_stdout(data):
            """stdout 回调 - 发送到前端"""
            line = data.line
            stdout_lines.append(line)
            
            # 发送 SSE 事件（同步回调中使用异步事件需要特殊处理）
            if self.event_manager:
                asyncio.create_task(
                    self.event_manager.system.emit_custom(
                        session_id=session_id,
                        event_type="code_output",
                        event_data={
                            "stream": "stdout",
                            "text": line,
                            "timestamp": data.timestamp
                        }
                    )
                )
        
        def on_stderr(data):
            """stderr 回调 - 发送到前端"""
            line = data.line
            stderr_lines.append(line)
            
            if self.event_manager:
                asyncio.create_task(
                    self.event_manager.system.emit_custom(
                        session_id=session_id,
                        event_type="code_output",
                        event_data={
                            "stream": "stderr",
                            "text": line,
                            "error": True,
                            "timestamp": data.timestamp
                        }
                    )
                )
        
        try:
            # 使用 E2B 的流式 API
            execution = await asyncio.to_thread(
                sandbox.run_code,
                code,
                on_stdout=on_stdout,
                on_stderr=on_stderr,
                timeout=timeout
            )
            
            return {
                "success": execution.error is None,
                "stdout": "".join(stdout_lines),
                "stderr": "".join(stderr_lines),
                "error": execution.error.value if execution.error else None
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "stdout": "".join(stdout_lines),
                "stderr": "".join(stderr_lines)
            }
    
    async def _execute_code(
        self,
        sandbox,
        code: str,
        timeout: int = 300
    ) -> Dict[str, Any]:
        """
        非流式执行代码
        """
        try:
            execution = await asyncio.to_thread(
                sandbox.run_code,
                code,
                timeout=timeout
            )
            
            # 收集所有输出
            if hasattr(execution.logs, 'stdout'):
                stdout_logs = execution.logs.stdout
                stdout = "\n".join([
                    log.line if hasattr(log, 'line') else str(log) 
                    for log in stdout_logs
                ]) if stdout_logs else ""
                
                stderr_logs = execution.logs.stderr
                stderr = "\n".join([
                    log.line if hasattr(log, 'line') else str(log)
                    for log in stderr_logs
                ]) if stderr_logs else ""
            else:
                # 降级：直接使用字符串
                stdout = str(execution.logs) if hasattr(execution, 'logs') else ""
                stderr = ""
            
            return {
                "success": execution.error is None,
                "stdout": stdout,
                "stderr": stderr,
                "error": execution.error.value if execution.error else None
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "stdout": "",
                "stderr": str(e)
            }
    
    def _extract_imports_from_code(self, code: str) -> List[str]:
        """
        从代码中提取 import 语句
        
        示例：
        import pandas as pd
        from sklearn.linear_model import LinearRegression
        
        → ["pandas", "scikit-learn"]  # 注意：sklearn -> scikit-learn
        """
        imports = set()
        
        # Python 内置模块（不需要安装）
        builtin_modules = {
            "os", "sys", "re", "json", "time", "datetime", "math", "random",
            "collections", "itertools", "functools", "typing", "pathlib",
            "io", "pickle", "copy", "shutil", "tempfile", "glob", "fnmatch",
            "subprocess", "threading", "multiprocessing", "asyncio", "concurrent",
            "socket", "ssl", "http", "urllib", "email", "html", "xml",
            "logging", "warnings", "traceback", "inspect", "dis", "gc",
            "abc", "contextlib", "dataclasses", "enum", "types",
            "hashlib", "hmac", "secrets", "base64", "binascii",
            "struct", "codecs", "unicodedata", "string", "textwrap",
            "difflib", "csv", "configparser", "argparse", "getopt",
            "unittest", "doctest", "pdb", "profile", "timeit",
            "platform", "ctypes", "uuid", "weakref", "operator",
            "heapq", "bisect", "array", "queue", "decimal", "fractions",
            "statistics", "cmath", "numbers", "builtins", "__future__",
            "zipfile", "tarfile", "gzip", "bz2", "lzma", "zlib"
        }
        
        # 包名映射（import名 → pip包名）
        package_mapping = {
            "cv2": "opencv-python",
            "PIL": "Pillow",
            "sklearn": "scikit-learn",
            "bs4": "beautifulsoup4"
        }
        
        # 匹配 import xxx
        pattern1 = r'^import\s+([\w\.]+)'
        # 匹配 from xxx import yyy
        pattern2 = r'^from\s+([\w\.]+)\s+import'
        
        for line in code.split('\n'):
            line = line.strip()
            
            match1 = re.match(pattern1, line)
            if match1:
                pkg = match1.group(1).split('.')[0]
                # 跳过内置模块
                if pkg in builtin_modules:
                    continue
                # 应用映射
                pkg = package_mapping.get(pkg, pkg)
                imports.add(pkg)
            
            match2 = re.match(pattern2, line)
            if match2:
                pkg = match2.group(1).split('.')[0]
                # 跳过内置模块
                if pkg in builtin_modules:
                    continue
                pkg = package_mapping.get(pkg, pkg)
                imports.add(pkg)
        
        return list(imports)
    
    async def _auto_install_packages(self, sandbox, code: str, conversation_id: str):
        """
        自动检测并安装缺失的包
        
        工作流：
        1. 从代码提取 import
        2. 检查哪些包未安装
        3. 批量安装
        """
        # 提取 imports
        imports = self._extract_imports_from_code(code)
        
        if not imports:
            return
        
        # 检查已安装的包（从 conversation 状态）
        session_data = self._get_session_data(conversation_id)
        installed = set(session_data.get("installed_packages", []))
        
        # 需要安装的包
        to_install = [pkg for pkg in imports if pkg not in installed]
        
        if not to_install:
            return
        
        logger.info(f"📦 自动安装包: {', '.join(to_install)}")
        
        try:
            # 批量安装
            install_cmd = f"pip install --quiet {' '.join(to_install)}"
            result = await asyncio.to_thread(
                sandbox.commands.run,
                install_cmd,
                timeout=120
            )
            
            if result.exit_code == 0:
                # 更新状态
                current_packages = session_data.get("installed_packages", [])
                current_packages.extend(to_install)
                session_data["installed_packages"] = current_packages
                logger.info(f"✅ 包安装成功: {', '.join(to_install)}")
            else:
                logger.warning(f"⚠️ 包安装失败: {result.stderr}")
        
        except Exception as e:
            logger.error(f"❌ 包安装异常: {e}")
    
    async def _auto_sync_workspace(self, sandbox, conversation_id: str):
        """
        自动同步 workspace 文件到沙箱
        
        使用场景：
        - 沙箱启动时
        - 把 conversation 的 workspace 文件同步到沙箱
        
        Args:
            sandbox: E2B Sandbox 实例
            conversation_id: 对话 ID
        """
        workspace_root = self.workspace_manager.get_workspace_root(conversation_id)
        
        if not workspace_root.exists():
            return
        
        synced_files = []
        for file_path in workspace_root.rglob("*"):
            if file_path.is_file():
                relative_path = file_path.relative_to(workspace_root)
                remote_path = f"/home/user/workspace/{relative_path}"
                
                try:
                    # 读取文件内容
                    content = file_path.read_bytes()
                    
                    # 确保远程目录存在
                    remote_dir = str(Path(remote_path).parent)
                    if remote_dir != "/home/user/workspace":
                        await asyncio.to_thread(
                            sandbox.commands.run,
                            f"mkdir -p {remote_dir}",
                            timeout=10
                        )
                    
                    # 上传到沙箱
                    await asyncio.to_thread(
                        sandbox.files.write,
                        remote_path,
                        content
                    )
                    
                    synced_files.append(str(relative_path))
                    logger.debug(f"📤 已上传: {relative_path}")
                
                except Exception as e:
                    logger.warning(f"⚠️ 文件上传失败 {file_path}: {e}")
        
        if synced_files:
            logger.info(f"📁 Workspace 同步完成: {len(synced_files)} 个文件")
    
    async def _download_files_to_workspace(
        self,
        sandbox,
        conversation_id: str,
        remote_paths: List[str],
        save_to: str = ""
    ) -> Dict[str, Any]:
        """
        从沙箱下载文件到 workspace
        
        Args:
            sandbox: E2B Sandbox 实例
            conversation_id: 对话 ID
            remote_paths: 沙箱中的文件路径列表
            save_to: 保存到 workspace 的相对路径（默认为根目录）
        
        返回格式：
        {
            "/home/user/sales.xlsx": {
                "local_path": "sales.xlsx",  # 相对于 workspace 的路径
                "size": 1024
            }
        }
        """
        files_data = {}
        
        for remote_path in remote_paths:
            try:
                # 从沙箱读取
                content = await asyncio.to_thread(
                    sandbox.files.read,
                    remote_path
                )
                
                # 确定本地路径（相对于 workspace）
                filename = Path(remote_path).name
                if save_to:
                    local_relative_path = f"{save_to}/{filename}"
                else:
                    local_relative_path = filename
                
                # 使用 WorkspaceManager 写入文件
                result = self.workspace_manager.write_file(
                    conversation_id, 
                    local_relative_path, 
                    content
                )
                
                files_data[remote_path] = {
                    "local_path": local_relative_path,
                    "size": result["size"],
                    "downloaded_at": datetime.now().isoformat()
                }
                
                logger.info(f"📥 文件已下载到 workspace: {remote_path} → {local_relative_path}")
            
            except Exception as e:
                logger.error(f"❌ 文件下载失败 {remote_path}: {e}")
                files_data[remote_path] = {
                    "error": str(e)
                }
        
        return files_data
    
    async def terminate_sandbox(self, conversation_id: str = None):
        """
        终止沙箱（清理资源）
        
        Args:
            conversation_id: 对话 ID（如果不指定，清理所有沙箱）
        
        调用时机：
        - 用户主动要求
        - conversation 结束
        - 沙箱闲置超时
        """
        if conversation_id:
            # 终止特定 conversation 的沙箱
            session_data = self._get_session_data(conversation_id)
            
            if not session_data.get("sandbox_id") or session_data.get("status") != "active":
                return {"success": True, "message": "没有活跃的沙箱"}
            
            sandbox_id = session_data["sandbox_id"]
            
            if conversation_id in self._sandbox_cache:
                sandbox = self._sandbox_cache[conversation_id]
                try:
                    await asyncio.to_thread(sandbox.close)
                except Exception as e:
                    logger.warning(f"⚠️ 沙箱关闭警告: {e}")
                del self._sandbox_cache[conversation_id]
            
            session_data.update({
                "sandbox_id": None,
                "template": None,
                "status": "inactive"
            })
            
            logger.info(f"🗑️ 沙箱已终止: {sandbox_id} (conversation: {conversation_id})")
            return {
                "success": True,
                "message": f"沙箱 {sandbox_id} 已终止"
            }
        else:
            # 终止所有沙箱
            terminated = []
            for conv_id, sandbox in list(self._sandbox_cache.items()):
                try:
                    await asyncio.to_thread(sandbox.close)
                    terminated.append(conv_id)
                except Exception as e:
                    logger.warning(f"⚠️ 沙箱关闭警告: {e}")
            
            self._sandbox_cache.clear()
            self._conversation_data.clear()
            
            logger.info(f"🗑️ 已终止所有沙箱: {terminated}")
            return {
                "success": True,
                "message": f"已终止 {len(terminated)} 个沙箱"
            }


# ==================== 工具注册辅助函数 ====================

def create_e2b_sandbox_tool(
    api_key: str = None,
    event_manager = None,
    workspace_base_dir: str = "./workspace"
):
    """
    创建E2B沙箱工具实例（供Agent使用）
    
    Args:
        api_key: E2B API密钥
        event_manager: EventManager实例
        workspace_base_dir: workspace 根目录
    
    Returns:
        E2BPythonSandbox实例
    """
    return E2BPythonSandbox(
        api_key=api_key,
        event_manager=event_manager,
        workspace_base_dir=workspace_base_dir
    )

