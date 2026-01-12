"""
调试意图分析器

验证：
1. 意图提示词是否包含 Multi-Agent 部分
2. LLM 响应是否正确
3. 解析是否正确
"""

import asyncio
import sys
import os

# 添加项目路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# 加载环境变量
from dotenv import load_dotenv
env_path = os.path.join(project_root, "instances", "test_agent", ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
    print(f"✅ 已加载环境变量: {env_path}")
else:
    print(f"⚠️ 未找到环境变量文件: {env_path}")

from prompts.intent_recognition_prompt import (
    get_intent_recognition_prompt,
    INTENT_PROMPT_MULTI_AGENT
)
from core.llm import create_llm_service


async def main():
    print("=" * 70)
    print("🔍 调试意图分析器")
    print("=" * 70)
    
    # 1. 检查提示词是否包含 Multi-Agent 部分
    print("\n1️⃣ 检查意图识别提示词...")
    intent_prompt = get_intent_recognition_prompt()
    
    if "needs_multi_agent" in intent_prompt:
        print("   ✅ 提示词包含 needs_multi_agent 字段要求")
    else:
        print("   ❌ 提示词缺少 needs_multi_agent 字段要求！")
    
    if "Multi-Agent" in intent_prompt:
        print("   ✅ 提示词包含 Multi-Agent 判断规则")
    else:
        print("   ❌ 提示词缺少 Multi-Agent 判断规则！")
    
    if "研究 Top 5 云计算公司" in intent_prompt:
        print("   ✅ 提示词包含相关 Few-shot 示例")
    else:
        print("   ❌ 提示词缺少关键 Few-shot 示例！")
    
    # 打印 Multi-Agent 部分
    print("\n   📝 Multi-Agent 提示词模块（前500字符）:")
    print("-" * 50)
    print(INTENT_PROMPT_MULTI_AGENT[:500])
    print("-" * 50)
    
    # 2. 测试 LLM 调用
    print("\n2️⃣ 测试 LLM 意图分析...")
    
    test_query = "研究 Top 5 云计算公司（AWS、Azure、GCP、阿里云、腾讯云）的 AI 战略，生成对比分析报告"
    print(f"   测试 Query: {test_query}")
    
    try:
        # 创建 LLM 服务（使用 Haiku 进行意图分析）
        from config.llm_config import get_llm_profile
        
        profile = get_llm_profile("intent_analyzer")
        llm = create_llm_service(**profile)
        
        print(f"   使用模型: {profile.get('model', 'unknown')}")
        
        # 调用 LLM
        from core.llm import Message
        
        response = await llm.create_message_async(
            messages=[Message(role="user", content=test_query)],
            system=intent_prompt
        )
        
        # 解析响应
        response_text = response.content
        if isinstance(response_text, list):
            text_parts = []
            for block in response_text:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif hasattr(block, "text"):
                    text_parts.append(block.text)
            response_text = "".join(text_parts)
        
        print("\n   📤 LLM 原始响应:")
        print("-" * 50)
        print(response_text)
        print("-" * 50)
        
        # 解析 JSON
        from utils.json_utils import extract_json
        parsed = extract_json(response_text)
        
        print("\n   📊 解析结果:")
        if parsed:
            for key, value in parsed.items():
                marker = "✅" if key == "needs_multi_agent" and value == True else ""
                print(f"      {key}: {value} {marker}")
            
            if parsed.get("needs_multi_agent") == True:
                print("\n   🎉 意图分析正确识别需要 Multi-Agent！")
            else:
                print("\n   ⚠️ 意图分析未识别需要 Multi-Agent，需要优化提示词！")
        else:
            print("   ❌ 无法解析 JSON！")
        
    except Exception as e:
        print(f"   ❌ LLM 调用失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
