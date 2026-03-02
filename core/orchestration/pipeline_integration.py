"""
Pipeline 集成层 — 将 PipelineExecutor 接入现有服务

接通的调用链：
    PipelineExecutor
        ├─ StepExecutorFn  → SkillStepExecutor  → ToolExecutor / NodesTool
        ├─ ApprovalFn      → hitl_approval_adapter → SessionService.wait_hitl_confirm
        └─ ProgressFn      → progress_adapter      → EventBroadcaster.emit_progress_update

使用方式：
    executor = create_integrated_pipeline_executor(
        tool_executor=tool_executor,
        session_service=session_service,
        broadcaster=broadcaster,
        session_id=session_id,
    )
    state = await executor.run(pipeline_def)
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from logger import get_logger

from .pipeline import (
    ApprovalFn,
    ExecutionStatus,
    PipelineDefinition,
    PipelineExecutor,
    PipelineState,
    PipelineStep,
    ProgressFn,
    StepType,
)

logger = get_logger("pipeline_integration")


# ================================================================
# 1. StepExecutorFn 适配 — 对接 ToolExecutor / NodesTool
# ================================================================


class SkillStepExecutor:
    """
    Pipeline 步骤执行器

    根据 step_type 分发到对应的执行路径：
    - tool  → ToolExecutor.execute(tool_name, params)
    - code  → NodesTool 执行 Python/Shell
    - skill → 读取 SKILL.md 中的 quickstart，通过 NodesTool 执行
    """

    def __init__(
        self,
        tool_executor: Any,
        skill_dirs: Optional[List[Path]] = None,
        workspace_dir: Optional[str] = None,
    ):
        """
        Args:
            tool_executor: core.tool.executor.ToolExecutor 实例
            skill_dirs: Skill 目录列表（搜索 SKILL.md 用）
            workspace_dir: 工作目录
        """
        self.tool_executor = tool_executor
        self.skill_dirs = skill_dirs or []
        self.workspace_dir = workspace_dir

    async def __call__(
        self,
        step: PipelineStep,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """执行单个步骤，返回结果字典"""
        if step.step_type == StepType.TOOL:
            return await self._execute_tool(step, params)
        elif step.step_type == StepType.CODE:
            return await self._execute_code(step, params)
        elif step.step_type == StepType.SKILL:
            return await self._execute_skill(step, params)
        else:
            return {"success": False, "error": f"未知步骤类型: {step.step_type}"}

    async def _execute_tool(
        self, step: PipelineStep, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """通过 ToolExecutor 执行已注册的 Tool"""
        tool_name = step.tool or step.skill
        if not tool_name:
            return {"success": False, "error": "步骤未指定 tool 名称"}

        tool_input = {k: v for k, v in step.params.items() if not k.startswith("_")}

        try:
            result = await self.tool_executor.execute(
                tool_name=tool_name,
                tool_input=tool_input,
            )
            if isinstance(result, dict):
                return result
            return {"success": True, "output": str(result)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _execute_code(
        self, step: PipelineStep, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """通过 NodesTool 执行代码"""
        code = step.code
        if not code:
            return {"success": False, "error": "步骤未指定 code"}

        try:
            result = await self.tool_executor.execute(
                tool_name="nodes",
                tool_input={
                    "action": "run",
                    "command": ["python3", "-c", code],
                    "timeout_ms": step.timeout_seconds * 1000,
                },
            )
            return result if isinstance(result, dict) else {"success": True, "output": str(result)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _execute_skill(
        self, step: PipelineStep, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        执行 Skill：
        1. 找到 SKILL.md
        2. 提取 quickstart 代码片段
        3. 替换参数占位符
        4. 通过 NodesTool 执行
        """
        skill_name = step.skill
        if not skill_name:
            return {"success": False, "error": "步骤未指定 skill 名称"}

        skill_md_path = self._find_skill_md(skill_name)
        if not skill_md_path:
            return {
                "success": False,
                "error": f"未找到 Skill: {skill_name}",
            }

        try:
            content = skill_md_path.read_text(encoding="utf-8")
            code = self._extract_executable_code(content, step.params)
            if not code:
                return {
                    "success": False,
                    "error": f"Skill {skill_name} 中未找到可执行代码",
                    "skill_path": str(skill_md_path),
                }

            result = await self.tool_executor.execute(
                tool_name="nodes",
                tool_input={
                    "action": "run",
                    "command": ["python3", "-c", code],
                    "timeout_ms": step.timeout_seconds * 1000,
                },
            )
            return result if isinstance(result, dict) else {"success": True, "output": str(result)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _find_skill_md(self, skill_name: str) -> Optional[Path]:
        """在多个目录中搜索 SKILL.md"""
        for skill_dir in self.skill_dirs:
            candidate = skill_dir / skill_name / "SKILL.md"
            if candidate.exists():
                return candidate
        return None

    def _extract_executable_code(
        self, skill_content: str, params: Dict[str, Any]
    ) -> Optional[str]:
        """从 SKILL.md 提取第一个 python 代码块并替换参数"""
        import re

        pattern = r"```python\n(.*?)```"
        matches = re.findall(pattern, skill_content, re.DOTALL)
        if not matches:
            return None

        code = matches[0].strip()
        for key, value in params.items():
            if key.startswith("_"):
                continue
            placeholder = f'"{{{key}}}"'
            code = code.replace(placeholder, json.dumps(value, ensure_ascii=False))
            code = code.replace(f"{{{key}}}", str(value))

        return code


# ================================================================
# 2. ApprovalFn 适配 — 对接 SessionService.wait_hitl_confirm
# ================================================================


def create_hitl_approval_adapter(
    session_service: Any,
    broadcaster: Any,
    session_id: str,
) -> ApprovalFn:
    """
    创建 HITL 审批适配器

    将 Pipeline 的 ApprovalFn(step, message) -> bool
    适配到 SessionService.wait_hitl_confirm(session_id) -> "approve"/"reject"

    Args:
        session_service: services.session_service.SessionService 实例
        broadcaster: core.events.broadcaster.EventBroadcaster 实例
        session_id: 当前会话 ID
    """

    async def approval_fn(step: PipelineStep, message: str) -> bool:
        approval_msg = (
            f"Pipeline 步骤需要确认\n\n"
            f"步骤: {step.name} (ID: {step.id})\n"
            f"说明: {message}\n\n"
            f"是否继续执行？"
        )

        try:
            if broadcaster:
                await broadcaster.events.system.emit_custom(
                    session_id=session_id,
                    conversation_id=getattr(broadcaster, "output_conversation_id", ""),
                    event_type="hitl_confirm",
                    event_data={
                        "type": "pipeline_approval",
                        "step_id": step.id,
                        "step_name": step.name,
                        "message": approval_msg,
                    },
                    output_format=getattr(broadcaster, "output_format", "sse"),
                )
        except Exception as e:
            logger.warning(f"发送审批事件失败: {e}")

        result = await session_service.wait_hitl_confirm(
            session_id=session_id,
            timeout=step.approval.timeout_seconds,
        )
        approved = result == "approve"
        logger.info(f"Pipeline 审批结果: step={step.id}, approved={approved}")
        return approved

    return approval_fn


# ================================================================
# 3. ProgressFn 适配 — 对接 EventBroadcaster.emit_progress_update
# ================================================================


def create_progress_adapter(
    broadcaster: Any,
    session_id: str,
) -> ProgressFn:
    """
    创建进度事件适配器

    将 Pipeline 的 ProgressFn(state, step, status)
    适配到 EventBroadcaster.emit_progress_update(session_id, step_id, message, percent)
    """

    async def progress_fn(
        state: PipelineState,
        step: PipelineStep,
        status: ExecutionStatus,
    ) -> None:
        status_labels = {
            ExecutionStatus.RUNNING: "执行中",
            ExecutionStatus.COMPLETED: "已完成",
            ExecutionStatus.FAILED: "失败",
            ExecutionStatus.WAITING_APPROVAL: "等待确认",
        }
        message = f"[{step.name}] {status_labels.get(status, status.value)}"

        try:
            await broadcaster.emit_progress_update(
                session_id=session_id,
                step_id=step.id,
                message=message,
                percent=state.progress,
            )
        except Exception as e:
            logger.debug(f"发送进度事件失败: {e}")

    return progress_fn


# ================================================================
# 4. 工厂函数 — 组装完整的 Pipeline Executor
# ================================================================


def create_integrated_pipeline_executor(
    tool_executor: Any,
    session_service: Any = None,
    broadcaster: Any = None,
    session_id: str = "",
    skill_dirs: Optional[List[Path]] = None,
    workspace_dir: Optional[str] = None,
    storage_dir: Optional[Path] = None,
) -> PipelineExecutor:
    """
    创建已接入现有服务的 Pipeline Executor（一行调用，全链路就绪）

    Args:
        tool_executor: ToolExecutor 实例（必需）
        session_service: SessionService 实例（提供 HITL 审批，可选）
        broadcaster: EventBroadcaster 实例（提供进度事件，可选）
        session_id: 会话 ID
        skill_dirs: Skill 目录列表
        workspace_dir: 工作目录
        storage_dir: Pipeline 状态存储目录

    Returns:
        已连接的 PipelineExecutor
    """
    step_executor = SkillStepExecutor(
        tool_executor=tool_executor,
        skill_dirs=skill_dirs or [],
        workspace_dir=workspace_dir,
    )

    approval_fn = None
    if session_service and session_id:
        approval_fn = create_hitl_approval_adapter(
            session_service=session_service,
            broadcaster=broadcaster,
            session_id=session_id,
        )

    progress_fn = None
    if broadcaster and session_id:
        progress_fn = create_progress_adapter(
            broadcaster=broadcaster,
            session_id=session_id,
        )

    return PipelineExecutor(
        step_executor=step_executor,
        approval_fn=approval_fn,
        progress_fn=progress_fn,
        storage_dir=storage_dir,
    )
