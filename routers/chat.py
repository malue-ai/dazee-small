"""
Chat 相关的路由
包含同步聊天、流式聊天、会话管理、结果改进等功能
"""

from logger import get_logger
import json
from enum import Enum
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from typing import Dict, Any
from datetime import datetime

from models.api import APIResponse
from models.chat import (
    ChatRequest,
    ChatResponse,
    StreamEvent,
    SessionInfo,
    RefineRequest
)
from core.agent import SimpleAgent

# 配置日志
logger = get_logger("chat")

# 创建路由器
router = APIRouter(
    prefix="/api/v1",
    tags=["chat"],
    responses={404: {"description": "Not found"}},
)


def sanitize_for_json(obj: Any) -> Any:
    """
    清理对象使其可以JSON序列化
    处理Enum、ToolType等不可序列化的对象
    """
    if obj is None:
        return None
    elif isinstance(obj, Enum):
        return obj.value
    elif isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [sanitize_for_json(item) for item in obj]
    elif isinstance(obj, (str, int, float, bool)):
        return obj
    else:
        # 尝试转换为字符串
        try:
            return str(obj)
        except Exception:
            return None


def cleanup_inactive_sessions():
    """清理不活跃的会话"""
    # 从 main 模块导入 agent_pool
    from main import agent_pool
    
    inactive_sessions = [
        sid for sid, agent in agent_pool.items()
        if not agent._session_active
    ]
    for sid in inactive_sessions:
        del agent_pool[sid]


