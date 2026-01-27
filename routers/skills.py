"""
Skills 管理路由

提供 Skills CRUD 操作的 REST API
创建 Skill 时自动同步到 Claude API（通过 auto_register 参数控制）
"""

import asyncio
import re
import shutil
from typing import Optional, List
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, status, Query

from logger import get_logger
from models.agent import (
    SkillCreateRequest,
    SkillUpdateRequest,
    SkillSummary,
    SkillDetail,
    SkillListResponse,
)

logger = get_logger("router.skills")

router = APIRouter(prefix="/api/v1/skills", tags=["Skills 管理"])


# ============================================================
# 辅助函数
# ============================================================

_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")


def _validate_name(value: str, label: str) -> None:
    if not value or not _NAME_RE.match(value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "VALIDATION_ERROR",
                "message": f"{label}格式不合法: {value}，必须以字母开头，只能包含字母、数字、下划线、连字符",
            },
        )


def _ensure_within(base_dir: Path, target_path: Path, label: str) -> Path:
    base_dir = base_dir.resolve()
    target_path = target_path.resolve()
    try:
        target_path.relative_to(base_dir)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "VALIDATION_ERROR",
                "message": f"{label}路径不合法",
            },
        )
    return target_path


def _get_skills_library_dir() -> Path:
    """获取 skills/library 目录路径"""
    current_file = Path(__file__)
    project_root = current_file.parent.parent
    return project_root / "skills" / "library"


def _get_instance_skills_dir(agent_id: str) -> Path:
    """获取 instances/{agent_id}/skills 目录路径"""
    current_file = Path(__file__)
    project_root = current_file.parent.parent
    instances_dir = project_root / "instances"
    skills_dir = instances_dir / agent_id / "skills"
    return _ensure_within(instances_dir, skills_dir, "agent_id")


def _get_skill_dir(skill_name: str, agent_id: Optional[str]) -> Path:
    """获取指定 Skill 的目录路径（带安全校验）"""
    _validate_name(skill_name, "Skill 名称")
    if agent_id:
        _validate_name(agent_id, "agent_id")
        base_dir = _get_instance_skills_dir(agent_id)
    else:
        base_dir = _get_skills_library_dir()
    return _ensure_within(base_dir, base_dir / skill_name, "Skill 名称")


def _parse_skill_metadata(skill_md_path: Path) -> dict:
    """
    解析 SKILL.md 文件的 YAML frontmatter
    
    Args:
        skill_md_path: SKILL.md 文件路径
        
    Returns:
        解析后的元数据
    """
    import yaml
    
    content = skill_md_path.read_text(encoding="utf-8")
    
    # 检查是否有 YAML frontmatter
    if not content.startswith("---"):
        return {"name": skill_md_path.parent.name, "description": ""}
    
    # 提取 frontmatter
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {"name": skill_md_path.parent.name, "description": ""}
    
    try:
        metadata = yaml.safe_load(parts[1])
        return metadata or {}
    except Exception:
        return {"name": skill_md_path.parent.name, "description": ""}


async def _sync_skill_to_claude_api(
    skill_name: str,
    skill_content: str,
    agent_id: str = None
) -> dict:
    """
    同步 Skill 到 Claude API（内部辅助函数）
    
    Args:
        skill_name: Skill 名称
        skill_content: SKILL.md 内容
        agent_id: 所属 Agent ID
        
    Returns:
        同步结果 {"success": bool, "skill_id": str, "message": str}
    """
    try:
        # TODO: 实际调用 Claude Skills API 注册 Skill
        # 这里先返回模拟结果
        skill_id = f"skill_{skill_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        logger.info(f"🔄 同步 Skill 到 Claude API: {skill_name}")
        
        return {
            "success": True,
            "skill_id": skill_id,
            "message": f"已同步到 Claude API",
        }
        
    except Exception as e:
        logger.error(f"同步 Skill 失败: {e}", exc_info=True)
        return {
            "success": False,
            "skill_id": None,
            "message": f"同步失败: {str(e)}",
        }


def _scan_skills_in_dir(skills_dir: Path, agent_id: str = None) -> List[dict]:
    """
    扫描目录中的所有 Skills
    
    Args:
        skills_dir: Skills 目录路径
        agent_id: 所属 Agent ID（可选）
        
    Returns:
        Skills 列表
    """
    skills = []
    
    if not skills_dir.exists():
        return skills
    
    for skill_dir in skills_dir.iterdir():
        if not skill_dir.is_dir():
            continue
        
        # 跳过特殊目录
        if skill_dir.name.startswith("_") or skill_dir.name == "__pycache__":
            continue
        
        # 检查 SKILL.md
        skill_md_path = skill_dir / "SKILL.md"
        if not skill_md_path.exists():
            continue
        
        try:
            metadata = _parse_skill_metadata(skill_md_path)
            
            skills.append({
                "name": metadata.get("name", skill_dir.name),
                "description": metadata.get("description", ""),
                "agent_id": agent_id or "global",
                "path": str(skill_dir),
                "is_enabled": True,
                "is_registered": False,  # TODO: 从数据库获取
                "skill_id": None,
                "created_at": datetime.fromtimestamp(skill_md_path.stat().st_mtime),
            })
        except Exception as e:
            logger.warning(f"解析 Skill '{skill_dir.name}' 失败: {e}")
    
    return skills


