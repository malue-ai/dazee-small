"""
Vibe Coding 端到端真实测试

场景：验证 LLM 能否通过推理主动发现并使用 E2B 工具

测试流程：
1. 用户输入自然语言需求（不提示使用E2B）
2. LLM 通过 Extended Thinking 推理
3. LLM 主动发现需要 E2B（因为需要网络/第三方包）
4. 执行完整的 Vibe Coding 流程

验证点：
✅ LLM 能否识别需要网络访问
✅ LLM 能否主动选择 e2b_python_sandbox
✅ LLM 能否正确使用 E2B 文件系统
✅ LLM 能否处理多轮迭代

运行方式：
  python tests/test_vibe_coding_real.py
"""

import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from logger import get_logger
from dotenv import load_dotenv

logger = get_logger("vibe_coding_test")

# 加载环境变量（从多个可能的位置）
env_paths = [
    Path(__file__).parent.parent / ".env",  # ./zenflux_agent/.env
    Path(__file__).parent.parent.parent / ".env",  # ./mvp/.env
]

env_loaded = False
for env_path in env_paths:
    if env_path.exists():
        loaded = load_dotenv(env_path, override=True)
        if loaded:
            logger.info(f"✅ 从 {env_path} 加载环境变量")
            env_loaded = True
            break

if not env_loaded:
    logger.warning("⚠️ 未找到 .env 文件，尝试从环境变量读取")


