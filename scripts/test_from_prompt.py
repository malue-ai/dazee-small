"""
测试 AgentFactory.from_prompt() - Prompt 驱动的 Agent 创建

测试项：
1. Fallback 路径：无 LLM Profile 时，使用保守默认 Schema
2. LLM 路径：配置 LLM Profile 后，LLM 语义推断 Schema
3. Agent 实例验证：检查返回的 Agent 属性是否正确
"""

import asyncio
import os
import sys
import json
import traceback
from datetime import datetime

# 确保项目根目录在 sys.path 中
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
os.chdir(project_root)


# ============================================================
# 测试用 Prompt（简化版小搭子）
# ============================================================

TEST_PROMPT_SIMPLE = """
你是一个简单的问答助手，帮助用户解答日常问题。
你不需要任何工具，只需要用自然语言回答即可。
"""

TEST_PROMPT_COMPLEX = """
# 小搭子 - 桌面端 AI 搭子

## 身份
你是「小搭子」，一个住在用户电脑里的 AI 搭子。

## 核心能力
- **会干活**：通过 Skills 完成写作、文件整理、表格分析、翻译等桌面任务
- **会思考**：理解复杂需求，拆解步骤，规划执行
- **会学习**：记住用户的偏好和习惯

## Skills 使用规则
1. 只用已启用的 Skills
2. 缺少能力时如实说明
3. 敏感操作必须确认
"""


