"""
Zenflux Agent - FastAPI 服务
基于 Claude 的智能体 Web API
"""

# ==================== 标准库 ====================
import os
from contextlib import asynccontextmanager
from datetime import datetime
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
    chat_router,
    files_router,
    knowledge_router,
    mem0_router,
    tasks_router,
    tools_router,
)
from routers.agents import router as agents_router
from routers.auth import router as auth_router
from routers.conversation import router as conversation_router
from routers.health import router as health_router
from routers.human_confirmation import router as human_confirmation_router
from routers.skills import router as skills_router
from routers.workspace import router as workspace_router
from infra.pools import get_session_pool, get_agent_pool
# ==================== 常量定义 ====================

APP_NAME = "Zenflux Agent API"
APP_VERSION = "3.6.0"
APP_DESCRIPTION = "基于 Claude Sonnet 4.5 的智能体框架"


# ==================== 启动辅助函数 ====================

async def _init_resilience_config() -> None:
    """加载容错配置"""
    print("🛡️ 加载容错配置...")
    try:
        from infra.resilience.config import apply_resilience_config
        apply_resilience_config()
        print("✅ 容错配置已加载")
    except Exception as e:
        print(f"⚠️ 容错配置加载失败: {e}")


async def _init_database() -> None:
    """初始化数据库"""
    print("💾 初始化数据库...")
    from infra.database import init_database
    await init_database()
    print("✅ 数据库初始化完成")


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
    import asyncio
    
    enable_grpc = os.getenv("ENABLE_GRPC", "false").lower() == "true"
    if not enable_grpc:
        return None
    
    try:
        print("📡 启动 gRPC 服务器...")
        from grpc_server.server import GRPCServer
        
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
            jobs = scheduler.get_jobs()
            print(f"✅ 定时任务调度器已启动，共 {len(jobs)} 个任务")
        else:
            print("○ 没有配置定时任务，调度器未启动")
        return scheduler
    
    except Exception as e:
        print(f"⚠️ 定时任务调度器启动失败: {e}")
    
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


async def _stop_grpc_server(grpc_server: Optional[Any]) -> None:
    """关闭 gRPC 服务器"""
    if grpc_server:
        try:
            await grpc_server.stop(grace_period=5)
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


async def _init_pools() -> None:
    """
    初始化资源池和协调器
    
    初始化顺序：
    1. AgentRegistry 加载配置（已在 _preload_agent_registry 中完成）
    2. AgentPool 创建原型（基于 Registry 配置）
    3. SessionPool 初始化（追踪活跃 Session）
    4. 校准活跃 Session 数据（清理可能的孤立记录）
    """
    try:
        print("🏊 初始化资源池...")
        
        # 1. 获取 AgentPool 并预加载原型
        agent_pool = get_agent_pool()
        loaded_count = await agent_pool.preload_all()
        print(f"   ✓ AgentPool: {loaded_count} 个原型已缓存")
        
        # 2. 获取 SessionPool
        session_pool = get_session_pool()
        
        # 3. 校准活跃 Session 数据（清理服务重启前的孤立记录）
        calibration_result = await session_pool.calibrate()
        if calibration_result.get("orphaned_removed", 0) > 0:
            print(f"   ✓ SessionPool: 校准完成，清理 {calibration_result['orphaned_removed']} 个孤立 Session")
        else:
            print(f"   ✓ SessionPool: 已就绪")
        
        print(f"✅ 资源池初始化完成")
    except Exception as e:
        print(f"⚠️ 资源池初始化失败: {e}")


async def _cleanup_pools() -> None:
    """清理资源池"""
    try:
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
    
    await _init_resilience_config()
    await _init_database()
    await _preload_agent_registry()  # 加载 Agent 配置
    await _init_pools()  # 初始化资源池（含 Agent 原型创建和 Session 校准）
    grpc_server = await _start_grpc_server()
    scheduler = await _start_scheduler()
    
    yield
    
    # ===== 关闭阶段 =====
    print("🛑 正在关闭服务...")
    
    await _cleanup_pools()  # 清理资源池
    await _cleanup_agent_registry()
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
            "skills": "/api/v1/skills"
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


@app.get("/health")
async def health() -> Dict[str, Any]:
    """
    健康检查
    
    返回服务健康状态
    """
    session_pool = get_session_pool()
    stats = await session_pool.get_system_stats()
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "pools": {
            "agent_prototypes": stats.get("agents", {}).get("total_prototypes", 0),
            "active_sessions": stats.get("sessions", {}).get("active", 0),
        }
    }


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
