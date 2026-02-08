"""
Zenflux Agent - FastAPI 服务
基于 Claude 的智能体 Web API
Build: 2026-01-16 v2
"""

# ==================== 标准库 ====================
import os
import asyncio
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

# ==================== 第三方库 ====================
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 加载配置（统一从 config.yaml）
from services.settings_service import load_config_to_env
load_config_to_env()

# ==================== 本地模块 ====================
from routers import (
    agents_router,
    chat_router,
    conversation_router,
    human_confirmation_router,
    settings_router,
    skills_router,
    models_router,
    websocket_router,
)
from infra.resilience.config import apply_resilience_config
from core.tool.registry import get_capability_registry
from infra.local_store import close_all_workspaces

# ==================== 常量定义 ====================

APP_NAME = "Zenflux Agent API"
APP_DESCRIPTION = "基于 Claude Sonnet 4.5 的智能体框架"


def _read_version() -> str:
    """Read version from VERSION file (single source of truth)."""
    from utils.app_paths import get_bundle_dir
    version_file = get_bundle_dir() / "VERSION"
    try:
        return version_file.read_text().strip()
    except FileNotFoundError:
        return "0.0.0-dev"


APP_VERSION = _read_version()


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

async def _init_resilience_config() -> None:
    """加载容错配置"""
    print("🛡️ 加载容错配置...")
    try:
        await apply_resilience_config()
        print("✅ 容错配置已加载")
    except Exception as e:
        print(f"⚠️ 容错配置加载失败: {e}")


