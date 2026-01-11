"""
gRPC 服务层

提供 gRPC 协议入口，和 routers/ 平级。
业务逻辑复用 services/ 层。
"""

from .server import GRPCServer, serve_grpc
from .chat_servicer import ChatServicer
from .session_servicer import SessionServicer
from .client import ZenfluxGRPCClient

__all__ = [
    "GRPCServer",
    "serve_grpc",
    "ChatServicer",
    "SessionServicer",
    "ZenfluxGRPCClient",
]

