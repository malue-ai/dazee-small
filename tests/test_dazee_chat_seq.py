"""
dazee_agent 聊天 seq 和事件测试

测试目标：
1. 验证返回的事件都包含 seq 字段
2. 验证 seq 从正整数开始递增
3. 验证事件类型符合 ZenO SSE 规范

运行方式：
    # 确保服务已启动
    uvicorn main:app --host 0.0.0.0 --port 8000
    
    # 运行测试
    pytest tests/test_dazee_chat_seq.py -v -s
"""

import json
import pytest
import httpx
from typing import List, Dict, Any, Optional
from uuid import uuid4


# ==================== 配置 ====================

# 测试服务器地址（假设本地运行）
BASE_URL = "http://localhost:8000"

# 测试超时（秒）- LLM 响应可能较慢
TEST_TIMEOUT = 180.0

# 最大事件数
MAX_EVENTS = 5000


# ==================== SSE 解析辅助函数 ====================

async def parse_sse_events(
    response: httpx.Response,
    max_events: int = MAX_EVENTS
) -> List[Dict[str, Any]]:
    """
    解析 SSE 事件流
    
    Args:
        response: httpx 响应对象
        max_events: 最大事件数（防止无限循环）
        
    Returns:
        事件列表
    """
    events = []
    event_count = 0
    
    async for line in response.aiter_lines():
        if event_count >= max_events:
            print(f"⚠️ 达到最大事件数 {max_events}，提前退出")
            break
            
        # SSE 格式：data: {...}
        line = line.strip()
        if line.startswith("data: "):
            try:
                data = json.loads(line[6:])
                events.append(data)
                event_count += 1
                
                # 检查是否结束事件
                event_type = data.get("type", "")
                if event_type in ("message.assistant.done", "session_end", "done"):
                    break
            except json.JSONDecodeError:
                # 忽略无法解析的行（如空行或注释）
                continue
    
    return events


async def send_chat_and_collect_events(
    message: str,
    user_id: str = None,
    agent_id: str = "dazee_agent"
) -> List[Dict[str, Any]]:
    """
    发送聊天请求并收集所有事件
    
    Args:
        message: 用户消息
        user_id: 用户 ID（可选）
        agent_id: Agent ID
        
    Returns:
        事件列表
    """
    if user_id is None:
        user_id = f"test_user_{uuid4().hex[:8]}"
    
    request_data = {
        "message": message,
        "userId": user_id,
        "agentId": agent_id,
        "stream": True
    }
    
    async with httpx.AsyncClient(timeout=httpx.Timeout(TEST_TIMEOUT)) as client:
        async with client.stream(
            "POST",
            f"{BASE_URL}/api/v1/chat",
            json=request_data,
            params={"format": "zeno"}
        ) as response:
            if response.status_code != 200:
                raise Exception(f"请求失败: {response.status_code}")
            return await parse_sse_events(response)


def extract_seq_values(events: List[Dict[str, Any]]) -> List[int]:
    """
    从事件列表中提取所有 seq 值
    
    Args:
        events: 事件列表
        
    Returns:
        seq 值列表
    """
    return [e.get("seq") for e in events if e.get("seq") is not None]


