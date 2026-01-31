# client_agent Skills

本目录包含 client_agent 实例的所有技能。

## 技能来源

这些技能从 clawdbot 项目导入，经过适配用于 zenflux agent 框架。

## 技能列表

### macOS 核心自动化
- **peekaboo**: macOS UI 自动化（截图、点击、输入、窗口管理）
- **apple-notes**: Apple Notes 管理
- **apple-reminders**: Apple Reminders 管理
- **things-mac**: Things 3 任务管理
- **bear-notes**: Bear Notes 管理

### 消息通讯
- **imsg**: iMessage 消息发送
- **slack**: Slack 集成
- **discord**: Discord 集成

### 开发者工具
- **github**: GitHub CLI 操作
- **tmux**: Tmux 会话管理
- **coding-agent**: 编码代理

### 媒体工具
- **camsnap**: 摄像头截图
- **video-frames**: 视频帧提取
- **openai-whisper**: 本地语音转文字

### 生产力工具
- **1password**: 1Password CLI
- **notion**: Notion 笔记
- **obsidian**: Obsidian 知识库
- **trello**: Trello 看板

### 智能家居
- **openhue**: Philips Hue 灯光控制
- **sonoscli**: Sonos 音响控制

### 其他
- **weather**: 天气查询
- **summarize**: 内容摘要
- **nano-pdf**: PDF 处理

## 使用方法

Agent 会根据用户意图自动选择合适的技能，读取对应的 SKILL.md 文件获取使用指南。

## 添加新技能

1. 在此目录创建新文件夹
2. 添加 SKILL.md 文件定义技能
3. 在 skill_registry.yaml 中注册
