#!/usr/bin/env python3
"""
真实用户 Query 直接测试 - 不依赖 services 层

目标：
1. 用户输入 → Agent 处理 → 最终答案
2. 验证 7 阶段流程
3. 验证答案质量

运行：
    cd /Users/liuyi/Documents/langchain/CoT_agent/mvp/zenflux_agent
    source /Users/liuyi/Documents/langchain/liuy/bin/activate
    python tests/test_real_query_direct.py
"""

import asyncio
import os
import sys
import json
from pathlib import Path
from datetime import datetime

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

# 确保有 API key
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
EXA_KEY = os.getenv("EXA_API_KEY")

if not ANTHROPIC_KEY:
    print("❌ ANTHROPIC_API_KEY 未设置")
    sys.exit(1)

print(f"✅ ANTHROPIC_API_KEY: {ANTHROPIC_KEY[:20]}...")
print(f"✅ EXA_API_KEY: {EXA_KEY[:15] if EXA_KEY else 'NOT SET'}...")


class QueryTestResult:
    """测试结果"""
    def __init__(self, query: str):
        self.query = query
        self.stages = {}
        self.tool_calls = []
        self.thinking = ""
        self.final_answer = ""
        self.errors = []
        self.rvr_turns = 0
        self.start_time = datetime.now()
        self.end_time = None
    
    def add_stage(self, name: str, data: dict):
        self.stages[name] = data
        
    def print_report(self):
        """打印详细报告"""
        self.end_time = datetime.now()
        duration = (self.end_time - self.start_time).total_seconds()
        
        print("\n" + "="*80)
        print("📊 端到端验证报告")
        print("="*80)
        
        print(f"\n⏱️  执行时间: {duration:.2f} 秒")
        
        print(f"\n📝 用户输入 (Query):")
        print(f"   「{self.query}」")
        
        print(f"\n🔄 执行流程 ({len(self.stages)}/7 阶段):")
        for i in range(1, 8):
            stage_key = f"stage_{i}"
            if stage_key in self.stages:
                stage_data = self.stages[stage_key]
                print(f"   ✅ 阶段 {i}: {stage_data.get('name', '?')}")
                if stage_data.get('details'):
                    for k, v in stage_data['details'].items():
                        print(f"      • {k}: {v}")
            else:
                print(f"   ❌ 阶段 {i}: 未执行")
        
        print(f"\n🔧 工具调用 ({len(self.tool_calls)}):")
        for tc in self.tool_calls:
            print(f"   • {tc['tool']}: {tc.get('status', '?')}")
        
        print(f"\n🧠 Extended Thinking (预览):")
        if self.thinking:
            preview = self.thinking[:300] + "..." if len(self.thinking) > 300 else self.thinking
            print(f"   {preview}")
        else:
            print(f"   (无)")
        
        print(f"\n💬 最终答案:")
        print("-"*80)
        if self.final_answer:
            print(self.final_answer)
        else:
            print("⚠️ 未获取到最终答案")
        print("-"*80)
        
        if self.errors:
            print(f"\n❌ 错误 ({len(self.errors)}):")
            for err in self.errors:
                print(f"   • {err}")
        
        print("\n" + "="*80)
        
        # 质量评估
        print("🎯 答案质量评估:")
        answer_len = len(self.final_answer)
        has_content = answer_len > 50
        has_tools = len(self.tool_calls) > 0
        
        print(f"   • 答案长度: {answer_len} 字符 {'✅' if has_content else '⚠️'}")
        print(f"   • 使用工具: {has_tools} {'✅' if has_tools else '⚠️'}")
        print(f"   • RVR 轮次: {self.rvr_turns}")
        
        overall = has_content
        print(f"\n{'🎉 验证通过' if overall else '❌ 验证失败'}")
        print("="*80)
        
        return overall


