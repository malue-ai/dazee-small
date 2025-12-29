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
"""


def get_e2b_sandbox_protocol() -> str:
    """获取 E2B Sandbox 协议"""
    return E2B_SANDBOX_PROTOCOL
