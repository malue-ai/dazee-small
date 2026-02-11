"""
Agent 管理路由

提供 Agent CRUD 操作的 REST API + WebSocket 创建进度推送
"""

import asyncio
import shutil
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Set

import aiofiles
import yaml
from fastapi import APIRouter, Body, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from logger import get_logger
from core.llm.model_registry import ModelRegistry
from models.agent import (
    AgentCreateRequest,
    AgentDetail,
    AgentListResponse,
    AgentSummary,
)
from services import (
    AgentNotFoundError,
    get_agent_registry,
)
from utils.instance_loader import get_instances_dir

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/agents", tags=["Agent 管理"])


# ============================================================
# 创建任务追踪（内存级，支持 WebSocket 推送进度）
# ============================================================


@dataclass
class CreationTask:
    """Agent 创建任务状态"""

    agent_id: str
    agent_name: str
    step: int = 0
    total: int = 7
    message: str = ""
    status: str = "creating"  # creating | complete | error
    error: str = ""
    detail: Optional[dict] = None
    subscribers: Set[asyncio.Queue] = field(default_factory=set)


# agent_id → CreationTask（生命周期：创建开始 → 完成/失败后 120s 清理）
_creation_tasks: Dict[str, CreationTask] = {}


async def _notify_subscribers(task: CreationTask, event: dict):
    """Push event to all WebSocket subscribers of a creation task."""
    for queue in list(task.subscribers):
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            pass


async def _background_preload(
    agent_id: str,
    agent_name: str,
    registry,
    instance_dir: Path,
):
    """
    Background task: preload agent instance and push progress via WebSocket.

    Runs as fire-and-forget — continues even if all WS subscribers disconnect.
    """
    task = _creation_tasks.get(agent_id)
    if not task:
        return

    try:
        async def progress_callback(step: int, message: str):
            task.step = step
            task.message = message
            await _notify_subscribers(task, {
                "type": "progress",
                "step": step,
                "total": task.total,
                "message": message,
            })

        await registry.preload_instance(agent_id, progress_callback=progress_callback)

        detail = registry.get_agent_detail(agent_id)
        task.status = "complete"
        task.step = task.total
        task.message = "创建完成"
        task.detail = detail

        await _notify_subscribers(task, {
            "type": "complete",
            "agent_id": agent_id,
            "name": agent_name,
            "success": True,
            **detail,
        })
        logger.info(f"✅ Agent '{agent_id}' 后台创建完成")

    except Exception as e:
        logger.error(f"后台创建 Agent '{agent_id}' 失败: {e}", exc_info=True)
        if instance_dir.exists():
            shutil.rmtree(instance_dir, ignore_errors=True)

        task.status = "error"
        task.error = str(e)
        await _notify_subscribers(task, {
            "type": "error",
            "code": "CREATE_FAILED",
            "message": str(e),
        })

    finally:
        # Keep task for late WS subscribers, then clean up
        await asyncio.sleep(120)
        _creation_tasks.pop(agent_id, None)


async def _background_reload(
    agent_id: str,
    agent_name: str,
    registry,
):
    """
    Background task: reload agent instance and push progress via WebSocket.

    Used by update_agent to avoid blocking the PUT request.
    Reuses the same CreationTask / WS progress mechanism as create.
    """
    task = _creation_tasks.get(agent_id)
    if not task:
        return

    try:
        # Clear old config/prototype before reload
        registry._agent_prototypes.pop(agent_id, None)
        registry._configs.pop(agent_id, None)

        async def progress_callback(step: int, message: str):
            task.step = step
            task.message = message
            await _notify_subscribers(task, {
                "type": "progress",
                "step": step,
                "total": task.total,
                "message": message,
            })

        await registry.preload_instance(
            agent_id,
            force_refresh=True,
            progress_callback=progress_callback,
        )

        detail = registry.get_agent_detail(agent_id)
        task.status = "complete"
        task.step = task.total
        task.message = "更新完成"
        task.detail = detail

        await _notify_subscribers(task, {
            "type": "complete",
            "agent_id": agent_id,
            "name": agent_name,
            "success": True,
            **detail,
        })
        logger.info(f"✅ Agent '{agent_id}' 后台重载完成")

    except Exception as e:
        logger.error(f"后台重载 Agent '{agent_id}' 失败: {e}", exc_info=True)

        task.status = "error"
        task.error = str(e)
        await _notify_subscribers(task, {
            "type": "error",
            "code": "RELOAD_FAILED",
            "message": str(e),
        })

    finally:
        # Keep task for late WS subscribers, then clean up
        await asyncio.sleep(120)
        _creation_tasks.pop(agent_id, None)


