"""
Custom Claude Skills 目录

此目录用于存放向 Claude 注册的自定义 Skills。

注意：
- 这里的 Skills 需要通过 skill_cli.py 注册到 Claude 服务器
- 注册后 skill_id 会自动写入 config/capabilities.yaml
- 与 skills/library/ 不同，那里是工作流指南和辅助脚本

使用方法：
1. 创建 skill 目录：custom_claude_skills/my-skill/
2. 编写 SKILL.md（符合 Claude Skills 规范）
3. 注册：python scripts/skill_cli.py register --skill my-skill
"""

