# Agent V3.6 文档

> 📅 **最后更新**: 2025-12-23  
> 🎯 **当前版本**: V3.6 - Memory-First + Prompt-Driven

---

## 📚 文档结构（总分关系）

```
docs/v3/
├── README.md                    # 👈 你在这里（索引 + 快速开始）
├── 00-ARCHITECTURE-OVERVIEW.md  # 【总】整体架构（必读）
├── 01-MEMORY-PROTOCOL.md        # 【分】Memory-First Protocol
├── 02-CAPABILITY-ROUTING.md     # 【分】能力路由
├── 03-SKILLS-DISCOVERY.md       # 【分】Skills 发现
├── 04-TOOL-CALLING-STRATEGIES.md# 【分】工具调用策略
├── HITL-USAGE-GUIDE.md          # 【分】人机协作
└── archive/                     # 归档（旧文档）
```

---

## 🚀 快速开始

### 1. 核心概念（1分钟理解）

```
┌─────────────────────────────────────────────────────────────┐
│                    V3.6 核心架构                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  System Prompt = 大脑（定义所有逻辑规则）                    │
│  Agent Code   = 骨架（框架管理，不含业务规则）              │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │             WorkingMemory (Short Memory)              │ │
│  │  ┌──────────┐  ┌──────────┐                          │ │
│  │  │plan.json │  │ todo.md  │  ← 避免多轮 token 浪费   │ │
│  │  └────↑─────┘  └────↑─────┘                          │ │
│  └───────┴─────────────┴────────────────────────────────┘ │
│          │ CRUD (via plan_todo tool)                       │
│          │                                                  │
│  ┌───────┴─────────────────────────────────────────────────┐
│  │                    LLM (Claude)                         │
│  │  • 每步开始：调用 plan_todo.get_plan()  ← MANDATORY     │
│  │  • 每步结束：调用 plan_todo.update_step() ← MANDATORY   │
│  └─────────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────┘
```

### 2. 基本使用

```python
from agent_v3 import SimpleAgent, create_simple_agent

# 创建 Agent
agent = create_simple_agent(verbose=True)

# 运行任务
result = await agent.run("创建一个AI产品介绍PPT")

# 查看结果
print(result["final_result"])
```

### 3. 关键改进（V3.6 vs V3.5）

| 特性 | V3.5 | V3.6 |
|------|------|------|
| **Plan/Todo 存储** | 文件系统 | ✅ Short Memory（WorkingMemory） |
| **Plan 管理** | PlanningManager | ✅ plan_todo 工具 |
| **Memory Protocol** | 无 | ✅ 每步 Read → Act → Write |
| **Token 优化** | 无 | ✅ 避免多轮传递完整 Plan |
| **架构理念** | Code-Driven | ✅ Prompt-Driven |

---

## 📖 阅读顺序

### 必读（理解架构）

1. **[00-ARCHITECTURE-OVERVIEW.md](./00-ARCHITECTURE-OVERVIEW.md)** ⭐⭐⭐
   - 整体架构图
   - Memory-First Protocol
   - RVR 循环
   - 核心组件

### 按需阅读（深入理解）

2. **[01-MEMORY-PROTOCOL.md](./01-MEMORY-PROTOCOL.md)** ⭐⭐
   - Plan/Todo 存储机制
   - 每步 Read → Write 协议
   - 参考 Claude Platform Memory Tool

3. **[02-CAPABILITY-ROUTING.md](./02-CAPABILITY-ROUTING.md)** ⭐⭐
   - 能力路由算法
   - 评分机制

4. **[03-SKILLS-DISCOVERY.md](./03-SKILLS-DISCOVERY.md)** ⭐
   - Skills 发现机制
   - 创建自定义 Skills

5. **[04-TOOL-CALLING-STRATEGIES.md](./04-TOOL-CALLING-STRATEGIES.md)** ⭐⭐
   - Direct Tool Call
   - Code Execution
   - Programmatic Tool Calling

6. **[HITL-USAGE-GUIDE.md](./HITL-USAGE-GUIDE.md)** ⭐
   - Human-in-the-Loop
   - 用户反馈改进

---

## 🗂️ 代码位置速查

| 组件 | 文件 | 说明 |
|------|------|------|
| **SimpleAgent** | `agent_v3/core/agent.py` | 核心 Agent |
| **WorkingMemory** | `agent_v3/core/memory.py` | Short Memory |
| **PlanTodoTool** | `agent_v3/tools/plan_todo_tool.py` | Plan/Todo CRUD |
| **CapabilityRouter** | `agent_v3/core/capability_router.py` | 能力路由 |
| **SkillsManager** | `agent_v3/core/skills_manager.py` | Skills 管理 |
| **LLMService** | `agent_v3/core/llm_service.py` | LLM 封装 |
| **System Prompt** | `agent_v3/prompts/universal_prompt.py` | 系统提示词 |

---

## 📊 关键概念速查

| 概念 | 说明 | 位置 |
|------|------|------|
| **Memory-First** | 每步读写 Short Memory | [01-MEMORY-PROTOCOL.md](./01-MEMORY-PROTOCOL.md) |
| **Prompt-Driven** | 系统提示词定义逻辑 | [00-ARCHITECTURE-OVERVIEW.md](./00-ARCHITECTURE-OVERVIEW.md) |
| **RVR 循环** | React+Validation+Reflection | [00-ARCHITECTURE-OVERVIEW.md](./00-ARCHITECTURE-OVERVIEW.md) |
| **plan_todo Tool** | Plan/Todo CRUD 工具 | [01-MEMORY-PROTOCOL.md](./01-MEMORY-PROTOCOL.md) |
| **Capability Routing** | 能力路由评分 | [02-CAPABILITY-ROUTING.md](./02-CAPABILITY-ROUTING.md) |
| **Code-First** | 配置生成用代码执行 | [04-TOOL-CALLING-STRATEGIES.md](./04-TOOL-CALLING-STRATEGIES.md) |

---

## 📁 归档文档

查看 [archive/](./archive/) 目录了解历史设计文档：
- V3.5 及更早版本的设计
- Invocation Strategy 设计过程
- 历史架构对比

---

**🎉 欢迎使用 Agent V3.6！**
