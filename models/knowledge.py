"""
知识库系统模型 - Knowledge Base System Models

🎯 用途：本地知识库管理（文件夹组织、权限控制、分享协作）
📊 包含：
- KnowledgeBase：知识库
- KnowledgeFolder：文件夹（多级嵌套）
- KnowledgeDocument：文档（关联 files 表 + Ragie）
- KnowledgeShare：分享
- KnowledgeMember：协作成员

⚠️ 注意：
- 这个文件是本地知识库管理模型
- Ragie API 对接模型在 ragie.py（DocumentUploadRequest 等）
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ==================== 枚举类型 ====================

class KBVisibility(str, Enum):
    """知识库可见性"""
    PRIVATE = "private"      # 私有（仅所有者可见）
    PUBLIC = "public"        # 公开（所有人可见）
    UNLISTED = "unlisted"    # 不公开但可通过链接访问


class KBPermission(str, Enum):
    """知识库权限"""
    READ = "read"            # 只读
    WRITE = "write"          # 可写（上传、编辑）
    ADMIN = "admin"          # 管理员（所有权限）


class MemberRole(str, Enum):
    """成员角色"""
    OWNER = "owner"          # 所有者
    EDITOR = "editor"        # 编辑者
    VIEWER = "viewer"        # 查看者


class ShareType(str, Enum):
    """分享类型"""
    LINK = "link"            # 链接分享
    USER = "user"            # 指定用户分享
    PUBLIC = "public"        # 公开分享


class DocumentStatus(str, Enum):
    """文档状态"""
    PENDING = "pending"      # 等待处理
    PROCESSING = "processing" # 处理中
    INDEXED = "indexed"      # 已索引
    FAILED = "failed"        # 失败


# ==================== 知识库模型 ====================

class KnowledgeBase(BaseModel):
    """知识库信息"""
    id: str
    name: str
    description: Optional[str] = None
    icon: str = "📚"
    color: str = "#667eea"
    
    owner_id: str
    visibility: KBVisibility
    is_shared: bool = False
    
    document_count: int = 0
    folder_count: int = 0
    total_size: int = 0
    
    settings: Optional[Dict[str, Any]] = None
    
    created_at: datetime
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "kb_abc123",
                "name": "产品文档库",
                "description": "存放所有产品相关文档",
                "icon": "📚",
                "color": "#667eea",
                "owner_id": "user_001",
                "visibility": "private",
                "document_count": 15,
                "folder_count": 3,
                "total_size": 10485760
            }
        }


class KnowledgeBaseCreate(BaseModel):
    """创建知识库请求"""
    name: str = Field(..., min_length=1, max_length=100, description="知识库名称")
    description: Optional[str] = Field(None, max_length=500, description="描述")
    icon: str = Field("📚", description="图标")
    color: str = Field("#667eea", description="颜色")
    visibility: KBVisibility = Field(KBVisibility.PRIVATE, description="可见性")
    settings: Optional[Dict[str, Any]] = Field(None, description="配置")


class KnowledgeBaseUpdate(BaseModel):
    """更新知识库请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    icon: Optional[str] = None
    color: Optional[str] = None
    visibility: Optional[KBVisibility] = None
    settings: Optional[Dict[str, Any]] = None


# ==================== 文件夹模型 ====================

class KnowledgeFolder(BaseModel):
    """知识库文件夹"""
    id: str
    name: str
    description: Optional[str] = None
    icon: str = "📁"
    
    kb_id: str
    parent_id: Optional[str] = None
    path: str
    level: int = 0
    
    document_count: int = 0
    subfolder_count: int = 0
    sort_order: int = 0
    
    created_at: datetime
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None


class KnowledgeFolderCreate(BaseModel):
    """创建文件夹请求"""
    kb_id: str = Field(..., description="知识库 ID")
    parent_id: Optional[str] = Field(None, description="父文件夹 ID")
    name: str = Field(..., min_length=1, max_length=100, description="文件夹名称")
    description: Optional[str] = Field(None, max_length=500)
    icon: str = Field("📁", description="图标")


