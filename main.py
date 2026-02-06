"""
Zenflux Agent - FastAPI 服务
基于 Claude 的智能体 Web API
Build: 2026-01-16 v2
"""

# ==================== 标准库 ====================
import os
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

# ==================== 第三方库 ====================
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 加载项目根目录的 .env 文件（必须在导入本地模块之前）
_env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=_env_path, override=True)

# ==================== 本地模块 ====================
from routers import (
    agents_router,
    auth_router,
    chat_router,
    conversation_router,
    docs_router,
    files_router,
    health_router,
    human_confirmation_router,
    knowledge_router,
    mem0_router,
    realtime_router,
    skills_router,
    tasks_router,
    tools_router,
    workspace_router,
    models_router,
)
from grpc_server.server import GRPCServer
from infra.pools import get_session_pool, get_agent_pool, get_mcp_pool
from infra.database import init_database
from infra.resilience.config import apply_resilience_config
from core.tool.registry import get_capability_registry
from utils import get_s3_uploader

# ==================== 常量定义 ====================

APP_NAME = "Zenflux Agent API"
APP_VERSION = "0.7.5"
APP_DESCRIPTION = "基于 Claude Sonnet 4.5 的智能体框架"


# ==================== 异步异常处理 ====================

def _setup_asyncio_exception_handler() -> None:
    """
    设置自定义的 asyncio 异常处理器
    
    用于抑制 MCP SDK 的 streamable_http_client 在关闭时产生的
    "Attempted to exit cancel scope in a different task" 错误。
    
    这是 anyio 和 MCP SDK 的已知问题，在应用关闭后清理异步生成器时会触发，
    但不影响应用的正常运行。
    """
    loop = asyncio.get_event_loop()
    original_handler = loop.get_exception_handler()
    
    def custom_exception_handler(loop, context):
        exception = context.get("exception")
        message = context.get("message", "")
        
        # 检查是否是 MCP streamable_http_client 关闭时的已知错误
        if exception and isinstance(exception, RuntimeError):
            error_msg = str(exception)
            if "Attempted to exit cancel scope in a different task" in error_msg:
                # 忽略这个特定错误，它发生在应用关闭后，不影响正常运行
                return
        
        # 检查是否是异步生成器关闭时的错误（包含 streamable_http_client）
        if "streamable_http_client" in message:
            return
        
        # 对于其他错误，使用原始处理器或默认处理
        if original_handler:
            original_handler(loop, context)
        else:
            loop.default_exception_handler(context)
    
    loop.set_exception_handler(custom_exception_handler)


# ==================== 启动辅助函数 ====================

async def _init_s3_uploader() -> None:
    """初始化 S3 上传器"""
    print("☁️ 初始化 S3 上传器...")
    try:
        s3_uploader = get_s3_uploader()
        await s3_uploader.initialize()
        print("✅ S3 上传器初始化完成")
    except Exception as e:
        print(f"⚠️ S3 上传器初始化失败（文件上传功能可能不可用）: {e}")


async def _init_resilience_config() -> None:
    """加载容错配置"""
    print("🛡️ 加载容错配置...")
    try:
        await apply_resilience_config()
        print("✅ 容错配置已加载")
    except Exception as e:
        print(f"⚠️ 容错配置加载失败: {e}")


async def _init_database() -> None:
    """初始化数据库"""
    print("💾 初始化数据库...")
    await init_database()
    print("✅ 数据库初始化完成")


async def _preload_capability_registry() -> None:
    """
    预加载 CapabilityRegistry（工具注册表）
    
    必须在 Agent 加载之前完成，确保 capabilities.yaml 中的工具被正确加载
    """
    print("📋 加载工具注册表...")
    registry = get_capability_registry()
    await registry.initialize()
    print(f"✅ 已加载 {len(registry.capabilities)} 个工具能力")