# ============================================================
# 请求/响应模型
# ============================================================


class ValidationError(BaseModel):
    """校验错误"""

    field: str = Field(..., description="错误字段")
    message: str = Field(..., description="错误消息")
    code: str = Field("VALIDATION_ERROR", description="错误代码")


class ValidationWarning(BaseModel):
    """校验警告"""

    field: str = Field(..., description="警告字段")
    message: str = Field(..., description="警告消息")


class AgentValidationResponse(BaseModel):
    """Agent 配置校验响应"""

    valid: bool = Field(..., description="是否通过校验")
    errors: list[ValidationError] = Field(default_factory=list, description="校验错误列表")
    warnings: list[ValidationWarning] = Field(default_factory=list, description="校验警告列表")


class AgentTemplate(BaseModel):
    """Agent 模板"""

    id: str = Field(..., description="模板 ID")
    name: str = Field(..., description="模板名称")
    description: str = Field(..., description="模板描述")
    icon: str = Field("🤖", description="模板图标")
    config: dict = Field(..., description="模板配置")


class AgentTemplateListResponse(BaseModel):
    """Agent 模板列表响应"""

    total: int = Field(..., description="模板总数")
    templates: list[AgentTemplate] = Field(..., description="模板列表")


class AgentPreviewResponse(BaseModel):
    """Agent 配置预览响应"""

    config_yaml: str = Field(..., description="生成的 config.yaml 内容")
    prompt_md: str = Field(..., description="生成的 prompt.md 内容")


# ============================================================
# 预定义模板
# ============================================================

AGENT_TEMPLATES = [
    AgentTemplate(
        id="minimal",
        name="最小配置",
        description="仅包含搜索能力的轻量级 Agent，适合简单问答场景",
        icon="🔍",
        config={
            "plan_manager_enabled": False,
            "enabled_capabilities": {
                "code_execution": False,
            },
            "llm": {
                "enable_thinking": False,
                "max_tokens": 8192,
                "enable_caching": True,
            },
            "memory": {
                "mem0_enabled": True,
                "smart_retrieval": True,
                "retention_policy": "session",
            },
        },
    ),
    AgentTemplate(
        id="standard",
        name="标准配置",
        description="搜索 + 知识库，适合大多数业务场景",
        icon="⚡",
        config={
            "plan_manager_enabled": True,
            "enabled_capabilities": {
                "code_execution": False,
            },
            "llm": {
                "enable_thinking": True,
                "thinking_budget": 8000,
                "max_tokens": 16384,
                "enable_caching": True,
            },
            "memory": {
                "mem0_enabled": True,
                "smart_retrieval": True,
                "retention_policy": "user",
            },
        },
    ),
    AgentTemplate(
        id="advanced",
        name="高级配置",
        description="全部功能 + Extended Thinking，适合复杂推理任务",
        icon="🚀",
        config={
            "plan_manager_enabled": True,
            "enabled_capabilities": {
                "code_execution": True,
                "document_skills": True,
            },
            "llm": {
                "enable_thinking": True,
                "thinking_budget": 16000,
                "max_tokens": 32768,
                "enable_caching": True,
            },
            "memory": {
                "mem0_enabled": True,
                "smart_retrieval": True,
                "retention_policy": "user",
            },
        },
    ),
]


# ============================================================
# 列表和查询
# ============================================================


