"""
测试 S3 下载功能
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

BACKEND_URL = "http://localhost:8000/api/v1/knowledge"
USER_ID = "user_test_s3"


async def test_s3_download():
    print("=" * 60)
    print("🧪 测试 S3 下载功能")
    print("=" * 60)
    
    async with aiohttp.ClientSession() as session:
        # 1. 上传一个测试文件
        print("\n📤 步骤 1: 上传测试文件到知识库")
        print("-" * 40)
        
        test_content = b"This is a test file for S3 download verification."
        test_filename = "s3_test_file.txt"
        
        form = aiohttp.FormData()
        form.add_field(
            'files',
            test_content,
            filename=test_filename,
            content_type='text/plain'
        )
        form.add_field('user_id', USER_ID)
        form.add_field('mode', 'fast')
        
        async with session.post(
            f'{BACKEND_URL}/upload',
            data=form
        ) as resp:
            text = await resp.text()
            print(f"HTTP {resp.status}")
            if resp.status == 200:
                data = json.loads(text)
                doc_id = data['data']['document_id']
                print(f"✅ 文档已上传: {doc_id}")
            else:
                print(f"❌ 上传失败: {text}")
                return
        
        # 2. 等待处理
        print("\n⏳ 步骤 2: 等待文档处理...")
        await asyncio.sleep(3)
        
        # 3. 获取文档信息（检查是否有 S3 信息）
        print("\n📋 步骤 3: 获取文档信息")
        print("-" * 40)
        
        async with session.get(
            f'{BACKEND_URL}/documents/{USER_ID}',
            params={'limit': 10, 'refresh': True}
        ) as resp:
            text = await resp.text()
            data = json.loads(text)
            
            if data['code'] == 200:
                docs = data['data']['documents']
                uploaded_doc = next((d for d in docs if d['document_id'] == doc_id), None)
                
                if uploaded_doc:
                    print(f"✅ 文档信息:")
                    print(f"   文件名: {uploaded_doc['filename']}")
                    print(f"   状态: {uploaded_doc['status']}")
                    
                    metadata = uploaded_doc.get('metadata', {})
                    if 's3_key' in metadata:
                        print(f"   S3 Key: {metadata['s3_key']}")
                        print(f"   S3 URL: {metadata.get('s3_url', 'N/A')}")
                        print(f"   预签名 URL: {metadata.get('s3_presigned_url', 'N/A')[:80]}...")
                    else:
                        print("   ⚠️ 文档不在 S3")
        
        # 4. 测试获取 S3 预签名 URL
        print("\n🔗 步骤 4: 获取 S3 预签名 URL")
        print("-" * 40)
        
        async with session.get(
            f'{BACKEND_URL}/documents/{USER_ID}/{doc_id}/s3-url',
            params={'expiration': 300}  # 5分钟
        ) as resp:
            text = await resp.text()
            print(f"HTTP {resp.status}")
            if resp.status == 200:
                data = json.loads(text)
                if data['code'] == 200:
                    s3_url = data['data']['s3_url']
                    print(f"✅ S3 预签名 URL:")
                    print(f"   {s3_url[:100]}...")
                    print(f"   有效期: {data['data']['expires_in']} 秒")
                    
                    # 尝试直接从 S3 下载
                    print("\n   测试直接从 S3 下载...")
                    async with session.get(s3_url) as s3_resp:
                        if s3_resp.status == 200:
                            content = await s3_resp.read()
                            print(f"   ✅ S3 下载成功: {len(content)} 字节")
                            print(f"   内容: {content.decode('utf-8')}")
                        else:
                            print(f"   ❌ S3 下载失败: HTTP {s3_resp.status}")
                else:
                    print(f"⚠️ {data['message']}")
            else:
                print(f"❌ 失败: {text}")
        
        # 5. 测试下载端点（自动选择）
        print("\n⬇️ 步骤 5: 测试下载端点（source=auto）")
        print("-" * 40)
        
        async with session.get(
            f'{BACKEND_URL}/documents/{USER_ID}/{doc_id}/download',
            params={'source': 'auto'},
            allow_redirects=True
        ) as resp:
            print(f"HTTP {resp.status}")
            if resp.status == 200:
                content = await resp.read()
                print(f"✅ 下载成功: {len(content)} 字节")
                print(f"   内容: {content.decode('utf-8')}")
            else:
                text = await resp.text()
                print(f"❌ 下载失败: {text}")
        
        # 6. 测试下载端点（仅 S3）
        print("\n⬇️ 步骤 6: 测试下载端点（source=s3）")
        print("-" * 40)
        
        async with session.get(
            f'{BACKEND_URL}/documents/{USER_ID}/{doc_id}/download',
            params={'source': 's3'},
            allow_redirects=True
        ) as resp:
            print(f"HTTP {resp.status}")
            if resp.status == 200:
                content = await resp.read()
                print(f"✅ S3 下载成功: {len(content)} 字节")
            else:
                text = await resp.text()
                print(f"❌ S3 下载失败: {text}")
        
        # 7. 清理
        print("\n🗑️ 步骤 7: 清理测试文档")
        print("-" * 40)
        
        async with session.delete(
            f'{BACKEND_URL}/documents/{USER_ID}/{doc_id}'
        ) as resp:
            if resp.status == 200:
                print("✅ 文档已删除")
            else:
                text = await resp.text()
                print(f"⚠️ 删除结果: {text}")
    
    print()
    print("=" * 60)
    print("✅ 测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_s3_download())

