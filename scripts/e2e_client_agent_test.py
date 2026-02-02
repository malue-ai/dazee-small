#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
client_agent 端对端真实验证

从用户真实 query 开始，全流程验证：
1. 用户发送自然语言请求
2. Agent 意图识别
3. 工具选择（nodes 工具）
4. 命令执行
5. 结果返回

测试场景：
- 打开 Safari 访问网页
- 在 Finder 中打开文件夹
- 发送系统通知
- 执行 AppleScript

使用方法：
    source /Users/liuyi/Documents/langchain/liuy/bin/activate
    cd /Users/liuyi/Documents/langchain/CoT_agent/mvp/zenflux_agent
    python scripts/e2e_client_agent_test.py
"""

import asyncio
import json
import sys
from pathlib import Path

# 添加项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 加载 .env 文件
from dotenv import load_dotenv
env_path = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=env_path, override=True)

from logger import get_logger

logger = get_logger("e2e_client_agent_test")


# ============================================================
# 测试场景定义
# ============================================================

# 基础测试场景（快速验证）
BASIC_SCENARIOS = [
    {
        "name": "打开 Safari 访问网页",
        "query": "打开 Safari 浏览器并访问 https://www.apple.com",
        "expected_tool": "nodes",
        "expected_action": "run",
        "verify_keywords": ["Safari", "apple.com", "open"],
    },
    {
        "name": "在 Finder 中打开下载文件夹",
        "query": "在 Finder 中打开我的下载文件夹",
        "expected_tool": "nodes",
        "expected_action": "run",
        "verify_keywords": ["Downloads", "Finder", "open"],
    },
    {
        "name": "发送系统通知",
        "query": "发送一个系统通知，标题是'测试'，内容是'这是端对端测试'",
        "expected_tool": "nodes",
        "expected_action": "notify",
        "verify_keywords": ["通知", "notify", "测试"],
    },
]

# 高级测试场景（复杂任务，需要多步骤推理和工具组合）
ADVANCED_SCENARIOS = [
    {
        "name": "本地文件处理-笑容筛选",
        "query": "把图片文件夹里的图片，筛选出有笑容的然后新建一个文件夹叫 smile",
        "expected_tool": None,  # 可能使用多个工具
        "expected_action": None,
        "verify_keywords": ["图片", "笑容", "smile", "文件夹"],
        "description": "需要图片识别（笑容检测）+ 文件操作",
    },
    {
        "name": "飞书沟通处理-会议安排",
        "query": "在飞书的 Dazee 突击小队 群聊里问大家什么时候有空开会，确定时间后创建日程",
        "expected_tool": None,
        "expected_action": None,
        "verify_keywords": ["飞书", "群聊", "开会", "日程"],
        "description": "需要飞书 API/App 集成 + 日历操作",
    },
    {
        "name": "自主策略制定-HR联系方式",
        "query": "帮我想办法找到深圳熵基律动科技有限公司的HR的联系方式",
        "expected_tool": None,  # 可能使用 web_search 等
        "expected_action": None,
        "verify_keywords": ["熵基律动", "HR", "联系方式", "深圳"],
        "description": "需要网络搜索 + 信息收集 + 策略规划",
    },
]

# 默认使用基础场景
TEST_SCENARIOS = BASIC_SCENARIOS


# ============================================================
# 测试执行器
# ============================================================

class E2ETestRunner:
    """端对端测试运行器"""
    
    def __init__(self):
        self.agent = None
        self.results = []
    
    async def setup(self):
        """初始化 Agent"""
        from scripts.instance_loader import (
            list_instances,
            create_agent_from_instance
        )
        
        # 检查 client_agent 实例是否存在
        instances = list_instances()
        if "client_agent" not in instances:
            raise RuntimeError(
                "client_agent 实例不存在！\n"
                "请先创建 instances/client_agent/ 目录并配置相关文件。"
            )
        
        print("=" * 60)
        print("🚀 client_agent 端对端验证")
        print("=" * 60)
        print("\n⏳ 正在加载 client_agent 实例...")
        
        # 创建 Agent
        self.agent = await create_agent_from_instance(
            "client_agent",
            skip_mcp_registration=True,  # 跳过 MCP，只测试 nodes
            skip_skills_registration=True,  # 跳过 Skills，只测试 nodes
        )
        
        print("✅ Agent 加载完成\n")
    
    async def run_test(self, scenario: dict) -> dict:
        """运行单个测试场景"""
        name = scenario["name"]
        query = scenario["query"]
        
        print("-" * 60)
        print(f"📋 测试场景: {name}")
        print(f"👤 用户输入: {query}")
        print("-" * 60)
        
        result = {
            "name": name,
            "query": query,
            "success": False,
            "tool_called": None,
            "response": "",
            "events": [],
            "error": None,
        }
        
        try:
            messages = [{"role": "user", "content": query}]
            response_text = ""
            tool_calls = []
            
            # 🆕 V10.0: 直接调用 agent.chat() 需自行初始化 broadcaster
            # ChatService 场景由 ChatService 初始化
            session_id = f"test_{name.replace(' ', '_').lower()}"
            message_id = f"msg_{session_id}"
            self.agent.broadcaster.start_message(
                session_id=session_id,
                message_id=message_id,
                conversation_id="test_conversation"
            )
            
            # 流式处理响应
            print("\n🤖 Agent 响应: ", end="", flush=True)
            
            async for event in self.agent.chat(messages=messages, session_id=session_id, message_id=message_id):
                event_type = event.get("type", "")
                result["events"].append(event)
                
                # SSE 事件格式处理
                if event_type == "content_start":
                    # 检查是否是 tool_use 类型的 content block
                    # 事件格式: {"type": "content_start", "data": {"content_block": {...}}}
                    data = event.get("data", {})
                    content_block = data.get("content_block", {})
                    block_type = content_block.get("type", "")
                    
                    if block_type == "tool_use":
                        tool_name = content_block.get("name", "unknown")
                        tool_input = content_block.get("input", {})
                        tool_calls.append({
                            "name": tool_name,
                            "input": tool_input,
                        })
                        print(f"\n   🔧 调用工具: {tool_name}")
                        if tool_input:
                            action = tool_input.get("action", "")
                            if action:
                                print(f"      action: {action}")
                            command = tool_input.get("command", [])
                            if command:
                                print(f"      command: {command}")
                    
                    elif block_type == "tool_result":
                        content = content_block.get("content", "")
                        try:
                            tool_result = json.loads(content) if isinstance(content, str) else content
                            success = tool_result.get("success", False)
                            status = "✅ 成功" if success else "❌ 失败"
                            print(f"   📦 工具结果: {status}")
                            if not success and tool_result.get("error"):
                                print(f"      错误: {tool_result.get('error')}")
                        except (json.JSONDecodeError, TypeError):
                            print(f"   📦 工具结果: {content[:100] if content else '无内容'}...")
                
                elif event_type == "content_delta":
                    delta = event.get("delta", "")
                    if isinstance(delta, str) and delta:
                        print(delta, end="", flush=True)
                        response_text += delta
                
                elif event_type == "message_delta":
                    delta = event.get("delta", {})
                    if isinstance(delta, dict):
                        text = delta.get("text", "")
                        if text:
                            print(text, end="", flush=True)
                            response_text += text
                
                elif event_type == "error":
                    error = event.get("error", "unknown")
                    print(f"\n   ❌ 错误: {error}")
                    result["error"] = error
            
            print("\n")
            
            result["response"] = response_text
            result["tool_called"] = tool_calls[0]["name"] if tool_calls else None
            
            # 验证结果
            expected_tool = scenario.get("expected_tool")
            if expected_tool and result["tool_called"] == expected_tool:
                result["success"] = True
                print(f"✅ 验证通过: 调用了预期工具 '{expected_tool}'")
            elif result["tool_called"]:
                print(f"⚠️  调用了工具 '{result['tool_called']}'，预期 '{expected_tool}'")
            else:
                print(f"⚠️  未调用任何工具")
            
        except Exception as e:
            result["error"] = str(e)
            print(f"\n❌ 测试失败: {e}")
            logger.error(f"测试失败: {e}", exc_info=True)
        
        return result
    
    async def run_all(self, scenarios: list = None):
        """运行所有测试场景"""
        scenarios = scenarios or TEST_SCENARIOS
        
        await self.setup()
        
        print("\n" + "=" * 60)
        print(f"📊 开始运行 {len(scenarios)} 个测试场景")
        print("=" * 60 + "\n")
        
        for scenario in scenarios:
            result = await self.run_test(scenario)
            self.results.append(result)
            
            # 等待一下，让 macOS 操作生效
            await asyncio.sleep(2)
        
        self.print_summary()
    
    def print_summary(self):
        """打印测试总结"""
        print("\n" + "=" * 60)
        print("📊 测试总结")
        print("=" * 60)
        
        passed = sum(1 for r in self.results if r["success"])
        total = len(self.results)
        
        for r in self.results:
            status = "✅" if r["success"] else "❌"
            print(f"   {status} {r['name']}")
            if r["error"]:
                print(f"      错误: {r['error']}")
        
        print("-" * 60)
        print(f"通过: {passed}/{total}")
        print("=" * 60)
    
    async def cleanup(self):
        """清理资源"""
        if self.agent and hasattr(self.agent, '_mcp_clients'):
            for client in self.agent._mcp_clients:
                try:
                    await client.disconnect()
                except:
                    pass


# ============================================================
# 单场景快速测试
# ============================================================

async def quick_test(query: str):
    """快速测试单个 query"""
    runner = E2ETestRunner()
    
    try:
        await runner.setup()
        
        result = await runner.run_test({
            "name": "快速测试",
            "query": query,
            "expected_tool": "nodes",
        })
        
        return result
    finally:
        await runner.cleanup()


# ============================================================
# 主入口
# ============================================================

async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="client_agent 端对端验证")
    parser.add_argument("--quick", "-q", type=str, help="快速测试单个 query")
    parser.add_argument("--scenario", "-s", type=int, help="只运行指定场景（编号从 1 开始）")
    parser.add_argument("--advanced", "-a", action="store_true", help="运行高级测试场景（复杂任务）")
    parser.add_argument("--advanced-scenario", "-as", type=int, dest="adv_scenario", help="运行指定的高级场景（编号从 1 开始）")
    parser.add_argument("--list", "-l", action="store_true", help="列出所有测试场景")
    
    args = parser.parse_args()
    
    if args.list:
        print("\n📋 基础测试场景:")
        for i, s in enumerate(BASIC_SCENARIOS, 1):
            print(f"   {i}. {s['name']}")
            print(f"      Query: {s['query']}")
        print("\n📋 高级测试场景 (--advanced):")
        for i, s in enumerate(ADVANCED_SCENARIOS, 1):
            print(f"   {i}. {s['name']}")
            print(f"      Query: {s['query']}")
            if s.get('description'):
                print(f"      描述: {s['description']}")
        return
    
    if args.quick:
        await quick_test(args.quick)
        return
    
    runner = E2ETestRunner()
    
    try:
        # 确定使用哪个场景集
        if args.advanced or args.adv_scenario:
            scenarios = ADVANCED_SCENARIOS
            if args.adv_scenario:
                idx = args.adv_scenario - 1
                if 0 <= idx < len(ADVANCED_SCENARIOS):
                    await runner.run_all([ADVANCED_SCENARIOS[idx]])
                else:
                    print(f"❌ 无效的高级场景编号: {args.adv_scenario}")
                    print(f"   有效范围: 1-{len(ADVANCED_SCENARIOS)}")
                return
            else:
                await runner.run_all(ADVANCED_SCENARIOS)
        elif args.scenario:
            idx = args.scenario - 1
            if 0 <= idx < len(BASIC_SCENARIOS):
                await runner.run_all([BASIC_SCENARIOS[idx]])
            else:
                print(f"❌ 无效的场景编号: {args.scenario}")
                print(f"   有效范围: 1-{len(BASIC_SCENARIOS)}")
        else:
            await runner.run_all(BASIC_SCENARIOS)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
