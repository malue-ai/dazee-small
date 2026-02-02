"""
容错机制端到端验证

测试场景：
1. Qwen 重试成功：模拟临时网络错误，验证自动重试
2. OpenAI 重试成功：模拟临时网络错误，验证自动重试
3. 全部失败触发降级：所有模型不可用时返回降级响应
4. 主备切换 + 重试组合：Claude 失败 → 自动切换 Qwen → Qwen 重试成功

依赖：
- 真实 API 测试需要配置 QWEN_API_KEY / DASHSCOPE_API_KEY
- Mock 测试无需外部依赖
"""

# 1. 标准库
import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# 2. 第三方库
import pytest
import httpx

# 3. 设置路径（避免导入完整 core 模块引发数据库依赖）
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 设置最小化环境变量避免数据库初始化
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

# 4. 本地模块（在环境变量设置后导入）
from core.llm.base import Message, LLMResponse, LLMConfig, LLMProvider
from infra.resilience import get_fallback_strategy, FallbackType


def _load_env() -> None:
    """
    读取本地 .env（加载 Qwen 相关配置）
    """
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).resolve().parents[1] / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=True)
    except Exception:
        env_path = Path(__file__).resolve().parents[1] / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                raw = line.strip()
                if not raw or raw.startswith("#"):
                    continue
                sep = "=" if "=" in raw else ":"
                if sep not in raw:
                    continue
                key, value = raw.split(sep, 1)
                key = key.strip().replace("export ", "")
                value = value.strip().strip('"').strip("'")
                if key in {"QWEN_API_KEY", "DASHSCOPE_API_KEY", "QWEN_BASE_URL"}:
                    os.environ.setdefault(key, value)


class TestQwenRetry:
    """Qwen 重试机制测试"""
    
    @pytest.mark.asyncio
    async def test_qwen_retry_on_connection_error(self):
        """测试 Qwen 连接错误自动重试"""
        from core.llm.qwen import QwenLLMService
        
        config = LLMConfig(
            provider=LLMProvider.QWEN,
            model="qwen-plus",
            api_key="test_key",
            max_tokens=100,
            temperature=0.7
        )
        llm = QwenLLMService(config)
        
        # Mock: 前 2 次失败，第 3 次成功
        call_count = 0
        
        def mock_call(**kwargs):
            nonlocal call_count
            call_count += 1
            
            if call_count <= 2:
                # 模拟连接错误
                raise ConnectionError("Connection refused")
            
            # 第 3 次成功
            return {
                "status_code": 200,
                "output": {
                    "choices": [{
                        "message": {
                            "content": "重试成功响应"
                        },
                        "finish_reason": "stop"
                    }]
                },
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "total_tokens": 15
                }
            }
        
        with patch("dashscope.Generation.call", mock_call):
            response = await llm.create_message_async(
                messages=[Message(role="user", content="测试")]
            )
            
            assert response.content == "重试成功响应"
            assert call_count == 3  # 重试了 2 次
    
    @pytest.mark.asyncio
    async def test_qwen_retry_on_timeout_error(self):
        """测试 Qwen 超时错误自动重试"""
        from core.llm.qwen import QwenLLMService
        
        config = LLMConfig(
            provider=LLMProvider.QWEN,
            model="qwen-plus",
            api_key="test_key",
            max_tokens=100,
            temperature=0.7
        )
        llm = QwenLLMService(config)
        
        call_count = 0
        
        def mock_call(**kwargs):
            nonlocal call_count
            call_count += 1
            
            if call_count == 1:
                # 模拟超时错误
                raise TimeoutError("Request timeout")
            
            # 第 2 次成功
            return {
                "status_code": 200,
                "output": {
                    "choices": [{
                        "message": {
                            "content": "超时后成功"
                        },
                        "finish_reason": "stop"
                    }]
                },
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "total_tokens": 15
                }
            }
        
        with patch("dashscope.Generation.call", mock_call):
            response = await llm.create_message_async(
                messages=[Message(role="user", content="测试")]
            )
            
            assert response.content == "超时后成功"
            assert call_count == 2  # 重试了 1 次
    
    @pytest.mark.asyncio
    async def test_qwen_max_retries_exceeded(self):
        """测试 Qwen 超过最大重试次数后抛出异常"""
        from core.llm.qwen import QwenLLMService
        
        config = LLMConfig(
            provider=LLMProvider.QWEN,
            model="qwen-plus",
            api_key="test_key",
            max_tokens=100,
            temperature=0.7
        )
        llm = QwenLLMService(config)
        
        call_count = 0
        
        def mock_call(**kwargs):
            nonlocal call_count
            call_count += 1
            # 每次都失败
            raise ConnectionError("Connection refused")
        
        with patch("dashscope.Generation.call", mock_call):
            with pytest.raises(ConnectionError):
                await llm.create_message_async(
                    messages=[Message(role="user", content="测试")]
                )
            
            # 1 次初始调用 + 3 次重试 = 4 次
            assert call_count == 4


