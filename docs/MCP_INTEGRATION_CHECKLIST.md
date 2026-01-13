# MCP 工具接入清单

> 📅 创建日期：2026-01-12  
> 🎯 目标：为 Dazee.ai（AI 工作伙伴）集成 MCP 生态工具  
> 📌 产品定位：搭建系统、智能分析、工作总结、业务梳理

---

## 📊 快速概览

### 已确认优先接入（⭐ 标记）

| 类别 | 工具 | 优先级 | 核心场景 |
|-----|------|--------|---------|
| 🏢 **知识管理** | Notion MCP | P0 | 业务梳理、团队知识库 |
| 💬 **国内通讯** | 飞书/钉钉 MCP | P0 | 国内企业协作 |
| 📁 **文档协作** | Google Drive MCP | P1 | 海外用户文档管理 |
| 🌐 **浏览器** | Puppeteer MCP | P1 | 网页抓取、自动化 |
| 💼 **外企通讯** | Slack MCP | P1 | 外企消息通知 |
| 📋 **项目管理** | Linear MCP | P1 | 任务追踪 |
| 🎨 **设计协作** | Figma MCP | P1 | 设计转代码 |
| 💻 **代码管理** | GitHub MCP | P1 | 技术用户仓库操作 |

### 已有内置方案（无需重复接入）

| 能力 | 内置方案 | 对应 MCP |
|-----|---------|---------|
| 记忆增强 | `core/memory/` + mem0 | Memory MCP |
| 数据库查询 | 内置数据库服务 | PostgreSQL/MySQL MCP |
| 文件操作 | `sandbox_*` 沙盒工具 | Filesystem MCP |
| 搜索 | `exa_search` + `web_search` | Brave Search MCP (待评估) |

---

## 一、MCP 资源平台汇总

