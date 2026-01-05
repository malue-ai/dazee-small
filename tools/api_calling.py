"""
API Calling Tool - 通用 API 调用工具

这是一个通用的 HTTP API 调用工具,可以调用任何 REST API。
配合 Skills 中的 API 文档使用,无需为每个 API 单独编写工具。

使用场景:
1. LLM 从 Skill 文档中了解 API 的使用方法
2. 使用本工具发起实际的 HTTP 请求
3. 处理响应并返回结果

示例:
- slidespeak-generator skill 提供了 SlideSpeak API 的完整文档
- LLM 读取文档后,使用 api_calling 工具调用 API
- 无需 slidespeak_render 这样的专门工具
"""

import os
import aiohttp
import asyncio
import json
from typing import Dict, Any, Optional, Literal
from pathlib import Path


class APICallingTool:
    """
    通用 API 调用工具
    
    支持任意 HTTP API 调用,包括:
    - RESTful API
    - 异步轮询
    - 文件上传/下载
    - 认证处理
    """
    
    def __init__(self):
        """初始化 API 调用工具"""
        self.timeout = 600  # 默认超时 10 分钟
        self.max_polls = 150  # 异步任务最多轮询 150 次
        self.poll_interval = 2  # 轮询间隔 2 秒
    
    @property
    def name(self) -> str:
        return "api_calling"
    
    @property
    def description(self) -> str:
        return """通用 API 调用工具,支持任意 HTTP API 请求。

支持的功能:
1. HTTP 请求 (GET/POST/PUT/DELETE/PATCH)
2. 自定义 Headers 和认证
3. JSON/FormData/Multipart 请求体
4. 异步任务轮询
5. 文件下载

使用方式:
- 配合 Skills 文档使用
- Skills 提供 API 的完整说明和 schema
- 本工具负责实际的 HTTP 调用

参数:
- url: API 端点 URL (必需)
- method: HTTP 方法 (默认 POST)
- headers: 请求头字典
- body: 请求体 (JSON 或其他格式)
- auth: 认证配置
- poll_for_result: 是否轮询异步任务结果
- download_url: 响应中的下载链接字段名
- save_dir: 文件保存目录
"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "API 端点 URL (完整的 HTTP(S) 地址)"
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                    "description": "HTTP 方法 (默认 POST)"
                },
                "headers": {
                    "type": "object",
                    "description": "请求头字典,例如 {'Content-Type': 'application/json', 'X-API-Key': 'xxx'}"
                },
                "body": {
                    "type": "object",
                    "description": "请求体 (将自动转为 JSON)"
                },
                "auth": {
                    "type": "object",
                    "description": "认证配置",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["api_key", "bearer", "basic"],
                            "description": "认证类型"
                        },
                        "credentials": {
                            "type": "object",
                            "description": "认证凭据"
                        }
                    }
                },
                "poll_for_result": {
                    "type": "boolean",
                    "description": "是否轮询异步任务结果 (默认 false)"
                },
                "poll_config": {
                    "type": "object",
                    "description": "轮询配置",
                    "properties": {
                        "status_url_field": {
                            "type": "string",
                            "description": "响应中任务ID或状态URL的字段名"
                        },
                        "status_url_template": {
                            "type": "string",
                            "description": "状态查询 URL 模板,例如 'https://api.example.com/task_status/{task_id}'"
                        },
                        "success_status": {
                            "type": "string",
                            "description": "成功状态值 (默认 'SUCCESS')"
                        },
                        "failed_status": {
                            "type": "string",
                            "description": "失败状态值 (默认 'FAILED')"
                        }
                    }
                },
                "download_url_field": {
                    "type": "string",
                    "description": "响应中下载链接的字段名 (如果需要下载文件)"
                },
                "save_dir": {
                    "type": "string",
                    "description": "文件保存目录 (默认 ./workspace/outputs)"
                }
            },
            "required": ["url"]
        }
    
    async def execute(
        self,
        url: str,
        method: str = "POST",
        headers: Optional[Dict[str, str]] = None,
        body: Optional[Dict[str, Any]] = None,
        auth: Optional[Dict[str, Any]] = None,
        poll_for_result: bool = False,
        poll_config: Optional[Dict[str, Any]] = None,
        download_url_field: Optional[str] = None,
        save_dir: Optional[str] = None,
        conversation_id: Optional[str] = None,
        **kwargs  # 接收其他注入的上下文
    ) -> Dict[str, Any]:
        """
        执行 API 调用
        
        Args:
            url: API 端点 URL
            method: HTTP 方法
            headers: 请求头
            body: 请求体
            auth: 认证配置
            poll_for_result: 是否轮询结果
            poll_config: 轮询配置
            download_url_field: 下载链接字段名
            save_dir: 保存目录（可选）
            conversation_id: 对话ID（用于计算 workspace 路径）
            
        Returns:
            API 响应结果
        """
        # 计算正确的保存路径
        if not save_dir and conversation_id:
            from core.workspace_manager import get_workspace_manager
            workspace_manager = get_workspace_manager()
            workspace_root = workspace_manager.get_workspace_root(conversation_id)
            save_dir = str(workspace_root / "outputs")
        elif not save_dir:
            save_dir = "./workspace/outputs"
        try:
            # 1. 准备请求头
            request_headers = headers or {}
            
            # 处理认证
            if auth:
                request_headers = self._apply_auth(request_headers, auth)
            
            # 2. 发送请求
            print(f"📡 调用 API: {method} {url}")
            if body:
                print(f"📤 请求体: {json.dumps(body, ensure_ascii=False)[:200]}...")
            
            async with aiohttp.ClientSession() as session:
                response_data = await self._send_request(
                    session, url, method, request_headers, body
                )
                
                if not response_data:
                    return {
                        "success": False,
                        "error": "API 请求失败"
                    }
                
                print(f"✅ API 响应成功")
                
                # 3. 异步轮询
                if poll_for_result and poll_config:
                    print(f"⏳ 开始轮询任务状态...")
                    response_data = await self._poll_for_result(
                        session, response_data, poll_config, request_headers
                    )
                    
                    if not response_data:
                        return {
                            "success": False,
                            "error": "任务轮询失败或超时"
                        }
                
                # 4. 下载文件
                if download_url_field and download_url_field in response_data:
                    download_url = response_data[download_url_field]
                    print(f"📥 下载文件: {download_url}")
                    
                    local_path = await self._download_file(
                        session, download_url, save_dir
                    )
                    response_data["local_path"] = str(local_path)
                
                return {
                    "success": True,
                    "data": response_data
                }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def _apply_auth(self, headers: Dict[str, str], auth: Dict[str, Any]) -> Dict[str, str]:
        """应用认证配置到请求头"""
        auth_type = auth.get("type", "api_key")
        credentials = auth.get("credentials", {})
        
        if auth_type == "api_key":
            # API Key 认证
            header_name = credentials.get("header_name", "X-API-Key")
            api_key = credentials.get("api_key") or os.getenv(credentials.get("env_var", ""))
            if api_key:
                headers[header_name] = api_key
        
        elif auth_type == "bearer":
            # Bearer Token
            token = credentials.get("token") or os.getenv(credentials.get("env_var", ""))
            if token:
                headers["Authorization"] = f"Bearer {token}"
        
        elif auth_type == "basic":
            # Basic Auth
            import base64
            username = credentials.get("username")
            password = credentials.get("password")
            if username and password:
                auth_str = base64.b64encode(f"{username}:{password}".encode()).decode()
                headers["Authorization"] = f"Basic {auth_str}"
        
        return headers
    
    async def _send_request(
        self,
        session: aiohttp.ClientSession,
        url: str,
        method: str,
        headers: Dict[str, str],
        body: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """发送 HTTP 请求"""
        try:
            # 设置默认 Content-Type
            if body and "Content-Type" not in headers:
                headers["Content-Type"] = "application/json"
            
            # 发送请求
            async with session.request(
                method=method,
                url=url,
                headers=headers,
                json=body if body else None,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status in [200, 201]:
                    return await response.json()
                else:
                    error_text = await response.text()
                    print(f"❌ API 错误 (HTTP {response.status}): {error_text}")
                    return None
        
        except Exception as e:
            print(f"❌ 请求失败: {e}")
            return None
    
    async def _poll_for_result(
        self,
        session: aiohttp.ClientSession,
        initial_response: Dict[str, Any],
        poll_config: Dict[str, Any],
        headers: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """轮询异步任务结果"""
        # 提取任务 ID 或状态 URL
        task_id_field = poll_config.get("status_url_field", "task_id")
        task_id = initial_response.get(task_id_field)
        
        if not task_id:
            print(f"⚠️ 未找到任务 ID (字段: {task_id_field})")
            return initial_response
        
        # 构建状态查询 URL
        status_url_template = poll_config.get("status_url_template", "")
        status_url = status_url_template.format(task_id=task_id)
        
        # 轮询
        success_status = poll_config.get("success_status", "SUCCESS")
        failed_status = poll_config.get("failed_status", "FAILED")
        
        for i in range(self.max_polls):
            try:
                async with session.get(
                    status_url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        status = result.get("task_status") or result.get("status")
                        
                        if status == success_status:
                            print(f"✅ 任务完成!")
                            return result.get("task_result") or result.get("task_info") or result
                        elif status == failed_status:
                            print(f"❌ 任务失败")
                            return None
                        
                        # 继续等待
                        if i % 10 == 0:
                            print(f"⏳ 处理中... ({i * self.poll_interval}秒)")
                
                await asyncio.sleep(self.poll_interval)
            
            except Exception as e:
                print(f"⚠️ 轮询错误: {e}")
                await asyncio.sleep(self.poll_interval)
        
        print(f"❌ 轮询超时 ({self.max_polls * self.poll_interval} 秒)")
        return None
    
    async def _download_file(
        self,
        session: aiohttp.ClientSession,
        url: str,
        save_dir: str
    ) -> Path:
        """下载文件"""
        save_path = Path(save_dir)
        save_path.mkdir(parents=True, exist_ok=True)
        
        # 生成文件名
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 从 URL 或 Content-Disposition 获取文件扩展名
        ext = ".file"
        if url.endswith(".pptx"):
            ext = ".pptx"
        elif url.endswith(".pdf"):
            ext = ".pdf"
        
        filename = f"downloaded_{timestamp}{ext}"
        local_path = save_path / filename
        
        # 下载文件
        async with session.get(url) as response:
            if response.status == 200:
                with open(local_path, 'wb') as f:
                    while True:
                        chunk = await response.content.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
        
        print(f"💾 文件已保存: {local_path}")
        return local_path

