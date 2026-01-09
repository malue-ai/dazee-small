"""
gRPC 服务器统一启动器

同时提供 Chat、Session、Tool、Agent 四个服务
"""

import grpc
import asyncio
from concurrent import futures
from logger import get_logger

# 导入生成的 protobuf 代码
try:
    from services.grpc.generated import tool_service_pb2_grpc
except ImportError:
    tool_service_pb2_grpc = None

# 导入服务实现
from services.grpc.chat_server import ChatServicer
from services.grpc.session_server import SessionServicer

logger = get_logger("grpc_server")


class GRPCServer:
    """
    gRPC 服务器管理器
    
    负责启动和管理所有 gRPC 服务
    """
    
    def __init__(self, host: str = "0.0.0.0", port: int = 50051, max_workers: int = 10):
        """
        初始化 gRPC 服务器
        
        Args:
            host: 监听地址
            port: 监听端口
            max_workers: 最大工作线程数
        """
        self.host = host
        self.port = port
        self.max_workers = max_workers
        self.server = None
        logger.info(f"🔧 gRPC 服务器配置: {host}:{port}, 最大并发={max_workers}")
    
    async def start(self):
        """启动 gRPC 服务器"""
        try:
            if tool_service_pb2_grpc is None:
                logger.error(
                    "❌ protobuf 代码未生成，请先运行: "
                    "bash scripts/generate_grpc.sh"
                )
                return
            
            logger.info("🚀 启动 gRPC 服务器...")
            
            # 创建异步 gRPC 服务器
            self.server = grpc.aio.server(
                futures.ThreadPoolExecutor(max_workers=self.max_workers)
            )
            
            # 注册所有服务
            logger.info("📋 注册 Chat 服务...")
            tool_service_pb2_grpc.add_ChatServiceServicer_to_server(
                ChatServicer(), self.server
            )
            
            logger.info("📋 注册 Session 服务...")
            tool_service_pb2_grpc.add_SessionServiceServicer_to_server(
                SessionServicer(), self.server
            )
            
            # TODO: 注册 Tool 服务和 Agent 服务
            # tool_service_pb2_grpc.add_ToolServiceServicer_to_server(
            #     ToolServicer(), self.server
            # )
            # tool_service_pb2_grpc.add_AgentServiceServicer_to_server(
            #     AgentServicer(), self.server
            # )
            
            # 绑定端口
            address = f"{self.host}:{self.port}"
            self.server.add_insecure_port(address)
            
            # 启动服务器
            await self.server.start()
            logger.info(f"✅ gRPC 服务器已启动: {address}")
            logger.info("📡 可用服务: ChatService, SessionService")
            
        except Exception as e:
            logger.error(f"❌ gRPC 服务器启动失败: {str(e)}", exc_info=True)
            raise
    
    async def stop(self, grace_period: int = 5):
        """
        停止 gRPC 服务器
        
        Args:
            grace_period: 优雅关闭等待时间（秒）
        """
        if self.server:
            logger.info(f"🛑 正在关闭 gRPC 服务器（等待 {grace_period}s）...")
            await self.server.stop(grace_period)
            logger.info("✅ gRPC 服务器已关闭")
    
    async def wait_for_termination(self):
        """等待服务器终止"""
        if self.server:
            await self.server.wait_for_termination()


async def serve_grpc(host: str = "0.0.0.0", port: int = 50051, max_workers: int = 10):
    """
    启动 gRPC 服务器的便捷函数
    
    Args:
        host: 监听地址
        port: 监听端口
        max_workers: 最大工作线程数
    """
    server = GRPCServer(host, port, max_workers)
    await server.start()
    await server.wait_for_termination()


if __name__ == "__main__":
    """独立运行 gRPC 服务器"""
    import sys
    
    # 从环境变量读取配置
    import os
    host = os.getenv("GRPC_HOST", "0.0.0.0")
    port = int(os.getenv("GRPC_PORT", "50051"))
    max_workers = int(os.getenv("GRPC_MAX_WORKERS", "10"))
    
    print("\n" + "="*60)
    print("🚀 启动 Zenflux Agent gRPC 服务器")
    print("="*60)
    print(f"📍 监听地址: {host}:{port}")
    print(f"⚙️  最大并发: {max_workers}")
    print(f"📡 可用服务: ChatService, SessionService")
    print("="*60 + "\n")
    
    try:
        asyncio.run(serve_grpc(host, port, max_workers))
    except KeyboardInterrupt:
        print("\n👋 gRPC 服务器已关闭")
        sys.exit(0)