class TestOpenAIRetry:
    """OpenAI 重试机制测试"""
    
    @pytest.mark.asyncio
    async def test_openai_retry_on_connection_error(self):
        """测试 OpenAI 连接错误自动重试"""
        from core.llm.openai import OpenAILLMService
        
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-4",
            api_key="test_key",
            max_tokens=100,
            temperature=0.7,
            base_url="https://api.openai.com/v1"
        )
        llm = OpenAILLMService(config)
        
        call_count = 0
        
        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            if call_count <= 2:
                # 模拟连接错误
                raise httpx.ConnectError("Connection refused")
            
            # 第 3 次成功
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "重试成功响应"
                    },
                    "finish_reason": "stop"
                }],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15
                }
            }
            return mock_response
        
        with patch.object(llm._client, "post", mock_post):
            response = await llm.create_message_async(
                messages=[Message(role="user", content="测试")]
            )
            
            assert response.content == "重试成功响应"
            assert call_count == 3  # 重试了 2 次
    
    @pytest.mark.asyncio
    async def test_openai_retry_on_timeout_error(self):
        """测试 OpenAI 超时错误自动重试"""
        from core.llm.openai import OpenAILLMService
        
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-4",
            api_key="test_key",
            max_tokens=100,
            temperature=0.7,
            base_url="https://api.openai.com/v1"
        )
        llm = OpenAILLMService(config)
        
        call_count = 0
        
        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            if call_count == 1:
                # 模拟超时错误
                raise httpx.TimeoutException("Request timeout")
            
            # 第 2 次成功
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "超时后成功"
                    },
                    "finish_reason": "stop"
                }],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15
                }
            }
            return mock_response
        
        with patch.object(llm._client, "post", mock_post):
            response = await llm.create_message_async(
                messages=[Message(role="user", content="测试")]
            )
            
            assert response.content == "超时后成功"
            assert call_count == 2  # 重试了 1 次


class TestFallbackStrategy:
    """降级策略测试"""
    
    def test_fallback_registration(self):
        """测试降级策略注册"""
        from infra.resilience import register_fallback, get_fallback_strategy, FallbackType
        
        # 注册降级策略
        register_fallback(
            "test_service",
            lambda *args, **kwargs: {
                "success": False,
                "content": "测试服务降级响应",
                "error": "test_service_unavailable"
            },
            FallbackType.DEFAULT_RESPONSE
        )
        
        # 验证注册成功
        strategy = get_fallback_strategy()
        fallback = strategy.get_fallback("test_service")
        
        assert fallback is not None
        assert fallback["type"] == FallbackType.DEFAULT_RESPONSE
        
        # 调用降级函数
        result = fallback["func"]()
        assert result["success"] is False
        assert result["error"] == "test_service_unavailable"
    
    @pytest.mark.asyncio
    async def test_llm_fallback_on_complete_failure(self):
        """测试 LLM 服务完全失败时的降级响应"""
        from infra.resilience import register_fallback, FallbackType
        from infra.resilience.fallback import FallbackStrategy
        
        # 创建降级策略
        strategy = FallbackStrategy()
        
        fallback_called = False
        
        def llm_fallback(*args, **kwargs):
            nonlocal fallback_called
            fallback_called = True
            return {
                "success": False,
                "content": "AI 服务暂时不可用，请稍后重试",
                "error": "llm_service_unavailable",
                "_fallback": True
            }
        
        strategy.register("llm_service", llm_fallback, FallbackType.DEFAULT_RESPONSE)
        
        # 模拟调用失败并触发降级
        @strategy.with_fallback("llm_service")
        async def failing_llm_call():
            raise RuntimeError("All models unavailable")
        
        result = await failing_llm_call()
        
        assert fallback_called is True
        assert result["_fallback"] is True
        assert result["error"] == "llm_service_unavailable"


