"""
Skills 管理路由

提供 Skills CRUD 操作的 REST API
"""

import asyncio
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import aiofiles
from fastapi import APIRouter, HTTPException, Query, UploadFile, status

from logger import get_logger
from models.skill import (
    SkillCreateRequest,
    SkillDetail,
    SkillInstallRequest,
    SkillListResponse,
    SkillSummary,
    SkillToggleRequest,
    SkillUninstallRequest,
    SkillUpdateContentRequest,
    SkillUpdateRequest,
)  # SkillStatus / SkillSyncResponse removed — no Claude Skill ID registration

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
    from utils.app_paths import get_bundle_dir
    return get_bundle_dir() / "skills" / "library"


def _get_instance_skills_dir(agent_id: str) -> Path:
    """获取 instances/{agent_id}/skills 目录路径"""
    from utils.app_paths import get_bundle_dir
    instances_dir = get_bundle_dir() / "instances"
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


async def _load_skills_yaml_descriptions(agent_id: str) -> dict[str, str]:
    """
    从实例的 skills.yaml 加载所有 skill 的 description 映射

    Args:
        agent_id: Agent 实例 ID

    Returns:
        {skill_name: description}
    """
    import yaml as _yaml

    from utils.app_paths import get_bundle_dir

    config_path = get_bundle_dir() / "instances" / agent_id / "config" / "skills.yaml"
    if not config_path.exists():
        return {}

    try:
        async with aiofiles.open(config_path, "r", encoding="utf-8") as f:
            content = await f.read()
            config = _yaml.safe_load(content) or {}
    except Exception:
        return {}

    desc_map: dict[str, str] = {}
    skills_section = config.get("skills", {})
    # 遍历 OS 分类（common / darwin / win32 / linux）
    for os_key in ("common", "darwin", "win32", "linux"):
        os_config = skills_section.get(os_key, {})
        if not isinstance(os_config, dict):
            continue
        # 遍历依赖等级（builtin / lightweight / external / cloud_api）
        for level_key in ("builtin", "lightweight", "external", "cloud_api"):
            items = os_config.get(level_key, [])
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict) and item.get("name"):
                    desc = item.get("description", "")
                    if desc:
                        desc_map[item["name"]] = desc

    return desc_map


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

            skills.append(
                {
                    "name": metadata.get("name", skill_dir.name),
                    "description": metadata.get("description", ""),
                    "agent_id": agent_id or "global",
                    "path": str(skill_dir),
                    "is_enabled": True,
                    "created_at": datetime.fromtimestamp(skill_md_path.stat().st_mtime),
                }
            )
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
            created_at=s["created_at"],
        )
        for s in skills
    ]

    return SkillListResponse(
        total=len(summaries),
        skills=summaries,
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
            },
        )

    try:
        # 创建目录结构
        skill_dir.mkdir(parents=True)
        (skill_dir / "scripts").mkdir(exist_ok=True)
        (skill_dir / "resources").mkdir(exist_ok=True)

        # 写入 SKILL.md（异步）
        skill_md_path = skill_dir / "SKILL.md"
        async with aiofiles.open(skill_md_path, "w", encoding="utf-8") as f:
            await f.write(request.skill_content)

        # 创建 __init__.py（异步）
        async with aiofiles.open(skill_dir / "__init__.py", "w", encoding="utf-8") as f:
            await f.write("")
        async with aiofiles.open(skill_dir / "scripts" / "__init__.py", "w", encoding="utf-8") as f:
            await f.write("")

        logger.info(f"✅ 创建 Skill: {request.name} (Agent: {request.agent_id})")

        return {
            "success": True,
            "name": request.name,
            "agent_id": request.agent_id,
            "path": str(skill_dir),
            "message": f"Skill '{request.name}' 创建成功",
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
            },
        )


# ============================================================
# 全局 Skills 管理
# ============================================================


