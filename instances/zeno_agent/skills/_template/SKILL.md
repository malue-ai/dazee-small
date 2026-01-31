---
name: your-skill-name
description: 简短描述该 Skill 的功能
---

# Skill 名称

简要说明这个 Skill 帮助用户完成什么任务。

## 核心能力

- **能力1**：描述
- **能力2**：描述
- **能力3**：描述

## 使用场景

- 场景1
- 场景2
- 场景3

## 输入参数

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| param1 | string | 是 | - | 参数说明 |
| param2 | int | 否 | 10 | 参数说明 |

## 输出格式

```json
{
  "success": true,
  "result": "...",
  "message": "操作完成"
}
```

## 使用示例

```python
# 示例代码
result = await your_skill_function(
    param1="value1",
    param2=20
)

if result["success"]:
    print(result["result"])
```

## ⚠️ 注意事项

- 注意事项1
- 注意事项2

## 环境变量配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `YOUR_API_KEY` | API 密钥 | - |

## 用户交互指引

| 时机 | 话术 |
|------|------|
| 开始前 | "好的，我来帮您..." |
| 完成后 | "已完成！" |
