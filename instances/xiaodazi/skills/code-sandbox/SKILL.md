---
name: code-sandbox
description: Secure sandboxed code execution for AI-generated scripts. Runs Python/JS in isolated environments (Docker or E2B) to protect the user's system.
metadata:
  xiaodazi:
    dependency_level: lightweight
    os: [common]
    backend_type: local
    user_facing: true
---

# 安全代码沙箱

在隔离的沙箱环境中执行 AI 生成的代码，保护用户系统安全。支持 Docker 本地沙箱（免费）和 E2B 云沙箱两种模式。

## 使用场景

- 用户说「帮我写个脚本分析这个 CSV 文件」→ 在沙箱中执行，不污染主系统
- 用户说「帮我画个图表」→ matplotlib 在沙箱中运行，输出图片文件
- 用户说「运行一下这段代码看看结果」→ 安全隔离执行
- 数据分析、原型验证、临时脚本等不适合在主系统直接执行的场景
- 执行来历不明或复杂度高的代码片段

## 何时使用此 Skill（而非直接 system.run）

```
判断逻辑：

需要执行代码
  ├── 简单系统命令（ls, git, pip 等） → 直接 system.run
  ├── 用户提供的完整脚本 → code-sandbox ✅ 更安全
  ├── AI 生成的分析/处理代码 → code-sandbox ✅ 推荐
  ├── 需要安装额外依赖的代码 → code-sandbox ✅ 不污染主环境
  └── 需要网络访问的爬虫/API 调用 → code-sandbox ✅ 隔离风险
```

## 前置条件（二选一）

### 方式一：Docker 本地沙箱（推荐，免费）

1. 安装 Docker：https://www.docker.com/get-started
2. 确保 Docker 正在运行：`docker info`
3. 无需额外配置，首次使用时自动拉取基础镜像

### 方式二：E2B 云沙箱

1. 注册 E2B 账号：https://e2b.dev/
2. 设置环境变量：`export E2B_API_KEY="your-key"`
3. 提供免费额度，适合不想装 Docker 的用户

## 执行方式

### Docker 本地沙箱模式

#### 执行 Python 脚本

```python
import asyncio
import tempfile
import os

async def run_in_sandbox(code: str, files: dict = None, timeout: int = 60):
    """在 Docker 沙箱中执行 Python 代码"""

    # 创建临时工作目录
    work_dir = tempfile.mkdtemp(prefix="sandbox_")

    # 写入用户代码
    script_path = os.path.join(work_dir, "script.py")
    with open(script_path, "w") as f:
        f.write(code)

    # 如果有输入文件，复制到工作目录
    if files:
        for name, content in files.items():
            fpath = os.path.join(work_dir, name)
            if isinstance(content, bytes):
                with open(fpath, "wb") as f:
                    f.write(content)
            else:
                with open(fpath, "w") as f:
                    f.write(content)

    # Docker 执行命令
    cmd = [
        "docker", "run", "--rm",
        "--network=none",               # 默认禁用网络（需要时可开启）
        "--memory=512m",                 # 内存限制
        "--cpus=1.0",                    # CPU 限制
        "-v", f"{work_dir}:/workspace",  # 挂载工作目录
        "-w", "/workspace",
        "python:3.12-slim",
        "python", "script.py"
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(
        proc.communicate(), timeout=timeout
    )

    return {
        "success": proc.returncode == 0,
        "stdout": stdout.decode(),
        "stderr": stderr.decode(),
        "output_dir": work_dir,  # 检查输出文件
    }
```

#### 带依赖安装的执行

```python
async def run_with_deps(code: str, packages: list, files: dict = None):
    """安装依赖后执行"""
    pip_install = " ".join(packages)
    wrapper = f"""
import subprocess, sys
subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", {', '.join(repr(p) for p in packages)}])

{code}
"""
    return await run_in_sandbox(wrapper, files, timeout=120)
```

### E2B 云沙箱模式

```python
# 需要 pip install e2b-code-interpreter
from e2b_code_interpreter import Sandbox

async def run_e2b(code: str):
    sandbox = Sandbox()
    execution = sandbox.run_code(code)
    return {
        "success": not execution.error,
        "stdout": execution.text,
        "error": str(execution.error) if execution.error else None,
        "results": execution.results,  # 包含图表等富媒体输出
    }
```

### 典型工作流

**数据分析**：
```
用户：分析一下这个 sales.csv 文件
→ 读取用户提供的 CSV 文件
→ 生成 pandas 分析代码
→ 在沙箱中执行（挂载 CSV 文件）
→ 提取输出的统计结果和图表
→ 向用户展示分析报告
```

**代码原型**：
```
用户：帮我写个爬虫抓取 xxx 网站的标题
→ 生成 requests + BeautifulSoup 代码
→ 在沙箱中执行（开启网络: --network=bridge）
→ 返回抓取结果
→ 如果用户满意，可选择在主系统中保存脚本
```

## 安全策略

| 维度 | 默认策略 | 可调整 |
|------|---------|--------|
| 网络 | 禁用（`--network=none`） | 用户确认后可开启 |
| 内存 | 512MB 上限 | 最大 2GB |
| CPU | 1 核 | 最大 2 核 |
| 超时 | 60 秒 | 最大 300 秒 |
| 文件系统 | 仅工作目录可写 | - |
| 特权 | 无 root 权限 | - |

## 输出规范

- 执行结果区分 stdout 和 stderr
- 如果生成了文件（图表、报告等），告知用户输出路径
- 执行超时或 OOM 时给出明确错误信息
- 代码执行失败时分析错误原因，建议修复方向
- 不在沙箱中执行涉及用户凭据的操作（API Key 等应通过环境变量传入）
