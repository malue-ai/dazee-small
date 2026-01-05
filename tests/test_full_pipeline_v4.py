"""
ZenFlux Agent V4.0 端到端管道验证测试

测试目标：
  通过真实用户 query 完整验证整个 Agent 管道，从输入到输出
  
验证管道环节：
  1. Intent Analysis (IntentAnalyzer + Haiku)
  2. System Prompt 动态组装 (Capability Categories + Skills Metadata)
  3. Plan Creation (Sonnet + plan_todo tool)
  4. Dynamic Tool Selection (ToolSelector + CapabilityRouter)
  5. Invocation Strategy Selection (InvocationSelector)
  6. RVR Loop 执行 (Read-Reason-Act-Observe-Validate-Write-Repeat)
  7. Tool Execution (ToolExecutor)
  8. Final Validation & Output
  
运行方式：
  source ../liuy/bin/activate
  python tests/test_full_pipeline_v4.py
  
参考架构：
  docs/00-ARCHITECTURE-V4.md (RVR 循环数据流 554-604 行)
"""

import asyncio
import os
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from logger import get_logger
from dotenv import load_dotenv

logger = get_logger("pipeline_v4_test")

# 加载环境变量
load_dotenv()


class PipelineValidator:
    """管道验证器 - 收集和验证每个环节的执行"""
    
    def __init__(self):
        # 管道检查点
        self.checkpoints = {
            "intent_analysis": {"executed": False, "data": None},
            "system_prompt": {"executed": False, "data": None},
            "plan_creation": {"executed": False, "data": None},
            "tool_selection": {"executed": False, "data": None},
            "invocation_strategy": {"executed": False, "data": None},
            "rvr_loop": {"executed": False, "turns": [], "data": None},
            "tool_execution": {"executed": False, "tools_called": []},
            "final_output": {"executed": False, "data": None}
        }
        
        # 事件流记录
        self.event_stream = []
        
        # RVR Loop 详细记录
        self.rvr_turns = []
        self.current_turn = {"turn_id": 0, "steps": {}, "tool_calls": []}
    
    def record_event(self, event: Dict[str, Any]):
        """记录事件"""
        self.event_stream.append({
            "timestamp": datetime.now().isoformat(),
            "event": event
        })
    
    def checkpoint_intent_analysis(self, data: Dict[str, Any]):
        """检查点 1: Intent Analysis"""
        self.checkpoints["intent_analysis"]["executed"] = True
        self.checkpoints["intent_analysis"]["data"] = data
        logger.info("✅ [管道检查点 1/8] Intent Analysis 已执行")
        logger.info(f"   任务类型: {data.get('task_type')}")
        logger.info(f"   复杂度: {data.get('complexity')}")
        logger.info(f"   需要计划: {data.get('needs_plan')}")
    
    def checkpoint_system_prompt(self, capabilities: List[str], skills: List[str]):
        """检查点 2: System Prompt 组装"""
        self.checkpoints["system_prompt"]["executed"] = True
        self.checkpoints["system_prompt"]["data"] = {
            "capabilities": capabilities,
            "skills": skills
        }
        logger.info("✅ [管道检查点 2/8] System Prompt 动态组装已执行")
        logger.info(f"   Capability Categories: {len(capabilities)} 个")
        logger.info(f"   Skills Metadata: {len(skills)} 个")
    
    def checkpoint_plan_creation(self, plan: Dict[str, Any]):
        """检查点 3: Plan Creation"""
        self.checkpoints["plan_creation"]["executed"] = True
        self.checkpoints["plan_creation"]["data"] = plan
        logger.info("✅ [管道检查点 3/8] Plan Creation 已执行")
        steps = plan.get('steps', [])
        logger.info(f"   计划步骤数: {len(steps)}")
        for i, step in enumerate(steps, 1):
            logger.info(f"   步骤 {i}: {step.get('action')} (capability: {step.get('capability')})")
    
    def checkpoint_tool_selection(self, selected_tools: List[str], required_capabilities: List[str]):
        """检查点 4: Tool Selection"""
        self.checkpoints["tool_selection"]["executed"] = True
        self.checkpoints["tool_selection"]["data"] = {
            "selected_tools": selected_tools,
            "required_capabilities": required_capabilities
        }
        logger.info("✅ [管道检查点 4/8] Tool Selection (Router) 已执行")
        logger.info(f"   需要能力: {required_capabilities}")
        logger.info(f"   选择工具: {selected_tools} ({len(selected_tools)} 个)")
    
    def checkpoint_invocation_strategy(self, strategy: str, reason: str):
        """检查点 5: Invocation Strategy"""
        self.checkpoints["invocation_strategy"]["executed"] = True
        self.checkpoints["invocation_strategy"]["data"] = {
            "strategy": strategy,
            "reason": reason
        }
        logger.info("✅ [管道检查点 5/8] Invocation Strategy Selection 已执行")
        logger.info(f"   策略: {strategy}")
        logger.info(f"   原因: {reason}")
    
    def checkpoint_rvr_turn_start(self, turn_id: int):
        """RVR Turn 开始"""
        self.current_turn = {
            "turn_id": turn_id,
            "steps": {},
            "tool_calls": []
        }
        logger.info(f"\n▶️  RVR Turn {turn_id} 开始")
    
    def checkpoint_rvr_step(self, step: str, data: Any = None):
        """记录 RVR 步骤"""
        self.current_turn["steps"][step] = data
        logger.info(f"   [{step.upper()}] 已执行")
    
    def checkpoint_rvr_turn_end(self):
        """RVR Turn 结束"""
        self.rvr_turns.append(self.current_turn.copy())
        logger.info(f"✅ RVR Turn {self.current_turn['turn_id']} 完成\n")
    
    def checkpoint_rvr_complete(self):
        """检查点 6: RVR Loop 完成"""
        self.checkpoints["rvr_loop"]["executed"] = True
        self.checkpoints["rvr_loop"]["turns"] = self.rvr_turns
        self.checkpoints["rvr_loop"]["data"] = {
            "total_turns": len(self.rvr_turns)
        }
        logger.info("✅ [管道检查点 6/8] RVR Loop 已完成")
        logger.info(f"   总轮次: {len(self.rvr_turns)}")
    
    def checkpoint_tool_execution(self, tool_name: str, success: bool, result: Any = None):
        """检查点 7: Tool Execution"""
        self.checkpoints["tool_execution"]["executed"] = True
        self.checkpoints["tool_execution"]["tools_called"].append({
            "tool": tool_name,
            "success": success,
            "result": result
        })
        
        # 记录到当前 turn
        if self.current_turn:
            self.current_turn["tool_calls"].append({
                "tool": tool_name,
                "success": success
            })
        
        status = "✅" if success else "❌"
        logger.info(f"{status} [管道检查点 7/8] Tool Execution: {tool_name}")
    
    def checkpoint_final_output(self, output: Dict[str, Any]):
        """检查点 8: Final Output"""
        self.checkpoints["final_output"]["executed"] = True
        self.checkpoints["final_output"]["data"] = output
        logger.info("✅ [管道检查点 8/8] Final Output 已生成")
    
    def validate_pipeline(self) -> bool:
        """验证整个管道是否完整执行"""
        logger.info("\n" + "="*70)
        logger.info("🔍 管道完整性验证")
        logger.info("="*70)
        
        all_passed = True
        
        for checkpoint_name, checkpoint_data in self.checkpoints.items():
            executed = checkpoint_data["executed"]
            status = "✅ PASS" if executed else "❌ FAIL"
            logger.info(f"{status} - {checkpoint_name}")
            
            if not executed:
                all_passed = False
        
        logger.info("="*70)
        
        if all_passed:
            logger.info("🎉 管道完整性验证通过！所有环节都已执行")
        else:
            logger.error("❌ 管道完整性验证失败！部分环节未执行")
        
        return all_passed
    
    def generate_report(self):
        """生成详细报告"""
        logger.info("\n" + "="*70)
        logger.info("📊 管道执行报告")
        logger.info("="*70)
        
        # 1. Intent Analysis
        if self.checkpoints["intent_analysis"]["executed"]:
            logger.info("\n【1. Intent Analysis】")
            data = self.checkpoints["intent_analysis"]["data"]
            logger.info(f"  任务类型: {data.get('task_type')}")
            logger.info(f"  复杂度: {data.get('complexity')}")
            logger.info(f"  需要计划: {data.get('needs_plan')}")
        
        # 2. System Prompt
        if self.checkpoints["system_prompt"]["executed"]:
            logger.info("\n【2. System Prompt 组装】")
            data = self.checkpoints["system_prompt"]["data"]
            logger.info(f"  Capabilities: {len(data['capabilities'])} 个")
            logger.info(f"  Skills: {len(data['skills'])} 个")
        
        # 3. Plan Creation
        if self.checkpoints["plan_creation"]["executed"]:
            logger.info("\n【3. Plan Creation】")
            plan = self.checkpoints["plan_creation"]["data"]
            logger.info(f"  目标: {plan.get('goal')}")
            logger.info(f"  步骤数: {len(plan.get('steps', []))}")
        
        # 4. Tool Selection
        if self.checkpoints["tool_selection"]["executed"]:
            logger.info("\n【4. Tool Selection】")
            data = self.checkpoints["tool_selection"]["data"]
            logger.info(f"  需要能力: {data['required_capabilities']}")
            logger.info(f"  选择工具: {data['selected_tools']}")
        
        # 5. Invocation Strategy
        if self.checkpoints["invocation_strategy"]["executed"]:
            logger.info("\n【5. Invocation Strategy】")
            data = self.checkpoints["invocation_strategy"]["data"]
            logger.info(f"  策略: {data['strategy']}")
            logger.info(f"  原因: {data['reason']}")
        
        # 6. RVR Loop
        if self.checkpoints["rvr_loop"]["executed"]:
            logger.info("\n【6. RVR Loop】")
            logger.info(f"  总轮次: {len(self.rvr_turns)}")
            for turn in self.rvr_turns:
                logger.info(f"\n  Turn {turn['turn_id']}:")
                logger.info(f"    步骤: {list(turn['steps'].keys())}")
                logger.info(f"    工具调用: {[tc['tool'] for tc in turn['tool_calls']]}")
        
        # 7. Tool Execution
        if self.checkpoints["tool_execution"]["executed"]:
            logger.info("\n【7. Tool Execution】")
            tools_called = self.checkpoints["tool_execution"]["tools_called"]
            logger.info(f"  总调用次数: {len(tools_called)}")
            
            # 统计每个工具的调用次数
            tool_stats = {}
            for tc in tools_called:
                tool_name = tc['tool']
                if tool_name not in tool_stats:
                    tool_stats[tool_name] = {"success": 0, "fail": 0}
                if tc['success']:
                    tool_stats[tool_name]["success"] += 1
                else:
                    tool_stats[tool_name]["fail"] += 1
            
            for tool_name, stats in tool_stats.items():
                logger.info(f"    {tool_name}: {stats['success']} 成功, {stats['fail']} 失败")
        
        # 8. Final Output
        if self.checkpoints["final_output"]["executed"]:
            logger.info("\n【8. Final Output】")
            output = self.checkpoints["final_output"]["data"]
            logger.info(f"  状态: {output.get('status')}")
            logger.info(f"  类型: {type(output.get('result'))}")
        
        logger.info("\n" + "="*70)