async def _preload_agent_registry() -> int:
    """
    预加载 Agent 配置到 AgentRegistry
    
    注意：只加载配置，不创建原型实例（由 AgentPool 负责）
    
    Returns:
        加载的 Agent 配置数量
    """
    print("📋 加载 Agent 配置...")
    from services.agent_registry import get_agent_registry
    
    agent_registry = get_agent_registry()
    try:
        loaded_count = await agent_registry.preload_all()
        if loaded_count > 0:
            print(f"✅ 已加载 {loaded_count} 个 Agent 配置")
            for agent in agent_registry.list_agents():
                print(f"   • {agent['agent_id']}: {agent['description'] or '(无描述)'}")
        else:
            print("○ 没有发现 Agent 配置（instances/ 目录为空）")
        return loaded_count
    except Exception as e:
        print(f"⚠️ Agent 配置加载失败: {e}")
        return 0


async def _start_grpc_server() -> Optional[Any]:
    """启动 gRPC 服务器"""
    enable_grpc = os.getenv("ENABLE_GRPC", "false").lower() == "true"
    if not enable_grpc:
        return None
    
    try:
        print("📡 启动 gRPC 服务器...")        
        grpc_host = os.getenv("GRPC_HOST", "0.0.0.0")
        grpc_port = int(os.getenv("GRPC_PORT", "50051"))
        grpc_workers_env = os.getenv("GRPC_MAX_WORKERS", "0")
        grpc_workers = int(grpc_workers_env) if grpc_workers_env else None
        if grpc_workers == 0:
            grpc_workers = None
        
        grpc_server = GRPCServer(grpc_host, grpc_port, grpc_workers)
        asyncio.create_task(grpc_server.start())
        
        print(f"✅ gRPC 服务器已启动: {grpc_host}:{grpc_port}")
        print(f"📡 内部服务可通过 gRPC 调用: ChatService, SessionService")
        return grpc_server
    
    except ImportError:
        print("⚠️ gRPC 依赖未安装或代码未生成，跳过 gRPC 服务器启动")
        print("   安装: pip install grpcio grpcio-tools")
        print("   生成代码: bash scripts/generate_grpc.sh")
    except Exception as e:
        print(f"⚠️ gRPC 服务器启动失败: {e}")
    
    return None


async def _start_scheduler() -> Optional[Any]:
    """启动定时任务调度器"""
    enable_scheduler = os.getenv("ENABLE_SCHEDULER", "true").lower() == "true"
    if not enable_scheduler:
        return None
    
    try:
        print("📅 启动定时任务调度器...")
        from utils.background_tasks import get_scheduler
        
        scheduler = get_scheduler()
        await scheduler.start()
        
        if scheduler.is_running():
            print("✅ 定时任务调度器已启动")
        else:
            print("○ 没有配置定时任务，调度器未启动")
        return scheduler   
    
    except Exception as e:
        print(f"⚠️ 定时任务调度器启动失败: {e}")
    
    return None


async def _init_chat_service() -> None:
    """
    预初始化 ChatService（避免首次请求冷启动）
    
    预热关键组件：
    - ChatService 单例
    - Intent LLM 连接（路由 + 开场白共用，带主备切换）
    - 文件处理器
    - Agent 注册表
    """
    print("💬 预热 ChatService...")
    try:
        from services.chat_service import get_chat_service
        from core.llm.router import ModelRouter
        
        service = get_chat_service()
        
        # 预热 Intent LLM（路由 + 开场白共用，避免首次请求延迟）
        intent_llm = await service.get_intent_llm()
        is_router = isinstance(intent_llm, ModelRouter)
        
        _ = service.file_processor
        _ = service.agent_registry
        
        print(f"✅ ChatService 预热完成 (intent_llm_router: {is_router})")
    except Exception as e:
        print(f"⚠️ ChatService 预热失败: {e}")


