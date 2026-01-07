#!/usr/bin/env python3
"""
测试 Professional PPT Generator Skill

验证：
1. Skill 目录结构
2. 图表生成功能
3. Claude 调用 Skill 生成 PPT
"""

import os
import sys
import json
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载环境变量
load_dotenv(project_root / ".env")

import anthropic


def validate_skill_structure():
    """验证 Skill 目录结构"""
    print("\n" + "=" * 60)
    print("🧪 Step 1: 验证 Skill 目录结构")
    print("=" * 60)
    
    skill_path = project_root / "skills" / "library" / "professional-ppt-generator"
    
    required_files = [
        "SKILL.md",
        "scripts/tools.py",
        "scripts/__init__.py",
        "resources/style_templates.json"
    ]
    
    all_exist = True
    for file_path in required_files:
        full_path = skill_path / file_path
        exists = full_path.exists()
        status = "✅" if exists else "❌"
        print(f"   {status} {file_path}")
        if not exists:
            all_exist = False
    
    # 检查 SKILL.md 内容
    skill_md = skill_path / "SKILL.md"
    if skill_md.exists():
        content = skill_md.read_text(encoding='utf-8')
        
        # 检查 YAML frontmatter
        if content.startswith("---"):
            print("   ✅ YAML frontmatter 存在")
        else:
            print("   ❌ YAML frontmatter 缺失")
            all_exist = False
        
        # 检查关键章节
        key_sections = [
            "## 你是谁",
            "## 可用工具",
            "## 工作思路",
            "## 决策框架",
            "## 质量标准"
        ]
        for section in key_sections:
            if section in content:
                print(f"   ✅ 包含 {section}")
            else:
                print(f"   ⚠️ 缺少 {section}")
    
    return all_exist


def test_chart_generation():
    """测试图表生成"""
    print("\n" + "=" * 60)
    print("🧪 Step 2: 测试图表生成")
    print("=" * 60)
    
    async def run_tests():
        # 添加 tools 路径
        sys.path.insert(0, str(project_root / "skills" / "library" / "professional-ppt-generator" / "scripts"))
        from tools import generate_chart
        
        # 测试柱状图
        print("\n📊 测试柱状图生成...")
        result = await generate_chart(
            chart_type="bar",
            title="季度销售对比",
            data={
                "labels": ["Q1", "Q2", "Q3", "Q4"],
                "datasets": [
                    {"label": "2023", "data": [120, 150, 180, 200]},
                    {"label": "2024", "data": [150, 180, 220, 260]}
                ]
            }
        )
        
        if result.get("success"):
            print(f"   ✅ 柱状图生成成功")
            print(f"      Chart ID: {result.get('chart_id')}")
            print(f"      Image 大小: {len(result.get('image_base64', ''))} chars")
        else:
            print(f"   ❌ 柱状图生成失败: {result.get('error')}")
        
        # 测试饼图
        print("\n📊 测试饼图生成...")
        result = await generate_chart(
            chart_type="pie",
            title="市场份额分布",
            data={
                "labels": ["产品A", "产品B", "产品C", "其他"],
                "datasets": [
                    {"data": [35, 25, 20, 20]}
                ]
            }
        )
        
        if result.get("success"):
            print(f"   ✅ 饼图生成成功")
        else:
            print(f"   ❌ 饼图生成失败: {result.get('error')}")
        
        # 测试流程图
        print("\n📊 测试流程图生成...")
        result = await generate_chart(
            chart_type="flow",
            title="用户注册流程",
            data={
                "direction": "TD",
                "nodes": [
                    {"id": "A", "label": "开始", "shape": "round"},
                    {"id": "B", "label": "填写信息", "shape": "rect"},
                    {"id": "C", "label": "验证邮箱", "shape": "rect"},
                    {"id": "D", "label": "完成", "shape": "round"}
                ],
                "edges": [
                    {"from": "A", "to": "B"},
                    {"from": "B", "to": "C"},
                    {"from": "C", "to": "D", "label": "验证成功"}
                ]
            }
        )
        
        if result.get("success"):
            print(f"   ✅ 流程图生成成功")
        else:
            print(f"   ❌ 流程图生成失败: {result.get('error')}")
        
        return True
    
    try:
        return asyncio.run(run_tests())
    except Exception as e:
        print(f"   ❌ 测试失败: {e}")
        return False