def filter_zeno_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    过滤出 ZenO 格式的事件（message.assistant.* 类型）
    
    Args:
        events: 事件列表
        
    Returns:
        ZenO 事件列表
    """
    zeno_prefixes = ("message.assistant.",)
    return [e for e in events if any(e.get("type", "").startswith(p) for p in zeno_prefixes)]


# ==================== 测试类 ====================

class TestDazeeChatSeq:
    """dazee_agent 聊天 seq 和事件测试"""
    
    @pytest.mark.asyncio
    async def test_seq_increments_correctly(self):
        """
        测试 seq 递增正确性
        
        验证：
        1. 每个事件都有 seq 字段
        2. seq 值单调递增
        """
        events = await send_chat_and_collect_events("你好，请简短回复")
        
        # 验证收到了事件
        assert len(events) > 0, "没有收到任何事件"
        
        # 提取 seq 值
        seq_values = extract_seq_values(events)
        
        # 验证每个 ZenO 事件都有 seq
        zeno_events = filter_zeno_events(events)
        for event in zeno_events:
            assert "seq" in event, f"事件缺少 seq 字段: {event.get('type')}"
        
        # 验证 seq 单调递增
        if len(seq_values) > 1:
            for i in range(1, len(seq_values)):
                assert seq_values[i] > seq_values[i - 1], (
                    f"seq 不是单调递增: {seq_values[i - 1]} -> {seq_values[i]}"
                )
        
        print(f"\n✅ seq 验证通过: {seq_values[:10]}{'...' if len(seq_values) > 10 else ''}")
    
    @pytest.mark.asyncio
    async def test_zeno_event_format(self):
        """
        测试 ZenO 事件格式
        
        验证 ZenO 格式的事件包含正确的字段：
        - message.assistant.start: message_id, conversation_id, session_id
        - message.assistant.delta: delta 对象
        - message.assistant.done: 结束事件
        """
        events = await send_chat_and_collect_events("请用一个字回复")
        
        zeno_events = filter_zeno_events(events)
        assert len(zeno_events) > 0, "没有收到 ZenO 格式的事件"
        
        # 验证各类型事件的字段
        for event in zeno_events:
            event_type = event.get("type", "")
            
            if event_type == "message.assistant.start":
                # start 事件必须包含的字段
                assert "message_id" in event, "start 事件缺少 message_id"
                assert "session_id" in event, "start 事件缺少 session_id"
                assert "timestamp" in event, "start 事件缺少 timestamp"
                print(f"\n✅ message.assistant.start 格式正确")
                print(f"   message_id: {event.get('message_id')}")
                print(f"   session_id: {event.get('session_id')}")
                
            elif event_type == "message.assistant.delta":
                # delta 事件必须包含 delta 对象
                assert "delta" in event, "delta 事件缺少 delta 字段"
                delta = event.get("delta", {})
                assert "type" in delta, "delta 对象缺少 type 字段"
                # type 可以是 thinking, response, progress 等
                
            elif event_type == "message.assistant.done":
                # done 事件
                print(f"\n✅ message.assistant.done 收到")
    
    @pytest.mark.asyncio
    async def test_event_type_sequence(self):
        """
        测试事件类型顺序
        
        验证事件序列：
        1. 必须以 message.assistant.start 开始
        2. 中间是 message.assistant.delta（可多个）
        3. 以 message.assistant.done 结束
        """
        events = await send_chat_and_collect_events("说好")
        
        zeno_events = filter_zeno_events(events)
        assert len(zeno_events) > 0, "没有收到 ZenO 格式的事件"
        
        # 提取事件类型序列
        event_types = [e.get("type") for e in zeno_events]
        
        # 验证以 start 开始
        assert event_types[0] == "message.assistant.start", (
            f"第一个事件应该是 message.assistant.start，实际是 {event_types[0]}"
        )
        
        # 验证以 done 结束
        assert event_types[-1] == "message.assistant.done", (
            f"最后一个事件应该是 message.assistant.done，实际是 {event_types[-1]}"
        )
        
        # 验证中间都是 delta 事件
        middle_events = event_types[1:-1]
        for event_type in middle_events:
            assert event_type == "message.assistant.delta", (
                f"中间事件应该是 message.assistant.delta，实际是 {event_type}"
            )
        
        print(f"\n✅ 事件序列验证通过")
        print(f"   总事件数: {len(zeno_events)}")
        print(f"   start: 1")
        print(f"   delta: {len(middle_events)}")
        print(f"   done: 1")
    
    @pytest.mark.asyncio
    async def test_seq_starts_from_positive(self):
        """
        测试 seq 从正整数开始
        
        验证第一个 seq 是正整数（通常是 1，但可能因为 session 事件而更大）
        """
        events = await send_chat_and_collect_events("hi")
        
        seq_values = extract_seq_values(events)
        assert len(seq_values) > 0, "没有收到带 seq 的事件"
        
        # 验证第一个 seq 是正整数
        first_seq = seq_values[0]
        assert isinstance(first_seq, int), f"seq 应该是整数，实际是 {type(first_seq)}"
        assert first_seq > 0, f"seq 应该是正整数，实际是 {first_seq}"
        
        print(f"\n✅ 第一个 seq: {first_seq}")


class TestDazeeChatSeqMultipleSessions:
    """多会话 seq 隔离测试"""
    
    @pytest.mark.asyncio
    async def test_different_sessions_have_independent_seq(self):
        """
        测试不同会话的 seq 相互独立
        
        两个独立的聊天请求应该各自从较小的 seq 开始（通常是 1）
        """
        # 第一个会话
        events1 = await send_chat_and_collect_events(
            "第一个会话，请简短回复",
            user_id=f"test_user_1_{uuid4().hex[:8]}"
        )
        
        # 第二个会话
        events2 = await send_chat_and_collect_events(
            "第二个会话，请简短回复",
            user_id=f"test_user_2_{uuid4().hex[:8]}"
        )
        
        seq1 = extract_seq_values(events1)
        seq2 = extract_seq_values(events2)
        
        assert len(seq1) > 0, "第一个会话没有收到带 seq 的事件"
        assert len(seq2) > 0, "第二个会话没有收到带 seq 的事件"
        
        # 两个会话都应该从较小的 seq 开始
        # 注意：可能不是严格从 1 开始，因为 session_start 等事件也会占用 seq
        print(f"\n✅ 会话 1 seq 范围: {seq1[0]} - {seq1[-1]}")
        print(f"✅ 会话 2 seq 范围: {seq2[0]} - {seq2[-1]}")
        
        # 验证两个会话的起始 seq 都是较小的正整数（< 100）
        assert seq1[0] < 100, f"会话 1 起始 seq 过大: {seq1[0]}"
        assert seq2[0] < 100, f"会话 2 起始 seq 过大: {seq2[0]}"


class TestDazeeChatEventContent:
    """事件内容测试"""
    
    @pytest.mark.asyncio
    async def test_delta_content_types(self):
        """
        测试 delta 事件的 content type
        
        验证 delta.type 是合法的类型：
        - thinking: 思考过程
        - response: 回复内容
        - progress: 进度信息
        - 等等
        """
        valid_delta_types = {
            "thinking",
            "response", 
            "progress",
            "intent",
            "preface",
            "clue",
            "files",
            "mind",
            "sql",
            "data",
            "chart",
            "recommended",
            "application",
            "interface",
        }
        
        events = await send_chat_and_collect_events("请回复好")
        
        delta_events = [
            e for e in events 
            if e.get("type") == "message.assistant.delta"
        ]
        
        delta_types_found = set()
        for event in delta_events:
            delta = event.get("delta", {})
            delta_type = delta.get("type")
            if delta_type:
                delta_types_found.add(delta_type)
                assert delta_type in valid_delta_types, (
                    f"未知的 delta.type: {delta_type}"
                )
        
        print(f"\n✅ 收到的 delta 类型: {delta_types_found}")


# ==================== 运行入口 ====================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
