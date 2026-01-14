"""
认证路由模块

提供简单的用户认证功能：
- 统一密码验证
- JWT Token 生成和验证
"""

import os
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["认证"])


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
# 数据模型
# ============================================================

class LoginRequest(BaseModel):
    """登录请求"""
    username: str
    password: str


class LoginResponse(BaseModel):
    """登录响应"""
    token: str
    user: dict


class UserInfo(BaseModel):
    """用户信息"""
    id: str
    username: str
    created_at: str


# ============================================================
# 简单的 Token 实现（不依赖 pyjwt）
# ============================================================

def create_token(user_id: str, username: str) -> str:
    """
    创建简单的认证 Token
    
    格式: base64(user_id:username:timestamp:signature)
    """
    import base64
    
    timestamp = datetime.utcnow().isoformat()
    payload = f"{user_id}:{username}:{timestamp}"
    
    # 创建签名
    signature = hashlib.sha256(f"{payload}:{JWT_SECRET}".encode()).hexdigest()[:16]
    
    # 组合并编码
    token_data = f"{payload}:{signature}"
    token = base64.urlsafe_b64encode(token_data.encode()).decode()
    
    return token


def verify_token(token: str) -> Optional[dict]:
    """
    验证 Token
    
    Returns:
        用户信息 dict，验证失败返回 None
    """
    import base64
    
    try:
        # 解码
        token_data = base64.urlsafe_b64decode(token.encode()).decode()
        parts = token_data.rsplit(":", 3)
        
        if len(parts) != 4:
            return None
        
        user_id, username, timestamp, signature = parts
        
        # 验证签名
        payload = f"{user_id}:{username}:{timestamp}"
        expected_signature = hashlib.sha256(f"{payload}:{JWT_SECRET}".encode()).hexdigest()[:16]
        
        if signature != expected_signature:
            return None
        
        # 验证过期时间
        token_time = datetime.fromisoformat(timestamp)
        if datetime.utcnow() - token_time > timedelta(hours=TOKEN_EXPIRE_HOURS):
            return None
        
        return {
            "id": user_id,
            "username": username,
            "created_at": timestamp
        }
        
    except Exception as e:
        logger.warning(f"Token 验证失败: {e}")
        return None


def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """
    从请求头获取当前用户
    
    Raises:
        HTTPException: 401 未授权
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="未提供认证信息")
    
    # 解析 Bearer token
    if authorization.startswith("Bearer "):
        token = authorization[7:]
    else:
        token = authorization
    
    user = verify_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="认证已过期或无效")
    
    return user


# ============================================================
# 路由
# ============================================================

@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    用户登录
    
    验证统一密码，返回 JWT Token
    """
    # 验证密码
    if request.password != AUTH_PASSWORD:
        logger.warning(f"登录失败: 用户 {request.username} 密码错误")
        raise HTTPException(status_code=401, detail="密码错误")
    
    # 生成用户 ID（基于用户名的哈希）
    user_id = f"user_{hashlib.md5(request.username.encode()).hexdigest()[:8]}"
    
    # 创建 Token
    token = create_token(user_id, request.username)
    
    logger.info(f"用户登录成功: {request.username} ({user_id})")
    
    return LoginResponse(
        token=token,
        user={
            "id": user_id,
            "username": request.username,
            "created_at": datetime.utcnow().isoformat()
        }
    )


@router.get("/me", response_model=UserInfo)
async def get_me(current_user: dict = Depends(get_current_user)):
    """
    获取当前用户信息
    
    需要在请求头中携带 Authorization: Bearer <token>
    """
    return UserInfo(**current_user)


@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    """
    用户登出
    
    实际上只是返回成功，客户端需要删除本地存储的 Token
    """
    logger.info(f"用户登出: {current_user['username']}")
    return {"message": "登出成功"}

