"""
线索生成工具 - 接收并格式化操作建议

当 Agent 判断当前对话需要给用户提供后续操作建议时，主动调用此工具。
Agent 直接传入已生成的线索列表，工具负责验证和格式化。

使用场景：
- 完成了用户的主要任务后，提供延伸操作建议
- 对话中存在需要用户确认、回复或上传文件的情况
- 助手给出了可转发/分享的内容时
- 用户的问题需要后续跟进操作

操作类型（act）：
- reply: 需要用户回复确认的问题
- forward: 可以转发/分享的内容
- confirm: 需要用户确认的配置或操作
- upload: 需要用户上传文件
"""

from typing import Any, Dict, List

from core.tool.types import BaseTool, ToolContext
from logger import get_logger

logger = get_logger(__name__)


class ClueGenerationTool(BaseTool):
    """
    线索生成工具

    Agent 直接传入已生成的线索列表，工具负责验证和格式化。
    不再内部调用 LLM，减少延迟和成本。

    工具只负责返回结果数据。
    """

    name = "clue_generation"

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        """
        执行线索格式化和验证

        Args:
            params: 工具输入参数
                - tasks: Agent 生成的线索列表，每个线索包含：
                    - text: 线索描述（必填）
                    - act: 操作类型 reply|forward|confirm|upload（可选，默认 reply）
                    - id: 线索 ID（可选，自动生成）
                    - payload: 附加数据（可选）
            context: 工具执行上下文

        Returns:
            验证后的线索数据
        """
        tasks = params.get("tasks", [])

        if not tasks:
            logger.info("○ 未提供线索")
            return {"success": True, "message": "无线索", "tasks": []}

        if not isinstance(tasks, list):
            return {"success": False, "error": "tasks 必须是列表"}

        logger.info(f"🔍 验证线索: session_id={context.session_id}, count={len(tasks)}")

        try:
            # 验证和格式化线索
            valid_tasks = self._validate_tasks(tasks)

            if not valid_tasks:
                logger.info("○ 无有效线索")
                return {"success": True, "message": "无有效线索", "tasks": []}

            logger.info(f"✅ 线索验证完成: {len(valid_tasks)} 个")

            return {
                "success": True,
                "message": f"✅ 成功将 {len(valid_tasks)} 个线索发送到前端。",
                "tasks": valid_tasks,
                "completed": True,  # 明确标记任务完成
            }

        except Exception as e:
            logger.warning(f"⚠️ 验证线索失败: {str(e)}", exc_info=True)
            return {"success": False, "error": f"验证线索失败: {str(e)}"}

    def _validate_tasks(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """验证和清理 tasks"""
        valid_tasks = []
        valid_acts = {"reply", "forward", "confirm", "upload"}

        for i, task in enumerate(tasks[:4]):  # 最多 4 个
            if not isinstance(task, dict):
                continue

            text = task.get("text", "").strip()
            act = task.get("act", "reply")

            if not text:
                continue

            # 验证 act 类型
            if act not in valid_acts:
                act = "reply"  # 默认回退

            # 截断过长的文本
            if len(text) > 30:
                text = text[:27] + "..."

            valid_task = {"id": task.get("id") or f"clue_{i + 1}", "text": text, "act": act}

            # 添加可选字段
            if task.get("payload"):
                valid_task["payload"] = task["payload"]
            if task.get("status"):
                valid_task["status"] = task["status"]
            if task.get("metadata"):
                valid_task["metadata"] = task["metadata"]

            valid_tasks.append(valid_task)

        return valid_tasks


# 工具实例（用于 ToolExecutor 加载）
clue_generation_tool = ClueGenerationTool()
