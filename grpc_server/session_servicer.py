"""
gRPC Session 服务端实现

对应 routers/chat.py 中的 Session 管理接口
业务逻辑复用 services/session_service.py
"""

import grpc
import json
from datetime import datetime
from typing import Any
from logger import get_logger

# 导入生成的 protobuf 代码
try:
    from grpc_server.generated import tool_service_pb2
    from grpc_server.generated import tool_service_pb2_grpc
except ImportError:
    tool_service_pb2 = None
    tool_service_pb2_grpc = None

# 导入业务服务（复用 services 层）
from services import get_session_service, SessionNotFoundError

logger = get_logger("grpc_session_servicer")


def safe_int(value: Any, default: int = 0) -> int:
    """安全地将值转换为整数"""
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        if 'T' in value or '-' in value:
            try:
                dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                return int(dt.timestamp() * 1000)
            except (ValueError, TypeError):
                pass
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


class SessionServicer(tool_service_pb2_grpc.SessionServiceServicer):
    """
    Session 服务 gRPC 实现
    
    提供会话管理功能，业务逻辑复用 services/session_service.py
    """
    
    def __init__(self):
        # 复用业务服务层
        self.session_service = get_session_service()
        logger.info("🔧 Session gRPC Servicer 已初始化")
    
    async def GetSessionStatus(
        self,
        request: tool_service_pb2.SessionStatusRequest,
        context: grpc.aio.ServicerContext
    ) -> tool_service_pb2.SessionStatusResponse:
        """获取 Session 状态"""
        try:
            logger.info(f"📨 gRPC 查询 Session 状态: {request.session_id}")
            
            status_data = await self.session_service.get_session_status(request.session_id)
            
            return tool_service_pb2.SessionStatusResponse(
                session_id=status_data["session_id"],
                user_id=status_data.get("user_id", ""),
                conversation_id=status_data.get("conversation_id", ""),
                message_id=status_data.get("message_id", ""),
                status=status_data.get("status", "unknown"),
                last_event_seq=status_data.get("last_event_seq", 0),
                start_time=status_data.get("start_time", ""),
                last_heartbeat=status_data.get("last_heartbeat", ""),
                progress=status_data.get("progress", 0.0),
                total_turns=status_data.get("total_turns", 0),
                message_preview=status_data.get("message_preview", "")
            )
        
        except SessionNotFoundError as e:
            logger.warning(f"⚠️ Session 不存在: {str(e)}")
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("Session 不存在或已过期")
            return tool_service_pb2.SessionStatusResponse()
        
        except Exception as e:
            logger.error(f"❌ gRPC 查询 Session 状态错误: {str(e)}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"查询失败: {str(e)}")
            return tool_service_pb2.SessionStatusResponse()
    
    async def GetSessionEvents(
        self,
        request: tool_service_pb2.SessionEventsRequest,
        context: grpc.aio.ServicerContext
    ) -> tool_service_pb2.SessionEventsResponse:
        """获取 Session 事件列表"""
        try:
            logger.info(
                f"📨 gRPC 获取 Session 事件: {request.session_id}, "
                f"after_id={request.after_id}, limit={request.limit}"
            )
            
            events = await self.session_service.get_session_events(
                session_id=request.session_id,
                after_id=request.after_id or 0,
                limit=request.limit or 100
            )
            
            grpc_events = []
            for event in events:
                grpc_event = tool_service_pb2.ChatEvent(
                    event_type=event.get("type", "message"),
                    data=json.dumps(event, ensure_ascii=False),
                    timestamp=safe_int(event.get("timestamp", 0)),
                    seq=safe_int(event.get("seq", 0)),
                    event_uuid=str(event.get("event_uuid", ""))
                )
                grpc_events.append(grpc_event)
            
            last_event_id = 0
            if events:
                last_event = events[-1]
                last_event_id = safe_int(last_event.get("seq", last_event.get("id", 0)))
            
            return tool_service_pb2.SessionEventsResponse(
                session_id=request.session_id,
                events=grpc_events,
                total=len(events),
                has_more=len(events) >= (request.limit or 100),
                last_event_id=last_event_id
            )
        
        except SessionNotFoundError as e:
            logger.warning(f"⚠️ Session 不存在: {str(e)}")
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("Session 不存在或已过期")
            return tool_service_pb2.SessionEventsResponse()
        
        except Exception as e:
            logger.error(f"❌ gRPC 获取 Session 事件错误: {str(e)}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"获取失败: {str(e)}")
            return tool_service_pb2.SessionEventsResponse()
    
    async def GetUserSessions(
        self,
        request: tool_service_pb2.UserSessionsRequest,
        context: grpc.aio.ServicerContext
    ) -> tool_service_pb2.UserSessionsResponse:
        """获取用户的所有活跃会话"""
        try:
            logger.info(f"📨 gRPC 获取用户会话: {request.user_id}")
            
            sessions = await self.session_service.get_user_sessions(request.user_id)
            
            grpc_sessions = []
            for session in sessions:
                grpc_session = tool_service_pb2.SessionInfo(
                    session_id=session["session_id"],
                    conversation_id=session.get("conversation_id", ""),
                    message_id=session.get("message_id", ""),
                    status=session.get("status", "unknown"),
                    progress=session.get("progress", 0.0),
                    start_time=session.get("start_time", ""),
                    message_preview=session.get("message_preview", "")
                )
                grpc_sessions.append(grpc_session)
            
            return tool_service_pb2.UserSessionsResponse(
                user_id=request.user_id,
                sessions=grpc_sessions,
                total=len(sessions)
            )
        
        except Exception as e:
            logger.error(f"❌ gRPC 获取用户会话错误: {str(e)}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"获取失败: {str(e)}")
            return tool_service_pb2.UserSessionsResponse()
    
    async def StopSession(
        self,
        request: tool_service_pb2.StopSessionRequest,
        context: grpc.aio.ServicerContext
    ) -> tool_service_pb2.StopSessionResponse:
        """停止会话"""
        try:
            logger.info(f"📨 gRPC 停止 Session: {request.session_id}")
            
            result = await self.session_service.stop_session(request.session_id)
            
            return tool_service_pb2.StopSessionResponse(
                session_id=result["session_id"],
                status=result.get("status", "stopped"),
                stopped_at=result.get("stopped_at", "")
            )
        
        except SessionNotFoundError as e:
            logger.warning(f"⚠️ Session 不存在: {str(e)}")
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("Session 不存在或已过期")
            return tool_service_pb2.StopSessionResponse()
        
        except Exception as e:
            logger.error(f"❌ gRPC 停止 Session 错误: {str(e)}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"停止失败: {str(e)}")
            return tool_service_pb2.StopSessionResponse()
    
    async def EndSession(
        self,
        request: tool_service_pb2.EndSessionRequest,
        context: grpc.aio.ServicerContext
    ) -> tool_service_pb2.EndSessionResponse:
        """结束会话"""
        try:
            logger.info(f"📨 gRPC 结束 Session: {request.session_id}")
            
            summary = await self.session_service.end_session(request.session_id)
            
            return tool_service_pb2.EndSessionResponse(
                session_id=request.session_id,
                summary=json.dumps(summary, ensure_ascii=False)
            )
        
        except SessionNotFoundError as e:
            logger.warning(f"⚠️ Session 不存在: {str(e)}")
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("Session 不存在或已过期")
            return tool_service_pb2.EndSessionResponse()
        
        except Exception as e:
            logger.error(f"❌ gRPC 结束 Session 错误: {str(e)}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"结束失败: {str(e)}")
            return tool_service_pb2.EndSessionResponse()
    
    async def ListSessions(
        self,
        request: tool_service_pb2.ListSessionsRequest,
        context: grpc.aio.ServicerContext
    ) -> tool_service_pb2.ListSessionsResponse:
        """列出所有活跃会话"""
        try:
            logger.info("📨 gRPC 列出所有会话")
            
            sessions = await self.session_service.list_sessions()
            
            grpc_sessions = []
            for session in sessions:
                grpc_session = tool_service_pb2.SessionInfo(
                    session_id=session["session_id"],
                    conversation_id=session.get("conversation_id", ""),
                    message_id=session.get("message_id", ""),
                    status=session.get("status", "unknown"),
                    progress=session.get("progress", 0.0),
                    start_time=session.get("start_time", ""),
                    message_preview=session.get("message_preview", "")
                )
                grpc_sessions.append(grpc_session)
            
            return tool_service_pb2.ListSessionsResponse(
                sessions=grpc_sessions,
                total=len(sessions)
            )
        
        except Exception as e:
            logger.error(f"❌ gRPC 列出会话错误: {str(e)}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"列出失败: {str(e)}")
            return tool_service_pb2.ListSessionsResponse()

