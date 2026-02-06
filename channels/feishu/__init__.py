"""
飞书渠道插件

实现飞书机器人双向对话：
1. 接收飞书消息事件
2. 调用 Agent 处理
3. 回复消息到飞书
4. 支持卡片交互
5. 支持流式输出
"""

from channels.feishu.plugin import FeishuPlugin, feishu_plugin
from channels.feishu.client import FeishuClient
from channels.feishu.types import FeishuAccount, FeishuMessage
from channels.feishu.gateway import FeishuGatewayAdapter
from channels.feishu.outbound import FeishuOutboundAdapter
from channels.feishu.security import FeishuSecurityAdapter
from channels.feishu.cards import FeishuCardBuilder
from channels.feishu.handler import FeishuMessageHandler

__all__ = [
    # 插件
    "FeishuPlugin",
    "feishu_plugin",
    # 客户端
    "FeishuClient",
    # 类型
    "FeishuAccount",
    "FeishuMessage",
    # 适配器
    "FeishuGatewayAdapter",
    "FeishuOutboundAdapter",
    "FeishuSecurityAdapter",
    # 工具
    "FeishuCardBuilder",
    "FeishuMessageHandler",
]
