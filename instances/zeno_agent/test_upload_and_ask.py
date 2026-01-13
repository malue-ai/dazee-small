#!/usr/bin/env python3
"""
测试：上传文件 → 获取 URL → 调用 ZenO Agent
"""

import asyncio
import sys
import aiohttp
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 加载环境变量（先加载根目录的，再加载实例的）
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")  # 根目录 .env（ANTHROPIC_API_KEY）
load_dotenv(PROJECT_ROOT / "instances/zeno_agent/.env")  # 实例 .env（ZENO_API_KEY）

# 配置
API_BASE = "http://localhost:8000"  # 系统 API 地址
USER_ID = "test_user"


async def upload_file(file_path: str) -> dict:
    """上传文件并返回文件信息"""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    print(f"📤 上传文件: {path.name}")
    
    async with aiohttp.ClientSession() as session:
        with open(path, 'rb') as f:
            data = aiohttp.FormData()
            data.add_field('file', f, filename=path.name)
            data.add_field('user_id', USER_ID)
            
            async with session.post(f"{API_BASE}/api/v1/files/upload", data=data) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(f"上传失败: {text}")
                result = await resp.json()
                file_id = result['data']['file_id']
                print(f"   ✅ 上传成功, file_id: {file_id}")
                
        # 获取文件 URL
        async with session.get(f"{API_BASE}/api/v1/files/{file_id}/url") as resp:
            if resp.status != 200:
                raise Exception("获取 URL 失败")
            result = await resp.json()
            file_url = result['data']['file_url']
            print(f"   📎 文件 URL: {file_url[:80]}...")
            
            return {
                "file_id": file_id,
                "file_name": path.name,
                "file_url": file_url
            }


async def test_with_files(files: list, question: str):
    """带文件测试 ZenO Agent"""
    from scripts.instance_loader import create_agent_from_instance
    
    print("\n⏳ 正在加载 zeno_agent...")
    agent = await create_agent_from_instance("zeno_agent")
    print("✅ 加载完成\n")
    
    # 构建消息 - 把文件信息写入 content，让 LLM 能看到
    file_info_text = "\n\n---\n**用户上传的文件：**"
    for f in files:
        file_info_text += f"\n- 文件名: {f['file_name']}"
        file_info_text += f"\n  URL: {f['file_url']}"
    
    user_message = {
        "role": "user",
        "content": question + file_info_text
    }
    
    print(f"👤 用户: {question}")
    for f in files:
        print(f"   📎 {f['file_name']}")
    print(f"\n🤖 助手: ", end="", flush=True)
    
    try:
        async for event in agent.chat(messages=[user_message]):
            event_type = event.get("type", "")
            
            if event_type == "message_delta":
                delta = event.get("delta", {})
                text = delta.get("text", "")
                if text:
                    print(text, end="", flush=True)
            
            elif event_type == "tool_use":
                tool_name = event.get("tool_name", "unknown")
                tool_input = event.get("tool_input", {})
                print(f"\n   🔧 调用工具: {tool_name}")
                if "url" in tool_input:
                    print(f"      URL: {tool_input.get('url', '')[:60]}...")
                if "body" in tool_input:
                    print(f"      Body: {str(tool_input.get('body', ''))[:100]}...")
            
            elif event_type == "tool_result":
                status = event.get("status", "unknown")
                print(f"   ✓ 工具结果: {status}", flush=True)
        
        print("\n")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()


async def main():
    # 要上传的文件
    file_paths = [
        "/Users/kens0n/projects/zenflux_agent/5月2.xlsx",
        # "/Users/kens0n/projects/zenflux_agent/employee_burnout_analysis-AI 2.xlsx",  # 可选
    ]
    
    # 上传文件
    uploaded_files = []
    for fp in file_paths:
        try:
            file_info = await upload_file(fp)
            uploaded_files.append(file_info)
        except Exception as e:
            print(f"❌ 上传失败: {e}")
            return
    
    if not uploaded_files:
        print("没有成功上传的文件")
        return
    
    # 测试问答
    await test_with_files(
        files=uploaded_files,
        question="帮我分析一下这份数据，总共有多少条记录？"
    )


if __name__ == "__main__":
    asyncio.run(main())

