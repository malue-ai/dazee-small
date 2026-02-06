# 可用工具参考

## 核心工具（自动启用，无需配置）

- **plan_todo**: 任务规划工具（智能版本）- 内部调用 Claude + Extended Thinking

核心能...
- **api_calling**: 通用 HTTP API 调用工具,配合 Skills 文档使用,无需为每个 API 编写专门工具...
- **hitl**: HITL (Human-in-the-Loop) 工具，请求用户输入或确认。适用于以下场景：
- 删除文件或数据等危险操作
- 修改重要配置
- 执行不可逆操...
- **sandbox_read_file**: Read file contents from the sandbox file system...

## 可配置工具

### code_sandbox

- **sandbox_run_code** [TOOL]: 在沙盒中执行 Python 代码（Code Interpreter）

核心特性：
• ✅ 完整网络访问（request...

### data_analysis

- **xlsx** [SKILL]: Create spreadsheets, analyze data, generate reports with cha...

### document_creation

- **docx** [SKILL]: Create documents, edit content, format text

### dynamic_execution

- **code_execution** [CODE]: Execute Python code dynamically via code_execution

### information_retrieval

- **web_search** [TOOL]: Search the web for information
- **exa_search** [TOOL]: High-quality semantic search using Exa API with content extr...

### knowledge_base

- **knowledge_search** [TOOL]: 从用户的个人知识库中检索相关信息（基于 Ragie）

### pdf_generation

- **pdf** [SKILL]: Generate formatted PDF documents and reports

### ppt_generation

- **pptx** [SKILL]: Create presentations, edit slides, analyze presentation cont...
- **ppt_generator** [TOOL]: 高质量闭环PPT生成工具 - 整合素材搜索、内容规划、PPT渲染的完整流程。
🎯 核心能力： - 自动搜索相关素材（可选...

### ppt_rendering

- **slidespeak_render** [TOOL]: SlideSpeak API rendering tool for professional PPT generatio...

### sandbox_file_operations

- **sandbox_list_dir** [TOOL]: 列出沙盒目录内容
- **sandbox_read_file** [TOOL]: 读取沙盒文件内容
- **sandbox_write_file** [TOOL]: 写入沙盒文件
- **sandbox_delete_file** [TOOL]: 删除沙盒文件或目录
- **sandbox_run_command** [TOOL]: 在沙盒中执行 shell 命令
- **sandbox_file_exists** [TOOL]: 检查沙盒文件或目录是否存在
- **sandbox_create_project** [TOOL]: 在沙盒中创建项目框架
- **sandbox_run_project** [TOOL]: 运行沙盒中的项目并获取预览 URL


## 工具类别（整体启用）

- **document_skills**: 文档生成技能包 (Claude Skills)
  - 包含: pptx, xlsx, docx, pdf
- **sandbox_tools**: 代码沙盒工具包 (E2B)
  - 包含: sandbox_list_dir, sandbox_read_file, sandbox_write_file, sandbox_delete_file, sandbox_file_exists, sandbox_run_command, sandbox_run_code, sandbox_create_project, sandbox_run_project
- **ppt_tools**: PPT 生成工具
  - 包含: ppt_generator, slidespeak_render