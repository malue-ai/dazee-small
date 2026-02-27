"""
设置服务 - Settings Service

统一管理应用配置，开发和生产环境均使用 config.yaml。
配置存储在 {user_data_dir}/config.yaml。

核心功能：
- 加载 config.yaml 并注入 os.environ（向后兼容 os.getenv()）
- 提供 REST API 给前端设置页面读写
- API Key 原文返回（桌面端本地运行，无需脱敏）
"""

import asyncio
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
import yaml

from logger import get_logger
from utils.app_paths import get_bundle_dir, get_user_config_path

logger = get_logger(__name__)

# ==================== 后台下载任务状态 ====================

_download_state: Dict[str, Any] = {
    "status": "idle",       # idle | downloading | done | error
    "mode": None,           # 触发下载时的模式
    "error": None,          # 错误信息
    "result": None,         # 下载结果 (download_result dict)
    "started_at": None,     # 开始时间戳
    "finished_at": None,    # 完成时间戳
}
_download_task: Optional[asyncio.Task] = None


def _load_dotenv_fallback() -> None:
    """When config.yaml is missing or has no API keys, load project root .env."""
    try:
        from dotenv import load_dotenv
        env_path = get_bundle_dir() / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=env_path, override=False)
            logger.info("已从 .env 回退加载环境变量")
    except ImportError:
        pass

# ==================== 配置结构定义 ====================

# _LLM_API_KEY_NAMES: 在 SETTINGS_SCHEMA 之后动态生成，见下方

# 可选配置项（按分组）
SETTINGS_SCHEMA = {
    "api_keys": {
        "ANTHROPIC_API_KEY": {"label": "Anthropic API Key", "required": False, "secret": True},
        "ANTHROPIC_BASE_URL": {"label": "Anthropic Base URL", "required": False, "secret": False},
        "OPENAI_API_KEY": {"label": "OpenAI API Key", "required": False, "secret": True},
        "OPENAI_BASE_URL": {"label": "OpenAI Base URL", "required": False, "secret": False},
        "DASHSCOPE_API_KEY": {"label": "DashScope API Key", "required": False, "secret": True},
        "DASHSCOPE_BASE_URL": {"label": "DashScope Base URL", "required": False, "secret": False},
        "GEMINI_API_KEY": {"label": "Gemini API Key", "required": False, "secret": True},
        "DEEPSEEK_API_KEY": {"label": "DeepSeek API Key", "required": False, "secret": True},
        "DEEPSEEK_BASE_URL": {"label": "DeepSeek Base URL", "required": False, "secret": False},
        "MOONSHOT_API_KEY": {"label": "Moonshot (Kimi) API Key", "required": False, "secret": True},
        "MOONSHOT_BASE_URL": {"label": "Moonshot Base URL", "required": False, "secret": False},
        "MINIMAX_API_KEY": {"label": "MiniMax API Key", "required": False, "secret": True},
        "MINIMAX_BASE_URL": {"label": "MiniMax Base URL", "required": False, "secret": False},
        "ZHIPUAI_API_KEY": {"label": "Zhipu AI (GLM) API Key", "required": False, "secret": True},
        "ZHIPUAI_BASE_URL": {"label": "Zhipu AI Base URL", "required": False, "secret": False},
    },
    "llm": {
        "COT_AGENT_MODEL": {"label": "默认模型", "required": False, "secret": False,
                            "default": "claude-sonnet-4-5-20250514"},
        "QOS_LEVEL": {"label": "服务等级", "required": False, "secret": False,
                      "default": "PRO"},
    },
    "knowledge": {
        "SEMANTIC_SEARCH_ENABLED": {
            "label": "语义搜索",
            "required": False,
            "secret": False,
            "default": "false",
            "type": "toggle",
            "description": "开启后可理解搜索意图（如搜\"天气\"也能找到\"气候\"相关文档）",
        },
        "EMBEDDING_PROVIDER": {
            "label": "向量模型",
            "required": False,
            "secret": False,
            "default": "auto",
            "type": "select",
            "options": [
                {"value": "auto", "label": "自动选择（推荐）",
                 "description": "优先本地模型，无本地模型时使用 OpenAI"},
                {"value": "local", "label": "本地模型（离线可用）",
                 "description": "BGE-M3 Q4 量化，424MB，中英文双语"},
                {"value": "openai", "label": "OpenAI 云端",
                 "description": "需要 OpenAI API Key 和网络连接"},
            ],
        },
        "EMBEDDING_MODEL": {
            "label": "模型名称（高级）",
            "required": False,
            "secret": False,
            "default": "",
            "type": "text",
            "description": "留空使用默认值。本地默认 BGE-M3 Q4 GGUF，OpenAI 默认 text-embedding-3-small",
            "advanced": True,
        },
    },
    "app": {
        "LOG_LEVEL": {"label": "日志级别", "required": False, "secret": False,
                      "default": "INFO"},
    },
}