async def _init_local_store() -> None:
    """初始化本地存储（SQLite）"""
    print("💾 初始化本地存储...")
    from infra.local_store import get_workspace
    # Workspace 在首次 get_workspace() 调用时懒初始化
    print("✅ 本地存储就绪（懒初始化模式）")



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

    实例检测优先级：
    1. 环境变量 AGENT_INSTANCE（显式指定）
    2. 自动检测：instances/ 目录下只有一个实例时自动使用
    3. 多个实例时提示用户选择

    Returns:
        加载的 Agent 配置数量（0 或 1）
    """
    print("📋 加载 Agent 配置...")
    from services.agent_registry import get_agent_registry

    agent_registry = get_agent_registry()

    # 实例检测：环境变量 > 自动检测
    instance_name = os.getenv("AGENT_INSTANCE")

    if not instance_name:
        from utils.instance_loader import list_instances

        available = list_instances()
        if len(available) == 1:
            instance_name = available[0]
            os.environ["AGENT_INSTANCE"] = instance_name
            print(f"🎯 自动检测到唯一实例: {instance_name}")
        elif len(available) == 0:
            print("❌ 未找到任何实例！")
            print("   请在 instances/ 目录下创建实例（可复制 _template）")
            return 0
        else:
            print(f"❌ 检测到多个实例: {available}")
            print(f"   请指定要加载的实例:")
            print(f"   AGENT_INSTANCE={available[0]} uvicorn main:app --reload")
            return 0
    
    try:
        print(f"🎯 单实例模式: 加载 '{instance_name}'...")
        success = await agent_registry.preload_instance(instance_name)
        if success:
            print(f"✅ 已加载 1 个 Agent 配置")
            for agent in agent_registry.list_agents():
                print(f"   • {agent['agent_id']}: {agent['description'] or '(无描述)'}")
            return 1
        else:
            print(f"⚠️ Agent 配置加载失败: {instance_name}")
            return 0
    except FileNotFoundError as e:
        print(f"❌ 实例不存在: {e}")
        return 0
    except Exception as e:
        print(f"⚠️ Agent 配置加载失败: {e}")
        return 0


async def _start_scheduler() -> Optional[Any]:
    """启动定时任务调度器（系统级）"""
    enable_scheduler = os.getenv("ENABLE_SCHEDULER", "true").lower() == "true"
    if not enable_scheduler:
        return None

    try:
        from utils.background_tasks import get_scheduler

        scheduler = get_scheduler()
        await scheduler.start()
        return scheduler

    except Exception as e:
        print(f"⚠️ 系统定时任务调度器启动失败: {e}")

    return None


async def _start_user_task_scheduler() -> Optional[Any]:
    """启动用户定时任务调度器"""
    enable_scheduler = os.getenv("ENABLE_USER_TASK_SCHEDULER", "true").lower() == "true"
    if not enable_scheduler:
        return None

    try:
        from services.user_task_scheduler import start_user_task_scheduler

        scheduler = await start_user_task_scheduler()
        return scheduler

    except Exception as e:
        print(f"⚠️ 用户任务调度器启动失败: {e}")

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


async def _init_knowledge_index() -> None:
    """
    初始化知识库索引

    从实例配置读取 knowledge.directories，索引配置的本地目录。
    索引在后台进行，不阻塞服务启动。
    """
    print("📚 初始化知识库...")
    try:
        from services.knowledge_service import index_configured_directories

        count = await index_configured_directories()
        if count > 0:
            print(f"✅ 知识库索引完成 ({count} 个文件)")
        else:
            print("✅ 知识库就绪（无配置目录或目录为空）")
    except Exception as e:
        print(f"⚠️ 知识库索引失败（不影响服务运行）: {e}")


# ==================== 关闭辅助函数 ====================


async def _cleanup_knowledge_service() -> None:
    """清理知识服务资源"""
    try:
        from services.knowledge_service import shutdown as knowledge_shutdown
        await knowledge_shutdown()
    except Exception:
        pass


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
    """关闭定时任务调度器（系统级）"""
    if scheduler and scheduler.is_running():
        try:
            await scheduler.shutdown()
        except Exception as e:
            print(f"⚠️ 关闭系统定时任务调度器失败: {e}")


async def _stop_user_task_scheduler(scheduler: Optional[Any]) -> None:
    """关闭用户任务调度器"""
    if scheduler and scheduler.is_running():
        try:
            await scheduler.shutdown()
        except Exception as e:
            print(f"⚠️ 关闭用户任务调度器失败: {e}")


# ==================== 生命周期管理 ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # ===== 启动阶段 =====
    print("🚀 Zenflux Agent API 启动中...")
    
    # 设置自定义异常处理器（抑制 MCP 关闭时的已知错误）
    _setup_asyncio_exception_handler()
    
    await _init_resilience_config()
    await _init_local_store()
    await _preload_capability_registry()  # 加载工具注册表（必须在 Agent 之前）
    await _preload_agent_registry()  # 加载 Agent 配置
    await _init_chat_service()  # 预热 ChatService（避免首次请求冷启动）
    await _init_knowledge_index()  # 知识库：索引配置的目录
    scheduler = await _start_scheduler()
    user_task_scheduler = await _start_user_task_scheduler()  # 用户定时任务调度器
    
    yield
    
    # ===== 关闭阶段 =====
    print("🛑 正在关闭服务...")
    
    await _cleanup_knowledge_service()
    await _cleanup_agent_registry()
    await _stop_user_task_scheduler(user_task_scheduler)  # 停止用户任务调度器
    await _stop_scheduler(scheduler)
    await close_all_workspaces()
    
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

# 核心功能
app.include_router(chat_router)
app.include_router(conversation_router)
app.include_router(human_confirmation_router)

# 资源管理
app.include_router(agents_router)
app.include_router(skills_router)
app.include_router(models_router)
app.include_router(settings_router)

# 实时通信（WebSocket）
app.include_router(websocket_router)


# ==================== 基础路由 ====================

@app.get("/")
async def root() -> Dict[str, Any]:
    """
    根路径 - API 信息
    
    返回 API 基本信息和可用端点
    """
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
            "chat_ws": "ws://host/api/v1/ws/chat"
        },
        "github": "https://github.com/your-repo/zenflux-agent"
    }
    
    return response


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint for Tauri sidecar readiness detection.

    Tauri main.rs polls this endpoint to determine if the backend is ready.
    Returns 200 with basic status info once the server is accepting connections.
    """
    return {
        "status": "ok",
        "version": APP_VERSION,
    }


# ==================== 启动入口 ====================

if __name__ == "__main__":
    import uvicorn
    from utils.app_paths import get_cli_port, is_frozen
    
    port = get_cli_port() if is_frozen() else 8000
    host = "127.0.0.1" if is_frozen() else "0.0.0.0"
    
    print("\n" + "=" * 60)
    print(f"🚀 启动 {APP_NAME}")
    print("=" * 60)
    print(f"📍 访问地址: http://localhost:{port}")
    print(f"📚 API 文档: http://localhost:{port}/docs")
    print(f"📖 ReDoc: http://localhost:{port}/redoc")
    print("=" * 60 + "\n")
    
    if is_frozen():
        # PyInstaller 打包模式：必须直接传 app 对象
        # 字符串导入 "main:app" 在 PyInstaller 中会导致 ModuleNotFoundError
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
        )
    else:
        # 开发模式：使用字符串导入 + 热重载
        uvicorn.run(
            "main:app",
            host=host,
            port=port,
            reload=True,
            log_level="info",
        )
