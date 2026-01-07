"""
工具仓库 - Tool Repository

职责：
1. 工具元数据持久化
2. 工具代码存储管理
3. 版本控制

设计原则：
- 只存储元数据到数据库
- 代码存储到对象存储（S3）或文件系统
- 不在数据库中存储可执行代码
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy import Column, String, Text, Integer, Boolean, DateTime, JSON, Enum as SQLEnum
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
import enum
import hashlib

from infra.database.base import Base
from logger import get_logger

logger = get_logger("tool_repository")


# ============================================================
# 数据库模型
# ============================================================

class ToolTrustLevel(str, enum.Enum):
    """工具信任等级"""
    L1_BUILTIN = "L1"
    L2_REVIEWED = "L2"
    L3_SANDBOX = "L3"
    L4_MCP = "L4"


class ToolStatus(str, enum.Enum):
    """工具状态"""
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DEPRECATED = "deprecated"


class ToolExecutionMode(str, enum.Enum):
    """执行模式"""
    DIRECT = "direct"
    SANDBOX = "sandbox"
    THREAD_POOL = "thread_pool"
    MCP = "mcp"


class RegisteredTool(Base):
    """
    已注册的工具（数据库模型）
    
    注意：不存储可执行代码，只存储元数据和代码引用
    """
    __tablename__ = "registered_tools"
    
    # 基本信息
    id = Column(String(64), primary_key=True)
    name = Column(String(128), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=False)
    version = Column(String(32), default="1.0.0")
    
    # 所有者
    author_id = Column(String(64), nullable=True, index=True)
    author_name = Column(String(128), nullable=True)
    
    # 类型和信任
    tool_type = Column(String(32), default="user_defined")  # user_defined / mcp
    trust_level = Column(SQLEnum(ToolTrustLevel), default=ToolTrustLevel.L3_SANDBOX)
    execution_mode = Column(SQLEnum(ToolExecutionMode), default=ToolExecutionMode.SANDBOX)
    
    # Schema（JSON 格式）
    input_schema = Column(JSON, nullable=False)
    output_schema = Column(JSON, nullable=True)
    
    # 约束配置
    constraints = Column(JSON, default=dict)
    # constraints 结构:
    # {
    #   "timeout": 30,
    #   "max_memory_mb": 256,
    #   "network_access": false,
    #   "file_access": false
    # }
    
    # 代码引用（不存储代码本身）
    code_reference = Column(JSON, nullable=True)
    # code_reference 结构:
    # {
    #   "type": "sandbox",  # builtin / sandbox / mcp
    #   "code_hash": "sha256:xxxxx",
    #   "storage_key": "tools/user_123/my_tool/v1.0.0.py",  # S3 key
    #   "module_path": "tools.xxx",  # 内置工具的模块路径
    #   "class_name": "XxxTool"      # 内置工具的类名
    # }
    
    # MCP 配置（MCP 工具专用）
    mcp_config = Column(JSON, nullable=True)
    # mcp_config 结构:
    # {
    #   "server_url": "http://xxx",
    #   "server_name": "office365",
    #   "auth_type": "bearer",
    #   "interaction_mode": "sync"
    # }
    
    # 元数据
    keywords = Column(JSON, default=list)
    category = Column(String(64), nullable=True, index=True)
    examples = Column(JSON, default=list)
    
    # 状态
    status = Column(SQLEnum(ToolStatus), default=ToolStatus.ACTIVE)
    is_public = Column(Boolean, default=False)
    
    # 审核信息
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by = Column(String(64), nullable=True)
    review_notes = Column(Text, nullable=True)
    
    # 统计
    invocation_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author_id": self.author_id,
            "author_name": self.author_name,
            "tool_type": self.tool_type,
            "trust_level": self.trust_level.value if self.trust_level else None,
            "execution_mode": self.execution_mode.value if self.execution_mode else None,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "constraints": self.constraints,
            "code_reference": self.code_reference,
            "mcp_config": self.mcp_config,
            "keywords": self.keywords,
            "category": self.category,
            "examples": self.examples,
            "status": self.status.value if self.status else None,
            "is_public": self.is_public,
            "invocation_count": self.invocation_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ============================================================
# 仓库类
# ============================================================

class ToolRepository:
    """
    工具仓库
    
    提供工具的 CRUD 操作
    """
    
    def __init__(self, session: AsyncSession):
        """
        初始化仓库
        
        Args:
            session: 数据库会话
        """
        self.session = session
    
    @staticmethod
    def generate_tool_id(name: str, author_id: Optional[str] = None) -> str:
        """
        生成工具 ID
        
        Args:
            name: 工具名称
            author_id: 作者 ID
            
        Returns:
            唯一的工具 ID
        """
        source = f"{name}:{author_id or 'system'}:{datetime.utcnow().timestamp()}"
        return f"tool_{hashlib.md5(source.encode()).hexdigest()[:16]}"
    
    async def create(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        tool_type: str = "user_defined",
        trust_level: ToolTrustLevel = ToolTrustLevel.L3_SANDBOX,
        execution_mode: ToolExecutionMode = ToolExecutionMode.SANDBOX,
        author_id: Optional[str] = None,
        author_name: Optional[str] = None,
        code_reference: Optional[Dict] = None,
        mcp_config: Optional[Dict] = None,
        constraints: Optional[Dict] = None,
        keywords: Optional[List[str]] = None,
        category: Optional[str] = None,
        **kwargs
    ) -> RegisteredTool:
        """
        创建工具记录
        
        Args:
            name: 工具名称
            description: 工具描述
            input_schema: 输入 Schema
            tool_type: 工具类型
            trust_level: 信任等级
            execution_mode: 执行模式
            author_id: 作者 ID
            author_name: 作者名称
            code_reference: 代码引用
            mcp_config: MCP 配置
            constraints: 约束配置
            keywords: 关键词
            category: 分类
            **kwargs: 其他字段
            
        Returns:
            创建的工具记录
        """
        tool_id = self.generate_tool_id(name, author_id)
        
        tool = RegisteredTool(
            id=tool_id,
            name=name,
            description=description,
            input_schema=input_schema,
            tool_type=tool_type,
            trust_level=trust_level,
            execution_mode=execution_mode,
            author_id=author_id,
            author_name=author_name,
            code_reference=code_reference,
            mcp_config=mcp_config,
            constraints=constraints or {
                "timeout": 30,
                "max_memory_mb": 256,
                "network_access": False,
                "file_access": False
            },
            keywords=keywords or [],
            category=category,
            **kwargs
        )
        
        self.session.add(tool)
        await self.session.commit()
        await self.session.refresh(tool)
        
        logger.info(f"✅ 创建工具记录: id={tool_id}, name={name}")
        
        return tool
    
    async def get_by_id(self, tool_id: str) -> Optional[RegisteredTool]:
        """根据 ID 获取工具"""
        result = await self.session.execute(
            select(RegisteredTool).where(RegisteredTool.id == tool_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_name(self, name: str) -> Optional[RegisteredTool]:
        """根据名称获取工具"""
        result = await self.session.execute(
            select(RegisteredTool).where(RegisteredTool.name == name)
        )
        return result.scalar_one_or_none()
    
    async def list_tools(
        self,
        tool_type: Optional[str] = None,
        trust_level: Optional[ToolTrustLevel] = None,
        status: Optional[ToolStatus] = None,
        category: Optional[str] = None,
        author_id: Optional[str] = None,
        is_public: Optional[bool] = None,
        keyword: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[RegisteredTool]:
        """
        列出工具
        
        Args:
            tool_type: 工具类型过滤
            trust_level: 信任等级过滤
            status: 状态过滤
            category: 分类过滤
            author_id: 作者过滤
            is_public: 公开状态过滤
            keyword: 关键词搜索
            limit: 每页数量
            offset: 偏移量
            
        Returns:
            工具列表
        """
        query = select(RegisteredTool)
        
        if tool_type:
            query = query.where(RegisteredTool.tool_type == tool_type)
        if trust_level:
            query = query.where(RegisteredTool.trust_level == trust_level)
        if status:
            query = query.where(RegisteredTool.status == status)
        if category:
            query = query.where(RegisteredTool.category == category)
        if author_id:
            query = query.where(RegisteredTool.author_id == author_id)
        if is_public is not None:
            query = query.where(RegisteredTool.is_public == is_public)
        if keyword:
            # 简单的关键词搜索（名称和描述）
            pattern = f"%{keyword}%"
            query = query.where(
                RegisteredTool.name.ilike(pattern) | 
                RegisteredTool.description.ilike(pattern)
            )
        
        query = query.order_by(RegisteredTool.created_at.desc())
        query = query.limit(limit).offset(offset)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def count_tools(
        self,
        tool_type: Optional[str] = None,
        status: Optional[ToolStatus] = None,
        author_id: Optional[str] = None
    ) -> int:
        """统计工具数量"""
        from sqlalchemy import func
        
        query = select(func.count(RegisteredTool.id))
        
        if tool_type:
            query = query.where(RegisteredTool.tool_type == tool_type)
        if status:
            query = query.where(RegisteredTool.status == status)
        if author_id:
            query = query.where(RegisteredTool.author_id == author_id)
        
        result = await self.session.execute(query)
        return result.scalar() or 0
    
    async def update(
        self,
        tool_id: str,
        **updates
    ) -> Optional[RegisteredTool]:
        """
        更新工具
        
        Args:
            tool_id: 工具 ID
            **updates: 要更新的字段
            
        Returns:
            更新后的工具，不存在则返回 None
        """
        tool = await self.get_by_id(tool_id)
        if not tool:
            return None
        
        for key, value in updates.items():
            if hasattr(tool, key):
                setattr(tool, key, value)
        
        tool.updated_at = datetime.utcnow()
        
        await self.session.commit()
        await self.session.refresh(tool)
        
        logger.info(f"✅ 更新工具: id={tool_id}")
        
        return tool
    
    async def update_status(
        self,
        tool_id: str,
        status: ToolStatus,
        review_notes: Optional[str] = None,
        reviewed_by: Optional[str] = None
    ) -> Optional[RegisteredTool]:
        """
        更新工具状态
        
        Args:
            tool_id: 工具 ID
            status: 新状态
            review_notes: 审核备注
            reviewed_by: 审核人
            
        Returns:
            更新后的工具
        """
        updates = {"status": status}
        
        if review_notes:
            updates["review_notes"] = review_notes
        if reviewed_by:
            updates["reviewed_by"] = reviewed_by
            updates["reviewed_at"] = datetime.utcnow()
        
        return await self.update(tool_id, **updates)
    
    async def increment_stats(
        self,
        tool_id: str,
        success: bool = True
    ):
        """
        增加调用统计
        
        Args:
            tool_id: 工具 ID
            success: 是否成功
        """
        tool = await self.get_by_id(tool_id)
        if not tool:
            return
        
        tool.invocation_count += 1
        if success:
            tool.success_count += 1
        else:
            tool.failure_count += 1
        
        await self.session.commit()
    
    async def delete(self, tool_id: str) -> bool:
        """
        删除工具
        
        Args:
            tool_id: 工具 ID
            
        Returns:
            是否删除成功
        """
        tool = await self.get_by_id(tool_id)
        if not tool:
            return False
        
        await self.session.delete(tool)
        await self.session.commit()
        
        logger.info(f"🗑️ 删除工具: id={tool_id}")
        
        return True
    
    async def soft_delete(self, tool_id: str) -> bool:
        """
        软删除工具（标记为废弃）
        
        Args:
            tool_id: 工具 ID
            
        Returns:
            是否成功
        """
        result = await self.update_status(tool_id, ToolStatus.DEPRECATED)
        return result is not None


# ============================================================
# 便捷函数
# ============================================================

async def get_tool_repository(session: AsyncSession) -> ToolRepository:
    """获取工具仓库实例"""
    return ToolRepository(session)

