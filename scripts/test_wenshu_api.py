#!/usr/bin/env python
"""
测试 wenshu_api（问数平台）调用

直接测试 APICallingTool 调用问数 API 的功能
"""

import asyncio
import os
import sys
import json
import aiohttp

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

# 加载环境变量
load_dotenv(".env.development")


async def test_wenshu_api_direct():
    """
    直接测试问数 API 调用（不通过 APICallingTool）
    
    这样可以验证 API 本身是否可用
    """
    
    # 1. API 配置（正确的端点是 /api/v3/zeno/chat/question）
    api_url = "http://183.6.79.71:40202/api/v3/zeno/chat/question"
    api_key = os.environ.get("WENSHU_API_KEY")
    
    if not api_key:
        print("❌ 错误: WENSHU_API_KEY 环境变量未设置!")
        print("请在 .env.development 中设置 WENSHU_API_KEY")
        return
    
    # 2. 测试文件 URL
    file_url = "https://dify-storage-zenflux.s3.amazonaws.com/chat-attachments/user_1768475079723/20260126/ea17e881-7104-40a4-86a3-98b4e00bca25_1fb6734f-cbe4-4228-8f18-bc0023b8314f.csv?AWSAccessKeyId=AKIAUPUSDVE22NYLK4XE&Signature=wjj9Eah4qxyRWwwRBQcgCt085R4%3D&Expires=1769498088"
    file_name = "1fb6734f-cbe4-4228-8f18-bc0023b8314f.csv"
    
    # 3. 构建请求体（使用真实值，不用占位符）
    request_body = {
        "user_id": "user_1768475079723",  # 真实用户 ID
        "task_id": "test_task_" + str(int(asyncio.get_event_loop().time())),  # 生成唯一 task_id
        "lg_code": "zh-CN",
        "question": "帮我分析一下这个数据文件的内容",
        "files": [
            {
                "file_name": file_name,
                "file_url": file_url
            }
        ]
    }
    
    # 4. 请求头
    headers = {
        "Content-Type": "application/json",
        "API-KEY": api_key
    }
    
    print("=" * 60)
    print("🧪 测试 wenshu_api（问数平台）直接调用")
    print("=" * 60)
    print(f"🌐 API URL: {api_url}")
    print(f"📁 文件名: {file_name}")
    print(f"📄 问题: {request_body['question']}")
    print(f"👤 user_id: {request_body['user_id']}")
    print(f"💬 task_id: {request_body['task_id']}")
    print(f"🔑 API Key: {api_key[:10]}..." if len(api_key) > 10 else f"🔑 API Key: {api_key}")
    print("=" * 60)
    
    print("\n📤 请求体:")
    print(json.dumps(request_body, ensure_ascii=False, indent=2))
    
    print("\n🚀 开始调用 wenshu_api...")
    print("-" * 60)
    
    try:
        async with aiohttp.ClientSession() as session:
            # 打印完整请求信息
            print(f"\n📤 请求 URL: {api_url}")
            print(f"📤 请求头: {json.dumps(headers, ensure_ascii=False)}")
            
            async with session.post(
                api_url,
                headers=headers,
                json=request_body,
                timeout=aiohttp.ClientTimeout(total=120),
                allow_redirects=False  # 不自动跟随重定向
            ) as response:
                print(f"\n📡 HTTP 状态码: {response.status}")
                print(f"📡 响应头: {dict(response.headers)}")
                
                # 读取响应
                response_text = await response.text()
                
                print("\n📦 API 原始响应:")
                print("-" * 60)
                print(response_text[:2000])  # 只打印前 2000 字符
                
                if response_text:
                    try:
                        result = json.loads(response_text)
                        print("\n📦 API JSON 响应:")
                        print("-" * 60)
                        print(json.dumps(result, ensure_ascii=False, indent=2)[:3000])
                        
                        # 检查结果
                        if response.status == 200:
                            print("\n✅ API 调用成功!")
                        else:
                            print(f"\n❌ API 调用失败: HTTP {response.status}")
                    except json.JSONDecodeError:
                        print("\n⚠️ 响应不是有效的 JSON")
    
    except asyncio.TimeoutError:
        print("\n❌ 请求超时（120秒）")
    except Exception as e:
        print(f"\n❌ 异常: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_wenshu_api_direct())
