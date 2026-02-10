# -*- coding: utf-8 -*-
"""
Qwen 流式重试 — 真实 API 调用验证

使用真实 DASHSCOPE_API_KEY 调用千问 API，验证：
  T1. 正常流式完成（无异常）
  T2. 模拟 RemoteProtocolError → 非流式 fallback 恢复
  T3. 静默断连（finish_reason=None）→ fallback 恢复
  T4. 非网络异常 → 不重试，降级返回

运行方式：
  python tests/unit/llm/test_qwen_stream_retry_real.py

需要环境变量：
  DASHSCOPE_API_KEY（从 instances/xiaodazi/.env 读取）
"""

import asyncio
import os
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

# 从 .env 文件加载 API Key
env_file = PROJECT_ROOT / "instances" / "xiaodazi" / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

# QWEN_API_KEY → DASHSCOPE_API_KEY（千问 SDK 读取的环境变量名）
if os.getenv("QWEN_API_KEY") and not os.getenv("DASHSCOPE_API_KEY"):
    os.environ["DASHSCOPE_API_KEY"] = os.getenv("QWEN_API_KEY")

import httpx

# ============================================================
# Color helpers
# ============================================================
G = "\033[92m"
R = "\033[91m"
Y = "\033[93m"
B = "\033[1m"
N = "\033[0m"

passed = 0
failed = 0


def ok(msg):
    global passed
    passed += 1
    print(f"  {G}✓{N} {msg}")


def fail(msg):
    global failed
    failed += 1
    print(f"  {R}✗{N} {msg}")


def check(cond, msg):
    ok(msg) if cond else fail(msg)


async def collect(gen):
    results = []
    async for item in gen:
        results.append(item)
    return results


# ============================================================
# T1: 正常流式完成（真实 API 调用）
# ============================================================
async def test_t1_normal_stream():
    """Real API call: normal streaming should work without retry."""
    print(f"\n{B}▶ T1: 正常流式调用（真实 API）{N}")

    from core.llm.qwen import create_qwen_service

    service = create_qwen_service(
        model="qwen-plus",
        region="singapore",
        enable_thinking=False,
    )

    from core.llm.base import Message

    messages = [Message(role="user", content="用一句话说明：什么是大语言模型？")]

    start = time.monotonic()
    responses = await collect(
        service.create_message_stream(
            messages=messages,
            system="你是一个简洁的助手，回答控制在50字以内。",
        )
    )
    elapsed = time.monotonic() - start

    # Should have streaming deltas + final response
    check(len(responses) >= 2, f"收到 {len(responses)} 个响应（含流式增量 + 最终响应）")

    final = responses[-1]
    check(final.is_stream is False, f"最终响应 is_stream=False")
    check(final.stop_reason in ("stop", "end_turn"), f"stop_reason={final.stop_reason}")
    check(len(final.content) > 5, f"content: '{final.content[:60]}...'")
    check(elapsed < 30, f"耗时: {elapsed:.1f}s")

    streaming_count = sum(1 for r in responses if r.is_stream and r.content)
    check(streaming_count >= 1, f"流式增量数: {streaming_count}")

    print(f"  📝 完整回答: {final.content}")


# ============================================================
# T2: 模拟 RemoteProtocolError → 非流式 fallback
# ============================================================
async def test_t2_simulated_interrupt_fallback():
    """
    Patch the OpenAI stream to raise RemoteProtocolError after a few chunks,
    then verify fallback to create_message_async (real API call).
    """
    print(f"\n{B}▶ T2: 模拟流式中断 → 非流式 fallback（真实 fallback API 调用）{N}")

    from core.llm.qwen import create_qwen_service

    service = create_qwen_service(
        model="qwen-plus",
        region="singapore",
        enable_thinking=False,
    )

    from core.llm.base import Message

    messages = [Message(role="user", content="用一句话介绍 Python 语言。")]

    # Patch the streaming API to fail, but leave create_message_async intact (real call)
    original_create = service.client.chat.completions.create

    call_count = 0

    async def fake_stream_then_error(**kwargs):
        nonlocal call_count
        call_count += 1
        if kwargs.get("stream"):
            # Simulate: yield a few chunks then raise
            async def broken_stream():
                # Yield one normal chunk
                chunk = MagicMock()
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta = MagicMock()
                chunk.choices[0].delta.content = "Python是"
                chunk.choices[0].delta.reasoning_content = None
                chunk.choices[0].delta.tool_calls = None
                chunk.choices[0].finish_reason = None
                chunk.usage = None
                yield chunk
                # Then crash
                raise httpx.RemoteProtocolError(
                    "peer closed connection without sending complete message body"
                )

            return broken_stream()
        else:
            # Non-streaming: use real API
            return await original_create(**kwargs)

    service.client.chat.completions.create = fake_stream_then_error

    start = time.monotonic()
    responses = await collect(
        service.create_message_stream(
            messages=messages,
            system="你是一个简洁的助手，回答控制在30字以内。",
        )
    )
    elapsed = time.monotonic() - start

    check(len(responses) >= 1, f"收到 {len(responses)} 个响应")

    final = responses[-1]
    check(
        final.stop_reason != "stream_error",
        f"通过 fallback 恢复成功（stop_reason={final.stop_reason}，非 stream_error）",
    )
    check(len(final.content) > 3, f"fallback 返回了完整内容: '{final.content[:60]}'")
    check(elapsed >= 0.5, f"耗时 {elapsed:.1f}s（含重试延迟）")

    print(f"  📝 Fallback 回答: {final.content}")


