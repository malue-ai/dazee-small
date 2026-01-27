"""
gRPC 服务器统一启动器

同时提供 Chat、Session 等服务
"""

import os
import grpc
import asyncio
from concurrent import futures
from typing import List, Tuple
from logger import get_logger

# 导入认证拦截器
from grpc_server.auth import AuthInterceptor


# ===========================================================================
# gRPC Keepalive 配置（防止长连接被中间代理断开）
# ===========================================================================

def get_grpc_server_options() -> List[Tuple[str, any]]:
    """
    获取 gRPC 服务器配置选项
    
    Keepalive 配置说明：
    - GRPC_ARG_KEEPALIVE_TIME_MS: 空闲多久后发送 keepalive ping（毫秒）
    - GRPC_ARG_KEEPALIVE_TIMEOUT_MS: keepalive ping 响应超时（毫秒）
    - GRPC_ARG_KEEPALIVE_PERMIT_WITHOUT_CALLS: 无 RPC 时是否允许 keepalive
    - GRPC_ARG_HTTP2_MAX_PINGS_WITHOUT_DATA: 无数据时最大 ping 次数
    - GRPC_ARG_HTTP2_MIN_RECV_PING_INTERVAL_WITHOUT_DATA_MS: 接收 ping 的最小间隔
    
    Returns:
        gRPC 服务器配置选项列表
    """
    # 从环境变量读取配置，提供合理默认值
    keepalive_time = int(os.getenv("GRPC_KEEPALIVE_TIME_MS", "30000"))  # 30 秒
    keepalive_timeout = int(os.getenv("GRPC_KEEPALIVE_TIMEOUT_MS", "10000"))  # 10 秒
    # 🔧 增加空闲超时到 30 分钟，适配长时间运行的任务（如 PPT 生成、视频处理）
    max_connection_idle = int(os.getenv("GRPC_MAX_CONNECTION_IDLE_MS", "1800000"))  # 30 分钟
    max_connection_age = int(os.getenv("GRPC_MAX_CONNECTION_AGE_MS", "3600000"))  # 1 小时
    max_connection_age_grace = int(os.getenv("GRPC_MAX_CONNECTION_AGE_GRACE_MS", "60000"))  # 1 分钟
    
    return [
        # Keepalive 配置
        ("grpc.keepalive_time_ms", keepalive_time),
        ("grpc.keepalive_timeout_ms", keepalive_timeout),
        ("grpc.keepalive_permit_without_calls", True),
        ("grpc.http2.max_pings_without_data", 0),  # 无限制
        ("grpc.http2.min_recv_ping_interval_without_data_ms", 100),  # 100ms（更宽松，防止 Too many pings）
        ("grpc.http2.min_sent_ping_interval_without_data_ms", 5000),  # 5 秒
        # 🆕 增加 ping 容忍度：防止 "Too many pings" 错误
        # max_ping_strikes=0 表示不限制客户端 ping 频率
        ("grpc.http2.max_ping_strikes", 0),
        
        # 连接生命周期管理
        ("grpc.max_connection_idle_ms", max_connection_idle),
        ("grpc.max_connection_age_ms", max_connection_age),
        ("grpc.max_connection_age_grace_ms", max_connection_age_grace),
        
        # 🆕 增加最大接收消息大小（默认 4MB 可能不够）
        ("grpc.max_receive_message_length", 50 * 1024 * 1024),  # 50 MB
        ("grpc.max_send_message_length", 50 * 1024 * 1024),  # 50 MB
    ]

# 导入生成的 protobuf 代码
try:
    from grpc_server.generated import tool_service_pb2_grpc
    from grpc_server.generated import tool_service_pb2
except ImportError:
    tool_service_pb2_grpc = None
    tool_service_pb2 = None

# 导入 gRPC reflection（用于 grpcurl 等工具调试）
try:
    from grpc_reflection.v1alpha import reflection
except ImportError:
    reflection = None

# 导入服务实现
from grpc_server.chat_servicer import ChatServicer
from grpc_server.session_servicer import SessionServicer
from grpc_server.health_servicer import HealthServicer
from grpc_server.sandbox_servicer import SandboxServicer

logger = get_logger("grpc_server")


