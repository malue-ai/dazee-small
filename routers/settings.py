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

from logger import get_logger
from services.settings_service import (
    get_embedding_status,
    get_settings,
    get_settings_schema,
    get_settings_status,
    update_settings,
)

logger = get_logger("settings_router")

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

    # API Key 变更后热重载所有 Agent（使新 provider/model 生效）
    if "api_keys" in body:
        # 清除 Mem0 config 缓存，下次初始化时重新检测 embedding provider
        try:
            from core.memory.mem0.config import set_mem0_config
            set_mem0_config(None)
            logger.info("🔄 Mem0 embedding 配置缓存已清除，将随 API Key 自动重新检测")
        except Exception:
            pass

        try:
            from services.agent_registry import get_agent_registry
            registry = get_agent_registry()
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
    - 是否已安装本地模型
    - 是否可用 OpenAI 云端
    - 安装提示和推荐方案
    """
    return {
        "success": True,
        "data": await get_embedding_status(),
    }
