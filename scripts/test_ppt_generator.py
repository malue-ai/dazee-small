#!/usr/bin/env python
"""
测试高质量闭环 PPT 生成工具

测试内容：
1. 基础功能测试 - 仅主题生成
2. 带搜索的完整流程测试
3. 自定义大纲测试
"""

import asyncio
import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()


async def test_basic_generation():
    """测试基础PPT生成（无搜索）"""
    print("\n" + "=" * 60)
    print("📋 测试 1: 基础PPT生成（无搜索）")
    print("=" * 60)
    
    from tools.ppt_generator import PPTGeneratorTool
    
    tool = PPTGeneratorTool()
    
    result = await tool.execute(
        topic="人工智能技术发展趋势",
        description="面向技术团队的AI技术发展趋势介绍",
        style="professional",
        slide_count=8,
        language="CHINESE",
        audience="技术团队",
        conversation_id="test_basic"
    )
    
    print(f"\n状态: {result['status']}")
    
    if result['status'] == 'success':
        print(f"\n📊 生成摘要:")
        print(result.get('summary', 'N/A'))
        
        output = result.get('output', {})
        print(f"\n📁 输出文件: {output.get('local_path', 'N/A')}")
        print(f"🔗 下载链接: {output.get('download_url', 'N/A')}")
    else:
        print(f"\n❌ 错误: {result.get('errors', [])}")
    
    # 打印各阶段详情
    print("\n📈 各阶段详情:")
    for phase_name, phase_data in result.get('phases', {}).items():
        status = phase_data.get('status', 'unknown')
        emoji = "✅" if status == "completed" else "❌"
        print(f"  {emoji} {phase_name}: {status}")
    
    return result


async def test_with_search():
    """测试带搜索的完整流程"""
    print("\n" + "=" * 60)
    print("📋 测试 2: 带搜索的完整流程")
    print("=" * 60)
    
    from tools.ppt_generator import PPTGeneratorTool
    
    tool = PPTGeneratorTool()
    
    result = await tool.execute(
        topic="2024年大模型行业发展报告",
        description="分析2024年大语言模型技术和商业化进展，面向投资人",
        search_queries=[
            "2024年大模型技术突破",
            "2024年GPT Claude Gemini对比",
            "AI大模型商业化应用案例"
        ],
        style="corporate",
        slide_count=12,
        language="CHINESE",
        time_context="2024年",
        audience="投资人",
        include_charts=True,
        conversation_id="test_search"
    )
    
    print(f"\n状态: {result['status']}")
    
    if result['status'] == 'success':
        print(f"\n📊 生成摘要:")
        print(result.get('summary', 'N/A'))
        
        # 显示搜索到的素材
        mc_phase = result.get('phases', {}).get('material_collection', {})
        if mc_phase:
            print(f"\n🔍 搜索素材数量: {mc_phase.get('materials_count', 0)}")
            for i, mat in enumerate(mc_phase.get('materials', [])[:3]):
                print(f"  {i+1}. {mat.get('title', 'N/A')[:50]}...")
    else:
        print(f"\n❌ 错误: {result.get('errors', [])}")
    
    return result


async def test_custom_outline():
    """测试自定义大纲"""
    print("\n" + "=" * 60)
    print("📋 测试 3: 自定义大纲")
    print("=" * 60)
    
    from tools.ppt_generator import PPTGeneratorTool
    
    tool = PPTGeneratorTool()
    
    custom_outline = [
        "产品概述",
        "市场机会",
        "核心功能",
        "技术架构",
        "竞争优势",
        "商业模式",
        "团队介绍",
        "融资需求"
    ]
    
    result = await tool.execute(
        topic="AI Agent 产品介绍",
        description="AI Agent SaaS产品的投资人路演",
        custom_outline=custom_outline,
        style="corporate",
        language="CHINESE",
        audience="投资人",
        conversation_id="test_outline"
    )
    
    print(f"\n状态: {result['status']}")
    
    if result['status'] == 'success':
        print(f"\n📊 生成摘要:")
        print(result.get('summary', 'N/A'))
        
        # 验证大纲是否被正确使用
        cp_phase = result.get('phases', {}).get('content_planning', {})
        print(f"\n📝 生成的幻灯片数量: {cp_phase.get('slides_count', 'N/A')}")
        print(f"📝 预期的幻灯片数量: {len(custom_outline)}")
    else:
        print(f"\n❌ 错误: {result.get('errors', [])}")
    
    return result


