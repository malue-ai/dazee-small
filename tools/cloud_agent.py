"""
云端 Agent 工具

将任务委托给云端 ZenFlux Agent 执行，实时推送进度到本地界面。
Phase 1: 通过 CloudClient.chat_stream_with_tracking() 消费 SSE，
本地 TaskManager 追踪任务状态，结构化 cloud_progress 事件桥接到前端。
"""

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.tool.types import BaseTool, ToolContext
from logger import get_logger

logger = get_logger(__name__)


class CloudAgentTool(BaseTool):
    """将任务委托给云端 Agent 执行"""

    name = "cloud_agent"
    description = "将任务委托给云端 Agent 执行，适用于深度调研、沙箱代码执行、持续运行等本地不擅长的场景"
    execution_timeout = 600
    input_schema = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "委托给云端的任务描述",
            },
            "context": {
                "type": "string",
                "description": "相关上下文信息（可选）",
            },
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "file_url": {"type": "string", "description": "文件路径或 URL"},
                        "file_name": {"type": "string", "description": "文件名"},
                        "file_type": {"type": "string", "description": "MIME 类型"},
                    },
                },
                "description": "附件列表（PDF/Excel/CSV/图片等），本地文件会自动上传到云端",
            },
        },
        "required": ["task"],
    }

    async def execute(
        self, params: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> Dict[str, Any]:
        task = params.get("task", "").strip()
        if not task:
            return {"success": False, "error": "task 参数不能为空"}

        extra_context = params.get("context", "")
        message = f"{task}\n\n{extra_context}".strip() if extra_context else task

        broadcaster = await self._get_broadcaster(context)
        session_id = context.session_id if context else ""
        user_id = context.user_id if context else "local_agent"

        await self._emit_progress(broadcaster, session_id, "cloud_connect", "正在连接云端 Agent...")

        task_id: Optional[str] = None
        task_mgr = None
        db_session = None

        try:
            from services.cloud_client import CloudClientError, get_cloud_client_for_instance

            instance_id = (context.instance_id if context else "") or ""
            client = await get_cloud_client_for_instance(instance_id)
            if client is None:
                return {
                    "success": False,
                    "error": "当前实例未开启云端协同。请在实例 config.yaml 中配置 cloud.enabled: true",
                }

            healthy = await client.health_check()
            if not healthy:
                return {"success": False, "error": "云端 Agent 不可达，请检查网络连接"}

            task_mgr, db_session = await self._init_task_tracking(context)
            if task_mgr and db_session:
                cloud_task = await task_mgr.create_task(db_session, task, user_id)
                task_id = cloud_task.id

            await self._emit_progress(
                broadcaster, session_id, "cloud_start", "云端 Agent 开始处理...",
                task_id=task_id,
            )

            files_from_params = params.get("files") or []
            files_from_context = (context.extra.get("files") if context else None) or []
            files = files_from_params + files_from_context if (files_from_params or files_from_context) else None
            if files:
                files = await self._upload_local_files(client, files, user_id)

            if task_mgr and db_session and task_id:
                await task_mgr.update_status(db_session, task_id, "streaming")

            final_text = ""
            start_time = time.time()

            async for evt in client.chat_stream_with_tracking(
                message=message,
                user_id=user_id,
                files=files,
            ):
                if evt.kind == "session_info" and evt.conversation_id:
                    if task_mgr and db_session and task_id:
                        await task_mgr.update_status(
                            db_session, task_id, "streaming",
                            cloud_conversation_id=evt.conversation_id,
                        )

                elif evt.kind == "tool_start":
                    await self._emit_progress(
                        broadcaster, session_id, "cloud_tool",
                        f"云端调用工具: {evt.tool_name}",
                        task_id=task_id, tool_name=evt.tool_name, status="running",
                    )
                    if task_mgr and db_session and task_id:
                        await task_mgr.add_progress_step(db_session, task_id, {
                            "tool": evt.tool_name, "status": "running",
                            "started_at": time.time(),
                        })

                elif evt.kind == "tool_end":
                    await self._emit_progress(
                        broadcaster, session_id, "cloud_tool_done",
                        f"云端工具 {evt.tool_name} 执行完成",
                        task_id=task_id, tool_name=evt.tool_name, status="done",
                    )

                elif evt.kind == "thinking_start":
                    await self._emit_progress(
                        broadcaster, session_id, "cloud_thinking", "云端思考中...",
                        task_id=task_id,
                    )

                elif evt.kind == "text_delta":
                    final_text += evt.text

                elif evt.kind == "completed":
                    break

            elapsed_ms = int((time.time() - start_time) * 1000)

            if not final_text:
                if task_mgr and db_session and task_id:
                    await task_mgr.update_status(
                        db_session, task_id, "failed",
                        error_message="云端未返回有效文本",
                    )
                return {"success": False, "error": "云端未返回有效文本", "task_id": task_id}

            if task_mgr and db_session and task_id:
                await task_mgr.update_status(
                    db_session, task_id, "completed",
                    result_summary=final_text[:3000],
                )

            await self._emit_progress(
                broadcaster, session_id, "cloud_done", "云端任务完成",
                task_id=task_id, elapsed_ms=elapsed_ms,
            )

            return {"success": True, "result": final_text, "task_id": task_id}

        except Exception as e:
            error_msg = str(e)
            logger.error("cloud_agent 执行失败: %s", error_msg, exc_info=True)
            if task_mgr and db_session and task_id:
                try:
                    await task_mgr.update_status(
                        db_session, task_id, "failed", error_message=error_msg[:500],
                    )
                except Exception:
                    pass
            return {"success": False, "error": f"云端执行失败: {error_msg}", "task_id": task_id}
        finally:
            if db_session:
                try:
                    await db_session.close()
                except Exception:
                    pass

    # --- 内部方法 ---

    async def _init_task_tracking(self, context: Optional[ToolContext]):
        """初始化任务追踪（graceful：workspace 不可用时返回 None）"""
        try:
            from core.cloud.task_manager import CloudTaskManager
            from infra.local_store import get_workspace

            instance_id = context.instance_id if context else ""
            if not instance_id:
                return None, None

            workspace = await get_workspace(instance_id)
            session = workspace.session()
            return CloudTaskManager(), session
        except Exception as e:
            logger.debug("任务追踪初始化失败（不影响执行）: %s", e)
            return None, None

    async def _upload_local_files(
        self, client, files: List[Dict[str, Any]], user_id: str,
    ) -> List[Dict[str, Any]]:
        """将本地文件上传到云端 S3，替换为可访问的预签名 URL"""
        uploaded: List[Dict[str, Any]] = []
        for f in files:
            file_url = f.get("file_url", "")
            if not file_url or file_url.startswith("http"):
                uploaded.append(f)
                continue

            local_path = Path(file_url)
            if not local_path.exists():
                logger.warning("本地文件不存在，跳过上传: %s", file_url)
                uploaded.append(f)
                continue

            try:
                content = local_path.read_bytes()
                result = await client.upload_file(
                    file_content=content,
                    filename=f.get("file_name") or local_path.name,
                    mime_type=f.get("file_type") or "application/octet-stream",
                    user_id=user_id,
                )
                uploaded.append(result)
            except Exception as e:
                logger.error("上传本地文件到云端失败: %s, %s", file_url, e, exc_info=True)
                uploaded.append(f)

        return uploaded

    async def _get_broadcaster(self, context: Optional[ToolContext]):
        if not context or not context.event_manager:
            return None
        try:
            from core.events.broadcaster import EventBroadcaster
            return EventBroadcaster(context.event_manager)
        except Exception:
            return None

    async def _emit_progress(
        self,
        broadcaster,
        session_id: str,
        step_id: str,
        message: str,
        *,
        task_id: Optional[str] = None,
        tool_name: str = "",
        status: str = "",
        elapsed_ms: int = 0,
    ):
        if not broadcaster or not session_id:
            return
        try:
            await broadcaster.emit_progress_update(
                session_id=session_id,
                step_id=step_id,
                message=message,
            )
        except Exception as e:
            logger.debug("进度事件发送失败（不影响执行）: %s", e)
