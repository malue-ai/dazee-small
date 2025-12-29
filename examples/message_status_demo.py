"""
Message Status 字段使用示例

演示如何使用 JSON 格式的 status 字段记录多步骤任务
"""

import json
import asyncio
from services.conversation_service import get_conversation_service


async def demo_multi_step_task():
    """演示多步骤任务的消息记录"""
    
    conversation_service = get_conversation_service()
    conversation_id = "conv_demo_001"
    
    print("=" * 60)
    print("多步骤任务示例：搜索并总结信息")
    print("=" * 60)
    
    # 步骤 0: 思考阶段
    print("\n步骤 0: 思考...")
    await conversation_service.add_message(
        conversation_id=conversation_id,
        role="assistant",
        content=json.dumps([
            {"type": "text", "text": "让我分析一下这个任务..."}
        ]),
        status=json.dumps({
            "index": 0,
            "action": "think",
            "description": "分析用户需求，制定搜索策略"
        }),
        score=0.9
    )
    
    # 步骤 1: 执行搜索
    print("步骤 1: 执行搜索...")
    await conversation_service.add_message(
        conversation_id=conversation_id,
        role="assistant",
        content=json.dumps([
            {
                "type": "tool_use",
                "id": "toolu_search_001",
                "name": "web_search",
                "input": {"query": "Python 异步编程最佳实践"}
            }
        ]),
        status=json.dumps({
            "index": 1,
            "action": "action",
            "description": "搜索 Python 异步编程相关资料"
        })
    )
    
    # 步骤 2: 处理搜索结果
    print("步骤 2: 处理搜索结果...")
    await conversation_service.add_message(
        conversation_id=conversation_id,
        role="assistant",
        content=json.dumps([
            {
                "type": "tool_result",
                "tool_use_id": "toolu_search_001",
                "content": "找到10篇相关文章..."
            }
        ]),
        status=json.dumps({
            "index": 2,
            "action": "action",
            "description": "解析搜索结果"
        })
    )
    
    # 步骤 3: 验证信息
    print("步骤 3: 验证信息...")
    await conversation_service.add_message(
        conversation_id=conversation_id,
        role="assistant",
        content=json.dumps([
            {"type": "text", "text": "正在验证信息的准确性..."}
        ]),
        status=json.dumps({
            "index": 3,
            "action": "validate",
            "description": "交叉验证多个来源的信息"
        })
    )
    
    # 步骤 4: 生成最终回复
    print("步骤 4: 生成回复...")
    await conversation_service.add_message(
        conversation_id=conversation_id,
        role="assistant",
        content=json.dumps([
            {
                "type": "text",
                "text": "根据搜索结果，Python 异步编程的最佳实践包括：\n1. 使用 async/await 语法\n2. 避免阻塞操作\n3. 合理使用 asyncio.gather..."
            }
        ]),
        status=json.dumps({
            "index": 4,
            "action": "respond",
            "description": "综合信息生成最终回复"
        }),
        score=0.95
    )
    
    # 步骤 5: 反思
    print("步骤 5: 反思...")
    await conversation_service.add_message(
        conversation_id=conversation_id,
        role="assistant",
        content=json.dumps([
            {"type": "text", "text": "这个回答涵盖了关键要点，质量较高"}
        ]),
        status=json.dumps({
            "index": 5,
            "action": "reflect",
            "description": "评估回答质量"
        }),
        metadata={"reflection": "comprehensive", "confidence": 0.95}
    )
    
    print("\n" + "=" * 60)
    print("✅ 所有步骤已记录完成")
    print("=" * 60)
    
    # 查询并显示所有步骤
    print("\n📊 查询消息历史（按步骤排序）：\n")
    result = await conversation_service.get_conversation_messages(
        conversation_id=conversation_id,
        limit=100,
        order="asc"
    )
    
    for msg in result["messages"]:
        if msg["status"]:
            status = json.loads(msg["status"])
            content_blocks = json.loads(msg["content"])
            
            # 获取文本内容
            texts = [b["text"] for b in content_blocks if b["type"] == "text"]
            text_preview = texts[0][:50] + "..." if texts else "[工具调用]"
            
            print(f"步骤 {status['index']}: {status['action']:10s} | {status['description']}")
            print(f"  内容: {text_preview}")
            if msg["score"]:
                print(f"  评分: {msg['score']}")
            print()


async def demo_simple_message():
    """演示简单消息（无状态）"""
    
    conversation_service = get_conversation_service()
    conversation_id = "conv_demo_002"
    
    print("\n" + "=" * 60)
    print("简单消息示例（无多步骤）")
    print("=" * 60 + "\n")
    
    # 用户消息
    await conversation_service.add_message(
        conversation_id=conversation_id,
        role="user",
        content=json.dumps([
            {"type": "text", "text": "你好"}
        ]),
        message_id="msg_user_hello"
    )
    print("✅ 用户消息已保存")
    
    # AI 简单回复（无状态）
    await conversation_service.add_message(
        conversation_id=conversation_id,
        role="assistant",
        content=json.dumps([
            {"type": "text", "text": "你好！我是 AI 助手，有什么可以帮你的吗？"}
        ]),
        status=None,  # 简单回复不需要 status
        score=0.8
    )
    print("✅ AI 回复已保存\n")


if __name__ == "__main__":
    print("\n🚀 Message Status 字段示例\n")
    
    # 运行示例
    asyncio.run(demo_simple_message())
    asyncio.run(demo_multi_step_task())
    
    print("\n✅ 示例完成！\n")
    print("💡 提示：")
    print("- 简单对话不需要 status 字段")
    print("- 多步骤任务使用 status 记录每个步骤")
    print("- 前端可以根据 status.index 排序显示任务进度")
    print()

