"""
设置 API 路由

提供桌面应用配置管理的 REST API：
- GET  /api/v1/settings         — 读取配置
- PUT  /api/v1/settings         — 更新配置
- GET  /api/v1/settings/status  — 检查配置状态
- GET  /api/v1/settings/schema  — 获取配置项定义
"""

from typing import Any, Dict

from fastapi import APIRouter

from pydantic import BaseModel

from logger import get_logger
from services.settings_service import (
    download_embedding_model,
    get_embedding_status,
    get_semantic_download_status,
    get_settings,
    get_settings_schema,
    get_settings_status,
    reset_download_state,
    setup_semantic_search,
    update_settings,
)

logger = get_logger(__name__)


class SemanticSearchSetupRequest(BaseModel):
    """语义搜索配置请求"""

    mode: str
    """
    "disabled" — 不需要，关键词搜索即可
    "local"    — 本地模型（438MB，离线可用，推荐）
    "cloud"    — OpenAI 云端（需要 API Key，按量计费）
    """

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


@router.get("")
async def read_settings() -> Dict[str, Any]:
    """
    获取当前配置

    桌面端本地运行，API Key 原文返回
    """
    return {
        "success": True,
        "data": await get_settings(),
    }


@router.put("")
async def write_settings(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    更新配置

    请求体示例:
    ```json
    {
      "api_keys": {
        "ANTHROPIC_API_KEY": "sk-ant-api03-..."
      },
      "llm": {
        "COT_AGENT_MODEL": "claude-sonnet-4-5-20250514"
      }
    }
    ```
    """
    updated = await update_settings(body)

    # API Key 变更后的处理
    if "api_keys" in body:
        try:
            from core.memory.mem0.config import set_mem0_config
            from core.memory.mem0.pool import reset_mem0_pool

            set_mem0_config(None)
            reset_mem0_pool()
            logger.info("🔄 Mem0 配置和缓存池已重置，将随 API Key 自动重新检测")
        except Exception:
            pass

        # 注意：Agent 热重载由 POST /providers/activate 触发
        # 前端流程：PUT /settings → POST /providers/activate（含 reload）
        # 这样确保 reload 发生在模型激活之后，agent 能获取到正确的 provider/model

    # 非 API Key 变更（如 llm 配置变更）仍需触发热重载
    if "api_keys" not in body and ("llm" in body or "app" in body):
        try:
            from services.agent_registry import get_agent_registry
            registry = get_agent_registry()
            if registry.is_loaded:
                result = await registry.reload_agent()
                logger.info(f"🔄 Settings 变更后热重载 Agent: {result}")
        except Exception as e:
            logger.warning(f"⚠️ Agent 热重载失败（不影响设置保存）: {e}")

    return {
        "success": True,
        "data": updated,
    }


@router.get("/status")
async def read_settings_status() -> Dict[str, Any]:
    """
    检查必要配置是否已填写

    用于首次启动引导：前端检查 configured=false 时弹出设置页
    """
    return {
        "success": True,
        "data": await get_settings_status(),
    }


@router.get("/schema")
async def read_settings_schema() -> Dict[str, Any]:
    """
    获取配置项 Schema

    前端根据 Schema 动态渲染设置表单
    """
    return {
        "success": True,
        "data": get_settings_schema(),
    }


@router.get("/embedding-status")
async def read_embedding_status() -> Dict[str, Any]:
    """
    检测语义搜索 embedding 模型可用性

    前端据此显示：
    - 模型是否已下载 (model_downloaded)
    - 是否已安装依赖 (local_available)
    - 安装提示和推荐方案
    """
    return {
        "success": True,
        "data": await get_embedding_status(),
    }


@router.post("/semantic-search/setup")
async def setup_semantic_search_mode(body: SemanticSearchSetupRequest) -> Dict[str, Any]:
    """
    配置语义搜索模式（首次启动引导 / 设置页）

    前端展示三个选项卡，用户选一个：

    ```
    ┌──────────┐  ┌──────────────┐  ┌────────────────┐
    │ 不需要   │  │ 本地模型     │  │ OpenAI 云端    │
    │          │  │ （推荐）     │  │                │
    │ 关键词   │  │ 438MB 离线   │  │ 需要 API Key   │
    │ 搜索即可 │  │ 中英文双语   │  │ 按量计费       │
    └──────────┘  └──────────────┘  └────────────────┘
    ```

    请求体：
    ```json
    {"mode": "disabled"}  // 或 "local" 或 "cloud"
    ```

    选 "local" 时：
    - 自动检测最佳下载源（国内镜像 / 官方）
    - 模型已存在则跳过下载
    - 返回 needs_download + download_result
    """
    result = await setup_semantic_search(body.mode)
    return {
        "success": result["success"],
        "data": result,
    }


@router.get("/semantic-search/download-status")
async def read_semantic_download_status() -> Dict[str, Any]:
    """
    查询后台模型下载任务状态

    前端轮询此接口以跟踪下载进度，即使离开设置页再回来也能恢复状态。

    返回:
    - status: "idle" | "downloading" | "done" | "error"
    - mode: 触发下载时的模式
    - error: 错误信息（仅 status=error 时有值）
    - source: 下载源（"mirror" | "official"，仅 status=done 时有值）
    - elapsed_seconds: 已耗时（秒）
    """
    return {
        "success": True,
        "data": get_semantic_download_status(),
    }


@router.post("/semantic-search/download-status/reset")
async def reset_semantic_download_status() -> Dict[str, Any]:
    """
    重置下载状态为 idle

    前端确认完成/失败后调用，清理状态以便下次操作。
    """
    reset_download_state()
    return {"success": True}


@router.post("/embedding-model/download")
async def trigger_embedding_model_download() -> Dict[str, Any]:
    """
    单独触发模型下载（补充端点）

    适用于：之前选了 disabled，现在想补装本地模型。
    如果后台已有下载任务正在进行，直接返回当前状态。
    """
    bg_status = get_semantic_download_status()
    if bg_status["status"] == "downloading":
        return {
            "success": True,
            "data": {
                "success": True,
                "model_path": None,
                "source": None,
                "error": None,
                "message": "后台下载已在进行中",
            },
        }

    result = await download_embedding_model()
    return {
        "success": result["success"],
        "data": result,
    }


@router.get("/memory/health")
async def memory_health() -> Dict[str, Any]:
    """
    Memory system health check.

    Reports status of each layer:
    - fts5: full-text search index
    - mem0: vector semantic search (Mem0 + sqlite-vec)
    """
    try:
        from core.memory.instance_memory import InstanceMemoryManager

        mgr = InstanceMemoryManager(
            user_id="health_check",
            mem0_enabled=True,
        )

        # Layer 2: FTS5
        fts5_status = "ok"
        fts5_count = 0
        try:
            fts_results = await mgr._fts5_recall("test", limit=1)
            fts5_status = "ok"
            fts5_count = len(fts_results)
        except Exception as e:
            fts5_status = f"error: {e}"

        # Layer 3: Mem0
        mem0_status = "disabled"
        mem0_count = 0
        if mgr._mem0_enabled:
            try:
                mgr._ensure_mem0()
                if mgr._mem0_pool:
                    info = mgr._mem0_pool.memory.vector_store.col_info()
                    mem0_count = info.get("document_count", 0)
                    mem0_status = "ok"
                else:
                    mem0_status = "init_failed"
            except Exception as e:
                mem0_status = f"error: {e}"

        all_ok = fts5_status == "ok" and mem0_status in ("ok", "disabled")
        return {
            "success": True,
            "data": {
                "status": "healthy" if all_ok else "degraded",
                "layers": {
                    "fts5": {"status": fts5_status, "count": fts5_count},
                    "mem0": {
                        "status": mem0_status,
                        "vector_count": mem0_count,
                        "enabled": mgr._mem0_enabled,
                    },
                },
            },
        }
    except Exception as e:
        logger.error(f"Memory health check failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
        }
