# E2B集成文档

> **版本**: V1.0  
> **日期**: 2025-12-29  
> **架构**: V3.7 兼容  

## 📋 目录

- [概述](#概述)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [使用示例](#使用示例)
- [测试验证](#测试验证)
- [常见问题](#常见问题)

## 概述

E2B Python Sandbox 已成功集成到 Zenflux Agent（V3.7架构），提供以下能力：

✅ **完整网络访问** - requests, httpx 等网络库  
✅ **任意第三方包** - 自动检测并安装 pip 包  
✅ **文件系统持久化** - workspace 与沙箱双向同步  
✅ **长时间运行** - 最长 24 小时  
✅ **多轮交互** - 会话级沙箱复用  
✅ **流式输出** - 实时显示 stdout/stderr  

### 架构集成方式

```
┌─────────────────────────────────────────────────────┐
│                  V3.7 架构集成                       │
├─────────────────────────────────────────────────────┤
│                                                      │
│  能力抽象层（Capability Categories）                │
│    → code_sandbox（新增）                            │
│                                                      │
│  工具层（Tools）                                     │
│    → e2b_python_sandbox                              │
│    → e2b_template_manager                            │
│                                                      │
│  状态管理（Memory）                                  │
│    → E2BSandboxSession                               │
│    → execution_history                               │
│                                                      │
│  System Prompt                                       │
│    → E2B Sandbox Protocol                            │
│                                                      │
└─────────────────────────────────────────────────────┘
```

## 快速开始

### 1. 安装依赖

```bash
# 安装 E2B SDK
pip install e2b e2b-code-interpreter

# 或者使用 requirements.txt
pip install -r requirements.txt
```

### 2. 配置 API Key

在 `.env` 文件中添加：

```bash
# E2B API Key（从 https://e2b.dev/dashboard 获取）
E2B_API_KEY=e2b_***
```

### 3. 验证安装

```bash
# 运行集成测试
python tests/test_e2b_integration.py
```

预期输出：
```
✅ 测试通过：基础代码执行成功
✅ 测试通过：自动包安装成功
✅ 测试通过：文件系统操作成功
✅ 测试通过：沙箱持久化成功
✅ 测试通过：模板管理器工作正常
✅ 测试通过：Memory 集成成功
🎉 所有测试通过！
```

## 配置说明

### 模板配置

编辑 `config/e2b_templates.yaml`：

```yaml
templates:
  # 基础模板
  base:
    name: "Base Python"
    build_method: "use_builtin"
    template_id: "base"
  
  # 数据分析模板（预装包）
  data-analysis:
    name: "Data Analysis"
    build_method: "custom_build"
    pre_install_packages:
      - pandas
      - numpy
      - matplotlib
    
  # 网页爬虫模板
  web-scraping:
    name: "Web Scraping"
    build_method: "custom_build"
    pre_install_packages:
      - requests
      - beautifulsoup4

# 路由规则（Agent自动选择）
routing_rules:
  - task_type: "data_analysis"
    preferred_template: "data-analysis"
  - task_type: "web_scraping"
    preferred_template: "web-scraping"
```

### 能力映射

编辑 `config/capabilities.yaml`：

```yaml
capability_categories:
  - id: code_sandbox
    description: "在安全沙箱中执行Python代码（支持网络、第三方包）"
    use_when: "需要网络访问或第三方Python包"

capabilities:
  - name: e2b_python_sandbox
    type: TOOL
    capabilities: [code_sandbox, code_execution, data_analysis]
    priority: 85
```

## 使用示例

### 示例 0: Initialize project（推荐）

当用户要做 vibe coding（快速起一个可预览的项目）时，建议走“确定性工具闭环”，避免在 chat 流程里临时拼命令：

```
1) sandbox_create_project：初始化项目骨架（创建 /home/user/<project_name>/）
2) sandbox_write_file：按需修改代码
3) sandbox_run_project：启动项目并返回 preview_url（用户可访问）
```

特点：
- 初始化/运行流程更稳定、可复用
- 预览地址由 `sandbox_run_project` 返回，避免误用 localhost

### 示例 1: 数据分析

```python
# Agent 会自动选择 e2b_python_sandbox
用户: "分析这个 CSV 文件的销售数据"

# LLM 生成 Plan
{
  "steps": [
    {
      "action": "使用 pandas 分析数据",
      "capability": "code_sandbox"  # 自动路由到 E2B
    }
  ]
}

# 执行代码
e2b_python_sandbox({
  "code": """
import pandas as pd

df = pd.read_csv('/home/user/input_data/sales.csv')
print(df.describe())

import matplotlib.pyplot as plt
df.plot(x='date', y='sales')
plt.savefig('/home/user/output_data/chart.png')
  """,
  "template": "data-analysis",  # 预装pandas，启动更快
  "return_files": ["/home/user/output_data/chart.png"]
})
```

### 示例 2: 网页爬取

```python
用户: "爬取 Hacker News 的前 10 条新闻"

e2b_python_sandbox({
  "code": """
import requests
from bs4 import BeautifulSoup

response = requests.get('https://news.ycombinator.com')
soup = BeautifulSoup(response.text, 'html.parser')

titles = []
for item in soup.select('.titleline')[:10]:
    titles.append(item.get_text())

for i, title in enumerate(titles, 1):
    print(f'{i}. {title}')
  """,
  "template": "web-scraping",  # 预装requests/bs4
  "auto_install": true  # 自动安装缺失的包
})
```

### 示例 3: 多轮对话

```python
# 第一轮
用户: "计算 1 到 100 的和"
e2b_python_sandbox({
  "code": "total = sum(range(1, 101))\nprint(f'Sum = {total}')"
})

# 第二轮（沙箱持久化，变量保持）
用户: "这个和除以 10 是多少？"
e2b_python_sandbox({
  "code": "print(f'Result = {total / 10}')"  # total 变量仍然存在
})
```

## 测试验证

### 运行完整测试

```bash
python tests/test_e2b_integration.py
```

### 测试覆盖范围

| 测试项 | 说明 | 状态 |
|-------|------|------|
| 基础代码执行 | 简单 Python 代码 | ✅ |
| 自动包安装 | 检测 import 并安装 | ✅ |
| 文件系统操作 | workspace 同步 | ✅ |
| 沙箱持久化 | 多轮对话复用 | ✅ |
| 模板管理 | 推荐和构建 | ✅ |
| Memory 集成 | 状态记录 | ✅ |

### 单独测试某个功能

```python
from tools.e2b_sandbox import E2BPythonSandbox
from core.memory import WorkingMemory

memory = WorkingMemory()
tool = E2BPythonSandbox(memory=memory)

result = await tool.execute(code="print('Hello E2B!')")
print(result)
```

## 常见问题

### Q1: E2B_API_KEY 未设置

**错误**：
```
ValueError: E2B_API_KEY 未设置
```

**解决**：
1. 访问 https://e2b.dev/dashboard
2. 创建账号并获取 API Key
3. 在 `.env` 文件中添加：`E2B_API_KEY=your_key`

### Q2: 沙箱连接失败

**错误**：
```
⚠️ 沙箱连接失败，创建新沙箱
```

**原因**：沙箱可能已超时或被回收

**解决**：自动创建新沙箱（无需手动处理）

### Q3: 包安装失败

**错误**：
```
⚠️ 包安装失败: ModuleNotFoundError
```

**解决**：
1. 检查包名是否正确
2. 使用 `auto_install=True`（默认开启）
3. 或在代码中手动安装：
```python
import subprocess
subprocess.run(['pip', 'install', 'package_name'])
```

### Q4: 文件未找到

**错误**：
```
FileNotFoundError: /home/user/data.csv
```

**解决**：
1. 使用完整路径：`/home/user/input_data/文件名`
2. 确保文件在 `workspace/inputs/` 目录中
3. 沙箱启动时会自动同步

### Q5: 如何禁用 E2B？

如果需要暂时禁用 E2B（使用 Claude 内置 Code Execution）：

**方法 1**: 修改 capabilities.yaml
```yaml
capabilities:
  - name: e2b_python_sandbox
    priority: 0  # 设为0，不会被选中
```

**方法 2**: 修改 task_type_mappings
```yaml
task_type_mappings:
  data_analysis:
    - code_execution  # 移除 code_sandbox
    - data_analysis
```

### Q6: 项目启动失败 / 端口检测超时

**错误**：
```
⚠️ 等待端口 8501 超时
⚠️ 端口 8501 未就绪，但服务可能仍在启动中
```

**常见原因及排查**：

1. **路径不正确**：确保 `project_path` 是完整路径（`/home/user/xxx`）或仅项目名
   - ✅ `/home/user/my_app` 或 `my_app`
   - ❌ `./my_app` 或 `user/my_app`

2. **依赖未安装**：检查 `requirements.txt` 或 `package.json` 是否正确
   ```bash
   # 日志会显示依赖安装情况
   📦 安装 Python 依赖: /home/user/my_app/requirements.txt
   ```

3. **入口文件缺失**：根据技术栈检查入口文件
   - streamlit/gradio/flask: `app.py`
   - fastapi: `main.py`（需要 `main:app`）
   - react/vue: `package.json` + `npm run dev`

4. **代码报错**：启动失败时会输出诊断信息
   ```
   ⚠️ 端口 8501 未就绪，诊断信息:
   (进程列表和最近日志)
   ```

**调试方法**：
```python
# 手动运行命令查看启动日志
result = await service.run_command(
    conversation_id,
    "cd /home/user/my_app && streamlit run app.py 2>&1 | head -50"
)
print(result["stdout"])
```

### Q7: 预览 URL 无法访问

**原因**：端口检测通过但服务实际没运行

**排查**：
1. 检查进程是否存在：`ps aux | grep python`
2. 检查端口是否真正监听：`ss -tlnp | grep 8501`
3. 确认服务绑定到 `0.0.0.0` 而非 `127.0.0.1`

**E2B 预览 URL 生成方式**（参考 [E2B 文档](https://e2b.dev/docs/commands/run-background)）：
```python
# 后台启动服务
sandbox.commands.run("streamlit run app.py ...", background=True)

# 获取公网可访问的 host
host = sandbox.get_host(8501)  # 返回类似 8501-xxx.e2b.app
preview_url = f"https://{host}"
```

## 性能优化

### 1. 使用预构建模板

```python
# ❌ 慢：每次安装包
e2b_python_sandbox({"code": "import pandas...", "template": "base"})

# ✅ 快：预装包，启动 <200ms
e2b_python_sandbox({"code": "import pandas...", "template": "data-analysis"})
```

### 2. 沙箱复用

```python
# 同一 session 内自动复用沙箱
# 第一次：创建沙箱（~2秒）
# 第二次：复用沙箱（~0.1秒）
```

### 3. 批量操作

```python
# ✅ 推荐：一次执行
code = """
import pandas as pd
df1 = pd.read_csv('file1.csv')
df2 = pd.read_csv('file2.csv')
result = pd.concat([df1, df2])
"""

# ❌ 不推荐：多次执行
# 每次都有网络开销
```

## 架构设计文档

更多详细设计，请参考：
- [00-ARCHITECTURE-OVERVIEW.md](./00-ARCHITECTURE-OVERVIEW.md) - V3.7 架构总览
- [E2B结合Claude实现Vibe Coding和浏览器操作完整指南.ini](./# E2B结合Claude实现Vibe Coding和浏览器操作完整指南.ini) - E2B 详细指南

## 下一步计划

Phase 2（未来）：
- [ ] Vibe Coding（生成完整应用）
- [ ] 浏览器自动化（Playwright）
- [ ] 后台任务（长时运行）
- [ ] 流式输出优化

---

**文档版本**: v1.0  
**最后更新**: 2025-12-29  
**维护者**: Zenflux Team

