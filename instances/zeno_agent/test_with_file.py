#!/usr/bin/env python3
"""
测试 ZenO Agent 带文件的请求
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


async def main():
    from scripts.instance_loader import create_agent_from_instance
    
    print("⏳ 正在加载 zeno_agent...")
    agent = await create_agent_from_instance("zeno_agent")
    print("✅ 加载完成\n")
    
    # 模拟带文件的消息
    # 注意：这里需要一个真实可访问的文件 URL
    messages = [
        {
            "role": "user",
            "content": "帮我分析一下这份反馈数据，有多少条待解决的问题？",
            # 模拟文件信息（实际使用时需要替换为真实 URL）
            "files": [
                {
                    "file_name": "用户反馈列表.png",
                    "file_url": "https://example.com/feedback.png"  # 替换为真实 URL
                }
            ]
        }
    ]
    
    print("👤 用户: 帮我分析一下这份反馈数据，有多少条待解决的问题？")
    print("📎 附件: 用户反馈列表.png")
    print("\n🤖 助手: ", end="", flush=True)
    
    try:
        async for event in agent.chat(messages=messages):
            event_type = event.get("type", "")
            
            if event_type == "message_delta":
                delta = event.get("delta", {})
                text = delta.get("text", "")
                if text:
                    print(text, end="", flush=True)
            
            elif event_type == "tool_use":
                tool_name = event.get("tool_name", "unknown")
                print(f"\n   🔧 调用工具: {tool_name}", flush=True)
            
            elif event_type == "tool_result":
                status = event.get("status", "unknown")
                print(f"   ✓ 工具完成: {status}", flush=True)
        
        print()
    except Exception as e:
        print(f"\n❌ 错误: {e}")


if __name__ == "__main__":
    asyncio.run(main())

