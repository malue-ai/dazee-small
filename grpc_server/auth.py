"""
gRPC 认证和授权拦截器
用于保护 Production gRPC 服务免受未授权访问
"""

import grpc
import logging
from typing import Callable, Any
from functools import wraps
import os

logger = logging.getLogger(__name__)

# 从环境变量读取 gRPC API Key
GRPC_API_KEY = os.getenv("GRPC_API_KEY", "")


class AuthInterceptor(grpc.aio.ServerInterceptor):
    """gRPC 服务器认证拦截器"""

    async def intercept_service(self, continuation, handler_call_details):
        """
        拦截每个 gRPC 请求，检查认证信息
        
        Args:
            continuation: 继续执行的函数
            handler_call_details: 包含请求元数据的详情对象
        
        Returns:
            继续处理或返回认证错误
        """
        
        # 允许的无认证方法（健康检查）
        allowed_methods = {
            "/grpc.health.v1.Health/Check",
            "/grpc.health.v1.Health/Watch",
        }
        
        method = handler_call_details.method
        
        # 跳过健康检查的认证
        if method in allowed_methods:
            return await continuation(handler_call_details)
        
        # 获取请求元数据
        metadata = dict(handler_call_details.invocation_metadata or [])
        
        # 检查 API Key（来自 authorization 元数据）
        auth_header = metadata.get("authorization", "").strip()
        
        if not auth_header or not auth_header.startswith("Bearer "):
            logger.warning(f"[认证失败] 方法: {method}, 缺少或格式错误的 authorization header")
            
            # 返回 UNAUTHENTICATED 错误
            await handler_call_details.context.abort(
                grpc.StatusCode.UNAUTHENTICATED,
                "Missing or invalid authorization header"
            )
        
        # 提取 token（去掉 "Bearer " 前缀）
        token = auth_header[7:]
        
        # 验证 token
        if not token or token != GRPC_API_KEY:
            logger.warning(f"[认证失败] 方法: {method}, 无效的 token")
            
            await handler_call_details.context.abort(
                grpc.StatusCode.PERMISSION_DENIED,
                "Invalid API key"
            )
        
        logger.debug(f"[认证成功] 方法: {method}")
        
        # 认证成功，继续处理请求
        return await continuation(handler_call_details)


def require_auth(func: Callable) -> Callable:
    """
    装饰器：要求 gRPC 方法进行认证
    
    用法：
        @require_auth
        async def ExecuteTask(self, request, context):
            # 处理请求
            pass
    """
    @wraps(func)
    async def wrapper(self, request, context):
        # 获取元数据
        metadata = dict(context.invocation_metadata())
        auth_header = metadata.get("authorization", "").strip()
        
        if not auth_header or not auth_header.startswith("Bearer "):
            await context.abort(
                grpc.StatusCode.UNAUTHENTICATED,
                "Missing authorization header"
            )
        
        token = auth_header[7:]
        if not token or token != GRPC_API_KEY:
            await context.abort(
                grpc.StatusCode.PERMISSION_DENIED,
                "Invalid API key"
            )
        
        # 认证通过，调用原函数
        return await func(self, request, context)
    
    return wrapper


# 使用示例：
# 在 grpc_server/__init__.py 中添加：
#
# from grpc_auth import AuthInterceptor
# 
# async def serve():
#     interceptors = [AuthInterceptor()]
#     server = grpc.aio.server(interceptors=interceptors)
#     # ... 其他配置 ...
