"""
测试提示词分层系统

验证：
1. 解析运营写的长提示词
2. 根据复杂度生成不同版本
3. 复杂度检测准确性
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.prompt import (
    TaskComplexity,
    PromptSchema,
    parse_prompt,
    generate_prompt,
    detect_complexity,
    detect_complexity_with_confidence,
)


def test_parse_prompt():
    """测试解析 prompt_example.md"""
    print("=" * 60)
    print("📝 测试 1: 解析运营提示词")
    print("=" * 60)
    
    # 读取 prompt_example.md
    prompt_file = PROJECT_ROOT / "prompts/templates/prompt_example.md"
    
    if not prompt_file.exists():
        print(f"⚠️ 文件不存在: {prompt_file}")
        return None
    
    with open(prompt_file, "r", encoding="utf-8") as f:
        raw_prompt = f.read()
    
    print(f"原始提示词长度: {len(raw_prompt)} 字符")
    
    # 解析
    schema = parse_prompt(raw_prompt)
    
    print(f"\n✅ 解析结果:")
    print(f"   Agent 名称: {schema.agent_name}")
    print(f"   Agent 角色: {schema.agent_role[:50]}...")
    print(f"   解析模块数: {len(schema.modules)}")
    print(f"   工具数量: {len(schema.tools)}")
    print(f"   意图类型: {len(schema.intent_types)}")
    
    print(f"\n📦 解析的模块:")
    for module, content in schema.modules.items():
        print(f"   • {module.value}: {len(content.content)} 字符")
    
    print(f"\n🔑 复杂度关键词:")
    for complexity, keywords in schema.complexity_keywords.items():
        print(f"   • {complexity.value}: {keywords[:5]}...")
    
    return schema


def test_generate_prompts(schema: PromptSchema):
    """测试生成不同版本的提示词"""
    print("\n" + "=" * 60)
    print("📝 测试 2: 生成分层提示词")
    print("=" * 60)
    
    for complexity in TaskComplexity:
        prompt = generate_prompt(schema, complexity)
        print(f"\n🏷️  {complexity.value.upper()} 版本:")
        print(f"   长度: {len(prompt)} 字符")
        print(f"   压缩比: {len(prompt) / len(schema.raw_prompt) * 100:.1f}%")
        
        # 显示前 200 字符
        preview = prompt[:200].replace("\n", " ")
        print(f"   预览: {preview}...")


def test_complexity_detection(schema: PromptSchema):
    """测试复杂度检测"""
    print("\n" + "=" * 60)
    print("📝 测试 3: 复杂度检测")
    print("=" * 60)
    
    test_queries = [
        # Simple
        ("今天天气怎么样？", TaskComplexity.SIMPLE),
        ("你好", TaskComplexity.SIMPLE),
        ("什么是 AI？", TaskComplexity.SIMPLE),
        
        # Medium
        ("帮我分析一下这个市场数据", TaskComplexity.MEDIUM),
        ("生成一份销售报告", TaskComplexity.MEDIUM),
        ("对比 A 产品和 B 产品的优缺点", TaskComplexity.MEDIUM),
        
        # Complex
        ("帮我搭建一个人力资源管理系统", TaskComplexity.COMPLEX),
        ("设计一个 CRM 系统的架构", TaskComplexity.COMPLEX),
        ("构建一个包含用户、订单、商品实体的数据模型", TaskComplexity.COMPLEX),
    ]
    
    correct = 0
    total = len(test_queries)
    
    for query, expected in test_queries:
        detected, confidence = detect_complexity_with_confidence(query, schema)
        
        is_correct = detected == expected
        correct += 1 if is_correct else 0
        
        status = "✅" if is_correct else "❌"
        print(f"\n{status} 查询: \"{query}\"")
        print(f"   期望: {expected.value}, 检测: {detected.value}, 置信度: {confidence:.2f}")
    
    print(f"\n📊 准确率: {correct}/{total} ({correct/total*100:.1f}%)")


def test_end_to_end():
    """端到端测试"""
    print("\n" + "=" * 60)
    print("📝 测试 4: 端到端流程")
    print("=" * 60)
    
    # 模拟运营写的简化提示词
    raw_prompt = """
# 角色和定义
你是一个名为 "TestBot" 的 AI 助手。你专业、高效。

<absolute_prohibitions priority="highest">
  <rule id="safety">
    <title>安全规则</title>
    <content>不要输出有害内容</content>
  </rule>
