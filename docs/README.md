# ZenFlux Agent — 小搭子桌面端实例

> 基于 ZenFlux Agent V9.0，为"养在电脑里的小搭子"设计的桌面端 AI 智能体。
> 100% 本地存储、Skills-First 能力体系、跨平台（macOS / Windows / Linux）。

## 架构定位

| 维度 | 云端版（dazee_agent） | 桌面版（xiaodazi） |
|---|---|---|
| 部署形态 | SaaS 服务 | Tauri 桌面应用 |
| 存储方案 | SQLite + FTS5 + sqlite-vec | SQLite + FTS5 + sqlite-vec |
| 能力来源 | MCP 工具 + REST API | Skills-First + 本地操作 + MCP Apps |
| 用户画像 | 企业用户 / 技术团队 | 个人用户 / 非技术用户 |
| 配置门槛 | 需运维部署 | 零配置开箱即用 |

## 技术架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        小搭子桌面应用（Tauri + Vue）                          │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                           UI 层                                        │  │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────────────┐ ┌─────────────────┐      │  │
│  │  │ 对话界面 │ │ 项目管理 │ │ MCP Apps iframe │ │ Skills 市场      │      │  │
│  │  └─────────┘ └─────────┘ └─────────────────┘ └─────────────────┘      │  │
│  │                              ↕ postMessage                              │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │  │
│  │  │            MCP Apps Client（Vue Component）                      │  │  │
│  │  │  • iframe 生命周期管理  • JSON-RPC 桥接  • UI 资源缓存           │  │  │
│  │  └─────────────────────────────────────────────────────────────────┘  │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │  │
│  │  │         ProgressRenderer（进度展示组件）                          │  │  │
│  │  │  • 友好进度消息展示  • 进度条渲染  • 隐藏技术细节                   │  │  │
│  │  └─────────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                   ↕ IPC
┌─────────────────────────────────────────────────────────────────────────────┐
│                      小搭子 Agent 实例（Python/Rust）                        │
│                                                                               │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │              意图与规划层（简化版 IntentAnalyzer + ProgressTransformer）  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │      状态一致性层 + 终止策略层（StateConsistencyManager + Terminator）   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │          Agent 引擎层（RVRBAgent + BacktrackManager + PlanTodoTool）    │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │     Skills-First 能力层（SkillRegistry + 二维分类 OS × 依赖复杂度）      │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │       OS 兼容层（MacOSLocalNode / WindowsLocalNode / LinuxLocalNode）   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  本地知识检索（LocalKnowledgeManager: FTS5 全文搜索 + sqlite-vec 语义）  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │              MCP Apps 服务层（UI 资源注册 / ui:// 协议 / CSP 安全）      │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    存储层（100% 本地）                                  │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐      │  │
│  │  │ SQLite      │ │ SQLite FTS5 │ │ sqlite-vec  │ │ Skills 缓存 │      │  │
│  │  │ (消息/会话) │ │ (全文索引)   │ │ (可选向量)  │ │ (延迟加载)  │      │  │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘      │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 项目结构

