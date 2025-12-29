"""
端到端测试 - PPT生成场景

验证架构文档中描述的完整流程：
1. Intent Analysis (Haiku)
2. System Prompt 动态组装
3. Plan Creation (Sonnet)
4. Dynamic Tool Selection (Router)
5. Invocation Strategy Selection
6. RVR Loop (执行步骤)
7. Final Validation & Output

对照架构文档：00-ARCHITECTURE-OVERVIEW.md (226-527)
"""

import os
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from logger import get_logger

logger = get_logger("ppt_e2e_test")

# 加载环境变量（使用绝对路径）
env_path = "/Users/liuyi/Documents/langchain/CoT_agent/mvp/.env"
load_dotenv(env_path)

# 验证必要的环境变量
required_keys = ["ANTHROPIC_API_KEY"]  # 至少需要Claude API
missing_keys = [key for key in required_keys if not os.getenv(key)]
if missing_keys:
    logger.error(f"❌ 缺少必需API密钥: {missing_keys}")
    logger.info("提示: 请检查 .env 文件配置")

# 可选的API密钥
optional_keys = ["EXA_API_KEY", "SLIDESPEAK_API_KEY"]
for key in optional_keys:
    if os.getenv(key):
        logger.info(f"✅ {key}: 已配置")
    else:
        logger.info(f"ℹ️  {key}: 未配置（将跳过相关工具）")

from core import create_simple_agent, create_event_manager


class SimpleEventStorage:
    """简单的事件存储（测试用）"""
    def __init__(self):
        self.events = {}
        self.seq_counters = {}
        self.contexts = {}
    
    def generate_session_seq(self, session_id):
        self.seq_counters[session_id] = self.seq_counters.get(session_id, 0) + 1
        return self.seq_counters[session_id]
    
    def get_session_context(self, session_id):
        return {}
    
    def buffer_event(self, session_id, event_data):
        pass
    
    def update_heartbeat(self, session_id):
        pass