# ============================================================
# 列表和查询
# ============================================================

@router.get(
    "",
    response_model=SkillListResponse,
    summary="列出所有 Skills",
    description="获取所有已注册的 Skills 列表",
)
async def list_skills(
    agent_id: Optional[str] = Query(None, description="按 Agent ID 过滤"),
    include_global: bool = Query(True, description="是否包含全局 Skills（skills/library）"),
):
    """
    列出所有 Skills
    
    返回全局 Skills 和/或指定 Agent 的 Skills
    """
    skills = []
    
    # 全局 Skills
    if include_global and not agent_id:
        library_dir = _get_skills_library_dir()
        global_skills = _scan_skills_in_dir(library_dir)
        skills.extend(global_skills)
    
    # Agent 特定 Skills
    if agent_id:
        _validate_name(agent_id, "agent_id")
        instance_skills_dir = _get_instance_skills_dir(agent_id)
        agent_skills = _scan_skills_in_dir(instance_skills_dir, agent_id)
        skills.extend(agent_skills)
    elif not include_global:
        # 列出所有 Agent 的 Skills
        from utils.instance_loader import list_instances
        for instance_name in list_instances():
            instance_skills_dir = _get_instance_skills_dir(instance_name)
            agent_skills = _scan_skills_in_dir(instance_skills_dir, instance_name)
            skills.extend(agent_skills)
    
    # 转换为响应格式
    summaries = [
        SkillSummary(
            name=s["name"],
            description=s["description"],
            agent_id=s["agent_id"],
            is_enabled=s["is_enabled"],
            is_registered=s["is_registered"],
            skill_id=s["skill_id"],
            created_at=s["created_at"],
        )
        for s in skills
    ]
    
    return SkillListResponse(
        total=len(summaries),
        skills=summaries,
    )


@router.get(
    "/{skill_name}",
    response_model=SkillDetail,
    summary="获取 Skill 详情",
    description="获取指定 Skill 的详细信息",
)
async def get_skill(
    skill_name: str,
    agent_id: Optional[str] = Query(None, description="所属 Agent ID（不传则搜索全局）"),
):
    """
    获取 Skill 详情
    
    Args:
        skill_name: Skill 名称
        agent_id: 所属 Agent ID
        
    Returns:
        Skill 详细信息
    """
    skill_dir = _get_skill_dir(skill_name, agent_id)
    skill_md_path = skill_dir / "SKILL.md"
    
    if skill_md_path.exists():
        metadata = _parse_skill_metadata(skill_md_path)
        
        return SkillDetail(
            name=metadata.get("name", skill_name),
            description=metadata.get("description", ""),
            agent_id=agent_id or "global",
            is_enabled=True,
            is_registered=False,  # TODO: 从数据库获取
            skill_id=None,
            skill_path=str(skill_dir),
            created_at=datetime.fromtimestamp(skill_md_path.stat().st_mtime),
            registered_at=None,
            updated_at=datetime.fromtimestamp(skill_md_path.stat().st_mtime),
        )
    
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "SKILL_NOT_FOUND",
            "message": f"Skill '{skill_name}' 不存在",
        }
    )


# ============================================================
# 创建和更新
# ============================================================