class KnowledgeFolderUpdate(BaseModel):
    """更新文件夹请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    icon: Optional[str] = None
    parent_id: Optional[str] = None  # 移动文件夹


# ==================== 文档模型 ====================

class KnowledgeDocument(BaseModel):
    """知识库文档"""
    id: str
    kb_id: str
    folder_id: Optional[str] = None
    file_id: str
    
    name: str
    original_filename: str
    file_size: int
    content_type: Optional[str] = None
    
    status: DocumentStatus
    ragie_document_id: Optional[str] = None
    
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    summary: Optional[str] = None
    
    view_count: int = 0
    reference_count: int = 0
    sort_order: int = 0
    is_pinned: bool = False
    
    created_at: datetime
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None


class KnowledgeDocumentCreate(BaseModel):
    """添加文档到知识库请求"""
    kb_id: str = Field(..., description="知识库 ID")
    folder_id: Optional[str] = Field(None, description="文件夹 ID")
    file_id: str = Field(..., description="文件 ID")
    name: Optional[str] = Field(None, description="自定义名称")
    tags: Optional[List[str]] = Field(None, description="标签")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")


class KnowledgeDocumentUpdate(BaseModel):
    """更新文档请求"""
    name: Optional[str] = None
    folder_id: Optional[str] = None  # 移动文档
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    is_pinned: Optional[bool] = None


# ==================== 分享模型 ====================

class KnowledgeShare(BaseModel):
    """知识库分享"""
    id: str
    kb_id: str
    share_type: ShareType
    
    shared_by: str
    shared_to: Optional[str] = None
    
    share_link: Optional[str] = None
    link_password: Optional[str] = None
    
    permission: KBPermission
    expires_at: Optional[datetime] = None
    
    access_count: int = 0
    last_accessed_at: Optional[datetime] = None
    
    created_at: datetime
    revoked_at: Optional[datetime] = None


class KnowledgeShareCreate(BaseModel):
    """创建分享请求"""
    kb_id: str = Field(..., description="知识库 ID")
    share_type: ShareType = Field(..., description="分享类型")
    shared_to: Optional[str] = Field(None, description="接收者用户 ID")
    permission: KBPermission = Field(KBPermission.READ, description="权限")
    link_password: Optional[str] = Field(None, description="链接密码")
    expires_at: Optional[datetime] = Field(None, description="过期时间")


# ==================== 成员模型 ====================

class KnowledgeMember(BaseModel):
    """知识库成员"""
    id: str
    kb_id: str
    user_id: str
    
    role: MemberRole
    permissions: Optional[Dict[str, Any]] = None
    
    invited_by: str
    invitation_status: str = "accepted"
    
    contribution_count: int = 0
    last_active_at: Optional[datetime] = None
    
    created_at: datetime
    updated_at: Optional[datetime] = None
    removed_at: Optional[datetime] = None


class KnowledgeMemberInvite(BaseModel):
    """邀请成员请求"""
    kb_id: str = Field(..., description="知识库 ID")
    user_id: str = Field(..., description="被邀请用户 ID")
    role: MemberRole = Field(MemberRole.VIEWER, description="角色")
    permissions: Optional[Dict[str, Any]] = Field(None, description="详细权限")


# ==================== 响应模型 ====================

class KnowledgeBaseListResponse(BaseModel):
    """知识库列表响应"""
    user_id: str
    total: int
    knowledge_bases: List[KnowledgeBase]
    has_more: bool


class KnowledgeFolderTreeNode(BaseModel):
    """文件夹树节点"""
    folder: KnowledgeFolder
    children: List['KnowledgeFolderTreeNode'] = []
    documents: List[KnowledgeDocument] = []


class KnowledgeBaseDetailResponse(BaseModel):
    """知识库详情响应"""
    knowledge_base: KnowledgeBase
    folders: List[KnowledgeFolder]
    documents: List[KnowledgeDocument]
    members: List[KnowledgeMember]
    shares: List[KnowledgeShare]


# 允许 KnowledgeFolderTreeNode 的递归引用
KnowledgeFolderTreeNode.model_rebuild()
