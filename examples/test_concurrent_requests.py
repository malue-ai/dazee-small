"""
测试并发请求 - 验证修复后其他接口不再被阻塞

问题描述：
之前在使用 Agent 聊天时，其他接口处于阻塞状态。
这是因为 LLM 的流式调用使用了同步 API，阻塞了事件循环。

修复方案：
1. 将 create_message_stream 改为异步生成器（使用 AsyncClient）
2. 将 agent.chat() 中的 for 循环改为 async for

测试方法：
同时发送：
1. 一个需要长时间生成的聊天请求（Agent）
2. 多个简单的 API 请求（如获取对话列表）
  
验证：
- 修复前：简单 API 请求会等待 Agent 完成才返回（阻塞）
- 修复后：简单 API 请求立即返回（不阻塞）
"""

import asyncio
import httpx
import time
from datetime import datetime


BASE_URL = "http://localhost:8000/api"


async def send_long_chat_request(user_id: str):
    """发送一个需要长时间生成的聊天请求"""
    print(f"\n{'='*60}")
    print(f"[长请求] 开始发送聊天请求...")
    print(f"{'='*60}")
    
    start_time = time.time()
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            # 发送流式请求（不等待完成）
            async with client.stream(
                "POST",
                f"{BASE_URL}/v1/chat",
                json={
                    "message": "帮我写一篇 5000 字的文章，关于人工智能的未来发展。请详细展开，包含多个章节。",
                    "user_id": user_id,
                    "stream": True
                },
                headers={"Accept": "text/event-stream"}
            ) as response:
                print(f"[长请求] ✅ SSE 连接已建立: {response.status_code}")
                
                # 读取几个事件后就返回（不等待全部完成）
                event_count = 0
                async for line in response.aiter_lines():
                    if line.startswith('data:'):
                        event_count += 1
                        if event_count <= 3:
                            print(f"[长请求] 📨 收到事件 #{event_count}")
                        
                        # 只读取前 5 个事件就返回
                        if event_count >= 5:
                            print(f"[长请求] ⏸️ 已读取 {event_count} 个事件，停止读取（Agent 继续在后台运行）")
                            break
                
                elapsed = time.time() - start_time
                print(f"[长请求] ⏱️ 耗时: {elapsed:.2f}s")
                
        except Exception as e:
            print(f"[长请求] ❌ 失败: {e}")


async def send_simple_api_request(request_id: int, user_id: str):
    """发送一个简单的 API 请求（应该立即返回）"""
    print(f"\n[短请求 #{request_id}] 开始...")
    start_time = time.time()
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # 获取对话列表（简单快速的请求）
            response = await client.get(
                f"{BASE_URL}/v1/conversations",
                params={"user_id": user_id, "limit": 20}
            )
            
            elapsed = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                conv_count = len(data.get("data", {}).get("conversations", []))
                print(f"[短请求 #{request_id}] ✅ 成功: {conv_count} 个对话, 耗时: {elapsed:.2f}s")
                
                # 🎯 关键检查：如果耗时超过 1 秒，说明被阻塞了
                if elapsed > 1.0:
                    print(f"[短请求 #{request_id}] ⚠️  警告: 响应时间过长 ({elapsed:.2f}s)，可能被阻塞！")
                    return False
                else:
                    print(f"[短请求 #{request_id}] ✅ 响应快速，没有被阻塞")
                    return True
            else:
                print(f"[短请求 #{request_id}] ❌ 失败: {response.status_code}")
                return False
                
        except httpx.TimeoutException:
            elapsed = time.time() - start_time
            print(f"[短请求 #{request_id}] ❌ 超时: {elapsed:.2f}s - 被阻塞！")
            return False
        except Exception as e:
            elapsed = time.time() - start_time
            print(f"[短请求 #{request_id}] ❌ 失败 ({elapsed:.2f}s): {e}")
            return False


