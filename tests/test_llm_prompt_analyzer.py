"""
测试 LLM 驱动的提示词分析器

🆕 V4.6.1: 验证 LLM 语义分析能力
- 不依赖特定格式
- 理解内容语义
- 支持任意格式的提示词
"""

import sys
import asyncio
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def test_llm_analyzer_with_structured_prompt():
    """测试 1: 分析结构化的提示词（XML/Markdown 混合）"""
    print("\n" + "=" * 60)
    print("📝 测试 1: LLM 分析结构化提示词")
    print("=" * 60)
    
    # 读取 prompt_example.md
    prompt_file = PROJECT_ROOT / "prompts/templates/prompt_example.md"
    
    if not prompt_file.exists():
        print(f"⚠️ 文件不存在: {prompt_file}")
        return
    
    with open(prompt_file, "r", encoding="utf-8") as f:
        raw_prompt = f.read()
    
    print(f"📄 提示词长度: {len(raw_prompt)} 字符")
    
    # 使用 LLM 分析
    from core.prompt import parse_prompt
    schema = parse_prompt(raw_prompt, use_llm=True)
    
    print(f"\n✅ 分析结果:")
    print(f"   Agent 名称: {schema.agent_name}")
    print(f"   Agent 角色: {schema.agent_role[:80]}...")
    print(f"   识别模块数: {len(schema.modules)}")
    print(f"   工具列表: {schema.tools[:5]}...")
    
    print(f"\n📦 识别的模块:")
    for module, content in schema.modules.items():
        print(f"   • {module.value}: {len(content.content)} 字符")


def test_llm_analyzer_with_plain_text():
    """测试 2: 分析纯文本格式的提示词（无标签）"""
    print("\n" + "=" * 60)
    print("📝 测试 2: LLM 分析纯文本提示词（无标签）")
    print("=" * 60)
    
    # 纯文本格式的提示词（运营可能这样写）
    plain_prompt = """
你是一个名为"小助手"的 AI 助手，你的主要职责是帮助用户解决问题。

你的性格：
- 友好、耐心
- 专业、高效
- 善于倾听用户需求

你绝对不能做的事情：
1. 输出任何有害内容
2. 泄露用户隐私
3. 编造虚假信息

当用户提问时，你需要先判断问题类型：
- 简单问题：直接回答，比如"今天天气怎么样"
- 复杂问题：需要多步骤分析，比如"帮我写一份项目报告"
- 危险操作：需要用户确认，比如"删除所有文件"

你可以使用的工具：
- 搜索工具：查找信息
- 计算器：数学运算
- 日历：时间管理

回答时请保持简洁、专业的风格。
"""
    
    print(f"📄 提示词长度: {len(plain_prompt)} 字符")
    print(f"📝 格式: 纯文本（无 XML 标签、无 Markdown 标题）")
    
    # 使用 LLM 分析
    from core.prompt import parse_prompt
    schema = parse_prompt(plain_prompt, use_llm=True)
    
    print(f"\n✅ 分析结果:")
    print(f"   Agent 名称: {schema.agent_name}")
    print(f"   Agent 角色: {schema.agent_role[:80]}...")
    print(f"   识别模块数: {len(schema.modules)}")
    print(f"   工具列表: {schema.tools}")
    
    print(f"\n📦 识别的模块:")
    for module, content in schema.modules.items():
        print(f"   • {module.value}")


def test_llm_analyzer_with_conversational_style():
    """测试 3: 分析对话风格的提示词"""
    print("\n" + "=" * 60)
    print("📝 测试 3: LLM 分析对话风格提示词")
    print("=" * 60)
    
    # 对话风格的提示词（运营可能这样写）
    conversational_prompt = """
嗨，你现在是"客服小蜜"，一个友好的电商客服助手。

你要做什么呢？主要是帮用户查订单、处理退货、回答产品问题。

有几件事你千万别做：
- 别骂人
- 别乱承诺打折
- 别泄露其他用户的信息

用户问你东西的时候，先想想他是想干嘛：
查订单的话就用订单查询工具，
退货的话要走退货流程，
问产品的话就去搜索产品知识库。

对了，你手里有这些工具可以用：
1. 订单查询
2. 退货申请
3. 产品知识库
4. 人工客服转接

回答的时候要像朋友聊天一样，别太官腔。
"""
    
    print(f"📄 提示词长度: {len(conversational_prompt)} 字符")
    print(f"📝 格式: 口语化、对话风格")
    
    # 使用 LLM 分析
    from core.prompt import parse_prompt
    schema = parse_prompt(conversational_prompt, use_llm=True)
    
    print(f"\n✅ 分析结果:")
    print(f"   Agent 名称: {schema.agent_name}")
    print(f"   Agent 角色: {schema.agent_role[:80]}...")
    print(f"   识别模块数: {len(schema.modules)}")
    print(f"   工具列表: {schema.tools}")
    
    print(f"\n📦 识别的模块:")
    for module, content in schema.modules.items():
        print(f"   • {module.value}")


