"""
ZenO 适配器测试脚本

功能：
1. 测试 ZenO 适配器的事件转换功能
2. 验证输出格式是否符合 ZenO SSE 规范 v2.0.1
3. 启动模拟服务器接收事件

使用方法：
    python tests/test_zeno_adapter.py
"""

import asyncio
import json
from typing import Dict, Any
from core.events.adapters.zeno import ZenOAdapter
from logger import get_logger

logger = get_logger("test_zeno_adapter")


def print_event(title: str, event: Dict[str, Any]):
    """打印格式化的事件"""
    print(f"\n{'='*60}")
    print(f"📌 {title}")
    print(f"{'='*60}")
    print(json.dumps(event, ensure_ascii=False, indent=2))
    print(f"{'='*60}\n")


def test_message_start():
    """测试 message_start 转换"""
    adapter = ZenOAdapter(conversation_id="conv_test_001")
    
    zenflux_event = {
        "type": "message_start",
        "session_id": "sess_123",
        "conversation_id": "conv_456",
        "data": {
            "message_id": "msg_001"
        }
    }
    
    zeno_event = adapter.transform(zenflux_event)
    print_event("message_start → message.assistant.start", zeno_event)
    
    # 验证
    assert zeno_event["type"] == "message.assistant.start"
    assert zeno_event["message_id"] == "msg_001"
    assert "timestamp" in zeno_event
    logger.info("✅ message_start 转换测试通过")


def test_content_delta_thinking():
    """测试 content_delta (thinking) 转换"""
    adapter = ZenOAdapter(conversation_id="conv_test_001")
    adapter._current_message_id = "msg_001"
    
    zenflux_event = {
        "type": "content_delta",
        "session_id": "sess_123",
        "data": {
            "delta": {
                "type": "thinking_delta",
                "thinking": "让我先分析一下用户的需求..."
            }
        }
    }
    
    zeno_event = adapter.transform(zenflux_event)
    print_event("content_delta (thinking) → delta.type: thinking", zeno_event)
    
    # 验证
    assert zeno_event["type"] == "message.assistant.delta"
    assert zeno_event["delta"]["type"] == "thinking"
    assert zeno_event["delta"]["content"] == "让我先分析一下用户的需求..."
    logger.info("✅ content_delta (thinking) 转换测试通过")


def test_content_delta_text():
    """测试 content_delta (text) 转换"""
    adapter = ZenOAdapter(conversation_id="conv_test_001")
    adapter._current_message_id = "msg_001"
    
    zenflux_event = {
        "type": "content_delta",
        "session_id": "sess_123",
        "data": {
            "delta": {
                "type": "text_delta",
                "text": "你好！我是 AI 助手。"
            }
        }
    }
    
    zeno_event = adapter.transform(zenflux_event)
    print_event("content_delta (text) → delta.type: response", zeno_event)
    
    # 验证
    assert zeno_event["type"] == "message.assistant.delta"
    assert zeno_event["delta"]["type"] == "response"
    assert zeno_event["delta"]["content"] == "你好！我是 AI 助手。"
    logger.info("✅ content_delta (text) 转换测试通过")


def test_message_delta_plan():
    """测试 message_delta:plan 转换"""
    adapter = ZenOAdapter(conversation_id="conv_test_001")
    adapter._current_message_id = "msg_001"
    
    plan_data = {
        "goal": "生成 AI 技术趋势 PPT",
        "steps": [
            {"index": 0, "action": "分析用户需求", "status": "completed", "result": "已理解"},
            {"index": 1, "action": "调用 PPT 生成工具", "status": "in_progress", "result": ""},
            {"index": 2, "action": "返回文件", "status": "pending", "result": ""}
        ],
        "current_step": 1,
        "progress": 0.33
    }
    
    zenflux_event = {
        "type": "message_delta",
        "session_id": "sess_123",
        "data": {
            "delta": {
                "type": "plan",
                "content": json.dumps(plan_data, ensure_ascii=False)
            }
        }
    }
    
    zeno_event = adapter.transform(zenflux_event)
    print_event("message_delta:plan → delta.type: progress", zeno_event)
    
    # 验证
    assert zeno_event["type"] == "message.assistant.delta"
    assert zeno_event["delta"]["type"] == "progress"
    
    # 解析 progress 内容
    progress_data = json.loads(zeno_event["delta"]["content"])
    assert progress_data["title"] == "生成 AI 技术趋势 PPT"
    assert progress_data["status"] == "running"
    assert len(progress_data["subtasks"]) == 3
    assert progress_data["subtasks"][0]["status"] == "success"
    assert progress_data["subtasks"][1]["status"] == "running"
    assert progress_data["subtasks"][2]["status"] == "pending"
    
    logger.info("✅ message_delta:plan 转换测试通过")


