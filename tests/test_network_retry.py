"""
测试网络重试机制

验证 V7.3 的网络重试机制是否正常工作
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch
import anthropic
import httpx

from core.llm import create_claude_service
from core.llm.base import Message


class TestNetworkRetry:
    """网络重试机制测试"""
    
    @pytest.mark.asyncio
    async def test_retry_on_connection_error(self):
        """测试连接错误自动重试"""
        llm = create_claude_service(
            model="claude-sonnet-4-5-20250929",
            enable_thinking=False
        )
        
        # Mock: 前 2 次失败，第 3 次成功
        call_count = 0
        
        async def mock_create(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            if call_count <= 2:
                # 模拟连接错误
                raise anthropic.APIConnectionError(
                    request=AsyncMock(),
                    message="Connection error"
                )
            
            # 第 3 次成功
            from anthropic.types import Message as AnthropicMessage, Usage, TextBlock
            return AnthropicMessage(
                id="msg_123",
                type="message",
                role="assistant",
                content=[TextBlock(type="text", text="成功响应")],
                model="claude-sonnet-4-5-20250929",
                stop_reason="end_turn",
                usage=Usage(input_tokens=10, output_tokens=5)
            )
        
        with patch.object(llm.async_client.messages, 'create', mock_create):
            response = await llm.create_message_async(
                messages=[Message(role="user", content="测试")]
            )
            
            assert response.content == "成功响应"
            assert call_count == 3  # 重试了 2 次
    
    @pytest.mark.asyncio
    async def test_retry_on_timeout_error(self):
        """测试超时错误自动重试"""
        llm = create_claude_service(
            model="claude-sonnet-4-5-20250929",
            enable_thinking=False
        )
        
        call_count = 0
        
        async def mock_create(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            if call_count == 1:
                # 模拟超时错误
                raise anthropic.APITimeoutError(request=AsyncMock())
            
            # 第 2 次成功
            from anthropic.types import Message as AnthropicMessage, Usage, TextBlock
            return AnthropicMessage(
                id="msg_124",
                type="message",
                role="assistant",
                content=[TextBlock(type="text", text="超时后成功")],
                model="claude-sonnet-4-5-20250929",
                stop_reason="end_turn",
                usage=Usage(input_tokens=10, output_tokens=5)
            )
        
        with patch.object(llm.async_client.messages, 'create', mock_create):
            response = await llm.create_message_async(
                messages=[Message(role="user", content="测试")]
            )
            
            assert response.content == "超时后成功"
            assert call_count == 2  # 重试了 1 次
    
    @pytest.mark.asyncio
    async def test_retry_on_rate_limit(self):
        """测试限流错误（429）自动重试"""
        llm = create_claude_service(
            model="claude-sonnet-4-5-20250929",
            enable_thinking=False
        )
        
        call_count = 0
        
        async def mock_create(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            if call_count == 1:
                # 模拟限流错误
                raise anthropic.RateLimitError(
                    message="Rate limit exceeded",
                    response=AsyncMock(),
                    body={}
                )
            
            # 第 2 次成功
            from anthropic.types import Message as AnthropicMessage, Usage, TextBlock
            return AnthropicMessage(
                id="msg_125",
                type="message",
                role="assistant",
                content=[TextBlock(type="text", text="限流后成功")],
                model="claude-sonnet-4-5-20250929",
                stop_reason="end_turn",
                usage=Usage(input_tokens=10, output_tokens=5)
            )
        
        with patch.object(llm.async_client.messages, 'create', mock_create):
            response = await llm.create_message_async(
                messages=[Message(role="user", content="测试")]
            )
            
            assert response.content == "限流后成功"
            assert call_count == 2
    
    @pytest.mark.asyncio
    async def test_no_retry_on_validation_error(self):
        """测试非网络错误不重试"""
        llm = create_claude_service(
            model="claude-sonnet-4-5-20250929",
            enable_thinking=False
        )
        
        call_count = 0
        
        async def mock_create(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            # 模拟验证错误（不应重试）
            raise anthropic.BadRequestError(
                message="Invalid parameter",
                response=AsyncMock(),
                body={}
            )
        
        with patch.object(llm.async_client.messages, 'create', mock_create):
            with pytest.raises(anthropic.BadRequestError):
                await llm.create_message_async(
                    messages=[Message(role="user", content="测试")]
                )
            
            assert call_count == 1  # 没有重试
    
    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        """测试超过最大重试次数后抛出异常"""
        llm = create_claude_service(
            model="claude-sonnet-4-5-20250929",
            enable_thinking=False
        )
        
        call_count = 0
        
        async def mock_create(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            # 每次都失败
            raise anthropic.APIConnectionError(
                request=AsyncMock(),
                message="Connection error"
            )
        
        with patch.object(llm.async_client.messages, 'create', mock_create):
            with pytest.raises(anthropic.APIConnectionError):
                await llm.create_message_async(
                    messages=[Message(role="user", content="测试")]
                )
            
            # 1 次初始调用 + 3 次重试 = 4 次
            assert call_count == 4


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
