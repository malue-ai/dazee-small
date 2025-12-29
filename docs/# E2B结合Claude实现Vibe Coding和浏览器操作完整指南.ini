# E2B结合Claude实现Vibe Coding和浏览器操作完整指南

## 一、核心概念

### 1.1 什么是Vibe Coding？

**Vibe Coding**是一种通过自然语言提示（Prompt）指导AI智能体生成完整应用程序的开发范式。它不是传统的"无代码"工具，而是让AI成为你的编程助手，通过对话式交互快速构建功能性应用。

**核心特点**：
- 自然语言驱动开发
- AI生成完整的前后端代码
- 实时预览和迭代
- 支持任意编程语言和框架

### 1.2 E2B在Vibe Coding中的角色

E2B提供**安全的云端沙箱环境**，用于执行AI生成的代码。这解决了Vibe Coding的核心挑战：
- **安全性**：隔离执行AI生成的不可信代码
- **实时性**：<200ms启动速度，支持实时预览
- **完整性**：支持网络访问、文件系统、包管理
- **可扩展性**：支持任意语言和框架

---

## 二、E2B + Claude实现Vibe Coding的技术架构

### 2.1 整体架构

```
用户输入 (自然语言Prompt)
    ↓
Claude LLM (代码生成)
    ↓
E2B Sandbox (代码执行)
    ↓
前端UI (实时预览)
```

### 2.2 核心组件

#### 2.2.1 前端层（Next.js + React）
- 用户交互界面
- 实时代码预览
- 流式输出显示
- 文件上传/下载

#### 2.2.2 AI层（Claude API）
- 接收用户Prompt
- 生成代码（Python、JS、HTML/CSS等）
- 支持多轮对话和代码迭代
- 使用Function Calling调用E2B工具

#### 2.2.3 执行层（E2B Sandbox）
- 隔离的Linux环境
- 支持网络访问
- 动态安装依赖包
- 文件系统操作
- 长会话支持（最长24小时）

### 2.3 数据流

**1. 用户发起请求**
```
用户: "创建一个数据可视化应用，分析这个CSV文件"
```

**2. Claude生成代码**
```python
import pandas as pd
import matplotlib.pyplot as plt

# 读取CSV
df = pd.read_csv('/home/user/data.csv')

# 生成图表
df.plot(kind='bar')
plt.savefig('/home/user/chart.png')
```

**3. E2B执行代码**
```javascript
const sandbox = await Sandbox.create('base')
await sandbox.files.write('/home/user/data.csv', csvContent)
const result = await sandbox.commands.run('python3 script.py')
const chartData = await sandbox.files.read('/home/user/chart.png')
```

**4. 前端展示结果**
- 显示生成的图表
- 展示代码执行日志
- 支持下载输出文件

---

## 三、E2B Fragments：开源Vibe Coding实现

### 3.1 Fragments项目概述

**E2B Fragments**是一个开源的Vibe Coding平台，类似于：
- Anthropic的Claude Artifacts
- Vercel v0
- GPT Engineer

**GitHub**: https://github.com/e2b-dev/fragments  
**在线体验**: https://fragments.e2b.dev

### 3.2 核心特性

#### 支持的技术栈
- **Python Interpreter**: 数据分析、机器学习
- **Next.js**: 全栈Web应用
- **Vue.js**: 前端应用
- **Streamlit**: 数据应用
- **Gradio**: ML模型界面

#### 支持的LLM提供商
- OpenAI (GPT-4, o1)
- Anthropic (Claude 3.5 Sonnet)
- Google AI (Gemini)
- Mistral
- Groq
- Fireworks
- Together AI
- Ollama (本地模型)

### 3.3 实现原理

#### 3.3.1 自定义沙箱模板

Fragments使用E2B的**自定义模板功能**，为每种技术栈预配置环境：

**示例：Streamlit模板**

```dockerfile
# e2b.Dockerfile
FROM python:3.19-slim

RUN pip3 install --no-cache-dir streamlit pandas numpy matplotlib requests seaborn plotly

WORKDIR /home/user
COPY . /home/user
```