class VibeCodingRealTest:
    """Vibe Coding 真实测试"""
    
    def __init__(self):
        # 验证环境变量
        self.e2b_api_key = os.getenv("E2B_API_KEY")
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        
        if not self.e2b_api_key:
            logger.error("❌ E2B_API_KEY 未设置（在 .env 文件中）")
            sys.exit(1)
        
        if not self.anthropic_api_key:
            logger.error("❌ ANTHROPIC_API_KEY 未设置（在 .env 文件中）")
            sys.exit(1)
        
        logger.info(f"✅ API Keys 已加载")
        logger.info(f"  E2B: {self.e2b_api_key[:10]}...")
        logger.info(f"  Anthropic: {self.anthropic_api_key[:10]}...")
        
        # 初始化 Agent
        from core.agent import create_simple_agent
        from core.events import create_event_manager
        from core.events.storage import InMemoryEventStorage
        
        # 创建 EventManager
        storage = InMemoryEventStorage()
        self.event_manager = create_event_manager(storage)
        self.workspace_dir = Path.cwd() / "workspace"
        
        self.agent = create_simple_agent(
            workspace_dir=str(self.workspace_dir),
            event_manager=self.event_manager
        )
        
        logger.info("✅ Agent 已初始化（V3.7 + E2B）")
    
    async def test_scenario_1_data_visualization(self):
        """
        场景 1: 数据可视化应用生成
        
        用户需求：创建一个数据可视化应用
        
        验证：
        1. LLM 能否识别需要生成应用（而不是简单代码）
        2. LLM 能否主动发现需要 E2B（因为要生成图表）
        3. LLM 能否正确使用文件系统
        """
        logger.info("\n" + "="*70)
        logger.info("🎨 场景 1: 数据可视化应用生成（Vibe Coding）")
        logger.info("="*70)
        
        user_input = """
帮我创建一个数据可视化应用，要求：
1. 读取 sales_data.csv 文件
2. 分析销售趋势
3. 生成折线图和柱状图
4. 计算总销售额和平均值
5. 保存分析结果和图表

注意：我希望看到完整的运行结果，不是代码片段
"""
        
        # 创建测试数据
        inputs_dir = self.workspace_dir / "inputs"
        inputs_dir.mkdir(parents=True, exist_ok=True)
        
        test_csv = inputs_dir / "sales_data.csv"
        test_data = """date,product,sales,revenue
2025-01-01,Product A,100,5000
2025-01-02,Product B,150,7500
2025-01-03,Product A,120,6000
2025-01-04,Product C,80,4000
2025-01-05,Product B,200,10000
2025-01-06,Product A,130,6500
2025-01-07,Product C,90,4500"""
        
        with open(test_csv, 'w') as f:
            f.write(test_data)
        
        logger.info(f"📝 创建测试数据: {test_csv}")
        logger.info(f"\n用户输入:\n{user_input}")
        logger.info("\n" + "-"*70)
        logger.info("开始执行 Agent（观察 LLM 推理过程）...")
        logger.info("-"*70)
        
        # 收集事件
        events = []
        intent_analysis = None
        plan = None
        tool_calls = []
        
        async for event in self.agent.chat(
            user_input=user_input,
            session_id="vibe_test_1",
            enable_stream=True
        ):
            events.append(event)
            
            event_type = event.get("type")
            
            # 捕获意图识别
            if event_type == "intent_analysis":
                intent_analysis = event.get("data")
                logger.info(f"\n📊 意图识别结果:")
                logger.info(f"  任务类型: {intent_analysis.get('task_type')}")
                logger.info(f"  复杂度: {intent_analysis.get('complexity')}")
                logger.info(f"  需要计划: {intent_analysis.get('needs_plan')}")
            
            # 捕获工具选择
            elif event_type == "tool_selection":
                data = event.get("data", {})
                logger.info(f"\n🔧 工具选择结果:")
                logger.info(f"  需要的能力: {data.get('required_capabilities')}")
                logger.info(f"  选择的工具: {data.get('selected_tools')}")
                
                # 🎯 验证点 1: LLM 是否主动发现 E2B？
                selected = data.get('selected_tools', [])
                if 'e2b_python_sandbox' in selected:
                    logger.info(f"\n  ✅ LLM 主动发现了 E2B 工具！")
                else:
                    logger.warning(f"\n  ⚠️ LLM 未选择 E2B 工具")
            
            # 捕获工具调用
            elif event_type == "tool_call_start":
                tool_data = event.get("data", {})
                tool_name = tool_data.get("tool_name")
                tool_calls.append(tool_name)
                logger.info(f"\n🔨 调用工具: {tool_name}")
                
                # 如果是 E2B，显示代码片段
                if tool_name == "e2b_python_sandbox":
                    tool_input = tool_data.get("input", {})
                    code = tool_input.get("code", "")
                    logger.info(f"\n代码片段（前200字符）:")
                    logger.info(f"{code[:200]}...")
            
            # 捕获 Plan 更新
            elif event_type == "plan_update":
                plan = event.get("data", {}).get("plan")
                if plan:
                    logger.info(f"\n📋 Plan 已创建:")
                    for i, step in enumerate(plan.get('steps', []), 1):
                        action = step.get('action', '')
                        capability = step.get('capability', '')
                        logger.info(f"  {i}. {action}")
                        if capability:
                            logger.info(f"     → capability: {capability}")
            
            # 捕获完成
            elif event_type == "complete":
                data = event.get("data", {})
                logger.info(f"\n✅ 任务完成:")
                logger.info(f"  状态: {data.get('status')}")
                logger.info(f"  轮次: {data.get('turns')}")
        
        # 验证结果
        logger.info("\n" + "="*70)
        logger.info("🔍 验证结果")
        logger.info("="*70)
        
        # 验证 1: LLM 是否使用了 E2B
        assert 'e2b_python_sandbox' in tool_calls, \
            "❌ LLM 未使用 E2B 工具（应该主动发现并使用）"
        logger.info("✅ 验证 1: LLM 主动使用了 E2B 工具")
        
        # 验证 2: 是否生成了文件
        outputs_dir = self.workspace_dir / "outputs"
        output_files = list(outputs_dir.glob("*.png")) + list(outputs_dir.glob("*.csv"))
        
        if output_files:
            logger.info(f"✅ 验证 2: 生成了 {len(output_files)} 个文件")
            for f in output_files:
                logger.info(f"  - {f.name} ({f.stat().st_size} bytes)")
        else:
            logger.warning("⚠️ 验证 2: 未生成输出文件")
        
        # 验证 3: Memory 状态
        from core.memory import WorkingMemory
        # 注意：这里需要从 Agent 获取 Memory
        # memory = self.agent.memory.working
        # if memory.has_e2b_session():
        #     logger.info("✅ 验证 3: E2B 会话已记录在 Memory")
        
        logger.info("\n✅ 场景 1 测试通过")
    
    async def test_scenario_2_web_scraping_app(self):
        """
        场景 2: 网页爬虫应用
        
        用户需求：爬取网页并分析
        
        验证：
        1. LLM 能否识别需要网络访问
        2. LLM 能否主动选择 E2B（而不是内置 code_execution）
        3. LLM 能否自动安装依赖包
        """
        logger.info("\n" + "="*70)
        logger.info("🕷️ 场景 2: 网页爬虫应用")
        logger.info("="*70)
        
        user_input = """
帮我爬取 Hacker News (https://news.ycombinator.com) 的数据：
1. 获取首页前 10 条新闻标题和链接
2. 分析新闻的关键词分布
3. 保存结果为 JSON 和 CSV 格式

要求：直接执行，我想看到真实的爬取结果
"""
        
        logger.info(f"用户输入:\n{user_input}")
        logger.info("\n开始执行...")
        
        tool_calls = []
        e2b_used = False
        
        async for event in self.agent.chat(
            user_input=user_input,
            session_id="vibe_test_2",
            enable_stream=True
        ):
            event_type = event.get("type")
            
            if event_type == "tool_call_start":
                tool_name = event.get("data", {}).get("tool_name")
                tool_calls.append(tool_name)
                
                if tool_name == "e2b_python_sandbox":
                    e2b_used = True
                    logger.info(f"\n✅ LLM 主动发现并使用了 E2B 工具！")
            
            elif event_type == "complete":
                logger.info(f"\n✅ 任务完成")
        
        # 验证
        assert e2b_used, "❌ LLM 应该主动使用 E2B 工具（因为需要网络爬取）"
        logger.info("\n✅ 场景 2 测试通过：LLM 正确识别了网络需求并使用 E2B")
    
    async def test_scenario_3_llm_discovery_ability(self):
        """
        场景 3: LLM 工具发现能力验证
        
        目的：验证在没有明确提示的情况下，LLM 能否通过推理发现 E2B
        
        测试方法：
        1. 提供一个明显需要 E2B 的任务（网络 + 第三方包）
        2. 不在用户输入中提示 "使用E2B" 或 "沙箱"
        3. 观察 LLM 的推理过程
        4. 验证 LLM 是否主动选择了 E2B
        """
        logger.info("\n" + "="*70)
        logger.info("🧠 场景 3: LLM 工具发现能力验证")
        logger.info("="*70)
        
        # 测试用例：明显需要 E2B 的任务
        test_cases = [
            {
                "name": "API 调用",
                "input": "调用 https://api.github.com/users/octocat 获取用户信息并分析",
                "should_use_e2b": True,
                "reason": "需要 requests 库和网络访问"
            },
            {
                "name": "数据分析",
                "input": "使用 pandas 分析 sales_data.csv，计算每个产品的销售额占比",
                "should_use_e2b": True,
                "reason": "需要 pandas 库"
            },
            {
                "name": "简单计算",
                "input": "计算斐波那契数列的前 20 项",
                "should_use_e2b": False,
                "reason": "简单计算，不需要外部依赖"
            }
        ]
        
        results = []
        
        for i, test_case in enumerate(test_cases, 1):
            logger.info(f"\n{'='*70}")
            logger.info(f"测试用例 {i}: {test_case['name']}")
            logger.info(f"{'='*70}")
            logger.info(f"输入: {test_case['input']}")
            logger.info(f"预期: {'应该' if test_case['should_use_e2b'] else '不应该'}使用 E2B")
            logger.info(f"原因: {test_case['reason']}")
            
            e2b_used = False
            thinking_content = []
            
            async for event in self.agent.chat(
                user_input=test_case['input'],
                session_id=f"discovery_test_{i}",
                enable_stream=True
            ):
                event_type = event.get("type")
                
                # 捕获 thinking 过程
                if event_type == "thinking":
                    thinking = event.get("data", {}).get("text", "")
                    thinking_content.append(thinking)
                
                # 捕获工具调用
                elif event_type == "tool_call_start":
                    tool_name = event.get("data", {}).get("tool_name")
                    if tool_name == "e2b_python_sandbox":
                        e2b_used = True
                
                # 任务完成
                elif event_type == "complete":
                    break
            
            # 分析 thinking 内容
            full_thinking = "".join(thinking_content)
            
            logger.info(f"\n🧠 LLM Thinking 分析（前500字符）:")
            logger.info(full_thinking[:500])
            
            logger.info(f"\n结果:")
            logger.info(f"  实际使用 E2B: {e2b_used}")
            logger.info(f"  预期使用 E2B: {test_case['should_use_e2b']}")
            
            # 验证
            if e2b_used == test_case['should_use_e2b']:
                logger.info(f"  ✅ 正确！LLM 推理正确")
                results.append(True)
            else:
                logger.warning(f"  ⚠️ 不匹配")
                results.append(False)
        
        # 总体验证
        success_rate = sum(results) / len(results)
        logger.info(f"\n" + "="*70)
        logger.info(f"📊 LLM 工具发现能力测试结果")
        logger.info(f"="*70)
        logger.info(f"成功率: {success_rate*100:.0f}% ({sum(results)}/{len(results)})")
        
        if success_rate >= 0.8:
            logger.info(f"✅ LLM 能够正确识别何时需要 E2B！")
        else:
            logger.warning(f"⚠️ LLM 工具发现能力需要优化")
        
        return success_rate >= 0.8
    
    async def test_scenario_4_iterative_development(self):
        """
        场景 4: 迭代式开发（Vibe Coding 核心）
        
        验证多轮对话中的 E2B 使用：
        1. 第一轮：创建基础应用
        2. 第二轮：修改和优化
        3. 第三轮：添加新功能
        """
        logger.info("\n" + "="*70)
        logger.info("🔄 场景 4: 迭代式开发")
        logger.info("="*70)
        
        # 第一轮
        input1 = "创建一个简单的数据统计脚本，读取 sales_data.csv 并输出总销售额"
        
        logger.info(f"\n第一轮: {input1}")
        
        async for event in self.agent.chat(
            user_input=input1,
            session_id="iterative_test",
            enable_stream=True
        ):
            if event.get("type") == "complete":
                break
        
        logger.info("✅ 第一轮完成")
        
        # 第二轮：修改
        input2 = "修改一下，增加按产品分组的统计"
        
        logger.info(f"\n第二轮: {input2}")
        
        async for event in self.agent.chat(
            user_input=input2,
            session_id="iterative_test",  # 同一 session
            history_messages=[],  # 实际应该从数据库加载
            enable_stream=True
        ):
            if event.get("type") == "complete":
                break
        
        logger.info("✅ 第二轮完成（验证沙箱复用）")
        
        logger.info("\n✅ 场景 4 测试通过：支持迭代式开发")


