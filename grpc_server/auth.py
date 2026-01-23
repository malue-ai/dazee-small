"""
gRPC 认证和授权拦截器
用于保护 Production gRPC 服务免受未授权访问

认证策略：
- 内网访问（VPC 内部）：无需认证
- 公网访问：需要 Bearer token API Key
"""

import grpc
import logging
import ipaddress
import os
from typing import Callable, Any
from functools import wraps

logger = logging.getLogger(__name__)

# 从环境变量读取 gRPC API Key
GRPC_API_KEY = os.getenv("GRPC_API_KEY", "")

# 内网 IP 段白名单（AWS VPC 常用范围）
INTERNAL_CIDRS = [
    ipaddress.ip_network("10.0.0.0/8", strict=False),      # AWS VPC 标准范围
    ipaddress.ip_network("172.16.0.0/12", strict=False),   # VPC 备选范围
    ipaddress.ip_network("192.168.0.0/16", strict=False),  # 本地开发范围
    ipaddress.ip_network("127.0.0.0/8", strict=False),     # localhost
]


def is_internal_ip(peer_address: str) -> bool:
    """
    检查客户端 IP 是否在内网范围内
    
    Args:
        peer_address: gRPC peer 地址，格式为 "ip:port"
    
    Returns:
        True if IP 在内网范围内，False 为公网
    """
    if not peer_address:
        return False
    
    try:
        # 提取 IP 地址（去掉端口）
        ip_str = peer_address.split(":")[0]
        ip = ipaddress.ip_address(ip_str)
        
        # 检查是否在任何内网 CIDR 中
        for cidr in INTERNAL_CIDRS:
            if ip in cidr:
                logger.debug(f"[内网访问] IP: {ip_str}, 允许无认证")
                return True
        
        logger.debug(f"[公网访问] IP: {ip_str}, 需要认证")
        return False
    except (ValueError, IndexError) as e:
        logger.warning(f"无法解析 peer 地址: {peer_address}, 错误: {e}")
        # 如果无法解析，假设为公网（安全起见）
        return False


class AuthInterceptor(grpc.aio.ServerInterceptor):
    """
    gRPC 服务器认证拦截器
    
    策略：
    - 内网 IP：直接通过（无需认证）
    - 公网 IP：需要有效的 Bearer token
    - 允许方法：Health Check 无需认证
    """

    async def intercept_service(self, continuation, handler_call_details):
        """
        拦截每个 gRPC 请求
        
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
            logger.debug(f"[健康检查豁免] 方法: {method}")
            return await continuation(handler_call_details)
        
        # 获取客户端 peer 地址
        peer = handler_call_details.peer
        
        # 检查是否是内网 IP
        if is_internal_ip(peer):
            logger.info(f"[内网访问允许] 方法: {method}, 客户端: {peer}")
            # 内网流量直接通过
            return await continuation(handler_call_details)
        
        # 公网流量需要认证
        logger.info(f"[公网访问] 方法: {method}, 客户端: {peer}, 进行认证检查")
        
        metadata = dict(handler_call_details.invocation_metadata or [])
        auth_header = metadata.get("authorization", "").strip()
        
        if not auth_header or not auth_header.startswith("Bearer "):
            logger.warning(
                f"[认证失败] 方法: {method}, 客户端: {peer}, "
                f"缺少或格式错误的 authorization header"
            )
            
            await handler_call_details.context.abort(
                grpc.StatusCode.UNAUTHENTICATED,
                "Public access requires valid API key (Authorization: Bearer <key>)"
            )
        
        # 提取 token（去掉 "Bearer " 前缀）
        token = auth_header[7:]
        
        # 验证 token
        if not token or token != GRPC_API_KEY:
            logger.warning(
                f"[认证失败] 方法: {method}, 客户端: {peer}, 无效的 API key"
            )
            
            await handler_call_details.context.abort(
                grpc.StatusCode.PERMISSION_DENIED,
                "Invalid API key"
            )
        
        logger.info(f"[公网认证成功] 方法: {method}, 客户端: {peer}")
        
        # 认证成功，继续处理请求
        return await continuation(handler_call_details)


def require_auth(func: Callable) -> Callable:
    """
    装饰器：要求 gRPC 方法进行公网认证
    （内网访问仍然免认证）
    
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
        peer = context.peer()
        
        # 内网 IP 直接通过
        if is_internal_ip(peer):
            return await func(self, request, context)
        
        # 公网需要认证
        auth_header = metadata.get("authorization", "").strip()
        
        if not auth_header or not auth_header.startswith("Bearer "):
            await context.abort(
                grpc.StatusCode.UNAUTHENTICATED,
                "Public access requires API key"
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

