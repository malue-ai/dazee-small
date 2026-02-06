"""
安全检查器

负责：
- 权限验证
- 私聊/群聊策略检查
- 白名单验证
"""

from typing import Dict, Any, Optional, Set
from channels.base.types import (
    SecurityContext,
    SecurityResult,
    SecurityResultType,
    DmPolicy,
    GroupPolicy,
    PolicyType,
    InboundMessage,
)
from channels.base.plugin import ChannelPlugin
from logger import get_logger

logger = get_logger("channel_security")


class SecurityChecker:
    """
    安全检查器
    
    根据配置的策略检查消息是否允许处理
    
    使用示例：
    ```python
    checker = SecurityChecker()
    
    result = await checker.check(context, plugin)
    if result.is_allowed:
        # 处理消息
    else:
        # 拒绝或回复提示
        if result.reply_message:
            await send_reply(result.reply_message)
    ```
    """
    
    def __init__(self):
        """初始化安全检查器"""
        # 配对验证存储（sender_id -> paired）
        self._paired_users: Set[str] = set()
    
    async def check(
        self,
        ctx: SecurityContext,
        plugin: ChannelPlugin
    ) -> SecurityResult:
        """
        执行安全检查
        
        Args:
            ctx: 安全上下文
            plugin: 渠道插件
            
        Returns:
            安全检查结果
        """
        # 1. 检查账户是否启用
        if not plugin.config.is_enabled(ctx.account):
            logger.debug(f"账户未启用: {ctx.channel_id}/{ctx.account_id}")
            return SecurityResult.denied("账户未启用")
        
        # 2. 根据聊天类型选择策略
        if ctx.chat_type == "direct":
            return await self._check_dm_policy(ctx, plugin)
        else:
            return await self._check_group_policy(ctx, plugin)
    
    async def _check_dm_policy(
        self,
        ctx: SecurityContext,
        plugin: ChannelPlugin
    ) -> SecurityResult:
        """
        检查私聊策略
        
        Args:
            ctx: 安全上下文
            plugin: 渠道插件
            
        Returns:
            安全检查结果
        """
        if not plugin.security:
            # 没有安全适配器，默认允许
            return SecurityResult.allowed()
        
        policy = plugin.security.resolve_dm_policy(ctx)
        
        # 策略检查
        if policy.policy == PolicyType.DISABLED:
            logger.debug(f"私聊已禁用: {ctx.channel_id}/{ctx.sender_id}")
            return SecurityResult.denied(
                "私聊已禁用",
                reply_message="抱歉，私聊功能已关闭。"
            )
        
        if policy.policy == PolicyType.PAIRING:
            # 配对验证
            if not self._is_paired(ctx):
                logger.debug(f"需要配对验证: {ctx.channel_id}/{ctx.sender_id}")
                return SecurityResult.pending(
                    "需要配对验证",
                    reply_message=f"请联系管理员将您添加到白名单。\n{policy.approve_hint}"
                )
        
        if policy.policy in (PolicyType.ALLOWLIST, PolicyType.PAIRING):
            # 白名单检查
            if policy.allow_from and not self._is_in_allowlist(ctx, policy.allow_from):
                logger.debug(f"不在白名单中: {ctx.channel_id}/{ctx.sender_id}")
                return SecurityResult.denied(
                    "不在白名单中",
                    reply_message="抱歉，您没有权限使用此功能。"
                )
        
        return SecurityResult.allowed()
    
    async def _check_group_policy(
        self,
        ctx: SecurityContext,
        plugin: ChannelPlugin
    ) -> SecurityResult:
        """
        检查群聊策略
        
        Args:
            ctx: 安全上下文
            plugin: 渠道插件
            
        Returns:
            安全检查结果
        """
        if not plugin.security:
            return SecurityResult.allowed()
        
        policy = plugin.security.resolve_group_policy(ctx)
        
        # 策略检查
        if policy.policy == PolicyType.DISABLED:
            logger.debug(f"群聊已禁用: {ctx.channel_id}/{ctx.chat_id}")
            return SecurityResult.denied("群聊已禁用")
        
        # 检查群组特定配置
        group_config = policy.groups.get(ctx.chat_id, {})
        if group_config.get("enabled") is False:
            logger.debug(f"群组已禁用: {ctx.channel_id}/{ctx.chat_id}")
            return SecurityResult.denied("此群组已禁用")
        
        if policy.policy == PolicyType.ALLOWLIST:
            # 群聊白名单
            if policy.allow_from and ctx.chat_id not in policy.allow_from:
                logger.debug(f"群组不在白名单中: {ctx.channel_id}/{ctx.chat_id}")
                return SecurityResult.denied("此群组不在白名单中")
        
        # 检查发送者白名单（群组级别）
        group_allow_from = group_config.get("allow_from", [])
        if group_allow_from and "*" not in group_allow_from:
            if not self._is_in_allowlist(ctx, group_allow_from):
                logger.debug(f"发送者不在群组白名单中: {ctx.sender_id}")
                return SecurityResult.denied("您在此群组没有使用权限")
        
        return SecurityResult.allowed()
    
    def _is_paired(self, ctx: SecurityContext) -> bool:
        """
        检查用户是否已配对
        
        Args:
            ctx: 安全上下文
            
        Returns:
            是否已配对
        """
        key = f"{ctx.channel_id}:{ctx.sender_id}"
        return key in self._paired_users
    
    def add_paired_user(self, channel_id: str, sender_id: str) -> None:
        """
        添加配对用户
        
        Args:
            channel_id: 渠道 ID
            sender_id: 发送者 ID
        """
        key = f"{channel_id}:{sender_id}"
        self._paired_users.add(key)
        logger.info(f"添加配对用户: {key}")
    
    def remove_paired_user(self, channel_id: str, sender_id: str) -> None:
        """
        移除配对用户
        
        Args:
            channel_id: 渠道 ID
            sender_id: 发送者 ID
        """
        key = f"{channel_id}:{sender_id}"
        self._paired_users.discard(key)
        logger.info(f"移除配对用户: {key}")
    
    def _is_in_allowlist(
        self,
        ctx: SecurityContext,
        allow_from: list
    ) -> bool:
        """
        检查发送者是否在白名单中
        
        支持的白名单格式：
        - "*": 允许所有人
        - "ou_xxxxx": 用户 ID
        - "@username": 用户名
        
        Args:
            ctx: 安全上下文
            allow_from: 白名单列表
            
        Returns:
            是否在白名单中
        """
        if not allow_from:
            return True  # 空白名单表示允许所有人
        
        if "*" in allow_from:
            return True
        
        # 检查 ID
        if ctx.sender_id in allow_from:
            return True
        
        # 检查用户名（@开头）
        if ctx.sender_name:
            if f"@{ctx.sender_name}" in allow_from:
                return True
            if ctx.sender_name in allow_from:
                return True
        
        return False
