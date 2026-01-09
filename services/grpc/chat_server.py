"""
gRPC Chat 服务端实现

对应 routers/chat.py 的 gRPC 版本
用于内部微服务高性能通信
"""

import grpc
import json
import asyncio
from datetime import datetime
from typing import AsyncIterator, Any, Optional
from logger import get_logger

# 导入生成的 protobuf 代码（生成后才可用）
try:
    from services.grpc.generated import tool_service_pb2
    from services.grpc.generated import tool_service_pb2_grpc
except ImportError:
    # 如果还没生成，提供占位符
    tool_service_pb2 = None
    tool_service_pb2_grpc = None

# 导入业务服务
from services import get_chat_service, get_session_service

# 导入 ZenO 格式适配器
from core.events.adapters.zeno import ZenOAdapter

logger = get_logger("grpc_chat_server")


def safe_int(value: Any, default: int = 0) -> int:
    """
    安全地将值转换为整数
    
    Args:
        value: 要转换的值（可能是 int、str、float 或其他）
        default: 转换失败时的默认值
        
    Returns:
        整数值
    """
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        # 处理 ISO 格式时间戳
        if 'T' in value or '-' in value:
            try:
                dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                return int(dt.timestamp() * 1000)
            except (ValueError, TypeError):
                pass
        # 尝试直接转换为整数
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


