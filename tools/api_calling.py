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
- SSE 流式响应（mode="stream"）
- 异步任务轮询（mode="async_poll"）

调用方式:
1. 直接指定 URL：url="https://api.example.com/v1/xxx"
2. 使用预配置 API：api_name="coze_api", path="/workflow/stream_run"
   （自动注入 base_url 和认证 headers）

示例:
- config.yaml 中配置了 apis（包含 base_url 和认证信息）
- LLM 只需指定 api_name + path + body
- 框架自动补全 URL 和认证头
"""

import os
import aiohttp
import asyncio
import json
from typing import Dict, Any, Optional, List, AsyncGenerator

from logger import get_logger

logger = get_logger("api_calling")


class APICallingTool:
    """
    通用 API 调用工具
    
    支持任意 HTTP API 调用,包括:
    - RESTful API（同步模式）
    - SSE 流式响应（mode="stream"）
    - 异步轮询（mode="async_poll"）
    - 认证自动注入（通过 api_name 匹配预配置）
    
    流式模式说明：
    - execute_stream(): 流式返回，每个 chunk 作为 content_delta 发送给前端
    - execute(): 非流式返回，完整结果一次性返回
    
    认证注入说明：
    - 方式1：直接传 url + headers（完全控制）
    - 方式2：传 api_name + path（自动从 apis_config 注入 base_url 和认证）
    """
    
    def __init__(self, apis_config: Optional[List[Dict[str, Any]]] = None):
        """
        初始化 API 调用工具
        
        Args:
            apis_config: 预配置的 API 列表（从 config.yaml 注入）
                每个 API 包含: name, base_url, headers, description
        """
        self.timeout = 1200  # 默认超时 20 分钟
        self.max_polls = 150  # 异步任务最多轮询 150 次
        self.poll_interval = 2  # 轮询间隔 2 秒
        
        # 🆕 预配置的 APIs（用于 api_name 自动注入）
        self.apis_config = {api["name"]: api for api in (apis_config or [])}
        if self.apis_config:
            logger.info(f"✅ api_calling 初始化，已加载 {len(self.apis_config)} 个 API 配置: {list(self.apis_config.keys())}")
        else:
            logger.warning(f"⚠️ api_calling 初始化，apis_config 为空")
    
    @property
    def name(self) -> str:
        return "api_calling"
    
    @property
    def description(self) -> str:
        return """通用 API 调用工具,支持任意 HTTP API 请求。

支持的模式:
1. sync（默认）: 同步请求,等待响应后返回
2. stream: SSE 流式响应,实时返回数据
3. async_poll: 异步轮询,提交任务后轮询结果

调用方式:
1. 直接指定 URL: url="https://api.example.com/xxx"
2. 使用预配置 API: api_name="coze_api", path="/workflow/stream_run"
   - 自动从配置注入 base_url 和认证 headers
   - 无需手动填写 API Key

