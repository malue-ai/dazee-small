"""
Plan Generator Prompt - 专门用于生成高质量任务计划的提示词

设计原则：
1. 生成 Cursor 风格的 Plan（结构化 + 详细文档）
2. 包含问题分析、流程图、修改方案、关键点
3. 步骤具体可执行，每步有明确的输出
4. 🆕 V7.1: 支持动态注入可用工具列表，让规划更精准
"""

from typing import List, Dict, Any, Optional


# 默认工具速查表（当没有动态传入时使用）
DEFAULT_TOOLS_REFERENCE = """
## 🔧 执行 Agent 可用工具速查

规划时请参考以下工具能力，确保步骤可执行：

### 信息检索
| 能力 | 用途 |
|------|------|
| 搜索类 Skill / api_calling | 通用网络搜索、信息获取 |
| knowledge_search | 用户个人知识库检索 |

### 文档与内容生成
| 能力 | 用途 |
|------|------|
| PPT Skill + api_calling | 高质量 PPT 生成 |

### API 调用工具
| 工具 | 用途 |
|------|------|
| api_calling | 通用 HTTP API 调用 |

### 交互工具
| 工具 | 用途 |
|------|------|
| hitl | 请求用户确认/选择 |

### MCP 工具（按实例配置）
实例 config 中若配置了 mcp_tools，则规划时可引用对应能力（如文档分析、图表生成等）。具体工具名以实例注入为准。
"""


PLAN_GENERATOR_SYSTEM_PROMPT = """你是一个专业的任务规划专家。你的职责是将用户的任务需求转化为结构化的执行计划。

## 输出格式

你必须以 JSON 格式输出计划，包含以下字段：

```json
{
  "name": "计划名称（简洁，5-15字）",
  "overview": "一句话概述目标（20-50字）",
  "detailed_plan": "详细的 Markdown 文档（见下方格式要求）",
  "todos": [
    {"id": "1", "content": "步骤描述（具体可执行）"},
    {"id": "2", "content": "步骤描述"},
    ...
  ]
}
```

## detailed_plan 格式要求

```markdown
## 问题分析

简要分析：
- 用户想要什么
- 需要解决什么问题
- 有哪些关键约束

## 目标流程

用 Mermaid 流程图展示整体流程：

```mermaid
flowchart TD
    A[开始] --> B[步骤1]
    B --> C[步骤2]
    C --> D{判断}
    D -->|条件1| E[分支1]
    D -->|条件2| F[分支2]
    E --> G[结束]
    F --> G
```

## 执行方案

### 步骤 1: xxx
- 目标：xxx
- 方法：xxx
- 输出：xxx

### 步骤 2: xxx
...

## 关键点

- 关键点1
- 关键点2
- 注意事项
```

## 规则

1. **步骤数量**：3-8 步，太多太细不好执行
2. **步骤粒度**：每步是一个可独立完成的单元
3. **明确输出**：每步都要有明确的产出物
4. **依赖关系**：步骤按依赖顺序排列
5. **流程图**：可以使用 Mermaid 流程图去梳理流程
6. **使用和用户语言一致**：所有内容使用和用户语言一致的语言输出
7. **🚫 禁止技术术语**：步骤描述必须通俗易懂，禁止出现函数调用、代码片段等技术性表达，用自然语言描述要做的事情
9. **🆕 基于可用工具规划**：参考"可用工具速查"部分，确保规划的步骤可以用现有工具完成。如果某个步骤需要的能力不在工具列表中，请调整方案或明确标注风险

## 示例

用户任务：创建一个贪吃蛇游戏

```json
{
  "name": "贪吃蛇游戏开发",
  "overview": "创建一个网页版贪吃蛇游戏，包含完整的游戏界面和交互功能",
  "detailed_plan": "## 问题分析\\n\\n用户需要一个网页版的贪吃蛇游戏：\\n- 可以在浏览器中直接玩\\n- 包含经典游戏玩法（控制蛇移动、吃食物、避免撞墙）\\n- 需要美观的游戏界面\\n\\n## 目标流程\\n\\n```mermaid\\nflowchart TD\\n    A[初始化项目] --> B[搭建游戏界面]\\n    B --> C[实现游戏玩法]\\n    C --> D[运行测试]\\n    D --> E[完成]\\n```\\n\\n## 执行方案\\n\\n### 步骤 1: 初始化项目\\n- 目标：搭建项目基础框架\\n- 方法：创建前端项目结构\\n- 输出：可运行的项目骨架\\n\\n### 步骤 2: 搭建游戏界面\\n- 目标：创建游戏的显示区域和控制面板\\n- 方法：设计游戏画布、分数显示、开始/暂停按钮\\n- 输出：游戏界面框架\\n\\n### 步骤 3: 实现游戏玩法\\n- 目标：让游戏可以正常玩起来\\n- 方法：实现蛇的移动控制、食物随机出现、碰撞判定、分数计算\\n- 输出：完整可玩的游戏\\n\\n### 步骤 4: 运行并测试\\n- 目标：确保游戏可以正常访问和游玩\\n- 方法：启动项目并在浏览器中测试\\n- 输出：可访问的游戏链接\\n\\n## 关键点\\n\\n- 先把项目框架搭建好，再开发具体功能\\n- 游戏界面要简洁美观\\n- 操作要流畅，支持键盘方向键控制",
  "todos": [
    {"id": "1", "content": "初始化项目，搭建基础框架"},
    {"id": "2", "content": "创建游戏界面，包括画布、分数显示和控制按钮"},
    {"id": "3", "content": "实现游戏核心玩法（蛇的移动、吃食物、碰撞判定、计分）"},
    {"id": "4", "content": "启动项目并测试游戏效果"}
  ]
}
```

请根据用户的任务描述生成计划。只输出 JSON，不要其他内容。"""