@router.post("/chat")
async def chat(request: ChatRequest, background_tasks: BackgroundTasks):
    """
    统一聊天接口（支持同步和流式）
    
    根据 `stream` 参数自动选择返回模式（默认为流式）
    
    ## 参数
    - **message**: 用户消息（必填）
    - **session_id**: 会话ID（可选，不提供则自动创建新会话）
    - **stream**: 是否使用流式输出（默认为 true）
    
    ## 返回
    - `stream=true`: Server-Sent Events (SSE) 事件流，实时返回思考过程和工具执行进度
    - `stream=false`: 完整的 JSON 响应，等待任务完成后一次性返回
    
    ## 流式事件类型
    - `session_start` / `turn_start`: 会话/轮次开始
    - `status`: 状态消息
    - `intent_analysis`: 意图识别结果
    - `tool_selection`: 工具筛选结果
    - `thinking`: LLM 思考过程（增量）
    - `content`: LLM 回复内容（增量）
    - `tool_call_start`: 工具调用开始
    - `tool_call_complete`: 工具执行完成
    - `plan_update`: Plan 进度更新
    - `complete`: 任务完成
    - `error`: 错误信息
    - `done`: 流结束
    
    ## 示例 - 流式模式（推荐）
    ```python
    import requests
    
    response = requests.post(
        "http://localhost:8000/api/v1/chat",
        json={"message": "生成一个PPT", "stream": True},
        stream=True
    )
    
    for line in response.iter_lines():
        if line:
            line = line.decode('utf-8')
            if line.startswith('data: '):
                event = json.loads(line[6:])
                print(event['type'], event['data'])
    ```
    
    ## 示例 - 同步模式
    ```python
    import requests
    
    response = requests.post(
        "http://localhost:8000/api/v1/chat",
        json={"message": "生成一个PPT", "stream": False}
    )
    print(response.json())
    ```
    """
    try:
        # stream 默认为 True
        use_stream = request.stream
        
        logger.info(f"📨 收到{'流式' if use_stream else '同步'}聊天请求: session_id={request.session_id}, message={request.message[:50]}...")
        
        # 从 main.py 获取或创建 Agent
        from main import get_or_create_agent_for_conversation, agent_pool
        
        # 使用 conversation_id 获取 Agent（自动管理 session_id 映射）
        conversation_id, session_id, agent = get_or_create_agent_for_conversation(
            conversation_id=request.conversation_id,
            verbose=False
        )
        
        # 🆕 将 user_id 和 conversation_id 存入 Agent 的 WorkingMemory
        if request.user_id:
            agent.memory.working.user_id = request.user_id
            logger.info(f"👤 设置 user_id: {request.user_id}")
        
        if request.conversation_id:
            agent.memory.working.conversation_id = request.conversation_id
            logger.info(f"💬 设置 conversation_id: {request.conversation_id}")
        
        # 🔍 输出会话状态信息
        session_info = agent.get_session_info()
        conversation_history = agent.get_conversation_history()
        logger.info(f"📊 会话状态: session_id={session_id}, conversation_id={request.conversation_id}, "
                   f"活跃={session_info['active']}, 轮次={session_info['turns']}, 历史消息数={len(conversation_history)}")
        
        # 🔍 如果有历史消息，输出最近的对话摘要
        if len(conversation_history) > 0:
            logger.info(f"💬 最近的对话历史:")
            # 显示最近3条消息
            for msg in conversation_history[-3:]:
                role = msg.get('role', 'unknown')
                content_preview = str(msg.get('content', ''))[:80] + '...' if len(str(msg.get('content', ''))) > 80 else str(msg.get('content', ''))
                logger.info(f"   - {role}: {content_preview}")
        else:
            logger.info(f"💬 这是本会话的第一条消息")
        
        logger.info(f"🤖 开始执行对话: session_id={session_id}, mode={'stream' if use_stream else 'sync'}")
        
        # ===== 流式模式 =====
        if use_stream:
            async def event_generator():
                """生成 SSE 事件流"""
                try:
                    async for event in agent.stream(request.message):
                        # 清理事件数据以确保可以JSON序列化
                        sanitized_event = {
                            "type": event["type"],
                            "data": sanitize_for_json(event["data"]),
                            "timestamp": event["timestamp"]
                        }
                        
                        # 转换为 SSE 格式
                        event_data = StreamEvent(**sanitized_event)
                        
                        # SSE 格式：data: {json}\n\n
                        yield f"data: {event_data.model_dump_json()}\n\n"
                    
                    # 🔍 输出执行完成后的状态
                    final_session_info = agent.get_session_info()
                    final_history_count = len(agent.get_conversation_history())
                    logger.info(f"✅ 流式对话完成: session_id={agent._session_id}, "
                               f"总轮次={final_session_info['turns']}, "
                               f"历史消息数={final_history_count}")
                    
                    # 发送完成事件
                    yield "data: {\"type\": \"done\", \"data\": {}, \"timestamp\": \"" + datetime.now().isoformat() + "\"}\n\n"
                
                except Exception as e:
                    logger.error(f"❌ 流式对话错误: {str(e)}", exc_info=True)
                    error_event = StreamEvent(
                        type="error",
                        data={"message": str(e)},
                        timestamp=datetime.now().isoformat()
                    )
                    yield f"data: {error_event.model_dump_json()}\n\n"
            
            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
                }
            )
        
        # ===== 同步模式 =====
        else:
            # 执行对话
            result = await agent.chat(request.message)
            
            # 🔍 输出执行结果统计
            final_history_count = len(agent.get_conversation_history())
            logger.info(f"✅ 对话执行完成: status={result.get('status')}, turns={result.get('turns')}, "
                       f"历史消息数={final_history_count}")
            
            # 🆕 验证最终结果中提到的文件是否真实存在
            final_result_content = result.get("final_result", "")
            if "/tmp/" in final_result_content or "outputs/" in final_result_content:
                import re
                # 提取可能的文件路径
                file_paths = re.findall(r'[`"]?(/tmp/[^`"\s]+\.pptx|outputs/[^`"\s]+\.pptx)[`"]?', final_result_content)
                if file_paths:
                    from pathlib import Path
                    for file_path in file_paths:
                        if not Path(file_path).exists():
                            logger.warning(f"⚠️ AI 声称生成了文件，但文件不存在: {file_path}")
                            # 在响应中添加警告
                            final_result_content += f"\n\n⚠️ **警告**: 文件 {file_path} 未找到。PPT 可能未成功生成，请检查日志。"
                            result["final_result"] = final_result_content
            
            # 清理数据以确保可以JSON序列化
            plan = sanitize_for_json(agent.get_plan())
            progress = sanitize_for_json(agent.get_progress())
            invocation_stats = sanitize_for_json(result.get("invocation_stats"))
            
            # 🆕 获取详细的执行信息
            routing_decisions = sanitize_for_json(result.get("routing_decisions", []))
            session_log = result.get("session_log", {})
            
            # 🆕 提取工具调用详情
            tool_calls_detail = []
            for interaction in session_log.get("interactions", []):
                if interaction.get("event_type") == "llm_response":
                    tool_count = interaction.get("data", {}).get("tool_calls_count", 0)
                    if tool_count > 0:
                        tool_calls_detail.append({
                            "turn": interaction.get("turn"),
                            "tool_calls_count": tool_count
                        })
            
            # 🆕 提取意图分析结果
            intent_analysis = sanitize_for_json(session_log.get("intent_recognition"))
            
            logger.debug(f"📊 统计信息: {invocation_stats}")
            logger.debug(f"🎯 路由决策: {routing_decisions}")
            
            # 构建响应
            response = ChatResponse(
                session_id=session_id,
                conversation_id=request.conversation_id,
                content=result.get("final_result", ""),
                status=result.get("status", "unknown"),
                turns=result.get("turns", 0),
                plan=plan,
                progress=progress,
                invocation_stats=invocation_stats,
                # 🆕 新增详细信息
                routing_decisions=routing_decisions,
                tool_calls=tool_calls_detail if tool_calls_detail else None,
                intent_analysis=intent_analysis
            )
            
            # 后台清理任务
            background_tasks.add_task(cleanup_inactive_sessions)
            
        logger.info(f"✅ 响应已构建: session_id={session_id}")
        
        # 🔍 简化日志：只打印关键信息
        if logger.level <= logging.DEBUG:
            print(f"\n📤 响应: session={response.session_id}, conversation={response.conversation_id}, status={response.status}, turns={response.turns}")
        
        return APIResponse(
                code=200,
                message="success",
                data=response
            )
    
    except Exception as e:
        logger.error(f"❌ 聊天接口错误: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{session_id}", response_model=APIResponse[SessionInfo])
