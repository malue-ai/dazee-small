# 智能体实例创建指南

## 快速开始（3 步完成）

### Step 1: 复制模板

```bash
# 在 instances/ 目录下创建新实例
cp -r _template my_agent
```

### Step 2: 编写提示词

编辑 `my_agent/prompt.md`，按模板填写：

| 章节 | 必填 | 说明 |
|------|------|------|
| 角色定义 | ✅ | 描述智能体的身份和定位 |
| 核心能力 | ✅ | 列出主要能力（框架自动识别关键词） |
| 工作规则 | ⬜ | 特定的工作流程或限制 |
| 专属工具说明 | ⬜ | 对 MCP 工具的使用指导 |
| 输出风格 | ⬜ | 回复格式和语言风格 |
| 限制与边界 | ⬜ | 明确不应该做什么 |

### Step 3: 配置密钥

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env，填入实际的 API 密钥
```

## 启动智能体

```bash
# 在项目根目录运行
python scripts/run_instance.py --instance my_agent
```

## 关键词自动识别

框架会自动识别 `prompt.md` 中的关键词并配置相应能力：

| 关键词 | 自动配置 |
|--------|----------|
| 搜索/查找/检索 | web_search, exa_search |
| 数据分析/pandas | e2b_sandbox |
| PPT/演示/幻灯片 | pptx skill |
| Excel/表格/报表 | xlsx skill |
| PDF/文档 | pdf skill |
| 计划/规划/多步骤 | plan_manager |

**示例**：如果 `prompt.md` 中写"具备数据分析能力"，框架会自动启用 e2b_sandbox 工具。

## 配置 MCP 工具

如果需要使用外部 MCP 工具（如 Dify 工作流），在 `config.yaml` 中声明：

```yaml
mcp_tools:
  - name: dify_workflow
    server_url: "https://api.dify.ai/mcp/server/xxx/mcp"
    server_name: "dify"
    auth_type: "bearer"
    auth_env: "DIFY_API_KEY"
```

然后在 `.env` 中配置密钥：

```bash
DIFY_API_KEY=app-xxx
```

## 目录结构

```
my_agent/
├── prompt.md          # 核心！智能体定义（运营填写）
├── config.yaml        # 配置覆盖和 MCP 工具声明
├── .env               # API 密钥（不提交到代码库）
└── .env.example       # 环境变量模板
```

## 常见问题

### Q: 如何添加新能力？

在 `prompt.md` 的"核心能力"章节添加描述即可，框架会自动识别关键词。

### Q: 配置没生效？

检查优先级：`config.yaml` > LLM 推断 > 默认值。如果需要强制覆盖，在 `config.yaml` 中显式配置。

### Q: MCP 工具连接失败？

1. 检查 `config.yaml` 中的 `server_url` 是否正确
2. 检查 `.env` 中的密钥是否配置
3. 检查网络连接
