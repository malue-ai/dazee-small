"""
测试文档内容和分块 API
"""
import asyncio
import aiohttp
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv

load_dotenv()

RAGIE_API_KEY = os.getenv('RAGIE_API_KEY')
RAGIE_BASE_URL = 'https://api.ragie.ai'


async def test_document_apis():
    print("=" * 60)
    print("🧪 测试文档内容和分块 API")
    print("=" * 60)
    
    headers = {
        'Authorization': f'Bearer {RAGIE_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    test_user_id = "user_test_apis"
    
    async with aiohttp.ClientSession() as session:
        # 1. 上传一个测试文档
        print("\n📤 步骤 1: 上传测试文档")
        print("-" * 40)
        
        test_content = """这是一个测试文档。

第一段：介绍部分
这是一个用于测试文档内容获取和分块查询的测试文档。

第二段：主要内容
文档内容包含多个段落，用于验证 Ragie 的分块功能是否正常工作。

第三段：结论
测试文档到此结束。"""
        
        form = aiohttp.FormData()
        form.add_field(
            'file',
            test_content.encode('utf-8'),
            filename='test_doc.txt',
            content_type='text/plain'
        )
        form.add_field('mode', 'fast')
        form.add_field('metadata', json.dumps({
            'user_id': test_user_id,
            'filename': 'test_doc.txt',
            'test': True
        }))
        
        async with session.post(
            f'{RAGIE_BASE_URL}/documents',
            data=form,
            headers={'Authorization': f'Bearer {RAGIE_API_KEY}'}
        ) as resp:
            text = await resp.text()
            data = json.loads(text)
            doc_id = data.get('id')
            print(f"✅ 文档已上传: {doc_id}")
            print(f"   状态: {data.get('status')}")
        
        # 2. 等待处理
        print("\n⏳ 步骤 2: 等待文档处理...")
        await asyncio.sleep(5)
        
        async with session.get(
            f'{RAGIE_BASE_URL}/documents/{doc_id}',
            headers=headers
        ) as resp:
            data = json.loads(await resp.text())
            print(f"   处理状态: {data.get('status')}")
        
        # 3. 获取文档内容
        print("\n📄 步骤 3: 获取文档内容")
        print("-" * 40)
        
        async with session.get(
            f'{RAGIE_BASE_URL}/documents/{doc_id}/content',
            headers=headers
        ) as resp:
            print(f"HTTP {resp.status}")
            if resp.status == 200:
                data = json.loads(await resp.text())
                content = data.get('content', '')
                print(f"✅ 内容长度: {len(content)} 字符")
                print(f"   预览: {content[:100]}...")
            else:
                text = await resp.text()
                print(f"❌ 失败: {text}")
        
        # 4. 获取文档分块
        print("\n🧩 步骤 4: 获取文档分块")
        print("-" * 40)
        
        async with session.get(
            f'{RAGIE_BASE_URL}/documents/{doc_id}/chunks',
            headers=headers,
            params={'limit': 10}
        ) as resp:
            print(f"HTTP {resp.status}")
            if resp.status == 200:
                data = json.loads(await resp.text())
                chunks = data.get('chunks', [])
                total = data.get('pagination', {}).get('total_count', len(chunks))
                print(f"✅ 分块总数: {total}")
                for i, chunk in enumerate(chunks[:3], 1):
                    print(f"\n   分块 #{i}:")
                    print(f"   ID: {chunk.get('id')}")
                    print(f"   文本: {chunk.get('text', '')[:80]}...")
            else:
                text = await resp.text()
                print(f"❌ 失败: {text}")
        
        # 5. 获取源文件
        print("\n⬇️ 步骤 5: 获取源文件")
        print("-" * 40)
        
        async with session.get(
            f'{RAGIE_BASE_URL}/documents/{doc_id}/source',
            headers=headers
        ) as resp:
            print(f"HTTP {resp.status}")
            if resp.status == 200:
                file_bytes = await resp.read()
                print(f"✅ 文件大小: {len(file_bytes)} 字节")
                print(f"   预览: {file_bytes[:100]}")
            else:
                text = await resp.text()
                print(f"❌ 失败: {text}")
        
        # 6. 清理
        print("\n🗑️ 步骤 6: 清理测试文档")
        print("-" * 40)
        
        async with session.delete(
            f'{RAGIE_BASE_URL}/documents/{doc_id}',
            headers=headers
        ) as resp:
            if resp.status in [200, 204]:
                print("✅ 文档已删除")
            else:
                text = await resp.text()
                print(f"⚠️ 删除结果: {text}")
    
    print()
    print("=" * 60)
    print("✅ 测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_document_apis())

