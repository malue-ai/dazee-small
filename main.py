"""
Zenflux Agent - FastAPI 服务
基于 Claude 的智能体 Web API
"""

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

from routers import chat_router, knowledge_router, files_router, tools_router, mem0_router
from routers.human_confirmation import router as human_confirmation_router
from routers.conversation import router as conversation_router
from routers.workspace import router as workspace_router


# ============================================================
# 生命周期管理
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    print("🚀 Zenflux Agent API 启动中...")
    
    # 初始化数据库
    print("💾 初始化数据库...")
    from infra.database import init_database, engine
    await init_database()
    print("✅ 数据库初始化完成")
    
    yield
    
    # 关闭时 - 清理所有资源
    print("🛑 正在关闭服务...")
    
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(chat_router)
app.include_router(knowledge_router)
app.include_router(human_confirmation_router)
app.include_router(conversation_router)
app.include_router(files_router)
app.include_router(workspace_router)
app.include_router(tools_router)
app.include_router(mem0_router)  # 🆕 V4.4: Mem0 用户画像 API


# ============================================================
# 基础路由
# ============================================================

@app.get("/")
async def root():
    """
    根路径 - API 信息
    
    返回 API 基本信息和可用端点
    """
    return {
        "name": "Zenflux Agent API",
        "version": "3.6.0",
        "status": "running",
        "description": "基于 Claude Sonnet 4.5 的智能体框架",
        "endpoints": {
            "docs": "/docs",
            "redoc": "/redoc",
            "health": "/health",
            "chat": "/api/v1/chat",
            "stream": "/api/v1/chat/stream",
            "session": "/api/v1/session/{session_id}",
            "sessions": "/api/v1/sessions",
            "human_confirmation": "/api/v1/human-confirmation/{request_id}"  # 🆕 HITL
        },
        "github": "https://github.com/your-repo/zenflux-agent"
    }


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
    
    print("\n" + "="*60)
    print("🚀 启动 Zenflux Agent API")
    print("="*60)
    print(f"📍 访问地址: http://localhost:8000")
    print(f"📚 API 文档: http://localhost:8000/docs")
    print(f"📖 ReDoc: http://localhost:8000/redoc")
    print("="*60 + "\n")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