def test_message_delta_confirmation():
    """测试 message_delta:confirmation_request 转换"""
    adapter = ZenOAdapter(conversation_id="conv_test_001")
    adapter._current_message_id = "msg_001"
    
    hitl_data = {
        "request_id": "req_123",
        "question": "是否继续生成 PPT？",
        "options": ["confirm", "cancel"],
        "confirmation_type": "yes_no"
    }
    
    zenflux_event = {
        "type": "message_delta",
        "session_id": "sess_123",
        "data": {
            "delta": {
                "type": "confirmation_request",
                "content": json.dumps(hitl_data, ensure_ascii=False)
            }
        }
    }
    
    zeno_event = adapter.transform(zenflux_event)
    print_event("message_delta:confirmation_request → delta.type: clue", zeno_event)
    
    # 验证
    assert zeno_event["type"] == "message.assistant.delta"
    assert zeno_event["delta"]["type"] == "clue"
    
    # 解析 clue 内容
    clue_data = json.loads(zeno_event["delta"]["content"])
    assert "tasks" in clue_data
    assert len(clue_data["tasks"]) == 2
    assert clue_data["tasks"][0]["act"] == "confirm"
    assert clue_data["tasks"][1]["act"] == "reply"
    
    logger.info("✅ message_delta:confirmation_request 转换测试通过")


def test_message_delta_recommended():
    """测试 message_delta:recommended 转换"""
    adapter = ZenOAdapter(conversation_id="conv_test_001")
    adapter._current_message_id = "msg_001"
    
    recommended_data = {
        "questions": [
            "什么是机器学习？",
            "AI 有哪些应用场景？",
            "深度学习和神经网络的区别是什么？"
        ]
    }
    
    zenflux_event = {
        "type": "message_delta",
        "session_id": "sess_123",
        "data": {
            "delta": {
                "type": "recommended",
                "content": json.dumps(recommended_data, ensure_ascii=False)
            }
        }
    }
    
    zeno_event = adapter.transform(zenflux_event)
    print_event("message_delta:recommended → delta.type: recommended", zeno_event)
    
    # 验证
    assert zeno_event["type"] == "message.assistant.delta"
    assert zeno_event["delta"]["type"] == "recommended"
    
    logger.info("✅ message_delta:recommended 转换测试通过")


def test_message_stop():
    """测试 message_stop 转换"""
    adapter = ZenOAdapter(conversation_id="conv_test_001")
    adapter._current_message_id = "msg_001"
    adapter._accumulated_content = "这是完整的响应内容。"
    
    zenflux_event = {
        "type": "message_stop",
        "session_id": "sess_123",
        "data": {
            "message_id": "msg_001"
        }
    }
    
    zeno_event = adapter.transform(zenflux_event)
    print_event("message_stop → message.assistant.done", zeno_event)
    
    # 验证
    assert zeno_event["type"] == "message.assistant.done"
    assert zeno_event["data"]["content"] == "这是完整的响应内容。"
    logger.info("✅ message_stop 转换测试通过")


def test_error():
    """测试 error 转换"""
    adapter = ZenOAdapter(conversation_id="conv_test_001")
    adapter._current_message_id = "msg_001"
    
    zenflux_event = {
        "type": "error",
        "session_id": "sess_123",
        "data": {
            "error": {
                "type": "network_error",
                "message": "API 调用超时"
            }
        }
    }
    
    zeno_event = adapter.transform(zenflux_event)
    print_event("error → message.assistant.error", zeno_event)
    
    # 验证
    assert zeno_event["type"] == "message.assistant.error"
    assert zeno_event["error"]["type"] == "network"
    assert zeno_event["error"]["retryable"] == True
    assert zeno_event["error"]["code"] == "NETWORK_ERROR"
    logger.info("✅ error 转换测试通过")