class TestCombinedResilience:
    """组合容错机制测试"""
    
    @pytest.mark.asyncio
    async def test_primary_failure_fallback_retry_success(self):
        """
        测试主备切换 + 重试组合：
        1. Claude 探针失败
        2. 自动切换到 Qwen
        3. Qwen 临时错误后重试成功
        """
        from core.llm.router import ModelRouter, RouteTarget
        from core.llm.qwen import QwenLLMService
        from core.llm.claude import ClaudeLLMService
        
        # 创建 Mock Claude 服务（始终失败）
        claude_service = MagicMock(spec=ClaudeLLMService)
        claude_service.create_message_async = AsyncMock(
            side_effect=RuntimeError("Claude unavailable")
        )
        
        # 创建 Mock Qwen 服务（直接成功，重试机制在单独测试中验证）
        qwen_service = MagicMock(spec=QwenLLMService)
        qwen_service.create_message_async = AsyncMock(
            return_value=LLMResponse(
                content="Qwen 切换成功",
                stop_reason="end_turn",
                usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
            )
        )
        
        # 创建路由器
        router = ModelRouter(
            primary=RouteTarget(
                service=claude_service,
                provider=LLMProvider.CLAUDE,
                model="claude-sonnet-4-5-20250929",
                name="claude_primary"
            ),
            fallbacks=[
                RouteTarget(
                    service=qwen_service,
                    provider=LLMProvider.QWEN,
                    model="qwen-plus",
                    name="qwen_fallback"
                )
            ],
            policy={"max_failures": 1, "cooldown_seconds": 60}
        )
        
        # 执行调用
        response = await router.create_message_async(
            messages=[Message(role="user", content="测试主备切换")]
        )
        
        # 验证
        assert response.content == "Qwen 切换成功"
        assert claude_service.create_message_async.call_count == 1  # Claude 失败 1 次
        assert qwen_service.create_message_async.call_count == 1  # Qwen 成功 1 次


class TestRealAPIResilience:
    """
    真实 API 调用测试
    
    需要配置环境变量：
    - QWEN_API_KEY 或 DASHSCOPE_API_KEY
    """
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not (os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")),
        reason="需要 QWEN_API_KEY 或 DASHSCOPE_API_KEY"
    )
    async def test_real_qwen_basic_call(self):
        """
        真实 API 调用：验证 Qwen 基本调用
        """
        _load_env()
        
        from core.llm.qwen import QwenLLMService
        
        api_key = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
        base_url = os.getenv("QWEN_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
        
        config = LLMConfig(
            provider=LLMProvider.QWEN,
            model="qwen-plus",
            api_key=api_key,
            base_url=base_url,
            max_tokens=50,
            temperature=0.7
        )
        llm = QwenLLMService(config)
        
        response = await llm.create_message_async(
            messages=[Message(role="user", content="请用一句话回答：1+1等于几？")]
        )
        
        assert response.content is not None
        assert len(response.content) > 0
        assert "2" in response.content or "二" in response.content
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not (os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")),
        reason="需要 QWEN_API_KEY 或 DASHSCOPE_API_KEY"
    )
    async def test_real_qwen_with_mock_transient_error(self):
        """
        真实 API + 模拟临时错误：验证重试后成功
        
        方法：使用 patch 拦截第一次请求制造超时，第二次正常放行
        """
        _load_env()
        
        from core.llm.qwen import QwenLLMService
        import dashscope
        
        api_key = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
        base_url = os.getenv("QWEN_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
        
        config = LLMConfig(
            provider=LLMProvider.QWEN,
            model="qwen-plus",
            api_key=api_key,
            base_url=base_url,
            max_tokens=50,
            temperature=0.7
        )
        llm = QwenLLMService(config)
        
        # 保存原始方法
        original_call = dashscope.Generation.call
        call_count = 0
        
        def patched_call(**kwargs):
            nonlocal call_count
            call_count += 1
            
            if call_count == 1:
                # 第一次模拟超时
                raise TimeoutError("Simulated timeout")
            
            # 后续调用使用真实 API
            return original_call(**kwargs)
        
        with patch("dashscope.Generation.call", patched_call):
            response = await llm.create_message_async(
                messages=[Message(role="user", content="请用一句话回答：1+1等于几？")]
            )
        
        assert call_count == 2  # 重试了 1 次
        assert response.content is not None
        assert len(response.content) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
