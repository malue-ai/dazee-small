"""
测试 api_calling 工具的流式执行

这个测试脚本模拟 Agent 调用 api_calling 工具的流程，验证：
1. 工具是否支持流式执行
2. execute_stream 是否正确返回内容
3. 框架如何收集流式结果

使用方式:
    python tests/test_api_calling_stream.py
"""

import asyncio
import json
import sys
import os

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.api_calling import APICallingTool
from core.tool.executor import ToolExecutor


async def test_api_calling_stream_direct():
    """
    直接测试 api_calling 工具的 execute_stream 方法
    """
    print("=" * 60)
    print("测试1: 直接调用 APICallingTool.execute_stream()")
    print("=" * 60)
    
    # 模拟 config.yaml 中的 apis 配置
    apis_config = [
        {
            "name": "coze_api",
            "base_url": "https://api.coze.cn",
            "headers": {
                "Authorization": "Bearer ${COZE_API_KEY}",
                "Content-Type": "application/json"
            },
            "description": "Coze API"
        }
    ]
    
    tool = APICallingTool(apis_config=apis_config)
    
    # 模拟工具调用参数（与终端日志一致）
    tool_input = {
        "api_name": "coze_api",
        "path": "/v1/workflow/stream_run",
        "method": "POST",
        "mode": "stream",
        "body": {
            "workflow_id": "7579565547005837331",
            "parameters": {
                "chart_url": "https://example.com/test.txt",
                "query": "测试查询",
                "language": "中文"
            }
        },
        "session_id": "test_session",
        "user_id": "test_user",
        "conversation_id": "test_conv"
    }
    
    print(f"\n📤 工具输入参数:\n{json.dumps(tool_input, ensure_ascii=False, indent=2)}")
    
    # 检查 execute_stream 是否存在
    print(f"\n🔍 检查工具方法:")
    print(f"  - execute 方法: {hasattr(tool, 'execute')}")
    print(f"  - execute_stream 方法: {hasattr(tool, 'execute_stream')}")
    print(f"  - execute_stream 是否可调用: {callable(getattr(tool, 'execute_stream', None))}")
    
    # 测试 execute_stream
    print(f"\n🌊 调用 execute_stream():")
    accumulated = ""
    chunk_count = 0
    
    try:
        async for chunk in tool.execute_stream(**tool_input):
            chunk_count += 1
            accumulated += chunk
            print(f"  Chunk {chunk_count}: {chunk[:100]}..." if len(chunk) > 100 else f"  Chunk {chunk_count}: {chunk}")
    except Exception as e:
        print(f"  ❌ 执行异常: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print(f"\n📊 流式执行结果:")
    print(f"  - 总 chunk 数: {chunk_count}")
    print(f"  - 累积内容长度: {len(accumulated)}")
    print(f"  - 累积内容是否为空: {accumulated == ''}")
    
    if accumulated:
        print(f"\n📝 累积内容预览 (前 500 字符):")
        print(accumulated[:500])


async def test_tool_executor_stream():
    """
    测试 ToolExecutor 的流式执行
    """
    print("\n" + "=" * 60)
    print("测试2: 通过 ToolExecutor 调用 execute_stream()")
    print("=" * 60)
    
    # 加载工具配置
    from utils.config_loader import load_agent_config
    
    # 尝试加载默认 agent 配置
    try:
        config = load_agent_config("zeno_agent")
        print(f"✅ 加载 zeno_agent 配置成功")
    except Exception as e:
        print(f"⚠️ 加载 zeno_agent 配置失败: {e}")
        print("尝试加载 test_agent 配置...")
        try:
            config = load_agent_config("test_agent")
            print(f"✅ 加载 test_agent 配置成功")
        except Exception as e2:
            print(f"❌ 加载配置失败: {e2}")
            return
    
    # 获取 apis 配置
    apis_config = config.get("apis", [])
    print(f"📋 APIs 配置数量: {len(apis_config)}")
    for api in apis_config:
        print(f"  - {api.get('name')}: {api.get('base_url', 'N/A')}")
    
    # 创建 ToolExecutor
    executor = ToolExecutor()
    
    # 注册 api_calling 工具
    api_tool = APICallingTool(apis_config=apis_config)
    executor._tool_instances["api_calling"] = api_tool
    
    # 检查是否支持流式
    print(f"\n🔍 检查工具流式支持:")
    supports_stream = executor.supports_stream("api_calling")
    print(f"  - api_calling 支持流式: {supports_stream}")
    
    if not supports_stream:
        print("  ⚠️ 工具不支持流式执行，测试结束")
        return
    
    # 测试流式执行
    tool_input = {
        "api_name": "coze_api",
        "path": "/v1/workflow/stream_run",
        "method": "POST",
        "mode": "stream",
        "body": {
            "workflow_id": "7579565547005837331",
            "parameters": {
                "query": "测试"
            }
        }
    }
    
    print(f"\n🌊 通过 ToolExecutor 执行流式调用:")
    accumulated = ""
    chunk_count = 0
    
    try:
        async for chunk in executor.execute_stream("api_calling", tool_input):
            chunk_count += 1
            accumulated += chunk
            print(f"  Chunk {chunk_count}: {chunk[:80]}..." if len(chunk) > 80 else f"  Chunk {chunk_count}: {chunk}")
    except Exception as e:
        print(f"  ❌ 执行异常: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print(f"\n📊 ToolExecutor 流式结果:")
    print(f"  - 总 chunk 数: {chunk_count}")
    print(f"  - 累积内容长度: {len(accumulated)}")
    print(f"  - 累积内容是否为空: {accumulated == ''}")


async def test_simulate_agent_flow():
    """
    模拟 Agent 的工具调用流程，验证 tool_result 如何被收集
    """
    print("\n" + "=" * 60)
    print("测试3: 模拟 Agent 流式工具调用流程")
    print("=" * 60)
    
    # 模拟 simple_agent.py 中的流式执行逻辑
    print("""
📋 Agent 流式工具执行流程分析:

1. chat() 方法中收集 tool_result:
   ```python
   # 第 798-802 行
   if tool_event.get("type") == "content_start":
       content_block = tool_event.get("data", {}).get("content_block", {})
       if content_block.get("type") == "tool_result":
           tool_results.append(content_block)
   ```

2. 流式执行时 (第 1428-1458 行):
   ```python
   # 发送 content_start，content 为空!
   tool_result_block = {
       "type": "tool_result",
       "tool_use_id": tool_id,
       "content": "",  # <-- 问题在这里！
       "is_error": False
   }
   yield await self.broadcaster.emit_content_start(...)
   
   # 流式发送 delta
   async for chunk in self.tool_executor.execute_stream(...):
       accumulated_result += chunk
       yield await self.broadcaster.emit_content_delta(...)  # delta 没有被收集！
   
   yield await self.broadcaster.emit_content_stop(...)
   continue  # <-- 直接跳过，没有更新 content_start 的 content
   ```

3. 问题根源:
   - content_start 发送时 content=""
   - content_delta 发送的内容没有被收集到 tool_results
   - 发送给 LLM 的 tool_result.content 是空的
    """)
    
    print("\n🔧 修复方案:")
    print("""
方案1: 在流式执行完成后，发送一个带完整内容的 content_start 事件（推荐）
       - 在 continue 之前，再发一个 content_start 事件
       - 这个事件的 content 是累积的完整结果
       
方案2: 修改 chat() 中的收集逻辑
       - 从 content_delta 累积内容
       - 在 content_stop 时将累积内容合并到 tool_result
    """)


async def main():
    """运行所有测试"""
    print("🧪 API Calling 流式执行测试")
    print("=" * 60)
    
    # 测试1: 直接测试工具
    await test_api_calling_stream_direct()
    
    # 测试2: 通过 ToolExecutor 测试
    await test_tool_executor_stream()
    
    # 测试3: 模拟 Agent 流程分析
    await test_simulate_agent_flow()
    
    print("\n" + "=" * 60)
    print("✅ 测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

