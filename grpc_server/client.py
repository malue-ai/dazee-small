"""
gRPC 客户端封装

用于内部微服务调用 Zenflux Agent 服务
"""

import grpc
import json
from typing import Optional, Dict, Any, List, AsyncIterator, Tuple
from logger import get_logger

# 导入生成的 protobuf 代码
try:
    from grpc_server.generated import tool_service_pb2
    from grpc_server.generated import tool_service_pb2_grpc
except ImportError:
    tool_service_pb2 = None
    tool_service_pb2_grpc = None

logger = get_logger("grpc_client")


def get_grpc_client_options() -> List[Tuple[str, any]]:
    """
    获取 gRPC 客户端配置选项
    
    Keepalive 配置说明：
    - 客户端的 keepalive 配置应与服务端兼容
    - 避免发送 ping 过于频繁导致 "Too many pings" 错误
    
    Returns:
        gRPC 客户端配置选项列表
    """
    return [
        # Keepalive 配置（与服务端协调）
        ("grpc.keepalive_time_ms", 30000),  # 30 秒（空闲后发送 keepalive ping）
        ("grpc.keepalive_timeout_ms", 10000),  # 10 秒（等待响应超时）
        ("grpc.keepalive_permit_without_calls", True),  # 无 RPC 时也允许 keepalive
        ("grpc.http2.max_pings_without_data", 0),  # 无限制
        
        # 消息大小限制（与服务端匹配）
        ("grpc.max_receive_message_length", 50 * 1024 * 1024),  # 50 MB
        ("grpc.max_send_message_length", 50 * 1024 * 1024),  # 50 MB
    ]


