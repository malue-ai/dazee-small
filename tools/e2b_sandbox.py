"""
E2B Python Sandbox Tool - V1.0

职责：
1. 创建和管理E2B沙箱
2. 执行Python代码（支持流式输出）
3. 自动安装第三方包
4. 文件系统同步（workspace <-> sandbox）
5. 与WorkingMemory集成（会话管理）

设计原则（V3.7架构）：
✅ 状态存储在Memory,而不是工具内部
✅ 支持沙箱复用（同一session多次调用）
✅ 自动清理资源（session结束时）
✅ 独立可测试（不依赖Agent）
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
    - download_file(): 从沙箱下载文件
    - terminate(): 终止沙箱
    """
    
    def __init__(
        self, 
        memory: "WorkingMemory",
        api_key: str = None,
        event_manager = None,
        workspace_dir: str = None
    ):
        """
        初始化E2B沙箱工具
        
        Args:
            memory: WorkingMemory实例（用于会话管理）
            api_key: E2B API密钥（默认从环境变量读取）
            event_manager: EventManager实例（用于流式输出）
            workspace_dir: 工作目录（用于文件同步）
        """
        if not E2B_AVAILABLE:
            raise RuntimeError("E2B SDK 未安装")
        
        self.memory = memory
        self.api_key = api_key or os.getenv("E2B_API_KEY")
        self.event_manager = event_manager
        self.workspace_dir = Path(workspace_dir) if workspace_dir else Path.cwd() / "workspace"
        
        if not self.api_key:
            raise ValueError("E2B_API_KEY 未设置")
        
        # 创建workspace目录结构
        (self.workspace_dir / "inputs").mkdir(parents=True, exist_ok=True)
        (self.workspace_dir / "outputs").mkdir(parents=True, exist_ok=True)
        (self.workspace_dir / "temp").mkdir(parents=True, exist_ok=True)
        
        # 沙箱对象缓存（用于复用）
        self._sandbox_cache: Dict[str, Any] = {}
        
        # 模板ID缓存
        self._current_template: str = "base"
        
        logger.info("✅ E2BPythonSandbox 已初始化")
    
    async def execute(self, session_id: str = None, **params) -> Dict[str, Any]:
        """
        工具执行入口（Claude调用此方法）
        
        参数（来自input_schema）：
            code: Python代码
            template: 沙箱模板（可选）
            enable_stream: 是否启用流式输出
            auto_install: 是否自动安装包
            timeout: 超时时间
            background: 是否后台运行
            return_files: 要返回的文件列表
        """
        code = params.get("code")
        template = params.get("template", "base")
        enable_stream = params.get("enable_stream", True)
        auto_install = params.get("auto_install", True)
        timeout = params.get("timeout", 300)
        background = params.get("background", False)
        return_files = params.get("return_files", [])
        
        if not code:
            return {
                "success": False,
                "error": "代码不能为空"
            }
        
        start_time = time.time()
        
        try:
            # 1. 获取或创建沙箱
            sandbox = await self._get_or_create_sandbox(template)
            
            # 2. 自动安装依赖包（如果启用）
            if auto_install:
                await self._auto_install_packages(sandbox, code)
            
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
            
            # 4. 下载返回文件（如果指定）
            files_data = {}
            if return_files:
                files_data = await self._download_files(sandbox, return_files)
            
            # 5. 更新Memory
            execution_time = time.time() - start_time
            execution_result = {
                "success": result.get("success", False),
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
                "error": result.get("error"),
                "files": files_data,
                "execution_time": execution_time
            }
            
            self.memory.add_e2b_execution(
                code=code,
                result=execution_result,
                execution_time=execution_time
            )
            
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
            
            self.memory.add_e2b_execution(
                code=code,
                result=error_result,
                execution_time=error_result["execution_time"]
            )
            
            return error_result
    
    async def _get_or_create_sandbox(self, template: str = "base"):
        """
        获取或创建沙箱（核心：Memory-First）
        
        逻辑：
        1. 检查Memory中是否有活跃会话
        2. 如果有，尝试复用（连接到现有沙箱）
        3. 如果没有或连接失败，创建新沙箱
        4. 更新Memory
        """
        # 1. 检查Memory中的会话
        if self.memory.has_e2b_session():
            session = self.memory.get_e2b_session()
            sandbox_id = session.sandbox_id
            
            # 尝试从缓存获取
            if sandbox_id in self._sandbox_cache:
                logger.info(f"♻️ 复用缓存沙箱: {sandbox_id}")
                return self._sandbox_cache[sandbox_id]
            
            # 尝试连接到现有沙箱
            try:
                if self.api_key and self.api_key != os.getenv("E2B_API_KEY"):
                    os.environ["E2B_API_KEY"] = self.api_key
                
                sandbox = await asyncio.to_thread(
                    CodeInterpreter.connect,
                    sandbox_id
                )
                self._sandbox_cache[sandbox_id] = sandbox
                logger.info(f"🔗 重新连接沙箱: {sandbox_id}")
                return sandbox
            except Exception as e:
                logger.warning(f"⚠️ 沙箱连接失败，创建新沙箱: {e}")
                self.memory.clear_e2b_session()
        
        # 2. 创建新沙箱
        logger.info(f"🆕 创建新沙箱 (template={template})...")
        
        try:
            # 使用环境变量或参数传递API key
            if self.api_key and self.api_key != os.getenv("E2B_API_KEY"):
                os.environ["E2B_API_KEY"] = self.api_key
            
            sandbox = await asyncio.to_thread(
                CodeInterpreter.create,
                timeout=120  # 设置120秒超时
            )
            
            # 等待沙箱就绪
            logger.info("⏳ 等待沙箱就绪...")
            await asyncio.sleep(5)  # 等待5秒让沙箱完全启动
            
            # 验证沙箱状态
            try:
                # 运行简单测试验证沙箱可用
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
        
        # 3. 保存到Memory
        from core.memory import E2BSandboxSession
        session = E2BSandboxSession(
            sandbox_id=sandbox.sandbox_id,
            created_at=datetime.now(),
            template=template,
            status="active"
        )
        self.memory.set_e2b_session(session)
        self._sandbox_cache[sandbox.sandbox_id] = sandbox
        self._current_template = template
        
        # 4. 自动同步workspace文件
        await self._auto_sync_workspace(sandbox)
        
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
                # 应用映射
                pkg = package_mapping.get(pkg, pkg)
                imports.add(pkg)
            
            match2 = re.match(pattern2, line)
            if match2:
                pkg = match2.group(1).split('.')[0]
                pkg = package_mapping.get(pkg, pkg)
                imports.add(pkg)
        
        return list(imports)
    
    async def _auto_install_packages(self, sandbox, code: str):
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
        
        # 检查已安装的包
        session = self.memory.get_e2b_session()
        installed = set(session.installed_packages) if session else set()
        
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
                # 更新 Memory
                if session:
                    session.installed_packages.extend(to_install)
                    self.memory.update_e2b_session(
                        installed_packages=session.installed_packages
                    )
                logger.info(f"✅ 包安装成功: {', '.join(to_install)}")
            else:
                logger.warning(f"⚠️ 包安装失败: {result.stderr}")
        
        except Exception as e:
            logger.error(f"❌ 包安装异常: {e}")
    
    async def _auto_sync_workspace(self, sandbox):
        """
        自动同步 workspace/inputs/ 到沙箱
        
        使用场景：
        - 沙箱启动时
        - 用户上传新文件时
        """
        inputs_dir = self.workspace_dir / "inputs"
        
        if not inputs_dir.exists():
            return
        
        synced_files = []
        for file_path in inputs_dir.glob("**/*"):
            if file_path.is_file():
                relative_path = file_path.relative_to(inputs_dir)
                remote_path = f"/home/user/input_data/{relative_path}"
                
                try:
                    # 读取文件内容
                    with open(file_path, 'rb') as f:
                        content = f.read()
                    
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
            logger.info(f"📁 同步完成: {len(synced_files)} 个文件")
    
    async def _download_files(
        self,
        sandbox,
        file_paths: List[str]
    ) -> Dict[str, Any]:
        """
        从沙箱下载文件
        
        返回格式：
        {
            "/home/user/output_data/result.csv": {
                "local_path": "workspace/outputs/result.csv",
                "size": 1024,
                "content_type": "text/csv"
            }
        }
        """
        files_data = {}
        outputs_dir = self.workspace_dir / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        
        for remote_path in file_paths:
            try:
                # 从沙箱读取
                content = await asyncio.to_thread(
                    sandbox.files.read,
                    remote_path
                )
                
                # 确定本地路径
                filename = Path(remote_path).name
                local_path = outputs_dir / filename
                
                # 保存到本地
                if isinstance(content, bytes):
                    with open(local_path, 'wb') as f:
                        f.write(content)
                else:
                    with open(local_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                
                files_data[remote_path] = {
                    "local_path": str(local_path.relative_to(self.workspace_dir)),
                    "size": len(content) if isinstance(content, bytes) else len(content.encode()),
                    "downloaded_at": datetime.now().isoformat()
                }
                
                logger.info(f"📥 文件已下载: {remote_path} → {local_path}")
            
            except Exception as e:
                logger.error(f"❌ 文件下载失败 {remote_path}: {e}")
                files_data[remote_path] = {
                    "error": str(e)
                }
        
        return files_data
    
    async def terminate_sandbox(self):
        """
        终止沙箱（清理资源）
        
        调用时机：
        - 用户主动要求
        - session结束
        - 沙箱闲置超时
        """
        if not self.memory.has_e2b_session():
            return {"success": True, "message": "没有活跃的沙箱"}
        
        session = self.memory.get_e2b_session()
        sandbox_id = session.sandbox_id
        
        # 终止沙箱
        if sandbox_id in self._sandbox_cache:
            sandbox = self._sandbox_cache[sandbox_id]
            try:
                await asyncio.to_thread(sandbox.close)
            except Exception as e:
                logger.warning(f"⚠️ 沙箱关闭警告: {e}")
            del self._sandbox_cache[sandbox_id]
        
        # 清除Memory
        self.memory.clear_e2b_session()
        
        logger.info(f"🗑️ 沙箱已终止: {sandbox_id}")
        return {
            "success": True,
            "message": f"沙箱 {sandbox_id} 已终止"
        }
    
    def set_template(self, template_id: str):
        """设置当前使用的模板"""
        self._current_template = template_id
        logger.debug(f"📋 模板已设置: {template_id}")


# ==================== 工具注册辅助函数 ====================

def create_e2b_sandbox_tool(
    memory: "WorkingMemory",
    api_key: str = None,
    event_manager = None,
    workspace_dir: str = None
):
    """
    创建E2B沙箱工具实例（供Agent使用）
    
    Args:
        memory: WorkingMemory实例
        api_key: E2B API密钥
        event_manager: EventManager实例
        workspace_dir: 工作目录
    
    Returns:
        E2BPythonSandbox实例
    """
    return E2BPythonSandbox(
        memory=memory,
        api_key=api_key,
        event_manager=event_manager,
        workspace_dir=workspace_dir
    )