```
zenflux_agent/
├── main.py                      # FastAPI 入口
├── core/                        # 核心组件
│   ├── agent/                   # Agent 编排（RVRBAgent / BacktrackManager）
│   ├── llm/                     # LLM 适配（Claude / OpenAI / Gemini / Qwen）
│   ├── memory/                  # 记忆管理（Mem0 / 系统记忆 / 工作记忆）
│   ├── planning/                # 规划系统（PlanTodoTool / ProgressTransformer）
│   ├── routing/                 # 意图分析与路由
│   ├── skill/                   # Skill 加载器（动态 / 延迟）
│   ├── tool/                    # 工具选择与执行
│   ├── events/                  # 事件管理
│   └── context/                 # 运行上下文
├── infra/                       # 基础设施
│   ├── database/                # PostgreSQL（云端版）
│   ├── local_store/             # SQLite 本地存储（桌面版）   ← 新增
│   │   ├── engine.py            #   异步引擎（aiosqlite + WAL）
│   │   ├── models.py            #   ORM 模型（会话 / 消息 / Skills 缓存）
│   │   ├── fts.py               #   FTS5 全文索引
│   │   ├── vector.py            #   sqlite-vec 可选向量搜索
│   │   ├── skills_cache.py      #   Skills 延迟加载缓存
│   │   ├── workspace.py         #   Workspace 管理器（统一入口）
│   │   └── crud/                #   CRUD 操作层
│   ├── cache/                   # 缓存
│   ├── storage/                 # 文件存储（本地 / S3）
│   └── cache/                   # 缓存层
├── instances/                   # 实例配置
│   ├── dazee_agent/             # 云端版实例
│   └── xiaodazi/                # 桌面版实例                  ← 新增
│       ├── config.yaml          #   实例配置
│       ├── prompt.md            #   小搭子人格提示词
│       ├── skills/              #   预置 Skills
│       │   ├── local-automation/
│       │   ├── content-creation/
│       │   ├── productivity/
│       │   └── data-analysis/
│       ├── ui_resources/        #   MCP Apps UI 资源
│       └── prompt_results/
├── routers/                     # API 路由
├── services/                    # 业务服务
├── tools/                       # 工具实现
├── skills/                      # 全局 Skills 库
├── config/                      # 配置文件
├── models/                      # Pydantic 数据模型
├── frontend/                    # Vue 前端
└── docs/                        # 文档
    └── architecture/
        └── xiaodazi-desktop.md  # 桌面版详细架构设计
```

## 快速开始（开发者指南）

### 前置要求

| 工具 | 最低版本 | 推荐版本 | 说明 |
|---|---|---|---|
| Python | 3.10+ | 3.12 | 后端服务 |
| Node.js | 18+ | 20 LTS | 前端构建 |
| Rust | 1.70+ | latest stable | Tauri 桌面壳（可选） |
| pnpm / npm | - | pnpm | 前端包管理 |

### 第一步：安装 Python 环境

```bash
# macOS（Homebrew）
brew install python@3.12

# Ubuntu / Debian
sudo apt update && sudo apt install python3.12 python3.12-venv python3-pip

# Windows（winget）
winget install Python.Python.3.12

# 验证
python3 --version  # Python 3.12.x
```

### 第二步：创建 Python 虚拟环境并安装依赖

```bash
# 进入项目根目录
cd zenflux_agent

# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境
# macOS / Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 第三步：配置环境变量

配置文件位于用户数据目录的 `config.yaml`，首次启动时会自动创建。

```bash
# macOS: ~/Library/Application Support/com.zenflux.agent/config.yaml
# Linux: ~/.local/share/zenflux-agent/config.yaml
# Windows: %APPDATA%\zenflux-agent\config.yaml
```

**方式一：通过前端设置页面配置（推荐）**

启动应用后，访问设置页面填写 API Key。

**方式二：手动编辑 config.yaml**

```yaml
api_keys:
  ANTHROPIC_API_KEY: sk-ant-api03-your-key-here  # 至少配置一个大模型（推荐 Claude）
  # OPENAI_API_KEY: sk-xxx  # 可选
  # DASHSCOPE_API_KEY: sk-xxx  # 可选（千问）

llm:
  COT_AGENT_MODEL: claude-sonnet-4-5-20250514  # 默认模型
  QOS_LEVEL: PRO  # 服务等级

app:
  LOG_LEVEL: INFO  # 日志级别
```

### 第四步：启动后端服务

```bash
# 确保虚拟环境已激活
source .venv/bin/activate

# 启动开发服务器（默认 http://localhost:8000）
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

验证服务：

```bash
curl http://localhost:8000/health
```

### 第五步：安装 Node.js 和前端依赖

```bash
# macOS（Homebrew）
brew install node

# Ubuntu / Debian（通过 NodeSource）
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Windows（winget）
winget install OpenJS.NodeJS.LTS

# 验证
node --version   # v20.x.x
npm --version    # 10.x.x
```

安装前端依赖：

```bash
cd frontend
npm install
```

### 第六步：启动前端开发服务器

```bash
# 在 frontend/ 目录下
npm run dev

# 前端开发服务器默认运行在 http://localhost:5174
```

