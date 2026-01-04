"""
测试新架构模块

验证：
1. core/agent/ - Agent 模块导入
2. core/tool/ - Tool 模块导入
3. core/context/ - Context 模块导入
4. 基本功能验证
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_imports():
    """测试所有新模块的导入"""
    print("=" * 60)
    print("🧪 测试模块导入")
    print("=" * 60)
    
    errors = []
    
    # 1. 测试 core.agent 导入
    print("\n📦 测试 core.agent...")
    try:
        from core.agent import (
            TaskType,
            Complexity,
            PromptLevel,
            IntentResult,
            ExecutionConfig,
            IntentAnalyzer,
            create_intent_analyzer,
            SimpleAgent,
            create_simple_agent,
        )
        print("  ✅ core.agent 导入成功")
        print(f"     - TaskType: {TaskType}")
        print(f"     - IntentAnalyzer: {IntentAnalyzer}")
        print(f"     - SimpleAgent: {SimpleAgent}")
    except Exception as e:
        errors.append(f"core.agent: {e}")
        print(f"  ❌ core.agent 导入失败: {e}")
    
    # 2. 测试 core.tool 导入
    print("\n📦 测试 core.tool...")
    try:
        from core.tool import (
            ToolSelector,
            ToolSelectionResult,
            create_tool_selector,
            ToolExecutor,
            create_tool_executor,
        )
        print("  ✅ core.tool 导入成功")
        print(f"     - ToolSelector: {ToolSelector}")
        print(f"     - ToolExecutor: {ToolExecutor}")
    except Exception as e:
        errors.append(f"core.tool: {e}")
        print(f"  ❌ core.tool 导入失败: {e}")
    
    # 3. 测试 core.context 导入
    print("\n📦 测试 core.context...")
    try:
        from core.context import (
            Context,
            create_context,
            RuntimeContext,
            create_runtime_context,
        )
        print("  ✅ core.context 导入成功")
        print(f"     - Context: {Context}")
        print(f"     - RuntimeContext: {RuntimeContext}")
    except Exception as e:
        errors.append(f"core.context: {e}")
        print(f"  ❌ core.context 导入失败: {e}")
    
    # 4. 测试向后兼容导入（tools）
    print("\n📦 测试 tools 向后兼容导入...")
    try:
        from tools import (
            ToolSelector as ToolSelector2,
            ToolExecutor as ToolExecutor2,
        )
        print("  ✅ tools 向后兼容导入成功")
    except Exception as e:
        errors.append(f"tools (backward compat): {e}")
        print(f"  ❌ tools 向后兼容导入失败: {e}")
    
    return errors


def test_types():
    """测试类型定义"""
    print("\n" + "=" * 60)
    print("🧪 测试类型定义")
    print("=" * 60)
    
    from core.agent.types import (
        TaskType,
        Complexity,
        PromptLevel,
        IntentResult,
        ExecutionConfig,
    )
    
    # 测试枚举
    print("\n📋 TaskType 枚举:")
    for t in TaskType:
        print(f"     - {t.name}: {t.value}")
    
    print("\n📋 Complexity 枚举:")
    for c in Complexity:
        print(f"     - {c.name}: {c.value}")
    
    # 测试 IntentResult
    print("\n📋 IntentResult 数据类:")
    result = IntentResult(
        task_type=TaskType.CODE_DEVELOPMENT,
        complexity=Complexity.MEDIUM,
        needs_plan=True,
        prompt_level=PromptLevel.STANDARD,
        keywords=["代码", "开发"],
        confidence=0.9
    )
    print(f"     {result}")
    print(f"     to_dict: {result.to_dict()}")
    
    print("  ✅ 类型定义测试通过")


def test_runtime_context():
    """测试 RuntimeContext"""
    print("\n" + "=" * 60)
    print("🧪 测试 RuntimeContext")
    print("=" * 60)
    
    from core.context.runtime import RuntimeContext, create_runtime_context, BlockState
    
    # 创建上下文
    ctx = create_runtime_context(session_id="test_session", max_turns=10)
    print(f"\n📋 创建 RuntimeContext:")
    print(f"     session_id: {ctx.session_id}")
    print(f"     max_turns: {ctx.max_turns}")
    
    # 测试 BlockState
    print("\n📋 测试 BlockState:")
    block = ctx.block
    
    # 开始 thinking block
    idx1 = block.start_new_block("thinking")
    print(f"     开始 thinking block: index={idx1}")
    assert block.current_type == "thinking"
    assert block.is_block_open() == True
    
    # 检查是否需要切换
    print(f"     需要切换到 text? {block.needs_transition('text')}")
    
    # 关闭 thinking block
    closed = block.close_current_block()
    print(f"     关闭 block: {closed}")
    assert block.is_block_open() == False
    
    # 开始 text block
    idx2 = block.start_new_block("text")
    print(f"     开始 text block: index={idx2}")
    assert idx2 == 1  # 索引递增
    
    # 测试 StreamAccumulator
    print("\n📋 测试 StreamAccumulator:")
    ctx.stream.append_thinking("这是思考内容")
    ctx.stream.append_content("这是输出内容")
    print(f"     thinking: {ctx.stream.thinking}")
    print(f"     content: {ctx.stream.content}")
    
    # 测试 summary
    print("\n📋 RuntimeContext summary:")
    summary = ctx.summary()
    for k, v in summary.items():
        print(f"     {k}: {v}")
    
    print("  ✅ RuntimeContext 测试通过")


def test_tool_selector():
    """测试 ToolSelector"""
    print("\n" + "=" * 60)
    print("🧪 测试 ToolSelector")
    print("=" * 60)
    
    from core.tool import create_tool_selector
    
    # 创建选择器
    selector = create_tool_selector()
    print("\n📋 创建 ToolSelector 成功")
    
    # 测试工具选择
    print("\n📋 测试工具选择 (web_search):")
    result = selector.select(
        required_capabilities=["web_search"],
        context={"task_type": "information_query"}
    )
    print(f"     工具数量: {len(result.tools)}")
    print(f"     工具名称: {result.tool_names[:5]}...")  # 只显示前5个
    print(f"     基础工具: {result.base_tools}")
    print(f"     动态工具: {result.dynamic_tools}")
    
    print("  ✅ ToolSelector 测试通过")


def test_tool_executor():
    """测试 ToolExecutor"""
    print("\n" + "=" * 60)
    print("🧪 测试 ToolExecutor")
    print("=" * 60)
    
    from core.tool import create_tool_executor
    
    # 创建执行器
    executor = create_tool_executor()
    print("\n📋 创建 ToolExecutor 成功")
    
    # 获取可用工具
    tools = executor.get_available_tools()
    print(f"\n📋 可用工具数量: {len(tools)}")
    
    # 显示前5个工具
    for i, (name, info) in enumerate(list(tools.items())[:5]):
        status = "✅" if info.get('loaded') else "⚠️"
        print(f"     {status} {name} ({info['provider']})")
    
    print("  ✅ ToolExecutor 测试通过")


async def test_intent_analyzer():
    """测试 IntentAnalyzer"""
    print("\n" + "=" * 60)
    print("🧪 测试 IntentAnalyzer (规则模式)")
    print("=" * 60)
    
    from core.agent import create_intent_analyzer
    
    # 创建分析器（不使用 LLM）
    analyzer = create_intent_analyzer(llm_service=None, enable_llm=False)
    print("\n📋 创建 IntentAnalyzer 成功（规则模式）")
    
    # 测试用例
    test_cases = [
        "帮我搜索一下 Python 的最新版本",
        "生成一个关于 AI 的 PPT",
        "写一个 Python 脚本",
        "你好，今天天气怎么样？",
    ]
    
    print("\n📋 意图分析测试:")
    for user_input in test_cases:
        result = await analyzer.analyze(user_input)
        print(f"\n     输入: {user_input}")
        print(f"     类型: {result.task_type.value}")
        print(f"     复杂度: {result.complexity.value}")
        print(f"     需要规划: {result.needs_plan}")
        print(f"     提示词级别: {result.prompt_level.value}")
    
    print("\n  ✅ IntentAnalyzer 测试通过")


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("🚀 新架构模块测试")
    print("=" * 60)
    
    # 1. 测试导入
    errors = test_imports()
    
    if errors:
        print("\n" + "=" * 60)
        print("❌ 导入测试失败，无法继续")
        print("=" * 60)
        for err in errors:
            print(f"  - {err}")
        return 1
    
    # 2. 测试类型
    test_types()
    
    # 3. 测试 RuntimeContext
    test_runtime_context()
    
    # 4. 测试 ToolSelector
    test_tool_selector()
    
    # 5. 测试 ToolExecutor
    test_tool_executor()
    
    # 6. 测试 IntentAnalyzer
    asyncio.run(test_intent_analyzer())
    
    print("\n" + "=" * 60)
    print("✅ 所有测试通过！")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    exit(main())