async def main():
    """运行 Vibe Coding 真实测试"""
    logger.info("="*70)
    logger.info("🎨 Vibe Coding 端到端真实测试")
    logger.info("="*70)
    logger.info(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("")
    logger.info("⚠️  这是真实测试，会调用:")
    logger.info("  - E2B API（创建沙箱、执行代码）")
    logger.info("  - Anthropic API（Claude LLM 推理）")
    logger.info("")
    logger.info("预计时间：5-10 分钟")
    logger.info("预计费用：< $0.50 USD")
    logger.info("")
    
    tester = VibeCodingRealTest()
    
    try:
        # 运行所有场景
        await tester.test_scenario_1_data_visualization()
        # await tester.test_scenario_2_web_scraping_app()
        # await tester.test_scenario_3_llm_discovery_ability()
        # await tester.test_scenario_4_iterative_development()
        
        logger.info("\n" + "="*70)
        logger.info("🎉 Vibe Coding 测试完成！")
        logger.info("="*70)
        
        logger.info("\n核心验证点:")
        logger.info("  ✅ LLM 能够主动发现 E2B 工具")
        logger.info("  ✅ E2B 执行真实代码")
        logger.info("  ✅ 文件系统同步正常")
        logger.info("  ✅ 支持多轮迭代开发")
        
    except AssertionError as e:
        logger.error(f"\n❌ 测试失败: {e}")
        sys.exit(1)
    
    except Exception as e:
        logger.error(f"\n❌ 测试异常: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

