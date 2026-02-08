"""
设置 API 路由

提供桌面应用配置管理的 REST API：
- GET  /api/v1/settings         — 读取配置（API Key 脱敏）
- PUT  /api/v1/settings         — 更新配置
- GET  /api/v1/settings/status  — 检查配置状态
- GET  /api/v1/settings/schema  — 获取配置项定义
"""

from typing import Any, Dict

from fastapi import APIRouter

from services.settings_service import (
    get_embedding_status,
    get_settings,
    get_settings_schema,
    get_settings_status,
    update_settings,
)

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


@router.get("")
async def read_settings() -> Dict[str, Any]:
    """
    获取当前配置

    API Key 等敏感字段会脱敏返回（如 "sk-ant...xxxx"）
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
