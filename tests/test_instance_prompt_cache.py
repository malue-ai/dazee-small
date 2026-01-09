"""
测试 InstancePromptCache 端对端流程

测试场景：
1. 实例启动 → 提示词缓存加载
2. 用户查询 → 使用缓存的意图识别提示词
3. 意图识别 → 使用缓存的系统提示词版本

运行方式：
    cd /Users/liuyi/Documents/langchain/CoT_agent/mvp/zenflux_agent
    source /Users/liuyi/Documents/langchain/liuy/bin/activate
    python -m pytest tests/test_instance_prompt_cache.py -v

需要环境变量：
    ANTHROPIC_API_KEY: Anthropic API 密钥
"""

import asyncio
import os
import sys
from pathlib import Path

# 添加项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 从 .env 加载环境变量
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "instances/test_agent/.env", override=True)

import pytest

from core.prompt import (
    InstancePromptCache,
    load_instance_cache,
    get_instance_cache,
    TaskComplexity,
)
from core.prompt.intent_prompt_generator import IntentPromptGenerator


# ============================================================
# 测试 InstancePromptCache 基础功能
# ============================================================

class TestInstancePromptCacheBasic:
    """测试 InstancePromptCache 基础功能"""
    
    def setup_method(self):
        """每个测试前清空缓存"""
        InstancePromptCache.clear_all()
    
    def test_singleton_pattern(self):
        """测试单例模式"""
        cache1 = InstancePromptCache.get_instance("test_agent")
        cache2 = InstancePromptCache.get_instance("test_agent")
        
        assert cache1 is cache2, "同一实例应该返回同一对象"
        
        cache3 = InstancePromptCache.get_instance("another_agent")
        assert cache1 is not cache3, "不同实例应该返回不同对象"
    
    def test_initial_state(self):
        """测试初始状态"""
        cache = InstancePromptCache.get_instance("test_agent")
        
        assert cache.is_loaded is False
        assert cache.prompt_schema is None
        assert cache.agent_schema is None
        assert cache.system_prompt_simple is None
        assert cache.system_prompt_medium is None
        assert cache.system_prompt_complex is None
        assert cache.intent_prompt is None


# ============================================================
# 测试 IntentPromptGenerator
# ============================================================

class TestIntentPromptGenerator:
    """测试意图识别提示词生成器"""
    
    def test_get_default(self):
        """测试默认提示词"""
        prompt = IntentPromptGenerator.get_default()
        
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "task_type" in prompt
        assert "complexity" in prompt
        assert "skip_memory_retrieval" in prompt
    
    def test_generate_with_none_schema(self):
        """测试 schema 为 None 时的生成"""
        from core.prompt import PromptSchema
        
        schema = PromptSchema()
        prompt = IntentPromptGenerator.generate(schema)
        
        # 应该使用默认值
        assert isinstance(prompt, str)
        assert "task_type" in prompt


# ============================================================
# 测试 InstancePromptCache 加载（需要 API Key）
# ============================================================

@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY 未设置"
)
class TestInstancePromptCacheLoad:
    """测试 InstancePromptCache 加载（需要 API Key）"""
    
    def setup_method(self):
        """每个测试前清空缓存"""
        InstancePromptCache.clear_all()
    
    @pytest.mark.asyncio
    async def test_load_once_basic(self):
        """测试基本加载"""
        raw_prompt = """
# 测试 Agent

你是一个测试助手。

## 能力

- 回答问题
- 执行简单任务

## 规则

- 保持简洁
- 友好回复
"""
        cache = await load_instance_cache(
            instance_name="test_cache",
            raw_prompt=raw_prompt,
            force_refresh=True
        )
        
        assert cache.is_loaded is True
        assert cache.prompt_schema is not None
        assert cache.system_prompt_simple is not None
        assert cache.system_prompt_medium is not None
        assert cache.system_prompt_complex is not None
        assert cache.intent_prompt is not None
        
        # 验证三个版本的长度关系
        # Simple <= Medium <= Complex（通常）
        print(f"\n提示词版本长度:")
        print(f"  Simple: {len(cache.system_prompt_simple)} 字符")
        print(f"  Medium: {len(cache.system_prompt_medium)} 字符")
        print(f"  Complex: {len(cache.system_prompt_complex)} 字符")
    
    @pytest.mark.asyncio
    async def test_load_idempotent(self):
        """测试幂等性（多次加载同一内容）"""
        raw_prompt = "你是一个简单的测试助手。"
        
        cache = await load_instance_cache(
            instance_name="test_idempotent",
            raw_prompt=raw_prompt,
            force_refresh=True
        )
        
        first_load_time = cache.metrics.load_time_ms
        
        # 第二次加载（不应该重新处理）
        await cache.load_once(raw_prompt, force_refresh=False)
        
        # 应该是缓存命中
        assert cache.metrics.cache_hits > 0
        print(f"\n缓存命中: {cache.metrics.cache_hits} 次")
    
    @pytest.mark.asyncio
    async def test_get_system_prompt_by_complexity(self):
        """测试按复杂度获取系统提示词"""
        raw_prompt = """
# 数据分析助手

你是一个数据分析专家。

## 能力

- 数据分析
- 报表生成
- 可视化
"""
        cache = await load_instance_cache(
            instance_name="test_complexity",
            raw_prompt=raw_prompt,
            force_refresh=True
        )
        
        simple = cache.get_system_prompt(TaskComplexity.SIMPLE)
        medium = cache.get_system_prompt(TaskComplexity.MEDIUM)
        complex_ = cache.get_system_prompt(TaskComplexity.COMPLEX)
        
        assert isinstance(simple, str)
        assert isinstance(medium, str)
        assert isinstance(complex_, str)
        
        print(f"\n按复杂度获取提示词:")
        print(f"  SIMPLE: {len(simple)} 字符")
        print(f"  MEDIUM: {len(medium)} 字符")
        print(f"  COMPLEX: {len(complex_)} 字符")


