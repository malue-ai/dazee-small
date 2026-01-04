"""
E2B Python Sandbox Protocol - System Prompt 扩展
面向 LLM，简洁直接
"""

E2B_SANDBOX_PROTOCOL = """
## E2B Python Sandbox

### 能力对比

| 工具 | 网络访问 | 第三方包 | 文件持久化 | 适用场景 |
|-----|---------|---------|-----------|---------|
| e2b_python_sandbox | ✅ | ✅ | ✅ session级 | API调用、爬虫、数据分析 |
| code_execution | ❌ | 内置包only | ❌ | 配置生成、简单计算 |

### 选择逻辑

```
需要网络/第三方包/文件持久化 → e2b_python_sandbox
简单计算/配置生成 → code_execution
```

### 文件路径

```python
# 读取输入
df = pd.read_csv('/home/user/input_data/data.csv')

# 保存输出
plt.savefig('/home/user/output_data/chart.png')
df.to_csv('/home/user/output_data/result.csv')
```

### 工具调用

```json
e2b_python_sandbox({
  "code": "import pandas as pd\ndf = pd.read_csv(...)",
  "template": "data-analysis",  // base | data-analysis | web-scraping
  "return_files": ["/home/user/output_data/file.csv"]
})
```

### 模板

- `base`: 按需安装包（默认）
- `data-analysis`: 预装 pandas, numpy, matplotlib
- `web-scraping`: 预装 requests, beautifulsoup4

### 多轮对话

同一 session 内：
- 文件保持（`/home/user/output_data/`）
- 已安装包复用

### 代码示例

**数据分析**：
```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv('/home/user/input_data/sales.csv')
summary = df.describe()
print(summary)

plt.figure(figsize=(10, 6))
df.plot(x='date', y='sales')
plt.savefig('/home/user/output_data/chart.png')
```

**爬虫**：
```python
import requests
from bs4 import BeautifulSoup

response = requests.get('https://news.ycombinator.com')
soup = BeautifulSoup(response.text, 'html.parser')

titles = [item.get_text() for item in soup.select('.titleline')[:10]]
print(f'爬取 {len(titles)} 条')
```

**API调用**：
```python
import requests

response = requests.get('https://api.github.com/users/octocat')
data = response.json()
print(data['name'], data['public_repos'])
```

---

## E2B Vibe Coding（前端应用生成）

### ⚠️ 重要：必须声明依赖！

当使用 `e2b_vibe_coding` 创建应用时，**必须在 requirements 参数中声明所有非标准依赖**。

### 预装包（无需声明）

| 技术栈 | 预装包 |
|-------|--------|
| streamlit | streamlit, pandas, numpy, matplotlib, plotly |
| gradio | gradio, numpy, pandas |
| nextjs | （npm 依赖） |
| vue | （npm 依赖） |

### ⚠️ 额外依赖必须声明！

如果你的代码使用了预装包之外的库（如 `audio_recorder_streamlit`、`openai`、`langchain` 等），
**必须在 requirements 参数中声明**，否则会报 `ModuleNotFoundError`！

### 正确的调用格式

```json
e2b_vibe_coding({
  "action": "create",
  "stack": "streamlit",
  "description": "ASR语音识别应用",
  "code": "import streamlit as st\\nfrom audio_recorder_streamlit import audio_recorder\\n...",
  "requirements": ["audio_recorder_streamlit", "openai-whisper", "soundfile"]
})
```

### ❌ 错误示例（会导致 ModuleNotFoundError）

```json
e2b_vibe_coding({
  "action": "create",
  "stack": "streamlit",
  "code": "from audio_recorder_streamlit import audio_recorder\\n..."
  // ❌ 缺少 requirements 参数！
})
```

### ✅ 正确示例

```json
e2b_vibe_coding({
  "action": "create",
  "stack": "streamlit",
  "code": "from audio_recorder_streamlit import audio_recorder\\n...",
  "requirements": ["audio_recorder_streamlit"]  // ✅ 声明额外依赖
})
```

### 如何判断需要哪些依赖？

检查代码中的 `import` 语句：
1. 标准库（os, json, datetime 等）→ 无需声明
2. 预装包（streamlit, pandas, numpy 等）→ 无需声明
3. 其他第三方包 → **必须在 requirements 中声明**

"""


def get_e2b_sandbox_protocol() -> str:
    """获取 E2B Sandbox 协议"""
    return E2B_SANDBOX_PROTOCOL
