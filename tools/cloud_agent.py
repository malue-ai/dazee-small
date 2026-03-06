"""
云端 Agent 工具

将任务委托给云端 ZenFlux Agent 执行，实时推送进度到本地界面。
Phase 1: 通过 CloudClient.chat_stream_with_tracking() 消费 SSE，
本地 TaskManager 追踪任务状态，cloud_progress content_block 桥接到前端。
"""

import json
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
        # 兼容 LLM 有时使用 prompt / query / message 作为参数名
        task = (
            params.get("task")
            or params.get("prompt")
            or params.get("query")
            or params.get("message")
            or ""
        ).strip()
        if not task:
            return {"success": False, "error": "task 参数不能为空"}

        extra_context = params.get("context", "")
        message = f"{task}\n\n{extra_context}".strip() if extra_context else task

        broadcaster = await self._get_broadcaster(context)
        session_id = context.session_id if context else ""
        user_id = context.user_id if context else "local_agent"

        logger.info(
            f"cloud_agent 启动: session_id={session_id[:8] if session_id else '空'}, "
            f"broadcaster={'有' if broadcaster else '无'}, "
            f"event_manager={'有' if (context and context.event_manager) else '无'}"
        )

        _block_idx = 100
        _steps: List[Dict[str, str]] = []
        _block_started = False

        task_id: Optional[str] = None
        task_mgr = None
        db_session = None
        start_time = time.time()

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

            # --- content_start: 创建 cloud_progress 块 ---
            _steps.append({"id": "connect", "label": "正在连接云端 Agent...", "status": "done"})
            await self._cloud_block_start(broadcaster, session_id, _block_idx, task_id, _steps)
            _block_started = True

            files_from_params = params.get("files") or []
            files_from_context = (context.extra.get("files") if context else None) or []
            files = files_from_params + files_from_context if (files_from_params or files_from_context) else None
            if files:
                files = await self._upload_local_files(client, files, user_id)

            if task_mgr and db_session and task_id:
                await task_mgr.update_status(db_session, task_id, "streaming")

            final_text = ""

            async for evt in client.chat_stream_with_tracking(
                message=message,
                user_id=user_id,
                files=files,
            ):
                elapsed_ms = int((time.time() - start_time) * 1000)

                if evt.kind == "session_info" and evt.conversation_id:
                    if task_mgr and db_session and task_id:
                        await task_mgr.update_status(
                            db_session, task_id, "streaming",
                            cloud_conversation_id=evt.conversation_id,
                        )

                elif evt.kind == "tool_start":
                    _steps.append({
                        "id": f"tool_{len(_steps)}",
                        "label": f"云端调用: {evt.tool_name}",
                        "status": "running",
                    })
                    await self._cloud_block_delta(
                        broadcaster, session_id, _block_idx, _steps, "running", elapsed_ms,
                    )
                    if task_mgr and db_session and task_id:
                        await task_mgr.add_progress_step(db_session, task_id, {
                            "tool": evt.tool_name, "status": "running",
                            "started_at": time.time(),
                        })

                elif evt.kind == "tool_end":
                    for s in _steps:
                        if s["status"] == "running":
                            s["status"] = "done"
                    await self._cloud_block_delta(
                        broadcaster, session_id, _block_idx, _steps, "running", elapsed_ms,
                    )

                elif evt.kind == "thinking_start":
                    _steps.append({
                        "id": f"think_{len(_steps)}",
                        "label": "云端思考中...",
                        "status": "running",
                    })
                    await self._cloud_block_delta(
                        broadcaster, session_id, _block_idx, _steps, "running", elapsed_ms,
                    )

                elif evt.kind == "text_delta":
                    final_text += evt.text

                elif evt.kind == "completed":
                    break

            elapsed_ms = int((time.time() - start_time) * 1000)

            if not final_text:
                for s in _steps:
                    if s["status"] == "running":
                        s["status"] = "done"
                _steps.append({"id": "error", "label": "云端未返回有效文本", "status": "done"})
                await self._cloud_block_delta(
                    broadcaster, session_id, _block_idx, _steps, "failed", elapsed_ms,
                )
                await self._cloud_block_stop(broadcaster, session_id, _block_idx)
                _block_started = False
                if task_mgr and db_session and task_id:
                    await task_mgr.update_status(
                        db_session, task_id, "failed", error_message="云端未返回有效文本",
                    )
                return {"success": False, "error": "云端未返回有效文本", "task_id": task_id}

            # 成功：标记所有 running steps 为 done
            for s in _steps:
                if s["status"] == "running":
                    s["status"] = "done"
            _steps.append({"id": "done", "label": "云端任务完成", "status": "done"})
            await self._cloud_block_delta(
                broadcaster, session_id, _block_idx, _steps, "completed", elapsed_ms,
            )
            await self._cloud_block_stop(broadcaster, session_id, _block_idx)
            _block_started = False

            if task_mgr and db_session and task_id:
                await task_mgr.update_status(
                    db_session, task_id, "completed", result_summary=final_text[:3000],
                )

            return {
                "success": True,
                "result": final_text,
                "task_id": task_id,
                "_compression_hint": "skip",
            }

        except Exception as e:
            error_msg = str(e)
            logger.error("cloud_agent 执行失败: %s", error_msg, exc_info=True)
            if _block_started:
                elapsed_ms = int((time.time() - start_time) * 1000)
                _steps.append({"id": "error", "label": f"失败: {error_msg[:80]}", "status": "done"})
                await self._cloud_block_delta(
                    broadcaster, session_id, _block_idx, _steps, "failed", elapsed_ms,
                )
                await self._cloud_block_stop(broadcaster, session_id, _block_idx)
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

    # ------------------------------------------------------------------
    # cloud_progress content_block 事件（前端 CloudProgressCard 消费）
    # ------------------------------------------------------------------

    async def _cloud_block_start(
        self, broadcaster, session_id: str, index: int,
        task_id: Optional[str], steps: List[Dict[str, str]],
    ):
        if not broadcaster or not session_id:
            logger.warning(
                f"cloud_progress 跳过: broadcaster={'无' if not broadcaster else '有'}, "
                f"session_id={session_id or '空'}"
            )
            return
        try:
            logger.info(f"cloud_progress content_start: index={index}, session={session_id[:8]}")
            await broadcaster.emit_content_start(
                session_id=session_id, index=index,
                content_block={
                    "type": "cloud_progress",
                    "taskId": task_id or "",
                    "status": "connecting",
                    "title": "云端执行中",
                    "steps": steps,
                },
            )
        except Exception as e:
            logger.warning("cloud_progress content_start 失败: %s", e)

    async def _cloud_block_delta(
        self, broadcaster, session_id: str, index: int,
        steps: List[Dict[str, str]], status: str, elapsed_ms: int,
    ):
        """发送 content_delta 更新 cloud_progress 块"""
        if not broadcaster or not session_id:
            return
        try:
            delta_json = json.dumps(
                {"steps": steps, "status": status, "elapsedMs": elapsed_ms},
                ensure_ascii=False,
            )
            await broadcaster.emit_content_delta(
                session_id=session_id, index=index, delta=delta_json,
            )
        except Exception as e:
            logger.debug("cloud_progress content_delta 失败: %s", e)

    async def _cloud_block_stop(self, broadcaster, session_id: str, index: int):
        """发送 content_stop 结束 cloud_progress 块"""
        if not broadcaster or not session_id:
            return
        try:
            await broadcaster.emit_content_stop(session_id=session_id, index=index)
        except Exception as e:
            logger.debug("cloud_progress content_stop 失败: %s", e)

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

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
