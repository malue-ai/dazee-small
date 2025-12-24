"""
Agent V3 流式输出示例

演示如何使用流式输出功能，实时显示智能体的工作进度。
"""

import asyncio
import os
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from agent_v3.core.agent import create_simple_agent


async def simple_streaming_example():
    """简单流式输出示例"""
    print("=" * 60)
    print("示例 1: 简单流式输出")
    print("=" * 60)
    
    agent = create_simple_agent(verbose=False)
    
    user_input = "今天深圳天气怎么样？"
    
    print(f"\n用户: {user_input}\n")
    print("-" * 60)
    
    async for event in agent.stream(user_input):
        event_type = event["type"]
        data = event["data"]
        
        if event_type == "content":
            # 实时输出回复内容
            print(data['text'], end="", flush=True)
        
        elif event_type == "tool_call_start":
            print(f"\n\n🔧 执行工具: {data['tool_name']}")
        
        elif event_type == "complete":
            print(f"\n\n✅ 完成")
    
    print("\n" + "=" * 60 + "\n")


async def detailed_streaming_example():
    """详细流式输出示例（显示所有事件）"""
    print("=" * 60)
    print("示例 2: 详细流式输出（显示所有事件）")
    print("=" * 60)
    
    agent = create_simple_agent(verbose=False)
    
    user_input = "帮我搜索一下AI Agent的最新发展"
    
    print(f"\n用户: {user_input}\n")
    print("-" * 60)
    
    async for event in agent.stream(user_input):
        event_type = event["type"]
        data = event["data"]
        timestamp = event["timestamp"]
        
        if event_type == "status":
            print(f"\n📊 {data['message']}")
        
        elif event_type == "thinking":
            # 可选：显示思考过程（可能很长）
            # print(f"💭 {data['text'][:50]}...", end="", flush=True)
            pass
        
        elif event_type == "content":
            print(data['text'], end="", flush=True)
        
        elif event_type == "tool_call_start":
            print(f"\n\n🔧 开始执行: {data['tool_name']}")
            if data.get('input'):
                print(f"   输入: {data['input']}")
        
        elif event_type == "tool_call_progress":
            status = data['status']
            tool_name = data['tool_name']
            if status == "executing":
                print(f"   ⏳ {tool_name} 执行中...")
            elif status == "completed":
                print(f"   ✅ {tool_name} 完成")
            elif status == "failed":
                error = data.get('data', {}).get('error', '未知错误')
                print(f"   ❌ {tool_name} 失败: {error}")
        
        elif event_type == "plan_update":
            progress = data['progress']
            bar_length = 30
            filled = int(bar_length * progress['progress'])
            bar = '█' * filled + '░' * (bar_length - filled)
            print(f"\n📋 进度: [{bar}] {progress['completed']}/{progress['total']} ({progress['progress']*100:.0f}%)")
        
        elif event_type == "complete":
            print(f"\n\n✅ 任务完成！")
            print(f"总轮次: {data.get('turns', 0)}")
        
        elif event_type == "error":
            print(f"\n❌ 错误: {data['error']}")
            print(f"阶段: {data.get('stage', 'unknown')}")
    
    print("\n" + "=" * 60 + "\n")


async def progress_tracking_example():
    """进度跟踪示例（只显示关键进度）"""
    print("=" * 60)
    print("示例 3: 进度跟踪（只显示关键进度）")
    print("=" * 60)
    
    agent = create_simple_agent(verbose=False)
    
    user_input = "帮我生成一个关于AI技术的PPT，包含5页内容"
    
    print(f"\n用户: {user_input}\n")
    print("-" * 60)
    
    last_progress = None
    content_buffer = ""
    
    async for event in agent.stream(user_input):
        event_type = event["type"]
        data = event["data"]
        
        if event_type == "status":
            print(f"\n📊 {data['message']}")
        
        elif event_type == "content":
            # 收集内容，最后一起显示
            content_buffer += data['text']
        
        elif event_type == "tool_call_start":
            print(f"\n🔧 执行: {data['tool_name']}")
        
        elif event_type == "plan_update":
            progress = data['progress']
            current_progress = progress['progress']
            
            # 只在进度变化时更新
            if last_progress != current_progress:
                bar_length = 20
                filled = int(bar_length * current_progress)
                bar = '█' * filled + '░' * (bar_length - filled)
                print(f"📋 [{bar}] {progress['completed']}/{progress['total']} ({current_progress*100:.0f}%)")
                last_progress = current_progress
        
        elif event_type == "complete":
            # 显示收集的内容
            if content_buffer:
                print(f"\n\n回复内容:\n{content_buffer}")
            print(f"\n✅ 完成！总轮次: {data.get('turns', 0)}")
    
    print("\n" + "=" * 60 + "\n")


async def callback_example():
    """使用回调函数的示例"""
    print("=" * 60)
    print("示例 4: 使用回调函数")
    print("=" * 60)
    
    # 事件统计
    event_stats = {
        "thinking": 0,
        "content": 0,
        "tool_calls": 0,
        "plan_updates": 0
    }
    
    def on_event_callback(event: dict):
        """事件回调函数"""
        event_type = event["type"]
        
        # 统计事件
        if event_type in event_stats:
            event_stats[event_type] += 1
        
        # 特殊处理某些事件
        if event_type == "error":
            print(f"\n⚠️ 错误回调: {event['data']['error']}")
    
    agent = create_simple_agent(verbose=False)
    
    user_input = "今天天气怎么样？"
    
    print(f"\n用户: {user_input}\n")
    print("-" * 60)
    
    async for event in agent.stream(user_input, on_event=on_event_callback):
        event_type = event["type"]
        data = event["data"]
        
        if event_type == "content":
            print(data['text'], end="", flush=True)
        
        elif event_type == "tool_call_start":
            print(f"\n\n🔧 {data['tool_name']}")
    
    # 显示统计
    print(f"\n\n📊 事件统计:")
    for event_type, count in event_stats.items():
        if count > 0:
            print(f"   {event_type}: {count}")
    
    print("\n" + "=" * 60 + "\n")


async def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("Agent V3 流式输出示例")
    print("=" * 60)
    print("\n这些示例展示了如何使用流式输出功能，实时显示智能体的工作进度。")
    print("一切以用户体验为中心，不让用户长时间等待！\n")
    
    # 运行示例
    examples = [
        ("简单流式输出", simple_streaming_example),
        ("详细流式输出", detailed_streaming_example),
        ("进度跟踪", progress_tracking_example),
        ("回调函数", callback_example),
    ]
    
    print("可用示例:")
    for i, (name, _) in enumerate(examples, 1):
        print(f"  {i}. {name}")
    
    print("\n选择要运行的示例（1-4），或按 Enter 运行所有示例:")
    choice = input().strip()
    
    if choice == "":
        # 运行所有示例
        for name, func in examples:
            print(f"\n{'='*60}")
            print(f"运行示例: {name}")
            print('='*60)
            try:
                await func()
            except Exception as e:
                print(f"\n❌ 示例运行出错: {e}")
                import traceback
                traceback.print_exc()
    else:
        # 运行指定示例
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(examples):
                name, func = examples[idx]
                await func()
            else:
                print("无效的选择")
        except ValueError:
            print("请输入数字")


if __name__ == "__main__":
    # 检查 API Key
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("⚠️  警告: 未设置 ANTHROPIC_API_KEY 环境变量")
        print("请设置环境变量后再运行示例")
        sys.exit(1)
    
    asyncio.run(main())

