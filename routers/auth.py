"""
认证路由层

职责：
- HTTP 请求解析
- 调用 AuthService 处理业务逻辑
- 异常转换为 HTTP 异常
"""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from logger import get_logger
from services.auth_service import (
    AuthService,
    InvalidCredentialsError,
    TokenExpiredError,
    TokenInvalidError,
    get_auth_service,
)

logger = get_logger("auth_router")

router = APIRouter(prefix="/api/v1/auth", tags=["认证"])

# 获取服务实例
auth_service = get_auth_service()


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
# 依赖注入
# ============================================================


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

    try:
        user = auth_service.verify_token(token)
        return user
    except TokenExpiredError:
        raise HTTPException(status_code=401, detail="认证已过期")
    except TokenInvalidError as e:
        raise HTTPException(status_code=401, detail=str(e))


# ============================================================
# 路由
# ============================================================


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    用户登录

    验证统一密码，返回 JWT Token
    """
    try:
        result = await auth_service.authenticate(request.username, request.password)
        return LoginResponse(**result)
    except InvalidCredentialsError as e:
        raise HTTPException(status_code=401, detail=str(e))


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
    auth_service.logout(current_user["id"], current_user["username"])
    return {"message": "登出成功"}
