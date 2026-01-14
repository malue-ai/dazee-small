"""
认证服务层

提供用户认证相关的业务逻辑：
- Token 生成和验证
- 密码验证
- 用户信息管理
"""

import os
import base64
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from logger import get_logger

logger = get_logger("auth_service")


# ============================================================
# 配置
# ============================================================

# 统一密码（从环境变量读取，默认为 'zenflux'）
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "zenflux")

# JWT 密钥（从环境变量读取，或自动生成）
JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_hex(32))

# Token 过期时间（小时）
TOKEN_EXPIRE_HOURS = int(os.getenv("TOKEN_EXPIRE_HOURS", "24"))


# ============================================================
# 异常定义
# ============================================================

class AuthServiceError(Exception):
    """认证服务基础异常"""
    pass


class InvalidCredentialsError(AuthServiceError):
    """凭证无效"""
    pass


class TokenExpiredError(AuthServiceError):
    """Token 已过期"""
    pass


class TokenInvalidError(AuthServiceError):
    """Token 无效"""
    pass


# ============================================================
# 认证服务
# ============================================================

class AuthService:
    """
    认证服务
    
    职责：
    - Token 创建和验证
    - 密码验证
    - 用户信息管理
    """
    
    def __init__(self):
        self._password = AUTH_PASSWORD
        self._secret = JWT_SECRET
        self._expire_hours = TOKEN_EXPIRE_HOURS
    
    def create_token(self, user_id: str, username: str) -> str:
        """
        创建认证 Token
        
        Args:
            user_id: 用户 ID
            username: 用户名
            
        Returns:
            Token 字符串
        """
        timestamp = datetime.utcnow().isoformat()
        payload = f"{user_id}:{username}:{timestamp}"
        
        # 创建签名
        signature = hashlib.sha256(
            f"{payload}:{self._secret}".encode()
        ).hexdigest()[:16]
        
        # 组合并编码
        token_data = f"{payload}:{signature}"
        token = base64.urlsafe_b64encode(token_data.encode()).decode()
        
        logger.debug(f"Token 已创建: user_id={user_id}")
        return token
    
    def verify_token(self, token: str) -> Dict[str, Any]:
        """
        验证 Token
        
        Args:
            token: Token 字符串
            
        Returns:
            用户信息字典
            
        Raises:
            TokenInvalidError: Token 无效
            TokenExpiredError: Token 已过期
        """
        try:
            # 解码
            token_data = base64.urlsafe_b64decode(token.encode()).decode()
            parts = token_data.rsplit(":", 3)
            
            if len(parts) != 4:
                raise TokenInvalidError("Token 格式无效")
            
            user_id, username, timestamp, signature = parts
            
            # 验证签名
            payload = f"{user_id}:{username}:{timestamp}"
            expected_signature = hashlib.sha256(
                f"{payload}:{self._secret}".encode()
            ).hexdigest()[:16]
            
            if signature != expected_signature:
                raise TokenInvalidError("Token 签名无效")
            
            # 验证过期时间
            token_time = datetime.fromisoformat(timestamp)
            if datetime.utcnow() - token_time > timedelta(hours=self._expire_hours):
                raise TokenExpiredError("Token 已过期")
            
            return {
                "id": user_id,
                "username": username,
                "created_at": timestamp
            }
            
        except (TokenInvalidError, TokenExpiredError):
            raise
        except Exception as e:
            logger.warning(f"Token 验证失败: {e}")
            raise TokenInvalidError(f"Token 验证失败: {e}")
    
    def authenticate(self, username: str, password: str) -> Dict[str, Any]:
        """
        用户认证
        
        Args:
            username: 用户名
            password: 密码
            
        Returns:
            包含 token 和用户信息的字典
            
        Raises:
            InvalidCredentialsError: 凭证无效
        """
        # 验证密码
        if password != self._password:
            logger.warning(f"登录失败: 用户 {username} 密码错误")
            raise InvalidCredentialsError("密码错误")
        
        # 生成用户 ID（基于用户名的哈希）
        user_id = f"user_{hashlib.md5(username.encode()).hexdigest()[:8]}"
        
        # 创建 Token
        token = self.create_token(user_id, username)
        
        logger.info(f"用户登录成功: {username} ({user_id})")
        
        return {
            "token": token,
            "user": {
                "id": user_id,
                "username": username,
                "created_at": datetime.utcnow().isoformat()
            }
        }
    
    def logout(self, user_id: str, username: str) -> None:
        """
        用户登出
        
        Args:
            user_id: 用户 ID
            username: 用户名
        """
        # 目前只记录日志，后续可以加入 Token 黑名单等逻辑
        logger.info(f"用户登出: {username} ({user_id})")


# ============================================================
# 单例管理
# ============================================================

_auth_service: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    """获取认证服务单例"""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service