@router.get(
    "/global",
    response_model=SkillListResponse,
    summary="列出全局 Skills",
    description="获取 skills/library/ 下的所有 Skills",
)
async def list_global_skills():
    """
    列出全局 Skills（skills/library/）

    这些 Skills 可以被安装到任意实例
    """
    library_dir = _get_skills_library_dir()
    global_skills = _scan_skills_in_dir(library_dir)

    summaries = [
        SkillSummary(
            name=s["name"],
            description=s["description"],
            agent_id="global",
            is_enabled=True,
            created_at=s["created_at"],
        )
        for s in global_skills
    ]

    return SkillListResponse(
        total=len(summaries),
        skills=summaries,
    )


@router.get(
    "/instance/{agent_id}",
    response_model=SkillListResponse,
    summary="列出实例已安装的 Skills",
    description="获取指定实例已安装的 Skills 列表（包含注册状态和描述）",
)
async def list_instance_skills(agent_id: str):
    """
    列出实例已安装的 Skills

    从 skill_registry.yaml 读取，并从 skills.yaml 或 SKILL.md 补充描述信息
    """
    _validate_name(agent_id, "agent_id")

    from utils.instance_loader import load_skill_registry

    try:
        skills = await load_skill_registry(agent_id)
    except Exception as e:
        logger.warning(f"加载实例 {agent_id} 的 skill_registry 失败: {e}")
        skills = []

    # 从 skills.yaml 加载描述（description 补充）
    desc_map = await _load_skills_yaml_descriptions(agent_id)

    summaries = []
    for s in skills:
        description = s.description
        # 描述为空时：优先从 skills.yaml 补充，其次从 SKILL.md frontmatter 补充
        if not description:
            description = desc_map.get(s.name, "")
        if not description and s.skill_path:
            skill_md = Path(s.skill_path) / "SKILL.md"
            if skill_md.exists():
                metadata = _parse_skill_metadata(skill_md)
                description = metadata.get("description", "")

        summaries.append(
            SkillSummary(
                name=s.name,
                description=description,
                agent_id=agent_id,
                is_enabled=s.enabled,
                created_at=datetime.now(),
            )
        )

    return SkillListResponse(
        total=len(summaries),
        skills=summaries,
    )


@router.get(
    "/detail/{skill_name}",
    response_model=SkillDetail,
    summary="获取 Skill 详细信息",
    description="获取 Skill 的完整信息，包括 SKILL.md 内容、脚本、资源文件",
)
async def get_skill_detail(
    skill_name: str,
    agent_id: Optional[str] = Query(None, description="实例 ID，不传则从全局库获取"),
):
    """
    获取 Skill 详细信息

    返回：
    - 元数据（name, description, priority, preferred_for）
    - SKILL.md 完整内容
    - 脚本文件列表
    - 资源文件列表
    - 注册状态（仅实例 Skill）
    """
    _validate_name(skill_name, "Skill 名称")

    # 确定 Skill 目录
    if agent_id:
        _validate_name(agent_id, "agent_id")
        skill_dir = _get_instance_skills_dir(agent_id) / skill_name
    else:
        skill_dir = _get_skills_library_dir() / skill_name

    if not skill_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "SKILL_NOT_FOUND",
                "message": f"Skill '{skill_name}' 不存在",
            },
        )

    # 读取 SKILL.md
    skill_md_path = skill_dir / "SKILL.md"
    content = ""
    metadata = {}
    if skill_md_path.exists():
        content = skill_md_path.read_text(encoding="utf-8")
        metadata = _parse_skill_metadata(skill_md_path)

    # 扫描脚本文件
    scripts = []
    scripts_dir = skill_dir / "scripts"
    if scripts_dir.exists():
        for f in scripts_dir.iterdir():
            if f.is_file() and f.suffix == ".py" and not f.name.startswith("_"):
                scripts.append(f.name)

    # 扫描资源文件
    resources = []
    resources_dir = skill_dir / "resources"
    if resources_dir.exists():
        for f in resources_dir.iterdir():
            if f.is_file() and not f.name.startswith("_"):
                resources.append(f.name)

    # 获取启用状态（仅实例 Skill）
    is_enabled = True

    if agent_id:
        from utils.instance_loader import load_skill_registry

        try:
            registry_skills = await load_skill_registry(agent_id)
            for s in registry_skills:
                if s.name == skill_name:
                    is_enabled = s.enabled
                    break
        except Exception as e:
            logger.warning(f"加载 skill_registry 失败: {e}")

    return SkillDetail(
        name=metadata.get("name", skill_name),
        description=metadata.get("description", ""),
        priority=metadata.get("priority", "medium"),
        preferred_for=metadata.get("preferred_for", []),
        scripts=scripts,
        resources=resources,
        content=content,
        agent_id=agent_id or "global",
        is_enabled=is_enabled,
        created_at=(
            datetime.fromtimestamp(skill_md_path.stat().st_mtime)
            if skill_md_path.exists()
            else None
        ),
    )