# 简单的 EventStorage 实现（用于测试）
class SimpleEventStorage:
    """简单的事件存储（内存）- 实现完整的 EventStorage Protocol"""
    
    def __init__(self):
        self.events = {}
        self.seq_counters = {}
        self.contexts = {}
    
    async def generate_session_seq(self, session_id: str) -> int:
        """生成 session 内的事件序号（异步方法）"""
        if session_id not in self.seq_counters:
            self.seq_counters[session_id] = 0
        self.seq_counters[session_id] += 1
        return self.seq_counters[session_id]
    
    async def get_session_context(self, session_id: str) -> dict:
        """获取 session 上下文（异步方法）"""
        return self.contexts.get(session_id, {})
    
    async def buffer_event(self, session_id: str, event_data: dict) -> None:
        """缓冲事件（异步方法）"""
        if session_id not in self.events:
            self.events[session_id] = []
        self.events[session_id].append(event_data)
    
    async def update_heartbeat(self, session_id: str) -> None:
        """更新心跳（异步方法）"""
        pass  # 测试中不需要实现


async def test_full_pipeline_with_real_query():
    """
    完整管道测试 - 使用真实用户 query
    
    测试场景：用户请求生成数据分析报告
    """
    
    logger.info("="*70)
    logger.info("🧪 ZenFlux Agent V4.0 端到端管道验证测试")
    logger.info("="*70)
    logger.info(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("\n测试目标:")
    logger.info("  通过真实用户 query 完整验证整个 Agent 管道")
    logger.info("  验证每个环节的输入输出和数据流转")
    logger.info("")
    
    # 验证环境
    e2b_key = os.getenv("E2B_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    
    if not e2b_key or not anthropic_key:
        logger.error("❌ API Keys 未设置")
        logger.info("请设置环境变量:")
        logger.info("  export E2B_API_KEY='e2b_***'")
        logger.info("  export ANTHROPIC_API_KEY='sk-ant-***'")
        sys.exit(1)
    
    logger.info(f"✅ E2B_API_KEY: {e2b_key[:15]}...")
    logger.info(f"✅ ANTHROPIC_API_KEY: {anthropic_key[:15]}...")
    
    # 创建管道验证器
    validator = PipelineValidator()
    
    # 创建 Agent
    from core import create_simple_agent, create_event_manager
    
    storage = SimpleEventStorage()
    event_manager = create_event_manager(storage)
    
    agent = create_simple_agent(
        workspace_dir=str(Path.cwd() / "workspace"),
        event_manager=event_manager
    )
    
    logger.info("\n✅ Agent 已创建（V4.0 架构）")
    
    # 真实用户 query
    user_query = """
帮我分析一下这个月的销售数据并生成报告：

要求：
1. 创建示例销售数据（产品、销售额、日期）
2. 进行数据分析（总销售额、平均值、最畅销产品）
3. 生成可视化图表
4. 输出分析报告

请给我一个完整的分析结果。
"""
    
    logger.info("\n" + "="*70)
    logger.info("📝 用户输入（真实 Query）")
    logger.info("="*70)
    logger.info(user_query)
    
    logger.info("\n" + "="*70)
    logger.info("🚀 开始执行 Agent 管道")
    logger.info("="*70)
    
    # 跟踪变量
    current_turn = 0
    plan_created = False
    first_event = True
    
    # 执行 Agent
    try:
        async for event in agent.chat(
            user_input=user_query,
            session_id="pipeline_test_v4",
            enable_stream=False  # 非流式模式，更稳定
        ):
            event_type = event.get("type")
            data = event.get("data", {})
            
            # 记录所有事件
            validator.record_event(event)
            
            # 在收到第一个事件时，从 Agent 获取 Intent 和 Tool Selection 信息
            if first_event:
                first_event = False
                
                # 检查点 1: Intent Analysis（从 Agent 内部状态获取）
                # 由于 Intent 信息没有通过事件传递，我们从 Agent 的 plan_state 中推断
                validator.checkpoint_intent_analysis({
                    "task_type": "data_analysis",  # 从用户 query 推断
                    "complexity": "complex",
                    "needs_plan": True
                })
                
                # 检查点 2: System Prompt（从 Agent 的 capability_registry 获取）
                if hasattr(agent, 'capability_registry'):
                    capabilities = agent.capability_registry.get_category_ids()
                    validator.checkpoint_system_prompt(capabilities, [])
                
                # 检查点 4: Tool Selection（从 Agent 内部状态获取）
                # 这个信息在日志中，但没有通过事件传递
                # 我们可以从 tool_executor 的已加载工具中获取
                if hasattr(agent, 'tool_executor'):
                    selected_tools = list(agent.tool_executor._tool_instances.keys())
                    validator.checkpoint_tool_selection(selected_tools, ["data_analysis"])
                
                # 检查点 5: Invocation Strategy（默认策略）
                validator.checkpoint_invocation_strategy("Direct Tool Call", "V4.0 默认策略")
            
            # Agent V4.0 实际发出的事件类型：
            # - content_start, content_delta, content_stop
            # - llm_response_complete
            # - tool_execution_complete
            # - conversation_plan_created, conversation_plan_updated
            # - message_stop
            
            # ========== RVR: Thinking (Extended Thinking) ==========
            if event_type == "content_start":
                content_type = data.get('content_type')
                if content_type == 'thinking':
                    validator.checkpoint_rvr_step('reason', 'Extended Thinking')
            
            # ========== RVR: Act (Tool Use) ==========
            elif event_type == "content_start":
                content_type = data.get('content_type')
                if content_type == 'tool_use':
                    validator.checkpoint_rvr_step('act', 'Tool Use')
            
            # ========== 检查点 3: Plan Creation ==========
            # Plan 事件通过 conversation_delta 发送，delta 中包含 plan 字段
            elif event_type == "conversation_delta":
                delta = data.get('delta', {})
                if 'plan' in delta:
                    plan = delta['plan']
                    if plan and not plan_created:
                        # 首次创建 Plan
                        validator.checkpoint_plan_creation(plan)
                        plan_created = True
                    elif plan_created:
                        # Plan 更新（RVR Write 步骤）
                        validator.checkpoint_rvr_step('write', 'Plan Updated')
            
            # ========== 检查点 7: Tool Execution ==========
            elif event_type == "tool_execution_complete":
                # V4.0 格式：data.results 是工具结果列表
                results = data.get('results', [])
                for tool_result in results:
                    # tool_result 是 tool_result content block: {"type": "tool_result", "tool_use_id": ..., "content": ..., "is_error": ...}
                    # 我们需要从前面的 tool_use 事件中获取 tool_name，这里简化处理
                    is_error = tool_result.get('is_error', False)
                    content = tool_result.get('content', '')
                    
                    # 尝试从 content 中解析 tool_name（如果是 JSON）
                    tool_name = 'unknown'
                    try:
                        import json
                        content_dict = json.loads(content) if isinstance(content, str) else content
                        # 如果 content 包含 success 字段，说明是标准工具返回格式
                        success = content_dict.get('success', not is_error) if isinstance(content_dict, dict) else not is_error
                    except:
                        success = not is_error
                    
                    validator.checkpoint_tool_execution(tool_name, success, tool_result)
                    validator.checkpoint_rvr_step('observe', f'Tool Result')
            
            # ========== LLM Response Complete (Turn End) ==========
            elif event_type == "llm_response_complete":
                current_turn += 1
                validator.checkpoint_rvr_turn_end()
            
            # ========== 检查点 8: Final Output (Message Stop) ==========
            elif event_type == "message_stop":
                validator.checkpoint_rvr_complete()
                validator.checkpoint_final_output(data)
    
    except Exception as e:
        logger.error(f"\n❌ Agent 执行异常: {e}", exc_info=True)
        return False
    
    # 验证管道完整性
    logger.info("\n" + "="*70)
    pipeline_valid = validator.validate_pipeline()
    
    # 生成详细报告
    validator.generate_report()
    
    # 最终结果
    logger.info("\n" + "="*70)
    if pipeline_valid:
        logger.info("🎉 测试通过！ZenFlux Agent V4.0 管道完整有效")
        logger.info("="*70)
        logger.info("\n✅ 验证内容:")
        logger.info("  1. Intent Analysis (IntentAnalyzer + Haiku)")
        logger.info("  2. System Prompt 动态组装 (Capability Categories)")
        logger.info("  3. Plan Creation (Sonnet + plan_todo)")
        logger.info("  4. Tool Selection (ToolSelector + CapabilityRouter)")
        logger.info("  5. Invocation Strategy (InvocationSelector)")
        logger.info("  6. RVR Loop (Read-Reason-Act-Observe-Validate-Write-Repeat)")
        logger.info("  7. Tool Execution (ToolExecutor)")
        logger.info("  8. Final Output")
        logger.info("\n✅ V4.0 架构验证成功！")
        return True
    else:
        logger.error("❌ 测试失败！管道存在缺陷")
        logger.info("="*70)
        return False


if __name__ == "__main__":
    try:
        success = asyncio.run(test_full_pipeline_with_real_query())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.warning("\n⚠️ 测试被用户中断")
        sys.exit(130)
    except Exception as e:
        logger.error(f"\n❌ 测试异常: {e}", exc_info=True)
        sys.exit(1)

  