@router.get(
    "",
    response_model=AgentListResponse,
    summary="列出所有 Agent",
    description="获取所有已注册的 Agent 列表",
)
async def list_agents(
    include_inactive: bool = Query(False, description="是否包含未激活的 Agent"),
):
    """
    列出所有 Agent

    返回所有已预加载的 Agent 摘要信息
    """
    registry = get_agent_registry()
    agents_raw = registry.list_agents()

    # 转换为 AgentSummary
    agents = []
    for agent_data in agents_raw:
        try:
            # 获取详细信息
            detail = registry.get_agent_detail(agent_data["agent_id"])

            summary = AgentSummary(
                agent_id=agent_data["agent_id"],
                name=detail.get("name", agent_data.get("name", agent_data["agent_id"])),
                description=detail.get("description", agent_data.get("description", "")),
                version=detail.get("version", agent_data.get("version", "1.0.0")),
                is_active=True,  # 预加载的都是激活状态
                total_calls=0,  # TODO: 从数据库获取
                created_at=datetime.fromisoformat(agent_data["loaded_at"]),
                last_used_at=None,
            )
            agents.append(summary)
        except Exception as e:
            logger.warning(f"获取 Agent '{agent_data['agent_id']}' 摘要失败: {e}")

    return AgentListResponse(
        total=len(agents),
        agents=agents,
    )


# ============================================================
# 模板、校验和预览（必须在 /{agent_id} 之前定义）
# ============================================================


@router.get(
    "/default-data-path",
    summary="获取默认实例数据存储路径",
    description="返回项目实例数据的默认存储根目录，前端可用于展示",
)
async def get_default_data_path():
    """
    获取默认实例数据存储路径

    返回 ``{user_data_dir}/data/instances/`` 的绝对路径字符串，
    前端可在「存储路径」字段中作为提示信息展示。
    """
    from utils.app_paths import get_user_data_dir

    default_path = get_user_data_dir() / "data" / "instances"
    return {"default_path": str(default_path)}


@router.get(
    "/templates",
    response_model=AgentTemplateListResponse,
    summary="获取 Agent 模板列表",
    description="获取预定义的 Agent 配置模板",
)
async def list_agent_templates():
    """
    获取 Agent 模板列表

    返回预定义的配置模板，包含最小、标准、高级三种配置
    """
    return AgentTemplateListResponse(
        total=len(AGENT_TEMPLATES),
        templates=AGENT_TEMPLATES,
    )


