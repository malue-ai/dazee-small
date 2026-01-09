# 工具注册规范 (Tool Registration Specification)

## 📋 概述

本文档定义了 Zenflux Agent 的工具注册规范，包括：
- 工具类型和信任等级
- 代码存储策略
- 安全验证机制
- 执行隔离方案

## 🔐 核心原则

> **永远不要直接执行用户上传的任意代码**

## 📊 工具信任等级

| 等级 | 类型 | 信任度 | 代码来源 | 执行方式 |
|------|------|--------|----------|----------|
| L1 | 内置工具 | 完全信任 | 我们编写 | 直接执行 |
| L2 | 审核工具 | 高信任 | 用户提交，我们审核 | 直接执行 |
| L3 | 沙箱工具 | 中信任 | 用户代码 | E2B 沙箱 |
| L4 | MCP 工具 | 外部信任 | 远程服务 | HTTP/MCP |

## 🏗️ 架构设计

```
用户提交工具
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│                    验证层 (Validator)                    │
├─────────────────────────────────────────────────────────┤
│  1. Schema 验证（参数格式）                               │
│  2. 代码静态分析（禁止危险操作）                           │
│  3. 签名验证（如果是审核过的工具）                         │
└─────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│                   分流层 (Router)                        │
├─────────────────────────────────────────────────────────┤
│  内置工具 → 直接执行                                      │
│  审核工具 → 直接执行（已签名）                             │
│  沙箱工具 → E2B 沙箱执行                                  │
│  MCP 工具 → 远程调用                                      │
└─────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│                   执行层 (Executor)                      │
├─────────────────────────────────────────────────────────┤
│  • 超时控制                                              │
│  • 资源限制                                              │
│  • 错误捕获                                              │
│  • 结果验证                                              │
└─────────────────────────────────────────────────────────┘
```

## 📦 工具定义规范

### 1. 工具元数据（存储在数据库）

```json
{
  "id": "tool_xxxx",
  "name": "my_search_tool",
  "description": "搜索信息",
  "version": "1.0.0",
  "author": "user_123",
  
  "trust_level": "L3",
  "execution_mode": "sandbox",
  
  "input_schema": {
    "type": "object",
    "properties": {
      "query": {"type": "string", "description": "搜索关键词"}
    },
    "required": ["query"]
  },
  
  "output_schema": {
    "type": "object",
    "properties": {
      "results": {"type": "array"}
    }
  },
  
  "constraints": {
    "timeout": 30,
    "max_memory_mb": 512,
    "network_access": false,
    "file_access": false
  },
  
  "code_reference": {
    "type": "sandbox",
    "code_hash": "sha256:xxxxx",
    "storage_key": "tools/user_123/my_search_tool/v1.0.0.py"
  },
  
  "status": "active",
  "created_at": "2024-01-01T00:00:00Z",
  "approved_at": null,
  "approved_by": null
}
```

### 2. 用户提交的代码规范

```python
"""
工具代码模板 (Tool Code Template)

规范：
1. 必须是单个 Python 文件
2. 必须包含一个 main 函数或 Tool 类
3. 只能导入白名单中的模块
4. 不能有 I/O 操作（除非明确允许）
5. 必须有类型注解
6. 必须处理异常
"""

# ==================== 方式 1: 函数式 ====================

from typing import Dict, Any, List, Optional

async def main(query: str, num_results: int = 10) -> Dict[str, Any]:
    """
    工具主函数
    
    Args:
        query: 搜索关键词
        num_results: 结果数量
        
    Returns:
        搜索结果
        
    Raises:
        ValueError: 参数无效
    """
    if not query:
        raise ValueError("query 不能为空")
    
    # 工具逻辑（在沙箱中执行）
    results = []
    
    return {
        "success": True,
        "results": results,
        "count": len(results)
    }


# ==================== 方式 2: 类式 ====================

class Tool:
    """
    工具类（必须实现 execute 方法）
    """
    
    name = "my_tool"
    description = "工具描述"
    
    # 输入参数 Schema
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"}
        },
        "required": ["query"]
    }
    
    async def execute(self, query: str, **kwargs) -> Dict[str, Any]:
        """执行工具"""
        return {"result": "..."}
```

## 🛡️ 安全验证机制

### 1. 代码静态分析

```python
# 禁止的操作（静态检查）
FORBIDDEN_PATTERNS = [
    r"import\s+os",           # 禁止 os 模块
    r"import\s+subprocess",   # 禁止 subprocess
    r"import\s+sys",          # 禁止 sys
    r"__import__",            # 禁止动态导入
    r"eval\s*\(",             # 禁止 eval
    r"exec\s*\(",             # 禁止 exec
    r"open\s*\(",             # 禁止文件操作（除非允许）
    r"compile\s*\(",          # 禁止 compile
    r"globals\s*\(",          # 禁止 globals
    r"locals\s*\(",           # 禁止 locals
]

# 允许的导入（白名单）
ALLOWED_IMPORTS = [
    "typing",
    "dataclasses",
    "json",
    "re",
    "datetime",
    "math",
    "collections",
    "itertools",
    "functools",
    # 网络（需要 network_access=true）
    "httpx",
    "aiohttp",
    # 数据处理
    "pandas",
    "numpy",
]
```

### 2. 运行时隔离

```
┌─────────────────────────────────────────────────────────┐
│                    E2B 沙箱环境                          │
├─────────────────────────────────────────────────────────┤
│  • 独立的 Python 运行时                                  │
│  • 限制 CPU/内存/时间                                    │
│  • 网络隔离（可配置）                                    │
│  • 文件系统隔离                                          │
│  • 无法访问主机系统                                      │
└─────────────────────────────────────────────────────────┘
```

