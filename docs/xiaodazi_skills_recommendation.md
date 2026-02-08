# 小搭子开源 Skills 推荐总表

共计 **49 个** 推荐 Skills，严格遵循小搭子产品定位，聚焦非技术用户的核心办公生产力场景。

## 筛选标准

- **保留**: 非技术用户场景（内容创作、知识管理、办公自动化、任务管理、学习成长）
- **排除**: 开发者工具 (GitHub/Git/CI-CD/Coding Agent) — 与 Cursor/Claude Code 冲突
- **差异化**: 人无我有（本地优先、隐私安全、住在电脑里） | 人有我优（会学习、会干活）
- **二维分类**: OS维度 (common/darwin/win32) x 依赖复杂度 (builtin/lightweight/external/cloud_api)

## 优先级分布

| 优先级 | 数量 | 说明 |
|:---|:---:|:---|
| P0 | 8 | MVP必备 — 零配置即可体验核心价值 |
| P1 | 18 | 快速跟进 — 简单配置即可解锁高价值场景 |
| P2 | 19 | 逐步完善 — 中等配置，丰富使用体验 |
| P3 | 4 | 长期规划 — 复杂配置，生态扩展 |

## 分类统计

| 分类 | 数量 | 代表 Skills |
|:---|:---:|:---|
| 内容创作与写作 | 11 | pptx, docx, remotion, marp-slide |
| SaaS 应用集成 | 9 | Gmail Automation, Google Calendar Automation, Google Drive Automation, Slack Automation |
| 办公自动化 | 7 | Invoice Organizer, Tailored Resume Generator, Brand Guidelines, Internal Comms |
| 图像与视觉 | 6 | imagen, Image Enhancer, excalidraw, draw-io |
| 知识管理与研究 | 5 | deep-research, last30days, article-extractor, tapestry |
| 任务管理与效率 | 4 | planner, task-breakdown, brainstorming, n8n-skills |
| 学习与成长 | 3 | skill-tutor, quiz-maker, job-application-optimizer |
| 智能增强 | 3 | session-memory-bootstrap, memory-management, Theme Factory |
| 社交媒体与营销 | 1 | Twitter Algorithm Optimizer |

## 安装难度分布

| 安装难度 | 数量 | 说明 |
|:---|:---:|:---|
| 极简 | 21 | 纯提示词技能，复制 SKILL.md 即可，零依赖 |
| 简单 | 11 | 需安装 Python 包（pip install），自动处理 |
| 中等 | 15 | 需要 API Key 或安装外部工具（Node.js/CLI） |
| 复杂 | 2 | 需要多步配置、OAuth 授权或外部服务实例 |

## 按安装难度推荐

