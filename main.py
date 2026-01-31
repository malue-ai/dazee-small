"""
Zenflux Agent - FastAPI 服务
基于 Claude 的智能体 Web API

🆕 V9.5 单实例部署模式：
    每个 Agent 实例是独立的部署单元，启动时只加载指定实例。
    
    使用方式：
        # 命令行参数
        python main.py --instance=dazee_ppt
        
        # 环境变量
        AGENT_INSTANCE=dazee_ppt python main.py
        
        # Docker
        docker run -e AGENT_INSTANCE=dazee_ppt zenflux-agent
        
    不指定实例时，使用批量加载模式（开发/测试用）
"""

import argparse
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import datetime

# 自动加载 .env 文件
from dotenv import load_dotenv

# 加载项目根目录的 .env 文件
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

# 解析命令行参数（在模块级别解析，以便 lifespan 使用）
def _parse_args():
    parser = argparse.ArgumentParser(description="Zenflux Agent API")
    parser.add_argument(
        "--instance", "-i",
        type=str,
        default=None,
        help="指定要加载的 Agent 实例名称（单实例部署模式）"
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=8000,
        help="API 服务端口（默认 8000）"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="API 服务地址（默认 0.0.0.0）"
    )
    # 使用 parse_known_args 避免与 uvicorn 的参数冲突
    args, _ = parser.parse_known_args()
    return args

_cli_args = _parse_args()

from routers import chat_router, knowledge_router, files_router, tools_router, mem0_router, tasks_router
from routers.human_confirmation import router as human_confirmation_router
from routers.conversation import router as conversation_router
from routers.workspace import router as workspace_router
from routers.agents import router as agents_router
from routers.skills import router as skills_router
from routers.auth import router as auth_router
from routers.health import router as health_router


