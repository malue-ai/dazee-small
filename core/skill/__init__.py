"""
Skill 管理模块（预留）

职责：
- 未来可能用于 Skill 运行时管理扩展
- 当前功能已由 core/tool/capability/skill_loader.py 实现

术语说明（对齐 clawdbot）：
- Skill: 本地工作流技能（skills/library/），通过系统提示词注入
- 目录结构：skills/library/（内置）, skills/custom/（自定义）, skills/workspace/（工作区）

相关组件：
- core/tool/capability/skill_loader.py: Skill 内容加载器
- core/tool/capability/registry.py: Skill 发现和注册
- prompts/skills_loader.py: 生成系统提示词中的 Skills 列表
- config/capabilities.yaml: 统一能力配置
"""

# 预留模块，暂无导出
__all__ = []
