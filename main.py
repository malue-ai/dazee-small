"""
xiaodazi - FastAPI 服务
基于 Claude 的智能体 Web API
Build: 2026-01-16 v2
"""

# ==================== 标准库 ====================
import os
import sys
import asyncio

# ==================== Windows 编码修复 ====================
# PyInstaller 打包后在中文 Windows 上，stdout/stderr 默认用 GBK 编码，
# 无法输出 emoji 字符（如 🔌🚀✅），会导致 UnicodeEncodeError 崩溃。
# 必须在任何 logging/print 之前执行。
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

# ==================== 第三方库 ====================
import json
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware


class UnicodeJSONResponse(JSONResponse):
    """JSONResponse that outputs Chinese characters directly (no \\uXXXX escapes)."""

    def render(self, content: any) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")

# 加载配置（统一从 config.yaml）
from services.settings_service import load_config_to_env
load_config_to_env()

# ==================== 本地模块 ====================
from routers import (
    agents_router,
    chat_router,
    conversation_router,
    files_router,
    gateway_router,
    human_confirmation_router,
    playbook_router,
    scheduled_tasks_router,
    settings_router,
    skills_router,
    models_router,
    websocket_router,
)
from infra.resilience.config import apply_resilience_config
from core.tool.registry import get_capability_registry
from infra.local_store import close_all_workspaces

# ==================== 常量定义 ====================

APP_NAME = "xiaodazi API"
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


def _is_hash_instance(name: str) -> bool:
    """Check if instance name looks like a hex hash (e.g. ac79243a, 40e2a104)."""
    import re
    return bool(re.fullmatch(r"[0-9a-f]{6,}", name))


async def _preload_agent_registry() -> int:
    """
    预加载 Agent 配置到 AgentRegistry

    本地桌面模式：加载所有 instances/ 下的实例。
    如果设置了 AGENT_INSTANCE 环境变量，则优先加载指定实例（兼容旧行为）。

    Returns:
        加载的 Agent 配置数量
    """
    print("📋 加载 Agent 配置...")
    from services.agent_registry import get_agent_registry

    agent_registry = get_agent_registry()

    # 优先检查环境变量（兼容单实例部署场景）
    instance_name = os.getenv("AGENT_INSTANCE")

    if instance_name:
        # 单实例模式：仅加载指定实例
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
    else:
        # 本地桌面模式：加载所有实例
        try:
            print("🖥️ 本地桌面模式: 加载所有实例...")
            loaded_count = await agent_registry.preload_all()
            if loaded_count > 0:
                print(f"✅ 已加载 {loaded_count} 个 Agent 配置")
                agents = agent_registry.list_agents()
                for agent in agents:
                    print(f"   • {agent['agent_id']}: {agent['description'] or '(无描述)'}")

                # 本地桌面模式自动设置 AGENT_INSTANCE
                # 确保后续组件（调度器、存储）能正确定位实例数据库
                # 优先选「有名字」的实例（非 hash ID），避免误选临时实例
                if not os.getenv("AGENT_INSTANCE") and agents:
                    agent_ids = [a["agent_id"] for a in agents]
                    # 过滤掉纯 hex hash 命名的临时实例（如 ac79243a、40e2a104）
                    named = [aid for aid in agent_ids if not _is_hash_instance(aid)]
                    auto_instance = named[0] if named else agent_ids[0]
                    os.environ["AGENT_INSTANCE"] = auto_instance
                    print(f"🎯 自动设置 AGENT_INSTANCE={auto_instance}")
            else:
                print("⚠️ 未发现任何可用实例（instances/ 目录为空或无有效配置）")
            return loaded_count
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


