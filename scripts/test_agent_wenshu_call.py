#!/usr/bin/env python
"""
测试 Agent 调用 wenshu_api 工具

通过 chat API 调用 agent，验证 agent 能否正确识别意图并调用 wenshu_api 工具
"""

import asyncio
import json
import httpx
import argparse
from datetime import datetime


# 默认配置
DEFAULT_CONFIG = {
    "api_base": "http://localhost:8000",
    "agent_id": "dazee_agent",
    "user_id": "user_test_wenshu",
    "format": "zeno",
}

# 测试文件（使用示例中的文件）
TEST_FILE = {
    "file_url": "https://dify-storage-zenflux.s3.amazonaws.com/chat-attachments/user_1768475079723/20260126/ea17e881-7104-40a4-86a3-98b4e00bca25_1fb6734f-cbe4-4228-8f18-bc0023b8314f.csv?AWSAccessKeyId=AKIAUPUSDVE22NYLK4XE&Signature=wjj9Eah4qxyRWwwRBQcgCt085R4%3D&Expires=1769498088",
    "file_name": "1fb6734f-cbe4-4228-8f18-bc0023b8314f.csv",
    "file_size": 1323,
    "file_type": "text/csv"
}


async def call_chat_api(
    message: str,
    files: list | None = None,
    session_id: str | None = None,
    conversation_id: str | None = None,
    config: dict | None = None
):
    """
    调用 chat API
    
    Args:
        message: 用户消息
        files: 文件列表
        session_id: 会话 ID（追问时使用）
        conversation_id: 对话 ID（追问时使用）
        config: 配置信息
    """
    config = config or DEFAULT_CONFIG
    
    url = f"{config['api_base']}/api/v1/chat?format={config['format']}"
    
    # 构建请求体
    request_body = {
        "message": message,
        "user_id": config["user_id"],
        "agent_id": config["agent_id"],
        "stream": True,
    }
    
    if files:
        request_body["files"] = files
    
    if session_id:
        request_body["session_id"] = session_id
    
    if conversation_id:
        request_body["conversation_id"] = conversation_id
    
    print("=" * 80)
    print(f"📤 请求 URL: {url}")
    print(f"📤 请求体:")
    # 打印请求体，但截断长 URL
    display_body = json.loads(json.dumps(request_body))
    if display_body.get("files"):
        for f in display_body["files"]:
            if len(f.get("file_url", "")) > 80:
                f["file_url"] = f["file_url"][:80] + "..."
    print(json.dumps(display_body, ensure_ascii=False, indent=2))
    print("=" * 80)
    
    # 发送请求
    print("\n🚀 开始调用 chat API（流式）...")
    print("-" * 80)
    
    session_info = {
        "session_id": None,
        "conversation_id": None,
        "message_id": None,
    }
    
    tool_calls = []
    full_content = ""
    event_count = 0
    
    try:
        timeout = httpx.Timeout(300.0)  # 5 分钟超时
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                url,
                headers={"Content-Type": "application/json"},
                json=request_body
            ) as response:
                print(f"📡 HTTP 状态码: {response.status_code}")
                
                if response.status_code != 200:
                    error_text = await response.aread()
                    print(f"❌ 错误响应: {error_text.decode()}")
                    return None
                
                # 读取 SSE 流
                async for line in response.aiter_lines():
                    line = line.strip()
                    
                    if not line:
                        continue
                    
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        
                        if data_str == "[DONE]":
                            print("\n\n✅ 流式响应完成")
                            break
                        
                        try:
                            data = json.loads(data_str)
                            event_count += 1
                            event_type = data.get("event") or data.get("type")
                            
                            # 解析不同类型的事件
                            if event_type == "session_start":
                                session_info["session_id"] = data.get("session_id")
                                session_info["conversation_id"] = data.get("conversation_id")
                                session_info["message_id"] = data.get("message_id")
                                print(f"\n📌 Session 开始: session_id={session_info['session_id']}")
                            
                            elif event_type == "tool_start":
                                tool_name = data.get("tool_name") or data.get("name")
                                tool_params = data.get("parameters") or data.get("params", {})
                                print(f"\n🔧 工具调用开始: {tool_name}")
                                print(f"   参数: {json.dumps(tool_params, ensure_ascii=False)[:500]}")
                                tool_calls.append({
                                    "name": tool_name,
                                    "params": tool_params,
                                    "status": "started"
                                })
                            
                            elif event_type == "tool_end":
                                tool_name = data.get("tool_name") or data.get("name")
                                result = data.get("result", {})
                                success = result.get("success", True) if isinstance(result, dict) else True
                                print(f"\n🔧 工具调用结束: {tool_name} - {'✅ 成功' if success else '❌ 失败'}")
                                if isinstance(result, dict):
                                    # 打印部分结果
                                    result_str = json.dumps(result, ensure_ascii=False)
                                    if len(result_str) > 500:
                                        print(f"   结果: {result_str[:500]}...")
                                    else:
                                        print(f"   结果: {result_str}")
                                # 更新工具调用状态
                                for tc in tool_calls:
                                    if tc["name"] == tool_name and tc["status"] == "started":
                                        tc["status"] = "success" if success else "failed"
                                        tc["result"] = result
                                        break
                            
                            elif event_type == "delta" or event_type == "text_delta":
                                delta = data.get("delta") or data.get("text", "")
                                if delta:
                                    print(delta, end="", flush=True)
                                    full_content += delta
                            
                            elif event_type == "error":
                                error_msg = data.get("error") or data.get("message", "未知错误")
                                print(f"\n❌ 错误: {error_msg}")
                            
                            elif event_type == "message_end":
                                print(f"\n\n📌 消息结束")
                            
                            else:
                                # 其他事件，简单打印
                                if event_count <= 10 or event_type in ["thinking_start", "thinking_end"]:
                                    print(f"\n📍 事件 [{event_type}]: {json.dumps(data, ensure_ascii=False)[:200]}")
                        
                        except json.JSONDecodeError:
                            # 非 JSON 数据，可能是普通文本
                            print(data_str, end="", flush=True)
                            full_content += data_str
    
    except httpx.TimeoutException:
        print("\n❌ 请求超时")
        return None
    except httpx.HTTPError as e:
        print(f"\n❌ 连接错误: {e}")
        return None
    except Exception as e:
        print(f"\n❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    # 打印总结
    print("\n")
    print("=" * 80)
    print("📊 调用总结")
    print("=" * 80)
    print(f"📌 Session ID: {session_info['session_id']}")
    print(f"📌 Conversation ID: {session_info['conversation_id']}")
    print(f"📌 Message ID: {session_info['message_id']}")
    print(f"📌 事件总数: {event_count}")
    print(f"📌 工具调用数: {len(tool_calls)}")
    
    if tool_calls:
        print("\n🔧 工具调用详情:")
        for i, tc in enumerate(tool_calls, 1):
            status_icon = "✅" if tc["status"] == "success" else ("❌" if tc["status"] == "failed" else "⏳")
            print(f"   {i}. {tc['name']} - {status_icon} {tc['status']}")
    
    print(f"\n📝 完整回复内容长度: {len(full_content)} 字符")
    
    return {
        "session_info": session_info,
        "tool_calls": tool_calls,
        "content": full_content,
    }


async def test_wenshu_analysis():
    """
    测试场景1：带文件的数据分析
    
    模拟用户上传 CSV 文件，让 agent 分析数据
    """
    print("\n" + "🧪" * 40)
    print("🧪 测试场景1：带文件的数据分析（应调用 wenshu_api）")
    print("🧪" * 40)
    
    message = "帮我分析一下这个数据文件的内容，给出数据概览和关键指标"
    
    result = await call_chat_api(
        message=message,
        files=[TEST_FILE]
    )
    
    if result:
        # 检查是否调用了 wenshu_api
        wenshu_calls = [tc for tc in result["tool_calls"] if "wenshu" in tc["name"].lower()]
        api_calls = [tc for tc in result["tool_calls"] if "api_calling" in tc["name"].lower()]
        
        print("\n" + "-" * 80)
        print("🔍 分析结果:")
        
        if wenshu_calls or api_calls:
            print("✅ Agent 正确调用了数据分析相关工具")
            for tc in wenshu_calls + api_calls:
                print(f"   - {tc['name']}: {tc['status']}")
        else:
            print("⚠️ Agent 没有调用 wenshu_api 或 api_calling 工具")
            print(f"   实际调用的工具: {[tc['name'] for tc in result['tool_calls']]}")
        
        return result
    
    return None


async def test_followup_question(session_info: dict):
    """
    测试场景2：追问（不带文件）
    
    在已有会话中追问，验证上下文保持
    """
    print("\n" + "🧪" * 40)
    print("🧪 测试场景2：追问（不带文件，应复用会话上下文）")
    print("🧪" * 40)
    
    if not session_info or not session_info.get("session_id"):
        print("⚠️ 没有有效的 session_id，跳过追问测试")
        return None
    
    message = "按类别分组看看各类的占比情况"
    
    result = await call_chat_api(
        message=message,
        files=None,  # 追问不带文件
        session_id=session_info["session_id"],
        conversation_id=session_info["conversation_id"]
    )
    
    return result


async def test_direct_wenshu_request():
    """
    测试场景3：明确指定使用问数分析
    
    使用更明确的指令，确保调用 wenshu_api
    """
    print("\n" + "🧪" * 40)
    print("🧪 测试场景3：明确指定使用问数分析")
    print("🧪" * 40)
    
    message = "使用问数平台分析这份数据，帮我统计各字段的分布情况"
    
    result = await call_chat_api(
        message=message,
        files=[TEST_FILE]
    )
    
    return result


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="测试 Agent 调用 wenshu_api")
    parser.add_argument("--test", choices=["all", "analysis", "followup", "direct"], 
                        default="analysis", help="选择测试场景")
    parser.add_argument("--api-base", default="http://localhost:8000", help="API 基础 URL")
    parser.add_argument("--agent-id", default="dazee_agent", help="Agent ID")
    parser.add_argument("--user-id", default="user_test_wenshu", help="用户 ID")
    
    args = parser.parse_args()
    
    # 更新配置
    DEFAULT_CONFIG["api_base"] = args.api_base
    DEFAULT_CONFIG["agent_id"] = args.agent_id
    DEFAULT_CONFIG["user_id"] = args.user_id
    
    print("=" * 80)
    print(f"🧪 Agent wenshu_api 调用测试")
    print(f"📅 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🔗 API: {args.api_base}")
    print(f"🤖 Agent: {args.agent_id}")
    print(f"👤 User: {args.user_id}")
    print("=" * 80)
    
    session_info = None
    
    if args.test in ["all", "analysis"]:
        result = await test_wenshu_analysis()
        if result:
            session_info = result["session_info"]
    
    if args.test in ["all", "followup"]:
        if session_info:
            await test_followup_question(session_info)
        else:
            print("\n⚠️ 跳过追问测试（需要先运行 analysis 测试）")
    
    if args.test in ["all", "direct"]:
        await test_direct_wenshu_request()
    
    print("\n" + "=" * 80)
    print("🏁 测试完成")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
