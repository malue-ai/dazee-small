"""
gRPC 健康检查服务实现

遵循 gRPC Health Checking Protocol:
https://github.com/grpc/grpc/blob/master/doc/health-checking.md
"""

import asyncio
from typing import Dict
from logger import get_logger

# 导入生成的 protobuf 代码
try:
    from grpc_server.generated import tool_service_pb2, tool_service_pb2_grpc
    _GRPC_AVAILABLE = True
except ImportError as e:
    tool_service_pb2 = None
    tool_service_pb2_grpc = None
    _GRPC_AVAILABLE = False
    import logging
    logging.getLogger(__name__).warning(f"gRPC protobuf 代码未生成: {e}")

logger = get_logger("grpc_health")

# 创建基类（如果 gRPC 不可用，使用 object 作为基类）
_HealthServicerBase = (
    tool_service_pb2_grpc.HealthServicer 
    if _GRPC_AVAILABLE and tool_service_pb2_grpc 
    else object
)


class HealthServicer(_HealthServicerBase):
    """
    gRPC 健康检查服务实现
    
    支持检查整体服务状态和特定服务状态
    """
    
    def __init__(self):
        """初始化健康检查服务"""
        # 服务状态映射：服务名 -> 状态
        # SERVING = 1 (根据 gRPC Health Checking Protocol)
        serving_status = tool_service_pb2.HealthCheckResponse.SERVING if tool_service_pb2 else 1
        self._service_status: Dict[str, int] = {
            "": serving_status,  # 整体状态
            "zenflux.ChatService": serving_status,
            "zenflux.SessionService": serving_status,
        }
        # 状态变更监听器
        self._watchers: Dict[str, list] = {}
        logger.info("✅ 健康检查服务已初始化")
    
    def set_service_status(self, service: str, status: int):
        """
        设置服务状态
        
        Args:
            service: 服务名称，空字符串表示整体状态
            status: 服务状态（SERVING, NOT_SERVING 等）
        """
        self._service_status[service] = status
        logger.info(f"📊 服务状态更新: {service or '整体'} -> {status}")
        
        # 通知监听器
        if service in self._watchers:
            for queue in self._watchers[service]:
                queue.put_nowait(status)
    
    async def Check(self, request, context):
        """
        检查服务健康状态
        
        Args:
            request: HealthCheckRequest，包含要检查的服务名
            context: gRPC 上下文
            
        Returns:
            HealthCheckResponse，包含服务状态
        """
        service = request.service
        
        if service in self._service_status:
            status = self._service_status[service]
            logger.debug(f"🔍 健康检查: {service or '整体'} -> {status}")
            return tool_service_pb2.HealthCheckResponse(status=status)
        else:
            # 未知服务
            logger.warning(f"⚠️ 健康检查: 未知服务 {service}")
            return tool_service_pb2.HealthCheckResponse(
                status=tool_service_pb2.HealthCheckResponse.SERVICE_UNKNOWN
            )
    
    async def Watch(self, request, context):
        """
        监听服务健康状态变化（流式）
        
        Args:
            request: HealthCheckRequest，包含要监听的服务名
            context: gRPC 上下文
            
        Yields:
            HealthCheckResponse，每次状态变化时发送
        """
        service = request.service
        logger.info(f"👀 开始监听服务状态: {service or '整体'}")
        
        # 创建状态队列
        queue = asyncio.Queue()
        
        # 注册监听器
        if service not in self._watchers:
            self._watchers[service] = []
        self._watchers[service].append(queue)
        
        try:
            # 首先发送当前状态
            if service in self._service_status:
                current_status = self._service_status[service]
            else:
                current_status = tool_service_pb2.HealthCheckResponse.SERVICE_UNKNOWN
            
            yield tool_service_pb2.HealthCheckResponse(status=current_status)
            
            # 持续监听状态变化
            while True:
                try:
                    # 等待状态变化，超时后重新发送当前状态（心跳）
                    status = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield tool_service_pb2.HealthCheckResponse(status=status)
                except asyncio.TimeoutError:
                    # 超时，发送当前状态作为心跳
                    if service in self._service_status:
                        yield tool_service_pb2.HealthCheckResponse(
                            status=self._service_status[service]
                        )
                    
        except asyncio.CancelledError:
            logger.info(f"👋 停止监听服务状态: {service or '整体'}")
        finally:
            # 移除监听器
            if service in self._watchers and queue in self._watchers[service]:
                self._watchers[service].remove(queue)
