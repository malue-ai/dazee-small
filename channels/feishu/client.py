"""
飞书 API 客户端

负责：
- 获取 access_token
- 发送消息
- 编辑消息
- 上传媒体
"""

import time
import json
from typing import Dict, Any, Optional, List
import httpx
from channels.feishu.types import FeishuAccount
from logger import get_logger

logger = get_logger("feishu_client")


class FeishuClient:
    """
    飞书 API 客户端
    
    使用示例：
    ```python
    client = FeishuClient(account)
    
    # 发送文本
    await client.send_text("chat_id", "Hello!")
    
    # 发送卡片
    await client.send_card("chat_id", card_content)
    
    # 编辑消息
    await client.update_message("message_id", "New text")
    ```
    """
    
    BASE_URL = "https://open.feishu.cn/open-apis"
    
    def __init__(self, account: FeishuAccount):
        """
        初始化飞书客户端
        
        Args:
            account: 飞书账户配置
        """
        self.account = account
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0
        self._http_client: Optional[httpx.AsyncClient] = None
        self._bot_ids_cache: Optional[set[str]] = None
    
    async def _get_http_client(self) -> httpx.AsyncClient:
        """获取 HTTP 客户端"""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client
    
    async def close(self):
        """关闭 HTTP 客户端"""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None
    
    async def get_access_token(self) -> str:
        """
        获取 tenant_access_token
        
        自动缓存和刷新
        
        Returns:
            access_token
        """
        # 检查缓存（提前 5 分钟刷新）
        if self._access_token and time.time() < self._token_expires_at - 300:
            return self._access_token
        
        client = await self._get_http_client()
        
        response = await client.post(
            f"{self.BASE_URL}/auth/v3/tenant_access_token/internal",
            json={
                "app_id": self.account.app_id,
                "app_secret": self.account.app_secret
            }
        )
        
        data = response.json()
        
        if data.get("code") != 0:
            raise Exception(f"获取 access_token 失败: {data.get('msg')}")
        
        self._access_token = data["tenant_access_token"]
        self._token_expires_at = time.time() + data.get("expire", 7200)
        
        logger.debug(f"✅ 获取飞书 access_token 成功")
        return self._access_token
    
    async def _request(
        self,
        method: str,
        path: str,
        body: Dict[str, Any] = None,
        params: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        发送 API 请求
        
        Args:
            method: HTTP 方法
            path: API 路径
            body: 请求体
            params: 查询参数
            
        Returns:
            响应数据
        """
        token = await self.get_access_token()
        client = await self._get_http_client()
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        response = await client.request(
            method=method,
            url=f"{self.BASE_URL}{path}",
            headers=headers,
            json=body,
            params=params
        )
        
        return response.json()

    # ===========================================================================
    # 机器人信息（用于严格 @ 触发）
    # ===========================================================================

    async def get_bot_info(self) -> Dict[str, Any]:
        """
        获取机器人信息

        Returns:
            机器人信息（原始响应）
        """
        # 该接口在不同文档版本中可能略有差异，这里做兼容处理：
        # - 优先尝试 /bot/v3/info
        # - 如果失败再尝试 /bot/v3/info/（部分网关可能要求结尾斜杠）
        resp = await self._request(method="GET", path="/bot/v3/info")
        if isinstance(resp, dict) and resp.get("code") == 0:
            return resp
        # 兜底尝试
        return await self._request(method="GET", path="/bot/v3/info/")

    async def get_bot_ids(self) -> set[str]:
        """
        获取机器人可用于匹配的 ID 集合

        说明：
        - 事件回调中的 mentions 可能包含 open_id / user_id / union_id
        - 为了在群聊中“只在 @机器人时回复”，这里尽量收集多种 ID 以提高匹配成功率
        """
        if self._bot_ids_cache is not None:
            return self._bot_ids_cache

        ids: set[str] = set()

        # 配置优先（避免额外网络请求）
        if getattr(self.account, "bot_open_id", ""):
            ids.add(self.account.bot_open_id)
        if getattr(self.account, "bot_user_id", ""):
            ids.add(self.account.bot_user_id)

        if ids:
            self._bot_ids_cache = ids
            return ids

        # 通过 API 自动获取
        try:
            info = await self.get_bot_info()
        except Exception as e:
            logger.warning(f"获取机器人信息失败: {e}")
            self._bot_ids_cache = set()
            return self._bot_ids_cache

        # 兼容多种返回结构
        def pick(d: Dict[str, Any], keys: List[str]) -> Optional[Any]:
            cur: Any = d
            for k in keys:
                if not isinstance(cur, dict):
                    return None
                cur = cur.get(k)
            return cur

        candidates: List[Optional[str]] = [
            pick(info, ["data", "bot", "open_id"]),
            pick(info, ["data", "bot", "user_id"]),
            pick(info, ["data", "bot", "union_id"]),
            pick(info, ["data", "open_id"]),
            pick(info, ["data", "user_id"]),
            pick(info, ["open_id"]),
            pick(info, ["user_id"]),
        ]

        for c in candidates:
            if isinstance(c, str) and c:
                ids.add(c)

        self._bot_ids_cache = ids
        return ids
    
    # ===========================================================================
    # 消息发送
    # ===========================================================================
    
    async def send_text(
        self,
        receive_id: str,
        text: str,
        receive_id_type: str = "chat_id",
        reply_to: str = None
    ) -> Dict[str, Any]:
        """
        发送文本消息
        
        Args:
            receive_id: 接收者 ID
            text: 消息内容
            receive_id_type: ID 类型（chat_id/open_id/user_id）
            reply_to: 回复的消息 ID
            
        Returns:
            API 响应
        """
        body = {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": json.dumps({"text": text})
        }
        
        return await self._request(
            method="POST",
            path="/im/v1/messages",
            body=body,
            params={"receive_id_type": receive_id_type}
        )
    
    async def send_card(
        self,
        receive_id: str,
        card: Dict[str, Any],
        receive_id_type: str = "chat_id"
    ) -> Dict[str, Any]:
        """
        发送卡片消息
        
        Args:
            receive_id: 接收者 ID
            card: 卡片内容
            receive_id_type: ID 类型
            
        Returns:
            API 响应
        """
        body = {
            "receive_id": receive_id,
            "msg_type": "interactive",
            "content": json.dumps(card)
        }
        
        return await self._request(
            method="POST",
            path="/im/v1/messages",
            body=body,
            params={"receive_id_type": receive_id_type}
        )
    
    async def send_image(
        self,
        receive_id: str,
        image_key: str,
        receive_id_type: str = "chat_id"
    ) -> Dict[str, Any]:
        """
        发送图片消息
        
        Args:
            receive_id: 接收者 ID
            image_key: 图片 key
            receive_id_type: ID 类型
            
        Returns:
            API 响应
        """
        body = {
            "receive_id": receive_id,
            "msg_type": "image",
            "content": json.dumps({"image_key": image_key})
        }
        
        return await self._request(
            method="POST",
            path="/im/v1/messages",
            body=body,
            params={"receive_id_type": receive_id_type}
        )
    
    async def send_file(
        self,
        receive_id: str,
        file_key: str,
        receive_id_type: str = "chat_id"
    ) -> Dict[str, Any]:
        """
        发送文件消息
        
        Args:
            receive_id: 接收者 ID
            file_key: 文件 key
            receive_id_type: ID 类型
            
        Returns:
            API 响应
        """
        body = {
            "receive_id": receive_id,
            "msg_type": "file",
            "content": json.dumps({"file_key": file_key})
        }
        
        return await self._request(
            method="POST",
            path="/im/v1/messages",
            body=body,
            params={"receive_id_type": receive_id_type}
        )
    
    async def reply_text(
        self,
        message_id: str,
        text: str
    ) -> Dict[str, Any]:
        """
        回复消息
        
        Args:
            message_id: 原消息 ID
            text: 回复内容
            
        Returns:
            API 响应
        """
        body = {
            "msg_type": "text",
            "content": json.dumps({"text": text})
        }
        
        return await self._request(
            method="POST",
            path=f"/im/v1/messages/{message_id}/reply",
            body=body
        )
    
    async def reply_card(
        self,
        message_id: str,
        card: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        用卡片回复消息
        
        Args:
            message_id: 原消息 ID
            card: 卡片内容
            
        Returns:
            API 响应
        """
        body = {
            "msg_type": "interactive",
            "content": json.dumps(card)
        }
        
        return await self._request(
            method="POST",
            path=f"/im/v1/messages/{message_id}/reply",
            body=body
        )
    
    # ===========================================================================
    # 消息编辑（流式输出用）
    # ===========================================================================
    
    async def update_message(
        self,
        message_id: str,
        text: str
    ) -> Dict[str, Any]:
        """
        更新消息内容（用于流式输出）
        
        Args:
            message_id: 消息 ID
            text: 新内容
            
        Returns:
            API 响应
        """
        body = {
            "msg_type": "text",
            "content": json.dumps({"text": text})
        }
        
        return await self._request(
            method="PATCH",
            path=f"/im/v1/messages/{message_id}",
            body=body
        )
    
    async def update_card(
        self,
        message_id: str,
        card: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        更新卡片消息
        
        Args:
            message_id: 消息 ID
            card: 新卡片内容
            
        Returns:
            API 响应
        """
        body = {
            "msg_type": "interactive",
            "content": json.dumps(card)
        }
        
        return await self._request(
            method="PATCH",
            path=f"/im/v1/messages/{message_id}",
            body=body
        )
    
    # ===========================================================================
    # 媒体上传
    # ===========================================================================
    
    async def upload_image(
        self,
        image_data: bytes,
        image_type: str = "message"
    ) -> str:
        """
        上传图片
        
        Args:
            image_data: 图片数据
            image_type: 图片类型（message/avatar）
            
        Returns:
            image_key
        """
        token = await self.get_access_token()
        client = await self._get_http_client()
        
        response = await client.post(
            f"{self.BASE_URL}/im/v1/images",
            headers={"Authorization": f"Bearer {token}"},
            files={"image": ("image.png", image_data, "image/png")},
            data={"image_type": image_type}
        )
        
        data = response.json()
        
        if data.get("code") != 0:
            raise Exception(f"上传图片失败: {data.get('msg')}")
        
        return data.get("data", {}).get("image_key", "")
    
    async def upload_file(
        self,
        file_data: bytes,
        file_name: str,
        file_type: str = "stream"
    ) -> str:
        """
        上传文件
        
        Args:
            file_data: 文件数据
            file_name: 文件名
            file_type: 文件类型
            
        Returns:
            file_key
        """
        token = await self.get_access_token()
        client = await self._get_http_client()
        
        response = await client.post(
            f"{self.BASE_URL}/im/v1/files",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": (file_name, file_data)},
            data={"file_type": file_type, "file_name": file_name}
        )
        
        data = response.json()
        
        if data.get("code") != 0:
            raise Exception(f"上传文件失败: {data.get('msg')}")
        
        return data.get("data", {}).get("file_key", "")
    
    # ===========================================================================
    # 用户信息
    # ===========================================================================
    
    async def get_user_info(self, user_id: str, id_type: str = "open_id") -> Dict[str, Any]:
        """
        获取用户信息
        
        Args:
            user_id: 用户 ID
            id_type: ID 类型
            
        Returns:
            用户信息
        """
        return await self._request(
            method="GET",
            path=f"/contact/v3/users/{user_id}",
            params={"user_id_type": id_type}
        )
