# 生成的系统提示词

本目录包含由 LLM 根据 `prompt.md` 自动生成的场景化系统提示词。

## 文件说明

| 文件 | 用途 | 可编辑 |
|------|------|--------|
| `agent_schema.yaml` | Agent 配置（组件、工具、参数） | ✅ 是 |
| `intent_prompt.md` | 意图识别专用提示词 | ✅ 是 |
| `simple_prompt.md` | 简单任务处理提示词 | ✅ 是 |
| `medium_prompt.md` | 中等任务处理提示词 | ✅ 是 |
| `complex_prompt.md` | 复杂任务处理提示词 | ✅ 是 |
| `_metadata.json` | 元数据（哈希、时间戳） | ⚠️ 系统维护 |

## 运营编辑指南

### 1. 可以直接编辑

修改任意 `.md` 或 `.yaml` 文件，优化提示词效果。

### 2. 修改后自动保护

系统会检测您的手动修改，下次更新 `prompt.md` 时：
- **未编辑的文件**：自动更新
- **您编辑的文件**：保留您的版本，不会被覆盖

### 3. 强制重新生成

如需重新生成某个文件：
```bash
# 方式 1：删除单个文件
rm intent_prompt.md
# 下次启动时会重新生成

# 方式 2：删除元数据（全部重新生成）
rm _metadata.json

# 方式 3：使用命令行参数
python scripts/instance_loader.py --instance {instance_name} --force-refresh
```

## 更新策略

### 触发更新的条件

- 修改了 `prompt.md`
- 修改了 `config.yaml`
- 删除了 `_metadata.json`
- 使用了 `--force-refresh` 参数

### 文件保护机制

1. **首次生成**：所有文件由 LLM 生成
2. **后续更新**：
   - 检测 `prompt.md` / `config.yaml` 变化
   - 对比文件哈希，识别手动编辑
   - 跳过已手动编辑的文件
   - 只更新未编辑的文件

## 各文件详细说明

### agent_schema.yaml

Agent 的配置参数，包括：
- 名称和描述
- 启用的组件（Intent Analyzer、Plan Manager 等）
- 工具配置
- LLM 参数

**示例**：
```yaml
name: "Dazee"
description: "高级工作小助理"
components:
  intent_analyzer: true
  plan_manager: true
  memory_manager: true
tools:
  - web_search
  - document_generation
```

### intent_prompt.md

意图识别专用提示词，引导 LLM 快速判断：
- 用户意图类型（系统搭建/BI问数/综合咨询/追问）
- 任务复杂度（简单/中等/复杂）
- 是否需要规划
- 是否跳过记忆检索

**优化方向**：
- 添加/修改意图类型和关键词
- 调整复杂度判断规则
- 增加特殊路由规则

### simple_prompt.md

简单任务处理提示词，特点：
- 精简高效
- 快速响应
- 保留安全规则

**优化方向**：
- 精简冗余内容
- 保留核心规则
- 优化输出格式

### medium_prompt.md

中等任务处理提示词，特点：
- 平衡精简和完整
- 包含工具使用指南
- 基础执行流程

**优化方向**：
- 保留实用的工具说明
- 移除复杂任务专用规则
- 优化质量检查要点

### complex_prompt.md

复杂任务处理提示词，特点：
- 保留完整规则和流程
- 详细的规划、执行、验证流程
- 错误处理机制

**优化方向**：
- 去除冗余重复
- 合并相似规则
- 保留核心能力定义

## 常见问题

### Q: 编辑后生效吗？

是的，下次对话会使用您编辑的版本。

### Q: 如何恢复默认？

删除对应文件，下次启动时会重新生成。

### Q: 文件格式要求？

- `.md` 文件：Markdown 格式
- `.yaml` 文件：YAML 格式
- 确保语法正确，否则可能导致加载失败

### Q: 如何调试？

查看启动日志，会显示：
- 哪些文件从 `prompt_results/` 加载
- 哪些文件需要重新生成
- 生成是否成功
