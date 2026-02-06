"""
特殊工具处理器

提供 plan_todo、request_human_confirmation 等特殊工具的处理逻辑。

迁移自：core/agent/simple/simple_agent_tools.py
"""

from typing import Any, Dict, Optional

from core.agent.tools.flow import (
    SpecialToolHandler,
    ToolExecutionContext,
    ToolExecutionResult,
)
from logger import get_logger

logger = get_logger(__name__)


class PlanTodoHandler(SpecialToolHandler):
    """
    Plan Todo 工具处理器

    处理 plan_todo 工具的执行和 plan_cache 更新。
    """

    @property
    def tool_name(self) -> str:
        return "plan"

    async def execute(
        self, tool_input: Dict[str, Any], context: ToolExecutionContext, tool_id: str
    ) -> ToolExecutionResult:
        """
        执行 plan

        Args:
            tool_input: 工具输入参数
            context: 执行上下文
            tool_id: 工具调用 ID

        Returns:
            执行结果
        """
        try:
            if not context.tool_executor:
                raise ValueError("tool_executor 未配置")
            if not context.conversation_id:
                raise ValueError("conversation_id 为空，无法存储计划")

            # 直接通过 ToolExecutor 执行（PlanTool 会自行持久化到 Conversation.metadata.plan）
            result = await context.tool_executor.execute(self.tool_name, tool_input)

            # 更新 plan 缓存
            action = tool_input.get("action", "unknown")
            if result.get("success") and "plan" in result:
                context.plan_cache["plan"] = result.get("plan")
                logger.info(f"📋 Plan 操作完成: {action}")

            return ToolExecutionResult(
                tool_id=tool_id,
                tool_name=self.tool_name,
                tool_input=tool_input,
                result=result,
                is_error=False,
            )

        except Exception as e:
            logger.error(f"❌ plan 执行失败: {e}")
            return ToolExecutionResult(
                tool_id=tool_id,
                tool_name=self.tool_name,
                tool_input=tool_input,
                result={"error": str(e), "success": False},
                is_error=True,
                error_msg=str(e),
            )


class HumanConfirmationHandler(SpecialToolHandler):
    """
    HITL (Human-in-the-Loop) 确认工具处理器

    处理 request_human_confirmation 工具的执行。
    """

    @property
    def tool_name(self) -> str:
        return "request_human_confirmation"

    async def execute(
        self, tool_input: Dict[str, Any], context: ToolExecutionContext, tool_id: str
    ) -> ToolExecutionResult:
        """
        处理 HITL 确认请求

        流程：
        1. 解析工具输入，创建 ConfirmationRequest
        2. 通过 EventBroadcaster 发送 SSE 事件到前端
        3. 等待用户通过 HTTP POST 响应
        4. 返回结果给 Agent

        Args:
            tool_input: 工具输入参数
            context: 执行上下文
            tool_id: 工具调用 ID

        Returns:
            确认结果
        """
        import json

        from services.confirmation_service import ConfirmationType, get_confirmation_manager

        try:
            # 解析参数
            question = tool_input.get("question", "")
            confirmation_type_str = tool_input.get("confirmation_type", "yes_no")
            options = tool_input.get("options")
            default_value = tool_input.get("default_value")
            questions = tool_input.get("questions")  # form 类型
            description = tool_input.get("description", "")
            timeout = tool_input.get("timeout", 60)

            # 解析确认类型
            try:
                conf_type = ConfirmationType(confirmation_type_str)
            except ValueError:
                conf_type = ConfirmationType.YES_NO

            # yes_no 类型使用默认选项
            if conf_type == ConfirmationType.YES_NO and not options:
                options = ["confirm", "cancel"]

            # form 类型给更多时间
            if conf_type == ConfirmationType.FORM and timeout == 60:
                timeout = 120

            logger.info(f"🤝 HITL 请求: type={confirmation_type_str}, question={question[:50]}...")

            # 创建确认请求
            manager = get_confirmation_manager()

            metadata = {}
            if description:
                metadata["description"] = description
            if default_value is not None:
                metadata["default_value"] = default_value
            if conf_type == ConfirmationType.FORM:
                metadata["form_type"] = "form"
                metadata["questions"] = questions or []

            request = manager.create_request(
                question=question,
                options=options,
                timeout=timeout,
                confirmation_type=conf_type,
                session_id=context.session_id,
                metadata=metadata,
            )

            logger.info(f"✅ 确认请求已创建: request_id={request.request_id}")

            # 发送 SSE 事件到前端
            if context.broadcaster:
                await context.broadcaster.emit_confirmation_request(
                    session_id=context.session_id,
                    request_id=request.request_id,
                    question=question,
                    options=options,
                    confirmation_type=confirmation_type_str,
                    timeout=timeout,
                    description=description,
                    questions=questions if conf_type == ConfirmationType.FORM else None,
                    metadata=metadata,
                )

            # 等待用户响应
            result = await manager.wait_for_response(request.request_id, timeout)

            # 处理结果
            if result.get("timed_out"):
                logger.warning(f"⏰ 用户响应超时 ({timeout}s)")
                return ToolExecutionResult(
                    tool_id=tool_id,
                    tool_name=self.tool_name,
                    tool_input=tool_input,
                    result={
                        "success": False,
                        "timed_out": True,
                        "response": "timeout",
                        "message": f"用户未在 {timeout} 秒内响应",
                    },
                    is_error=False,  # 超时不是错误
                )

            response = result.get("response")

            # form 类型：尝试解析 JSON
            if conf_type == ConfirmationType.FORM and isinstance(response, str):
                try:
                    response = json.loads(response)
                except json.JSONDecodeError:
                    logger.warning(
                        f"无法解析 form 响应为 JSON: {response[:100] if response else ''}"
                    )

            logger.info(f"✅ 用户已响应: {type(response).__name__}")

            return ToolExecutionResult(
                tool_id=tool_id,
                tool_name=self.tool_name,
                tool_input=tool_input,
                result={
                    "success": True,
                    "timed_out": False,
                    "response": response,
                    "metadata": result.get("metadata", {}),
                },
                is_error=False,
            )

        except Exception as e:
            logger.error(f"❌ HITL 处理失败: {e}")
            return ToolExecutionResult(
                tool_id=tool_id,
                tool_name=self.tool_name,
                tool_input=tool_input,
                result={"error": str(e), "success": False},
                is_error=True,
                error_msg=str(e),
            )
