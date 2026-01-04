"""
调试 Ragie API - 打印完整响应
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


async def debug_ragie():
    print(f"API Key: {RAGIE_API_KEY[:15]}...{RAGIE_API_KEY[-5:]}")
    print()
    
    headers = {
        'Authorization': f'Bearer {RAGIE_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    test_user_id = "user_1766974073604"
    
    async with aiohttp.ClientSession() as session:
        # ========== 最终方案测试：使用 default partition + metadata.user_id ==========
        
        print('=' * 60)
        print('🧪 最终方案：使用 default partition + metadata.user_id')
        print('=' * 60)
        
        form_a = aiohttp.FormData()
        form_a.add_field('file', b'Test without partition', filename='no_partition.txt', content_type='text/plain')
        form_a.add_field('mode', 'fast')
        
        async with session.post(
            f'{RAGIE_BASE_URL}/documents',
            data=form_a,
            headers={'Authorization': f'Bearer {RAGIE_API_KEY}'}
        ) as resp_a:
            text_a = await resp_a.text()
            print(f'上传响应: HTTP {resp_a.status}')
            print(text_a)
            
            if resp_a.status in [200, 201]:
                data_a = json.loads(text_a)
                doc_id_a = data_a.get('id')
                
                print(f'\n立即查询 {doc_id_a}:')
                async with session.get(f'{RAGIE_BASE_URL}/documents/{doc_id_a}', headers=headers) as get_a:
                    print(f'HTTP {get_a.status}')
                    if get_a.status == 200:
                        print('✅ 成功!')
                    else:
                        print(await get_a.text())
                
                # 清理
                await session.delete(f'{RAGIE_BASE_URL}/documents/{doc_id_a}', headers=headers)
        
        print()
        
        # 测试 B: 有 Partition 上传
        print('=' * 60)
        print('🧪 测试 B: 有 Partition 上传')
        print('=' * 60)
        
        form_b = aiohttp.FormData()
        form_b.add_field('file', b'Test with partition', filename='with_partition.txt', content_type='text/plain')
        form_b.add_field('mode', 'fast')
        form_b.add_field('partition', 'partition_test001')  # 使用已存在的 partition
        
        async with session.post(
            f'{RAGIE_BASE_URL}/documents',
            data=form_b,
            headers={'Authorization': f'Bearer {RAGIE_API_KEY}'}
        ) as resp_b:
            text_b = await resp_b.text()
            print(f'上传响应: HTTP {resp_b.status}')
            print(text_b)
            
            if resp_b.status in [200, 201]:
                data_b = json.loads(text_b)
                doc_id_b = data_b.get('id')
                
                print(f'\n立即查询 {doc_id_b}:')
                async with session.get(f'{RAGIE_BASE_URL}/documents/{doc_id_b}', headers=headers) as get_b:
                    print(f'HTTP {get_b.status}')
                    if get_b.status == 200:
                        print('✅ 成功!')
                    else:
                        print(await get_b.text())
        
        print()
        print('=' * 60)
        print('原始测试继续...')
        print('=' * 60)
        print()
        
        # 1. 获取 Partition 列表的完整响应
        print('📋 Partition 列表完整响应:')
        print('-' * 50)
        async with session.get(f'{RAGIE_BASE_URL}/partitions', headers=headers) as response:
            text = await response.text()
            print(f'HTTP {response.status}')
            print(text[:1000])
        
        print()
        
        # 2. 创建 Partition 的完整响应
        print('📤 创建 Partition 完整响应:')
        print('-' * 50)
        test_partition_name = f'debug_partition_{int(asyncio.get_event_loop().time())}'
        async with session.post(
            f'{RAGIE_BASE_URL}/partitions',
            headers=headers,
            json={'name': test_partition_name}
        ) as response:
            text = await response.text()
            print(f'HTTP {response.status}')
            print(text)
            
            if response.status in [200, 201]:
                data = json.loads(text)
                partition_name = data.get('name')
                
                # 3. 上传文件到这个 Partition
                print()
                print('📤 上传文件完整响应:')
                print('-' * 50)
                
                form = aiohttp.FormData()
                form.add_field('file', b'Test content for debugging Ragie API', filename='debug_test.txt', content_type='text/plain')
                form.add_field('partition', partition_name)
                form.add_field('mode', 'fast')
                
                async with session.post(
                    f'{RAGIE_BASE_URL}/documents',
                    data=form,
                    headers={'Authorization': f'Bearer {RAGIE_API_KEY}'}
                ) as upload_response:
                    upload_text = await upload_response.text()
                    print(f'HTTP {upload_response.status}')
                    print(upload_text)
                    
                    if upload_response.status in [200, 201]:
                        doc_data = json.loads(upload_text)
                        doc_id = doc_data.get('id')
                        
                        # 4. 立即查询（不等待）
                        print()
                        print('🔍 立即查询文档 (0秒):')
                        print('-' * 50)
                        async with session.get(
                            f'{RAGIE_BASE_URL}/documents/{doc_id}',
                            headers=headers
                        ) as get_response:
                            get_text = await get_response.text()
                            print(f'HTTP {get_response.status}')
                            print(get_text)
                        
                        # 5. 等待 5 秒后再查询
                        print()
                        print('⏳ 等待 5 秒后再查询...')
                        await asyncio.sleep(5)
                        print('🔍 5秒后查询文档:')
                        print('-' * 50)
                        async with session.get(
                            f'{RAGIE_BASE_URL}/documents/{doc_id}',
                            headers=headers
                        ) as get_response2:
                            get_text2 = await get_response2.text()
                            print(f'HTTP {get_response2.status}')
                            print(get_text2)
                        
                        # 6. 列出所有文档
                        print()
                        print('📋 列出所有文档:')
                        print('-' * 50)
                        async with session.get(
                            f'{RAGIE_BASE_URL}/documents',
                            headers=headers,
                            params={'limit': 10}
                        ) as list_response:
                            list_text = await list_response.text()
                            print(f'HTTP {list_response.status}')
                            print(list_text[:1000])
                
                # 清理 Partition
                print()
                print('🗑️ 清理 Partition...')
                async with session.delete(
                    f'{RAGIE_BASE_URL}/partitions/{partition_name}',
                    headers=headers
                ) as del_response:
                    print(f'HTTP {del_response.status}')
                    del_text = await del_response.text()
                    print(del_text)


if __name__ == "__main__":
    asyncio.run(debug_ragie())