@router.post(
    "/validate",
    response_model=AgentValidationResponse,
    summary="校验 Agent 配置",
    description="校验 Agent 配置是否有效（不创建）",
)
async def validate_agent_config(request: AgentCreateRequest):
    """
    校验 Agent 配置

    对配置进行校验，返回错误和警告信息，但不实际创建 Agent
    """
    errors: list[ValidationError] = []
    warnings: list[ValidationWarning] = []

    # 1. 校验 name 字段（必填）
    if not request.name:
        errors.append(
            ValidationError(
                field="name",
                message="Agent 名称不能为空",
                code="REQUIRED_FIELD",
            )
        )
    elif len(request.name) > 100:
        errors.append(
            ValidationError(
                field="name",
                message="Agent 名称长度不能超过 100 个字符",
                code="MAX_LENGTH_EXCEEDED",
            )
        )

    # 2. 校验 agent_id 格式（可选，如果提供了则校验）
    registry = get_agent_registry()
    if request.agent_id:
        if not request.agent_id.replace("_", "").replace("-", "").isalnum():
            errors.append(
                ValidationError(
                    field="agent_id",
                    message="Agent ID 只能包含字母、数字、下划线和连字符",
                    code="INVALID_FORMAT",
                )
            )
        elif len(request.agent_id) > 64:
            errors.append(
                ValidationError(
                    field="agent_id",
                    message="Agent ID 长度不能超过 64 个字符",
                    code="MAX_LENGTH_EXCEEDED",
                )
            )
        elif registry.has_agent(request.agent_id):
            errors.append(
                ValidationError(
                    field="agent_id",
                    message=f"Agent '{request.agent_id}' 已存在",
                    code="ALREADY_EXISTS",
                )
            )

    # 3. 校验 prompt
    if not request.prompt:
        errors.append(
            ValidationError(
                field="prompt",
                message="系统提示词不能为空",
                code="REQUIRED_FIELD",
            )
        )
    elif len(request.prompt) < 50:
        warnings.append(
            ValidationWarning(
                field="prompt",
                message="系统提示词过短（建议至少 50 个字符），可能影响 Agent 表现",
            )
        )

    # 4. 校验模型（通过 ModelRegistry 验证存在性和能力匹配）
    model_config = ModelRegistry.get(request.model) if request.model else None

    if request.model and not model_config:
        available_models = ModelRegistry.list_model_names()
        errors.append(
            ValidationError(
                field="model",
                message=(
                    f"模型 '{request.model}' 未在 ModelRegistry 注册。"
                    f"可用模型: {', '.join(available_models[:10])}"
                    + (f" 等共 {len(available_models)} 个" if len(available_models) > 10 else "")
                ),
                code="UNKNOWN_MODEL",
            )
        )

    if model_config:
        caps = model_config.capabilities

        # 4a. enable_thinking vs supports_thinking
        if request.llm and request.llm.enable_thinking and not caps.supports_thinking:
            warnings.append(
                ValidationWarning(
                    field="llm.enable_thinking",
                    message=(
                        f"模型 '{model_config.display_name or model_config.model_name}' "
                        f"不支持 Extended Thinking，该配置将被忽略"
                    ),
                )
            )

        # 4b. max_tokens vs model limit
        if request.llm and request.llm.max_tokens and caps.max_tokens:
            if request.llm.max_tokens > caps.max_tokens:
                warnings.append(
                    ValidationWarning(
                        field="llm.max_tokens",
                        message=(
                            f"请求的 max_tokens={request.llm.max_tokens} 超过模型上限 "
                            f"{caps.max_tokens}，运行时将被自动截断"
                        ),
                    )
                )

    # 5. 校验 LLM 配置
    if request.llm:
        if request.llm.thinking_budget and request.llm.thinking_budget > 32000:
            warnings.append(
                ValidationWarning(
                    field="llm.thinking_budget",
                    message="思考预算过大（>32000），可能导致响应缓慢",
                )
            )

    # 7. 校验 REST APIs
    if request.apis:
        for i, api in enumerate(request.apis):
            if not api.name:
                errors.append(
                    ValidationError(
                        field=f"apis[{i}].name",
                        message="API 名称不能为空",
                        code="REQUIRED_FIELD",
                    )
                )
            if not api.base_url:
                errors.append(
                    ValidationError(
                        field=f"apis[{i}].base_url",
                        message="API URL 不能为空",
                        code="REQUIRED_FIELD",
                    )
                )

    return AgentValidationResponse(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


@router.post(
    "/preview",
    response_model=AgentPreviewResponse,
    summary="预览 Agent 配置",
    description="预览最终生成的配置文件内容",
)
async def preview_agent_config(request: AgentCreateRequest):
    """
    预览 Agent 配置

    根据请求数据生成配置文件预览（config.yaml 和 prompt.md）
    """
    preview_agent_id = request.agent_id or "agent_<auto_generated_uuid>"

    config_data = _build_config_dict(request)

    config_yaml = yaml.dump(
        config_data,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        indent=2,
    )

    config_yaml = (
        f"# ============================================================\n"
        f"# {request.name} 实例配置\n"
        f"# ============================================================\n"
        f"# \n"
        f"# Agent ID: {preview_agent_id}\n"
        f"# {request.description or '智能助手'}\n"
        f"#\n"
        f"# ============================================================\n\n"
        f"{config_yaml}"
    )

    return AgentPreviewResponse(
        config_yaml=config_yaml,
        prompt_md=request.prompt,
    )


# ============================================================
# 创建、更新、删除
# ============================================================


def _build_config_dict(request: AgentCreateRequest) -> dict:
    """
    Convert AgentCreateRequest to config.yaml dict.

    Generates config that matches the _template/config.yaml format:
    - Uses agent.provider (derived from model) for LLM profiles resolution
    - Only includes explicitly set fields, no hardcoded defaults

    Shared by create / update / preview endpoints.
    """
    config_data: dict = {
        "instance": {
            "name": request.name,
            "description": request.description or f"{request.name} 智能助手",
            "version": "1.0.0",
        },
    }

    # Agent config: derive provider from model, match template format
    agent_section: dict = {}

    if request.model:
        # Derive provider from model registry
        model_config = ModelRegistry.get(request.model)
        if model_config:
            agent_section["provider"] = model_config.provider
        # Also store explicit model (overrides provider template default)
        agent_section["model"] = request.model

    # Only include optional fields when explicitly provided (not None)
    if request.plan_manager_enabled is not None:
        agent_section["plan_manager_enabled"] = request.plan_manager_enabled

    if agent_section:
        config_data["agent"] = agent_section

    # LLM config
    if request.llm:
        llm_config: dict = {}
        if request.llm.enable_thinking is not None:
            llm_config["enable_thinking"] = request.llm.enable_thinking
        if request.llm.thinking_budget is not None:
            llm_config["thinking_budget"] = request.llm.thinking_budget
        if request.llm.thinking_mode is not None:
            llm_config["thinking_mode"] = request.llm.thinking_mode
        if request.llm.max_tokens is not None:
            llm_config["max_tokens"] = request.llm.max_tokens
        if request.llm.enable_caching is not None:
            llm_config["enable_caching"] = request.llm.enable_caching
        if request.llm.temperature is not None:
            llm_config["temperature"] = request.llm.temperature
        if request.llm.top_p is not None:
            llm_config["top_p"] = request.llm.top_p
        if llm_config:
            config_data.setdefault("agent", {})["llm"] = llm_config

    # enabled_capabilities
    if request.enabled_capabilities:
        config_data["enabled_capabilities"] = {
            k: (1 if v else 0) for k, v in request.enabled_capabilities.items()
        }

    # REST APIs
    if request.apis:
        config_data["apis"] = [
            {
                "name": api.name,
                "base_url": api.base_url,
                "auth": {
                    "type": api.auth.type,
                    "header": api.auth.header,
                    "env": api.auth.env,
                },
                "doc": api.doc,
                "capability": api.capability,
                "description": api.description,
            }
            for api in request.apis
        ]

    # Memory (only when explicitly provided)
    if request.memory:
        config_data["memory"] = {
            "mem0_enabled": request.memory.mem0_enabled,
            "smart_retrieval": request.memory.smart_retrieval,
            "retention_policy": request.memory.retention_policy,
        }

    # Storage (custom data directory)
    if request.data_dir:
        config_data["storage"] = {
            "data_dir": request.data_dir,
        }

    return config_data


async def _write_instance_files(
    instance_dir: Path,
    config_data: dict,
    prompt_content: str,
    agent_id: str,
    name: str,
    description: str,
) -> None:
    """
    Write config.yaml and prompt.md to instance directory.

    Creates subdirectories and copies template skeleton files if needed.
    """
    instance_dir.mkdir(parents=True, exist_ok=True)

    # Create subdirectories
    (instance_dir / "config").mkdir(exist_ok=True)
    (instance_dir / "skills").mkdir(exist_ok=True)

    # Copy template skeleton files (skills.yaml, llm_profiles.yaml) if not present
    template_dir = get_instances_dir() / "_template"
    for sub_file in ["config/skills.yaml", "config/llm_profiles.yaml"]:
        target = instance_dir / sub_file
        source = template_dir / sub_file
        if not target.exists() and source.exists():
            shutil.copy2(source, target)

    # Write config.yaml
    config_yaml = yaml.dump(
        config_data,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        indent=2,
    )
    header = (
        f"# ============================================================\n"
        f"# {name} 实例配置\n"
        f"# ============================================================\n"
        f"# \n"
        f"# Agent ID: {agent_id}\n"
        f"# {description or '智能助手'}\n"
        f"#\n"
        f"# ============================================================\n\n"
    )
    async with aiofiles.open(instance_dir / "config.yaml", "w", encoding="utf-8") as f:
        await f.write(header + config_yaml)

    # Write prompt.md
    async with aiofiles.open(instance_dir / "prompt.md", "w", encoding="utf-8") as f:
        await f.write(prompt_content)


def _validate_create_request(request: AgentCreateRequest):
    """
    Validate create-agent request (model, agent_id, directory).

    Returns (registry, agent_id, instance_dir, config_data) on success.
    Raises HTTPException on validation failure.
    """
    registry = get_agent_registry()

    # 0. Validate model is provided
    if not request.model:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "MODEL_REQUIRED",
                "message": "请选择一个模型",
            },
        )

    model_config = ModelRegistry.get(request.model)
    if not model_config:
        available = ModelRegistry.list_model_names()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "UNKNOWN_MODEL",
                "message": f"模型 '{request.model}' 未注册",
                "available_models": available[:20],
            },
        )

    # 1. Generate or validate agent_id
    agent_id = request.agent_id or str(uuid.uuid4())[:8]

    if registry.has_agent(agent_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "ALREADY_EXISTS",
                "message": f"Agent '{agent_id}' 已存在",
            },
        )

    instance_dir = get_instances_dir() / agent_id
    if instance_dir.exists():
        if registry.has_agent(agent_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "DIRECTORY_EXISTS",
                    "message": f"实例目录 '{agent_id}' 已存在，请更换 agent_id",
                },
            )
        else:
            # Orphan directory from a previous interrupted creation — clean it up
            logger.warning(f"发现孤儿目录 '{agent_id}'（未加载到注册表），清理后重建")
            shutil.rmtree(instance_dir, ignore_errors=True)

    # 2. Validate custom data_dir (if provided)
    if request.data_dir:
        data_path = Path(request.data_dir).expanduser().resolve()
        # Must be an absolute path
        if not data_path.is_absolute():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_DATA_DIR",
                    "message": "存储路径必须是绝对路径",
                },
            )
        # Verify parent directory exists (or can be created)
        try:
            data_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "DATA_DIR_NOT_WRITABLE",
                    "message": f"存储路径无法创建或无写入权限: {e}",
                },
            )
        # Normalize the path back to request for config building
        request.data_dir = str(data_path)

    config_data = _build_config_dict(request)
    return registry, agent_id, instance_dir, config_data


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="创建 Agent",
    description=(
        "创建新的 Agent 实例。"
        "写入配置文件后立即返回 agent_id，后台异步执行 preload。"
        "通过 WebSocket /ws/create/{agent_id} 接收实时创建进度。"
    ),
)
async def create_agent(request: AgentCreateRequest, raw_request: Request):
    """
    创建 Agent（异步模式）

    流程：
    1. 校验请求（名称、ID 唯一性等）
    2. 生成 config.yaml + prompt.md
    3. 写入 instances/{agent_id}/ 目录
    4. 后台异步执行 registry.preload_instance()
    5. 立即返回 agent_id + status: "creating"

    前端通过 WS /api/v1/agents/ws/create/{agent_id} 实时获取创建进度。
    """
    registry, agent_id, instance_dir, config_data = _validate_create_request(request)

    # Write files synchronously (fast, <1s)
    try:
        await _write_instance_files(
            instance_dir=instance_dir,
            config_data=config_data,
            prompt_content=request.prompt,
            agent_id=agent_id,
            name=request.name,
            description=request.description,
        )
    except Exception as e:
        if instance_dir.exists():
            shutil.rmtree(instance_dir, ignore_errors=True)
        logger.error(f"创建 Agent '{agent_id}' 写入文件失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "WRITE_FAILED", "message": f"写入配置文件失败: {str(e)}"},
        )

    # Register creation task tracker
    task = CreationTask(agent_id=agent_id, agent_name=request.name)
    _creation_tasks[agent_id] = task

    # Fire-and-forget: preload in background
    asyncio.create_task(_background_preload(
        agent_id=agent_id,
        agent_name=request.name,
        registry=registry,
        instance_dir=instance_dir,
    ))

    logger.info(f"Agent '{agent_id}' 文件写入完成，后台开始 preload")
    return {
        "success": True,
        "agent_id": agent_id,
        "name": request.name,
        "status": "creating",
    }


