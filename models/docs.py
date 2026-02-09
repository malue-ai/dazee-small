"""
文档浏览相关数据模型
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class DocFile(BaseModel):
    """文档文件"""
    name: str = Field(..., description="文件名")
    path: str = Field(..., description="相对路径")
    title: str = Field(..., description="文档标题")


class DocCategory(BaseModel):
    """文档分类"""
    id: str = Field(..., description="分类 ID")
    name: str = Field(..., description="分类名称")
    icon: str = Field(default="📄", description="图标")
    description: str = Field(default="", description="分类描述")
    files: List[DocFile] = Field(default_factory=list, description="文件列表")


class DocsStructure(BaseModel):
    """文档结构"""
    categories: List[DocCategory] = Field(..., description="分类列表")
    total_files: int = Field(..., description="总文件数")


class DocContent(BaseModel):
    """文档内容"""
    path: str = Field(..., description="文档路径")
    title: str = Field(..., description="文档标题")
    content: str = Field(..., description="Markdown 内容")
    category: str = Field(..., description="所属分类")


class DocsStructureResponse(BaseModel):
    """文档结构响应"""
    success: bool = True
    data: DocsStructure


class DocContentResponse(BaseModel):
    """文档内容响应"""
    success: bool = True
    data: DocContent
