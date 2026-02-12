---
name: skill-template
description: 这是一个 Skill 模板，请替换为实际描述（简短说明技能的核心功能）
---

# Skill 名称

<!-- 
📌 模板说明：
本文件是 Claude Skill 的入口文件，遵循 Anthropic 官方规范。

🔧 YAML frontmatter 必填字段（不超过 1024 字符）：
- name: Skill 唯一标识（与目录名一致）
- description: 简短功能描述

使用步骤：
1. 修改上方 YAML 中的 name 和 description
2. 替换下方 Markdown 内容为实际技能说明
3. 在 skill_registry.yaml 中声明并启用
-->

简短描述此技能的核心功能（1-2 句话）。

## Capabilities

此技能可以：
- 能力1：具体描述
- 能力2：具体描述
- 能力3：具体描述

## How to Use

1. **输入数据**：描述用户需要提供什么
2. **选择操作**：描述可选的操作类型
3. **获取结果**：描述输出内容

## Input Format

支持的输入格式：
- CSV 文件
- JSON 数据
- 文本描述
- Excel 文件

## Output Format

输出结果包含：
- 计算结果
- 可视化图表（如适用）
- 格式化报告

## Example Usage

"请帮我执行 XXX 操作"

"基于提供的数据，分析 XXX"

## Scripts

如果此 Skill 包含 Python 脚本：

- `main.py`: 主执行脚本
- `utils.py`: 辅助函数

## Best Practices

1. 最佳实践1
2. 最佳实践2
3. 最佳实践3

## Limitations

- 限制1：描述此技能的局限性
- 限制2：描述不适用的场景