async def _start_health_probe_service() -> Optional[Any]:
    """
    启动健康探测服务（🆕 V7.10）
    
    后台异步探测所有 LLM 模型健康状态，与用户请求完全解耦
    """
    try:
        print("🩺 启动健康探测服务...")
        from services.health_probe_service import start_health_probe_service
        
        service = await start_health_probe_service()
        
        if service._running:
            print(f"✅ 健康探测服务已启动: "
                  f"interval={service.interval}s, profiles={service.profiles}")
        else:
            print("○ 健康探测服务已禁用 (LLM_HEALTH_PROBE_ENABLED=false)")
        
        return service
    
    except Exception as e:
        print(f"⚠️ 健康探测服务启动失败: {e}")
        return None


# ==================== 关闭辅助函数 ====================

async def _cleanup_agent_registry() -> None:
    """清理 Agent Registry"""
    try:
        from services.agent_registry import get_agent_registry
        agent_registry = get_agent_registry()
        await agent_registry.cleanup()
        print("✅ Agent Registry 已清理")
    except Exception as e:
        print(f"⚠️ 清理 Agent Registry 失败: {e}")


async def _stop_scheduler(scheduler: Optional[Any]) -> None:
    """关闭定时任务调度器"""
    if scheduler and scheduler.is_running():
        try:
            await scheduler.shutdown()
            print("✅ 定时任务调度器已关闭")
        except Exception as e:
            print(f"⚠️ 关闭定时任务调度器失败: {e}")


async def _stop_health_probe_service(service: Optional[Any]) -> None:
    """
    停止健康探测服务（🆕 V7.10）
    """
    if service:
        try:
            from services.health_probe_service import stop_health_probe_service
            await stop_health_probe_service()
            print("✅ 健康探测服务已关闭")
        except Exception as e:
            print(f"⚠️ 关闭健康探测服务失败: {e}")


async def _stop_grpc_server(grpc_server: Optional[Any]) -> None:
    """关闭 gRPC 服务器"""
    if grpc_server:
        try:
            # 🆕 使用 gRPC 服务器实例配置的 grace_period（默认 30 秒）
            await grpc_server.stop()
            print("✅ gRPC 服务器已关闭")
        except Exception as e:
            print(f"⚠️ 关闭 gRPC 服务器失败: {e}")


async def _close_redis() -> None:
    """关闭 Redis 连接"""
    try:
        from services.redis_manager import get_redis_manager
        redis_manager = get_redis_manager()
        await redis_manager.close()
        print("✅ Redis 连接已关闭")
    except Exception as e:
        print(f"⚠️ 关闭 Redis 连接失败: {e}")


async def _mcp_preconnect_background(mcp_pool) -> None:
    """
    后台 MCP 预连接任务
    
    在独立的 asyncio Task 中执行预连接，避免 anyio cancel scope 污染事件循环。
    预连接失败不会影响应用启动，工具仍可在首次调用时按需连接。
    """
    try:
        results = await mcp_pool.preconnect_all()
        connected = sum(1 for v in results.values() if v)
        total = len(results)
        if total > 0:
            print(f"   ✓ MCP 后台预连接完成: {connected}/{total} 个服务器")
    except Exception as e:
        print(f"   ⚠️ MCP 后台预连接失败（工具将按需连接）: {e}")