### 3. 超时和资源限制

| 资源 | 默认限制 | 最大限制 |
|------|----------|----------|
| 执行时间 | 30 秒 | 300 秒 |
| 内存 | 256 MB | 1 GB |
| CPU | 1 核 | 2 核 |
| 网络 | 禁止 | 可申请 |
| 文件 | 禁止 | 沙箱内 |

## 🔄 同步/异步处理

### 问题：用户提交同步函数怎么办？

```python
# 用户提交的同步函数
def my_sync_tool(query: str) -> dict:
    import time
    time.sleep(10)  # 阻塞！
    return {"result": "..."}
```

### 解决方案：强制异步 + 线程池包装

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial

# 线程池（用于运行同步代码）
_executor = ThreadPoolExecutor(max_workers=4)

async def execute_user_tool(
    code: str,
    input_data: dict,
    timeout: int = 30
) -> dict:
    """
    安全执行用户工具
    
    1. 在沙箱中执行
    2. 如果是同步函数，包装到线程池
    3. 强制超时控制
    """
    
    # 方案 1: E2B 沙箱执行（推荐）
    from tools.e2b_sandbox import E2BPythonSandbox
    
    sandbox = E2BPythonSandbox()
    result = await asyncio.wait_for(
        sandbox.execute(code=code, input=input_data),
        timeout=timeout
    )
    return result
    
    # 方案 2: 线程池执行（仅限审核过的代码）
    # loop = asyncio.get_event_loop()
    # result = await asyncio.wait_for(
    #     loop.run_in_executor(_executor, partial(func, **input_data)),
    #     timeout=timeout
    # )
    # return result
```

## 📝 工具注册流程

### 流程图

```
用户提交工具定义 + 代码
         │
         ▼
┌─────────────────────┐
│    Schema 验证      │ → 失败 → 返回错误
└─────────────────────┘
         │ 通过
         ▼
┌─────────────────────┐
│   代码静态分析      │ → 失败 → 返回危险代码警告
└─────────────────────┘
         │ 通过
         ▼
┌─────────────────────┐
│   确定信任等级      │
│   L1: 内置          │
│   L2: 需审核        │
│   L3: 沙箱执行      │ ← 默认
│   L4: MCP 远程      │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│   存储工具元数据    │ → 数据库
│   存储代码文件      │ → S3/对象存储（如果是沙箱工具）
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│   返回注册结果      │
│   (pending/active)  │
└─────────────────────┘
```

### 注册状态

| 状态 | 描述 | 可执行 |
|------|------|--------|
| `draft` | 草稿 | ❌ |
| `pending_review` | 等待审核（L2 工具） | ❌ |
| `active` | 已激活 | ✅ |
| `suspended` | 已暂停 | ❌ |
| `deprecated` | 已废弃 | ❌ |

## 🚨 错误处理

### 工具执行错误分类

```python
class ToolExecutionError(Exception):
    """工具执行错误基类"""
    pass

class ToolTimeoutError(ToolExecutionError):
    """执行超时"""
    pass

class ToolValidationError(ToolExecutionError):
    """参数验证失败"""
    pass

class ToolRuntimeError(ToolExecutionError):
    """运行时错误（用户代码 bug）"""
    pass

class ToolSecurityError(ToolExecutionError):
    """安全违规"""
    pass

class ToolResourceError(ToolExecutionError):
    """资源超限"""
    pass
```

### 错误响应格式

```json
{
  "success": false,
  "error": {
    "code": "TOOL_TIMEOUT",
    "message": "工具执行超时（30秒）",
    "details": {
      "tool_name": "my_tool",
      "timeout": 30,
      "elapsed": 30.5
    }
  },
  "invocation_id": "inv_xxxxx"
}
```

## 🔧 配置示例

### 工具约束配置

```yaml
# config/tool_constraints.yaml

# 默认约束
defaults:
  timeout: 30
  max_memory_mb: 256
  network_access: false
  file_access: false
  max_output_size: 1048576  # 1MB

# 按信任等级的约束
trust_levels:
  L1:  # 内置工具
    timeout: 300
    max_memory_mb: 1024
    network_access: true
    file_access: true
    
  L2:  # 审核工具
    timeout: 120
    max_memory_mb: 512
    network_access: true
    file_access: false
    
  L3:  # 沙箱工具
    timeout: 30
    max_memory_mb: 256
    network_access: false
    file_access: false
    
  L4:  # MCP 工具
    timeout: 60
    # 由 MCP 服务器控制资源

# 白名单模块
allowed_imports:
  - typing
  - json
  - re
  - datetime
  - math
  - collections
  # 需要 network_access=true
  network:
    - httpx
    - aiohttp
  # 需要特殊权限
  privileged:
    - pandas
    - numpy
```

## 📊 总结

### 我们的策略

| 场景 | 方案 | 代码存储 |
|------|------|----------|
| 平台内置工具 | 直接执行 | 代码库 |
| 用户自定义工具 | **E2B 沙箱执行** | S3 对象存储 |
| 审核通过的工具 | 直接执行 | 代码库（合并） |
| MCP 工具 | 远程调用 | 无（元数据） |

### 关键决策

1. **不存储代码到数据库执行** - 只存元数据
2. **用户代码在沙箱执行** - E2B 提供隔离
3. **强制超时和资源限制** - 防止 DoS
4. **静态分析 + 白名单** - 防止危险代码
5. **同步函数自动包装** - 兼容性处理