@router.get(
    "/file/{skill_name}/{file_type}/{file_name:path}",
    response_model=dict,
    summary="获取 Skill 文件内容",
    description="获取 Skill 中脚本或资源文件的内容",
)
async def get_skill_file_content(
    skill_name: str,
    file_type: str,
    file_name: str,
    agent_id: Optional[str] = Query(None, description="实例 ID，不传则从全局库获取"),
):
    """
    获取 Skill 文件内容

    Args:
        skill_name: Skill 名称
        file_type: 文件类型（scripts 或 resources）
        file_name: 文件名
        agent_id: 实例 ID（可选）

    Returns:
        文件内容和元信息
    """
    _validate_name(skill_name, "Skill 名称")

    if file_type not in ("scripts", "resources"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_FILE_TYPE",
                "message": f"文件类型必须是 scripts 或 resources，当前为: {file_type}",
            },
        )

    # 确定 Skill 目录
    if agent_id:
        _validate_name(agent_id, "agent_id")
        skill_dir = _get_instance_skills_dir(agent_id) / skill_name
    else:
        skill_dir = _get_skills_library_dir() / skill_name

    if not skill_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "SKILL_NOT_FOUND",
                "message": f"Skill '{skill_name}' 不存在",
            },
        )

    # 构建文件路径
    file_path = skill_dir / file_type / file_name

    # 安全检查：防止路径遍历攻击
    try:
        file_path = file_path.resolve()
        if not str(file_path).startswith(str(skill_dir.resolve())):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_PATH",
                    "message": "非法文件路径",
                },
            )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_PATH",
                "message": "非法文件路径",
            },
        )

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "FILE_NOT_FOUND",
                "message": f"文件 '{file_name}' 不存在",
            },
        )

    # 读取文件内容
    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # 二进制文件，返回提示
        return {
            "skill_name": skill_name,
            "file_type": file_type,
            "file_name": file_name,
            "content": None,
            "is_binary": True,
            "size": file_path.stat().st_size,
            "message": "此文件为二进制格式，无法显示内容",
        }
    except Exception as e:
        logger.error(f"读取文件失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "READ_ERROR",
                "message": f"读取文件失败: {str(e)}",
            },
        )

    # 根据文件扩展名确定语言
    ext = file_path.suffix.lower()
    language_map = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".md": "markdown",
        ".txt": "text",
        ".sh": "bash",
        ".sql": "sql",
        ".html": "html",
        ".css": "css",
    }
    language = language_map.get(ext, "text")

    return {
        "skill_name": skill_name,
        "file_type": file_type,
        "file_name": file_name,
        "content": content,
        "is_binary": False,
        "size": len(content),
        "language": language,
    }


# ============================================================
# 安装/卸载 Skills
# ============================================================