@router.websocket("/ws/create/{agent_id}")
async def ws_agent_create_progress(websocket: WebSocket, agent_id: str):
    """
    WebSocket endpoint for real-time agent creation progress.

    Frontend connects after POST /api/v1/agents returns the agent_id.
    Events pushed:
      - {"type": "progress", "step": N, "total": 7, "message": "..."}
      - {"type": "complete", "agent_id": "...", "name": "...", ...}
      - {"type": "error", "code": "...", "message": "..."}
    """
    await websocket.accept()

    task = _creation_tasks.get(agent_id)
    if not task:
        # No active creation task — maybe already complete and cleaned up
        # Check if agent is loaded in registry
        registry = get_agent_registry()
        if registry.has_agent(agent_id):
            detail = registry.get_agent_detail(agent_id)
            await websocket.send_json({
                "type": "complete",
                "agent_id": agent_id,
                "name": detail.get("name", ""),
                "success": True,
                **detail,
            })
        else:
            await websocket.send_json({
                "type": "error",
                "code": "NO_TASK",
                "message": f"没有进行中的创建任务: {agent_id}",
            })
        await websocket.close()
        return

    # If task already finished, send final event immediately
    if task.status == "complete" and task.detail:
        await websocket.send_json({
            "type": "complete",
            "agent_id": agent_id,
            "name": task.agent_name,
            "success": True,
            **task.detail,
        })
        await websocket.close()
        return

    if task.status == "error":
        await websocket.send_json({
            "type": "error",
            "code": "CREATE_FAILED",
            "message": task.error,
        })
        await websocket.close()
        return

    # Subscribe to live events
    queue: asyncio.Queue = asyncio.Queue(maxsize=64)
    task.subscribers.add(queue)

    try:
        # Send current progress snapshot (for late subscribers)
        if task.step > 0:
            await websocket.send_json({
                "type": "progress",
                "step": task.step,
                "total": task.total,
                "message": task.message,
            })

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15)
            except asyncio.TimeoutError:
                # Keepalive — send a ping frame
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
                continue

            await websocket.send_json(event)

            if event.get("type") in ("complete", "error"):
                break

    except (WebSocketDisconnect, Exception):
        logger.debug(f"WS 创建进度连接断开: agent_id={agent_id}")
    finally:
        task.subscribers.discard(queue)


