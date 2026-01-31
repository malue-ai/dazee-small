"""
Agent 管理路由

提供 Agent CRUD 操作的 REST API
"""

from typing import Optional
from datetime import datetime

import yaml
from fastapi import APIRouter, HTTPException, status, Query, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from logger import get_logger
from services import (
    get_agent_registry,
    AgentNotFoundError,
    get_mcp_service,
    MCPNotFoundError, 
    MCPAlreadyExistsError,
)
from models.agent import (
    AgentCreateRequest,
    AgentUpdateRequest,
    AgentSummary,
    AgentDetail,
    AgentListResponse,
)

logger = get_logger("router.agents")

router = APIRouter(prefix="/api/v1/agents", tags=["Agent 管理"])

# 获取服务实例
mcp_service = get_mcp_service()


# ============================================================
# 请求/响应模型
# ============================================================

class AgentMCPEnableRequest(BaseModel):
    """为 Agent 启用 MCP 的请求"""
    auth_env: Optional[str] = Field(None, description="Agent 专用的认证环境变量名（覆盖全局配置）")
    metadata: Optional[dict] = Field(None, description="Agent 专用的元数据")


class AgentMCPUpdateRequest(BaseModel):
    """更新 Agent MCP 配置的请求"""
    auth_env: Optional[str] = Field(None, description="认证环境变量名")
    is_active: Optional[bool] = Field(None, description="是否启用")
    metadata: Optional[dict] = Field(None, description="元数据")


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
            "model": "claude-sonnet-4-5-20250929",
            "max_turns": 10,
            "plan_manager_enabled": False,
            "enabled_capabilities": {
                "tavily_search": True,
                "knowledge_search": False,
                "sandbox_tools": False,
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
        description="搜索 + 知识库 + 代码沙盒，适合大多数业务场景",
        icon="⚡",
        config={
            "model": "claude-sonnet-4-5-20250929",
            "max_turns": 20,
            "plan_manager_enabled": True,
            "enabled_capabilities": {
                "tavily_search": True,
                "knowledge_search": True,
                "sandbox_tools": True,
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
            "model": "claude-sonnet-4-5-20250929",
            "max_turns": 30,
            "plan_manager_enabled": True,
            "enabled_capabilities": {
                "tavily_search": True,
                "knowledge_search": True,
                "sandbox_tools": True,
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
                name=agent_data["agent_id"],
                description=agent_data.get("description", ""),
                version=agent_data.get("version", "1.0.0"),
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
    
    # 1. 校验 agent_id 格式
    if not request.agent_id:
        errors.append(ValidationError(
            field="agent_id",
            message="Agent ID 不能为空",
            code="REQUIRED_FIELD",
        ))
    elif not request.agent_id.replace("_", "").replace("-", "").isalnum():
        errors.append(ValidationError(
            field="agent_id",
            message="Agent ID 只能包含字母、数字、下划线和连字符",
            code="INVALID_FORMAT",
        ))
    elif len(request.agent_id) > 64:
        errors.append(ValidationError(
            field="agent_id",
            message="Agent ID 长度不能超过 64 个字符",
            code="MAX_LENGTH_EXCEEDED",
        ))
    
    # 2. 检查 agent_id 是否已存在
    registry = get_agent_registry()
    if request.agent_id and registry.has_agent(request.agent_id):
        errors.append(ValidationError(
            field="agent_id",
            message=f"Agent '{request.agent_id}' 已存在",
            code="ALREADY_EXISTS",
        ))
    
    # 3. 校验 prompt
    if not request.prompt:
        errors.append(ValidationError(
            field="prompt",
            message="系统提示词不能为空",
            code="REQUIRED_FIELD",
        ))
    elif len(request.prompt) < 50:
        warnings.append(ValidationWarning(
            field="prompt",
            message="系统提示词过短（建议至少 50 个字符），可能影响 Agent 表现",
        ))
    
    # 4. 校验模型
    valid_model_prefixes = ["claude-", "gpt-", "gemini-", "qwen"]
    if request.model and not any(request.model.startswith(p) for p in valid_model_prefixes):
        warnings.append(ValidationWarning(
            field="model",
            message=f"未知模型 '{request.model}'，可能不受支持",
        ))
    
    # 5. 校验 max_turns
    if request.max_turns < 1:
        errors.append(ValidationError(
            field="max_turns",
            message="最大对话轮数必须大于 0",
            code="INVALID_VALUE",
        ))
    elif request.max_turns > 100:
        warnings.append(ValidationWarning(
            field="max_turns",
            message="最大对话轮数过大（>100），可能导致性能问题",
        ))
    
    # 6. 校验 LLM 配置
    if request.llm:
        if request.llm.thinking_budget and request.llm.thinking_budget > 32000:
            warnings.append(ValidationWarning(
                field="llm.thinking_budget",
                message="思考预算过大（>32000），可能导致响应缓慢",
            ))
        if request.llm.max_tokens and request.llm.max_tokens > 64000:
            warnings.append(ValidationWarning(
                field="llm.max_tokens",
                message="最大输出 token 过大（>64000），可能超出模型限制",
            ))
    
    # 7. 校验 MCP 工具
    if request.mcp_tools:
        for i, tool in enumerate(request.mcp_tools):
            if not tool.name:
                errors.append(ValidationError(
                    field=f"mcp_tools[{i}].name",
                    message="MCP 工具名称不能为空",
                    code="REQUIRED_FIELD",
                ))
            if not tool.server_url:
                errors.append(ValidationError(
                    field=f"mcp_tools[{i}].server_url",
                    message="MCP 服务器 URL 不能为空",
                    code="REQUIRED_FIELD",
                ))
            if tool.auth_type not in ["none", "bearer", "api_key"]:
                errors.append(ValidationError(
                    field=f"mcp_tools[{i}].auth_type",
                    message=f"无效的认证类型 '{tool.auth_type}'",
                    code="INVALID_VALUE",
                ))
    
    # 8. 校验 REST APIs
    if request.apis:
        for i, api in enumerate(request.apis):
            if not api.name:
                errors.append(ValidationError(
                    field=f"apis[{i}].name",
                    message="API 名称不能为空",
                    code="REQUIRED_FIELD",
                ))
            if not api.base_url:
                errors.append(ValidationError(
                    field=f"apis[{i}].base_url",
                    message="API URL 不能为空",
                    code="REQUIRED_FIELD",
                ))
    
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
    # 构建 config.yaml 内容
    config_data = {
        "instance": {
            "name": request.agent_id,
            "description": request.description or f"{request.agent_id} 智能助手",
            "version": "1.0.0",
        },
        "agent": {
            "model": request.model,
            "max_turns": request.max_turns,
            "plan_manager_enabled": request.plan_manager_enabled,
            "allow_parallel_tools": False,
        },
    }
    
    # 添加 LLM 配置
    if request.llm:
        llm_config = {}
        if request.llm.enable_thinking is not None:
            llm_config["enable_thinking"] = request.llm.enable_thinking
        if request.llm.thinking_budget is not None:
            llm_config["thinking_budget"] = request.llm.thinking_budget
        if request.llm.max_tokens is not None:
            llm_config["max_tokens"] = request.llm.max_tokens
        if request.llm.enable_caching is not None:
            llm_config["enable_caching"] = request.llm.enable_caching
        if request.llm.temperature is not None:
            llm_config["temperature"] = request.llm.temperature
        if request.llm.top_p is not None:
            llm_config["top_p"] = request.llm.top_p
        if llm_config:
            config_data["agent"]["llm"] = llm_config
    
    # 添加 enabled_capabilities
    if request.enabled_capabilities:
        config_data["enabled_capabilities"] = {
            k: (1 if v else 0) for k, v in request.enabled_capabilities.items()
        }
    
    # 添加 MCP 工具
    if request.mcp_tools:
        config_data["mcp_tools"] = [
            {
                "name": tool.name,
                "server_url": tool.server_url,
                "server_name": tool.server_name or tool.name,
                "auth_type": tool.auth_type,
                "auth_env": tool.auth_env,
                "capability": tool.capability,
                "description": tool.description,
            }
            for tool in request.mcp_tools
        ]
    
    # 添加 APIs
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
    
    # 添加 Memory 配置
    if request.memory:
        config_data["memory"] = {
            "mem0_enabled": request.memory.mem0_enabled,
            "smart_retrieval": request.memory.smart_retrieval,
            "retention_policy": request.memory.retention_policy,
        }
    
    # 生成 YAML
    config_yaml = yaml.dump(
        config_data,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        indent=2,
    )
    
    # 添加注释头
    config_yaml = f"""# ============================================================
# {request.agent_id} 实例配置
# ============================================================
# 
# {request.description or '智能助手'}
#
# ============================================================

{config_yaml}"""
    
    return AgentPreviewResponse(
        config_yaml=config_yaml,
        prompt_md=request.prompt,
    )


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
            }
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
        
        # 返回原始字典，包含 enabled_capabilities 对象格式
        return {
            "agent_id": detail_raw["agent_id"],
            "name": detail_raw["name"],
            "description": detail_raw.get("description", ""),
            "version": detail_raw.get("version", "1.0.0"),
            "is_active": detail_raw.get("is_active", True),
            "model": detail_raw.get("model"),
            "max_turns": detail_raw.get("max_turns"),
            "plan_manager_enabled": detail_raw.get("plan_manager_enabled", False),
            "enabled_capabilities": detail_raw.get("enabled_capabilities", {}),
            "mcp_tools": detail_raw.get("mcp_tools", []),
            "apis": detail_raw.get("apis", []),
            "skills": detail_raw.get("skills", []),
            "loaded_at": detail_raw["loaded_at"],
        }
    except AgentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "AGENT_NOT_FOUND",
                "message": str(e),
                "available_agents": registry.list_agents(),
            }
        )


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
        return {
            "agent_id": agent_id,
            "prompt": prompt_content,
        }
    except AgentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "AGENT_NOT_FOUND",
                "message": str(e),
            }
        )