@router.post(
    "/install",
    response_model=dict,
    summary="安装 Skill 到实例",
    description="从全局库复制 Skill 到实例",
)
async def install_skill(request: SkillInstallRequest):
    """
    安装 Skill 到实例

    流程：
    1. 从 skills/library/{skill_name}/ 复制到 instances/{agent_id}/skills/{skill_name}/
    2. 更新 skill_registry.yaml
    """

    _validate_name(request.skill_name, "Skill 名称")
    _validate_name(request.agent_id, "agent_id")

    # 源目录（全局库）
    source_dir = _get_skills_library_dir() / request.skill_name
    if not source_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "SKILL_NOT_FOUND",
                "message": f"全局库中不存在 Skill '{request.skill_name}'",
            },
        )

    # 目标目录（实例）
    target_dir = _get_instance_skills_dir(request.agent_id) / request.skill_name
    if target_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "SKILL_EXISTS",
                "message": f"实例 '{request.agent_id}' 中已存在 Skill '{request.skill_name}'",
            },
        )

    try:
        # 1. 复制文件
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copytree, source_dir, target_dir)
        logger.info(f"✅ 复制 Skill: {source_dir} -> {target_dir}")

        # 2. 解析 SKILL.md 获取元数据
        skill_md_path = target_dir / "SKILL.md"
        metadata = _parse_skill_metadata(skill_md_path) if skill_md_path.exists() else {}
        description = metadata.get("description", "")

        # 3. 更新 skill_registry.yaml
        from utils.instance_loader import SkillConfig, _update_skill_registry, load_skill_registry

        existing_skills = await load_skill_registry(request.agent_id)

        new_skill = SkillConfig(
            name=request.skill_name, enabled=True, description=description, skill_path=target_dir
        )
        existing_skills.append(new_skill)

        await _update_skill_registry(request.agent_id, existing_skills)
        logger.info(f"✅ 更新 skill_registry.yaml: 添加 {request.skill_name}")

        return {
            "success": True,
            "skill_name": request.skill_name,
            "agent_id": request.agent_id,
            "message": f"Skill '{request.skill_name}' 已安装到实例 '{request.agent_id}'",
        }

    except Exception as e:
        # 回滚
        if target_dir.exists():
            await asyncio.to_thread(shutil.rmtree, target_dir)

        logger.error(f"安装 Skill 失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INTERNAL_ERROR",
                "message": f"安装 Skill 失败: {str(e)}",
            },
        )


@router.post(
    "/uninstall",
    response_model=dict,
    summary="从实例卸载 Skill",
    description="从实例删除 Skill",
)
async def uninstall_skill(request: SkillUninstallRequest):
    """
    从实例卸载 Skill

    流程：
    1. 从 skill_registry.yaml 移除
    2. 删除文件目录
    """

    _validate_name(request.skill_name, "Skill 名称")
    _validate_name(request.agent_id, "agent_id")

    skill_dir = _get_instance_skills_dir(request.agent_id) / request.skill_name

    if not skill_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "SKILL_NOT_FOUND",
                "message": f"实例 '{request.agent_id}' 中不存在 Skill '{request.skill_name}'",
            },
        )

    try:
        # 1. 从 skill_registry.yaml 移除
        from utils.instance_loader import _update_skill_registry, load_skill_registry

        existing_skills = await load_skill_registry(request.agent_id)
        updated_skills = [s for s in existing_skills if s.name != request.skill_name]
        await _update_skill_registry(request.agent_id, updated_skills)
        logger.info(f"✅ 从 skill_registry.yaml 移除: {request.skill_name}")

        # 2. 删除文件目录
        await asyncio.to_thread(shutil.rmtree, skill_dir)
        logger.info(f"🗑️ 删除 Skill 目录: {skill_dir}")

        return {
            "success": True,
            "skill_name": request.skill_name,
            "agent_id": request.agent_id,
            "message": f"Skill '{request.skill_name}' 已从实例 '{request.agent_id}' 卸载",
        }

    except Exception as e:
        logger.error(f"卸载 Skill 失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INTERNAL_ERROR",
                "message": f"卸载 Skill 失败: {str(e)}",
            },
        )


@router.post(
    "/toggle",
    response_model=dict,
    summary="启用/禁用 Skill",
    description="切换实例中 Skill 的启用状态",
)
async def toggle_skill(request: SkillToggleRequest):
    """
    启用/禁用 Skill

    更新 skill_registry.yaml 中的 enabled 字段
    """
    _validate_name(request.skill_name, "Skill 名称")
    _validate_name(request.agent_id, "agent_id")

    from utils.instance_loader import _update_skill_registry, load_skill_registry

    try:
        skills = await load_skill_registry(request.agent_id)

        # 查找目标 Skill
        target_skill = None
        for skill in skills:
            if skill.name == request.skill_name:
                target_skill = skill
                break

        if not target_skill:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "SKILL_NOT_FOUND",
                    "message": f"实例 '{request.agent_id}' 中不存在 Skill '{request.skill_name}'",
                },
            )

        # 更新状态
        target_skill.enabled = request.enabled
        await _update_skill_registry(request.agent_id, skills)

        status_text = "启用" if request.enabled else "禁用"
        logger.info(f"✅ {status_text} Skill: {request.skill_name} (实例: {request.agent_id})")

        return {
            "success": True,
            "skill_name": request.skill_name,
            "agent_id": request.agent_id,
            "enabled": request.enabled,
            "message": f"Skill '{request.skill_name}' 已{status_text}",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"切换 Skill 状态失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INTERNAL_ERROR",
                "message": f"切换 Skill 状态失败: {str(e)}",
            },
        )