| 平台 | 链接 | 说明 | 推荐度 |
|-----|------|------|--------|
| **官方 MCP 服务器** | [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) | Anthropic 官方维护，质量最高 | ⭐⭐⭐⭐⭐ |
| **Glama MCP 目录** | [glama.ai/mcp/servers](https://glama.ai/mcp/servers) | 可视化目录，方便搜索 | ⭐⭐⭐⭐⭐ |
| **MCP Hub** | [mcphub.io](https://mcphub.io) | 社区维护的 MCP 市场 | ⭐⭐⭐⭐ |
| **Smithery** | [smithery.ai](https://smithery.ai) | MCP 工具市场 | ⭐⭐⭐⭐ |
| **MCP 中文站** | [mcpcn.com](https://mcpcn.com/tools/) | 中文社区资源 | ⭐⭐⭐⭐ |
| **MCPdb** | [mcpdb.org](https://mcpdb.org/zh/tools) | 教程和实施指南 | ⭐⭐⭐ |
| **Awesome MCP Servers** | [punkpeye/awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers) | 精选 MCP 列表 | ⭐⭐⭐⭐⭐ |

---

## 二、接入优先级分层

### 🔴 P0 - 核心必接（第一批）

这些工具直接支撑产品核心场景，建议优先集成。

| 工具名称 | 能力类别 | 场景价值 | 官方/社区 | GitHub/来源 | 状态 |
|---------|---------|---------|-----------|-------------|------|
| **MetaMCP** | 聚合器 | MCP 管理中间件，一次接入多个 MCP | 社区 | [metatool-ai/metatool-app](https://github.com/metatool-ai/metatool-app) | ⬜ 待接入 |
| **Notion MCP** ⭐ | 知识管理 | 业务梳理、团队知识管理首选 | 🎖️ 官方 | [servers/src/notion](https://github.com/modelcontextprotocol/servers/tree/main/src/notion) | ⬜ 待接入 |
| **飞书 MCP** ⭐ | 企业通讯 | 国内企业通讯首选，消息+文档+日历 | 社区 | 需自研或寻找社区实现 | ⬜ 待调研 |
| **钉钉 MCP** ⭐ | 企业通讯 | 国内中小企业用户，阿里系 | 社区 | 需自研或寻找社区实现 | ⬜ 待调研 |
| ~~**PostgreSQL MCP**~~ | 数据库 | 智能分析 - 直接查企业数据库 | 🎖️ 官方 | [servers/src/postgres](https://github.com/modelcontextprotocol/servers/tree/main/src/postgres) | ✅ **已有内置方案** |
| ~~**MySQL MCP**~~ | 数据库 | 智能分析 - 国内企业数据库首选 | 社区 | [designcomputer/mysql-mcp-server](https://github.com/designcomputer/mysql-mcp-server) | ✅ **已有内置方案** |
| ~~**Filesystem MCP**~~ | 文件系统 | 本地文件读写、目录管理 | 🎖️ 官方 | [servers/src/filesystem](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem) | ✅ **已有内置方案** (sandbox_*) |

### 🟡 P1 - 重要扩展（第二批）

增强现有能力，提升用户体验。

| 工具名称 | 能力类别 | 场景价值 | 官方/社区 | GitHub/来源 | 状态 |
|---------|---------|---------|-----------|-------------|------|
| **Google Drive MCP** ⭐ | 文档协作 | 访问 Google Docs/Sheets，海外用户必备 | 🎖️ 官方 | [servers/src/gdrive](https://github.com/modelcontextprotocol/servers/tree/main/src/gdrive) | ⬜ 待接入 |
| **Puppeteer MCP** ⭐ | 浏览器自动化 | 增强信息获取，抓取需要登录的页面 | 🎖️ 官方 | [servers/src/puppeteer](https://github.com/modelcontextprotocol/servers/tree/main/src/puppeteer) | ⬜ 待接入 |
| **Slack MCP** ⭐ | 企业通讯 | 外企用户消息通知渠道 | 🎖️ 官方 | [servers/src/slack](https://github.com/modelcontextprotocol/servers/tree/main/src/slack) | ⬜ 待接入 |
| **GitHub MCP** ⭐ | 代码管理 | 技术用户代码仓库管理，很实用 | 🎖️ 官方 | [servers/src/github](https://github.com/modelcontextprotocol/servers/tree/main/src/github) | ⬜ 待接入 |
| **Linear MCP** ⭐ | 项目管理 | 任务追踪、项目管理场景 | 社区 | [jerhadf/linear-mcp-server](https://github.com/jerhadf/linear-mcp-server) | ⬜ 待接入 |
| **Figma MCP** ⭐ | 设计协作 | 设计稿解析、设计转代码 | 社区 | [nicholasoxford/cursor-figma-mcp](https://github.com/nicholasoxford/cursor-figma-mcp) | ⬜ 待接入 |
| **Brave Search MCP** | 搜索增强 | 补充现有 Exa 搜索 | 🎖️ 官方 | [servers/src/brave-search](https://github.com/modelcontextprotocol/servers/tree/main/src/brave-search) | ⬜ 待评估 |
| ~~**Memory MCP**~~ | 记忆增强 | 长期记忆、知识图谱 | 🎖️ 官方 | [servers/src/memory](https://github.com/modelcontextprotocol/servers/tree/main/src/memory) | ✅ **已有内置方案** (core/memory + mem0) |

### 🟢 P2 - 锦上添花（第三批）

特定场景增强，按需接入。

| 工具名称 | 能力类别 | 场景价值 | 官方/社区 | GitHub/来源 | 状态 |
|---------|---------|---------|-----------|-------------|------|
| **企业微信 MCP** | 企业通讯 | 腾讯系企业用户 | 社区 | 需自研或寻找社区实现 | ⬜ 待调研 |
| **Airtable MCP** | 轻量数据库 | 灵活数据管理、无代码数据库 | 社区 | [domdomegg/airtable-mcp-server](https://github.com/domdomegg/airtable-mcp-server) | ⬜ 待接入 |
| **YouTube MCP** | 视频分析 | 视频内容提取和总结 | 社区 | [kimtaeyoon83/mcp-youtube](https://github.com/kimtaeyoon83/mcp-youtube) | ⬜ 待接入 |
| **Obsidian MCP** | 个人知识库 | 个人用户笔记管理 | 社区 | [smithery-ai/obsidian-mcp](https://github.com/smithery-ai/obsidian-mcp) | ⬜ 待接入 |
| **Sentry MCP** | 监控告警 | 应用错误监控 | 🎖️ 官方 | [servers/src/sentry](https://github.com/modelcontextprotocol/servers/tree/main/src/sentry) | ⬜ 待接入 |
| **Todoist MCP** | 任务管理 | 个人任务管理 | 社区 | 社区实现 | ⬜ 待评估 |
| **Trello MCP** | 看板管理 | 可视化任务管理 | 社区 | 社区实现 | ⬜ 待评估 |

### 🔵 P3 - 未来规划（待评估）

| 工具名称 | 能力类别 | 场景价值 | 备注 |
|---------|---------|---------|------|
| **AWS MCP** | 云平台 | 云资源管理 | 运维场景 |
| **Docker MCP** | 容器管理 | 容器操作 | DevOps 场景 |
| **Kubernetes MCP** | 容器编排 | K8s 集群管理 | 运维场景 |
| **Jira MCP** | 项目管理 | 企业项目管理 | 大型企业 |
| **Confluence MCP** | 知识管理 | 企业 Wiki | Atlassian 用户 |
| **Salesforce MCP** | CRM | 客户管理 | 销售场景 |

---

## 三、集成架构方案

### 方案 A：MCP Bridge 直接集成（推荐）

```
┌─────────────────────────────────────────────────────────────┐
│                     ZenFlux Agent                            │
├─────────────────────────────────────────────────────────────┤
│  CapabilityRegistry  │  ToolLoader  │  ToolExecutor         │
├─────────────────────────────────────────────────────────────┤
│                    MCPBridge (新增)                          │
│  ┌─────────────┬─────────────┬─────────────┐                │
│  │ MCP Client  │ Protocol    │ Tool        │                │
│  │ Manager     │ Adapter     │ Converter   │                │
│  └─────────────┴─────────────┴─────────────┘                │
├─────────────────────────────────────────────────────────────┤
│              MCP Servers (stdio/SSE)                         │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐               │
│  │Postgres│ │ Notion │ │Puppeteer│ │ Slack  │ ...          │
│  └────────┘ └────────┘ └────────┘ └────────┘               │
└─────────────────────────────────────────────────────────────┘
```

### 方案 B：MetaMCP 中间层（简化管理）

```
┌─────────────────────────────────────────────────────────────┐
│                     ZenFlux Agent                            │
├─────────────────────────────────────────────────────────────┤
│  CapabilityRegistry  │  ToolLoader  │  ToolExecutor         │
├─────────────────────────────────────────────────────────────┤
│                    MetaMCP Adapter (新增)                    │
│                         ↓                                    │
│                    MetaMCP Server                            │
│                    (统一 MCP 管理)                           │
│                         ↓                                    │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐               │
│  │Postgres│ │ Notion │ │Puppeteer│ │ Slack  │ ...          │
│  └────────┘ └────────┘ └────────┘ └────────┘               │
└─────────────────────────────────────────────────────────────┘
```

**推荐：先用方案 A 接入几个核心 MCP，熟悉协议后再考虑 MetaMCP。**

---

## 四、技术实现计划

### 4.1 新增文件结构

```
tools/
├── mcp/                          # MCP 集成模块
│   ├── __init__.py
│   ├── bridge.py                 # MCP Bridge 主类
│   ├── client.py                 # MCP 客户端实现
│   ├── protocol.py               # MCP 协议适配
│   ├── converter.py              # Tool 转换器
│   └── servers/                  # 各 MCP Server 配置
│       ├── __init__.py
│       ├── postgres.py
│       ├── notion.py
│       ├── puppeteer.py
│       └── ...
```

### 4.2 MCPBridge 核心类设计

```python
# tools/mcp/bridge.py
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from tools.base import BaseTool, ToolDefinition
import asyncio
import json


class MCPServerConfig:
    """MCP Server 配置"""
    def __init__(
        self,
        name: str,
        command: str,           # 启动命令，如 "npx @modelcontextprotocol/server-postgres"
        args: List[str] = None, # 启动参数
        env: Dict[str, str] = None,  # 环境变量
        transport: str = "stdio"     # stdio 或 sse
    ):
        self.name = name
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.transport = transport


class MCPBridge:
    """
    MCP 协议桥接器
    
    功能：
    - 管理多个 MCP Server 的生命周期
    - 将 MCP 工具转换为 ZenFlux BaseTool
    - 统一调用接口
    """
    
    def __init__(self):
        self._servers: Dict[str, MCPServerProcess] = {}
        self._tools: Dict[str, MCPToolWrapper] = {}
    
    async def connect_server(self, config: MCPServerConfig) -> bool:
        """连接 MCP Server"""
        # 1. 启动 MCP Server 进程
        # 2. 建立 stdio/SSE 通信
        # 3. 获取工具列表
        # 4. 转换为 BaseTool
        pass
    
    async def disconnect_server(self, name: str) -> bool:
        """断开 MCP Server"""
        pass
    
    def get_tool(self, name: str) -> Optional[BaseTool]:
        """获取转换后的工具"""
        return self._tools.get(name)
    
    def list_tools(self) -> List[ToolDefinition]:
        """列出所有 MCP 工具"""
        return [tool.to_definition() for tool in self._tools.values()]


class MCPToolWrapper(BaseTool):
    """
    MCP 工具包装器
    
    将 MCP 工具包装为 ZenFlux BaseTool
    """
    
    def __init__(self, mcp_tool_info: dict, server_name: str, bridge: MCPBridge):
        self._info = mcp_tool_info
        self._server_name = server_name
        self._bridge = bridge
    
    @property
    def name(self) -> str:
        return f"mcp_{self._server_name}_{self._info['name']}"
    
    @property
    def description(self) -> str:
        return self._info.get('description', '')
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return self._info.get('inputSchema', {})
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """调用 MCP 工具"""
        # 通过 bridge 发送 tools/call 请求
        pass
```

### 4.3 配置文件扩展

```yaml
# config/mcp_servers.yaml
servers:
  # PostgreSQL - 智能分析
  - name: postgres
    enabled: true
    priority: P0
    command: npx
    args: 
      - "@modelcontextprotocol/server-postgres"
    env:
      POSTGRES_CONNECTION_STRING: "${POSTGRES_URL}"
    capabilities:
      - database_query
      - data_analysis
    
  # Notion - 业务梳理
  - name: notion
    enabled: true
    priority: P0
    command: npx
    args:
      - "@modelcontextprotocol/server-notion"
    env:
      NOTION_API_KEY: "${NOTION_API_KEY}"
    capabilities:
      - knowledge_management
      - document_creation
    
  # Puppeteer - 网页自动化
  - name: puppeteer
    enabled: true
    priority: P1
    command: npx
    args:
      - "@modelcontextprotocol/server-puppeteer"
    capabilities:
      - web_automation
      - web_scraping

  # Filesystem - 文件操作
  - name: filesystem
    enabled: true
    priority: P0
    command: npx
    args:
      - "@modelcontextprotocol/server-filesystem"
      - "/workspace"
    capabilities:
      - file_operations
```

---

## 五、接入检查清单

### 5.1 P0 - MetaMCP 接入

- [ ] 部署 MetaMCP 服务
- [ ] 配置 MetaMCP 端点
- [ ] 测试 MCP 协议通信
- [ ] 集成到 CapabilityRegistry

### 5.2 P0 - PostgreSQL MCP

- [ ] 安装 `@modelcontextprotocol/server-postgres`
- [ ] 配置数据库连接字符串
- [ ] 测试数据库查询功能
- [ ] 添加到 capabilities.yaml
- [ ] 编写使用文档

### 5.3 P0 - MySQL MCP

- [ ] 安装 mysql-mcp-server
- [ ] 配置数据库连接
- [ ] 测试基本查询
- [ ] 集成测试

### 5.4 P0 - Notion MCP

- [ ] 创建 Notion Integration
- [ ] 获取 API Key
- [ ] 安装 `@modelcontextprotocol/server-notion`
- [ ] 测试页面读写
- [ ] 集成到知识管理流程

### 5.5 P0 - Filesystem MCP

- [ ] 安装 `@modelcontextprotocol/server-filesystem`
- [ ] 配置允许访问的目录
- [ ] 测试文件读写
- [ ] 安全性检查

### 5.6 P1 - Google Drive MCP

- [ ] 配置 Google OAuth
- [ ] 安装 `@modelcontextprotocol/server-gdrive`
- [ ] 测试文件访问
- [ ] 集成到文档处理流程

### 5.7 P1 - Puppeteer MCP

- [ ] 安装 `@modelcontextprotocol/server-puppeteer`
- [ ] 配置浏览器选项
- [ ] 测试网页抓取
- [ ] 与现有 exa_search 协作

### 5.8 P1 - Slack MCP

- [ ] 创建 Slack App
- [ ] 配置 Bot Token
- [ ] 安装 `@modelcontextprotocol/server-slack`
- [ ] 测试消息发送

### 5.9 P1 - GitHub MCP

- [ ] 配置 GitHub Token
- [ ] 安装 `@modelcontextprotocol/server-github`
- [ ] 测试仓库操作
- [ ] 集成到开发者工具

---

## 六、环境变量清单

```bash
# .env.example 补充

# ========== MCP Servers ==========

# PostgreSQL MCP
POSTGRES_URL=postgresql://user:pass@localhost:5432/dbname

# MySQL MCP  
MYSQL_URL=mysql://user:pass@localhost:3306/dbname

# Notion MCP
NOTION_API_KEY=ntn_xxxxx

# Google Drive MCP
GOOGLE_CLIENT_ID=xxxxx
GOOGLE_CLIENT_SECRET=xxxxx
GOOGLE_REDIRECT_URI=http://localhost:3000/oauth/callback

# Slack MCP
SLACK_BOT_TOKEN=xoxb-xxxxx
SLACK_TEAM_ID=Txxxxx

# GitHub MCP
GITHUB_PERSONAL_TOKEN=ghp_xxxxx

# 飞书 MCP (待定)
FEISHU_APP_ID=xxxxx
FEISHU_APP_SECRET=xxxxx

# 钉钉 MCP (待定)
DINGTALK_APP_KEY=xxxxx
DINGTALK_APP_SECRET=xxxxx
```

---

## 七、测试计划

### 7.1 单元测试

```python
# tests/test_mcp_bridge.py

import pytest
from tools.mcp.bridge import MCPBridge, MCPServerConfig


@pytest.mark.asyncio
async def test_connect_postgres():
    """测试 PostgreSQL MCP 连接"""
    bridge = MCPBridge()
    config = MCPServerConfig(
        name="postgres",
        command="npx",
        args=["@modelcontextprotocol/server-postgres"],
        env={"POSTGRES_CONNECTION_STRING": "postgresql://..."}
    )
    
    result = await bridge.connect_server(config)
    assert result is True
    
    tools = bridge.list_tools()
    assert len(tools) > 0


@pytest.mark.asyncio
async def test_tool_execution():
    """测试工具执行"""
    bridge = MCPBridge()
    # ... 连接服务器 ...
    
    tool = bridge.get_tool("mcp_postgres_query")
    result = await tool.execute(query="SELECT 1")
    assert "error" not in result
```

### 7.2 集成测试

- [ ] 测试 MCP Bridge 与 CapabilityRegistry 集成
- [ ] 测试 MCP 工具在聊天流程中的调用
- [ ] 测试多 MCP Server 并行工作
- [ ] 测试 MCP Server 重连机制

---

## 八、里程碑计划

| 阶段 | 时间 | 目标 | 交付物 |
|-----|------|------|--------|
| **Phase 1** | 第 1-2 周 | MCP Bridge 基础架构 | bridge.py, client.py, protocol.py |
| **Phase 2** | 第 3-4 周 | P0 工具接入 | MetaMCP, Notion, 飞书/钉钉调研 |
| **Phase 3** | 第 5-6 周 | P1 工具接入（协作类） | Google Drive, Slack, Linear, Figma |
| **Phase 4** | 第 7-8 周 | P1 工具接入（技术类） | Puppeteer, GitHub |
| **Phase 5** | 第 9-10 周 | P2 工具接入 + 国内IM | 企业微信, Airtable, YouTube 等 |

---

## 九、参考资源

### 官方文档
- [MCP 协议规范](https://modelcontextprotocol.io/docs)
- [MCP TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)

### 社区资源
- [Awesome MCP Servers](https://github.com/punkpeye/awesome-mcp-servers)
- [MCP 中文站](https://mcpcn.com)
- [Glama MCP 目录](https://glama.ai/mcp/servers)

### 示例项目
- [MetaMCP](https://github.com/metatool-ai/metatool-app)
- [MCP Proxy](https://github.com/punkpeye/mcp-proxy)

---

## 十、风险与应对

| 风险 | 影响 | 应对措施 |
|-----|------|---------|
| MCP Server 进程不稳定 | 工具调用失败 | 实现重连机制 + 健康检查 |
| 国内网络问题 | npm 包下载慢 | 使用镜像源 / 提前预装 |
| 飞书/钉钉无官方 MCP | 功能缺失 | 自研或使用现有 API |
| MCP 协议版本升级 | 兼容性问题 | 关注官方 changelog |

---

> 📝 **维护说明**：本文档应随项目进展持续更新，完成的项目标记为 ✅

