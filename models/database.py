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
    """消息模型"""
    
    id: Optional[int] = None
    conversation_id: str = Field(..., description="所属对话ID（UUID）")
    role: str = Field(..., description="角色: user/assistant/system")
    content: str = Field(..., description="消息内容")
    created_at: Optional[datetime] = None
    metadata: Optional[dict] = Field(default_factory=dict, description="消息元数据")
    
    class Config:
        from_attributes = True