**配置文件：e2b.toml**
```toml
start_cmd = "cd /home/user && streamlit run app.py"
```

**部署模板**
```bash
e2b template build --name streamlit-developer
```

#### 3.3.2 模板配置

**lib/templates.json**
```json
{
  "streamlit-developer": {
    "name": "Streamlit developer",
    "lib": ["streamlit", "pandas", "numpy", "matplotlib"],
    "file": "app.py",
    "instructions": "A streamlit app that reloads automatically.",
    "port": 8501
  }
}
```

#### 3.3.3 核心工作流程

**1. 用户选择技术栈**
```typescript
const template = 'streamlit-developer'
const sandbox = await Sandbox.create(template)
```

**2. Claude生成代码**
```typescript
const response = await anthropic.messages.create({
  model: 'claude-3-5-sonnet-20241022',
  messages: [{
    role: 'user',
    content: `Create a Streamlit app that ${userPrompt}`
  }],
  tools: [
    {
      name: 'execute_code',
      description: 'Execute code in E2B sandbox',
      input_schema: {
        type: 'object',
        properties: {
          code: { type: 'string' },
          language: { type: 'string' }
        }
      }
    }
  ]
})
```

**3. 执行代码并获取预览URL**
```typescript
// 写入代码文件
await sandbox.files.write('/home/user/app.py', generatedCode)

// 获取预览URL
const url = `https://${sandbox.getHost(8501)}`

// 返回给用户
return { previewUrl: url, code: generatedCode }
```

---

## 四、E2B实现浏览器自动化操作

### 4.1 浏览器自动化架构

E2B支持在沙箱中运行**Playwright**和**Puppeteer**，实现完整的浏览器自动化能力。

### 4.2 Playwright集成方案

#### 4.2.1 创建Playwright沙箱模板

**e2b.Dockerfile**
```dockerfile
FROM node:20-slim

# 安装Playwright依赖
RUN apt-get update && apt-get install -y \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2

# 安装Playwright
WORKDIR /app
RUN npm init -y && \
    npm install playwright && \
    PLAYWRIGHT_BROWSERS_PATH=0 npx playwright install chromium

ENV PLAYWRIGHT_BROWSERS_PATH=0
```

**构建模板**
```bash
e2b template build --name playwright-chromium
```

#### 4.2.2 使用Playwright沙箱

**基础示例**
```typescript
import { Sandbox } from 'e2b'
import { chromium } from 'playwright'

// 创建沙箱
const sbx = await Sandbox.create('playwright-chromium')

// 上传Playwright脚本
const script = `
import { chromium } from 'playwright'

const browser = await chromium.launch()
const context = await browser.newContext()
const page = await context.newPage()

await page.goto('https://example.com')
await page.screenshot({ path: '/home/user/screenshot.png' })

await browser.close()
console.log('done')
`

await sbx.files.write('/app/script.mjs', script)

// 执行脚本
const result = await sbx.commands.run('node /app/script.mjs', {
  cwd: '/app'
})

console.log(result.stdout)

// 下载截图
const screenshot = await sbx.files.read('/home/user/screenshot.png')

await sbx.kill()
```

**重要提示**：
1. 所有Playwright脚本必须从`/app`目录运行
2. 必须设置环境变量`PLAYWRIGHT_BROWSERS_PATH=0`

#### 4.2.3 Claude + E2B实现智能浏览器操作

**完整示例：AI驱动的网页抓取**

```typescript
import Anthropic from '@anthropic-ai/sdk'
import { Sandbox } from 'e2b'

const anthropic = new Anthropic({
  apiKey: process.env.ANTHROPIC_API_KEY
})

const sandbox = await Sandbox.create('playwright-chromium')

// 定义工具
const tools = [
  {
    name: 'browser_navigate',
    description: 'Navigate to a URL and take a screenshot',
    input_schema: {
      type: 'object',
      properties: {
        url: { type: 'string', description: 'The URL to visit' }
      },
      required: ['url']
    }
  },
  {
    name: 'browser_click',
    description: 'Click an element on the page',
    input_schema: {
      type: 'object',
      properties: {
        selector: { type: 'string', description: 'CSS selector of element to click' }
      },
      required: ['selector']
    }
  },
  {
    name: 'browser_extract',
    description: 'Extract text content from the page',
    input_schema: {
      type: 'object',
      properties: {
        selector: { type: 'string', description: 'CSS selector to extract from' }
      },
      required: ['selector']
    }
  }
]

