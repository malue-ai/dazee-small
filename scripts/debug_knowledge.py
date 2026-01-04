#!/usr/bin/env python3
"""
调试知识库问题：检查 Ragie 中的文档状态和 metadata
"""

import asyncio
import os
import sys

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# 加载环境变量
from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, ".env"))

from utils.ragie_client import get_ragie_client
from utils.knowledge_store import get_knowledge_store


async def main():
    print("=" * 60)
    print("🔍 知识库调试工具")
    print("=" * 60)
    
    # 1. 检查本地存储
    print("\n📦 本地存储 (knowledge_store.json):")
    store = get_knowledge_store()
    
    user_id = "user_1766974073604"  # 当前测试用户
    user = store.get_user(user_id)
    
    if not user:
        print(f"  ❌ 用户 {user_id} 不存在于本地存储")
        return
    
    print(f"  ✅ 用户: {user_id}")
    print(f"     Partition ID: {user.get('partition_id')}")
    
    documents = store.get_user_documents(user_id)
    print(f"  📄 文档数量: {len(documents)}")
    
    for doc in documents:
        print(f"\n     文档: {doc.get('filename')}")
        print(f"       ID: {doc.get('document_id')}")
        print(f"       状态: {doc.get('status')}")
        print(f"       Metadata: {doc.get('metadata')}")
    
    # 2. 检查 Ragie API
    print("\n" + "=" * 60)
    print("🌐 Ragie API 检查:")
    print("=" * 60)
    
    ragie = get_ragie_client()
    
    # 2.1 列出所有文档
    print("\n📋 Ragie 中的所有文档:")
    try:
        result = await ragie.list_documents(limit=10)
        ragie_docs = result.get("documents", [])
        print(f"   总数: {len(ragie_docs)}")
        
        for doc in ragie_docs:
            print(f"\n   文档: {doc.get('name')}")
            print(f"     ID: {doc.get('id')}")
            print(f"     状态: {doc.get('status')}")
            print(f"     Partition: {doc.get('partition')}")
            print(f"     Metadata: {doc.get('metadata')}")
    except Exception as e:
        print(f"   ❌ 列出文档失败: {e}")
    
    # 2.2 检索测试
    print("\n" + "=" * 60)
    print("🔍 检索测试:")
    print("=" * 60)
    
    test_query = "Multi-Agent 并行调度"
    
    # 不带 filter
    print(f"\n🔎 测试 1: 无 filter 检索 query='{test_query}'")
    try:
        result = await ragie.retrieve(query=test_query, top_k=5, filters=None)
        chunks = result.get("scored_chunks", [])
        print(f"   找到 {len(chunks)} 个结果")
        for chunk in chunks[:3]:
            print(f"   - score={chunk.get('score'):.3f}, doc={chunk.get('document_metadata', {}).get('filename', 'unknown')}")
            print(f"     text: {chunk.get('text', '')[:100]}...")
    except Exception as e:
        print(f"   ❌ 检索失败: {e}")
    
    # 带 user_id filter
    print(f"\n🔎 测试 2: 带 user_id filter 检索")
    try:
        filters = {"user_id": {"$eq": user_id}}
        print(f"   filters: {filters}")
        result = await ragie.retrieve(query=test_query, top_k=5, filters=filters)
        chunks = result.get("scored_chunks", [])
        print(f"   找到 {len(chunks)} 个结果")
        for chunk in chunks[:3]:
            print(f"   - score={chunk.get('score'):.3f}, doc={chunk.get('document_metadata', {}).get('filename', 'unknown')}")
    except Exception as e:
        print(f"   ❌ 检索失败: {e}")
    
    print("\n" + "=" * 60)
    print("✅ 调试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