def test_extended_methods():
    """测试扩展方法"""
    adapter = ZenOAdapter(conversation_id="conv_test_001")
    
    # 测试 intent
    intent_event = adapter.create_intent_delta(
        message_id="msg_001",
        intent_id=1,
        intent_name="系统搭建",
        platform="Web"
    )
    print_event("扩展方法：create_intent_delta", intent_event)
    assert intent_event["delta"]["type"] == "intent"
    
    # 测试 preface
    preface_event = adapter.create_preface_delta(
        message_id="msg_001",
        preface_text="我将帮你生成一个关于 AI 的演示文稿。"
    )
    print_event("扩展方法：create_preface_delta", preface_event)
    assert preface_event["delta"]["type"] == "preface"
    
    # 测试 files
    files_event = adapter.create_files_delta(
        message_id="msg_001",
        files=[
            {"name": "demo.pptx", "type": "pptx", "url": "https://example.com/demo.pptx"},
            {"name": "report.pdf", "type": "pdf", "url": "https://example.com/report.pdf"}
        ]
    )
    print_event("扩展方法：create_files_delta", files_event)
    assert files_event["delta"]["type"] == "files"
    
    # 测试 mind (Mermaid)
    mind_event = adapter.create_mind_delta(
        message_id="msg_001",
        mermaid_content="graph TD; A-->B; B-->C;",
        chart_type="flowchart"
    )
    print_event("扩展方法：create_mind_delta", mind_event)
    assert mind_event["delta"]["type"] == "mind"
    
    logger.info("✅ 扩展方法测试通过")


def test_complete_flow():
    """测试完整的事件流"""
    print("\n" + "="*60)
    print("🚀 完整事件流测试")
    print("="*60 + "\n")
    
    adapter = ZenOAdapter(conversation_id="conv_test_001")
    
    events = [
        # 1. 消息开始
        {
            "type": "message_start",
            "session_id": "sess_123",
            "data": {"message_id": "msg_001"}
        },
        # 2. 思考过程
        {
            "type": "content_delta",
            "session_id": "sess_123",
            "data": {
                "delta": {"type": "thinking_delta", "thinking": "分析需求中..."}
            }
        },
        # 3. 文本响应
        {
            "type": "content_delta",
            "session_id": "sess_123",
            "data": {
                "delta": {"type": "text_delta", "text": "好的，我来帮你生成 PPT。"}
            }
        },
        # 4. 执行计划
        {
            "type": "message_delta",
            "session_id": "sess_123",
            "data": {
                "delta": {
                    "type": "plan",
                    "content": json.dumps({
                        "goal": "生成PPT",
                        "steps": [
                            {"index": 0, "action": "准备数据", "status": "completed"},
                            {"index": 1, "action": "生成内容", "status": "in_progress"}
                        ],
                        "current_step": 1,
                        "progress": 0.5
                    })
                }
            }
        },
        # 5. 消息结束
        {
            "type": "message_stop",
            "session_id": "sess_123",
            "data": {"message_id": "msg_001"}
        }
    ]
    
    for i, event in enumerate(events, 1):
        zeno_event = adapter.transform(event)
        if zeno_event:
            print(f"\n步骤 {i}: {event['type']}")
            print(f"转换为: {zeno_event['type']}")
            if "delta" in zeno_event:
                print(f"Delta 类型: {zeno_event['delta']['type']}")
            print(json.dumps(zeno_event, ensure_ascii=False, indent=2))
    
    logger.info("✅ 完整事件流测试通过")


def run_all_tests():
    """运行所有测试"""
    print("\n" + "="*60)
    print("🧪 ZenO 适配器测试套件")
    print("="*60 + "\n")
    
    try:
        test_message_start()
        test_content_delta_thinking()
        test_content_delta_text()
        test_message_delta_plan()
        test_message_delta_confirmation()
        test_message_delta_recommended()
        test_message_stop()
        test_error()
        test_extended_methods()
        test_complete_flow()
        
        print("\n" + "="*60)
        print("✅ 所有测试通过！")
        print("="*60 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        raise
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        raise


if __name__ == "__main__":
    run_all_tests()