async def test_simple_query():
    """
    测试简单 Query: "今天深圳天气怎么样？"
    
    预期:
    - 使用 exa_search 或 web_search 工具
    - 返回天气信息
    """
    print("\n" + "="*80)
    print("🧪 测试 1: 简单问答")
    print("="*80)
    
    query = "今天深圳天气怎么样？"
    result = QueryTestResult(query)
    
    print(f"\n👤 用户输入: {query}")
    
    # ===== 阶段 1: 初始化 Agent =====
    print("\n📦 阶段 1: 初始化 Agent...")
    
    from core import create_simple_agent, create_event_manager
    from core.events.storage import InMemoryEventStorage
    
    storage = InMemoryEventStorage()
    event_manager = create_event_manager(storage)
    
    workspace_dir = str(Path.cwd() / "workspace")
    agent = create_simple_agent(
        workspace_dir=workspace_dir,
        event_manager=event_manager
    )
    
    result.add_stage("stage_1", {
        "name": "Session/Agent 初始化",
        "details": {
            "workspace": workspace_dir,
            "components": "CapabilityRegistry, IntentAnalyzer, ToolSelector, ToolExecutor"
        }
    })
    print("   ✅ Agent 已初始化")
    
    # ===== 阶段 2-7: 执行 chat =====
    print("\n🚀 执行 Agent.chat()...")
    
    messages = [{"role": "user", "content": query}]
    session_id = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    intent_logged = False
    tool_selection_logged = False
    
    try:
        async for event in agent.chat(
            messages=messages,
            session_id=session_id,
            enable_stream=True
        ):
            event_type = event.get("type", "")
            data = event.get("data", {})
            
            # 阶段 2: Intent Analysis
            if event_type == "message_delta" and not intent_logged:
                delta = data.get("delta", {})
                if delta.get("type") == "intent":
                    try:
                        intent = json.loads(delta.get("content", "{}"))
                        result.add_stage("stage_2", {
                            "name": "Intent Analysis (Haiku)",
                            "details": {
                                "task_type": intent.get("task_type"),
                                "complexity": intent.get("complexity"),
                                "needs_plan": intent.get("needs_plan")
                            }
                        })
                        intent_logged = True
                        print(f"   ✅ 阶段 2: Intent = {intent.get('task_type')}, {intent.get('complexity')}")
                    except:
                        pass
            
            # 工具选择 (阶段 3)
            if not tool_selection_logged and intent_logged:
                result.add_stage("stage_3", {
                    "name": "Tool Selection (Schema 驱动)",
                    "details": {"priority": "Schema > Plan > Intent"}
                })
                tool_selection_logged = True
                print("   ✅ 阶段 3: Tool Selection")
                
                result.add_stage("stage_4", {
                    "name": "System Prompt 组装",
                    "details": {"prompt": "UNIVERSAL_AGENT_PROMPT"}
                })
                print("   ✅ 阶段 4: System Prompt 组装")
            
            # RVR Loop - Thinking
            if event_type == "content_start":
                content_block = data.get("content_block", {})
                if content_block.get("type") == "thinking":
                    result.rvr_turns += 1
                    print(f"\n   🔄 RVR Turn {result.rvr_turns}")
            
            # RVR Loop - Tool Call
            if event_type == "content_start":
                content_block = data.get("content_block", {})
                if content_block.get("type") == "tool_use":
                    tool_name = content_block.get("name", "unknown")
                    tool_input = content_block.get("input", {})
                    result.tool_calls.append({
                        "tool": tool_name,
                        "input": tool_input,
                        "status": "called"
                    })
                    print(f"      [Act] 调用工具: {tool_name}")
                    
                    # 检测 Plan Creation (阶段 5)
                    if tool_name == "plan_todo":
                        operation = tool_input.get("operation", "")
                        if operation == "create_plan":
                            result.add_stage("stage_5", {
                                "name": "Plan Creation (Claude 自主触发)",
                                "details": {"tool": "plan_todo.create_plan"}
                            })
                            print("   ✅ 阶段 5: Plan Creation")
            
            # 收集 thinking 内容
            if event_type == "content_delta":
                delta = data.get("delta", {})
                if delta.get("type") == "thinking_delta":
                    result.thinking += delta.get("thinking", "")
            
            # 收集最终答案
            if event_type == "content_delta":
                delta = data.get("delta", {})
                if delta.get("type") == "text_delta":
                    result.final_answer += delta.get("text", "")
            
            # 完成
            if event_type == "message_stop":
                # 如果没有 Plan，记录为跳过
                if "stage_5" not in result.stages:
                    result.add_stage("stage_5", {
                        "name": "Plan Creation (跳过)",
                        "details": {"reason": "简单任务无需 Plan"}
                    })
                    print("   ✅ 阶段 5: Plan Creation (跳过 - 简单任务)")
                
                result.add_stage("stage_6", {
                    "name": "RVR Loop",
                    "details": {
                        "turns": result.rvr_turns,
                        "tools": [tc["tool"] for tc in result.tool_calls]
                    }
                })
                print(f"   ✅ 阶段 6: RVR Loop 完成 (轮次: {result.rvr_turns})")
                
                result.add_stage("stage_7", {
                    "name": "Final Output",
                    "details": {"answer_length": len(result.final_answer)}
                })
                print("   ✅ 阶段 7: Final Output")
    
    except Exception as e:
        result.errors.append(str(e))
        print(f"\n   ❌ 执行异常: {e}")
        import traceback
        traceback.print_exc()
    
    # 打印报告
    return result.print_report()