# 从 Schema 自动提取所有 LLM API Key 名称（secret=True 且以 _API_KEY 结尾）
_LLM_API_KEY_NAMES = [
    key for key, meta in SETTINGS_SCHEMA["api_keys"].items()
    if meta.get("secret") and key.endswith("_API_KEY")
]

# 缓存
_settings_cache: Optional[Dict[str, Any]] = None


# ==================== 核心加载函数 ====================


def load_config_to_env() -> None:
    """
    Load config.yaml and inject values into os.environ.

    Falls back to loading .env from project root if config.yaml is missing
    or no LLM API key is found.
    Also validates SETTINGS_SCHEMA covers all SUPPORTED_PROVIDERS api_key_env.
    """
    config_path = get_user_config_path()

    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            "# ZenFlux Agent 配置文件\n"
            "# 通过设置页面管理，或手动编辑\n",
            encoding="utf-8",
        )
        logger.info(f"首次启动，已创建空配置文件: {config_path}")
        _load_dotenv_fallback()
        return

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}", exc_info=True)
        _load_dotenv_fallback()
        return

    # 从 config 注入 os.environ
    injected_count = 0
    for section_key, section_data in config.items():
        if isinstance(section_data, dict):
            for key, value in section_data.items():
                if value is not None and value != "":
                    os.environ[key] = str(value)
                    injected_count += 1
        elif section_key and section_data is not None:
            os.environ[section_key] = str(section_data)
            injected_count += 1

    # 若注入后仍无任何 LLM API Key，回退到 .env（兼容仅用 .env 的开发方式）
    has_any_key = any(os.environ.get(k) for k in _LLM_API_KEY_NAMES)
    if not has_any_key:
        _load_dotenv_fallback()

    if injected_count > 0:
        logger.info(f"从 config.yaml 注入 {injected_count} 个环境变量")

    # 交叉校验：SUPPORTED_PROVIDERS 的 api_key_env 应在 SETTINGS_SCHEMA 中注册
    _validate_schema_provider_sync()


def _validate_schema_provider_sync() -> None:
    """
    Validate that all SUPPORTED_PROVIDERS api_key_env values are registered
    in SETTINGS_SCHEMA. Logs warnings at startup to prevent silent key-loss bugs.
    """
    try:
        from routers.models import SUPPORTED_PROVIDERS
    except ImportError:
        return  # routers not loaded yet (e.g. unit test), skip

    schema_keys = set(SETTINGS_SCHEMA.get("api_keys", {}).keys())
    for provider_name, meta in SUPPORTED_PROVIDERS.items():
        api_key_env = meta.get("api_key_env", "")
        if api_key_env and api_key_env not in schema_keys:
            logger.warning(
                f"⚠️ Provider '{provider_name}' 的 api_key_env='{api_key_env}' "
                f"未在 SETTINGS_SCHEMA['api_keys'] 中注册，API Key 将无法通过设置页面持久化"
            )


async def _load_settings() -> Dict[str, Any]:
    """加载配置文件内容（带缓存，async I/O）"""
    global _settings_cache
    if _settings_cache is not None:
        return _settings_cache

    config_path = get_user_config_path()
    if not config_path.exists():
        _settings_cache = {}
        return _settings_cache

    try:
        async with aiofiles.open(config_path, "r", encoding="utf-8") as f:
            content = await f.read()
        _settings_cache = yaml.safe_load(content) or {}
    except Exception as e:
        logger.error(f"加载配置失败: {e}", exc_info=True)
        _settings_cache = {}

    return _settings_cache