async def _warmup_embedding_model() -> None:
    """
    Pre-load embedding model so the first memory recall is fast.

    Non-fatal: failure only means the first embed call will be slower.
    """
    try:
        from core.knowledge.embeddings import create_embedding_provider

        provider = await create_embedding_provider("auto")
        if hasattr(provider, "warmup"):
            await provider.warmup()
            print(f"✅ Embedding 模型预热完成 ({provider.provider_id})")
        else:
            print(f"✅ Embedding 模型就绪 ({provider.provider_id})")
    except Exception as e:
        # ModelNotAvailableError, ImportError, etc. — not fatal
        print(f"⚠️ Embedding 模型预热跳过（不影响服务运行）: {e}")


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


async def _start_gateway():
    """Start the multi-channel gateway if configured."""
    try:
        from core.gateway.loader import create_gateway, load_gateway_config
        from routers.gateway import set_channel_manager

        config = await load_gateway_config()
        if not config.enabled:
            return None

        result = await create_gateway(config)
        if result is None:
            return None

        manager, bridge = result
        await manager.start_all()

        # Wire up health check router
        set_channel_manager(manager)

        status = manager.get_all_status()
        channels_str = ", ".join(f"{k}={v}" for k, v in status.items())
        print(f"🌐 Gateway 已启动 ({channels_str})")

        return manager
    except Exception as e:
        print(f"⚠️ Gateway 启动失败（不影响服务运行）: {e}")
        return None


async def _stop_gateway(manager) -> None:
    """Stop the multi-channel gateway."""
    if manager is not None:
        try:
            await manager.stop_all()
            # Clear router reference to avoid stale state
            from routers.gateway import set_channel_manager
            set_channel_manager(None)
            print("✅ Gateway 已停止")
        except Exception as e:
            print(f"⚠️ Gateway 停止失败: {e}")


# ==================== 生命周期管理 ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # ===== 启动阶段 =====
    print("🚀 xiaodazi API 启动中...")
    
    # 打包模式：迁移旧版本数据 + 初始化种子实例
    from utils.app_paths import ensure_instances_initialized, is_frozen, migrate_legacy_data
    if is_frozen():
        migrate_legacy_data()
        copied = ensure_instances_initialized()
        if copied:
            from utils.app_paths import get_instances_dir
            print(f"📦 首次启动：已初始化实例目录 → {get_instances_dir()}")
    
    await _init_resilience_config()
    await _init_local_store()
    await _preload_capability_registry()  # 加载工具注册表（必须在 Agent 之前）
    await _preload_agent_registry()  # 加载 Agent 配置
    await _init_chat_service()  # 预热 ChatService（避免首次请求冷启动）
    await _init_knowledge_index()  # 知识库：索引配置的目录
    await _warmup_embedding_model()  # Embedding 模型预热（非阻塞）
    scheduler = await _start_scheduler()
    user_task_scheduler = await _start_user_task_scheduler()  # 用户定时任务调度器
    gateway_manager = await _start_gateway()  # 多渠道网关（可选）
    
    yield
    
    # ===== 关闭阶段 =====
    print("🛑 正在关闭服务...")
    
    await _stop_gateway(gateway_manager)  # 先停网关，防止新消息进入
    await _cleanup_knowledge_service()
    await _cleanup_agent_registry()
    await _stop_user_task_scheduler(user_task_scheduler)  # 停止用户任务调度器
    await _stop_scheduler(scheduler)
    await close_all_workspaces()
    
    print("👋 xiaodazi API 已关闭")


# ==================== FastAPI 应用 ====================

app = FastAPI(
    title=APP_NAME,
    description=APP_DESCRIPTION,
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    default_response_class=UnicodeJSONResponse,
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
app.include_router(files_router)
app.include_router(skills_router)
app.include_router(models_router)
app.include_router(settings_router)
app.include_router(playbook_router)
app.include_router(scheduled_tasks_router)

# 实时通信（WebSocket）
app.include_router(websocket_router)

# 多渠道网关
app.include_router(gateway_router)


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
        "github": "https://github.com/your-repo/xiaodazi"
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

    # Windows: ProactorEventLoop 支持 asyncio.create_subprocess_exec
    # SelectorEventLoop（默认）不支持子进程，会导致 NotImplementedError
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
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