### 第七步（可选）：Tauri 桌面应用开发

如需开发 Tauri 桌面应用，还需安装 Rust 工具链：

```bash
# 安装 Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# macOS 额外依赖
xcode-select --install

# Ubuntu / Debian 额外依赖
sudo apt install libwebkit2gtk-4.1-dev build-essential curl wget file \
  libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev

# 验证
rustc --version  # rustc 1.70+
```

启动 Tauri 开发模式（同时启动前端 + 后端 + 桌面壳）：

```bash
cd frontend
npm run tauri:dev
```

构建桌面应用：

```bash
cd frontend
npm run tauri:build
```

### 常用开发命令速查

```bash
# ---- 后端 ----
source .venv/bin/activate            # 激活虚拟环境
uvicorn main:app --reload            # 启动后端（开发模式）
pytest tests/unit/ -v                # 运行单元测试
pytest tests/integration/ -v         # 运行集成测试

# ---- 前端 ----
cd frontend
npm run dev                          # 启动前端开发服务器
npm run build                        # 构建前端生产包
npm run type-check                   # TypeScript 类型检查
npm run lint                         # ESLint 代码检查

# ---- 桌面应用 ----
cd frontend
npm run tauri:dev                    # Tauri 开发模式
npm run tauri:build                  # Tauri 生产构建
```

### 常见问题

**Q: `pip install` 报错找不到某些系统依赖？**

部分 Python 包（如 `Pillow`、`sqlite-vec`）需要系统级依赖：

```bash
# macOS
brew install libjpeg libpng

# Ubuntu / Debian
sudo apt install libjpeg-dev libpng-dev
```

**Q: 前端启动后页面空白？**

确认后端服务已启动并运行在 `http://localhost:8000`。前端需要后端 API 才能正常工作。

**Q: Tauri 构建失败？**

确保 Rust 工具链是最新的：

```bash
rustup update
```

**Q: 端口冲突？**

后端默认使用 `8000` 端口，前端默认使用 `5174` 端口。如需修改：

```bash
# 后端换端口
uvicorn main:app --port 9000 --reload

# 前端换端口（修改 vite.config.ts 或使用 --port 参数）
npm run dev -- --port 3000
```

## 核心机制

### 1. 存储层（100% 本地）

| 组件 | 技术 | 说明 |
|---|---|---|
| 消息/会话 | SQLite + aiosqlite | WAL 模式，异步读写 |
| 全文索引 | SQLite FTS5 | BM25 排序，unicode61 分词，零配置 |
| 向量搜索 | sqlite-vec | 可选扩展，不可用时优雅降级 |
| Skills 缓存 | SQLite 表 | 延迟加载 + file_mtime 变更检测 |

代码入口：`infra/local_store/workspace.py` → `LocalWorkspace`

### 2. Skills-First 能力体系

二维分类（OS × 依赖复杂度）：

```
                    依赖复杂度 →
           ┌──────────┬─────────────┬──────────┬───────────┐
           │ builtin  │ lightweight │ external │ cloud_api │
    OS ↓   │ (内置)    │ (轻量)      │ (外部)    │ (云服务)   │
┌──────────┼──────────┼─────────────┼──────────┼───────────┤
│ common   │summarize │excel-       │obsidian  │notion     │
│ (跨平台)  │canvas    │analyzer     │          │gemini-img │
├──────────┼──────────┼─────────────┼──────────┼───────────┤
│ darwin   │screenshot│apple-notes  │peekaboo  │           │
├──────────┼──────────┼─────────────┼──────────┼───────────┤
│ win32    │screenshot│outlook-cli  │powershell│           │
├──────────┼──────────┼─────────────┼──────────┼───────────┤
│ linux    │screenshot│notify-send  │xdotool   │           │
└──────────┴──────────┴─────────────┴──────────┴───────────┘

状态管理: ready → need_auth → need_setup → unavailable
```

### 3. 零配置/低配置设计

**大模型配置**（开源项目，不提供免费额度）：