@router.put(
    "/{agent_id}",
    summary="更新 Agent",
    description="更新已有 Agent 的配置和提示词",
)
async def update_agent(agent_id: str, request: AgentCreateRequest):
    """
    更新 Agent

    覆盖写入 config.yaml 和 prompt.md，然后热重载。
    """
    registry = get_agent_registry()

    # Resolve model: use specified model, or fall back to first activated model
    if not request.model:
        activated = ModelRegistry.list_activated()
        if activated:
            request.model = activated[0].model_name

    if request.model:
        model_config = ModelRegistry.get(request.model)
        if not model_config:
            available = ModelRegistry.list_model_names()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "UNKNOWN_MODEL",
                    "message": f"模型 '{request.model}' 未注册",
                    "available_models": available[:20],
                },
            )

    # Check agent exists
    instance_dir = get_instances_dir() / agent_id
    if not instance_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "AGENT_NOT_FOUND",
                "message": f"Agent '{agent_id}' 不存在",
            },
        )

    # Validate custom data_dir (if provided)
    if request.data_dir:
        data_path = Path(request.data_dir).expanduser().resolve()
        if not data_path.is_absolute():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_DATA_DIR",
                    "message": "存储路径必须是绝对路径",
                },
            )
        try:
            data_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "DATA_DIR_NOT_WRITABLE",
                    "message": f"存储路径无法创建或无写入权限: {e}",
                },
            )
        request.data_dir = str(data_path)

    # Build and write
    config_data = _build_config_dict(request)

    try:
        await _write_instance_files(
            instance_dir=instance_dir,
            config_data=config_data,
            prompt_content=request.prompt,
            agent_id=agent_id,
            name=request.name,
            description=request.description,
        )
    except Exception as e:
        logger.error(f"更新 Agent '{agent_id}' 写入文件失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "WRITE_FAILED",
                "message": f"写入配置文件失败: {str(e)}",
            },
        )

    # Async reload: register task and fire-and-forget (same as create flow)
    task = CreationTask(agent_id=agent_id, agent_name=request.name)
    _creation_tasks[agent_id] = task

    asyncio.create_task(_background_reload(
        agent_id=agent_id,
        agent_name=request.name,
        registry=registry,
    ))

    logger.info(f"Agent '{agent_id}' 配置已更新，后台开始重载")
    return {
        "success": True,
        "agent_id": agent_id,
        "name": request.name,
        "status": "reloading",
    }


