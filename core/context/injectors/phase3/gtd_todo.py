"""
GTDTodoInjector - GTD Todo 注入器

职责：
1. 从 InjectionContext 获取当前 Todo 状态
2. 格式化为 XML 标签追加到最后一条用户消息

缓存策略：DYNAMIC（不缓存，Todo 状态实时变化）
注入位置：Phase 3 - Runtime（追加到最后一条用户消息）
优先级：80（较高优先级）
"""

from typing import Any, Dict, List

from logger import get_logger

from ..base import BaseInjector, CacheStrategy, InjectionPhase, InjectionResult
from ..context import InjectionContext

logger = get_logger("injectors.phase3.gtd_todo")


class GTDTodoInjector(BaseInjector):
    """
    GTD Todo 注入器

    追加当前任务的 Todo 状态到最后一条用户消息。

    输出示例：
    ```
    <gtd_todos>
    当前待办事项：
    - [ ] 实现用户认证模块
    - [ ] 添加单元测试
    - [x] 设计 API 接口
    </gtd_todos>
    ```
    """

    @property
    def name(self) -> str:
        return "gtd_todo"

    @property
    def phase(self) -> InjectionPhase:
        return InjectionPhase.RUNTIME

    @property
    def cache_strategy(self) -> CacheStrategy:
        # Todo 状态实时变化，不缓存
        return CacheStrategy.DYNAMIC

    @property
    def priority(self) -> int:
        # 较高优先级
        return 80

    async def should_inject(self, context: InjectionContext) -> bool:
        """只有存在 Todo 时才注入"""
        todos = context.get("todos") or context.get("current_todos")
        return bool(todos)

    async def inject(self, context: InjectionContext) -> InjectionResult:
        """
        注入 Todo 状态

        从 context.metadata 获取 todos 并格式化
        """
        todos = context.get("todos") or context.get("current_todos")

        if not todos:
            return InjectionResult()

        content = self._format_todos(todos)

        if not content:
            logger.debug("Todo 格式化结果为空，跳过")
            return InjectionResult()

        logger.info(f"GTDTodoInjector: {len(content)} 字符")

        return InjectionResult(content=content, xml_tag="gtd_todos")

    def _format_todos(self, todos: List[Dict[str, Any]]) -> str:
        """
        格式化 Todo 列表为 Markdown

        支持的 Todo 格式：
        - 字符串列表: ["任务1", "任务2"]
        - 字典列表: [{"title": "任务1", "status": "pending"}, ...]
        """
        if not todos:
            return ""

        lines = ["当前待办事项："]

        for todo in todos:
            if isinstance(todo, str):
                lines.append(f"- [ ] {todo}")
            elif isinstance(todo, dict):
                title = todo.get("title") or todo.get("content") or todo.get("description", "")
                status = todo.get("status", "pending")

                if not title:
                    continue

                # 确定状态符号
                if status in ("completed", "done", "finished"):
                    symbol = "[x]"
                elif status in ("in_progress", "current"):
                    symbol = "[-]"
                else:
                    symbol = "[ ]"

                lines.append(f"- {symbol} {title}")

        return "\n".join(lines)