</absolute_prohibitions>

<task_complexity_system>
  <complexity_levels>
    <level id="1" name="简单查询">
      <keywords>什么、查、问</keywords>
    </level>
    <level id="2" name="中等任务">
      <keywords>分析、报告、对比</keywords>
    </level>
    <level id="3" name="复杂任务">
      <keywords>搭建、设计、系统</keywords>
    </level>
  </complexity_levels>
</task_complexity_system>
"""
    
    # 1. 解析
    schema = parse_prompt(raw_prompt)
    print(f"✅ 解析完成: {schema.agent_name}")
    
    # 2. 模拟用户查询
    queries = [
        "什么是机器学习？",
        "分析一下销售数据",
        "帮我搭建一个订单管理系统",
    ]
    
    for query in queries:
        # 3. 检测复杂度
        complexity = detect_complexity(query, schema)
        
        # 4. 生成对应提示词
        prompt = generate_prompt(schema, complexity)
        
        print(f"\n📥 查询: \"{query}\"")
        print(f"   复杂度: {complexity.value}")
        print(f"   提示词长度: {len(prompt)} 字符")


def test_smart_exclusion():
    """🆕 V4.6 测试: 智能排除机制"""
    print("\n" + "=" * 60)
    print("📝 测试 5: 智能排除机制（V4.6）")
    print("=" * 60)
    
    # 读取 prompt_example.md
    prompt_file = PROJECT_ROOT / "prompts/templates/prompt_example.md"
    
    if not prompt_file.exists():
        print(f"⚠️ 文件不存在: {prompt_file}")
        return
    
    with open(prompt_file, "r", encoding="utf-8") as f:
        raw_prompt = f.read()
    
    # 模拟 AgentSchema（启用各种组件）
    from dataclasses import dataclass
    
    @dataclass
    class MockComponentConfig:
        enabled: bool = True
    
    @dataclass
    class MockAgentSchema:
        intent_analyzer: MockComponentConfig = None
        plan_manager: MockComponentConfig = None
        tool_selector: MockComponentConfig = None
        confirmation_manager: MockComponentConfig = None
        
        def __post_init__(self):
            self.intent_analyzer = MockComponentConfig(enabled=True)
            self.plan_manager = MockComponentConfig(enabled=True)
            self.tool_selector = MockComponentConfig(enabled=True)
            self.confirmation_manager = MockComponentConfig(enabled=True)
    
    # 不启用组件 vs 启用组件的对比
    print("\n📊 智能排除效果对比:")
    
    for complexity in TaskComplexity:
        # 不启用组件（每次重新解析 schema，避免状态污染）
        schema_no_exclusion = parse_prompt(raw_prompt)
        prompt_no_exclusion = generate_prompt(schema_no_exclusion, complexity, agent_schema=None)
        
        # 启用所有组件（每次重新解析 schema）
        schema_with_exclusion = parse_prompt(raw_prompt)
        mock_schema = MockAgentSchema()
        prompt_with_exclusion = generate_prompt(schema_with_exclusion, complexity, agent_schema=mock_schema)
        
        savings = len(prompt_no_exclusion) - len(prompt_with_exclusion)
        savings_pct = savings / len(prompt_no_exclusion) * 100 if len(prompt_no_exclusion) > 0 else 0
        
        print(f"\n🏷️  {complexity.value.upper()}:")
        print(f"   无排除: {len(prompt_no_exclusion):,} 字符")
        print(f"   智能排除: {len(prompt_with_exclusion):,} 字符")
        print(f"   节省: {savings:,} 字符 ({savings_pct:.1f}%)")
    
    # 显示排除的模块
    print(f"\n📦 排除的模块（框架组件已处理）:")
    for module in schema_with_exclusion.excluded_modules:
        print(f"   • {module.value}")


if __name__ == "__main__":
    # 测试 1: 解析
    schema = test_parse_prompt()
    
    if schema:
        # 测试 2: 生成
        test_generate_prompts(schema)
        
        # 测试 3: 检测
        test_complexity_detection(schema)
    
    # 测试 4: 端到端
    test_end_to_end()
    
    # 🆕 测试 5: 智能排除机制
    test_smart_exclusion()
    
    print("\n" + "=" * 60)
    print("🎉 所有测试完成")
    print("=" * 60)
