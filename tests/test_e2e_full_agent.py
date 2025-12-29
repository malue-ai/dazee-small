"""
真正的端到端测试 - 完整 Agent 流程

严格按照架构图：
User Query → Intent LLM → Plan → Router → RVR Loop → Output

验证：
1. 从用户输入开始
2. 走完整个 Agent 流程
3. LLM 主动发现 E2B 工具
4. 返回 Vibe Coding 预览 URL

运行：python tests/test_e2e_full_agent.py
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from logger import get_logger
from dotenv import load_dotenv

logger = get_logger("e2e_test")

# 加载环境变量
load_dotenv(Path(__file__).parent.parent.parent / ".env", override=True)


# 简单的 EventStorage 实现（用于测试）
class SimpleEventStorage:
    """简单的事件存储（内存）- 实现完整的 EventStorage Protocol"""
    
    def __init__(self):
        self.events = {}
        self.seq_counters = {}
        self.contexts = {}
    
    def generate_session_seq(self, session_id: str) -> int:
        """生成 session 内的事件序号"""
        if session_id not in self.seq_counters:
            self.seq_counters[session_id] = 0
        self.seq_counters[session_id] += 1
        return self.seq_counters[session_id]
    
    def get_session_context(self, session_id: str) -> dict:
        """获取 session 上下文"""
        return self.contexts.get(session_id, {})
    
    def buffer_event(self, session_id: str, event_data: dict) -> None:
        """缓冲事件"""
        if session_id not in self.events:
            self.events[session_id] = []
        self.events[session_id].append(event_data)
    
    def update_heartbeat(self, session_id: str) -> None:
        """更新心跳"""
        pass  # 测试中不需要实现


async def test_full_agent_e2e():
    """完整的端到端测试"""
    
    logger.info("="*70)
    logger.info("🧪 端到端测试 - 完整 Agent 流程")
    logger.info("="*70)
    logger.info("\n架构流程:")
    logger.info("  User Query → Intent LLM → Plan → Router → RVR → Output")
    logger.info("")
    
    # 验证环境
    e2b_key = os.getenv("E2B_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    
    if not e2b_key or not anthropic_key:
        logger.error("❌ API Keys 未设置")
        sys.exit(1)
    
    logger.info(f"✅ E2B_API_KEY: {e2b_key[:15]}...")
    logger.info(f"✅ ANTHROPIC_API_KEY: {anthropic_key[:15]}...")
    
    # 创建 Agent
    from core import create_simple_agent, create_event_manager
    
    # 创建简单的 EventStorage
    storage = SimpleEventStorage()
    event_manager = create_event_manager(storage)
    
    agent = create_simple_agent(
        workspace_dir=str(Path.cwd() / "workspace"),
        event_manager=event_manager
    )
    
    logger.info("\n✅ Agent 已创建（V3.7 + E2B + Vibe Coding）")
    
    # 用户输入（Vibe Coding 场景）
    user_input = """
帮我创建一个数据可视化应用，要求：
1. 生成随机的销售数据
2. 显示交互式图表（用户可以调整参数）
3. 计算统计指标
4. 支持多种图表类型切换

