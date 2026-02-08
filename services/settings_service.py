"""
设置服务 - Settings Service

统一管理应用配置，开发和生产环境均使用 config.yaml。
配置存储在 {user_data_dir}/config.yaml。

核心功能：
- 加载 config.yaml 并注入 os.environ（向后兼容 os.getenv()）
- 提供 REST API 给前端设置页面读写
- API Key 原文返回（桌面端本地运行，无需脱敏）
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
import yaml

from logger import get_logger
from utils.app_paths import get_bundle_dir, get_user_config_path

logger = get_logger("settings_service")


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

# 必填配置项（至少需要一个 LLM API Key）
REQUIRED_KEYS = ["ANTHROPIC_API_KEY"]

# 可选配置项（按分组）
SETTINGS_SCHEMA = {
    "api_keys": {
        "ANTHROPIC_API_KEY": {"label": "Anthropic API Key", "required": True, "secret": True},
        "ANTHROPIC_BASE_URL": {"label": "Anthropic Base URL", "required": False, "secret": False},
        "OPENAI_API_KEY": {"label": "OpenAI API Key", "required": False, "secret": True},
        "OPENAI_BASE_URL": {"label": "OpenAI Base URL", "required": False, "secret": False},
        "DASHSCOPE_API_KEY": {"label": "DashScope API Key", "required": False, "secret": True},
        "GEMINI_API_KEY": {"label": "Gemini API Key", "required": False, "secret": True},
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

# 缓存
_settings_cache: Optional[Dict[str, Any]] = None


# ==================== 核心加载函数 ====================


def load_config_to_env() -> None:
    """
    从 config.yaml 加载配置并注入 os.environ。

    若 config.yaml 不存在或未提供 API Key，则回退加载项目根目录 .env，
    保证开发时用 .env 配置 ANTHROPIC_API_KEY 仍能生效。
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

    # 若注入后仍无 ANTHROPIC_API_KEY，回退到 .env（兼容仅用 .env 的开发方式）
    if not os.environ.get("ANTHROPIC_API_KEY"):
        _load_dotenv_fallback()

    if injected_count > 0:
        logger.info(f"从 config.yaml 注入 {injected_count} 个环境变量")


def _load_settings() -> Dict[str, Any]:
    """加载配置文件内容（带缓存）"""
    global _settings_cache
    if _settings_cache is not None:
        return _settings_cache

    config_path = get_user_config_path()
    if not config_path.exists():
        _settings_cache = {}
        return _settings_cache

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            _settings_cache = yaml.safe_load(f) or {}
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
    settings = _load_settings()
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
    settings = _load_settings()

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
    settings = _load_settings()
    missing = []

    for key in REQUIRED_KEYS:
        # 从配置文件和环境变量两个来源检查
        found = False
        for group_data in settings.values():
            if isinstance(group_data, dict) and group_data.get(key):
                found = True
                break
        if not found and not os.getenv(key):
            missing.append(key)

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
        "configured": len(missing) == 0,
        "missing": missing,
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
    settings = _load_settings()
    knowledge_settings = settings.get("knowledge", {})

    semantic_enabled = str(
        knowledge_settings.get("SEMANTIC_SEARCH_ENABLED", "false")
    ).lower() in ("true", "1", "yes")
    provider_setting = knowledge_settings.get("EMBEDDING_PROVIDER", "auto")

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

    # Determine current effective provider
    current_provider = None
    if semantic_enabled:
        if provider_setting == "auto":
            if local_available:
                current_provider = "local"
            elif openai_available:
                current_provider = "openai"
        elif provider_setting == "local" and local_available:
            current_provider = "local"
        elif provider_setting == "openai" and openai_available:
            current_provider = "openai"

    # Recommendation for user
    if local_available and local_backend == "gguf":
        recommendation = "已安装本地模型（GGUF），语义搜索离线可用"
    elif local_available and local_backend == "sentence-transformers":
        recommendation = "已安装本地模型（sentence-transformers），语义搜索离线可用"
    elif openai_available:
        recommendation = "可使用 OpenAI 云端语义搜索。安装本地模型可离线使用"
    else:
        recommendation = "安装本地模型即可启用语义搜索（离线可用，424MB）"

    # Model storage location (shared across instances)
    from utils.app_paths import get_shared_models_dir
    models_dir = str(get_shared_models_dir())

    return {
        "semantic_enabled": semantic_enabled,
        "current_provider": current_provider,
        "provider_setting": provider_setting,
        "local_available": local_available,
        "local_backend": local_backend,
        "openai_available": openai_available,
        "local_install_hint": "pip install llama-cpp-python",
        "local_model_name": "BGE-M3 Q4 (GGUF)",
        "local_model_size": "424MB",
        "local_model_description": "中英文双语，MIT 开源，首次使用自动下载",
        "models_dir": models_dir,
        "recommendation": recommendation,
    }