@router.post(
    "/update_content",
    response_model=dict,
    summary="更新 Skill 内容",
    description="更新实例中 Skill 的 SKILL.md 内容",
)
async def update_skill_content(request: SkillUpdateContentRequest):
    """
    更新 Skill 内容 (SKILL.md)
    """
    _validate_name(request.skill_name, "Skill 名称")
    _validate_name(request.agent_id, "agent_id")

    skill_dir = _get_instance_skills_dir(request.agent_id) / request.skill_name
    skill_md_path = skill_dir / "SKILL.md"

    if not skill_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "SKILL_NOT_FOUND",
                "message": f"实例 '{request.agent_id}' 中不存在 Skill '{request.skill_name}'",
            },
        )

    try:
        # 写入文件（异步）
        async with aiofiles.open(skill_md_path, "w", encoding="utf-8") as f:
            await f.write(request.content)
        logger.info(f"✅ 更新 Skill 内容: {request.skill_name} (实例: {request.agent_id})")

        # 尝试解析元数据以确保格式正确（可选）
        try:
            metadata = _parse_skill_metadata(skill_md_path)
            # 可以在这里更新 registry 中的 description，如果需要的话
            from utils.instance_loader import _update_skill_registry, load_skill_registry

            skills = await load_skill_registry(request.agent_id)
            for skill in skills:
                if skill.name == request.skill_name:
                    skill.description = metadata.get("description", skill.description)
                    break
            await _update_skill_registry(request.agent_id, skills)

        except Exception as e:
            logger.warning(f"解析更新后的 SKILL.md 失败: {e}")

        return {
            "success": True,
            "skill_name": request.skill_name,
            "agent_id": request.agent_id,
            "message": "Skill 内容已更新",
        }

    except Exception as e:
        logger.error(f"更新 Skill 内容失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INTERNAL_ERROR",
                "message": f"更新 Skill 内容失败: {str(e)}",
            },
        )


# ============================================================
# 上传 Skill
# ============================================================


@router.post(
    "/upload",
    response_model=dict,
    summary="上传新 Skill 到全局库",
    description="上传 zip 文件创建新的 Skill",
)
async def upload_skill(
    file: UploadFile,
    skill_name: str = Query(..., description="Skill 名称"),
):
    """
    上传新 Skill 到全局库

    流程：
    1. 验证 skill_name 格式
    2. 解压 zip 文件到临时目录
    3. 验证必须包含 SKILL.md
    4. 验证 SKILL.md 的 YAML frontmatter
    5. 移动到 skills/library/{skill_name}/
    """
    import tempfile
    import zipfile

    _validate_name(skill_name, "Skill 名称")

    # 检查目标目录是否已存在
    target_dir = _get_skills_library_dir() / skill_name
    if target_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "SKILL_EXISTS",
                "message": f"全局库中已存在 Skill '{skill_name}'",
            },
        )

    # 验证文件类型
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_FILE",
                "message": "请上传 .zip 文件",
            },
        )

    temp_dir = None
    try:
        # 创建临时目录
        temp_dir = Path(tempfile.mkdtemp())
        zip_path = temp_dir / "skill.zip"

        # 保存上传的文件
        content = await file.read()
        zip_path.write_bytes(content)

        # 解压
        extract_dir = temp_dir / "extracted"
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_dir)

        # 查找 SKILL.md（可能在根目录或子目录中）
        skill_md_path = None
        for p in extract_dir.rglob("SKILL.md"):
            skill_md_path = p
            break

        if not skill_md_path:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_STRUCTURE",
                    "message": "zip 文件中必须包含 SKILL.md",
                },
            )

        # 确定 Skill 根目录（SKILL.md 所在目录）
        skill_root = skill_md_path.parent

        # 验证 SKILL.md 内容
        from utils.instance_loader import validate_skill_directory

        validation = await validate_skill_directory(skill_root)
        if not validation["valid"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "VALIDATION_FAILED",
                    "message": f"SKILL.md 验证失败: {'; '.join(validation['errors'])}",
                },
            )

        # 移动到全局库
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copytree, skill_root, target_dir)

        logger.info(f"✅ 上传 Skill 到全局库: {skill_name}")

        # 获取元数据
        metadata = _parse_skill_metadata(target_dir / "SKILL.md")

        return {
            "success": True,
            "skill_name": skill_name,
            "description": metadata.get("description", ""),
            "path": str(target_dir),
            "message": f"Skill '{skill_name}' 已上传到全局库",
        }

    except HTTPException:
        raise
    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_ZIP",
                "message": "无效的 zip 文件",
            },
        )
    except Exception as e:
        logger.error(f"上传 Skill 失败: {e}", exc_info=True)
        # 回滚
        if target_dir and target_dir.exists():
            await asyncio.to_thread(shutil.rmtree, target_dir)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INTERNAL_ERROR",
                "message": f"上传 Skill 失败: {str(e)}",
            },
        )
    finally:
        # 清理临时目录
        if temp_dir and temp_dir.exists():
            await asyncio.to_thread(shutil.rmtree, temp_dir)


