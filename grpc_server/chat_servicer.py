"""
gRPC Chat 服务端实现

对应 routers/chat.py 的 gRPC 版本
业务逻辑复用 services/chat_service.py
"""

import grpc
import json
from datetime import datetime
from typing import AsyncIterator, Any
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
from services.session_service import SessionNotFoundError

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
            
            # 调用业务服务
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
        保持与 HTTP API 一致的事件格式
        
        🆕 优化：
        - 检测客户端断开连接，提前终止处理
        - 记录更详细的错误信息
        """
        event_count = 0
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
            
            # 调用业务服务（流式模式），与 HTTP API 保持一致
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
                # 🆕 检查客户端是否已断开连接
                if context.cancelled():
                    logger.warning(
                        f"⚠️ gRPC 客户端已断开连接，停止流式响应: "
                        f"user_id={request.user_id}, events_sent={event_count}"
                    )
                    return
                
                if event is None:
                    continue
                
                event_count += 1
                
                # 直接返回原始 event JSON，与 HTTP API 完全一致
                yield tool_service_pb2.ChatEvent(
                    data=json.dumps(event, ensure_ascii=False)
                )
            
            logger.info(f"✅ gRPC 流式聊天完成: events_sent={event_count}")
        
        except Exception as e:
            error_str = str(e)
            # 🆕 区分连接断开和其他错误
            if context.cancelled() or "cancelled" in error_str.lower():
                logger.warning(
                    f"⚠️ gRPC 流式聊天被取消: user_id={request.user_id}, "
                    f"events_sent={event_count}, reason={error_str}"
                )
                return
            
            logger.error(
                f"❌ gRPC 流式聊天错误: {error_str}, "
                f"events_sent={event_count}",
                exc_info=True
            )
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"流式聊天失败: {error_str}")
            
            # 与 HTTP API 错误格式一致
            error_event = {
                "type": "message.assistant.error",
                "message_id": request.message_id or "",
                "timestamp": int(datetime.now().timestamp() * 1000),
                "error": {
                    "type": "unknown",
                    "code": "INTERNAL_ERROR",
                    "message": error_str,
                    "retryable": False
                }
            }
            yield tool_service_pb2.ChatEvent(
                data=json.dumps(error_event, ensure_ascii=False)
            )
    
    async def ReconnectStream(
        self,
        request: tool_service_pb2.ReconnectRequest,
        context: grpc.aio.ServicerContext
    ) -> AsyncIterator[tool_service_pb2.ChatEvent]:
        """
        重连到已存在的会话（流式）
        
        🆕 优化：
        - 检测客户端断开连接，提前终止处理
        - 记录更详细的错误信息
        """
        event_count = 0
        try:
            logger.info(
                f"📨 gRPC 重连请求: session_id={request.session_id}, "
                f"after_seq={request.after_seq}"
            )
            
            # 检查 Session 是否存在
            try:
                status_data = await self.session_service.get_session_status(request.session_id)
            except SessionNotFoundError:
                # Session 不存在：返回友好的通知事件，不设置 gRPC 错误状态
                logger.info(
                    f"📋 Session 不存在或已过期（预检查）: session_id={request.session_id}"
                )
                info_event = {
                    "type": "message.assistant.info",
                    "message_id": "",
                    "timestamp": int(datetime.now().timestamp() * 1000),
                    "info": {
                        "type": "session_not_found",
                        "code": "SESSION_NOT_FOUND",
                        "message": "会话不存在或已过期，请创建新会话",
                        "action": "create_new_session",
                        "session_id": request.session_id
                    }
                }
                yield tool_service_pb2.ChatEvent(
                    data=json.dumps(info_event, ensure_ascii=False)
                )
                return
            
            if not status_data:
                # 理论上不会到达这里（get_session_status 会抛异常）
                logger.info(
                    f"📋 Session 状态为空: session_id={request.session_id}"
                )
                info_event = {
                    "type": "message.assistant.info",
                    "message_id": "",
                    "timestamp": int(datetime.now().timestamp() * 1000),
                    "info": {
                        "type": "session_not_found",
                        "code": "SESSION_NOT_FOUND",
                        "message": "会话不存在或已过期，请创建新会话",
                        "action": "create_new_session",
                        "session_id": request.session_id
                    }
                }
                yield tool_service_pb2.ChatEvent(
                    data=json.dumps(info_event, ensure_ascii=False)
                )
                return
            
            session_status = status_data.get("status")
            
            if session_status in ["completed", "failed", "timeout", "stopped"]:
                context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                context.set_details(f"Session 已结束 (status={session_status})")
                return
            
            # 初始化 ZenO 格式适配器
            adapter = ZenOAdapter(conversation_id=status_data.get("conversation_id"))
            logger.info("📋 gRPC 重连使用 ZenO 格式适配器")
            
            # 获取历史事件
            history_events = await self.session_service.get_session_events(
                session_id=request.session_id,
                after_id=request.after_seq or 0,
                limit=10000
            )
            
            if history_events:
                logger.info(f"📤 推送 {len(history_events)} 个历史事件")
                for event in history_events:
                    # 🆕 检查客户端是否已断开连接
                    if context.cancelled():
                        logger.warning(
                            f"⚠️ gRPC 重连客户端断开（历史事件阶段）: "
                            f"session_id={request.session_id}, events_sent={event_count}"
                        )
                        return
                    
                    # 🔧 与 HTTP API 一致：判断事件是否已经是 zeno 格式
                    event_type = event.get("type", "")
                    is_zeno_format = event_type.startswith("message.assistant.") or event_type == "reconnect_info"
                    
                    if is_zeno_format:
                        # 已经是 zeno 格式，直接透传
                        output_event = event
                    else:
                        # 需要转换
                        output_event = adapter.transform(event)
                        if output_event is None:
                            continue
                    
                    event_count += 1
                    yield tool_service_pb2.ChatEvent(
                        data=json.dumps(output_event, ensure_ascii=False)
                    )
            
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
                # 🆕 检查客户端是否已断开连接
                if context.cancelled():
                    logger.warning(
                        f"⚠️ gRPC 重连客户端断开（实时事件阶段）: "
                        f"session_id={request.session_id}, events_sent={event_count}"
                    )
                    return
                
                # 🔧 与 HTTP API 一致：判断事件是否已经是 zeno 格式
                event_type = event.get("type", "")
                is_zeno_format = event_type.startswith("message.assistant.") or event_type == "reconnect_info"
                
                if is_zeno_format:
                    output_event = event
                else:
                    output_event = adapter.transform(event)
                    if output_event is None:
                        continue
                
                event_count += 1
                yield tool_service_pb2.ChatEvent(
                    data=json.dumps(output_event, ensure_ascii=False)
                )
                
                # 🔧 与 HTTP API 一致的结束条件
                output_type = output_event.get("type", "")
                if output_type in ["session_end", "message_complete", "message.assistant.done"]:
                    break
            
            logger.info(f"✅ gRPC 重连流结束: events_sent={event_count}")
        
        except SessionNotFoundError as e:
            # 🆕 Session 不存在：这是预期的业务场景，不应该记录 ERROR 也不设置 gRPC 错误状态
            logger.info(
                f"📋 Session 不存在或已过期: session_id={request.session_id}"
            )
            # ⚠️ 不设置 gRPC 错误状态码，避免触发上层错误报警
            # context.set_code(grpc.StatusCode.NOT_FOUND)
            # context.set_details(f"Session 不存在或已过期: {request.session_id}")
            
            # 返回友好的通知事件（而非错误事件），告知客户端需要创建新会话
            # 使用 "message.assistant.info" 类型，表示这是信息提示而非错误
            info_event = {
                "type": "message.assistant.info",
                "message_id": "",
                "timestamp": int(datetime.now().timestamp() * 1000),
                "info": {
                    "type": "session_not_found",
                    "code": "SESSION_NOT_FOUND",
                    "message": "会话不存在或已过期，请创建新会话",
                    "action": "create_new_session",
                    "session_id": request.session_id
                }
            }
            yield tool_service_pb2.ChatEvent(
                data=json.dumps(info_event, ensure_ascii=False)
            )
        
        except Exception as e:
            error_str = str(e)
            # 🆕 区分连接断开和其他错误
            if context.cancelled() or "cancelled" in error_str.lower():
                logger.warning(
                    f"⚠️ gRPC 重连被取消: session_id={request.session_id}, "
                    f"events_sent={event_count}, reason={error_str}"
                )
                return
            
            logger.error(
                f"❌ gRPC 重连错误: {error_str}, "
                f"session_id={request.session_id}, events_sent={event_count}",
                exc_info=True
            )
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"重连失败: {error_str}")
            
            # 与 HTTP API 错误格式一致
            error_event = {
                "type": "message.assistant.error",
                "message_id": "",
                "timestamp": int(datetime.now().timestamp() * 1000),
                "error": {
                    "type": "unknown",
                    "code": "INTERNAL_ERROR",
                    "message": error_str,
                    "retryable": False
                }
            }
            yield tool_service_pb2.ChatEvent(
                data=json.dumps(error_event, ensure_ascii=False)
            )
