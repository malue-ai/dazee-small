"""
后台任务服务 - BackgroundTaskService

职责：
- 统一调度后台任务
- 提供共享资源（LLM、Mem0 Pool）

设计原则：
- 任务自动注册，无需手动维护 TASK_REGISTRY
- 任务实现在 tasks/ 目录下，使用 @background_task 装饰器
- Service 只负责调度和资源管理，不包含具体业务逻辑
"""

# 1. 标准库
import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

# 3. 本地模块
from logger import get_logger

from .context import TaskContext
from .registry import get_registered_task_names, get_task_registry

# 2. 第三方库（无）


if TYPE_CHECKING:
    from core.llm.base import Message

# 注意：create_llm_service 延迟导入以避免循环依赖
# core.llm → utils → background_tasks → core.llm

logger = get_logger("background_tasks.service")


class BackgroundTaskService:
    """
    后台任务服务

    统一管理所有后台任务，提供可扩展的任务接口

    使用方式：
        # 统一调度
        await service.dispatch_tasks(
            task_names=["title_generation", "recommended_questions"],
            context=TaskContext(...)
        )

    新增任务只需：
    1. 在 tasks/ 目录下创建新文件
    2. 使用 @background_task("task_name") 装饰器
    """

    def __init__(self) -> None:
        """初始化后台任务服务"""
        # 使用 Haiku（快速、便宜，适合简单任务）
        self._llm = None  # 延迟初始化，避免启动时加载
        self._mem0_pool = None  # Mem0 Pool 延迟初始化

        # Prompt 模板（供 tasks 使用）
        self.title_generation_prompt = """请为以下对话内容生成一个简短的中文标题。

要求：
- 不超过15个字
- 不要加引号、书名号等标点符号
- 简洁明了，概括对话主题
- 只返回标题文本，不要任何其他内容

对话内容：
{message}

标题："""

        self.recommended_questions_prompt = """基于以下对话内容，生成3个用户可能想要继续问的后续问题。

重要规则：
- 如果助手已经完成了任务（如生成了图片、完成了查询等），问题应该是**后续延伸类**，引导用户探索更多可能性
- 绝对不要生成"事后诸葛亮"式的问题（如任务完成后再问"你想要什么风格"这类本该事前问的问题）
- 问题应该面向未来，而不是回溯过去

好的后续问题示例（任务完成后）：
- "帮我再生成一张不同风格的"
- "可以把背景换成xxx吗"
- "你还能生成什么卡通人物"
- "把这张图片发给我的好友"

不好的问题示例（任务完成后不应再问）：
- "你想要什么风格的图片"（应该事前问，不是事后问）
- "背景应该包含什么元素"（任务都完成了再问没意义）

要求：
- 生成3个问题
- 每个问题不超过25个字
- 问题要引导用户继续探索和使用
- 使用中文
- 只返回 JSON，不要其他内容

对话内容：
用户：{user_message}
助手：{assistant_response}

返回格式：
{{"questions": ["问题1", "问题2", "问题3"]}}
"""

    # ==================== 共享资源管理 ====================

    async def get_llm(self) -> Any:
        """
        获取 LLM 服务（懒加载）

        供 tasks 使用，避免重复创建 LLM 实例
        """
        if self._llm is None:
            from config.llm_config import get_llm_profile
            from core.llm import create_llm_service  # 延迟导入避免循环依赖

            profile = await get_llm_profile("background_task")
            self._llm = create_llm_service(**profile)
        return self._llm

    def get_mem0_pool(self) -> Optional[Any]:
        """
        获取 Mem0 Pool（懒加载）

        供 tasks 使用，避免重复创建 Pool 实例

        Returns:
            Mem0 Pool 实例，如果模块未安装则返回 None
        """
        if self._mem0_pool is None:
            try:
                from core.memory.mem0 import get_mem0_pool

                self._mem0_pool = get_mem0_pool()
            except ImportError:
                logger.warning("⚠️ mem0 模块未安装，Mem0 功能不可用")
                return None
        return self._mem0_pool

    # ==================== 统一调度入口 ====================

    # Tasks that MUST complete before SSE stream closes
    # (they send SSE events that the frontend needs)
    # NOTE: recommended_questions now pushes via WebSocket ConnectionManager
    # (bypasses closed event stream), so it no longer needs to block here.
    _SSE_DEPENDENT_TASKS = {"title_generation"}

    async def dispatch_tasks(
        self, task_names: List[str], context: TaskContext, wait: bool = True
    ) -> Dict[str, bool]:
        """
        Unified background task dispatcher.

        Two-tier dispatch strategy:
        - SSE-dependent tasks (title, questions): await before stream close
        - Learning tasks (memory, playbook): fire-and-forget, never block user

        Args:
            task_names: Task name list
            context: Task context
            wait: Wait for SSE-dependent tasks (default True)

        Returns:
            Dict[str, bool]: Whether each task started successfully
        """
        results = {}
        registry = get_task_registry()
        blocking_tasks = []
        blocking_map = {}

        for task_name in task_names:
            if task_name not in registry:
                logger.warning(
                    f"未知的后台任务: {task_name}，"
                    f"已注册: {get_registered_task_names()}"
                )
                results[task_name] = False
                continue

            task_func = registry[task_name]

            try:
                task = asyncio.create_task(task_func(context, self))

                if wait and task_name in self._SSE_DEPENDENT_TASKS:
                    # SSE-dependent: must complete before stream closes
                    blocking_tasks.append(task)
                    blocking_map[id(task)] = task_name
                else:
                    # Learning tasks: fire-and-forget
                    task.add_done_callback(self._log_task_result(task_name))

                results[task_name] = True
                logger.info(
                    f"后台任务已启动: {task_name} "
                    f"({'await' if task_name in self._SSE_DEPENDENT_TASKS else 'fire-and-forget'})"
                )
            except Exception as e:
                logger.warning(f"启动后台任务失败: {task_name}, error={e}")
                results[task_name] = False

        # Only wait for SSE-dependent tasks
        if blocking_tasks:
            logger.debug(f"等待 {len(blocking_tasks)} 个 SSE 依赖任务...")
            done, _ = await asyncio.wait(
                blocking_tasks, return_when=asyncio.ALL_COMPLETED
            )
            for task in done:
                name = blocking_map.get(id(task), "unknown")
                if task.exception():
                    logger.warning(f"SSE 任务失败: {name}, error={task.exception()}")
                    results[name] = False

        return results

    @staticmethod
    def _log_task_result(task_name: str):
        """Create a done-callback that logs fire-and-forget task results."""
        def _callback(task: asyncio.Task):
            try:
                exc = task.exception()
                if exc:
                    logger.warning(
                        f"后台学习任务失败: {task_name}, error={exc}"
                    )
                else:
                    logger.info(f"后台学习任务完成: {task_name}")
            except asyncio.CancelledError:
                logger.debug(f"后台学习任务被取消: {task_name}")
        return _callback

    # ==================== 工具方法 ====================

    @staticmethod
    def calc_duration_ms(start_time: datetime) -> int:
        """计算耗时（毫秒）"""
        return int((datetime.now() - start_time).total_seconds() * 1000)


# ==================== 便捷函数 ====================

_default_service: Optional[BackgroundTaskService] = None


def get_background_task_service() -> BackgroundTaskService:
    """获取默认后台任务服务单例"""
    global _default_service
    if _default_service is None:
        _default_service = BackgroundTaskService()
    return _default_service
