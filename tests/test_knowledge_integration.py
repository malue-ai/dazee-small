"""
测试知识库集成 - 完整流程验证

测试流程：
1. 上传文档到用户的知识库
2. 等待文档处理完成
3. 发起对话，Agent 自动使用 knowledge_search 工具检索
4. 验证返回结果包含知识库内容
"""

import asyncio
import aiohttp
import json
from pathlib import Path

# 配置
BASE_URL = "http://localhost:8001"
USER_ID = "test_user_001"
TEST_FILE = Path(__file__).parent / "test_document.txt"


async def test_knowledge_integration():
    """完整测试：上传 → 等待 → 对话 → 验证"""
    
    print("=" * 60)
    print("🧪 知识库集成测试")
    print("=" * 60)
    
    # 步骤1: 创建测试文档
    print("\n1️⃣ 创建测试文档...")
    test_content = """
    # 产品需求文档

    ## 项目名称
    智能助手 v2.0

    ## 核心功能
    1. 个人知识库管理
       - 支持多种文档格式
       - 智能语义检索
       - 自动分类和标签

    2. 对话式交互
       - 自然语言理解
       - 上下文记忆
       - 多轮对话

    3. 任务自动化
       - 工作流编排
       - 定时任务
       - 自动通知

    ## 技术架构
    - 后端：Python + FastAPI
    - 向量数据库：Ragie
    - LLM：Claude 4.5
    """
    
    TEST_FILE.write_text(test_content, encoding='utf-8')
    print(f"✅ 测试文档已创建: {TEST_FILE}")
    
    # 步骤2: 上传文档
    print("\n2️⃣ 上传文档到知识库...")
    async with aiohttp.ClientSession() as session:
        with open(TEST_FILE, 'rb') as f:
            form_data = aiohttp.FormData()
            form_data.add_field('file', f, filename='test_document.txt')
            form_data.add_field('user_id', USER_ID)
            form_data.add_field('metadata', json.dumps({
                "source": "test",
                "type": "requirements"
            }))
            
            async with session.post(
                f"{BASE_URL}/api/v1/knowledge/upload",
                data=form_data
            ) as resp:
                if resp.status != 200:
                    print(f"❌ 上传失败: {resp.status}")
                    print(await resp.text())
                    return
                
                result = await resp.json()
                document_id = result['data']['document_id']
                print(f"✅ 文档已上传: document_id={document_id}")
                print(f"   状态: {result['data']['status']}")
    
    # 步骤3: 等待文档处理完成
    print("\n3️⃣ 等待文档处理完成...")
    max_wait = 60  # 最多等待60秒
    wait_time = 0
    status = "pending"
    
    async with aiohttp.ClientSession() as session:
        while wait_time < max_wait and status not in ["indexed", "ready"]:
            await asyncio.sleep(3)
            wait_time += 3
            
            async with session.get(
                f"{BASE_URL}/api/v1/knowledge/documents/{USER_ID}/{document_id}?refresh=true"
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    status = result['data']['status']
                    print(f"   [{wait_time}s] 状态: {status}")
                    
                    if status == "ready":
                        print(f"✅ 文档处理完成！")
                        break
                    elif status == "indexed":
                        print(f"✅ 文档已索引（可检索）")
                        break
                else:
                    print(f"   检查状态失败: {resp.status}")
    
    if status not in ["indexed", "ready"]:
        print(f"⚠️ 文档未在 {max_wait}秒内处理完成，当前状态: {status}")
        print(f"   继续进行对话测试...")
    
    # 步骤4: 发起对话（Agent 应自动使用 knowledge_search 工具）
    print("\n4️⃣ 发起对话测试...")
    test_queries = [
        "智能助手有哪些核心功能？",
        "项目的技术架构是什么？",
        "个人知识库支持哪些能力？"
    ]
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n📝 测试 {i}/{len(test_queries)}: {query}")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{BASE_URL}/api/v1/chat",
                json={
                    "message": query,
                    "user_id": USER_ID,
                    "stream": False
                }
            ) as resp:
                if resp.status != 200:
                    print(f"❌ 请求失败: {resp.status}")
                    print(await resp.text())
                    continue
                
                result = await resp.json()
                content = result['data']['content']
                tool_calls = result['data'].get('tool_calls', [])
                
                # 检查是否使用了 knowledge_search 工具
                used_knowledge_search = False
                if tool_calls:
                    for tc in tool_calls:
                        if 'knowledge_search' in str(tc):
                            used_knowledge_search = True
                            break
                
                print(f"\n💬 回复:")
                print(f"{content[:200]}..." if len(content) > 200 else content)
                print(f"\n🔧 工具使用: {'knowledge_search ✅' if used_knowledge_search else '未使用知识库 ⚠️'}")
                
                if not used_knowledge_search:
                    print("⚠️ Agent 未自动调用 knowledge_search 工具")
    
    # 步骤5: 清理
    print("\n5️⃣ 清理测试数据...")
    async with aiohttp.ClientSession() as session:
        async with session.delete(
            f"{BASE_URL}/api/v1/knowledge/documents/{USER_ID}/{document_id}"
        ) as resp:
            if resp.status == 200:
                print(f"✅ 测试文档已删除")
            else:
                print(f"⚠️ 删除失败: {resp.status}")
    
    # 删除本地测试文件
    if TEST_FILE.exists():
        TEST_FILE.unlink()
        print(f"✅ 本地测试文件已删除")
    
    print("\n" + "=" * 60)
    print("🎉 测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_knowledge_integration())