// 工具实现
async function executeTool(toolName: string, toolInput: any) {
  const script = generatePlaywrightScript(toolName, toolInput)
  
  await sandbox.files.write('/app/script.mjs', script)
  const result = await sandbox.commands.run('node /app/script.mjs', {
    cwd: '/app'
  })
  
  return result.stdout
}

function generatePlaywrightScript(toolName: string, toolInput: any): string {
  if (toolName === 'browser_navigate') {
    return `
import { chromium } from 'playwright'

const browser = await chromium.launch()
const page = await browser.newPage()

await page.goto('${toolInput.url}')
await page.screenshot({ path: '/home/user/screenshot.png' })

console.log('Navigated to ${toolInput.url}')
await browser.close()
    `
  }
  
  if (toolName === 'browser_click') {
    return `
import { chromium } from 'playwright'

const browser = await chromium.launch()
const page = await browser.newPage()

// 假设已经导航到页面
await page.click('${toolInput.selector}')

console.log('Clicked element: ${toolInput.selector}')
await browser.close()
    `
  }
  
  if (toolName === 'browser_extract') {
    return `
import { chromium } from 'playwright'

const browser = await chromium.launch()
const page = await browser.newPage()

const text = await page.textContent('${toolInput.selector}')
console.log(JSON.stringify({ text }))

await browser.close()
    `
  }
  
  return ''
}

// 主循环
const messages = [
  {
    role: 'user',
    content: '访问 https://news.ycombinator.com 并提取前5条新闻标题'
  }
]

while (true) {
  const response = await anthropic.messages.create({
    model: 'claude-3-5-sonnet-20241022',
    max_tokens: 4096,
    tools: tools,
    messages: messages
  })
  
  console.log('Claude response:', response.content)
  
  if (response.stop_reason === 'end_turn') {
    break
  }
  
  if (response.stop_reason === 'tool_use') {
    const toolUse = response.content.find(block => block.type === 'tool_use')
    
    if (toolUse) {
      const result = await executeTool(toolUse.name, toolUse.input)
      
      messages.push({
        role: 'assistant',
        content: response.content
      })
      
      messages.push({
        role: 'user',
        content: [{
          type: 'tool_result',
          tool_use_id: toolUse.id,
          content: result
        }]
      })
    }
  }
}

await sandbox.kill()
```

### 4.3 MCP Browserbase集成

E2B还支持通过**MCP (Model Context Protocol)**集成第三方浏览器自动化服务，如**Browserbase**。

**示例：使用Browserbase MCP Server**

```typescript
import { Sandbox } from 'e2b'

// 创建带有MCP支持的沙箱
const sandbox = await Sandbox.create('base', {
  envVars: {
    BROWSERBASE_API_KEY: process.env.BROWSERBASE_API_KEY,
    BROWSERBASE_PROJECT_ID: process.env.BROWSERBASE_PROJECT_ID
  }
})

// 使用MCP客户端连接到Browserbase
const mcpScript = `
import { Client } from '@modelcontextprotocol/sdk/client/index.js'
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js'

const transport = new StdioClientTransport({
  command: 'npx',
  args: ['-y', '@browserbasehq/mcp-server-browserbase']
})

const client = new Client({
  name: 'e2b-browserbase-client',
  version: '1.0.0'
}, {
  capabilities: {}
})

await client.connect(transport)

// 调用Browserbase工具
const result = await client.callTool({
  name: 'browserbase_navigate',
  arguments: {
    url: 'https://example.com'
  }
})

console.log(result)
`

await sandbox.files.write('/app/mcp-client.mjs', mcpScript)
const result = await sandbox.commands.run('node /app/mcp-client.mjs', {
  cwd: '/app'
})