async def _init_pools() -> None:
    """
    初始化资源池和协调器
    
    初始化顺序：
    1. AgentRegistry 加载配置（已在 _preload_agent_registry 中完成）
    2. MCPPool 初始化（后台预连接所有 MCP 服务器）
    3. AgentPool 创建原型（使用 MCPPool 中的连接）
    4. SessionPool 初始化（追踪活跃 Session）
    5. 校准活跃 Session 数据（清理可能的孤立记录）
    6. 启动 MCP 健康检查
    """
    try:
        print("🏊 初始化资源池...")
        
        # 1. 获取 MCPPool
        mcp_pool = get_mcp_pool()
        
        # 2. 获取 AgentPool 并预加载原型
        # 🔧 将预加载放在独立 task 中，隔离 MCP 的 anyio cancel scope
        # 避免 MCP 连接失败时的 cancel scope 污染后续的 Redis 操作
        agent_pool = get_agent_pool()
        
        async def _isolated_preload():
            """隔离 MCP cancel scope 的预加载包装"""
            try:
                return await agent_pool.preload_all()
            except asyncio.CancelledError:
                print("   ⚠️ AgentPool 预加载被取消")
                return 0
            except Exception as e:
                print(f"   ⚠️ AgentPool 预加载出错: {e}")
                return 0
        
        # 在独立 task 中运行，确保 cancel scope 不泄漏到主流程
        preload_task = asyncio.create_task(_isolated_preload())
        loaded_count = await preload_task
        
        # 短暂等待让事件循环处理任何残留的 cancel scope
        await asyncio.sleep(0.01)
        
        print(f"   ✓ AgentPool: {loaded_count} 个原型已缓存")
        
        # 3. 获取 SessionPool
        session_pool = get_session_pool()
        
        # 4. 校准活跃 Session 数据（清理服务重启前的孤立记录）
        # 使用深度校准，同时清理用户级别的孤立 Session
        calibration_result = await session_pool.calibrate(deep=True)
        orphaned = calibration_result.get("orphaned_removed", 0)
        user_cleaned = calibration_result.get("user_sessions_cleaned", 0)
        if orphaned > 0 or user_cleaned > 0:
            print(f"   ✓ SessionPool: 校准完成，清理 {orphaned} 个孤立 Session，{user_cleaned} 个用户级孤立记录")
        else:
            print(f"   ✓ SessionPool: 已就绪")
        
        # 5. 启动 MCP 后台预连接任务（不阻塞主启动流程）
        # 使用 asyncio.create_task 在独立任务中执行，避免 anyio cancel scope 问题
        enable_mcp_preconnect = os.getenv("MCP_ENABLE_PRECONNECT", "true").lower() == "true"
        if enable_mcp_preconnect:
            print(f"   ✓ MCPPool: 启动后台预连接...")
            asyncio.create_task(_mcp_preconnect_background(mcp_pool))
        else:
            print(f"   ✓ MCPPool: 已就绪（按需连接模式）")
        
        # 6. 启动 MCP 健康检查
        try:
            mcp_pool.start_health_check()
            print(f"   ✓ MCP 健康检查: 已启动")
        except Exception:
            print(f"   ⚠️ MCP 健康检查启动跳过")
        
        print(f"✅ 资源池初始化完成")
    except Exception as e:
        print(f"⚠️ 资源池初始化失败: {e}")


async def _cleanup_pools() -> None:
    """清理资源池"""
    try:
        # 1. 清理 MCPPool（停止健康检查，断开连接）
        mcp_pool = get_mcp_pool()
        await mcp_pool.cleanup()
        
        # 2. 清理 SessionPool
        session_pool = get_session_pool()
        await session_pool.cleanup()
        
        print("✅ 资源池已清理")
    except Exception as e:
        print(f"⚠️ 清理资源池失败: {e}")


async def _close_database() -> None:
    """关闭数据库连接池"""
    try:
        from infra.database import engine
        await engine.dispose()
        print("✅ 数据库连接已关闭")
    except Exception as e:
        print(f"⚠️ 关闭数据库连接失败: {e}")