@router.delete(
    "/{agent_id}",
    summary="删除 Agent",
    description="删除 Agent 实例（从注册表卸载并删除配置文件）",
)
async def delete_agent(agent_id: str):
    """
    删除 Agent

    1. 从注册表卸载
    2. 删除 instances/{agent_id}/ 目录
    """
    registry = get_agent_registry()
    instance_dir = get_instances_dir() / agent_id

    if not instance_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "AGENT_NOT_FOUND",
                "message": f"Agent '{agent_id}' 不存在",
            },
        )

    # Unload from registry (if loaded)
    try:
        registry.unload_agent(agent_id)
    except AgentNotFoundError:
        pass  # Not loaded, but directory exists - still delete

    # Delete directory
    try:
        shutil.rmtree(instance_dir)
    except Exception as e:
        logger.error(f"删除 Agent '{agent_id}' 目录失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "DELETE_FAILED",
                "message": f"删除目录失败: {str(e)}",
            },
        )

    logger.info(f"🗑️ Agent '{agent_id}' 已删除")

    return {
        "success": True,
        "agent_id": agent_id,
        "message": f"Agent '{agent_id}' 已删除",
    }


# ============================================================
# 重载
# ============================================================


@router.post(
    "/reload",
    response_model=dict,
    summary="热重载所有 Agent",
    description="重新加载所有 Agent 配置",
)
async def reload_all_agents():
    """
    热重载所有 Agent

    重新从 instances/ 目录加载所有 Agent 配置
    """
    registry = get_agent_registry()

    try:
        result = await registry.reload_agent(agent_id=None)

        logger.info("🔄 热重载所有 Agent 完成")

        return {
            "success": True,
            **result,
        }

    except Exception as e:
        logger.error(f"热重载失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INTERNAL_ERROR",
                "message": f"热重载失败: {str(e)}",
            },
        )


