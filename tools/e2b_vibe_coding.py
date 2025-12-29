"""
E2B Vibe Coding - 完整应用生成

严格按照 E2B Fragments 的实现：
https://github.com/e2b-dev/fragments

核心功能：
1. 生成完整应用（Streamlit/Gradio/Next.js）
2. 返回实时预览 URL
3. 支持热重载和迭代
4. 管理应用生命周期

参考：
- https://github.com/e2b-dev/fragments/tree/main/sandbox-templates
- https://github.com/e2b-dev/fragments/blob/main/lib/templates.json
"""

import os
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path

from logger import get_logger

logger = get_logger("e2b_vibe_coding")

# E2B SDK
try:
    from e2b_code_interpreter import Sandbox as CodeInterpreter
    E2B_AVAILABLE = True
except ImportError:
    logger.warning("⚠️ E2B SDK 未安装")
    E2B_AVAILABLE = False
    CodeInterpreter = None


class E2BVibeCoding:
    """
    E2B Vibe Coding - 完整应用生成器
    
    支持的技术栈（参考 Fragments）：
    - streamlit: 数据应用（端口 8501）
    - gradio: ML 模型界面（端口 7860）
    - nextjs: 全栈 Web 应用（端口 3000）
    - vue: 前端应用（端口 5173）
    """
    
    # 模板配置（参考 Fragments lib/templates.json）
    TEMPLATES = {
        "streamlit": {
            "name": "Streamlit App",
            "file": "app.py",
            "port": 8501,
            "start_cmd": "streamlit run app.py --server.port=8501 --server.address=0.0.0.0",
            "packages": ["streamlit", "pandas", "numpy", "matplotlib", "plotly"],
            "description": "数据可视化和分析应用"
        },
        "gradio": {
            "name": "Gradio App",
            "file": "app.py",
            "port": 7860,
            "start_cmd": "python app.py",
            "packages": ["gradio", "numpy", "pandas"],
            "description": "机器学习模型界面"
        },
        "nextjs": {
            "name": "Next.js App",
            "file": "pages/index.tsx",
            "port": 3000,
            "start_cmd": "npm run dev",
            "packages": [],
            "description": "全栈 Web 应用"
        },
        "vue": {
            "name": "Vue.js App", 
            "file": "src/App.vue",
            "port": 5173,
            "start_cmd": "npm run dev",
            "packages": [],
            "description": "前端应用"
        }
    }
    
    def __init__(self, memory, api_key: str = None, sandbox_timeout_hours: float = 1.0):
        """初始化 Vibe Coding
        
        Args:
            memory: WorkingMemory 实例
            api_key: E2B API Key
            sandbox_timeout_hours: 沙箱生命周期（小时）。免费版最长1小时，专业版最长24小时
        """
        if not E2B_AVAILABLE:
            raise RuntimeError("E2B SDK 未安装")
        
        self.memory = memory
        self.api_key = api_key or os.getenv("E2B_API_KEY")
        self.sandbox_timeout_seconds = int(sandbox_timeout_hours * 3600)
        
        if not self.api_key:
            raise ValueError("E2B_API_KEY 未设置")
        
        self._app_sandboxes: Dict[str, Any] = {}  # app_id -> sandbox
        self._heartbeat_tasks: Dict[str, Any] = {}  # app_id -> task（心跳任务）
        
        logger.info(f"✅ E2B Vibe Coding 已初始化（沙箱生命周期: {sandbox_timeout_hours}小时）")
    
    async def execute(self, action: str, **params) -> Dict[str, Any]:
        """
        工具执行入口（Claude调用此方法）
        
        路由到具体操作：
        - create: 创建应用
        - update: 更新应用
        - get_logs: 获取日志
        - terminate: 终止应用
        - list: 列出所有应用
        
        Args:
            action: 操作类型
            **params: 操作参数
        """
        if action == "create":
            return await self.create_app(
                stack=params.get("stack"),
                description=params.get("description", ""),
                code=params.get("code"),
                **{k: v for k, v in params.items() if k not in ["stack", "description", "code"]}
            )
        elif action == "update":
            return await self.update_app(
                app_id=params.get("app_id"),
                new_code=params.get("code")
            )
        elif action == "get_logs":
            return await self.get_app_logs(params.get("app_id"))
        elif action == "terminate":
            return await self.terminate_app(params.get("app_id"))
        elif action == "list":
            return await self.list_apps()
        else:
            return {
                "success": False,
                "error": f"未知操作: {action}"
            }
    
    async def create_app(
        self,
        stack: str,
        description: str,
        code: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        创建完整应用（Vibe Coding 核心）
        
        Args:
            stack: 技术栈（streamlit/gradio/nextjs/vue）
            description: 应用描述
            code: AI 生成的应用代码
        
        Returns:
            {
                "success": True,
                "app_id": "...",
                "preview_url": "https://xxx.e2b.dev",  ← 关键！
                "sandbox_id": "...",
                "port": 8501
            }
        """
        if stack not in self.TEMPLATES:
            return {
                "success": False,
                "error": f"不支持的技术栈: {stack}。支持: {list(self.TEMPLATES.keys())}"
            }
        
        template_config = self.TEMPLATES[stack]
        
        try:
            logger.info(f"🎨 创建 {template_config['name']} 应用...")
            
            # 1. 创建沙箱（指定生命周期）
            if self.api_key != os.getenv("E2B_API_KEY"):
                os.environ["E2B_API_KEY"] = self.api_key
            
            sandbox = await asyncio.to_thread(
                CodeInterpreter.create,
                timeout=self.sandbox_timeout_seconds  # 沙箱生命周期（秒）
            )
            
            await asyncio.sleep(5)  # 等待沙箱就绪
            
            logger.info(f"✅ 沙箱已创建: {sandbox.sandbox_id} (生命周期: {self.sandbox_timeout_seconds}秒)")
            
            # 2. 安装依赖包
            if template_config['packages']:
                await self._install_packages(sandbox, template_config['packages'])
            
            # 3. 写入应用代码
            file_path = f"/home/user/{template_config['file']}"
            
            # 确保目录存在
            file_dir = os.path.dirname(file_path)
            if file_dir != "/home/user":
                await asyncio.to_thread(
                    sandbox.commands.run,
                    f"mkdir -p {file_dir}"
                )
            
            await asyncio.to_thread(
                sandbox.files.write,
                file_path,
                code
            )
            
            logger.info(f"✅ 代码已写入: {file_path}")
            
            # 4. 启动应用（后台运行）
            start_cmd = template_config['start_cmd']
            
            # 使用 nohup 后台运行
            bg_cmd = f"nohup {start_cmd} > /tmp/app.log 2>&1 &"
            await asyncio.to_thread(
                sandbox.commands.run,
                bg_cmd,
                timeout=10
            )
            
            # 等待应用启动
            await asyncio.sleep(3)
            
            logger.info(f"✅ 应用已启动")
            
            # 5. 获取预览 URL（关键！）
            port = template_config['port']
            preview_url = f"https://{port}-{sandbox.sandbox_id}.e2b.app"
            
            logger.info(f"🔗 预览 URL: {preview_url}")
            
            # 6. 保存应用信息到 Memory
            app_id = f"app_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            app_info = {
                "app_id": app_id,
                "sandbox_id": sandbox.sandbox_id,
                "stack": stack,
                "preview_url": preview_url,
                "port": port,
                "file_path": file_path,
                "code": code,
                "description": description,
                "created_at": datetime.now().isoformat(),
                "status": "running"
            }
            
            self._app_sandboxes[app_id] = {
                "sandbox": sandbox,
                "info": app_info,
                "created_at": datetime.now()
            }
            
            # 保存到 WorkingMemory
            if not hasattr(self.memory, 'vibe_coding_apps'):
                self.memory.vibe_coding_apps = {}
            self.memory.vibe_coding_apps[app_id] = app_info
            
            # 启动心跳保活任务
            await self._start_heartbeat(app_id, sandbox)
            
            return {
                "success": True,
                "app_id": app_id,
                "preview_url": preview_url,
                "sandbox_id": sandbox.sandbox_id,
                "port": port,
                "expires_in": f"{self.sandbox_timeout_seconds}秒",
                "message": f"✅ {template_config['name']} 应用已创建！\n🔗 访问: {preview_url}\n⏱️  沙箱将在 {self.sandbox_timeout_seconds//60} 分钟后过期"
            }
        
        except Exception as e:
            logger.error(f"❌ 应用创建失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    async def update_app(
        self,
        app_id: str,
        new_code: str
    ) -> Dict[str, Any]:
        """
        更新应用代码（支持迭代）
        
        Args:
            app_id: 应用 ID
            new_code: 新的代码
        
        Returns:
            更新结果
        """
        if app_id not in self._app_sandboxes:
            return {
                "success": False,
                "error": f"应用不存在: {app_id}"
            }
        
        try:
            app_data = self._app_sandboxes[app_id]
            sandbox = app_data["sandbox"]
            app_info = app_data["info"]
            
            # 写入新代码
            file_path = app_info["file_path"]
            await asyncio.to_thread(
                sandbox.files.write,
                file_path,
                new_code
            )
            
            # 更新信息
            app_info["code"] = new_code
            app_info["updated_at"] = datetime.now().isoformat()
            app_info["version"] = app_info.get("version", 1) + 1
            
            # 对于 Streamlit/Gradio，会自动重载
            logger.info(f"✅ 应用已更新（v{app_info['version']}）")
            
            return {
                "success": True,
                "app_id": app_id,
                "preview_url": app_info["preview_url"],
                "version": app_info["version"],
                "message": f"✅ 应用已更新！刷新预览查看变化"
            }
        
        except Exception as e:
            logger.error(f"❌ 更新失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_app_logs(self, app_id: str) -> Dict[str, Any]:
        """获取应用日志"""
        if app_id not in self._app_sandboxes:
            return {"success": False, "error": "应用不存在"}
        
        try:
            sandbox = self._app_sandboxes[app_id]["sandbox"]
            
            # 读取日志文件
            logs = await asyncio.to_thread(
                sandbox.files.read,
                "/tmp/app.log"
            )
            
            return {
                "success": True,
                "logs": logs
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def terminate_app(self, app_id: str):
        """终止应用"""
        if app_id in self._app_sandboxes:
            # 停止心跳任务
            await self._stop_heartbeat(app_id)
            
            app_data = self._app_sandboxes[app_id]
            sandbox = app_data["sandbox"]
            
            # 终止沙箱（应用会自动停止）
            try:
                await asyncio.to_thread(sandbox.kill)
            except:
                pass
            
            del self._app_sandboxes[app_id]
            
            logger.info(f"🗑️ 应用已终止: {app_id}")
            
            return {"success": True}
        
        return {"success": False, "error": "应用不存在"}
    
    async def list_apps(self) -> List[Dict[str, Any]]:
        """列出所有应用"""
        apps = []
        for app_id, app_data in self._app_sandboxes.items():
            apps.append(app_data["info"])
        return apps
    
    async def _install_packages(self, sandbox, packages: List[str]):
        """安装 Python 包"""
        if not packages:
            return
        
        logger.info(f"📦 安装包: {', '.join(packages)}")
        
        cmd = f"pip install --quiet {' '.join(packages)}"
        await asyncio.to_thread(
            sandbox.commands.run,
            cmd,
            timeout=120
        )
        
        logger.info(f"✅ 包安装完成")
    
    async def _start_heartbeat(self, app_id: str, sandbox):
        """启动心跳保活任务
        
        每 30 秒执行一次简单命令，保持沙箱活跃
        """
        async def heartbeat_loop():
            heartbeat_interval = 30  # 30秒
            try:
                while app_id in self._app_sandboxes:
                    await asyncio.sleep(heartbeat_interval)
                    
                    # 执行简单的健康检查命令
                    try:
                        await asyncio.to_thread(
                            sandbox.commands.run,
                            "echo 'heartbeat'",
                            timeout=10
                        )
                        logger.debug(f"💓 心跳成功: {app_id}")
                    except Exception as e:
                        logger.warning(f"⚠️ 心跳失败: {app_id} - {e}")
                        # 沙箱可能已失效，停止心跳
                        break
            except asyncio.CancelledError:
                logger.debug(f"💓 心跳任务已取消: {app_id}")
        
        # 创建并启动心跳任务
        task = asyncio.create_task(heartbeat_loop())
        self._heartbeat_tasks[app_id] = task
        logger.info(f"💓 心跳保活已启动: {app_id}")
    
    async def _stop_heartbeat(self, app_id: str):
        """停止心跳任务"""
        if app_id in self._heartbeat_tasks:
            task = self._heartbeat_tasks[app_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self._heartbeat_tasks[app_id]
            logger.debug(f"💓 心跳已停止: {app_id}")
    
    async def check_sandbox_health(self, app_id: str) -> Dict[str, Any]:
        """检查沙箱健康状态
        
        Returns:
            {
                "success": True,
                "alive": True/False,
                "sandbox_id": "...",
                "uptime_seconds": 123
            }
        """
        if app_id not in self._app_sandboxes:
            return {
                "success": False,
                "error": "应用不存在"
            }
        
        try:
            app_data = self._app_sandboxes[app_id]
            sandbox = app_data["sandbox"]
            created_at = app_data["created_at"]
            
            # 执行健康检查
            result = await asyncio.to_thread(
                sandbox.commands.run,
                "echo 'health_check'",
                timeout=10
            )
            
            uptime = (datetime.now() - created_at).total_seconds()
            remaining = self.sandbox_timeout_seconds - uptime
            
            return {
                "success": True,
                "alive": True,
                "sandbox_id": sandbox.sandbox_id,
                "uptime_seconds": int(uptime),
                "remaining_seconds": max(0, int(remaining)),
                "message": f"✅ 沙箱运行正常，剩余 {int(remaining//60)} 分钟"
            }
        
        except Exception as e:
            logger.error(f"❌ 健康检查失败: {e}")
            return {
                "success": True,
                "alive": False,
                "error": str(e),
                "message": "⚠️ 沙箱可能已失效"
            }


def create_e2b_vibe_coding(memory, api_key: str = None):
    """创建 Vibe Coding 实例"""
    return E2BVibeCoding(memory=memory, api_key=api_key)