# ============================================================
# 创建和更新
# ============================================================

@router.post(
    "",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="创建 Agent",
    description="创建新的 Agent 实例",
)
async def create_agent(request: AgentCreateRequest):
    """
    创建 Agent
    
    在 instances/ 目录下创建新的 Agent 配置
    """
    registry = get_agent_registry()
    
    try:
        # 转换 MCP 工具配置
        mcp_tools = None
        if request.mcp_tools:
            mcp_tools = [tool.model_dump() for tool in request.mcp_tools]
        
        # 转换 API 配置
        apis = None
        if request.apis:
            apis = [api.model_dump() for api in request.apis]
        
        # 转换 LLM 配置
        llm = None
        if request.llm:
            llm = {k: v for k, v in request.llm.model_dump().items() if v is not None}
            if not llm:
                llm = None
        
        # 转换 Memory 配置
        memory = None
        if request.memory:
            memory = request.memory.model_dump()
        
        result = await registry.create_agent(
            agent_id=request.agent_id,
            description=request.description,
            prompt=request.prompt,
            model=request.model,
            max_turns=request.max_turns,
            plan_manager_enabled=request.plan_manager_enabled,
            enabled_capabilities=request.enabled_capabilities,
            mcp_tools=mcp_tools,
            apis=apis,
            memory=memory,
            llm=llm,
        )
        
        logger.info(f"✅ 创建 Agent: {request.agent_id}")
        
        return {
            "success": True,
            **result,
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "VALIDATION_ERROR",
                "message": str(e),
            }
        )
    except Exception as e:
        logger.error(f"创建 Agent 失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INTERNAL_ERROR",
                "message": f"创建 Agent 失败: {str(e)}",
            }
        )


