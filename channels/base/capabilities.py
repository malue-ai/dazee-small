"""
渠道功能声明

定义渠道元数据和功能能力
"""

from dataclasses import dataclass, field
from typing import List, Literal, Optional


@dataclass
class ChannelMeta:
    """
    渠道元数据
    
    Attributes:
        id: 渠道 ID
        label: 显示名称
        description: 描述
        docs_path: 文档路径
        icon: 图标（URL 或 emoji）
        aliases: 别名列表
    """
    id: str
    label: str
    description: str = ""
    docs_path: str = ""
    icon: str = ""
    aliases: List[str] = field(default_factory=list)


@dataclass
class ChannelCapabilities:
    """
    渠道功能声明
    
    声明渠道支持的功能，用于：
    1. 功能检测（是否支持某功能）
    2. UI 展示（显示可用功能）
    3. 路由决策（选择合适的处理方式）
    
    Attributes:
        chat_types: 支持的聊天类型
        media: 支持媒体（图片/视频/文件）
        cards: 支持卡片消息
        reactions: 支持表情反应
        threads: 支持线程/话题
        streaming: 支持流式输出
        edit: 支持编辑消息
        unsend: 支持撤回消息
        reply: 支持回复消息
        mentions: 支持 @用户
        polls: 支持投票
        buttons: 支持按钮交互
        rich_text: 支持富文本
        markdown: 支持 Markdown
    """
    chat_types: List[Literal["direct", "group", "channel", "thread"]] = field(
        default_factory=lambda: ["direct", "group"]
    )
    media: bool = False
    cards: bool = False
    reactions: bool = False
    threads: bool = False
    streaming: bool = False
    edit: bool = False
    unsend: bool = False
    reply: bool = True
    mentions: bool = True
    polls: bool = False
    buttons: bool = False
    rich_text: bool = False
    markdown: bool = False
    
    # 限制
    text_max_length: int = 4000
    media_max_size_mb: int = 20
    
    def supports(self, feature: str) -> bool:
        """检查是否支持某功能"""
        return getattr(self, feature, False)
