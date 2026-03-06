"""
云端 Agent 客户端

调用远端 ZenFlux Agent 的 /api/v1/chat 接口（zenflux SSE 格式），
供 CloudAgentTool 消费。

endpoint_mode:
  "direct" — 直连云端 /api/v1/chat（Phase 1）
  "proxy"  — 走独立 ACP 代理 /acp/tasks（Phase 1.5+，预留）
"""

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from logger import get_logger

logger = get_logger(__name__)

_cloud_client: Optional["CloudClient"] = None
# 按实例缓存的云端客户端（实例 config.yaml cloud.enabled: true 时使用）
_instance_clients: Dict[str, "CloudClient"] = {}

JWT_EXPIRY_BUFFER_SECONDS = 300  # 提前 5 分钟视为过期


class CloudClientError(Exception):
    """云端客户端错误"""


class CloudClient:
    """远端 ZenFlux Agent HTTP 客户端"""

    def __init__(
        self,
        cloud_url: str = "https://agent.dazee.ai",
        user_id: str = "local_agent",
        jwt_token: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        endpoint_mode: str = "direct",
    ):
        self.cloud_url = cloud_url.rstrip("/")
        self.user_id = user_id
        self.jwt_token = jwt_token
        self.endpoint_mode = endpoint_mode
        self._username = username
        self._password = password
        self._token_obtained_at: float = time.time() if jwt_token else 0
        self._token_ttl: float = 86400  # 默认 24h，与云端 JWT 一致
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10, read=600, write=30, pool=10),
            follow_redirects=True,
        )

    async def login(self, username: Optional[str] = None, password: Optional[str] = None) -> str:
        """
        调用云端 POST /api/v1/auth/login 获取 JWT token。

        Args:
            username: 用户名（不传则使用构造时保存的凭据）
            password: 密码

        Returns:
            JWT token 字符串

        Raises:
            CloudClientError: 登录失败
        """
        uname = username or self._username
        pwd = password or self._password
        if not uname or not pwd:
            raise CloudClientError("未提供登录凭据（username/password）")

        url = f"{self.cloud_url}/api/v1/auth/login"
        try:
            resp = await self._http.post(
                url, json={"username": uname, "password": pwd}, timeout=10.0,
            )
            if resp.status_code != 200:
                raise CloudClientError(f"登录失败 {resp.status_code}: {resp.text[:300]}")

            data = resp.json()
            self.jwt_token = data["token"]
            self._token_obtained_at = time.time()
            self._username = uname
            self._password = pwd

            user_info = data.get("user", {})
            if user_info.get("id"):
                self.user_id = user_info["id"]

            logger.info("云端登录成功: user=%s", uname)
            return self.jwt_token
        except httpx.HTTPError as e:
            raise CloudClientError(f"登录 HTTP 错误: {e}") from e

    async def _ensure_auth(self) -> None:
        """确保持有有效 JWT；过期则自动重新登录。"""
        if self.jwt_token and not self._is_token_expired():
            return
        if self._username and self._password:
            logger.info("JWT 过期或缺失，自动重新登录...")
            await self.login()
            return
        if not self.jwt_token:
            logger.warning("无 JWT 且无登录凭据，请求将以匿名身份发送")

    def _is_token_expired(self) -> bool:
        if not self._token_obtained_at:
            return True
        return (time.time() - self._token_obtained_at) > (self._token_ttl - JWT_EXPIRY_BUFFER_SECONDS)

    async def chat_stream(
        self,
        message: str,
        *,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        files: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式调用云端 /api/v1/chat（zenflux 格式 SSE）

        Args:
            message: 发送给云端 Agent 的消息
            user_id: 覆盖默认 user_id
            conversation_id: 可选，延续已有对话
            agent_id: 可选，指定云端 Agent 实例
            files: 可选，文件引用列表（透传到云端 ChatRequest.files）

        Yields:
            解析后的 SSE 事件字典，包含 type、seq、data 等字段
        """
        await self._ensure_auth()
        url = f"{self.cloud_url}/api/v1/chat?format=zenflux"

        body: Dict[str, Any] = {
            "message": message,
            "userId": user_id or self.user_id,
            "stream": True,
        }
        if conversation_id:
            body["conversationId"] = conversation_id
        if agent_id:
            body["agentId"] = agent_id
        if files:
            body["files"] = files

        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self.jwt_token:
            headers["Authorization"] = f"Bearer {self.jwt_token}"

        try:
            async with self._http.stream(
                "POST", url, json=body, headers=headers
            ) as response:
                if response.status_code != 200:
                    text = ""
                    async for chunk in response.aiter_text():
                        text += chunk
                    raise CloudClientError(
                        f"云端返回 {response.status_code}: {text[:500]}"
                    )

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:].strip()
                    if not raw:
                        continue
                    try:
                        event = json.loads(raw)
                        yield event
                    except json.JSONDecodeError:
                        logger.warning("SSE JSON 解析失败: %s", raw[:200])

        except httpx.ConnectError as e:
            raise CloudClientError(f"无法连接云端 {self.cloud_url}: {e}") from e
        except httpx.ReadTimeout as e:
            raise CloudClientError("云端响应超时（600s）") from e
        except httpx.HTTPError as e:
            raise CloudClientError(f"云端 HTTP 错误: {e}") from e

    async def upload_file(
        self,
        file_content: bytes,
        filename: str,
        mime_type: str,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        上传文件到云端 S3（调用 POST /api/v1/files/upload）

        Args:
            file_content: 文件二进制内容
            filename: 文件名
            mime_type: MIME 类型
            user_id: 用户 ID

        Returns:
            {"file_url": "https://s3...", "file_name": ..., "file_size": ..., "file_type": ...}

        Raises:
            CloudClientError: 上传失败
        """
        await self._ensure_auth()
        url = f"{self.cloud_url}/api/v1/files/upload"
        headers: Dict[str, str] = {}
        if self.jwt_token:
            headers["Authorization"] = f"Bearer {self.jwt_token}"

        try:
            resp = await self._http.post(
                url,
                files={"file": (filename, file_content, mime_type)},
                data={"user_id": user_id or self.user_id},
                headers=headers,
                timeout=60.0,
            )
            if resp.status_code != 200:
                raise CloudClientError(
                    f"文件上传失败 {resp.status_code}: {resp.text[:500]}"
                )
            result = resp.json()
            data = result.get("data", result)
            logger.info("文件已上传到云端: %s -> %s", filename, data.get("file_url", "")[:80])
            return data
        except httpx.HTTPError as e:
            raise CloudClientError(f"文件上传 HTTP 错误: {e}") from e

    async def health_check(self) -> bool:
        """检查云端是否可达"""
        try:
            resp = await self._http.get(
                f"{self.cloud_url}/health", timeout=5.0
            )
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def chat_stream_with_tracking(
        self,
        message: str,
        *,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        files: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator["CloudStreamEvent", None]:
        """
        带本地追踪的流式对话：解析 SSE 并产出结构化的 CloudStreamEvent。

        在 chat_stream() 基础上增加：
        - 自动提取 conversation_id
        - 维护 content block 状态机（跟踪 tool_use/thinking/text）
        - 产出结构化事件，供 cloud_agent 工具和 TaskManager 消费
        """
        cloud_conv_id: Optional[str] = None
        current_block_type: Optional[str] = None
        current_tool_name: Optional[str] = None

        async for raw in self.chat_stream(
            message,
            user_id=user_id,
            conversation_id=conversation_id,
            agent_id=agent_id,
            files=files,
        ):
            etype = raw.get("type", "")

            if etype in ("session_start", "conversation_start"):
                data = raw.get("data", {})
                cid = data.get("conversation_id") or raw.get("conversation_id")
                if cid:
                    cloud_conv_id = cid
                yield CloudStreamEvent(
                    kind="session_info",
                    conversation_id=cloud_conv_id,
                    raw=raw,
                )

            elif etype == "content_start":
                block = raw.get("data", {}).get("content_block", {})
                current_block_type = block.get("type")

                if current_block_type == "tool_use":
                    current_tool_name = block.get("name", "unknown")
                    yield CloudStreamEvent(
                        kind="tool_start",
                        tool_name=current_tool_name,
                        conversation_id=cloud_conv_id,
                        raw=raw,
                    )
                elif current_block_type == "thinking":
                    yield CloudStreamEvent(
                        kind="thinking_start",
                        conversation_id=cloud_conv_id,
                        raw=raw,
                    )

            elif etype == "content_delta":
                delta = raw.get("data", {}).get("delta", "")
                if current_block_type == "text" and isinstance(delta, str):
                    yield CloudStreamEvent(
                        kind="text_delta",
                        text=delta,
                        conversation_id=cloud_conv_id,
                        raw=raw,
                    )

            elif etype == "content_stop":
                if current_block_type == "tool_use" and current_tool_name:
                    yield CloudStreamEvent(
                        kind="tool_end",
                        tool_name=current_tool_name,
                        conversation_id=cloud_conv_id,
                        raw=raw,
                    )
                current_block_type = None
                current_tool_name = None

            elif etype == "message_stop":
                yield CloudStreamEvent(
                    kind="completed",
                    conversation_id=cloud_conv_id,
                    raw=raw,
                )
                break

    async def close(self):
        """关闭 HTTP 连接"""
        await self._http.aclose()


@dataclass
class CloudStreamEvent:
    """chat_stream_with_tracking 产出的结构化事件"""

    kind: str  # session_info / tool_start / tool_end / thinking_start / text_delta / completed
    text: str = ""
    tool_name: str = ""
    conversation_id: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


def get_cloud_client() -> CloudClient:
    """获取全局 CloudClient 单例"""
    global _cloud_client
    if _cloud_client is None:
        _cloud_client = CloudClient()
    return _cloud_client


def configure_cloud_client(
    cloud_url: str,
    user_id: str = "local_agent",
    jwt_token: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    endpoint_mode: str = "direct",
) -> CloudClient:
    """配置并重建全局 CloudClient（支持 JWT 直传或用户名密码自动登录）"""
    global _cloud_client
    if _cloud_client is not None:
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_cloud_client.close())
        except RuntimeError:
            pass
    _cloud_client = CloudClient(
        cloud_url=cloud_url,
        user_id=user_id,
        jwt_token=jwt_token,
        username=username,
        password=password,
        endpoint_mode=endpoint_mode,
    )
    return _cloud_client


async def get_cloud_client_for_instance(instance_name: str) -> Optional["CloudClient"]:
    """
    按实例配置返回云端客户端。仅当该实例 config.yaml 中 cloud.enabled 为 true 时返回客户端，否则返回 None。
    同一实例的客户端会缓存复用。
    """
    global _instance_clients
    if not instance_name:
        return None
    try:
        from utils.instance_loader import load_instance_config

        config = await load_instance_config(instance_name)
        raw = config.raw_config or {}
        cloud_cfg = raw.get("cloud") or {}
        # 环境变量兜底：CLOUD_ENABLED=true 时即使 config.yaml 缺失也能启用
        enabled = cloud_cfg.get("enabled", False) or os.getenv("CLOUD_ENABLED", "").lower() in ("true", "1", "yes")
        if not enabled:
            return None
        cloud_url = (cloud_cfg.get("url") or "").strip() or os.getenv("CLOUD_URL", "https://agent.dazee.ai")
        username = os.getenv("CLOUD_USERNAME") or cloud_cfg.get("username") or None
        password = os.getenv("CLOUD_PASSWORD") or cloud_cfg.get("password") or None
        if username:
            username = str(username).strip() or None
        if password:
            password = str(password).strip() or None
    except Exception as e:
        logger.warning("加载实例 %s 云端配置失败: %s", instance_name, e)
        return None

    if instance_name in _instance_clients:
        c = _instance_clients[instance_name]
        if c.cloud_url.rstrip("/") == cloud_url.rstrip("/"):
            return c
        try:
            import asyncio
            loop = asyncio.get_running_loop()
            loop.create_task(c.close())
        except RuntimeError:
            pass
        del _instance_clients[instance_name]

    client = CloudClient(
        cloud_url=cloud_url,
        username=username,
        password=password,
    )
    _instance_clients[instance_name] = client
    return client