@router.put(
    "/{agent_id}",
    response_model=dict,
    summary="更新 Agent",
    description="更新指定 Agent 的配置",
)
async def update_agent(agent_id: str, request: AgentUpdateRequest):
    """
    更新 Agent
    
    更新 Agent 的配置文件并重新加载
    """
    registry = get_agent_registry()
    
    try:
        # 准备更新参数（只传递非 None 的值）
        update_kwargs = {}
        
        if request.description is not None:
            update_kwargs["description"] = request.description
        if request.prompt is not None:
            update_kwargs["prompt"] = request.prompt
        if request.model is not None:
            update_kwargs["model"] = request.model
        if request.max_turns is not None:
            update_kwargs["max_turns"] = request.max_turns
        if request.plan_manager_enabled is not None:
            update_kwargs["plan_manager_enabled"] = request.plan_manager_enabled
        if request.enabled_capabilities is not None:
            update_kwargs["enabled_capabilities"] = request.enabled_capabilities
        if request.mcp_tools is not None:
            update_kwargs["mcp_tools"] = [tool.model_dump() for tool in request.mcp_tools]
        if request.apis is not None:
            update_kwargs["apis"] = [api.model_dump() for api in request.apis]
        if request.memory is not None:
            update_kwargs["memory"] = request.memory.model_dump()
        if request.llm is not None:
            update_kwargs["llm"] = {k: v for k, v in request.llm.model_dump().items() if v is not None}
        if request.is_active is not None:
            update_kwargs["is_active"] = request.is_active
        
        result = await registry.update_agent(agent_id=agent_id, **update_kwargs)
        
        logger.info(f"✅ 更新 Agent: {agent_id}")
        
        return {
            "success": True,
            **result,
        }
        
    except AgentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "AGENT_NOT_FOUND",
                "message": str(e),
            }
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "VALIDATION_ERROR",
                "message": str(e),
            }
        )
    except Exception as e:
        logger.error(f"更新 Agent 失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INTERNAL_ERROR",
                "message": f"更新 Agent 失败: {str(e)}",
            }
        )


