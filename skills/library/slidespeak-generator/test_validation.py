#!/usr/bin/env python3
"""
测试验证逻辑 - 只测试官方API硬性约束

Reference: https://docs.slidespeak.co/basics/api-references/slide-by-slide/
"""

import sys
import os
import json
from pathlib import Path

# Import from scripts directory
scripts_path = Path(__file__).parent / 'scripts'
sys.path.insert(0, str(scripts_path))

try:
    from config_builder import validate_api_constraints  # type: ignore
except ImportError:
    # Fallback: direct import
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "config_builder",
        scripts_path / "config_builder.py"
    )
    config_builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config_builder)
    validate_api_constraints = config_builder.validate_api_constraints


def test_valid_config():
    """测试：符合API规范的配置"""
    print("\n" + "="*60)
    print("测试 1: 符合API规范的配置")
    print("="*60)
    
    config = {
        "template": "DEFAULT",
        "language": "CHINESE",
        "slides": [
            {
                "title": "产品概述",
                "layout": "ITEMS",
                "item_amount": 4,
                "content": "核心功能介绍"
            },
            {
                "title": "市场对比",
                "layout": "COMPARISON",
                "item_amount": 2,  # API要求：exactly 2
                "content": "我们 vs 竞品"
            },
            {
                "title": "SWOT分析",
                "layout": "SWOT",
                "item_amount": 4,  # API要求：exactly 4
                "content": "S W O T"
            }
        ]
    }
    
    is_valid, errors = validate_api_constraints(config)
    
    if is_valid:
        print("✅ 通过：配置符合API规范")
        return True
    else:
        print("❌ 失败：配置应该通过但被拒绝")
        for error in errors:
            print(f"  {error}")
        return False


def test_comparison_wrong_amount():
    """测试：COMPARISON layout的item_amount错误"""
    print("\n" + "="*60)
    print("测试 2: COMPARISON layout (应该=2，传了3)")
    print("="*60)
    
    config = {
        "template": "DEFAULT",
        "slides": [
            {
                "title": "对比",
                "layout": "COMPARISON",
                "item_amount": 3,  # 错误：应该是2
                "content": "项目1 项目2 项目3"
            }
        ]
    }
    
    is_valid, errors = validate_api_constraints(config)
    
    if not is_valid:
        print("✅ 通过：正确识别了API约束违规")
        for error in errors:
            print(f"  {error}")
        return True
    else:
        print("❌ 失败：应该拒绝但通过了")
        return False


def test_swot_wrong_amount():
    """测试：SWOT layout的item_amount错误"""
    print("\n" + "="*60)
    print("测试 3: SWOT layout (应该=4，传了3)")
    print("="*60)
    
    config = {
        "template": "DEFAULT",
        "slides": [
            {
                "title": "SWOT分析",
                "layout": "SWOT",
                "item_amount": 3,  # 错误：应该是4
                "content": "S W O"
            }
        ]
    }
    
    is_valid, errors = validate_api_constraints(config)
    
    if not is_valid:
        print("✅ 通过：正确识别了API约束违规")
        for error in errors:
            print(f"  {error}")
        return True
    else:
        print("❌ 失败：应该拒绝但通过了")
        return False


def test_missing_required_fields():
    """测试：缺少必需字段"""
    print("\n" + "="*60)
    print("测试 4: 缺少必需字段")
    print("="*60)
    
    config = {
        "template": "DEFAULT",
        "slides": [
            {
                "title": "示例",
                # 缺少 layout 或 layout_name
                "item_amount": 3,
                "content": "内容"
            }
        ]
    }
    
    is_valid, errors = validate_api_constraints(config)
    
    if not is_valid:
        print("✅ 通过：正确识别了缺少必需字段")
        for error in errors:
            print(f"  {error}")
        return True
    else:
        print("❌ 失败：应该拒绝但通过了")
        return False


def test_flexible_item_amounts():
    """测试：非固定约束的layout允许灵活的item_amount"""
    print("\n" + "="*60)
    print("测试 5: ITEMS layout允许灵活的item_amount")
    print("="*60)
    
    configs = [
        # ITEMS with 2 items
        {
            "template": "DEFAULT",
            "slides": [{
                "title": "Test",
                "layout": "ITEMS",
                "item_amount": 2,
                "content": "Item1 Item2"
            }]
        },
        # ITEMS with 10 items
        {
            "template": "DEFAULT",
            "slides": [{
                "title": "Test",
                "layout": "ITEMS",
                "item_amount": 10,
                "content": "Many items"
            }]
        },
    ]
    
    all_valid = True
    for i, config in enumerate(configs, 1):
        is_valid, errors = validate_api_constraints(config)
        if not is_valid:
            print(f"❌ Config {i} 被拒绝（不应该）:")
            for error in errors:
                print(f"  {error}")
            all_valid = False
    
    if all_valid:
        print("✅ 通过：ITEMS layout允许灵活的item_amount（只要不违反固定约束）")
        return True
    else:
        return False


def main():
    """运行所有测试"""
    print("\n" + "🧪"*30)
    print("SlideSpeak API约束验证测试")
    print("只测试官方API文档明确要求的约束")
    print("🧪"*30)
    
    tests = [
        ("符合API规范", test_valid_config),
        ("COMPARISON=2约束", test_comparison_wrong_amount),
        ("SWOT=4约束", test_swot_wrong_amount),
        ("必需字段检查", test_missing_required_fields),
        ("灵活item_amount", test_flexible_item_amounts),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ 测试异常：{e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # 总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}  {name}")
    
    print(f"\n通过率: {passed}/{total} ({passed*100//total}%)")
    
    if passed == total:
        print("\n🎉 所有测试通过！")
        print("   验证逻辑只检查官方API硬性约束，不限制智能化生成")
        return 0
    else:
        print("\n⚠️  部分测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