# ============================================================
# 生命周期管理
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    import os
    import asyncio
    
    # 启动时
    print("🚀 Zenflux Agent API 启动中...")
    
    # 🆕 加载容错配置
    print("🛡️ 加载容错配置...")
    try:
        from infra.resilience.config import apply_resilience_config
        apply_resilience_config()
        print("✅ 容错配置已加载")
    except Exception as e:
        print(f"⚠️ 容错配置加载失败: {e}")
    
    # 初始化数据库
    print("💾 初始化数据库...")
    from infra.database import init_database, engine
    await init_database()
    print("✅ 数据库初始化完成")
    
    # 🆕 V9.5: 按需加载模式
    # 可选：启动时预加载指定实例（--instance 或 AGENT_INSTANCE）
    # 如果不指定，则在首次请求时按需加载
    from services.agent_registry import get_agent_registry
    from scripts.instance_loader import list_instances
    
    agent_registry = get_agent_registry()
    instance_name = _cli_args.instance or os.getenv("AGENT_INSTANCE")
    
    if instance_name:
        # 启动时预加载指定实例（推荐：更快的首次响应）
        print(f"🎯 预加载 Agent 实例: '{instance_name}'...")
        try:
            success = await agent_registry.preload_instance(instance_name)
            if success:
                agent_info = agent_registry.list_agents()[0]
                print(f"✅ Agent 加载成功: {instance_name}")
                print(f"   描述: {agent_info.get('description') or '(无描述)'}")
            else:
                print(f"⚠️ Agent '{instance_name}' 加载失败，将在首次请求时重试")
        except FileNotFoundError as e:
            print(f"❌ 实例不存在: {e}")
            raise SystemExit(1)
        except Exception as e:
            print(f"⚠️ Agent '{instance_name}' 预加载失败: {e}")
            print("   将在首次请求时重试加载")
    else:
        # 按需加载模式
        available = list_instances()
        print("📦 按需加载模式: Agent 将在首次请求时加载")
        if available:
            print(f"   可用实例: {', '.join(available)}")
        else:
            print("   ⚠️ instances/ 目录下没有发现任何实例")
    
    # 启动 gRPC 服务器（如果启用）
    grpc_server = None
    enable_grpc = os.getenv("ENABLE_GRPC", "false").lower() == "true"
    
    if enable_grpc:
        try:
            print("📡 启动 gRPC 服务器...")
            from grpc_server.server import GRPCServer
            
            grpc_host = os.getenv("GRPC_HOST", "0.0.0.0")
            grpc_port = int(os.getenv("GRPC_PORT", "50051"))
            # 0 或空值表示自动（CPU 核心数 * 5）
            grpc_workers_env = os.getenv("GRPC_MAX_WORKERS", "0")
            grpc_workers = int(grpc_workers_env) if grpc_workers_env else None
            if grpc_workers == 0:
                grpc_workers = None  # None 表示自动
            
            grpc_server = GRPCServer(grpc_host, grpc_port, grpc_workers)
            
            # 在后台启动 gRPC 服务器
            asyncio.create_task(grpc_server.start())
            
            print(f"✅ gRPC 服务器已启动: {grpc_host}:{grpc_port}")
            print(f"📡 内部服务可通过 gRPC 调用: ChatService, SessionService")
        
        except ImportError:
            print("⚠️ gRPC 依赖未安装或代码未生成，跳过 gRPC 服务器启动")
            print("   安装: pip install grpcio grpcio-tools")
            print("   生成代码: bash scripts/generate_grpc.sh")
        except Exception as e:
            print(f"⚠️ gRPC 服务器启动失败: {e}")
    
    # 启动定时任务调度器（如果配置了定时任务）
    task_scheduler = None
    enable_scheduler = os.getenv("ENABLE_SCHEDULER", "true").lower() == "true"
    
    if enable_scheduler:
        try:
            print("📅 启动定时任务调度器...")
            from utils.background_tasks import get_scheduler
            
            task_scheduler = get_scheduler()
            await task_scheduler.start()
            
            if task_scheduler.is_running():
                jobs = task_scheduler.get_jobs()
                print(f"✅ 定时任务调度器已启动，共 {len(jobs)} 个任务")
            else:
                print("○ 没有配置定时任务，调度器未启动")
        except Exception as e:
            print(f"⚠️ 定时任务调度器启动失败: {e}")
    
    # 🆕 V7.10: 启动后台健康探测服务
    health_probe_service = None
    enable_health_probe = os.getenv("LLM_HEALTH_PROBE_ENABLED", "true").lower() in ("true", "1", "yes")
    
    if enable_health_probe:
        try:
            print("🩺 启动后台健康探测服务...")
            from services.health_probe_service import start_health_probe_service
            
            health_probe_service = await start_health_probe_service()
            print("✅ 后台健康探测服务已启动")
        except Exception as e:
            print(f"⚠️ 后台健康探测服务启动失败: {e}")
    
    yield
    
    # 关闭时 - 清理所有资源
    print("🛑 正在关闭服务...")
    
    # 0. 清理 Agent Registry
    try:
        await agent_registry.cleanup()
        print("✅ Agent Registry 已清理")
    except Exception as e:
        print(f"⚠️ 清理 Agent Registry 失败: {e}")
    
    # 0.1 关闭定时任务调度器
    if task_scheduler and task_scheduler.is_running():
        try:
            await task_scheduler.shutdown()
            print("✅ 定时任务调度器已关闭")
        except Exception as e:
            print(f"⚠️ 关闭定时任务调度器失败: {e}")
    
    # 0.2 🆕 V7.10: 关闭后台健康探测服务
    if health_probe_service:
        try:
            from services.health_probe_service import stop_health_probe_service
            await stop_health_probe_service()
            print("✅ 后台健康探测服务已关闭")
        except Exception as e:
            print(f"⚠️ 关闭后台健康探测服务失败: {e}")
    
    # 1. 关闭 gRPC 服务器
    if grpc_server:
        try:
            await grpc_server.stop(grace_period=5)
            print("✅ gRPC 服务器已关闭")
        except Exception as e:
            print(f"⚠️ 关闭 gRPC 服务器失败: {e}")
    
    # 1. 关闭 Redis 连接
    try:
        from services.redis_manager import get_redis_manager
        redis_manager = get_redis_manager()
        await redis_manager.close()
        print("✅ Redis 连接已关闭")
    except Exception as e:
        print(f"⚠️ 关闭 Redis 连接失败: {e}")
    
    # 2. 清理 Agent Pool（取消所有运行中的任务）
    try:
        from services import get_session_service
        session_service = get_session_service()
        
        # 取消所有 Agent 任务
        for session_id, agent in list(session_service.agent_pool.items()):
            try:
                if hasattr(agent, 'cancel'):
                    agent.cancel()
            except Exception:
                pass
        session_service.agent_pool.clear()
        print("✅ Agent Pool 已清理")
    except Exception as e:
        print(f"⚠️ 清理 Agent Pool 失败: {e}")
    
    # 3. 关闭数据库连接池
    try:
        await engine.dispose()
        print("✅ 数据库连接已关闭")
    except Exception as e:
        print(f"⚠️ 关闭数据库连接失败: {e}")
    
    print("👋 Zenflux Agent API 已关闭")


