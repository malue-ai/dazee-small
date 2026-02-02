#!/usr/bin/env python3
"""
Skill 机制重构验证脚本

验证内容：
1. 目录结构正确（skills/library/, skills/custom/, skills/workspace/）
2. 文件命名正确（SKILL.md 而非 INTERFACE.md）
3. Python 模块可正常导入
4. 类名和函数名正确
5. 多源加载机制工作正常
6. XML Prompt 格式正确
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 颜色输出
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def check_mark(success: bool) -> str:
    return f"{GREEN}✓{RESET}" if success else f"{RED}✗{RESET}"


def verify_directory_structure():
    """验证目录结构"""
    print("\n" + "=" * 60)
    print("1. 验证目录结构")
    print("=" * 60)
    
    results = []
    
    # 检查 skills/ 目录存在
    skills_dir = PROJECT_ROOT / "skills"
    results.append(("skills/ 目录存在", skills_dir.exists()))
    
    # 检查 skills/library/ 存在（系统级）
    library_dir = skills_dir / "library"
    results.append(("skills/library/ 目录存在（系统级）", library_dir.exists()))
    
    # 检查 instances/ 目录存在
    instances_dir = PROJECT_ROOT / "instances"
    results.append(("instances/ 目录存在", instances_dir.exists()))
    
    # 检查至少一个实例有 skills/ 目录
    instance_with_skills = False
    if instances_dir.exists():
        for instance_dir in instances_dir.iterdir():
            if instance_dir.is_dir() and not instance_dir.name.startswith('_'):
                instance_skills = instance_dir / "skills"
                if instance_skills.exists():
                    instance_with_skills = True
                    break
    results.append(("至少一个实例有 skills/ 目录", instance_with_skills))
    
    # 检查没有 interfaces/ 目录
    interfaces_dir = PROJECT_ROOT / "interfaces"
    results.append(("interfaces/ 目录不存在", not interfaces_dir.exists()))
    
    for name, passed in results:
        print(f"  {check_mark(passed)} {name}")
    
    return all(passed for _, passed in results)


def verify_skill_md_files():
    """验证 SKILL.md 文件"""
    print("\n" + "=" * 60)
    print("2. 验证 SKILL.md 文件")
    print("=" * 60)
    
    library_dir = PROJECT_ROOT / "skills" / "library"
    results = []
    
    if not library_dir.exists():
        print(f"  {RED}✗ skills/library/ 不存在{RESET}")
        return False
    
    skill_count = 0
    interface_count = 0
    
    for skill_dir in library_dir.iterdir():
        if not skill_dir.is_dir() or skill_dir.name.startswith('_'):
            continue
        
        skill_md = skill_dir / "SKILL.md"
        interface_md = skill_dir / "INTERFACE.md"
        
        if skill_md.exists():
            skill_count += 1
            print(f"  {GREEN}✓{RESET} {skill_dir.name}/SKILL.md 存在")
        elif interface_md.exists():
            interface_count += 1
            print(f"  {RED}✗ {skill_dir.name}/INTERFACE.md 应该是 SKILL.md{RESET}")
        else:
            print(f"  {YELLOW}⚠ {skill_dir.name}/ 没有 SKILL.md{RESET}")
    
    print(f"\n  总计: {skill_count} 个 SKILL.md, {interface_count} 个 INTERFACE.md")
    
    return interface_count == 0 and skill_count > 0


def verify_python_imports():
    """验证 Python 模块导入"""
    print("\n" + "=" * 60)
    print("3. 验证 Python 模块导入")
    print("=" * 60)
    
    results = []
    
    # 测试各个模块导入
    imports_to_test = [
        ("SkillLoader", "core.tool.capability.skill_loader", "SkillLoader"),
        ("SkillInfo", "core.tool.capability.skill_loader", "SkillInfo"),
        ("SkillMemory", "core.memory.system.skill", "SkillMemory"),
        ("CapabilityType.SKILL", "core.tool.capability.types", "CapabilityType"),
        ("generate_skills_section", "prompts.skills_loader", "generate_skills_section"),
    ]
    
    for display_name, module_path, attr_name in imports_to_test:
        try:
            module = __import__(module_path, fromlist=[attr_name])
            obj = getattr(module, attr_name)
            
            # 特殊检查 CapabilityType.SKILL
            if display_name == "CapabilityType.SKILL":
                has_skill = hasattr(obj, "SKILL")
                has_interface = hasattr(obj, "INTERFACE")
                
                if has_skill and not has_interface:
                    results.append((display_name, True))
                    print(f"  {GREEN}✓{RESET} {display_name} 存在且 INTERFACE 已移除")
                else:
                    results.append((display_name, False))
                    print(f"  {RED}✗ {display_name} 问题: SKILL={has_skill}, INTERFACE={has_interface}{RESET}")
            else:
                results.append((display_name, True))
                print(f"  {GREEN}✓{RESET} {display_name} 可正常导入")
                
        except Exception as e:
            results.append((display_name, False))
            print(f"  {RED}✗ {display_name} 导入失败: {e}{RESET}")
    
    # 检查不应该存在的导入
    deprecated_imports = [
        ("InterfaceLoader", "core.tool.capability", "InterfaceLoader"),
        ("InterfaceMemory", "core.memory.system", "InterfaceMemory"),
    ]
    
    for display_name, module_path, attr_name in deprecated_imports:
        try:
            module = __import__(module_path, fromlist=[attr_name])
            obj = getattr(module, attr_name, None)
            if obj is not None:
                results.append((f"{display_name} 已移除", False))
                print(f"  {RED}✗ {display_name} 应该已被移除{RESET}")
            else:
                results.append((f"{display_name} 已移除", True))
                print(f"  {GREEN}✓{RESET} {display_name} 已正确移除")
        except (ImportError, AttributeError):
            results.append((f"{display_name} 已移除", True))
            print(f"  {GREEN}✓{RESET} {display_name} 已正确移除")
    
    return all(passed for _, passed in results)


def verify_xml_prompt_format():
    """验证 XML Prompt 格式"""
    print("\n" + "=" * 60)
    print("4. 验证 XML Prompt 格式")
    print("=" * 60)
    
    try:
        from prompts.skills_loader import generate_skills_section
        
        # 创建测试数据
        test_skills = [
            {
                "name": "test-skill",
                "description": "测试技能描述",
                "location": "/skills/library/test-skill/SKILL.md"
            }
        ]
        
        output = generate_skills_section(test_skills)
        
        # 检查 XML 格式
        checks = [
            ("<available_skills>" in output, "包含 <available_skills> 标签"),
            ("</available_skills>" in output, "包含 </available_skills> 标签"),
            ("<skill " in output, "包含 <skill> 标签"),
            ("<description>" in output, "包含 <description> 标签"),
            ("SKILL.md" in output, "引用 SKILL.md 而非 INTERFACE.md"),
        ]
        
        results = []
        for passed, desc in checks:
            results.append((desc, passed))
            print(f"  {check_mark(passed)} {desc}")
        
        return all(passed for _, passed in results)
        
    except Exception as e:
        print(f"  {RED}✗ 生成 XML Prompt 失败: {e}{RESET}")
        return False


def verify_multi_source_loading():
    """验证两级加载机制（系统级 + 实例级）及配置开关"""
    print("\n" + "=" * 60)
    print("5. 验证两级加载机制及配置开关")
    print("=" * 60)
    
    try:
        from core.tool.capability.registry import CapabilityRegistry
        
        # 测试1：仅系统级加载（无配置过滤）
        registry_system = CapabilityRegistry()
        system_skills = [cap for cap in registry_system.capabilities.values() 
                         if hasattr(cap, 'skill_path') and cap.skill_path]
        
        print(f"  {GREEN}✓{RESET} 系统级加载（全部）: {len(system_skills)} 个 Skills")
        
        # 测试2：使用配置过滤系统级 Skills
        test_config = {
            "enabled_skills": {
                "planning-task": 1,       # 启用
                "slidespeak-generator": 0, # 禁用
                "ontology-builder": 1,     # 启用
            }
        }
        registry_filtered = CapabilityRegistry(instance_config=test_config)
        filtered_skills = [cap for cap in registry_filtered.capabilities.values() 
                          if hasattr(cap, 'skill_path') and cap.skill_path]
        
        print(f"  {GREEN}✓{RESET} 配置过滤后: {len(filtered_skills)} 个 Skills")
        
        # 测试3：系统级 + 实例级加载
        registry_instance = CapabilityRegistry(instance_id="dazee_agent")
        instance_skills = [cap for cap in registry_instance.capabilities.values() 
                          if hasattr(cap, 'skill_path') and cap.skill_path]
        
        print(f"  {GREEN}✓{RESET} 系统级 + 实例级加载: {len(instance_skills)} 个 Skills")
        
        # 检查实例级技能
        instance_only = [s for s in instance_skills if "instances" in s.skill_path]
        print(f"  {GREEN}✓{RESET} 其中实例级技能: {len(instance_only)} 个")
        
        checks = [
            (len(system_skills) > 0, "系统级 Skills 加载成功"),
            (len(filtered_skills) < len(system_skills), "配置过滤生效"),
            (len(instance_skills) >= len(system_skills), "实例级加载包含系统级"),
        ]
        
        for passed, desc in checks:
            print(f"  {check_mark(passed)} {desc}")
        
        return all(passed for passed, _ in checks)
        
    except Exception as e:
        print(f"  {RED}✗ 加载 CapabilityRegistry 失败: {e}{RESET}")
        import traceback
        traceback.print_exc()
        return False


def verify_eligibility_check():
    """验证资格检查机制"""
    print("\n" + "=" * 60)
    print("6. 验证资格检查机制")
    print("=" * 60)
    
    try:
        from core.tool.capability.registry import CapabilityRegistry
        from core.tool.capability.types import Capability, CapabilityType
        
        registry = CapabilityRegistry()
        
        # 检查方法存在
        has_should_include = hasattr(registry, 'should_include_skill')
        has_get_eligible = hasattr(registry, 'get_eligible_skills')
        
        print(f"  {check_mark(has_should_include)} should_include_skill() 方法存在")
        print(f"  {check_mark(has_get_eligible)} get_eligible_skills() 方法存在")
        
        if has_get_eligible:
            eligible = registry.get_eligible_skills()
            print(f"  {GREEN}✓{RESET} get_eligible_skills() 返回 {len(eligible)} 个技能")
        
        return has_should_include and has_get_eligible
        
    except Exception as e:
        print(f"  {RED}✗ 验证失败: {e}{RESET}")
        return False


def main():
    """运行所有验证"""
    print("\n" + "=" * 60)
    print("  Skill 机制重构验证")
    print("=" * 60)
    
    results = {
        "目录结构": verify_directory_structure(),
        "SKILL.md 文件": verify_skill_md_files(),
        "Python 模块导入": verify_python_imports(),
        "XML Prompt 格式": verify_xml_prompt_format(),
        "多源加载机制": verify_multi_source_loading(),
        "资格检查机制": verify_eligibility_check(),
    }
    
    print("\n" + "=" * 60)
    print("  验证结果汇总")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results.items():
        print(f"  {check_mark(passed)} {name}")
        if not passed:
            all_passed = False
    
    print()
    if all_passed:
        print(f"{GREEN}✓ 所有验证通过！{RESET}")
        return 0
    else:
        print(f"{RED}✗ 部分验证失败，请检查上述错误。{RESET}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
