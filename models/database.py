"""
数据库模型定义

使用 SQLite 存储用户、对话和消息数据
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class User(BaseModel):
    """用户模型"""
    
    id: Optional[int] = None
    username: str = Field(..., description="用户名")
    email: Optional[str] = Field(None, description="邮箱")
    created_at: Optional[datetime] = None
    metadata: Optional[dict] = Field(default_factory=dict, description="用户元数据")
    
    class Config:
        from_attributes = True


class Conversation(BaseModel):
    """会话模型"""
    
    id: str = Field(..., description="对话唯一标识（UUID）")
    user_id: str = Field(..., description="用户ID")
    title: str = Field(default="新对话", description="对话标题")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    metadata: Optional[dict] = Field(default_factory=dict, description="对话元数据")
    
    class Config:
        from_attributes = True


class Message(BaseModel):
    """
    消息模型
    
    字段说明：
    - id: 消息唯一标识（UUID）
    - conversation_id: 所属对话ID
    - role: 角色 (user/assistant/system)
    - content: 消息内容（JSON 数组格式，兼容 Claude API）
        格式: [
            {"type": "thinking", "thinking": "...", "signature": "..."},  # thinking 完整保存
            {"type": "text", "text": "..."},
            {"type": "tool_use", "id": "...", "name": "...", "input": {...}},
            {"type": "tool_result", "tool_use_id": "...", "content": "..."}
        ]
        说明：thinking block 完整保存在 content 数组最前面（含 signature），确保 RVR 循环正常工作
    - status: 消息状态（JSON 对象，纯状态信息，不含内容）
        格式: {
            "action": "completed",     # 动作状态: completed/stopped/failed
            "has_thinking": true,      # 是否包含 thinking
            "blocks_count": 5          # 内容块数量
        }
    - score: 评分/质量分数
    - metadata: 其他元数据（如 session_id, model, usage 等）
            
    存储策略说明：
    - content: 完整存储所有内容块（thinking + text + tool_use + tool_result）
    - status: 纯状态字段，不再混入 thinking 内容
    - 前端: 从 content 中提取 thinking block 来展示思考过程
    """
    
    id: str = Field(..., description="消息唯一标识（UUID）")
    conversation_id: str = Field(..., description="所属对话ID（UUID）")
    role: str = Field(..., description="角色: user/assistant/system")
    content: str = Field(..., description="消息内容（JSON 数组格式）")
    status: Optional[str] = Field(None, description="消息状态（JSON 对象）")
    score: Optional[float] = Field(None, description="评分/质量分数")
    created_at: Optional[datetime] = None
    metadata: Optional[dict] = Field(default_factory=dict, description="消息元数据")
    
    class Config:
        from_attributes = True