console.log(result.stdout)
```

---

## 五、集成到Claude 4.5智能体架构（V3.7）

### 5.1 架构集成方案

根据您的V3.7架构，E2B应该作为**工具层（Tools）**的一部分集成。

#### 5.1.1 工具定义

**tools_config.json**
```json
{
  "tools": [
    {
      "name": "e2b_execute_code",
      "description": "在安全沙箱中执行AI生成的代码",
      "capabilities": ["code_execution", "data_analysis"],
      "parameters": {
        "code": "要执行的代码",
        "language": "编程语言（python/javascript/bash）",
        "template": "沙箱模板ID（可选）"
      },
      "implementation": "tools.e2b_wrapper.execute_code"
    },
    {
      "name": "e2b_browser_navigate",
      "description": "使用浏览器访问网页并截图",
      "capabilities": ["web_automation", "data_collection"],
      "parameters": {
        "url": "要访问的URL",
        "actions": "要执行的操作列表（可选）"
      },
      "implementation": "tools.e2b_wrapper.browser_navigate"
    },
    {
      "name": "e2b_create_app",
      "description": "创建完整的Web应用（Vibe Coding）",
      "capabilities": ["app_generation", "code_execution"],
      "parameters": {
        "description": "应用描述",
        "stack": "技术栈（streamlit/nextjs/vue）"
      },
      "implementation": "tools.e2b_wrapper.create_app"
    }
  ]
}
```

#### 5.1.2 工具实现

**tools/e2b_wrapper.py**
```python
from e2b import Sandbox
from typing import Dict, Any, Optional

class E2BWrapper:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.active_sandboxes: Dict[str, Sandbox] = {}
    
    async def execute_code(
        self,
        code: str,
        language: str = 'python',
        template: Optional[str] = None
    ) -> Dict[str, Any]:
        """执行代码"""
        
        # 创建沙箱
        sandbox_template = template or 'base'
        sandbox = await Sandbox.create(sandbox_template, api_key=self.api_key)
        
        try:
            # 写入代码文件
            if language == 'python':
                file_path = '/home/user/script.py'
                cmd = 'python3 /home/user/script.py'
            elif language == 'javascript':
                file_path = '/home/user/script.js'
                cmd = 'node /home/user/script.js'
            else:
                file_path = '/home/user/script.sh'
                cmd = 'bash /home/user/script.sh'
            
            await sandbox.files.write(file_path, code)
            
            # 执行代码
            result = await sandbox.commands.run(cmd)
            
            return {
                'success': True,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'exit_code': result.exit_code
            }
        
        finally:
            await sandbox.kill()
    
    async def browser_navigate(
        self,
        url: str,
        actions: Optional[list] = None
    ) -> Dict[str, Any]:
        """浏览器导航"""
        
        sandbox = await Sandbox.create('playwright-chromium', api_key=self.api_key)
        
        try:
            # 生成Playwright脚本
            script = f"""
import {{ chromium }} from 'playwright'

const browser = await chromium.launch()
const page = await browser.newPage()

await page.goto('{url}')
await page.screenshot({{ path: '/home/user/screenshot.png' }})

// 执行额外操作
{self._generate_actions_code(actions)}

await browser.close()
console.log('done')
            """
            
            await sandbox.files.write('/app/script.mjs', script)
            result = await sandbox.commands.run('node /app/script.mjs', cwd='/app')
            
            # 读取截图
            screenshot = await sandbox.files.read('/home/user/screenshot.png')
            
            return {
                'success': True,
                'screenshot': screenshot,
                'logs': result.stdout
            }
        
        finally:
            await sandbox.kill()
    
    async def create_app(
        self,
        description: str,
        stack: str = 'streamlit'
    ) -> Dict[str, Any]:
        """创建应用（Vibe Coding）"""
        
        # 根据技术栈选择模板
        template_map = {
            'streamlit': 'streamlit-developer',
            'nextjs': 'nextjs-developer',
            'vue': 'vue-developer'
        }
        
        template = template_map.get(stack, 'base')
        sandbox = await Sandbox.create(template, api_key=self.api_key)
        
        # 保存沙箱引用（用于长会话）
        sandbox_id = sandbox.id
        self.active_sandboxes[sandbox_id] = sandbox
        
        return {
            'success': True,
            'sandbox_id': sandbox_id,
            'message': f'已创建{stack}应用沙箱，可以开始生成代码'
        }
    
    def _generate_actions_code(self, actions: Optional[list]) -> str:
        """生成浏览器操作代码"""
        if not actions:
            return ''
        
        code_lines = []
        for action in actions:
            if action['type'] == 'click':
                code_lines.append(f"await page.click('{action['selector']}')")
            elif action['type'] == 'type':
                code_lines.append(f"await page.fill('{action['selector']}', '{action['text']}')")
            elif action['type'] == 'wait':
                code_lines.append(f"await page.waitForTimeout({action['ms']})")
        
        return '\n'.join(code_lines)