# ============================================================
# FastAPI 应用
# ============================================================

app = FastAPI(
    title="Zenflux Agent API",
    description="基于 Claude Sonnet 4.5 的智能体框架 API",
    version="3.6.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS 中间件
# 从环境变量读取允许的域名，支持逗号分隔的多个域名
import os
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

# 注册路由
app.include_router(auth_router)  # 认证 API
app.include_router(health_router)  # 🆕 健康检查路由
app.include_router(chat_router)
app.include_router(knowledge_router)
app.include_router(human_confirmation_router)
app.include_router(conversation_router)
app.include_router(files_router)
app.include_router(workspace_router)
app.include_router(tools_router)
app.include_router(mem0_router)  # 🆕 V4.4: Mem0 用户画像 API
app.include_router(tasks_router)  # 🆕 后台任务管理 API
app.include_router(agents_router)  # 🆕 Agent 管理 API
app.include_router(skills_router)  # 🆕 Skills 管理 API


# ============================================================
# 基础路由
# ============================================================

@app.get("/")
async def root():
    """
    根路径 - API 信息
    
    返回 API 基本信息和可用端点
    """
    import os
    
    enable_grpc = os.getenv("ENABLE_GRPC", "false").lower() == "true"
    grpc_port = os.getenv("GRPC_PORT", "50051")
    
    response = {
        "name": "Zenflux Agent API",
        "version": "3.6.0",
        "status": "running",
        "description": "基于 Claude Sonnet 4.5 的智能体框架",
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
    
    # 如果 gRPC 启用，添加 gRPC 信息
    if enable_grpc:
        response["protocols"]["grpc"] = {
            "enabled": True,
            "port": int(grpc_port),
            "services": ["ChatService", "SessionService", "ToolService", "AgentService"],
            "client_example": f"from services.grpc.client import ZenfluxGRPCClient\nclient = ZenfluxGRPCClient('localhost:{grpc_port}')"
        }
    
    return response


@app.get("/health")
async def health():
    """
    健康检查
    
    返回服务健康状态
    """
    from services import get_session_service
    session_service = get_session_service()
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "active_sessions": len(session_service.agent_pool)
    }


# ============================================================
# 启动入口
# ============================================================

if __name__ == "__main__":
    import uvicorn
    import os
    
    host = _cli_args.host
    port = _cli_args.port
    instance = _cli_args.instance or os.getenv("AGENT_INSTANCE")
    
    print("\n" + "="*60)
    print("🚀 启动 Zenflux Agent API")
    print("="*60)
    
    if instance:
        print(f"🎯 预加载实例: {instance}")
    else:
        print("📦 按需加载模式（首次请求时加载）")
        
    print(f"📍 访问地址: http://localhost:{port}")
    print(f"📚 API 文档: http://localhost:{port}/docs")
    print("="*60 + "\n")
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )
