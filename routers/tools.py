"""
工具管理路由 - Tool Management

职责：
- 工具注册/注销 API
- MCP 服务器连接
- 工具查询和列表
- 工具执行（直接/流式）

工具类型：
- USER_DEFINED: 用户自定义工具（BaseTool 子类或函数）
- MCP: MCP 协议工具
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException, Query, status
from fastapi.responses import JSONResponse, StreamingResponse

from logger import get_logger
from models.api import APIResponse
from models.tool import (  # 枚举; 工具定义; 工具执行; 工具注册; 工具查询
    ExecutionStatus,
    InteractionMode,
    MCPConfig,
    MCPServerRegistration,
    MCPServerRegistrationResponse,
    ReturnMode,
    ToolDefinition,
    ToolDetailResponse,
    ToolInputSchema,
    ToolInvocation,
    ToolListQuery,
    ToolListResponse,
    ToolRegistration,
    ToolRegistrationResponse,
    ToolResult,
    ToolResultChunk,
    ToolStatus,
    ToolType,
)
from services import (  # MCP 服务
    MCPAlreadyExistsError,
    MCPNotFoundError,
    ToolAlreadyExistsError,
    ToolExecutionError,
    ToolNotFoundError,
    ToolRegistrationError,
    ToolServiceError,
    get_mcp_service,
    get_tool_service,
)
from tools.base import BaseTool

# 配置日志
logger = get_logger("tools_router")

# 创建路由器
router = APIRouter(
    prefix="/api/v1/tools",
    tags=["tools"],
    responses={404: {"description": "Tool not found"}},
)

# 获取服务实例
tool_service = get_tool_service()
mcp_service = get_mcp_service()


# ============================================================
# 请求/响应模型（路由专用）
# ============================================================

from pydantic import BaseModel, Field


class ToolExecuteRequest(BaseModel):
    """工具执行请求"""

    tool_name: str = Field(..., description="工具名称")
    input: Dict[str, Any] = Field(default_factory=dict, description="输入参数")
    stream: bool = Field(False, description="是否流式返回")
    session_id: Optional[str] = Field(None, description="会话 ID")
    user_id: Optional[str] = Field(None, description="用户 ID")
    timeout: Optional[int] = Field(None, description="超时时间（秒）")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "tool_name": "web_search",
                    "input": {"query": "Claude API", "num_results": 5},
                    "stream": False,
                }
            ]
        }
    }


class BaseToolRegistrationRequest(BaseModel):
    """BaseTool 类注册请求"""

    module_path: str = Field(..., description="模块路径，如 'tools.plan_todo_tool'")
    class_name: str = Field(..., description="类名，如 'PlanTodoTool'")
    replace_existing: bool = Field(False, description="是否替换已存在的工具")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "module_path": "tools.plan_todo_tool",
                    "class_name": "PlanTodoTool",
                    "replace_existing": False,
                }
            ]
        }
    }


class FunctionToolRegistrationRequest(BaseModel):
    """
    函数工具注册请求（简化版）

    注意：真正的函数注册需要在代码中使用 @tool 装饰器
    此接口主要用于配置驱动的注册
    """

    name: str = Field(..., description="工具名称")
    description: str = Field(..., description="工具描述")
    input_schema: Dict[str, Any] = Field(..., description="输入参数 Schema")
    module_path: str = Field(..., description="函数所在模块路径")
    function_name: str = Field(..., description="函数名称")
    return_mode: ReturnMode = Field(ReturnMode.DIRECT, description="返回模式")
    keywords: List[str] = Field(default_factory=list, description="关键词")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "translate",
                    "description": "翻译文本",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string", "description": "待翻译文本"},
                            "target_lang": {"type": "string", "description": "目标语言"},
                        },
                        "required": ["text", "target_lang"],
                    },
                    "module_path": "tools.translate",
                    "function_name": "translate_text",
                    "return_mode": "direct",
                    "keywords": ["翻译", "语言"],
                }
            ]
        }
    }


# ============================================================
# 工具注册接口
# ============================================================


@router.post(
    "/register",
    response_model=ToolRegistrationResponse,
    summary="注册工具（完整定义）",
    description="注册一个新工具，需要提供完整的工具定义",
)
async def register_tool(request: ToolRegistration):
    """
    注册工具

    支持两种工具类型：
    - USER_DEFINED: 用户自定义工具
    - MCP: MCP 协议工具（需要先注册 MCP 服务器）
    """
    try:
        logger.info(f"📝 注册工具请求: name={request.definition.name}")

        response = tool_service.register_from_request(request)

        return response

    except ToolAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ToolRegistrationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 注册工具失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"注册失败: {str(e)}"
        )


@router.post(
    "/register/base-tool",
    response_model=ToolRegistrationResponse,
    summary="注册 BaseTool 类",
    description="注册一个 BaseTool 子类",
)
async def register_base_tool(request: BaseToolRegistrationRequest):
    """
    注册 BaseTool 子类

    示例：
    ```
    POST /api/v1/tools/register/base-tool
    {
        "module_path": "tools.exa_search",
        "class_name": "ExaSearchTool"
    }
    ```
    """
    try:
        logger.info(f"📝 注册 BaseTool: {request.module_path}.{request.class_name}")

        # 动态导入模块和类
        import importlib

        module = importlib.import_module(request.module_path)
        tool_class = getattr(module, request.class_name)

        # 验证是否是 BaseTool 子类
        if not issubclass(tool_class, BaseTool):
            raise ToolRegistrationError(f"{request.class_name} 不是 BaseTool 子类")

        # 创建实例
        tool_instance = tool_class()

        # 获取 schema
        schema: Dict[str, Any] = getattr(tool_instance, "parameters", {}) or {}

        # 转换为 ToolDefinition
        definition = ToolDefinition(
            name=tool_instance.name,
            description=tool_instance.description,
            tool_type=ToolType.USER_DEFINED,
            return_mode=ReturnMode.DIRECT,
            input_schema=ToolInputSchema(
                properties=schema.get("properties", {}), required=schema.get("required", [])
            ),
            implementation={"module": request.module_path, "class": request.class_name},
        )

        # 注册到服务
        response = tool_service.register_tool(
            definition=definition, replace_existing=request.replace_existing
        )

        return response

    except ToolAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except (ImportError, AttributeError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"无法加载工具类: {str(e)}"
        )
    except Exception as e:
        logger.error(f"❌ 注册 BaseTool 失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"注册失败: {str(e)}"
        )


@router.post(
    "/register/function",
    response_model=ToolRegistrationResponse,
    summary="注册函数工具",
    description="注册一个函数作为工具",
)
async def register_function_tool(request: FunctionToolRegistrationRequest):
    """
    注册函数作为工具

    注意：函数必须是异步函数（async def）
    """
    try:
        logger.info(f"📝 注册函数工具: {request.name}")

        # 动态导入函数
        import importlib

        module = importlib.import_module(request.module_path)
        func = getattr(module, request.function_name)

        # 注册到服务
        response = tool_service.register_function(
            name=request.name,
            description=request.description,
            func=func,
            input_schema=request.input_schema,
            return_mode=request.return_mode,
            keywords=request.keywords,
        )

        return response

    except ToolAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except (ImportError, AttributeError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"无法加载函数: {str(e)}"
        )
    except Exception as e:
        logger.error(f"❌ 注册函数工具失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"注册失败: {str(e)}"
        )


# ============================================================
# MCP 服务器注册接口
# ============================================================


@router.post(
    "/mcp/register",
    response_model=MCPServerRegistrationResponse,
    summary="注册全局 MCP 服务器模板",
    description="注册全局 MCP 服务器模板，存入数据库供 Agent 使用",
)
async def register_mcp_server(request: MCPServerRegistration):
    """
    注册全局 MCP 服务器模板

    将 MCP 服务器配置存入数据库，供运营人员在配置 Agent 时选择

    示例：
    ```
    POST /api/v1/tools/mcp/register
    {
        "server_url": "http://localhost:8080",
        "server_name": "notion",
        "auth_type": "bearer",
        "auth_config": {"token_env": "NOTION_API_KEY"},
        "description": "Notion 工作区管理"
    }
    ```
    """
    try:
        logger.info(f"🔌 注册全局 MCP 模板: {request.server_name} @ {request.server_url}")

        # 从 auth_config 中提取 auth_env
        auth_env = None
        if request.auth_config:
            auth_env = request.auth_config.get("token_env") or request.auth_config.get(
                "api_key_env"
            )

        # 存入数据库
        mcp_data = await mcp_service.register_global_mcp(
            server_name=request.server_name,
            server_url=request.server_url,
            auth_type=request.auth_type,
            auth_env=auth_env,
            description=getattr(request, "description", "") or "",
            metadata={
                "auth_config": request.auth_config,
                "tool_filter": request.tool_filter,
                "tool_prefix": request.tool_prefix,
                "auto_reconnect": request.auto_reconnect,
                "health_check_interval": request.health_check_interval,
            },
        )

        logger.info(f"✅ 全局 MCP 模板已存入数据库: {request.server_name}, id={mcp_data['id']}")

        return MCPServerRegistrationResponse(
            success=True,
            message=f"全局 MCP 模板 '{request.server_name}' 注册成功（已存入数据库）",
            server_name=request.server_name,
            registered_tools=[],  # 仅注册模板，不连接服务器
            failed_tools=[],
        )

    except MCPAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 注册 MCP 服务器失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"注册失败: {str(e)}"
        )


@router.delete(
    "/mcp/{server_name}",
    summary="删除全局 MCP 服务器模板",
    description="从数据库删除 MCP 服务器模板",
)
async def unregister_mcp_server(server_name: str):
    """删除全局 MCP 服务器模板"""
    try:
        logger.info(f"🗑️ 删除全局 MCP 模板: {server_name}")

        # 从数据库删除
        success = await mcp_service.delete_global_mcp(server_name)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"全局 MCP 模板不存在: {server_name}"
            )

        # 注意：MCP 连接由 MCPPool 管理，删除模板不影响运行时连接
        # 如需断开连接，可通过 MCPPool.cleanup() 或重启服务

        return JSONResponse(
            content={"success": True, "message": f"全局 MCP 模板 '{server_name}' 已删除"}
        )

    except MCPNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 删除 MCP 模板失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"删除失败: {str(e)}"
        )


@router.get(
    "/mcp", summary="列出全局 MCP 服务器模板", description="获取所有已注册的全局 MCP 服务器模板列表"
)
async def list_mcp_servers(
    include_inactive: bool = Query(False, description="是否包含未激活的服务器"),
):
    """
    列出所有全局 MCP 服务器模板

    从数据库查询已注册的 MCP 服务器配置
    """
    try:
        # 从数据库查询
        mcp_servers = await mcp_service.list_global_mcps(include_inactive=include_inactive)

        # TODO: MCP 池功能已移除，连接状态信息暂时不可用
        # 从 MCPPool 补充运行时连接状态
        # try:
        #     from infra.pools import get_mcp_pool
        #     mcp_pool = get_mcp_pool()
        #     pool_clients = mcp_pool.get_all_clients()
        #     for server in mcp_servers:
        #         server_url = server.get("server_url", "")
        #         if server_url in pool_clients:
        #             client = pool_clients[server_url]
        #             server["is_connected"] = getattr(client, "_connected", False)
        #             server["connected_tools_count"] = len(getattr(client, "_tools", {}))
        #         else:
        #             server["is_connected"] = False
        #             server["connected_tools_count"] = 0
        # except Exception:
        #     pass

        # 设置默认值
        for server in mcp_servers:
            server["is_connected"] = False
            server["connected_tools_count"] = 0

        return JSONResponse(
            content={
                "total": len(mcp_servers),
                "servers": mcp_servers,
            }
        )

    except Exception as e:
        logger.error(f"❌ 列出 MCP 服务器失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"查询失败: {str(e)}"
        )


@router.get(
    "/mcp/{server_name}",
    summary="获取全局 MCP 服务器详情",
    description="获取指定全局 MCP 服务器模板的详细信息",
)
async def get_mcp_server_detail(server_name: str):
    """
    获取全局 MCP 服务器模板详情

    从数据库查询 MCP 服务器配置和统计信息
    """
    try:
        # 从数据库获取
        mcp_data = await mcp_service.get_global_mcp(server_name)

        # TODO: MCP 池功能已移除，连接状态信息暂时不可用
        # 从 MCPPool 补充运行时连接状态
        # try:
        #     from infra.pools import get_mcp_pool
        #     mcp_pool = get_mcp_pool()
        #     server_url = mcp_data.get("server_url", "")
        #     pool_clients = mcp_pool.get_all_clients()
        #     if server_url in pool_clients:
        #         client = pool_clients[server_url]
        #         mcp_data["is_connected"] = getattr(client, "_connected", False)
        #         mcp_data["connected_tools"] = list(getattr(client, "_tools", {}).keys())
        #         mcp_data["connected_tools_count"] = len(getattr(client, "_tools", {}))
        #     else:
        #         mcp_data["is_connected"] = False
        #         mcp_data["connected_tools"] = []
        #         mcp_data["connected_tools_count"] = 0
        # except Exception:
        #     pass

        # 设置默认值
        mcp_data["is_connected"] = False
        mcp_data["connected_tools"] = []
        mcp_data["connected_tools_count"] = 0

        return JSONResponse(content=mcp_data)

    except MCPNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 获取 MCP 服务器详情失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"查询失败: {str(e)}"
        )


class MCPUpdateRequest(BaseModel):
    """MCP 服务器更新请求"""

    server_url: Optional[str] = Field(None, description="服务器 URL")
    auth_type: Optional[str] = Field(None, description="认证类型")
    auth_env: Optional[str] = Field(None, description="认证环境变量名")
    description: Optional[str] = Field(None, description="描述")
    is_active: Optional[bool] = Field(None, description="是否启用")
    capability: Optional[str] = Field(None, description="能力分类")


@router.put(
    "/mcp/{server_name}",
    summary="更新全局 MCP 服务器配置",
    description="更新数据库中的 MCP 服务器模板配置",
)
async def update_mcp_server(
    server_name: str,
    request: MCPUpdateRequest,
):
    """
    更新全局 MCP 服务器模板配置

    更新数据库中的 MCP 服务器配置
    """
    try:
        logger.info(f"📝 更新全局 MCP 模板: {server_name}")

        # 更新数据库
        mcp_data = await mcp_service.update_global_mcp(
            server_name=server_name,
            server_url=request.server_url,
            auth_type=request.auth_type,
            auth_env=request.auth_env,
            description=request.description,
            is_active=request.is_active,
            capability=request.capability,
        )

        return JSONResponse(
            content={
                "success": True,
                "server_name": server_name,
                "data": mcp_data,
                "message": f"全局 MCP 模板 '{server_name}' 更新成功",
            }
        )

    except MCPNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 更新 MCP 服务器配置失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"更新失败: {str(e)}"
        )


# ============================================================
# 工具查询接口
# ============================================================


@router.get(
    "",
    response_model=ToolListResponse,
    summary="列出工具",
    description="获取工具列表，支持过滤和分页",
)
async def list_tools(
    tool_type: Optional[ToolType] = Query(None, description="按类型过滤"),
    category: Optional[str] = Query(None, description="按分类过滤"),
    status: Optional[ToolStatus] = Query(None, description="按状态过滤"),
    keyword: Optional[str] = Query(None, description="关键词搜索"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
):
    """
    列出所有已注册的工具

    支持多种过滤条件和分页
    """
    try:
        query = ToolListQuery(
            tool_type=tool_type,
            category=category,
            status=status,
            keyword=keyword,
            page=page,
            page_size=page_size,
        )

        response = tool_service.list_tools(query)
        return response

    except Exception as e:
        logger.error(f"❌ 列出工具失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"查询失败: {str(e)}"
        )


@router.get(
    "/schemas",
    summary="获取 Claude API 格式的工具 Schema",
    description="获取可直接用于 Claude API 的工具定义列表",
)
async def get_tool_schemas(
    tool_names: Optional[str] = Query(None, description="指定工具名称（逗号分隔）")
):
    """
    获取 Claude API 格式的工具 Schema

    返回格式可直接用于 Claude API 的 tools 参数
    """
    try:
        names = tool_names.split(",") if tool_names else None

        schemas = tool_service.get_claude_tool_schemas(names)

        return JSONResponse(content={"tools": schemas, "total": len(schemas)})

    except Exception as e:
        logger.error(f"❌ 获取工具 Schema 失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"查询失败: {str(e)}"
        )


@router.get(
    "/{tool_name}",
    response_model=ToolDetailResponse,
    summary="获取工具详情",
    description="获取指定工具的详细信息和统计数据",
)
async def get_tool_detail(tool_name: str):
    """获取工具详情"""
    try:
        response = tool_service.get_tool_detail(tool_name)
        return response

    except ToolNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 获取工具详情失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"查询失败: {str(e)}"
        )


# ============================================================
# 工具执行接口
# ============================================================


@router.post("/execute", summary="执行工具", description="执行指定工具，支持直接返回和流式返回")
async def execute_tool(request: ToolExecuteRequest):
    """
    执行工具

    ## 返回模式
    - stream=False: 直接返回完整结果（JSON）
    - stream=True: 流式返回（Server-Sent Events）

    ## 流式返回格式
    ```
    data: {"chunk_type": "progress", "content": {"percent": 50}}
    data: {"chunk_type": "data", "content": {...}}
    data: {"chunk_type": "done", "content": {}}
    ```
    """
    try:
        logger.info(f"🔧 执行工具请求: tool={request.tool_name}, stream={request.stream}")

        # 生成调用 ID
        invocation_id = str(uuid4())

        # 创建调用对象
        invocation = ToolInvocation(
            invocation_id=invocation_id,
            tool_name=request.tool_name,
            input=request.input,
            session_id=request.session_id,
            user_id=request.user_id,
            timeout=request.timeout,
        )

        if request.stream:
            # 流式返回
            async def generate_stream():
                try:
                    async for chunk in tool_service.execute_tool_streaming(invocation):
                        yield f"data: {chunk.model_dump_json()}\n\n"
                except Exception as e:
                    error_chunk = ToolResultChunk(
                        invocation_id=invocation_id,
                        chunk_index=0,
                        chunk_type="error",
                        content=str(e),
                    )
                    yield f"data: {error_chunk.model_dump_json()}\n\n"

            return StreamingResponse(
                generate_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Invocation-Id": invocation_id,
                },
            )
        else:
            # 直接返回
            result = await tool_service.execute_tool(invocation)

            return JSONResponse(content=result.model_dump(mode="json"))

    except ToolNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ToolExecutionError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 执行工具失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"执行失败: {str(e)}"
        )


@router.post("/{tool_name}/invoke", summary="调用指定工具", description="简化的工具调用接口")
async def invoke_tool(
    tool_name: str,
    input_data: Dict[str, Any] = Body(..., description="输入参数"),
    stream: bool = Query(False, description="是否流式返回"),
    session_id: Optional[str] = Query(None, description="会话 ID"),
    user_id: Optional[str] = Query(None, description="用户 ID"),
):
    """
    简化的工具调用接口

    URL 中指定工具名，Body 中传递参数
    """
    request = ToolExecuteRequest(
        tool_name=tool_name, input=input_data, stream=stream, session_id=session_id, user_id=user_id
    )

    return await execute_tool(request)


# ============================================================
# 工具注销接口
# ============================================================


@router.delete("/{tool_name}", summary="注销工具", description="注销指定工具")
async def unregister_tool(tool_name: str):
    """注销工具"""
    try:
        logger.info(f"🗑️ 注销工具: {tool_name}")

        success = tool_service.unregister_tool(tool_name)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"工具不存在: {tool_name}"
            )

        return JSONResponse(content={"success": True, "message": f"工具 {tool_name} 已注销"})

    except Exception as e:
        logger.error(f"❌ 注销工具失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"注销失败: {str(e)}"
        )


# ============================================================
# 批量操作接口
# ============================================================


@router.post("/batch/register", summary="批量注册工具", description="从配置批量注册多个工具")
async def batch_register_tools(
    tools: List[ToolRegistration] = Body(..., description="工具注册列表")
):
    """
    批量注册工具

    返回每个工具的注册结果
    """
    try:
        results = []

        for tool_reg in tools:
            try:
                response = tool_service.register_from_request(tool_reg)
                results.append(
                    {"name": tool_reg.definition.name, "success": True, "message": response.message}
                )
            except Exception as e:
                results.append(
                    {"name": tool_reg.definition.name, "success": False, "error": str(e)}
                )

        succeeded = sum(1 for r in results if r["success"])
        failed = len(results) - succeeded

        return JSONResponse(
            content={
                "total": len(results),
                "succeeded": succeeded,
                "failed": failed,
                "results": results,
            }
        )

    except Exception as e:
        logger.error(f"❌ 批量注册失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"批量注册失败: {str(e)}"
        )


@router.post(
    "/batch/register/base-tools",
    summary="批量注册 BaseTool 类",
    description="批量注册多个 BaseTool 子类",
)
async def batch_register_base_tools(
    tools: List[BaseToolRegistrationRequest] = Body(..., description="工具列表")
):
    """
    批量注册 BaseTool 类

    用于快速注册多个现有工具
    """
    try:
        results = []

        for tool_req in tools:
            try:
                # 调用单个注册接口的逻辑
                import importlib

                module = importlib.import_module(tool_req.module_path)
                tool_class = getattr(module, tool_req.class_name)

                if not issubclass(tool_class, BaseTool):
                    raise ToolRegistrationError(f"{tool_req.class_name} 不是 BaseTool 子类")

                tool_instance = tool_class()

                # 获取 schema
                schema: Dict[str, Any] = {}
                if hasattr(tool_instance, "parameters"):
                    schema = getattr(tool_instance, "parameters") or {}

                definition = ToolDefinition(
                    name=tool_instance.name,
                    description=tool_instance.description,
                    tool_type=ToolType.USER_DEFINED,
                    return_mode=ReturnMode.DIRECT,
                    input_schema=ToolInputSchema(
                        properties=schema.get("properties", {}), required=schema.get("required", [])
                    ),
                    implementation={"module": tool_req.module_path, "class": tool_req.class_name},
                )

                tool_service.register_tool(
                    definition=definition, replace_existing=tool_req.replace_existing
                )

                results.append(
                    {
                        "name": tool_instance.name,
                        "success": True,
                        "message": f"工具 {tool_instance.name} 注册成功",
                    }
                )

            except Exception as e:
                results.append(
                    {
                        "name": f"{tool_req.module_path}.{tool_req.class_name}",
                        "success": False,
                        "error": str(e),
                    }
                )

        succeeded = sum(1 for r in results if r["success"])
        failed = len(results) - succeeded

        return JSONResponse(
            content={
                "total": len(results),
                "succeeded": succeeded,
                "failed": failed,
                "results": results,
            }
        )

    except Exception as e:
        logger.error(f"❌ 批量注册 BaseTool 失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"批量注册失败: {str(e)}"
        )


# ============================================================
# 健康检查接口
# ============================================================


@router.get("/health", summary="工具服务健康检查", description="检查工具服务状态")
async def health_check():
    """工具服务健康检查"""
    try:
        tools = tool_service.list_tools()

        # TODO: MCP 池功能已移除，连接数暂时不可用
        # 从 MCPPool 获取连接数
        # try:
        #     from infra.pools import get_mcp_pool
        #     mcp_pool = get_mcp_pool()
        #     mcp_clients = len(mcp_pool.get_all_clients())
        # except Exception:
        #     mcp_clients = 0

        mcp_clients = 0

        return JSONResponse(
            content={
                "status": "healthy",
                "tools_count": tools.total,
                "mcp_servers_count": mcp_clients,
                "timestamp": datetime.now().isoformat(),
            }
        )

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            },
        )