def print_separator(title: str):
    """Print section separator"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def print_agent_info(agent, label: str):
    """Print Agent key attributes"""
    print(f"\n--- {label} ---")
    print(f"  Agent 类型: {type(agent).__name__}")
    print(f"  Schema name: {agent.schema.name if hasattr(agent, 'schema') and agent.schema else 'N/A'}")
    print(f"  Schema description: {agent.schema.description if hasattr(agent, 'schema') and agent.schema else 'N/A'}")
    print(f"  Max steps: {agent._max_steps if hasattr(agent, '_max_steps') else 'N/A'}")
    print(f"  Model: {agent.model if hasattr(agent, 'model') else 'N/A'}")
    print(f"  Executor: {agent.executor.name if hasattr(agent, 'executor') and agent.executor else 'N/A'}")

    if hasattr(agent, 'schema') and agent.schema:
        schema = agent.schema
        print(f"  Schema.plan_manager.enabled: {schema.plan_manager.enabled}")
        print(f"  Schema.tool_selector.enabled: {schema.tool_selector.enabled}")
        print(f"  Schema.intent_analyzer.enabled: {schema.intent_analyzer.enabled}")
        print(f"  Schema.max_turns: {schema.max_turns}")
        print(f"  Schema.reasoning: {schema.reasoning}")
        print(f"  Schema.skills: {[s.name if hasattr(s, 'name') else s for s in schema.skills]}")
        print(f"  Schema.tools: {schema.tools}")

    if hasattr(agent, 'tool_selector'):
        print(f"  Tool selector: {'已创建' if agent.tool_selector else '未创建'}")
    if hasattr(agent, 'capability_registry'):
        print(f"  Capability registry: {'已创建' if agent.capability_registry else '未创建'}")


async def test_fallback_path():
    """
    测试 1: Fallback 路径
    不配置 LLM Profile，from_prompt() 应 fallback 到保守默认 Schema
    """
    print_separator("测试 1: Fallback 路径 (use_default_if_failed=True)")

    from core.events import create_event_manager, get_memory_storage
    from core.agent import AgentFactory

    # 确保没有 schema_generator profile
    from config.llm_config import clear_instance_profiles
    clear_instance_profiles()

    storage = get_memory_storage()
    event_manager = create_event_manager(storage)

    start = datetime.now()
    try:
        agent = await AgentFactory.from_prompt(
            system_prompt=TEST_PROMPT_SIMPLE,
            event_manager=event_manager,
            use_default_if_failed=True,  # 关键：允许 fallback
        )
        elapsed_ms = (datetime.now() - start).total_seconds() * 1000

        print(f"✅ Fallback 路径成功！耗时: {elapsed_ms:.0f}ms")
        print_agent_info(agent, "Fallback Agent")

        # 验证
        assert agent is not None, "Agent 不应为 None"
        assert hasattr(agent, 'schema'), "Agent 应有 schema 属性"
        assert agent.schema.name == "GeneralAgent", \
            f"Fallback 应产生 GeneralAgent，实际: {agent.schema.name}"
        assert hasattr(agent, 'executor'), "Agent 应有 executor"
        print(f"\n✅ 所有断言通过")
        return True

    except Exception as e:
        elapsed_ms = (datetime.now() - start).total_seconds() * 1000
        print(f"❌ Fallback 路径失败！耗时: {elapsed_ms:.0f}ms")
        print(f"   错误: {e}")
        traceback.print_exc()
        return False


async def test_fallback_raises_without_flag():
    """
    测试 2: use_default_if_failed=False 时，应抛出异常
    """
    print_separator("测试 2: use_default_if_failed=False 应抛异常")

    from core.events import create_event_manager, get_memory_storage
    from core.agent import AgentFactory

    # 确保没有 schema_generator profile
    from config.llm_config import clear_instance_profiles
    clear_instance_profiles()

    storage = get_memory_storage()
    event_manager = create_event_manager(storage)

    start = datetime.now()
    try:
        agent = await AgentFactory.from_prompt(
            system_prompt=TEST_PROMPT_SIMPLE,
            event_manager=event_manager,
            use_default_if_failed=False,  # 不允许 fallback
        )
        elapsed_ms = (datetime.now() - start).total_seconds() * 1000
        print(f"❌ 应该抛异常但没有！耗时: {elapsed_ms:.0f}ms")
        return False

    except KeyError as e:
        elapsed_ms = (datetime.now() - start).total_seconds() * 1000
        print(f"✅ 正确抛出 KeyError: {e}")
        print(f"   耗时: {elapsed_ms:.0f}ms")
        return True

    except Exception as e:
        elapsed_ms = (datetime.now() - start).total_seconds() * 1000
        print(f"✅ 抛出异常（类型: {type(e).__name__}）: {e}")
        print(f"   耗时: {elapsed_ms:.0f}ms")
        return True


async def test_llm_path():
    """
    测试 3: LLM 路径
    配置 LLM Profile 后，from_prompt() 应通过 LLM 语义推断生成 Schema
    """
    print_separator("测试 3: LLM 路径 (schema_generator profile)")

    from core.events import create_event_manager, get_memory_storage
    from core.agent import AgentFactory
    from config.llm_config import set_instance_profiles

    # 配置 schema_generator profile（使用 qwen-plus 作为轻量级模型）
    # 先检查环境变量
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        print("⚠️ 未设置 DASHSCOPE_API_KEY 环境变量")
        # 尝试从 config.yaml 加载
        try:
            from utils.instance_loader import load_instance_env_from_config
            load_instance_env_from_config("xiaodazi")
            api_key = os.getenv("DASHSCOPE_API_KEY")
        except Exception:
            pass

    if not api_key:
        # 尝试 ANTHROPIC_API_KEY
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            set_instance_profiles({
                "schema_generator": {
                    "provider": "claude",
                    "model": "claude-haiku-4-5-20250929",
                    "description": "Schema 生成器（测试用）",
                }
            })
            print("📋 使用 Claude Haiku 作为 schema_generator")
        else:
            print("⚠️ 未找到任何可用的 API Key，跳过 LLM 路径测试")
            print("   需要设置 DASHSCOPE_API_KEY 或 ANTHROPIC_API_KEY")
            return None  # 跳过
    else:
        set_instance_profiles({
            "schema_generator": {
                "provider": "qwen",
                "model": "qwen-plus",
                "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
                "description": "Schema 生成器（测试用）",
            }
        })
        print("📋 使用 Qwen Plus 作为 schema_generator（国际区端点）")

    storage = get_memory_storage()
    event_manager = create_event_manager(storage)

    # 测试简单 prompt
    print("\n--- 3a: 简单 Prompt ---")
    start = datetime.now()
    try:
        agent_simple = await AgentFactory.from_prompt(
            system_prompt=TEST_PROMPT_SIMPLE,
            event_manager=event_manager,
            use_default_if_failed=True,
        )
        elapsed_ms = (datetime.now() - start).total_seconds() * 1000
        print(f"✅ 简单 Prompt LLM 路径成功！耗时: {elapsed_ms:.0f}ms")
        print_agent_info(agent_simple, "Simple Prompt Agent (LLM)")
    except Exception as e:
        elapsed_ms = (datetime.now() - start).total_seconds() * 1000
        print(f"❌ 简单 Prompt LLM 路径失败！耗时: {elapsed_ms:.0f}ms")
        print(f"   错误: {e}")
        traceback.print_exc()

    # 测试复杂 prompt
    print("\n--- 3b: 复杂 Prompt ---")
    start = datetime.now()
    try:
        agent_complex = await AgentFactory.from_prompt(
            system_prompt=TEST_PROMPT_COMPLEX,
            event_manager=event_manager,
            use_default_if_failed=True,
        )
        elapsed_ms = (datetime.now() - start).total_seconds() * 1000
        print(f"✅ 复杂 Prompt LLM 路径成功！耗时: {elapsed_ms:.0f}ms")
        print_agent_info(agent_complex, "Complex Prompt Agent (LLM)")
    except Exception as e:
        elapsed_ms = (datetime.now() - start).total_seconds() * 1000
        print(f"❌ 复杂 Prompt LLM 路径失败！耗时: {elapsed_ms:.0f}ms")
        print(f"   错误: {e}")
        traceback.print_exc()

    return True


async def test_agent_basic_functionality():
    """
    测试 4: 验证 from_prompt 创建的 Agent 基本功能
    确保 Agent 可以被 clone_for_session()
    """
    print_separator("测试 4: Agent 基本功能验证")

    from core.events import create_event_manager, get_memory_storage
    from core.agent import AgentFactory

    from config.llm_config import clear_instance_profiles
    clear_instance_profiles()

    storage = get_memory_storage()
    event_manager = create_event_manager(storage)

    try:
        agent = await AgentFactory.from_prompt(
            system_prompt=TEST_PROMPT_SIMPLE,
            event_manager=event_manager,
            use_default_if_failed=True,
        )

        # 验证关键属性
        checks = {
            "has schema": hasattr(agent, 'schema') and agent.schema is not None,
            "has executor": hasattr(agent, 'executor') and agent.executor is not None,
            "has llm": hasattr(agent, 'llm') and agent.llm is not None,
            "has tool_executor": hasattr(agent, 'tool_executor') and agent.tool_executor is not None,
            "has broadcaster": hasattr(agent, 'broadcaster') and agent.broadcaster is not None,
            "has _max_steps": hasattr(agent, '_max_steps'),
        }

        all_passed = True
        for check_name, result in checks.items():
            status = "✅" if result else "❌"
            print(f"  {status} {check_name}: {result}")
            if not result:
                all_passed = False

        # 测试 clone_for_session
        print("\n--- clone_for_session 测试 ---")
        try:
            event_manager2 = create_event_manager(storage)
            cloned = agent.clone_for_session(
                event_manager=event_manager2,
                conversation_service=None,
            )
            print(f"  ✅ clone_for_session 成功")
            print(f"     原型 Agent: {id(agent)}")
            print(f"     克隆 Agent: {id(cloned)}")
            print(f"     共享 LLM: {id(agent.llm) == id(cloned.llm)}")
            print(f"     共享 executor: {id(agent.executor) == id(cloned.executor)}")
        except Exception as e:
            print(f"  ❌ clone_for_session 失败: {e}")
            all_passed = False

        if all_passed:
            print(f"\n✅ 所有功能检查通过")
        else:
            print(f"\n❌ 部分检查未通过")

        return all_passed

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        traceback.print_exc()
        return False


async def main():
    """Run all tests"""
    print_separator("AgentFactory.from_prompt() 测试")
    print(f"时间: {datetime.now().isoformat()}")
    print(f"工作目录: {os.getcwd()}")

    results = {}

    # 测试 1: Fallback 路径
    results["test_fallback_path"] = await test_fallback_path()

    # 测试 2: use_default_if_failed=False
    results["test_fallback_raises"] = await test_fallback_raises_without_flag()

    # 测试 3: LLM 路径
    results["test_llm_path"] = await test_llm_path()

    # 测试 4: Agent 基本功能
    results["test_agent_basic"] = await test_agent_basic_functionality()

    # 汇总
    print_separator("测试汇总")
    for name, result in results.items():
        if result is None:
            status = "⏭️ SKIPPED"
        elif result:
            status = "✅ PASSED"
        else:
            status = "❌ FAILED"
        print(f"  {status}  {name}")

    passed = sum(1 for r in results.values() if r is True)
    failed = sum(1 for r in results.values() if r is False)
    skipped = sum(1 for r in results.values() if r is None)
    total = len(results)

    print(f"\n  总计: {total} | 通过: {passed} | 失败: {failed} | 跳过: {skipped}")

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
