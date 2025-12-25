"""
Zenflux Agent - FastAPI 服务
基于 Claude 的智能体 Web API
"""

import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import Dict, Optional
from datetime import datetime

# 🆕 自动加载 .env 文件
from dotenv import load_dotenv

# 加载项目根目录的 .env 文件
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

from core.agent import create_simple_agent, SimpleAgent
from routers import chat_router

# ============================================================
# 全局变量
# ============================================================

# Agent 实例池（支持多会话）
agent_pool: Dict[str, SimpleAgent] = {}

# 默认 Agent 配置
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
DEFAULT_WORKSPACE = "./workspace"


# ============================================================
# 生命周期管理
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    print("🚀 Zenflux Agent API 启动中...")
    print(f"📦 默认模型: {DEFAULT_MODEL}")
    print(f"📁 工作目录: {DEFAULT_WORKSPACE}")
    yield
    # 关闭时
    print("🛑 清理 Agent 实例...")
    for agent in agent_pool.values():
        if agent._session_active:
            agent.end_session()
    agent_pool.clear()
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


# ============================================================
# 辅助函数（供 routers 使用）
# ============================================================

def get_or_create_agent(session_id: Optional[str] = None, verbose: bool = True) -> SimpleAgent:
    """
    获取或创建 Agent 实例
    
    Args:
        session_id: 会话ID（可选）
        verbose: 是否输出详细日志
        
    Returns:
        Agent 实例
    """
    if session_id and session_id in agent_pool:
        return agent_pool[session_id]
    
    # 创建新 Agent
    agent = create_simple_agent(
        model=DEFAULT_MODEL,
        workspace_dir=DEFAULT_WORKSPACE,
        verbose=verbose
    )
    
    if session_id:
        agent.start_session(session_id)
        agent_pool[session_id] = agent
    
    return agent


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
            "refine": "/api/v1/refine"
        },
        "github": "https://github.com/your-repo/zenflux-agent"
    }


@app.get("/health")
async def health():
    """
    健康检查
    
    返回服务健康状态和活跃会话数
    """
    active_count = len([a for a in agent_pool.values() if a._session_active])
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "active_sessions": active_count,
        "total_agents": len(agent_pool)
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