我想要一个完整可用的应用，不是代码片段。
"""
    
    logger.info("\n" + "="*70)
    logger.info("📝 用户输入（Vibe Coding 场景）")
    logger.info("="*70)
    logger.info(user_input)
    
    logger.info("\n" + "-"*70)
    logger.info("开始执行 Agent...观察完整流程")
    logger.info("-"*70)
    
    # 收集关键信息
    intent_result = None
    plan_result = None
    tool_selections = []
    tool_calls = []
    preview_url = None
    
    # 执行 Agent（非流式模式，重试机制更可靠）
    async for event in agent.chat(
        user_input=user_input,
        session_id="e2e_vibe_test",
        enable_stream=False  # 🆕 非流式模式，重试机制生效
    ):
        event_type = event.get("type")
        data = event.get("data", {})
        
        # 1. Intent Analysis
        if event_type == "intent_analysis":
            intent_result = data
            logger.info(f"\n✅ 1️⃣ Intent Analysis (Haiku):")
            logger.info(f"  任务类型: {data.get('task_type')}")
            logger.info(f"  复杂度: {data.get('complexity')}")
            logger.info(f"  需要计划: {data.get('needs_plan')}")
        
        # 2. Tool Selection
        elif event_type == "tool_selection":
            tool_selections = data.get('selected_tools', [])
            logger.info(f"\n✅ 2️⃣ Router (能力映射):")
            logger.info(f"  需要能力: {data.get('required_capabilities')}")
            logger.info(f"  选择工具: {tool_selections}")
            
            # 🎯 验证：是否选择了 E2B 相关工具
            if 'e2b_vibe_coding' in tool_selections:
                logger.info(f"\n  🎯 LLM 主动发现了 Vibe Coding 工具！")
            elif 'e2b_python_sandbox' in tool_selections:
                logger.info(f"\n  🎯 LLM 主动发现了 E2B 沙箱工具！")
        
        # 3. Plan Update  
        elif event_type == "plan_update":
            plan_result = data.get('plan')
            if plan_result and not tool_selections:  # 首次创建Plan
                logger.info(f"\n✅ 3️⃣ Plan Creation (Sonnet):")
                for i, step in enumerate(plan_result.get('steps', []), 1):
                    logger.info(f"  {i}. {step.get('action')}")
                    if step.get('capability'):
                        logger.info(f"     capability: {step.get('capability')}")
        
        # 4. Tool Call
        elif event_type == "tool_call_start":
            tool_name = data.get('tool_name')
            tool_calls.append(tool_name)
            logger.info(f"\n✅ 4️⃣ 工具调用: {tool_name}")
            
            # 如果是 vibe_coding，提取预览URL
            if tool_name == "e2b_vibe_coding":
                tool_input = data.get('input', {})
                logger.info(f"  操作: {tool_input.get('action')}")
                logger.info(f"  技术栈: {tool_input.get('stack')}")
        
        # 5. Tool Complete
        elif event_type == "tool_call_complete":
            tool_name = data.get('tool_name')
            result = data.get('result') or {}  # 安全处理 None
            
            # 提取预览 URL
            if tool_name == "e2b_vibe_coding" and result.get('preview_url'):
                preview_url = result['preview_url']
                logger.info(f"\n✅ 5️⃣ Vibe Coding 结果:")
                logger.info(f"  🔗 预览 URL: {preview_url}")
        
        # 6. Complete
        elif event_type == "complete":
            logger.info(f"\n✅ 6️⃣ 任务完成")
            logger.info(f"  轮次: {data.get('turns')}")
    
    # 验证结果
    logger.info("\n" + "="*70)
    logger.info("🔍 端到端流程验证")
    logger.info("="*70)
    
    checks = []
    
    # 验证 1: Intent Analysis
    if intent_result:
        logger.info("✅ Intent Analysis: 已执行")
        checks.append(True)
    else:
        logger.error("❌ Intent Analysis: 未执行")
        checks.append(False)
    
    # 验证 2: Plan Creation
    if plan_result:
        logger.info("✅ Plan Creation: 已执行")
        checks.append(True)
    else:
        logger.error("❌ Plan Creation: 未执行")
        checks.append(False)
    
    # 验证 3: Router
    if tool_selections:
        logger.info(f"✅ Router: 已执行（筛选了 {len(tool_selections)} 个工具）")
        checks.append(True)
    else:
        logger.error("❌ Router: 未执行")
        checks.append(False)
    
    # 验证 4: LLM 主动发现 E2B
    e2b_tools_used = [t for t in tool_calls if 'e2b' in t]
    if e2b_tools_used:
        logger.info(f"✅ LLM 主动发现: {e2b_tools_used}")
        checks.append(True)
    else:
        logger.warning("⚠️ LLM 未使用 E2B 工具")
        checks.append(False)
    
    # 验证 5: Vibe Coding 输出
    if preview_url:
        logger.info(f"✅ Vibe Coding: {preview_url}")
        checks.append(True)
    else:
        logger.warning("⚠️ 未生成预览 URL")
        checks.append(False)
    
    # 总结
    success_rate = sum(checks) / len(checks)
    logger.info(f"\n成功率: {success_rate*100:.0f}% ({sum(checks)}/{len(checks)})")
    
    if success_rate == 1.0:
        logger.info("\n" + "="*70)
        logger.info("🎉 端到端测试完全成功！")
        logger.info("="*70)
        logger.info("\n验证内容:")
        logger.info("  ✅ 完整架构流程（User Query → Output）")
        logger.info("  ✅ Intent Analysis (Haiku)")
        logger.info("  ✅ Plan Creation (Sonnet)")
        logger.info("  ✅ Router 能力映射")
        logger.info("  ✅ LLM 主动发现 E2B")
        logger.info("  ✅ Vibe Coding 预览 URL")
        logger.info(f"\n🔗 应用访问: {preview_url}")
        logger.info("\n✅ 架构验证成功！可以更新架构文档")
        return True
    else:
        logger.warning("\n⚠️ 部分流程未通过，需要调试")
        return False


if __name__ == "__main__":
    try:
        success = asyncio.run(test_full_agent_e2e())
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"\n❌ 测试异常: {e}", exc_info=True)
        sys.exit(1)

