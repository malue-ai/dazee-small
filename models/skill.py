"""
Skill 模型

用于 Skill 相关的请求/响应
"""

from typing import Dict, Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


# ============================================================
# Skill 请求模型
# ============================================================

class SkillCreateRequest(BaseModel):
    """创建 Skill 请求"""
    name: str = Field(..., description="Skill 名称", min_length=1, max_length=64)
    description: str = Field("", description="Skill 描述")
    agent_id: str = Field(..., description="所属 Agent ID")
    skill_content: str = Field(..., description="SKILL.md 内容")
    enabled: bool = Field(True, description="是否启用")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "data_analysis",
                    "description": "数据分析技能",
                    "agent_id": "test_agent",
                    "skill_content": "---\nname: data_analysis\ndescription: 数据分析\n---\n\n# Data Analysis Skill\n...",
                    "enabled": True,
                }
            ]
        }
    }


class SkillUpdateRequest(BaseModel):
    """更新 Skill 请求"""
    description: Optional[str] = Field(None, description="Skill 描述")
    skill_content: Optional[str] = Field(None, description="SKILL.md 内容")
    enabled: Optional[bool] = Field(None, description="是否启用")


# ============================================================
# Skill 响应模型
# ============================================================

class SkillSummary(BaseModel):
    """Skill 摘要（用于列表）"""
    name: str = Field(..., description="Skill 名称")
    description: str = Field("", description="描述")
    agent_id: str = Field(..., description="所属 Agent ID")
    status: str = Field("ready", description="运行时状态: ready/need_setup/need_auth/unavailable")
    status_message: str = Field("", description="状态说明")
    created_at: datetime = Field(..., description="创建时间")


class EnvRequirement(BaseModel):
    """Skill 所需的环境变量"""
    name: str = Field(..., description="环境变量名称，如 GEMINI_API_KEY")
    label: str = Field(..., description="显示标签，如 Gemini API Key")
    is_set: bool = Field(False, description="是否已配置")


class SkillDetail(BaseModel):
    """Skill 详情（完整信息）"""
    name: str = Field(..., description="Skill 名称")
    description: str = Field("", description="描述")
    priority: str = Field("medium", description="优先级: high/medium/low")
    preferred_for: List[str] = Field(default_factory=list, description="适用场景")
    scripts: List[str] = Field(default_factory=list, description="脚本文件列表")
    resources: List[str] = Field(default_factory=list, description="资源文件列表")
    content: str = Field("", description="SKILL.md 完整内容")
    agent_id: str = Field(..., description="所属 Agent ID（global 表示全局库）")
    status: str = Field("ready", description="运行时状态: ready/need_setup/need_auth/unavailable")
    status_message: str = Field("", description="状态说明")
    required_env: List[EnvRequirement] = Field(default_factory=list, description="所需环境变量列表")
    created_at: Optional[datetime] = Field(None, description="创建时间")


class SkillListResponse(BaseModel):
    """Skill 列表响应"""
    total: int = Field(..., description="总数")
    skills: List[SkillSummary] = Field(..., description="Skill 列表")


# ============================================================
# Skill 操作请求
# ============================================================

class SkillInstallRequest(BaseModel):
    """安装 Skill 到实例请求"""
    skill_name: str = Field(..., description="Skill 名称（全局库中的 Skill）")
    agent_id: str = Field(..., description="目标实例 ID")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "skill_name": "excel-analyzer",
                    "agent_id": "dazee_agent",
                }
            ]
        }
    }


class SkillUninstallRequest(BaseModel):
    """从实例卸载 Skill 请求"""
    skill_name: str = Field(..., description="Skill 名称")
    agent_id: str = Field(..., description="实例 ID")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "skill_name": "excel-analyzer",
                    "agent_id": "dazee_agent"
                }
            ]
        }
    }


class SkillUpdateContentRequest(BaseModel):
    """更新 Skill 内容请求"""
    skill_name: str = Field(..., description="Skill 名称")
    agent_id: str = Field(..., description="实例 ID")
    content: str = Field(..., description="新的 SKILL.md 内容")


class SkillConfigureRequest(BaseModel):
    """配置 Skill API Key 请求"""
    skill_name: str = Field(..., description="Skill 名称")
    agent_id: str = Field("global", description="实例 ID（global 表示全局库）")
    env_vars: Dict[str, str] = Field(..., description="环境变量键值对，如 {GEMINI_API_KEY: 'xxx'}")
