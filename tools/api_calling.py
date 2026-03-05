"""
API Calling Tool - 通用 API 调用工具

支持的功能:
- 普通 HTTP 请求 (GET/POST/PUT/DELETE/PATCH)
- SSE 流式响应（mode="stream"）
- 异步任务轮询（mode="async_poll"）

配置说明：
- input_schema 在 config/capabilities.yaml 中定义
- 运营可直接修改 YAML 调整参数，无需改代码
"""

import asyncio
import copy
import json
import os
import re
from typing import Any, AsyncGenerator, Dict, List, Optional

import aiohttp

from core.tool.types import BaseTool, ToolContext
from logger import get_logger

logger = get_logger("api_calling")


# ============================================================
# 占位符正则（全局复用）
# ============================================================
# ${xxx} - 框架注入（从 context 获取：user_id, conversation_id 等）
INJECT_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
# {{xxx}} - AI 填写（从 parameters 获取）
AI_PLACEHOLDER = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}")
# 兼容旧格式
PLACEHOLDER_PATTERN = INJECT_PLACEHOLDER


class APICallingTool(BaseTool):
    """
    通用 API 调用工具（input_schema 由 capabilities.yaml 定义）

    支持：
    - RESTful API（同步模式）
    - SSE 流式响应（mode="stream"）
    - 异步轮询（mode="async_poll"）
    """

    name = "api_calling"

    def __init__(self, apis_config: Optional[List[Dict[str, Any]]] = None):
        """初始化 API 调用工具"""
        self.timeout = 1200  # 默认超时 20 分钟
        self.max_polls = 400  # 最多轮询 400 次（约 13 分钟）
        self.poll_interval = 2  # 轮询间隔 2 秒

        # 预配置的 APIs（用于 api_name 自动注入）
        # 🔧 注意：运行时优先使用 context.apis_config（通过 _get_apis_config 方法）
        self._init_apis_config = {api["name"]: api for api in (apis_config or [])}
        if self._init_apis_config:
            logger.info(
                f"✅ api_calling 初始化，已加载 {len(self._init_apis_config)} 个 API: {list(self._init_apis_config.keys())}"
            )

    def _get_apis_config(self, context: Optional[ToolContext] = None) -> Dict[str, Any]:
        """
        获取有效的 APIs 配置

        优先级：context.apis_config > self._init_apis_config

        Args:
            context: 工具执行上下文

        Returns:
            API 配置字典 {api_name: api_config}
        """
        # 优先从 context 获取（运行时注入）
        if context and context.apis_config:
            apis_config = {api["name"]: api for api in context.apis_config}
            if apis_config:
                return apis_config

        # 回退到初始化时的配置
        return self._init_apis_config

    # ============================================================
    # 辅助方法
    # ============================================================

    def _validate_parameters(
        self, parameters: Dict[str, Any], schema: Dict[str, Any]
    ) -> Optional[str]:
        """
        简单的 JSON Schema 校验
        支持: required, type (string, integer, number, boolean, array, object)
        """
        if not schema or not isinstance(parameters, dict):
            return None

        # 1. 检查必填字段
        required = schema.get("required", [])
        for field in required:
            if field not in parameters:
                return f"缺少必填参数: {field}"

        # 2. 检查类型
        properties = schema.get("properties", {})
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }

        for key, value in parameters.items():
            if key in properties:
                field_schema = properties[key]
                prop_type = field_schema.get("type")

                # 允许 null 值（如果不是必填，或者明确允许 null）
                if value is None:
                    # 如果是必填且为 None，前面已经通过 required 检查了（如果 key 存在但值为 None）
                    # 这里假设如果 key 存在，值不能为 None，除非 schema 允许 nullable（暂不支持复杂 schema）
                    # 简单处理：如果值是 None，且是 string 类型，可能允许？
                    # 暂定：严格检查类型
                    pass

                if prop_type in type_map:
                    expected_type = type_map[prop_type]
                    # 宽松处理：整型可以作为浮点型
                    if prop_type == "number" and isinstance(value, int):
                        continue

                    if not isinstance(value, expected_type):
                        return (
                            f"参数 '{key}' 类型错误: 预期 {prop_type}, 实际 {type(value).__name__}"
                        )

        return None

    def _extract_ai_params(self, data: Any, prefix: str = "") -> list[str]:
        """从 request_body 中提取 {{xxx}} AI 参数名"""
        params = []

        if isinstance(data, str):
            match = AI_PLACEHOLDER.fullmatch(data)
            if match:
                params.append(match.group(1))
        elif isinstance(data, dict):
            for k, v in data.items():
                params.extend(self._extract_ai_params(v, f"{prefix}{k}."))
        elif isinstance(data, list):
            for item in data:
                params.extend(self._extract_ai_params(item, prefix))

        return params

    # ============================================================
    # 核心执行方法
    # ============================================================

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        """
        执行 API 调用

        Args:
            params: 工具输入参数
                - api_name: API 名称（必需）
                - parameters: API 动态参数
                - poll_config: 轮询配置（可选，通常在 YAML 中定义）
            context: 工具执行上下文
        """
        # 🔧 V7.12: 如果 context 提供了 apis_config，使用它更新 self.apis_config
        if context and hasattr(context, "apis_config") and context.apis_config:
            if isinstance(context.apis_config, list):
                self.apis_config = {api["name"]: api for api in context.apis_config}
            elif isinstance(context.apis_config, dict):
                self.apis_config = context.apis_config

        # 从 params 提取参数
        api_name = params.get("api_name")
        parameters = params.get("parameters")

        if not api_name:
            return {"error": "必须提供 api_name 参数"}

        # 🔧 获取有效的 APIs 配置（优先从 context 获取）
        apis_config = self._get_apis_config(context)

        # 🆕 1. 确定超时时间（优先使用 API 配置，否则使用默认值）
        current_timeout = self.timeout
        api_config = apis_config.get(api_name) if api_name else None
        if api_config and "timeout" in api_config:
            current_timeout = api_config["timeout"]

        # 🆕 2. 输入校验 (如果提供了 parameters 和 schema)
        if api_config and parameters and "input_schema" in api_config:
            schema = api_config["input_schema"]
            validation_error = self._validate_parameters(parameters, schema)
            if validation_error:
                logger.warning(f"❌ 参数校验失败: {validation_error}")
                return {"error": f"参数校验失败: {validation_error}"}

        # 构建框架注入的上下文（用于占位符替换）
        kwargs = {
            "user_id": context.user_id,
            "conversation_id": context.conversation_id,
            "session_id": context.session_id,
        }

        try:
            # ===== 简化调用方式：api_name + parameters（唯一推荐方式） =====
            logger.info(
                f"📡 [调用] api_name={api_name}, parameters={list(parameters.keys()) if parameters else 'None'}"
            )

            # 如果 parameters 为空，但配置中有 request_body 需要填充，可能由 AI 填充为空（或者配置本身不需要参数）
            # 这里允许 parameters 为 None 或空字典
            safe_parameters = parameters or {}

            request_config, error = self._build_request_from_config(
                api_name, safe_parameters, apis_config
            )
            if error:
                return {"error": error}

            method = request_config["method"]
            mode = request_config["mode"]
            poll_config = request_config.get("poll_config")
            body = request_config["body"]

            # 1. 解析 URL 和 Headers (仅保留 api_name 分支)
            final_url, final_headers, error, _ = self._resolve_api_config(
                api_name, None, None, apis_config
            )
            if not final_url or error:
                return {"error": error or "无法解析 API 配置"}

            # 2. 替换环境变量占位符
            final_headers = self._resolve_env_vars(final_headers)

            # 3. 替换 body 中的系统占位符（user_id, conversation_id 等）
            if body:
                body = self._resolve_system_placeholders(body, kwargs)

            # 4. 发送请求
            logger.info(f"📡 {method} {final_url}")
            logger.info(
                f"📤 完整请求参数: url={final_url}, method={method}, headers={final_headers}, body={json.dumps(body, ensure_ascii=False) if body else 'None'}"
            )

            async with aiohttp.ClientSession() as session:
                # SSE 流式模式
                if mode == "stream":
                    return await self._send_sse_request(
                        session, final_url, method, final_headers, body, timeout=current_timeout
                    )

                # 同步/异步轮询模式
                response_data, http_status = await self._send_request(
                    session, final_url, method, final_headers, body, timeout=current_timeout
                )

                if response_data is None:
                    return {"error": "API 请求失败（无响应）", "http_status": http_status}

                if isinstance(response_data, dict) and response_data.get("_error"):
                    return {
                        "error": response_data.get("_message", "未知错误"),
                        "http_status": response_data.get("_status", 0),
                    }

                logger.info(f"✅ API 响应成功")
                logger.info(f"🔍 [调试] mode={mode}, poll_config={poll_config is not None}")

                # 异步轮询模式
                if mode == "async_poll" and poll_config:
                    logger.info(f"⏳ 开始轮询任务状态...")
                    response_data = await self._poll_for_result(
                        session, response_data, poll_config, final_headers, body
                    )
                    if response_data is None:
                        return {"error": "任务轮询失败或超时"}

                return response_data

        except Exception as e:
            logger.error(f"API 调用异常: {e}", exc_info=True)
            return {"error": str(e)}

    # ============================================================
    # 请求构建
    # ============================================================

    def _build_request_from_config(
        self,
        api_name: str,
        parameters: Dict[str, Any],
        apis_config: Optional[Dict[str, Any]] = None,
    ) -> tuple[Dict[str, Any], Optional[str]]:
        """
        根据 api_name 和 AI parameters 构建完整请求

        占位符处理：
        - {{xxx}} = AI 填写（在此方法中替换为 parameters 中的值）
        - ${xxx} = 框架注入（在 execute 方法中由 _resolve_system_placeholders 替换）

        Args:
            api_name: API 名称
            parameters: AI 填写的参数
            apis_config: API 配置字典（优先从 context 获取）
        """
        apis_config = apis_config or {}
        api_config = apis_config.get(api_name)
        if not api_config:
            return {}, f"未找到 API '{api_name}'，可用: {list(apis_config.keys())}"

        method = api_config.get("default_method", "POST")
        mode = api_config.get("default_mode", "sync")
        poll_config = api_config.get("poll_config")

        # 获取请求体模板
        request_body = api_config.get("request_body", {})

        # 深拷贝模板
        body = copy.deepcopy(request_body)

        # 替换 {{xxx}} AI 占位符
        body = self._replace_ai_placeholders(body, parameters)

        logger.debug(f"📋 构建请求: api={api_name}, method={method}, mode={mode}")
        logger.debug(f"📋 body（AI占位符已替换）: {json.dumps(body, ensure_ascii=False)[:500]}")

        return {"method": method, "mode": mode, "poll_config": poll_config, "body": body}, None

    def _replace_ai_placeholders(self, data: Any, parameters: Dict[str, Any]) -> Any:
        """
        替换 {{xxx}} AI 占位符

        - 如果整个值是 {{xxx}}，保留原始类型（数组、对象等）
        - 如果是混合内容，转换为字符串
        """
        if isinstance(data, str):
            # 检查是否是单个完整的 AI 占位符（如 "{{files}}"）
            single_match = AI_PLACEHOLDER.fullmatch(data)
            if single_match:
                var_name = single_match.group(1)
                if var_name in parameters:
                    return parameters[var_name]
                # AI 未提供该参数，返回 None（可选字段）
                return None

            # 混合内容，替换为字符串
            def replace_match(match):
                var_name = match.group(1)
                if var_name in parameters:
                    value = parameters[var_name]
                    return str(value) if not isinstance(value, str) else value
                return match.group(0)

            return AI_PLACEHOLDER.sub(replace_match, data)

        elif isinstance(data, dict):
            result = {}
            for k, v in data.items():
                replaced = self._replace_ai_placeholders(v, parameters)
                # 跳过 None 值（AI 未提供的可选字段）
                if replaced is not None:
                    result[k] = replaced
            return result

        elif isinstance(data, list):
            return [self._replace_ai_placeholders(item, parameters) for item in data]

        return data

    # ============================================================
    # 占位符替换
    # ============================================================

    def _replace_placeholders(
        self, data: Any, replacements: Dict[str, Any], warn_missing: bool = False
    ) -> Any:
        """
        通用占位符替换（递归处理嵌套结构）

        Args:
            data: 待替换的数据（支持 str, dict, list）
            replacements: 替换映射 {占位符名: 值}
            warn_missing: 是否对未找到的占位符发出警告

        特殊处理：
            - 如果整个字符串是单个占位符（如 "${files}"），保留原始类型（数组/对象）
            - 如果字符串包含多个占位符或混合内容，转换为字符串
        """
        if isinstance(data, str):
            # 🆕 检查是否是单个完整占位符（如 "${files}"）
            single_match = PLACEHOLDER_PATTERN.fullmatch(data)
            if single_match:
                var_name = single_match.group(1)
                if var_name in replacements:
                    # 直接返回原始值，保留类型（数组、对象等）
                    return replacements[var_name]
                if warn_missing:
                    logger.warning(f"⚠️ 占位符未解析: ${{{var_name}}}")
                return data

            # 混合内容或多个占位符，转换为字符串
            def replace_match(match):
                var_name = match.group(1)
                if var_name in replacements:
                    value = replacements[var_name]
                    return str(value) if not isinstance(value, str) else value
                if warn_missing:
                    logger.warning(f"⚠️ 占位符未解析: ${{{var_name}}}")
                return match.group(0)

            return PLACEHOLDER_PATTERN.sub(replace_match, data)

        elif isinstance(data, dict):
            return {
                k: self._replace_placeholders(v, replacements, warn_missing)
                for k, v in data.items()
            }

        elif isinstance(data, list):
            return [self._replace_placeholders(item, replacements, warn_missing) for item in data]

        return data

    def _resolve_system_placeholders(
        self, body: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        替换系统占位符（user_id, conversation_id, session_id）

        替换顺序：context → 环境变量
        """
        # 构建替换映射
        replacements = {}

        # 从 context 获取
        for key in ["user_id", "conversation_id", "session_id"]:
            if context.get(key):
                replacements[key] = context[key]

        # 从环境变量补充
        for key, value in os.environ.items():
            if key not in replacements:
                replacements[key] = value

        return self._replace_placeholders(body, replacements, warn_missing=True)

    def _resolve_env_var_in_string(self, value: str) -> str:
        """替换字符串中的环境变量占位符"""
        from urllib.parse import unquote

        if not isinstance(value, str):
            return value

        # URL 解码（处理 $%7BVAR%7D 格式）
        if "%7B" in value or "%7D" in value:
            value = unquote(value)

        def replace_env(match):
            var_name = match.group(1)
            env_value = os.environ.get(var_name)
            if env_value:
                return env_value
            logger.warning(f"⚠️ 环境变量未设置: {var_name}")
            return match.group(0)

        return PLACEHOLDER_PATTERN.sub(replace_env, value)

    def _resolve_env_vars(self, headers: Dict[str, str]) -> Dict[str, str]:
        """替换请求头中的环境变量占位符"""
        return {
            k: self._resolve_env_var_in_string(v) if isinstance(v, str) else v
            for k, v in headers.items()
        }

    # ============================================================
    # API 配置解析
    # ============================================================

    def _resolve_api_config(
        self,
        api_name: Optional[str] = None,
        url: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        apis_config: Optional[Dict[str, Any]] = None,
    ) -> tuple[Optional[str], Dict[str, str], Optional[str], Dict[str, Any]]:
        """
        解析 API 配置

        Args:
            api_name: API 名称
            url: (已废弃，必须为None)
            headers: (已废弃，必须为None)
            apis_config: API 配置字典（优先从 context 获取）

        Returns:
            (final_url, final_headers, error_message, meta_info)
        """
        final_headers = {}
        meta_info: Dict[str, Any] = {}
        apis_config = apis_config or {}

        if not api_name:
            return None, final_headers, "必须提供 api_name", meta_info

        api_config = apis_config.get(api_name)
        if not api_config:
            available = list(apis_config.keys()) if apis_config else []
            return None, final_headers, f"未找到 API: '{api_name}'，可用: {available}", meta_info

        # 获取 URL
        final_url = self._resolve_env_var_in_string(api_config.get("base_url", ""))
        if not final_url:
            return None, final_headers, f"API '{api_name}' 缺少 base_url", meta_info

        # 获取 headers
        config_headers = api_config.get("headers", {})
        final_headers = config_headers.copy()

        # 处理认证
        auth_config = api_config.get("auth")
        if auth_config:
            auth_type = auth_config.get("type", "bearer")
            auth_header = auth_config.get("header", "Authorization")
            auth_env = auth_config.get("env")

            if auth_env:
                auth_value = os.environ.get(auth_env)
                if auth_value:
                    if auth_type == "bearer":
                        final_headers[auth_header] = f"Bearer {auth_value}"
                    else:
                        final_headers[auth_header] = auth_value
                else:
                    logger.warning(f"⚠️ 认证环境变量未设置: {auth_env}")

        meta_info = {
            "api_name": api_name,
            "url": final_url,
            "capability": api_config.get("capability", ""),
        }
        return final_url, final_headers, None, meta_info

    # ============================================================
    # HTTP 请求发送
    # ============================================================

    async def _send_request(
        self,
        session: aiohttp.ClientSession,
        url: str,
        method: str,
        headers: Dict[str, str],
        body: Optional[Dict[str, Any]],
        timeout: Optional[int] = None,
    ) -> tuple[Optional[Dict[str, Any]], int]:
        """发送 HTTP 请求"""
        # 使用传入的 timeout 或默认 self.timeout
        request_timeout = timeout if timeout is not None else self.timeout

        try:
            if body and "Content-Type" not in headers:
                headers["Content-Type"] = "application/json"

            async with session.request(
                method=method,
                url=url,
                headers=headers,
                json=body if body else None,
                timeout=aiohttp.ClientTimeout(total=request_timeout),
            ) as response:
                http_status = response.status
                content_type = response.headers.get("Content-Type", "")

                if response.status in [200, 201]:
                    if "text/event-stream" in content_type:
                        logger.warning(f"⚠️ 检测到 SSE 响应，建议使用 stream=True")
                        return await self._parse_sse_response(response), http_status

                    if "application/json" in content_type:
                        return await response.json(), http_status
                    else:
                        return {"_raw_text": await response.text()}, http_status
                else:
                    error_text = await response.text()
                    logger.error(f"❌ HTTP {response.status}: {error_text[:500]}")
                    return {
                        "_error": True,
                        "_status": response.status,
                        "_message": error_text,
                    }, http_status

        except asyncio.TimeoutError:
            logger.error(f"❌ 请求超时 ({request_timeout}秒)")
            return {"_error": True, "_status": 0, "_message": "请求超时"}, 0
        except Exception as e:
            logger.error(f"❌ 请求失败: {e}")
            return {"_error": True, "_status": 0, "_message": str(e)}, 0

    async def _parse_sse_response(self, response: aiohttp.ClientResponse) -> Dict[str, Any]:
        """解析 SSE 响应"""
        try:
            raw_content = ""
            async for chunk in response.content.iter_any():
                raw_content += chunk.decode("utf-8", errors="ignore")
            return {"raw_content": raw_content}
        except Exception as e:
            logger.error(f"❌ SSE 解析异常: {e}")
            return {"error": str(e)}

    async def _send_sse_request(
        self,
        session: aiohttp.ClientSession,
        url: str,
        method: str,
        headers: Dict[str, str],
        body: Optional[Dict[str, Any]],
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """发送 SSE 流式请求"""
        # 使用传入的 timeout 或默认 self.timeout
        request_timeout = timeout if timeout is not None else self.timeout

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
                timeout=aiohttp.ClientTimeout(total=request_timeout),
            ) as response:
                if response.status not in [200, 201]:
                    error_text = await response.text()
                    logger.error(f"❌ SSE 请求失败 (HTTP {response.status})")
                    return {
                        "error": f"HTTP {response.status}: {error_text[:1000]}",
                        "http_status": response.status,
                    }

                raw_content = ""
                async for chunk in response.content.iter_any():
                    raw_content += chunk.decode("utf-8", errors="ignore")

                logger.info(f"✅ SSE 完成，共 {len(raw_content)} 字符")
                return {"raw_content": raw_content}

        except asyncio.TimeoutError:
            return {"error": "SSE 请求超时"}
        except Exception as e:
            logger.error(f"❌ SSE 异常: {e}", exc_info=True)
            return {"error": str(e)}

    async def execute_stream(
        self, params: Dict[str, Any], context: ToolContext
    ) -> AsyncGenerator[str, None]:
        """
        流式执行 API 调用（符合 BaseTool 接口）

        Args:
            params: 工具输入参数（包含 api_name, parameters）
            context: 执行上下文
        """
        # 从 params 中提取各个参数
        api_name = params.get("api_name")
        parameters = params.get("parameters")
        # 移除了 url, method, headers, body, mode 等直接调用参数的支持

        if not api_name:
            yield json.dumps({"error": "必须提供 api_name 参数"})
            return

        # 🔧 获取有效的 APIs 配置（优先从 context 获取）
        apis_config = self._get_apis_config(context)

        # 构建 kwargs（用于系统占位符替换）
        kwargs = {
            "user_id": context.user_id,
            "conversation_id": context.conversation_id,
            "session_id": context.session_id,
        }

        # ===== 简化调用方式：api_name + parameters（唯一推荐方式） =====
        poll_config = None  # 初始化 poll_config

        # 🆕 1. 确定超时时间（优先使用 API 配置）
        current_timeout = self.timeout
        api_config = apis_config.get(api_name) if api_name else None
        if api_config and "timeout" in api_config:
            current_timeout = api_config["timeout"]

        logger.info(
            f"📡 [流式调用] api_name={api_name}, parameters={list(parameters.keys()) if parameters else 'None'}"
        )

        # 允许 parameters 为空，只要 input_schema 允许
        safe_parameters = parameters or {}

        # 🆕 2. 输入校验
        if api_config and "input_schema" in api_config:
            schema = api_config["input_schema"]
            validation_error = self._validate_parameters(safe_parameters, schema)
            if validation_error:
                logger.warning(f"❌ 参数校验失败: {validation_error}")
                yield json.dumps({"error": f"参数校验失败: {validation_error}"})
                return

        request_config, error = self._build_request_from_config(
            api_name, safe_parameters, apis_config
        )
        if error:
            yield json.dumps({"error": error})
            return

        method = request_config["method"]
        mode = request_config["mode"]
        poll_config = request_config.get("poll_config")  # 🔧 修复：提取 poll_config
        body = request_config["body"]

        final_url, final_headers, error, _ = self._resolve_api_config(
            api_name, None, None, apis_config
        )

        if not final_url or error:
            yield json.dumps({"error": error or "无法解析 API 配置"})
            return

        final_headers = self._resolve_env_vars(final_headers)
        if body:
            body = self._resolve_system_placeholders(body, kwargs)

        if mode != "stream":
            # 非流式模式：调用 execute 方法
            result = await self.execute(params, context)
            yield json.dumps(result, ensure_ascii=False)
            return

        logger.info(f"🌊 流式执行: {method} {final_url}")

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
                    timeout=aiohttp.ClientTimeout(total=current_timeout),
                ) as response:
                    if response.status not in [200, 201]:
                        error_text = await response.text()
                        yield json.dumps(
                            {
                                "error": f"HTTP {response.status}: {error_text[:1000]}",
                                "http_status": response.status,
                            }
                        )
                        return

                    async for chunk in response.content.iter_any():
                        decoded = chunk.decode("utf-8", errors="ignore")
                        if decoded:
                            yield decoded

        except asyncio.TimeoutError:
            yield json.dumps({"error": "SSE 请求超时"})
        except Exception as e:
            yield json.dumps({"error": str(e)})

    # ============================================================
    # 异步轮询
    # ============================================================

    def _get_nested_value(self, data: Dict[str, Any], field_path: str) -> Any:
        """
        从嵌套结构中获取值

        支持：点分隔路径（data.execute_id）、数组索引（data.0.output）
        """
        if not field_path or not data:
            return None

        keys = field_path.split(".")
        value = data

        for key in keys:
            if value is None:
                return None

            if isinstance(value, dict):
                value = value.get(key)
            elif isinstance(value, list):
                try:
                    index = int(key)
                    value = value[index] if 0 <= index < len(value) else None
                except ValueError:
                    return None
            else:
                return None

        return value

    # Coze API 错误码映射（默认）
    DEFAULT_COZE_ERROR_MESSAGES: Dict[int, str] = {
        4000: "参数无效",
        4001: "会话不存在",
        4008: "超出每日配额",
        4009: "系统繁忙，请稍后重试",
        4011: "余额不足",
        4019: "账户欠费",
        4020: "超出 RPM 限制",
        4100: "认证无效",
        4101: "权限不足",
        4105: "内容敏感",
        4314: "执行记录不存在",
        5000: "服务器内部错误",
    }

    def _get_error_message(
        self, code: int, default_msg: str = "", error_mapping: Optional[Dict[int, str]] = None
    ) -> str:
        """
        获取错误码的友好提示
        优先级: 自定义映射 > 默认 Coze 映射
        """
        mapping = error_mapping or self.DEFAULT_COZE_ERROR_MESSAGES
        # 尝试转换 code 为 int
        try:
            code_int = int(code)
            if code_int in mapping:
                return mapping[code_int]
        except (ValueError, TypeError):
            pass

        # 尝试直接作为 key 查找 (兼容字符串 key)
        if str(code) in mapping:
            return mapping[str(code)]

        return default_msg or f"未知错误 (code={code})"

    async def _poll_for_result(
        self,
        session: aiohttp.ClientSession,
        initial_response: Dict[str, Any],
        poll_config: Dict[str, Any],
        headers: Dict[str, str],
        request_body: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        轮询异步任务结果

        poll_config 配置项：
        - status_url_template: URL 模板
        - execute_id_field: execute_id 字段路径
        - body_vars: 从 request_body 提取的变量列表
        - status_field: 状态字段路径
        - success_status: 成功状态值
        - failed_status: 失败状态值
        - check_code: 是否检查 code 字段
        - error_mapping: 错误码映射 {code: message} (🆕 支持自定义错误码)
        """
        request_body = request_body or {}

        # 1. 构建 URL 变量
        url_vars: Dict[str, str] = {}

        # 从 body 提取变量
        for var_name in poll_config.get("body_vars", []):
            if var_value := request_body.get(var_name):
                url_vars[var_name] = str(var_value)

        # 从响应提取 execute_id
        execute_id_field = poll_config.get("execute_id_field", "execute_id")
        execute_id = self._get_nested_value(initial_response, execute_id_field)

        if not execute_id:
            legacy_field = poll_config.get("status_url_field", "task_id")
            execute_id = self._get_nested_value(
                initial_response, legacy_field
            ) or initial_response.get(legacy_field)

        if execute_id:
            url_vars["execute_id"] = str(execute_id)
            url_vars["task_id"] = str(execute_id)
            logger.info(f"🔑 execute_id: {execute_id}")
        else:
            logger.warning(f"⚠️ 未找到 execute_id")
            return initial_response

        # 2. 构建轮询 URL
        status_url_template = poll_config.get("status_url_template", "")
        if not status_url_template:
            logger.error("❌ 缺少 status_url_template")
            return initial_response

        try:
            status_url = status_url_template.format(**url_vars)
            logger.info(f"🔗 轮询 URL: {status_url}")
        except KeyError as e:
            logger.error(f"❌ URL 变量缺失: {e}")
            return initial_response

        # 3. 轮询配置
        success_status = poll_config.get("success_status", "Success")
        failed_status = poll_config.get("failed_status", "Fail")
        status_field = poll_config.get("status_field", "status")
        check_code = poll_config.get("check_code", True)
        error_mapping = poll_config.get("error_mapping")  # 🆕 获取自定义错误映射

        # 4. 开始轮询
        for i in range(self.max_polls):
            try:
                async with session.get(
                    status_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        result = await response.json()

                        # 调试日志（每 10 次打印一次）
                        if i % 10 == 0:
                            logger.debug(
                                f"🔍 轮询响应: {json.dumps(result, ensure_ascii=False)[:500]}"
                            )

                        # 检查 code 字段
                        if check_code:
                            api_code = result.get("code")
                            if api_code is not None and api_code != 0:
                                error_msg = self._get_error_message(
                                    api_code, result.get("msg", ""), error_mapping
                                )
                                logger.error(f"❌ API 错误 (code={api_code}): {error_msg}")
                                return {
                                    "error": error_msg,
                                    "code": api_code,
                                    "raw_response": result,
                                }

                        # 获取状态
                        status = self._get_nested_value(result, status_field)
                        if status is None:
                            status = result.get("task_status") or result.get("status")

                        # 判断成功
                        is_success = False
                        if success_status == "__non_empty__":
                            is_success = (
                                status is not None
                                and status != ""
                                and status != []
                                and status != {}
                            )
                        else:
                            is_success = status == success_status

                        if is_success:
                            logger.info(f"✅ 任务完成!")
                            return result

                        # 判断失败
                        is_failed = False
                        if failed_status == "__error__":
                            error_val = self._get_nested_value(
                                result, "data.0.error"
                            ) or result.get("error")
                            is_failed = error_val is not None and error_val != ""
                        else:
                            is_failed = status == failed_status

                        if is_failed:
                            error_msg = (
                                self._get_nested_value(result, "data.0.error_message")
                                or result.get("error_message")
                                or result.get("msg")
                                or "未知错误"
                            )
                            logger.error(f"❌ 任务失败: {error_msg}")
                            return {"error": f"任务失败: {error_msg}", "raw_response": result}

                        # 进度日志
                        if i % 10 == 0:
                            logger.info(f"⏳ 处理中... ({i * self.poll_interval}秒)")

                    else:
                        error_text = await response.text()
                        logger.warning(f"⚠️ 轮询失败 (HTTP {response.status}): {error_text[:200]}")

                        try:
                            error_json = json.loads(error_text)
                            if api_code := error_json.get("code"):
                                return {
                                    "error": self._get_error_message(
                                        api_code, error_mapping=error_mapping
                                    ),
                                    "code": api_code,
                                }
                        except json.JSONDecodeError:
                            pass

                await asyncio.sleep(self.poll_interval)

            except Exception as e:
                logger.warning(f"⚠️ 轮询错误: {e}")
                await asyncio.sleep(self.poll_interval)

        logger.error(f"❌ 轮询超时 ({self.max_polls * self.poll_interval}秒)")
        return {"error": f"任务轮询超时（{self.max_polls * self.poll_interval}秒）"}
