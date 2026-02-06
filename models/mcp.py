"""
MCP 工具配置模型

用于 MCP 服务器和工具配置
"""

from typing import Optional
from pydantic import BaseModel, Field


class MCPToolConfig(BaseModel):
    """MCP 工具配置（用于创建/更新请求）"""
    name: str = Field(..., description="工具名称")
    server_url: str = Field(..., description="MCP 服务器 URL")
    server_name: str = Field("", description="服务器名称（用作工具前缀）")
    auth_type: str = Field("none", description="认证类型: none / bearer / api_key")
    auth_env: Optional[str] = Field(None, description="认证密钥的环境变量名")
    capability: Optional[str] = Field(None, description="工具能力分类")
    description: str = Field("", description="工具描述")


class MCPToolDetail(BaseModel):
    """MCP 工具详情（用于响应）"""
    name: str = Field(..., description="工具名称")
    server_url: str = Field("", description="MCP 服务器 URL")
    server_name: str = Field("", description="服务器名称")
    auth_type: str = Field("none", description="认证类型")
    auth_env: Optional[str] = Field(None, description="认证密钥的环境变量名")
    capability: Optional[str] = Field(None, description="工具能力分类")
    description: str = Field("", description="工具描述")
