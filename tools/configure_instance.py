"""
实例级配置工具（HITL 持久化到本地 SQLite）

Agent 在对话中通过此工具将用户提供的配置持久化到本地 SQLite：
  - credential: 服务 API Key（如 UNSTRUCTURED_API_KEY, TAVILY_API_KEY）
  - package:    已安装包（如 pdfplumber 0.11.4）
  - permission: OS 权限（如 accessibility granted）
  - setting:    工具/Skill 配置项
"""

import os
from typing import Any, Dict

from core.tool.types import BaseTool, ToolContext
from logger import get_logger

logger = get_logger(__name__)


class ConfigureInstanceTool(BaseTool):
    """将实例级配置持久化到本地 SQLite（按实例隔离）。"""

    name = "configure_instance"

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        category = (params.get("category") or "").strip()
        key = (params.get("key") or "").strip()
        value = (params.get("value") or "").strip()
        skill_name = (params.get("skill_name") or "").strip()
        instance_id = (context.instance_id or os.getenv("AGENT_INSTANCE") or "").strip()

        if not category:
            return {"success": False, "error": "缺少参数: category"}
        if not key:
            return {"success": False, "error": "缺少参数: key"}
        if not instance_id:
            return {"success": False, "error": "无法确定当前实例"}

        try:
            from infra.local_store.engine import get_local_session_factory
            from infra.local_store import instance_config_store

            if category not in instance_config_store.VALID_CATEGORIES:
                return {
                    "success": False,
                    "error": f"无效品类 '{category}'，支持: {', '.join(sorted(instance_config_store.VALID_CATEGORIES))}",
                }

            factory = await get_local_session_factory()
            async with factory() as session:
                await instance_config_store.upsert(
                    session,
                    instance_id,
                    category,
                    key,
                    value,
                    skill_name=skill_name,
                    source="hitl",
                )

            if category == "credential" and value:
                os.environ[key] = value

            label_map = {
                "credential": "API Key",
                "package": "安装包记录",
                "permission": "权限状态",
                "setting": "配置项",
            }
            return {
                "success": True,
                "message": f"已保存{label_map.get(category, '配置')} {key}，后续会话将自动生效。",
                "instance_id": instance_id,
                "category": category,
                "key": key,
            }
        except Exception as e:
            logger.exception("configure_instance 失败")
            return {"success": False, "error": str(e)}
