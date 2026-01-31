#!/usr/bin/env python3
"""
Client Agent 端到端验证脚本 - 屏幕抓图场景

验证目标：
1. 调用链验证：ChatService.chat() → _run_agent() → AgentRouter.route() → SimpleAgent.chat() → _run_rvr_loop()
2. Skills 延迟加载：验证 peekaboo 等 Skills 是否正确注入
3. Nodes 工具：验证 screencapture 命令执行
4. 事件流：验证 EventBroadcaster 事件推送

测试场景：
- 屏幕截图到桌面
- 截取当前窗口
- 截图后分析内容
"""

import asyncio
import sys
import os
import json
from pathlib import Path
from datetime import datetime

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from logger import get_logger

logger = get_logger("e2e.client_agent.screenshot")


async def test_screenshot_basic():
    """测试基础截图功能 - 使用 nodes 工具调用 screencapture"""
    print("\n" + "=" * 60)
    print("测试 1: 基础屏幕截图")
    print("=" * 60)
    
    from core.nodes.manager import init_node_manager
    
    # 初始化节点管理器
    node_manager = await init_node_manager()
    
    # 截图保存路径
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_path = f"/tmp/zenflux_test_screenshot_{timestamp}.png"
    
    # 使用 screencapture 命令
    command = ["screencapture", "-x", screenshot_path]  # -x 禁用声音
    
    print(f"📸 执行命令: {' '.join(command)}")
    
    result = await node_manager.run_command(
        command=command,
        timeout_ms=10000
    )
    
    # NodeInvokeResponse: ok, payload, error
    exit_code = result.payload.get("exit_code") if result.payload else -1
    print(f"执行结果: ok={result.ok}, exit_code={exit_code}")
    
    if result.error:
        print(f"错误: {result.error}")
    
    # 验证截图是否成功
    if os.path.exists(screenshot_path):
        file_size = os.path.getsize(screenshot_path)
        print(f"✅ 截图成功: {screenshot_path} ({file_size} bytes)")
        
        # 清理测试文件
        os.remove(screenshot_path)
        print(f"🧹 已清理测试文件")
        return True
    else:
        print(f"❌ 截图失败: 文件不存在")
        if result.payload:
            print(f"   stdout: {result.payload.get('stdout', '')}")
            print(f"   stderr: {result.payload.get('stderr', '')}")
        return False


