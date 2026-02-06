"""
飞书 Security 适配器

负责权限策略
"""

from typing import Dict, Any, List, Union
from channels.base.types import (
    SecurityContext,
    DmPolicy,
    GroupPolicy,
    PolicyType,
)
from channels.feishu.types import FeishuAccount
from logger import get_logger

logger = get_logger("feishu_security")


class FeishuSecurityAdapter:
    """
    飞书 Security 适配器
    
    解析飞书的权限策略
    """
    
    def resolve_dm_policy(self, ctx: SecurityContext) -> DmPolicy:
        """
        解析私聊策略
        
        Args:
            ctx: 安全上下文
            
        Returns:
            私聊策略
        """
        account: FeishuAccount = ctx.account
        
        policy_map = {
            "open": PolicyType.OPEN,
            "pairing": PolicyType.PAIRING,
            "disabled": PolicyType.DISABLED,
            "allowlist": PolicyType.ALLOWLIST,
        }
        
        return DmPolicy(
            policy=policy_map.get(account.dm_policy, PolicyType.OPEN),
            allow_from=account.allow_from,
            policy_path=f"channels.feishu.accounts.{ctx.account_id}.dm_policy",
            allow_from_path=f"channels.feishu.accounts.{ctx.account_id}.allow_from",
            approve_hint="添加用户 open_id 到 allow_from 列表"
        )
    
    def resolve_group_policy(self, ctx: SecurityContext) -> GroupPolicy:
        """
        解析群聊策略
        
        Args:
            ctx: 安全上下文
            
        Returns:
            群聊策略
        """
        account: FeishuAccount = ctx.account
        
        policy_map = {
            "open": PolicyType.OPEN,
            "allowlist": PolicyType.ALLOWLIST,
            "disabled": PolicyType.DISABLED,
        }
        
        return GroupPolicy(
            policy=policy_map.get(account.group_policy, PolicyType.OPEN),
            allow_from=account.group_allow_from,
            require_mention=account.require_mention,
            groups=account.groups
        )
    
    def is_sender_allowed(
        self,
        ctx: SecurityContext,
        policy: Union[DmPolicy, GroupPolicy]
    ) -> bool:
        """
        检查发送者是否在白名单中
        
        Args:
            ctx: 安全上下文
            policy: 策略对象
            
        Returns:
            是否允许
        """
        allow_from = policy.allow_from
        
        if not allow_from:
            return True
        
        if "*" in allow_from:
            return True
        
        # 检查 open_id
        if ctx.sender_id in allow_from:
            return True
        
        # 检查 @用户名
        if ctx.sender_name and f"@{ctx.sender_name}" in allow_from:
            return True
        
        return False