# ============================================================
# 删除
# ============================================================

@router.delete(
    "/{agent_id}",
    response_model=dict,
    summary="删除 Agent",
    description="删除指定的 Agent（包括配置文件）",
)
async def delete_agent(
    agent_id: str,
    force: bool = Query(False, description="是否强制删除"),
):
    """
    删除 Agent
    
    删除 Agent 的配置目录和注册表记录
    """
    registry = get_agent_registry()
    
    try:
        result = await registry.delete_agent(agent_id=agent_id, force=force)
        
        logger.info(f"🗑️ 删除 Agent: {agent_id}")
        
        return {
            "success": True,
            **result,
        }
        
    except AgentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "AGENT_NOT_FOUND",
                "message": str(e),
            }
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "VALIDATION_ERROR",
                "message": str(e),
            }
        )
    except Exception as e:
        logger.error(f"删除 Agent 失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INTERNAL_ERROR",
                "message": f"删除 Agent 失败: {str(e)}",
            }
        )


# ============================================================
# 单个 Agent 热重载
# ============================================================

@router.post(
    "/{agent_id}/reload",
    response_model=dict,
    summary="热重载单个 Agent",
    description="重新加载指定 Agent 的配置",
)
async def reload_agent(agent_id: str):
    """
    热重载单个 Agent
    
    重新加载指定 Agent 的配置文件
    """
    registry = get_agent_registry()
    
    try:
        result = await registry.reload_agent(agent_id=agent_id)
        
        logger.info(f"🔄 热重载 Agent: {agent_id}")
        
        return {
            "success": True,
            **result,
        }
        
    except AgentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "AGENT_NOT_FOUND",
                "message": str(e),
            }
        )
    except Exception as e:
        logger.error(f"热重载 Agent 失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INTERNAL_ERROR",
                "message": f"热重载失败: {str(e)}",
            }
        )


# ============================================================
# Agent-MCP 关联管理
# ============================================================

