"""
gRPC Chat 服务端实现

对应 routers/chat.py 的 gRPC 版本
业务逻辑复用 services/chat_service.py
"""

import grpc
import json
import asyncio
from datetime import datetime
from typing import AsyncIterator, Any, Optional
from logger import get_logger

# 导入生成的 protobuf 代码
try:
    from grpc_server.generated import tool_service_pb2
    from grpc_server.generated import tool_service_pb2_grpc
    _GRPC_AVAILABLE = True
except ImportError as e:
    tool_service_pb2 = None
    tool_service_pb2_grpc = None
    _GRPC_AVAILABLE = False
    import logging
    logging.getLogger(__name__).warning(f"gRPC protobuf 代码未生成: {e}")

# 创建基类（如果 gRPC 不可用，使用 object 作为基类）
_ChatServicerBase = (
    tool_service_pb2_grpc.ChatServiceServicer 
    if _GRPC_AVAILABLE and tool_service_pb2_grpc 
    else object
)

# 导入业务服务（复用 services 层）
from services import get_chat_service, get_session_service

# 导入 ZenO 格式适配器
from core.events.adapters.zeno import ZenOAdapter

logger = get_logger("grpc_chat_servicer")


def safe_int(value: Any, default: int = 0) -> int:
    """
    安全地将值转换为整数
    
    Args:
        value: 要转换的值
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
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


class ChatServicer(_ChatServicerBase):
    """
    Chat 服务 gRPC 实现
    
    提供与 routers/chat.py 相同的功能，使用 gRPC 协议
    业务逻辑复用 services/chat_service.py
    """
    
    def __init__(self):
        # 复用业务服务层
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
        
        注意：当 ChatService 启用 mock 模式时，会返回 mock 任务信息
        
        Args:
            request: 聊天请求
            context: gRPC 上下文
            
        Returns:
            聊天响应
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
            
            # 获取 agent_id（默认为 dazee_agent）
            agent_id = request.agent_id if request.agent_id else "dazee_agent"
            
            # 调用业务服务（同步模式，mock 模式下会返回 mock 任务信息）
            result = await self.chat_service.chat(
                message=request.message,
                user_id=request.user_id,
                conversation_id=request.conversation_id or None,
                message_id=request.message_id or None,
                stream=False,
                background_tasks=list(request.background_tasks) if request.background_tasks else None,
                files=files_data,
                variables=variables,
                agent_id=agent_id
            )
            
            logger.info(f"✅ gRPC 任务已启动: task_id={result['task_id']}")
            
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
        
        使用 output_format="zeno" 让 EventBroadcaster 在内部处理格式转换，
        保持与 HTTP API 一致的事件格式（包括 progress、intent 等 delta 事件）
        
        注意：当 ChatService 启用 mock 模式时，会自动返回 mock 数据流
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

            
            # 获取 agent_id（默认为 dazee_agent）
            agent_id = request.agent_id if request.agent_id else "dazee_agent"
            
            # 获取 agent_id（默认为 dazee_agent）
            agent_id = request.agent_id if request.agent_id else "dazee_agent"
            
            # 调用业务服务（流式模式）
            # 🔧 传递 output_format="zeno"，让 EventBroadcaster 在内部处理格式转换
            # 这样 progress、intent 等 delta 事件会被正确转换为 ZenO 格式
            event_stream = await self.chat_service.chat(
                message=request.message,
                user_id=request.user_id,
                conversation_id=request.conversation_id or None,
                message_id=request.message_id or None,
                stream=True,
                background_tasks=list(request.background_tasks) if request.background_tasks else None,
                files=files_data,
                variables=variables,
                agent_id=agent_id,
                output_format="zeno"  # 🆕 与 HTTP API 保持一致
            )
            
            async for event in event_stream:
                # 事件已在内部转换为 ZenO 格式，直接使用
                transformed_event = event
                
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
            
            logger.info("✅ gRPC 流式聊天完成")
        
        except Exception as e:
            logger.error(f"❌ gRPC 流式聊天错误: {str(e)}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"流式聊天失败: {str(e)}")
            
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
            
            if session_status in ["completed", "failed", "timeout", "stopped"]:
                context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                context.set_details(f"Session 已结束 (status={session_status})")
                return
            
            # 初始化 ZenO 格式适配器
            adapter = ZenOAdapter(conversation_id=status_data.get("conversation_id"))
            logger.info("📋 gRPC 重连使用 ZenO 格式适配器")
            
            # 发送重连信息
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
            
            # 获取历史事件
            history_events = await self.session_service.get_session_events(
                session_id=request.session_id,
                after_id=request.after_seq or 0,
                limit=10000
            )
            
            if history_events:
                logger.info(f"📤 推送 {len(history_events)} 个历史事件")
                for event in history_events:
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
            
            # 订阅实时事件
            redis = self.session_service.redis
            last_seq = request.after_seq or 0
            if history_events:
                last_seq = max(safe_int(e.get("seq", 0)) for e in history_events)
            
            logger.info(f"📡 开始订阅实时事件流: after_seq={last_seq}")
            
            async for event in redis.subscribe_events(
                session_id=request.session_id,
                after_id=last_seq,
                timeout=1800
            ):
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
                
                if transformed_event.get("type") in ["message.assistant.done", "message.assistant.error"]:
                    break
            
            logger.info("✅ gRPC 重连流结束")
        
        except Exception as e:
            logger.error(f"❌ gRPC 重连错误: {str(e)}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"重连失败: {str(e)}")
            
            yield tool_service_pb2.ChatEvent(
                event_type="error",
                data=json.dumps({"error": str(e)}),
                timestamp=0
            )
    
    async def ChatMockStream(
        self,
        request: tool_service_pb2.ChatMockRequest,
        context: grpc.aio.ServicerContext
    ) -> AsyncIterator[tool_service_pb2.ChatEvent]:
        """
        Mock 流式接口（用于前端测试）
        
        返回预定义的 ZenO 格式事件流，无需调用真实 Agent
        
        Args:
            request: Mock 请求，包含 scenario 和 delay_ms
            context: gRPC 上下文
            
        Yields:
            ChatEvent 事件流
        """
        try:
            scenario = request.scenario or "analytics"
            delay_ms = request.delay_ms if request.delay_ms > 0 else 50
            
            logger.info(f"📨 gRPC Mock 请求: scenario={scenario}, delay={delay_ms}ms")
            
            # 调用 chat_service 的 mock 方法
            async for sse_line in self.chat_service.chat_mock(
                scenario=scenario,
                delay_ms=delay_ms
            ):
                # chat_mock 返回的是 "data: {...}\n\n" 格式，需要解析
                if sse_line.startswith("data: "):
                    json_str = sse_line[6:].strip()
                    if json_str:
                        try:
                            event_data = json.loads(json_str)
                            
                            grpc_event = tool_service_pb2.ChatEvent(
                                event_type=event_data.get("type", "message"),
                                data=json_str,
                                timestamp=safe_int(event_data.get("timestamp", 0)),
                                seq=safe_int(event_data.get("seq", 0)),
                                event_uuid=""
                            )
                            
                            yield grpc_event
                        except json.JSONDecodeError:
                            continue
            
            logger.info("✅ gRPC Mock 流完成")
        
        except Exception as e:
            logger.error(f"❌ gRPC Mock 错误: {str(e)}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Mock 流失败: {str(e)}")
            
            yield tool_service_pb2.ChatEvent(
                event_type="error",
                data=json.dumps({"error": str(e)}),
                timestamp=0
            )

