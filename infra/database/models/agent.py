"""
Agent、Skill 和 MCP 数据库模型

存储 Agent 元数据、Skill 注册状态和 MCP 服务器配置
主配置存储在文件系统（instances/），数据库仅记录元数据和统计信息
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Text, Integer, Boolean, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infra.database.base import Base


class AgentInstance(Base):
    """
    Agent 实例元数据表
    
    主配置存储在 instances/{agent_id}/ 目录
    此表记录：创建时间、调用统计、状态等元数据
    """
    __tablename__ = "agent_instances"
    
    # 主键（与 instances/ 目录名一致）
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    
    # 基本信息（从 config.yaml 同步，name 添加索引）
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    version: Mapped[str] = mapped_column(String(32), default="1.0.0", nullable=False)
    
    # 状态（添加索引，支持查询活跃 Agent）
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    
    # 统计信息
    total_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
        nullable=False
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True
    )
    
    # 元数据（JSONB 类型，PostgreSQL 原生支持）
    extra_data: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        default={},
        nullable=False
    )
    
    # 关系
    skills: Mapped[list["SkillInstance"]] = relationship(
        back_populates="agent",
        cascade="all, delete-orphan"
    )
    
    # 复合索引：活跃 Agent 排序
    __table_args__ = (
        Index('idx_agent_instances_active_used', 'is_active', 'last_used_at'),
    )
    
    def increment_calls(self, success: bool = True):
        """增加调用计数"""
        self.total_calls += 1
        if success:
            self.success_calls += 1
        else:
            self.failed_calls += 1
        self.last_used_at = datetime.now()
    
    def __repr__(self) -> str:
        return f"<AgentInstance(id={self.id}, name={self.name})>"


class SkillInstance(Base):
    """
    Skill 实例表
    
    记录 Skill 的注册状态和 Claude API 的 skill_id
    Skill 内容存储在 instances/{agent_id}/skills/{skill_name}/
    """
    __tablename__ = "skill_instances"
    
    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # 外键（关联 Agent）
    agent_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("agent_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Skill 信息
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    
    # Claude API 注册信息（添加索引，支持按 skill_id 和启用状态查询）
    skill_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    is_registered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False
    )
    registered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
        nullable=False
    )
    
    # 元数据（JSONB 类型，PostgreSQL 原生支持）
    extra_data: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        default={},
        nullable=False
    )
    
    # 关系
    agent: Mapped["AgentInstance"] = relationship(back_populates="skills")
    
    # 复合索引：Agent 启用的 Skill
    __table_args__ = (
        Index('idx_skill_instances_agent_enabled', 'agent_id', 'is_enabled'),
    )
    
    def __repr__(self) -> str:
        return f"<SkillInstance(id={self.id}, name={self.name}, agent_id={self.agent_id})>"


class MCPServerInstance(Base):
    """
    MCP 服务器注册表
    
    存储已注册的 MCP 服务器配置，避免重复注册
    支持全局 MCP 服务器（agent_id 为 null）和 Agent 特定的 MCP 服务器
    """
    __tablename__ = "mcp_servers"
    
    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # 服务器标识（唯一）
    server_name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    server_url: Mapped[str] = mapped_column(String(512), nullable=False)
    
    # 认证配置
    auth_type: Mapped[str] = mapped_column(String(32), default="none", nullable=False)
    auth_env: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    
    # 关联 Agent（可选，null 表示全局 MCP 服务器）
    agent_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("agent_instances.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    
    # 状态（添加索引，支持查询活跃服务器）
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    
    # 能力分类
    capability: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    
    # 已发现的工具列表（JSONB 类型）
    registered_tools: Mapped[list] = mapped_column(
        JSONB,
        default=[],
        nullable=False
    )
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
        nullable=False
    )
    last_connected_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True
    )
    
    # 元数据（JSONB 类型，PostgreSQL 原生支持）
    extra_data: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        default={},
        nullable=False
    )
    
    def update_connection_time(self):
        """更新最后连接时间"""
        self.last_connected_at = datetime.now()
    
    def __repr__(self) -> str:
        return f"<MCPServerInstance(id={self.id}, name={self.server_name}, url={self.server_url})>"

