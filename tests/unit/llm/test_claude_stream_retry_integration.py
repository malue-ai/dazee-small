# -*- coding: utf-8 -*-
"""
Claude 流式重试 — 集成测试（模拟真实网络中断）

使用本地 HTTP 服务模拟 Anthropic SSE streaming API：
1. 正常返回部分 SSE 事件后突然关闭连接
2. 触发真实的 httpx.RemoteProtocolError
3. 验证 ClaudeLLMService 的重试 + 非流式 fallback 机制

不需要真实 API Key，完全本地运行。
"""

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx
from aiohttp import web


# ============================================================
# Fake Anthropic SSE Server
# ============================================================

class FakeAnthropicServer:
    """
    Local HTTP server that mimics Claude's streaming Messages API.

    Supports two modes:
    - /v1/messages (POST, stream=true):  Returns SSE events then abruptly
      closes connection mid-stream to trigger RemoteProtocolError.
    - /v1/messages (POST, stream=false): Returns a complete JSON response
      (used by the non-streaming fallback).
    """

    def __init__(self):
        self.app = web.Application()
        self.app.router.add_post("/v1/messages", self._handle_messages)
        self.runner = None
        self.port = None
        # Counters for test assertions
        self.stream_call_count = 0
        self.non_stream_call_count = 0
        # Control behavior
        self.interrupt_after_events = 3  # Close connection after N SSE events
        self.non_stream_should_fail = False

    async def start(self) -> int:
        """Start server on a random available port. Returns port number."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        # Extract the actual port
        self.port = site._server.sockets[0].getsockname()[1]
        return self.port

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()

    async def _handle_messages(self, request: web.Request) -> web.StreamResponse:
        """Handle /v1/messages — stream or non-stream based on request body."""
        body = await request.json()
        is_stream = body.get("stream", False)

        if is_stream:
            return await self._handle_stream(request, body)
        else:
            return await self._handle_non_stream(request, body)

    async def _handle_stream(
        self, request: web.Request, body: dict
    ) -> web.StreamResponse:
        """
        Simulate Claude SSE streaming.

        Sends a few valid SSE events, then abruptly closes the connection
        (simulating network interruption / peer closed).
        """
        self.stream_call_count += 1

        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
            },
        )
        await response.prepare(request)

        # SSE events that mimic real Claude streaming
        sse_events = [
            # message_start
            {
                "type": "message_start",
                "message": {
                    "id": "msg_test123",
                    "type": "message",
                    "role": "assistant",
                    "content": [],
                    "model": body.get("model", "claude-sonnet-4-5-20250929"),
                    "stop_reason": None,
                    "usage": {"input_tokens": 100, "output_tokens": 0},
                },
            },
            # content_block_start (text)
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
            # content_block_delta (partial text)
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "现在整理关键信息"},
            },
            # content_block_delta (more text — this won't be sent)
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "，创建结构化数据："},
            },
            # content_block_start (tool_use — this won't be sent)
            {
                "type": "content_block_start",
                "index": 1,
                "content_block": {
                    "type": "tool_use",
                    "id": "toolu_test",
                    "name": "nodes",
                },
            },
        ]

        # Send events up to interrupt_after_events, then close abruptly
        for i, event in enumerate(sse_events):
            if i >= self.interrupt_after_events:
                # Abrupt close — this triggers RemoteProtocolError on the client
                break

            event_data = json.dumps(event)
            sse_line = f"event: {event['type']}\ndata: {event_data}\n\n"
            await response.write(sse_line.encode())
            await asyncio.sleep(0.05)  # Small delay to simulate real streaming

        # Close the connection abruptly WITHOUT sending message_stop
        # This is what happens in production when Anthropic drops the connection
        response.force_close()
        return response

    async def _handle_non_stream(
        self, request: web.Request, body: dict
    ) -> web.Response:
        """
        Non-streaming response (used by create_message_async fallback).
        Returns a complete valid Claude API response.
        """
        self.non_stream_call_count += 1

        if self.non_stream_should_fail:
            return web.Response(status=500, text="Internal Server Error")

        response_body = {
            "id": "msg_fallback123",
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": "这是通过非流式 fallback 恢复的完整响应。AI 圈最新动态已整理完成。",
                },
                {
                    "type": "tool_use",
                    "id": "toolu_fallback",
                    "name": "nodes",
                    "input": {
                        "action": "run",
                        "command": ["echo", "recovered"],
                    },
                },
            ],
            "model": body.get("model", "claude-sonnet-4-5-20250929"),
            "stop_reason": "tool_use",
            "usage": {
                "input_tokens": 200,
                "output_tokens": 100,
            },
        }
        return web.json_response(response_body)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
async def fake_server():
    """Start and stop the fake Anthropic server."""
    server = FakeAnthropicServer()
    port = await server.start()
    yield server
    await server.stop()


@pytest.fixture
def claude_service_with_fake_server(fake_server):
    """
    Create a real ClaudeLLMService pointing to the fake local server.
    Uses a real httpx client but with a fake base_url.
    """
    import anthropic
    from core.llm.claude import ClaudeLLMService

    # Create service with real Anthropic client pointing to fake server
    config = MagicMock()
    config.model = "claude-sonnet-4-5-20250929"
    config.max_tokens = 4096
    config.temperature = 1.0
    config.enable_caching = False
    config.enable_thinking = False
    config.thinking_budget = 10000
    config.api_key = "fake-api-key"

    service = ClaudeLLMService.__new__(ClaudeLLMService)
    service.config = config
    service._custom_tools = []
    service._betas = []

    # Create a real adaptor that does minimal conversion
    adaptor = MagicMock()
    adaptor.convert_messages_to_provider.return_value = {
        "messages": [{"role": "user", "content": "获取最近AI圈的一些时讯"}]
    }
    service._adaptor = adaptor

    # Create real Anthropic async client pointing to fake server
    service.async_client = anthropic.AsyncAnthropic(
        api_key="fake-api-key",
        base_url=f"http://127.0.0.1:{fake_server.port}",
    )

    return service


# ============================================================
# Helper
# ============================================================

async def collect_all(gen) -> list:
    results = []
    async for item in gen:
        results.append(item)
    return results


# ============================================================
# Integration Test: Real HTTP connection interrupted
# ============================================================

@pytest.mark.asyncio
async def test_real_stream_interrupt_triggers_fallback(
    fake_server, claude_service_with_fake_server
):
    """
    End-to-end test:
    1. Claude streaming starts, server sends 3 SSE events then closes connection
    2. Client gets RemoteProtocolError (real httpx error, not mocked)
    3. Service retries via non-streaming fallback
    4. Fallback returns complete response
    5. Verify the complete response is yielded
    """
    service = claude_service_with_fake_server

    # Mock create_message_async to use the fake server's non-stream endpoint
    # (The real create_message_async has @with_retry which complicates things,
    #  so we mock it to call the fake server directly)
    from core.llm.base import LLMResponse

    async def fake_fallback(*args, **kwargs):
        """Simulate what create_message_async would return."""
        return LLMResponse(
            content="AI 圈最新动态：通过 fallback 恢复的完整响应",
            tool_calls=[
                {
                    "id": "toolu_recovered",
                    "name": "nodes",
                    "input": {"action": "run", "command": ["echo", "ok"]},
                    "type": "tool_use",
                }
            ],
            stop_reason="tool_use",
            model="claude-sonnet-4-5-20250929",
            raw_content=[
                {"type": "text", "text": "AI 圈最新动态：通过 fallback 恢复的完整响应"},
                {
                    "type": "tool_use",
                    "id": "toolu_recovered",
                    "name": "nodes",
                    "input": {"action": "run", "command": ["echo", "ok"]},
                },
            ],
        )

    service.create_message_async = fake_fallback

    # Run the stream
    start = time.monotonic()
    responses = await collect_all(
        service.create_message_stream(
            messages=[],
            system="You are a helpful assistant.",
        )
    )
    elapsed = time.monotonic() - start

    # --- Assertions ---

    # 1. Stream was attempted (server received the request)
    assert fake_server.stream_call_count == 1, (
        f"Expected 1 stream call, got {fake_server.stream_call_count}"
    )

    # 2. Got some streaming responses before the error
    streaming_responses = [r for r in responses if r.is_stream]
    assert len(streaming_responses) >= 1, "Should have received some streaming data before interrupt"

    # 3. Final response is from the fallback (complete, not partial)
    final = responses[-1]
    assert final.stop_reason == "tool_use", (
        f"Expected stop_reason='tool_use' from fallback, got '{final.stop_reason}'"
    )
    assert "fallback" in final.content or "恢复" in final.content, (
        f"Expected fallback content, got: {final.content}"
    )
    assert final.tool_calls is not None and len(final.tool_calls) >= 1, (
        "Fallback should have returned complete tool_calls"
    )

    # 4. Retry had a delay (at least ~1 second)
    assert elapsed >= 0.8, f"Expected >= 0.8s (retry delay), got {elapsed:.2f}s"

    print(f"\n✅ Integration test passed!")
    print(f"   - Stream interrupted after {fake_server.interrupt_after_events} events")
    print(f"   - {len(streaming_responses)} streaming deltas received before interrupt")
    print(f"   - Fallback returned: {final.content[:60]}...")
    print(f"   - Tool calls recovered: {[tc.get('name') for tc in final.tool_calls]}")
    print(f"   - Total elapsed: {elapsed:.2f}s (includes retry delay)")


@pytest.mark.asyncio
async def test_real_stream_interrupt_both_fail(
    fake_server, claude_service_with_fake_server
):
    """
    When both stream AND fallback fail, should return stream_error partial response.
    """
    service = claude_service_with_fake_server

    # Fallback also fails
    service.create_message_async = AsyncMock(
        side_effect=httpx.ConnectError("all endpoints down")
    )

    responses = await collect_all(
        service.create_message_stream(
            messages=[],
            system="test",
        )
    )

    # Should get partial response with stream_error
    final = responses[-1]
    assert final.stop_reason == "stream_error", (
        f"Expected stream_error, got {final.stop_reason}"
    )
    assert final.is_stream is False
    # Should contain the partial text that was streamed before interrupt
    assert len(final.content) > 0, "Should have partial content from before interrupt"

    print(f"\n✅ Both-fail test passed!")
    print(f"   - Partial content preserved: '{final.content[:50]}...'")
    print(f"   - stop_reason: {final.stop_reason}")


@pytest.mark.asyncio
async def test_real_stream_immediate_disconnect(
    fake_server, claude_service_with_fake_server
):
    """
    Server closes connection immediately (0 events) → fallback or raise.
    """
    from core.llm.base import LLMResponse

    # Set server to interrupt before any events
    fake_server.interrupt_after_events = 0

    service = claude_service_with_fake_server

    # Fallback succeeds
    service.create_message_async = AsyncMock(
        return_value=LLMResponse(
            content="Recovered from immediate disconnect",
            stop_reason="end_turn",
            model="claude-sonnet-4-5-20250929",
        )
    )

    responses = await collect_all(
        service.create_message_stream(
            messages=[],
            system="test",
        )
    )

    # Fallback should have been called and succeeded
    final = responses[-1]
    assert "Recovered" in final.content
    assert final.stop_reason == "end_turn"

    print(f"\n✅ Immediate disconnect test passed!")
    print(f"   - Recovered via fallback: '{final.content}'")