# ============================================================
# 单个 Agent 查询（动态路由，必须在静态路由之后）
# ============================================================


@router.get(
    "/{agent_id}",
    summary="获取 Agent 详情",
    description="获取指定 Agent 的详细配置信息",
)
async def get_agent(agent_id: str):
    """
    获取 Agent 详情

    Args:
        agent_id: Agent ID

    Returns:
        Agent 详细信息（包含 enabled_capabilities 对象）
    """
    registry = get_agent_registry()

    try:
        detail_raw = registry.get_agent_detail(agent_id)
    except AgentNotFoundError:
        # Try on-demand loading before returning 404
        loaded = await registry._try_on_demand_load(agent_id)
        if loaded:
            detail_raw = registry.get_agent_detail(agent_id)
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "AGENT_NOT_FOUND",
                    "message": f"Agent '{agent_id}' 不存在",
                    "available_agents": registry.list_agents(),
                },
            )

    # 返回原始字典，包含 enabled_capabilities 对象格式
    return {
        "agent_id": detail_raw["agent_id"],
        "name": detail_raw["name"],
        "description": detail_raw.get("description", ""),
        "version": detail_raw.get("version", "1.0.0"),
        "is_active": detail_raw.get("is_active", True),
        "model": detail_raw.get("model"),
        "plan_manager_enabled": detail_raw.get("plan_manager_enabled", False),
        "enabled_capabilities": detail_raw.get("enabled_capabilities", {}),
        "apis": detail_raw.get("apis", []),
        "skills": detail_raw.get("skills", []),
        "loaded_at": detail_raw["loaded_at"],
    }


@router.get(
    "/{agent_id}/prompt",
    summary="获取 Agent 的 Prompt",
    description="获取 Agent 的原始 prompt.md 内容",
)
async def get_agent_prompt(agent_id: str):
    """
    获取 Agent 的 Prompt 内容

    Args:
        agent_id: Agent ID

    Returns:
        prompt.md 文件内容
    """
    registry = get_agent_registry()

    try:
        prompt_content = await registry.get_agent_prompt(agent_id)
    except AgentNotFoundError:
        # Try on-demand loading before returning 404
        loaded = await registry._try_on_demand_load(agent_id)
        if loaded:
            prompt_content = await registry.get_agent_prompt(agent_id)
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "AGENT_NOT_FOUND",
                    "message": f"Agent '{agent_id}' 不存在",
                },
            )

    return {
        "agent_id": agent_id,
        "prompt": prompt_content,
    }


