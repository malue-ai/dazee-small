#!/usr/bin/env python3
"""
术语重构验证脚本

独立运行，不依赖项目模块，只验证目录结构和文件内容

验证 Skill → Interface 术语重构是否完整：
- Interface: 本地工作流接口（interfaces/library/）
- Claude Skills: 上传到 Anthropic 服务器的技能（完全独立机制）
"""

import os
from pathlib import Path
import sys

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

def check(condition: bool, message: str, passed: list, failed: list):
    """检查条件并记录结果"""
    if condition:
        passed.append(f"✅ {message}")
    else:
        failed.append(f"❌ {message}")


def main():
    passed = []
    failed = []
    
    print("=" * 60)
    print("术语重构验证")
    print("=" * 60)
    print()
    
    # === 1. 目录结构验证 ===
    print("📁 目录结构验证")
    print("-" * 40)
    
    interfaces_dir = PROJECT_ROOT / "interfaces" / "library"
    check(
        interfaces_dir.exists(),
        f"interfaces/library/ 目录存在",
        passed, failed
    )
    
    old_skills_dir = PROJECT_ROOT / "skills" / "library"
    check(
        not old_skills_dir.exists(),
        f"旧的 skills/library/ 目录已删除",
        passed, failed
    )
    
    # === 2. INTERFACE.md 文件验证 ===
    print()
    print("📄 INTERFACE.md 文件验证")
    print("-" * 40)
    
    expected_interfaces = [
        "ontology-builder",
        "planning-task",
        "ppt-generator",
        "slidespeak-editor",
        "slidespeak-generator",
        "slidespeak-slide-editor"
    ]
    
    for interface_name in expected_interfaces:
        interface_md = interfaces_dir / interface_name / "INTERFACE.md"
        check(
            interface_md.exists(),
            f"{interface_name}/INTERFACE.md 存在",
            passed, failed
        )
        
        old_skill_md = interfaces_dir / interface_name / "SKILL.md"
        check(
            not old_skill_md.exists(),
            f"{interface_name}/SKILL.md 已删除",
            passed, failed
        )
    
    # === 3. Python 文件重命名验证 ===
    print()
    print("🐍 Python 文件重命名验证")
    print("-" * 40)
    
    # interface_loader.py
    interface_loader = PROJECT_ROOT / "core" / "tool" / "capability" / "interface_loader.py"
    check(
        interface_loader.exists(),
        "interface_loader.py 存在",
        passed, failed
    )
    
    old_skill_loader = PROJECT_ROOT / "core" / "tool" / "capability" / "skill_loader.py"
    check(
        not old_skill_loader.exists(),
        "旧的 skill_loader.py 已删除",
        passed, failed
    )
    
    # interface.py (memory)
    interface_memory = PROJECT_ROOT / "core" / "memory" / "system" / "interface.py"
    check(
        interface_memory.exists(),
        "core/memory/system/interface.py 存在",
        passed, failed
    )
    
    old_skill_memory = PROJECT_ROOT / "core" / "memory" / "system" / "skill.py"
    check(
        not old_skill_memory.exists(),
        "旧的 core/memory/system/skill.py 已删除",
        passed, failed
    )
    
    # interfaces_loader.py (prompts)
    interfaces_loader = PROJECT_ROOT / "prompts" / "interfaces_loader.py"
    check(
        interfaces_loader.exists(),
        "prompts/interfaces_loader.py 存在",
        passed, failed
    )
    
    old_skills_loader = PROJECT_ROOT / "prompts" / "skills_loader.py"
    check(
        not old_skills_loader.exists(),
        "旧的 prompts/skills_loader.py 已删除",
        passed, failed
    )
    
    # === 4. 类名验证 ===
    print()
    print("🔤 类名验证")
    print("-" * 40)
    
    # InterfaceLoader
    if interface_loader.exists():
        content = interface_loader.read_text()
        check(
            "class InterfaceLoader" in content,
            "InterfaceLoader 类定义存在",
            passed, failed
        )
        check(
            "class InterfaceInfo" in content,
            "InterfaceInfo 类定义存在",
            passed, failed
        )
    
    # InterfaceMemory
    if interface_memory.exists():
        content = interface_memory.read_text()
        check(
            "class InterfaceMemory" in content,
            "InterfaceMemory 类定义存在",
            passed, failed
        )
    
    # === 5. Claude Skills 独立性验证 ===
    print()
    print("🔷 Claude Skills 独立性验证")
    print("-" * 40)
    
    # interfaces_loader 不应该包含 PREBUILT_CLAUDE_SKILLS
    if interfaces_loader.exists():
        content = interfaces_loader.read_text()
        check(
            "PREBUILT_CLAUDE_SKILLS" not in content,
            "interfaces_loader.py 不包含 PREBUILT_CLAUDE_SKILLS",
            passed, failed
        )
    
    # routers/skills.py 应该包含 PREBUILT_CLAUDE_SKILLS
    routers_skills = PROJECT_ROOT / "routers" / "skills.py"
    if routers_skills.exists():
        content = routers_skills.read_text()
        check(
            "PREBUILT_CLAUDE_SKILLS" in content,
            "routers/skills.py 包含 PREBUILT_CLAUDE_SKILLS",
            passed, failed
        )
    
    # core/llm/claude.py 保留 SkillInfo（用于 Claude API）
    claude_llm = PROJECT_ROOT / "core" / "llm" / "claude.py"
    if claude_llm.exists():
        content = claude_llm.read_text()
        check(
            "class SkillInfo" in content,
            "core/llm/claude.py 保留 SkillInfo（Claude API）",
            passed, failed
        )
    
    # === 6. 规则文件验证 ===
    print()
    print("📜 规则文件验证")
    print("-" * 40)
    
    interfaces_rule = PROJECT_ROOT / ".cursor" / "rules" / "06-interfaces-development"
    check(
        interfaces_rule.exists(),
        "06-interfaces-development 规则存在",
        passed, failed
    )
    
    old_skills_rule = PROJECT_ROOT / ".cursor" / "rules" / "06-skills-development"
    check(
        not old_skills_rule.exists(),
        "旧的 06-skills-development 规则已删除",
        passed, failed
    )
    
    # === 7. __init__.py 导出验证 ===
    print()
    print("📦 __init__.py 导出验证")
    print("-" * 40)
    
    capability_init = PROJECT_ROOT / "core" / "tool" / "capability" / "__init__.py"
    if capability_init.exists():
        content = capability_init.read_text()
        check(
            "InterfaceLoader" in content,
            "capability/__init__.py 导出 InterfaceLoader",
            passed, failed
        )
        check(
            "InterfaceInfo" in content,
            "capability/__init__.py 导出 InterfaceInfo",
            passed, failed
        )
    
    system_init = PROJECT_ROOT / "core" / "memory" / "system" / "__init__.py"
    if system_init.exists():
        content = system_init.read_text()
        check(
            "InterfaceMemory" in content,
            "system/__init__.py 导出 InterfaceMemory",
            passed, failed
        )
    
    # === 结果汇总 ===
    print()
    print("=" * 60)
    print("验证结果汇总")
    print("=" * 60)
    print()
    
    for msg in passed:
        print(msg)
    
    print()
    
    for msg in failed:
        print(msg)
    
    print()
    print("-" * 60)
    print(f"通过: {len(passed)}, 失败: {len(failed)}")
    print("-" * 60)
    
    if failed:
        print()
        print("⚠️ 有测试失败，请检查上述失败项")
        sys.exit(1)
    else:
        print()
        print("🎉 所有验证通过！术语重构完成。")
        sys.exit(0)


if __name__ == "__main__":
    main()
