from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class ChatRequest(BaseModel):
    """聊天请求"""
    message: str = Field(..., description="用户消息", min_length=1)
    session_id: Optional[str] = Field(None, description="会话ID（可选）")
    stream: bool = Field(True, description="是否使用流式输出（默认为True）")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "message": "帮我生成一个关于AI的PPT",
                    "session_id": "20231224_120000",
                    "stream": True
                }
            ]
        }
    }


class ChatResponse(BaseModel):
    """聊天响应"""
    session_id: str = Field(..., description="会话ID")
    content: str = Field(..., description="回复内容")
    status: str = Field(..., description="任务状态：success/failed/incomplete")
    turns: int = Field(..., description="执行轮次")
    plan: Optional[Dict[str, Any]] = Field(None, description="执行计划（如果有）")
    progress: Optional[Dict[str, Any]] = Field(None, description="进度信息")
    invocation_stats: Optional[Dict[str, int]] = Field(None, description="工具调用统计")
    # 🆕 新增字段：详细的执行信息
    routing_decisions: Optional[List[Dict[str, Any]]] = Field(None, description="能力路由决策记录")
    tool_calls: Optional[List[Dict[str, Any]]] = Field(None, description="工具调用详情")
    intent_analysis: Optional[Dict[str, Any]] = Field(None, description="意图识别结果")
    selected_tools: Optional[List[str]] = Field(None, description="本次选择的工具列表")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "session_id": "20231224_120000",
                    "content": "已经为您生成了PPT...",
                    "status": "success",
                    "turns": 5,
                    "progress": {
                        "total": 4,
                        "completed": 4,
                        "progress": 1.0
                    },
                    "routing_decisions": [
                        {
                            "keywords": ["ppt", "专业"],
                            "selected": "slidespeak-generator",
                            "score": 276,
                            "reason": "专业PPT需求"
                        }
                    ],
                    "tool_calls": [
                        {
                            "tool_name": "slidespeak-generator",
                            "status": "success",
                            "duration": 2.5
                        }
                    ]
                }
            ]
        }
    }


class StreamEvent(BaseModel):
    """流式输出事件"""
    type: str = Field(..., description="事件类型")
    data: Dict[str, Any] = Field(..., description="事件数据")
    timestamp: str = Field(..., description="时间戳")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "type": "thinking",
                    "data": {"text": "让我思考一下..."},
                    "timestamp": "2023-12-24T12:00:00"
                }
            ]
        }
    }


class SessionInfo(BaseModel):
    """会话信息"""
    session_id: str = Field(..., description="会话ID")
    active: bool = Field(..., description="是否活跃")
    turns: int = Field(..., description="对话轮次")
    message_count: int = Field(..., description="消息数量")
    has_plan: bool = Field(..., description="是否有执行计划")
    start_time: Optional[str] = Field(None, description="会话开始时间")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "session_id": "20231224_120000",
                    "active": True,
                    "turns": 3,
                    "message_count": 6,
                    "has_plan": True,
                    "start_time": "2023-12-24T12:00:00"
                }
            ]
        }
    }


class RefineRequest(BaseModel):
    """改进请求（简化版）"""
    session_id: str = Field(..., description="会话ID")
    message: str = Field(..., description="用户反馈/修改要求", min_length=1)
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "session_id": "20231224_120000",
                    "message": "标题字体太小了，需要调整为48号并加粗"
                }
            ]
        }
    }

