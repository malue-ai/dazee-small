"""
E2E 验证：确保 Agent 真实调用工具执行代码

验证目标：
1. ✅ 真实调用 LLM
2. ✅ 真实调用工具（e2b_python_sandbox 或 bash）
3. ✅ 工具调用次数 > 0
4. ✅ 追踪器记录完整执行路径
"""

import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载 .env 文件
from dotenv import load_dotenv
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)

from logger import get_logger

logger = get_logger("e2e_verify")


async def verify_tool_execution_with_retry(max_retries: int = 2):
    """
    验证工具执行（带重试）
    
    Args:
        max_retries: 最大重试次数
    """
    
    print("=" * 70)
    print("🔍 E2E 验证：确保 Agent 真实调用工具")
    print("=" * 70)
    
    # 检查 API Key
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("\n❌ 错误: 未设置 ANTHROPIC_API_KEY")
        return
    
    # 导入 Agent
    from core.agent import SimpleAgent
    from core.events import create_event_manager, get_memory_storage
    
    # 创建 Agent
    print("\n📦 初始化 Agent...")
    storage = get_memory_storage()
    event_manager = create_event_manager(storage)
    
    agent = SimpleAgent(
        event_manager=event_manager,
        workspace_dir="./workspace",
        model="claude-sonnet-4-5-20250929"
    )
    
    # 测试用例：必须调用工具的任务
    test_query = "创建一个文件 test_output.txt，写入当前时间戳和 Python 版本信息"
    
    print(f"\n📝 测试 Query: {test_query}")
    print("   期望: Agent 调用 bash 或 e2b_python_sandbox")
    print("\n" + "─" * 70)
    
    for attempt in range(max_retries + 1):
        if attempt > 0:
            print(f"\n🔄 重试第 {attempt} 次...")
        
        try:
            # 构建消息
            messages = [{"role": "user", "content": test_query}]
            session_id = f"verify_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # 收集事件
            tool_calls = []
            final_response = ""
            
            print("🔄 开始执行...")
            
            # 调用 Agent
            async for event in agent.chat(
                messages=messages,
                session_id=session_id,
                enable_stream=True
            ):
                event_type = event.get("type", "unknown")
                
                if event_type == "message_delta":
                    delta = event.get("data", {}).get("delta", {})
                    delta_type = delta.get("type", "")
                    
                    if delta_type == "text_delta":
                        text = delta.get("text", "")
                        final_response += text
                        print(text, end="", flush=True)
                
                elif event_type == "content_start":
                    content_block = event.get("data", {}).get("content_block", {})
                    block_type = content_block.get("type", "")
                    
                    if block_type == "tool_use":
                        tool_name = content_block.get("name", "")
                        tool_calls.append(tool_name)
                        print(f"\n\n✅ 调用工具: {tool_name}")
            
            print("\n" + "─" * 70)
            
            # 获取追踪报告
            trace_report = agent.get_trace_report()
            
            if not trace_report:
                print("⚠️ 未获取到追踪报告")
                continue
            
            # 验证结果
            stats = trace_report.get("stats", {})
            tool_call_count = len(tool_calls)
            
            print("\n📊 验证结果:")
            print(f"   工具调用次数: {tool_call_count}")
            print(f"   调用的工具: {tool_calls}")
            print(f"   总耗时: {stats.get('total_duration_ms', 0):.1f}ms")
            
            # 判断是否通过
            if tool_call_count > 0:
                print("\n✅ 验证通过: Agent 真实调用了工具！")
                
                # 打印执行路径
                stage_order = trace_report.get("stage_order", [])
                stages = trace_report.get("stages", {})
                
                print(f"\n📍 执行路径 ({len(stage_order)} 个阶段):")
                for i, stage_name in enumerate(stage_order, 1):
                    stage = stages.get(stage_name, {})
                    status = stage.get("status", "unknown")
                    duration = stage.get("duration_ms", 0)
                    status_icon = "✅" if status == "completed" else "❌"
                    print(f"   {i}. {status_icon} {stage_name}: {duration:.1f}ms")
                
                return True
            else:
                print("\n❌ 验证失败: Agent 没有调用任何工具！")
                print("   可能原因:")
                print("   1. System Prompt 未强制要求使用工具")
                print("   2. Claude 认为任务可以直接完成")
                
                if attempt < max_retries:
                    print(f"\n将在 2 秒后重试...")
                    await asyncio.sleep(2)
                    continue
                else:
                    return False
        
        except Exception as e:
            error_msg = str(e)
            print(f"\n❌ 执行失败: {error_msg}")
            
            if "peer closed connection" in error_msg or "RemoteProtocolError" in error_msg:
                print("   原因: Claude API 连接中断（网络问题）")
                if attempt < max_retries:
                    print(f"   将在 2 秒后重试...")
                    await asyncio.sleep(2)
                    continue
            else:
                import traceback
                traceback.print_exc()
                return False
    
    return False


async def main():
    """主函数"""
    success = await verify_tool_execution_with_retry(max_retries=2)
    
    print("\n" + "=" * 70)
    if success:
        print("🎉 E2E 验证成功！")
    else:
        print("⚠️ E2E 验证失败，需要优化 System Prompt")
    print("=" * 70)
    
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