class ZenfluxGRPCClient:
    """
    Zenflux Agent gRPC 客户端
    
    提供与 HTTP API 相同的功能，使用 gRPC 协议
    
    使用示例：
        async with ZenfluxGRPCClient("localhost:50051") as client:
            # 同步聊天
            response = await client.chat(
                message="帮我生成PPT",
                user_id="user_001"
            )
            
            # 流式聊天
            async for event in client.chat_stream(
                message="帮我生成PPT",
                user_id="user_001"
            ):
                print(event)
    """
    
    def __init__(self, server_address: str = "localhost:50051", timeout: int = 1800):
        """
        初始化 gRPC 客户端
        
        Args:
            server_address: gRPC 服务器地址
            timeout: 请求超时时间（秒）
        """
        self.server_address = server_address
        self.timeout = timeout
        self.channel: Optional[grpc.aio.Channel] = None
        self.chat_stub = None
        self.session_stub = None
        logger.info(f"🔧 gRPC 客户端配置: {server_address}")
    
    async def connect(self):
        """建立连接"""
        if tool_service_pb2_grpc is None:
            raise ImportError(
                "protobuf 代码未生成，请先运行: bash scripts/generate_grpc.sh"
            )
        
        try:
            logger.info(f"📡 连接到 gRPC 服务器: {self.server_address}")
            
            # 🆕 使用 keepalive 配置选项，防止 "Too many pings" 错误
            channel_options = get_grpc_client_options()
            logger.debug(f"🔧 gRPC 客户端选项: {channel_options}")
            
            self.channel = grpc.aio.insecure_channel(
                self.server_address,
                options=channel_options
            )
            self.chat_stub = tool_service_pb2_grpc.ChatServiceStub(self.channel)
            self.session_stub = tool_service_pb2_grpc.SessionServiceStub(self.channel)
            
            logger.info("✅ gRPC 客户端已连接")
        
        except Exception as e:
            logger.error(f"❌ gRPC 连接失败: {str(e)}", exc_info=True)
            raise
    
    async def close(self):
        """关闭连接"""
        if self.channel:
            logger.info("🛑 关闭 gRPC 连接...")
            await self.channel.close()
            logger.info("✅ gRPC 连接已关闭")
    
    # ==================== Chat 服务 ====================
    
    async def chat(
        self,
        message: str,
        user_id: str,
        conversation_id: Optional[str] = None,
        message_id: Optional[str] = None,
        background_tasks: Optional[List[str]] = None,
        files: Optional[List[Dict[str, str]]] = None,
        variables: Optional[Dict[str, str]] = None,
        agent_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        聊天接口（同步模式）
        
        Args:
            message: 用户消息
            user_id: 用户 ID
            conversation_id: 对话 ID（可选）
            message_id: 消息 ID（可选）
            background_tasks: 后台任务列表（可选）
            files: 文件引用列表（可选）
            variables: 前端上下文变量（可选）
            agent_id: Agent 实例 ID（可选，对应 instances/ 目录名）
            
        Returns:
            聊天响应字典
        """
        if not self.chat_stub:
            raise RuntimeError("gRPC 客户端未连接，请先调用 connect()")
        
        try:
            file_refs = []
            if files:
                for f in files:
                    file_refs.append(
                        tool_service_pb2.FileReference(
                            file_id=f.get("file_id", ""),
                            file_url=f.get("file_url", ""),
                            file_name=f.get("file_name", "")
                        )
                    )
            
            request = tool_service_pb2.ChatRequest(
                message=message,
                user_id=user_id,
                conversation_id=conversation_id or "",
                message_id=message_id or "",
                stream=False,
                background_tasks=background_tasks or [],
                files=file_refs,
                variables=variables or {},
                agent_id=agent_id or ""
            )
            
            response = await self.chat_stub.Chat(request, timeout=self.timeout)
            
            return {
                "code": response.code,
                "message": response.message,
                "task_id": response.task_id,
                "conversation_id": response.conversation_id,
                "status": response.status,
                "result": json.loads(response.result) if response.result else None
            }
        
        except grpc.RpcError as e:
            logger.error(f"❌ gRPC 调用失败: {e.code()}: {e.details()}")
            raise
    
    async def chat_stream(
        self,
        message: str,
        user_id: str,
        conversation_id: Optional[str] = None,
        message_id: Optional[str] = None,
        background_tasks: Optional[List[str]] = None,
        files: Optional[List[Dict[str, str]]] = None,
        variables: Optional[Dict[str, str]] = None,
        agent_id: Optional[str] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        聊天接口（流式模式）
        
        Args:
            message: 用户消息
            user_id: 用户 ID
            conversation_id: 对话 ID（可选）
            message_id: 消息 ID（可选）
            background_tasks: 后台任务列表（可选）
            files: 文件引用列表（可选）
            variables: 前端上下文变量（可选）
            agent_id: Agent 实例 ID（可选，对应 instances/ 目录名）
            
        Yields:
            ZenO 格式的事件字典
        """
        if not self.chat_stub:
            raise RuntimeError("gRPC 客户端未连接，请先调用 connect()")
        
        try:
            file_refs = []
            if files:
                for f in files:
                    file_refs.append(
                        tool_service_pb2.FileReference(
                            file_id=f.get("file_id", ""),
                            file_url=f.get("file_url", ""),
                            file_name=f.get("file_name", "")
                        )
                    )
            
            request = tool_service_pb2.ChatRequest(
                message=message,
                user_id=user_id,
                conversation_id=conversation_id or "",
                message_id=message_id or "",
                stream=True,
                background_tasks=background_tasks or [],
                files=file_refs,
                variables=variables or {},
                agent_id=agent_id or ""
            )
            
            async for event in self.chat_stub.ChatStream(request, timeout=self.timeout):
                zeno_event = json.loads(event.data) if event.data else {}
                
                if event.seq and "seq" not in zeno_event:
                    zeno_event["seq"] = event.seq
                if event.event_uuid and "event_uuid" not in zeno_event:
                    zeno_event["event_uuid"] = event.event_uuid
                
                yield zeno_event
        
        except grpc.RpcError as e:
            logger.error(f"❌ gRPC 流式调用失败: {e.code()}: {e.details()}")
            raise
    
    async def reconnect_stream(
        self,
        session_id: str,
        after_seq: Optional[int] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """重连到已存在的会话"""
        if not self.chat_stub:
            raise RuntimeError("gRPC 客户端未连接，请先调用 connect()")
        
        try:
            request = tool_service_pb2.ReconnectRequest(
                session_id=session_id,
                after_seq=after_seq or 0
            )
            
            async for event in self.chat_stub.ReconnectStream(request, timeout=self.timeout):
                zeno_event = json.loads(event.data) if event.data else {}
                
                if event.seq and "seq" not in zeno_event:
                    zeno_event["seq"] = event.seq
                if event.event_uuid and "event_uuid" not in zeno_event:
                    zeno_event["event_uuid"] = event.event_uuid
                
                yield zeno_event
        
        except grpc.RpcError as e:
            logger.error(f"❌ gRPC 重连失败: {e.code()}: {e.details()}")
            raise
    
    # ==================== Session 服务 ====================
    
    async def get_session_status(self, session_id: str) -> Dict[str, Any]:
        """获取 Session 状态"""
        if not self.session_stub:
            raise RuntimeError("gRPC 客户端未连接，请先调用 connect()")
        
        try:
            request = tool_service_pb2.SessionStatusRequest(session_id=session_id)
            response = await self.session_stub.GetSessionStatus(request, timeout=self.timeout)
            
            return {
                "session_id": response.session_id,
                "user_id": response.user_id,
                "conversation_id": response.conversation_id,
                "message_id": response.message_id,
                "status": response.status,
                "last_event_seq": response.last_event_seq,
                "start_time": response.start_time,
                "last_heartbeat": response.last_heartbeat,
                "progress": response.progress,
                "total_turns": response.total_turns,
                "message_preview": response.message_preview
            }
        
        except grpc.RpcError as e:
            logger.error(f"❌ gRPC 获取 Session 状态失败: {e.code()}: {e.details()}")
            raise
    
    async def stop_session(self, session_id: str) -> Dict[str, Any]:
        """停止 Session"""
        if not self.session_stub:
            raise RuntimeError("gRPC 客户端未连接，请先调用 connect()")
        
        try:
            request = tool_service_pb2.StopSessionRequest(session_id=session_id)
            response = await self.session_stub.StopSession(request, timeout=self.timeout)
            
            return {
                "session_id": response.session_id,
                "status": response.status,
                "stopped_at": response.stopped_at
            }
        
        except grpc.RpcError as e:
            logger.error(f"❌ gRPC 停止 Session 失败: {e.code()}: {e.details()}")
            raise
    
    async def end_session(self, session_id: str) -> Dict[str, Any]:
        """结束 Session"""
        if not self.session_stub:
            raise RuntimeError("gRPC 客户端未连接，请先调用 connect()")
        
        try:
            request = tool_service_pb2.EndSessionRequest(session_id=session_id)
            response = await self.session_stub.EndSession(request, timeout=self.timeout)
            
            return {
                "session_id": response.session_id,
                "summary": json.loads(response.summary) if response.summary else {}
            }
        
        except grpc.RpcError as e:
            logger.error(f"❌ gRPC 结束 Session 失败: {e.code()}: {e.details()}")
            raise
    
    async def list_sessions(self) -> List[Dict[str, Any]]:
        """列出所有活跃会话"""
        if not self.session_stub:
            raise RuntimeError("gRPC 客户端未连接，请先调用 connect()")
        
        try:
            request = tool_service_pb2.ListSessionsRequest()
            response = await self.session_stub.ListSessions(request, timeout=self.timeout)
            
            sessions = []
            for session in response.sessions:
                sessions.append({
                    "session_id": session.session_id,
                    "conversation_id": session.conversation_id,
                    "message_id": session.message_id,
                    "status": session.status,
                    "progress": session.progress,
                    "start_time": session.start_time,
                    "message_preview": session.message_preview
                })
            
            return sessions
        
        except grpc.RpcError as e:
            logger.error(f"❌ gRPC 列出会话失败: {e.code()}: {e.details()}")
            raise
    
    # ==================== 上下文管理器 ====================
    
    async def __aenter__(self):
        """进入上下文时自动连接"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """退出上下文时自动关闭"""
        await self.close()