async def test_concurrent_requests():
    """
    测试并发请求
    
    测试策略：
    1. 启动一个长时间运行的 Agent 请求（流式）
    2. 在 Agent 运行期间，发送多个简单的 API 请求
    3. 检查简单请求是否能快速返回（< 1秒）
    
    预期结果：
    - 修复前：简单请求会等待 Agent 完成（被阻塞）
    - 修复后：简单请求立即返回（不被阻塞）
    """
    print("\n" + "="*60)
    print("并发请求测试 - 验证修复效果")
    print("="*60)
    
    user_id = f"test_concurrent_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # 先创建一个测试对话（确保有数据）
    print(f"\n📝 准备测试数据...")
    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"{BASE_URL}/v1/conversations",
                params={"user_id": user_id, "title": "测试对话"}
            )
            print("✅ 测试数据已准备")
        except Exception as e:
            print(f"⚠️  准备测试数据失败（可能已存在）: {e}")
    
    # 启动测试
    print(f"\n🚀 开始并发测试...")
    print(f"策略：")
    print(f"  1. 启动长时间 Agent 请求（流式）")
    print(f"  2. 等待 0.5 秒（确保 Agent 开始执行）")
    print(f"  3. 发送 5 个简单 API 请求")
    print(f"  4. 检查简单请求是否被阻塞")
    
    # 创建任务列表
    tasks = []
    
    # 任务 1: 长时间 Agent 请求
    tasks.append(asyncio.create_task(send_long_chat_request(user_id)))
    
    # 等待 Agent 开始执行
    await asyncio.sleep(0.5)
    
    # 任务 2-6: 5 个简单 API 请求（间隔 0.2 秒）
    for i in range(5):
        await asyncio.sleep(0.2)
        tasks.append(asyncio.create_task(send_simple_api_request(i + 1, user_id)))
    
    # 等待所有简单请求完成（不等待长请求）
    simple_results = await asyncio.gather(*tasks[1:])  # 只等待简单请求
    
    # 统计结果
    print(f"\n" + "="*60)
    print("测试结果")
    print("="*60)
    
    success_count = sum(1 for r in simple_results if r)
    total_count = len(simple_results)
    
    print(f"\n📊 简单请求统计:")
    print(f"  - 总数: {total_count}")
    print(f"  - 成功（未阻塞）: {success_count}")
    print(f"  - 失败（被阻塞）: {total_count - success_count}")
    
    if success_count == total_count:
        print(f"\n✅ 测试通过！所有简单请求都快速返回，没有被 Agent 阻塞")
        print(f"✅ 修复成功！异步并发工作正常")
    elif success_count > 0:
        print(f"\n⚠️  部分通过：{success_count}/{total_count} 个请求未被阻塞")
        print(f"可能是网络延迟或服务器负载导致")
    else:
        print(f"\n❌ 测试失败！所有简单请求都被阻塞")
        print(f"❌ 问题仍然存在，需要进一步检查")
    
    # 取消长请求任务（如果还在运行）
    if not tasks[0].done():
        tasks[0].cancel()
        try:
            await tasks[0]
        except asyncio.CancelledError:
            pass


async def test_simple_case():
    """
    简单测试：只发送 2 个并发请求
    更容易看出是否有阻塞问题
    """
    print("\n" + "="*60)
    print("简单并发测试（2 个请求）")
    print("="*60)
    
    user_id = f"test_simple_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    print(f"\n策略：")
    print(f"  1. 同时发送 2 个获取对话列表的请求")
    print(f"  2. 检查是否都能快速返回（< 0.5 秒）")
    
    start_time = time.time()
    
    # 同时发送 2 个请求
    results = await asyncio.gather(
        send_simple_api_request(1, user_id),
        send_simple_api_request(2, user_id)
    )
    
    elapsed = time.time() - start_time
    
    print(f"\n📊 结果:")
    print(f"  - 总耗时: {elapsed:.2f}s")
    print(f"  - 成功: {sum(results)}/2")
    
    if elapsed < 1.0 and all(results):
        print(f"\n✅ 测试通过！并发请求工作正常")
    else:
        print(f"\n❌ 测试失败！可能存在阻塞问题")


async def main():
    """主函数"""
    try:
        # 测试 1: 简单并发测试
        await test_simple_case()
        
        print(f"\n{'='*60}\n")
        
        # 测试 2: 复杂并发测试（Agent + 简单请求）
        await test_concurrent_requests()
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("="*60)
    print("并发请求测试脚本")
    print("="*60)
    print("\n⚠️  请确保后端服务已启动: python main.py")
    print()
    
    asyncio.run(main())

