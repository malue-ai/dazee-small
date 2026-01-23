"""
gRPC 认证和授权拦截器
用于保护 Production gRPC 服务免受未授权访问

当前策略：仅提供基于 IP 的白名单（内网免认证）
"""

import grpc
import logging
import ipaddress
import os
from typing import Callable, Any
from functools import wraps

logger = logging.getLogger(__name__)

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
                logger.debug(f"[内网访问] IP: {ip_str}")
                return True
        
        logger.debug(f"[公网访问] IP: {ip_str}")
        return False
    except (ValueError, IndexError) as e:
        logger.warning(f"无法解析 peer 地址: {peer_address}, 错误: {e}")
        return False


class AuthInterceptor(grpc.aio.ServerInterceptor):
    """
    gRPC 服务器认证拦截器
    
    当前策略：
    - 仅用于监控和日志记录
    - 不进行实际的认证和授权检查
    - 允许所有请求通过
    """

    async def intercept_service(self, continuation, handler_call_details):
        """
        拦截每个 gRPC 请求，记录日志但不阻止
        
        Args:
            continuation: 继续执行的函数
            handler_call_details: 包含请求元数据的详情对象
        
        Returns:
            继续处理请求
        """
        
        method = handler_call_details.method
        peer = handler_call_details.peer
        
        # 记录所有请求用于审计
        if is_internal_ip(peer):
            logger.info(f"[gRPC 请求] 内网 - 方法: {method}, 客户端: {peer}")
        else:
            logger.info(f"[gRPC 请求] 公网 - 方法: {method}, 客户端: {peer}")
        
        # 直接通过，无需认证
        return await continuation(handler_call_details)


def require_auth(func: Callable) -> Callable:
    """
    装饰器：目前无实际作用，保留用于未来扩展
    
    用法：
        @require_auth
        async def ExecuteTask(self, request, context):
            # 处理请求
            pass
    """
    @wraps(func)
    async def wrapper(self, request, context):
        # 直接调用原函数，无认证检查
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


