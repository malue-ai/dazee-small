"""
飞书渠道插件

完整的飞书 ChannelPlugin 实现
"""

from typing import Dict, Any, List, Optional
from channels.base.plugin import BaseChannelPlugin
from channels.base.capabilities import ChannelMeta, ChannelCapabilities
from channels.feishu.types import FeishuAccount
from channels.feishu.gateway import FeishuGatewayAdapter
from channels.feishu.outbound import FeishuOutboundAdapter
from channels.feishu.security import FeishuSecurityAdapter
from channels.feishu.client import FeishuClient
from logger import get_logger

logger = get_logger("feishu_plugin")


class FeishuConfigAdapter:
    """
    飞书配置适配器
    """
    
    def list_account_ids(self, config: Dict[str, Any]) -> List[str]:
        """列出所有账户 ID"""
        accounts = config.get("accounts", {})
        if accounts:
            return list(accounts.keys())
        # 兼容单账户配置
        if config.get("app_id"):
            return ["default"]
        return []
    
    def resolve_account(
        self,
        config: Dict[str, Any],
        account_id: Optional[str] = None
    ) -> FeishuAccount:
        """解析账户配置"""
        accounts = config.get("accounts", {})
        
        if accounts:
            # 多账户配置
            account_id = account_id or self.default_account_id(config) or "default"
            account_data = accounts.get(account_id, {})
        else:
            # 单账户配置（兼容）
            account_data = config
        
        return FeishuAccount.from_dict(account_data)
    
    def default_account_id(self, config: Dict[str, Any]) -> Optional[str]:
        """获取默认账户 ID"""
        accounts = config.get("accounts", {})
        if accounts:
            # 返回第一个启用的账户
            for account_id, account_data in accounts.items():
                if account_data.get("enabled", True):
                    return account_id
        return "default"
    
    def is_enabled(self, account: FeishuAccount) -> bool:
        """检查账户是否启用"""
        return account.enabled
    
    def is_configured(self, account: FeishuAccount) -> bool:
        """检查账户是否已配置"""
        return bool(account.app_id and account.app_secret)


class FeishuPlugin(BaseChannelPlugin[FeishuAccount]):
    """
    飞书渠道插件
    
    完整的飞书双向对话实现：
    - 接收消息事件
    - 发送各类消息
    - 卡片交互
    - 流式输出
    """
    
    id = "feishu"
    
    meta = ChannelMeta(
        id="feishu",
        label="飞书",
        description="飞书企业协作平台",
        docs_path="/channels/feishu",
        icon="🐦",
        aliases=["lark"]
    )
    
    capabilities = ChannelCapabilities(
        chat_types=["direct", "group"],
        media=True,
        cards=True,
        reactions=True,
        threads=True,
        streaming=True,  # 通过编辑消息实现
        edit=True,
        reply=True,
        mentions=True,
        buttons=True,
        rich_text=True,
        markdown=True,
        text_max_length=4000,
        media_max_size_mb=20,
    )
    
    def __init__(self):
        """初始化飞书插件"""
        super().__init__()
        
        # 初始化适配器
        self.config = FeishuConfigAdapter()
        self.gateway = FeishuGatewayAdapter()
        self.outbound = FeishuOutboundAdapter()
        self.security = FeishuSecurityAdapter()
        
        logger.info("✅ 飞书插件已初始化")
    
    def get_client(self, account: FeishuAccount) -> FeishuClient:
        """获取飞书客户端"""
        return FeishuClient(account)


# 全局插件实例
feishu_plugin = FeishuPlugin()