```

#### 5.1.3 Router集成

**system_prompt.txt**
```
你是一个通用智能体，可以执行各种任务。

当用户需要执行代码、数据分析或创建应用时，使用e2b_execute_code或e2b_create_app工具。

当用户需要访问网页、抓取数据或进行浏览器自动化时，使用e2b_browser_navigate工具。

工具选择规则：
- 数据分析、可视化 → e2b_execute_code (language=python)
- 创建Web应用 → e2b_create_app
- 网页抓取、浏览器操作 → e2b_browser_navigate
```

---

## 六、实战案例

### 6.1 案例1：AI数据分析师

**用户需求**：分析CSV文件并生成可视化报告

**实现流程**：

1. **用户上传CSV文件**
```python
# 用户通过前端上传data.csv
```

2. **Claude生成分析代码**
```python
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# 读取数据
df = pd.read_csv('/home/user/data.csv')

# 基础统计
print(df.describe())

# 生成可视化
fig, axes = plt.subplots(2, 2, figsize=(12, 10))

# 分布图
df.hist(ax=axes[0, 0])
axes[0, 0].set_title('Data Distribution')

# 相关性热图
sns.heatmap(df.corr(), annot=True, ax=axes[0, 1])
axes[0, 1].set_title('Correlation Matrix')

# 保存图表
plt.savefig('/home/user/report.png')
print('Analysis complete!')
```

3. **E2B执行代码**
```typescript
const result = await e2bWrapper.execute_code(generatedCode, 'python')
const report = await sandbox.files.read('/home/user/report.png')
```

4. **返回结果给用户**
- 展示统计结果
- 显示可视化图表
- 提供下载链接

### 6.2 案例2：智能网页抓取

**用户需求**：抓取电商网站的产品信息

**实现流程**：

1. **用户输入**
```
"访问 https://example-shop.com 并提取所有产品的名称和价格"
```

2. **Claude规划操作步骤**
```json
{
  "steps": [
    { "action": "navigate", "url": "https://example-shop.com" },
    { "action": "wait", "ms": 2000 },
    { "action": "extract", "selector": ".product-name" },
    { "action": "extract", "selector": ".product-price" }
  ]
}
```

3. **E2B执行浏览器操作**
```typescript
const result = await e2bWrapper.browser_navigate(
  'https://example-shop.com',
  [
    { type: 'wait', ms: 2000 },
    { type: 'extract', selector: '.product-name' },
    { type: 'extract', selector: '.product-price' }
  ]
)
```

4. **Claude整理数据**
```json
{
  "products": [
    { "name": "Product A", "price": "$29.99" },
    { "name": "Product B", "price": "$49.99" }
  ]
}
```

### 6.3 案例3：Vibe Coding创建Streamlit应用

**用户需求**：创建一个股票数据分析应用

**实现流程**：

1. **创建沙箱**
```python
result = await e2bWrapper.create_app(
    description="股票数据分析应用",
    stack="streamlit"
)
sandbox_id = result['sandbox_id']
```

2. **Claude生成Streamlit代码**
```python
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go

st.title('📈 股票数据分析')

# 用户输入
ticker = st.text_input('输入股票代码', 'AAPL')

