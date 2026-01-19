# E2B 沙盒与 S3 存储架构设计

> 本文档定义文件操作架构：E2B 云端沙盒执行 + S3 持久化存储

---

## 🔒 核心安全原则

**Agent 绝对不能直接操作本地文件系统！**

```
┌─────────────────────────────────────────────────────────────┐
│                      Agent 工具层                            │
│                                                             │
│  ✅ sandbox_write_file  → E2B 云端沙盒                       │
│  ✅ sandbox_run_command → E2B 云端沙盒                       │
│  ✅ S3 上传            → AWS S3 持久化存储                   │
│  ❌ 禁止任何本地文件操作                                     │
└─────────────────────────────────────────────────────────────┘
                              │
                ┌─────────────┴─────────────┐
                ▼                           ▼
┌─────────────────────────────┐   ┌───────────────────────────┐
│      E2B 云端沙盒            │   │       AWS S3 存储          │
│                             │   │                           │
│  /home/user/                │   │  产物存储：                │
│    └── 用户项目文件         │   │    - PPT                  │
│                             │   │    - 文档                  │
│  ✅ 代码执行                 │   │    - 其他产物             │
│  ✅ 项目运行                 │   │                           │
│  ✅ 多用户安全隔离           │   │  ✅ 永久存储              │
│  ⏰ 临时（1小时自动销毁）    │   │  ✅ 前端可下载            │
└─────────────────────────────┘   └───────────────────────────┘
```

### 架构变更说明

| 变更 | 状态 | 说明 |
|------|------|------|
| `core/workspace_manager.py` | 🗑️ 已删除 | 不再使用本地 workspace |
| `workspace_dir` 参数 | 🗑️ 已移除 | Agent/Service 不再接收此参数 |
| 本地文件工具 | 🗑️ 废弃 | 改用 E2B 沙盒工具 |
| S3 存储 | ✅ 推荐 | 持久化产物存储 |

### 代码清洁度检查

确保代码库中没有已废弃的 WorkspaceManager 引用：

```bash
python scripts/static_check.py --cleanup
```

---

## 一、文件操作方式

### 1.1 新架构概览

| 场景 | 方案 | 说明 |
|------|------|------|
| 代码执行 | E2B 沙盒 | 临时环境，安全隔离 |
| 项目运行 | E2B 沙盒 | 返回预览 URL |
| 产物存储 | S3 | 永久存储，可下载 |
| 临时缓存 | 系统 /tmp | 工具内部使用 |

### 1.2 不再支持

- ❌ 本地 `./workspace` 目录
- ❌ `WorkspaceManager` 类
- ❌ `workspace_dir` 参数
- ❌ Agent 直接操作本地文件

---

## 二、E2B 沙盒工具

### 2.1 可用工具列表

| 工具 | 功能 | 执行位置 |
|------|------|----------|
| `sandbox_write_file` | 写入文件 | E2B `/home/user/` |
| `sandbox_run_command` | 执行命令（cat/ls/rm 等） | E2B 沙盒 |
| `sandbox_create_project` | 创建项目骨架 | E2B `/home/user/{project}` |
| `sandbox_run_project` | 运行项目 | E2B 沙盒 |

### 2.2 工具实现位置

```
tools/sandbox_tools.py
```

### 2.3 使用示例

```python
# Agent 通过 E2B 沙盒写文件
result = await sandbox_write_file(
    conversation_id="conv_123",
    path="main.py",
    content="print('Hello World')"
)

# Agent 在 E2B 沙盒执行命令
result = await sandbox_run_command(
    conversation_id="conv_123",
    command="python main.py"
)
```

---

## 三、S3 持久化存储

### 3.1 使用场景

| 产物类型 | S3 存储 | 说明 |
|----------|---------|------|
| PPT | ✅ | SlideSpeak 生成的演示文稿 |
| 文档 | ✅ | 生成的报告、文档 |
| 数据文件 | ✅ | Excel、CSV 等 |

### 3.2 工具集成示例（SlideSpeak）

```python
# tools/slidespeak.py
async def execute(self, config: Dict, upload_to_s3: bool = False, **kwargs):
    # 1. 生成 PPT
    download_url = await self._generate_ppt(config)
    
    # 2. 可选：上传到 S3
    if upload_to_s3:
        s3_result = await self._upload_to_s3(download_url)
        return {
            "success": True,
            "s3_key": s3_result["s3_key"],
            "download_url": s3_result["presigned_url"]
        }
    
    return {"success": True, "download_url": download_url}
```

