# Zenflux Agent - Claude-Powered Intelligent Agent Framework

> 基于 Claude 原生能力的智能体框架，支持 RVR（Read-Validate-Reflect）机制和流式输出

## 🎯 项目概述

Zenflux Agent 是一个基于 Claude Sonnet 4.5 构建的智能体框架，充分利用 Claude 的原生能力：

- **Extended Thinking**: 深度推理能力
- **Tool Use**: 5种工具调用方式（Direct, Code Execution, Programmatic, Streaming, Tool Search）
- **Prompt Caching**: 降低成本和延迟
- **Memory Protocol**: 跨会话记忆管理

## 📁 项目结构

```
CoT_agent/mvp/
├── /                 # V3 架构（推荐使用）
│   ├── core/                 # 核心组件
│   │   ├── agent.py          # SimpleAgent（流式+RVR）
│   │   ├── llm_service.py    # LLM 服务封装
│   │   ├── memory.py         # 记忆管理
│   │   ├── capability_registry.py    # 能力注册表
│   │   ├── capability_router.py      # 能力路由
│   │   └── invocation_selector.py    # 调用方式选择器
│   ├── config/               # 配置文件
│   │   └── capabilities.yaml # 能力配置（统一数据源）
│   ├── prompts/              # 提示词
│   ├── tools/                # 工具层
│   ├── skills/               # Skills 库
│   ├── docs/                 # 文档
│   └── examples/             # 示例代码
├── docs/v3/                  # V3 架构文档
│   ├── 00-ARCHITECTURE-OVERVIEW.md
│   ├── 01-MEMORY-PROTOCOL.md
│   ├── 02-CAPABILITY-ROUTING.md
│   ├── 03-SKILLS-DISCOVERY.md
│   └── 04-TOOL-CALLING-STRATEGIES.md
└── tests_v3/                 # 测试用例

```

## 🚀 快速开始

### 安装依赖

```bash
pip install anthropic pyyaml
```

### 基本使用

```python
from core.agent import create_simple_agent

# 创建 Agent
agent = create_simple_agent()

# 同步执行
result = await agent.run("帮我生成一个产品PPT")

# 流式执行（推荐）
async for event in agent.stream("帮我生成一个产品PPT"):
    if event["type"] == "thinking":
        print(f"💭 {event['data']['text']}", end="", flush=True)
    elif event["type"] == "content":
        print(event['data']['text'], end="", flush=True)
    elif event["type"] == "tool_call_start":
        print(f"\n🔧 {event['data']['tool_name']}")
    elif event["type"] == "plan_update":
        print(f"\n📋 {event['data']['progress']}")
```

## 🏗️ 核心特性

### 1. 流式输出架构

- **实时反馈**: thinking、content、工具进度实时输出
- **分层设计**: LLM Service 封装能力，Agent 集成 RVR
- **统一事件**: 标准化事件格式，易于前端消费

参考文档：`/docs/STREAMING_ARCHITECTURE.md`

### 2. RVR 循环机制

```
[Read] → [Reason] → [Act] → [Validate] → [Reflect] → [Write]
  ↑                                                       ↓
  └─────────────────── Repeat ──────────────────────────┘
```

- **Read**: 从 Memory 读取 Plan 状态
- **Reason**: Extended Thinking 深度推理
- **Act**: 执行工具调用
- **Validate**: 验证结果质量
- **Reflect**: 失败时反思调整
- **Write**: 更新 Plan 进度

### 3. 动态工具筛选

- **能力抽象层**: 8个抽象能力分类
- **Router 筛选**: 从 12 个工具筛选到 5 个相关工具
- **智能选择**: Sonnet 根据场景自主选择最优工具

### 4. 5种工具调用方式

| 调用方式 | 使用场景 | 示例 |
|---------|---------|------|
| Direct Tool Call | 单工具+简单参数 | `web_search("天气")` |
| Code Execution | 配置生成、计算 | 生成 PPT JSON 配置 |
| Programmatic | 多工具编排(>2) | 批量搜索+聚合 |
| Streaming | 大参数(>10KB) | 流式传输 PPT 配置 |
| Tool Search | 工具数量>30 | 动态发现工具 |

## 📚 文档

### 核心文档
- [架构总览](docs/v3/00-ARCHITECTURE-OVERVIEW.md) - 完整架构设计
- [流式输出架构](/docs/STREAMING_ARCHITECTURE.md) - 流式输出设计
- [Memory Protocol](docs/v3/01-MEMORY-PROTOCOL.md) - 记忆管理协议
- [Capability Routing](docs/v3/02-CAPABILITY-ROUTING.md) - 能力路由算法
- [Tool Calling Strategies](docs/v3/04-TOOL-CALLING-STRATEGIES.md) - 工具调用策略

### 示例代码
- [streaming_example.py](/examples/streaming_example.py) - 流式输出示例

## 🧪 测试

```bash
# 运行测试
cd tests_v3
pytest test_simple_task_logic.py
pytest test_invocation_selector.py
pytest test_multi_turn_chat.py
```

## 📝 配置

### 环境变量

```bash
export ANTHROPIC_API_KEY="your-api-key"
```

### 能力配置

编辑 `/config/capabilities.yaml` 添加新工具或Skills：

```yaml
capabilities:
  - name: my_tool
    type: TOOL
    capabilities: [web_search]
    priority: 85
    provider: CUSTOM
    implementation:
      module: "my_module.my_tool"
      function: "execute"
```

## 🔧 开发

### 添加新工具

1. 在 `/tools/` 创建工具文件
2. 在 `capabilities.yaml` 注册
3. Router 自动发现并使用

### 添加新 Skill

1. 在 `/skills/library/` 创建 Skill 目录
2. 创建 `SKILL.md` 描述文件
3. 创建 `scripts/` 目录放置脚本
4. SkillsManager 自动发现

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

## 👥 作者

- **刘毅** (ironliuyi)
- Email: liuyi@zenflux.cn

---

**🌟 如果这个项目对你有帮助，请给一个 Star！**