@router.get(
    "/{agent_id}/mcp",
    summary="列出 Agent 启用的 MCP",
    description="获取指定 Agent 启用的所有 MCP 服务器列表",
)
async def list_agent_mcps(
    agent_id: str,
    include_inactive: bool = Query(False, description="是否包含未激活的"),
):
    """
    列出 Agent 启用的所有 MCP
    
    返回该 Agent 已启用并配置的 MCP 服务器列表
    """
    # 先检查 Agent 是否存在
    registry = get_agent_registry()
    if not registry.has_agent(agent_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "AGENT_NOT_FOUND", "message": f"Agent '{agent_id}' 不存在或未加载"}
        )
    
    try:
        mcps = await mcp_service.list_agent_mcps(
            agent_id=agent_id,
            include_inactive=include_inactive
        )
        
        return JSONResponse(content={
            "agent_id": agent_id,
            "total": len(mcps),
            "mcps": mcps,
        })
    
    except Exception as e:
        logger.error(f"列出 Agent MCP 失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "INTERNAL_ERROR", "message": f"查询失败: {str(e)}"}
        )


@router.post(
    "/{agent_id}/mcp/{server_name}",
    summary="为 Agent 启用 MCP",
    description="从全局 MCP 模板启用一个 MCP 并配置 Agent 专用认证",
)
async def enable_mcp_for_agent(
    agent_id: str,
    server_name: str,
    request: AgentMCPEnableRequest = Body(default=AgentMCPEnableRequest()),
):
    """
    为 Agent 启用 MCP
    
    从全局 MCP 模板复制配置，允许 Agent 自定义认证信息
    
    示例：
    ```
    POST /api/v1/agents/my_agent/mcp/notion
    {
        "auth_env": "MY_AGENT_NOTION_TOKEN"
    }
    ```
    """
    # 先检查 Agent 是否存在
    registry = get_agent_registry()
    if not registry.has_agent(agent_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "AGENT_NOT_FOUND", "message": f"Agent '{agent_id}' 不存在或未加载"}
        )
    
    try:
        mcp_data = await mcp_service.enable_mcp_for_agent(
            agent_id=agent_id,
            server_name=server_name,
            auth_env=request.auth_env,
            metadata=request.metadata,
        )
        
        logger.info(f"✅ 为 Agent 启用 MCP: agent={agent_id}, mcp={server_name}")
        
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "success": True,
                "message": f"Agent '{agent_id}' 已启用 MCP '{server_name}'",
                "data": mcp_data,
            }
        )
    
    except MCPNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "MCP_NOT_FOUND", "message": str(e)}
        )
    except MCPAlreadyExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "MCP_ALREADY_ENABLED", "message": str(e)}
        )
    except Exception as e:
        logger.error(f"启用 MCP 失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "INTERNAL_ERROR", "message": f"启用失败: {str(e)}"}
        )


@router.get(
    "/{agent_id}/mcp/available",
    summary="获取可用的全局 MCP 列表",
    description="获取所有全局 MCP 模板，方便在配置 Agent 时选择",
)
async def list_available_mcps_for_agent(
    agent_id: str,
    include_enabled: bool = Query(True, description="是否包含已启用的 MCP"),
):
    """
    获取可用的全局 MCP 列表
    
    返回所有全局 MCP 模板，标注哪些已被该 Agent 启用
    """
    # 先检查 Agent 是否存在
    registry = get_agent_registry()
    if not registry.has_agent(agent_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "AGENT_NOT_FOUND", "message": f"Agent '{agent_id}' 不存在或未加载"}
        )
    
    try:
        # 获取全局 MCP 列表
        global_mcps = await mcp_service.list_global_mcps(include_inactive=False)
        
        # 获取 Agent 已启用的 MCP
        agent_mcps = await mcp_service.list_agent_mcps(
            agent_id=agent_id,
            include_inactive=True
        )
        enabled_names = {mcp.get("original_name") for mcp in agent_mcps}
        
        # 标注启用状态
        result = []
        for mcp in global_mcps:
            mcp_name = mcp.get("server_name")
            is_enabled = mcp_name in enabled_names
            
            if include_enabled or not is_enabled:
                result.append({
                    **mcp,
                    "is_enabled_by_agent": is_enabled,
                })
        
        return JSONResponse(content={
            "agent_id": agent_id,
            "total": len(result),
            "enabled_count": len(enabled_names),
            "mcps": result,
        })
    
    except Exception as e:
        logger.error(f"获取可用 MCP 列表失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "INTERNAL_ERROR", "message": f"查询失败: {str(e)}"}
        )