if ticker:
    # 获取数据
    stock = yf.Ticker(ticker)
    hist = stock.history(period='1y')
    
    # 显示图表
    fig = go.Figure(data=[go.Candlestick(
        x=hist.index,
        open=hist['Open'],
        high=hist['High'],
        low=hist['Low'],
        close=hist['Close']
    )])
    
    st.plotly_chart(fig)
    
    # 显示统计
    st.write(hist.describe())
```

3. **部署到沙箱**
```python
sandbox = e2bWrapper.active_sandboxes[sandbox_id]
await sandbox.files.write('/home/user/app.py', generated_code)

# 获取预览URL
preview_url = f"https://{sandbox.get_host(8501)}"
```

4. **返回给用户**
```json
{
  "preview_url": "https://xxx.e2b.dev",
  "code": "...",
  "message": "应用已创建，点击链接查看"
}
```

---

## 七、最佳实践

### 7.1 沙箱生命周期管理

**问题**：频繁创建和销毁沙箱会增加延迟和成本

**解决方案**：
```python
class SandboxPool:
    def __init__(self, max_size=10):
        self.pool = []
        self.max_size = max_size
    
    async def get_sandbox(self, template='base'):
        # 复用现有沙箱
        for sandbox in self.pool:
            if sandbox.template == template and not sandbox.in_use:
                sandbox.in_use = True
                return sandbox
        
        # 创建新沙箱
        if len(self.pool) < self.max_size:
            sandbox = await Sandbox.create(template)
            sandbox.in_use = True
            self.pool.append(sandbox)
            return sandbox
        
        # 等待可用沙箱
        return await self._wait_for_available()
    
    async def release_sandbox(self, sandbox):
        sandbox.in_use = False
```

### 7.2 错误处理

```python
async def safe_execute_code(code: str, language: str):
    try:
        result = await e2b_wrapper.execute_code(code, language)
        return result
    except TimeoutError:
        return {
            'success': False,
            'error': '代码执行超时，请优化代码或增加超时时间'
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'执行失败: {str(e)}'
        }
```

### 7.3 成本优化

**策略**：
1. **使用沙箱池**：减少创建/销毁开销
2. **设置超时**：避免长时间运行
3. **按需销毁**：任务完成后及时释放
4. **监控用量**：使用E2B Dashboard追踪使用情况

```python
# 设置超时
result = await sandbox.commands.run(
    'python3 script.py',
    timeout=30  # 30秒超时
)

# 任务完成后销毁
await sandbox.kill()
```

### 7.4 安全性

**E2B已提供的安全保障**：
- 完全隔离的沙箱环境
- 网络访问控制
- 资源限制（CPU、内存）
- 自动超时机制

**额外建议**：
1. **代码审查**：在执行前让Claude检查生成的代码
2. **用户确认**：敏感操作（如网络请求）需要用户确认
3. **日志记录**：记录所有代码执行历史

---

## 八、总结与建议

### 8.1 E2B的核心优势

1. **网络访问能力**：这是Claude Code Execution Tool不具备的
2. **完整的Linux环境**：支持任意语言和工具
3. **企业级可靠性**：88% Fortune 100公司使用
4. **快速启动**：<200ms，支持实时交互
5. **开源生态**：Fragments等开源项目可直接使用

### 8.2 适用场景

**✅ 强烈推荐使用E2B的场景**：
- Vibe Coding（AI生成应用）
- 浏览器自动化（网页抓取、测试）
- 数据分析和可视化
- 需要安装第三方包的场景
- 长会话任务（>1小时）

**⚠️ 可能不需要E2B的场景**：
- 简单的数学计算
- 纯文本处理（无需执行代码）
- 离线数据分析（可用Claude Code Execution Tool）

### 8.3 集成到您的架构的建议

**立即行动**：
1. 注册E2B账号：https://e2b.dev/dashboard
2. 测试基础API：创建沙箱、执行代码
3. 部署Playwright模板：实现浏览器自动化
4. 集成到V3.7架构：作为工具层的一部分

**分阶段实施**：
- **第1周**：基础代码执行能力
- **第2周**：浏览器自动化
- **第3-4周**：Vibe Coding（参考Fragments）
- **第5-8周**：优化和高级特性

### 8.4 参考资源

- **E2B官方文档**：https://e2b.dev/docs
- **E2B Cookbook**：https://github.com/e2b-dev/e2b-cookbook
- **E2B Fragments**：https://github.com/e2b-dev/fragments
- **Playwright in E2B**：https://github.com/e2b-dev/e2b-cookbook/tree/main/examples/playwright-in-e2b
- **E2B Discord社区**：https://discord.gg/e2b

---

## 附录：完整代码示例

### A.1 完整的Vibe Coding实现（简化版）

```typescript
// app/api/generate/route.ts
import { Anthropic } from '@anthropic-ai/sdk'
import { Sandbox } from 'e2b'

