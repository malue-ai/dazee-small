"""
飞书类型定义
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Literal


@dataclass
class FeishuAccount:
    """
    飞书账户配置
    
    Attributes:
        app_id: 应用 ID
        app_secret: 应用密钥
        verification_token: 事件订阅验证令牌
        encrypt_key: 加密密钥（可选）
        enabled: 是否启用
        dm_policy: 私聊策略
        allow_from: 私聊白名单
        group_policy: 群聊策略
        group_allow_from: 群聊白名单
        require_mention: 群聊是否需要 @机器人
        groups: 群组特定配置
        history_limit: 历史消息数限制
        media_max_mb: 媒体大小限制
        stream_mode: 流式模式
    """
    app_id: str = ""
    app_secret: str = ""
    verification_token: str = ""
    encrypt_key: str = ""
    enabled: bool = True

    # 机器人身份（可选，用于严格的 @ 触发）
    # - bot_open_id: 机器人作为“用户”在飞书内的 open_id
    # - bot_user_id: 机器人作为“用户”在飞书内的 user_id
    # 如果未配置，会在运行时通过 API 自动获取并缓存
    bot_open_id: str = ""
    bot_user_id: str = ""
    
    # 私聊策略
    dm_policy: Literal["open", "pairing", "disabled"] = "open"
    allow_from: List[str] = field(default_factory=list)
    
    # 群聊策略
    group_policy: Literal["open", "allowlist", "disabled"] = "open"
    group_allow_from: List[str] = field(default_factory=list)
    require_mention: bool = True
    
    # 群组特定配置
    groups: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # 高级配置
    history_limit: int = 20
    media_max_mb: int = 20
    stream_mode: Literal["off", "edit"] = "edit"
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FeishuAccount":
        """从字典创建账户配置"""
        return cls(
            app_id=data.get("app_id", ""),
            app_secret=data.get("app_secret", ""),
            verification_token=data.get("verification_token", ""),
            encrypt_key=data.get("encrypt_key", ""),
            enabled=data.get("enabled", True),
            bot_open_id=data.get("bot_open_id", ""),
            bot_user_id=data.get("bot_user_id", ""),
            dm_policy=data.get("dm_policy", "open"),
            allow_from=data.get("allow_from", []),
            group_policy=data.get("group_policy", "open"),
            group_allow_from=data.get("group_allow_from", []),
            require_mention=data.get("require_mention", True),
            groups=data.get("groups", {}),
            history_limit=data.get("history_limit", 20),
            media_max_mb=data.get("media_max_mb", 20),
            stream_mode=data.get("stream_mode", "edit"),
        )


@dataclass
class FeishuMessage:
    """
    飞书消息
    
    Attributes:
        message_id: 消息 ID
        chat_id: 聊天 ID
        chat_type: 聊天类型
        msg_type: 消息类型
        content: 消息内容
        sender_id: 发送者 ID
        sender_name: 发送者名称
        mentions: @ 的用户
        thread_id: 线程 ID
        timestamp: 时间戳
    """
    message_id: str
    chat_id: str
    chat_type: Literal["p2p", "group"]
    msg_type: str
    content: str
    sender_id: str
    sender_name: str = ""
    mentions: List[Dict[str, Any]] = field(default_factory=list)
    thread_id: Optional[str] = None
    timestamp: Optional[str] = None
    
    @classmethod
    def from_event(cls, event: Dict[str, Any]) -> "FeishuMessage":
        """从事件数据创建消息"""
        message = event.get("message", {})
        sender = event.get("sender", {})
        sender_id_obj = sender.get("sender_id", {})
        
        # 解析消息内容
        content = ""
        content_str = message.get("content", "{}")
        msg_type = message.get("message_type", "text")
        
        import json
        try:
            content_obj = json.loads(content_str)
            if msg_type == "text":
                content = content_obj.get("text", "")
            elif msg_type == "post":
                # 富文本，提取纯文本
                content = cls._extract_post_text(content_obj)
            else:
                content = content_str
        except json.JSONDecodeError:
            content = content_str
        
        # 解析 @ 信息
        mentions = []
        if message.get("mentions"):
            mentions = message.get("mentions", [])
        
        return cls(
            message_id=message.get("message_id", ""),
            chat_id=message.get("chat_id", ""),
            chat_type="p2p" if message.get("chat_type") == "p2p" else "group",
            msg_type=msg_type,
            content=content,
            sender_id=sender_id_obj.get("open_id", ""),
            sender_name=sender.get("sender_id", {}).get("user_id", ""),
            mentions=mentions,
            thread_id=message.get("thread_id"),
            timestamp=message.get("create_time"),
        )
    
    @staticmethod
    def _extract_post_text(content: Dict[str, Any]) -> str:
        """从富文本消息提取纯文本"""
        texts = []
        for lang, post in content.items():
            if isinstance(post, dict):
                for para in post.get("content", []):
                    for element in para:
                        if element.get("tag") == "text":
                            texts.append(element.get("text", ""))
        return " ".join(texts)
