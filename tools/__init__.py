"""
Tools 工具模块

此目录包含各类工具的具体实现：
- plan_todo_tool.py: Plan/Todo 工具
- slidespeak.py: SlideSpeek PPT 工具
- ppt_generator.py: PPT 生成工具
- request_human_confirmation.py: HITL 工具（hitl）
- knowledge_search.py: 知识库搜索工具
- tavily_search.py: Tavily 通用搜索工具（替代 Claude web_search Server Tool）
- exa_search.py: Exa 语义搜索工具
- api_calling.py: 通用 API 调用工具（支持问数平台等分析类 API）

注意：工具核心逻辑（Selector、Executor）已移至 core/tool/
      请使用 `from core.tool import ToolSelector, ToolExecutor` 导入
"""

# 此模块不再导出任何内容，请使用 core.tool
__all__: list[str] = []
