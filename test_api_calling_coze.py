"""
测试 api_calling 工具调用 Coze API - 直接硬编码版本
"""
import asyncio
import json
import os

# 直接硬编码
COZE_API_KEY = "pat_bHCRBoLRb4gXLqPsMv3jum4sTrtM0s6T3mQYjOr9FPKaBIb87XoLcePKJWh75PgR"

from tools.api_calling import APICallingTool


async def test_coze_stream():
    """测试 Coze stream_run API"""
    tool = APICallingTool()
    
    url = "https://api.coze.cn/v1/workflow/stream_run"
    headers = {
        "Authorization": f"Bearer {COZE_API_KEY}",  # 直接硬编码
        "Content-Type": "application/json"
    }
    body = {
        "workflow_id": "7579565547005837331",
        "parameters": {
            "chart_url": "https://dify-storage-zenflux.s3.ap-southeast-1.amazonaws.com/uploads/20260113_153508_10329702_af781bee5d20bac15e0142731f8b94f0.txt",
            "query": "个人健康记录管理系统",
            "language": "中文"
        }
    }
    
    print("=" * 60)
    print("测试: stream=True")
    print("=" * 60)
    
    result = await tool.execute(
        url=url,
        method="POST",
        headers=headers,
        body=body,
        stream=True
    )
    
    print(f"\n结果 keys: {result.keys() if isinstance(result, dict) else 'N/A'}")
    print(f"events_count: {result.get('events_count', 'N/A')}")
    print(f"has text: {bool(result.get('text'))}")
    if result.get('text'):
        print(f"text: {result['text'][:1000]}...")
    if result.get('last_event'):
        print(f"last_event: {json.dumps(result['last_event'], ensure_ascii=False)[:500]}...")
    if result.get('error'):
        print(f"❌ 错误: {result['error']}")


if __name__ == "__main__":
    asyncio.run(test_coze_stream())