def test_comparison_llm_vs_regex():
    """测试 4: 对比 LLM 分析 vs 正则匹配"""
    print("\n" + "=" * 60)
    print("📝 测试 4: LLM 分析 vs 正则匹配对比")
    print("=" * 60)
    
    # 读取结构化提示词
    prompt_file = PROJECT_ROOT / "prompts/templates/prompt_example.md"
    
    if not prompt_file.exists():
        print(f"⚠️ 文件不存在: {prompt_file}")
        return
    
    with open(prompt_file, "r", encoding="utf-8") as f:
        raw_prompt = f.read()
    
    from core.prompt import parse_prompt
    
    # LLM 分析
    print("\n🧠 使用 LLM 语义分析...")
    schema_llm = parse_prompt(raw_prompt, use_llm=True)
    
    # 正则匹配
    print("\n📜 使用正则匹配...")
    schema_regex = parse_prompt(raw_prompt, use_llm=False)
    
    print(f"\n📊 对比结果:")
    print(f"{'指标':<20} {'LLM 分析':<15} {'正则匹配':<15}")
    print("-" * 50)
    print(f"{'Agent 名称':<20} {schema_llm.agent_name:<15} {schema_regex.agent_name:<15}")
    print(f"{'识别模块数':<20} {len(schema_llm.modules):<15} {len(schema_regex.modules):<15}")
    print(f"{'工具数量':<20} {len(schema_llm.tools):<15} {len(schema_regex.tools):<15}")
    
    # 模块对比
    llm_modules = set(m.value for m in schema_llm.modules.keys())
    regex_modules = set(m.value for m in schema_regex.modules.keys())
    
    print(f"\n📦 模块对比:")
    print(f"   LLM 独有: {llm_modules - regex_modules}")
    print(f"   正则独有: {regex_modules - llm_modules}")
    print(f"   共同识别: {llm_modules & regex_modules}")


async def test_async_llm_analyzer():
    """测试 5: 异步 LLM 分析"""
    print("\n" + "=" * 60)
    print("📝 测试 5: 异步 LLM 分析")
    print("=" * 60)
    
    from core.prompt import analyze_prompt_with_llm
    
    simple_prompt = """
你是一个代码助手，帮助用户写代码。
不要输出有害代码。
可以使用代码执行工具。
"""
    
    print(f"📄 提示词长度: {len(simple_prompt)} 字符")
    
    # 异步分析
    result = await analyze_prompt_with_llm(simple_prompt)
    
    print(f"\n✅ 异步分析结果:")
    print(f"   Agent 名称: {result.agent_name}")
    print(f"   识别模块数: {sum(1 for m in result.modules.values() if m.found)}")
    print(f"   工具列表: {result.tools}")


if __name__ == "__main__":
    import os
    
    # 检查 API Key
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("❌ 请设置 ANTHROPIC_API_KEY 环境变量")
        print("   export ANTHROPIC_API_KEY=your-api-key")
        sys.exit(1)
    
    # 测试 1: 结构化提示词
    test_llm_analyzer_with_structured_prompt()
    
    # 测试 2: 纯文本提示词
    test_llm_analyzer_with_plain_text()
    
    # 测试 3: 对话风格提示词
    test_llm_analyzer_with_conversational_style()
    
    # 测试 4: LLM vs 正则对比
    test_comparison_llm_vs_regex()
    
    # 测试 5: 异步分析
    asyncio.run(test_async_llm_analyzer())
    
    print("\n" + "=" * 60)
    print("🎉 所有测试完成")
    print("=" * 60)
