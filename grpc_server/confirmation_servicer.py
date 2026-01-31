"""
gRPC Confirmation 服务实现

提供 HITL (Human-in-the-Loop) 确认功能的 gRPC 接口
"""

import grpc
from typing import Optional
from datetime import datetime

from logger import get_logger
from services.confirmation_service import (
    get_confirmation_service,
    ConfirmationService,
    ConfirmationNotFoundError,
    ConfirmationExpiredError,
    ConfirmationResponseError,
)

# 导入生成的 protobuf 代码
try:
    from grpc_server.generated import tool_service_pb2
    from grpc_server.generated import tool_service_pb2_grpc
except ImportError:
    tool_service_pb2 = None
    tool_service_pb2_grpc = None

logger = get_logger("grpc_confirmation")


class ConfirmationServicer(tool_service_pb2_grpc.ConfirmationServiceServicer):
    """
    gRPC Confirmation 服务实现
    
    封装 ConfirmationService，提供 gRPC 接口
    """
    
    def __init__(self):
        """初始化服务"""
        self._service: ConfirmationService = get_confirmation_service()
        logger.info("ConfirmationServicer 初始化完成")
    
    async def GetPendingRequests(
        self,
        request: tool_service_pb2.GetPendingRequestsRequest,
        context: grpc.aio.ServicerContext
    ) -> tool_service_pb2.GetPendingRequestsResponse:
        """
        获取待处理的确认请求
        """
        try:
            session_id = request.session_id if request.HasField("session_id") else None
            
            requests = self._service.get_pending_requests(session_id)
            
            # 转换为 protobuf 消息
            request_infos = []
            for req in requests:
                info = tool_service_pb2.ConfirmationRequestInfo(
                    request_id=req.request_id,
                    question=req.question,
                    options=req.options,
                    timeout=req.timeout if req.timeout is not None else 0,
                    confirmation_type=req.confirmation_type.value,
                    session_id=req.session_id,
                    created_at=req.created_at.isoformat(),
                    is_expired=req.is_expired()
                )
                # 添加 metadata
                if req.metadata:
                    for k, v in req.metadata.items():
                        info.metadata[k] = str(v)
                request_infos.append(info)
            
            logger.debug(f"获取待处理请求: count={len(request_infos)}, session_id={session_id}")
            
            return tool_service_pb2.GetPendingRequestsResponse(
                requests=request_infos,
                total=len(request_infos)
            )
        
        except Exception as e:
            logger.error(f"获取待处理请求失败: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return tool_service_pb2.GetPendingRequestsResponse()
    
    async def SubmitResponse(
        self,
        request: tool_service_pb2.SubmitConfirmationRequest,
        context: grpc.aio.ServicerContext
    ) -> tool_service_pb2.SubmitConfirmationResponse:
        """
        提交确认响应
        """
        try:
            request_id = request.request_id
            response = request.response
            metadata = dict(request.metadata) if request.metadata else None
            
            logger.info(f"收到确认响应: request_id={request_id}, response={response}")
            
            result = self._service.submit_response(request_id, response, metadata)
            
            return tool_service_pb2.SubmitConfirmationResponse(
                success=True,
                request_id=result["request_id"],
                response=str(result["response"])
            )
        
        except ConfirmationNotFoundError as e:
            logger.warning(f"确认请求不存在: {e}")
            return tool_service_pb2.SubmitConfirmationResponse(
                success=False,
                request_id=request.request_id,
                error=str(e)
            )
        
        except ConfirmationExpiredError as e:
            logger.warning(f"确认请求已过期: {e}")
            return tool_service_pb2.SubmitConfirmationResponse(
                success=False,
                request_id=request.request_id,
                error=str(e)
            )
        
        except ConfirmationResponseError as e:
            logger.error(f"设置响应失败: {e}")
            return tool_service_pb2.SubmitConfirmationResponse(
                success=False,
                request_id=request.request_id,
                error=str(e)
            )
        
        except Exception as e:
            logger.error(f"提交响应失败: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return tool_service_pb2.SubmitConfirmationResponse(
                success=False,
                error=str(e)
            )
    
    async def CancelRequest(
        self,
        request: tool_service_pb2.CancelConfirmationRequest,
        context: grpc.aio.ServicerContext
    ) -> tool_service_pb2.CancelConfirmationResponse:
        """
        取消确认请求
        """
        try:
            request_id = request.request_id
            
            logger.info(f"取消确认请求: request_id={request_id}")
            
            success = self._service.cancel_request(request_id)
            
            return tool_service_pb2.CancelConfirmationResponse(success=success)
        
        except ConfirmationNotFoundError as e:
            logger.warning(f"取消失败，请求不存在: {e}")
            return tool_service_pb2.CancelConfirmationResponse(
                success=False,
                error=str(e)
            )
        
        except Exception as e:
            logger.error(f"取消请求失败: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return tool_service_pb2.CancelConfirmationResponse(
                success=False,
                error=str(e)
            )
    
    async def GetStats(
        self,
        request: tool_service_pb2.ConfirmationStatsRequest,
        context: grpc.aio.ServicerContext
    ) -> tool_service_pb2.ConfirmationStatsResponse:
        """
        获取统计信息
        """
        try:
            stats = self._service.get_stats()
            
            return tool_service_pb2.ConfirmationStatsResponse(
                pending_count=stats.get("pending_count", 0),
                history_count=stats.get("history_count", 0),
                pending_sessions=stats.get("pending_sessions", [])
            )
        
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return tool_service_pb2.ConfirmationStatsResponse()
    
    async def WatchConfirmations(
        self,
        request: tool_service_pb2.WatchConfirmationsRequest,
        context: grpc.aio.ServicerContext
    ):
        """
        监听确认请求（流式）
        
        注意：这是一个简化实现，实际生产环境可能需要更复杂的事件订阅机制
        """
        import asyncio
        
        session_id = request.session_id if request.HasField("session_id") else None
        
        logger.info(f"开始监听确认请求: session_id={session_id}")
        
        try:
            # 发送当前待处理的请求
            pending = self._service.get_pending_requests(session_id)
            for req in pending:
                info = tool_service_pb2.ConfirmationRequestInfo(
                    request_id=req.request_id,
                    question=req.question,
                    options=req.options,
                    timeout=req.timeout if req.timeout is not None else 0,
                    confirmation_type=req.confirmation_type.value,
                    session_id=req.session_id,
                    created_at=req.created_at.isoformat(),
                    is_expired=req.is_expired()
                )
                if req.metadata:
                    for k, v in req.metadata.items():
                        info.metadata[k] = str(v)
                
                yield tool_service_pb2.ConfirmationEvent(
                    event_type="existing",
                    request=info,
                    timestamp=int(datetime.now().timestamp() * 1000)
                )
            
            # 持续监听新请求（简化实现：轮询）
            seen_ids = set(req.request_id for req in pending)
            
            while not context.cancelled():
                await asyncio.sleep(1)  # 每秒检查一次
                
                current = self._service.get_pending_requests(session_id)
                
                for req in current:
                    if req.request_id not in seen_ids:
                        seen_ids.add(req.request_id)
                        
                        info = tool_service_pb2.ConfirmationRequestInfo(
                            request_id=req.request_id,
                            question=req.question,
                            options=req.options,
                            timeout=req.timeout if req.timeout is not None else 0,
                            confirmation_type=req.confirmation_type.value,
                            session_id=req.session_id,
                            created_at=req.created_at.isoformat(),
                            is_expired=req.is_expired()
                        )
                        if req.metadata:
                            for k, v in req.metadata.items():
                                info.metadata[k] = str(v)
                        
                        yield tool_service_pb2.ConfirmationEvent(
                            event_type="new",
                            request=info,
                            timestamp=int(datetime.now().timestamp() * 1000)
                        )
                
                # 检查已响应/过期的请求
                current_ids = set(req.request_id for req in current)
                removed_ids = seen_ids - current_ids - {""}
                
                for removed_id in removed_ids:
                    seen_ids.discard(removed_id)
                    # 发送移除事件
                    yield tool_service_pb2.ConfirmationEvent(
                        event_type="removed",
                        request=tool_service_pb2.ConfirmationRequestInfo(
                            request_id=removed_id
                        ),
                        timestamp=int(datetime.now().timestamp() * 1000)
                    )
        
        except asyncio.CancelledError:
            logger.info(f"监听已取消: session_id={session_id}")
        except Exception as e:
            logger.error(f"监听异常: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
