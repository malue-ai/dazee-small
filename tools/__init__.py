"""
Tools 工具模块

此目录包含各类工具的具体实现：
- sandbox_tools.py: E2B 沙盒工具（文件操作、代码执行、项目运行）
- plan_todo_tool.py: Plan/Todo 工具
- slidespeak.py: SlideSpeek PPT 工具
- ppt_generator.py: PPT 生成工具
- request_human_confirmation.py: HITL 工具（hitl）
- knowledge_search.py: 知识库搜索工具
- tavily_search.py: Tavily 通用搜索工具（替代 Claude web_search Server Tool）
- exa_search.py: Exa 语义搜索工具
- api_calling.py: 通用 API 调用工具（支持问数平台等分析类 API）
- e2b_template_manager.py: E2B 模板管理工具

注意：工具核心逻辑（Selector、Executor）已移至 core/tool/
      请使用 `from core.tool import ToolSelector, ToolExecutor` 导入
"""

# 此模块不再导出任何内容，请使用 core.tool
__all__: list[str] = []