async def get_session(session_id: str):
    """
    获取会话信息
    
    返回指定会话的详细信息，包括活跃状态、消息数量、执行计划等
    
    ## 参数
    - **session_id**: 会话ID
    
    ## 返回
    会话详细信息
    """
    try:
        logger.info(f"📨 获取会话信息: session_id={session_id}")
        
        from main import agent_pool
        
        if session_id not in agent_pool:
            logger.warning(f"⚠️ 会话不存在: session_id={session_id}")
            raise HTTPException(status_code=404, detail="会话不存在")
        
        agent = agent_pool[session_id]
        session_info = agent.get_session_info()
        
        # 添加开始时间
        start_time = agent.memory.working.metadata.get("start_time")
        
        response = SessionInfo(
            session_id=session_info["session_id"],
            active=session_info["active"],
            turns=session_info["turns"],
            message_count=session_info["message_count"],
            has_plan=session_info["has_plan"],
            start_time=start_time
        )
        
        logger.info(f"✅ 会话信息已返回: session_id={session_id}")
        
        return APIResponse(
            code=200,
            message="success",
            data=response
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 获取会话信息错误: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/session/{session_id}", response_model=APIResponse[Dict])
async def end_session(session_id: str):
    """
    结束会话
    
    结束指定会话并返回会话摘要
    
    ## 参数
    - **session_id**: 会话ID
    
    ## 返回
    会话摘要（包含轮次、消息数量、工具调用次数等）
    """
    try:
        logger.info(f"📨 结束会话请求: session_id={session_id}")
        
        from main import agent_pool
        
        if session_id not in agent_pool:
            logger.warning(f"⚠️ 会话不存在: session_id={session_id}")
            raise HTTPException(status_code=404, detail="会话不存在")
        
        agent = agent_pool[session_id]
        summary = agent.end_session()
        
        # 清理摘要数据
        summary = sanitize_for_json(summary)
        
        # 从池中移除
        del agent_pool[session_id]
        
        logger.info(f"✅ 会话已结束: session_id={session_id}")
        
        return APIResponse(
            code=200,
            message="会话已结束",
            data=summary
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 结束会话错误: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refine", response_model=APIResponse[ChatResponse])
async def refine(request: RefineRequest):
    """
    改进结果接口
    
    基于用户反馈改进之前的输出（HITL - Human-in-the-Loop）
    
    ## 参数
    - **session_id**: 会话ID
    - **original_query**: 原始查询
    - **previous_result**: 之前的结果
    - **user_feedback**: 用户反馈
    
    ## 返回
    改进后的结果
    
    ## 使用场景
    用户对 Agent 的输出不满意时，可以提供反馈让 Agent 改进
    
    ## 示例
    ```python
    response = requests.post(
        "http://localhost:8000/api/v1/refine",
        json={
            "session_id": "20231224_120000",
            "original_query": "生成一个PPT",
            "previous_result": "已生成PPT...",
            "user_feedback": "标题字体太小了"
        }
    )
    ```
    """
    try:
        logger.info(f"📨 收到改进请求: session_id={request.session_id}")
        
        from main import agent_pool
        
        if request.session_id not in agent_pool:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        agent = agent_pool[request.session_id]
        
        logger.info(f"🔧 开始改进结果: session_id={request.session_id}")
        
        # 执行改进
        result = await agent.refine(
            original_query=request.original_query,
            previous_result=request.previous_result,
            user_feedback=request.user_feedback
        )
        
        logger.info(f"✅ 改进完成: status={result.get('status')}")
        
        # 清理数据以确保可以JSON序列化
        plan = sanitize_for_json(agent.get_plan())
        progress = sanitize_for_json(agent.get_progress())
        invocation_stats = sanitize_for_json(result.get("invocation_stats"))
        
        # 🆕 获取详细的执行信息
        routing_decisions = sanitize_for_json(result.get("routing_decisions", []))
        session_log = result.get("session_log", {})
        tool_calls_detail = []
        for interaction in session_log.get("interactions", []):
            if interaction.get("event_type") == "llm_response":
                tool_count = interaction.get("data", {}).get("tool_calls_count", 0)
                if tool_count > 0:
                    tool_calls_detail.append({
                        "turn": interaction.get("turn"),
                        "tool_calls_count": tool_count
                    })
        intent_analysis = sanitize_for_json(session_log.get("intent_recognition"))
        
        # 构建响应
        response = ChatResponse(
            session_id=agent._session_id,
            content=result.get("final_result", ""),
            status=result.get("status", "unknown"),
            turns=result.get("turns", 0),
            plan=plan,
            progress=progress,
            invocation_stats=invocation_stats,
            routing_decisions=routing_decisions,
            tool_calls=tool_calls_detail if tool_calls_detail else None,
            intent_analysis=intent_analysis
        )
        
        return APIResponse(
            code=200,
            message="success",
            data=response
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 改进接口错误: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions", response_model=APIResponse[Dict])
async def list_sessions():
    """
    列出所有活跃会话
    
    返回当前所有活跃会话的列表和统计信息
    
    ## 返回
    包含会话总数和会话列表
    """
    try:
        logger.info("📨 列出所有会话")
        
        from main import agent_pool
        
        sessions = []
        for session_id, agent in agent_pool.items():
            try:
                info = agent.get_session_info()
                sessions.append({
                    "session_id": session_id,
                    "active": info["active"],
                    "turns": info["turns"],
                    "message_count": info["message_count"],
                    "has_plan": info.get("has_plan", False)
                })
            except Exception as e:
                logger.warning(f"⚠️ 获取会话信息失败: session_id={session_id}, error={str(e)}")
        
        logger.info(f"✅ 返回 {len(sessions)} 个会话")
        
        return APIResponse(
            code=200,
            message="success",
            data={
                "total": len(sessions),
                "sessions": sessions
            }
        )
    
    except Exception as e:
        logger.error(f"❌ 列出会话错误: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