class ChatServicer(tool_service_pb2_grpc.ChatServiceServicer):
    """
    Chat 服务 gRPC 实现
    
    提供与 routers/chat.py 相同的功能，但使用 gRPC 协议
    """
    
    def __init__(self):
        self.chat_service = get_chat_service()
        self.session_service = get_session_service()
        logger.info("🔧 Chat gRPC Servicer 已初始化")
    
    async def Chat(
        self, 
        request: tool_service_pb2.ChatRequest,
        context: grpc.aio.ServicerContext
    ) -> tool_service_pb2.ChatResponse:
        """
        聊天接口（同步模式）
        
        Args:
            request: 聊天请求
            context: gRPC 上下文
            
        Returns:
            聊天响应（包含 task_id）
        """
        try:
            logger.info(
                f"📨 gRPC 聊天请求: user_id={request.user_id}, "
                f"message={request.message[:50]}..."
            )
            
            # 转换文件引用
            files_data = None
            if request.files:
                files_data = [
                    {
                        "file_id": f.file_id if f.file_id else None,
                        "file_url": f.file_url if f.file_url else None,
                        "file_name": f.file_name if f.file_name else None,
                    }
                    for f in request.files
                ]
            
            # 转换变量
            variables = dict(request.variables) if request.variables else None
            
            # 调用业务服务（同步模式）
            result = await self.chat_service.chat(
                message=request.message,
                user_id=request.user_id,
                conversation_id=request.conversation_id or None,
                message_id=request.message_id or None,
                stream=False,  # 同步模式
                background_tasks=list(request.background_tasks) if request.background_tasks else None,
                files=files_data,
                variables=variables
            )
            
            logger.info(f"✅ gRPC 任务已启动: task_id={result['task_id']}")
            
            # 构建响应
            return tool_service_pb2.ChatResponse(
                code=200,
                message=result.get("message", "任务已启动"),
                task_id=result["task_id"],
                conversation_id=result.get("conversation_id", ""),
                status=result.get("status", "running"),
                result=json.dumps(result) if "result" in result else ""
            )
        
        except Exception as e:
            logger.error(f"❌ gRPC 聊天错误: {str(e)}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"聊天处理失败: {str(e)}")
            return tool_service_pb2.ChatResponse(
                code=500,
                message="聊天处理失败",
                task_id="",
                status="failed"
            )
    
    async def ChatStream(
        self,
        request: tool_service_pb2.ChatRequest,
        context: grpc.aio.ServicerContext
    ) -> AsyncIterator[tool_service_pb2.ChatEvent]:
        """
        聊天接口（流式模式）
        
        使用 ZenO 格式适配器，保持与 HTTP API 一致的事件格式
        
        Args:
            request: 聊天请求
            context: gRPC 上下文
            
        Yields:
            聊天事件流（ZenO 格式）
        """
        try:
            logger.info(
                f"📨 gRPC 流式聊天请求: user_id={request.user_id}, "
                f"message={request.message[:50]}..."
            )
            
            # 转换文件引用
            files_data = None
            if request.files:
                files_data = [
                    {
                        "file_id": f.file_id if f.file_id else None,
                        "file_url": f.file_url if f.file_url else None,
                        "file_name": f.file_name if f.file_name else None,
                    }
                    for f in request.files
                ]
            
            # 转换变量
            variables = dict(request.variables) if request.variables else None
            
            # 🆕 初始化 ZenO 格式适配器（与 HTTP API 保持一致）
            adapter = ZenOAdapter(conversation_id=request.conversation_id or None)
            logger.info("📋 gRPC 流式聊天使用 ZenO 格式适配器")
            
            # 调用业务服务（流式模式）
            async for event in await self.chat_service.chat(
                message=request.message,
                user_id=request.user_id,
                conversation_id=request.conversation_id or None,
                message_id=request.message_id or None,
                stream=True,  # 流式模式
                background_tasks=list(request.background_tasks) if request.background_tasks else None,
                files=files_data,
                variables=variables
            ):
                # 🆕 使用 ZenO 适配器转换事件
                transformed_event = adapter.transform(event)
                
                # 如果适配器过滤了此事件（返回 None），跳过
                if transformed_event is None:
                    continue
                
                # 转换为 gRPC 事件格式
                grpc_event = tool_service_pb2.ChatEvent(
                    event_type=transformed_event.get("type", "message"),
                    data=json.dumps(transformed_event, ensure_ascii=False),
                    timestamp=safe_int(transformed_event.get("timestamp", 0)),
                    seq=safe_int(event.get("seq", 0)),  # seq 使用原始事件的
                    event_uuid=str(event.get("event_uuid", ""))
                )
                
                yield grpc_event
            
            logger.info("✅ gRPC 流式聊天完成")
        
        except Exception as e:
            logger.error(f"❌ gRPC 流式聊天错误: {str(e)}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"流式聊天失败: {str(e)}")
            
            # 发送错误事件
            yield tool_service_pb2.ChatEvent(
                event_type="error",
                data=json.dumps({"error": str(e)}),
                timestamp=0
            )
    
    async def ReconnectStream(
        self,
        request: tool_service_pb2.ReconnectRequest,
        context: grpc.aio.ServicerContext
    ) -> AsyncIterator[tool_service_pb2.ChatEvent]:
        """
        重连到已存在的会话（流式）
        
        使用 ZenO 格式适配器，保持与 HTTP API 一致的事件格式
        
        Args:
            request: 重连请求
            context: gRPC 上下文
            
        Yields:
            聊天事件流（ZenO 格式）
        """
        try:
            logger.info(
                f"📨 gRPC 重连请求: session_id={request.session_id}, "
                f"after_seq={request.after_seq}"
            )
            
            # 检查 Session 是否存在
            status_data = await self.session_service.get_session_status(request.session_id)
            
            if not status_data:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details("Session 不存在或已过期")
                return
            
            session_status = status_data.get("status")
            
            # 如果 Session 已结束
            if session_status in ["completed", "failed", "timeout", "stopped"]:
                context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                context.set_details(f"Session 已结束 (status={session_status})")
                return
            
            # 🆕 初始化 ZenO 格式适配器
            adapter = ZenOAdapter(conversation_id=status_data.get("conversation_id"))
            logger.info("📋 gRPC 重连使用 ZenO 格式适配器")
            
            # 1. 发送重连信息
            reconnect_info = tool_service_pb2.ChatEvent(
                event_type="reconnect_info",
                data=json.dumps({
                    "session_id": request.session_id,
                    "conversation_id": status_data.get("conversation_id"),
                    "message_id": status_data.get("message_id"),
                    "status": session_status,
                    "last_event_seq": status_data.get("last_event_seq", 0)
                }, ensure_ascii=False),
                timestamp=0
            )
            yield reconnect_info
            
            # 2. 获取历史事件
            history_events = await self.session_service.get_session_events(
                session_id=request.session_id,
                after_id=request.after_seq or 0,
                limit=10000
            )
            
            if history_events:
                logger.info(f"📤 推送 {len(history_events)} 个历史事件（使用 ZenO 格式）")
                for event in history_events:
                    # 🆕 使用 ZenO 适配器转换历史事件
                    transformed_event = adapter.transform(event)
                    if transformed_event is None:
                        continue
                    
                    grpc_event = tool_service_pb2.ChatEvent(
                        event_type=transformed_event.get("type", "message"),
                        data=json.dumps(transformed_event, ensure_ascii=False),
                        timestamp=safe_int(transformed_event.get("timestamp", 0)),
                        seq=safe_int(event.get("seq", 0)),
                        event_uuid=str(event.get("event_uuid", ""))
                    )
                    yield grpc_event
            
            # 3. 订阅实时事件
            redis = self.session_service.redis
            last_seq = request.after_seq or 0
            if history_events:
                last_seq = max(safe_int(e.get("seq", 0)) for e in history_events)
            
            logger.info(f"📡 开始订阅实时事件流: after_seq={last_seq}")
            
            async for event in redis.subscribe_events(
                session_id=request.session_id,
                after_id=last_seq,
                timeout=300
            ):
                # 🆕 使用 ZenO 适配器转换实时事件
                transformed_event = adapter.transform(event)
                if transformed_event is None:
                    continue
                
                grpc_event = tool_service_pb2.ChatEvent(
                    event_type=transformed_event.get("type", "message"),
                    data=json.dumps(transformed_event, ensure_ascii=False),
                    timestamp=safe_int(transformed_event.get("timestamp", 0)),
                    seq=safe_int(event.get("seq", 0)),
                    event_uuid=str(event.get("event_uuid", ""))
                )
                yield grpc_event
                
                # 检查是否结束（ZenO 格式的结束事件）
                if transformed_event.get("type") in ["message.assistant.done", "message.assistant.error"]:
                    break
            
            logger.info("✅ gRPC 重连流结束")
        
        except Exception as e:
            logger.error(f"❌ gRPC 重连错误: {str(e)}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"重连失败: {str(e)}")
            
            # 发送错误事件
            yield tool_service_pb2.ChatEvent(
                event_type="error",
                data=json.dumps({"error": str(e)}),
                timestamp=0
            )

