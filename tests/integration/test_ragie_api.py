"""
直接测试 Ragie API 连接和功能

这个脚本绕过所有业务逻辑，直接测试 Ragie API 是否正常工作
"""

import os
import asyncio
import aiohttp
import json
from pathlib import Path

# 添加项目根目录到 path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# 加载 .env
load_dotenv()

RAGIE_API_KEY = os.getenv("RAGIE_API_KEY")
RAGIE_BASE_URL = "https://api.ragie.ai"


async def test_ragie():
    print("=" * 60)
    print("🧪 Ragie API 直接测试")
    print("=" * 60)
    
    if not RAGIE_API_KEY:
        print("❌ 错误: RAGIE_API_KEY 未设置")
        print("   请在 .env 文件中设置 RAGIE_API_KEY")
        return
    
    print(f"✅ API Key: {RAGIE_API_KEY[:10]}...{RAGIE_API_KEY[-4:]}")
    print(f"✅ Base URL: {RAGIE_BASE_URL}")
    print()
    
    headers = {
        "Authorization": f"Bearer {RAGIE_API_KEY}",
        "Content-Type": "application/json"
    }
    
    async with aiohttp.ClientSession() as session:
        # ========== 测试 1: 列出所有文档 ==========
        print("📋 测试 1: 列出所有文档")
        print("-" * 40)
        
        try:
            async with session.get(
                f"{RAGIE_BASE_URL}/documents",
                headers=headers,
                params={"limit": 10}
            ) as response:
                text = await response.text()
                print(f"   HTTP {response.status}")
                
                if response.status == 200:
                    data = json.loads(text)
                    documents = data.get("documents", data) if isinstance(data, dict) else data
                    
                    if isinstance(documents, list):
                        print(f"   ✅ 找到 {len(documents)} 个文档")
                        for doc in documents[:5]:
                            print(f"      - id={doc.get('id')}, status={doc.get('status')}, name={doc.get('name', 'N/A')}")
                    else:
                        print(f"   响应: {text[:500]}")
                else:
                    print(f"   ❌ 错误: {text}")
        except Exception as e:
            print(f"   ❌ 异常: {str(e)}")
        
        print()
        
        # ========== 测试 2: 列出所有 Partitions ==========
        print("📋 测试 2: 列出所有 Partitions")
        print("-" * 40)
        
        try:
            async with session.get(
                f"{RAGIE_BASE_URL}/partitions",
                headers=headers
            ) as response:
                text = await response.text()
                print(f"   HTTP {response.status}")
                
                if response.status == 200:
                    data = json.loads(text)
                    partitions = data.get("partitions", data) if isinstance(data, dict) else data
                    
                    if isinstance(partitions, list):
                        print(f"   ✅ 找到 {len(partitions)} 个 Partition")
                        for p in partitions[:5]:
                            print(f"      - id={p.get('id')}, name={p.get('name')}")
                    else:
                        print(f"   响应: {text[:500]}")
                else:
                    print(f"   ❌ 错误: {text}")
        except Exception as e:
            print(f"   ❌ 异常: {str(e)}")
        
        print()
        
        # ========== 测试 3: 上传一个简单的测试文档 ==========
        print("📤 测试 3: 上传测试文档 (Raw Text)")
        print("-" * 40)
        
        test_content = "这是一个测试文档，用于验证 Ragie API 是否正常工作。"
        test_name = f"test_document_{int(asyncio.get_event_loop().time())}.txt"
        
        try:
            # 根据 Ragie API 文档，需要用 data 字段包裹
            payload = {
                "data": test_content,  # 文本内容
                "name": test_name       # 文档名称
            }
            
            async with session.post(
                f"{RAGIE_BASE_URL}/documents/raw",
                headers=headers,
                json=payload
            ) as response:
                text = await response.text()
                print(f"   HTTP {response.status}")
                
                if response.status in [200, 201]:
                    data = json.loads(text)
                    doc_id = data.get("id")
                    status = data.get("status")
                    print(f"   ✅ 创建成功!")
                    print(f"      document_id: {doc_id}")
                    print(f"      status: {status}")
                    print(f"      name: {data.get('name')}")
                    
                    # ========== 测试 4: 立即查询这个文档 ==========
                    print()
                    print("🔍 测试 4: 查询刚创建的文档")
                    print("-" * 40)
                    
                    await asyncio.sleep(1)  # 等待 1 秒
                    
                    async with session.get(
                        f"{RAGIE_BASE_URL}/documents/{doc_id}",
                        headers=headers
                    ) as get_response:
                        get_text = await get_response.text()
                        print(f"   HTTP {get_response.status}")
                        
                        if get_response.status == 200:
                            get_data = json.loads(get_text)
                            print(f"   ✅ 查询成功!")
                            print(f"      document_id: {get_data.get('id')}")
                            print(f"      status: {get_data.get('status')}")
                            print(f"      name: {get_data.get('name')}")
                        else:
                            print(f"   ❌ 查询失败: {get_text}")
                    
                    # ========== 测试 5: 删除测试文档 ==========
                    print()
                    print("🗑️ 测试 5: 删除测试文档")
                    print("-" * 40)
                    
                    async with session.delete(
                        f"{RAGIE_BASE_URL}/documents/{doc_id}",
                        headers=headers
                    ) as del_response:
                        print(f"   HTTP {del_response.status}")
                        if del_response.status in [200, 204]:
                            print("   ✅ 删除成功!")
                        else:
                            del_text = await del_response.text()
                            print(f"   ❌ 删除失败: {del_text}")
                
                else:
                    print(f"   ❌ 创建失败: {text}")
        except Exception as e:
            print(f"   ❌ 异常: {str(e)}")
    
        # ========== 测试 6: 先创建 Partition，再上传文件 ==========
        print()
        print("📤 测试 6: 创建 Partition 后上传文件")
        print("-" * 40)
        
        # 创建一个新的测试 partition
        test_partition_name = f"test_partition_{int(asyncio.get_event_loop().time())}"
        print(f"   1. 创建 Partition: {test_partition_name}")
        
        test_partition = None
        try:
            async with session.post(
                f"{RAGIE_BASE_URL}/partitions",
                headers=headers,
                json={"name": test_partition_name}
            ) as create_part_response:
                part_text = await create_part_response.text()
                print(f"      HTTP {create_part_response.status}")
                if create_part_response.status in [200, 201]:
                    part_data = json.loads(part_text)
                    test_partition = part_data.get("name")  # 使用 name 作为 partition 参数
                    print(f"      ✅ Partition 创建成功!")
                    print(f"         name: {part_data.get('name')}")
                    print(f"         id: {part_data.get('id')}")
                else:
                    print(f"      ❌ 创建失败: {part_text}")
        except Exception as e:
            print(f"      ❌ 异常: {str(e)}")
        
        if not test_partition:
            print("   ⚠️ 跳过文件上传测试（Partition 创建失败）")
        else:
            import tempfile
            import os as os_module
            
            # 创建临时测试文件
            test_file_content = b"This is a test file for Ragie API upload with partition."
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.txt', delete=False) as tmp:
                tmp.write(test_file_content)
                tmp_path = tmp.name
            
            print(f"   2. 上传文件到 Partition")
            print(f"      临时文件: {tmp_path}")
            print(f"      文件大小: {len(test_file_content)} bytes")
            print(f"      Partition: {test_partition}")
            
            try:
                # 构建 multipart form data（带 partition）
                form = aiohttp.FormData()
                form.add_field(
                    'file',
                    test_file_content,
                    filename='test_partition_upload.txt',
                    content_type='text/plain'
                )
                form.add_field('mode', 'fast')
                form.add_field('partition', test_partition)  # 添加 partition
                
                async with session.post(
                    f"{RAGIE_BASE_URL}/documents",
                    data=form,
                    headers={"Authorization": f"Bearer {RAGIE_API_KEY}"}
                ) as response:
                    text = await response.text()
                    print(f"      HTTP {response.status}")
                    
                    if response.status in [200, 201]:
                        data = json.loads(text)
                        doc_id = data.get("id")
                        print(f"      ✅ 文件上传成功!")
                        print(f"         document_id: {doc_id}")
                        print(f"         status: {data.get('status')}")
                        print(f"         name: {data.get('name')}")
                        print(f"         partition: {data.get('partition')}")
                        
                        # 等待 2 秒让 Ragie 处理
                        print("      ⏳ 等待 2 秒...")
                        await asyncio.sleep(2)
                        
                        # 查询文档
                        print()
                        print("🔍 测试 7: 查询刚上传的文档")
                        print("-" * 40)
                        async with session.get(
                            f"{RAGIE_BASE_URL}/documents/{doc_id}",
                            headers=headers
                        ) as get_response:
                            get_text = await get_response.text()
                            print(f"   HTTP {get_response.status}")
                            if get_response.status == 200:
                                get_data = json.loads(get_text)
                                print(f"   ✅ 查询成功!")
                                print(f"      status: {get_data.get('status')}")
                            else:
                                print(f"   ❌ 查询失败: {get_text}")
                        
                        # 列出该 partition 下的所有文档
                        print()
                        print("📋 测试 8: 列出 Partition 下的文档")
                        print("-" * 40)
                        async with session.get(
                            f"{RAGIE_BASE_URL}/documents",
                            headers=headers,
                            params={"partition": test_partition, "limit": 10}
                        ) as list_response:
                            list_text = await list_response.text()
                            print(f"   HTTP {list_response.status}")
                            if list_response.status == 200:
                                list_data = json.loads(list_text)
                                docs = list_data.get("documents", list_data) if isinstance(list_data, dict) else list_data
                                if isinstance(docs, list):
                                    print(f"   ✅ 找到 {len(docs)} 个文档")
                                else:
                                    print(f"   响应: {list_text[:300]}")
                            else:
                                print(f"   ❌ 列出失败: {list_text}")
                        
                        # 清理文档
                        print()
                        print("🗑️ 清理测试文档...")
                        async with session.delete(
                            f"{RAGIE_BASE_URL}/documents/{doc_id}",
                            headers=headers
                        ) as del_response:
                            if del_response.status in [200, 204]:
                                print(f"   ✅ 测试文档已清理")
                    else:
                        print(f"      ❌ 文件上传失败: {text}")
                
                # 清理临时文件
                os_module.unlink(tmp_path)
                
            except Exception as e:
                print(f"   ❌ 异常: {str(e)}")
            
            # 清理 Partition
            print()
            print("🗑️ 清理测试 Partition...")
            try:
                async with session.delete(
                    f"{RAGIE_BASE_URL}/partitions/{test_partition}",
                    headers=headers
                ) as del_part_response:
                    if del_part_response.status in [200, 204]:
                        print(f"   ✅ Partition 已清理")
                    else:
                        del_part_text = await del_part_response.text()
                        print(f"   ⚠️ Partition 清理失败: {del_part_text}")
            except Exception as e:
                print(f"   ⚠️ Partition 清理异常: {str(e)}")
    
    print()
    print("=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_ragie())