class GRPCServer:
    """
    gRPC 服务器管理器
    
    负责启动和管理所有 gRPC 服务
    """
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 50051,
        max_workers: int = None,
        grace_period: int = None
    ):
        """
        初始化 gRPC 服务器
        
        Args:
            host: 监听地址
            port: 监听端口
            max_workers: 最大工作线程数，None 表示不限制（使用 1000）
            grace_period: 优雅关闭等待时间（秒），None 表示从环境变量读取或使用默认值 30 秒
        """
        self.host = host
        self.port = port
        if max_workers is None or max_workers <= 0:
            self.max_workers = 1000  # 无限制模式
        else:
            self.max_workers = max_workers
        
        # 🆕 优雅关闭等待时间（默认 30 秒，与 Envoy Drain 时间匹配）
        if grace_period is None:
            self.grace_period = int(os.getenv("GRPC_GRACE_PERIOD", "30"))
        else:
            self.grace_period = grace_period
        
        self.server = None
        logger.info(
            f"🔧 gRPC 服务器配置: {host}:{port}, "
            f"最大并发={self.max_workers}, 优雅关闭={self.grace_period}s"
        )
    
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
            
            # 创建认证拦截器
            interceptors = [AuthInterceptor()]
            
            # 🆕 获取 keepalive 和其他配置选项
            server_options = get_grpc_server_options()
            logger.debug(f"🔧 gRPC 服务器选项: {server_options}")
            
            # 创建异步 gRPC 服务器（带认证拦截器和 keepalive 配置）
            self.server = grpc.aio.server(
                futures.ThreadPoolExecutor(max_workers=self.max_workers),
                interceptors=interceptors,
                options=server_options
            )
            
            # 注册所有服务
            logger.info("📋 注册 Health 服务...")
            self.health_servicer = HealthServicer()
            tool_service_pb2_grpc.add_HealthServicer_to_server(
                self.health_servicer, self.server
            )
            
            logger.info("📋 注册 Chat 服务...")
            tool_service_pb2_grpc.add_ChatServiceServicer_to_server(
                ChatServicer(), self.server
            )
            
            logger.info("📋 注册 Session 服务...")
            tool_service_pb2_grpc.add_SessionServiceServicer_to_server(
                SessionServicer(), self.server
            )
            
            logger.info("📋 注册 Sandbox 服务...")
            tool_service_pb2_grpc.add_SandboxServiceServicer_to_server(
                SandboxServicer(), self.server
            )
            
            # 启用 gRPC reflection（用于 grpcurl 等工具调试）
            if reflection is not None and tool_service_pb2 is not None:
                SERVICE_NAMES = (
                    tool_service_pb2.DESCRIPTOR.services_by_name['Health'].full_name,
                    tool_service_pb2.DESCRIPTOR.services_by_name['ChatService'].full_name,
                    tool_service_pb2.DESCRIPTOR.services_by_name['SessionService'].full_name,
                    tool_service_pb2.DESCRIPTOR.services_by_name['SandboxService'].full_name,
                    reflection.SERVICE_NAME,
                )
                reflection.enable_server_reflection(SERVICE_NAMES, self.server)
                logger.info("📋 启用 gRPC Reflection 服务...")
            
            # 绑定端口
            address = f"{self.host}:{self.port}"
            self.server.add_insecure_port(address)
            
            # 启动服务器
            await self.server.start()
            logger.info(f"✅ gRPC 服务器已启动: {address}")
            logger.info("📡 可用服务: Health, ChatService, SessionService, SandboxService")
            
        except Exception as e:
            logger.error(f"❌ gRPC 服务器启动失败: {str(e)}", exc_info=True)
            raise
    
    async def stop(self, grace_period: int = None):
        """
        停止 gRPC 服务器
        
        Args:
            grace_period: 优雅关闭等待时间（秒），None 使用初始化时的配置
        """
        if self.server:
            actual_grace = grace_period if grace_period is not None else self.grace_period
            logger.info(f"🛑 正在关闭 gRPC 服务器（等待 {actual_grace}s）...")
            await self.server.stop(actual_grace)
            logger.info("✅ gRPC 服务器已关闭")
    
    async def wait_for_termination(self):
        """等待服务器终止"""
        if self.server:
            await self.server.wait_for_termination()


async def serve_grpc(host: str = "0.0.0.0", port: int = 50051, max_workers: int = None):
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
    host = os.getenv("GRPC_HOST", "0.0.0.0")
    port = int(os.getenv("GRPC_PORT", "50051"))
    max_workers_env = os.getenv("GRPC_MAX_WORKERS", "0")
    max_workers = int(max_workers_env) if max_workers_env else 0
    
    # 计算实际值用于显示
    if max_workers <= 0:
        workers_display = "1000 (无限制)"
    else:
        workers_display = str(max_workers)
    
    print("\n" + "="*60)
    print("🚀 启动 Zenflux Agent gRPC 服务器")
    print("="*60)
    print(f"📍 监听地址: {host}:{port}")
    print(f"⚙️  最大并发: {workers_display}")
    print(f"📡 可用服务: Health, ChatService, SessionService, SandboxService")
    print("="*60 + "\n")
    
    try:
        asyncio.run(serve_grpc(host, port, max_workers if max_workers > 0 else None))
    except KeyboardInterrupt:
        print("\n👋 gRPC 服务器已关闭")
        sys.exit(0)