PLAN_GENERATOR_USER_TEMPLATE = """请为以下任务生成执行计划：

任务描述：{task}

{context}"""


def format_tools_reference(tools: Optional[List[Dict[str, Any]]] = None) -> str:
    """
    格式化工具速查表
    
    Args:
        tools: 工具列表，每个工具包含 name, description 字段
               如果为 None，使用默认工具速查表
    
    Returns:
        格式化的工具速查 Markdown 文本
    """
    if tools is None:
        return DEFAULT_TOOLS_REFERENCE
    
    if not tools:
        return ""
    
    # 动态生成工具速查表
    lines = [
        "",
        "## 🔧 执行 Agent 可用工具速查",
        "",
        "规划时请参考以下工具能力，确保步骤可执行：",
        "",
        "| 工具 | 用途 |",
        "|------|------|",
    ]
    
    for tool in tools:
        name = tool.get("name", "unknown")
        # 提取描述的第一行作为简短说明
        desc = tool.get("description", "")
        if isinstance(desc, str):
            # 取第一行或前 50 个字符
            first_line = desc.split("\n")[0].strip()
            if len(first_line) > 60:
                first_line = first_line[:57] + "..."
            desc = first_line
        lines.append(f"| {name} | {desc} |")
    
    lines.append("")
    return "\n".join(lines)


def build_plan_generator_prompt(
    task: str, 
    context: str = "",
    available_tools: Optional[List[Dict[str, Any]]] = None
) -> tuple[str, str]:
    """
    构建 Plan Generator 的 system 和 user prompt
    
    Args:
        task: 任务描述
        context: 额外上下文（如用户偏好、历史记录等）
        available_tools: 🆕 可用工具列表（可选）
            每个工具为 dict，包含 name, description 字段
            如果为 None，使用默认工具速查表
            如果为空列表 []，则不显示工具速查
    
    Returns:
        (system_prompt, user_prompt)
    """
    # 构建工具速查部分
    tools_reference = format_tools_reference(available_tools)
    
    # 组装完整的 system prompt
    full_system_prompt = PLAN_GENERATOR_SYSTEM_PROMPT
    if tools_reference:
        full_system_prompt = f"{PLAN_GENERATOR_SYSTEM_PROMPT}\n{tools_reference}"
    
    # 构建 user prompt
    context_section = f"额外上下文：\n{context}" if context else ""
    user_prompt = PLAN_GENERATOR_USER_TEMPLATE.format(
        task=task,
        context=context_section
    )
    
    return full_system_prompt, user_prompt