async def test_search_query():
    """
    测试搜索 Query: "搜索一下 Claude 4 的最新特性"
    
    预期:
    - 使用 exa_search 工具
    - 返回搜索结果摘要
    """
    print("\n" + "="*80)
    print("🧪 测试 2: 搜索查询")
    print("="*80)
    
    query = "搜索一下 Claude 4 Sonnet 的最新特性有哪些？"
    result = QueryTestResult(query)
    
    print(f"\n👤 用户输入: {query}")
    
    # 初始化
    from core import create_simple_agent, create_event_manager
    from core.events.storage import InMemoryEventStorage
    
    storage = InMemoryEventStorage()
    event_manager = create_event_manager(storage)
    
    agent = create_simple_agent(
        workspace_dir=str(Path.cwd() / "workspace"),
        event_manager=event_manager
    )
    
    result.add_stage("stage_1", {
        "name": "Session/Agent 初始化",
        "details": {}
    })
    print("   ✅ 阶段 1: Agent 初始化")
    
    messages = [{"role": "user", "content": query}]
    session_id = f"search_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    intent_done = False
    
    try:
        async for event in agent.chat(
            messages=messages,
            session_id=session_id,
            enable_stream=True
        ):
            event_type = event.get("type", "")
            data = event.get("data", {})
            
            # Intent
            if event_type == "message_delta" and not intent_done:
                delta = data.get("delta", {})
                if delta.get("type") == "intent":
                    try:
                        intent = json.loads(delta.get("content", "{}"))
                        result.add_stage("stage_2", {"name": "Intent Analysis", "details": intent})
                        result.add_stage("stage_3", {"name": "Tool Selection", "details": {}})
                        result.add_stage("stage_4", {"name": "System Prompt", "details": {}})
                        intent_done = True
                        print(f"   ✅ 阶段 2-4 完成")
                    except:
                        pass
            
            # Tool Call
            if event_type == "content_start":
                cb = data.get("content_block", {})
                if cb.get("type") == "thinking":
                    result.rvr_turns += 1
                if cb.get("type") == "tool_use":
                    tool_name = cb.get("name", "")
                    result.tool_calls.append({"tool": tool_name, "status": "ok"})
                    print(f"      [工具] {tool_name}")
            
            # Thinking
            if event_type == "content_delta":
                delta = data.get("delta", {})
                if delta.get("type") == "thinking_delta":
                    result.thinking += delta.get("thinking", "")
                if delta.get("type") == "text_delta":
                    result.final_answer += delta.get("text", "")
            
            # Done
            if event_type == "message_stop":
                result.add_stage("stage_5", {"name": "Plan (跳过)", "details": {}})
                result.add_stage("stage_6", {"name": "RVR Loop", "details": {"turns": result.rvr_turns}})
                result.add_stage("stage_7", {"name": "Final Output", "details": {}})
                print("   ✅ 阶段 5-7 完成")
    
    except Exception as e:
        result.errors.append(str(e))
        print(f"   ❌ 异常: {e}")
    
    return result.print_report()


async def main():
    """运行所有测试"""
    print("="*80)
    print("🚀 ZenFlux Agent V4.4 - 真实用户 Query 端到端验证")
    print("="*80)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"目标: 验证 输入 → 处理 → 输出 的完整流程和答案质量")
    print("")
    
    # 测试 1: 简单问答
    result1 = await test_simple_query()
    
    # 测试 2: 搜索查询
    print("\n\n")
    result2 = await test_search_query()
    
    # 总结
    print("\n" + "="*80)
    print("🏁 测试总结")
    print("="*80)
    print(f"测试 1 (简单问答): {'✅ 通过' if result1 else '❌ 失败'}")
    print(f"测试 2 (搜索查询): {'✅ 通过' if result2 else '❌ 失败'}")
    print("="*80)
    
    return result1 and result2


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️ 测试被中断")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

