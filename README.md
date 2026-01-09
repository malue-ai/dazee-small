# ZenFlux Agent

> 基于 Claude 原生能力的智能体框架，支持 RVR 循环、流式输出、E2B 沙箱集成

## 🎯 项目概述

ZenFlux Agent 是一个基于 Claude Sonnet/Haiku 4.5 构建的智能体框架，充分利用 Claude 的原生能力：

- **Extended Thinking**: 深度推理能力
- **Tool Use**: 5 种工具调用方式
- **E2B 沙箱**: 安全的代码执行环境
- **Memory Protocol**: 跨会话记忆管理

## 📁 项目结构

```
zenflux_agent/
├── main.py                  # FastAPI 入口
├── core/                    # 🧠 核心组件
│   ├── agent/               # Agent 编排
│   ├── llm/                 # LLM 服务封装
│   ├── memory/              # 记忆管理
│   ├── tool/                # 工具选择与执行
│   ├── events/              # 事件管理
│   └── context/             # 运行上下文
├── routers/                 # 🌐 API 路由
├── services/                # 💼 业务服务
├── tools/                   # 🔧 工具实现
├── skills/                  # 📚 Skills 库
├── prompts/                 # 📝 提示词模板
├── config/                  # ⚙️ 配置文件
├── infra/                   # 🏗️ 基础设施
│   ├── database/            # 数据库
│   ├── cache/               # 缓存
│   └── storage/             # 存储
├── models/                  # 📊 数据模型
├── tests/                   # 🧪 测试
│   ├── e2e/                 # 端到端测试
│   ├── integration/         # 集成测试
│   └── unit/                # 单元测试
├── scripts/                 # 🛠️ 工具脚本
├── docs/                    # 📖 文档
│   ├── architecture/        # 架构文档
│   ├── guides/              # 使用指南
│   ├── specs/               # 规范文档
│   └── deployment/          # 部署文档
└── frontend/                # 🖥️ 前端界面
```

## 🚀 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置环境变量

```bash
cp env.template .env
# 编辑 .env 设置 ANTHROPIC_API_KEY 等
```

### 启动服务

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 基本使用

```python
from core.agent import create_simple_agent
from core.events import EventManager

# 创建 Agent
event_manager = EventManager()
agent = create_simple_agent(
    model="claude-sonnet-4-5-20250929",
    event_manager=event_manager
)

# 流式执行
async for event in agent.chat(messages, session_id="session_001"):
    print(event)
```

## 🏗️ 核心特性

### 1. V4 模块化架构

| 模块 | 位置 | 说明 |
|------|------|------|
| Agent 编排 | `core/agent/` | SimpleAgent 核心编排 |
| 工具选择 | `core/tool/selector.py` | 动态工具筛选 |
| 工具执行 | `core/tool/executor.py` | 统一工具执行 |
| 记忆管理 | `core/memory/` | user/ + system/ 层级 |
| 事件管理 | `core/events/` | 6 类统一事件 |

### 2. RVR 循环机制

```
[Read] → [Reason] → [Act] → [Validate] → [Reflect] → [Write]
  ↑                                                       ↓
  └─────────────────── Repeat ──────────────────────────┘
```

### 3. 动态工具筛选

- **能力抽象层**: 11 个抽象能力分类
- **Router 筛选**: 根据任务动态筛选相关工具
- **智能选择**: LLM 根据场景自主选择最优工具

### 4. 5 种工具调用方式

| 调用方式 | 使用场景 |
|---------|---------|
| Direct Tool Call | 单工具 + 简单参数 |
| Code Execution | 配置生成、计算 |
| E2B 沙箱 | 第三方包、长时运行 |
| Programmatic | 多工具编排 |
| Tool Search | 工具数量 > 30 |

## 📚 文档

详细文档请查看 [docs/README.md](docs/README.md)

### 核心文档

- [V4 架构总览](docs/architecture/00-ARCHITECTURE-V4.md) ⭐
- [Memory Protocol](docs/architecture/01-MEMORY-PROTOCOL.md)
- [事件协议](docs/architecture/03-EVENT-PROTOCOL.md)
- [E2B 集成](docs/guides/E2B_INTEGRATION.md)

## 🧪 测试

```bash
# 单元测试
pytest tests/unit/

# 集成测试
pytest tests/integration/

# E2E 测试
pytest tests/e2e/
```

## 📝 配置

### 能力配置

编辑 `config/capabilities.yaml` 添加新工具：

```yaml
capabilities:
  - name: my_tool
    type: TOOL
    capabilities: [web_search]
    priority: 85
    implementation:
      module: "tools.my_tool"
```

## 🔧 开发

### 添加新工具

1. 在 `tools/` 创建工具文件
2. 在 `config/capabilities.yaml` 注册
3. Router 自动发现并使用

### 添加新 Skill

1. 在 `skills/library/` 创建 Skill 目录
2. 创建 `SKILL.md` 描述文件
3. SkillsManager 自动发现

## 🚀 部署

```bash
# Docker 部署
docker-compose up -d

# 详细部署文档
cat docs/deployment/DOCKER_DEPLOYMENT.md
```

## 📄 许可证

MIT License

## 👥 作者

- **刘屹** (ironliuyi) - liuyi@zenflux.cn
- **汪康成** - wangkangcheng@zenflux.cn

---

**🌟 如果这个项目对你有帮助，请给一个 Star！**
