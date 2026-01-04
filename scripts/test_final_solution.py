"""
测试最终方案：使用 default partition + metadata.user_id 区分用户
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


async def test_final_solution():
    print("=" * 60)
    print("🧪 最终方案测试：default partition + metadata.user_id")
    print("=" * 60)
    print(f"API Key: {RAGIE_API_KEY[:15]}...{RAGIE_API_KEY[-5:]}")
    print()
    
    headers = {
        'Authorization': f'Bearer {RAGIE_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    test_user_id = "user_test_12345"
    
    async with aiohttp.ClientSession() as session:
        # 1. 上传文件（不指定 partition，使用 metadata.user_id）
        print("📤 步骤 1: 上传文件 (metadata.user_id)")
        print("-" * 40)
        
        form = aiohttp.FormData()
        form.add_field(
            'file', 
            b'This is test content for final solution verification.',
            filename='final_test.txt',
            content_type='text/plain'
        )
        form.add_field('mode', 'fast')
        form.add_field('metadata', json.dumps({
            'user_id': test_user_id,
            'filename': 'final_test.txt',
            'test': True
        }))
        # 注意：不添加 partition 字段，使用 default
        
        async with session.post(
            f'{RAGIE_BASE_URL}/documents',
            data=form,
            headers={'Authorization': f'Bearer {RAGIE_API_KEY}'}
        ) as resp:
            text = await resp.text()
            print(f"HTTP {resp.status}")
            data = json.loads(text)
            print(f"document_id: {data.get('id')}")
            print(f"status: {data.get('status')}")
            print(f"partition: {data.get('partition')}")
            print(f"metadata: {data.get('metadata')}")
            
            if resp.status not in [200, 201]:
                print(f"❌ 上传失败: {text}")
                return
            
            doc_id = data.get('id')
        
        print()
        
        # 2. 立即查询文档
        print("🔍 步骤 2: 立即查询文档")
        print("-" * 40)
        
        async with session.get(
            f'{RAGIE_BASE_URL}/documents/{doc_id}',
            headers=headers
        ) as resp:
            text = await resp.text()
            print(f"HTTP {resp.status}")
            if resp.status == 200:
                data = json.loads(text)
                print(f"✅ 查询成功!")
                print(f"   status: {data.get('status')}")
                print(f"   partition: {data.get('partition')}")
                print(f"   metadata: {data.get('metadata')}")
            else:
                print(f"❌ 查询失败: {text}")
                return
        
        print()
        
        # 3. 等待处理完成
        print("⏳ 步骤 3: 等待 5 秒让 Ragie 处理...")
        await asyncio.sleep(5)
        
        async with session.get(
            f'{RAGIE_BASE_URL}/documents/{doc_id}',
            headers=headers
        ) as resp:
            text = await resp.text()
            data = json.loads(text)
            print(f"5秒后状态: {data.get('status')}")
        
        print()
        
        # 4. 列出所有文档
        print("📋 步骤 4: 列出所有文档")
        print("-" * 40)
        
        async with session.get(
            f'{RAGIE_BASE_URL}/documents',
            headers=headers,
            params={'limit': 10}
        ) as resp:
            text = await resp.text()
            data = json.loads(text)
            docs = data.get('documents', [])
            print(f"总文档数: {data.get('pagination', {}).get('total_count', len(docs))}")
            for doc in docs[:5]:
                print(f"  - {doc.get('id')}: {doc.get('name')} (metadata: {doc.get('metadata')})")
        
        print()
        
        # 5. 使用 filter 查询特定用户的文档
        print("🔍 步骤 5: 使用 filter 查询特定用户文档")
        print("-" * 40)
        
        filter_param = json.dumps({"user_id": {"$eq": test_user_id}})
        async with session.get(
            f'{RAGIE_BASE_URL}/documents',
            headers=headers,
            params={'limit': 10, 'filter': filter_param}
        ) as resp:
            text = await resp.text()
            print(f"HTTP {resp.status}")
            if resp.status == 200:
                data = json.loads(text)
                docs = data.get('documents', [])
                print(f"✅ 用户 {test_user_id} 的文档数: {len(docs)}")
                for doc in docs:
                    print(f"  - {doc.get('id')}: {doc.get('name')}")
            else:
                print(f"⚠️ Filter 查询结果: {text}")
        
        print()
        
        # 6. 清理
        print("🗑️ 步骤 6: 清理测试文档")
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
    asyncio.run(test_final_solution())