@router.get(
    "/{agent_id}/mcp/{server_name}",
    summary="获取 Agent 的 MCP 配置",
    description="获取 Agent 启用的某个 MCP 的详细配置",
)
async def get_agent_mcp(
    agent_id: str,
    server_name: str,
):
    """
    获取 Agent 的某个 MCP 配置详情
    """
    # 先检查 Agent 是否存在
    registry = get_agent_registry()
    if not registry.has_agent(agent_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "AGENT_NOT_FOUND", "message": f"Agent '{agent_id}' 不存在或未加载"}
        )
    
    try:
        mcp_data = await mcp_service.get_agent_mcp(
            agent_id=agent_id,
            server_name=server_name,
        )
        
        return JSONResponse(content=mcp_data)
    
    except MCPNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "MCP_NOT_FOUND", "message": str(e)}
        )
    except Exception as e:
        logger.error(f"获取 Agent MCP 失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "INTERNAL_ERROR", "message": f"查询失败: {str(e)}"}
        )


@router.put(
    "/{agent_id}/mcp/{server_name}",
    summary="更新 Agent 的 MCP 配置",
    description="更新 Agent 启用的某个 MCP 的配置（如认证信息）",
)
async def update_agent_mcp(
    agent_id: str,
    server_name: str,
    request: AgentMCPUpdateRequest,
):
    """
    更新 Agent 的 MCP 配置
    
    可更新认证环境变量、启用状态等
    """
    # 先检查 Agent 是否存在
    registry = get_agent_registry()
    if not registry.has_agent(agent_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "AGENT_NOT_FOUND", "message": f"Agent '{agent_id}' 不存在或未加载"}
        )
    
    try:
        mcp_data = await mcp_service.update_agent_mcp_config(
            agent_id=agent_id,
            server_name=server_name,
            auth_env=request.auth_env,
            is_active=request.is_active,
            metadata=request.metadata,
        )
        
        logger.info(f"✅ 更新 Agent MCP: agent={agent_id}, mcp={server_name}")
        
        return JSONResponse(content={
            "success": True,
            "message": f"Agent '{agent_id}' 的 MCP '{server_name}' 配置已更新",
            "data": mcp_data,
        })
    
    except MCPNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "MCP_NOT_FOUND", "message": str(e)}
        )
    except Exception as e:
        logger.error(f"更新 Agent MCP 失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "INTERNAL_ERROR", "message": f"更新失败: {str(e)}"}
        )


@router.delete(
    "/{agent_id}/mcp/{server_name}",
    summary="为 Agent 禁用 MCP",
    description="禁用 Agent 的某个 MCP（从数据库删除关联）",
)
async def disable_mcp_for_agent(
    agent_id: str,
    server_name: str,
):
    """
    为 Agent 禁用 MCP
    
    删除 Agent 与该 MCP 的关联配置
    """
    # 先检查 Agent 是否存在
    registry = get_agent_registry()
    if not registry.has_agent(agent_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "AGENT_NOT_FOUND", "message": f"Agent '{agent_id}' 不存在或未加载"}
        )
    
    try:
        success = await mcp_service.disable_mcp_for_agent(
            agent_id=agent_id,
            server_name=server_name,
        )
        
        logger.info(f"✅ 为 Agent 禁用 MCP: agent={agent_id}, mcp={server_name}")
        
        return JSONResponse(content={
            "success": success,
            "message": f"Agent '{agent_id}' 已禁用 MCP '{server_name}'",
        })
    
    except MCPNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "MCP_NOT_FOUND", "message": str(e)}
        )
    except Exception as e:
        logger.error(f"禁用 MCP 失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "INTERNAL_ERROR", "message": f"禁用失败: {str(e)}"}
        )