# ============================================================
# 动态路由（放在最后以避免路径冲突）
# ============================================================


@router.get(
    "/{skill_name}",
    response_model=SkillDetail,
    summary="获取 Skill 详情（旧版）",
    description="获取指定 Skill 的详细信息（建议使用 /detail/{skill_name}）",
)
async def get_skill_legacy(
    skill_name: str,
    agent_id: Optional[str] = Query(None, description="所属 Agent ID（不传则搜索全局）"),
):
    """
    获取 Skill 详情（旧版兼容）
    """
    skill_dir = _get_skill_dir(skill_name, agent_id)
    skill_md_path = skill_dir / "SKILL.md"

    if skill_md_path.exists():
        metadata = _parse_skill_metadata(skill_md_path)

        return SkillDetail(
            name=metadata.get("name", skill_name),
            description=metadata.get("description", ""),
            priority=metadata.get("priority", "medium"),
            preferred_for=metadata.get("preferred_for", []),
            scripts=[],
            resources=[],
            content="",
            agent_id=agent_id or "global",
            is_enabled=True,
            created_at=datetime.fromtimestamp(skill_md_path.stat().st_mtime),
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "SKILL_NOT_FOUND",
            "message": f"Skill '{skill_name}' 不存在",
        },
    )


@router.put(
    "/{skill_name}",
    response_model=dict,
    summary="更新 Skill（旧版）",
    description="更新指定 Skill 的内容",
)
async def update_skill_legacy(
    skill_name: str,
    request: SkillUpdateRequest,
    agent_id: Optional[str] = Query(None, description="所属 Agent ID"),
):
    """
    更新 Skill（旧版兼容）
    """
    skill_dir = _get_skill_dir(skill_name, agent_id)
    skill_md_path = skill_dir / "SKILL.md"

    if not skill_md_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "SKILL_NOT_FOUND",
                "message": f"Skill '{skill_name}' 不存在",
            },
        )

    try:
        updated_fields = []

        if request.skill_content is not None:
            async with aiofiles.open(skill_md_path, "w", encoding="utf-8") as f:
                await f.write(request.skill_content)
            updated_fields.append("skill_content")

        if request.enabled is not None:
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
            },
        )


@router.delete(
    "/{skill_name}",
    response_model=dict,
    summary="删除 Skill（旧版）",
    description="删除指定的 Skill（包括文件）",
)
async def delete_skill_legacy(
    skill_name: str,
    agent_id: Optional[str] = Query(None, description="所属 Agent ID"),
    force: bool = Query(False, description="是否强制删除"),
):
    """
    删除 Skill（旧版兼容）
    """
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
            },
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
            },
        )
