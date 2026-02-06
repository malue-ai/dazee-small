"""
PageEditorContextInjector - 页面编辑器上下文注入器

职责：
1. 从 InjectionContext 获取当前编辑器上下文
2. 格式化为 XML 标签追加到最后一条用户消息

缓存策略：DYNAMIC（不缓存，编辑器状态实时变化）
注入位置：Phase 3 - Runtime（追加到最后一条用户消息）
优先级：70（在 Todo 之后）
"""

from typing import Any, Dict, Optional

from logger import get_logger

from ..base import BaseInjector, CacheStrategy, InjectionPhase, InjectionResult
from ..context import InjectionContext

logger = get_logger("injectors.phase3.page_editor")


class PageEditorContextInjector(BaseInjector):
    """
    页面编辑器上下文注入器

    追加当前页面编辑器的上下文到最后一条用户消息。

    输出示例：
    ```
    <page_editor_context>
    当前编辑器状态：

    **文件**: src/components/Button.tsx
    **语言**: TypeScript
    **光标位置**: 第 42 行

    **选中代码**:
    ```typescript
    const handleClick = () => {
      // TODO: 实现点击逻辑
    }
    ```
    </page_editor_context>
    ```
    """

    @property
    def name(self) -> str:
        return "page_editor"

    @property
    def phase(self) -> InjectionPhase:
        return InjectionPhase.RUNTIME

    @property
    def cache_strategy(self) -> CacheStrategy:
        # 编辑器状态实时变化，不缓存
        return CacheStrategy.DYNAMIC

    @property
    def priority(self) -> int:
        # 在 Todo 之后
        return 70

    async def should_inject(self, context: InjectionContext) -> bool:
        """只有存在编辑器上下文时才注入"""
        editor_context = context.get("editor_context") or context.get("page_context")
        return bool(editor_context)

    async def inject(self, context: InjectionContext) -> InjectionResult:
        """
        注入编辑器上下文

        从 context.metadata 获取编辑器状态并格式化
        """
        editor_context = context.get("editor_context") or context.get("page_context")

        if not editor_context:
            return InjectionResult()

        content = self._format_editor_context(editor_context)

        if not content:
            logger.debug("编辑器上下文格式化结果为空，跳过")
            return InjectionResult()

        logger.info(f"PageEditorContextInjector: {len(content)} 字符")

        return InjectionResult(content=content, xml_tag="page_editor_context")

    def _format_editor_context(self, editor_context: Dict[str, Any]) -> str:
        """
        格式化编辑器上下文为 Markdown

        支持的字段：
        - file_path: 当前文件路径
        - language: 编程语言
        - cursor_line: 光标行号
        - selection: 选中的代码
        - visible_range: 可见范围
        """
        lines = ["当前编辑器状态：", ""]

        # 文件信息
        file_path = editor_context.get("file_path") or editor_context.get("file")
        if file_path:
            lines.append(f"**文件**: {file_path}")

        # 语言
        language = editor_context.get("language") or editor_context.get("lang")
        if language:
            lines.append(f"**语言**: {language}")

        # 光标位置
        cursor_line = editor_context.get("cursor_line") or editor_context.get("line")
        if cursor_line:
            lines.append(f"**光标位置**: 第 {cursor_line} 行")

        lines.append("")

        # 选中代码
        selection = editor_context.get("selection") or editor_context.get("selected_code")
        if selection:
            lang_tag = language.lower() if language else ""
            lines.append("**选中代码**:")
            lines.append(f"```{lang_tag}")
            lines.append(selection)
            lines.append("```")

        # 可见代码
        visible_code = editor_context.get("visible_code") or editor_context.get("visible_range")
        if visible_code and not selection:
            lang_tag = language.lower() if language else ""
            lines.append("**可见代码**:")
            lines.append(f"```{lang_tag}")
            # 截断长代码
            if len(visible_code) > 1000:
                visible_code = visible_code[:1000] + "\n... (已截断)"
            lines.append(visible_code)
            lines.append("```")

        return "\n".join(lines)