# ==================== 生命周期管理 ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # ===== 启动阶段 =====
    print("🚀 Zenflux Agent API 启动中...")
    
    # 设置自定义异常处理器（抑制 MCP 关闭时的已知错误）
    _setup_asyncio_exception_handler()
    
    await _init_resilience_config()
    await _init_database()
    await _init_s3_uploader()
    await _preload_capability_registry()  # 🆕 加载工具注册表（必须在 Agent 之前）
    await _preload_agent_registry()  # 加载 Agent 配置
    await _init_pools()  # 初始化资源池（含 Agent 原型创建和 Session 校准）
    await _init_chat_service()  # 预热 ChatService（避免首次请求冷启动）
    grpc_server = await _start_grpc_server()
    scheduler = await _start_scheduler()
    health_probe_service = await _start_health_probe_service()  # 🆕 V7.10: 启动健康探测
    
    yield
    
    # ===== 关闭阶段 =====
    print("🛑 正在关闭服务...")
    
    await _cleanup_pools()  # 清理资源池
    await _cleanup_agent_registry()
    await _stop_health_probe_service(health_probe_service)  # 🆕 V7.10: 停止健康探测
    await _stop_scheduler(scheduler)
    await _stop_grpc_server(grpc_server)
    await _close_redis()
    await _close_database()
    
    print("👋 Zenflux Agent API 已关闭")


# ==================== FastAPI 应用 ====================

app = FastAPI(
    title=APP_NAME,
    description=APP_DESCRIPTION,
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)


# ==================== 中间件配置 ====================

# CORS 配置：从环境变量读取允许的域名
_allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "*")
_allowed_origins = (
    ["*"] if _allowed_origins_env == "*"
    else [origin.strip() for origin in _allowed_origins_env.split(",") if origin.strip()]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== 路由注册 ====================

# 认证相关
app.include_router(auth_router)
app.include_router(health_router)

# 核心功能
app.include_router(chat_router)
app.include_router(conversation_router)
app.include_router(human_confirmation_router)

# 资源管理
app.include_router(knowledge_router)
app.include_router(files_router)
app.include_router(workspace_router)
app.include_router(tools_router)

# 扩展功能
app.include_router(mem0_router)
app.include_router(tasks_router)
app.include_router(agents_router)
app.include_router(skills_router)
app.include_router(docs_router)
app.include_router(models_router)

# 实时通信（WebSocket）
app.include_router(realtime_router)


# ==================== 基础路由 ====================

@app.get("/")
async def root() -> Dict[str, Any]:
    """
    根路径 - API 信息
    
    返回 API 基本信息和可用端点
    """
    enable_grpc = os.getenv("ENABLE_GRPC", "false").lower() == "true"
    grpc_port = os.getenv("GRPC_PORT", "50051")
    
    response: Dict[str, Any] = {
        "name": APP_NAME,
        "version": APP_VERSION,
        "status": "running",
        "description": APP_DESCRIPTION,
        "protocols": {
            "http": {
                "enabled": True,
                "docs": "/docs",
                "redoc": "/redoc"
            }
        },
        "endpoints": {
            "health": "/health",
            "chat": "/api/v1/chat",
            "stream": "/api/v1/chat/stream",
            "session": "/api/v1/session/{session_id}",
            "sessions": "/api/v1/sessions",
            "human_confirmation": "/api/v1/human-confirmation/{request_id}",
            "agents": "/api/v1/agents",
            "skills": "/api/v1/skills",
            "models": "/api/v1/models",
            "realtime_ws": "ws://host/api/v1/realtime/ws",
            "realtime_sessions": "/api/v1/realtime/sessions"
        },
        "github": "https://github.com/your-repo/zenflux-agent"
    }
    
    # gRPC 信息（如果启用）
    if enable_grpc:
        response["protocols"]["grpc"] = {
            "enabled": True,
            "port": int(grpc_port),
            "services": ["ChatService", "SessionService", "ToolService", "AgentService"],
            "client_example": (
                f"from services.grpc.client import ZenfluxGRPCClient\n"
                f"client = ZenfluxGRPCClient('localhost:{grpc_port}')"
            )
        }
    
    return response


# ==================== 启动入口 ====================

if __name__ == "__main__":
    import uvicorn
    
    print("\n" + "=" * 60)
    print(f"🚀 启动 {APP_NAME}")
    print("=" * 60)
    print("📍 访问地址: http://localhost:8000")
    print("📚 API 文档: http://localhost:8000/docs")
    print("📖 ReDoc: http://localhost:8000/redoc")
    print("=" * 60 + "\n")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
