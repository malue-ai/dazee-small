#!/usr/bin/env python3
"""
端到端测试：验证 Skill 注册与发现流程

测试流程：
1. 从 capabilities.yaml 读取已注册的 Skills
2. 从 plan_todo_tool 发现 Skills（包含 skill_id）
3. 验证 skill_id 正确注入到 Plan 生成过程

这是一个快速测试，不需要调用 Claude API，只验证数据流。
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import yaml
from tools.plan_todo_tool import (
    discover_skills, 
    get_registered_skills_from_config,
    match_skills_for_query
)


async def test_skill_registration_flow():
    """测试 Skill 注册与发现流程"""
    
    print("=" * 70)
    print("🧪 端到端测试：Skill 注册与发现流程")
    print("=" * 70)
    print()
    
    # ===== Step 1: 验证 capabilities.yaml 包含已注册的 Skill =====
    print("📋 Step 1: 验证 capabilities.yaml")
    print("-" * 70)
    
    config_file = PROJECT_ROOT / "config" / "capabilities.yaml"
    with open(config_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    custom_skills = [
        cap for cap in config.get("capabilities", [])
        if cap.get("type") == "SKILL" 
        and cap.get("subtype") == "CUSTOM"
        and cap.get("skill_id")
    ]
    
    print(f"   ✅ 找到 {len(custom_skills)} 个已注册的 Custom Skills:")
    for skill in custom_skills:
        print(f"      - {skill['name']}")
        print(f"        skill_id: {skill['skill_id']}")
        print(f"        注册时间: {skill.get('registered_at', 'N/A')}")
    print()
    
    # ===== Step 2: 测试 get_registered_skills_from_config =====
    print("📋 Step 2: 测试 get_registered_skills_from_config()")
    print("-" * 70)
    
    registered_skills = get_registered_skills_from_config()
    print(f"   ✅ 返回 {len(registered_skills)} 个已注册 Skills")
    for skill in registered_skills:
        print(f"      - {skill['name']}: {skill.get('skill_id', 'N/A')}")
    print()
    
    # ===== Step 3: 测试 discover_skills（包含已注册和未注册） =====
    print("📋 Step 3: 测试 discover_skills()")
    print("-" * 70)
    
    all_skills = discover_skills()
    print(f"   ✅ 发现 {len(all_skills)} 个 Skills")
    
    registered_count = sum(1 for s in all_skills if s.get("skill_id"))
    unregistered_count = len(all_skills) - registered_count
    
    print(f"      - 已注册: {registered_count}")
    print(f"      - 未注册: {unregistered_count}")
    print()
    
    for skill in all_skills:
        status = "✅ 已注册" if skill.get("skill_id") else "⚠️ 未注册"
        print(f"      {status} - {skill['name']}")
        if skill.get("skill_id"):
            print(f"                skill_id: {skill['skill_id'][:30]}...")
    print()
    
    # ===== Step 4: 测试 match_skills_for_query（PPT 相关查询） =====
    print("📋 Step 4: 测试 match_skills_for_query()")
    print("-" * 70)
    
    test_query = "帮我做一个关于AI市场分析的PPT"
    matched_skills = match_skills_for_query(test_query, all_skills)
    
    print(f"   用户查询: {test_query}")
    print(f"   ✅ 匹配到 {len(matched_skills)} 个 Skills:")
    
    for skill in matched_skills:
        skill_id = skill.get("skill_id")
        status = "✅ 可直接使用" if skill_id else "⚠️ 需要先注册"
        print(f"      {status} - {skill['name']}")
        if skill_id:
            print(f"                skill_id: {skill_id[:30]}...")
    print()
    
    # ===== Step 5: 验证数据完整性 =====
    print("📋 Step 5: 验证数据完整性")
    print("-" * 70)
    
    checks = []
    
    # 检查1: capabilities.yaml 中的 Custom Skills 是否都有 skill_id
    check1 = all(skill.get("skill_id") for skill in custom_skills)
    checks.append(("所有 Custom Skills 都有 skill_id", check1))
    
    # 检查2: discover_skills 返回的已注册 Skills 数量是否正确
    check2 = registered_count == len(registered_skills)
    checks.append(("discover_skills 正确识别已注册 Skills", check2))
    
    # 检查3: PPT 相关查询是否匹配到了 professional-ppt-generator
    check3 = any(s['name'] == 'professional-ppt-generator' for s in matched_skills)
    checks.append(("PPT 查询匹配到 professional-ppt-generator", check3))
    
    # 检查4: 匹配到的 professional-ppt-generator 是否有 skill_id
    ppt_skill = next((s for s in matched_skills if s['name'] == 'professional-ppt-generator'), None)
    check4 = ppt_skill and ppt_skill.get("skill_id") is not None
    checks.append(("professional-ppt-generator 有 skill_id", check4))
    
    for check_name, passed in checks:
        status = "✅" if passed else "❌"
        print(f"   {status} {check_name}")
    
    print()
    
    # ===== 总结 =====
    print("=" * 70)
    all_passed = all(check[1] for check in checks)
    if all_passed:
        print("✅ 所有测试通过！Skill 注册与发现流程工作正常。")
    else:
        print("❌ 部分测试失败，请检查上述输出。")
    print("=" * 70)
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(test_skill_registration_flow())
    sys.exit(0 if success else 1)