参数说明:
- api_name: 预配置的 API 名称（与 url 二选一）
- path: API 路径,与 api_name 配合使用
- url: 完整的 API URL（与 api_name 二选一）
- method: HTTP 方法 (默认 POST)
- headers: 额外的请求头（会与预配置合并）
- body: 请求体 (JSON)
- mode: 请求模式 sync/stream/async_poll (默认 sync)
- poll_config: 轮询配置（mode=async_poll 时使用）
"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                # ===== 方式1: 使用预配置 API（推荐）=====
                "api_name": {
                    "type": "string",
                    "description": "预配置的 API 名称（如 coze_api、dify_api）,自动注入 base_url 和认证"
                },
                "path": {
                    "type": "string",
                    "description": "API 路径（与 api_name 配合使用）,例如 /workflow/stream_run"
                },
                # ===== 方式2: 直接指定 URL =====
                "url": {
                    "type": "string",
                    "description": "完整的 API URL（与 api_name 二选一）"
                },
                # ===== 通用参数 =====
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                    "description": "HTTP 方法 (默认 POST)"
                },
                "headers": {
                    "type": "object",
                    "description": "额外的请求头（会与预配置的 headers 合并）"
                },
                "body": {
                    "type": "object",
                    "description": "请求体 (将自动转为 JSON)"
                },
                # ===== 请求模式（三选一）=====
                "mode": {
                    "type": "string",
                    "enum": ["sync", "stream", "async_poll"],
                    "description": "请求模式: sync(同步,默认)、stream(SSE流式)、async_poll(异步轮询)"
                },
                # ===== 轮询配置（mode=async_poll 时使用）=====
                "poll_config": {
                    "type": "object",
                    "description": "轮询配置（仅 mode=async_poll 时有效）",
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
                }
            },
            "required": []  # api_name 或 url 至少一个，在 execute 中校验
        }
    
    async def execute(
        self,
        # 方式1: 使用预配置 API
        api_name: Optional[str] = None,
        path: Optional[str] = None,
        # 方式2: 直接指定 URL
        url: Optional[str] = None,
        # 通用参数
        method: str = "POST",
        headers: Optional[Dict[str, str]] = None,
        body: Optional[Dict[str, Any]] = None,
        # 请求模式
        mode: str = "sync",  # sync / stream / async_poll
        poll_config: Optional[Dict[str, Any]] = None,
        **kwargs  # 框架注入的上下文
    ) -> Dict[str, Any]:
        """
        执行 API 调用
        
        Args:
            api_name: 预配置的 API 名称（自动注入 base_url 和认证）
            path: API 路径（与 api_name 配合使用）
            url: 完整的 API URL（与 api_name 二选一）
            method: HTTP 方法
            headers: 额外的请求头（会与预配置合并）
            body: 请求体
            mode: 请求模式 sync/stream/async_poll
            poll_config: 轮询配置（mode=async_poll 时使用）
            
        Returns:
            API 原始响应结果（不嵌套包装）
        """
        try:
            # 1. 解析 URL 和 Headers（支持 api_name 自动注入）
            final_url, final_headers, resolve_error, _ = self._resolve_api_config(
                api_name=api_name,
                path=path,
                url=url,
                headers=headers
            )
            
            # 校验 URL
            if not final_url or resolve_error:
                return {"error": resolve_error or "必须提供 url 或 api_name 参数"}
            
            # 2. 自动替换请求头中的环境变量占位符 ${VAR_NAME}
            final_headers = self._resolve_env_vars(final_headers)
            
            # 3. 🆕 自动替换 body 中的上下文占位符 ${user_id}, ${conversation_id} 等
            if body:
                body = self._resolve_body_placeholders(body, kwargs)
            
            # 4. 打印请求信息
            logger.info(f"📡 调用 API: {method} {final_url}")
            logger.info(f"📤 请求头: {json.dumps({k: v[:20] + '...' if len(str(v)) > 20 else v for k, v in final_headers.items()}, ensure_ascii=False)}")
            if body:
                logger.info(f"📤 请求体: {json.dumps(body, ensure_ascii=False)[:500]}")
            
            async with aiohttp.ClientSession() as session:
                # ==================== SSE 流式模式 ====================
                if mode == "stream":
                    logger.info(f"🌊 SSE 模式（收集后返回完整结果，流式请用 execute_stream）")
                    return await self._send_sse_request(
                        session=session,
                        url=final_url,
                        method=method,
                        headers=final_headers,
                        body=body
                    )
                
                # ==================== 同步/异步轮询模式 ====================
                response_data, http_status = await self._send_request(
                    session, final_url, method, final_headers, body
                )
                
                # 检查是否有错误
                if response_data is None:
                    return {"error": "API 请求失败（无响应）", "http_status": http_status}
                
                if isinstance(response_data, dict) and response_data.get("_error"):
                    return {
                        "error": response_data.get("_message", "未知错误"),
                        "http_status": response_data.get("_status", 0)
                    }
                
                logger.info(f"✅ API 响应成功")
                
                # ==================== 异步轮询模式 ====================
                if mode == "async_poll" and poll_config:
                    logger.info(f"⏳ 开始轮询任务状态...")
                    response_data = await self._poll_for_result(
                        session=session,
                        initial_response=response_data,
                        poll_config=poll_config,
                        headers=final_headers,
                        request_body=body  # 🆕 传递 body 用于提取 workflow_id 等变量
                    )
                    
                    if response_data is None:
                        return {"error": "任务轮询失败或超时"}
                
                return response_data
        
        except Exception as e:
            logger.error(f"API 调用异常: {e}", exc_info=True)
            return {"error": str(e)}
    
    def _resolve_api_config(
        self,
        api_name: Optional[str] = None,
        path: Optional[str] = None,
        url: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> tuple[Optional[str], Dict[str, str], Optional[str], Dict[str, Any]]:
        """
        解析 API 配置,支持自动注入
        
        Args:
            api_name: 预配置的 API 名称
            path: API 路径
            url: 完整 URL
            headers: 额外请求头
            
        Returns:
            (final_url, final_headers, error_message, meta_info)
            - 成功时 error_message 为 None
            - 失败时 final_url 为 None，error_message 包含错误原因
            - meta_info: 元数据信息 {api_name, base_url, path}，用于下游识别 API 来源
        """
        final_headers = headers.copy() if headers else {}
        meta_info: Dict[str, Any] = {}
        
        # 方式1: 使用预配置 API
        if api_name:
            logger.info(f"🔍 查找 API 配置: api_name={api_name}, apis_config 数量={len(self.apis_config)}")
            api_config = self.apis_config.get(api_name)
            if not api_config:
                available_apis = list(self.apis_config.keys()) if self.apis_config else []
                error_msg = f"未找到预配置的 API: '{api_name}'。可用的 API: {available_apis if available_apis else '无（apis_config 为空）'}"
                logger.warning(f"⚠️ {error_msg}")
                return None, final_headers, error_msg, meta_info
            
            # 拼接 URL（并替换环境变量）
            base_url = api_config.get("base_url", "")
            base_url = self._resolve_env_var_in_string(base_url).rstrip("/")
            if not base_url:
                error_msg = f"API '{api_name}' 配置缺少 base_url"
                logger.error(f"❌ {error_msg}")
                return None, final_headers, error_msg, meta_info
            
            # 🔧 智能处理路径前缀重复问题
            # 如果 base_url 以 /v1 结尾，而 path 以 /v1/ 开头，自动去除 path 中的 /v1
            original_path = path
            path = (path or "").lstrip("/")
            if path:
                # 检测并移除重复的版本前缀（如 v1/v1/...）
                from urllib.parse import urlparse
                base_path = urlparse(base_url).path.rstrip("/")
                if base_path:
                    # 提取 base_url 中的最后一个路径段（如 /v1）
                    base_suffix = base_path.split("/")[-1]  # "v1"
                    # 如果 path 以相同前缀开头，去除它
                    if path.startswith(f"{base_suffix}/"):
                        original_path_for_log = path
                        path = path[len(base_suffix) + 1:]  # 去除 "v1/"
                        logger.warning(
                            f"⚠️ 检测到路径重复前缀，自动修正: "
                            f"'{original_path_for_log}' → '{path}'"
                        )
            
            final_url = f"{base_url}/{path}" if path else base_url
            
            # 合并 headers：预配置的 headers + LLM 传入的 headers
            config_headers = api_config.get("headers", {})
            merged_headers = {**config_headers, **final_headers}
            
            # 🔐 处理 auth 配置（自动注入认证头）
            auth_config = api_config.get("auth")
            if auth_config:
                auth_type = auth_config.get("type", "bearer")  # 默认 bearer
                auth_header = auth_config.get("header", "Authorization")  # 默认 Authorization
                auth_env = auth_config.get("env")  # 环境变量名
                
                if auth_env:
                    auth_value = os.environ.get(auth_env)
                    if auth_value:
                        # bearer 类型添加 "Bearer " 前缀，其他类型直接使用值
                        if auth_type == "bearer":
                            merged_headers[auth_header] = f"Bearer {auth_value}"
                        else:
                            merged_headers[auth_header] = auth_value
                        logger.debug(f"🔐 注入认证头: {auth_header} (来自环境变量 {auth_env})")
                    else:
                        logger.warning(f"⚠️ 认证环境变量未设置: {auth_env}")
            
            # 🆕 构建元数据信息（用于下游识别 API 来源）
            meta_info = {
                "api_name": api_name,
                "base_url": base_url,
                "path": f"/{path}" if path else "",
                "capability": api_config.get("capability", "")
            }
            
            logger.info(f"🔑 使用预配置 API: {api_name} → {final_url}")
            return final_url, merged_headers, None, meta_info
        
        # 方式2: 直接使用 URL
        if not url:
            return None, final_headers, "必须提供 url 或 api_name 参数", meta_info
        
        # 直接使用 URL 时，meta_info 只包含 url
        meta_info = {"url": url}
        return url, final_headers, None, meta_info
    
    async def execute_stream(
        self,
        # 方式1: 使用预配置 API
        api_name: Optional[str] = None,
        path: Optional[str] = None,
        # 方式2: 直接指定 URL
        url: Optional[str] = None,
        # 通用参数
        method: str = "POST",
        headers: Optional[Dict[str, str]] = None,
        body: Optional[Dict[str, Any]] = None,
        # 请求模式
        mode: str = "stream",  # 流式执行默认为 stream
        **kwargs  # 框架注入的上下文
    ) -> AsyncGenerator[str, None]:
        """
        流式执行 API 调用
        
        SSE 流式返回，每个 yield 的字符串会作为 content_delta 发送给前端。
        
        Args:
            api_name: 预配置的 API 名称
            path: API 路径
            url: 完整的 API URL
            method: HTTP 方法
            headers: 额外请求头
            body: 请求体
            mode: 请求模式（流式执行时应为 stream）
            
        Yields:
            字符串片段（SSE 事件的文本内容）
        """
        # 1. 解析 URL 和 Headers
        final_url, final_headers, resolve_error, _ = self._resolve_api_config(
            api_name=api_name,
            path=path,
            url=url,
            headers=headers
        )
        
        if not final_url or resolve_error:
            yield json.dumps({"error": resolve_error or "必须提供 url 或 api_name 参数"})
            return
        
        # 2. 替换环境变量
        final_headers = self._resolve_env_vars(final_headers)
        
        # 3. 🆕 V7.9.2: 替换 body 中的上下文占位符（与 execute 保持一致）
        if body:
            body = self._resolve_body_placeholders(body, kwargs)
        
        # 非流式模式：回退到普通执行
        if mode != "stream":
            result = await self.execute(
                api_name=api_name,
                path=path,
                url=url,
                method=method,
                headers=headers,
                body=body,
                mode=mode,
                **kwargs
            )
            yield json.dumps(result, ensure_ascii=False)
            return
        
        # 3. SSE 流式模式 - 直接 yield 原始 chunk
        logger.info(f"🌊 流式执行 API: {method} {final_url}")
        
        # 设置 SSE 接收的 Accept 头
        final_headers = final_headers.copy()
        final_headers["Accept"] = "text/event-stream"
        
        if body and "Content-Type" not in final_headers:
            final_headers["Content-Type"] = "application/json"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method=method,
                    url=final_url,
                    headers=final_headers,
                    json=body if body else None,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status not in [200, 201]:
                        error_text = await response.text()
                        logger.error(f"❌ SSE 请求失败 (HTTP {response.status}): {error_text[:500]}")
                        yield json.dumps({
                            "error": f"HTTP {response.status}: {error_text[:1000]}" if error_text else f"HTTP {response.status} 错误",
                            "http_status": response.status,
                            "url": final_url
                        }, ensure_ascii=False)
                        return
                    
                    logger.info(f"🌊 SSE 连接已建立")
                    
                    # 直接 yield 原始 chunk 内容
                    async for chunk in response.content.iter_any():
                        decoded = chunk.decode("utf-8", errors="ignore")
                        if decoded:
                            yield decoded
                    
                    logger.info(f"✅ SSE 流结束")
        
        except asyncio.TimeoutError:
            logger.error(f"❌ SSE 请求超时")
            yield json.dumps({"error": "SSE 请求超时"})
        except Exception as e:
            logger.error(f"❌ SSE 请求异常: {e}", exc_info=True)
            yield json.dumps({"error": str(e)})
    
    def _resolve_env_var_in_string(self, value: str) -> str:
        """
        替换单个字符串中的环境变量占位符 ${VAR_NAME}
        
        用于处理 base_url 等配置中的环境变量。
        支持处理 URL 编码后的占位符（如 $%7BVAR_NAME%7D）。
        
        Args:
            value: 包含环境变量占位符的字符串
            
        Returns:
            替换后的字符串
        """
        import re
        from urllib.parse import unquote
        
        if not isinstance(value, str):
            return value
        
        # 🔧 先尝试 URL 解码，处理被编码的 ${...} 占位符
        # 例如：$%7BWENSHU_API_BASE_URL%7D → ${WENSHU_API_BASE_URL}
        if '%7B' in value or '%7D' in value:
            decoded_value = unquote(value)
            if decoded_value != value:
                logger.debug(f"🔓 URL 解码: {value[:50]}... → {decoded_value[:50]}...")
                value = decoded_value
        
        env_var_pattern = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}')
        
        def replace_env_var(match):
            var_name = match.group(1)
            env_value = os.environ.get(var_name)
            if env_value:
                logger.debug(f"🔑 替换环境变量: ${{{var_name}}} → [已设置]")
                return env_value
            else:
                logger.warning(f"⚠️ 环境变量未设置: {var_name}")
                return match.group(0)  # 保留原样
        
        return env_var_pattern.sub(replace_env_var, value)
    
    def _resolve_env_vars(self, headers: Dict[str, str]) -> Dict[str, str]:
        """
        自动替换请求头中的环境变量占位符 ${VAR_NAME}
        
        这样 LLM 可以使用 ${COZE_API_KEY} 等占位符，
        框架会自动从环境变量中读取真实值。
        """
        resolved = {}
        
        for key, value in headers.items():
            resolved[key] = self._resolve_env_var_in_string(value) if isinstance(value, str) else value
        
        return resolved
    
    def _resolve_body_placeholders(
        self,
        body: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        🆕 V7.9: 替换 body 中的上下文占位符
        
        支持的占位符：
        - ${user_id}: 从 context 中获取用户 ID
        - ${conversation_id}: 从 context 中获取会话 ID
        - ${session_id}: 从 context 中获取 session ID
        
        占位符替换顺序：
        1. 先从 context（框架注入的上下文）获取
        2. 再从环境变量获取
        
        Args:
            body: 请求体字典
            context: 框架注入的上下文（来自 **kwargs）
            
        Returns:
            替换后的 body
        """
        import re
        import copy
        
        # 🔍 调试日志：记录收到的 context 键和值
        logger.info(f"🔑 [_resolve_body_placeholders] context keys: {list(context.keys())}")
        logger.info(f"🔑 [_resolve_body_placeholders] conversation_id={context.get('conversation_id')}, user_id={context.get('user_id')}, session_id={context.get('session_id')}")
        
        # 深拷贝避免修改原始数据
        resolved_body = copy.deepcopy(body)
        
        # 支持的上下文占位符映射
        # key: 占位符名（不含 ${}），value: context 中的 key
        context_mapping = {
            "user_id": "user_id",
            "conversation_id": "conversation_id",
            "session_id": "session_id",
        }
        
        # 占位符正则：${VAR_NAME}
        placeholder_pattern = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}')
        
        def replace_in_value(value):
            """递归替换字符串中的占位符"""
            if isinstance(value, str):
                def replace_placeholder(match):
                    var_name = match.group(1)
                    
                    # 1. 先从 context 获取
                    if var_name in context_mapping:
                        context_key = context_mapping[var_name]
                        context_value = context.get(context_key)
                        if context_value:
                            logger.debug(f"🔑 替换上下文占位符: ${{{var_name}}} → {context_value[:20] if len(str(context_value)) > 20 else context_value}")
                            return str(context_value)
                    
                    # 2. 再从环境变量获取
                    env_value = os.environ.get(var_name)
                    if env_value:
                        logger.debug(f"🔑 替换环境变量占位符: ${{{var_name}}} → [已设置]")
                        return env_value
                    
                    # 3. 未找到，保留原样并警告
                    logger.warning(f"⚠️ 占位符未解析: ${{{var_name}}}（context 和环境变量中均未找到）")
                    return match.group(0)
                
                return placeholder_pattern.sub(replace_placeholder, value)
            
            elif isinstance(value, dict):
                return {k: replace_in_value(v) for k, v in value.items()}
            
            elif isinstance(value, list):
                return [replace_in_value(item) for item in value]
            
            else:
                return value
        
        resolved_body = replace_in_value(resolved_body)
        return resolved_body
    
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
                content_type = response.headers.get("Content-Type", "")
                
                if response.status in [200, 201]:
                    # 🔧 自动检测 SSE 响应（即使 stream=False 也能正确处理）
                    if "text/event-stream" in content_type:
                        logger.warning(
                            f"⚠️ 检测到 SSE 响应但未设置 stream=True，自动切换到 SSE 模式。"
                            f"建议：调用此 API 时设置 stream=True"
                        )
                        # 内联解析 SSE 流
                        return await self._parse_sse_response_from_response(response), http_status
                    
                    # 尝试解析 JSON，失败则返回文本
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
    
    async def _parse_sse_response_from_response(
        self,
        response: aiohttp.ClientResponse
    ) -> Dict[str, Any]:
        """
        从已有的 response 对象读取 SSE 流（用于自动检测 SSE 场景）
        
        简化设计：直接累加原始内容返回
        """
        try:
            raw_content = ""
            async for chunk in response.content.iter_any():
                raw_content += chunk.decode("utf-8", errors="ignore")
            
            logger.info(f"✅ SSE 自动读取完成，共收到 {len(raw_content)} 字符")
            return {"raw_content": raw_content}
            
        except Exception as e:
            logger.error(f"❌ SSE 自动读取异常: {e}", exc_info=True)
            return {"error": str(e)}
    
    async def _send_sse_request(
        self,
        session: aiohttp.ClientSession,
        url: str,
        method: str,
        headers: Dict[str, str],
        body: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        发送 SSE 流式请求，收集所有原始数据后返回
        
        简化设计：不解析 SSE 事件格式，直接累加原始内容返回给 Agent
        Agent 可以自行处理返回的原始数据
        
        Args:
            session: aiohttp 会话
            url: API 端点
            method: HTTP 方法
            headers: 请求头
            body: 请求体
            
        Returns:
            {"raw_content": "完整的原始响应内容"}
        """
        # 设置 SSE 接收的 Accept 头
        headers = headers.copy()
        headers["Accept"] = "text/event-stream"
        
        if body and "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"
        
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
                        "error": f"HTTP {response.status}: {error_text[:1000]}" if error_text else f"HTTP {response.status} 错误",
                        "http_status": response.status,
                        "url": url
                    }
                
                logger.info(f"🌊 SSE 连接已建立")
                
                # 直接累加所有原始内容
                raw_content = ""
                async for chunk in response.content.iter_any():
                    raw_content += chunk.decode("utf-8", errors="ignore")
                
                logger.info(f"✅ SSE 流结束，共收到 {len(raw_content)} 字符")
                
                return {"raw_content": raw_content}
        
        except asyncio.TimeoutError:
            logger.error(f"❌ SSE 请求超时")
            return {"error": "SSE 请求超时"}
        except Exception as e:
            logger.error(f"❌ SSE 请求异常: {e}", exc_info=True)
            return {"error": str(e)}
    
    def _get_nested_value(self, data: Dict[str, Any], field_path: str) -> Any:
        """
        从嵌套字典中获取值
        
        支持点分隔的路径，如 "data.execute_id" 或 "data.output"
        
        Args:
            data: 数据字典
            field_path: 字段路径，支持点分隔（如 "data.execute_id"）
            
        Returns:
            字段值，未找到时返回 None
        """
        if not field_path or not data:
            return None
        
        keys = field_path.split(".")
        value = data
        
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
            
            if value is None:
                return None
        
        return value
    
    async def _poll_for_result(
        self,
        session: aiohttp.ClientSession,
        initial_response: Dict[str, Any],
        poll_config: Dict[str, Any],
        headers: Dict[str, str],
        request_body: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        轮询异步任务结果
        
        支持多变量 URL 模板，变量来源：
        1. 从 request_body 中提取（如 workflow_id）
        2. 从 initial_response 中提取（如 execute_id）
        
        poll_config 配置项：
        - status_url_template: URL 模板，支持多个变量，如 "{base_url}/workflows/{workflow_id}/run_histories/{execute_id}"
        - execute_id_field: 响应中 execute_id 的字段路径，支持嵌套（如 "data.execute_id"），默认 "execute_id"
        - body_vars: 需要从 request_body 提取的变量列表，如 ["workflow_id"]
        - status_field: 轮询响应中状态的字段路径，如 "data.status"，默认 "status"
        - result_field: 最终结果的字段路径，如 "data.output"，默认返回整个响应
        - success_status: 成功状态值，默认 "Success"
        - failed_status: 失败状态值，默认 "Fail"
        
        Args:
            session: aiohttp 会话
            initial_response: 初始请求的响应
            poll_config: 轮询配置
            headers: 请求头
            request_body: 原始请求体（用于提取 workflow_id 等变量）
            
        Returns:
            轮询成功时返回结果，失败或超时返回 None
        """
        request_body = request_body or {}
        
        # ===== 1. 构建 URL 模板变量 =====
        url_vars: Dict[str, str] = {}
        
        # 1.1 从 request_body 提取变量（如 workflow_id）
        body_vars = poll_config.get("body_vars", [])
        for var_name in body_vars:
            var_value = request_body.get(var_name)
            if var_value:
                url_vars[var_name] = str(var_value)
                logger.debug(f"🔑 从 body 提取变量: {var_name}={var_value}")
            else:
                logger.warning(f"⚠️ body 中未找到变量: {var_name}")
        
        # 1.2 从 initial_response 提取 execute_id（支持嵌套路径）
        execute_id_field = poll_config.get("execute_id_field", "execute_id")
        execute_id = self._get_nested_value(initial_response, execute_id_field)
        
        # 兼容旧配置：也支持 status_url_field
        if not execute_id:
            legacy_field = poll_config.get("status_url_field", "task_id")
            execute_id = self._get_nested_value(initial_response, legacy_field) or initial_response.get(legacy_field)
        
        if execute_id:
            url_vars["execute_id"] = str(execute_id)
            url_vars["task_id"] = str(execute_id)  # 兼容旧模板
            logger.info(f"🔑 从响应提取 execute_id: {execute_id}")
        else:
            logger.warning(f"⚠️ 未找到 execute_id (字段: {execute_id_field})")
            return initial_response
        
        # ===== 2. 构建轮询 URL =====
        status_url_template = poll_config.get("status_url_template", "")
        if not status_url_template:
            logger.error("❌ poll_config 缺少 status_url_template")
            return initial_response
        
        try:
            status_url = status_url_template.format(**url_vars)
            logger.info(f"🔗 轮询 URL: {status_url}")
        except KeyError as e:
            logger.error(f"❌ URL 模板变量缺失: {e}，可用变量: {url_vars}")
            return initial_response
        
        # ===== 3. 轮询配置 =====
        success_status = poll_config.get("success_status", "Success")
        failed_status = poll_config.get("failed_status", "Fail")
        status_field = poll_config.get("status_field", "status")
        result_field = poll_config.get("result_field")  # 可选，为空则返回整个响应
        
        # ===== 4. 开始轮询 =====
        for i in range(self.max_polls):
            try:
                async with session.get(
                    status_url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        
                        # 获取状态（支持嵌套路径）
                        status = self._get_nested_value(result, status_field)
                        # 兼容旧格式
                        if status is None:
                            status = result.get("task_status") or result.get("status")
                        
                        logger.debug(f"🔄 轮询状态: {status}")
                        
                        if status == success_status:
                            logger.info(f"✅ 任务完成!")
                            # 提取结果（支持嵌套路径）
                            if result_field:
                                final_result = self._get_nested_value(result, result_field)
                                return final_result if final_result is not None else result
                            # 兼容旧格式
                            return result.get("task_result") or result.get("task_info") or result
                        
                        elif status == failed_status:
                            error_msg = self._get_nested_value(result, "data.error_message") or result.get("error_message", "未知错误")
                            logger.error(f"❌ 任务失败: {error_msg}")
                            return {"error": f"任务执行失败: {error_msg}", "raw_response": result}
                        
                        # 记录进度
                        if i % 10 == 0:
                            logger.info(f"⏳ 处理中... ({i * self.poll_interval}秒), 状态: {status}")
                    else:
                        error_text = await response.text()
                        logger.warning(f"⚠️ 轮询请求失败 (HTTP {response.status}): {error_text[:200]}")
                
                await asyncio.sleep(self.poll_interval)
            
            except Exception as e:
                logger.warning(f"⚠️ 轮询错误: {e}")
                await asyncio.sleep(self.poll_interval)
        
        logger.error(f"❌ 轮询超时 ({self.max_polls * self.poll_interval} 秒)")
        return {"error": f"任务轮询超时（{self.max_polls * self.poll_interval}秒）"}