def test_skill_with_claude():
    """测试 Claude 使用 Skill 生成 PPT"""
    print("\n" + "=" * 60)
    print("🧪 Step 3: 测试 Claude 使用 Skill")
    print("=" * 60)
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("   ❌ ANTHROPIC_API_KEY 未配置")
        return False
    
    # 读取 SKILL.md 作为 System Prompt 的一部分
    skill_md_path = project_root / "skills" / "library" / "professional-ppt-generator" / "SKILL.md"
    skill_content = skill_md_path.read_text(encoding='utf-8')
    
    # 移除 YAML frontmatter
    if skill_content.startswith("---"):
        end_idx = skill_content.index("---", 3) + 3
        skill_content = skill_content[end_idx:].strip()
    
    system_prompt = f"""你是一个专业 PPT 生成助手。

以下是你的能力说明和工作指南：

{skill_content}

---

现在，请根据用户的需求，设计一个 PPT 大纲。
你可以使用你的推理能力来分析需求、规划内容。
如果需求不够清晰，可以简短询问用户。
"""
    
    client = anthropic.Anthropic(api_key=api_key)
    
    # 测试用例
    test_queries = [
        "帮我做一个 AI 客服产品介绍的 PPT，给潜在客户看",
        "帮我做个 PPT"  # 模糊需求，测试 HITL
    ]
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n📝 测试用例 {i}: {query[:30]}...")
        
        try:
            response = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=2048,
                system=system_prompt,
                messages=[{"role": "user", "content": query}]
            )
            
            response_text = response.content[0].text if response.content else ""
            
            print(f"   ✅ Claude 响应成功")
            print(f"   📄 响应预览:")
            print("   " + "-" * 50)
            # 显示前 500 字符
            preview = response_text[:500]
            for line in preview.split('\n'):
                print(f"   {line}")
            if len(response_text) > 500:
                print("   ...")
            print("   " + "-" * 50)
            
            # 检查是否包含关键内容
            if "💡 需要确认" in response_text or "需要确认" in response_text:
                print("   📌 Claude 主动询问用户确认（HITL 触发）")
            if "大纲" in response_text or "结构" in response_text:
                print("   📌 Claude 生成了内容大纲")
            if "页" in response_text:
                print("   📌 Claude 规划了页面内容")
                
        except Exception as e:
            print(f"   ❌ 调用失败: {e}")
    
    return True


def test_skill_registration():
    """测试将 Skill 注册到 Claude"""
    print("\n" + "=" * 60)
    print("🧪 Step 4: 测试 Skill 注册")
    print("=" * 60)
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("   ❌ ANTHROPIC_API_KEY 未配置")
        return False
    
    skill_path = project_root / "skills" / "library" / "professional-ppt-generator"
    
    try:
        from anthropic.lib import files_from_dir
        
        client = anthropic.Anthropic(api_key=api_key)
        
        print(f"   📤 正在注册 Skill: {skill_path}")
        
        skill = client.beta.skills.create(
            display_title="Professional PPT Generator",
            files=files_from_dir(str(skill_path))
        )
        
        print(f"   ✅ Skill 注册成功!")
        print(f"      Skill ID: {skill.id}")
        print(f"      Version: {skill.latest_version}")
        print(f"      Created At: {skill.created_at}")
        
        # 保存 Skill ID 供后续使用
        skill_id_file = project_root / "outputs" / "professional_ppt_skill_id.txt"
        skill_id_file.parent.mkdir(exist_ok=True)
        skill_id_file.write_text(skill.id)
        print(f"      Skill ID 已保存到: {skill_id_file}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ 注册失败: {e}")
        return False


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("🚀 Professional PPT Generator Skill 测试")
    print("=" * 60)
    
    results = {}
    
    # Step 1: 验证目录结构
    results["目录结构"] = validate_skill_structure()
    
    # Step 2: 测试图表生成
    results["图表生成"] = test_chart_generation()
    
    # Step 3: 测试 Claude 使用 Skill
    results["Claude 调用"] = test_skill_with_claude()
    
    # Step 4: 注册 Skill（可选）
    user_input = input("\n是否注册 Skill 到 Claude? (y/N): ")
    if user_input.lower() == 'y':
        results["Skill 注册"] = test_skill_registration()
    
    # 总结
    print("\n" + "=" * 60)
    print("📊 测试结果总结")
    print("=" * 60)
    
    for test_name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"   {test_name}: {status}")
    
    all_passed = all(results.values())
    print(f"\n{'🎉 所有测试通过!' if all_passed else '⚠️ 部分测试失败'}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="测试 Professional PPT Generator Skill")
    parser.add_argument("--validate", action="store_true", help="仅验证目录结构")
    parser.add_argument("--chart", action="store_true", help="仅测试图表生成")
    parser.add_argument("--claude", action="store_true", help="仅测试 Claude 调用")
    parser.add_argument("--register", action="store_true", help="注册 Skill 到 Claude")
    
    args = parser.parse_args()
    
    if args.validate:
        validate_skill_structure()
    elif args.chart:
        test_chart_generation()
    elif args.claude:
        test_skill_with_claude()
    elif args.register:
        test_skill_registration()
    else:
        main()