# ============================================================
# 测试端对端流程（需要 API Key）
# ============================================================

@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY 未设置"
)
class TestE2EFlow:
    """测试端对端流程"""
    
    def setup_method(self):
        """每个测试前清空缓存"""
        InstancePromptCache.clear_all()
    
    @pytest.mark.asyncio
    async def test_instance_loader_with_cache(self):
        """测试 instance_loader 集成缓存"""
        from scripts.instance_loader import (
            load_instance_config,
            load_instance_prompt,
            list_instances
        )
        
        # 检查是否有可用实例
        instances = list_instances()
        if not instances:
            pytest.skip("没有可用的实例")
        
        # 使用 test_agent 实例（如果存在）
        instance_name = "test_agent" if "test_agent" in instances else instances[0]
        
        # 加载配置和提示词
        config = load_instance_config(instance_name)
        prompt = load_instance_prompt(instance_name)
        
        print(f"\n测试实例: {instance_name}")
        print(f"  配置: {config.name}")
        print(f"  提示词: {len(prompt)} 字符")
        
        # 加载缓存
        cache = await load_instance_cache(
            instance_name=instance_name,
            raw_prompt=prompt,
            config=config.raw_config,
            force_refresh=True
        )
        
        assert cache.is_loaded is True
        
        # 打印统计
        status = cache.get_status()
        print(f"\n缓存状态:")
        print(f"  is_loaded: {status['is_loaded']}")
        print(f"  prompt_schema: {status['prompt_schema']}")
        print(f"  agent_schema: {status['agent_schema']}")
        print(f"  system_prompts: {status['system_prompts']}")
        print(f"  intent_prompt: {status['intent_prompt']} 字符")
        print(f"  metrics: {status['metrics']}")
    
    @pytest.mark.asyncio
    async def test_intent_analyzer_with_cache(self):
        """测试 IntentAnalyzer 使用缓存的提示词"""
        from core.agent.intent_analyzer import create_intent_analyzer
        from core.llm import create_claude_service
        
        # 准备缓存
        raw_prompt = """
# 智能助手

你是一个多功能助手。

## 意图类型

- information_query: 信息查询
- content_generation: 内容生成
- data_analysis: 数据分析
"""
        cache = await load_instance_cache(
            instance_name="test_intent",
            raw_prompt=raw_prompt,
            force_refresh=True
        )
        
        # 创建 LLM 服务
        llm = create_claude_service(
            model="claude-haiku-4-5-20251001",
            enable_thinking=False,
            enable_caching=False,
            tools=[],
            max_tokens=8192
        )
        
        # 创建带缓存的 IntentAnalyzer
        analyzer = create_intent_analyzer(
            llm_service=llm,
            enable_llm=True,
            prompt_cache=cache
        )
        
        # 测试意图分析
        messages = [
            {"role": "user", "content": "帮我分析一下这个数据"}
        ]
        
        result = await analyzer.analyze(messages)
        
        print(f"\n意图分析结果:")
        print(f"  task_type: {result.task_type}")
        print(f"  complexity: {result.complexity}")
        print(f"  needs_plan: {result.needs_plan}")
        print(f"  skip_memory: {result.skip_memory_retrieval}")
        
        assert result.task_type is not None
        assert result.complexity is not None


# ============================================================
# 运行测试
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("InstancePromptCache 端对端测试")
    print("=" * 60)
    
    # 检查 API Key
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("\n⚠️  ANTHROPIC_API_KEY 未设置")
        print("   只运行不需要 API 的测试")
        print("\n   要运行完整测试，请设置:")
        print("   export ANTHROPIC_API_KEY=sk-ant-xxx")
    
    # 运行测试
    pytest.main([__file__, "-v", "-s"])
