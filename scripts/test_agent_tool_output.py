#!/usr/bin/env python
"""
模拟 Agent 调用 wenshu_api 工具的输出

展示 Agent 实际产生的工具调用 JSON 和执行结果
"""

import asyncio
import os
import sys
import json
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(".env.development")


def print_section(title: str):
    """打印分节标题"""
    print("\n" + "=" * 70)
    print(f"📌 {title}")
    print("=" * 70)


async def simulate_agent_tool_call():
    """模拟 Agent 调用工具的完整流程"""
    
    from tools.api_calling import APICallingTool
    
    # 1. 加载配置
    with open("instances/dazee_agent/config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    apis = config.get("apis", [])
    tool = APICallingTool(apis_config=apis)
    
    # ========================================
    # 模拟 Agent 的思考过程
    # ========================================
    print_section("Agent 思考过程")
    
    thinking = """
用户上传了一个 CSV 数据文件，请求分析数据内容。

分析意图：
- 这是一个数据分析请求（意图2: BI智能问数）
- 需要使用问数平台 API 进行数据分析

选择工具：
- 根据 API 文档，应该使用 wenshu_api
- 需要传入 question 和 files 参数

构建调用参数：
- api_name: "wenshu_api"
- parameters:
  - question: 用户的问题
  - files: 包含 file_name 和 file_url
"""
    print(thinking)
    
    # ========================================
    # 模拟 Agent 生成的工具调用 JSON
    # ========================================
    print_section("Agent 生成的工具调用 (Tool Use)")
    
    # 这是 Agent（LLM）实际会生成的工具调用格式
    tool_call = {
        "type": "tool_use",
        "id": "toolu_01XYZ123abc",
        "name": "api_calling",
        "input": {
            "api_name": "wenshu_api",
            "parameters": {
                "question": "帮我分析一下这个数据文件的内容，给出数据概览和关键指标",
                "files": [
                    {
                        "file_name": "sales_data.csv",
                        "file_url": "https://dify-storage-zenflux.s3.amazonaws.com/chat-attachments/user_1768475079723/20260126/ea17e881-7104-40a4-86a3-98b4e00bca25_1fb6734f-cbe4-4228-8f18-bc0023b8314f.csv?AWSAccessKeyId=AKIAUPUSDVE22NYLK4XE&Signature=wjj9Eah4qxyRWwwRBQcgCt085R4%3D&Expires=1769498088"
                    }
                ]
            }
        }
    }
    
    print("```json")
    print(json.dumps(tool_call, ensure_ascii=False, indent=2))
    print("```")
    
    # ========================================
    # 框架处理：提取参数并调用工具
    # ========================================
    print_section("框架处理：提取参数")
    
    # 框架从 tool_call 中提取参数
    api_name = tool_call["input"]["api_name"]
    parameters = tool_call["input"]["parameters"]
    
    # 框架注入的上下文（来自 session/conversation）
    context = {
        "user_id": "user_1768475079723",
        "conversation_id": "conv_abc123",
        "session_id": "sess_xyz789"
    }
    
    print(f"api_name: {api_name}")
    print(f"parameters: {json.dumps(parameters, ensure_ascii=False)[:200]}...")
    print(f"context (框架注入): {context}")
    
    # ========================================
    # 实际构建的请求体
    # ========================================
    print_section("实际发送到 wenshu_api 的请求体")
    
    # 展示最终构建的请求体
    final_body = {
        "user_id": context["user_id"],
        "task_id": context["conversation_id"],
        "lg_code": "zh-CN",
        "question": parameters["question"],
        "files": parameters["files"]
    }
    
    print("```json")
    print(json.dumps(final_body, ensure_ascii=False, indent=2))
    print("```")
    
    # ========================================
    # 执行工具调用
    # ========================================
    print_section("执行工具调用")
    
    print("🚀 开始调用 wenshu_api...")
    print("   POST http://183.6.79.71:40202/api/v3/zeno/chat/question")
    print("   Headers: API-KEY: app-vr_Cwx...")
    print()
    
    result = await tool.execute(
        api_name=api_name,
        parameters=parameters,
        **context
    )
    
    # ========================================
    # 工具返回结果（给 Agent 的）
    # ========================================
    print_section("工具返回结果 (Tool Result)")
    
    tool_result = {
        "type": "tool_result",
        "tool_use_id": "toolu_01XYZ123abc",
        "content": result
    }
    
    # 格式化输出（截断过长内容）
    result_str = json.dumps(tool_result, ensure_ascii=False, indent=2)
    if len(result_str) > 3000:
        print(result_str[:3000])
        print("\n... (内容截断)")
    else:
        print(result_str)
    
    # ========================================
    # Agent 基于结果生成回复
    # ========================================
    print_section("Agent 基于结果生成的回复")
    
    if result.get("error"):
        print(f"❌ 工具调用失败: {result.get('error')}")
    else:
        # 提取关键信息
        data = result.get("data", {})
        report = data.get("report", {})
        
        print("Agent 会基于以下信息生成回复：")
        print(f"  - 意图识别: {data.get('intent_name', 'N/A')}")
        print(f"  - 报告标题: {report.get('title', 'N/A')}")
        print(f"  - Dashboard ID: {data.get('dashboard_id', 'N/A')}")
        
        # 模拟 Agent 的回复
        print("\n" + "-" * 50)
        print("📝 Agent 生成的回复预览：")
        print("-" * 50)
        
        content = report.get("content", "")
        if content:
            # 只显示前 1000 字符
            preview = content[:1000] if len(content) > 1000 else content
            print(preview)
            if len(content) > 1000:
                print("\n... (更多内容)")


async def main():
    """主函数"""
    print("=" * 70)
    print("🤖 模拟 Agent 调用 wenshu_api 工具")
    print("=" * 70)
    
    await simulate_agent_tool_call()
    
    print("\n" + "=" * 70)
    print("🏁 模拟完成")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
