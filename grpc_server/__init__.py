"""
gRPC 服务层

提供 gRPC 协议入口，和 routers/ 平级。
业务逻辑复用 services/ 层。

注意：使用延迟导入，避免客户端脚本加载服务端依赖（如数据库）
"""

__all__ = [
    "GRPCServer",
    "serve_grpc",
    "ChatServicer",
    "SessionServicer",
    "ZenfluxGRPCClient",
]


def __getattr__(name: str):
    """
    延迟导入：只在实际使用时才加载模块
    
    - 客户端脚本只需要 ZenfluxGRPCClient，不需要加载服务端依赖
    - 服务端启动时才加载 ChatServicer、SessionServicer 等
    """
    if name == "ZenfluxGRPCClient":
        from .client import ZenfluxGRPCClient
        return ZenfluxGRPCClient
    
    if name in ("GRPCServer", "serve_grpc"):
        from .server import GRPCServer, serve_grpc
        if name == "GRPCServer":
            return GRPCServer
        return serve_grpc
    
    if name == "ChatServicer":
        from .chat_servicer import ChatServicer
        return ChatServicer
    
    if name == "SessionServicer":
        from .session_servicer import SessionServicer
        return SessionServicer
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