### 极简 (共 21 个)
| Skill名称 | 分类 | 优先级 | 核心价值 |
|:---|:---|:---:|:---|
| [planner](#planner) | 任务管理与效率 | P0 | 多任务项目结构化计划：拆解目标、分配优先级、设定里程碑 |
| [humanizer](#humanizer) | 内容创作与写作 | P0 | 去除 AI 写作痕迹，使文本更自然、更像人类撰写 |
| [Internal Comms](#internal-comms) | 办公自动化 | P0 | 撰写内部沟通文档：周报、公司通讯、FAQ、状态报告 |
| [Meeting Insights Analyzer](#meeting-insights-analyzer) | 办公自动化 | P0 | 分析会议记录：发言比例、冲突模式、领导风格、行动项提取 |
| [memory-management](#memory-management) | 智能增强 | P0 | 自动管理用户个人记忆、上下文和决策跟踪 |
| [session-memory-bootstrap](#session-memory-bootstrap) | 智能增强 | P0 | 会话启动时自动加载持久化记忆，恢复用户偏好和历史上下文 |
| [brainstorming](#brainstorming) | 任务管理与效率 | P1 | 结构化头脑风暴：通过提问和探索将粗糙想法变为完整方案 |
| [task-breakdown](#task-breakdown) | 任务管理与效率 | P1 | 任务拆解器：将大任务分解为可执行的小步骤（支持中文） |
| [Content Research Writer](#content-research-writer) | 内容创作与写作 | P1 | 辅助高质量内容写作：调研、引用、优化标题、逐段反馈 |
| [clear-writing](#clear-writing) | 内容创作与写作 | P1 | 清晰写作指导，教授简洁、有力、易懂的写作原则 |
| [meeting-notes-to-action-items](#meeting-notes-to-action-items) | 办公自动化 | P1 | 将会议纪要自动转化为结构化行动项，分配责任人和截止日期 |
| [job-application-optimizer](#job-application-optimizer) | 学习与成长 | P1 | 求职申请优化：分析JD、优化简历、准备面试、模拟面试 |
| [beautiful-prose](#beautiful-prose) | 内容创作与写作 | P2 | 优美散文写作指导，注重文学性、节奏感和修辞手法 |
| [Brand Guidelines](#brand-guidelines) | 办公自动化 | P2 | 创建品牌视觉指南：统一配色、字体、设计规范 |
| [quiz-maker](#quiz-maker) | 学习与成长 | P2 | 创建多种题型测验：选择题、判断题、填空题、匹配题 |
| [skill-tutor](#skill-tutor) | 学习与成长 | P2 | 个人导师：教授任何主题，跟踪学习进度，间隔重复复习 |
| [Theme Factory](#theme-factory) | 智能增强 | P2 | 为文档、幻灯片、报告应用专业字体和配色主题（10种预设） |
| [Competitive Ads Extractor](#competitive-ads-extractor) | 知识管理与研究 | P2 | 提取和分析竞品广告：文案策略、创意方向、投放模式 |
| [last30days](#last30days) | 知识管理与研究 | P2 | 研究过去30天互联网热点话题，生成趋势分析报告 |
| [tapestry](#tapestry) | 知识管理与研究 | P2 | 将相关文档互联并生成知识网络摘要 |
| [Twitter Algorithm Optimizer](#twitter-algorithm-optimizer) | 社交媒体与营销 | P2 | 分析和优化推文：利用 Twitter 开源算法洞察提升曝光和互动 |

### 简单 (共 11 个)
| Skill名称 | 分类 | 优先级 | 核心价值 |
|:---|:---|:---:|:---|
| [docx](#docx) | 内容创作与写作 | P0 | 创建、编辑 Word 文档，支持样式、表格、页眉页脚 |
| [pptx](#pptx) | 内容创作与写作 | P0 | 创建、读取、编辑 PowerPoint 演示文稿，内置设计指南和模板 |
| [elegant-reports](#elegant-reports) | 内容创作与写作 | P1 | 生成精美 Nordic 风格 PDF 报告，支持图表、表格、多页排版 |
| [youtube-transcript](#youtube-transcript) | 内容创作与写作 | P1 | 提取 YouTube 视频字幕并生成摘要 |
| [CSV Data Summarizer](#csv-data-summarizer) | 办公自动化 | P1 | 自动分析 CSV 文件，生成洞察报告和可视化图表 |
| [Invoice Organizer](#invoice-organizer) | 办公自动化 | P1 | 自动整理发票和收据：读取文件、提取信息、统一命名、分类归档 |
| [Tailored Resume Generator](#tailored-resume-generator) | 办公自动化 | P1 | 分析职位描述，生成针对性简历，突出匹配的经验和技能 |
| [article-extractor](#article-extractor) | 知识管理与研究 | P1 | 从网页提取完整文章文本和元数据（标题、作者、日期） |
| [Canvas Design](#canvas-design) | 图像与视觉 | P2 | 创建精美视觉艺术作品：海报、设计稿、静态视觉作品（PNG/PDF） |
| [Image Enhancer](#image-enhancer) | 图像与视觉 | P2 | 增强图像质量：提升分辨率、锐度、清晰度 |
| [md-to-epub](#md-to-epub) | 内容创作与写作 | P3 | 将 Markdown 文档转换为专业 EPUB 电子书 |

### 中等 (共 15 个)
| Skill名称 | 分类 | 优先级 | 核心价值 |
|:---|:---|:---:|:---|
| [Gmail Automation](#gmail-automation) | SaaS 应用集成 | P1 | 自动化 Gmail：发送/回复邮件、搜索、标签管理、草稿、附件 |
| [Google Calendar Automation](#google-calendar-automation) | SaaS 应用集成 | P1 | 自动化 Google Calendar：创建/修改事件、查看日程、管理提醒 |
| [google-workspace-skills](#google-workspace-skills) | SaaS 应用集成 | P1 | Google Workspace 全家桶集成：Gmail、Calendar、Chat、Docs、Sheets、Slides、Drive |
| [remotion](#remotion) | 内容创作与写作 | P1 | 使用 React 编程方式创建视频，支持动态图表、数据可视化视频 |
| [imagen](#imagen) | 图像与视觉 | P1 | 使用 Google Gemini API 生成图像，支持 UI 模型、图标、插图 |
| [deep-research](#deep-research) | 知识管理与研究 | P1 | 使用 Gemini Deep Research Agent 执行多步骤自主研究 |
| [Canva Automation](#canva-automation) | SaaS 应用集成 | P2 | 自动化 Canva：创建设计、使用模板、管理品牌素材 |
| [Google Drive Automation](#google-drive-automation) | SaaS 应用集成 | P2 | 自动化 Google Drive：上传/下载、搜索、分享、整理文件 |
| [Slack Automation](#slack-automation) | SaaS 应用集成 | P2 | 自动化 Slack：发送消息、搜索、管理频道、定时发送 |
| [Todoist Automation](#todoist-automation) | SaaS 应用集成 | P2 | 自动化 Todoist：创建/管理任务、项目、标签、过滤器 |
| [Zoom Automation](#zoom-automation) | SaaS 应用集成 | P2 | 自动化 Zoom：创建/管理会议、获取录制、参会者管理 |
| [marp-slide](#marp-slide) | 内容创作与写作 | P2 | 用 Markdown 语法创建幻灯片，7种主题，可导出 PDF/HTML/PPTX |
| [draw-io](#draw-io) | 图像与视觉 | P2 | 生成专业流程图、组织架构图、UML图、网络拓扑图 |
| [excalidraw](#excalidraw) | 图像与视觉 | P2 | 生成手绘风格图表、流程图、思维导图、架构图 |
| [Video Downloader](#video-downloader) | 图像与视觉 | P3 | 从 YouTube 等平台下载视频，支持多种格式和质量选项 |

### 复杂 (共 2 个)
| Skill名称 | 分类 | 优先级 | 核心价值 |
|:---|:---|:---:|:---|
| [DocuSign Automation](#docusign-automation) | SaaS 应用集成 | P3 | 自动化 DocuSign：创建信封、管理模板、发送签署请求 |
| [n8n-skills](#n8n-skills) | 任务管理与效率 | P3 | 理解和操作 n8n 自动化工作流：创建、修改、调试工作流 |

## 按分类推荐

### SaaS 应用集成 (共 9 个)
| Skill名称 | 优先级 | 核心价值 | 安装难度 |
|:---|:---:|:---|:---:|
| [Gmail Automation](#gmail-automation) | P1 | 自动化 Gmail：发送/回复邮件、搜索、标签管理、草稿、附件 | 中等 |
| [Google Calendar Automation](#google-calendar-automation) | P1 | 自动化 Google Calendar：创建/修改事件、查看日程、管理提醒 | 中等 |
| [google-workspace-skills](#google-workspace-skills) | P1 | Google Workspace 全家桶集成：Gmail、Calendar、Chat、Docs、Sheets、Slides、Drive | 中等 |
| [Canva Automation](#canva-automation) | P2 | 自动化 Canva：创建设计、使用模板、管理品牌素材 | 中等 |
| [Google Drive Automation](#google-drive-automation) | P2 | 自动化 Google Drive：上传/下载、搜索、分享、整理文件 | 中等 |
| [Slack Automation](#slack-automation) | P2 | 自动化 Slack：发送消息、搜索、管理频道、定时发送 | 中等 |
| [Todoist Automation](#todoist-automation) | P2 | 自动化 Todoist：创建/管理任务、项目、标签、过滤器 | 中等 |
| [Zoom Automation](#zoom-automation) | P2 | 自动化 Zoom：创建/管理会议、获取录制、参会者管理 | 中等 |
| [DocuSign Automation](#docusign-automation) | P3 | 自动化 DocuSign：创建信封、管理模板、发送签署请求 | 复杂 |

### 任务管理与效率 (共 4 个)
| Skill名称 | 优先级 | 核心价值 | 安装难度 |
|:---|:---:|:---|:---:|
| [planner](#planner) | P0 | 多任务项目结构化计划：拆解目标、分配优先级、设定里程碑 | 极简 |
| [brainstorming](#brainstorming) | P1 | 结构化头脑风暴：通过提问和探索将粗糙想法变为完整方案 | 极简 |
| [task-breakdown](#task-breakdown) | P1 | 任务拆解器：将大任务分解为可执行的小步骤（支持中文） | 极简 |
| [n8n-skills](#n8n-skills) | P3 | 理解和操作 n8n 自动化工作流：创建、修改、调试工作流 | 复杂 |

### 内容创作与写作 (共 11 个)
| Skill名称 | 优先级 | 核心价值 | 安装难度 |
|:---|:---:|:---|:---:|
| [docx](#docx) | P0 | 创建、编辑 Word 文档，支持样式、表格、页眉页脚 | 简单 |
| [humanizer](#humanizer) | P0 | 去除 AI 写作痕迹，使文本更自然、更像人类撰写 | 极简 |
| [pptx](#pptx) | P0 | 创建、读取、编辑 PowerPoint 演示文稿，内置设计指南和模板 | 简单 |
| [Content Research Writer](#content-research-writer) | P1 | 辅助高质量内容写作：调研、引用、优化标题、逐段反馈 | 极简 |
| [clear-writing](#clear-writing) | P1 | 清晰写作指导，教授简洁、有力、易懂的写作原则 | 极简 |
| [elegant-reports](#elegant-reports) | P1 | 生成精美 Nordic 风格 PDF 报告，支持图表、表格、多页排版 | 简单 |
| [remotion](#remotion) | P1 | 使用 React 编程方式创建视频，支持动态图表、数据可视化视频 | 中等 |
| [youtube-transcript](#youtube-transcript) | P1 | 提取 YouTube 视频字幕并生成摘要 | 简单 |
| [beautiful-prose](#beautiful-prose) | P2 | 优美散文写作指导，注重文学性、节奏感和修辞手法 | 极简 |
| [marp-slide](#marp-slide) | P2 | 用 Markdown 语法创建幻灯片，7种主题，可导出 PDF/HTML/PPTX | 中等 |
| [md-to-epub](#md-to-epub) | P3 | 将 Markdown 文档转换为专业 EPUB 电子书 | 简单 |

### 办公自动化 (共 7 个)
| Skill名称 | 优先级 | 核心价值 | 安装难度 |
|:---|:---:|:---|:---:|
| [Internal Comms](#internal-comms) | P0 | 撰写内部沟通文档：周报、公司通讯、FAQ、状态报告 | 极简 |
| [Meeting Insights Analyzer](#meeting-insights-analyzer) | P0 | 分析会议记录：发言比例、冲突模式、领导风格、行动项提取 | 极简 |
| [CSV Data Summarizer](#csv-data-summarizer) | P1 | 自动分析 CSV 文件，生成洞察报告和可视化图表 | 简单 |
| [Invoice Organizer](#invoice-organizer) | P1 | 自动整理发票和收据：读取文件、提取信息、统一命名、分类归档 | 简单 |
| [Tailored Resume Generator](#tailored-resume-generator) | P1 | 分析职位描述，生成针对性简历，突出匹配的经验和技能 | 简单 |
| [meeting-notes-to-action-items](#meeting-notes-to-action-items) | P1 | 将会议纪要自动转化为结构化行动项，分配责任人和截止日期 | 极简 |
| [Brand Guidelines](#brand-guidelines) | P2 | 创建品牌视觉指南：统一配色、字体、设计规范 | 极简 |

### 图像与视觉 (共 6 个)
| Skill名称 | 优先级 | 核心价值 | 安装难度 |
|:---|:---:|:---|:---:|
| [imagen](#imagen) | P1 | 使用 Google Gemini API 生成图像，支持 UI 模型、图标、插图 | 中等 |
| [Canvas Design](#canvas-design) | P2 | 创建精美视觉艺术作品：海报、设计稿、静态视觉作品（PNG/PDF） | 简单 |
| [Image Enhancer](#image-enhancer) | P2 | 增强图像质量：提升分辨率、锐度、清晰度 | 简单 |
| [draw-io](#draw-io) | P2 | 生成专业流程图、组织架构图、UML图、网络拓扑图 | 中等 |
| [excalidraw](#excalidraw) | P2 | 生成手绘风格图表、流程图、思维导图、架构图 | 中等 |
| [Video Downloader](#video-downloader) | P3 | 从 YouTube 等平台下载视频，支持多种格式和质量选项 | 中等 |

### 学习与成长 (共 3 个)
| Skill名称 | 优先级 | 核心价值 | 安装难度 |
|:---|:---:|:---|:---:|
| [job-application-optimizer](#job-application-optimizer) | P1 | 求职申请优化：分析JD、优化简历、准备面试、模拟面试 | 极简 |
| [quiz-maker](#quiz-maker) | P2 | 创建多种题型测验：选择题、判断题、填空题、匹配题 | 极简 |
| [skill-tutor](#skill-tutor) | P2 | 个人导师：教授任何主题，跟踪学习进度，间隔重复复习 | 极简 |

### 智能增强 (共 3 个)
| Skill名称 | 优先级 | 核心价值 | 安装难度 |
|:---|:---:|:---|:---:|
| [memory-management](#memory-management) | P0 | 自动管理用户个人记忆、上下文和决策跟踪 | 极简 |
| [session-memory-bootstrap](#session-memory-bootstrap) | P0 | 会话启动时自动加载持久化记忆，恢复用户偏好和历史上下文 | 极简 |
| [Theme Factory](#theme-factory) | P2 | 为文档、幻灯片、报告应用专业字体和配色主题（10种预设） | 极简 |

### 知识管理与研究 (共 5 个)
| Skill名称 | 优先级 | 核心价值 | 安装难度 |
|:---|:---:|:---|:---:|
| [article-extractor](#article-extractor) | P1 | 从网页提取完整文章文本和元数据（标题、作者、日期） | 简单 |
| [deep-research](#deep-research) | P1 | 使用 Gemini Deep Research Agent 执行多步骤自主研究 | 中等 |
| [Competitive Ads Extractor](#competitive-ads-extractor) | P2 | 提取和分析竞品广告：文案策略、创意方向、投放模式 | 极简 |
| [last30days](#last30days) | P2 | 研究过去30天互联网热点话题，生成趋势分析报告 | 极简 |
| [tapestry](#tapestry) | P2 | 将相关文档互联并生成知识网络摘要 | 极简 |

### 社交媒体与营销 (共 1 个)
| Skill名称 | 优先级 | 核心价值 | 安装难度 |
|:---|:---:|:---|:---:|
| [Twitter Algorithm Optimizer](#twitter-algorithm-optimizer) | P2 | 分析和优化推文：利用 Twitter 开源算法洞察提升曝光和互动 | 极简 |

## Skills 详细信息

### <a name='internal-comms'></a>Internal Comms
**来源**: [anthropics/skills](https://github.com/anthropics/skills/tree/main/skills/internal-comms) | **Stars**: 63500 | **综合评分**: 4.7

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 撰写内部沟通文档：周报、公司通讯、FAQ、状态报告 |
| **Why** (为什么需要) | 每周写周报、写通知很烦，AI自动生成标准格式 |
| **Who** (谁用) | 职场白领、管理者、HR |
| **When** (何时用) | 需要撰写周报、项目更新、内部通知时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md 到 skills 目录，纯提示词技能 |
| **使用示例** | `帮我写这周的项目周报，包含进度、问题和下周计划` |

### <a name='meeting-insights-analyzer'></a>Meeting Insights Analyzer
**来源**: [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) | **Stars**: 32300 | **综合评分**: 4.4

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 分析会议记录：发言比例、冲突模式、领导风格、行动项提取 |
| **Why** (为什么需要) | 会议效率低，AI帮助发现沟通模式和改进方向 |
| **Who** (谁用) | 管理者、HR、团队负责人 |
| **When** (何时用) | 会议结束后需要深度分析会议质量和行动项时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md 到 skills 目录，纯提示词技能 |
| **使用示例** | `分析这份会议记录，提取行动项和关键决策` |

### <a name='docx'></a>docx
**来源**: [anthropics/skills](https://github.com/anthropics/skills/tree/main/skills/docx) | **Stars**: 63500 | **综合评分**: 5

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 创建、编辑 Word 文档，支持样式、表格、页眉页脚 |
| **Why** (为什么需要) | 自动生成格式规范的报告、合同、信函等文档 |
| **Who** (谁用) | 职场白领、研究工作者、学生 |
| **When** (何时用) | 需要生成正式文档、报告、合同时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md 到 skills 目录，依赖 python-docx |
| **使用示例** | `帮我写一份项目可行性分析报告，Word格式，带目录和页码` |

### <a name='humanizer'></a>humanizer
**来源**: [jdrhyne/agent-skills](https://github.com/jdrhyne/agent-skills/tree/main/skills/humanizer) | **Stars**: 163 | **综合评分**: 4.1

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 去除 AI 写作痕迹，使文本更自然、更像人类撰写 |
| **Why** (为什么需要) | AI生成的内容容易被识别，需要润色为自然风格 |
| **Who** (谁用) | 内容创作者、自媒体运营、学生 |
| **When** (何时用) | 需要发布AI辅助撰写的文章、报告、社交媒体内容时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md 到 skills 目录，纯提示词技能，无依赖 |
| **使用示例** | `帮我润色这篇文章，去掉AI味，让它读起来更自然` |

### <a name='memory-management'></a>memory-management
**来源**: [agent-skills.md](https://agent-skills.md/skills/memory-management) | **Stars**: N/A | **综合评分**: 3.8

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 自动管理用户个人记忆、上下文和决策跟踪 |
| **Why** (为什么需要) | AI需要记住用户偏好才能越用越好 |
| **Who** (谁用) | 所有用户 |
| **When** (何时用) | 持续使用过程中自动积累 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md 到 skills 目录，纯提示词技能 |
| **使用示例** | `（自动激活）记住我的写作风格偏好` |

### <a name='planner'></a>planner
**来源**: [jdrhyne/agent-skills](https://github.com/jdrhyne/agent-skills/tree/main/skills/planner) | **Stars**: 163 | **综合评分**: 4.1

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 多任务项目结构化计划：拆解目标、分配优先级、设定里程碑 |
| **Why** (为什么需要) | 复杂项目需要系统规划，AI帮助拆解和排期 |
| **Who** (谁用) | 项目管理者、自由职业者、创业者 |
| **When** (何时用) | 启动新项目、制定季度计划、拆解复杂任务时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md 到 skills 目录，纯提示词技能 |
| **使用示例** | `帮我把这个产品上线计划拆解成可执行的任务清单` |

### <a name='pptx'></a>pptx
**来源**: [anthropics/skills](https://github.com/anthropics/skills/tree/main/skills/pptx) | **Stars**: 63500 | **综合评分**: 5

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 创建、读取、编辑 PowerPoint 演示文稿，内置设计指南和模板 |
| **Why** (为什么需要) | 非技术用户做PPT耗时费力，AI自动生成专业演示文稿 |
| **Who** (谁用) | 职场白领、学生、自由职业者 |
| **When** (何时用) | 需要制作产品发布、工作汇报、教学课件等演示文稿时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md 到 skills 目录，依赖 python-pptx |
| **使用示例** | `帮我做一份10页的产品发布PPT，包含公司介绍和市场分析` |

### <a name='session-memory-bootstrap'></a>session-memory-bootstrap
**来源**: [agent-skills.md (jgh0sh)](https://github.com/jgh0sh/session-memory-bootstrap) | **Stars**: 21 | **综合评分**: 4.1

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 会话启动时自动加载持久化记忆，恢复用户偏好和历史上下文 |
| **Why** (为什么需要) | 每次新对话都要重新解释背景，记忆系统解决这个问题 |
| **Who** (谁用) | 所有用户 |
| **When** (何时用) | 每次启动新会话时自动激活 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md 到 skills 目录，纯提示词技能 |
| **使用示例** | `（自动激活）记住我喜欢简洁的报告风格` |

### <a name='csv-data-summarizer'></a>CSV Data Summarizer
**来源**: [ComposioHQ/awesome-claude-skills (@coffeefuelbump)](https://github.com/ComposioHQ/awesome-claude-skills) | **Stars**: 32300 | **综合评分**: 3.4

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 自动分析 CSV 文件，生成洞察报告和可视化图表 |
| **Why** (为什么需要) | 数据分析门槛高，AI自动发现数据规律和趋势 |
| **Who** (谁用) | 职场白领、研究工作者、数据分析师 |
| **When** (何时用) | 拿到数据文件需要快速了解数据概况时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md，依赖 pandas/matplotlib |
| **使用示例** | `分析这个销售数据CSV，告诉我有什么有趣的发现` |

### <a name='content-research-writer'></a>Content Research Writer
**来源**: [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) | **Stars**: 32300 | **综合评分**: 4

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 辅助高质量内容写作：调研、引用、优化标题、逐段反馈 |
| **Why** (为什么需要) | 写深度文章需要大量调研和反复修改，AI加速全流程 |
| **Who** (谁用) | 内容创作者、研究工作者、自媒体运营 |
| **When** (何时用) | 撰写深度文章、研究报告、专栏内容时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md 到 skills 目录，纯提示词技能 |
| **使用示例** | `帮我写一篇关于AI办公自动化趋势的深度文章，要有数据引用` |

### <a name='gmail-automation'></a>Gmail Automation
**来源**: [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills/tree/main/gmail-automation) | **Stars**: 32300 | **综合评分**: 4.7

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 自动化 Gmail：发送/回复邮件、搜索、标签管理、草稿、附件 |
| **Why** (为什么需要) | 邮件管理是每天最耗时的任务之一 |
| **Who** (谁用) | 职场白领、自由职业者、管理者 |
| **When** (何时用) | 需要批量处理邮件、自动回复、邮件分类时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 通过 Composio 连接，需要 API Key 和 OAuth 授权 |
| **使用示例** | `帮我回复所有未读的客户咨询邮件` |

### <a name='google-calendar-automation'></a>Google Calendar Automation
**来源**: [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills/tree/main/google-calendar-automation) | **Stars**: 32300 | **综合评分**: 4.7

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 自动化 Google Calendar：创建/修改事件、查看日程、管理提醒 |
| **Why** (为什么需要) | 日程管理是高频需求，语音/文字创建日程更自然 |
| **Who** (谁用) | 职场白领、自由职业者、管理者 |
| **When** (何时用) | 需要安排会议、查看日程、设置提醒时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 通过 Composio 连接，需要 OAuth 授权 |
| **使用示例** | `帮我安排下周一下午3点和张总的会议` |

### <a name='invoice-organizer'></a>Invoice Organizer
**来源**: [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) | **Stars**: 32300 | **综合评分**: 4.4

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 自动整理发票和收据：读取文件、提取信息、统一命名、分类归档 |
| **Why** (为什么需要) | 报税季整理发票痛苦，AI自动分类省时省力 |
| **Who** (谁用) | 自由职业者、小型企业主、财务人员 |
| **When** (何时用) | 报税前整理发票、日常收据管理时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md，依赖 pypdf/Pillow |
| **使用示例** | `帮我把下载文件夹里的所有发票按月份整理好` |

### <a name='tailored-resume-generator'></a>Tailored Resume Generator
**来源**: [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) | **Stars**: 32300 | **综合评分**: 4.4

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 分析职位描述，生成针对性简历，突出匹配的经验和技能 |
| **Why** (为什么需要) | 每个职位都需要定制简历，手动调整耗时 |
| **Who** (谁用) | 求职者、职场人士 |
| **When** (何时用) | 投递简历、求职面试准备时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md，依赖 python-docx/reportlab |
| **使用示例** | `根据这个产品经理职位描述，帮我优化简历` |

### <a name='article-extractor'></a>article-extractor
**来源**: [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) | **Stars**: 32300 | **综合评分**: 4

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 从网页提取完整文章文本和元数据（标题、作者、日期） |
| **Why** (为什么需要) | 网页内容杂乱，自动提取干净的正文内容 |
| **Who** (谁用) | 研究工作者、学生、内容创作者 |
| **When** (何时用) | 需要收集和整理网络文章、建立资料库时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md，依赖 beautifulsoup4/requests |
| **使用示例** | `帮我提取这5个网页的文章内容，整理成一份资料` |

### <a name='brainstorming'></a>brainstorming
**来源**: [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) | **Stars**: 32300 | **综合评分**: 4

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 结构化头脑风暴：通过提问和探索将粗糙想法变为完整方案 |
| **Why** (为什么需要) | 独自思考容易陷入死角，AI作为思维伙伴拓展思路 |
| **Who** (谁用) | 创业者、产品经理、内容创作者 |
| **When** (何时用) | 需要创意灵感、方案构思、问题解决时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md 到 skills 目录，纯提示词技能 |
| **使用示例** | `帮我头脑风暴一下，如何提升公众号的阅读量` |

### <a name='clear-writing'></a>clear-writing
**来源**: [agent-skills.md](https://agent-skills.md/skills/clear-writing) | **Stars**: N/A | **综合评分**: 3.7

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 清晰写作指导，教授简洁、有力、易懂的写作原则 |
| **Why** (为什么需要) | 提升用户写作质量，避免冗长啰嗦的表达 |
| **Who** (谁用) | 职场白领、学生、内容创作者 |
| **When** (何时用) | 撰写邮件、报告、文章需要提升表达质量时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md 到 skills 目录，纯提示词技能 |
| **使用示例** | `帮我改写这段话，让它更简洁有力` |

### <a name='deep-research'></a>deep-research
**来源**: [ComposioHQ/awesome-claude-skills (@sanjay3290)](https://github.com/ComposioHQ/awesome-claude-skills) | **Stars**: 32300 | **综合评分**: 4.4

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 使用 Gemini Deep Research Agent 执行多步骤自主研究 |
| **Why** (为什么需要) | 深度调研耗时数天，AI自动完成市场分析、竞品调研 |
| **Who** (谁用) | 研究工作者、咨询顾问、产品经理 |
| **When** (何时用) | 需要进行市场分析、竞品研究、文献综述时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md，需要 Gemini API Key |
| **使用示例** | `帮我调研国内AI办公助手市场，分析前5名竞品` |

### <a name='elegant-reports'></a>elegant-reports
**来源**: [jdrhyne/agent-skills](https://github.com/jdrhyne/agent-skills/tree/main/skills/elegant-reports) | **Stars**: 163 | **综合评分**: 4.1

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 生成精美 Nordic 风格 PDF 报告，支持图表、表格、多页排版 |
| **Why** (为什么需要) | 自动生成设计感强的专业报告，省去排版时间 |
| **Who** (谁用) | 职场白领、研究工作者、咨询顾问 |
| **When** (何时用) | 需要生成美观的分析报告、调研报告、项目报告时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md 到 skills 目录，依赖 reportlab/fpdf2 |
| **使用示例** | `把这份市场调研数据生成一份精美的PDF报告` |

### <a name='google-workspace-skills'></a>google-workspace-skills
**来源**: [ComposioHQ/awesome-claude-skills (@sanjay3290)](https://github.com/ComposioHQ/awesome-claude-skills) | **Stars**: 32300 | **综合评分**: 4.4

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | Google Workspace 全家桶集成：Gmail、Calendar、Chat、Docs、Sheets、Slides、Drive |
| **Why** (为什么需要) | 一个 Skill 打通 Google 全套办公应用，极高性价比 |
| **Who** (谁用) | 使用 Google Workspace 的职场白领 |
| **When** (何时用) | 需要跨 Google 应用操作时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md，需要 Google OAuth 授权 |
| **使用示例** | `帮我查看今天的日历，把会议纪要写到Google Docs，发邮件给参会者` |

### <a name='imagen'></a>imagen
**来源**: [ComposioHQ/awesome-claude-skills (@sanjay3290)](https://github.com/ComposioHQ/awesome-claude-skills) | **Stars**: 32300 | **综合评分**: 4.4

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 使用 Google Gemini API 生成图像，支持 UI 模型、图标、插图 |
| **Why** (为什么需要) | 快速生成配图、海报、图标，无需设计技能 |
| **Who** (谁用) | 内容创作者、自媒体运营、职场白领 |
| **When** (何时用) | 需要文章配图、社交媒体图片、PPT插图时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md，需要 Gemini API Key |
| **使用示例** | `给这篇咖啡文化文章生成3张配图` |

### <a name='job-application-optimizer'></a>job-application-optimizer
**来源**: [agent-skills.md (OneWave-AI)](https://github.com/OneWave-AI/job-application-optimizer) | **Stars**: 237 | **综合评分**: 4.1

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 求职申请优化：分析JD、优化简历、准备面试、模拟面试 |
| **Why** (为什么需要) | 求职是高频刚需，AI全流程辅助提升成功率 |
| **Who** (谁用) | 求职者、应届毕业生、职场转型者 |
| **When** (何时用) | 准备求职、投递简历、面试准备时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md 到 skills 目录，纯提示词技能 |
| **使用示例** | `帮我分析这个职位要求，优化我的简历和准备面试问题` |

### <a name='meeting-notes-to-action-items'></a>meeting-notes-to-action-items
**来源**: [agent-skills.md](https://agent-skills.md/skills/meeting-notes-to-action-items) | **Stars**: N/A | **综合评分**: 3.8

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 将会议纪要自动转化为结构化行动项，分配责任人和截止日期 |
| **Why** (为什么需要) | 会议后行动项容易遗忘，自动提取确保执行 |
| **Who** (谁用) | 职场白领、项目管理者、团队负责人 |
| **When** (何时用) | 会议结束后需要快速整理待办事项时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md 到 skills 目录，纯提示词技能 |
| **使用示例** | `把这份会议纪要转成行动项清单，标注负责人和截止日期` |

### <a name='remotion'></a>remotion
**来源**: [remotion-dev/skills](https://github.com/remotion-dev/skills) | **Stars**: 21000 | **综合评分**: 4.7

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 使用 React 编程方式创建视频，支持动态图表、数据可视化视频 |
| **Why** (为什么需要) | 视频内容创作门槛高，AI驱动的视频生成大幅降低制作难度 |
| **Who** (谁用) | 内容创作者、自媒体运营、教育工作者 |
| **When** (何时用) | 需要制作数据可视化视频、产品演示视频、教学视频时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | npx skills add remotion-dev/skills，需要 Node.js 环境 |
| **使用示例** | `用这些销售数据生成一个30秒的动态图表视频` |

### <a name='task-breakdown'></a>task-breakdown
**来源**: [agent-skills.md](https://agent-skills.md/skills/task-breakdown) | **Stars**: N/A | **综合评分**: 3.4

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 任务拆解器：将大任务分解为可执行的小步骤（支持中文） |
| **Why** (为什么需要) | 大任务让人不知从何下手，拆解后一步步执行 |
| **Who** (谁用) | 职场白领、学生、自由职业者 |
| **When** (何时用) | 面对复杂任务不知如何开始时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md 到 skills 目录，纯提示词技能 |
| **使用示例** | `帮我把'组织公司年会'拆解成具体的执行步骤` |

### <a name='youtube-transcript'></a>youtube-transcript
**来源**: [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) | **Stars**: 32300 | **综合评分**: 4

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 提取 YouTube 视频字幕并生成摘要 |
| **Why** (为什么需要) | 快速消化视频内容，无需看完整个视频 |
| **Who** (谁用) | 研究工作者、学生、内容创作者 |
| **When** (何时用) | 需要快速了解视频内容、提取关键信息时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md，依赖 youtube-transcript-api |
| **使用示例** | `帮我总结这个1小时的TED演讲视频的核心观点` |

### <a name='brand-guidelines'></a>Brand Guidelines
**来源**: [anthropics/skills](https://github.com/anthropics/skills/tree/main/skills/brand-guidelines) | **Stars**: 63500 | **综合评分**: 4.3

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 创建品牌视觉指南：统一配色、字体、设计规范 |
| **Why** (为什么需要) | 保持品牌一致性，所有输出物风格统一 |
| **Who** (谁用) | 自媒体运营、小型企业主、设计师 |
| **When** (何时用) | 建立品牌形象、统一视觉风格时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md 到 skills 目录，纯提示词技能 |
| **使用示例** | `帮我建立一套品牌视觉指南，主色调用深蓝色` |

### <a name='canva-automation'></a>Canva Automation
**来源**: [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills/tree/main/canva-automation) | **Stars**: 32300 | **综合评分**: 3.7

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 自动化 Canva：创建设计、使用模板、管理品牌素材 |
| **Why** (为什么需要) | Canva是最流行的设计工具，AI驱动设计更高效 |
| **Who** (谁用) | 内容创作者、自媒体运营、小型企业主 |
| **When** (何时用) | 需要快速制作社交媒体图片、海报、名片时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 通过 Composio 连接，需要 Canva API 授权 |
| **使用示例** | `帮我用Canva做一张微信公众号封面图` |

### <a name='canvas-design'></a>Canvas Design
**来源**: [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) | **Stars**: 32300 | **综合评分**: 4

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 创建精美视觉艺术作品：海报、设计稿、静态视觉作品（PNG/PDF） |
| **Why** (为什么需要) | 无需设计软件，AI直接生成专业级视觉设计 |
| **Who** (谁用) | 内容创作者、自媒体运营、小型企业主 |
| **When** (何时用) | 需要制作海报、宣传图、社交媒体封面时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md，依赖 Pillow/Cairo |
| **使用示例** | `帮我设计一张读书会活动海报` |

### <a name='competitive-ads-extractor'></a>Competitive Ads Extractor
**来源**: [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) | **Stars**: 32300 | **综合评分**: 3.4

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 提取和分析竞品广告：文案策略、创意方向、投放模式 |
| **Why** (为什么需要) | 竞品分析是营销必备，AI自动收集和分析广告数据 |
| **Who** (谁用) | 市场人员、自媒体运营、创业者 |
| **When** (何时用) | 需要了解竞品营销策略、寻找广告灵感时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md 到 skills 目录，纯提示词技能 |
| **使用示例** | `帮我分析这3个竞品的广告文案策略` |

### <a name='google-drive-automation'></a>Google Drive Automation
**来源**: [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills/tree/main/google-drive-automation) | **Stars**: 32300 | **综合评分**: 4

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 自动化 Google Drive：上传/下载、搜索、分享、整理文件 |
| **Why** (为什么需要) | 云盘文件管理混乱，AI帮助智能整理和搜索 |
| **Who** (谁用) | 职场白领、学生、团队协作者 |
| **When** (何时用) | 需要在云盘中查找、整理、分享文件时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 通过 Composio 连接，需要 OAuth 授权 |
| **使用示例** | `帮我在Google Drive里找到上个月的项目文档并分享给团队` |

### <a name='image-enhancer'></a>Image Enhancer
**来源**: [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) | **Stars**: 32300 | **综合评分**: 3.4

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 增强图像质量：提升分辨率、锐度、清晰度 |
| **Why** (为什么需要) | 手机拍的照片模糊、截图不清晰，一键增强 |
| **Who** (谁用) | 职场白领、内容创作者、学生 |
| **When** (何时用) | 需要提升图片质量用于演示、文档、社交媒体时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md，依赖 Pillow |
| **使用示例** | `帮我把这张模糊的截图增强清晰度` |

### <a name='slack-automation'></a>Slack Automation
**来源**: [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills/tree/main/slack-automation) | **Stars**: 32300 | **综合评分**: 4

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 自动化 Slack：发送消息、搜索、管理频道、定时发送 |
| **Why** (为什么需要) | Slack消息太多，AI帮助筛选重要信息和自动回复 |
| **Who** (谁用) | 职场白领、团队管理者 |
| **When** (何时用) | 需要在Slack中发送通知、搜索历史消息、管理频道时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 通过 Composio 连接，需要 Slack App 授权 |
| **使用示例** | `帮我在项目频道发送本周进度更新` |

### <a name='theme-factory'></a>Theme Factory
**来源**: [anthropics/skills](https://github.com/anthropics/skills/tree/main/skills/theme-factory) | **Stars**: 63500 | **综合评分**: 3.9

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 为文档、幻灯片、报告应用专业字体和配色主题（10种预设） |
| **Why** (为什么需要) | 统一视觉风格，所有输出物保持一致的专业感 |
| **Who** (谁用) | 职场白领、内容创作者 |
| **When** (何时用) | 需要统一文档风格、建立个人品牌时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md 到 skills 目录，纯提示词技能 |
| **使用示例** | `给我所有的文档和PPT应用'Nordic'主题风格` |

### <a name='todoist-automation'></a>Todoist Automation
**来源**: [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills/tree/main/todoist-automation) | **Stars**: 32300 | **综合评分**: 4

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 自动化 Todoist：创建/管理任务、项目、标签、过滤器 |
| **Why** (为什么需要) | 任务管理是日常刚需，语音/文字添加任务更自然 |
| **Who** (谁用) | 职场白领、学生、自由职业者 |
| **When** (何时用) | 需要添加待办、管理项目任务、设置提醒时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 通过 Composio 连接，需要 Todoist API Token |
| **使用示例** | `帮我把这些会议行动项添加到Todoist项目中` |

### <a name='twitter-algorithm-optimizer'></a>Twitter Algorithm Optimizer
**来源**: [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills/tree/main/twitter-algorithm-optimizer) | **Stars**: 32300 | **综合评分**: 3.7

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 分析和优化推文：利用 Twitter 开源算法洞察提升曝光和互动 |
| **Why** (为什么需要) | 社交媒体运营需要了解算法，AI帮助优化内容策略 |
| **Who** (谁用) | 自媒体运营、内容创作者、市场人员 |
| **When** (何时用) | 发布推文前优化内容、分析互动数据时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md 到 skills 目录，纯提示词技能 |
| **使用示例** | `帮我优化这条推文，让它获得更多曝光` |

### <a name='zoom-automation'></a>Zoom Automation
**来源**: [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills/tree/main/zoom-automation) | **Stars**: 32300 | **综合评分**: 4

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 自动化 Zoom：创建/管理会议、获取录制、参会者管理 |
| **Why** (为什么需要) | Zoom会议管理繁琐，AI帮助自动安排和整理 |
| **Who** (谁用) | 职场白领、管理者、教育工作者 |
| **When** (何时用) | 需要安排Zoom会议、获取会议录制、管理参会者时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 通过 Composio 连接，需要 Zoom OAuth 授权 |
| **使用示例** | `帮我创建明天下午2点的团队周会Zoom链接` |

### <a name='beautiful-prose'></a>beautiful-prose
**来源**: [agent-skills.md](https://agent-skills.md/skills/beautiful-prose) | **Stars**: N/A | **综合评分**: 3.4

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 优美散文写作指导，注重文学性、节奏感和修辞手法 |
| **Why** (为什么需要) | 帮助用户撰写更有感染力的文学性内容 |
| **Who** (谁用) | 内容创作者、自媒体运营、文学爱好者 |
| **When** (何时用) | 撰写公众号文章、散文、品牌故事等需要文学性的内容时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md 到 skills 目录，纯提示词技能 |
| **使用示例** | `帮我用散文风格写一篇关于秋天的公众号文章` |

### <a name='draw-io'></a>draw-io
**来源**: [softaworks/agent-toolkit](https://github.com/softaworks/agent-toolkit/tree/main/skills/draw-io) | **Stars**: 200 | **综合评分**: 3.7

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 生成专业流程图、组织架构图、UML图、网络拓扑图 |
| **Why** (为什么需要) | 专业级图表绘制，适合正式文档和报告 |
| **Who** (谁用) | 职场白领、项目管理者、咨询顾问 |
| **When** (何时用) | 需要绘制专业级流程图、组织架构图时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md，生成 .drawio XML 格式文件 |
| **使用示例** | `帮我画一个公司组织架构图` |

### <a name='excalidraw'></a>excalidraw
**来源**: [softaworks/agent-toolkit](https://github.com/softaworks/agent-toolkit/tree/main/skills/excalidraw) | **Stars**: 200 | **综合评分**: 3.7

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 生成手绘风格图表、流程图、思维导图、架构图 |
| **Why** (为什么需要) | 快速可视化想法和流程，手绘风格更亲切易懂 |
| **Who** (谁用) | 职场白领、教育工作者、项目管理者 |
| **When** (何时用) | 需要画流程图、思维导图、概念图时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md，需安装 Excalidraw CLI 或使用 JSON 格式 |
| **使用示例** | `帮我画一个项目开发流程图，手绘风格` |

### <a name='last30days'></a>last30days
**来源**: [jdrhyne/agent-skills](https://github.com/jdrhyne/agent-skills/tree/main/skills/last30days) | **Stars**: 163 | **综合评分**: 3.4

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 研究过去30天互联网热点话题，生成趋势分析报告 |
| **Why** (为什么需要) | 追踪行业动态和热点，保持信息敏感度 |
| **Who** (谁用) | 内容创作者、自媒体运营、市场人员 |
| **When** (何时用) | 需要了解行业最新动态、寻找选题灵感时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md 到 skills 目录，纯提示词技能 |
| **使用示例** | `帮我调研AI领域过去30天的热点话题和趋势` |

### <a name='marp-slide'></a>marp-slide
**来源**: [softaworks/agent-toolkit](https://github.com/softaworks/agent-toolkit/tree/main/skills/marp-slide) | **Stars**: 200 | **综合评分**: 3.7

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 用 Markdown 语法创建幻灯片，7种主题，可导出 PDF/HTML/PPTX |
| **Why** (为什么需要) | 快速将文本内容转化为演示文稿，无需设计技能 |
| **Who** (谁用) | 职场白领、教育工作者、研究人员 |
| **When** (何时用) | 需要快速制作简洁幻灯片、技术分享、教学课件时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md，需安装 @marp-team/marp-cli |
| **使用示例** | `把这篇会议纪要转成一份简洁的幻灯片` |

### <a name='quiz-maker'></a>quiz-maker
**来源**: [agent-skills.md](https://agent-skills.md/skills/quiz-maker) | **Stars**: N/A | **综合评分**: 3.1

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 创建多种题型测验：选择题、判断题、填空题、匹配题 |
| **Why** (为什么需要) | 主动测试是最有效的学习方法，AI自动生成测验 |
| **Who** (谁用) | 学生、教育工作者、培训师 |
| **When** (何时用) | 复习备考、制作教学测验、培训考核时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md 到 skills 目录，纯提示词技能 |
| **使用示例** | `根据这章教材内容，帮我出20道选择题` |

### <a name='skill-tutor'></a>skill-tutor
**来源**: [agent-skills.md (Nitzan94)](https://agent-skills.md/skills/skill-tutor) | **Stars**: 5 | **综合评分**: 3.5

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 个人导师：教授任何主题，跟踪学习进度，间隔重复复习 |
| **Why** (为什么需要) | 自学缺乏系统性和反馈，AI作为私人导师持续指导 |
| **Who** (谁用) | 学生、终身学习者、职场人士 |
| **When** (何时用) | 学习新技能、备考、系统性学习某个领域时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md 到 skills 目录，纯提示词技能 |
| **使用示例** | `教我学习数据分析，从零开始，每天30分钟` |

### <a name='tapestry'></a>tapestry
**来源**: [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) | **Stars**: 32300 | **综合评分**: 3.4

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 将相关文档互联并生成知识网络摘要 |
| **Why** (为什么需要) | 散落的文档缺乏关联，自动构建知识图谱 |
| **Who** (谁用) | 研究工作者、学生、知识管理者 |
| **When** (何时用) | 需要整理大量文档、发现知识关联时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md 到 skills 目录，纯提示词技能 |
| **使用示例** | `把这10篇论文的核心观点整理成知识网络` |

### <a name='docusign-automation'></a>DocuSign Automation
**来源**: [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills/tree/main/docusign-automation) | **Stars**: 32300 | **综合评分**: 3.4

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 自动化 DocuSign：创建信封、管理模板、发送签署请求 |
| **Why** (为什么需要) | 电子签名流程繁琐，AI帮助自动化合同签署流程 |
| **Who** (谁用) | 企业主、法务、销售人员 |
| **When** (何时用) | 需要发送合同签署、管理签署流程时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 通过 Composio 连接，需要 DocuSign API 授权 |
| **使用示例** | `帮我用DocuSign发送这份合同给客户签署` |

### <a name='video-downloader'></a>Video Downloader
**来源**: [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) | **Stars**: 32300 | **综合评分**: 3.3

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 从 YouTube 等平台下载视频，支持多种格式和质量选项 |
| **Why** (为什么需要) | 离线观看、素材收集、内容二次创作 |
| **Who** (谁用) | 内容创作者、学生、研究工作者 |
| **When** (何时用) | 需要下载视频素材、离线学习材料时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md，需安装 yt-dlp |
| **使用示例** | `帮我下载这个教程视频的最高画质版本` |

### <a name='md-to-epub'></a>md-to-epub
**来源**: [ComposioHQ/awesome-claude-skills (@smerchek)](https://github.com/ComposioHQ/awesome-claude-skills) | **Stars**: 32300 | **综合评分**: 3

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 将 Markdown 文档转换为专业 EPUB 电子书 |
| **Why** (为什么需要) | 将笔记、文章整理成电子书格式，方便阅读和分享 |
| **Who** (谁用) | 内容创作者、研究工作者、教育工作者 |
| **When** (何时用) | 需要将文章合集、课程笔记转为电子书时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md，依赖 ebooklib |
| **使用示例** | `把我这10篇公众号文章合并成一本EPUB电子书` |

### <a name='n8n-skills'></a>n8n-skills
**来源**: [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) | **Stars**: 32300 | **综合评分**: 3.4

| 维度 | 内容 |
|:---|:---|
| **What** (是什么) | 理解和操作 n8n 自动化工作流：创建、修改、调试工作流 |
| **Why** (为什么需要) | n8n是流行的自动化平台，AI帮助构建复杂工作流 |
| **Who** (谁用) | 效率达人、自由职业者、小型企业主 |
| **When** (何时用) | 需要构建跨应用自动化工作流时 |
| **Where** (在哪用) | macOS / Windows / Linux |
| **How** (怎么装) | 复制 SKILL.md，需要本地或云端 n8n 实例 |
| **使用示例** | `帮我创建一个n8n工作流：新邮件自动整理到Notion` |