async def test_instance_loader():
    """测试 instance_loader 调用链"""
    print("\n" + "=" * 60)
    print("测试 2: Instance Loader 调用链验证")
    print("=" * 60)
    
    from scripts.instance_loader import create_agent_from_instance
    
    try:
        # 加载 client_agent 实例
        print("📦 加载 client_agent 实例...")
        agent = await create_agent_from_instance(
            instance_name="client_agent",
            skip_mcp_registration=True,  # 跳过 MCP 注册，加快测试
        )
        
        print(f"✅ Agent 加载成功")
        print(f"   - 类型: {type(agent).__name__}")
        print(f"   - 模型: {getattr(agent, 'model', 'N/A')}")
        print(f"   - Max Turns: {getattr(agent, 'max_turns', 'N/A')}")
        
        # 验证 prompt_cache
        if hasattr(agent, 'prompt_cache') and agent.prompt_cache:
            print(f"   - Prompt Cache: ✅ 已加载")
            
            # 检查系统提示词中是否包含 Skills
            system_prompt = agent.prompt_cache.get_system_prompt("medium")
            if system_prompt:
                has_skills = "<available_skills>" in system_prompt
                print(f"   - Skills 注入: {'✅ 包含' if has_skills else '❌ 未包含'}")
                
                # 检查是否包含 peekaboo
                has_peekaboo = "peekaboo" in system_prompt.lower()
                print(f"   - Peekaboo Skill: {'✅ 包含' if has_peekaboo else '⚠️ 未包含（可能依赖未满足）'}")
        else:
            print(f"   - Prompt Cache: ❌ 未加载")
        
        return True
        
    except Exception as e:
        print(f"❌ Agent 加载失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_skills_lazy_loading():
    """测试 Skills 延迟加载机制"""
    print("\n" + "=" * 60)
    print("测试 3: Skills 延迟加载验证")
    print("=" * 60)
    
    from scripts.instance_loader import load_instance_config, _format_skills_for_prompt, _check_skill_eligibility
    
    try:
        # 加载配置
        config = load_instance_config("client_agent")
        
        print(f"📋 实例配置:")
        print(f"   - 名称: {config.name}")
        print(f"   - Skills 总数: {len(config.skills)}")
        
        # 检查 skill_loading 配置
        skill_loading = config.raw_config.get("skill_loading", {})
        loading_mode = skill_loading.get("mode", "lazy")
        print(f"   - 加载模式: {loading_mode}")
        
        # 统计启用和满足依赖的 Skills
        enabled_skills = [s for s in config.skills if s.enabled]
        eligible_skills = [s for s in enabled_skills if _check_skill_eligibility(s)]
        
        print(f"\n📊 Skills 统计:")
        print(f"   - 启用: {len(enabled_skills)}")
        print(f"   - 满足依赖: {len(eligible_skills)}")
        print(f"   - 过滤掉: {len(enabled_skills) - len(eligible_skills)}")
        
        # 检查屏幕相关 Skills
        screen_skills = ["peekaboo", "camsnap", "video-frames"]
        print(f"\n🖥️ 屏幕相关 Skills:")
        for skill_name in screen_skills:
            skill = next((s for s in config.skills if s.name == skill_name), None)
            if skill:
                is_eligible = _check_skill_eligibility(skill)
                status = "✅ 可用" if is_eligible else "⚠️ 依赖未满足"
                print(f"   - {skill_name}: {status}")
            else:
                print(f"   - {skill_name}: ❌ 未配置")
        
        # 生成 Skills Prompt
        runtime_env_config = config.raw_config.get("runtime_environment", {})
        language = runtime_env_config.get("language", "zh")
        
        skills_prompt = _format_skills_for_prompt(
            instance_name="client_agent",
            skills=enabled_skills,
            loading_mode=loading_mode,
            language=language
        )
        
        print(f"\n📝 Skills Prompt:")
        print(f"   - 长度: {len(skills_prompt)} 字符")
        print(f"   - 包含 <available_skills>: {'✅' if '<available_skills>' in skills_prompt else '❌'}")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_routing_decision():
    """测试路由决策（截图场景）"""
    print("\n" + "=" * 60)
    print("测试 4: 路由决策验证（截图场景）")
    print("=" * 60)
    
    from core.routing import AgentRouter
    from core.llm import create_llm_service
    
    try:
        # 创建路由器
        llm = create_llm_service(model="claude-sonnet-4-5-20250929")
        router = AgentRouter(llm_service=llm)
        
        # 测试截图相关查询
        test_queries = [
            "帮我截取当前屏幕",
            "把屏幕截图保存到桌面",
            "截取 Safari 浏览器窗口的截图",
        ]
        
        for query in test_queries:
            print(f"\n📝 查询: {query}")
            
            decision = await router.route(
                user_query=query,
                conversation_history=[]
            )
            
            print(f"   - Agent 类型: {decision.agent_type}")
            print(f"   - 执行策略: {decision.execution_strategy}")
            if decision.intent:
                print(f"   - 任务类型: {decision.intent.task_type.value}")
                print(f"   - 复杂度: {getattr(decision.intent, 'complexity_score', 'N/A')}")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_full_e2e_screenshot():
    """完整端到端测试：从用户查询到截图执行"""
    print("\n" + "=" * 60)
    print("测试 5: 完整端到端截图测试")
    print("=" * 60)
    
    from scripts.instance_loader import create_agent_from_instance
    from core.events.manager import EventManager
    from uuid import uuid4
    
    try:
        # 创建事件管理器
        event_manager = EventManager()
        
        # 加载 Agent
        print("📦 加载 client_agent...")
        agent = await create_agent_from_instance(
            instance_name="client_agent",
            event_manager=event_manager,
            skip_mcp_registration=True,
        )
        
        # 准备测试消息
        session_id = f"test_{uuid4().hex[:8]}"
        message_id = f"msg_{uuid4().hex[:8]}"
        
        # 初始化 broadcaster
        agent.broadcaster.start_message(session_id, message_id, "test_conversation")
        
        # 测试查询
        test_message = [{"role": "user", "content": "使用 screencapture 命令截取当前屏幕，保存到 /tmp/test_screenshot.png"}]
        
        print(f"\n📝 测试查询: {test_message[0]['content']}")
        print(f"   - Session ID: {session_id}")
        print(f"   - Message ID: {message_id}")
        
        # 执行 Agent
        print("\n🚀 执行 Agent...")
        events = []
        async for event in agent.chat(
            messages=test_message,
            session_id=session_id,
            message_id=message_id,
            enable_stream=True
        ):
            events.append(event)
            event_type = event.get("type", "unknown")
            if event_type in ["content_start", "tool_use", "message_stop"]:
                print(f"   📡 事件: {event_type}")
        
        print(f"\n📊 事件统计:")
        print(f"   - 总事件数: {len(events)}")
        
        # 检查是否有工具调用
        tool_events = [e for e in events if e.get("type") == "tool_use"]
        print(f"   - 工具调用: {len(tool_events)}")
        
        for tool_event in tool_events:
            tool_name = tool_event.get("tool_name", "unknown")
            print(f"     - {tool_name}")
        
        # 检查截图是否成功
        if os.path.exists("/tmp/test_screenshot.png"):
            file_size = os.path.getsize("/tmp/test_screenshot.png")
            print(f"\n✅ 截图成功: /tmp/test_screenshot.png ({file_size} bytes)")
            os.remove("/tmp/test_screenshot.png")
            print("🧹 已清理测试文件")
            return True
        else:
            print("\n⚠️ 截图文件未找到（可能 Agent 未执行截图命令）")
            return False
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主测试入口"""
    print("=" * 60)
    print("Client Agent 端到端验证 - 屏幕抓图场景")
    print("=" * 60)
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"平台: {sys.platform}")
    
    results = {}
    
    # 测试 1: 基础截图
    results["screenshot_basic"] = await test_screenshot_basic()
    
    # 测试 2: Instance Loader
    results["instance_loader"] = await test_instance_loader()
    
    # 测试 3: Skills 延迟加载
    results["skills_lazy_loading"] = await test_skills_lazy_loading()
    
    # 测试 4: 路由决策（需要 API Key，可选）
    if os.environ.get("ANTHROPIC_API_KEY"):
        results["routing_decision"] = await test_routing_decision()
    else:
        print("\n⚠️ 跳过路由决策测试（未设置 ANTHROPIC_API_KEY）")
        results["routing_decision"] = None
    
    # 测试 5: 完整端到端（需要 API Key，可选）
    if os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("RUN_FULL_E2E", "false").lower() == "true":
        results["full_e2e"] = await test_full_e2e_screenshot()
    else:
        print("\n⚠️ 跳过完整端到端测试（设置 RUN_FULL_E2E=true 启用）")
        results["full_e2e"] = None
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    for test_name, result in results.items():
        if result is None:
            status = "⏭️ 跳过"
        elif result:
            status = "✅ 通过"
        else:
            status = "❌ 失败"
        print(f"  {test_name}: {status}")
    
    # 返回是否全部通过
    failed = [k for k, v in results.items() if v is False]
    if failed:
        print(f"\n❌ {len(failed)} 个测试失败")
        return 1
    else:
        print(f"\n✅ 所有测试通过")
        return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
