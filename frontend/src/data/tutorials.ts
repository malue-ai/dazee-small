/**
 * 教程内容数据
 */

import type { Tutorial } from '@/types'

export const tutorials: Tutorial[] = [
  // ==================== 教程 1: 快速入门 ====================
  {
    id: 'getting-started',
    title: '快速入门',
    description: '5 分钟了解 ZenFlux Agent 的核心概念和基本用法',
    icon: '🚀',
    level: 'beginner',
    totalDuration: 5,
    tags: ['入门', '基础'],
    chapters: [
      {
        id: 'intro-what-is-zenflux',
        title: '什么是 ZenFlux Agent',
        description: '了解 ZenFlux Agent 的核心概念',
        duration: 2,
        steps: [
          {
            id: 'intro-1',
            title: '欢迎使用 ZenFlux Agent',
            content: `ZenFlux Agent 是一个强大的 AI 智能体平台，它可以帮助你：

• 自动化复杂的工作流程
• 生成文档、PPT、报告等内容
• 搜索和整理信息
• 执行代码和数据分析
• 与外部服务集成

与普通的 AI 对话不同，ZenFlux Agent 具有"工具调用"能力，可以真正执行任务，而不仅仅是生成文本。`,
            tip: 'ZenFlux Agent 的核心优势在于它的"行动力"——它不只是告诉你怎么做，而是直接帮你做。'
          },
          {
            id: 'intro-2',
            title: '核心概念',
            content: `在使用 ZenFlux Agent 之前，你需要了解几个核心概念：

1. **Agent（智能体）**
   预配置的 AI 助手，针对特定场景优化。例如"PPT 助手"、"数据分析师"等。

2. **Skill（技能）**
   Agent 可以使用的能力模块。例如"生成 PPT"、"搜索网络"、"执行代码"等。

3. **Knowledge（知识库）**
   你上传的文档和数据，Agent 可以从中检索信息来回答问题。

4. **Sandbox（沙盒）**
   安全的代码执行环境，Agent 可以在其中运行代码和构建项目。`
          },
          {
            id: 'intro-3',
            title: '开始你的第一次对话',
            content: `现在，让我们尝试与 Agent 进行第一次对话。

你可以直接在聊天界面输入你的需求，Agent 会理解你的意图并采取行动。

试试这些示例 Prompt：
• "帮我制作一个关于 AI 趋势的 PPT"
• "搜索今天的科技新闻"
• "写一个 Python 脚本计算斐波那契数列"`,
            action: {
              type: 'try_prompt',
              label: '试试看',
              prompt: '你好！请介绍一下你能帮我做什么？'
            }
          }
        ]
      },
      {
        id: 'intro-interface',
        title: '界面导览',
        description: '熟悉 ZenFlux Agent 的界面布局',
        duration: 3,
        steps: [
          {
            id: 'interface-1',
            title: '聊天界面',
            content: `聊天界面是你与 Agent 交互的主要区域：

**左侧边栏**
• 会话列表：管理你的所有对话
• 知识库/智能体入口：快速访问管理页面

**中间区域**
• 消息流：显示对话历史
• 输入框：输入你的需求
• 附件按钮：上传文件

**右侧边栏**
• 任务看板：显示 Agent 生成的任务计划
• Mind 面板：展示思维导图和流程图`,
            tip: '你可以点击侧边栏的折叠按钮来获得更大的聊天空间。'
          },
          {
            id: 'interface-2',
            title: '工作区面板',
            content: `当 Agent 执行代码或创建文件时，你可以通过工作区面板查看：

**文件浏览器**
• 查看 Agent 创建的所有文件
• 支持预览代码、文档等

**项目运行**
• 一键运行 Web 项目
• 实时预览运行结果

点击顶部工具栏的 📂 按钮可以打开工作区面板。`,
            action: {
              type: 'navigate',
              label: '查看聊天界面',
              path: '/'
            }
          },
          {
            id: 'interface-3',
            title: '管理后台',
            content: `除了聊天界面，ZenFlux Agent 还提供管理后台：

**知识库** 📚
上传和管理你的文档，让 Agent 能够检索你的私有数据。

**智能体** 🤖
查看和配置不同的 Agent，选择最适合你任务的助手。

**Skill 管理** 🧩
浏览和管理 Agent 可用的技能模块。

**Agent 教程** 📖
就是你现在正在阅读的内容！`,
            action: {
              type: 'navigate',
              label: '查看知识库',
              path: '/knowledge'
            }
          }
        ]
      }
    ]
  },

  // ==================== 教程 2: 创建你的第一个 Agent ====================
  {
    id: 'create-agent',
    title: '创建你的第一个 Agent',
    description: '学习如何配置和创建自定义智能体',
    icon: '🤖',
    level: 'beginner',
    totalDuration: 10,
    tags: ['Agent', '配置'],
    chapters: [
      {
        id: 'agent-basics',
        title: 'Agent 配置基础',
        description: '了解 Agent 的配置结构',
        duration: 5,
        steps: [
          {
            id: 'agent-basics-1',
            title: '什么是 Instance 配置',
            content: `在 ZenFlux Agent 中，每个智能体都通过一个 YAML 配置文件定义，我们称之为 "Instance"。

Instance 配置定义了：
• Agent 的名称和描述
• 使用的 AI 模型
• 可用的工具和技能
• 系统提示词（Prompt）
• 其他行为参数

配置文件存放在 \`instances/\` 目录下。`
          },
          {
            id: 'agent-basics-2',
            title: '配置文件结构',
            content: `一个典型的 Agent 配置文件结构如下：`,
            code: `# instances/my-agent/config.yaml
name: my-custom-agent
description: 我的自定义智能体
version: "1.0"

# AI 模型配置
model:
  provider: anthropic
  model_id: claude-sonnet-4-20250514
  max_tokens: 8192

# 可用工具
tools:
  - web_search
  - code_execution
  - file_operations

# 加载的 Skills
skills:
  - planning-task
  - ppt-generator

# 系统提示词
system_prompt: |
  你是一个专业的助手...`,
            codeLanguage: 'yaml'
          },
          {
            id: 'agent-basics-3',
            title: '关键配置项说明',
            content: `让我们详细了解每个配置项：

**name** (必需)
Agent 的唯一标识符，使用小写字母和连字符。

**description** (必需)
Agent 的描述，会显示在智能体列表中。

**model** (必需)
指定使用的 AI 模型：
• provider: 模型提供商 (anthropic, openai, ollama)
• model_id: 具体的模型 ID
• max_tokens: 最大输出 token 数

**tools** (可选)
Agent 可以使用的工具列表。

**skills** (可选)
要加载的 Skill 名称列表。

**system_prompt** (推荐)
定义 Agent 行为的系统提示词。`,
            tip: '好的系统提示词是创建高质量 Agent 的关键。它定义了 Agent 的角色、能力边界和行为规范。'
          }
        ]
      },
      {
        id: 'agent-create-steps',
        title: '创建自定义 Agent',
        description: '动手创建你的第一个 Agent',
        duration: 5,
        steps: [
          {
            id: 'create-1',
            title: '规划你的 Agent',
            content: `在创建 Agent 之前，先思考以下问题：

1. **目标场景**
   这个 Agent 主要用于什么任务？例如：数据分析、内容创作、客服问答等。

2. **需要的能力**
   Agent 需要哪些工具和技能？例如：搜索能力、代码执行、PPT 生成等。

3. **行为风格**
   Agent 应该如何与用户交互？正式还是亲切？详细还是简洁？

4. **限制条件**
   Agent 不应该做什么？有什么安全边界？`
          },
          {
            id: 'create-2',
            title: '编写配置文件',
            content: `假设我们要创建一个"数据分析助手"，它可以帮助用户分析数据并生成可视化图表。`,
            code: `# instances/data-analyst/config.yaml
name: data-analyst
description: 专业的数据分析助手，擅长数据处理、可视化和洞察发现
version: "1.0"

model:
  provider: anthropic
  model_id: claude-sonnet-4-20250514
  max_tokens: 8192

tools:
  - code_execution
  - file_operations
  - web_search

skills:
  - planning-task

system_prompt: |
  你是一位专业的数据分析师。你的职责是：
  
  1. 帮助用户理解和分析数据
  2. 使用 Python 进行数据处理和可视化
  3. 发现数据中的模式和洞察
  4. 生成清晰的分析报告
  
  在分析数据时，请：
  - 先理解数据的结构和含义
  - 提出分析思路并征求用户确认
  - 使用 pandas、matplotlib、seaborn 等库
  - 解释你的分析过程和结论`,
            codeLanguage: 'yaml',
            tip: '系统提示词应该清晰地定义 Agent 的角色和工作方式。'
          },
          {
            id: 'create-3',
            title: '测试你的 Agent',
            content: `创建完配置后，你可以：

1. 在智能体列表中找到你的新 Agent
2. 选择它开始对话
3. 测试各种场景，确保它按预期工作

测试时注意观察：
• Agent 是否正确理解你的需求
• 是否正确使用了配置的工具
• 回复风格是否符合预期`,
            action: {
              type: 'create_agent',
              label: '创建智能体'
            }
          }
        ]
      }
    ]
  },

  // ==================== 教程 3: 添加 Skills ====================
  {
    id: 'add-skills',
    title: '添加 Skills',
    description: '为 Agent 添加更多能力',
    icon: '🧩',
    level: 'intermediate',
    totalDuration: 8,
    tags: ['Skills', '扩展'],
    chapters: [
      {
        id: 'skills-overview',
        title: 'Skills 概述',
        description: '了解 Skills 的作用和结构',
        duration: 4,
        steps: [
          {
            id: 'skills-1',
            title: '什么是 Skill',
            content: `Skill 是 Agent 的能力扩展模块。每个 Skill 定义了：

• **触发条件**：什么情况下应该使用这个 Skill
• **执行逻辑**：如何完成特定任务
• **输入/输出**：需要什么参数，产生什么结果

例如，"planning-task" Skill 可以将复杂任务分解为步骤列表；"ppt-generator" Skill 可以生成 PPT 文件。

Skills 让 Agent 具备了"专业技能"，而不仅仅是通用的对话能力。`
          },
          {
            id: 'skills-2',
            title: 'Skill 目录结构',
            content: `每个 Skill 是一个独立的目录，包含以下文件：`,
            code: `skills/library/my-skill/
├── SKILL.md          # 技能文档（必需）
├── scripts/          # Python 脚本
│   ├── __init__.py
│   └── main.py       # 主要逻辑
└── resources/        # 资源文件
    └── template.json # 模板、配置等`,
            codeLanguage: 'text'
          },
          {
            id: 'skills-3',
            title: 'SKILL.md 格式',
            content: `SKILL.md 是 Skill 的核心文档，它告诉 Agent 何时以及如何使用这个技能：`,
            code: `---
name: my-skill
description: 技能描述，说明它能做什么
priority: medium
preferred_for:
  - 场景1
  - 场景2
---

# My Skill

详细说明这个技能的用途。

## When to Use

描述什么情况下应该加载这个技能。

## Capabilities

1. **能力1**: 说明
2. **能力2**: 说明

## Workflow

描述使用这个技能的工作流程...`,
            codeLanguage: 'markdown'
          }
        ]
      },
      {
        id: 'skills-usage',
        title: '使用和管理 Skills',
        description: '学习如何启用和管理 Skills',
        duration: 4,
        steps: [
          {
            id: 'usage-1',
            title: '在 Agent 中启用 Skill',
            content: `要让 Agent 使用某个 Skill，需要在配置文件中添加：`,
            code: `# config.yaml
skills:
  - planning-task      # 任务规划
  - ppt-generator      # PPT 生成
  - slidespeak-generator  # 智能演示文稿`,
            codeLanguage: 'yaml',
            tip: 'Agent 会根据用户的请求自动选择合适的 Skill，你不需要手动指定。'
          },
          {
            id: 'usage-2',
            title: '查看可用 Skills',
            content: `在 Skill 管理页面，你可以：

• 浏览所有可用的 Skills
• 查看每个 Skill 的详细文档
• 了解 Skill 的适用场景
• 创建新的自定义 Skill

点击下方按钮前往 Skill 管理页面。`,
            action: {
              type: 'add_skill',
              label: '管理 Skills'
            }
          },
          {
            id: 'usage-3',
            title: '创建自定义 Skill',
            content: `如果现有 Skills 不能满足需求，你可以创建自定义 Skill：

1. 在 \`skills/library/\` 下创建目录
2. 编写 SKILL.md 文档
3. 添加必要的脚本和资源
4. 在 Agent 配置中启用

自定义 Skill 可以调用外部 API、执行复杂计算、或实现特定的业务逻辑。`,
            warning: '创建 Skill 需要一定的编程知识。建议先熟悉现有 Skills 的实现方式。'
          }
        ]
      }
    ]
  },

  // ==================== 教程 4: 使用知识库 ====================
  {
    id: 'knowledge-base',
    title: '使用知识库',
    description: '让 Agent 具有领域知识',
    icon: '📚',
    level: 'intermediate',
    totalDuration: 8,
    tags: ['知识库', 'RAG'],
    chapters: [
      {
        id: 'kb-intro',
        title: '知识库介绍',
        description: '了解知识库的作用',
        duration: 3,
        steps: [
          {
            id: 'kb-1',
            title: '为什么需要知识库',
            content: `AI 模型的训练数据有截止日期，而且不包含你的私有数据。知识库可以：

**解决时效性问题**
上传最新的文档，让 Agent 了解最新信息。

**引入私有数据**
上传公司文档、产品手册、内部规范等。

**提高回答准确性**
Agent 可以引用知识库中的具体内容，而不是凭记忆回答。

**支持复杂问答**
对于需要大量上下文的问题，知识库可以提供必要的背景信息。`
          },
          {
            id: 'kb-2',
            title: '支持的文件类型',
            content: `知识库支持多种文件格式：

**文档类**
• PDF (.pdf)
• Word (.docx)
• PowerPoint (.pptx)
• Markdown (.md)
• 纯文本 (.txt)

**数据类**
• CSV (.csv)
• JSON (.json)

**多媒体**
• 图片 (PNG, JPG) - 会提取文字
• 音频 (MP3) - 会转写为文本`,
            tip: '上传前确保文档内容清晰、结构合理，这样检索效果会更好。'
          }
        ]
      },
      {
        id: 'kb-usage',
        title: '使用知识库',
        description: '学习如何上传和使用文档',
        duration: 5,
        steps: [
          {
            id: 'kb-usage-1',
            title: '上传文档',
            content: `上传文档的步骤：

1. 进入知识库页面
2. 点击"上传文件"或拖拽文件
3. 等待处理完成（状态变为"就绪"）

文档处理包括：
• 文本提取
• 分块处理
• 向量化索引

处理时间取决于文档大小，通常几秒到几分钟。`,
            action: {
              type: 'navigate',
              label: '前往知识库',
              path: '/knowledge'
            }
          },
          {
            id: 'kb-usage-2',
            title: '在对话中使用',
            content: `上传文档后，Agent 会自动使用知识库：

• 当用户提问时，Agent 会检索相关文档
• 检索结果会作为上下文提供给 AI
• AI 会基于文档内容生成回答

**示例对话**

用户: "我们的产品退换货政策是什么？"
Agent: 根据《客户服务手册》，退换货政策如下：
1. 7天无理由退货...
2. 质量问题30天内可换...`,
            tip: '你可以在 Prompt 中明确要求 Agent 引用知识库，例如"根据文档回答..."'
          },
          {
            id: 'kb-usage-3',
            title: '最佳实践',
            content: `让知识库发挥最大作用的建议：

**文档准备**
• 确保文档格式正确、内容完整
• 添加清晰的标题和章节结构
• 避免扫描质量差的 PDF

**组织管理**
• 定期更新过时的文档
• 删除不再需要的文件
• 为文档添加有意义的名称

**使用技巧**
• 问题要具体，便于精确检索
• 可以指定要查询的文档范围
• 对于复杂问题，可以分步提问`
          }
        ]
      }
    ]
  },

  // ==================== 教程 5: 高级配置 ====================
  {
    id: 'advanced-config',
    title: '高级配置',
    description: 'Prompt 工程、Tools 和 MCP 集成',
    icon: '⚙️',
    level: 'advanced',
    totalDuration: 15,
    tags: ['高级', 'Prompt', 'MCP'],
    chapters: [
      {
        id: 'prompt-engineering',
        title: 'Prompt 工程',
        description: '编写高质量的系统提示词',
        duration: 5,
        steps: [
          {
            id: 'prompt-1',
            title: 'System Prompt 的重要性',
            content: `System Prompt（系统提示词）定义了 Agent 的"性格"和"能力边界"。

一个好的 System Prompt 应该包含：

1. **角色定义**
   明确 Agent 是谁，擅长什么。

2. **行为规范**
   如何与用户交互，什么风格。

3. **能力范围**
   可以做什么，不能做什么。

4. **工作流程**
   处理任务的标准步骤。

5. **输出格式**
   回复的结构和格式要求。`
          },
          {
            id: 'prompt-2',
            title: '编写技巧',
            content: `编写有效 System Prompt 的技巧：`,
            code: `system_prompt: |
  # 角色
  你是 ZenFlux 的技术支持专家，专门帮助用户解决产品使用问题。
  
  # 核心职责
  1. 解答产品功能和使用问题
  2. 指导用户完成配置和操作
  3. 排查和解决技术故障
  4. 收集用户反馈和建议
  
  # 工作方式
  - 先理解用户的具体问题
  - 提供分步骤的解决方案
  - 使用简洁易懂的语言
  - 必要时提供截图或代码示例
  
  # 限制
  - 不处理账单和付款问题（引导至客服）
  - 不提供法律或财务建议
  - 遇到安全问题，立即上报
  
  # 回复格式
  1. 确认理解问题
  2. 提供解决步骤
  3. 询问是否解决`,
            codeLanguage: 'yaml'
          },
          {
            id: 'prompt-3',
            title: '常见错误',
            content: `编写 System Prompt 时要避免：

**过于笼统**
❌ "你是一个有帮助的助手"
✅ "你是专业的数据分析师，擅长 Python 和可视化"

**指令冲突**
❌ "简洁回答" + "详细解释每个步骤"
✅ 明确说明何时简洁、何时详细

**遗漏边界**
❌ 没有定义不应该做的事
✅ 明确列出限制条件

**忽略格式**
❌ 让 AI 自由发挥输出格式
✅ 定义清晰的输出结构`,
            warning: '修改 System Prompt 后要充分测试，确保 Agent 行为符合预期。'
          }
        ]
      },
      {
        id: 'tools-config',
        title: 'Tools 配置',
        description: '配置和使用工具',
        duration: 5,
        steps: [
          {
            id: 'tools-1',
            title: '可用的 Tools',
            content: `ZenFlux Agent 提供多种内置工具：

**搜索类**
• \`web_search\`: 网络搜索
• \`exa_search\`: AI 驱动的智能搜索
• \`knowledge_search\`: 知识库检索

**代码执行**
• \`code_execution\`: 在沙盒中运行代码
• \`sandbox_tools\`: 文件操作、项目运行

**文档生成**
• \`ppt_generator\`: 生成 PPT
• \`slidespeak\`: SlideSpeak API 集成

**其他**
• \`api_calling\`: 调用外部 API
• \`scheduled_task\`: 定时任务`
          },
          {
            id: 'tools-2',
            title: '配置 Tools',
            content: `在 Agent 配置中指定可用工具：`,
            code: `# 基础工具配置
tools:
  - web_search
  - code_execution
  - file_operations

# 工具参数配置
tool_config:
  web_search:
    max_results: 10
    safe_search: true
  code_execution:
    timeout: 60
    max_memory: "512MB"`,
            codeLanguage: 'yaml',
            tip: '只启用需要的工具，避免 Agent 在不必要的场景使用工具。'
          }
        ]
      },
      {
        id: 'mcp-integration',
        title: 'MCP 集成',
        description: '集成外部服务',
        duration: 5,
        steps: [
          {
            id: 'mcp-1',
            title: '什么是 MCP',
            content: `MCP (Model Context Protocol) 是 Anthropic 提出的开放协议，用于连接 AI 模型和外部工具/数据源。

通过 MCP，ZenFlux Agent 可以：

• 连接数据库和 API
• 访问本地文件系统
• 集成第三方服务
• 使用自定义工具

MCP 让 Agent 的能力边界大大扩展，可以与几乎任何系统集成。`
          },
          {
            id: 'mcp-2',
            title: '配置 MCP 服务',
            content: `在配置中添加 MCP 服务：`,
            code: `# MCP 服务配置
mcp_servers:
  - name: filesystem
    command: npx
    args:
      - "-y"
      - "@anthropic/mcp-filesystem"
      - "/path/to/directory"
  
  - name: database
    command: python
    args:
      - "mcp_servers/database_server.py"
    env:
      DB_URL: "postgresql://..."`,
            codeLanguage: 'yaml',
            warning: 'MCP 服务需要单独安装和配置。确保服务安全可靠后再启用。'
          },
          {
            id: 'mcp-3',
            title: '恭喜完成！',
            content: `你已完成 ZenFlux Agent 的全部教程！

**你学到了：**
✅ ZenFlux Agent 的核心概念
✅ 创建和配置自定义 Agent
✅ 使用和管理 Skills
✅ 知识库的使用方法
✅ 高级配置技巧

**下一步：**
• 创建你的第一个自定义 Agent
• 上传你的文档到知识库
• 探索更多 Skills 的用法
• 尝试 MCP 集成

祝你使用愉快！`,
            action: {
              type: 'navigate',
              label: '开始使用',
              path: '/'
            }
          }
        ]
      }
    ]
  }
]
