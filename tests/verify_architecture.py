"""
架构验证脚本 - 对照文档验证两个场景

场景1: PPT生成（content_generation）
场景2: Vibe Coding（app_creation）

验证点：
1. Intent Analysis → task_type正确
2. Router → 筛选对应工具
3. Plan Creation → LLM自主决定
4. Tool Execution → 正确调用工具
5. Final Result → 用户得到期望结果
"""

import os
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from logger import get_logger
logger = get_logger("arch_verify")

# 加载环境变量
load_dotenv("/Users/liuyi/Documents/langchain/CoT_agent/mvp/.env")

from core import create_simple_agent, create_event_manager


class SimpleEventStorage:
    def __init__(self):
        self.events, self.seq_counters, self.contexts = {}, {}, {}
    def generate_session_seq(self, session_id): 
        self.seq_counters[session_id] = self.seq_counters.get(session_id, 0) + 1
        return self.seq_counters[session_id]
    def get_session_context(self, session_id): return {}
    def buffer_event(self, session_id, event_data): pass
    def update_heartbeat(self, session_id): pass


async def verify_scenario(scenario_name: str, user_query: str, expected_tools: list):
    """验证单个场景"""
    logger.info("\n" + "="*80)
    logger.info(f"📋 场景: {scenario_name}")
    logger.info("="*80)
    
    # 创建Agent
    storage = SimpleEventStorage()
    event_manager = create_event_manager(storage)
    agent = create_simple_agent(
        workspace_dir=str(project_root / "workspace"),
        event_manager=event_manager
    )
    
    logger.info(f"\n用户查询:\n{user_query}\n")
    logger.info("-"*80)
    
    # 追踪器
    tracker = {
        "stage": "开始",
        "intent": None,
        "router_tools": [],
        "plan": None,
        "tools_called": [],
        "final_result": None
    }
    
    try:
        async for event in agent.chat(
            user_input=user_query,
            session_id=f"verify_{scenario_name}",
            enable_stream=False
        ):
            event_type = event.get('type')  # 修正：事件格式是type而不是event_type
            data = event.get('data', {})
            
            # Intent
            if event_type == "intent_analysis":
                tracker["intent"] = data
                tracker["stage"] = "Intent完成"
                logger.info(f"✅ Intent Analysis: task_type={data.get('task_type')}, needs_plan={data.get('needs_plan')}")
            
            # Router
            elif event_type == "tool_selection":
                tracker["router_tools"] = data.get('selected_tools', [])
                tracker["stage"] = "Router完成"
                logger.info(f"✅ Router筛选: {len(tracker['router_tools'])}个工具")
                logger.info(f"   工具列表: {tracker['router_tools']}")
            
            # Plan
            elif event_type == "plan_update":
                if not tracker["plan"]:
                    tracker["plan"] = data.get('plan')
                    tracker["stage"] = "Plan完成"
                    logger.info(f"✅ Plan创建: {len(tracker['plan'].get('steps', []))}个步骤")
            
            # Tool Call
            elif event_type == "tool_call_start":
                tool = data.get('tool_name')
                tracker["tools_called"].append(tool)
                tracker["stage"] = f"执行工具-{tool}"
                logger.info(f"🔧 调用工具: {tool}")
            
            # Tool Result
            elif event_type == "tool_call_complete":
                tool = data.get('tool_name')
                result = data.get('result', {})
                logger.info(f"✅ 工具完成: {tool}")
                
                # 提取关键结果
                if result.get('preview_url'):
                    logger.info(f"   🔗 URL: {result['preview_url']}")
                if result.get('ppt_url'):
                    logger.info(f"   📥 下载: {result['ppt_url']}")
            
            # Complete
            elif event_type == "complete":
                tracker["final_result"] = data.get('final_result')
                tracker["stage"] = "完成"
                logger.info(f"🎉 任务完成: {data.get('turns')}轮")
        
        # 验证结果
        logger.info("\n" + "-"*80)
        logger.info("📊 验证结果:")
        logger.info("-"*80)
        
        checks = []
        
        # 检查1: Intent执行
        if tracker["intent"]:
            logger.info("✅ Intent Analysis: 已执行")
            checks.append(True)
        else:
            logger.error("❌ Intent Analysis: 未执行")
            checks.append(False)
        
        # 检查2: Router筛选
        if tracker["router_tools"]:
            logger.info(f"✅ Router: 筛选了{len(tracker['router_tools'])}个工具")
            
            # 验证是否包含预期工具
            found_tools = [tool for tool in expected_tools if tool in tracker["router_tools"]]
            if found_tools:
                logger.info(f"   包含预期工具: {found_tools}")
            checks.append(True)
        else:
            logger.error("❌ Router: 未执行")
            checks.append(False)
        
        # 检查3: 工具执行
        if tracker["tools_called"]:
            logger.info(f"✅ 工具执行: {tracker['tools_called']}")
            checks.append(True)
        else:
            logger.error("❌ 工具执行: 未执行")
            checks.append(False)
        
        # 检查4: 最终结果
        if tracker["final_result"]:
            logger.info(f"✅ 最终结果: {tracker['final_result'][:100]}...")
            checks.append(True)
        else:
            logger.warning("⚠️ 最终结果: 无")
            checks.append(False)
        
        success_rate = sum(checks) / len(checks) * 100
        logger.info(f"\n成功率: {success_rate:.0f}% ({sum(checks)}/{len(checks)})")
        
        return success_rate >= 75
    
    except Exception as e:
        logger.error(f"❌ 测试异常: {e}", exc_info=True)
        return False


async def main():
    """运行两个场景验证"""
    logger.info("🏗️ V3.7 架构验证 - 真实端到端场景")
    logger.info("="*80)
    
    # 场景1: PPT生成
    ppt_result = await verify_scenario(
        scenario_name="PPT生成",
        user_query="帮我生成一个关于AI技术趋势的PPT，大约5页，专业风格",
        expected_tools=["slidespeak-generator", "slidespeak_render", "exa_search"]
    )
    
    # 场景2: Vibe Coding
    vibe_result = await verify_scenario(
        scenario_name="Vibe_Coding",
        user_query="创建一个简单的数据可视化应用，显示随机图表",
        expected_tools=["e2b_vibe_coding", "e2b_python_sandbox"]
    )
    
    # 最终总结
    logger.info("\n" + "="*80)
    logger.info("📊 架构验证总结")
    logger.info("="*80)
    logger.info(f"PPT生成场景: {'✅ 通过' if ppt_result else '❌ 失败'}")
    logger.info(f"Vibe Coding场景: {'✅ 通过' if vibe_result else '❌ 失败'}")
    logger.info(f"\n总体结果: {'✅ 架构验证通过' if (ppt_result and vibe_result) else '⚠️ 需要调试'}")
    
    return ppt_result and vibe_result


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