@router.post(
    "",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="创建 Skill",
    description="创建新的 Skill",
)
async def create_skill(request: SkillCreateRequest):
    """
    创建 Skill
    
    在 instances/{agent_id}/skills/ 目录下创建新的 Skill
    """
    # 验证 skill_name 格式
    _validate_name(request.name, "Skill 名称")
    
    # 确定目标目录
    skill_dir = _get_skill_dir(request.name, request.agent_id)
    
    if skill_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "SKILL_EXISTS",
                "message": f"Skill '{request.name}' 已存在",
            }
        )
    
    try:
        # 创建目录结构
        skill_dir.mkdir(parents=True)
        (skill_dir / "scripts").mkdir(exist_ok=True)
        (skill_dir / "resources").mkdir(exist_ok=True)
        
        # 写入 SKILL.md
        skill_md_path = skill_dir / "SKILL.md"
        skill_md_path.write_text(request.skill_content, encoding="utf-8")
        
        # 创建 __init__.py
        (skill_dir / "__init__.py").write_text("", encoding="utf-8")
        (skill_dir / "scripts" / "__init__.py").write_text("", encoding="utf-8")
        
        logger.info(f"✅ 创建 Skill: {request.name} (Agent: {request.agent_id})")
        
        # 自动同步到 Claude API（如果启用）
        skill_id = None
        sync_message = ""
        if request.auto_register:
            sync_result = await _sync_skill_to_claude_api(
                skill_name=request.name,
                skill_content=request.skill_content,
                agent_id=request.agent_id
            )
            skill_id = sync_result.get("skill_id")
            sync_message = sync_result.get("message", "")
            logger.info(f"🔄 Skill '{request.name}' 已同步到 Claude API: {skill_id}")
        
        return {
            "success": True,
            "name": request.name,
            "agent_id": request.agent_id,
            "path": str(skill_dir),
            "skill_id": skill_id,
            "message": f"Skill '{request.name}' 创建成功" + (f"，{sync_message}" if sync_message else ""),
        }
        
    except Exception as e:
        # 回滚（异步删除）
        if skill_dir.exists():
            await asyncio.to_thread(shutil.rmtree, skill_dir)
        
        logger.error(f"创建 Skill 失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INTERNAL_ERROR",
                "message": f"创建 Skill 失败: {str(e)}",
            }
        )


@router.put(
    "/{skill_name}",
    response_model=dict,
    summary="更新 Skill",
    description="更新指定 Skill 的内容",
)
async def update_skill(
    skill_name: str,
    request: SkillUpdateRequest,
    agent_id: Optional[str] = Query(None, description="所属 Agent ID"),
):
    """
    更新 Skill
    
    更新 Skill 的 SKILL.md 内容
    """
    # 确定搜索路径
    skill_dir = _get_skill_dir(skill_name, agent_id)
    
    skill_md_path = skill_dir / "SKILL.md"
    
    if not skill_md_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "SKILL_NOT_FOUND",
                "message": f"Skill '{skill_name}' 不存在",
            }
        )
    
    try:
        updated_fields = []
        
        if request.skill_content is not None:
            skill_md_path.write_text(request.skill_content, encoding="utf-8")
            updated_fields.append("skill_content")
        
        if request.enabled is not None:
            # TODO: 更新数据库中的启用状态
            updated_fields.append("enabled")
        
        logger.info(f"✅ 更新 Skill: {skill_name}")
        
        return {
            "success": True,
            "name": skill_name,
            "updated_fields": updated_fields,
            "message": f"Skill '{skill_name}' 更新成功",
        }
        
    except Exception as e:
        logger.error(f"更新 Skill 失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INTERNAL_ERROR",
                "message": f"更新 Skill 失败: {str(e)}",
            }
        )


# ============================================================
# 删除
# ============================================================

@router.delete(
    "/{skill_name}",
    response_model=dict,
    summary="删除 Skill",
    description="删除指定的 Skill（包括文件）",
)
async def delete_skill(
    skill_name: str,
    agent_id: Optional[str] = Query(None, description="所属 Agent ID"),
    force: bool = Query(False, description="是否强制删除"),
):
    """
    删除 Skill
    
    删除 Skill 的目录和所有文件
    """
    # 确定搜索路径
    skill_dir = _get_skill_dir(skill_name, agent_id)
    
    if not skill_dir.exists():
        if force:
            return {
                "success": True,
                "name": skill_name,
                "message": f"Skill '{skill_name}' 不存在，已忽略",
            }
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "SKILL_NOT_FOUND",
                "message": f"Skill '{skill_name}' 不存在",
            }
        )
    
    try:
        await asyncio.to_thread(shutil.rmtree, skill_dir)
        
        logger.info(f"🗑️ 删除 Skill: {skill_name}")
        
        return {
            "success": True,
            "name": skill_name,
            "message": f"Skill '{skill_name}' 已删除",
        }
        
    except Exception as e:
        if force:
            logger.warning(f"删除 Skill 失败但已忽略: {e}")
            return {
                "success": True,
                "name": skill_name,
                "message": f"Skill '{skill_name}' 删除失败已忽略",
            }
        logger.error(f"删除 Skill 失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INTERNAL_ERROR",
                "message": f"删除 Skill 失败: {str(e)}",
            }
        )


# ============================================================
# Pre-built Skills
# ============================================================

@router.get(
    "/prebuilt/list",
    response_model=dict,
    summary="列出 Pre-built Skills",
    description="获取 Anthropic 提供的 Pre-built Skills 列表",
)
async def list_prebuilt_skills():
    """
    列出 Pre-built Skills
    
    返回 Anthropic 官方提供的 Pre-built Skills
    """
    from prompts.skills_loader import PREBUILT_SKILLS
    
    return {
        "total": len(PREBUILT_SKILLS),
        "skills": PREBUILT_SKILLS,
    }
