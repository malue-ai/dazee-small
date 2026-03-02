"""
Pipeline Tool — Agent 可调用的确定性工作流工具

让 LLM 通过 tool_use 定义并执行确定性管道，与 plan 工具互补：
- plan: LLM 驱动，每步都需 LLM 推理（灵活但 token 开销大）
- pipeline: 一次定义、确定性执行（高效，适合已知流程）

action:
- define_and_run: 定义管道并立即执行
- run_background:  定义管道并在后台执行（长任务）
- resume:          从断点恢复被暂停的管道
- status:          查询管道执行状态
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from core.tool.types import BaseTool, ToolContext
from logger import get_logger

logger = get_logger(__name__)


class PipelineTool(BaseTool):
    """
    确定性工作流管道工具

    input_schema:
        action: "define_and_run" | "run_background" | "resume" | "status"

        # define_and_run / run_background 时必需：
        pipeline:
            name: "管道名称"
            steps:
                - id: "1"
                  skill: "skill名称"         # skill / tool / code 三选一
                  tool: "tool名称"
                  code: "python代码"
                  params: { key: value }
                  depends_on: ["依赖步骤ID"]
                  approval: false            # 是否需要审批
                  timeout_seconds: 300

        # resume 时必需：
        resume_token: "恢复令牌"

        # status 时必需：
        task_id: "任务ID"
    """

    name = "pipeline"

    def __init__(self):
        self._executor_cache: Dict[str, Any] = {}

    async def execute(
        self, params: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> Dict[str, Any]:
        action = params.get("action", "")

        if action == "define_and_run":
            return await self._define_and_run(params, context)
        elif action == "run_background":
            return await self._run_background(params, context)
        elif action == "resume":
            return await self._resume(params, context)
        elif action == "status":
            return await self._status(params, context)
        else:
            return {
                "success": False,
                "error": f"未知 action: {action}，可用: define_and_run, run_background, resume, status",
            }

    async def _define_and_run(
        self, params: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> Dict[str, Any]:
        """定义管道并同步执行"""
        pipeline_data = params.get("pipeline")
        if not pipeline_data:
            return {"success": False, "error": "缺少 pipeline 定义"}

        try:
            from core.orchestration.pipeline import PipelineDefinition

            if isinstance(pipeline_data, str):
                definition = PipelineDefinition.from_yaml(pipeline_data)
            else:
                definition = PipelineDefinition.from_yaml(
                    json.dumps({"pipeline": pipeline_data}, ensure_ascii=False)
                )

            executor = await self._get_executor(context)
            initial_ctx = params.get("context", {})
            state = await executor.run(definition, initial_context=initial_ctx)

            return {
                "success": state.status.value == "completed",
                "pipeline_id": state.pipeline_id,
                "status": state.status.value,
                "progress": state.progress,
                "resume_token": state.resume_token if state.is_resumable else None,
                "steps": {
                    sid: {
                        "status": se.status.value,
                        "result": se.result[:500] if se.result else None,
                        "error": se.error,
                        "duration_ms": se.duration_ms,
                    }
                    for sid, se in state.step_executions.items()
                },
            }

        except Exception as e:
            logger.error(f"Pipeline 执行失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _run_background(
        self, params: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> Dict[str, Any]:
        """定义管道并在后台执行"""
        pipeline_data = params.get("pipeline")
        if not pipeline_data:
            return {"success": False, "error": "缺少 pipeline 定义"}

        try:
            from core.orchestration.pipeline import PipelineDefinition

            if isinstance(pipeline_data, str):
                definition = PipelineDefinition.from_yaml(pipeline_data)
            else:
                definition = PipelineDefinition.from_yaml(
                    json.dumps({"pipeline": pipeline_data}, ensure_ascii=False)
                )

            bg_manager = self._get_background_manager(context)
            if not bg_manager:
                return {
                    "success": False,
                    "error": "后台任务管理器不可用，请使用 define_and_run 同步执行",
                }

            executor = await self._get_executor(context)
            initial_ctx = params.get("context", {})

            async def run_pipeline_bg(task, manager):
                state = await executor.run(definition, initial_context=initial_ctx)
                return {
                    "pipeline_id": state.pipeline_id,
                    "status": state.status.value,
                    "progress": state.progress,
                    "resume_token": state.resume_token if state.is_resumable else None,
                }

            task = bg_manager.submit(
                name=f"Pipeline: {definition.name}",
                fn=run_pipeline_bg,
                user_id=context.user_id if context else "",
                session_id=context.session_id if context else "",
                conversation_id=context.conversation_id if context else "",
                description=definition.description,
            )

            return {
                "success": True,
                "task_id": task.task_id,
                "message": f"管道 [{definition.name}] 已提交到后台执行，共 {len(definition.steps)} 步",
            }

        except Exception as e:
            logger.error(f"Pipeline 后台提交失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _resume(
        self, params: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> Dict[str, Any]:
        """从断点恢复管道"""
        resume_token = params.get("resume_token")
        if not resume_token:
            return {"success": False, "error": "缺少 resume_token"}

        try:
            executor = await self._get_executor(context)
            state = await executor.resume(resume_token)

            if not state:
                return {"success": False, "error": "无效的 resume_token 或管道不可恢复"}

            return {
                "success": state.status.value == "completed",
                "pipeline_id": state.pipeline_id,
                "status": state.status.value,
                "progress": state.progress,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _status(
        self, params: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> Dict[str, Any]:
        """查询后台任务状态"""
        task_id = params.get("task_id")
        bg_manager = self._get_background_manager(context)

        if not bg_manager:
            return {"success": False, "error": "后台任务管理器不可用"}

        if task_id:
            task = bg_manager.get_task(task_id)
            if not task:
                return {"success": False, "error": f"任务 {task_id} 不存在"}
            return {"success": True, **task.to_dict()}

        user_id = context.user_id if context else ""
        tasks = bg_manager.get_user_tasks(user_id)
        return {
            "success": True,
            "tasks": [t.to_dict() for t in tasks[:10]],
        }

    # ================================================================
    # 内部工厂方法
    # ================================================================

    async def _get_executor(self, context: Optional[ToolContext] = None):
        """获取或创建已接入的 PipelineExecutor"""
        session_id = context.session_id if context else ""
        cache_key = session_id or "default"

        if cache_key in self._executor_cache:
            return self._executor_cache[cache_key]

        from core.orchestration.pipeline_integration import (
            create_integrated_pipeline_executor,
        )

        tool_executor = context.extra.get("tool_executor") if context else None
        session_service = context.extra.get("session_service") if context else None
        broadcaster = context.extra.get("broadcaster") if context else None
        skill_dirs = context.extra.get("skill_dirs", []) if context else []
        workspace_dir = context.extra.get("workspace_dir") if context else None

        executor = create_integrated_pipeline_executor(
            tool_executor=tool_executor,
            session_service=session_service,
            broadcaster=broadcaster,
            session_id=session_id,
            skill_dirs=[Path(d) for d in skill_dirs] if skill_dirs else [],
            workspace_dir=workspace_dir,
        )

        self._executor_cache[cache_key] = executor
        return executor

    def _get_background_manager(self, context: Optional[ToolContext] = None):
        """从上下文获取 BackgroundTaskManager"""
        if context and context.extra:
            return context.extra.get("background_task_manager")
        return None