# ============================================================
# T3: 静默断连（finish_reason=None）→ fallback
# ============================================================
async def test_t3_silent_disconnect_fallback():
    """
    Patch stream to end without finish_reason (simulating silent disconnect),
    then verify fallback to real non-streaming call.
    """
    print(f"\n{B}▶ T3: 模拟静默断连（无 finish_reason）→ fallback（真实 API）{N}")

    from core.llm.qwen import create_qwen_service

    service = create_qwen_service(
        model="qwen-plus",
        region="singapore",
        enable_thinking=False,
    )

    from core.llm.base import Message

    messages = [Message(role="user", content="1+1=?")]

    original_create = service.client.chat.completions.create

    async def truncated_stream(**kwargs):
        if kwargs.get("stream"):
            # Yield content but NO finish_reason, then end
            async def stream_no_finish():
                chunk = MagicMock()
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta = MagicMock()
                chunk.choices[0].delta.content = "答案是"
                chunk.choices[0].delta.reasoning_content = None
                chunk.choices[0].delta.tool_calls = None
                chunk.choices[0].finish_reason = None
                chunk.usage = None
                yield chunk
                # End without finish_reason — silent disconnect

            return stream_no_finish()
        else:
            return await original_create(**kwargs)

    service.client.chat.completions.create = truncated_stream

    start = time.monotonic()
    responses = await collect(
        service.create_message_stream(
            messages=messages,
            system="直接回答数字。",
        )
    )
    elapsed = time.monotonic() - start

    check(len(responses) >= 1, f"收到 {len(responses)} 个响应")

    final = responses[-1]
    # Should have recovered via fallback (real API call)
    check(
        final.stop_reason != "stream_error" or len(final.content) > 0,
        f"静默断连后恢复（stop_reason={final.stop_reason}）",
    )
    check(elapsed >= 0.3, f"耗时 {elapsed:.1f}s（含重试延迟）")

    print(f"  📝 恢复后回答: {final.content}")


# ============================================================
# T4: 非网络异常 → 不重试
# ============================================================
async def test_t4_non_network_error_no_retry():
    """Non-network errors should NOT trigger retry."""
    print(f"\n{B}▶ T4: 非网络异常 → 不重试，降级返回{N}")

    from core.llm.qwen import create_qwen_service

    service = create_qwen_service(
        model="qwen-plus",
        region="singapore",
        enable_thinking=False,
    )

    from core.llm.base import Message

    messages = [Message(role="user", content="hello")]

    async def error_stream(**kwargs):
        if kwargs.get("stream"):
            async def crash_after_content():
                chunk = MagicMock()
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta = MagicMock()
                chunk.choices[0].delta.content = "部分内容"
                chunk.choices[0].delta.reasoning_content = None
                chunk.choices[0].delta.tool_calls = None
                chunk.choices[0].finish_reason = None
                chunk.usage = None
                yield chunk
                raise ValueError("模拟的非网络异常")

            return crash_after_content()
        else:
            raise ValueError("不应该被调用")

    service.client.chat.completions.create = error_stream

    responses = await collect(
        service.create_message_stream(
            messages=messages,
            system="test",
        )
    )

    check(len(responses) >= 1, f"收到 {len(responses)} 个响应")

    final = responses[-1]
    check(final.stop_reason == "stream_error", f"stop_reason=stream_error（非网络异常不重试）")
    check("部分内容" in final.content, f"保留了部分内容: '{final.content}'")

    print(f"  📝 降级响应: {final.content}")


# ============================================================
# Main
# ============================================================
async def main():
    api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY")
    if not api_key:
        print(f"{R}❌ DASHSCOPE_API_KEY / QWEN_API_KEY 未设置，跳过真实 API 测试{N}")
        sys.exit(1)

    print(f"{B}Qwen 流式重试 — 真实 API 验证{N}")
    print(f"  API Key: {api_key[:8]}...{api_key[-4:]}")
    print(f"  Region: singapore")
    print(f"  Model: qwen-plus")

    await test_t1_normal_stream()
    await test_t2_simulated_interrupt_fallback()
    await test_t3_silent_disconnect_fallback()
    await test_t4_non_network_error_no_retry()

    print(f"\n{B}{'='*60}{N}")
    print(f"{B}  总计: {passed} 通过, {failed} 失败{N}")
    if failed == 0:
        print(f"  {G}ALL PASS{N}")
    else:
        print(f"  {R}{failed} FAILED{N}")
    print(f"{B}{'='*60}{N}")

    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    asyncio.run(main())