async def test_quick():
    """快速测试（不调用API，仅测试流程）"""
    print("\n" + "=" * 60)
    print("📋 快速测试: 仅测试工具初始化和参数验证")
    print("=" * 60)
    
    from tools.ppt_generator import PPTGeneratorTool
    
    tool = PPTGeneratorTool()
    
    print(f"✅ 工具名称: {tool.name}")
    print(f"✅ 工具描述: {tool.description[:100]}...")
    
    params = tool.parameters
    print(f"✅ 参数定义完整")
    print(f"  - 必需参数: {params.get('required', [])}")
    print(f"  - 可选参数数量: {len(params.get('properties', {})) - len(params.get('required', []))}")
    
    # 测试需求分析方法
    requirement = tool._analyze_requirement(
        topic="测试主题",
        description="测试描述",
        style="professional",
        slide_count=None,
        audience="测试受众",
        time_context=None,
        custom_outline=None
    )
    
    print(f"\n✅ 需求分析测试:")
    print(f"  - 主题: {requirement['topic']}")
    print(f"  - 目标幻灯片数: {requirement['target_slides']}")
    print(f"  - 时间上下文: {requirement['time_context']}")
    print(f"  - 模板: {requirement['template_mapping']}")
    
    # 测试内容规划
    slides = tool._plan_content(
        requirement=requirement,
        materials=[],
        include_charts=True
    )
    
    print(f"\n✅ 内容规划测试:")
    print(f"  - 生成幻灯片数: {len(slides)}")
    for i, slide in enumerate(slides[:3]):
        print(f"  - 第{i+1}页: {slide.get('title', 'N/A')} ({slide.get('layout', 'N/A')})")
    
    print("\n✅ 快速测试通过！")
    return {"status": "success"}


async def main():
    """主测试入口"""
    print("🚀 高质量闭环 PPT 生成工具测试")
    print("=" * 60)
    
    # 检查环境变量
    slidespeak_key = os.getenv("SLIDESPEAK_API_KEY")
    exa_key = os.getenv("EXA_API_KEY")
    
    print(f"SLIDESPEAK_API_KEY: {'✅ 已配置' if slidespeak_key else '❌ 未配置'}")
    print(f"EXA_API_KEY: {'✅ 已配置' if exa_key else '❌ 未配置'}")
    
    # 根据参数选择测试
    if len(sys.argv) > 1:
        test_type = sys.argv[1]
        
        if test_type == "quick":
            await test_quick()
        elif test_type == "basic":
            if not slidespeak_key:
                print("\n❌ 需要 SLIDESPEAK_API_KEY 环境变量")
                return
            await test_basic_generation()
        elif test_type == "search":
            if not slidespeak_key or not exa_key:
                print("\n❌ 需要 SLIDESPEAK_API_KEY 和 EXA_API_KEY 环境变量")
                return
            await test_with_search()
        elif test_type == "outline":
            if not slidespeak_key:
                print("\n❌ 需要 SLIDESPEAK_API_KEY 环境变量")
                return
            await test_custom_outline()
        elif test_type == "all":
            await test_quick()
            if slidespeak_key:
                await test_basic_generation()
                await test_custom_outline()
            if slidespeak_key and exa_key:
                await test_with_search()
        else:
            print(f"\n❌ 未知测试类型: {test_type}")
            print("可用选项: quick, basic, search, outline, all")
    else:
        # 默认运行快速测试
        print("\n运行快速测试（无需API）...")
        print("使用其他测试: python test_ppt_generator.py [quick|basic|search|outline|all]")
        await test_quick()


if __name__ == "__main__":
    asyncio.run(main())

