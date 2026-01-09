"""
提示词分层集成测试

验证：
1. instance_loader 正确解析 PromptSchema
2. AgentFactory 正确传递 PromptSchema
3. SimpleAgent 运行时根据复杂度动态生成提示词
"""

import sys
import asyncio
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.prompt import (
    TaskComplexity,
    parse_prompt,
    generate_prompt,
    detect_complexity,
)


def test_prompt_compression_ratio():
    """测试提示词压缩比"""
    print("=" * 60)
    print("📝 测试: 提示词压缩比")
    print("=" * 60)
    
    # 使用示例提示词
    prompt_file = PROJECT_ROOT / "prompts/templates/prompt_example.md"
    
    if not prompt_file.exists():
        print(f"⚠️ 文件不存在: {prompt_file}")
        return
    
    with open(prompt_file, "r", encoding="utf-8") as f:
        raw_prompt = f.read()
    
    schema = parse_prompt(raw_prompt)
    
    print(f"\n📊 原始提示词: {len(raw_prompt):,} 字符")
    
    for complexity in TaskComplexity:
        layered_prompt = generate_prompt(schema, complexity)
        ratio = len(layered_prompt) / len(raw_prompt) * 100
        savings = (len(raw_prompt) - len(layered_prompt)) / 1000  # KB
        
        print(f"\n🏷️  {complexity.value.upper()}:")
        print(f"   长度: {len(layered_prompt):,} 字符")
        print(f"   压缩比: {ratio:.1f}%")
        print(f"   节省: {savings:.1f} KB / 请求")
    
    # 计算预估成本节省
    print("\n💰 成本节省估算（基于 Claude Sonnet 定价）:")
    simple_len = len(generate_prompt(schema, TaskComplexity.SIMPLE))
    medium_len = len(generate_prompt(schema, TaskComplexity.MEDIUM))
    complex_len = len(generate_prompt(schema, TaskComplexity.COMPLEX))
    
    # 假设 60% simple, 30% medium, 10% complex
    weighted_avg = simple_len * 0.6 + medium_len * 0.3 + complex_len * 0.1
    savings_pct = (1 - weighted_avg / len(raw_prompt)) * 100
    
    print(f"   加权平均长度: {weighted_avg:,.0f} 字符")
    print(f"   预估节省: {savings_pct:.1f}% 输入 token 成本")


def test_complexity_detection_accuracy():
    """测试复杂度检测的鲁棒性"""
    print("\n" + "=" * 60)
    print("📝 测试: 复杂度检测准确性")
    print("=" * 60)
    
    # 使用示例提示词获取 schema
    prompt_file = PROJECT_ROOT / "prompts/templates/prompt_example.md"
    
    if not prompt_file.exists():
        print(f"⚠️ 文件不存在: {prompt_file}")
        return
    
    with open(prompt_file, "r", encoding="utf-8") as f:
        raw_prompt = f.read()
    
    schema = parse_prompt(raw_prompt)
    
    # 边缘案例测试
    edge_cases = [
        # 简单
        ("查一下库存", TaskComplexity.SIMPLE),
        ("发票状态是什么", TaskComplexity.SIMPLE),
        ("多少钱", TaskComplexity.SIMPLE),
        ("哪个部门负责", TaskComplexity.SIMPLE),
        
        # 中等
        ("帮我分析这个月的销售趋势", TaskComplexity.MEDIUM),
        ("对比竞品 A 和 B 的功能差异", TaskComplexity.MEDIUM),
        ("生成一份周报", TaskComplexity.MEDIUM),
        ("给出优化建议", TaskComplexity.MEDIUM),
        
        # 复杂
        ("设计一个完整的供应链管理系统", TaskComplexity.COMPLEX),
        ("搭建 ERP 系统的财务模块", TaskComplexity.COMPLEX),
        ("构建用户画像的本体论模型", TaskComplexity.COMPLEX),
        ("规划 BI 报表系统的架构", TaskComplexity.COMPLEX),
    ]
    
    results = {TaskComplexity.SIMPLE: {"correct": 0, "total": 0},
               TaskComplexity.MEDIUM: {"correct": 0, "total": 0},
               TaskComplexity.COMPLEX: {"correct": 0, "total": 0}}
    
    for query, expected in edge_cases:
        detected = detect_complexity(query, schema)
        is_correct = detected == expected
        
        results[expected]["total"] += 1
        if is_correct:
            results[expected]["correct"] += 1
        
        status = "✅" if is_correct else "❌"
        if not is_correct:
            print(f"   {status} \"{query}\" → {detected.value} (期望: {expected.value})")
    
    print(f"\n📊 分类准确率:")
    total_correct = 0
    total_all = 0
    for complexity, stats in results.items():
        acc = stats["correct"] / stats["total"] * 100 if stats["total"] > 0 else 0
        total_correct += stats["correct"]
        total_all += stats["total"]
        print(f"   {complexity.value}: {stats['correct']}/{stats['total']} ({acc:.0f}%)")
    
    overall_acc = total_correct / total_all * 100
    print(f"\n   总体: {total_correct}/{total_all} ({overall_acc:.0f}%)")


def test_module_completeness():
    """测试模块完整性"""
    print("\n" + "=" * 60)
    print("📝 测试: 模块完整性")
    print("=" * 60)
    
    prompt_file = PROJECT_ROOT / "prompts/templates/prompt_example.md"
    
    if not prompt_file.exists():
        print(f"⚠️ 文件不存在: {prompt_file}")
        return
    
    with open(prompt_file, "r", encoding="utf-8") as f:
        raw_prompt = f.read()
    
    schema = parse_prompt(raw_prompt)
    
    # 检查各复杂度包含的模块
    expected_modules = {
        TaskComplexity.SIMPLE: ["role_definition", "absolute_prohibitions"],
        TaskComplexity.MEDIUM: [
            "role_definition", "absolute_prohibitions",
            "intent_recognition", "task_complexity",
            "output_format", "tool_selection", "progress_feedback"
        ],
        TaskComplexity.COMPLEX: list(schema.modules.keys()),  # 应包含所有
    }
    
    from core.prompt.prompt_layer import PromptModule
    
    for complexity in TaskComplexity:
        prompt = generate_prompt(schema, complexity)
        
        print(f"\n🏷️  {complexity.value.upper()} 模块检查:")
        
        # 检查核心模块是否存在
        core_modules = expected_modules[complexity]
        for module_name in core_modules:
            try:
                module = PromptModule(module_name)
                if module in schema.modules:
                    # 简单检查模块内容是否在生成的提示词中
                    module_content = schema.modules[module].content[:50]
                    if module_content in prompt:
                        print(f"   ✅ {module_name}")
                    else:
                        print(f"   ⚠️ {module_name} (内容未找到)")
                else:
                    print(f"   ⚠️ {module_name} (模块不存在)")
            except ValueError:
                print(f"   ⚠️ {module_name} (未知模块)")


if __name__ == "__main__":
    # 测试 1: 压缩比
    test_prompt_compression_ratio()
    
    # 测试 2: 检测准确性
    test_complexity_detection_accuracy()
    
    # 测试 3: 模块完整性
    test_module_completeness()
    
    print("\n" + "=" * 60)
    print("🎉 集成测试完成")
    print("=" * 60)
