#!/usr/bin/env python3
"""
测试 fallback_tool 功能（独立版本）

验证 Pre-built Skills 的 fallback_tool 是否正确配置
"""

import yaml
from pathlib import Path


def test_fallback_tool():
    """测试 fallback_tool 配置"""
    print("\n" + "=" * 60)
    print("🧪 测试 fallback_tool 功能")
    print("=" * 60)
    
    # 1. 加载配置文件
    project_root = Path(__file__).resolve().parents[2]
    config_path = project_root / "config" / "capabilities.yaml"
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    print(f"\n📁 配置文件: {config_path}")
    
    # 2. 检查 Pre-built Skills 配置
    print("\n📋 Pre-built Skills 配置检查:")
    prebuilt_skills = ["pptx", "xlsx", "docx", "pdf"]
    
    capabilities = config.get('capabilities', [])
    
    all_pass = True
    for skill_name in prebuilt_skills:
        # 查找 skill
        skill = None
        for cap in capabilities:
            if cap.get('name') == skill_name:
                skill = cap
                break
        
        if skill:
            skill_type = skill.get('type', 'unknown')
            subtype = skill.get('subtype', 'unknown')
            fallback = skill.get('fallback_tool')
            requires_cce = skill.get('constraints', {}).get('requires_claude_code_execution', False)
            
            # 检查结果
            status = "✅" if fallback else "❌"
            cce_status = "✅" if requires_cce else "⚠️"
            
            print(f"  {status} {skill_name}:")
            print(f"      type: {skill_type}, subtype: {subtype}")
            print(f"      fallback_tool: {fallback or '未配置'}")
            print(f"      requires_claude_code_execution: {cce_status} {requires_cce}")
            
            if not fallback:
                all_pass = False
        else:
            print(f"  ❌ {skill_name}: 未找到")
            all_pass = False
    
    # 3. 验证 fallback_tool 指向的工具存在
    print("\n🔗 验证 fallback_tool 指向的工具:")
    
    tool_names = [cap.get('name') for cap in capabilities if cap.get('type') == 'TOOL']
    
    for skill_name in prebuilt_skills:
        skill = next((cap for cap in capabilities if cap.get('name') == skill_name), None)
        if skill:
            fallback = skill.get('fallback_tool')
            if fallback:
                if fallback in tool_names:
                    print(f"  ✅ {skill_name} → {fallback} (存在)")
                else:
                    print(f"  ❌ {skill_name} → {fallback} (不存在！)")
                    all_pass = False
    
    # 4. 检查 Capability 类是否有 fallback_tool 字段
    print("\n📦 代码结构检查:")
    
    types_file = Path(__file__).parent.parent / "core" / "tool" / "capability" / "types.py"
    types_content = types_file.read_text(encoding='utf-8')
    
    if 'fallback_tool' in types_content:
        print("  ✅ types.py: Capability 类包含 fallback_tool 字段")
    else:
        print("  ❌ types.py: Capability 类缺少 fallback_tool 字段")
        all_pass = False
    
    registry_file = Path(__file__).parent.parent / "core" / "tool" / "capability" / "registry.py"
    registry_content = registry_file.read_text(encoding='utf-8')
    
    if 'fallback_tool' in registry_content:
        print("  ✅ registry.py: 解析 fallback_tool 配置")
    else:
        print("  ❌ registry.py: 未解析 fallback_tool")
        all_pass = False
    
    selector_file = Path(__file__).parent.parent / "core" / "tool" / "selector.py"
    selector_content = selector_file.read_text(encoding='utf-8')
    
    if 'fallback_tool' in selector_content:
        print("  ✅ selector.py: 使用 fallback_tool 逻辑")
    else:
        print("  ❌ selector.py: 未使用 fallback_tool")
        all_pass = False
    
    # 5. 总结
    print("\n" + "=" * 60)
    if all_pass:
        print("✅ 所有检查通过！fallback_tool 功能已正确实现")
    else:
        print("⚠️ 部分检查未通过，请查看上面的错误信息")
    print("=" * 60)
    
    return all_pass


if __name__ == "__main__":
    test_fallback_tool()
