#!/usr/bin/env python3
"""
简化的端到端测试：验证 Skill 注册流程

不依赖 ZenFlux 模块，直接验证配置文件和目录结构。
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

import yaml


def test_skill_registration():
    """测试 Skill 注册流程"""
    
    print("=" * 70)
    print("🧪 端到端测试：Skill 注册与发现流程")
    print("=" * 70)
    print()
    
    # ===== Step 1: 验证 capabilities.yaml =====
    print("📋 Step 1: 验证 capabilities.yaml 中的已注册 Skills")
    print("-" * 70)
    
    config_file = PROJECT_ROOT / "config" / "capabilities.yaml"
    if not config_file.exists():
        print(f"   ❌ 配置文件不存在: {config_file}")
        return False
    
    with open(config_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    all_capabilities = config.get("capabilities", [])
    custom_skills = [
        cap for cap in all_capabilities
        if cap.get("type") == "SKILL" 
        and cap.get("subtype") == "CUSTOM"
    ]
    
    registered_skills = [
        skill for skill in custom_skills
        if skill.get("skill_id")
    ]
    
    print(f"   总 Capabilities: {len(all_capabilities)}")
    print(f"   Custom Skills: {len(custom_skills)}")
    print(f"   已注册的 Custom Skills: {len(registered_skills)}")
    print()
    
    if not registered_skills:
        print("   ⚠️ 没有找到已注册的 Custom Skills")
        print()
    else:
        for skill in registered_skills:
            print(f"   ✅ {skill['name']}")
            print(f"      skill_id: {skill['skill_id']}")
            print(f"      注册时间: {skill.get('registered_at', 'N/A')}")
            print(f"      Skill 路径: {skill.get('skill_path', 'N/A')}")
            print()
    
    # ===== Step 2: 验证 Skill 目录结构 =====
    print("📋 Step 2: 验证 Skill 目录结构")
    print("-" * 70)
    
    skills_lib = PROJECT_ROOT / "skills" / "library"
    if not skills_lib.exists():
        print(f"   ❌ Skills 目录不存在: {skills_lib}")
        return False
    
    skill_dirs = [
        d for d in skills_lib.iterdir()
        if d.is_dir() and not d.name.startswith('_')
    ]
    
    print(f"   Skills 目录: {skills_lib}")
    print(f"   发现 {len(skill_dirs)} 个 Skill 目录")
    print()
    
    for skill_dir in skill_dirs:
        skill_md = skill_dir / "SKILL.md"
        has_skill_md = skill_md.exists()
        
        # 检查是否已注册
        registered = any(
            s['name'] == skill_dir.name 
            for s in registered_skills
        )
        
        status = "✅ 已注册" if registered else "⚠️ 未注册"
        md_status = "✅" if has_skill_md else "❌"
        
        print(f"   {status} - {skill_dir.name}")
        print(f"      SKILL.md: {md_status}")
        
        if registered:
            skill_info = next(s for s in registered_skills if s['name'] == skill_dir.name)
            print(f"      skill_id: {skill_info['skill_id'][:30]}...")
        print()
    
    # ===== Step 3: 验证关键 Skill =====
    print("📋 Step 3: 验证 professional-ppt-generator Skill")
    print("-" * 70)
    
    ppt_skill = next(
        (s for s in registered_skills if s['name'] == 'professional-ppt-generator'),
        None
    )
    
    checks = []
    
    if ppt_skill:
        print(f"   ✅ 找到 professional-ppt-generator")
        print(f"      skill_id: {ppt_skill['skill_id']}")
        print(f"      注册时间: {ppt_skill.get('registered_at', 'N/A')}")
        
        # 检查1: 有 skill_id
        checks.append(("有 skill_id", bool(ppt_skill.get("skill_id"))))
        
        # 检查2: skill_id 格式正确（以 skill_ 开头）
        skill_id = ppt_skill.get("skill_id", "")
        checks.append(("skill_id 格式正确", skill_id.startswith("skill_")))
        
        # 检查3: 有注册时间
        checks.append(("有注册时间", bool(ppt_skill.get("registered_at"))))
        
        # 检查4: 目录存在
        skill_path = PROJECT_ROOT / "skills" / "library" / "professional-ppt-generator"
        checks.append(("Skill 目录存在", skill_path.exists()))
        
        # 检查5: SKILL.md 存在
        skill_md = skill_path / "SKILL.md"
        checks.append(("SKILL.md 存在", skill_md.exists()))
        
        print()
        print("   验证项:")
        for check_name, passed in checks:
            status = "✅" if passed else "❌"
            print(f"      {status} {check_name}")
    else:
        print(f"   ❌ 未找到 professional-ppt-generator")
        print(f"   请运行: python scripts/skill_cli.py register --skill professional-ppt-generator")
        checks.append(("找到 professional-ppt-generator", False))
    
    print()
    
    # ===== 总结 =====
    print("=" * 70)
    all_passed = len(registered_skills) > 0 and all(check[1] for check in checks)
    if all_passed:
        print("✅ 所有测试通过！Skill 注册流程工作正常。")
        print()
        print("📝 下一步：运行端到端 PPT 生成测试")
        print("   python scripts/e2e_ppt_generation_test.py")
    else:
        print("❌ 部分测试失败，请检查上述输出。")
        if not registered_skills:
            print()
            print("💡 提示：请先注册 Skill")
            print("   python scripts/skill_cli.py register --skill professional-ppt-generator")
    print("=" * 70)
    
    return all_passed


if __name__ == "__main__":
    success = test_skill_registration()
    sys.exit(0 if success else 1)