| 优先级 | 方案 | 门槛 | 适用场景 |
|---|---|---|---|
| 1 | Gemini（Google 免费额度 1500 req/day） | 3 分钟配置 | 大多数用户 |
| 2 | 本地模型（Ollama / LM Studio） | 10 分钟安装 | 隐私敏感 / 离线 |
| 3 | OpenAI / Claude 等 | 自备 API Key | 进阶用户 |

**本地知识检索**（渐进式解锁）：

| 层级 | 方案 | 配置门槛 | 依赖 |
|---|---|---|---|
| Level 1（默认） | SQLite FTS5 全文搜索 | 零（选择文件夹即可） | 内置 |
| Level 2（可选） | sqlite-vec 语义搜索 | 一键启用 | 复用已配 LLM API |
| Level 3（进阶） | 外部向量库 | 用户自行配置 | Chroma / Qdrant |

### 4. 状态一致性管理

```
任务开始 → 创建快照（文件备份 + 环境状态）
    ↓
执行操作 → 记录操作日志（含逆操作定义）
    ↓
  ┌─ 正常完成 → 提交（清理快照）
  └─ 异常/中断 → HITL 询问用户 → 回滚 / 保持 / 继续
```

### 5. 多维度终止策略

```
LLM 自主终止（任务完成自评）
    + HITL 人工干预（危险操作确认）
    + 用户主动停止（"算了" / "取消"）
    + 安全兜底（max_turns=100 / 30min 超时）
    + 长任务确认（>20 轮时询问）
```

### 6. OS 兼容层

| 平台 | 节点 | 核心能力 |
|---|---|---|
| macOS | `MacOSLocalNode` | AppleScript / screencapture / pbcopy |
| Windows | `WindowsLocalNode` | PowerShell / WinAPI / clip |
| Linux | `LinuxLocalNode` | X11 & Wayland / xdotool / xclip |

### 7. MCP Apps UI 集成

> "别的智能体返回文本，小搭子返回界面"

工具执行完成 → 返回带 `_meta.ui` 的结果 → 前端渲染到 iframe → 用户在 UI 中交互

## 实施路线图

| 阶段 | 内容 | 周期 |
|---|---|---|
| Phase 1 | 基础实例（目录结构 / 人格提示词 / Skills 加载） | 2 周 |
| Phase 2 | 自适应终止（AdaptiveTerminator / HITL 集成） | 1 周 |
| Phase 3 | OS 兼容性（三平台 LocalNode / Skill 适配） | 2 周 |
| Phase 4 | MCP Apps 集成（MCPAppViewer / UI 模板库） | 2 周 |
| Phase 5 | Tauri 桌面壳（IPC 通信 / 三平台打包） | 2 周 |

## 文档

| 文档 | 说明 |
|---|---|
| [桌面版详细架构](docs/architecture/xiaodazi-desktop.md) | 完整设计：Skills 分类、配置向导、状态管理、知识检索 |
| [V4 架构总览](docs/architecture/00-ARCHITECTURE-V4.md) | ZenFlux Agent 核心架构 |
| [Memory Protocol](docs/architecture/01-MEMORY-PROTOCOL.md) | 跨会话记忆管理 |
| [事件协议](docs/architecture/03-EVENT-PROTOCOL.md) | 统一事件系统 |

## 开发

### 添加新 Skill

1. 在 `instances/xiaodazi/skills/` 创建目录
2. 创建 `SKILL.md`（兼容 OpenClaw 格式）
3. 配置 `metadata.xiaodazi.dependency_level`（builtin / lightweight / external / cloud_api）
4. SkillRegistry 自动发现并按 OS + 依赖复杂度分类

### 运行测试

```bash
# 确保虚拟环境已激活
source .venv/bin/activate

# 单元测试
pytest tests/unit/ -v

# 集成测试
pytest tests/integration/ -v

# 端到端测试
pytest tests/e2e/ -v

# 运行全部测试
pytest -v
```

## 许可证

MIT License

## 作者

- **刘屹** (ironliuyi) - liuyi@zenflux.cn
- **汪康成** - wangkangcheng@zenflux.cn
- **曾梦琪** - zengmengqi@zenflux.cn
- **谢海鹏** - xiehaipeng@zenflux.cn
