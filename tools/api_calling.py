"""
API Calling Tool - 通用 API 调用工具

这是一个通用的 HTTP API 调用工具,可以调用任何 REST API。
配合 Skills 中的 API 文档使用,无需为每个 API 单独编写工具。

使用场景:
1. LLM 从 Skill 文档中了解 API 的使用方法
2. 使用本工具发起实际的 HTTP 请求
3. 处理响应并返回结果

支持的功能:
- 普通 HTTP 请求 (GET/POST/PUT/DELETE/PATCH)
- SSE 流式响应（stream=true）
- 异步任务轮询
- 文件下载

示例:
- slidespeak-generator skill 提供了 SlideSpeak API 的完整文档
- LLM 读取文档后,使用 api_calling 工具调用 API
- 无需 slidespeak_render 这样的专门工具
"""

import os
import aiohttp
import asyncio
import json
import logging
from typing import Dict, Any, Optional, List, AsyncGenerator
from pathlib import Path

logger = logging.getLogger(__name__)


class APICallingTool:
    """
    通用 API 调用工具
    
    支持任意 HTTP API 调用,包括:
    - RESTful API
    - SSE 流式响应（通过 execute_stream() 流式返回）
    - 异步轮询
    - 文件上传/下载
    - 认证处理
    
    流式模式说明：
    - execute_stream(): 流式返回，每个 chunk 作为 content_delta 发送给前端
    - execute(): 非流式返回，完整结果一次性返回
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
2. SSE 流式响应 (stream=true)
3. 自定义 Headers 和认证
4. JSON/FormData/Multipart 请求体
5. 异步任务轮询
6. 文件下载

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
- stream: 是否为 SSE 流式响应 (默认 false)
- poll_for_result: 是否轮询异步任务结果
- download_url_field: 响应中的下载链接字段名
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
                "stream": {
                    "type": "boolean",
                    "description": "是否为 SSE 流式响应 (默认 false)。启用后会收集流式数据，最终返回完整结果"
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
        stream: bool = False,
        poll_for_result: bool = False,
        poll_config: Optional[Dict[str, Any]] = None,
        download_url_field: Optional[str] = None,
        save_dir: Optional[str] = None,
        conversation_id: Optional[str] = None,
        session_id: Optional[str] = None,
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
            stream: 是否为 SSE 流式响应
            poll_for_result: 是否轮询结果
            poll_config: 轮询配置
            download_url_field: 下载链接字段名
            save_dir: 保存目录（可选）
            conversation_id: 对话ID（用于计算 workspace 路径）
            session_id: 会话ID（用于 SSE 事件转发给前端）
            
        Returns:
            API 原始响应结果（不嵌套包装）
            
        注意：
            如需流式返回，请使用 execute_stream() 方法
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
            logger.info(f"📡 调用 API: {method} {url}")
            if body:
                logger.debug(f"📤 请求体: {json.dumps(body, ensure_ascii=False)[:200]}...")
            
            async with aiohttp.ClientSession() as session:
                # ==================== SSE 流式模式（非流式返回，收集后返回完整结果）====================
                # 注意：如需流式返回，请使用 execute_stream() 方法
                if stream:
                    logger.info(f"🌊 SSE 模式（收集后返回完整结果，流式请用 execute_stream）")
                    return await self._send_sse_request(
                        session=session,
                        url=url,
                        method=method,
                        headers=request_headers,
                        body=body
                    )
                
                # ==================== 普通请求模式 ====================
                response_data, http_status = await self._send_request(
                    session, url, method, request_headers, body
                )
                
                # 检查是否有错误
                if response_data is None:
                    return {
                        "error": "API 请求失败（无响应）",
                        "http_status": http_status
                    }
                
                # 检查内部错误标记
                if isinstance(response_data, dict) and response_data.get("_error"):
                    return {
                        "error": response_data.get("_message", "未知错误"),
                        "http_status": response_data.get("_status", 0)
                    }
                
                logger.info(f"✅ API 响应成功")
                
                # 3. 异步轮询
                if poll_for_result and poll_config:
                    logger.info(f"⏳ 开始轮询任务状态...")
                    response_data = await self._poll_for_result(
                        session, response_data, poll_config, request_headers
                    )
                    
                    if response_data is None:
                        return {
                            "error": "任务轮询失败或超时"
                        }
                
                # 4. 下载文件
                if download_url_field and isinstance(response_data, dict) and download_url_field in response_data:
                    download_url = response_data[download_url_field]
                    logger.info(f"📥 下载文件: {download_url}")
                    
                    local_path = await self._download_file(
                        session, download_url, save_dir
                    )
                    response_data["local_path"] = str(local_path)
                
                # 直接返回原始响应（不再嵌套包装）
                return response_data
        
        except Exception as e:
            logger.error(f"API 调用异常: {e}", exc_info=True)
            return {
                "error": str(e)
            }
    
    async def execute_stream(
        self,
        url: str,
        method: str = "POST",
        headers: Optional[Dict[str, str]] = None,
        body: Optional[Dict[str, Any]] = None,
        auth: Optional[Dict[str, Any]] = None,
        stream: bool = False,
        conversation_id: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """
        流式执行 API 调用
        
        当 stream=True 时，会流式返回 SSE 事件的文本内容。
        每个 yield 的字符串会作为 content_delta 发送给前端。
        
        Args:
            url: API 端点 URL
            method: HTTP 方法
            headers: 请求头
            body: 请求体
            auth: 认证配置
            stream: 是否为 SSE 流式响应
            conversation_id: 对话ID
            
        Yields:
            字符串片段（SSE 事件的文本内容）
        """
        # 准备请求头
        request_headers = headers or {}
        if auth:
            request_headers = self._apply_auth(request_headers, auth)
        
        # SSE 流式模式
        if stream:
            logger.info(f"🌊 流式执行 API: {method} {url}")
            
            # 设置 SSE 接收的 Accept 头
            request_headers = request_headers.copy()
            request_headers["Accept"] = "text/event-stream"
            
            if body and "Content-Type" not in request_headers:
                request_headers["Content-Type"] = "application/json"
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.request(
                        method=method,
                        url=url,
                        headers=request_headers,
                        json=body if body else None,
                        timeout=aiohttp.ClientTimeout(total=self.timeout)
                    ) as response:
                        if response.status not in [200, 201]:
                            error_text = await response.text()
                            logger.error(f"❌ SSE 请求失败 (HTTP {response.status})")
                            yield json.dumps({"error": error_text, "http_status": response.status})
                            return
                        
                        logger.info(f"🌊 SSE 连接已建立")
                        
                        # 解析 SSE 流
                        buffer = ""
                        current_event = {"event": None, "data": None, "id": None}
                        
                        async for chunk in response.content.iter_any():
                            buffer += chunk.decode("utf-8", errors="ignore")
                            
                            # 按行处理
                            while "\n" in buffer:
                                line, buffer = buffer.split("\n", 1)
                                line = line.strip()
                                
                                if not line:
                                    # 空行表示事件结束
                                    if current_event["data"] is not None:
                                        event_data = self._parse_sse_event(current_event)
                                        
                                        if event_data:
                                            # 提取文本片段
                                            text_chunk = self._extract_text_chunk(event_data)
                                            if text_chunk:
                                                # 🎯 流式返回文本片段
                                                yield text_chunk
                                    
                                    # 重置
                                    current_event = {"event": None, "data": None, "id": None}
                                
                                elif line.startswith("event:"):
                                    current_event["event"] = line[6:].strip()
                                elif line.startswith("data:"):
                                    data_content = line[5:].strip()
                                    if current_event["data"] is None:
                                        current_event["data"] = data_content
                                    else:
                                        current_event["data"] += "\n" + data_content
                                elif line.startswith("id:"):
                                    current_event["id"] = line[3:].strip()
                        
                        # 处理剩余的 buffer
                        if current_event["data"] is not None:
                            event_data = self._parse_sse_event(current_event)
                            if event_data:
                                text_chunk = self._extract_text_chunk(event_data)
                                if text_chunk:
                                    yield text_chunk
                        
                        logger.info(f"✅ SSE 流结束")
            
            except asyncio.TimeoutError:
                logger.error(f"❌ SSE 请求超时")
                yield json.dumps({"error": "SSE 请求超时"})
            except Exception as e:
                logger.error(f"❌ SSE 请求异常: {e}", exc_info=True)
                yield json.dumps({"error": str(e)})
        else:
            # 非流式模式：回退到普通执行，一次性返回完整结果
            result = await self.execute(
                url=url,
                method=method,
                headers=headers,
                body=body,
                auth=auth,
                stream=False,
                conversation_id=conversation_id,
                **kwargs
            )
            yield json.dumps(result, ensure_ascii=False)
    
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
    ) -> tuple[Optional[Dict[str, Any]], int]:
        """
        发送 HTTP 请求
        
        Returns:
            (响应数据, HTTP 状态码)
        """
        try:
            # 设置默认 Content-Type
            if body and "Content-Type" not in headers:
                headers["Content-Type"] = "application/json"
            
            # 发送请求（使用实例的 timeout 配置，默认 600 秒）
            async with session.request(
                method=method,
                url=url,
                headers=headers,
                json=body if body else None,
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as response:
                http_status = response.status
                
                if response.status in [200, 201]:
                    # 尝试解析 JSON，失败则返回文本
                    content_type = response.headers.get("Content-Type", "")
                    if "application/json" in content_type:
                        return await response.json(), http_status
                    else:
                        text = await response.text()
                        return {"_raw_text": text}, http_status
                else:
                    error_text = await response.text()
                    logger.error(f"❌ API 错误 (HTTP {response.status}): {error_text[:500]}")
                    # 返回错误详情
                    return {"_error": True, "_status": response.status, "_message": error_text}, http_status
        
        except asyncio.TimeoutError:
            logger.error(f"❌ 请求超时 ({self.timeout}秒)")
            return {"_error": True, "_status": 0, "_message": "请求超时"}, 0
        except Exception as e:
            logger.error(f"❌ 请求失败: {e}")
            return {"_error": True, "_status": 0, "_message": str(e)}, 0
    
    async def _send_sse_request(
        self,
        session: aiohttp.ClientSession,
        url: str,
        method: str,
        headers: Dict[str, str],
        body: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        发送 SSE 流式请求，收集所有数据后返回完整结果
        
        注意：如需流式返回，请使用 execute_stream() 方法
        
        Args:
            session: aiohttp 会话
            url: API 端点
            method: HTTP 方法
            headers: 请求头
            body: 请求体
            
        Returns:
            收集到的所有 SSE 数据
        """
        # 设置 SSE 接收的 Accept 头
        headers = headers.copy()
        headers["Accept"] = "text/event-stream"
        
        if body and "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"
        
        collected_events: List[Dict[str, Any]] = []
        collected_text: List[str] = []  # 收集文本片段（用于流式文本合并）
        
        try:
            async with session.request(
                method=method,
                url=url,
                headers=headers,
                json=body if body else None,
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as response:
                if response.status not in [200, 201]:
                    error_text = await response.text()
                    logger.error(f"❌ SSE 请求失败 (HTTP {response.status}): {error_text[:500]}")
                    return {
                        "error": error_text,
                        "http_status": response.status
                    }
                
                logger.info(f"🌊 SSE 连接已建立")
                
                # 解析 SSE 流
                buffer = ""
                current_event = {"event": None, "data": None, "id": None}
                
                async for chunk in response.content.iter_any():
                    buffer += chunk.decode("utf-8", errors="ignore")
                    
                    # 按行处理
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        
                        if not line:
                            # 空行表示事件结束
                            if current_event["data"] is not None:
                                event_data = self._parse_sse_event(current_event)
                                
                                if event_data:
                                    collected_events.append({
                                        "event": current_event["event"],
                                        "data": event_data
                                    })
                                    
                                    # 提取文本片段（常见的流式文本格式）
                                    text_chunk = self._extract_text_chunk(event_data)
                                    if text_chunk:
                                        collected_text.append(text_chunk)
                                
                            # 重置
                            current_event = {"event": None, "data": None, "id": None}
                        
                        elif line.startswith("event:"):
                            current_event["event"] = line[6:].strip()
                        elif line.startswith("data:"):
                            data_content = line[5:].strip()
                            if current_event["data"] is None:
                                current_event["data"] = data_content
                            else:
                                current_event["data"] += "\n" + data_content
                        elif line.startswith("id:"):
                            current_event["id"] = line[3:].strip()
                
                # 处理剩余的 buffer
                if current_event["data"] is not None:
                    event_data = self._parse_sse_event(current_event)
                    if event_data:
                        collected_events.append({
                            "event": current_event["event"],
                            "data": event_data
                        })
                        text_chunk = self._extract_text_chunk(event_data)
                        if text_chunk:
                            collected_text.append(text_chunk)
                
                logger.info(f"✅ SSE 流结束，共收到 {len(collected_events)} 个事件")
                
                # 合并文本
                full_text = "".join(collected_text) if collected_text else None
                
                # 返回结果
                result = {
                    "events_count": len(collected_events),
                }
                
                # 如果收集到了文本，直接返回合并后的文本
                if full_text:
                    result["text"] = full_text
                
                # 返回最后一个事件的数据（通常包含最终结果）
                if collected_events:
                    result["last_event"] = collected_events[-1]
                    
                    # 只保留最后几个事件，避免结果过大
                    if len(collected_events) <= 5:
                        result["events"] = collected_events
                    else:
                        result["events"] = collected_events[-5:]
                        result["events_truncated"] = True
                
                return result
        
        except asyncio.TimeoutError:
            logger.error(f"❌ SSE 请求超时")
            return {
                "error": "SSE 请求超时",
                "events_count": len(collected_events),
                "text": "".join(collected_text) if collected_text else None
            }
        except Exception as e:
            logger.error(f"❌ SSE 请求异常: {e}", exc_info=True)
            return {
                "error": str(e),
                "events_count": len(collected_events),
                "text": "".join(collected_text) if collected_text else None
            }
    
    def _parse_sse_event(self, current_event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """解析 SSE 事件数据"""
        data_str = current_event.get("data")
        if not data_str:
            return None
        
        # 特殊处理 [DONE] 标记（OpenAI 风格）
        if data_str.strip() == "[DONE]":
            return {"done": True}
        
        # 尝试解析 JSON
        try:
            data = json.loads(data_str)
            return data
        except json.JSONDecodeError:
            # 非 JSON 数据，返回原始文本
            return {"raw_text": data_str}
    
    def _extract_text_chunk(self, event_data: Dict[str, Any]) -> Optional[str]:
        """
        从 SSE 事件数据中提取文本片段
        
        支持常见的流式 API 格式：
        - OpenAI: choices[0].delta.content
        - Anthropic: delta.text
        - 通用: text, content, message
        """
        if not isinstance(event_data, dict):
            return None
        
        # OpenAI 格式
        choices = event_data.get("choices", [])
        if choices and isinstance(choices, list):
            delta = choices[0].get("delta", {})
            if isinstance(delta, dict):
                content = delta.get("content")
                if content:
                    return content
        
        # Anthropic 格式
        delta = event_data.get("delta", {})
        if isinstance(delta, dict):
            text = delta.get("text")
            if text:
                return text
        
        # 通用格式
        for key in ["text", "content", "message", "chunk"]:
            value = event_data.get(key)
            if isinstance(value, str) and value:
                return value
        
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
            logger.warning(f"⚠️ 未找到任务 ID (字段: {task_id_field})")
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
                            logger.info(f"✅ 任务完成!")
                            return result.get("task_result") or result.get("task_info") or result
                        elif status == failed_status:
                            logger.error(f"❌ 任务失败")
                            return None
                        
                        # 记录进度
                        if i % 10 == 0:
                            logger.info(f"⏳ 处理中... ({i * self.poll_interval}秒)")
                
                await asyncio.sleep(self.poll_interval)
            
            except Exception as e:
                logger.warning(f"⚠️ 轮询错误: {e}")
                await asyncio.sleep(self.poll_interval)
        
        logger.error(f"❌ 轮询超时 ({self.max_polls * self.poll_interval} 秒)")
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
        elif url.endswith(".png"):
            ext = ".png"
        elif url.endswith(".jpg") or url.endswith(".jpeg"):
            ext = ".jpg"
        elif url.endswith(".zip"):
            ext = ".zip"
        
        filename = f"downloaded_{timestamp}{ext}"
        local_path = save_path / filename
        
        # 下载文件
        async with session.get(url) as response:
            if response.status == 200:
                # 尝试从 Content-Disposition 获取文件名
                content_disposition = response.headers.get("Content-Disposition", "")
                if "filename=" in content_disposition:
                    import re
                    match = re.search(r'filename[*]?=["\']?([^"\';\n]+)', content_disposition)
                    if match:
                        original_filename = match.group(1).strip()
                        # 保留原始扩展名
                        if "." in original_filename:
                            ext = "." + original_filename.rsplit(".", 1)[1]
                            filename = f"downloaded_{timestamp}{ext}"
                            local_path = save_path / filename
                
                with open(local_path, 'wb') as f:
                    while True:
                        chunk = await response.content.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
        
        logger.info(f"💾 文件已保存: {local_path}")
        return local_path