export async function POST(req: Request) {
  const { prompt, stack } = await req.json()
  
  const anthropic = new Anthropic({
    apiKey: process.env.ANTHROPIC_API_KEY
  })
  
  // 创建沙箱
  const sandbox = await Sandbox.create(`${stack}-developer`)
  
  try {
    // 调用Claude生成代码
    const response = await anthropic.messages.create({
      model: 'claude-3-5-sonnet-20241022',
      max_tokens: 4096,
      messages: [{
        role: 'user',
        content: `Create a ${stack} app that ${prompt}`
      }]
    })
    
    const generatedCode = response.content[0].text
    
    // 写入代码文件
    const fileName = stack === 'streamlit' ? 'app.py' : 'index.js'
    await sandbox.files.write(`/home/user/${fileName}`, generatedCode)
    
    // 获取预览URL
    const port = stack === 'streamlit' ? 8501 : 3000
    const previewUrl = `https://${sandbox.getHost(port)}`
    
    return Response.json({
      success: true,
      code: generatedCode,
      previewUrl,
      sandboxId: sandbox.id
    })
    
  } catch (error) {
    await sandbox.kill()
    throw error
  }
}
```

### A.2 完整的浏览器自动化实现

```typescript
// tools/browser-automation.ts
import { Sandbox } from 'e2b'

export class BrowserAutomation {
  private sandbox: Sandbox | null = null
  
  async initialize() {
    this.sandbox = await Sandbox.create('playwright-chromium')
  }
  
  async navigate(url: string): Promise<string> {
    const script = `
import { chromium } from 'playwright'

const browser = await chromium.launch()
const page = await browser.newPage()

await page.goto('${url}')
await page.screenshot({ path: '/home/user/screenshot.png' })

const title = await page.title()
console.log(JSON.stringify({ title }))

await browser.close()
    `
    
    await this.sandbox!.files.write('/app/script.mjs', script)
    const result = await this.sandbox!.commands.run('node /app/script.mjs', {
      cwd: '/app'
    })
    
    return result.stdout
  }
  
  async click(selector: string): Promise<void> {
    const script = `
import { chromium } from 'playwright'

const browser = await chromium.launch()
const page = await browser.newPage()

await page.click('${selector}')
console.log('Clicked: ${selector}')

await browser.close()
    `
    
    await this.sandbox!.files.write('/app/script.mjs', script)
    await this.sandbox!.commands.run('node /app/script.mjs', { cwd: '/app' })
  }
  
  async extract(selector: string): Promise<string> {
    const script = `
import { chromium } from 'playwright'

const browser = await chromium.launch()
const page = await browser.newPage()

const elements = await page.$$('${selector}')
const texts = await Promise.all(
  elements.map(el => el.textContent())
)

console.log(JSON.stringify({ texts }))

await browser.close()
    `
    
    await this.sandbox!.files.write('/app/script.mjs', script)
    const result = await this.sandbox!.commands.run('node /app/script.mjs', {
      cwd: '/app'
    })
    
    return result.stdout
  }
  
  async cleanup() {
    if (this.sandbox) {
      await this.sandbox.kill()
    }
  }
}
```

---

**文档版本**: v1.0  
**最后更新**: 2025-12-29  
**作者**: AI Assistant  
**参考**: E2B官方文档、Fragments项目、E2B Cookbook