async def _save_settings(settings: Dict[str, Any]) -> None:
    """保存配置到文件"""
    global _settings_cache
    config_path = get_user_config_path()

    # 确保目录存在
    config_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiofiles.open(config_path, "w", encoding="utf-8") as f:
        content = yaml.dump(
            settings,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
        await f.write(content)

    # 更新缓存
    _settings_cache = settings

    # 同步注入 os.environ
    for section_key, section_data in settings.items():
        if isinstance(section_data, dict):
            for key, value in section_data.items():
                if value is not None and value != "":
                    os.environ[key] = str(value)

    logger.info(f"配置已保存: {config_path}")


# ==================== API 层方法 ====================


async def get_settings() -> Dict[str, Any]:
    """
    获取当前配置

    Returns:
        按分组返回的配置
    """
    settings = await _load_settings()
    result = {}

    for group_key, group_schema in SETTINGS_SCHEMA.items():
        group_data = settings.get(group_key, {})
        result[group_key] = {}

        for key, meta in group_schema.items():
            raw_value = ""
            if isinstance(group_data, dict):
                raw_value = group_data.get(key, "")
            # 兼容：也从 os.environ 读取
            if not raw_value:
                raw_value = os.getenv(key, "")

            result[group_key][key] = raw_value or meta.get("default", "")

    return result


async def update_settings(updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    更新配置

    Args:
        updates: 按分组的配置更新
            例: {"api_keys": {"ANTHROPIC_API_KEY": "sk-ant-..."}}

    Returns:
        更新后的配置
    """
    settings = await _load_settings()

    for group_key, group_updates in updates.items():
        if group_key not in SETTINGS_SCHEMA:
            continue
        if not isinstance(group_updates, dict):
            continue

        if group_key not in settings:
            settings[group_key] = {}

        for key, value in group_updates.items():
            if key not in SETTINGS_SCHEMA[group_key]:
                continue

            # 空字符串 = 删除配置
            if value == "":
                settings[group_key].pop(key, None)
                # 同步清除 os.environ，避免 fallback 读到旧值
                os.environ.pop(key, None)
            else:
                settings[group_key][key] = value

    await _save_settings(settings)
    return await get_settings()


async def get_settings_status() -> Dict[str, Any]:
    """
    检查必要配置是否已填写

    Returns:
        {"configured": bool, "missing": [...], "summary": {...}}
    """
    settings = await _load_settings()

    # 检查是否至少配置了一个 LLM API Key（从配置文件和环境变量两个来源检查）
    has_any_llm_key = False
    configured_providers: List[str] = []
    for key in _LLM_API_KEY_NAMES:
        found = False
        for group_data in settings.values():
            if isinstance(group_data, dict) and group_data.get(key):
                found = True
                break
        if not found:
            found = bool(os.getenv(key))
        if found:
            has_any_llm_key = True
            configured_providers.append(key)

    # 汇总各组配置状态
    summary = {}
    for group_key, group_schema in SETTINGS_SCHEMA.items():
        group_data = settings.get(group_key, {})
        configured = 0
        total = len(group_schema)
        for key in group_schema:
            val = group_data.get(key, "") if isinstance(group_data, dict) else ""
            if not val:
                val = os.getenv(key, "")
            if val:
                configured += 1
        summary[group_key] = {"configured": configured, "total": total}

    return {
        "configured": has_any_llm_key,
        "missing": [] if has_any_llm_key else ["ANY_LLM_API_KEY"],
        "configured_providers": configured_providers,
        "summary": summary,
    }


def get_settings_schema() -> Dict[str, Any]:
    """
    获取配置项 Schema（供前端渲染表单）

    Returns:
        配置项定义
    """
    return SETTINGS_SCHEMA


def invalidate_cache() -> None:
    """清除配置缓存（配置更新后调用）"""
    global _settings_cache
    _settings_cache = None


# ==================== 知识库 Embedding 状态检测 ====================


async def get_embedding_status() -> Dict[str, Any]:
    """
    检测 embedding 提供商可用性

    自动检测：
    1. sentence-transformers 是否安装（本地模型）
    2. OPENAI_API_KEY 是否配置（云端模型）
    3. 当前选择的提供商

    Returns:
        {
            "semantic_enabled": bool,
            "current_provider": str | None,
            "local_available": bool,
            "openai_available": bool,
            "local_install_hint": str,
            "recommendation": str,
        }
    """
    from services.knowledge_service import _load_knowledge_config
    knowledge_config = await _load_knowledge_config()
    semantic_enabled = knowledge_config.get("semantic_enabled", False)
    provider_setting = knowledge_config.get("embedding_provider", "auto")

    # Check local availability (GGUF preferred, sentence-transformers fallback)
    local_available = False
    local_backend = None
    try:
        import llama_cpp  # noqa: F401
        local_available = True
        local_backend = "gguf"
    except ImportError:
        pass

    if not local_available:
        try:
            import sentence_transformers  # noqa: F401
            local_available = True
            local_backend = "sentence-transformers"
        except ImportError:
            pass

    # Check OpenAI availability
    openai_available = bool(os.getenv("OPENAI_API_KEY"))

    # Model download status (checked early — needed for provider resolution)
    from core.knowledge.embeddings import is_gguf_model_downloaded
    from utils.app_paths import get_shared_models_dir

    model_downloaded = is_gguf_model_downloaded()
    models_dir = str(get_shared_models_dir())

    # Local model is truly ready only when both dependency AND model file exist
    local_ready = local_available and model_downloaded

    # Determine current effective provider
    # Cross-check: config says "local" but model file deleted → not actually working
    current_provider = None
    if semantic_enabled:
        if provider_setting == "auto":
            if local_ready:
                current_provider = "local"
            elif openai_available:
                current_provider = "openai"
        elif provider_setting == "local" and local_ready:
            current_provider = "local"
        elif provider_setting == "openai" and openai_available:
            current_provider = "openai"

    # If config says enabled but no provider is actually working, report as disabled
    if semantic_enabled and current_provider is None:
        semantic_enabled = False

    # Recommendation for user
    if model_downloaded:
        recommendation = "本地模型已就绪，可开启语义搜索"
    elif local_available and not model_downloaded:
        recommendation = "依赖已安装，需要下载模型（438MB）才能使用本地语义搜索"
    elif openai_available:
        recommendation = "可使用 OpenAI 云端语义搜索，或安装本地模型离线使用"
    else:
        recommendation = "安装 llama-cpp-python 后可启用本地语义搜索（438MB）"

    return {
        "semantic_enabled": semantic_enabled,
        "current_provider": current_provider,
        "provider_setting": provider_setting,
        "local_available": local_available,
        "local_backend": local_backend,
        "model_downloaded": model_downloaded,
        "openai_available": openai_available,
        "local_install_hint": "pip install llama-cpp-python",
        "local_model_name": "BGE-M3 Q4 (GGUF)",
        "local_model_size": "438MB",
        "local_model_description": "中英文双语，MIT 开源，离线可用",
        "models_dir": models_dir,
        "recommendation": recommendation,
    }


async def download_embedding_model() -> Dict[str, Any]:
    """
    Download GGUF embedding model (user-initiated).

    Called from settings API after user confirms download.
    Auto-detects best source (official HuggingFace vs China mirror).

    Returns:
        {"success": bool, "model_path": str, "source": str, "error": str | None}
    """
    from core.knowledge.embeddings import (
        HF_MIRROR_ENDPOINT,
        _detect_hf_endpoint,
        download_gguf_model,
        is_gguf_model_downloaded,
    )

    if is_gguf_model_downloaded():
        from core.knowledge.embeddings import get_models_dir, DEFAULT_GGUF_FILE
        return {
            "success": True,
            "model_path": str(get_models_dir() / DEFAULT_GGUF_FILE),
            "source": "local (already exists)",
            "error": None,
        }

    try:
        endpoint = await _detect_hf_endpoint()
        source = "mirror" if endpoint == HF_MIRROR_ENDPOINT else "official"

        model_path = await download_gguf_model()

        return {
            "success": True,
            "model_path": model_path,
            "source": source,
            "error": None,
        }
    except Exception as e:
        logger.error(f"Embedding model download failed: {e}", exc_info=True)
        return {
            "success": False,
            "model_path": None,
            "source": None,
            "error": str(e),
        }


async def setup_semantic_search(mode: str) -> Dict[str, Any]:
    """
    Setup semantic search mode (user-initiated, first-launch or settings page).

    Three modes:
    - "disabled": keyword search only, no model needed
    - "local":    download 438MB GGUF model, offline, recommended
    - "cloud":    use OpenAI embedding API, needs API key

    When local mode needs model download, the download runs as a background
    asyncio task. The API returns immediately with ``"downloading": True``,
    and the frontend polls ``get_semantic_download_status()`` for progress.
    Once download finishes, the backend auto-applies the config (reloads
    runtime singletons) without requiring the user to stay on the page.

    Args:
        mode: "disabled" | "local" | "cloud"

    Returns:
        {
            "success": bool,
            "mode": str,
            "needs_download": bool,
            "downloading": bool,
            "download_result": {...} | None,
            "error": str | None,
        }
    """
    if mode not in ("disabled", "local", "cloud"):
        return {
            "success": False,
            "mode": mode,
            "needs_download": False,
            "downloading": False,
            "download_result": None,
            "error": f"Invalid mode: {mode}. Must be 'disabled', 'local', or 'cloud'.",
        }

    # Step 1: Write to global config/semantic_search.yaml
    await _write_semantic_search_config(mode)
    logger.info(f"Semantic search setup: mode={mode}")

    # Step 2: If local mode, check and download model
    if mode == "local":
        from core.knowledge.embeddings import is_gguf_model_downloaded

        if not is_gguf_model_downloaded():
            # Launch background download task and return immediately
            _start_background_download(mode)
            return {
                "success": True,
                "mode": mode,
                "needs_download": True,
                "downloading": True,
                "download_result": None,
                "error": None,
            }

        # Model already exists → reload runtime singletons directly
        await _reload_semantic_components()

        return {
            "success": True,
            "mode": mode,
            "needs_download": False,
            "downloading": False,
            "download_result": None,
            "error": None,
        }

    # Step 3: If cloud mode, check API key
    if mode == "cloud":
        has_key = bool(os.getenv("OPENAI_API_KEY"))
        if has_key:
            await _reload_semantic_components()
        return {
            "success": has_key,
            "mode": mode,
            "needs_download": False,
            "downloading": False,
            "download_result": None,
            "error": None if has_key else "需要先配置 OpenAI API Key",
        }

    # disabled → reload to disable semantic
    await _reload_semantic_components()
    return {
        "success": True,
        "mode": mode,
        "needs_download": False,
        "downloading": False,
        "download_result": None,
        "error": None,
    }


# ==================== 后台下载任务管理 ====================


def _start_background_download(mode: str) -> None:
    """
    Launch an asyncio background task that downloads the embedding model
    and auto-applies the semantic search config when done.

    Safe to call multiple times — if a download is already in progress,
    the call is a no-op.
    """
    global _download_task, _download_state

    # Already downloading → no-op
    if _download_state["status"] == "downloading" and _download_task and not _download_task.done():
        logger.info("Background download already in progress, skipping duplicate launch")
        return

    _download_state.update({
        "status": "downloading",
        "mode": mode,
        "error": None,
        "result": None,
        "started_at": time.time(),
        "finished_at": None,
    })

    _download_task = asyncio.create_task(
        _background_download_and_apply(mode),
        name="embedding_model_download",
    )
    logger.info("Background embedding model download task started")


async def _background_download_and_apply(mode: str) -> None:
    """
    Background coroutine: download model → reload semantic components.

    Updates ``_download_state`` throughout so the frontend can poll status.
    """
    global _download_state
    try:
        result = await download_embedding_model()
        if result["success"]:
            written = await _write_semantic_search_config(mode)
            if not written:
                logger.warning(
                    "Config write failed after download, semantic search may not persist"
                )

            # Auto-apply: reload runtime singletons
            await _reload_semantic_components()
            _download_state.update({
                "status": "done",
                "result": result,
                "error": None,
                "finished_at": time.time(),
            })
            logger.info("Background download completed and semantic search applied")
        else:
            _download_state.update({
                "status": "error",
                "result": result,
                "error": result.get("error", "下载失败"),
                "finished_at": time.time(),
            })
            logger.error(f"Background download failed: {result.get('error')}")
    except Exception as e:
        _download_state.update({
            "status": "error",
            "result": None,
            "error": str(e),
            "finished_at": time.time(),
        })
        logger.error(f"Background download exception: {e}", exc_info=True)


def get_semantic_download_status() -> Dict[str, Any]:
    """
    Return current background download task status.

    Called by the frontend poll endpoint.

    Returns:
        {
            "status": "idle" | "downloading" | "done" | "error",
            "mode": str | None,
            "error": str | None,
            "source": str | None,
            "elapsed_seconds": float | None,
        }
    """
    elapsed = None
    if _download_state["started_at"]:
        end = _download_state["finished_at"] or time.time()
        elapsed = round(end - _download_state["started_at"], 1)

    source = None
    if _download_state["result"] and isinstance(_download_state["result"], dict):
        source = _download_state["result"].get("source")

    return {
        "status": _download_state["status"],
        "mode": _download_state["mode"],
        "error": _download_state["error"],
        "source": source,
        "elapsed_seconds": elapsed,
    }


def reset_download_state() -> None:
    """Reset download state to idle (called after frontend acknowledges completion).

    No-op if a download is currently in progress — prevents accidental state loss.
    """
    global _download_state, _download_task
    if _download_state["status"] == "downloading":
        logger.warning("Attempted to reset download state while downloading, ignored")
        return

    _download_state.update({
        "status": "idle",
        "mode": None,
        "error": None,
        "result": None,
        "started_at": None,
        "finished_at": None,
    })
    _download_task = None


async def _write_semantic_search_config(mode: str) -> bool:
    """
    Write semantic search mode to global config/semantic_search.yaml.

    Args:
        mode: "disabled" | "local" | "cloud"

    Returns:
        True if config was written successfully, False otherwise.
    """
    config_path = Path(__file__).resolve().parent.parent / "config" / "semantic_search.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if config_path.exists():
        async with aiofiles.open(config_path, "r", encoding="utf-8") as f:
            content = await f.read()
        config = yaml.safe_load(content) or {}
    else:
        config = {}

    config.setdefault("semantic_search", {})
    config["semantic_search"]["mode"] = mode

    async with aiofiles.open(config_path, "w", encoding="utf-8") as f:
        content = yaml.dump(
            config,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
        await f.write(content)

    logger.info(f"Semantic search config updated: {config_path} (mode={mode})")
    return True


async def _reload_semantic_components() -> None:
    """
    Reload all runtime singletons that depend on semantic search config.

    Called after setup_semantic_search() so changes take effect without restart.
    Destroys existing singletons; they'll be re-created with new config on next use.
    """
    # 0. 重新加载 SQLite 引擎（重新检测 sqlite-vec 扩展）
    #    必须在 KnowledgeManager 之前，因为 KnowledgeManager 初始化时会调用 is_vec_available()
    from infra.local_store.engine import reload_local_engine
    await reload_local_engine()
    
    # 1. Reset KnowledgeManager singleton → re-reads instance config on next use
    from services.knowledge_service import reload_knowledge_manager
    await reload_knowledge_manager()

    # 2. Reset IntentCache singleton → re-creates with new config (including EmbeddingService)
    #    不直接操作内部私有属性，避免 _embedding_service 为 None 时崩溃
    from core.routing.intent_cache import IntentSemanticCache
    IntentSemanticCache.reset_instance()

    logger.info("Semantic components reloaded")