### 3.3 S3 上传工具

```
utils/s3_uploader.py
```

---

## 四、临时文件处理

### 4.1 系统临时目录

工具内部的临时缓存使用系统临时目录：

```python
import tempfile

# 使用系统临时目录
cache_dir = Path(tempfile.gettempdir()) / "zenflux_partition_cache"
cache_dir.mkdir(exist_ok=True)
```

### 4.2 示例：partition.py

```python
# tools/partition.py
def __init__(self, **kwargs):
    # 缓存目录使用系统临时目录
    default_cache_dir = os.path.join(tempfile.gettempdir(), "zenflux_partition_cache")
    self.config = PartitionConfig(
        cache_dir=os.getenv("PARTITION_CACHE_DIR", default_cache_dir)
    )
```

---

## 五、前端接口

### 5.1 E2B 沙盒管理

| 接口 | 方法 | 说明 |
|------|------|------|
| `/sandbox/{conv_id}/run` | POST | 启动项目到 E2B 沙盒 |
| `/sandbox/{conv_id}/{sandbox_id}` | GET | 获取沙盒状态 |
| `/sandbox/{conv_id}/{sandbox_id}` | DELETE | 停止沙盒 |

### 5.2 S3 文件下载

| 接口 | 方法 | 说明 |
|------|------|------|
| `/files/{s3_key}/download` | GET | 下载 S3 文件 |

---

## 六、E2B 沙盒生命周期

```
用户操作：
    点击「运行」→ 创建 Sandbox → 返回预览 URL → 使用
    ↓
    1小时后 Sandbox 自动销毁
    ↓
    再次点击「运行」→ 重新创建 → 重新返回 URL → 继续使用
```

### 6.1 关键点

- ✅ E2B 沙盒按需创建
- ✅ 1 小时后自动销毁
- ✅ 用户可随时重新启动
- ✅ 每个会话独立的沙盒

---

## 七、安全考虑

### 7.1 多用户隔离

- 每个 conversation 有独立的 E2B 沙盒
- 沙盒之间完全隔离
- 即使被攻击也不影响服务器

### 7.2 文件大小限制

- 单文件上传限制：100MB
- S3 存储无总大小限制（按用量计费）

### 7.3 代码清洁度检查

定期运行检查，确保没有废弃代码：

```bash
python scripts/static_check.py --cleanup
```

---

## 八、实现清单

### 8.1 已实现的组件

| 组件 | 职责 | 状态 |
|------|------|--------|
| `SandboxService` | E2B 沙盒生命周期管理 | ✅ 已实现 |
| `sandbox_tools` | Agent 的 E2B 沙盒操作工具 | ✅ 已实现 |
| `s3_uploader` | S3 文件上传 | ✅ 已实现 |
| `cleanup 检查脚本` | 确保没有废弃代码 | ✅ 已实现 |

### 8.2 已移除的组件

| 组件 | 状态 | 替代方案 |
|------|------|----------|
| `core/workspace_manager.py` | 🗑️ 已删除 | E2B 沙盒 |
| `workspace_dir` 参数 | 🗑️ 已移除 | 不需要 |
| 本地文件工具 | 🗑️ 废弃 | `sandbox_*` 工具 |

### 8.3 Agent Tools 列表

**E2B 沙盒操作工具（推荐使用）**

| 工具 | 状态 | 说明 |
|------|------|------|
| `sandbox_write_file` | ✅ 推荐 | 写入文件到 E2B 沙盒 |
| `sandbox_run_command` | ✅ 推荐 | 在 E2B 沙盒执行命令 |
| `sandbox_create_project` | ✅ 推荐 | 创建项目骨架 |
| `sandbox_run_project` | ✅ 推荐 | 运行项目获取预览 URL |

**已废弃的工具**

| 工具 | 状态 | 替代方案 |
|------|------|----------|
| `read_file` (本地) | ❌ 废弃 | `sandbox_run_command + cat` |
| `write_file` (本地) | ❌ 废弃 | `sandbox_write_file` |
| `list_dir` (本地) | ❌ 废弃 | `sandbox_run_command + ls` |

---

## 九、总结

```
新架构文件操作流程：

Agent 文件操作：
├── 代码执行/项目运行 → E2B 沙盒 (/home/user/)
├── 产物存储 (PPT/文档等) → S3
└── 临时缓存 → 系统临时目录 (/tmp)

✅ 不再有本地 ./workspace 目录
✅ Agent 不能直接操作本地文件系统
✅ 多用户安全隔离
```