async def test_ppt_generation_e2e():
    """
    端到端测试：PPT生成
    
    用户场景：
    "帮我生成一个产品介绍PPT，主题是AI智能客服系统，要求专业风格"
    
    预期流程（对照架构文档）：
    1. Intent Analysis → task_type: "content_generation", complexity: "complex", needs_plan: true
    2. Router → 筛选工具: [exa_search, slidespeak-generator, plan_todo, bash, ...]
    3. Plan Creation → LLM创建Plan（可选）
    4. RVR Loop → 执行步骤（如果有Plan）
    5. Final Output → PPT下载链接
    """
    logger.info("="*70)
    logger.info("🧪 端到端测试 - PPT生成场景")
    logger.info("="*70)
    logger.info("\n架构流程验证:")
    logger.info("  User Query → Intent → Router → Plan? → RVR → Output")
    logger.info("")
    
    # 验证环境变量
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    logger.info(f"✅ ANTHROPIC_API_KEY: {anthropic_key[:15]}...")
    
    # 创建Agent
    storage = SimpleEventStorage()
    event_manager = create_event_manager(storage)
    agent = create_simple_agent(
        workspace_dir=str(project_root / "workspace"),
        event_manager=event_manager
    )
    
    logger.info("\n✅ Agent 已创建（V3.7 架构）")
    
    # 用户输入（PPT生成场景）
    user_query = """
帮我生成一个产品介绍PPT，主题是AI智能客服系统。

要求：
1. 专业风格，适合向客户展示
2. 包含以下内容：
   - 产品功能介绍
   - 核心技术优势
   - 应用场景
   - 客户案例
3. 大约8-10页幻灯片
"""
    
    logger.info("\n" + "="*70)
    logger.info("📝 用户输入（PPT生成场景）")
    logger.info("="*70)
    logger.info(user_query)
    
    # 流程追踪
    flow_tracker = {
        "intent_analysis": False,
        "router_selection": False,
        "plan_creation": False,
        "rvr_execution": False,
        "tools_called": [],
        "ppt_url": None,
        "preview_url": None
    }
    
    logger.info("\n" + "-"*70)
    logger.info("开始执行 Agent...观察完整流程")
    logger.info("-"*70)
    
    try:
        # 执行Agent（非流式，避免网络错误）
        async for event in agent.chat(
            user_input=user_query,
            session_id="ppt_e2e_test",
            enable_stream=False  # 使用非流式模式
        ):
            event_type = event.get('event_type')
            data = event.get('data', {})
            
            # 1. Intent Analysis
            if event_type == "intent_analysis":
                flow_tracker["intent_analysis"] = True
                logger.info("\n✅ 1️⃣ Intent Analysis (Haiku):")
                logger.info(f"  任务类型: {data.get('task_type')}")
                logger.info(f"  复杂度: {data.get('complexity')}")
                logger.info(f"  需要计划: {data.get('needs_plan')}")
            
            # 2. Router (工具筛选)
            elif event_type == "tool_selection":
                flow_tracker["router_selection"] = True
                required_caps = data.get('required_capabilities', [])
                selected_tools = data.get('selected_tools', [])
                logger.info("\n✅ 2️⃣ Router (能力映射):")
                logger.info(f"  需要能力: {required_caps}")
                logger.info(f"  选择工具: {selected_tools}")
                
                # 验证关键工具
                has_ppt_tool = any('slidespeak' in tool.lower() or 'pptx' in tool.lower() 
                                   for tool in selected_tools)
                has_search_tool = any('search' in tool.lower() for tool in selected_tools)
                
                if has_ppt_tool:
                    logger.info("\n  🎯 Router正确筛选了PPT生成工具！")
                if has_search_tool:
                    logger.info("  🔍 Router正确筛选了搜索工具！")
            
            # 3. Plan Creation
            elif event_type == "plan_update":
                if not flow_tracker["plan_creation"]:
                    flow_tracker["plan_creation"] = True
                    logger.info("\n✅ 3️⃣ Plan Creation:")
                    plan = data.get('plan', {})
                    logger.info(f"  目标: {plan.get('goal')}")
                    steps = plan.get('steps', [])
                    logger.info(f"  步骤数: {len(steps)}")
                    for i, step in enumerate(steps, 1):
                        logger.info(f"    {i}. {step.get('action')} (capability: {step.get('capability')})")
            
            # 4. Tool Call Start
            elif event_type == "tool_call_start":
                tool_name = data.get('tool_name')
                if not flow_tracker["rvr_execution"]:
                    flow_tracker["rvr_execution"] = True
                    logger.info("\n✅ 4️⃣ RVR Loop (工具执行):")
                
                flow_tracker["tools_called"].append(tool_name)
                logger.info(f"\n  🔧 工具调用: {tool_name}")
            
            # 5. Tool Complete
            elif event_type == "tool_call_complete":
                tool_name = data.get('tool_name')
                result = data.get('result') or {}
                
                # 提取PPT URL
                if 'slidespeak' in tool_name.lower():
                    if result.get('ppt_url'):
                        flow_tracker["ppt_url"] = result['ppt_url']
                    if result.get('preview_url'):
                        flow_tracker["preview_url"] = result['preview_url']
                    
                    if flow_tracker["ppt_url"]:
                        logger.info(f"\n✅ 5️⃣ PPT生成结果:")
                        logger.info(f"  📥 下载URL: {flow_tracker['ppt_url']}")
                        if flow_tracker["preview_url"]:
                            logger.info(f"  👀 预览URL: {flow_tracker['preview_url']}")
            
            # 6. Complete
            elif event_type == "complete":
                logger.info(f"\n✅ 6️⃣ 任务完成")
                logger.info(f"  轮次: {data.get('turns')}")
        
        # 验证流程完整性
        logger.info("\n" + "="*70)
        logger.info("🔍 架构流程验证")
        logger.info("="*70)
        
        validation_results = []
        
        # 阶段1: Intent Analysis
        if flow_tracker["intent_analysis"]:
            logger.info("✅ Intent Analysis: 已执行")
            validation_results.append(True)
        else:
            logger.error("❌ Intent Analysis: 未执行")
            validation_results.append(False)
        
        # 阶段2: Router
        if flow_tracker["router_selection"]:
            logger.info("✅ Router: 已执行（工具筛选）")
            validation_results.append(True)
        else:
            logger.error("❌ Router: 未执行")
            validation_results.append(False)
        
        # 阶段3: Plan (可选)
        if flow_tracker["plan_creation"]:
            logger.info("✅ Plan Creation: 已执行")
        else:
            logger.info("⚠️ Plan Creation: 未执行（LLM选择跳过）")
        
        # 阶段4: RVR/工具执行
        if flow_tracker["rvr_execution"]:
            logger.info(f"✅ 工具执行: {flow_tracker['tools_called']}")
            validation_results.append(True)
        else:
            logger.error("❌ 工具执行: 未执行")
            validation_results.append(False)
        
        # 阶段5: 最终结果
        if flow_tracker["ppt_url"]:
            logger.info(f"✅ PPT生成: {flow_tracker['ppt_url']}")
            validation_results.append(True)
        else:
            logger.warning("⚠️ PPT URL: 未生成")
            validation_results.append(False)
        
        # 计算成功率
        success_rate = sum(validation_results) / len(validation_results) * 100
        logger.info(f"\n成功率: {success_rate:.0f}% ({sum(validation_results)}/{len(validation_results)})")
        
        # 最终判断
        logger.info("\n" + "="*70)
        if success_rate >= 80:
            logger.info("✅ 端到端测试通过！架构流程验证成功")
            return True
        else:
            logger.warning("⚠️ 端到端测试部分通过，需要调试")
            return False
    
    except Exception as e:
        logger.error(f"\n❌ 测试异常: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = asyncio.run(test_ppt_generation_e2e())
    sys.exit(0 if success else 1)

